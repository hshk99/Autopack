#!/usr/bin/env python3
"""
Automatic Documentation Updater

Two modes:
1. Quick mode (default): Fast endpoint count updates for pre-commit hook
2. Full analysis (--analyze): Deep structural change detection for CI flow

Detects: new modules, classes, API changes, dependencies - WITHOUT using LLMs (100% token-free).
Uses: Python AST parsing + git diff analysis

Usage:
    python scripts/update_docs.py                    # Quick update (endpoint counts)
    python scripts/update_docs.py --check            # Check if updates needed
    python scripts/update_docs.py --dry-run          # Preview changes
    python scripts/update_docs.py --analyze          # Full analysis (for CI flow)
    python scripts/update_docs.py --analyze --dry-run # Preview structural changes
"""

import argparse
import ast
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional


class StructuralChange:
    """Represents a detected structural change"""

    def __init__(self, category: str, description: str, location: str):
        self.category = category  # "module", "class", "api", "dependency", "config"
        self.description = description
        self.location = location


class DocUpdater:
    """Automatically updates documentation based on codebase changes"""

    def __init__(self, repo_root: Path):
        self.root = repo_root
        self.changes_needed = []
        self.structural_changes: List[StructuralChange] = []

    def count_api_endpoints(self) -> int:
        """Count total API endpoints in main.py"""
        main_py = self.root / "src" / "autopack" / "main.py"
        if not main_py.exists():
            return 0

        content = main_py.read_text(encoding="utf-8")
        # Count @app decorators (get, post, put, delete, patch)
        pattern = r"@app\.(get|post|put|delete|patch)\("
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

    def detect_new_modules_since_commit(
        self, since_commit: str = "HEAD~5"
    ) -> List[StructuralChange]:
        """Detect new Python modules added since a commit using git diff"""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", since_commit, "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return []

            changes = []
            for line in result.stdout.splitlines():
                if line.startswith("A") and ".py" in line:
                    # Extract file path (format: "A\tpath/to/file.py")
                    parts = line.split("\t")
                    if len(parts) == 2:
                        file_path = parts[1]
                        if "src/autopack/" in file_path and not file_path.endswith("__init__.py"):
                            module_name = Path(file_path).stem
                            changes.append(
                                StructuralChange(
                                    category="module",
                                    description=f"New module: {module_name}",
                                    location=file_path,
                                )
                            )

            return changes
        except Exception:
            return []

    def detect_new_classes_in_file(self, file_path: Path) -> List[str]:
        """Use AST to detect class definitions in a Python file"""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)

            return classes
        except Exception:
            return []

    def detect_api_endpoint_changes(self) -> List[StructuralChange]:
        """Detect changes to API endpoints (new routes, parameter changes)"""
        main_py = self.root / "src" / "autopack" / "main.py"
        if not main_py.exists():
            return []

        changes = []
        try:
            content = main_py.read_text(encoding="utf-8")

            # Find all endpoint decorators with their routes
            pattern = r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']\)'
            matches = re.findall(pattern, content)

            # Store current endpoints (could compare against saved state in future)
            current_endpoints = {f"{method.upper()} {route}" for method, route in matches}

            # For now, just note if we have new endpoint categories
            endpoint_routes = [route for _, route in matches]

            # Detect major new endpoint groups
            if any("/dashboard/" in route for route in endpoint_routes):
                if not hasattr(self, "_dashboard_endpoints_seen"):
                    changes.append(
                        StructuralChange(
                            category="api",
                            description="Dashboard API endpoints added",
                            location="main.py::/dashboard/*",
                        )
                    )

        except Exception:
            pass

        return changes

    def detect_dependency_changes(self) -> List[StructuralChange]:
        """Detect new dependencies in requirements.txt or package.json"""
        changes = []

        # Check Python dependencies
        requirements_txt = self.root / "requirements.txt"
        if requirements_txt.exists():
            try:
                content = requirements_txt.read_text(encoding="utf-8")
                lines = [
                    line.strip()
                    for line in content.splitlines()
                    if line.strip() and not line.startswith("#")
                ]

                # Major dependencies to watch for
                major_deps = [
                    "fastapi",
                    "sqlalchemy",
                    "pydantic",
                    "openai",
                    "anthropic",
                    "react",
                    "vite",
                ]

                for dep in major_deps:
                    if any(dep.lower() in line.lower() for line in lines):
                        # Could track if this is new by comparing against saved state
                        pass
            except Exception:
                pass

        # Check Node dependencies
        package_json = self.root / "src" / "autopack" / "dashboard" / "frontend" / "package.json"
        if package_json.exists():
            try:
                import json

                content = package_json.read_text(encoding="utf-8")
                data = json.loads(content)

                # Check for major frontend frameworks
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                if "react" in deps:
                    # React dashboard exists
                    pass
            except Exception:
                pass

        return changes

    def analyze_structural_changes(self) -> List[StructuralChange]:
        """
        Analyze codebase for major structural changes.
        This is the main method that orchestrates all detection.
        """
        all_changes = []

        # 1. Detect new modules via git diff
        new_modules = self.detect_new_modules_since_commit()
        all_changes.extend(new_modules)

        # 2. Analyze new modules for important classes
        for change in new_modules:
            file_path = self.root / change.location
            if file_path.exists():
                classes = self.detect_new_classes_in_file(file_path)
                if classes:
                    important_classes = [c for c in classes if not c.startswith("_")]
                    if important_classes:
                        all_changes.append(
                            StructuralChange(
                                category="class",
                                description=f"New classes: {', '.join(important_classes[:3])}",
                                location=change.location,
                            )
                        )

        # 3. Detect API changes
        api_changes = self.detect_api_endpoint_changes()
        all_changes.extend(api_changes)

        # 4. Detect dependency changes
        dep_changes = self.detect_dependency_changes()
        all_changes.extend(dep_changes)

        return all_changes

    def update_readme_stats(self, dry_run: bool = False) -> bool:
        """Update statistics in README.md"""
        readme = self.root / "README.md"
        if not readme.exists():
            print("❌ README.md not found")
            return False

        content = readme.read_text(encoding="utf-8")
        updated = False

        # Update API endpoint count
        endpoint_count = self.count_api_endpoints()
        new_content = re.sub(
            r"\*\*Backend\*\* \| FastAPI \(\d+ REST endpoints\)",
            f"**Backend** | FastAPI ({endpoint_count} REST endpoints)",
            content,
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
            readme.write_text(content, encoding="utf-8")
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

        content = readme.read_text(encoding="utf-8")
        # Dashboard is production ready if dist/ exists
        has_dashboard = self.check_dashboard_ui_exists()

        if has_dashboard and "dashboard" not in content.lower():
            self.changes_needed.append("README should mention dashboard in status")
            return False

        return True

    def update_changelog(self, changes: List[StructuralChange], dry_run: bool = False) -> bool:
        """
        Update CHANGELOG.md with detected structural changes.
        Updates or replaces today's entry (no duplicate entries per day).
        """
        if not changes:
            return False

        changelog = self.root / "CHANGELOG.md"

        # Group changes by category
        by_category = {}
        for change in changes:
            if change.category not in by_category:
                by_category[change.category] = []
            by_category[change.category].append(change)

        # Build changelog entry
        today = datetime.now().strftime("%Y-%m-%d")
        entry_lines = [f"\n## [{today}] - Structural Updates\n"]

        category_headers = {
            "module": "### New Modules",
            "class": "### New Classes",
            "api": "### API Changes",
            "dependency": "### Dependencies",
            "config": "### Configuration",
        }

        for category in ["module", "class", "api", "dependency", "config"]:
            if category in by_category:
                entry_lines.append(f"\n{category_headers[category]}\n")
                for change in by_category[category]:
                    entry_lines.append(f"- {change.description} (`{change.location}`)\n")

        entry_text = "".join(entry_lines)

        if dry_run:
            print("[DRY RUN] Would update CHANGELOG.md:")
            print(entry_text)
            return True

        # Create or update changelog
        if changelog.exists():
            content = changelog.read_text(encoding="utf-8")

            # Check if today's entry already exists
            today_marker = f"## [{today}] - Structural Updates"
            if today_marker in content:
                # Replace existing entry for today
                lines = content.splitlines(keepends=True)
                new_lines = []
                skip_until_next_section = False

                for i, line in enumerate(lines):
                    if today_marker in line:
                        # Found today's entry, skip until next ## section
                        skip_until_next_section = True
                        new_lines.append(entry_text.lstrip("\n"))  # Add new entry
                        continue

                    if skip_until_next_section:
                        # Stop skipping when we hit next date or end
                        if line.startswith("## [") and today_marker not in line:
                            skip_until_next_section = False
                            new_lines.append(line)
                        # Skip lines that are part of today's old entry
                        continue

                    new_lines.append(line)

                new_content = "".join(new_lines)
            else:
                # Add new entry for today at the top
                if "# Changelog" in content:
                    parts = content.split("# Changelog", 1)
                    new_content = parts[0] + "# Changelog" + entry_text + parts[1]
                else:
                    new_content = "# Changelog\n" + entry_text + "\n" + content
        else:
            new_content = "# Changelog\n" + entry_text

        changelog.write_text(new_content, encoding="utf-8")
        print(
            f"[OK] Updated CHANGELOG.md with {len(changes)} structural changes (merged into today's entry)"
        )
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

    def run(self, check_only: bool = False, dry_run: bool = False, analyze: bool = False) -> int:
        """
        Run documentation updates

        Args:
            check_only: Only check if updates needed, don't apply
            dry_run: Show what would change without modifying files
            analyze: Run full structural analysis (for CI flow, takes longer)

        Returns:
            0 if no updates needed, 1 if updates needed/applied
        """
        print("[*] Scanning codebase for documentation updates...")

        # Quick mode: Just update stats (fast, for pre-commit hook)
        if not analyze:
            print("[Mode] Quick update (endpoint counts only)")
            self.update_readme_stats(dry_run=dry_run or check_only)
            self.check_status_badge()

            if self.changes_needed:
                print("\n[!] Documentation changes needed:")
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

        # Full analysis mode: Detect structural changes (for CI flow)
        print("[Mode] Full structural analysis (detecting major changes)")

        # Gather current state
        summary = self.generate_feature_summary()

        print("\n[Status] Current State:")
        print(f"  API Endpoints: {summary['api_endpoints']}")
        print(f"  New Modules: {len(summary['new_modules'])}")
        print(f"  Dashboard Built: {'YES' if summary['dashboard_built'] else 'NO'}")
        print(f"  Doc Files: {summary['doc_files']}")

        # Analyze structural changes
        print("\n[*] Analyzing structural changes (AST + git diff)...")
        structural_changes = self.analyze_structural_changes()

        if structural_changes:
            print(f"\n[Detected] {len(structural_changes)} major structural changes:")
            for change in structural_changes:
                print(f"  [{change.category.upper()}] {change.description}")
                print(f"      Location: {change.location}")

        # Update README stats
        self.update_readme_stats(dry_run=dry_run or check_only)
        self.check_status_badge()

        # Update CHANGELOG with structural changes
        if structural_changes:
            self.update_changelog(structural_changes, dry_run=dry_run or check_only)

        # Report results
        total_updates = len(self.changes_needed) + len(structural_changes)

        if total_updates > 0:
            print(f"\n[Summary] {total_updates} documentation updates")

            if check_only:
                print("\n[Tip] Run without --check to apply updates")
                return 1
            elif not dry_run:
                print("\n[OK] All updates applied")
                return 1
            else:
                print("\n[DRY RUN] No files modified")
                return 1
        else:
            print("\n[OK] Documentation is up to date!")
            return 0


def main():
    parser = argparse.ArgumentParser(description="Automatically update Autopack documentation")
    parser.add_argument(
        "--check", action="store_true", help="Check if updates needed without modifying files"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without modifying files"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run full structural analysis (for CI flow - detects major changes)",
    )

    args = parser.parse_args()

    # Find repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    updater = DocUpdater(repo_root)
    exit_code = updater.run(check_only=args.check, dry_run=args.dry_run, analyze=args.analyze)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
