-- GLOF Risk Assessment Database Schema
-- PostgreSQL + PostGIS

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- LAKES: glacial lake inventory (ICIMOD-style attributes)
-- ============================================================
CREATE TABLE IF NOT EXISTS lakes (
    id              SERIAL PRIMARY KEY,
    icimod_id       VARCHAR(50) UNIQUE,          -- stand-in ID, matches ICIMOD ID scheme when real data is imported
    name            VARCHAR(200) NOT NULL,
    district        VARCHAR(100),
    basin           VARCHAR(100),                -- river basin, e.g. "Dudh Koshi"
    geom            GEOMETRY(Point, 4326) NOT NULL,   -- lake centroid, WGS84
    elevation_m     INTEGER,
    area_km2        NUMERIC(10,4),               -- most recent known surface area
    area_1990_km2   NUMERIC(10,4),               -- historical baseline area, if known (ICIMOD inventories track this)
    dam_type        VARCHAR(30) NOT NULL DEFAULT 'unknown',  -- moraine | ice | bedrock | unknown
    slope_deg       NUMERIC(5,2),                -- avg slope of dam/surrounding terrain, degrees
    source          VARCHAR(50) NOT NULL DEFAULT 'sample',   -- 'sample' | 'icimod' | other
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lakes_geom ON lakes USING GIST (geom);

-- ============================================================
-- RISK_SCORES: time series of computed risk scores per lake
-- ============================================================
CREATE TABLE IF NOT EXISTS risk_scores (
    id              SERIAL PRIMARY KEY,
    lake_id         INTEGER NOT NULL REFERENCES lakes(id) ON DELETE CASCADE,
    score           NUMERIC(5,2) NOT NULL,       -- 0-100
    level           VARCHAR(20) NOT NULL,        -- low | medium | high | very_high
    breakdown       JSONB NOT NULL,              -- per-factor contributions + raw inputs + data provenance (real vs mock)
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_lake_time ON risk_scores (lake_id, computed_at DESC);

-- ============================================================
-- USER_REPORTS: community-submitted lake condition reports
-- ============================================================
CREATE TABLE IF NOT EXISTS user_reports (
    id              SERIAL PRIMARY KEY,
    lake_id         INTEGER NOT NULL REFERENCES lakes(id) ON DELETE CASCADE,
    reporter_name   VARCHAR(100),                -- optional, anonymous allowed
    condition       VARCHAR(30) NOT NULL,        -- normal | rising_water | new_cracks | seepage | debris | other
    description     TEXT,
    severity        SMALLINT NOT NULL DEFAULT 1 CHECK (severity BETWEEN 1 AND 5),
    photo_url       TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | approved | flagged | rejected
    submitter_ip_hash VARCHAR(64),                -- hashed, for basic rate limiting/spam detection, not raw IP
    honeypot_tripped BOOLEAN NOT NULL DEFAULT false,
    spam_score      NUMERIC(4,2) DEFAULT 0,       -- heuristic spam likelihood, 0-1
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_lake ON user_reports (lake_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_status ON user_reports (status);

-- Convenience view: latest risk score per lake
CREATE OR REPLACE VIEW latest_risk_scores AS
SELECT DISTINCT ON (lake_id) *
FROM risk_scores
ORDER BY lake_id, computed_at DESC;
