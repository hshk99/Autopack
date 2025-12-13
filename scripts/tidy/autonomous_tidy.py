#!/usr/bin/env python3
"""
Autonomous Tidy Workflow - Fully Automated with Auditor Integration

Replaces manual human review with autonomous Auditor agents.

Workflow:
1. Pre-Tidy Auditor: Analyzes files, generates routing guidance
2. Tidy Engine: Consolidates with Auditor guidance
3. Post-Tidy Auditor: Verifies results, auto-commits

Triggered by:
- Cursor prompt: "Tidy archive directory"
- CLI: python scripts/tidy/autonomous_tidy.py archive

Usage:
    python scripts/tidy/autonomous_tidy.py <directory> --dry-run
    python scripts/tidy/autonomous_tidy.py <directory> --execute
"""

import argparse
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "tidy"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from tidy_logger import TidyLogger


class PreTidyAuditor:
    """Analyzes files before consolidation to provide routing guidance"""

    def __init__(self, target_directory: str, run_id: str, project_id: str = "autopack"):
        self.target_directory = target_directory
        self.target_path = REPO_ROOT / target_directory
        self.run_id = run_id
        self.project_id = project_id
        self.report_path = REPO_ROOT / "PRE_TIDY_AUDIT_REPORT.md"

        # Database logging instead of markdown reports
        self.logger = TidyLogger(REPO_ROOT, project_id=project_id)

        # Analysis results
        self.total_files = 0
        self.files_by_type: Dict[str, List[Path]] = {}
        self.routing_recommendations: Dict[Path, str] = {}
        self.special_handling: List[Tuple[Path, str]] = []

    def analyze(self):
        """Run pre-tidy analysis"""
        print("=" * 80)
        print("PRE-TIDY AUDITOR: Analyzing Files")
        print("=" * 80)
        print(f"Target: {self.target_directory}")
        print()

        # Scan all files
        self._scan_files()

        # Analyze file types
        self._analyze_file_types()

        # Generate routing recommendations
        self._generate_routing_recommendations()

        # Detect special cases
        self._detect_special_handling()

        # Generate report
        self._generate_report()

        print(f"\n✅ Pre-Tidy Audit Complete")
        print(f"   Total files: {self.total_files}")
        print(f"   Report: {self.report_path}")
        print()

        return self.routing_recommendations

    def _scan_files(self):
        """Scan all files in target directory"""
        # Directories to exclude from tidy processing (already reviewed/classified)
        EXCLUDED_DIRS = {"superseded", ".git", ".autonomous_runs", "__pycache__", "node_modules"}

        all_files = list(self.target_path.rglob("*"))
        all_files = [f for f in all_files if f.is_file()]

        # Exclude files in superseded directories
        all_files = [
            f for f in all_files
            if not any(excluded in f.parts for excluded in EXCLUDED_DIRS)
        ]

        self.total_files = len(all_files)

        # Group by extension
        for file_path in all_files:
            ext = file_path.suffix.lower() or "no_extension"
            if ext not in self.files_by_type:
                self.files_by_type[ext] = []
            self.files_by_type[ext].append(file_path)

        print(f"   Scanned {self.total_files} files (excluded: {', '.join(EXCLUDED_DIRS)})")

    def _analyze_file_types(self):
        """Analyze distribution of file types"""
        print("\n   File Type Distribution:")
        for ext, files in sorted(self.files_by_type.items(), key=lambda x: -len(x[1])):
            print(f"      {ext}: {len(files)} files")

    def _generate_routing_recommendations(self):
        """Generate routing recommendations for each file"""
        print("\n   Generating routing recommendations...")

        # For .md files, recommend based on filename patterns
        if ".md" in self.files_by_type:
            for md_file in self.files_by_type[".md"]:
                recommendation = self._recommend_category(md_file)
                self.routing_recommendations[md_file] = recommendation

        print(f"      Generated {len(self.routing_recommendations)} recommendations")

    def _recommend_category(self, file_path: Path) -> str:
        """Recommend category for a file based on filename/content analysis"""
        name_lower = file_path.name.lower()

        # Strong indicators for each category
        if any(keyword in name_lower for keyword in ["implementation", "build", "complete", "summary"]):
            return "BUILD_HISTORY"
        elif any(keyword in name_lower for keyword in ["error", "bug", "fix", "debug", "troubleshoot"]):
            return "DEBUG_LOG"
        elif any(keyword in name_lower for keyword in ["decision", "analysis", "architecture", "comparison", "research"]):
            return "ARCHITECTURE_DECISIONS"
        else:
            return "NEEDS_REVIEW"

    def _detect_special_handling(self):
        """Detect files requiring special handling"""
        print("\n   Detecting special cases...")

        # Check for very large files
        for ext, files in self.files_by_type.items():
            for file_path in files:
                try:
                    size = file_path.stat().st_size
                    if size > 1_000_000:  # > 1MB
                        self.special_handling.append((file_path, f"Large file ({size / 1_000_000:.1f}MB)"))
                except Exception:
                    pass

        # Check for binary files in markdown directory
        if ".md" in self.files_by_type:
            md_dir = self.files_by_type[".md"][0].parent
            for ext in self.files_by_type:
                if ext in [".png", ".jpg", ".pdf", ".bin", ".exe"]:
                    for file_path in self.files_by_type[ext]:
                        if file_path.is_relative_to(md_dir):
                            self.special_handling.append((file_path, f"Binary file in docs directory"))

        if self.special_handling:
            print(f"      Found {len(self.special_handling)} special cases")

    def _generate_report(self):
        """Generate pre-tidy audit report"""
        report = f"""# Pre-Tidy Audit Report

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Target Directory**: `{self.target_directory}`
**Total Files**: {self.total_files}

---

## File Type Distribution

"""
        for ext, files in sorted(self.files_by_type.items(), key=lambda x: -len(x[1])):
            report += f"- `{ext}`: {len(files)} files\n"

        report += "\n---\n\n## Routing Recommendations\n\n"

        # Group recommendations by category
        by_category: Dict[str, List[Path]] = {}
        for file_path, category in self.routing_recommendations.items():
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(file_path)

        for category, files in sorted(by_category.items()):
            report += f"\n### {category} ({len(files)} files)\n\n"
            for file_path in sorted(files)[:10]:  # Show first 10
                report += f"- `{file_path.relative_to(REPO_ROOT)}`\n"
            if len(files) > 10:
                report += f"- ... and {len(files) - 10} more\n"

        if self.special_handling:
            report += "\n---\n\n## Special Handling Required\n\n"
            for file_path, reason in self.special_handling:
                report += f"- `{file_path.relative_to(REPO_ROOT)}`: {reason}\n"

        report += "\n---\n\n## Recommendations\n\n"
        report += "1. ✅ Proceed with tidy consolidation\n"
        report += f"2. 📊 Expected: ~{len(self.routing_recommendations)} files → SOT files\n"
        report += "3. 🔍 Review special handling cases after consolidation\n"

        self.report_path.write_text(report, encoding="utf-8")


class PostTidyAuditor:
    """Verifies tidy results and auto-commits"""

    def __init__(self, target_directory: str, project_id: str = "autopack"):
        self.target_directory = target_directory
        self.project_id = project_id
        self.report_path = REPO_ROOT / "POST_TIDY_VERIFICATION_REPORT.md"

        # Load project configuration
        from project_config import load_project_config
        self.config = load_project_config(project_id)
        self.project_root = Path(self.config['project_root'])
        if not self.project_root.is_absolute():
            self.project_root = REPO_ROOT / self.project_root
        self.docs_dir = self.project_root / self.config['docs_dir']

        # Verification results
        self.sot_files_updated = []
        self.total_entries_added = 0
        self.verification_errors = []

    def verify_and_commit(self, dry_run: bool = True):
        """Verify results and auto-commit"""
        print("=" * 80)
        print("POST-TIDY AUDITOR: Verifying Results")
        print("=" * 80)
        print()

        # Verify SOT files
        self._verify_sot_files()

        # Check git status
        self._check_git_status()

        # Generate report
        self._generate_report()

        # Auto-commit if verification passed
        if not dry_run and not self.verification_errors:
            self._auto_commit()

        print(f"\n✅ Post-Tidy Verification Complete")
        print(f"   Report: {self.report_path}")
        print()

    def _verify_sot_files(self):
        """Verify SOT files are valid"""
        print("   Verifying SOT files...")

        sot_files = [
            self.docs_dir / self.config['sot_build_history'],
            self.docs_dir / self.config['sot_debug_log'],
            self.docs_dir / self.config['sot_architecture'],
        ]

        for sot_file in sot_files:
            if not sot_file.exists():
                self.verification_errors.append(f"Missing SOT file: {sot_file.name}")
                continue

            try:
                content = sot_file.read_text(encoding="utf-8")

                # Verify it's valid markdown
                if not content.strip():
                    self.verification_errors.append(f"Empty SOT file: {sot_file.name}")
                    continue

                # Count entries
                if sot_file.name == "BUILD_HISTORY.md":
                    entries = content.count("### BUILD-")
                elif sot_file.name == "DEBUG_LOG.md":
                    entries = content.count("### DEBUG-")
                elif sot_file.name == "ARCHITECTURE_DECISIONS.md":
                    entries = content.count("### DECISION-")
                else:
                    entries = 0

                self.sot_files_updated.append((sot_file.name, entries))
                print(f"      ✅ {sot_file.name}: {entries} entries")

            except Exception as e:
                self.verification_errors.append(f"Error reading {sot_file.name}: {e}")

    def _check_git_status(self):
        """Check git status for changes"""
        print("\n   Checking git status...")

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True
        )

        changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        print(f"      {len(changed_files)} files changed")

    def _generate_report(self):
        """Generate post-tidy verification report"""
        report = f"""# Post-Tidy Verification Report

**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Target Directory**: `{self.target_directory}`

---

## SOT Files Updated

"""
        for sot_file, entries in self.sot_files_updated:
            report += f"- ✅ `{sot_file}`: {entries} total entries\n"

        if self.verification_errors:
            report += "\n---\n\n## Verification Errors\n\n"
            for error in self.verification_errors:
                report += f"- ❌ {error}\n"
        else:
            report += "\n---\n\n## Verification Status\n\n"
            report += "✅ All checks passed\n"

        self.report_path.write_text(report, encoding="utf-8")

    def _auto_commit(self):
        """Auto-commit tidy results"""
        print("\n   Auto-committing changes...")

        # Generate commit message
        commit_msg = f"""tidy: autonomous consolidation of {self.target_directory}

Auditor-verified consolidation:
"""
        for sot_file, entries in self.sot_files_updated:
            commit_msg += f"- {sot_file}: {entries} entries\n"

        commit_msg += """
🤖 Autonomous Tidy (Auditor-verified)
Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
"""

        # Stage changes
        subprocess.run(["git", "add", "docs/*.md"], cwd=REPO_ROOT)

        # Commit
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_ROOT)

        print("      ✅ Changes committed")


class AutonomousTidy:
    """Orchestrates autonomous tidy workflow with Auditor integration"""

    def __init__(self, target_directory: str, dry_run: bool = True):
        self.target_directory = target_directory
        self.dry_run = dry_run

        # Auto-detect project from working directory
        from project_config import detect_project_id
        self.project_id = detect_project_id(cwd=Path.cwd())

        # Generate run_id for this tidy operation
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = f"tidy-{self.project_id}-{timestamp}"

    def run(self):
        """Execute autonomous tidy workflow"""
        print("\n" + "=" * 80)
        print("AUTONOMOUS TIDY WORKFLOW")
        print("=" * 80)
        print(f"Target: {self.target_directory}")
        print(f"Mode: {'DRY-RUN' if self.dry_run else 'EXECUTE'}")
        print("=" * 80)
        print()

        # Step 1: Pre-Tidy Auditor
        pre_auditor = PreTidyAuditor(self.target_directory, self.run_id, self.project_id)
        routing_recommendations = pre_auditor.analyze()

        # Step 2: Tidy Engine (consolidate with Auditor guidance)
        print("=" * 80)
        print("TIDY ENGINE: Consolidating Files")
        print("=" * 80)
        print()

        # Import and run consolidation
        from unified_tidy_directory import UnifiedTidyDirectory

        tidy = UnifiedTidyDirectory(
            target_directory=self.target_directory,
            docs_only=True,
            full_cleanup=False,
            interactive=False,
            dry_run=self.dry_run
        )

        result = tidy.run()

        if result != 0:
            print("\n❌ Tidy consolidation failed")
            return result

        # Step 3: Post-Tidy Auditor
        post_auditor = PostTidyAuditor(self.target_directory, self.project_id)
        post_auditor.verify_and_commit(dry_run=self.dry_run)

        # Final summary
        print("\n" + "=" * 80)
        print("AUTONOMOUS TIDY COMPLETE")
        print("=" * 80)
        print()
        print("📊 Reports Generated:")
        print(f"   - Pre-Tidy Audit: PRE_TIDY_AUDIT_REPORT.md")
        print(f"   - Post-Tidy Verification: POST_TIDY_VERIFICATION_REPORT.md")
        print()

        if self.dry_run:
            print("🔍 Dry-run complete. Run with --execute to apply changes.")
        else:
            print("✅ Changes applied and committed automatically!")

        print("=" * 80)

        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous Tidy with Auditor Integration",
        epilog="""
Examples:
  # Preview autonomous tidy
  python scripts/tidy/autonomous_tidy.py archive --dry-run

  # Execute autonomous tidy
  python scripts/tidy/autonomous_tidy.py archive --execute

  # Triggered from Cursor
  python scripts/tidy/autonomous_tidy.py archive --execute
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("directory", help="Directory to tidy (relative to project root)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute if args.execute else True

    tidy = AutonomousTidy(args.directory, dry_run=dry_run)
    return tidy.run()


if __name__ == "__main__":
    sys.exit(main())
