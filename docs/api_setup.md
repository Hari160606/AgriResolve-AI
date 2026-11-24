# Phase 3b — Google Cloud / Earth Engine setup (not done yet in this build)

Nothing in this file has been executed. It is the exact sequence to follow, with the free-vs-billing
picture stated plainly. **No key is stored in this repository.**

## 0. Project

1. https://console.cloud.google.com → **New Project** (or select an existing one).
2. Note the **project id** — it goes into `.env` as `GEE_PROJECT_ID`.
3. **Billing**: Google Maps Platform requires a billing account to be attached even inside the free
   monthly credit. Earth Engine requires a registered Cloud project (non-commercial/research use is
   free of charge, but registration is required). Check the current pricing pages before relying on
   any figure — quotas change.

## 1. Google Maps JavaScript API (village intelligence map)

Why: draw the RSK villages on a Google base map with markers coloured by priority in the AO dashboard.

1. **APIs & Services → Library** → enable **Maps JavaScript API**.
2. **APIs & Services → Credentials → Create credentials → API key**.
3. Restrict the key: **Application restrictions → HTTP referrers**, add `http://localhost:8501/*`
   and `http://127.0.0.1:8501/*` for development; **API restrictions → Maps JavaScript API** only.
4. Put it in `.env` as `GOOGLE_MAPS_API_KEY`.
5. The app uses it automatically; without a key it falls back to a Plotly/OpenStreetMap map, which is
   what the current screenshots show.

## 2. Google Routes API (travel time from the RSK to each village)

Why: replace the simulated `road_distance_km` with real driving distance/time for the accessibility
factor.

1. Enable **Routes API** in the library.
2. Create a second key or reuse the first; restrict it to **Routes API** and (for a local demo) to
   your IP: **Application restrictions → IP addresses** → your public IP.
3. Put it in `.env` as `GOOGLE_ROUTES_API_KEY`.
4. Run `python -m src.ingestion.routes` once — results are cached in
   `data/derived/route_cache.json` so later demos cost no quota.

## 3. Google Weather API (heat/dry-spell factor)

Why: replace synthetic weather with real daily forecasts for the current week.

1. Enable **Weather API**. Endpoints used (verified in the docs):
   - `GET https://weather.googleapis.com/v1/forecast/days:lookup?key=…&location.latitude=…&location.longitude=…`
   - `GET https://weather.googleapis.com/v1/currentConditions:lookup?key=…&location.latitude=…&location.longitude=…`
2. **Billing is required** for production use (FAQ states a valid billing account is needed). A
   no-billing *Maps Demo Key* exists for trials but is rate-limited and not for production.
3. Restrict the key to **Weather API** only.
4. Put it in `.env` as `GOOGLE_WEATHER_API_KEY`, then run `python -m src.ingestion.weather`.
5. Coverage: the API returns 404 for unsupported locations; check that the coordinates are in a
   covered country before demoing.

## 4. Google Earth Engine + Sentinel-2 NDVI

Why: the NDVI signal is the core of complaint-free monitoring.

1. Register the Cloud project for Earth Engine (Earth Engine console → register project). Research /
   educational use does not require payment, but the project must be registered and the user must
   have an EE-enabled account.
2. `pip install earthengine-api` (deliberately not installed by default).
3. **Either** authenticate interactively:
   ```bash
   earthengine authenticate
   ```
   **or** use a service account: create one in IAM, grant it the Earth Engine resource viewer/writer
   role, download the JSON key to `secrets/gee-key.json` (folder is git-ignored), then set in `.env`:
   ```
   GEE_PROJECT_ID=your-project-id
   GEE_SERVICE_ACCOUNT=your-sa@your-project.iam.gserviceaccount.com
   GEE_PRIVATE_KEY_PATH=./secrets/gee-key.json
   ```
4. Verify without printing tokens:
   ```bash
   python -m src.ingestion.gee_ndvi --check
   ```
5. Ingest: `python -m src.ingestion.gee_ndvi --year 2026` (June–October), then move the output into
   `data/raw/gee/` and re-run the pipeline after teaching `derive.py` to read real NDVI.

### Key hygiene checklist

- One key per API, API-restricted, and (where possible) referrer/IP-restricted.
- Never commit `.env`, `secrets/`, or a service-account JSON.
- Rotate any key that has been pasted into chat, a notebook, or a screenshot.

## Why Ollama, not Gemini

The master instructions default to a local model. Ollama (`llama3`) runs offline, needs no key, no
billing and no data leaving the laptop — the right trade-off for a college demo handling farmer
complaints. Gemini would only be justified if answer quality on real guideline PDFs proved
insufficient; that experiment has not been run, so no switch is proposed.
