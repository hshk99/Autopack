#!/usr/bin/env python3
"""
Automatic Documentation Updater

Scans codebase for changes and updates root documentation files accordingly.
Run automatically via git pre-commit hook or manually.

Usage:
    python scripts/update_docs.py              # Update docs
    python scripts/update_docs.py --check      # Check if updates needed
    python scripts/update_docs.py --dry-run    # Show what would change
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class DocUpdater:
    """Automatically updates documentation based on codebase changes"""

    def __init__(self, repo_root: Path):
        self.root = repo_root
        self.changes_needed = []

    def count_api_endpoints(self) -> int:
        """Count total API endpoints in main.py"""
        main_py = self.root / "src" / "autopack" / "main.py"
        if not main_py.exists():
            return 0

        content = main_py.read_text(encoding='utf-8')
        # Count @app decorators (get, post, put, delete, patch)
        pattern = r'@app\.(get|post|put|delete|patch)\('
        matches = re.findall(pattern, content)
        return len(matches)

    def list_new_modules(self) -> List[str]:
        """List recently added Python modules"""
        src_dir = self.root / "src" / "autopack"
        if not src_dir.exists():
            return []

        # Dashboard-related modules
        dashboard_modules = [
            "dashboard_schemas.py",
            "usage_recorder.py",
            "usage_service.py",
            "run_progress.py",
            "model_router.py",
            "llm_service.py",
            "dual_auditor.py",
        ]

        found_modules = []
        for module in dashboard_modules:
            if (src_dir / module).exists():
                found_modules.append(module)

        return found_modules

    def check_dashboard_ui_exists(self) -> bool:
        """Check if dashboard frontend is built"""
        dashboard_dir = self.root / "src" / "autopack" / "dashboard" / "frontend"
        dist_dir = dashboard_dir / "dist"
        return dist_dir.exists() and (dist_dir / "index.html").exists()

    def count_doc_files(self) -> int:
        """Count documentation files in docs/"""
        docs_dir = self.root / "docs"
        if not docs_dir.exists():
            return 0
        return len(list(docs_dir.glob("*.md")))

    def update_readme_stats(self, dry_run: bool = False) -> bool:
        """Update statistics in README.md"""
        readme = self.root / "README.md"
        if not readme.exists():
            print("❌ README.md not found")
            return False

        content = readme.read_text(encoding='utf-8')
        updated = False

        # Update API endpoint count
        endpoint_count = self.count_api_endpoints()
        new_content = re.sub(
            r'\*\*Backend\*\* \| FastAPI \(\d+ REST endpoints\)',
            f'**Backend** | FastAPI ({endpoint_count} REST endpoints)',
            content
        )
        if new_content != content:
            updated = True
            content = new_content

        # Check for dashboard section
        if "### 📊 Real-Time Dashboard" not in content:
            self.changes_needed.append("Dashboard section missing from README")

        # Check for updated architecture diagram
        if "LlmService (Model Router + Usage Track)" not in content:
            self.changes_needed.append("Architecture diagram needs LlmService")

        if updated and not dry_run:
            readme.write_text(content, encoding='utf-8')
            print(f"[OK] Updated README.md (API endpoints: {endpoint_count})")
            return True
        elif dry_run and updated:
            print(f"[DRY RUN] Would update README.md (API endpoints: {endpoint_count})")

        return updated

    def check_status_badge(self) -> bool:
        """Check if status badge reflects dashboard addition"""
        readme = self.root / "README.md"
        if not readme.exists():
            return False

        content = readme.read_text(encoding='utf-8')
        # Dashboard is production ready if dist/ exists
        has_dashboard = self.check_dashboard_ui_exists()

        if has_dashboard and "dashboard" not in content.lower():
            self.changes_needed.append("README should mention dashboard in status")
            return False

        return True

    def generate_feature_summary(self) -> Dict[str, any]:
        """Generate summary of current features"""
        return {
            "api_endpoints": self.count_api_endpoints(),
            "new_modules": self.list_new_modules(),
            "dashboard_built": self.check_dashboard_ui_exists(),
            "doc_files": self.count_doc_files(),
            "changes_needed": self.changes_needed,
        }

    def run(self, check_only: bool = False, dry_run: bool = False) -> int:
        """
        Run documentation updates

        Args:
            check_only: Only check if updates needed, don't apply
            dry_run: Show what would change without modifying files

        Returns:
            0 if no updates needed, 1 if updates needed/applied
        """
        print("[*] Scanning codebase for documentation updates...")

        # Gather current state
        summary = self.generate_feature_summary()

        print(f"\n[Status] Current State:")
        print(f"  API Endpoints: {summary['api_endpoints']}")
        print(f"  New Modules: {len(summary['new_modules'])}")
        print(f"  Dashboard Built: {'YES' if summary['dashboard_built'] else 'NO'}")
        print(f"  Doc Files: {summary['doc_files']}")

        # Check what needs updating
        self.update_readme_stats(dry_run=dry_run or check_only)
        self.check_status_badge()

        if self.changes_needed:
            print(f"\n[!] Documentation changes needed:")
            for change in self.changes_needed:
                print(f"  - {change}")

            if check_only:
                print("\n[Tip] Run without --check to apply updates")
                return 1
            elif not dry_run:
                print("\n[OK] Updates applied")
                return 1
            else:
                print("\n[DRY RUN] No files modified")
                return 1
        else:
            print("\n[OK] Documentation is up to date!")
            return 0


def main():
    parser = argparse.ArgumentParser(
        description="Automatically update Autopack documentation"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if updates needed without modifying files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files"
    )

    args = parser.parse_args()

    # Find repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    updater = DocUpdater(repo_root)
    exit_code = updater.run(check_only=args.check, dry_run=args.dry_run)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
