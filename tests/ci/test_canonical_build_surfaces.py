from __future__ import annotations

from pathlib import Path

from scripts.ci.check_canonical_build_surfaces import check_canonical_build_surfaces


def test_canonical_build_surfaces_clean() -> None:
    """Repo should not contain duplicate tracked build surfaces outside archive/."""
    repo_root = Path(__file__).resolve().parents[2]
    result = check_canonical_build_surfaces(repo_root)
    assert result.exit_code == 0, f"violations: {result.violations}"
    assert result.violations == []
