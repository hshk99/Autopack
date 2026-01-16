-- Migration: Add policy promotions table
-- Purpose: Track automated promotion of A-B tested improvements to production (IMP-ARCH-006)
-- Created: 2026-01-16
--
-- This table stores records of validated improvements promoted to production configuration
-- with rollback protection and monitoring capabilities.

-- Table: policy_promotions
-- Stores promotion records for validated improvements
CREATE TABLE IF NOT EXISTS policy_promotions (
    id SERIAL PRIMARY KEY,
    promotion_id VARCHAR(128) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Source tracking
    ab_test_result_id INTEGER NOT NULL REFERENCES ab_test_results(id),
    improvement_task_id VARCHAR(128) NOT NULL,

    -- Configuration changes
    config_changes JSONB NOT NULL,               -- {"key": {"old": val1, "new": val2}}
    promoted_version VARCHAR(128) NOT NULL,
    previous_version VARCHAR(128) NOT NULL,

    -- Promotion lifecycle
    promoted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    monitoring_until TIMESTAMPTZ,                 -- 24hr monitoring window

    -- Rollback protection
    rollback_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    rollback_reason TEXT,
    rollback_at TIMESTAMPTZ,

    -- Post-promotion metrics
    post_promotion_metrics JSONB,                 -- Metrics tracked during monitoring period
    degradation_detected BOOLEAN NOT NULL DEFAULT FALSE,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active'  -- 'active', 'stable', 'rolled_back'
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_policy_promotions_promotion_id
    ON policy_promotions(promotion_id);

CREATE INDEX IF NOT EXISTS idx_policy_promotions_created_at
    ON policy_promotions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_policy_promotions_ab_test_result
    ON policy_promotions(ab_test_result_id);

CREATE INDEX IF NOT EXISTS idx_policy_promotions_improvement_task
    ON policy_promotions(improvement_task_id);

CREATE INDEX IF NOT EXISTS idx_policy_promotions_rollback
    ON policy_promotions(rollback_triggered) WHERE rollback_triggered = TRUE;

CREATE INDEX IF NOT EXISTS idx_policy_promotions_status
    ON policy_promotions(status);

CREATE INDEX IF NOT EXISTS idx_policy_promotions_active
    ON policy_promotions(status, monitoring_until) WHERE status = 'active';

-- Comments
COMMENT ON TABLE policy_promotions IS 'Tracks automated promotion of validated improvements with rollback protection (IMP-ARCH-006)';
COMMENT ON COLUMN policy_promotions.ab_test_result_id IS 'Reference to validated A-B test result';
COMMENT ON COLUMN policy_promotions.config_changes IS 'Configuration changes applied: {"key": {"old": previous_value, "new": new_value}}';
COMMENT ON COLUMN policy_promotions.monitoring_until IS 'End of 24hr monitoring period for auto-rollback';
COMMENT ON COLUMN policy_promotions.rollback_triggered IS 'Whether automatic rollback was triggered due to degradation';
COMMENT ON COLUMN policy_promotions.post_promotion_metrics IS 'Metrics collected during monitoring period for degradation detection';
COMMENT ON COLUMN policy_promotions.status IS 'Promotion status: active (monitoring), stable (monitoring passed), rolled_back (degradation detected)';
