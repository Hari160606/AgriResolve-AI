# Assumptions log

Running list of every assumption the prototype depends on. If one of these is wrong, the affected part
of the demo is wrong too.

## Data and provenance

1. All observations in the repository are synthetic, generated with seed 42 by
   `src/ingestion/synthetic/generate.py`; see `docs/synthetic_assumptions.md` for the formulas.
2. The RSK and its six villages are a **simulated** administrative arrangement; LGD codes are
   placeholders (`SIM-LGD-000x`) and coordinates are indicative points, not surveyed centroids.
3. IMD gridded rainfall, Sentinel-2 via Earth Engine, Google Weather/Routes/Maps and data.gov.in are
   documented and coded but **never executed** here — no file, key or authentication was available.
4. A 0.25° IMD cell (~27 km) is the finest rainfall resolution an officer could have from that source;
   the demo assigns each village its own rainfall series, which overstates between-village variation.
5. `data/raw/` is the only place originals may live; nothing in the pipeline writes to it.

## Modelling

6. The priority engine is rule/weight based; the weights and bands were chosen to make the six-village
   demo legible, not calibrated against outcomes. Changing them is expected, not a bug.
7. "Double counting" means a routine driver and the village's **dominant** complaint category describe
   the same issue; secondary complaint categories are not checked against the dedupe map.
8. Reliability (completeness, cloud burden, recency) measures whether the desk can judge the village,
   not whether the village is healthy — hence low reliability raises priority instead of clearing it.
9. Capacity is expressed in village-visits per week: `max_villages_per_day × available_days − current
   load`, floored at zero.
10. Farmer complaints are single-issue records; an issue's lifecycle (assigned → inspected → closed) is
    not modelled beyond the `status` field.

## Application

11. Role selection is a prototype switch, not authentication; there are no user accounts, sessions or
    per-user data isolation (a stated scope exclusion).
12. In CSV demo mode, form submissions live in process memory and disappear on restart; the UI states
    this on every write.
13. Streamlit is addressed on `127.0.0.1:8501`; the Google Maps key (when added) must allow that
    referrer.
14. Local `llama3` is the only LLM; no external model or API is used, and no key is needed.
15. The assistant's corpus is one internal demo note, explicitly not an official document.

## Still unresolved

16. PostgreSQL credentials (role/password) for `agriresolve_app` — blocks phase 6 verification.
17. Google Cloud project id for Earth Engine, and whether the student's account is EE-registered.
18. Repository licence, branch strategy and whether phases should land on `main` or per-phase branches.
