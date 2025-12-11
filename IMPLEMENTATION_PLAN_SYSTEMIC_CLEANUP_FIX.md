# Implementation Plan: Systemic Cleanup Fix for Autopack Tidy Up

**Date:** 2025-12-11
**Purpose:** Fix workspace cleanup to integrate with existing Autopack tidy infrastructure
**Reference:** [ROOT_CAUSE_ANALYSIS_CLEANUP_FAILURE.md](ROOT_CAUSE_ANALYSIS_CLEANUP_FAILURE.md)

---

## Overview

This plan addresses the root causes of cleanup failure by:
1. Creating a **corrective cleanup** that leverages tidy_workspace.py
2. Adding **comprehensive validation** to catch misplaced files
3. Enhancing **tidy_workspace.py** to handle nested folders and diagnostics
4. Integrating **cleanup into autonomous run lifecycle**

---

## Phase 1: Immediate Corrective Cleanup

### Goal
Fix the current workspace mess using existing Autopack tidy infrastructure.

### Files to Create

#### 1.1: `scripts/corrective_cleanup.py`

**Purpose:** Clean up the 72+ loose files using tidy_workspace.py

```python
#!/usr/bin/env python3
"""
Corrective Cleanup - Fix comprehensive_cleanup.py failures

This script:
1. Uses tidy_workspace.py to classify and move loose files
2. Fixes archive/diagnostics/ nesting issues
3. Moves openai_delegations/ to reports/
4. Validates final structure
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backend.tidy_workspace import tidy_workspace
from backend.file_mover import safe_move, safe_merge_folder

REPO_ROOT = Path(__file__).parent.parent

def fix_root_loose_files(dry_run=True):
    """Use tidy_workspace to classify and move loose .md and .log files."""
    print("\n" + "=" * 80)
    print("FIX 1: ROOT LOOSE FILES")
    print("=" * 80)

    # Truth sources to keep at root
    keep_at_root = {
        "README.md",
        "WORKSPACE_ORGANIZATION_SPEC.md",
        "WHATS_LEFT_TO_BUILD.md",
        "WHATS_LEFT_TO_BUILD_MAINTENANCE.md",
        "PROPOSED_CLEANUP_STRUCTURE.md",
        "CLEANUP_SUMMARY_REPORT.md",
        "CLEANUP_VERIFICATION_ISSUES.md",
        "ROOT_CAUSE_ANALYSIS_CLEANUP_FAILURE.md",
        "IMPLEMENTATION_PLAN_SYSTEMIC_CLEANUP_FIX.md",
    }

    archive = REPO_ROOT / "archive"
    diag_logs = archive / "diagnostics" / "logs"
    diag_logs.mkdir(parents=True, exist_ok=True)

    # Move ALL .log files to archive/diagnostics/logs/
    log_files = list(REPO_ROOT.glob("*.log"))
    if log_files:
        print(f"\n[LOGS] Moving {len(log_files)} .log files to archive/diagnostics/logs/")
        for log_file in log_files:
            dest = diag_logs / log_file.name
            print(f"  {log_file.name} → archive/diagnostics/logs/")
            if not dry_run:
                safe_move(log_file, dest)

    # Classify and move .md files
    md_files = list(REPO_ROOT.glob("*.md"))
    classify_needed = [f for f in md_files if f.name not in keep_at_root]

    if classify_needed:
        print(f"\n[CLASSIFY] {len(classify_needed)} .md files need classification")

        # Classification buckets
        plans_bucket = archive / "plans"
        reports_bucket = archive / "reports"
        analysis_bucket = archive / "analysis"

        plans_bucket.mkdir(parents=True, exist_ok=True)
        reports_bucket.mkdir(parents=True, exist_ok=True)
        analysis_bucket.mkdir(parents=True, exist_ok=True)

        for md_file in classify_needed:
            content = md_file.read_text(encoding="utf-8", errors="ignore").lower()
            name_lower = md_file.name.lower()

            # Classification logic
            if any(keyword in name_lower for keyword in ["plan", "implementation", "roadmap"]) and \
               not any(keyword in name_lower for keyword in ["complete", "summary", "status"]):
                dest = plans_bucket / md_file.name
                bucket = "plans"
            elif any(keyword in name_lower for keyword in ["guide", "checklist", "complete", "verified", "summary", "improvement", "fix", "enhancement"]):
                dest = reports_bucket / md_file.name
                bucket = "reports"
            elif any(keyword in name_lower for keyword in ["analysis", "review", "progress", "probe"]):
                dest = analysis_bucket / md_file.name
                bucket = "analysis"
            else:
                # Default to reports for safety
                dest = reports_bucket / md_file.name
                bucket = "reports (default)"

            print(f"  {md_file.name} → archive/{bucket}/")
            if not dry_run:
                safe_move(md_file, dest)

    print(f"\n[FIX 1] Complete")


def fix_prompts_folder(dry_run=True):
    """Move prompts/ folder to archive/prompts/."""
    print("\n" + "=" * 80)
    print("FIX 2: PROMPTS FOLDER")
    print("=" * 80)

    prompts_src = REPO_ROOT / "prompts"
    if not prompts_src.exists():
        print("[SKIP] prompts/ does not exist")
        return

    # Check if it's a folder with files or just links
    if prompts_src.is_dir():
        archive_prompts = REPO_ROOT / "archive" / "prompts"
        archive_prompts.mkdir(parents=True, exist_ok=True)

        print(f"[MERGE] prompts/ → archive/prompts/")
        if not dry_run:
            safe_merge_folder(prompts_src, archive_prompts)

    print(f"\n[FIX 2] Complete")


def fix_archive_diagnostics_nesting(dry_run=True):
    """Fix nested folders in archive/diagnostics/."""
    print("\n" + "=" * 80)
    print("FIX 3: ARCHIVE/DIAGNOSTICS NESTING")
    print("=" * 80)

    diag = REPO_ROOT / "archive" / "diagnostics"
    if not diag.exists():
        print("[SKIP] archive/diagnostics does not exist")
        return

    # Nested folders that should NOT be in diagnostics/
    bad_nested = [".autonomous_runs", "archive", "docs", "exports", "patches"]

    for nested_name in bad_nested:
        nested_path = diag / nested_name
        if not nested_path.exists():
            continue

        print(f"\n[NESTED] Found diagnostics/{nested_name}/ - moving to archive/")

        if nested_name == ".autonomous_runs":
            # This contains run directories - move to diagnostics/runs/
            runs_dir = diag / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)

            if nested_path.is_dir():
                for run_dir in nested_path.iterdir():
                    if run_dir.is_dir():
                        dest = runs_dir / run_dir.name
                        print(f"  {nested_name}/{run_dir.name} → diagnostics/runs/")
                        if not dry_run:
                            safe_move(run_dir, dest)
                if not dry_run:
                    # Remove empty nested folder
                    try:
                        nested_path.rmdir()
                    except:
                        pass

        else:
            # Move to appropriate location in archive/
            archive = REPO_ROOT / "archive"
            dest = archive / nested_name
            dest.mkdir(parents=True, exist_ok=True)

            print(f"  diagnostics/{nested_name}/ → archive/{nested_name}/")
            if not dry_run:
                safe_merge_folder(nested_path, dest)

    # Handle loose .md files in diagnostics/
    diag_md_files = list(diag.glob("*.md"))
    if diag_md_files:
        print(f"\n[MD FILES] Found {len(diag_md_files)} .md files in diagnostics/")
        diag_docs = diag / "docs"
        diag_docs.mkdir(parents=True, exist_ok=True)

        for md_file in diag_md_files:
            dest = diag_docs / md_file.name
            print(f"  {md_file.name} → diagnostics/docs/")
            if not dry_run:
                safe_move(md_file, dest)

    print(f"\n[FIX 3] Complete")


def fix_autonomous_runs_root(dry_run=True):
    """Fix loose folders at .autonomous_runs root."""
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

        print(f"\n[DELEGATIONS] Merging openai_delegations/ → archive/reports/")
        if not dry_run:
            safe_merge_folder(openai_deleg, reports)

    # Note: Other loose folders (archive/, docs/, exports/, patches/, runs/)
    # require project-specific analysis - will be handled by tidy_workspace

    print(f"\n[FIX 4] Complete")


def fix_fileorganizer_archive(dry_run=True):
    """Fix loose files in file-organizer archive/."""
    print("\n" + "=" * 80)
    print("FIX 5: FILE-ORGANIZER ARCHIVE")
    print("=" * 80)

    fileorg_archive = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive"
    if not fileorg_archive.exists():
        print("[SKIP] file-organizer archive does not exist")
        return

    # Move WHATS_LEFT_TO_BUILD_MAINTENANCE.md to docs/guides/
    wltb_maint = fileorg_archive / "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"
    if wltb_maint.exists():
        docs_guides = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "guides"
        docs_guides.mkdir(parents=True, exist_ok=True)
        dest = docs_guides / "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"
        print(f"\n[TRUTH] WHATS_LEFT_TO_BUILD_MAINTENANCE.md → docs/guides/")
        if not dry_run:
            safe_move(wltb_maint, dest)

    # Move backend-fixes-v6-20251130/ to diagnostics/runs/
    backend_fixes = fileorg_archive / "backend-fixes-v6-20251130"
    if backend_fixes.exists() and backend_fixes.is_dir():
        runs_dir = fileorg_archive / "diagnostics" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        dest = runs_dir / "backend-fixes-v6-20251130"
        print(f"\n[RUN] backend-fixes-v6-20251130/ → diagnostics/runs/")
        if not dry_run:
            safe_move(backend_fixes, dest)

    # Classify loose .md files
    loose_md = [f for f in fileorg_archive.glob("*.md") if f.is_file()]
    if loose_md:
        print(f"\n[CLASSIFY] {len(loose_md)} loose .md files in archive/")

        plans = fileorg_archive / "plans"
        reports = fileorg_archive / "reports"
        analysis = fileorg_archive / "analysis"

        plans.mkdir(parents=True, exist_ok=True)
        reports.mkdir(parents=True, exist_ok=True)
        analysis.mkdir(parents=True, exist_ok=True)

        for md_file in loose_md:
            name_lower = md_file.name.lower()

            # Classification
            if "phase_" in name_lower:
                dest = analysis / md_file.name
                bucket = "analysis"
            elif any(k in name_lower for k in ["plan", "master"]):
                dest = reports / md_file.name
                bucket = "reports"
            elif any(k in name_lower for k in ["guide", "checklist", "reference", "quick"]):
                dest = reports / md_file.name
                bucket = "reports"
            else:
                dest = reports / md_file.name
                bucket = "reports (default)"

            print(f"  {md_file.name} → {bucket}/")
            if not dry_run:
                safe_move(md_file, dest)

    # Move archive/docs/research/ to archive/research/
    docs_research = fileorg_archive / "docs" / "research"
    if docs_research.exists():
        research = fileorg_archive / "research"
        research.mkdir(parents=True, exist_ok=True)
        print(f"\n[RESEARCH] docs/research/ → research/")
        if not dry_run:
            safe_merge_folder(docs_research, research)

    # Remove .faiss/ if exists
    faiss_dir = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / ".faiss"
    if faiss_dir.exists():
        print(f"\n[DELETE] Removing .faiss/ (old vector DB)")
        if not dry_run:
            import shutil
            shutil.rmtree(faiss_dir)

    print(f"\n[FIX 5] Complete")


def validate_final_structure():
    """Comprehensive validation of final structure."""
    print("\n" + "=" * 80)
    print("VALIDATION: COMPREHENSIVE STRUCTURE CHECK")
    print("=" * 80)

    issues = []

    # Check 1: Loose .md files at root
    keep_md = {
        "README.md", "WORKSPACE_ORGANIZATION_SPEC.md",
        "WHATS_LEFT_TO_BUILD.md", "WHATS_LEFT_TO_BUILD_MAINTENANCE.md",
        "PROPOSED_CLEANUP_STRUCTURE.md", "CLEANUP_SUMMARY_REPORT.md",
        "CLEANUP_VERIFICATION_ISSUES.md", "ROOT_CAUSE_ANALYSIS_CLEANUP_FAILURE.md",
        "IMPLEMENTATION_PLAN_SYSTEMIC_CLEANUP_FIX.md"
    }
    loose_md = list(REPO_ROOT.glob("*.md"))
    unwanted_md = [f for f in loose_md if f.name not in keep_md]
    if unwanted_md:
        issues.append(f"✗ {len(unwanted_md)} loose .md files at root")
        for f in unwanted_md[:5]:
            print(f"  - {f.name}")
    else:
        print("✓ No loose .md files at root (only truth sources)")

    # Check 2: Loose .log files at root
    loose_logs = list(REPO_ROOT.glob("*.log"))
    if loose_logs:
        issues.append(f"✗ {len(loose_logs)} loose .log files at root")
        for f in loose_logs[:5]:
            print(f"  - {f.name}")
    else:
        print("✓ No loose .log files at root")

    # Check 3: prompts/ at root
    if (REPO_ROOT / "prompts").exists():
        issues.append("✗ prompts/ folder still at root")
    else:
        print("✓ No prompts/ folder at root")

    # Check 4: openai_delegations/ at .autonomous_runs root
    if (REPO_ROOT / ".autonomous_runs" / "openai_delegations").exists():
        issues.append("✗ openai_delegations/ still at .autonomous_runs root")
    else:
        print("✓ No openai_delegations/ at .autonomous_runs root")

    # Check 5: Nested folders in archive/diagnostics/
    diag = REPO_ROOT / "archive" / "diagnostics"
    if diag.exists():
        bad_nested = [".autonomous_runs", "archive", "docs", "exports", "patches"]
        for nested in bad_nested:
            if (diag / nested).exists():
                issues.append(f"✗ Nested {nested}/ in archive/diagnostics/")
        if not any(f"✗ Nested" in issue for issue in issues):
            print("✓ No nested folders in archive/diagnostics/")

    # Check 6: Loose .md files in file-organizer archive/
    fileorg_archive = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive"
    if fileorg_archive.exists():
        loose_md_fileorg = [f for f in fileorg_archive.glob("*.md") if f.is_file()]
        if loose_md_fileorg:
            issues.append(f"✗ {len(loose_md_fileorg)} loose .md files in file-organizer archive/")
        else:
            print("✓ No loose .md files in file-organizer archive/")

    print("\n" + "=" * 80)
    if issues:
        print("VALIDATION: ✗ ISSUES FOUND")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("VALIDATION: ✓ ALL CHECKS PASSED")
        return True
    print("=" * 80)


def main():
    """Run corrective cleanup."""
    import argparse

    parser = argparse.ArgumentParser(description="Corrective cleanup using tidy infrastructure")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 80)
    print("CORRECTIVE CLEANUP")
    print("Fixing comprehensive_cleanup.py failures")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()

    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: pre-cleanup checkpoint")

    # Execute all fixes
    fix_root_loose_files(dry_run)
    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: fix 1 - root loose files cleaned")

    fix_prompts_folder(dry_run)
    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: fix 2 - prompts folder moved")

    fix_archive_diagnostics_nesting(dry_run)
    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: fix 3 - diagnostics nesting fixed")

    fix_autonomous_runs_root(dry_run)
    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: fix 4 - autonomous_runs root cleaned")

    fix_fileorganizer_archive(dry_run)
    if not dry_run:
        from backend.git_operations import git_checkpoint
        git_checkpoint(REPO_ROOT, "corrective: fix 5 - file-organizer archive cleaned")

    # Validate
    validate_final_structure()

    print("\n" + "=" * 80)
    print("CORRECTIVE CLEANUP COMPLETE")
    print("=" * 80)

    if dry_run:
        print("\nThis was a DRY RUN. Use --execute to apply changes.")
    else:
        print("\nChanges committed. Review with: git log -7 --oneline")


if __name__ == "__main__":
    main()
```

**Dependencies:**
- Need to check if `file_mover.py` exists with `safe_move()` and `safe_merge_folder()`
- Need to check if `git_operations.py` exists with `git_checkpoint()`
- May need to create these utilities

---

## Phase 2: Enhance Existing Tidy Infrastructure

### Goal
Make tidy_workspace.py capable of handling workspace cleanup scenarios.

### Files to Modify

#### 2.1: `src/backend/file_mover.py` (Create if doesn't exist)

**Purpose:** Safe file/folder operations with validation

```python
from pathlib import Path
import shutil
from typing import Union

def safe_move(src: Path, dest: Path, overwrite: bool = False) -> bool:
    """Safely move file/folder with validation."""
    if not src.exists():
        raise FileNotFoundError(f"Source does not exist: {src}")

    if dest.exists() and not overwrite:
        # File exists, merge or skip
        if src.is_dir() and dest.is_dir():
            # Merge directories
            return safe_merge_folder(src, dest)
        else:
            # Skip file that exists
            return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return True


def safe_merge_folder(src: Path, dest: Path) -> bool:
    """Merge source folder into destination folder."""
    if not src.is_dir():
        raise ValueError(f"Source is not a directory: {src}")

    dest.mkdir(parents=True, exist_ok=True)

    for item in src.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(src)
            dest_file = dest / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            if not dest_file.exists():
                shutil.move(str(item), str(dest_file))
            else:
                # File exists at destination, skip or handle conflict
                pass

    # Remove empty source directory
    try:
        shutil.rmtree(src)
    except:
        pass

    return True
```

#### 2.2: `src/backend/workspace_validator.py` (New)

**Purpose:** Comprehensive workspace validation

```python
from pathlib import Path
from typing import List, Dict

class WorkspaceValidator:
    """Validates workspace structure against WORKSPACE_ORGANIZATION_SPEC.md."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.issues = []

    def validate_root_cleanliness(self) -> List[str]:
        """Check root has ≤5 .md files and 0 .log files."""
        issues = []

        # Truth sources allowed at root
        keep_md = {
            "README.md", "WORKSPACE_ORGANIZATION_SPEC.md",
            "WHATS_LEFT_TO_BUILD.md", "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"
        }

        loose_md = list(self.repo_root.glob("*.md"))
        unwanted_md = [f for f in loose_md if f.name not in keep_md]
        if unwanted_md:
            issues.append(f"Found {len(unwanted_md)} loose .md files at root")

        loose_logs = list(self.repo_root.glob("*.log"))
        if loose_logs:
            issues.append(f"Found {len(loose_logs)} loose .log files at root")

        return issues

    def validate_archive_structure(self) -> List[str]:
        """Check archive has correct bucket structure."""
        issues = []

        archive = self.repo_root / "archive"
        if not archive.exists():
            issues.append("archive/ folder does not exist")
            return issues

        required_buckets = [
            "plans", "reports", "analysis", "research",
            "prompts", "diagnostics", "configs", "docs",
            "exports", "patches", "refs", "src"
        ]

        for bucket in required_buckets:
            if not (archive / bucket).exists():
                issues.append(f"Missing archive/{bucket}/ folder")

        return issues

    def validate_diagnostics_structure(self) -> List[str]:
        """Check diagnostics only has logs/ and runs/."""
        issues = []

        diag = self.repo_root / "archive" / "diagnostics"
        if not diag.exists():
            return issues

        allowed = {"logs", "runs", "docs"}  # docs for CONSOLIDATED_DEBUG.md notes
        bad_nested = [".autonomous_runs", "archive", "exports", "patches"]

        for item in diag.iterdir():
            if item.is_dir() and item.name in bad_nested:
                issues.append(f"Nested {item.name}/ in archive/diagnostics/")

        return issues

    def validate_no_nested_folders(self) -> List[str]:
        """Check no archive/archive/, etc."""
        issues = []

        # Check archive/ for nesting
        archive = self.repo_root / "archive"
        if archive.exists():
            if (archive / "archive").exists():
                issues.append("Nested archive/archive/ found")
            if (archive / ".autonomous_runs").exists():
                issues.append("Nested archive/.autonomous_runs/ found")

        return issues

    def full_validation(self) -> List[str]:
        """Run all validations."""
        all_issues = []
        all_issues.extend(self.validate_root_cleanliness())
        all_issues.extend(self.validate_archive_structure())
        all_issues.extend(self.validate_diagnostics_structure())
        all_issues.extend(self.validate_no_nested_folders())
        return all_issues
```

---

## Phase 3: Integration with Autonomous Runs

### Goal
Automatically clean up after autonomous runs complete.

### Files to Modify

#### 3.1: `src/backend/autonomous_executor.py`

**Add method:**
```python
def post_run_cleanup(self):
    """Clean up workspace after run completes."""
    from backend.tidy_workspace import tidy_workspace
    from backend.workspace_validator import WorkspaceValidator

    # Tidy workspace
    tidy_workspace(
        target_dir=self.project_root,
        scope="workspace",
        dry_run=False
    )

    # Validate
    validator = WorkspaceValidator(self.project_root)
    issues = validator.full_validation()

    if issues:
        self.logger.warning(f"Post-run cleanup validation found issues: {issues}")
    else:
        self.logger.info("Post-run cleanup validation passed")
```

---

## Phase 4: Documentation Updates

### Goal
Document the new cleanup workflow.

### Files to Update

#### 4.1: `WORKSPACE_ORGANIZATION_SPEC.md`

Add section:
```markdown
## Cleanup Workflow

### Corrective Cleanup

For one-time workspace reorganization:
\`\`\`bash
python scripts/corrective_cleanup.py --execute
\`\`\`

### Ongoing Maintenance

Autopack tidy_up automatically maintains workspace structure:
\`\`\`bash
python -m backend.autonomous_executor --scope workspace
\`\`\`

### Validation

Check workspace structure:
\`\`\`python
from backend.workspace_validator import WorkspaceValidator

validator = WorkspaceValidator(Path.cwd())
issues = validator.full_validation()

if issues:
    print("Issues found:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("✓ Workspace structure validated")
\`\`\`
```

---

## Implementation Steps

### Step 1: Create Utility Functions
1. Create `src/backend/file_mover.py` with safe move/merge functions
2. Test file operations in isolation

### Step 2: Create Corrective Cleanup
1. Create `scripts/corrective_cleanup.py` with all 5 fixes
2. Run in dry-run mode to verify logic
3. Execute with `--execute` flag

### Step 3: Create Workspace Validator
1. Create `src/backend/workspace_validator.py`
2. Add comprehensive validation checks
3. Test against current (messy) workspace

### Step 4: Test Corrective Cleanup
1. Run `corrective_cleanup.py --dry-run`
2. Review planned changes
3. Run `corrective_cleanup.py --execute`
4. Verify final structure with validator

### Step 5: Integrate with Tidy System
1. Enhance `tidy_workspace.py` to use validator
2. Add post-run cleanup to autonomous_executor.py
3. Test with small autonomous run

### Step 6: Documentation
1. Update WORKSPACE_ORGANIZATION_SPEC.md
2. Add cleanup workflow guide
3. Document validator usage

---

## Testing Plan

### Test 1: Corrective Cleanup Dry Run
```bash
python scripts/corrective_cleanup.py --dry-run > dry_run.log
```

**Expected Output:**
- Lists all 72+ files to be moved
- Shows classification decisions
- No actual file moves

### Test 2: Corrective Cleanup Execute
```bash
python scripts/corrective_cleanup.py --execute
```

**Expected Output:**
- Moves all loose .md files to appropriate buckets
- Moves all .log files to archive/diagnostics/logs/
- Fixes archive/diagnostics/ nesting
- Moves openai_delegations/
- Cleans file-organizer archive/
- Git commits for each fix
- Final validation passes

### Test 3: Workspace Validator
```python
from pathlib import Path
from src.backend.workspace_validator import WorkspaceValidator

validator = WorkspaceValidator(Path.cwd())
issues = validator.full_validation()

assert len(issues) == 0, f"Validation failed: {issues}"
```

---

## Success Criteria

### Immediate (After Corrective Cleanup):
- ✅ Root has ≤5 .md files (only truth sources)
- ✅ Root has 0 .log files
- ✅ No prompts/ folder at root
- ✅ No openai_delegations/ at .autonomous_runs root
- ✅ No nested folders in archive/diagnostics/
- ✅ No loose files in file-organizer archive/
- ✅ WorkspaceValidator reports 0 issues

### Long-Term (After Integration):
- ✅ Autonomous runs automatically clean up after themselves
- ✅ Workspace stays organized over time
- ✅ No manual cleanup needed
- ✅ Validation runs as part of CI/CD

---

## Rollback Plan

If corrective cleanup fails:

1. **Git rollback:**
   ```bash
   git log --oneline -10  # Find pre-cleanup commit
   git reset --hard <commit-hash>
   ```

2. **Manual inspection:**
   - Check what files were moved incorrectly
   - Review git diff to see changes

3. **Selective restoration:**
   ```bash
   git checkout <commit-hash> -- path/to/file
   ```

---

## Timeline Estimate

- **Phase 1 (Corrective Cleanup):** 2-3 hours
  - Create file_mover.py: 30 mins
  - Create corrective_cleanup.py: 1 hour
  - Test and execute: 1 hour

- **Phase 2 (Enhance Infrastructure):** 1-2 hours
  - Create workspace_validator.py: 1 hour
  - Test validation: 30 mins

- **Phase 3 (Integration):** 1 hour
  - Add post-run cleanup: 30 mins
  - Test integration: 30 mins

- **Phase 4 (Documentation):** 30 mins

**Total:** 4.5-6.5 hours

---

## Next Steps

1. **Immediate:** Run corrective cleanup to fix current workspace
2. **Short-term:** Create workspace validator for ongoing validation
3. **Long-term:** Integrate cleanup into autonomous run lifecycle

---

**Generated:** 2025-12-11
**Status:** Ready for Implementation
**Priority:** HIGH (workspace is currently 40% organized)
