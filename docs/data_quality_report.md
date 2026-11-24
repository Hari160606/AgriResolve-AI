# Phase 5 — Data quality report

Source of truth: `data/derived/village_features.csv`, `data/derived/cleaning_log.csv`,
`data/derived/monitoring_results.csv`. Reference date 2026-11-24. All data synthetic.

## Cleaning actions performed

`src/preprocessing/clean.py` writes one log row per action; the current run removed nothing, because
the generator already emits well-formed data. The rules still run and are unit-tested:

| Table | Rule | Effect this run |
|---|---|---|
| villages | trim/title-case names, dedupe on `village_id` | 6 → 6 |
| rainfall_monthly | coerce numeric, drop negatives, dedupe (village, year, month) | 564 → 564 |
| ndvi_monthly | coerce, treat `0` as missing, clip to 0–1, clip cloud/valid % to 0–100, dedupe | 276 → 276 (6 rows already NULL by design) |
| weather_weekly | parse week dates, clip temperature 5–50 °C, humidity 0–100, rainfall ≥ 0 | 96 → 96 |
| farmer_complaints | standardise category & urgency, parse dates, dedupe, flag missing crop/area | 16 → 16 (2 rows flagged) |
| inspections_history | parse dates, dedupe | 12 → 12 |

## Per-village reliability

Reliability = 0.50 × completeness (share of the last 12 months with valid NDVI) + 0.25 ×
(1 − cloud fraction) + 0.25 × recency factor (100 % if the latest valid NDVI is today, 0 % at 60 days).

| Village | NDVI completeness | Mean cloud % | NDVI recency (days) | Reliability | Reading |
|---|---|---|---|---|---|
| Keralapura (V01) | 0.917 | 21.9 | 25 | 0.679 | acceptable |
| Hanagodu (V02) | 0.917 | 21.4 | 25 | 0.680 | acceptable |
| Bilikere (V03) | 0.917 | 25.8 | 25 | 0.669 | acceptable |
| Doddabyranakuppe (V04) | 0.917 | 22.7 | 25 | 0.677 | acceptable |
| **Gavadagere (V05)** | **0.583** | 24.1 | 25 | **0.481** | **below the 0.60 low-reliability cutoff** |
| Uyyamballi (V06) | 0.917 | 20.2 | 25 | 0.683 | acceptable |

Gavadagere's low score is not a bug: the generator deliberately loses half its valid observations to
cloud, which is exactly the situation where satellite-only monitoring must hand over to a field visit.
The UI shows a warning and the priority engine adds a `data_reliability` contribution.

## Derived indicators (season-level)

| Village | Season rainfall (mm) | Baseline (mm) | Deviation | NDVI latest | NDVI YoY | Days since inspection |
|---|---|---|---|---|---|---|
| Keralapura | 323.0 | 665.2 | **−51.4 %** | 0.573 | −0.043 | 220 |
| Hanagodu | 968.3 | 708.8 | +36.6 % | 0.668 | +0.095 | 25 |
| Bilikere | 680.0 | 637.1 | +6.7 % | 0.567 | −0.075 | 30 |
| Doddabyranakuppe | 480.6 | 606.8 | −20.8 % | 0.597 | −0.020 | 75 |
| Gavadagere | 602.0 | 579.6 | +3.9 % | 0.639 | −0.035 | 140 |
| Uyyamballi | 655.5 | 674.8 | −2.9 % | 0.629 | 0.000 | 60 |

## Known data-quality issues

1. **Village-scale rainfall does not exist.** A 0.25° IMD cell (~27 km) is used as a proxy; all six
   villages would share one or two cells in reality, so between-village rainfall differences are
   exaggerated by the generator (which assigns each village its own multiplier).
2. **Cloud-driven gaps are real, not noise.** They are kept as `NULL` rather than imputed, because an
   imputed NDVI would silently inflate confidence.
3. **Outliers are clipped, not removed.** A rainfall value of 400 mm in one month is physically
   possible; deleting it would bias the baseline low.
4. **Complaint area is often missing or estimated.** The schema allows `NULL`; the reported monitor
   sums only reported areas and the explanation says "reported affected area".
5. **Two complaint rows have no crop id** (by design). They are flagged `missing_crop_info = TRUE` and
   still count towards severity — an unreported crop must not make an issue disappear.

## Reproduce

```bash
python -m src.utils.pipeline
# then read data/derived/cleaning_log.csv and data/derived/village_features.csv
```
