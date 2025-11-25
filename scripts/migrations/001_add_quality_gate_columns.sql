-- Migration: Add quality gate columns to phases table
-- Phase 2: Thin quality gate for high-risk categories
-- Date: 2025-11-26

-- Add quality gate columns to phases table
ALTER TABLE phases ADD COLUMN IF NOT EXISTS quality_level VARCHAR(20);
ALTER TABLE phases ADD COLUMN IF NOT EXISTS quality_blocked BOOLEAN NOT NULL DEFAULT FALSE;

-- Create index for quality-blocked phases (for dashboard queries)
CREATE INDEX IF NOT EXISTS idx_phases_quality_blocked ON phases(quality_blocked) WHERE quality_blocked = TRUE;

-- Comments for documentation
COMMENT ON COLUMN phases.quality_level IS 'Quality gate assessment: ok, needs_review, or blocked';
COMMENT ON COLUMN phases.quality_blocked IS 'Whether phase is blocked by quality gate';
