#!/usr/bin/env python3
"""
Unit tests for redirect stub validation (BUILD-167).

Ensures redirect stubs point to existing files and don't rot.
"""

import re
from pathlib import Path


def test_redirect_stubs_point_to_existing_files():
    """Test that all redirect stubs point to valid existing files."""
    repo_root = Path(__file__).parents[2]

    # Known redirect stubs (BUILD-167)
    # Note: Root stubs removed in BUILD-182 to satisfy workspace structure compliance.
    # Redirect stubs now live only under docs/ per WORKSPACE_ORGANIZATION_SPEC.md.
    # CONSOLIDATED_DEBUG.md archived in PR-115 (no longer tracked in docs/).
    redirect_stubs = [
        repo_root / "docs" / "SOT_BUNDLE.md",
    ]

    # Pattern to extract markdown links: [text](path)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    failures = []

    for stub_path in redirect_stubs:
        if not stub_path.exists():
            failures.append(f"Redirect stub does not exist: {stub_path}")
            continue

        content = stub_path.read_text(encoding="utf-8")

        # Extract all markdown links
        links = link_pattern.findall(content)

        if not links:
            failures.append(f"No redirect link found in stub: {stub_path}")
            continue

        # Check each link points to an existing file
        for link_text, link_path in links:
            # Resolve relative to stub's parent directory
            target_path = (stub_path.parent / link_path).resolve()

            if not target_path.exists():
                failures.append(
                    f"Broken redirect in {stub_path.name}: "
                    f"[{link_text}]({link_path}) → {target_path} (does not exist)"
                )

    if failures:
        print("\n❌ Redirect stub validation failures:")
        for failure in failures:
            print(f"  - {failure}")
        assert False, f"{len(failures)} redirect stub validation failure(s)"

    print(
        f"✅ test_redirect_stubs_point_to_existing_files passed ({len(redirect_stubs)} stubs validated)"
    )


def test_redirect_stub_format():
    """Test that redirect stubs follow expected format."""
    repo_root = Path(__file__).parents[2]

    # Note: Root stubs removed in BUILD-182 to satisfy workspace structure compliance.
    # Redirect stubs now live only under docs/ per WORKSPACE_ORGANIZATION_SPEC.md.
    # CONSOLIDATED_DEBUG.md archived in PR-115 (no longer tracked in docs/).
    redirect_stubs = [
        repo_root / "docs" / "SOT_BUNDLE.md",
    ]

    failures = []

    for stub_path in redirect_stubs:
        if not stub_path.exists():
            continue  # Already caught by previous test

        content = stub_path.read_text(encoding="utf-8")

        # Check for required elements
        required_elements = [
            ("**Status**: Moved", "status marker"),
            ("This document has been moved", "move explanation"),
            ("redirect stub created by doc link triage", "provenance marker"),
        ]

        for required_text, element_name in required_elements:
            if required_text not in content:
                failures.append(f"{stub_path.name} missing {element_name}: '{required_text}'")

    if failures:
        print("\n❌ Redirect stub format failures:")
        for failure in failures:
            print(f"  - {failure}")
        assert False, f"{len(failures)} redirect stub format failure(s)"

    print(f"✅ test_redirect_stub_format passed ({len(redirect_stubs)} stubs validated)")


if __name__ == "__main__":
    test_redirect_stubs_point_to_existing_files()
    test_redirect_stub_format()

    print("\n" + "=" * 70)
    print("ALL REDIRECT STUB TESTS PASSED ✅")
    print("=" * 70)
