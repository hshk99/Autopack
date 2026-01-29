# Project Isolation Architecture

## Overview

This document defines the separation between:
1. **Autopack Tool** - The automation framework itself
2. **Bootstrapped Projects** - Projects created/researched by Autopack

## Directory Structure

```
C:\dev\
├── Autopack\                           # The tool (this repo)
│   ├── src\                            # Tool source code
│   ├── tests\                          # Tool tests
│   ├── .claude\
│   │   ├── agents\                     # Agent definitions (part of tool)
│   │   ├── skills\                     # Skills (part of tool)
│   │   └── scripts\                    # Helper scripts (part of tool)
│   └── .autonomous_runs\               # Tool's own run artifacts
│       └── builds\                     # Autopack self-improvement runs
│
└── AutopackProjects\                   # All bootstrapped projects (SEPARATE REPO)
    ├── .autopack-registry.yaml         # Registry of all projects
    └── {project-name}\                 # Each project is isolated
        ├── .autopack\                  # Project-specific Autopack data
        │   ├── research\
        │   │   ├── discovery\
        │   │   ├── findings\
        │   │   ├── frameworks\
        │   │   └── validation\
        │   ├── synthesis\
        │   ├── builds\                 # Project build history
        │   └── runs\                   # Project run artifacts
        ├── src\                        # Project source (built by Autopack)
        ├── tests\                      # Project tests
        ├── intention_anchor.yaml       # Project's intention anchor
        ├── READY_FOR_AUTOPACK          # Handoff marker
        └── .gitignore                  # Project-specific ignores
```

## Why This Separation?

### 1. CI Isolation
- Autopack CI only runs on `C:\dev\Autopack\`
- Project CI runs independently per project
- No cross-contamination of test results

### 2. Lint Isolation
- Autopack linters only check tool code
- Each project can have its own lint rules
- Research artifacts (JSON/MD) don't trigger tool linting

### 3. Parallel Execution
- Multiple projects can run simultaneously
- Each project has isolated `.autopack\runs\` directory
- No path collisions between projects

### 4. Git Isolation
- Autopack changes don't appear in project commits
- Project changes don't appear in tool commits
- Clean separation of concerns

## Project Registry

The registry tracks all bootstrapped projects:

```yaml
# C:\dev\AutopackProjects\.autopack-registry.yaml
version: "1.0"
projects:
  - name: etsy-listing-automator
    path: etsy-listing-automator
    status: active
    created: 2024-01-15
    last_build: 2024-01-20

  - name: youtube-shorts-generator
    path: youtube-shorts-generator
    status: research_complete
    created: 2024-01-18
    last_build: null

  - name: trading-signal-bot
    path: trading-signal-bot
    status: paused
    created: 2024-01-10
    paused_reason: "Awaiting regulatory clarity"
```

## Configuration

### Environment Variable
```bash
# Set in system environment or .env
AUTOPACK_PROJECTS_ROOT=C:\dev\AutopackProjects
```

### Autopack Config
```yaml
# C:\dev\Autopack\config\autopack.yaml
projects:
  root: ${AUTOPACK_PROJECTS_ROOT}
  default_template: standard
  isolation:
    git_separate: true
    ci_separate: true
```

## Workflow

### 1. Bootstrap New Project
```bash
# From Autopack directory
autopack bootstrap --idea "Etsy automation tool" --output $AUTOPACK_PROJECTS_ROOT/etsy-tool

# Or using Claude Code skill
/project-bootstrap "Etsy automation tool" --output C:\dev\AutopackProjects\etsy-tool
```

### 2. Research Phase
Research agents write to:
```
C:\dev\AutopackProjects\etsy-tool\.autopack\research\
```

### 3. Build Phase
Autopack builds project in:
```
C:\dev\AutopackProjects\etsy-tool\src\
```

### 4. CI/CD
Each project can have its own:
- `.github\workflows\` (GitHub Actions)
- `azure-pipelines.yml` (Azure DevOps)
- Independent test runs

## Migration from Current Structure

If projects currently exist in Autopack's `.claude\` directory:

1. Create `C:\dev\AutopackProjects\` directory
2. Move project research outputs to new location
3. Update project-bootstrap skill to use new paths
4. Update intention_anchor paths
5. Clean up `.claude\` to only contain agent definitions

## Benefits Summary

| Concern | Before (Mixed) | After (Isolated) |
|---------|---------------|------------------|
| Lint failures | Risk of cross-contamination | Fully isolated |
| CI conflicts | Tool + project changes mixed | Independent pipelines |
| Parallel builds | Path collisions | Safe parallel execution |
| Git history | Noisy mixed commits | Clean separation |
| Disk space | Single repo grows unbounded | Projects can be archived |
