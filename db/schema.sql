-- AgriResolve AI - PostgreSQL schema.
-- Apply with:  psql -U agriresolve_app -d agriresolve -f db/schema.sql
-- Every observational table carries is_synthetic + data_type so a synthetic row can
-- never be mistaken for a government or field observation.

BEGIN;

DROP VIEW IF EXISTS v_village_priority_latest;

DROP TABLE IF EXISTS priority_score_factors;
DROP TABLE IF EXISTS priority_scores;
DROP TABLE IF EXISTS monitoring_results;
DROP TABLE IF EXISTS data_reliability;
DROP TABLE IF EXISTS guideline_documents;
DROP TABLE IF EXISTS assignments;
DROP TABLE IF EXISTS inspections_history;
DROP TABLE IF EXISTS farmer_complaints;
DROP TABLE IF EXISTS weather_observations;
DROP TABLE IF EXISTS ndvi_observations;
DROP TABLE IF EXISTS rainfall_observations;
DROP TABLE IF EXISTS village_crops;
DROP TABLE IF EXISTS staff;
DROP TABLE IF EXISTS crops;
DROP TABLE IF EXISTS villages;
DROP TABLE IF EXISTS rsk;

-- ---------------------------------------------------------------- reference data

CREATE TABLE rsk (
    rsk_id          VARCHAR(16) PRIMARY KEY,
    rsk_name        TEXT        NOT NULL,
    district        TEXT        NOT NULL,
    taluk           TEXT        NOT NULL,
    hobli           TEXT,
    latitude        NUMERIC(9, 6) NOT NULL,
    longitude       NUMERIC(9, 6) NOT NULL,
    -- 'verified' only when the RSK-to-village mapping comes from an official source.
    mapping_status  TEXT        NOT NULL CHECK (mapping_status IN ('verified', 'simulated')),
    is_synthetic    BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type       TEXT        NOT NULL DEFAULT 'Synthetic'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE villages (
    village_id          VARCHAR(16) PRIMARY KEY,
    village_name        TEXT        NOT NULL,
    lgd_code            VARCHAR(24) UNIQUE,
    rsk_id              VARCHAR(16) NOT NULL REFERENCES rsk (rsk_id),
    district            TEXT        NOT NULL,
    taluk               TEXT        NOT NULL,
    hobli               TEXT,
    latitude            NUMERIC(9, 6) NOT NULL,
    longitude           NUMERIC(9, 6) NOT NULL,
    cultivated_area_ha  NUMERIC(10, 2) NOT NULL CHECK (cultivated_area_ha > 0),
    road_distance_km    NUMERIC(6, 2) CHECK (road_distance_km >= 0),
    -- 'simulated' until the KGIS/LGD lookup is verified for this village.
    source_status       TEXT        NOT NULL DEFAULT 'simulated'
                        CHECK (source_status IN ('verified', 'simulated')),
    is_synthetic        BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type           TEXT        NOT NULL DEFAULT 'Synthetic'
                        CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crops (
    crop_id             VARCHAR(16) PRIMARY KEY,
    crop_name           TEXT        NOT NULL UNIQUE,
    water_requirement   TEXT        CHECK (water_requirement IN ('low', 'medium', 'high')),
    is_synthetic        BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type           TEXT        NOT NULL DEFAULT 'Synthetic'
                        CHECK (data_type IN ('Real', 'Derived', 'Synthetic'))
);

CREATE TABLE village_crops (
    village_id   VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    crop_id      VARCHAR(16) NOT NULL REFERENCES crops (crop_id),
    area_ha      NUMERIC(10, 2) NOT NULL CHECK (area_ha > 0),
    is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    data_type    TEXT NOT NULL DEFAULT 'Synthetic'
                 CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    PRIMARY KEY (village_id, crop_id)
);

CREATE TABLE staff (
    staff_id                VARCHAR(16) PRIMARY KEY,
    name                    TEXT        NOT NULL,
    role                    TEXT        NOT NULL CHECK (role IN ('AO', 'AAO', 'AA')),
    max_villages_per_day    SMALLINT    NOT NULL DEFAULT 0 CHECK (max_villages_per_day >= 0),
    available_days_per_week SMALLINT    NOT NULL DEFAULT 0 CHECK (available_days_per_week BETWEEN 0 AND 7),
    current_load            NUMERIC(5, 2) NOT NULL DEFAULT 0,
    is_synthetic            BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type               TEXT        NOT NULL DEFAULT 'Synthetic'
                            CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- observations

CREATE TABLE rainfall_observations (
    observation_id  BIGSERIAL PRIMARY KEY,
    village_id      VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    year            SMALLINT    NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    month           SMALLINT    NOT NULL CHECK (month BETWEEN 1 AND 12),
    rainfall_mm     NUMERIC(8, 1) NOT NULL CHECK (rainfall_mm >= 0),
    source          TEXT        NOT NULL,
    is_synthetic    BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type       TEXT        NOT NULL DEFAULT 'Synthetic'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (village_id, year, month)
);

CREATE TABLE ndvi_observations (
    observation_id   BIGSERIAL PRIMARY KEY,
    village_id       VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    year             SMALLINT    NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month            SMALLINT    NOT NULL CHECK (month BETWEEN 1 AND 12),
    ndvi_mean        NUMERIC(5, 3) CHECK (ndvi_mean BETWEEN -1 AND 1),
    cloud_cover_pct  NUMERIC(5, 1) CHECK (cloud_cover_pct BETWEEN 0 AND 100),
    valid_pixel_pct  NUMERIC(5, 1) CHECK (valid_pixel_pct BETWEEN 0 AND 100),
    sensor           TEXT        NOT NULL DEFAULT 'Sentinel-2',
    is_synthetic     BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type        TEXT        NOT NULL DEFAULT 'Synthetic'
                     CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (village_id, year, month)
);

CREATE TABLE weather_observations (
    observation_id  BIGSERIAL PRIMARY KEY,
    village_id      VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    week_start      DATE        NOT NULL,
    temp_max_c      NUMERIC(4, 1),
    temp_min_c      NUMERIC(4, 1),
    humidity_pct    NUMERIC(5, 1),
    rainfall_mm     NUMERIC(8, 1),
    source          TEXT        NOT NULL DEFAULT 'synthetic_generator',
    is_synthetic    BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type       TEXT        NOT NULL DEFAULT 'Synthetic'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (village_id, week_start)
);

-- ---------------------------------------------------------------- workflow data

CREATE TABLE farmer_complaints (
    complaint_id     VARCHAR(16) PRIMARY KEY,
    village_id       VARCHAR(16) NOT NULL REFERENCES villages (village_id),
    crop_id          VARCHAR(16) REFERENCES crops (crop_id),
    category         TEXT        NOT NULL CHECK (category IN (
                        'pest_attack', 'disease_outbreak', 'drought_stress',
                        'flood_damage', 'nutrient_deficiency', 'irrigation_issue', 'other')),
    affected_area_ha NUMERIC(10, 2) CHECK (affected_area_ha > 0),
    urgency          TEXT        NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
    reported_date    DATE        NOT NULL,
    description      TEXT        NOT NULL,
    reporter_role    TEXT        NOT NULL DEFAULT 'AA' CHECK (reporter_role IN ('AO', 'AAO', 'AA')),
    status           TEXT        NOT NULL DEFAULT 'registered'
                     CHECK (status IN ('registered', 'assigned', 'inspected', 'closed')),
    is_synthetic     BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type        TEXT        NOT NULL DEFAULT 'Synthetic'
                     CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inspections_history (
    inspection_id   VARCHAR(16) PRIMARY KEY,
    village_id      VARCHAR(16) NOT NULL REFERENCES villages (village_id),
    staff_id        VARCHAR(16) REFERENCES staff (staff_id),
    inspection_date DATE        NOT NULL,
    purpose         TEXT        NOT NULL DEFAULT 'routine'
                    CHECK (purpose IN ('routine', 'complaint_followup', 'verification')),
    findings        TEXT,
    outcome         TEXT        CHECK (outcome IN ('no_action', 'advisory_issued', 'treatment_recommended', 'escalated')),
    is_synthetic    BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type       TEXT        NOT NULL DEFAULT 'Synthetic'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assignments (
    assignment_id VARCHAR(16) PRIMARY KEY,
    village_id    VARCHAR(16) NOT NULL REFERENCES villages (village_id),
    staff_id      VARCHAR(16) NOT NULL REFERENCES staff (staff_id),
    assigned_date DATE        NOT NULL,
    due_date      DATE,
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority_rank SMALLINT,
    notes         TEXT,
    is_synthetic  BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type     TEXT        NOT NULL DEFAULT 'Synthetic'
                  CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (due_date IS NULL OR due_date >= assigned_date)
);

-- ---------------------------------------------------------------- engine outputs

CREATE TABLE monitoring_results (
    result_id         BIGSERIAL PRIMARY KEY,
    run_date          DATE        NOT NULL,
    village_id        VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    trigger           TEXT        NOT NULL CHECK (trigger IN ('routine_monitoring', 'reported_issue')),
    flag              BOOLEAN     NOT NULL DEFAULT FALSE,
    risk_score        NUMERIC(5, 1) CHECK (risk_score BETWEEN 0 AND 100),
    severity_score    NUMERIC(5, 1) CHECK (severity_score BETWEEN 0 AND 100),
    severity_level    TEXT,
    explanation       TEXT        NOT NULL,
    reliability_score NUMERIC(5, 3) CHECK (reliability_score BETWEEN 0 AND 1),
    factors           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    is_synthetic      BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type         TEXT        NOT NULL DEFAULT 'Synthetic'
                      CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_date, village_id, trigger)
);

CREATE TABLE priority_scores (
    priority_id      BIGSERIAL PRIMARY KEY,
    run_date         DATE        NOT NULL,
    village_id       VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    rank             SMALLINT    NOT NULL CHECK (rank > 0),
    priority_score   NUMERIC(5, 1) NOT NULL CHECK (priority_score BETWEEN 0 AND 100),
    band             TEXT        NOT NULL,
    explanation      TEXT        NOT NULL,
    overlap_detected BOOLEAN     NOT NULL DEFAULT FALSE,
    dedupe_rule      TEXT,
    approved_by      TEXT,
    approved_at      TIMESTAMPTZ,
    is_synthetic     BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type        TEXT        NOT NULL DEFAULT 'Synthetic'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_date, village_id)
);

CREATE TABLE priority_score_factors (
    factor_id   BIGSERIAL PRIMARY KEY,
    priority_id BIGINT      NOT NULL REFERENCES priority_scores (priority_id) ON DELETE CASCADE,
    factor      TEXT        NOT NULL,
    factor_value NUMERIC(6, 4) NOT NULL CHECK (factor_value BETWEEN 0 AND 1),
    weight      NUMERIC(6, 4) NOT NULL CHECK (weight BETWEEN 0 AND 1),
    contribution NUMERIC(6, 4) NOT NULL CHECK (contribution BETWEEN 0 AND 1),
    UNIQUE (priority_id, factor)
);

CREATE TABLE data_reliability (
    reliability_id   BIGSERIAL PRIMARY KEY,
    village_id       VARCHAR(16) NOT NULL REFERENCES villages (village_id) ON DELETE CASCADE,
    as_of            DATE        NOT NULL,
    completeness     NUMERIC(5, 3) NOT NULL CHECK (completeness BETWEEN 0 AND 1),
    cloud_cover_avg  NUMERIC(5, 1),
    ndvi_recency_days SMALLINT,
    reliability_score NUMERIC(5, 3) NOT NULL CHECK (reliability_score BETWEEN 0 AND 1),
    is_synthetic     BOOLEAN     NOT NULL DEFAULT TRUE,
    data_type        TEXT        NOT NULL DEFAULT 'Derived'
                    CHECK (data_type IN ('Real', 'Derived', 'Synthetic')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (village_id, as_of)
);

CREATE TABLE guideline_documents (
    document_id  BIGSERIAL PRIMARY KEY,
    title        TEXT        NOT NULL,
    organisation TEXT        NOT NULL,
    source_url   TEXT,
    licence      TEXT,
    page_count   SMALLINT,
    file_path    TEXT,
    retrieved_at DATE,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- indexes + view

CREATE INDEX idx_villages_rsk ON villages (rsk_id);
CREATE INDEX idx_rainfall_village_year ON rainfall_observations (village_id, year);
CREATE INDEX idx_ndvi_village_year ON ndvi_observations (village_id, year);
CREATE INDEX idx_weather_village_week ON weather_observations (village_id, week_start);
CREATE INDEX idx_complaints_village_date ON farmer_complaints (village_id, reported_date DESC);
CREATE INDEX idx_complaints_status ON farmer_complaints (status);
CREATE INDEX idx_inspections_village_date ON inspections_history (village_id, inspection_date DESC);
CREATE INDEX idx_assignments_staff_status ON assignments (staff_id, status);
CREATE INDEX idx_monitoring_run ON monitoring_results (run_date, trigger);
CREATE INDEX idx_priority_run ON priority_scores (run_date, rank);
CREATE INDEX idx_factors_priority ON priority_score_factors (priority_id);

CREATE VIEW v_village_priority_latest AS
SELECT p.run_date,
       p.rank,
       v.village_id,
       v.village_name,
       v.source_status,
       p.priority_score,
       p.band,
       p.overlap_detected,
       p.dedupe_rule,
       p.explanation,
       p.approved_by,
       p.is_synthetic
FROM priority_scores p
JOIN villages v ON v.village_id = p.village_id
WHERE p.run_date = (SELECT max(run_date) FROM priority_scores);

COMMIT;
