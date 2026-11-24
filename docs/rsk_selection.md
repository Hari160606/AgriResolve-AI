# Phase 2 — RSK and village cluster selection

> **Status: SIMULATED.** The villages below were **not** verified as belonging to RSK Hunsur.
> KGIS village boundaries and LGD codes were not downloaded (no access verified in this session),
> so every village id, name-to-code binding and coordinate in this prototype is a placeholder.
> Read this document as "the shape of the selection", not as an administrative fact.

## What an RSK is

A **Raitha Samparka Kendra (RSK)** is Karnataka's farmer contact centre at hobli level, staffed by
Agriculture Department personnel (AO / AAO / AA). The prototype models **one RSK with six villages**,
because the demo must fit one officer's weekly capacity.

## Candidate RSKs considered (all unverified)

| Candidate | District | Why considered | What blocked verification |
|---|---|---|---|
| RSK Hunsur (chosen, simulated) | Mysuru | rainfed ragi/maize + paddy in the tank command, short travel distances, mixed crop portfolio | RSK jurisdiction list not published as open data; KGIS/LGD not downloaded |
| RSK Periyapatna | Mysuru | paddy-heavy, good Sentinel-2 coverage | same |
| RSK Nanjangud | Mysuru | canal command, irrigation issues | same |
| RSK HD Kote | Mysuru | large tribal/rainfed area | longer travel distances, sparse data |

Scoring dimensions (as required by the phase brief) could not be filled with verified values, so the
table above records *why*, not fake numbers. Once KGIS boundaries and LGD codes are exported, this
table should be completed with: boundary availability, code availability, IMD cell coverage,
Sentinel-2 cloud burden, crop statistics availability, administrator record availability.

## Selected cluster (simulated)

| Village id | Name | LGD code | Lat, Lon | Cultivated area (ha) | Distance from RSK (km) | Profile used by the generator |
|---|---|---|---|---|---|---|
| V01 | Keralapura | SIM-LGD-0001 | 12.3521, 76.2610 | 412 | 9.5 | drought-stressed in Kharif 2026 |
| V02 | Hanagodu | SIM-LGD-0002 | 12.2731, 76.3205 | 530 | 14.0 | excess rain / flood complaints |
| V03 | Bilikere | SIM-LGD-0003 | 12.3398, 76.3452 | 468 | 7.0 | pest outbreak (planthopper) |
| V04 | Doddabyranakuppa | SIM-LGD-0004 | 12.2890, 76.2408 | 356 | 22.5 | canal-release irrigation issues |
| V05 | Gavadagere | SIM-LGD-0005 | 12.3140, 76.2075 | 298 | 31.0 | low data reliability (cloud-prone) |
| V06 | Uyyamballi | SIM-LGD-0006 | 12.3655, 76.3021 | 388 | 17.5 | near-normal baseline |

Coordinates are indicative points near the taluk headquarters (12.3085 N, 76.2927 E), not surveyed
village centroids. Names are realistic for the area but their association with these coordinates is
**not verified**.

## Why this cluster suits a prototype

- **Crop diversity**: ragi, paddy, maize, sugarcane, groundnut and cotton across the six villages,
  so category-specific logic (waterlogging vs drought vs pest) can all be demonstrated.
- **Distinct risk stories**: one drought village, one flood village, one pest cluster, one
  irrigation-issue village and one low-reliability village — enough to test every monitoring branch.
- **Manageable size**: six villages fit an AO's weekly capacity discussion without diluting the demo.
- **Travel spread**: 7–31 km, so accessibility visibly changes the ranking.

## How to make this real (replaces the simulated block)

1. Download the village boundary layer from KGIS (https://kgis.ksrsac.in/kgis/downloads.aspx) and
   check its usage terms.
2. Export the taluk's village list from the Local Government Directory (https://lgdirectory.gov.in).
3. Run `python -m src.ingestion.villages <shapefile>` to spatially match points to polygons.
4. Update `villages.lgd_code` / `latitude` / `longitude`, set `source_status = 'verified'` (and
   `rsk.mapping_status = 'verified'` only if the RSK jurisdiction is confirmed from an official list).
5. Only then may the "simulated" banner be removed from the UI.
