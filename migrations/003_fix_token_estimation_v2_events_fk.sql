-- Migration: Fix token_estimation_v2_events foreign key to phases
-- Created: 2025-12-24
-- Purpose:
--   Fix "foreign key mismatch" errors caused by token_estimation_v2_events referencing phases(phase_id),
--   where phases.phase_id is NOT globally unique (and not a PRIMARY KEY / UNIQUE column).
--
-- Approach (SQLite-safe):
--   1) Ensure phases(run_id, phase_id) is UNIQUE (this pair is unique in current data).
--   2) Recreate token_estimation_v2_events with a COMPOSITE FK (run_id, phase_id) -> phases(run_id, phase_id).
--   3) Recreate dependent views.
--
-- Notes:
--   - This migration is safe even if token_estimation_v2_events is empty (recommended to run before enabling DB telemetry).
--   - SQLite cannot ALTER TABLE to add/drop foreign keys, so we rebuild the table.

PRAGMA foreign_keys = OFF;

-- 1) Enforce uniqueness for phases within a run (required for composite FK)
CREATE UNIQUE INDEX IF NOT EXISTS uq_phases_run_id_phase_id
  ON phases(run_id, phase_id);

-- 2) Drop dependent views (if present)
DROP VIEW IF EXISTS v_token_estimation_validation;
DROP VIEW IF EXISTS v_recent_token_estimations;

-- 3) Rebuild token_estimation_v2_events with correct composite FK
ALTER TABLE token_estimation_v2_events RENAME TO token_estimation_v2_events_old;

CREATE TABLE IF NOT EXISTS token_estimation_v2_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Estimation inputs
    category TEXT NOT NULL,
    complexity TEXT NOT NULL CHECK(complexity IN ('low', 'medium', 'high', 'critical')),
    deliverable_count INTEGER NOT NULL,
    deliverables_json TEXT NOT NULL,  -- JSON array of deliverable paths (max 20)

    -- Token predictions vs actuals
    predicted_output_tokens INTEGER NOT NULL,
    actual_output_tokens INTEGER NOT NULL,
    selected_budget INTEGER NOT NULL,

    -- Outcome
    success BOOLEAN NOT NULL,
    truncated BOOLEAN NOT NULL DEFAULT 0,
    stop_reason TEXT,
    model TEXT NOT NULL,

    -- Calculated metrics
    smape_percent REAL,  -- Computed: 200 * |pred - actual| / (|pred| + |actual|)
    waste_ratio REAL,    -- Computed: pred / actual
    underestimated BOOLEAN,  -- Computed: actual > pred

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id, phase_id) REFERENCES phases(run_id, phase_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_run_id ON token_estimation_v2_events(run_id);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_phase_id ON token_estimation_v2_events(phase_id);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_timestamp ON token_estimation_v2_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_category ON token_estimation_v2_events(category);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_complexity ON token_estimation_v2_events(complexity);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_success ON token_estimation_v2_events(success);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_truncated ON token_estimation_v2_events(truncated) WHERE truncated = 1;
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_underestimated ON token_estimation_v2_events(underestimated) WHERE underestimated = 1;
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_category_complexity ON token_estimation_v2_events(category, complexity);
CREATE INDEX IF NOT EXISTS ix_token_estimation_v2_deliverable_count ON token_estimation_v2_events(deliverable_count);

-- Copy data forward (safe even if table empty)
INSERT INTO token_estimation_v2_events (
    event_id, run_id, phase_id, timestamp,
    category, complexity, deliverable_count, deliverables_json,
    predicted_output_tokens, actual_output_tokens, selected_budget,
    success, truncated, stop_reason, model,
    smape_percent, waste_ratio, underestimated,
    created_at
)
SELECT
    event_id, run_id, phase_id, timestamp,
    category, complexity, deliverable_count, deliverables_json,
    predicted_output_tokens, actual_output_tokens, selected_budget,
    success, truncated, stop_reason, model,
    smape_percent, waste_ratio, underestimated,
    created_at
FROM token_estimation_v2_events_old;

DROP TABLE IF EXISTS token_estimation_v2_events_old;

-- 4) Recreate views
CREATE VIEW IF NOT EXISTS v_token_estimation_validation AS
SELECT
    category,
    complexity,
    deliverable_count,
    COUNT(*) as sample_count,
    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
    ROUND(AVG(smape_percent), 2) as avg_smape,
    ROUND(AVG(CASE WHEN success = 1 THEN smape_percent END), 2) as avg_smape_success_only,
    ROUND(AVG(waste_ratio), 2) as avg_waste_ratio,
    ROUND(AVG(CASE WHEN success = 1 THEN waste_ratio END), 2) as avg_waste_ratio_success_only,
    SUM(CASE WHEN underestimated = 1 THEN 1 ELSE 0 END) as underestimation_count,
    ROUND(SUM(CASE WHEN underestimated = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as underestimation_rate_pct,
    SUM(CASE WHEN truncated = 1 THEN 1 ELSE 0 END) as truncation_count,
    ROUND(SUM(CASE WHEN truncated = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as truncation_rate_pct,
    ROUND(AVG(predicted_output_tokens), 0) as avg_predicted,
    ROUND(AVG(actual_output_tokens), 0) as avg_actual
FROM token_estimation_v2_events
GROUP BY category, complexity, deliverable_count
ORDER BY sample_count DESC;

CREATE VIEW IF NOT EXISTS v_recent_token_estimations AS
SELECT
    event_id,
    run_id,
    phase_id,
    timestamp,
    category,
    complexity,
    deliverable_count,
    predicted_output_tokens,
    actual_output_tokens,
    selected_budget,
    success,
    truncated,
    stop_reason,
    model,
    ROUND(smape_percent, 2) as smape_percent,
    ROUND(waste_ratio, 2) as waste_ratio,
    underestimated
FROM token_estimation_v2_events
ORDER BY timestamp DESC
LIMIT 100;

PRAGMA foreign_keys = ON;


