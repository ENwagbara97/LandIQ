-- =============================================================================
-- LandIQ — Land Risk Intelligence Agent
-- SQLite Database Schema v1.0
-- Idempotent — safe to re-run on an existing database
-- All tables use IF NOT EXISTS — no data is ever dropped
-- =============================================================================

PRAGMA journal_mode=WAL;   -- Write-Ahead Logging for concurrent reads
PRAGMA foreign_keys=ON;

-- =============================================================================
-- TABLE: sessions
-- Tracks active pipeline runs. One row per run_id.
-- Cleared on report completion; retained for HITL audit.
-- =============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    run_id              TEXT    PRIMARY KEY,                -- UUID4
    user_id             TEXT    NOT NULL,                   -- hashed, no PII
    created_at          TEXT    NOT NULL,                   -- ISO8601
    confirmed_at        TEXT,                               -- when user clicked YES
    confirmed           INTEGER NOT NULL DEFAULT 0,        -- boolean 0/1
    status              TEXT    NOT NULL DEFAULT 'pending', -- pending|running|complete|error
    coord_extract_json  TEXT,                               -- CoordExtractOutput JSON
    feed_context_json   TEXT,                               -- NormalisedFeedSchema JSON
    snapshot_path       TEXT,                               -- path to PNG snapshot
    error_detail        TEXT,                               -- structured error if failed
    persona_mode        TEXT    DEFAULT 'EVERYDAY_BUYER',   -- active persona
    pipeline_stage      TEXT    DEFAULT 'INIT'              -- current stage name
);

-- =============================================================================
-- TABLE: reports
-- Permanent record of every completed report.
-- report_json stores the full ReportSchema — source of truth for all exports.
-- =============================================================================
CREATE TABLE IF NOT EXISTS reports (
    report_id           TEXT    PRIMARY KEY,                -- UUID4 — matches run_id
    user_id             TEXT    NOT NULL,
    generated_at        TEXT    NOT NULL,                   -- ISO8601
    parcel_centroid     TEXT    NOT NULL,                   -- JSON: {"lat": x, "lng": y}
    parcel_state        TEXT,                               -- e.g. "Lagos"
    parcel_lga          TEXT,                               -- e.g. "Ikorodu"
    traffic_light       TEXT    NOT NULL,                   -- GREEN|AMBER|RED
    overall_risk_score  REAL    NOT NULL,
    report_json         TEXT    NOT NULL,                   -- full ReportSchema JSON
    snapshot_path       TEXT,                               -- path to PNG (null if failed)
    snapshot_thumb_path TEXT,                               -- path to 240x160 thumbnail
    persona_mode        TEXT    NOT NULL,
    pipeline_version    TEXT    NOT NULL DEFAULT '2.0',
    ollama_model_used   TEXT,                               -- which model ran
    llm_timeout_fired   INTEGER NOT NULL DEFAULT 0,        -- boolean: template fallback used
    total_generation_ms INTEGER,                            -- end-to-end ms
    FOREIGN KEY (report_id) REFERENCES sessions(run_id)
);

-- =============================================================================
-- TABLE: report_data_sources
-- Granular per-field data lineage. One row per measured indicator per report.
-- Powers the Data Sources Transparency Panel.
-- =============================================================================
CREATE TABLE IF NOT EXISTS report_data_sources (
    source_id           TEXT    PRIMARY KEY,                -- UUID4
    report_id           TEXT    NOT NULL,
    field_name          TEXT    NOT NULL,                   -- which report field
    source_adapter      TEXT    NOT NULL,                   -- adapter_id
    source_label        TEXT    NOT NULL,                   -- human-readable name
    data_vintage        TEXT,                               -- "2022", "2023-Q4", "live"
    confidence_score    REAL    NOT NULL,                   -- 0.0–100.0
    live_feed_used      INTEGER NOT NULL DEFAULT 0,        -- boolean
    fallback_used       INTEGER NOT NULL DEFAULT 0,        -- boolean
    field_value_summary TEXT,                               -- short human-readable summary
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

-- =============================================================================
-- TABLE: report_comparisons
-- Delta records between two runs of the same parcel (centroid ≤10m tolerance).
-- Generated automatically when user re-runs a previously analysed parcel.
-- =============================================================================
CREATE TABLE IF NOT EXISTS report_comparisons (
    comparison_id       TEXT    PRIMARY KEY,                -- UUID4
    report_id_a         TEXT    NOT NULL,                   -- earlier report
    report_id_b         TEXT    NOT NULL,                   -- later report
    parcel_match        INTEGER NOT NULL DEFAULT 0,        -- boolean: centroid ≤10m
    delta_json          TEXT    NOT NULL,                   -- field-by-field diff JSON
    plain_english_delta TEXT,                               -- Ollama-generated delta summary
    generated_at        TEXT    NOT NULL,
    FOREIGN KEY (report_id_a) REFERENCES reports(report_id),
    FOREIGN KEY (report_id_b) REFERENCES reports(report_id)
);

-- =============================================================================
-- TABLE: exports
-- Audit log of every PDF/JSON/PNG export generated from report history.
-- Exports always read from stored report_json — never re-run the pipeline.
-- =============================================================================
CREATE TABLE IF NOT EXISTS exports (
    export_id           TEXT    PRIMARY KEY,                -- UUID4
    report_id           TEXT    NOT NULL,
    export_format       TEXT    NOT NULL,                   -- "PDF"|"JSON"|"PNG_CARD"
    export_path         TEXT    NOT NULL,                   -- local file path
    persona_mode        TEXT    NOT NULL,
    exported_at         TEXT    NOT NULL,                   -- ISO8601
    file_size_bytes     INTEGER,
    FOREIGN KEY (report_id) REFERENCES reports(report_id)
);

-- =============================================================================
-- TABLE: lga_benchmarks
-- Aggregate risk stats per LGA — built from accumulated report data.
-- Used for "Contextual Comparisons" in the report (Depth Layer 3).
-- Populated by benchmark_updater.py after each completed report.
-- =============================================================================
CREATE TABLE IF NOT EXISTS lga_benchmarks (
    benchmark_id        TEXT    PRIMARY KEY,                -- UUID4
    lga                 TEXT    NOT NULL,
    state               TEXT    NOT NULL,
    report_count        INTEGER NOT NULL DEFAULT 0,
    avg_flood_score     REAL,
    avg_risk_score      REAL,
    avg_growth_score    REAL,
    avg_elevation_m     REAL,
    avg_data_confidence REAL,
    last_updated        TEXT    NOT NULL,
    UNIQUE(lga, state)
);

-- =============================================================================
-- INDEXES for common query patterns
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_reports_user_id      ON reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_generated_at ON reports(generated_at);
CREATE INDEX IF NOT EXISTS idx_reports_traffic_light ON reports(traffic_light);
CREATE INDEX IF NOT EXISTS idx_reports_lga           ON reports(parcel_lga);
CREATE INDEX IF NOT EXISTS idx_sources_report_id     ON report_data_sources(report_id);
CREATE INDEX IF NOT EXISTS idx_exports_report_id     ON exports(report_id);
CREATE INDEX IF NOT EXISTS idx_benchmarks_lga_state  ON lga_benchmarks(lga, state);

-- =============================================================================
-- Schema version tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS schema_versions (
    version_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version             TEXT    NOT NULL,
    applied_at          TEXT    NOT NULL,
    description         TEXT
);

INSERT OR IGNORE INTO schema_versions (version, applied_at, description)
VALUES ('1.0', datetime('now'), 'Initial LandIQ schema — all core tables');
