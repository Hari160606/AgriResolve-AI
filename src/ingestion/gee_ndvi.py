"""Sentinel-2 NDVI ingestion through Google Earth Engine (real data path, not yet run).

Status: **not executed** - Earth Engine is not authenticated on this machine (no
``earthengine`` credentials, ``earthengine-api`` not installed). The code below is the real
implementation; ``python -m src.ingestion.gee_ndvi --check`` reports what is missing.

Setup (see ``docs/api_setup.md``): create/select a Google Cloud project, register it for
Earth Engine, ``pip install earthengine-api``, then ``earthengine authenticate`` (or set
``GEE_SERVICE_ACCOUNT`` + ``GEE_PRIVATE_KEY_PATH`` in ``.env``) and set ``GEE_PROJECT_ID``.

Collection: ``COPERNICUS/S2_SR_HARMONIZED`` (Sentinel-2 L2A surface reflectance, 10 m bands),
cloud-masked with the ``SCL`` classification band (3, 8, 9, 10, 11 = cloud/shadow/snow).
NDVI = (B8 - B4) / (B8 + B4).
"""

from __future__ import annotations

import argparse
from typing import Any

import pandas as pd

from src.config.settings import gee_settings, project_path

COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
CLOUDY_SCL_CLASSES = [3, 8, 9, 10, 11]
MAX_CLOUD_PCT = 60
SCALE_METRES = 10


def _initialise() -> tuple[Any, str]:
    """Initialise Earth Engine, returning the module and project id.

    Raises:
        RuntimeError: With an actionable message when the setup is incomplete.
    """
    try:
        import ee  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "earthengine-api is not installed. Run: pip install earthengine-api "
            "then `earthengine authenticate`."
        ) from exc

    settings = gee_settings()
    project = settings["project_id"] or None
    try:
        if settings["service_account"] and settings["private_key_path"]:
            credentials = ee.ServiceAccountCredentials(
                settings["service_account"], settings["private_key_path"]
            )
            ee.Initialize(credentials, project=project)
        else:
            ee.Initialize(project=project)
    except Exception as exc:  # noqa: BLE001 - the message is what matters here
        raise RuntimeError(
            f"Earth Engine is not authenticated ({type(exc).__name__}). Run "
            "`earthengine authenticate` or configure a service account in .env."
        ) from exc
    return ee, settings["project_id"]


def monthly_ndvi(ee: Any, geometry: Any, year: int, month: int) -> dict[str, float]:
    """Cloud-masked monthly NDVI statistics for one geometry."""
    start = f"{year}-{month:02d}-01"
    end = f"{year + (month == 12)}-{(month % 12) + 1:02d}-01"
    collection = (
        ee.ImageCollection(COLLECTION)
        .filterDate(start, end)
        .filterBounds(geometry)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
    )
    if collection.size().getInfo() == 0:
        return {"ndvi_mean": float("nan"), "valid_pixel_pct": 0.0, "scenes": 0}

    def mask_clouds(image: Any) -> Any:
        clear = image.select("SCL").remap(CLOUDY_SCL_CLASSES, [0] * len(CLOUDY_SCL_CLASSES), 1)
        return image.updateMask(clear)

    def add_ndvi(image: Any) -> Any:
        return image.addBands(image.normalizedDifference(["B8", "B4"]).rename("NDVI"))

    composite = collection.map(mask_clouds).map(add_ndvi).select("NDVI").median()
    stats = composite.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=geometry, scale=SCALE_METRES, maxPixels=1e9
    ).getInfo()
    valid = (
        composite.mask()
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=geometry, scale=SCALE_METRES, maxPixels=1e9)
        .getInfo()
    )
    return {
        "ndvi_mean": float(stats.get("NDVI") or float("nan")),
        "valid_pixel_pct": round(float(valid.get("NDVI") or 0.0) * 100, 1),
        "scenes": int(collection.size().getInfo()),
    }


def fetch_village_ndvi(villages: pd.DataFrame, months: list[tuple[int, int]]) -> pd.DataFrame:
    """Return NDVI statistics for every village and month requested."""
    ee, _ = _initialise()
    rows = []
    for village in villages.itertuples():
        # A ~1 km box keeps the retrieval cheap and comparable across villages.
        geometry = ee.Geometry.Point([float(village.longitude), float(village.latitude)]).buffer(500)
        for year, month in months:
            rows.append(
                {
                    "village_id": village.village_id,
                    "year": year,
                    "month": month,
                    **monthly_ndvi(ee, geometry, year, month),
                    "sensor": "Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED)",
                    "data_type": "Real",
                }
            )
    return pd.DataFrame(rows)


def check() -> None:
    """Report whether Earth Engine can be initialised (never prints credentials)."""
    settings = gee_settings()
    print("Earth Engine configuration:")
    print(f"  GEE_PROJECT_ID set: {bool(settings['project_id'])}")
    print(f"  service account set: {bool(settings['service_account'])}")
    print(f"  private key path set: {bool(settings['private_key_path'])}")
    try:
        ee, project = _initialise()
        print(f"  initialisation: OK (project={project})")
    except RuntimeError as exc:
        print(f"  initialisation: FAILED - {exc}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Sentinel-2 NDVI ingestion via Earth Engine")
    parser.add_argument("--check", action="store_true", help="only verify the setup")
    parser.add_argument("--year", type=int, help="year to ingest (June-October)")
    args = parser.parse_args()
    if args.check or args.year is None:
        check()
        return
    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    frame = fetch_village_ndvi(villages, [(args.year, month) for month in range(6, 11)])
    out = project_path("data", "raw", "gee", f"ndvi_{args.year}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    print(f"Wrote {len(frame)} village-months to {out.relative_to(project_path())}")


if __name__ == "__main__":
    main()
