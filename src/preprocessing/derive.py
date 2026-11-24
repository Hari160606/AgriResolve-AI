"""Derived features: per-village indicators used by the monitoring modules.

Everything here is a pure function of the cleaned tables, so the numbers in the UI can
be reproduced from ``data/cleaned`` alone. Results are written to
``data/derived/village_features.csv``.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.config.settings import ensure_data_dirs, get_config, project_path
from src.preprocessing.clean import clean_all

KHARIF_MONTHS: tuple[int, ...] = (6, 7, 8, 9, 10)


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def season_totals(rainfall: pd.DataFrame, months: tuple[int, ...] = KHARIF_MONTHS) -> pd.DataFrame:
    """Season rainfall total per village and year.

    Args:
        rainfall: Cleaned monthly rainfall (village_id, year, month, rainfall_mm).
        months: Calendar months that make up the season.

    Returns:
        DataFrame with village_id, year, season_mm.
    """
    subset = rainfall[rainfall["month"].isin(months)]
    return (
        subset.groupby(["village_id", "year"], as_index=False)["rainfall_mm"]
        .sum()
        .rename(columns={"rainfall_mm": "season_mm"})
    )


def rainfall_anomaly(rainfall: pd.DataFrame, current_year: int, baseline_start_year: int) -> pd.DataFrame:
    """Current-season rainfall versus the multi-year baseline.

    The baseline is the mean of the same season in every year from ``baseline_start_year``
    up to ``current_year - 1`` that has data. Deviation is a fraction (negative = deficit),
    and the z-score uses the baseline year-to-year standard deviation.
    """
    totals = season_totals(rainfall)
    current = totals[totals["year"] == current_year].set_index("village_id")["season_mm"]
    baseline = totals[(totals["year"] >= baseline_start_year) & (totals["year"] < current_year)]
    stats = baseline.groupby("village_id")["season_mm"].agg(["mean", "std"]).rename(
        columns={"mean": "baseline_rain_mm", "std": "baseline_std_mm"}
    )
    frame = stats.join(current.rename("season_rain_mm"), how="left").reset_index()
    frame["baseline_std_mm"] = frame["baseline_std_mm"].fillna(0.0)
    frame["rainfall_deviation"] = (frame["season_rain_mm"] - frame["baseline_rain_mm"]) / frame[
        "baseline_rain_mm"
    ]
    safe_std = frame["baseline_std_mm"].replace(0.0, np.nan)
    frame["rainfall_z"] = ((frame["season_rain_mm"] - frame["baseline_rain_mm"]) / safe_std).fillna(0.0)
    return frame[
        [
            "village_id",
            "season_rain_mm",
            "baseline_rain_mm",
            "rainfall_deviation",
            "rainfall_z",
        ]
    ]


def ndvi_features(ndvi: pd.DataFrame) -> pd.DataFrame:
    """Latest NDVI, year-on-year change and within-village monthly anomaly."""
    rows: list[dict[str, object]] = []
    for village_id, group in ndvi.groupby("village_id"):
        valid = group.dropna(subset=["ndvi_mean"]).sort_values(["year", "month"])
        if valid.empty:
            rows.append(
                {
                    "village_id": village_id,
                    "ndvi_latest": np.nan,
                    "ndvi_prev_year": np.nan,
                    "ndvi_delta_yoy": np.nan,
                    "ndvi_3m_mean": np.nan,
                    "ndvi_z": 0.0,
                    "ndvi_latest_period": None,
                }
            )
            continue
        latest = valid.iloc[-1]
        year, month = int(latest["year"]), int(latest["month"])
        prev = valid[(valid["year"] == year - 1) & (valid["month"] == month)]
        prev_value = float(prev["ndvi_mean"].iloc[0]) if not prev.empty else np.nan
        history = valid[valid["month"] == month]["ndvi_mean"]
        std = float(history.std(ddof=0)) if len(history) > 1 else 0.0
        z = 0.0 if std == 0 else (float(latest["ndvi_mean"]) - float(history.mean())) / std
        rows.append(
            {
                "village_id": village_id,
                "ndvi_latest": round(float(latest["ndvi_mean"]), 3),
                "ndvi_prev_year": None if np.isnan(prev_value) else round(prev_value, 3),
                "ndvi_delta_yoy": None if np.isnan(prev_value) else round(float(latest["ndvi_mean"]) - prev_value, 3),
                "ndvi_3m_mean": round(float(valid.tail(3)["ndvi_mean"].mean()), 3),
                "ndvi_z": round(float(z), 2),
                "ndvi_latest_period": f"{year}-{month:02d}",
            }
        )
    return pd.DataFrame(rows)


def weather_features(weather: pd.DataFrame, reference_date: date, weeks: int = 4) -> pd.DataFrame:
    """Heat and dry-spell indicators over the last ``weeks`` weeks."""
    cutoff = pd.Timestamp(reference_date) - timedelta(weeks=weeks)
    recent = weather[weather["week_start"] >= cutoff]
    frame = recent.groupby("village_id").agg(
        heat_weeks=("temp_max_c", lambda s: int((s >= 35.0).sum())),
        dry_weeks=("rainfall_mm", lambda s: int((s < 2.0).sum())),
        recent_rain_mm=("rainfall_mm", "sum"),
        max_temp_c=("temp_max_c", "max"),
    )
    return frame.reset_index()


def inspection_features(inspections: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """Days since the last inspection per village (999 when never inspected)."""
    frame = inspections.groupby("village_id")["inspection_date"].max().reset_index()
    frame["last_inspection_date"] = pd.to_datetime(frame["inspection_date"])
    frame["days_since_inspection"] = (pd.Timestamp(reference_date) - frame["last_inspection_date"]).dt.days
    frame = frame.drop(columns=["inspection_date"])
    # Villages with no inspection history at all must still appear.
    return frame


def reliability_features(ndvi: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """Per-village data reliability: completeness, cloud burden and recency.

    Score = 0.50 * completeness + 0.25 * (1 - cloud fraction) + 0.25 * recency factor,
    where completeness is the share of the last 12 months with a valid NDVI retrieval.
    """
    ref = pd.Timestamp(reference_date)
    cutoff = ref - pd.DateOffset(months=12)
    rows = []
    for village_id, group in ndvi.groupby("village_id"):
        window = group[(group["year_month"] >= cutoff) & (group["year_month"] <= ref)]
        months_present = len(window)
        valid = int(window["ndvi_mean"].notna().sum())
        completeness = valid / 12.0
        cloud = float(window["cloud_cover_pct"].mean()) if months_present else 100.0
        latest_valid = group.dropna(subset=["ndvi_mean"])["year_month"].max()
        if pd.isna(latest_valid):
            recency_days = 365
        else:
            recency_days = int(max(0, (ref - latest_valid).days))
        recency_factor = _clip01(1 - recency_days / 60.0)
        score = _clip01(0.50 * completeness + 0.25 * (1 - cloud / 100.0) + 0.25 * recency_factor)
        rows.append(
            {
                "village_id": village_id,
                "completeness": round(completeness, 3),
                "cloud_cover_avg": round(cloud, 1),
                "ndvi_recency_days": recency_days,
                "reliability_score": round(score, 3),
            }
        )
    return pd.DataFrame(rows)


def build_village_features(tables: dict[str, pd.DataFrame], reference_date: date) -> pd.DataFrame:
    """Merge every derived indicator into one village-level feature table."""
    cfg = get_config()
    villages = tables["villages"]
    features = villages[
        [
            "village_id",
            "village_name",
            "latitude",
            "longitude",
            "cultivated_area_ha",
            "road_distance_km",
        ]
    ].copy()
    features = features.merge(
        rainfall_anomaly(tables["rainfall_monthly"], reference_date.year, cfg.baseline_start_year),
        on="village_id",
        how="left",
    )
    features = features.merge(ndvi_features(tables["ndvi_monthly"]), on="village_id", how="left")
    features = features.merge(weather_features(tables["weather_weekly"], reference_date), on="village_id", how="left")
    features = features.merge(
        inspection_features(tables["inspections_history"], reference_date), on="village_id", how="left"
    )
    features = features.merge(reliability_features(tables["ndvi_monthly"], reference_date), on="village_id", how="left")
    features["days_since_inspection"] = features["days_since_inspection"].fillna(999).astype(int)
    features["heat_weeks"] = features["heat_weeks"].fillna(0).astype(int)
    features["dry_weeks"] = features["dry_weeks"].fillna(0).astype(int)
    features["reliability_score"] = features["reliability_score"].fillna(0.0)
    return features.sort_values("village_id").reset_index(drop=True)


def main() -> None:
    """Run cleaning + feature derivation and write the derived tables."""
    ensure_data_dirs()
    tables, _ = clean_all()
    reference_date = get_config().reference_date
    features = build_village_features(tables, reference_date)
    out = project_path("data", "derived", "village_features.csv")
    features.to_csv(out, index=False)
    print(f"Village features -> {out.relative_to(project_path())} ({len(features)} villages)")


if __name__ == "__main__":
    main()
