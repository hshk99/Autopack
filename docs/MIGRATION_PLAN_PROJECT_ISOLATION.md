# Migration Plan: Project Isolation

## Overview

This plan migrates Autopack from storing bootstrapped projects in `.autonomous_runs/` (inside the Autopack repo) to a dedicated `C:\dev\AutopackProjects\` directory (outside the repo).

**Reference:** [PROJECT_ISOLATION_ARCHITECTURE.md](./PROJECT_ISOLATION_ARCHITECTURE.md)

## Why This Migration?

| Problem | Impact | Solution |
|---------|--------|----------|
| Lint failures on project code | CI red when working on unrelated Autopack changes | Projects outside lint scope |
| CI conflicts | Project tests run with Autopack tests | Separate CI pipelines |
| Path collisions | Parallel builds overwrite each other | Isolated project directories |
| Git noise | Project commits mixed with tool commits | Separate repos |

## Migration Steps

### Phase 1: Environment Setup

#### 1.1 Create Projects Root Directory

```powershell
# PowerShell (Windows)
New-Item -ItemType Directory -Path "C:\dev\AutopackProjects" -Force
```

```bash
# Bash (Linux/Mac)
mkdir -p ~/dev/AutopackProjects
```

#### 1.2 Set Environment Variable

**Windows (System-wide):**
```powershell
[System.Environment]::SetEnvironmentVariable("AUTOPACK_PROJECTS_ROOT", "C:\dev\AutopackProjects", "User")
```

**Windows (Current session):**
```powershell
$env:AUTOPACK_PROJECTS_ROOT = "C:\dev\AutopackProjects"
```

**Linux/Mac (.bashrc or .zshrc):**
```bash
export AUTOPACK_PROJECTS_ROOT=~/dev/AutopackProjects
```

**Docker (.env file):**
```env
AUTOPACK_PROJECTS_ROOT=/workspace/projects
```

#### 1.3 Verify Configuration

```python
# Python verification
from autopack.config import settings, get_projects_root

print(f"Projects root: {settings.autopack_projects_root}")
print(f"Resolved path: {get_projects_root()}")
```

### Phase 2: Migrate Existing Projects

#### 2.1 Identify Existing Projects

```powershell
# List projects in old location
Get-ChildItem -Directory "C:\dev\Autopack\.autonomous_runs"
```

Current projects to migrate:
- `file-organizer-app-v1`

#### 2.2 Move Projects

```powershell
# PowerShell migration script
$oldRoot = "C:\dev\Autopack\.autonomous_runs"
$newRoot = "C:\dev\AutopackProjects"

# Create new root
New-Item -ItemType Directory -Path $newRoot -Force

# Move each project
$projects = @("file-organizer-app-v1")
foreach ($project in $projects) {
    $source = Join-Path $oldRoot $project
    $dest = Join-Path $newRoot $project

    if (Test-Path $source) {
        Write-Host "Moving $project..."
        Move-Item -Path $source -Destination $dest -Force
        Write-Host "  Moved to $dest"
    }
}
```

#### 2.3 Update Internal Paths

After moving, update any hardcoded paths in project files:

```powershell
# Find files with old paths
Get-ChildItem -Recurse "C:\dev\AutopackProjects" -Include *.yaml,*.json,*.md |
    Select-String -Pattern "\.autonomous_runs" |
    Select-Object -Unique Path
```

### Phase 3: Update Autopack Components

#### 3.1 Files Requiring Updates

Based on grep analysis, these files reference `autonomous_runs`:

**Core Configuration:**
- `src/autopack/config.py` ✅ (already updated)

**Executors/Runners:**
- `src/autopack/executor/autonomous_loop.py`
- `src/autopack/autonomous_executor.py`
- `src/autopack/workspace_manager.py`

**Memory/Storage:**
- `src/autopack/memory/memory_service.py`
- `src/autopack/memory/faiss_store.py`

**Tests:**
- `tests/conftest.py`
- Multiple test files (use autonomous_runs for test isolation)

**Skills/Agents:**
- `.claude/skills/project-bootstrap.md` ✅ (already updated)

#### 3.2 Update Pattern

Replace references to `autonomous_runs_dir` with `autopack_projects_root` for project-related operations:

```python
# OLD
from autopack.config import settings
project_dir = Path(settings.autonomous_runs_dir) / project_name

# NEW
from autopack.config import get_project_path
project_dir = get_project_path(project_name)
```

#### 3.3 Backward Compatibility

Keep `autonomous_runs_dir` for Autopack's own internal runs (self-improvement cycles). Only project bootstrapping should use the new path.

| Use Case | Directory |
|----------|-----------|
| Autopack self-improvement runs | `.autonomous_runs/` (internal) |
| Bootstrapped projects | `$AUTOPACK_PROJECTS_ROOT/` (external) |

### Phase 4: Update Project Bootstrap Skill

The `/project-bootstrap` skill should:

1. Read `AUTOPACK_PROJECTS_ROOT` from environment
2. Create project in isolated location
3. Set up `.autopack/` subfolder for project-specific data
4. Generate `READY_FOR_AUTOPACK` marker

**Updated output structure:**
```
C:\dev\AutopackProjects\{project-name}\
├── .autopack\
│   ├── research\
│   │   ├── discovery\
│   │   ├── findings\
│   │   ├── frameworks\
│   │   └── validation\
│   ├── synthesis\
│   ├── builds\
│   └── runs\
├── src\
├── tests\
├── intention_anchor.yaml
├── PROJECT_BRIEF.md
├── READY_FOR_AUTOPACK
└── .gitignore
```

### Phase 5: CI/CD Updates

#### 5.1 Autopack CI (unchanged scope)

```yaml
# .github/workflows/ci.yml
# Only runs on Autopack code - projects are external
paths:
  - 'src/**'
  - 'tests/**'
  - 'pyproject.toml'
```

#### 5.2 Project CI (per-project)

Each bootstrapped project can have its own CI:

```yaml
# C:\dev\AutopackProjects\{project}\\.github\workflows\ci.yml
name: Project CI
on:
  push:
    branches: [main]
  pull_request:
```

### Phase 6: Registry Setup

Create a project registry to track all bootstrapped projects:

```yaml
# C:\dev\AutopackProjects\.autopack-registry.yaml
version: "1.0"
created: 2026-01-29
projects:
  - name: file-organizer-app-v1
    path: file-organizer-app-v1
    status: active
    created: 2026-01-15
    migrated_from: .autonomous_runs
    migration_date: 2026-01-29
```

## Verification Checklist

After migration, verify:

- [ ] `C:\dev\AutopackProjects\` directory exists
- [ ] `AUTOPACK_PROJECTS_ROOT` environment variable is set
- [ ] `get_projects_root()` returns correct path
- [ ] Existing projects moved successfully
- [ ] No broken paths in migrated projects
- [ ] `/project-bootstrap` creates projects in new location
- [ ] Autopack CI still passes (no project code in scope)
- [ ] Project files not appearing in Autopack git status

## Rollback Plan

If issues arise:

1. Copy projects back to `.autonomous_runs/`
2. Unset `AUTOPACK_PROJECTS_ROOT` environment variable
3. Revert config.py changes

```powershell
# Emergency rollback
Copy-Item -Recurse "C:\dev\AutopackProjects\*" "C:\dev\Autopack\.autonomous_runs\"
[System.Environment]::SetEnvironmentVariable("AUTOPACK_PROJECTS_ROOT", $null, "User")
```

## Timeline

| Step | Status |
|------|--------|
| Phase 1: Environment Setup | 🔜 Ready to execute |
| Phase 2: Migrate Existing Projects | 🔜 Ready to execute |
| Phase 3: Update Autopack Components | ⏳ In progress |
| Phase 4: Update Project Bootstrap | ✅ Completed |
| Phase 5: CI/CD Updates | 🔜 After migration |
| Phase 6: Registry Setup | 🔜 After migration |

## Commands Summary

```powershell
# Quick setup (run in order)
New-Item -ItemType Directory -Path "C:\dev\AutopackProjects" -Force
[System.Environment]::SetEnvironmentVariable("AUTOPACK_PROJECTS_ROOT", "C:\dev\AutopackProjects", "User")
$env:AUTOPACK_PROJECTS_ROOT = "C:\dev\AutopackProjects"

# Migrate existing project
Move-Item "C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1" "C:\dev\AutopackProjects\"

# Verify
python -c "from autopack.config import get_projects_root; print(get_projects_root())"
```
