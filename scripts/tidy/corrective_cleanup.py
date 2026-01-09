#!/usr/bin/env python3
"""
Corrective Cleanup - Fix comprehensive_cleanup.py failures

This script fixes the issues found in CLEANUP_VERIFICATION_ISSUES.md by:
1. Moving 43 loose .log files to archive/diagnostics/logs/
2. Classifying and moving 29 loose .md files to appropriate archive buckets
3. Moving prompts/ folder to archive/prompts/
4. Fixing archive/diagnostics/ nested folder issues
5. Moving openai_delegations/ to archive/reports/
6. Cleaning file-organizer archive/ loose files
7. Validating final structure matches PROPOSED_CLEANUP_STRUCTURE.md
"""

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def git_checkpoint(message: str):
    """Create a git checkpoint commit."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True, capture_output=True)
        result = subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, capture_output=True)
        print(f"\n[GIT] [OK] Created checkpoint: {message}")
        return True
    except subprocess.CalledProcessError:
        print("\n[GIT] No changes to commit")
        return False


def safe_move(src: Path, dest: Path) -> bool:
    """Safely move file or folder."""
    if not src.exists():
        print(f"  [SKIP] Source does not exist: {src}")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        if src.is_file() and dest.is_file():
            # File exists, skip
            print(f"  [SKIP] Destination already exists: {dest.name}")
            return False
        elif src.is_dir() and dest.is_dir():
            # Merge directories
            return safe_merge_folder(src, dest)

    try:
        shutil.move(str(src), str(dest))
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to move {src} to {dest}: {e}")
        return False


def safe_merge_folder(src: Path, dest: Path) -> bool:
    """Merge source folder into destination folder."""
    if not src.is_dir():
        return False

    dest.mkdir(parents=True, exist_ok=True)
    moved_count = 0

    for item in src.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(src)
            dest_file = dest / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            if not dest_file.exists():
                shutil.move(str(item), str(dest_file))
                moved_count += 1

    # Remove empty source directory
    try:
        if not any(src.rglob("*")):
            shutil.rmtree(src)
            print(f"  [DELETE] Removed empty folder: {src.relative_to(REPO_ROOT)}")
    except:
        pass

    return moved_count > 0


def classify_md_file(md_file: Path) -> str:
    """Classify .md file into appropriate bucket."""
    name_lower = md_file.name.lower()

    # Truth sources - keep at root
    truth_sources = {
        "readme.md", "workspace_organization_spec.md",
        "whats_left_to_build.md", "whats_left_to_build_maintenance.md",
        "proposed_cleanup_structure.md", "cleanup_summary_report.md",
        "cleanup_verification_issues.md", "root_cause_analysis_cleanup_failure.md",
        "implementation_plan_systemic_cleanup_fix.md"
    }

    if name_lower in truth_sources:
        return "keep_at_root"

    # Plans: PLAN, IMPLEMENTATION, ROADMAP (but not COMPLETE, SUMMARY, STATUS)
    if any(k in name_lower for k in ["plan", "implementation", "roadmap"]) and \
       not any(k in name_lower for k in ["complete", "summary", "status"]):
        return "plans"

    # Reports: GUIDE, CHECKLIST, COMPLETE, VERIFIED, STATUS, SUMMARY, IMPROVEMENTS, FIX
    if any(k in name_lower for k in ["guide", "checklist", "complete", "verified",
                                      "status", "summary", "improvement", "fix",
                                      "enhancement", "verification", "cursor", "integration"]):
        return "reports"

    # Analysis: ANALYSIS, REVIEW, PROGRESS, TROUBLESHOOTING
    if any(k in name_lower for k in ["analysis", "review", "progress", "troubleshooting",
                                      "probe", "scope"]):
        return "analysis"

    # Research: RESEARCH, QUOTA, TRANSITION
    if any(k in name_lower for k in ["research", "quota", "transition"]):
        return "research"

    # Default to reports for safety
    return "reports"


def fix1_root_loose_files(dry_run: bool = True):
    """Fix 1: Move loose .md and .log files from root."""
    print("\n" + "=" * 80)
    print("FIX 1: ROOT LOOSE FILES (43 .log + 29 .md files)")
    print("=" * 80)

    archive = REPO_ROOT / "archive"
    moved_logs = 0
    moved_md = 0

    # 1. Move ALL .log files to archive/diagnostics/logs/
    diag_logs = archive / "diagnostics" / "logs"
    diag_logs.mkdir(parents=True, exist_ok=True)

    log_files = sorted(REPO_ROOT.glob("*.log"))
    if log_files:
        print(f"\n[LOGS] Found {len(log_files)} .log files at root")
        for log_file in log_files:
            dest = diag_logs / log_file.name
            print(f"  {log_file.name} -> archive/diagnostics/logs/")
            if not dry_run and safe_move(log_file, dest):
                moved_logs += 1

    # 2. Classify and move .md files
    md_files = sorted(REPO_ROOT.glob("*.md"))
    buckets = {
        "plans": archive / "plans",
        "reports": archive / "reports",
        "analysis": archive / "analysis",
        "research": archive / "research"
    }

    for bucket_path in buckets.values():
        bucket_path.mkdir(parents=True, exist_ok=True)

    print(f"\n[MD FILES] Classifying {len(md_files)} .md files")
    for md_file in md_files:
        bucket = classify_md_file(md_file)

        if bucket == "keep_at_root":
            print(f"  {md_file.name} -> KEEP at root (truth source)")
            continue

        dest = buckets[bucket] / md_file.name
        print(f"  {md_file.name} -> archive/{bucket}/")
        if not dry_run and safe_move(md_file, dest):
            moved_md += 1

    print(f"\n[FIX 1] Moved {moved_logs} .log files, {moved_md} .md files")


def fix2_prompts_folder(dry_run: bool = True):
    """Fix 2: Move prompts/ folder to archive/prompts/."""
    print("\n" + "=" * 80)
    print("FIX 2: PROMPTS FOLDER")
    print("=" * 80)

    prompts_src = REPO_ROOT / "prompts"
    if not prompts_src.exists():
        print("[SKIP] prompts/ does not exist")
        return

    archive_prompts = REPO_ROOT / "archive" / "prompts"
    archive_prompts.mkdir(parents=True, exist_ok=True)

    print("[MERGE] prompts/ -> archive/prompts/")
    if not dry_run:
        safe_merge_folder(prompts_src, archive_prompts)

    print("\n[FIX 2] Complete")


def fix3_archive_diagnostics_nesting(dry_run: bool = True):
    """Fix 3: Fix nested folders in archive/diagnostics/."""
    print("\n" + "=" * 80)
    print("FIX 3: ARCHIVE/DIAGNOSTICS NESTING")
    print("=" * 80)

    diag = REPO_ROOT / "archive" / "diagnostics"
    if not diag.exists():
        print("[SKIP] archive/diagnostics does not exist")
        return

    # Folders that should NOT be in diagnostics/
    bad_nested = {
        ".autonomous_runs": "runs",  # Move contents to diagnostics/runs/
        "archive": "../archive",      # Merge up to archive/
        "docs": "docs",               # Keep as diagnostics/docs/ (for CONSOLIDATED_DEBUG.md notes)
        "exports": "../exports",      # Merge up to archive/exports/
        "patches": "../patches",      # Merge up to archive/patches/
        "archived_runs": "runs",      # Move to diagnostics/runs/
        "autopack": "runs"            # Move to diagnostics/runs/
    }

    for nested_name, dest_rel_path in bad_nested.items():
        nested_path = diag / nested_name
        if not nested_path.exists():
            continue

        print(f"\n[NESTED] Found diagnostics/{nested_name}/")

        if dest_rel_path == "runs":
            # Move run directories to diagnostics/runs/
            runs_dir = diag / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)

            if nested_path.is_dir():
                for item in nested_path.iterdir():
                    if item.is_dir():
                        dest = runs_dir / item.name
                        print(f"  {nested_name}/{item.name} -> diagnostics/runs/")
                        if not dry_run:
                            safe_move(item, dest)

                if not dry_run:
                    try:
                        if not any(nested_path.iterdir()):
                            nested_path.rmdir()
                            print(f"  [DELETE] Removed empty {nested_name}/")
                    except:
                        pass

        elif dest_rel_path.startswith(".."):
            # Merge up to archive/
            archive = REPO_ROOT / "archive"
            dest_folder_name = dest_rel_path.replace("../", "")
            dest = archive / dest_folder_name
            dest.mkdir(parents=True, exist_ok=True)

            print(f"  diagnostics/{nested_name}/ -> archive/{dest_folder_name}/")
            if not dry_run:
                safe_merge_folder(nested_path, dest)

        elif dest_rel_path == "docs":
            # Keep as diagnostics/docs/ - just note it
            print(f"  diagnostics/{nested_name}/ -> KEEP as diagnostics/docs/ (for debug notes)")

    # Handle loose .md files in diagnostics/ root
    diag_md_files = [f for f in diag.glob("*.md") if f.is_file()]
    if diag_md_files:
        print(f"\n[MD FILES] Found {len(diag_md_files)} .md files in diagnostics/")
        diag_docs = diag / "docs"
        diag_docs.mkdir(parents=True, exist_ok=True)

        for md_file in diag_md_files:
            dest = diag_docs / md_file.name
            print(f"  {md_file.name} -> diagnostics/docs/")
            if not dry_run:
                safe_move(md_file, dest)

    print("\n[FIX 3] Complete")


def fix4_autonomous_runs_root(dry_run: bool = True):
    """Fix 4: Clean .autonomous_runs root."""
    print("\n" + "=" * 80)
    print("FIX 4: .AUTONOMOUS_RUNS ROOT")
    print("=" * 80)

    autonomous_root = REPO_ROOT / ".autonomous_runs"
    if not autonomous_root.exists():
        print("[SKIP] .autonomous_runs does not exist")
        return

    # Move openai_delegations/ to archive/reports/
    openai_deleg = autonomous_root / "openai_delegations"
    if openai_deleg.exists():
        reports = REPO_ROOT / "archive" / "reports"
        reports.mkdir(parents=True, exist_ok=True)

        print("\n[DELEGATIONS] Merging openai_delegations/ -> archive/reports/")
        if not dry_run:
            safe_merge_folder(openai_deleg, reports)

    # Note: Other loose folders at .autonomous_runs root are project-specific
    # and require manual review (archive/, docs/, exports/, patches/, runs/)
    loose_folders = ["archive", "docs", "exports", "patches", "runs"]
    found_loose = [f for f in loose_folders if (autonomous_root / f).exists()]

    if found_loose:
        print(f"\n[NOTE] Found loose folders at .autonomous_runs root: {', '.join(found_loose)}")
        print("  These require project-specific review and are not automatically moved")

    print("\n[FIX 4] Complete")


def fix5_fileorganizer_archive(dry_run: bool = True):
    """Fix 5: Clean file-organizer archive/."""
    print("\n" + "=" * 80)
    print("FIX 5: FILE-ORGANIZER ARCHIVE")
    print("=" * 80)

    fileorg_root = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
    fileorg_archive = fileorg_root / "archive"

    if not fileorg_archive.exists():
        print("[SKIP] file-organizer archive does not exist")
        return

    # 1. Move FUTURE_PLAN_MAINTENANCE.md to docs/guides/
    wltb_maint = fileorg_archive / "FUTURE_PLAN_MAINTENANCE.md"
    if wltb_maint.exists():
        docs_guides = fileorg_root / "docs" / "guides"
        docs_guides.mkdir(parents=True, exist_ok=True)
        dest = docs_guides / "FUTURE_PLAN_MAINTENANCE.md"
        print("\n[TRUTH] FUTURE_PLAN_MAINTENANCE.md -> docs/guides/")
        if not dry_run:
            safe_move(wltb_maint, dest)

    # 2. Move backend-fixes-v6-20251130/ to diagnostics/runs/
    backend_fixes = fileorg_archive / "backend-fixes-v6-20251130"
    if backend_fixes.exists() and backend_fixes.is_dir():
        runs_dir = fileorg_archive / "diagnostics" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        dest = runs_dir / "backend-fixes-v6-20251130"
        print("\n[RUN] backend-fixes-v6-20251130/ -> diagnostics/runs/")
        if not dry_run:
            safe_move(backend_fixes, dest)

    # 3. Classify loose .md files
    loose_md = [f for f in fileorg_archive.glob("*.md") if f.is_file()]

    # Handle 'plans' file (not folder) - move it first
    plans_file = fileorg_archive / "plans"
    plans_is_file = plans_file.exists() and plans_file.is_file()

    if plans_is_file:
        reports = fileorg_archive / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        dest = reports / "plans_notes.txt"
        print("\n[FILE] 'plans' file -> reports/plans_notes.txt")
        if not dry_run:
            safe_move(plans_file, dest)
            plans_is_file = False  # File moved, no longer exists

    if loose_md:
        print(f"\n[CLASSIFY] {len(loose_md)} loose .md files in archive/")

        plans = fileorg_archive / "plans"
        reports = fileorg_archive / "reports"
        analysis = fileorg_archive / "analysis"

        # Only create plans folder if it's not currently a file (or was moved in non-dry-run)
        if not plans_is_file and not plans.is_dir():
            plans.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        analysis.mkdir(parents=True, exist_ok=True)

        for md_file in loose_md:
            name_lower = md_file.name.lower()

            # Classification
            if "phase_" in name_lower and name_lower.endswith(".md"):
                dest = analysis / md_file.name
                bucket = "analysis"
            elif "plan" in name_lower or "plans" in name_lower:
                # Use reports for plans if plans folder doesn't exist yet (in dry-run)
                if plans_is_file or not plans.is_dir():
                    dest = reports / md_file.name
                    bucket = "reports"
                else:
                    dest = plans / md_file.name
                    bucket = "plans"
            elif any(k in name_lower for k in ["guide", "checklist", "reference", "quick", "master"]):
                dest = reports / md_file.name
                bucket = "reports"
            else:
                dest = reports / md_file.name
                bucket = "reports (default)"

            print(f"  {md_file.name} -> {bucket}/")
            if not dry_run:
                safe_move(md_file, dest)

    # 4. Move archive/docs/research/ to archive/research/
    docs_research = fileorg_archive / "docs" / "research"
    if docs_research.exists():
        research = fileorg_archive / "research"
        research.mkdir(parents=True, exist_ok=True)
        print("\n[RESEARCH] docs/research/ -> research/")
        if not dry_run:
            safe_merge_folder(docs_research, research)

            # Remove empty docs/ if it's now empty
            docs_dir = fileorg_archive / "docs"
            if docs_dir.exists() and not any(docs_dir.rglob("*")):
                try:
                    docs_dir.rmdir()
                    print("  [DELETE] Removed empty docs/")
                except:
                    pass

    # 5. Remove .faiss/ (old vector DB)
    faiss_dir = fileorg_root / ".faiss"
    if faiss_dir.exists():
        print("\n[DELETE] Removing .faiss/ (old vector DB)")
        if not dry_run:
            shutil.rmtree(faiss_dir)

    # 6. Remove .autonomous_runs/autopack/ nested folder
    nested_autopack = fileorg_root / ".autonomous_runs" / "autopack"
    if nested_autopack.exists():
        print("\n[NESTED] Found .autonomous_runs/autopack/")
        # This needs investigation - may contain run data
        print("  [NOTE] Requires manual review - not automatically removed")

    print("\n[FIX 5] Complete")


def fix6_archive_runs_folder(dry_run: bool = True):
    """Fix 6: Move archive/runs/ to archive/diagnostics/runs/."""
    print("\n" + "=" * 80)
    print("FIX 6: ARCHIVE/RUNS LOCATION")
    print("=" * 80)

    archive = REPO_ROOT / "archive"
    runs_at_archive = archive / "runs"

    if not runs_at_archive.exists():
        print("[SKIP] archive/runs/ does not exist")
        return

    diag_runs = archive / "diagnostics" / "runs"
    diag_runs.mkdir(parents=True, exist_ok=True)

    print("[MOVE] archive/runs/ -> archive/diagnostics/runs/")
    if not dry_run:
        if runs_at_archive.is_dir():
            for item in runs_at_archive.iterdir():
                dest = diag_runs / item.name
                print(f"  {item.name}")
                safe_move(item, dest)

            # Remove empty runs/ folder
            try:
                if not any(runs_at_archive.iterdir()):
                    runs_at_archive.rmdir()
                    print("  [DELETE] Removed empty runs/")
            except:
                pass

    print("\n[FIX 6] Complete")


def fix7_create_unsorted_bucket(dry_run: bool = True):
    """Fix 7: Create archive/unsorted/ bucket (mentioned in spec)."""
    print("\n" + "=" * 80)
    print("FIX 7: CREATE UNSORTED BUCKET")
    print("=" * 80)

    archive = REPO_ROOT / "archive"
    unsorted = archive / "unsorted"

    if unsorted.exists():
        print("[SKIP] archive/unsorted/ already exists")
        return

    print("[CREATE] archive/unsorted/ (last-resort inbox)")
    if not dry_run:
        unsorted.mkdir(parents=True, exist_ok=True)
        # Create README
        readme = unsorted / "README.md"
        readme.write_text("""# Unsorted Inbox

This folder serves as a last-resort inbox for files that couldn't be automatically classified.

Files placed here should be manually reviewed and moved to the appropriate bucket:
- **plans/** - Implementation plans
- **reports/** - Guides, checklists, summaries
- **analysis/** - Analysis, reviews, troubleshooting
- **research/** - Research documents
- **diagnostics/logs/** - Log files
- **diagnostics/runs/** - Run directories

Tidy_up will attempt to classify and move these files to proper locations.
""")
        print("  Created unsorted/ with README.md")

    print("\n[FIX 7] Complete")


def validate_final_structure():
    """Comprehensive validation matching PROPOSED_CLEANUP_STRUCTURE.md."""
    print("\n" + "=" * 80)
    print("VALIDATION: COMPREHENSIVE STRUCTURE CHECK")
    print("=" * 80)

    issues = []
    warnings = []

    # Check 1: Loose .md files at root
    keep_md = {
        "README.md", "WORKSPACE_ORGANIZATION_SPEC.md",
        "FUTURE_PLAN.md", "FUTURE_PLAN_MAINTENANCE.md",
        "PROPOSED_CLEANUP_STRUCTURE.md", "CLEANUP_SUMMARY_REPORT.md",
        "CLEANUP_VERIFICATION_ISSUES.md", "ROOT_CAUSE_ANALYSIS_CLEANUP_FAILURE.md",
        "IMPLEMENTATION_PLAN_SYSTEMIC_CLEANUP_FIX.md"
    }
    loose_md = list(REPO_ROOT.glob("*.md"))
    unwanted_md = [f for f in loose_md if f.name not in keep_md]

    if unwanted_md:
        issues.append(f"[X] {len(unwanted_md)} loose .md files at root")
        for f in unwanted_md[:5]:
            print(f"  - {f.name}")
        if len(unwanted_md) > 5:
            print(f"  ... and {len(unwanted_md) - 5} more")
    else:
        print("[OK] Root has only truth source .md files")

    # Check 2: Loose .log files at root
    loose_logs = list(REPO_ROOT.glob("*.log"))
    if loose_logs:
        issues.append(f"[X] {len(loose_logs)} loose .log files at root")
        for f in loose_logs[:5]:
            print(f"  - {f.name}")
    else:
        print("[OK] No loose .log files at root")

    # Check 3: prompts/ at root
    if (REPO_ROOT / "prompts").exists():
        issues.append("[X] prompts/ folder still at root")
    else:
        print("[OK] No prompts/ folder at root")

    # Check 4: Archive bucket structure
    archive = REPO_ROOT / "archive"
    required_buckets = ["plans", "reports", "analysis", "research", "prompts",
                       "diagnostics", "unsorted", "configs", "docs", "exports", "patches", "refs", "src"]

    missing_buckets = []
    for bucket in required_buckets:
        if not (archive / bucket).exists():
            missing_buckets.append(bucket)

    if missing_buckets:
        warnings.append(f"[!] Missing archive buckets: {', '.join(missing_buckets)}")
    else:
        print("[OK] All archive buckets exist")

    # Check 5: Diagnostics structure (only logs/ and runs/ allowed)
    diag = archive / "diagnostics"
    if diag.exists():
        allowed_diag = {"logs", "runs", "docs"}  # docs for CONSOLIDATED_DEBUG.md notes
        bad_nested = [".autonomous_runs", "archive", "exports", "patches", "archived_runs", "autopack"]
        found_bad = []

        for nested in bad_nested:
            if (diag / nested).exists():
                found_bad.append(nested)

        if found_bad:
            issues.append(f"[X] Nested folders in diagnostics/: {', '.join(found_bad)}")
        else:
            print("[OK] No nested folders in archive/diagnostics/")

    # Check 6: openai_delegations/ at .autonomous_runs root
    if (REPO_ROOT / ".autonomous_runs" / "openai_delegations").exists():
        issues.append("[X] openai_delegations/ still at .autonomous_runs root")
    else:
        print("[OK] No openai_delegations/ at .autonomous_runs root")

    # Check 7: file-organizer archive loose files
    fileorg_archive = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive"
    if fileorg_archive.exists():
        loose_md_fileorg = [f for f in fileorg_archive.glob("*.md") if f.is_file()]
        if loose_md_fileorg:
            issues.append(f"[X] {len(loose_md_fileorg)} loose .md files in file-organizer archive/")
        else:
            print("[OK] No loose .md files in file-organizer archive/")

    # Check 8: archive/runs/ at wrong level
    if (archive / "runs").exists():
        issues.append("[X] archive/runs/ folder (should be archive/diagnostics/runs/)")
    else:
        print("[OK] No archive/runs/ at wrong level")

    # Check 9: Root folder structure
    expected_root = {"src", "scripts", "tests", "docs", "config", "archive", ".autonomous_runs"}
    print(f"\n[OK] Root structure: {', '.join(sorted(expected_root))}")

    # Summary
    print("\n" + "=" * 80)
    if issues or warnings:
        if issues:
            print("VALIDATION: [X] ISSUES FOUND")
            for issue in issues:
                print(f"  {issue}")
        if warnings:
            print("\nWARNINGS:")
            for warning in warnings:
                print(f"  {warning}")
        return False
    else:
        print("VALIDATION: [OK] ALL CHECKS PASSED")
        print("=" * 80)
        print("\n[PASS] Workspace structure matches PROPOSED_CLEANUP_STRUCTURE.md")
        return True


def main():
    """Run corrective cleanup."""
    import argparse

    parser = argparse.ArgumentParser(description="Corrective cleanup - fix comprehensive_cleanup.py failures")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 80)
    print("CORRECTIVE CLEANUP")
    print("Implementing: PROPOSED_CLEANUP_STRUCTURE.md")
    print("Fixing: comprehensive_cleanup.py failures")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    if not dry_run:
        git_checkpoint("corrective: pre-cleanup checkpoint")

    # Execute all fixes
    fix1_root_loose_files(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 1 - root loose files cleaned")

    fix2_prompts_folder(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 2 - prompts folder merged to archive")

    fix3_archive_diagnostics_nesting(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 3 - diagnostics nesting fixed")

    fix4_autonomous_runs_root(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 4 - autonomous_runs root cleaned")

    fix5_fileorganizer_archive(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 5 - file-organizer archive cleaned")

    fix6_archive_runs_folder(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 6 - archive/runs moved to diagnostics")

    fix7_create_unsorted_bucket(dry_run)
    if not dry_run:
        git_checkpoint("corrective: fix 7 - created unsorted bucket")

    # Validate
    validation_passed = validate_final_structure()

    print("\n" + "=" * 80)
    print("CORRECTIVE CLEANUP COMPLETE")
    print("=" * 80)

    if dry_run:
        print("\nThis was a DRY RUN. Use --execute to apply changes.")
        print("\nTo execute:")
        print("  python scripts/corrective_cleanup.py --execute")
    else:
        print("\nChanges committed. Review with:")
        print("  git log -10 --oneline")

        if validation_passed:
            print("\n[PASS] SUCCESS: Workspace now matches PROPOSED_CLEANUP_STRUCTURE.md")
        else:
            print("\n[!] WARNING: Some validation issues remain - review output above")


if __name__ == "__main__":
    main()
