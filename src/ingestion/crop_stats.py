"""Crop statistics ingestion from data.gov.in (real data path, needs an API key).

data.gov.in exposes catalogued resources as JSON::

    GET https://api.data.gov.in/resource/<resource-id>?api-key=<key>&format=json&limit=100

The resource id for a specific Karnataka crop-area dataset must be copied from the catalogue
page you chose - this module deliberately does not guess ids. Record the resource id, title,
publisher and licence in ``docs/data_sources.md`` when you use it.
"""

from __future__ import annotations

import argparse

import pandas as pd
import requests

from src.config.settings import project_path

BASE_URL = "https://api.data.gov.in/resource"
TIMEOUT = 30


def fetch_resource(resource_id: str, api_key: str, limit: int = 1000, offset: int = 0) -> dict:
    """Fetch one page of a data.gov.in resource."""
    response = requests.get(
        f"{BASE_URL}/{resource_id}",
        params={"api-key": api_key, "format": "json", "limit": limit, "offset": offset},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"data.gov.in returned HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def fetch_all(resource_id: str, api_key: str, page_size: int = 1000, max_pages: int = 10) -> pd.DataFrame:
    """Page through a resource and return all records as one DataFrame."""
    records: list[dict] = []
    for page in range(max_pages):
        payload = fetch_resource(resource_id, api_key, limit=page_size, offset=page * page_size)
        batch = payload.get("records", [])
        records.extend(batch)
        if len(batch) < page_size:
            break
    return pd.DataFrame(records)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Fetch a data.gov.in crop statistics resource")
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--api-key", default=None, help="data.gov.in API key (never committed)")
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit(
            "A data.gov.in API key is required: register at https://www.data.gov.in/ and pass "
            "the key on the command line (do not store it in the repository)."
        )
    frame = fetch_all(args.resource_id, args.api_key)
    out = project_path("data", "raw", "crop_stats", f"{args.resource_id}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    print(f"Wrote {len(frame)} rows to {out.relative_to(project_path())} (data_type='Real')")


if __name__ == "__main__":
    main()
