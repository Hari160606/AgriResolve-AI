"""Seeded generator for the AgriResolve AI synthetic dataset.

Why this exists
---------------
Google Earth Engine, the Google Weather/Routes APIs and the IMD/KGIS downloads are
*not* configured in this prototype yet (see ``docs/api_setup.md``). So that the
pipeline stays demonstrable end to end, this module fabricates internally consistent
observations and *labels every row* with ``is_synthetic = TRUE`` /
``data_type = 'Synthetic'``.

Rules honoured here (master instructions A2.5):
    * raw real data is never overwritten - this writes only to ``data/synthetic``;
    * every row carries a synthetic flag;
    * generation is seeded, documented (``docs/synthetic_assumptions.md``) and
      internally consistent (dates line up with the Kharif season, complaints refer
      to crops the village actually grows, pest/drought complaints follow rainfall);
    * the RSK-to-village mapping is *simulated* and labelled as such.

Run from the project root::

    python -m src.ingestion.synthetic.generate
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Allow "python src/ingestion/synthetic/generate.py" as well as "-m" execution.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.config.settings import ensure_data_dirs, get_config, project_path

SEED: int = 42
DATA_TYPE: str = "Synthetic"

#: Simulated RSK (Raitha Samparka Kendra). A real RSK serves a hobli; the exact
#: village jurisdiction of any single RSK could not be officially verified, so this
#: mapping is a placeholder and is labelled "simulated" in the UI and the docs.
RSK = {
    "rsk_id": "RSK-SIM-01",
    "rsk_name": "RSK Hunsur (simulated jurisdiction)",
    "district": "Mysuru",
    "taluk": "Hunsur",
    "hobli": "Hunsur",
    "latitude": 12.3085,
    "longitude": 76.2927,
    "mapping_status": "simulated",
}

#: Six villages around the taluk headquarters. Names and coordinates are indicative
#: placeholders: LGD codes are NOT real and must be replaced from KGIS/LGD before any
#: external use. ``source_status`` records that fact per row.
VILLAGES: list[dict[str, object]] = [
    {
        "village_id": "V01",
        "village_name": "Keralapura",
        "lgd_code": "SIM-LGD-0001",
        "latitude": 12.3521,
        "longitude": 76.2610,
        "cultivated_area_ha": 412.0,
        "road_distance_km": 9.5,
        "rain_factor": 1.00,
        "kharif_factor": 0.45,  # 2026 drought-stress village
        "profile": "drought",
    },
    {
        "village_id": "V02",
        "village_name": "Hanagodu",
        "lgd_code": "SIM-LGD-0002",
        "latitude": 12.2731,
        "longitude": 76.3205,
        "cultivated_area_ha": 530.0,
        "road_distance_km": 14.0,
        "rain_factor": 1.08,
        "kharif_factor": 1.35,  # 2026 excess-rain / flood village
        "profile": "flood",
    },
    {
        "village_id": "V03",
        "village_name": "Bilikere",
        "lgd_code": "SIM-LGD-0003",
        "latitude": 12.3398,
        "longitude": 76.3452,
        "cultivated_area_ha": 468.0,
        "road_distance_km": 7.0,
        "rain_factor": 0.97,
        "kharif_factor": 0.94,
        "profile": "pest",
    },
    {
        "village_id": "V04",
        "village_name": "Doddabyranakuppe",
        "lgd_code": "SIM-LGD-0004",
        "latitude": 12.2890,
        "longitude": 76.2408,
        "cultivated_area_ha": 356.0,
        "road_distance_km": 22.5,
        "rain_factor": 0.93,
        "kharif_factor": 0.88,
        "profile": "irrigation",
    },
    {
        "village_id": "V05",
        "village_name": "Gavadagere",
        "lgd_code": "SIM-LGD-0005",
        "latitude": 12.3140,
        "longitude": 76.2075,
        "cultivated_area_ha": 298.0,
        "road_distance_km": 31.0,
        "rain_factor": 0.89,
        "kharif_factor": 0.97,
        "profile": "low_reliability",
    },
    {
        "village_id": "V06",
        "village_name": "Uyyamballi",
        "lgd_code": "SIM-LGD-0006",
        "latitude": 12.3655,
        "longitude": 76.3021,
        "cultivated_area_ha": 388.0,
        "road_distance_km": 17.5,
        "rain_factor": 1.03,
        "kharif_factor": 1.02,
        "profile": "normal",
    },
]

CROPS: list[dict[str, object]] = [
    {"crop_id": "C01", "crop_name": "Ragi", "water_requirement": "low"},
    {"crop_id": "C02", "crop_name": "Paddy", "water_requirement": "high"},
    {"crop_id": "C03", "crop_name": "Maize", "water_requirement": "medium"},
    {"crop_id": "C04", "crop_name": "Sugarcane", "water_requirement": "high"},
    {"crop_id": "C05", "crop_name": "Groundnut", "water_requirement": "low"},
    {"crop_id": "C06", "crop_name": "Cotton", "water_requirement": "medium"},
]

#: Which crops each village grows (village_id -> list of crop_ids).
VILLAGE_CROPS: dict[str, list[str]] = {
    "V01": ["C01", "C03", "C05"],
    "V02": ["C02", "C04", "C03"],
    "V03": ["C02", "C06"],
    "V04": ["C01", "C03", "C05"],
    "V05": ["C01", "C05"],
    "V06": ["C02", "C03", "C01"],
}

#: Long-term monthly rainfall climatology (mm) for the taluk: bimodal monsoon.
BASE_MONTHLY_MM: tuple[float, ...] = (2.0, 3.0, 8.0, 45.0, 110.0, 140.0, 180.0, 150.0, 190.0, 155.0, 55.0, 15.0)

#: Baseline NDVI seasonality by month (index 0 = January).
BASE_NDVI: tuple[float, ...] = (0.45, 0.40, 0.35, 0.33, 0.36, 0.42, 0.55, 0.65, 0.68, 0.62, 0.52, 0.47)

#: One AO, two AAOs and three AAs (synthetic roster, no personal data).
#: ``current_load`` = villages already queued for that person this week.
STAFF: list[dict[str, object]] = [
    {"staff_id": "S01", "name": "Officer A (AO)", "role": "AO", "max_villages_per_day": 0, "available_days_per_week": 5, "current_load": 0.0},
    {"staff_id": "S02", "name": "Officer B (AAO)", "role": "AAO", "max_villages_per_day": 2, "available_days_per_week": 5, "current_load": 2.0},
    {"staff_id": "S03", "name": "Officer C (AAO)", "role": "AAO", "max_villages_per_day": 2, "available_days_per_week": 4, "current_load": 4.0},
    {"staff_id": "S04", "name": "Officer D (AA)", "role": "AA", "max_villages_per_day": 1, "available_days_per_week": 5, "current_load": 1.0},
    {"staff_id": "S05", "name": "Officer E (AA)", "role": "AA", "max_villages_per_day": 1, "available_days_per_week": 4, "current_load": 3.0},
    {"staff_id": "S06", "name": "Officer F (AA)", "role": "AA", "max_villages_per_day": 1, "available_days_per_week": 3, "current_load": 0.0},
]

#: Complaint template per village profile: (category, crop_id, urgency, affected_ha, days_ago, text)
COMPLAINT_TEMPLATES: dict[str, list[tuple[str, str | None, str, float | None, int, str]]] = {
    "drought": [
        ("drought_stress", "C01", "high", 18.0, 3, "Ragi crop wilting, soil dry since the last spell; farmers report poor tillering."),
        ("drought_stress", "C03", "high", 12.5, 9, "Maize leaves curling in the afternoon, no borewell water left."),
        ("drought_stress", "C05", "medium", 6.0, 16, "Groundnut sown late, germination patchy because of dry spell."),
        ("nutrient_deficiency", "C01", "medium", 4.0, 21, "Yellowing of lower leaves in ragi; farmer suspects nitrogen deficiency."),
    ],
    "flood": [
        ("flood_damage", "C02", "high", 22.0, 2, "Standing water in paddy fields for three days after heavy rain; seedlings submerged."),
        ("flood_damage", "C04", "high", 9.0, 6, "Sugarcane field waterlogged, root rot starting in the low-lying patch."),
        ("disease_outbreak", "C02", "medium", 14.0, 12, "Blast-like lesions on paddy leaves after continuous wet weather."),
    ],
    "pest": [
        ("pest_attack", "C02", "high", 16.0, 1, "Brown planthopper hoppers seen in large numbers at the base of paddy plants."),
        ("pest_attack", "C02", "high", 11.0, 4, "Paddy crop showing hopper burn patches; two farmers affected in the same block."),
        ("pest_attack", "C06", "medium", 7.5, 8, "Cotton pink bollworm larvae found in green bolls."),
        ("pest_attack", "C02", "medium", 5.0, 15, "Stem borer damage, dead hearts visible in about a tenth of the field."),
    ],
    "irrigation": [
        ("irrigation_issue", "C03", "medium", 10.0, 7, "Canal release delayed; maize needs one protective irrigation."),
        ("irrigation_issue", "C01", "low", 3.5, 18, "Community tank level low, only one irrigation possible this month."),
    ],
    "low_reliability": [
        ("nutrient_deficiency", "C01", "low", 2.5, 11, "Farmer reports pale ragi crop; no affected-area measurement given."),
    ],
    "normal": [
        ("pest_attack", "C02", "medium", 6.0, 5, "Leaf folder damage observed along the field bund."),
        ("nutrient_deficiency", "C01", "low", None, 20, "Ragi growth uneven; farmer did not specify the area affected."),
    ],
}

#: Baseline village totals and Kharif month indices used for season aggregation.
KHARIF_MONTHS: tuple[int, ...] = (6, 7, 8, 9, 10)


def _months(start: str, end: str) -> list[tuple[int, int]]:
    """Return ``[(year, month), ...]`` inclusive between two ``YYYY-MM`` strings."""
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    out: list[tuple[int, int]] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        out.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def generate_villages() -> pd.DataFrame:
    """Build the village table (simulated geography, flagged)."""
    rows = []
    for v in VILLAGES:
        rows.append(
            {
                "village_id": v["village_id"],
                "village_name": v["village_name"],
                "lgd_code": v["lgd_code"],
                "rsk_id": RSK["rsk_id"],
                "district": RSK["district"],
                "taluk": RSK["taluk"],
                "hobli": RSK["hobli"],
                "latitude": v["latitude"],
                "longitude": v["longitude"],
                "cultivated_area_ha": v["cultivated_area_ha"],
                "road_distance_km": v["road_distance_km"],
                "source_status": "simulated",
                "is_synthetic": True,
                "data_type": DATA_TYPE,
            }
        )
    return pd.DataFrame(rows)


def generate_rsk() -> pd.DataFrame:
    """Build the RSK table."""
    return pd.DataFrame(
        [
            {
                "rsk_id": RSK["rsk_id"],
                "rsk_name": RSK["rsk_name"],
                "district": RSK["district"],
                "taluk": RSK["taluk"],
                "hobli": RSK["hobli"],
                "latitude": RSK["latitude"],
                "longitude": RSK["longitude"],
                "mapping_status": "simulated",
                "is_synthetic": True,
                "data_type": DATA_TYPE,
            }
        ]
    )


def generate_crops() -> pd.DataFrame:
    """Build the crop master table."""
    return pd.DataFrame(
        [{**crop, "is_synthetic": True, "data_type": DATA_TYPE} for crop in CROPS]
    )


def generate_village_crops() -> pd.DataFrame:
    """Build the village x crop area table (areas sum to ~85% of cultivated area)."""
    rng = np.random.default_rng(SEED + 1)
    rows = []
    for village in VILLAGES:
        crop_ids = VILLAGE_CROPS[str(village["village_id"])]
        weights = rng.dirichlet(np.ones(len(crop_ids)) * 3)
        areas = weights * float(village["cultivated_area_ha"]) * 0.85
        for crop_id, area in zip(crop_ids, areas):
            rows.append(
                {
                    "village_id": village["village_id"],
                    "crop_id": crop_id,
                    "area_ha": round(float(area), 2),
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
    return pd.DataFrame(rows)


def generate_rainfall() -> pd.DataFrame:
    """Monthly rainfall per village, 2019-01 .. 2026-10.

    The 2026 Kharif season is deliberately shifted per village (``kharif_factor``) so
    that one village is drought-stressed and one has excess rain while the rest are
    near normal - a realistic demo without claiming real measurements.
    """
    rng = np.random.default_rng(SEED + 2)
    rows = []
    for village in VILLAGES:
        rain_factor = float(village["rain_factor"])
        kharif_factor = float(village["kharif_factor"])
        for year, month in _months("2019-01", "2026-10"):
            base = BASE_MONTHLY_MM[month - 1] * rain_factor * 0.8  # ~840 mm/yr at factor 1.0
            noise = float(rng.lognormal(mean=0.0, sigma=0.22))
            value = base * noise
            if year == 2026 and month in KHARIF_MONTHS:
                value *= kharif_factor
            rows.append(
                {
                    "village_id": village["village_id"],
                    "year": year,
                    "month": month,
                    "rainfall_mm": round(value, 1),
                    "source": "synthetic_generator",
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
    return pd.DataFrame(rows)


def generate_ndvi(rainfall: pd.DataFrame) -> pd.DataFrame:
    """Monthly village NDVI, 2023-01 .. 2026-10, driven by the rainfall history.

    ``Gavadagere`` (the low-reliability village) deliberately loses half its valid
    observations to high cloud cover, which the reliability score must detect.
    """
    rng = np.random.default_rng(SEED + 3)
    rain_by_key = {
        (row.village_id, int(row.year), int(row.month)): float(row.rainfall_mm)
        for row in rainfall.itertuples()
    }
    rows = []
    for village in VILLAGES:
        vid = str(village["village_id"])
        for year, month in _months("2023-01", "2026-10"):
            rain = rain_by_key.get((vid, year, month), BASE_MONTHLY_MM[month - 1])
            base_rain = BASE_MONTHLY_MM[month - 1] * float(village["rain_factor"]) * 0.8
            wetness = 0.0 if base_rain <= 1 else (rain / base_rain - 1.0)
            ndvi = BASE_NDVI[month - 1] + 0.16 * float(np.clip(wetness, -1.5, 1.5))
            ndvi += float(rng.normal(0.0, 0.012))
            cloud = 35.0 if month in KHARIF_MONTHS else 12.0
            cloud = float(np.clip(cloud + rng.normal(0, 8), 0, 95))
            valid = float(np.clip(100.0 - cloud + rng.normal(0, 5), 10, 100))
            if village["profile"] == "low_reliability":
                valid = float(np.clip(valid - 45.0, 0, 100))
                if valid < 25.0:
                    # Too cloudy to retrieve a reliable composite: record it as missing.
                    ndvi_value: float | None = None
                else:
                    ndvi_value = round(float(np.clip(ndvi, 0.05, 0.92)), 3)
            else:
                ndvi_value = round(float(np.clip(ndvi, 0.05, 0.92)), 3)
            rows.append(
                {
                    "village_id": vid,
                    "year": year,
                    "month": month,
                    "ndvi_mean": ndvi_value,
                    "cloud_cover_pct": round(cloud, 1),
                    "valid_pixel_pct": round(valid, 1),
                    "sensor": "Sentinel-2 (simulated retrieval)",
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
    return pd.DataFrame(rows)


def generate_weather() -> pd.DataFrame:
    """Weekly weather per village for the 16 weeks ending on the reference date."""
    rng = np.random.default_rng(SEED + 4)
    cfg = get_config()
    end = cfg.reference_date
    start = end - timedelta(weeks=15, days=-6)  # Monday of the first week
    start = start - timedelta(days=start.weekday())
    rows = []
    for village in VILLAGES:
        profile = str(village["profile"])
        for week in range(16):
            week_start = start + timedelta(weeks=week)
            temp_max = 29.5 + 2.0 * np.sin(week / 5.0) + rng.normal(0, 1.2)
            rain = max(0.0, float(rng.gamma(2.0, 12.0)))
            if profile == "drought":
                temp_max += 4.5
                rain *= 0.2
            elif profile == "flood":
                rain *= 2.4
                temp_max -= 1.5
            rows.append(
                {
                    "village_id": village["village_id"],
                    "week_start": week_start.isoformat(),
                    "temp_max_c": round(float(temp_max), 1),
                    "temp_min_c": round(float(temp_max - rng.uniform(8, 12)), 1),
                    "humidity_pct": round(float(np.clip(rng.normal(70, 9), 30, 98)), 1),
                    "rainfall_mm": round(float(rain), 1),
                    "source": "synthetic_generator",
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
    return pd.DataFrame(rows)


def generate_staff() -> pd.DataFrame:
    """Build the (synthetic) staff table. Phone numbers are deliberately omitted."""
    return pd.DataFrame(
        [
            {**member, "is_synthetic": True, "data_type": DATA_TYPE}
            for member in STAFF
        ]
    )


def generate_complaints() -> pd.DataFrame:
    """Farmer complaints registered in the last ~45 days, one set per village profile."""
    cfg = get_config()
    rows = []
    counter = 1
    for village in VILLAGES:
        profile = str(village["profile"])
        for category, crop_id, urgency, area, days_ago, text in COMPLAINT_TEMPLATES[profile]:
            reported = cfg.reference_date - timedelta(days=days_ago)
            rows.append(
                {
                    "complaint_id": f"CMP{counter:04d}",
                    "village_id": village["village_id"],
                    "crop_id": crop_id,
                    "category": category,
                    "affected_area_ha": area,
                    "urgency": urgency,
                    "reported_date": reported.isoformat(),
                    "description": text,
                    "reporter_role": "AA",
                    "status": "registered",
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def generate_inspections() -> pd.DataFrame:
    """Past inspections, deliberately uneven so "inspection recency" varies."""
    cfg = get_config()
    plan = {
        "V01": [220, 300],   # drought village: long neglected
        "V02": [25, 95, 180],
        "V03": [30, 150],    # pest village: visited recently
        "V04": [75, 210],
        "V05": [140],
        "V06": [60, 190],
    }
    rows = []
    counter = 1
    for village_id, days_list in plan.items():
        for idx, days in enumerate(days_list):
            inspection_date = cfg.reference_date - timedelta(days=days)
            rows.append(
                {
                    "inspection_id": f"INS{counter:04d}",
                    "village_id": village_id,
                    "staff_id": STAFF[(counter + 1) % len(STAFF)]["staff_id"],
                    "inspection_date": inspection_date.isoformat(),
                    "purpose": "routine" if idx % 2 == 0 else "complaint_followup",
                    "findings": "Routine crop condition check completed.",
                    "outcome": "no_action" if idx % 2 == 0 else "advisory_issued",
                    "is_synthetic": True,
                    "data_type": DATA_TYPE,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def generate_assignments(complaints: pd.DataFrame) -> pd.DataFrame:
    """Current assignments: a couple of completed, one in progress, rest pending."""
    cfg = get_config()
    rows = [
        {
            "assignment_id": "ASG0001",
            "village_id": "V03",
            "staff_id": "S04",
            "assigned_date": (cfg.reference_date - timedelta(days=20)).isoformat(),
            "due_date": (cfg.reference_date - timedelta(days=13)).isoformat(),
            "status": "completed",
            "priority_rank": 2,
            "notes": "Pest outbreak verified; advisory issued.",
        },
        {
            "assignment_id": "ASG0002",
            "village_id": "V02",
            "staff_id": "S05",
            "assigned_date": (cfg.reference_date - timedelta(days=8)).isoformat(),
            "due_date": (cfg.reference_date + timedelta(days=1)).isoformat(),
            "status": "in_progress",
            "priority_rank": 1,
            "notes": "Waterlogging assessment in progress.",
        },
        {
            "assignment_id": "ASG0003",
            "village_id": "V04",
            "staff_id": "S06",
            "assigned_date": (cfg.reference_date - timedelta(days=2)).isoformat(),
            "due_date": (cfg.reference_date + timedelta(days=5)).isoformat(),
            "status": "pending",
            "priority_rank": 4,
            "notes": "Canal release verification.",
        },
    ]
    frame = pd.DataFrame(rows)
    frame["is_synthetic"] = True
    frame["data_type"] = DATA_TYPE
    return frame


def write_tables(tables: dict[str, pd.DataFrame]) -> dict[str, Path]:
    """Write each table to ``data/synthetic/<name>.csv`` and return the paths."""
    out_dir = project_path("data", "synthetic")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, frame in tables.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        written[name] = path
    return written


def main() -> None:
    """Generate every synthetic table and report row counts."""
    ensure_data_dirs()
    rainfall = generate_rainfall()
    tables = {
        "rsk": generate_rsk(),
        "villages": generate_villages(),
        "crops": generate_crops(),
        "village_crops": generate_village_crops(),
        "rainfall_monthly": rainfall,
        "ndvi_monthly": generate_ndvi(rainfall),
        "weather_weekly": generate_weather(),
        "staff": generate_staff(),
        "complaints": generate_complaints(),
        "inspections": generate_inspections(),
    }
    tables["assignments"] = generate_assignments(tables["complaints"])
    paths = write_tables(tables)
    print("Synthetic dataset written (seed=%d, all rows flagged is_synthetic):" % SEED)
    for name, path in paths.items():
        print(f"  {name:18s} {len(tables[name]):5d} rows  -> {path.relative_to(project_path())}")


if __name__ == "__main__":
    main()
