-- Migration: Add token_budget_escalation_events table (P10 observability)
-- Created: 2025-12-26
--
-- Purpose:
--   Provide deterministic, DB-backed validation for BUILD-129 Phase 3 P10 escalate-once.
--   TokenEstimationV2Event rows are written inside anthropic_clients.py (during the builder call),
--   but P10 decisions are made later in autonomous_executor.py. This table records the P10 decision
--   at the moment it is made (base/source/retry tokens) without requiring post-hoc updates.
--
-- SQLite-safe: CREATE TABLE IF NOT EXISTS + indexes.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS token_budget_escalation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL,
    reason TEXT NOT NULL,                 -- "truncation" or "utilization"
    was_truncated BOOLEAN NOT NULL DEFAULT 0,
    output_utilization REAL,              -- percent (0-100)

    escalation_factor REAL NOT NULL,      -- e.g. 1.25
    base_value INTEGER NOT NULL,          -- max(selected_budget, actual_max_tokens, tokens_used)
    base_source TEXT NOT NULL,            -- selected_budget|actual_max_tokens|tokens_used|complexity_default
    retry_max_tokens INTEGER NOT NULL,    -- min(base_value*factor, 64000)

    selected_budget INTEGER,              -- candidate
    actual_max_tokens INTEGER,            -- candidate
    tokens_used INTEGER,                  -- candidate (actual output tokens)

    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id, phase_id) REFERENCES phases(run_id, phase_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_token_budget_escalation_run_id ON token_budget_escalation_events(run_id);
CREATE INDEX IF NOT EXISTS ix_token_budget_escalation_phase_id ON token_budget_escalation_events(phase_id);
CREATE INDEX IF NOT EXISTS ix_token_budget_escalation_timestamp ON token_budget_escalation_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_token_budget_escalation_base_source ON token_budget_escalation_events(base_source);
CREATE INDEX IF NOT EXISTS ix_token_budget_escalation_reason ON token_budget_escalation_events(reason);
