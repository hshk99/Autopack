#!/usr/bin/env python3
"""
Documentation link drift checker.

Validates that file references in core navigation documents actually exist.
Prevents "two truths" problem where docs reference non-existent files.

Scope (BUILD-158 v1):
- README.md
- docs/INDEX.md
- docs/BUILD_HISTORY.md

Future extensions could add:
- All BUILD_*.md files (--deep mode)
- External URL validation
- Link graph analysis

Exit codes:
- 0: All links valid
- 1: Broken links found
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# File reference patterns
# Matches: [text](path/to/file.md) and `path/to/file.txt`
MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')  # [text](link)
BACKTICK_PATH_PATTERN = re.compile(r'`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`')  # `file.ext`
DIRECT_PATH_PATTERN = re.compile(r'(?:^|[ \t])([a-zA-Z0-9_\-./]+\.md)(?:[ \t:]|$)')  # file.md


def extract_file_references(content: str, file_path: Path) -> Set[str]:
    """
    Extract potential file references from markdown content.

    Args:
        content: Markdown file content
        file_path: Path to the markdown file (for relative resolution)

    Returns:
        Set of referenced file paths (relative to repo root)
    """
    refs = set()

    # Extract markdown links: [text](path)
    for match in MARKDOWN_LINK_PATTERN.finditer(content):
        link = match.group(2)
        # Skip URLs (http://, https://, mailto:, #anchors)
        if link.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        # Remove anchor fragments
        if '#' in link:
            link = link.split('#')[0]
        if link:
            refs.add(link)

    # Extract backtick-wrapped paths: `path/to/file.ext`
    for match in BACKTICK_PATH_PATTERN.finditer(content):
        path_ref = match.group(1)
        # Only include if it looks like a file path (has slash or dots)
        if '/' in path_ref or path_ref.count('.') >= 2:
            refs.add(path_ref)

    return refs


def validate_references(
    refs: Set[str],
    source_file: Path,
    repo_root: Path
) -> Tuple[List[str], List[str]]:
    """
    Validate that referenced paths exist.

    Args:
        refs: Set of referenced paths
        source_file: Source markdown file doing the referencing
        repo_root: Repository root directory

    Returns:
        (valid_refs, broken_refs) tuple
    """
    valid = []
    broken = []

    for ref in refs:
        # Try as absolute path from repo root
        abs_path = repo_root / ref
        if abs_path.exists():
            valid.append(ref)
            continue

        # Try as relative path from source file's directory
        rel_path = source_file.parent / ref
        if rel_path.exists():
            valid.append(ref)
            continue

        # Path not found
        broken.append(ref)

    return valid, broken


def check_file(file_path: Path, repo_root: Path) -> Dict:
    """
    Check a single file for broken links.

    Args:
        file_path: Path to markdown file
        repo_root: Repository root

    Returns:
        Dict with check results
    """
    if not file_path.exists():
        return {
            "file": str(file_path.relative_to(repo_root)),
            "exists": False,
            "refs_total": 0,
            "refs_valid": [],
            "refs_broken": [],
        }

    content = file_path.read_text(encoding='utf-8')
    refs = extract_file_references(content, file_path)
    valid, broken = validate_references(refs, file_path, repo_root)

    return {
        "file": str(file_path.relative_to(repo_root)),
        "exists": True,
        "refs_total": len(refs),
        "refs_valid": valid,
        "refs_broken": broken,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check documentation links for drift (broken file references)"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root directory (default: autodetect)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show valid links in addition to broken ones"
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()

    # Core navigation files (BUILD-158 scope)
    files_to_check = [
        repo_root / "README.md",
        repo_root / "docs" / "INDEX.md",
        repo_root / "docs" / "BUILD_HISTORY.md",
    ]

    print("=" * 70)
    print("DOCUMENTATION LINK DRIFT CHECK")
    print("=" * 70)
    print(f"Repository root: {repo_root}")
    print(f"Files to check: {len(files_to_check)}")
    print("=" * 70)
    print()

    total_refs = 0
    total_broken = 0
    results = []

    for file_path in files_to_check:
        result = check_file(file_path, repo_root)
        results.append(result)

        if not result["exists"]:
            print(f"❌ {result['file']}: FILE NOT FOUND")
            continue

        total_refs += result["refs_total"]
        total_broken += len(result["refs_broken"])

        if result["refs_broken"]:
            print(f"❌ {result['file']}: {len(result['refs_broken'])} broken link(s)")
            for broken_ref in sorted(result["refs_broken"]):
                print(f"   - {broken_ref}")
        else:
            print(f"✅ {result['file']}: all {result['refs_total']} link(s) valid")

        if args.verbose and result["refs_valid"]:
            print(f"   Valid refs ({len(result['refs_valid'])}):")
            for valid_ref in sorted(result["refs_valid"])[:10]:  # Show first 10
                print(f"     • {valid_ref}")
            if len(result["refs_valid"]) > 10:
                print(f"     ... and {len(result['refs_valid']) - 10} more")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files checked: {len(results)}")
    print(f"Total references found: {total_refs}")
    print(f"Broken references: {total_broken}")

    if total_broken > 0:
        print()
        print("❌ FAILED: Broken links detected")
        print("   Fix broken references or remove them from documentation")
        return 1
    else:
        print()
        print("✅ PASSED: All documentation links are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
