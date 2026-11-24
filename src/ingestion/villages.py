"""Village boundary + code ingestion from KGIS and the Local Government Directory.

Verified source pages (checked 2026-11):

* KGIS downloads (KSRSAC, Government of Karnataka): https://kgis.ksrsac.in/kgis/downloads.aspx
  Administrative boundaries (state / district / taluk / hobli / village) are listed there as
  PDF, KML or shapefile. The page states the data is Government of Karnataka property and
  that misuse is subject to legal proceedings, so check the terms before redistributing it.
* Local Government Directory: https://lgdirectory.gov.in - official village (LGD) codes. The
  taluk's village list must be exported from LGD; this module never invents a code.

``geopandas`` is optional and not installed by default.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config.settings import project_path


def load_village_boundaries(path: Path) -> "object":
    """Read a KGIS village boundary layer with geopandas.

    Raises:
        RuntimeError: When geopandas is missing or the layer cannot be read.
    """
    try:
        import geopandas as gpd
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "geopandas is not installed. Run `pip install geopandas` to read KGIS shapefiles."
        ) from exc
    return gpd.read_file(path)


def match_villages(boundaries: "object", villages: pd.DataFrame) -> pd.DataFrame:
    """Spatially join village points to boundary polygons.

    Returns:
        Copy of ``villages`` with ``boundary_name``, ``boundary_code`` and ``match`` columns.
    """
    import geopandas as gpd

    points = gpd.GeoDataFrame(
        villages.copy(),
        geometry=gpd.points_from_xy(villages["longitude"], villages["latitude"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, boundaries, how="left", predicate="within")
    name_column = next(
        (c for c in ("KGISVILNAME", "Village_Name", "VILLAGE", "NAME") if c in boundaries.columns), None
    )
    code_column = next(
        (c for c in ("KGISVILLAGECODE", "Village_Code", "LGDCODE", "CODE") if c in boundaries.columns), None
    )
    result = pd.DataFrame(joined.drop(columns="geometry"))
    result["boundary_name"] = result[name_column] if name_column else None
    result["boundary_code"] = result[code_column] if code_column else None
    result["match"] = result["boundary_name"].notna()
    return result


def main() -> None:
    """CLI: match the configured village points against a KGIS boundary file."""
    parser = argparse.ArgumentParser(description="Match villages to KGIS boundaries")
    parser.add_argument("shapefile", type=Path, help="path to the KGIS village boundary layer")
    args = parser.parse_args()
    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    boundaries = load_village_boundaries(args.shapefile)
    matched = match_villages(boundaries, villages)
    out = project_path("data", "raw", "kgis", "village_matches.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    matched.to_csv(out, index=False)
    print(
        matched[["village_id", "village_name", "boundary_name", "boundary_code", "match"]].to_string(
            index=False
        )
    )
    print(
        "\nWith official names and LGD codes in hand, update villages.lgd_code and set "
        "source_status='verified' - the UI banner can then drop the 'simulated' label."
    )


if __name__ == "__main__":
    main()
