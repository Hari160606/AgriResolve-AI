"""Google Weather API ingestion (real data path, requires an API key).

Verified endpoints (Google Maps Platform docs, checked 2026-11):

* current conditions: ``GET https://weather.googleapis.com/v1/currentConditions:lookup``
* daily forecast (10 days): ``GET https://weather.googleapis.com/v1/forecast/days:lookup``
* hourly forecast (240 h): ``GET https://weather.googleapis.com/v1/forecast/hours:lookup``

Query parameters: ``key``, ``location.latitude``, ``location.longitude`` (+ optional
``days``/``pageSize``). Production use needs a billing-enabled project; see
``docs/api_setup.md`` for console steps, quota notes and key restrictions.
"""

from __future__ import annotations

import argparse
from typing import Any

import pandas as pd
import requests

from src.config.settings import google_key, project_path

BASE_URL = "https://weather.googleapis.com/v1"
DAILY_FORECAST = f"{BASE_URL}/forecast/days:lookup"
CURRENT_CONDITIONS = f"{BASE_URL}/currentConditions:lookup"
TIMEOUT = 20


def fetch_daily_forecast(latitude: float, longitude: float, days: int = 10) -> list[dict[str, Any]]:
    """Return the raw daily forecast entries for one coordinate.

    Raises:
        RuntimeError: When the key is missing or the API rejects the call. The message
            includes the HTTP status but never the key.
    """
    key = google_key("GOOGLE_WEATHER_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_WEATHER_API_KEY is not set. Add it to .env - see docs/api_setup.md. "
            "The Google Weather API requires a billing-enabled project."
        )
    response = requests.get(
        DAILY_FORECAST,
        params={
            "key": key,
            "location.latitude": latitude,
            "location.longitude": longitude,
            "days": max(1, min(days, 10)),
            "pageSize": max(1, min(days, 10)),
        },
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Weather API returned HTTP {response.status_code}: {response.text[:300]}")
    return response.json().get("forecastDays", [])


def forecast_to_daily(days: list[dict[str, Any]]) -> pd.DataFrame:
    """Flatten the API response into a small daily table used by the pipeline."""
    rows = []
    for day in days:
        daytime = day.get("daytimeForecast") or {}
        rows.append(
            {
                "date": (day.get("interval") or {}).get("startTime", "")[:10],
                "temp_max_c": (day.get("maxTemperature") or {}).get("degrees"),
                "temp_min_c": (day.get("minTemperature") or {}).get("degrees"),
                "humidity_pct": (day.get("relativeHumidity") or {}).get("percent"),
                "rain_mm": ((daytime.get("precipitation") or {}).get("qpf") or {}).get("quantity"),
                "condition": ((daytime.get("weatherCondition") or {}).get("description") or {}).get("text"),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """CLI: fetch a forecast for every configured village (requires a key)."""
    parser = argparse.ArgumentParser(description="Google Weather API fetch")
    parser.add_argument("--days", type=int, default=10)
    args = parser.parse_args()
    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    frames = []
    for village in villages.itertuples():
        try:
            days = fetch_daily_forecast(float(village.latitude), float(village.longitude), args.days)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        frame = forecast_to_daily(days)
        frame["village_id"] = village.village_id
        frames.append(frame)
    out = project_path("data", "raw", "google_weather", "forecast.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(out, index=False)
    print(f"Wrote forecast to {out.relative_to(project_path())} (data_type='Real')")


if __name__ == "__main__":
    main()
