#!/usr/bin/env python3
"""
CI Check: Version Consistency Validation

Ensures version numbers stay in sync across all files:
- src/autopack/__version__.py (canonical source of truth)
- pyproject.toml (build metadata)
- docs/PROJECT_INDEX.json (documentation)

Usage:
    python scripts/check_version_consistency.py

Exit codes:
    0: All versions match
    1: Version drift detected
    2: Runtime error (missing files, invalid JSON/TOML, etc.)
"""

import json
import re
import sys
from pathlib import Path


def extract_version_from_python(file_path: Path) -> str | None:
    """Extract __version__ from Python file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Match: __version__ = "x.y.z"
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        print(f"❌ ERROR: Failed to read {file_path}: {e}", file=sys.stderr)
        return None


def extract_version_from_toml(file_path: Path) -> str | None:
    """Extract version from pyproject.toml."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Match: version = "x.y.z" under [project] section
        match = re.search(r'\[project\].*?version\s*=\s*["\']([^"\']+)["\']', content, re.DOTALL)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        print(f"❌ ERROR: Failed to read {file_path}: {e}", file=sys.stderr)
        return None


def extract_version_from_json(file_path: Path) -> str | None:
    """Extract version from PROJECT_INDEX.json."""
    try:
        content = file_path.read_text(encoding='utf-8')
        data = json.loads(content)
        return data.get("version")
    except json.JSONDecodeError as e:
        print(f"❌ ERROR: Invalid JSON in {file_path}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ ERROR: Failed to read {file_path}: {e}", file=sys.stderr)
        return None


def main() -> int:
    """Check if versions are consistent across all files."""
    repo_root = Path(__file__).parent.parent

    # Define version file locations
    version_files = {
        "src/autopack/__version__.py": ("Python", extract_version_from_python),
        "pyproject.toml": ("TOML", extract_version_from_toml),
        "docs/PROJECT_INDEX.json": ("JSON", extract_version_from_json),
    }

    # Extract versions from all files
    versions = {}
    missing_files = []
    extraction_errors = []

    for rel_path, (file_type, extractor) in version_files.items():
        file_path = repo_root / rel_path
        if not file_path.exists():
            missing_files.append(rel_path)
            continue

        version = extractor(file_path)
        if version is None:
            extraction_errors.append(f"{rel_path} ({file_type})")
            continue

        versions[rel_path] = version

    # Check for missing files
    if missing_files:
        print("❌ ERROR: Missing version files:", file=sys.stderr)
        for path in missing_files:
            print(f"  - {path}", file=sys.stderr)
        return 2

    # Check for extraction errors
    if extraction_errors:
        print("❌ ERROR: Failed to extract version from:", file=sys.stderr)
        for path in extraction_errors:
            print(f"  - {path}", file=sys.stderr)
        return 2

    # Check if all versions match
    unique_versions = set(versions.values())

    if len(unique_versions) == 1:
        canonical_version = list(unique_versions)[0]
        print(f"✅ SUCCESS: All versions match: {canonical_version}")
        print("")
        print("Version locations:")
        for path in sorted(versions.keys()):
            print(f"  - {path}: {versions[path]}")
        return 0
    else:
        print("❌ DRIFT DETECTED: Version mismatch across files", file=sys.stderr)
        print("", file=sys.stderr)
        print("Current versions:", file=sys.stderr)
        for path in sorted(versions.keys()):
            print(f"  - {path}: {versions[path]}", file=sys.stderr)
        print("", file=sys.stderr)
        print("To fix this:", file=sys.stderr)
        print("  1. Decide on canonical version (usually from src/autopack/__version__.py)", file=sys.stderr)
        print("  2. Update all other files to match", file=sys.stderr)
        print("  3. Commit the version sync", file=sys.stderr)
        print("", file=sys.stderr)

        # Identify canonical version (from __version__.py)
        canonical_file = "src/autopack/__version__.py"
        if canonical_file in versions:
            canonical_version = versions[canonical_file]
            print(f"Canonical version (from {canonical_file}): {canonical_version}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Files needing update:", file=sys.stderr)
            for path, version in sorted(versions.items()):
                if version != canonical_version:
                    print(f"  - {path}: {version} → {canonical_version}", file=sys.stderr)

        return 1


if __name__ == "__main__":
    sys.exit(main())
