#!/usr/bin/env python3
"""
Autopack New Project Setup Script

Creates a new autonomous project directory with all necessary files
for the magic phrase pattern to work.

Usage:
    python .autonomous_runs/setup_new_project.py --name "MyApp"

    # Slug is auto-generated from project name (e.g., "MyApp" → "my-app-v1")
    # For custom slug: python .autonomous_runs/setup_new_project.py --name "MyApp" --slug "custom-slug-v1"

This script creates:
- .autonomous_runs/<project-slug>/
  ├── scripts/autopack_runner.py      (copied from template)
  ├── FUTURE_PLAN.md          (empty template)
  ├── PROJECT_README.md               (auto-generated)
  └── run.sh                          (wrapper script)

After running this script, the magic phrase will work:
"RUN AUTOPACK END-TO-END for <ProjectName> now."
"""

import argparse
import re
import shutil
from pathlib import Path
from datetime import datetime

# Repo root detection for dynamic paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def generate_slug_from_name(name: str, runs_root: Path) -> str:
    """
    Generate a filesystem-safe slug from a human project name.

    Rules:
    - Convert to lowercase
    - Replace non-alphanumeric characters with '-'
    - Collapse repeated '-' into single '-'
    - Trim leading/trailing '-'
    - Append '-v1'
    - If that directory already exists under runs_root, increment to -v2, -v3, etc.

    Examples:
        "File Organizer" → "file-organizer-v1"
        "Shopping Cart" → "shopping-cart-v1"
        "My API Gateway" → "my-api-gateway-v1"
        "Todo App" → "todo-app-v1" (or "todo-app-v2" if v1 exists)

    Args:
        name: Human-friendly project name (can include spaces, capitals, etc.)
        runs_root: Path to .autonomous_runs directory

    Returns:
        Filesystem-safe slug with version suffix
    """
    # Normalize: lowercase and replace non-alphanumeric with hyphens
    base = name.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)

    # Collapse repeated hyphens and trim
    base = re.sub(r"-+", "-", base).strip("-")

    # Fallback if result is empty
    if not base:
        base = "autopack-project"

    # Auto-increment version if directory exists
    # runs_root is typically Path(".autonomous_runs")
    version = 1
    while True:
        slug = f"{base}-v{version}"
        if not (runs_root / slug).exists():
            return slug
        version += 1


def create_project_structure(project_name: str, project_slug: str, base_dir: Path):
    """Create new project directory structure"""

    project_dir = base_dir / project_slug
    scripts_dir = project_dir / "scripts"

    # Create directories
    project_dir.mkdir(exist_ok=True)
    scripts_dir.mkdir(exist_ok=True)

    print(f"[1/5] Created directory structure: {project_dir}")

    # Copy generic autopack_runner.py from FileOrganizer
    source_runner = base_dir / "file-organizer-app-v1" / "scripts" / "autopack_runner.py"
    dest_runner = scripts_dir / "autopack_runner.py"

    if source_runner.exists():
        shutil.copy2(source_runner, dest_runner)
        print("[2/5] Copied generic autopack_runner.py")
    else:
        print(f"[WARNING] Source runner not found at {source_runner}")
        print("[WARNING] You'll need to create autopack_runner.py manually")

    # Create FUTURE_PLAN.md template
    whats_left = project_dir / "FUTURE_PLAN.md"
    whats_left.write_text(
        f"""# {project_name} - Tasks for Autopack

**Project**: {project_name}
**Slug**: {project_slug}
**Created**: {datetime.now().strftime("%Y-%m-%d")}

---

## Phase 1: [Phase Name]

### Task 1: [Task Name]
**Phase ID**: `{project_slug}-task1`
**Category**: [backend|frontend|database|api|testing|docs|deployment]
**Complexity**: [low|medium|high]
**Description**:
[Describe what needs to be built]

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

**Dependencies**: None

---

### Task 2: [Task Name]
**Phase ID**: `{project_slug}-task2`
**Category**: [category]
**Complexity**: [complexity]
**Description**:
[Describe what needs to be built]

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

**Dependencies**: `{project_slug}-task1`

---

## Notes for Autopack

- **Token Budget**: 150,000 (adjust as needed)
- **Max Duration**: 5 hours (adjust as needed)
- **Safety Profile**: standard
- **Priority Tiers**: Organize tasks into tiers if needed

---

## How to Run

**Magic Phrase**:
```
RUN AUTOPACK END-TO-END for {project_name} now.
```

**Or manually**:
```bash
cd {REPO_ROOT}/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```
"""
    )
    print("[3/5] Created FUTURE_PLAN.md template")

    # Create PROJECT_README.md
    readme = project_dir / "PROJECT_README.md"
    readme.write_text(
        f"""# {project_name}

**Project Slug**: `{project_slug}`
**Created**: {datetime.now().strftime("%Y-%m-%d")}
**Status**: Setup complete, ready for task definition

---

## Overview

[Describe the project here]

---

## How to Run Autonomous Build

### Magic Phrase (Recommended)

Simply say to Cursor:
```
RUN AUTOPACK END-TO-END for {project_name} now.
```

Cursor will execute:
```bash
cd {REPO_ROOT}/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```

### Manual Execution

**Non-interactive mode** (no prompts, auto-start service):
```bash
cd {REPO_ROOT}/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```

**Interactive mode** (asks for confirmation):
```bash
cd {REPO_ROOT}/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py
```

**Using wrapper script**:
```bash
cd {REPO_ROOT}/.autonomous_runs/{project_slug}
./run.sh
```

---

## What Happens When You Run

1. **Auto-detects** if Autopack service is running
2. **Auto-starts** uvicorn in background if needed
3. **Reads** all tasks from `FUTURE_PLAN.md`
4. **Creates** an Autopack run with all tasks
5. **Monitors** progress in real-time
6. **Generates** comprehensive reports
7. **Shuts down** service gracefully on completion

**Zero human interaction required!**

---

## Project Structure

```
.autonomous_runs/{project_slug}/
├── scripts/
│   └── autopack_runner.py          # Generic runner (project-agnostic)
├── FUTURE_PLAN.md          # Task definitions (edit this!)
├── PROJECT_README.md               # This file
└── run.sh                          # Wrapper script (optional)
```

---

## Next Steps

1. **Define tasks** in `FUTURE_PLAN.md`
2. **Trigger build** with magic phrase: `RUN AUTOPACK END-TO-END for {project_name} now.`
3. **Review reports** generated after completion

---

## Configuration

### Environment Variables

```bash
# Autopack API URL (default: http://localhost:8000)
export AUTOPACK_API_URL=http://localhost:8000

# Autopack API Key (if authentication enabled)
export AUTOPACK_API_KEY=your-api-key-here
```

### Adjusting Budget/Timeouts

The generic `autopack_runner.py` uses sensible defaults:
- Token Cap: 150,000
- Max Duration: 5 hours (300 minutes)
- Safety Profile: standard

To adjust, edit the run configuration in `autopack_runner.py` or create a project-specific runner.

---

## Troubleshooting

See [FileOrganizer HOW_TO_RUN_PHASE2.md](../file-organizer-app-v1/HOW_TO_RUN_PHASE2.md) for common issues and solutions.
"""
    )
    print("[4/5] Created PROJECT_README.md")

    # Create run.sh wrapper
    run_script = project_dir / "run.sh"
    run_script.write_text(
        f"""#!/bin/bash
# {project_name} - Fully Autonomous Build Runner
#
# This script triggers the autonomous build defined in FUTURE_PLAN.md
# with zero human interaction. Auto-starts Autopack service if needed.
#
# Usage: ./run.sh

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

echo "================================================================================"
echo "{project_name.upper()} - AUTOPACK AUTONOMOUS BUILD"
echo "================================================================================"
echo ""
echo "Project: {project_name}"
echo "Tasks: All items from FUTURE_PLAN.md"
echo "Mode: Non-interactive (zero human prompts, auto-start service)"
echo ""
echo "Reports will be written to:"
echo "  - ${{SCRIPT_DIR}}/AUTOPACK_BUILD_REPORT_<timestamp>.md"
echo "  - ${{SCRIPT_DIR}}/AUTOPACK_BUILD_DATA_<timestamp>.json"
echo ""
echo "================================================================================"
echo ""

# Run the generic runner (auto-starts Autopack API service)
python "${{SCRIPT_DIR}}/scripts/autopack_runner.py" --non-interactive

echo ""
echo "================================================================================"
echo "BUILD COMPLETE"
echo "================================================================================"
echo ""
echo "Check the report files listed above for results."
echo ""
"""
    )
    run_script.chmod(0o755)  # Make executable
    print("[5/5] Created run.sh wrapper script")

    print(f"\n{'=' * 80}")
    print("✅ Project setup complete!")
    print(f"{'=' * 80}")
    print(f"\nProject: {project_name}")
    print(f"Slug: {project_slug}")
    print(f"Location: {project_dir}")
    print("\nNext steps:")
    print(f"1. Edit {project_dir}/FUTURE_PLAN.md to define your tasks")
    print(f"2. Use magic phrase: 'RUN AUTOPACK END-TO-END for {project_name} now.'")
    print("\nThe magic phrase will execute:")
    print(f"  cd {project_dir}")
    print("  python scripts/autopack_runner.py --non-interactive")
    print(f"\n{'=' * 80}")


def main():
    parser = argparse.ArgumentParser(
        description="Setup a new Autopack autonomous project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (slug auto-generated from name):
  python setup_new_project.py --name "MyApp"
  python setup_new_project.py --name "File Organizer"
  python setup_new_project.py --name "Shopping Cart"

  # Custom slug (advanced):
  python setup_new_project.py --name "MyApp" --slug "custom-app-v1"

Slug Generation:
  By default, the slug is auto-generated from the project name:
  - "MyApp" → "my-app-v1"
  - "File Organizer" → "file-organizer-v1"
  - "Shopping Cart" → "shopping-cart-v1"

  If the directory already exists, version is auto-incremented:
  - "MyApp" → "my-app-v2" (if v1 exists)

After setup, the magic phrase will work:
  "RUN AUTOPACK END-TO-END for <ProjectName> now."
        """,
    )

    parser.add_argument(
        "--name",
        type=str,
        required=True,
        help='Project name (e.g., "MyApp", "File Organizer", "Shopping Cart")',
    )

    parser.add_argument(
        "--slug",
        type=str,
        required=False,  # SLUG IS NOW OPTIONAL!
        default=None,
        help="Project slug for directory name (optional, auto-generated from name if not provided)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Test slug generation without creating files"
    )

    args = parser.parse_args()

    # Get base directory (.autonomous_runs)
    base_dir = Path(__file__).parent

    # Ensure .autonomous_runs directory exists
    base_dir.mkdir(exist_ok=True)

    # Determine slug: use provided slug, or auto-generate from name
    if args.slug:
        # User provided custom slug - use it as-is (with basic normalization)
        slug = args.slug.strip().lower()
        print(f"[INFO] Using custom slug: {slug}")
    else:
        # Auto-generate slug from project name
        slug = generate_slug_from_name(args.name, base_dir)
        print(f"[INFO] Auto-generated slug from '{args.name}': {slug}")

    # Dry-run mode: just show what would be generated
    if args.dry_run:
        print("\n[DRY RUN] Would create project:")
        print(f"  Name: {args.name}")
        print(f"  Slug: {slug}")
        print(f"  Path: {base_dir / slug}")
        print("\n[DRY RUN] No files created.")
        return

    # Create project structure
    create_project_structure(args.name, slug, base_dir)


if __name__ == "__main__":
    main()
