-- Migration: Add tidy_project_config table for centralized multi-project tidy system
-- Date: 2025-12-13

CREATE TABLE IF NOT EXISTS tidy_project_config (
    id SERIAL PRIMARY KEY,
    project_id TEXT UNIQUE NOT NULL,           -- "autopack", "file-organizer-app-v1"
    project_root TEXT NOT NULL,                -- Path to project (relative to Autopack root)
    docs_dir TEXT DEFAULT 'docs',              -- Relative to project_root
    archive_dir TEXT DEFAULT 'archive',        -- Relative to project_root

    -- SOT file names (allow customization per project)
    sot_build_history TEXT DEFAULT 'BUILD_HISTORY.md',
    sot_debug_log TEXT DEFAULT 'DEBUG_LOG.md',
    sot_architecture TEXT DEFAULT 'ARCHITECTURE_DECISIONS.md',
    sot_unsorted TEXT DEFAULT 'UNSORTED_REVIEW.md',

    -- Project-specific context for AI classification
    project_context JSONB,                     -- Keywords, patterns, priorities

    -- Feature flags
    enable_database_logging BOOLEAN DEFAULT true,
    enable_research_workflow BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert config for Autopack (main project)
INSERT INTO tidy_project_config (
    project_id,
    project_root,
    docs_dir,
    archive_dir,
    project_context
) VALUES (
    'autopack',
    '.',
    'docs',
    'archive',
    '{
        "keywords": {
            "build": [
                "autonomous executor", "phase", "builder result", "llm client",
                "implementation", "build", "complete", "feature", "autonomous tidy"
            ],
            "debug": [
                "error", "bug", "fix", "500 error", "database migration",
                "troubleshoot", "failed", "exception"
            ],
            "architecture": [
                "design decision", "schema", "routing", "classification",
                "architecture", "comparison", "research", "analysis"
            ]
        },
        "priorities": {
            "autonomous_execution": "high",
            "llm_integration": "high",
            "file_organization": "medium",
            "tidy_system": "high"
        },
        "exclude_patterns": [
            ".autonomous_runs/*",
            "*.pyc",
            "__pycache__",
            "venv/*",
            ".git/*"
        ]
    }'::jsonb
) ON CONFLICT (project_id) DO UPDATE SET
    project_context = EXCLUDED.project_context,
    updated_at = NOW();

-- Insert config for File Organizer App
INSERT INTO tidy_project_config (
    project_id,
    project_root,
    docs_dir,
    archive_dir,
    project_context
) VALUES (
    'file-organizer-app-v1',
    '.autonomous_runs/file-organizer-app-v1',
    'docs',
    'archive',
    '{
        "keywords": {
            "build": [
                "visa pack", "country pack", "document classification",
                "batch upload", "pack generation", "classification system",
                "visa type", "document routing", "pack management",
                "implementation", "feature", "complete"
            ],
            "debug": [
                "processing error", "classification failed", "upload failed",
                "pack generation error", "document processing", "validation error",
                "error", "bug", "fix", "failed"
            ],
            "architecture": [
                "pack structure", "visa type design", "document routing",
                "classification architecture", "batch processing design",
                "storage strategy", "pack organization", "decision", "design"
            ]
        },
        "priorities": {
            "document_classification": "high",
            "pack_management": "high",
            "visa_compliance": "critical",
            "batch_processing": "medium"
        },
        "exclude_patterns": [
            "packs/*",
            "*.db",
            "*.sqlite",
            "__pycache__",
            "*.pyc",
            ".autonomous_runs/*"
        ]
    }'::jsonb
) ON CONFLICT (project_id) DO UPDATE SET
    project_context = EXCLUDED.project_context,
    updated_at = NOW();
