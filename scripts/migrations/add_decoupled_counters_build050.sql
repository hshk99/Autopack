-- BUILD-050 Phase 2: Add decoupled attempt counters to Phase model
-- Migration to add retry_attempt, revision_epoch, and escalation_level columns
--
-- This migration supports non-destructive replanning by separating:
-- 1. retry_attempt: Monotonic retry counter for hints accumulation
-- 2. revision_epoch: Replan counter (increments when Doctor revises approach)
-- 3. escalation_level: Model selection state (0=base, 1=escalated, etc.)
--
-- Run this migration BEFORE starting executor with BUILD-050 changes.

-- Add new columns with default values
ALTER TABLE phases ADD COLUMN retry_attempt INTEGER NOT NULL DEFAULT 0;
ALTER TABLE phases ADD COLUMN revision_epoch INTEGER NOT NULL DEFAULT 0;
ALTER TABLE phases ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0;

-- Migrate existing data: copy attempts_used to retry_attempt
-- (attempts_used becomes deprecated in favor of retry_attempt)
UPDATE phases SET retry_attempt = attempts_used WHERE retry_attempt = 0;

-- Add comment to track migration
-- Note: SQLite doesn't support COMMENT ON COLUMN, so we document here
-- Column descriptions:
--   retry_attempt: Monotonic retry counter (never resets, even on replan)
--   revision_epoch: Increments each time Doctor triggers replanning
--   escalation_level: Model escalation state (0=base model, 1=escalated, etc.)
