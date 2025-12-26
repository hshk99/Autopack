-- Migration: Fix v_truncation_analysis view to match current phases schema
-- Created: 2025-12-26
--
-- Problem:
--   Some SQLite DBs contain v_truncation_analysis defined as:
--     SELECT ..., p.phase_name, ... FROM truncation_events te LEFT JOIN phases p ...
--   but phases table uses column `name` (not `phase_name`).
--   This breaks schema operations that touch sqlite_master and can block other migrations.
--
-- Fix:
--   Drop and recreate v_truncation_analysis using p.name AS phase_name.

DROP VIEW IF EXISTS v_truncation_analysis;

CREATE VIEW IF NOT EXISTS v_truncation_analysis AS
SELECT
    te.phase_id,
    p.name AS phase_name,
    te.truncation_type,
    te.severity,
    COUNT(*) as event_count,
    ROUND(AVG(te.estimated_loss_pct), 2) as avg_loss_pct,
    ROUND(AVG(te.tokens_used), 2) as avg_tokens_used,
    SUM(CASE WHEN te.recovery_successful = 1 THEN 1 ELSE 0 END) as successful_recoveries,
    ROUND(SUM(CASE WHEN te.recovery_successful = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as recovery_rate_pct
FROM truncation_events te
LEFT JOIN phases p ON te.phase_id = p.phase_id
GROUP BY te.phase_id, p.name, te.truncation_type, te.severity
ORDER BY event_count DESC;


