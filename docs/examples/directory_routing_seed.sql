-- Example Seed Data: Directory Routing Configuration
-- Purpose: Provide example seed data for the directory_routing tables
-- Usage: Load after running the schema migration (add_directory_routing_config.sql)
--
-- IMPORTANT: This file uses RELATIVE paths only. Absolute paths should be
-- avoided in committed seed data to ensure portability across machines.
--
-- Path variables supported in destination_path:
--   {project}  - Project identifier
--   {family}   - Run family grouping (e.g., "fileorg-country-uk")
--   {run_id}   - Unique run identifier
--   {date}     - Current date (YYYY-MM-DD format)
--
-- For workstation-specific paths, configure at runtime via environment
-- variables or a local configuration file (not committed to git).

-- =============================================================================
-- Project Directory Configuration (using relative paths)
-- =============================================================================

-- Autopack project configuration (repo root)
INSERT INTO project_directory_config (project_id, base_path, runs_path, archive_path, docs_path, uses_family_grouping)
VALUES (
    'autopack',
    '.',                    -- Repo root (relative)
    'archive/logs',         -- Autopack runs are rare, treated as logs
    'archive',
    'docs',
    FALSE                   -- Autopack doesn't use family grouping
) ON CONFLICT (project_id) DO NOTHING;

-- File Organizer project configuration (under .autonomous_runs/)
INSERT INTO project_directory_config (project_id, base_path, runs_path, archive_path, docs_path, uses_family_grouping)
VALUES (
    'file-organizer-app-v1',
    '.autonomous_runs/file-organizer-app-v1',
    '.autonomous_runs/file-organizer-app-v1/runs',
    '.autonomous_runs/file-organizer-app-v1/archive',
    '.autonomous_runs/file-organizer-app-v1/docs',
    TRUE                    -- File Organizer uses family grouping
) ON CONFLICT (project_id) DO NOTHING;

-- =============================================================================
-- Routing Rules for Autopack (Cursor-created files)
-- =============================================================================

INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, content_keywords)
VALUES
    ('autopack', 'plan', 'cursor', 'archive/plans', 10, ARRAY['plan', 'implementation', 'design', 'roadmap']),
    ('autopack', 'analysis', 'cursor', 'archive/analysis', 10, ARRAY['analysis', 'review', 'retrospective', 'findings']),
    ('autopack', 'prompt', 'cursor', 'archive/prompts', 10, ARRAY['prompt', 'delegation', 'instruction']),
    ('autopack', 'log', 'cursor', 'archive/diagnostics/logs', 10, ARRAY['log', 'diagnostic', 'trace', 'debug']),
    ('autopack', 'script', 'cursor', 'archive/scripts', 10, ARRAY['script', 'utility', 'tool', 'runner']),
    ('autopack', 'unknown', 'cursor', 'archive/unsorted', 0, NULL)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;

-- =============================================================================
-- Routing Rules for File Organizer (Cursor-created files)
-- =============================================================================

INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, content_keywords)
VALUES
    ('file-organizer-app-v1', 'plan', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/plans', 10, ARRAY['plan', 'implementation', 'design']),
    ('file-organizer-app-v1', 'analysis', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/analysis', 10, ARRAY['analysis', 'review', 'postmortem']),
    ('file-organizer-app-v1', 'report', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/reports', 10, ARRAY['report', 'summary', 'consolidated']),
    ('file-organizer-app-v1', 'prompt', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/prompts', 10, ARRAY['prompt', 'delegation']),
    ('file-organizer-app-v1', 'diagnostic', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/diagnostics', 10, ARRAY['diagnostic', 'trace', 'debug']),
    ('file-organizer-app-v1', 'unknown', 'cursor', '.autonomous_runs/file-organizer-app-v1/archive/unsorted', 0, NULL)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;

-- =============================================================================
-- Routing Rules for Autopack-created Runs
-- =============================================================================

INSERT INTO directory_routing_rules (project_id, file_type, source_context, destination_path, priority, is_archived)
VALUES
    ('autopack', 'run', 'autopack', 'archive/logs/{run_id}', 10, FALSE),
    ('file-organizer-app-v1', 'run', 'autopack', '.autonomous_runs/file-organizer-app-v1/runs/{family}/{run_id}', 10, FALSE),
    ('file-organizer-app-v1', 'run', 'autopack', '.autonomous_runs/file-organizer-app-v1/archive/superseded/runs/{family}/{run_id}', 10, TRUE)
ON CONFLICT (project_id, file_type, source_context, is_archived) DO NOTHING;
