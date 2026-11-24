# Phase 7 — Exploratory data analysis findings

Notebook: `notebooks/eda.ipynb` (Plotly charts over `data/cleaned`). The notebook was written but not
executed in this environment (`jupyter` is not part of the fixed stack); the figures below come from
the same CSVs via the pipeline scripts, so the observations are reproducible either way.

> Every observation below describes **synthetic** data. It justifies design choices; it is not a
> finding about Karnataka agriculture.

## 1. Rainfall separates the villages sharply

- Season totals span 323 mm (Keralapura) to 968 mm (Hanagodu) against baselines of 580–709 mm.
- Deviation range: −51.4 % to +36.6 %; five of six villages fall inside ±21 %, so the two outliers are
  the interesting cases.
- **Implication:** a single absolute rainfall threshold would be useless; deviation from each village's
  own baseline is the right normalisation. That is why the routine factor uses
  `(baseline − season)/baseline` and not raw millimetres.

## 2. NDVI follows rainfall, with a lag

- The drought village's NDVI falls 0.043 below the same month last year; the flood village rises 0.095.
- Year-on-year change is small in absolute terms (0.02–0.10), which is why the `ndvi_decline` threshold
  is 0.15 for "full risk" and the routine score uses a 0–1 ramp instead of a binary test.

## 3. Complaint mix

- 16 complaints, of which 6 are `pest_attack`, 3 `drought_stress`, 2 `flood_damage`, 2 `irrigation_issue`,
  2 `nutrient_deficiency`, 1 `disease_outbreak`.
- The pest cluster is concentrated in one village (4 complaints in Bilikere) — this is the "repeat
  complaints" signal the reported monitor is designed to catch (repeat factor = (n−1)/3).
- Two rows have no crop id and one has no affected area, which is realistic: the monitor must not
  ignore a complaint just because the form was incomplete.

## 4. Inspection gaps are uneven

- Gaps range from 25 to 220 days. Keralapura (drought, 220 days) is the clearest "nobody has looked
  recently" case; the routine monitor gives it a full 1.0 on `inspection_recency`.
- Bilikere was visited 30 days ago, so its high priority comes from complaints, not neglect — a useful
  contrast when explaining the ranking to an AO.

## 5. Data completeness is not uniform

- Five villages have 91.7 % NDVI completeness; Gavadagere has 58.3 % and a reliability score of 0.481.
- **Implication:** reliability must be a visible factor, not a silent quality filter. The engine adds a
  `data_reliability` contribution and the UI shows a "verify in field" warning.

## 6. Threshold ideas produced by the analysis

| Rule | Threshold used | Why |
|---|---|---|
| Routine flag | risk ≥ 60 | with the current weights, only the −51 % rainfall village reaches it; higher would flag nothing |
| Rainfall "full" risk | deficit ≥ 50 % | matches the observed drought-village magnitude |
| NDVI decline "full" | −0.15 YoY | about 3× the largest normal year-on-year wobble in the data |
| Repeat complaints | (n−1)/3 | 4 complaints in one village saturates; 2 gives 0.33 |
| Inspection overdue | 180 days | half a year without a visit on a seasonal crop |
| Low reliability | < 0.60 | separates Gavadagere (0.481) from everyone else (≈0.68) |

All of these are **design choices for the demo**, not calibrated probabilities. They live in
`src/config/monitoring.yaml` so they can be changed and re-run in one command.

## 7. Separating real from synthetic in the notebook

The notebook explicitly filters on `data_type`/`is_synthetic` before plotting and colours synthetic
series differently, so a future run that mixes real IMD rainfall with synthetic complaints cannot
accidentally present them as one dataset.
