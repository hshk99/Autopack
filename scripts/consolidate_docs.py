#!/usr/bin/env python3
"""
Documentation Consolidation Script

This script consolidates scattered documentation files into organized,
project-aware archives with auto-update capabilities.

Author: Autopack
Date: 2025-11-30
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

class ProjectDocConsolidator:
    """Consolidates documentation with strict project separation."""

    def __init__(self, autopack_root: Path):
        self.autopack_root = Path(autopack_root)
        self.timestamp = datetime.now().strftime("%Y-%m-%d")

        # Project detection patterns
        self.project_patterns = {
            "file-organizer-app-v1": [
                "fileorg", "file-organizer", "pack", "scenario",
                "ocr", "tesseract", "classification"
            ],
            "autopack-framework": [
                "autopack", "builder", "auditor", "llm", "phase",
                "tier", "executor", "governed"
            ]
        }

    def detect_project(self, file_path: Path, content: str) -> str:
        """Detect which project a file belongs to."""
        file_str = str(file_path).lower()
        content_lower = content.lower()

        # Check file path first
        if "file-organizer-app-v1" in file_str:
            return "file-organizer-app-v1"
        if ".autonomous_runs" not in file_str and ("src/autopack" in file_str or "tests/" in file_str):
            return "autopack-framework"

        # Check content patterns
        fileorg_score = sum(1 for pattern in self.project_patterns["file-organizer-app-v1"]
                           if pattern in content_lower)
        autopack_score = sum(1 for pattern in self.project_patterns["autopack-framework"]
                            if pattern in content_lower)

        if fileorg_score > autopack_score * 2:
            return "file-organizer-app-v1"
        elif autopack_score > fileorg_score * 2:
            return "autopack-framework"
        else:
            # Check file path as tiebreaker
            if "autonomous_runs" in file_str:
                return "file-organizer-app-v1"
            return "autopack-framework"

    def categorize_file(self, file_path: Path, content: str) -> str:
        """Categorize file by content type."""
        content_lower = content.lower()
        filename = file_path.name.lower()

        # Debug/Error files
        if any(word in filename for word in ["debug", "error", "fix", "issue", "troubleshoot"]):
            return "debug"
        if any(word in content_lower[:500] for word in ["error", "bug", "fix", "issue", "symptom"]):
            return "debug"

        # Build history files
        if any(word in filename for word in ["build", "progress", "history", "timeline", "week"]):
            return "build"
        if any(word in content_lower[:500] for word in ["week", "deliverable", "milestone", "commit"]):
            return "build"

        # Strategy/Analysis files
        if any(word in filename for word in ["strategy", "analysis", "market", "product", "revenue"]):
            return "strategy"
        if any(word in content_lower[:500] for word in ["market", "revenue", "customer", "pricing"]):
            return "strategy"

        # Research/Investigation files
        if any(word in filename for word in ["research", "investigation", "exploration", "review"]):
            return "research"

        # Reference/Guide files
        if any(word in filename for word in ["reference", "guide", "index", "readme"]):
            return "reference"

        return "misc"

    def _process_file(self, md_file: Path, all_files: list, force_project=None, force_category=None):
        try:
            content = md_file.read_text(encoding='utf-8')
            project = force_project or self.detect_project(md_file, content)
            category = force_category or self.categorize_file(md_file, content)
            all_files.append((md_file, content, project, category))
            print(f"  - Scanned: {md_file.name} -> {project}/{category}")
        except Exception as e:
            print(f"  [WARN] Failed to read {md_file.name}: {e}")

    def consolidate_debug_files(self, files: List[Tuple[Path, str]]) -> str:
        """Consolidate all debug/error files."""
        consolidated = f"""# Consolidated Debug and Error Reference

**Last Updated**: {self.timestamp}
**Auto-generated** by scripts/consolidate_docs.py

## Purpose
Single source of truth for all errors, fixes, prevention rules, and troubleshooting.

---

## Prevention Rules

"""
        # Extract prevention rules from all files
        rules_seen = set()
        for file_path, content in files:
            # Extract numbered rules
            rule_pattern = r'(?:Rule|rule)\s*[#:]?\s*(\d+)[:\s]+([^\n]+)'
            for match in re.finditer(rule_pattern, content):
                rule_text = match.group(2).strip()
                if rule_text not in rules_seen:
                    rules_seen.add(rule_text)
                    consolidated += f"- {rule_text}\n"

        consolidated += "\n---\n\n## Resolved Issues\n\n"

        # Extract resolved issues
        for file_path, content in files:
            # Look for resolved issue sections
            resolved_pattern = r'###?\s+(?:Issue\s+#?\d+|.*?)[\s\S]*?(?:RESOLVED|Fixed|Resolved)'
            for match in re.finditer(resolved_pattern, content, re.IGNORECASE):
                issue_text = match.group(0)
                if "**Status**: RESOLVED" in issue_text or "Status**: ✅" in issue_text:
                    consolidated += f"\n{issue_text}\n\n"
                    consolidated += f"**Source**: [{file_path.name}]({file_path})\n\n---\n\n"

        consolidated += "\n## Open Issues\n\n"

        # Extract open issues
        for file_path, content in files:
            # Look for open issue sections
            open_pattern = r'###?\s+(?:Issue\s+#?\d+|.*?)[\s\S]*?(?:OPEN|Priority|First Observed)'
            for match in re.finditer(open_pattern, content, re.IGNORECASE):
                issue_text = match.group(0)
                if "**Status**: OPEN" in issue_text or ("Priority" in issue_text and "RESOLVED" not in issue_text):
                    consolidated += f"\n{issue_text}\n\n"
                    consolidated += f"**Source**: [{file_path.name}]({file_path})\n\n---\n\n"

        return consolidated

    def consolidate_by_category(self,
                                  files: List[Tuple[Path, str]],
                                  category: str) -> str:
        """Consolidate files by category."""
        if category == "debug":
            return self.consolidate_debug_files(files)

        # For other categories, create a comprehensive timeline-based consolidation
        consolidated = f"""# Consolidated {category.title()} Reference

**Last Updated**: {self.timestamp}
**Auto-generated** by scripts/consolidate_docs.py

## Contents

"""
        # Add table of contents
        for file_path, _ in files:
            consolidated += f"- [{file_path.stem}](#{file_path.stem.lower().replace('_', '-')})\n"

        consolidated += "\n---\n\n"

        # Add each file's content
        for file_path, content in files:
            consolidated += f"""## {file_path.stem}

**Source**: [{file_path.name}]({file_path})
**Last Modified**: {datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d')}

{content}

---

"""

        return consolidated

    def run_consolidation(self):
        """Main consolidation process."""
        print(f"[INFO] Starting documentation consolidation at {self.timestamp}")

        # Find all markdown files in archive locations
        file_org_archive = self.autopack_root / ".autonomous_runs" / "file-organizer-app-v1" / "archive"
        file_org_research = self.autopack_root / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "research"
        autopack_archive = self.autopack_root / "archive"

        all_files = []

        # Scan file-organizer-app-v1 archive (including superseded)
        if file_org_archive.exists():
            # Scan main folder
            for md_file in file_org_archive.glob("*.md"):
                if md_file.name not in ["ARCHIVE_INDEX.md"] and not md_file.name.startswith("CONSOLIDATED_"):
                    self._process_file(md_file, all_files)
            
            # Scan superseded folder
            superseded = file_org_archive / "superseded"
            if superseded.exists():
                for md_file in superseded.glob("*.md"):
                    self._process_file(md_file, all_files)

        # Scan file-organizer-app-v1 research docs (including superseded)
        if file_org_research.exists():
            for md_file in file_org_research.glob("*.md"):
                 self._process_file(md_file, all_files, force_project="file-organizer-app-v1", force_category="research")
            
            research_superseded = file_org_research / "superseded"
            if research_superseded.exists():
                for md_file in research_superseded.glob("*.md"):
                    self._process_file(md_file, all_files, force_project="file-organizer-app-v1", force_category="research")

        # Scan Autopack archive (including superseded)
        if autopack_archive.exists():
            # Scan main folder
            for md_file in autopack_archive.glob("*.md"):
                if md_file.name not in ["ARCHIVE_INDEX.md"] and not md_file.name.startswith("CONSOLIDATED_"):
                    self._process_file(md_file, all_files)
            
            # Scan superseded folder
            superseded = autopack_archive / "superseded"
            if superseded.exists():
                for md_file in superseded.glob("*.md"):
                    self._process_file(md_file, all_files)

        print(f"\n[INFO] Scanned {len(all_files)} files total\n")

        # Group by project and category
        grouped: Dict[str, Dict[str, List[Tuple[Path, str]]]] = {}
        for file_path, content, project, category in all_files:
            if project not in grouped:
                grouped[project] = {}
            if category not in grouped[project]:
                grouped[project][category] = []
            grouped[project][category].append((file_path, content))

        # Create consolidated files for each project/category
        for project, categories in grouped.items():
            print(f"[INFO] Processing project: {project}")

            # Determine output location
            if project == "file-organizer-app-v1":
                output_dir = file_org_archive
            else:
                output_dir = autopack_archive

            output_dir.mkdir(parents=True, exist_ok=True)

            for category, files in categories.items():
                print(f"  - Consolidating {len(files)} {category} files")

                consolidated_content = self.consolidate_by_category(files, category)
                output_file = output_dir / f"CONSOLIDATED_{category.upper()}.md"

                output_file.write_text(consolidated_content, encoding='utf-8')
                print(f"    [OK] Created: {output_file}")

        # Create master index
        self.create_master_index(grouped, file_org_archive, autopack_archive)

        print("\n[SUCCESS] Consolidation complete!")
        print("\nNext steps:")
        print("1. Review consolidated files in:")
        print(f"   - {file_org_archive}")
        print(f"   - {autopack_archive}")
        print("2. Archive original files to 'superseded/' subfolder")
        print("3. Update archive_consolidator.py for auto-update")

    def create_master_index(self,
                           grouped: Dict[str, Dict[str, List]],
                           file_org_archive: Path,
                           autopack_archive: Path):
        """Create master index file."""
        index_content = f"""# Documentation Archive Index

**Last Updated**: {self.timestamp}
**Auto-generated** by scripts/consolidate_docs.py

## Purpose
Quick reference guide to all consolidated documentation across projects.

---

## File-Organizer-App-v1 Documentation

"""
        if "file-organizer-app-v1" in grouped:
            for category, files in grouped["file-organizer-app-v1"].items():
                consolidated_file = f"CONSOLIDATED_{category.upper()}.md"
                index_content += f"\n### {category.title()}\n"
                index_content += f"**File**: [{consolidated_file}]({file_org_archive / consolidated_file})\n"
                index_content += f"**Sources**: {len(files)} files consolidated\n\n"

        index_content += "\n---\n\n## Autopack Framework Documentation\n\n"

        if "autopack-framework" in grouped:
            for category, files in grouped["autopack-framework"].items():
                consolidated_file = f"CONSOLIDATED_{category.upper()}.md"
                index_content += f"\n### {category.title()}\n"
                index_content += f"**File**: [{consolidated_file}]({autopack_archive / consolidated_file})\n"
                index_content += f"**Sources**: {len(files)} files consolidated\n\n"

        index_content += """
---

## How to Use

1. **Find your topic** in the sections above
2. **Open the consolidated file** for that category
3. **Use Ctrl+F** to search for specific keywords
4. **Check Source links** to trace back to original files

---

## Maintenance

This index is auto-generated. To update:

```bash
python scripts/consolidate_docs.py
```

---

*Auto-generated by Autopack Documentation Consolidator*
"""

        # Write index to both locations
        (file_org_archive / "ARCHIVE_INDEX.md").write_text(index_content, encoding='utf-8')
        (autopack_archive / "ARCHIVE_INDEX.md").write_text(index_content, encoding='utf-8')

        print("  [OK] Created: ARCHIVE_INDEX.md in both locations")


def main():
    """Main entry point."""
    autopack_root = Path(__file__).parent.parent
    consolidator = ProjectDocConsolidator(autopack_root)
    consolidator.run_consolidation()


if __name__ == "__main__":
    main()
