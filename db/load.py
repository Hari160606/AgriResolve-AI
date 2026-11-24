"""Load the pipeline CSVs into PostgreSQL.

Usage (from the project root, with ``DB_*`` set in ``.env``)::

    python -m db.load --init          # create schema first, then load
    python -m db.load                 # load data only
    python -m db.load --init --results  # also persist monitoring/priority results

The loader is deliberately idempotent: it truncates the tables it owns before inserting.
It never touches a table it does not know about.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from src.config.settings import database_url, get_config, project_path

#: Insert order respects foreign keys.
TABLE_ORDER: tuple[str, ...] = (
    "rsk",
    "villages",
    "crops",
    "village_crops",
    "staff",
    "rainfall_observations",
    "ndvi_observations",
    "weather_observations",
    "farmer_complaints",
    "inspections_history",
    "assignments",
)

#: CSV file name -> database table name.
CSV_TO_TABLE: dict[str, str] = {
    "rsk": "rsk",
    "villages": "villages",
    "crops": "crops",
    "village_crops": "village_crops",
    "staff": "staff",
    "rainfall_monthly": "rainfall_observations",
    "ndvi_monthly": "ndvi_observations",
    "weather_weekly": "weather_observations",
    "farmer_complaints": "farmer_complaints",
    "inspections_history": "inspections_history",
    "assignments": "assignments",
}

#: Columns to drop because the database generates them.
GENERATED_COLUMNS: dict[str, list[str]] = {
    "rainfall_observations": ["observation_id"],
    "ndvi_observations": ["observation_id"],
    "weather_observations": ["observation_id"],
}


def _engine():
    url = database_url()
    if url is None:
        raise SystemExit(
            "PostgreSQL is not configured. Copy .env.example to .env and set DB_NAME, "
            "DB_USER and DB_PASSWORD first."
        )
    from sqlalchemy import create_engine

    return create_engine(url, future=True)


def apply_schema(engine) -> None:
    """Execute ``db/schema.sql`` against the configured database."""
    from sqlalchemy import text

    sql = project_path("db", "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.exec_driver_sql(sql)
    print("Schema applied from db/schema.sql")


def load_tables(engine) -> dict[str, int]:
    """Truncate and load every reference/observation table from the CSVs."""
    from sqlalchemy import text

    counts: dict[str, int] = {}
    with engine.begin() as connection:
        # One TRUNCATE ... CASCADE keeps referential integrity simple and fast.
        connection.execute(
            text("TRUNCATE " + ", ".join(TABLE_ORDER) + " RESTART IDENTITY CASCADE")
        )
    for csv_name, table in CSV_TO_TABLE.items():
        path = project_path("data", "cleaned", f"{csv_name}.csv")
        if not path.exists():
            print(f"  skip {table}: {path.name} not found (run the pipeline first)")
            continue
        frame = pd.read_csv(path)
        for column in GENERATED_COLUMNS.get(table, []):
            if column in frame.columns:
                frame = frame.drop(columns=[column])
        frame.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=500)
        counts[table] = len(frame)
        print(f"  loaded {table:26s} {len(frame):5d} rows")
    return counts


def load_results(engine) -> None:
    """Persist monitoring and priority outputs for the configured reference date."""
    from sqlalchemy import text

    cfg = get_config()
    run_date = cfg.reference_date
    routine = pd.read_csv(project_path("data", "derived", "monitoring_results.csv"))
    reported = pd.read_csv(project_path("data", "derived", "reported_monitoring.csv"))
    priority = pd.read_csv(project_path("data", "derived", "priority_scores.csv"))
    factors = pd.read_csv(project_path("data", "derived", "priority_score_factors.csv"))
    reliability = pd.read_csv(project_path("data", "derived", "village_features.csv"))

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM monitoring_results WHERE run_date = :d"), {"d": run_date})
        connection.execute(text("DELETE FROM priority_scores WHERE run_date = :d"), {"d": run_date})
        connection.execute(
            text("DELETE FROM data_reliability WHERE as_of = :d"), {"d": run_date}
        )
        for row in reliability.itertuples():
            connection.execute(
                text(
                    """
                    INSERT INTO data_reliability
                        (village_id, as_of, completeness, cloud_cover_avg, ndvi_recency_days,
                         reliability_score, is_synthetic, data_type)
                    VALUES (:vid, :d, :completeness, :cloud, :recency, :score, TRUE, 'Derived')
                    ON CONFLICT (village_id, as_of) DO NOTHING
                    """
                ),
                {
                    "vid": row.village_id,
                    "d": run_date,
                    "completeness": float(row.completeness),
                    "cloud": float(row.cloud_cover_avg),
                    "recency": int(row.ndvi_recency_days),
                    "score": float(row.reliability_score),
                },
            )
        for row in routine.itertuples():
            connection.execute(
                text(
                    """
                    INSERT INTO monitoring_results
                        (run_date, village_id, trigger, flag, risk_score, explanation,
                         reliability_score, factors, is_synthetic, data_type)
                    VALUES (:d, :vid, 'routine_monitoring', :flag, :score, :explanation,
                            :reliability, :factors, TRUE, 'Synthetic')
                    """
                ),
                {
                    "d": run_date,
                    "vid": row.village_id,
                    "flag": bool(row.flag),
                    "score": float(row.risk_score),
                    "explanation": row.explanation,
                    "reliability": float(row.reliability_score),
                    "factors": json.dumps(
                        {
                            name: float(getattr(row, f"factor_{name}"))
                            for name in (
                                "rainfall_deficit",
                                "ndvi_decline",
                                "vegetation_anomaly",
                                "weather_risk",
                                "inspection_recency",
                                "data_reliability_gap",
                            )
                        }
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
                    VALUES (:d, :vid, 'reported_issue', TRUE, :score, :level, :explanation,
                            :factors, TRUE, 'Synthetic')
                    """
                ),
                {
                    "d": run_date,
                    "vid": row.village_id,
                    "score": float(row.severity_score),
                    "level": row.severity_level,
                    "explanation": row.explanation,
                    "factors": json.dumps(
                        {
                            name: float(getattr(row, f"factor_{name}"))
                            for name in (
                                "urgency",
                                "category",
                                "affected_area",
                                "repeat_complaints",
                                "waiting_days",
                                "report_recency",
                            )
                        }
                    ),
                },
            )
        for row in priority.itertuples():
            priority_id = connection.execute(
                text(
                    """
                    INSERT INTO priority_scores
                        (run_date, village_id, rank, priority_score, band, explanation,
                         overlap_detected, dedupe_rule, is_synthetic, data_type)
                    VALUES (:d, :vid, :rank, :score, :band, :explanation, :overlap, :rule,
                            TRUE, 'Synthetic')
                    RETURNING priority_id
                    """
                ),
                {
                    "d": run_date,
                    "vid": row.village_id,
                    "rank": int(row.rank),
                    "score": float(row.priority_score),
                    "band": row.band,
                    "explanation": row.explanation,
                    "overlap": bool(row.overlap_detected),
                    "rule": None if pd.isna(row.dedupe_rule) else row.dedupe_rule,
                },
            ).scalar_one()
            for factor in factors[factors["village_id"] == row.village_id].itertuples():
                connection.execute(
                    text(
                        """
                        INSERT INTO priority_score_factors
                            (priority_id, factor, factor_value, weight, contribution)
                        VALUES (:pid, :factor, :value, :weight, :contribution)
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
    print(f"Results persisted for run_date={run_date}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Load AgriResolve AI data into PostgreSQL")
    parser.add_argument("--init", action="store_true", help="apply db/schema.sql first")
    parser.add_argument("--results", action="store_true", help="also store engine outputs")
    args = parser.parse_args()

    engine = _engine()
    if args.init:
        apply_schema(engine)
    counts = load_tables(engine)
    if args.results:
        load_results(engine)
    print(f"\nDone: {sum(counts.values())} rows across {len(counts)} tables on {date.today()}.")


if __name__ == "__main__":
    main()
