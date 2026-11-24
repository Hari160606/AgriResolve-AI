# Phase 10 — Priority engine design

Code: `src/priority_engine/{engine,capacity,sensitivity}.py` · Config: `src/config/priority_weights.yaml`
and `src/config/monitoring.yaml` · Tests: `tests/test_priority_engine.py`.

The engine is a **transparent weighted sum**. There is no trained model, so no accuracy is claimed.
Every village's score can be recomputed by hand from the numbers shown in the UI.

## Pipeline position

```
routine monitoring (no complaint)  ─┐
                                    ├─► combined priority engine ─► ranked list + explanations
reported-issue monitoring          ─┘                              └─► capacity plan
```

## Six factors (weights must sum to 1.0)

| Factor | Weight | Definition | Where the input comes from |
|---|---|---|---|
| `agricultural_risk` | 0.28 | routine risk score / 100 | `src/monitoring/routine.py` |
| `issue_urgency` | 0.36 | complaint severity score / 100 | `src/monitoring/reported.py` |
| `waiting_time` | 0.10 | days since the oldest open complaint / 21, clipped to 1 | complaints |
| `inspection_gap` | 0.08 | days since last inspection / 180, clipped to 1 | inspections |
| `accessibility` | 0.05 | road distance / 40 km, clipped to 1 | villages (simulated distances) |
| `data_reliability` | 0.13 | 1 − reliability score | reliability features |

`priority_score = 100 × Σ (weightᵢ × factorᵢ)`, rounded to 1 decimal.
The contribution table (`data/derived/priority_score_factors.csv`,
`priority_score_factors` in PostgreSQL) stores `factor_value`, `weight` and `contribution` per
village, and a unit test asserts that the contributions add back to the published score.

## Double-counting guard

A drought shows up twice: as an NDVI/rainfall routine signal and as a farmer complaint. Counting both
in full would double-punish the village for one problem.

`dedupe_map` (in the config) maps routine drivers to the complaint categories that describe the same
issue:

```yaml
rainfall_deficit:   [drought_stress, irrigation_issue]
ndvi_decline:       [drought_stress, nutrient_deficiency]
vegetation_anomaly: [pest_attack, disease_outbreak]
weather_risk:       [flood_damage, drought_stress]
```

Rule, applied per village:
1. A routine factor counts as a *driver* when its normalised value ≥ 0.30.
2. If any driver maps to the village's **dominant complaint category**, the village is flagged as an
   overlap and the **weaker of the two streams is halved** — the stronger evidence already represents
   the problem.
3. The rule that fired is written to `dedupe_rule` and shown in the UI ("Double-counting guard applied").

Worked example (Keralapura): routine 62.2 > reported 83.9 is false, so routine is the weaker stream →
`agricultural_risk = 0.311`, `issue_urgency = 0.839`. Rule recorded:
`rainfall_deficit + complaint 'drought_stress' counted once`.

Known limitation: the guard compares the **dominant** category only. A village with a critical pest
outbreak *and* a minor drought complaint is judged on the pest outbreak; that is a deliberate
simplification, documented rather than hidden.

## Bands and thresholds

| Band | Score |
|---|---|
| Inspect first | ≥ 55 |
| High | ≥ 42 |
| Medium | ≥ 32 |
| Low | below 32 |

These are demo-calibrated (six synthetic villages), not field-validated. They are one edit away in
`priority_weights.yaml`.

## Capacity awareness

`capacity.py` turns the staff roster into available visits:

```
capacity_per_week(staff) = max(0, max_villages_per_day × available_days_per_week − current_load)
```

Villages above the Medium band are placed in rank order into that capacity, round-robin weighted by
remaining slots, and the uncovered villages are listed explicitly. With the current roster the plan
covers 20 visits/week, so all six villages fit — the mechanism matters when the list grows or staff are
on leave, and "waiting is an explicit decision" is printed on the page either way.

## Sensitivity analysis

`sensitivity.py` perturbs each weight by ±20 % (renormalising the rest), re-runs the engine and reports
the rank shift for the top three villages.

Current result: **max rank shift 1 across 12 scenarios → stable**. That is an honest, checkable
statement about this data and these weights; it is not a claim about robustness to different villages.

## Design rules that are deliberately *not* followed

- No machine-learned model: with synthetic labels it would produce plausible numbers with no meaning.
- No hidden interaction terms: the score is additive and the factors are the interface.
- No automatic "approval": the human decision is recorded (`approved_by`, `approved_at`) separately
  from the engine output.

## Reproduce

```bash
python -m src.priority_engine.engine        # priority_scores.csv + priority_score_factors.csv
python -m src.priority_engine.capacity      # capacity plan on the console
python -m src.priority_engine.sensitivity   # rank stability under weight perturbation
```
