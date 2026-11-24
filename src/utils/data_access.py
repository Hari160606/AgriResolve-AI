"""Single data-access layer for the Streamlit app.

Two modes, chosen automatically:

``postgres``
    ``DB_*`` is configured in ``.env`` and the database answers. Tables are read with
    SQLAlchemy. Writes (new complaints, assignments, approvals) are persisted.

``demo-csv``
    PostgreSQL is not configured/unreachable, so the app reads the CSVs in
    ``data/cleaned`` and ``data/derived`` that the pipeline scripts produce. Writes are
    kept in memory for the session only and the UI shows a warning banner. This keeps
    the prototype demoable while the database password is still pending - it is not a
    second database, just a read-through cache of the same pipeline output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import pandas as pd

from src.config.settings import database_url, db_configured, get_config, project_path

try:  # SQLAlchemy is only needed for the postgres mode.
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    _SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal installs
    _SQLALCHEMY_AVAILABLE = False
    SQLAlchemyError = Exception  # type: ignore[assignment,misc]

Mode = Literal["postgres", "demo-csv"]

#: In-memory writes used in demo mode (cleared when the app process restarts).
_DEMO_COMPLAINTS: list[dict[str, Any]] = []
_DEMO_ASSIGNMENTS: list[dict[str, Any]] = []
_DEMO_APPROVALS: dict[str, dict[str, Any]] = {}


@dataclass
class Repository:
    """Read/write facade used by every Streamlit page."""

    mode: Mode = "demo-csv"
    error: str | None = None
    engine: Any = None
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict)

    @classmethod
    def connect(cls) -> "Repository":
        """Try PostgreSQL, fall back to the CSV demo mode with a recorded reason."""
        if not _SQLALCHEMY_AVAILABLE:
            return cls(mode="demo-csv", error="SQLAlchemy is not installed.")
        url = database_url()
        if url is None:
            return cls(mode="demo-csv", error="DB_* is not configured in .env (demo mode).")
        try:
            engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return cls(mode="postgres", engine=engine)
        except Exception as exc:  # noqa: BLE001 - surface any driver/auth error to the UI
            return cls(mode="demo-csv", error=f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ helpers
    def _read(self, table: str) -> pd.DataFrame:
        if table in self._cache:
            return self._cache[table].copy()
        if self.mode == "postgres":
            frame = pd.read_sql_table(table, self.engine)
        else:
            frame = self._read_csv(table)
        self._cache[table] = frame
        return frame.copy()

    @staticmethod
    def _read_csv(table: str) -> pd.DataFrame:
        """Read a pipeline CSV, preferring ``data/cleaned`` over ``data/derived``."""
        for folder in ("cleaned", "derived"):
            path = project_path("data", folder, f"{table}.csv")
            if path.exists():
                return pd.read_csv(path)
        raise FileNotFoundError(f"No CSV found for table '{table}'. Run the pipeline scripts first.")

    # ------------------------------------------------------------------ reads
    def villages(self) -> pd.DataFrame:
        return self._read("villages")

    def rsk(self) -> pd.DataFrame:
        return self._read("rsk")

    def crops(self) -> pd.DataFrame:
        return self._read("crops")

    def staff(self) -> pd.DataFrame:
        return self._read("staff")

    def features(self) -> pd.DataFrame:
        return self._read("village_features")

    def complaints(self) -> pd.DataFrame:
        frame = self._read("farmer_complaints")
        frame["reported_date"] = pd.to_datetime(frame["reported_date"])
        if self.mode == "demo-csv" and _DEMO_COMPLAINTS:
            extra = pd.DataFrame(_DEMO_COMPLAINTS)
            extra["reported_date"] = pd.to_datetime(extra["reported_date"])
            frame = pd.concat([frame, extra], ignore_index=True)
        return frame

    def inspections(self) -> pd.DataFrame:
        frame = self._read("inspections_history")
        frame["inspection_date"] = pd.to_datetime(frame["inspection_date"])
        return frame

    def assignments(self) -> pd.DataFrame:
        frame = self._read("assignments")
        for column in ("assigned_date", "due_date"):
            frame[column] = pd.to_datetime(frame[column])
        if self.mode == "demo-csv" and _DEMO_ASSIGNMENTS:
            extra = pd.DataFrame(_DEMO_ASSIGNMENTS)
            for column in ("assigned_date", "due_date"):
                extra[column] = pd.to_datetime(extra[column])
            frame = pd.concat([frame, extra], ignore_index=True)
        return frame

    def rainfall(self) -> pd.DataFrame:
        return self._read("rainfall_monthly")

    def ndvi(self) -> pd.DataFrame:
        return self._read("ndvi_monthly")

    def reliability(self) -> pd.DataFrame:
        return self._read("village_features")[
            ["village_id", "completeness", "cloud_cover_avg", "ndvi_recency_days", "reliability_score"]
        ]

    def approvals(self) -> dict[str, dict[str, Any]]:
        """Return ``{village_id: {'approved_by', 'approved_at'}}`` for this run."""
        if self.mode == "postgres":
            latest = self._latest_run_date()
            if latest is None:
                return {}
            frame = pd.read_sql_query(
                text(
                    "SELECT village_id, approved_by, approved_at FROM priority_scores "
                    "WHERE run_date = :run_date AND approved_by IS NOT NULL"
                ).bindparams(run_date=latest),
                self.engine,
            )
            return {
                row.village_id: {"approved_by": row.approved_by, "approved_at": row.approved_at}
                for row in frame.itertuples()
            }
        return dict(_DEMO_APPROVALS)

    def _latest_run_date(self) -> date | None:
        frame = pd.read_sql_query(text("SELECT max(run_date) AS run_date FROM priority_scores"), self.engine)
        value = frame["run_date"].iloc[0]
        return None if pd.isna(value) else value

    # ------------------------------------------------------------------ writes
    def add_complaint(self, payload: dict[str, Any]) -> str:
        """Persist a validated complaint and return its id."""
        complaint_id = self._next_id("CMP", self.complaints()["complaint_id"].tolist())
        row = {"complaint_id": complaint_id, **payload, "is_synthetic": True, "data_type": "Synthetic"}
        if self.mode == "postgres":
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO farmer_complaints
                            (complaint_id, village_id, crop_id, category, affected_area_ha,
                             urgency, reported_date, description, reporter_role, status,
                             is_synthetic, data_type)
                        VALUES (:complaint_id, :village_id, :crop_id, :category, :affected_area_ha,
                                :urgency, :reported_date, :description, :reporter_role, :status,
                                TRUE, 'Synthetic')
                        """
                    ),
                    {**row, "reported_date": str(row["reported_date"])},
                )
        else:
            _DEMO_COMPLAINTS.append(row)
        self._cache.pop("farmer_complaints", None)
        return complaint_id

    def add_assignment(self, payload: dict[str, Any]) -> str:
        """Create an assignment for a village and staff member."""
        assignment_id = self._next_id("ASG", self.assignments()["assignment_id"].tolist())
        row = {"assignment_id": assignment_id, **payload, "is_synthetic": True, "data_type": "Synthetic"}
        if self.mode == "postgres":
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO assignments
                            (assignment_id, village_id, staff_id, assigned_date, due_date,
                             status, priority_rank, notes, is_synthetic, data_type)
                        VALUES (:assignment_id, :village_id, :staff_id, :assigned_date, :due_date,
                                :status, :priority_rank, :notes, TRUE, 'Synthetic')
                        """
                    ),
                    {
                        **row,
                        "assigned_date": str(row["assigned_date"]),
                        "due_date": None if row.get("due_date") is None else str(row["due_date"]),
                    },
                )
        else:
            _DEMO_ASSIGNMENTS.append(row)
        self._cache.pop("assignments", None)
        return assignment_id

    def approve_village(self, village_id: str, approved_by: str, run_date: date) -> None:
        """Record that the AO approved a village's priority for this run date."""
        if self.mode == "postgres":
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE priority_scores SET approved_by = :approved_by, approved_at = now() "
                        "WHERE village_id = :village_id AND run_date = :run_date"
                    ),
                    {"approved_by": approved_by, "village_id": village_id, "run_date": run_date},
                )
        else:
            _DEMO_APPROVALS[village_id] = {
                "approved_by": approved_by,
                "approved_at": pd.Timestamp.now().isoformat(timespec="seconds"),
            }

    def save_engine_outputs(
        self,
        priority: pd.DataFrame,
        factors: pd.DataFrame,
        routine: pd.DataFrame,
        reported: pd.DataFrame,
        run_date: date,
    ) -> bool:
        """Write monitoring + priority results to PostgreSQL (no-op in demo mode)."""
        if self.mode != "postgres":
            return False
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM priority_scores WHERE run_date = :d"), {"d": run_date})
            connection.execute(
                text("DELETE FROM monitoring_results WHERE run_date = :d"), {"d": run_date}
            )
            for row in routine.itertuples():
                connection.execute(
                    text(
                        """
                        INSERT INTO monitoring_results
                            (run_date, village_id, trigger, flag, risk_score, explanation,
                             reliability_score, factors, is_synthetic, data_type)
                        VALUES (:d, :village_id, 'routine_monitoring', :flag, :risk_score, :explanation,
                                :reliability_score, :factors, TRUE, 'Synthetic')
                        ON CONFLICT (run_date, village_id, trigger) DO NOTHING
                        """
                    ),
                    {
                        "d": run_date,
                        "village_id": row.village_id,
                        "flag": bool(row.flag),
                        "risk_score": float(row.risk_score),
                        "explanation": row.explanation,
                        "reliability_score": float(row.reliability_score),
                        "factors": json.dumps(
                            {k: float(row[f"factor_{k}"]) for k in FACTOR_COLUMNS}
                        ),
                    },
                )
            for row in reported.itertuples():
                connection.execute(
                    text(
                        """
                        INSERT INTO monitoring_results
                            (run_date, village_id, trigger, flag, severity_score, severity_level,
                             explanation, factors, is_synthetic, data_type)
                        VALUES (:d, :village_id, 'reported_issue', TRUE, :severity_score,
                                :severity_level, :explanation, :factors, TRUE, 'Synthetic')
                        ON CONFLICT (run_date, village_id, trigger) DO NOTHING
                        """
                    ),
                    {
                        "d": run_date,
                        "village_id": row.village_id,
                        "severity_score": float(row.severity_score),
                        "severity_level": row.severity_level,
                        "explanation": row.explanation,
                        "factors": json.dumps({k: float(row[f"factor_{k}"]) for k in REPORTED_FACTORS}),
                    },
                )
            for row in priority.itertuples():
                priority_id = connection.execute(
                    text(
                        """
                        INSERT INTO priority_scores
                            (run_date, village_id, rank, priority_score, band, explanation,
                             overlap_detected, dedupe_rule, is_synthetic, data_type)
                        VALUES (:d, :village_id, :rank, :score, :band, :explanation,
                                :overlap, :rule, TRUE, 'Synthetic')
                        ON CONFLICT (run_date, village_id) DO UPDATE
                            SET priority_score = EXCLUDED.priority_score,
                                rank = EXCLUDED.rank,
                                band = EXCLUDED.band,
                                explanation = EXCLUDED.explanation
                        RETURNING priority_id
                        """
                    ),
                    {
                        "d": run_date,
                        "village_id": row.village_id,
                        "rank": int(row.rank),
                        "score": float(row.priority_score),
                        "band": row.band,
                        "explanation": row.explanation,
                        "overlap": bool(row.overlap_detected),
                        "rule": None if pd.isna(row.dedupe_rule) else row.dedupe_rule,
                    },
                ).scalar_one()
                subset = factors[factors["village_id"] == row.village_id]
                for factor in subset.itertuples():
                    connection.execute(
                        text(
                            """
                            INSERT INTO priority_score_factors
                                (priority_id, factor, factor_value, weight, contribution)
                            VALUES (:pid, :factor, :value, :weight, :contribution)
                            ON CONFLICT (priority_id, factor) DO UPDATE
                                SET factor_value = EXCLUDED.factor_value,
                                    weight = EXCLUDED.weight,
                                    contribution = EXCLUDED.contribution
                            """
                        ),
                        {
                            "pid": priority_id,
                            "factor": factor.factor,
                            "value": float(factor.factor_value),
                            "weight": float(factor.weight),
                            "contribution": float(factor.contribution),
                        },
                    )
        return True

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _next_id(prefix: str, existing: list[str]) -> str:
        """Return the next free ``PREFIX0001``-style id."""
        numbers = []
        for value in existing:
            text_value = str(value)
            if text_value.startswith(prefix):
                try:
                    numbers.append(int(text_value[len(prefix):]))
                except ValueError:
                    continue
        return f"{prefix}{(max(numbers) + 1) if numbers else 1:04d}"


FACTOR_COLUMNS: tuple[str, ...] = (
    "rainfall_deficit",
    "ndvi_decline",
    "vegetation_anomaly",
    "weather_risk",
    "inspection_recency",
    "data_reliability_gap",
)
REPORTED_FACTORS: tuple[str, ...] = (
    "urgency",
    "category",
    "affected_area",
    "repeat_complaints",
    "waiting_days",
    "report_recency",
)


def mode_banner(repository: Repository) -> str:
    """Return a one-line status string for the sidebar."""
    cfg = get_config()
    if repository.mode == "postgres":
        return f"Data source: PostgreSQL (configured in .env). Reference date {cfg.reference_date}."
    return (
        "Data source: CSV demo mode - PostgreSQL is not configured, so form submissions "
        f"are not persisted. Reason: {repository.error}"
    )
