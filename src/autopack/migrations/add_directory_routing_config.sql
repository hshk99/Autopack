-- Migration: Add directory routing configuration tables
-- Purpose: Store project-specific directory routing rules for files created by Cursor and Autopack
-- Created: 2025-12-11
-- Updated: 2026-01-07 (BUILD-188: Removed hardcoded workstation paths from schema migration)
--
-- NOTE: This migration creates schema only. Seed data should be loaded separately
-- at runtime from configuration or via a dedicated seed script. See:
-- - docs/examples/directory_routing_seed.sql for example seed data
-- - src/autopack/config.py for runtime path resolution

-- Table: directory_routing_rules
-- Stores routing rules for different file types and projects
CREATE TABLE IF NOT EXISTS directory_routing_rules (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,                  -- Project identifier (e.g., 'autopack', 'file-organizer-app-v1')
    file_type TEXT NOT NULL,                   -- File type category (e.g., 'plan', 'analysis', 'log', 'run', 'diagnostic')
    source_context TEXT NOT NULL,              -- Source of file creation ('cursor', 'autopack', 'manual')
    destination_path TEXT NOT NULL,            -- Destination path pattern (supports variables like {project}, {family}, {run_id})
    is_archived BOOLEAN DEFAULT FALSE,         -- Whether this rule is for archived files
    priority INTEGER DEFAULT 0,                -- Priority for rule matching (higher = higher priority)
    pattern_match TEXT,                        -- Optional regex pattern for filename matching
    content_keywords TEXT[],                   -- Optional keywords for content-based classification
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(project_id, file_type, source_context, is_archived)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_directory_routing_project_type
    ON directory_routing_rules(project_id, file_type);

CREATE INDEX IF NOT EXISTS idx_directory_routing_source
    ON directory_routing_rules(source_context);

-- Table: project_directory_config
-- Stores base directory configuration for each project
CREATE TABLE IF NOT EXISTS project_directory_config (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,           -- Project identifier
    base_path TEXT NOT NULL,                   -- Base path for project (relative paths recommended, e.g., '.')
    runs_path TEXT NOT NULL,                   -- Path for active runs (relative to base_path)
    archive_path TEXT NOT NULL,                -- Path for archived files (relative to base_path)
    docs_path TEXT NOT NULL,                   -- Path for truth source documents (relative to base_path)
    uses_family_grouping BOOLEAN DEFAULT TRUE, -- Whether to group runs by family
    auto_archive_days INTEGER DEFAULT 30,      -- Auto-archive runs older than N days
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Comments
COMMENT ON TABLE directory_routing_rules IS 'Routing rules for file organization by project, type, and source';
COMMENT ON TABLE project_directory_config IS 'Base directory configuration for each project';
COMMENT ON COLUMN directory_routing_rules.destination_path IS 'Path pattern supports variables: {project}, {family}, {run_id}, {date}. Use relative paths.';
COMMENT ON COLUMN directory_routing_rules.content_keywords IS 'Keywords for content-based classification (used by tidy_workspace.py)';
COMMENT ON COLUMN project_directory_config.uses_family_grouping IS 'Whether to group runs by family prefix (e.g., fileorg-country-uk)';
COMMENT ON COLUMN project_directory_config.base_path IS 'Use relative paths (e.g., ".") or env-var references. Avoid absolute workstation paths.';
