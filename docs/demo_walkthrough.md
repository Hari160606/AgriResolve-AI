# Demo walkthrough (three scenarios)

Reference date **2026-11-24**, all data synthetic. Start the site with
`.venv\Scripts\streamlit run app/streamlit_app.py`, sign in as **AO**.

## Scenario A — drought village that nobody complained about (Keralapura)

1. **RSK overview** → mean reliability 0.66, one routine flag, "Inspect first: Keralapura (62.3)".
2. **Routine monitoring** → Keralapura is the only flagged village, risk 62.2.
   Open its detail: season rainfall **323 mm vs 665 mm baseline (−51.4 %)**, NDVI **−0.043** versus last
   year, **220 days** since the last inspection.
3. **Priority list** → rank 1. The factor chart shows `agricultural_risk` 0.62 (weight 0.28),
   `issue_urgency` 0.42 (weight 0.36, halved by the dedupe rule because the drought complaint describes
   the same problem) and `inspection_gap` 1.00 (weight 0.08).
4. The rationale reads: priority 62.3/100 — Inspect first; top drivers; "Double-counting guard applied
   (rainfall_deficit + complaint 'drought_stress' counted once)"; "Routine risk 62 and complaint
   severity 84 both point at this village."
5. **Approve** it as AO, then **assign** it to an AAO with a due date. The capacity panel shows the
   suggestion it would have made itself.

What this demonstrates: complaint-free detection, explainability, dedupe, human approval.

## Scenario B — pest outbreak that the satellite barely noticed (Bilikere)

1. **Reported issues** → Bilikere severity **85.7, Critical**, 4 complaints, dominant category
   `pest_attack`, 37 ha reported.
2. **Priority list** → rank 2 (47.6). Here the complaint stream drives the score: routine risk is only
   22.3 and the last inspection was 30 days ago, so the "neglect" factors are low.
3. Compare with **Hanagodu** (rank 3, 45.3) whose complaints are `flood_damage`/`disease_outbreak` and
   whose rainfall is +37 % — same band, different story.
4. Sign in as **AAO/AA**, pick the officer holding the Bilikere assignment, and open **My field
   dashboard**: only that officer's villages appear.

What this demonstrates: reported-issue severity, ranking contrast, role separation.

## Scenario C — the village you cannot judge from a desk (Gavadagere)

1. **RSK overview** → reliability table shows Gavadagere at **0.481** (completeness 0.583) and the
   warning "Low reliability: Gavadagere. Treat their flags as 'verify in field'."
2. **Priority list** → rank 4 (43.5). The `data_reliability` factor is 0.52 — the engine is explicitly
   sending an officer to check, not concluding that the village is healthy.
3. In the AAO view, **register a new complaint** for Gavadagere: try a negative area and a future date
   first (validation refuses both), then a valid entry. The new complaint appears in the register and
   changes the reported-issue ranking on the next rerun.

What this demonstrates: reliability as a visible factor, server-side validation, live recomputation.

## Scenario D (optional) — the assistant

1. **AI field assistant** → ask "What should I check first in a paddy field with planthopper hoppers?"
   with village Bilikere, crop Paddy, issue `pest_attack`.
2. The answer is produced by local `llama3` from retrieved passages only, with document + page sources.
3. Ask something outside the corpus ("what dose of chlorpyrifos should I use?") — it refuses instead of
   inventing a dose. That refusal is the feature.

## End-to-end flow recap

register complaint (AAO) → cleaning/derived features → routine monitoring → reported monitoring →
combined priority (AO) → approve → assign (AO) → AAO sees assignment → assistant guidance.

The first link (registration) and the last (assignment) are written through
`src/utils/data_access.py`: persisted in PostgreSQL when configured, session-only in CSV demo mode.

## What is still not testable here

- The PostgreSQL write path — no database password was configured, so those statements have never run
  against a live server.
- The Google Maps / Routes / Weather / Earth Engine paths — no keys, no authentication.
- Any comparison with real government data or real inspection outcomes.

## Bugs fixed while building this walkthrough

1. The drought village scored 53.6 and fell just under the 60 flag threshold — the generator's drought
   signal was too weak to be a convincing demo; the Kharif factor was tightened to 0.45 and the
   NDVI-rainfall coupling raised to 0.16.
2. The dedupe rule initially discounted the *complaint* stream even when the complaint was the stronger
   evidence, which pushed a Critical pest outbreak to last place; it now halves the weaker stream.
3. Weight rebalance (urgency 0.36, reliability 0.13) so a same-day critical complaint is not buried
   under structural penalties — the factor chart makes this choice auditable.
4. `pandas.Timedelta(days=…)` emitted NumPy deprecation warnings on Python 3.13; replaced with
   `datetime.timedelta`.
5. The RAG ingest picked up `guidelines_pdfs/README.md` as a document; folder meta-files are now skipped.
