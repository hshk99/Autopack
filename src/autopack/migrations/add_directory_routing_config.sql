-- Migration: Add directory routing configuration table
-- Purpose: Store project-specific directory routing rules for files created by Cursor and Autopack
-- Created: 2025-12-11

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
    base_path TEXT NOT NULL,                   -- Base path for project (e.g., '.autonomous_runs/file-organizer-app-v1')
    runs_path TEXT NOT NULL,                   -- Path for active runs
    archive_path TEXT NOT NULL,                -- Path for archived files
    docs_path TEXT NOT NULL,                   -- Path for truth source documents
    uses_family_grouping BOOLEAN DEFAULT TRUE, -- Whether to group runs by family
    auto_archive_days INTEGER DEFAULT 30,      -- Auto-archive runs older than N days
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed data for Autopack project
INSERT INTO project_directory_config (project_id, base_path, runs_path, archive_path, docs_path, uses_family_grouping)
VALUES (
    'autopack',
    'C:\dev\Autopack',
    'C:\dev\Autopack\archive\logs',  -- Autopack runs are rare, treated as logs
    'C:\dev\Autopack\archive',
    'C:\dev\Autopack\docs',
    FALSE  -- Autopack doesn't use family grouping
) ON CONFLICT (project_id) DO NOTHING;

-- Seed data for File Organizer project
INSERT INTO project_directory_config (project_id, base_path, runs_path, archive_path, docs_path, uses_family_grouping)
VALUES (
    'file-organizer-app-v1',
    '.autonomous_runs/file-organizer-app-v1',
    '.autonomous_runs/file-organizer-app-v1/runs',
    '.autonomous_runs/file-organizer-app-v1/archive',
    '.autonomous_runs/file-organizer-app-v1/docs',
    TRUE  -- File Organizer uses family grouping
) ON CONFLICT (project_id) DO NOTHING;

-- Seed routing rules for Autopack project (Cursor-created files)
INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, content_keywords)
VALUES
    ('autopack', 'plan', 'cursor', 'C:\dev\Autopack\archive\plans', 10, ARRAY['plan', 'implementation', 'design', 'roadmap']),
    ('autopack', 'analysis', 'cursor', 'C:\dev\Autopack\archive\analysis', 10, ARRAY['analysis', 'review', 'retrospective', 'findings']),
    ('autopack', 'prompt', 'cursor', 'C:\dev\Autopack\archive\prompts', 10, ARRAY['prompt', 'delegation', 'instruction']),
    ('autopack', 'log', 'cursor', 'C:\dev\Autopack\archive\logs', 10, ARRAY['log', 'diagnostic', 'trace', 'debug']),
    ('autopack', 'script', 'cursor', 'C:\dev\Autopack\archive\scripts', 10, ARRAY['script', 'utility', 'tool', 'runner']),
    ('autopack', 'unknown', 'cursor', 'C:\dev\Autopack\archive\unsorted', 0, NULL)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;

-- Seed routing rules for File Organizer project (Cursor-created files)
INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, content_keywords)
VALUES
    ('file-organizer-app-v1', 'plan', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/plans', 10, ARRAY['plan', 'implementation', 'design']),
    ('file-organizer-app-v1', 'analysis', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/analysis', 10, ARRAY['analysis', 'review', 'postmortem']),
    ('file-organizer-app-v1', 'report', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/reports', 10, ARRAY['report', 'summary', 'consolidated']),
    ('file-organizer-app-v1', 'prompt', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/prompts', 10, ARRAY['prompt', 'delegation']),
    ('file-organizer-app-v1', 'diagnostic', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/diagnostics', 10, ARRAY['diagnostic', 'trace', 'debug']),
    ('file-organizer-app-v1', 'unknown', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/unsorted', 0, NULL)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;

-- Seed routing rules for Autopack-created runs
INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, is_archived)
VALUES
    ('autopack', 'run', 'autopack', 'C:\dev\Autopack\archive\logs\{run_id}', 10, FALSE),
    ('file-organizer-app-v1', 'run', 'autopack', '.autonomous_runs/file-organizer-app-v1/runs/{family}/{run_id}', 10, FALSE),
    ('file-organizer-app-v1', 'run', 'autopack', '.autonomous_runs/file-organizer-app-v1/archive/superseded/runs/{family}/{run_id}', 10, TRUE)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;

-- Comments
COMMENT ON TABLE directory_routing_rules IS 'Routing rules for file organization by project, type, and source';
COMMENT ON TABLE project_directory_config IS 'Base directory configuration for each project';
COMMENT ON COLUMN directory_routing_rules.destination_path IS 'Path pattern supports variables: {project}, {family}, {run_id}, {date}';
COMMENT ON COLUMN directory_routing_rules.content_keywords IS 'Keywords for content-based classification (used by tidy_workspace.py)';
COMMENT ON COLUMN project_directory_config.uses_family_grouping IS 'Whether to group runs by family prefix (e.g., fileorg-country-uk)';
