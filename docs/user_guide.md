# User guide

## Starting the site

```bash
.venv\Scripts\streamlit run app/streamlit_app.py
```

The app opens on http://127.0.0.1:8501. Two prototype roles are offered in the sidebar — **AO** and
**AAO/AA**. There is no authentication: the selector only decides which pages are visible, mirroring
the workflow split (this is a stated scope exclusion, not a missing feature).

Every page shows two banners: a **synthetic data** warning and the current storage mode
(PostgreSQL, or CSV demo mode where form submissions are session-only).

## AO pages

### RSK overview
KPIs (villages, routine flags, villages with new complaints, 30-day complaint count, mean reliability),
the village intelligence map, the ranked priority list and an "inspect first" recommendation with its
reason. Use it as the opening screen of a demo.

### Routine monitoring
Flags villages that need attention **without any complaint**: rainfall deficit against the village's
own 8-year baseline, NDVI decline versus the same month last year, unusual vegetation change,
heat/dry weeks, days since last inspection and low data reliability. Chart + factor table + per-village
explanation, including a reliability note ("verify in field" when reliability < 0.60).

### Reported issues
Severity per village from the last 30 days of complaints, the category mix, and the full complaint
register. Severity uses the worst urgency/category, the summed affected area, repeat count and waiting
time. Multiple complaints from one village are treated as one village-level issue.

### Priority list
The ranked list, then for the selected village: a factor-contribution chart, the plain-language
rationale, the double-counting note (if it fired) and the linked complaint ids. From here the AO can
**approve** the priority and **assign** an AAO/AA with a due date. Below that: the capacity plan
(visits available this week, suggested officer per village, villages beyond capacity) and the
sensitivity table (rank shifts when a weight moves ±20 %).

### Staff & assignments
Available capacity per officer, the roster with workload, and every assignment with status and rank at
assignment time.

### AI field assistant
Ask an inspection question; optionally add village/crop/category context. Answers are restricted to
retrieved guideline passages and cite document + page. The panel at the bottom states the corpus
limitations honestly.

## AAO / AA page

- **My field dashboard**: pick the officer, see only their own assignments with counts by status.
- **Register a farmer issue**: village, crop (optional), category, urgency, affected area (optional),
  date, description. Validation rejects unknown villages/crops/categories, non-positive areas and
  future dates; a missing crop or area is allowed and flagged. In demo mode the registration is
  session-only and the page says so.
- **Village information**: LGD code (marked simulated), cultivated area, distance, crops grown,
  complaint count.
- **AI field assistant** is available here too; approvals and staff allocation are not.

## Reading the numbers

| Number | Meaning |
|---|---|
| Routine risk 0–100 | weighted sum of six monitoring factors; ≥ 60 raises a flag |
| Complaint severity 0–100 | urgency, category, affected-area share, repeats, waiting, recency |
| Priority 0–100 | six-factor weighted combination of the two streams above |
| Band | Inspect first ≥ 55 · High ≥ 42 · Medium ≥ 32 |
| Reliability 0–1 | NDVI completeness + cloud burden + recency |

Anything you see can be recomputed by hand from the weights in `src/config/*.yaml` — that is the point.

## Common questions

**Why is a village with no complaints ranked?** Because routine monitoring flagged it (rainfall
deficit, NDVI decline, long inspection gap, or unreliable data). That is the "no farmer complaint
required" half of the workflow.

**Why is a critical complaint not rank 1?** Priority also weighs routine risk, waiting time,
accessibility and data reliability. Open the village's factor chart to see exactly why; adjust the
weights in `priority_weights.yaml` and re-run if you disagree.

**Why does the map look like OpenStreetMap?** No `GOOGLE_MAPS_API_KEY` is configured, so the app uses
the Plotly/OpenStreetMap fallback. See `docs/api_setup.md`.
