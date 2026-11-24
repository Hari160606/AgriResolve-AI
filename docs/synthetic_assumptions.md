# Phase 4 — Synthetic data assumptions

All synthetic tables live in `data/synthetic/` and every row carries `is_synthetic = TRUE` and
`data_type = 'Synthetic'`. The generator is `src/ingestion/synthetic/generate.py`, seeded with
`SEED = 42`, so re-running it reproduces byte-identical CSVs.

## Why synthetic data exists here

The real-data path is documented but blocked: no IMD file, no Earth Engine authentication, no Google
API keys, and the KGIS/LGD mapping is unverified. Rather than fabricate "real" numbers, the project
generates clearly-labelled data with the same schema as the real sources, so the pipeline, engine and
UI can be built and demonstrated — and swapping in real data later is a loader change, not a rewrite.

## Global assumptions

| Assumption | Value |
|---|---|
| RSK | one simulated RSK (`RSK-SIM-01`), Hunsur taluk, Mysuru district |
| Villages | 6, simulated ids `V01…V06`, placeholder LGD codes `SIM-LGD-000x` |
| Reference date | 2026-11-24 (all "days ago" windows are relative to it) |
| Season modelled | Kharif 2026 (June–October) |
| Rainfall history | January 2019 – October 2026, monthly |
| NDVI history | January 2023 – October 2026, monthly |
| Weather | weekly, the 16 weeks ending on the reference date |
| Complaints | 16 rows, reported 1–21 days before the reference date |
| Inspections | 12 rows, 25–300 days before the reference date |
| Staff | 6 synthetic staff (1 AO, 2 AAO, 3 AA), no personal data, no phone numbers |
| Assignments | 3 rows (completed / in progress / pending) |

## Rainfall model

`monthly_mm = 0.8 × climatology[month] × village.rain_factor × lognormal(σ = 0.22)`, then multiplied
by `village.kharif_factor` for June–October 2026 only.

- Climatology is a six-village Mysuru-type bimodal curve (peak July 180 mm, September 190 mm), scaled
  to roughly 840 mm/year at factor 1.0 — a plausible rainfed-taluk figure, not a measured one.
- `rain_factor` varies 0.89–1.08 between villages.
- 2026 Kharif factors: Keralapura 0.45 (drought), Hanagodu 1.35 (excess), others 0.88–1.02.
- Resulting season totals: 323 mm (Keralapura) to 968 mm (Hanagodu) against a 580–709 mm baseline.

## NDVI model

`ndvi = seasonality[month] + 0.16 × clamp(rain/expected_rain − 1, ±1.5) + N(0, 0.012)`, clipped to
0.05–0.92. Cloud cover is 35 % in the monsoon months and 12 % otherwise, with noise; valid pixel
percentage is derived from it. **Gavadagere** additionally loses 45 percentage points of validity, and
months with `valid_pixel_pct < 25` are written as `NULL` NDVI — an explicit "could not retrieve"
state that the reliability score must detect (it drops to 0.48).

This coupling is intentional: drought must show up in NDVI, otherwise the routine monitor would have
nothing to correlate. It also means the demo cannot be used to claim that NDVI detects drought — the
correlation was built in.

## Weather model

Weekly `temp_max_c = 29.5 + 2·sin(week/5) + N(0, 1.2)`; the drought village gets +4.5 °C and 20 % of
the rain, the flood village gets 2.4× rain and −1.5 °C. This produces the heat-week/dry-week counts
the weather factor consumes.

## Complaints

Each village has a "profile" that decides its complaint template:

| Village | Profile | Complaints generated |
|---|---|---|
| Keralapura | drought | 3 × `drought_stress`, 1 × `nutrient_deficiency` |
| Hanagodu | flood | 2 × `flood_damage`, 1 × `disease_outbreak` |
| Bilikere | pest | 4 × `pest_attack` (paddy, cotton) |
| Doddabyranakuppe | irrigation | 2 × `irrigation_issue` |
| Gavadagere | low_reliability | 1 × `nutrient_deficiency` with a low-confidence note |
| Uyyamballi | normal | 1 × `pest_attack`, 1 × `nutrient_deficiency` (area left NULL) |

Categories always match crops the village actually grows (`VILLAGE_CROPS`), affected areas stay below
the village's cultivated area, and dates are chronological and inside the season. Two rows deliberately
omit crop id or area to exercise the "missing crop information" path.

## Inspections and staff

Last-inspection gaps are set per village (Keralapura 220 days — neglected; Bilikere 30 days — recently
visited). Staff capacity is small on purpose (`max_villages_per_day` 1–2, 3–5 available days,
`current_load` 0–4) so the capacity plan is realistic rather than infinite.

## What would change with real data

- IMD grids replace the rainfall generator → `data_type = 'Real'`, source string per row.
- Earth Engine NDVI replaces the NDVI generator → real cloud cover and gaps.
- Registered complaints replace the complaint templates; the schema does not change.
- Nothing in the engine needs retuning, but **all weights and thresholds would need re-validation**
  against real outcomes — the current numbers are design choices, not calibrated values.

## Honest limitation

Because rainfall, NDVI, weather and complaints are all generated from the same village profiles, the
demo's correlations are **constructed**. They demonstrate that the pipeline and explanations work; they
say nothing about real-world predictive performance.
