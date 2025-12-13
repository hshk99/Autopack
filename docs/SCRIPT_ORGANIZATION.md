# Script Organization System

**Purpose**: Automatically organize scattered scripts and files into a consistent directory structure.

**Date**: 2025-12-13

---

## Overview

The Script Organization System automatically moves scattered scripts, patches, and configuration files from various locations into organized directories within the `scripts/` and `archive/` folders.

## What Gets Organized

### 1. **Root Scripts** → `scripts/archive/root_scripts/`
Scripts at the repository root level:
- `*.py` - Python scripts
- `*.sh` - Shell scripts
- `*.bat` - Batch scripts

**Example**: `probe_script.py`, `test_auditor_400.py`, `run_full_probe_suite.sh`

### 2. **Examples** → `scripts/examples/`
Example scripts and usage demonstrations:
- All files from `examples/` directory

**Example**: `multi_project_example.py`

### 3. **Tasks** → `archive/tasks/`
Task configuration files:
- `*.yaml`, `*.yml` - YAML configs
- `*.json` - JSON configs

**Example**: `tidy_consolidation.yaml`

### 4. **Patches** → `archive/patches/`
Git patches and diff files:
- `*.patch` - Git patch files
- `*.diff` - Diff files

**Example**: `oi-fo-ci-failure.patch`

## What Stays in Place

The following files and directories are **excluded** from organization:

### Special Files (Never Moved)
- `setup.py` - Package setup
- `manage.py` - Django/Flask management
- `conftest.py` - Pytest configuration
- `wsgi.py`, `asgi.py` - WSGI/ASGI entry points
- `__init__.py` - Python package markers

### Directories (Never Scanned)
- `scripts/` - Already organized
- `src/` - Source code
- `tests/` - Test suites (pytest)
- `config/` - Configuration files
- `.autonomous_runs/` - Sub-project workspaces
- `archive/` - Already archived
- `.git/`, `venv/`, `node_modules/`, `__pycache__/` - System directories

---

## Usage

### Manual Organization

Run the standalone script organizer:

```bash
# Preview what will be organized (dry-run)
python scripts/organize_scripts.py

# Execute the organization
python scripts/organize_scripts.py --execute
```

### Automatic Organization (Integrated with Tidy)

Script organization is **automatically included** when running the autonomous tidy workflow for the main Autopack project:

```bash
# Tidy archive (includes script organization)
python scripts/tidy/autonomous_tidy.py archive --execute
```

**Note**: Script organization only runs for the **main Autopack project**, not for sub-projects in `.autonomous_runs/`.

---

## Example Output

```
📋 Found 13 script(s) to organize

📁 Scripts from repository root (6 files)
   → C:\dev\Autopack\scripts\archive\root_scripts
      • probe_script.py
      • test_auditor_400.py
      • test_learned_rules_standalone.py
      • probe_test_runner.sh
      • run_full_probe_suite.sh
      • RUN_EXECUTOR.bat

📁 Example scripts and usage demos (1 files)
   → C:\dev\Autopack\scripts\examples
      • multi_project_example.py

📁 Task configuration files (1 files)
   → C:\dev\Autopack\archive\tasks
      • tidy_consolidation.yaml

📁 Git patches and diffs (5 files)
   → C:\dev\Autopack\archive\patches
      • oi-fo-ci-failure.patch
      • oi-fo-frontend-noop.patch
      • oi-fo-patch-mismatch.patch
      • oi-fo-uk-yaml-truncation.patch
      • oi-fo-yaml-schema.patch
```

---

## Benefits

1. **Clean Repository Root**: Keeps the root directory focused on essential files
2. **Consistent Structure**: All scripts organized in predictable locations
3. **Easy Navigation**: Developers know where to find scripts and examples
4. **Automatic Maintenance**: Runs as part of regular tidy workflow
5. **Safe Operation**: Dry-run mode prevents accidental moves

---

## Integration with Autonomous Tidy

The script organizer is integrated into the autonomous tidy workflow as **Step 0**:

```
AUTONOMOUS TIDY WORKFLOW
═══════════════════════════════════════════════════════════

Step 0: Script Organization (Autopack only)
   ↓
Step 1: Pre-Tidy Auditor
   ↓
Step 2: Documentation Consolidation
   ↓
Step 3: Archive Cleanup (sub-projects only)
   ↓
Step 4: Post-Tidy Verification
```

---

## Configuration

The script organization rules are defined in `scripts/tidy/script_organizer.py`:

```python
script_patterns = {
    "root_scripts": {
        "source": repo_root,
        "patterns": ["*.py", "*.sh", "*.bat"],
        "max_depth": 1,
        "destination": scripts_dir / "archive" / "root_scripts"
    },
    "examples": {
        "source": repo_root / "examples",
        "patterns": ["*"],
        "max_depth": 10,
        "destination": scripts_dir / "examples"
    },
    # ... more categories
}
```

To add new organization rules, edit this configuration.

---

## Troubleshooting

### "No scattered scripts found"
- Everything is already organized!
- This is the expected state after running the organizer.

### Files not being moved
- Check if the file matches an excluded pattern (`setup.py`, `conftest.py`, etc.)
- Check if the file is in an excluded directory (`src/`, `tests/`, etc.)

### Duplicate files
- If a file with the same name exists in the destination, the organizer appends a timestamp
- Format: `filename_20251213_161234.ext`

---

## Future Enhancements

- [ ] Add configurable organization rules (YAML config)
- [ ] Support for project-specific script patterns
- [ ] Integration with git (detect tracked vs untracked scripts)
- [ ] Archive old scripts based on last modified date

---

**Last Updated**: 2025-12-13
**Maintainer**: Autopack Team
