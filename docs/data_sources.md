# Phase 3 — Data sources and provenance

Every row of this table states what was **actually verified**, not what is planned. "Not downloaded"
means the source exists and was documented, but no file from it is in this repository and no number
in the demo comes from it.

## Source inventory

| # | Data | Organisation | URL (verified) | Coverage / resolution | Licence / terms | Status in this build | data_type |
|---|---|---|---|---|---|---|---|
| 1 | Village boundaries | KSRSAC — Karnataka GIS (KGIS) | https://kgis.ksrsac.in/kgis/downloads.aspx | state → village polygons, KML/SHP/PDF | GoK data; page states misuse is subject to legal proceedings — check terms before redistribution | **not downloaded** | would be Real |
| 2 | Village codes (LGD) | Ministry of Panchayati Raj, GoI | https://lgdirectory.gov.in | village-level official codes | Government of India, public directory | **not downloaded**; prototype uses `SIM-LGD-000x` placeholders | would be Real |
| 3 | Daily gridded rainfall 0.25° | India Meteorological Department, Pune | https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html (binary) · https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html (NetCDF) | 1901–2024, 0.25° × 0.25°, 135 × 129 grid, daily | IMD Pune; free for research with acknowledgement | client written (`src/ingestion/imd_rainfall.py`), **not run** — no file downloaded | Synthetic (demo) |
| 4 | Real-time merged rainfall (GPM + gauge) | IMD / NCMRWF | https://imdpune.gov.in/cmpg/Realtimedata/gpm/Rain_Download.html | 0.25°, near-real-time | IMD/NCMRWF; acknowledges NASA/JAXA GPM | not used | — |
| 5 | Sentinel-2 L2A surface reflectance | ESA Copernicus, accessed via Google Earth Engine | collection id `COPERNICUS/S2_SR_HARMONIZED` (Earth Engine catalog) | 10 m bands, 5-day revisit | Copernicus open data; EE terms of service | code written (`src/ingestion/gee_ndvi.py`), **not authenticated** → NDVI in the demo is synthetic | Synthetic (demo) |
| 6 | Weather (forecast / current) | Google Maps Platform — Weather API | https://developers.google.com/maps/documentation/weather/overview · endpoints `weather.googleapis.com/v1/forecast/days:lookup`, `/v1/currentConditions:lookup` | hyperlocal, up to 10-day daily / 240 h hourly forecast | Google Maps Platform terms; billing required | client written (`src/ingestion/weather.py`), **no key** | Synthetic (demo) |
| 7 | Travel distance/time | Google Maps Platform — Routes API | https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes | route distance + duration | Google Maps Platform terms; billing required | client written with file cache (`src/ingestion/routes.py`), **no key** → uses simulated `road_distance_km` | Simulated |
| 8 | Base map | Google Maps JavaScript API | https://developers.google.com/maps/documentation/javascript | raster/vector tiles | Google Maps Platform terms; billing required | embedded only when `GOOGLE_MAPS_API_KEY` is set; otherwise Plotly/OpenStreetMap fallback | n/a |
| 9 | Crop area statistics | data.gov.in (Government of India open data) | https://api.data.gov.in/resource/{resource-id} — resource id must be copied from the catalogue page you choose | tehsil/district level depending on the resource | Government Open Data Licence — India | generic client (`src/ingestion/crop_stats.py`); **no resource id chosen, no key** | Synthetic (demo) |
| 10 | Guideline documents (RAG) | UAS Bengaluru, ICAR, Dept. of Agriculture Karnataka, PPQS | not bundled — sources listed in `src/ingestion/download_guidelines.py`; record the exact URL you use | crop-wise package of practices | varies per publisher; several are not redistributable | one **internal demo note** committed (`guidelines_pdfs/demo_field_notes.md`), labelled as not official | Demo corpus |
| 11 | Farmer complaints, inspections, staff, assignments | — | — | — | — | **fully synthetic** | Synthetic |

## Resolution honesty

- Rainfall: IMD's finest open product is a **0.25° grid** ≈ 27 km. A village therefore uses the value
  of its containing cell; this is a grid value, not a village rain-gauge measurement.
- NDVI: Sentinel-2 at 10 m is genuinely village-scale, but with per-month cloud cover of 20–60 % in
  the monsoon. The pipeline records `cloud_cover_pct` and `valid_pixel_pct` per observation and uses
  completeness/recency to down-weight unreliable villages instead of hiding the gaps.
- Crop statistics and complaint data are not available at village level in this build; nothing here
  claims otherwise.

## Licence and citation notes

- IMD gridded data must be acknowledged as IMD Pune's product if used in a report.
- KGIS data is Government of Karnataka property; do not publish derived boundary files without checking terms.
- data.gov.in resources carry the Government Open Data Licence — India; cite the resource page.
- Guideline PDFs: record title, publisher, URL, licence and download date in
  `data/derived/guideline_documents.csv` before committing anything.

## Reproduce which sources are reachable from your network

```bash
python -m src.ingestion.download_public_data --check
```
