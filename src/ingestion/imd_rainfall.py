"""IMD gridded daily rainfall ingestion (real data path - not yet exercised).

Source: India Meteorological Department, Pune - "New High Spatial Resolution (0.25 x 0.25
degree) Long Period (1901-2024) Daily Gridded Rainfall Data Set Over India".

* binary files: https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html
* NetCDF files: https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html

The files are downloaded manually (IMD publishes no stable direct-link pattern), so this
module takes a local path. Documented binary layout:

* 135 rows (latitude) x 129 columns (longitude), float32, little-endian;
* first point 6.5 N / 66.5 E, then eastwards in 0.25 degree steps;
* 365/366 daily records per yearly file.

Nothing here is synthetic: output goes to ``data/raw/imd`` and is only merged into the
pipeline once you run it with a real file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import project_path

GRID_ROWS = 135
GRID_COLS = 129
LAT_ORIGIN = 6.5
LON_ORIGIN = 66.5
STEP = 0.25
MISSING = -999.0


def read_daily_grid(path: Path, year: int) -> np.ndarray:
    """Read one year of IMD daily gridded rainfall into ``(days, 135, 129)`` millimetres.

    Raises:
        ValueError: If the file size does not match the documented 0.25-degree layout.
    """
    days = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    expected = days * GRID_ROWS * GRID_COLS * 4
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(
            f"{path.name}: expected {expected} bytes for {days} days, found {actual}. "
            "Check that this is the 0.25-degree binary product, not the 1-degree one."
        )
    grid = np.fromfile(path, dtype="<f4").reshape(days, GRID_ROWS, GRID_COLS).astype("float32")
    grid[grid <= MISSING + 1] = np.nan
    return grid


def nearest_cell(latitude: float, longitude: float) -> tuple[int, int]:
    """Return the ``(row, column)`` index of the grid cell containing a coordinate."""
    row = int(round((latitude - LAT_ORIGIN) / STEP))
    column = int(round((longitude - LON_ORIGIN) / STEP))
    if not (0 <= row < GRID_ROWS and 0 <= column < GRID_COLS):
        raise ValueError(f"({latitude}, {longitude}) falls outside the IMD grid.")
    return row, column


def monthly_totals_for_villages(path: Path, year: int, villages: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily grid rainfall into monthly totals per village."""
    grid = read_daily_grid(path, year)
    dates = pd.date_range(f"{year}-01-01", periods=grid.shape[0], freq="D")
    rows = []
    for village in villages.itertuples():
        row, column = nearest_cell(float(village.latitude), float(village.longitude))
        series = pd.Series(grid[:, row, column], index=dates)
        for timestamp, value in series.resample("MS").sum(min_count=1).items():
            if pd.isna(value):
                continue
            rows.append(
                {
                    "village_id": village.village_id,
                    "year": int(timestamp.year),
                    "month": int(timestamp.month),
                    "rainfall_mm": round(float(value), 1),
                    "source": f"IMD 0.25deg grid (cell {row},{column})",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    """CLI: extract monthly rainfall for the configured villages from a local IMD file."""
    parser = argparse.ArgumentParser(description="Extract village rainfall from an IMD gridded file")
    parser.add_argument("path", type=Path, help="local path to ind<year>_rfp25.grd")
    parser.add_argument("--year", type=int, required=True, help="year of that file")
    args = parser.parse_args()

    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    frame = monthly_totals_for_villages(args.path, args.year, villages)
    out = project_path("data", "raw", "imd", f"imd_rainfall_{args.year}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    print(f"Wrote {len(frame)} village-months to {out.relative_to(project_path())}")
    print("Mark these rows data_type='Real' in the database once verified.")


if __name__ == "__main__":
    main()
