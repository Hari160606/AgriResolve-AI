"""Guided downloads for the real data sources, with reachability checks.

No credentials and no scraping: this script prints the verified source pages, the exact file
to look for, and the licence notes, then optionally checks that the page is reachable so the
student can see which sources are available from their network.

Run::

    python -m src.ingestion.download_public_data
    python -m src.ingestion.download_public_data --check
"""

from __future__ import annotations

import argparse
import sys

import requests

TIMEOUT = 20

SOURCES: list[dict[str, str]] = [
    {
        "name": "IMD 0.25° daily gridded rainfall (binary)",
        "url": "https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html",
        "product": "ind<year>_rfp25.grd",
        "target": "data/raw/imd/",
        "nginx": "IMD Pune; free for research with acknowledgement; check the page's terms.",
    },
    {
        "name": "IMD 0.25° daily gridded rainfall (NetCDF)",
        "url": "https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html",
        "product": "ind<year>_rfp25.nc",
        "target": "data/raw/imd/",
        "nginx": "IMD Pune; NetCDF needs netCDF4/xarray (not in the fixed stack), so the binary path is used.",
    },
    {
        "name": "IMD real-time merged satellite-gauge rainfall",
        "url": "https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html",
        "product": "daily merged GPM binary",
        "target": "data/raw/imd/realtime/",
        "nginx": "Near-real-time product; use it only for the current season, not history.",
    },
    {
        "name": "KGIS administrative boundaries (KSRSAC)",
        "url": "https://kgis.ksrsac.in/kgis/downloads.aspx",
        "product": "village-level boundary shapefile / KML",
        "target": "data/raw/kgis/",
        "nginx": "Government of Karnataka; the page states misuse is subject to legal proceedings.",
    },
    {
        "name": "Local Government Directory (village codes)",
        "url": "https://lgdirectory.gov.in",
        "product": "village list export for the selected taluk",
        "target": "data/raw/lgd/",
        "nginx": "Government of India; codes are the authoritative village identifiers.",
    },
]


def check(url: str) -> str:
    """Return a short reachability status for a URL (never raises)."""
    try:
        response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        return f"HTTP {response.status_code}"
    except requests.RequestException as exc:  # network may be blocked on campus
        return f"unreachable ({type(exc).__name__})"


def main() -> None:
    """Print the source manifest, optionally checking reachability."""
    parser = argparse.ArgumentParser(description="List and check real data sources")
    parser.add_argument("--check", action="store_true", help="probe each URL")
    args = parser.parse_args()

    for source in SOURCES:
        status = f"  [{check(source['url'])}]" if args.check else ""
        print(f"\n{source['name']}{status}")
        print(f"  page:    {source['url']}")
        print(f"  file:    {source['product']}")
        print(f"  save to: {source['target']}")
        print(f"  licence: {source['nginx']}")

    print(
        "\nThese downloads are manual by design: IMD and KGIS do not publish stable "
        "direct-download URLs, so nothing is guessed here. Record the date you downloaded "
        "each file in docs/data_sources.md and keep the original files unmodified in data/raw/."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
