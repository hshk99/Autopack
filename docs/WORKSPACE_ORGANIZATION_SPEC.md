# Workspace Organization Specification

**Version:** 1.0
**Date:** 2025-12-11
**Status:** Active

This document defines the canonical organizational structure for the Autopack workspace.

---

## Root Directory Structure

```
C:\dev\Autopack\
├── README.md                                    # Project overview
├── WORKSPACE_ORGANIZATION_SPEC.md               # This file
├── WHATS_LEFT_TO_BUILD.md                       # Current project roadmap
├── WHATS_LEFT_TO_BUILD_MAINTENANCE.md           # Maintenance tasks
├── src/                                         # Application source code
├── scripts/                                     # Utility scripts
├── tests/                                       # Test files
├── docs/                                        # Current documentation
├── config/                                      # Configuration files
├── archive/                                     # Historical files
└── .autonomous_runs/                            # Project-specific autonomous runs
```

---

## Archive Structure

All historical files are organized in `archive/` with standardized buckets:

```
archive/
├── plans/              # Implementation plans, roadmaps
├── reports/            # Build reports, delegation results, assessments
├── analysis/           # Analysis documents, reviews, progress reports
├── research/           # Market research, feature research
├── prompts/            # AI prompts, templates
├── diagnostics/        # Historical diagnostic data
│   ├── logs/          # Log files
│   └── runs/          # Run outputs
├── unsorted/          # Temporary holding area
├── configs/           # Historical config files
├── docs/              # Superseded documentation
├── exports/           # Historical exports
├── patches/           # Code patches
├── refs/              # Reference materials
└── src/               # Historical source code
```

**Rules:**
- NO nested archive folders (e.g., archive/archive/)
- NO loose files at archive root
- Diagnostics layer contains logs/ and runs/ subdirectories

---

## .autonomous_runs Structure

Project-specific autonomous execution folders only:

```
.autonomous_runs/
├── Autopack/                    # Autopack-specific runs
├── file-organizer-app-v1/       # FileOrganizer project runs
├── checkpoints/                 # Active checkpoints
├── *.json                       # Run configuration files
└── tidy_semantic_cache.json     # Tidy system cache
```

**Rules:**
- NO loose folders (archive/, docs/, exports/, patches/, runs/)
- Each project folder follows same structure as root (src/, docs/, archive/, etc.)
- All project-specific files go under their project folder

---

## Truth Sources vs Archive

**Truth Sources** (current, active files at root):
- README.md
- WORKSPACE_ORGANIZATION_SPEC.md
- WHATS_LEFT_TO_BUILD.md
- WHATS_LEFT_TO_BUILD_MAINTENANCE.md
- Current cleanup documentation (PROPOSED_CLEANUP_STRUCTURE.md, etc.)

**Archive** (historical, superseded files):
- Old versions of truth sources
- Completed plans
- Historical reports
- Superseded documentation

---

## File Classification Rules

### .md Files:
- **Plans**: Contains "plan", "implementation", "roadmap" → `archive/plans/`
- **Reports**: Contains "guide", "checklist", "complete", "verified" → `archive/reports/`
- **Analysis**: Contains "analysis", "review", "progress" → `archive/analysis/`
- **Research**: Contains "research", "market" → `archive/research/`
- **Prompts**: Contains "prompt", "template" → `archive/prompts/`
- **Default**: If unclear → `archive/reports/`

### .log Files:
- All → `archive/diagnostics/logs/`

### Run Outputs:
- All → `archive/diagnostics/runs/` (or project-specific `diagnostics/runs/`)

---

## Validation Checklist

A properly organized workspace has:

- [x] No loose .md files at root (except truth sources)
- [x] No loose .log files at root
- [x] No prompts/ folder at root
- [x] All archive buckets exist
- [x] No nested folders in archive/diagnostics/
- [x] No loose folders at .autonomous_runs root
- [x] WORKSPACE_ORGANIZATION_SPEC.md exists at root
- [x] WHATS_LEFT_TO_BUILD*.md files at root
- [x] All project folders under .autonomous_runs/ follow standard structure

---

## Maintenance

When adding new files:
1. Determine if it's a truth source (current/active) or historical
2. If truth source → keep at root or appropriate top-level folder
3. If historical → classify and move to appropriate archive bucket
4. If project-specific → move to `.autonomous_runs/[project]/`

When creating autonomous runs:
1. Create project folder under `.autonomous_runs/`
2. Follow standard structure (src/, docs/, archive/, etc.)
3. Keep all project files contained within project folder

---

**Generated:** 2025-12-11
**Last Updated:** 2025-12-11
