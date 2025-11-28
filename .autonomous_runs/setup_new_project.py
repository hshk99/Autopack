#!/usr/bin/env python3
"""
Autopack New Project Setup Script

Creates a new autonomous project directory with all necessary files
for the magic phrase pattern to work.

Usage:
    python .autonomous_runs/setup_new_project.py --name "MyApp" --slug "my-app-v1"

This script creates:
- .autonomous_runs/<project-slug>/
  ├── scripts/autopack_runner.py      (copied from template)
  ├── WHATS_LEFT_TO_BUILD.md          (empty template)
  ├── PROJECT_README.md               (auto-generated)
  └── run.sh                          (wrapper script)

After running this script, the magic phrase will work:
"RUN AUTOPACK END-TO-END for <ProjectName> now."
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime


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
        print(f"[2/5] Copied generic autopack_runner.py")
    else:
        print(f"[WARNING] Source runner not found at {source_runner}")
        print(f"[WARNING] You'll need to create autopack_runner.py manually")

    # Create WHATS_LEFT_TO_BUILD.md template
    whats_left = project_dir / "WHATS_LEFT_TO_BUILD.md"
    whats_left.write_text(f"""# {project_name} - Tasks for Autopack

**Project**: {project_name}
**Slug**: {project_slug}
**Created**: {datetime.now().strftime('%Y-%m-%d')}

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
cd c:/dev/Autopack/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```
""")
    print(f"[3/5] Created WHATS_LEFT_TO_BUILD.md template")

    # Create PROJECT_README.md
    readme = project_dir / "PROJECT_README.md"
    readme.write_text(f"""# {project_name}

**Project Slug**: `{project_slug}`
**Created**: {datetime.now().strftime('%Y-%m-%d')}
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
cd c:/dev/Autopack/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```

### Manual Execution

**Non-interactive mode** (no prompts, auto-start service):
```bash
cd c:/dev/Autopack/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py --non-interactive
```

**Interactive mode** (asks for confirmation):
```bash
cd c:/dev/Autopack/.autonomous_runs/{project_slug}
python scripts/autopack_runner.py
```

**Using wrapper script**:
```bash
cd c:/dev/Autopack/.autonomous_runs/{project_slug}
./run.sh
```

---

## What Happens When You Run

1. **Auto-detects** if Autopack service is running
2. **Auto-starts** uvicorn in background if needed
3. **Reads** all tasks from `WHATS_LEFT_TO_BUILD.md`
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
├── WHATS_LEFT_TO_BUILD.md          # Task definitions (edit this!)
├── PROJECT_README.md               # This file
└── run.sh                          # Wrapper script (optional)
```

---

## Next Steps

1. **Define tasks** in `WHATS_LEFT_TO_BUILD.md`
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
""")
    print(f"[4/5] Created PROJECT_README.md")

    # Create run.sh wrapper
    run_script = project_dir / "run.sh"
    run_script.write_text(f"""#!/bin/bash
# {project_name} - Fully Autonomous Build Runner
#
# This script triggers the autonomous build defined in WHATS_LEFT_TO_BUILD.md
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
echo "Tasks: All items from WHATS_LEFT_TO_BUILD.md"
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
""")
    run_script.chmod(0o755)  # Make executable
    print(f"[5/5] Created run.sh wrapper script")

    print(f"\n{'=' * 80}")
    print(f"✅ Project setup complete!")
    print(f"{'=' * 80}")
    print(f"\nProject: {project_name}")
    print(f"Location: {project_dir}")
    print(f"\nNext steps:")
    print(f"1. Edit {project_dir}/WHATS_LEFT_TO_BUILD.md to define your tasks")
    print(f"2. Use magic phrase: 'RUN AUTOPACK END-TO-END for {project_name} now.'")
    print(f"\nThe magic phrase will execute:")
    print(f"  cd {project_dir}")
    print(f"  python scripts/autopack_runner.py --non-interactive")
    print(f"\n{'=' * 80}")


def main():
    parser = argparse.ArgumentParser(
        description="Setup a new Autopack autonomous project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup_new_project.py --name "MyApp" --slug "my-app-v1"
  python setup_new_project.py --name "API Gateway" --slug "api-gateway-v1"
  python setup_new_project.py --name "ChatBot" --slug "chatbot-v1"

After setup, the magic phrase will work:
  "RUN AUTOPACK END-TO-END for <ProjectName> now."
        """
    )

    parser.add_argument(
        '--name',
        type=str,
        required=True,
        help='Project name (e.g., "MyApp", "API Gateway")'
    )

    parser.add_argument(
        '--slug',
        type=str,
        required=True,
        help='Project slug for directory name (e.g., "my-app-v1", "api-gateway-v1")'
    )

    args = parser.parse_args()

    # Get base directory (.autonomous_runs)
    base_dir = Path(__file__).parent

    # Create project structure
    create_project_structure(args.name, args.slug, base_dir)


if __name__ == "__main__":
    main()
