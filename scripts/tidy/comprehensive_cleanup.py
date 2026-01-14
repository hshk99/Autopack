#!/usr/bin/env python3
"""
Comprehensive Workspace Cleanup - Implementation of PROPOSED_CLEANUP_STRUCTURE.md

This script implements the complete reorganization plan with all specific requirements.
"""

import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Dict

REPO_ROOT = Path(__file__).parent.parent


# Import run family extractor functions inline
def extract_run_family(run_id: str) -> str:
    """Extract run family name from run ID."""
    if not run_id:
        return "general"

    patterns = [
        r"-\d{8}-\d{6}$",
        r"-\d{8}-\d{4,6}$",
        r"-\d{6,8}$",
        r"-20\d{6}-\d{6}$",
        r"-20\d{6}\d{6}$",
        r"-20\d{6}[a-z]$",
        r"-\d{4}$",
        r"-[a-z]$",
    ]

    family = run_id
    for pattern in patterns:
        family = re.sub(pattern, "", family)

    return family if family else "general"


def group_runs_by_family(run_ids: List[str]) -> Dict[str, List[str]]:
    """Group run IDs by their family names."""
    families = {}
    for run_id in run_ids:
        family = extract_run_family(run_id)
        if family not in families:
            families[family] = []
        families[family].append(run_id)
    return families


def git_checkpoint(message: str):
    """Create a git checkpoint commit."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, capture_output=True
        )
        print(f"\n[GIT] ✓ Created checkpoint: {message}")
        return True
    except subprocess.CalledProcessError:
        print("\n[GIT] No changes to commit")
        return False


def phase1_root_cleanup(dry_run: bool = True):
    """Phase 1: Clean root directory."""
    print("\n" + "=" * 80)
    print("PHASE 1: ROOT DIRECTORY CLEANUP")
    print("=" * 80)

    archive = REPO_ROOT / "archive"
    archive.mkdir(exist_ok=True)

    actions = []

    # 1. Move .cursor/ → archive/prompts/
    cursor_dir = REPO_ROOT / ".cursor"
    if cursor_dir.exists():
        prompts_dir = archive / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for item in cursor_dir.glob("*.md"):
            dest = prompts_dir / item.name
            actions.append(("move", item, dest))
            print(f"  .cursor/{item.name} → archive/prompts/")
        if not dry_run:
            for action, src, dest in [a for a in actions if a[0] == "move"]:
                shutil.move(str(src), str(dest))
            if not any(cursor_dir.iterdir()):
                cursor_dir.rmdir()

    # 2. Move planning/ → archive/prompts/
    planning_dir = REPO_ROOT / "planning"
    if planning_dir.exists():
        prompts_dir = archive / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for item in planning_dir.glob("*.md"):
            dest = prompts_dir / item.name
            print(f"  planning/{item.name} → archive/prompts/")
            if not dry_run:
                shutil.move(str(item), str(dest))
        if not dry_run and not any(planning_dir.iterdir()):
            planning_dir.rmdir()

    # 3. Move templates/ → config/templates/
    templates_dir = REPO_ROOT / "templates"
    if templates_dir.exists():
        config_dir = REPO_ROOT / "config"
        config_dir.mkdir(exist_ok=True)
        dest = config_dir / "templates"
        print("  templates/ → config/templates/")
        if not dry_run:
            shutil.move(str(templates_dir), str(dest))

    # 4. Move integrations/ → scripts/integrations/
    integrations_dir = REPO_ROOT / "integrations"
    if integrations_dir.exists():
        scripts_dir = REPO_ROOT / "scripts"
        dest = scripts_dir / "integrations"
        print("  integrations/ → scripts/integrations/")
        if not dry_run:
            shutil.move(str(integrations_dir), str(dest))

    # 5. Move logs/ → archive/diagnostics/logs/
    logs_dir = REPO_ROOT / "logs"
    if logs_dir.exists():
        diag_logs = archive / "diagnostics" / "logs"
        diag_logs.mkdir(parents=True, exist_ok=True)
        print("  logs/ → archive/diagnostics/logs/")
        if not dry_run:
            for item in logs_dir.iterdir():
                dest = diag_logs / item.name
                shutil.move(str(item), str(dest))
            if not any(logs_dir.iterdir()):
                logs_dir.rmdir()

    print(f"\n[PHASE 1] {'DRY RUN - ' if dry_run else ''}Complete")


def phase2_docs_cleanup(dry_run: bool = True):
    """Phase 2: Clean docs/ folder and organize truth sources."""
    print("\n" + "=" * 80)
    print("PHASE 2: DOCS CLEANUP & TRUTH SOURCES")
    print("=" * 80)

    archive = REPO_ROOT / "archive"
    docs_dir = REPO_ROOT / "docs"

    if not docs_dir.exists():
        print("[SKIP] docs/ does not exist")
        return

    # Files to move to archive/plans/
    plans_files = [
        "DASHBOARD_IMPLEMENTATION_PLAN.md",
        "CRITICAL_ISSUES_IMPLEMENTATION_PLAN.md",
        "IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md",
        "IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT_PHASE2.md",
        "TOKEN_EFFICIENCY_IMPLEMENTATION.md",
    ]

    # Files to move to archive/reports/
    reports_files = [
        "AUTOPACK_TIDY_SYSTEM_COMPREHENSIVE_GUIDE.md",
        "DEPLOYMENT_GUIDE.md",
        "DASHBOARD_WIRING_GUIDE.md",
        "directory_routing_qdrant_schema.md",
        "phase_spec_schema.md",
        "stage2_structured_edits.md",
        "PRE_PUBLICATION_CHECKLIST.md",
        "TEST_RUN_CHECKLIST.md",
        "QDRANT_INTEGRATION_VERIFIED.md",
        "QDRANT_SETUP_COMPLETE.md",
        "QDRANT_TRANSITION_COMPLETE.md",
        "IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md",
    ]

    # Files to move to archive/analysis/
    analysis_files = [
        "EFFICIENCY_ANALYSIS.md",
        "TROUBLESHOOTING_AUTONOMY_PLAN.md",
    ]

    # Files to move to archive/research/
    research_files = ["QUOTA_AWARE_ROUTING.md"]

    moved_count = 0

    # Move plans
    plans_dir = archive / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    for filename in plans_files:
        for src in docs_dir.rglob(filename):
            dest = plans_dir / src.name
            print(f"  {src.name} → archive/plans/")
            if not dry_run:
                shutil.move(str(src), str(dest))
                moved_count += 1

    # Move reports
    reports_dir = archive / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for filename in reports_files:
        for src in docs_dir.rglob(filename):
            dest = reports_dir / src.name
            print(f"  {src.name} → archive/reports/")
            if not dry_run:
                shutil.move(str(src), str(dest))
                moved_count += 1

    # Move analysis
    analysis_dir = archive / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for filename in analysis_files:
        for src in docs_dir.rglob(filename):
            dest = analysis_dir / src.name
            print(f"  {src.name} → archive/analysis/")
            if not dry_run:
                shutil.move(str(src), str(dest))
                moved_count += 1

    # Move research
    research_dir = archive / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    for filename in research_files:
        for src in docs_dir.rglob(filename):
            dest = research_dir / src.name
            print(f"  {src.name} → archive/research/")
            if not dry_run:
                shutil.move(str(src), str(dest))
                moved_count += 1

    # Move FUTURE_PLAN to file-organizer docs/
    fileorg_docs = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "guides"
    fileorg_docs.mkdir(parents=True, exist_ok=True)
    for pattern in ["FUTURE_PLAN.md", "FUTURE_PLAN_MAINTENANCE.md"]:
        src = REPO_ROOT / pattern
        if src.exists():
            dest = fileorg_docs / src.name
            print(f"  {src.name} → file-organizer/docs/guides/")
            if not dry_run:
                shutil.move(str(src), str(dest))

    print(f"\n[PHASE 2] Moved {moved_count} files")


def phase3_autopack_archive_cleanup(dry_run: bool = True):
    """Phase 3: Clean Autopack archive."""
    print("\n" + "=" * 80)
    print("PHASE 3: AUTOPACK ARCHIVE CLEANUP")
    print("=" * 80)

    archive = REPO_ROOT / "archive"

    # 1. Move stranded .log files to diagnostics/logs/
    diag_logs = archive / "diagnostics" / "logs"
    diag_logs.mkdir(parents=True, exist_ok=True)

    stranded_logs = list(archive.glob("*.log"))
    if stranded_logs:
        print(f"\n[LOGS] Moving {len(stranded_logs)} stranded .log files")
        for log_file in stranded_logs:
            dest = diag_logs / log_file.name
            print(f"  {log_file.name} → diagnostics/logs/")
            if not dry_run:
                shutil.move(str(log_file), str(dest))

    # 2. Merge archive/logs/ into diagnostics/logs/
    logs_folder = archive / "logs"
    if logs_folder.exists():
        print("\n[LOGS] Merging archive/logs/ into diagnostics/logs/")
        for item in logs_folder.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(logs_folder)
                dest = diag_logs / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                print(f"  logs/{rel_path} → diagnostics/logs/")
                if not dry_run:
                    shutil.move(str(item), str(dest))
        if not dry_run:
            try:
                shutil.rmtree(logs_folder)
                print("[DELETE] Removed empty logs/ folder")
            except:
                pass

    # 3. Merge archive/delegations/ into reports/
    delegations = archive / "delegations"
    reports = archive / "reports"
    if delegations.exists():
        print("\n[DELEGATIONS] Merging into reports/")
        reports.mkdir(parents=True, exist_ok=True)
        for item in delegations.iterdir():
            dest = reports / item.name
            print(f"  delegations/{item.name} → reports/")
            if not dry_run:
                shutil.move(str(item), str(dest))
        if not dry_run:
            try:
                shutil.rmtree(delegations)
                print("[DELETE] Removed delegations/ folder")
            except:
                pass

    # 4. Flatten superseded/ (if exists)
    # This will be handled by existing tidy_workspace.py

    # 5. Remove nested folders
    for nested in ["archive", ".autonomous_runs"]:
        nested_path = archive / nested
        if nested_path.exists():
            print(f"\n[DELETE] Removing nested archive/{nested}/")
            if not dry_run:
                shutil.rmtree(nested_path)

    print("\n[PHASE 3] Complete")


def phase4_autonomous_runs_cleanup(dry_run: bool = True):
    """Phase 4: Clean .autonomous_runs root."""
    print("\n" + "=" * 80)
    print("PHASE 4: .AUTONOMOUS_RUNS ROOT CLEANUP")
    print("=" * 80)

    autonomous_root = REPO_ROOT / ".autonomous_runs"
    if not autonomous_root.exists():
        print("[SKIP] .autonomous_runs does not exist")
        return

    # Move loose Python scripts to scripts/
    scripts_dir = REPO_ROOT / "scripts"
    for script in ["delegate_to_openai.py", "setup_new_project.py", "task_format_converter.py"]:
        src = autonomous_root / script
        if src.exists():
            dest = scripts_dir / script
            print(f"  {script} → scripts/")
            if not dry_run:
                shutil.move(str(src), str(dest))

    # Note: Organizing loose folders (runs/, archive/, docs/, exports/, patches/, openai_delegations/)
    # requires manual review - will be handled by tidy system

    print("\n[PHASE 4] Complete")


def phase5_fileorganizer_reorganization(dry_run: bool = True):
    """Phase 5: Reorganize file-organizer project."""
    print("\n" + "=" * 80)
    print("PHASE 5: FILE-ORGANIZER PROJECT REORGANIZATION")
    print("=" * 80)

    fileorg_root = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
    if not fileorg_root.exists():
        print("[SKIP] file-organizer-app-v1 does not exist")
        return

    # 1. Rename fileorganizer/ → src/
    fileorganizer_dir = fileorg_root / "fileorganizer"
    src_dir = fileorg_root / "src"
    if fileorganizer_dir.exists() and not src_dir.exists():
        print("\n[REORGANIZE] fileorganizer/ → src/")
        if not dry_run:
            shutil.move(str(fileorganizer_dir), str(src_dir))
            print("  ✓ Renamed fileorganizer/ to src/")

        # Move deploy.sh to scripts/
        deploy_sh = src_dir / "deploy.sh"
        if deploy_sh.exists():
            scripts_dir = fileorg_root / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            dest = scripts_dir / "deploy.sh"
            print("  deploy.sh → scripts/")
            if not dry_run:
                shutil.move(str(deploy_sh), str(dest))

    # 2. Merge codex_delegations/ into reports/
    archive = fileorg_root / "archive"
    codex_delegations = archive / "codex_delegations"
    reports = archive / "reports"
    if codex_delegations.exists():
        print("\n[DELEGATIONS] Merging codex_delegations/ → reports/")
        reports.mkdir(parents=True, exist_ok=True)
        for item in codex_delegations.iterdir():
            dest = reports / item.name
            print(f"  {item.name} → reports/")
            if not dry_run:
                shutil.move(str(item), str(dest))
        if not dry_run:
            try:
                shutil.rmtree(codex_delegations)
                print("[DELETE] Removed codex_delegations/ folder")
            except:
                pass

    # 3. Remove unused folders
    for unused in ["patches", "exports", "__pycache__"]:
        unused_path = fileorg_root / unused
        if unused_path.exists():
            # Check if truly empty/unused
            if unused == "__pycache__" or not any(unused_path.rglob("*")):
                print(f"\n[DELETE] Removing unused {unused}/")
                if not dry_run:
                    shutil.rmtree(unused_path)

    # 4. Remove archive/__pycache__
    archive_pycache = archive / "__pycache__"
    if archive_pycache.exists():
        print("\n[DELETE] Removing archive/__pycache__/")
        if not dry_run:
            shutil.rmtree(archive_pycache)

    # 5. Remove nested folders in archive
    for nested in ["archive", ".autonomous_runs", "autopack"]:
        nested_path = archive / nested
        if nested_path.exists():
            print(f"\n[DELETE] Removing nested archive/{nested}/")
            if not dry_run:
                shutil.rmtree(nested_path)

    # 6. Move archive/docs/ up to parent
    archive_docs = archive / "docs"
    parent_docs = fileorg_root / "docs"
    if archive_docs.exists() and not parent_docs.exists():
        print("\n[MOVE] archive/docs/ → docs/")
        if not dry_run:
            shutil.move(str(archive_docs), str(parent_docs))

    print("\n[PHASE 5] Complete")


def phase6_run_family_grouping(dry_run: bool = True):
    """Phase 6: Group 137 runs into 31 families."""
    print("\n" + "=" * 80)
    print("PHASE 6: RUN FAMILY GROUPING (137 → 31 families)")
    print("=" * 80)

    fileorg_archive = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive"
    runs_dir = fileorg_archive / "diagnostics" / "runs"

    if not runs_dir.exists():
        # Move loose run directories first
        runs_to_move = []
        for item in fileorg_archive.iterdir():
            if item.is_dir() and item.name not in {
                "plans",
                "reports",
                "analysis",
                "research",
                "delegations",
                "prompts",
                "diagnostics",
                "__pycache__",
                "deprecated",
                "docs",
            }:
                if any(
                    pattern in item.name
                    for pattern in [
                        "fileorg-",
                        "autopack-",
                        "backlog-",
                        "phase",
                        "test-",
                        "scope-",
                        "demo-",
                        "escalation-",
                        "run-",
                        "start",
                    ]
                ):
                    runs_to_move.append(item)

        if runs_to_move:
            runs_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n[RUNS] Moving {len(runs_to_move)} run directories to diagnostics/runs/")
            for run_dir in runs_to_move:
                dest = runs_dir / run_dir.name
                print(f"  {run_dir.name}")
                if not dry_run:
                    shutil.move(str(run_dir), str(dest))

    if not runs_dir.exists():
        print("[SKIP] No runs directory found")
        return

    # Group by family
    run_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    run_names = [d.name for d in run_dirs]
    families = group_runs_by_family(run_names)

    print(f"\n[GROUPING] Found {len(run_dirs)} runs in {len(families)} families")

    grouped_count = 0
    for family_name, run_ids in sorted(families.items()):
        if len(run_ids) == 1:
            continue  # Single runs stay as-is

        print(f"\n[FAMILY] {family_name}/ ({len(run_ids)} runs)")
        family_dir = runs_dir / family_name

        for run_id in run_ids:
            src_dir = runs_dir / run_id
            dest_dir = family_dir / run_id

            if not src_dir.exists():
                continue

            if run_id == family_name:
                print(f"  {run_id} (at family root, skipping)")
                continue

            print(f"  {run_id}")
            if not dry_run:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_dir), str(dest_dir))
                grouped_count += 1

    print(f"\n[PHASE 6] Grouped {grouped_count} runs into families")


def verify_structure():
    """Verify final structure matches PROPOSED_CLEANUP_STRUCTURE.md."""
    print("\n" + "=" * 80)
    print("VERIFICATION: FINAL STRUCTURE CHECK")
    print("=" * 80)

    issues = []

    # Check root structure
    root_should_have = {"src", "scripts", "tests", "docs", "config", "archive", ".autonomous_runs"}
    unwanted = {".cursor", "logs", "planning", "templates", "integrations"}

    print("\n[ROOT DIRECTORY]")
    for folder in sorted(root_should_have):
        exists = (REPO_ROOT / folder).exists()
        status = "✓" if exists else "✗"
        print(f"  {status} {folder}/")
        if not exists:
            issues.append(f"Missing: {folder}/")

    for folder in unwanted:
        if (REPO_ROOT / folder).exists():
            issues.append(f"Unwanted folder still exists: {folder}/")
            print(f"  ✗ {folder}/ (should be removed)")

    # Check docs/ truth sources
    print("\n[TRUTH SOURCES]")
    docs_dir = REPO_ROOT / "docs"
    if docs_dir.exists():
        md_files = list(docs_dir.rglob("*.md"))
        print(f"  Autopack docs/: {len(md_files)} files")
        for f in md_files:
            print(f"    ✓ {f.relative_to(docs_dir)}")

    fileorg_docs = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs"
    if fileorg_docs.exists():
        md_files = list(fileorg_docs.rglob("*.md"))
        print(f"  File-organizer docs/: {len(md_files)} files")
        for f in md_files:
            print(f"    ✓ {f.relative_to(fileorg_docs)}")

    # Check run family grouping
    print("\n[RUN FAMILIES]")
    runs_dir = (
        REPO_ROOT
        / ".autonomous_runs"
        / "file-organizer-app-v1"
        / "archive"
        / "diagnostics"
        / "runs"
    )
    if runs_dir.exists():
        families = sorted([d.name for d in runs_dir.iterdir() if d.is_dir()])
        print(f"  Found {len(families)} families")
        for family in families[:10]:
            family_dir = runs_dir / family
            run_count = len([d for d in family_dir.iterdir() if d.is_dir()])
            if run_count > 0:
                print(f"    ✓ {family}/ ({run_count} runs)")
            else:
                print(f"    ✓ {family}/ (single run)")

    print("\n" + "=" * 80)
    if issues:
        print("VERIFICATION: ISSUES FOUND")
        for issue in issues:
            print(f"  ✗ {issue}")
    else:
        print("VERIFICATION: ✓ ALL CHECKS PASSED")
    print("=" * 80)

    return len(issues) == 0


def main():
    """Run comprehensive workspace cleanup."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Comprehensive workspace cleanup implementing PROPOSED_CLEANUP_STRUCTURE.md"
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 80)
    print("COMPREHENSIVE WORKSPACE CLEANUP")
    print("Implementing: PROPOSED_CLEANUP_STRUCTURE.md")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    if not dry_run:
        git_checkpoint("cleanup: pre-cleanup checkpoint")

    # Execute all phases
    phase1_root_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 1 - root directory cleaned")

    phase2_docs_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 2 - docs cleaned, truth sources organized")

    phase3_autopack_archive_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 3 - autopack archive cleaned")

    phase4_autonomous_runs_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 4 - autonomous_runs root cleaned")

    phase5_fileorganizer_reorganization(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 5 - file-organizer reorganized")

    phase6_run_family_grouping(dry_run)
    if not dry_run:
        git_checkpoint("cleanup: phase 6 - runs grouped by family")

    # Verify
    verify_structure()

    print("\n" + "=" * 80)
    print("CLEANUP COMPLETE")
    print("=" * 80)

    if dry_run:
        print("\nThis was a DRY RUN. Use --execute to apply changes.")
    else:
        print("\nChanges committed. Review with: git log -7 --oneline")


if __name__ == "__main__":
    main()
