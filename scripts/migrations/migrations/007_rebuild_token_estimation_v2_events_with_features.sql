-- Migration: Rebuild token_estimation_v2_events with Phase 3 feature columns
-- Created: 2025-12-26
--
-- Problem:
--   Root migrations rebuild token_estimation_v2_events without Phase 3 feature columns
--   (is_truncated_output, DOC_SYNTHESIS features, SOT tracking). This causes DB telemetry
--   inserts to fail at runtime and breaks validation scripts.
--
-- Fix:
--   SQLite-safe table rebuild (similar to prior rebuild migrations), adding the missing columns.
--   Data is copied forward with sensible defaults (FALSE/NULL) for new columns.

PRAGMA foreign_keys = OFF;

-- Drop dependent views
DROP VIEW IF EXISTS v_token_estimation_validation;
DROP VIEW IF EXISTS v_recent_token_estimations;

ALTER TABLE token_estimation_v2_events RENAME TO token_estimation_v2_events_old;

CREATE TABLE token_estimation_v2_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Estimation inputs
    category TEXT NOT NULL,
    complexity TEXT NOT NULL CHECK(complexity IN ('low', 'medium', 'high', 'maintenance')),
    deliverable_count INTEGER NOT NULL,
    deliverables_json TEXT NOT NULL,

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
    smape_percent REAL,
    waste_ratio REAL,
    underestimated BOOLEAN,

    -- BUILD-129 Phase 3: truncation-awareness + DOC_SYNTHESIS features
    is_truncated_output BOOLEAN NOT NULL DEFAULT 0,
    api_reference_required BOOLEAN,
    examples_required BOOLEAN,
    research_required BOOLEAN,
    usage_guide_required BOOLEAN,
    context_quality TEXT,

    -- BUILD-129 Phase 3 P3: SOT tracking
    is_sot_file BOOLEAN NOT NULL DEFAULT 0,
    sot_file_name TEXT,
    sot_entry_count_hint INTEGER,

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
CREATE INDEX IF NOT EXISTS idx_telemetry_truncated ON token_estimation_v2_events (is_truncated_output, category);

-- Copy forward (new columns default to FALSE/NULL)
INSERT INTO token_estimation_v2_events (
    event_id, run_id, phase_id, timestamp,
    category, complexity, deliverable_count, deliverables_json,
    predicted_output_tokens, actual_output_tokens, selected_budget,
    success, truncated, stop_reason, model,
    smape_percent, waste_ratio, underestimated,
    is_truncated_output, api_reference_required, examples_required, research_required, usage_guide_required, context_quality,
    is_sot_file, sot_file_name, sot_entry_count_hint,
    created_at
)
SELECT
    event_id, run_id, phase_id, timestamp,
    category, complexity, deliverable_count, deliverables_json,
    predicted_output_tokens, actual_output_tokens, selected_budget,
    success, truncated, stop_reason, model,
    smape_percent, waste_ratio, underestimated,
    0, NULL, NULL, NULL, NULL, NULL,
    0, NULL, NULL,
    created_at
FROM token_estimation_v2_events_old;

DROP TABLE token_estimation_v2_events_old;

-- Recreate views (same shape as prior migrations)
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
    smape_percent,
    waste_ratio,
    underestimated
FROM token_estimation_v2_events
ORDER BY timestamp DESC
LIMIT 200;

PRAGMA foreign_keys = ON;
