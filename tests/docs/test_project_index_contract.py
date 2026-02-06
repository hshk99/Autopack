"""
Contract tests for docs/PROJECT_INDEX.json (SOT navigation surface).

Goal: prevent "two truths" drift where PROJECT_INDEX diverges from the canonical
SOT structure defined in docs/WORKSPACE_ORGANIZATION_SPEC.md and from other
repo-wide canonical decisions (env template location).
"""

import json
from pathlib import Path


def test_project_index_has_canonical_sot_files():
    repo_root = Path(__file__).parents[2]
    project_index_path = repo_root / "docs" / "PROJECT_INDEX.json"
    assert project_index_path.exists(), "Missing docs/PROJECT_INDEX.json"

    data = json.loads(project_index_path.read_text(encoding="utf-8"))

    assert "sot_files" in data and isinstance(
        data["sot_files"], dict
    ), "PROJECT_INDEX missing sot_files map"

    # docs/WORKSPACE_ORGANIZATION_SPEC.md defines the canonical 6-file SOT core.
    required_sot = {
        "PROJECT_INDEX.json",
        "BUILD_HISTORY.md",
        "DEBUG_LOG.md",
        "ARCHITECTURE_DECISIONS.md",
        "FUTURE_PLAN.md",
        "LEARNED_RULES.json",
    }

    missing = sorted(required_sot - set(data["sot_files"].keys()))
    assert not missing, f"PROJECT_INDEX sot_files missing required SOT files: {missing}"


def test_project_index_does_not_claim_5_file_sot():
    repo_root = Path(__file__).parents[2]
    project_index_path = repo_root / "docs" / "PROJECT_INDEX.json"
    data = json.loads(project_index_path.read_text(encoding="utf-8"))

    # Direct string checks to prevent accidental reintroduction.
    raw = project_index_path.read_text(encoding="utf-8")
    assert "5-file" not in raw, "PROJECT_INDEX should not claim a 5-file SOT (canonical is 6-file)"

    # A couple of specific fields are historically drift-prone:
    notes = data.get("notes", {})
    if isinstance(notes, dict):
        same = str(notes.get("same_structure_all_projects", ""))
        assert "6-file" in same, "notes.same_structure_all_projects should mention 6-file SOT"

    ws = data.get("workspace_structure", {})
    if isinstance(ws, dict):
        ars = ws.get("autonomous_runs_structure", {})
        if isinstance(ars, dict):
            pps = ars.get("per_project_structure", {})
            if isinstance(pps, dict):
                docs_desc = str(pps.get("docs/", ""))
                assert (
                    "6-file" in docs_desc
                ), "workspace_structure.*.per_project_structure docs/ should mention 6-file SOT"


def test_project_index_quickstart_uses_canonical_env_template_path():
    repo_root = Path(__file__).parents[2]
    project_index_path = repo_root / "docs" / "PROJECT_INDEX.json"
    data = json.loads(project_index_path.read_text(encoding="utf-8"))

    quick_start = data.get("setup", {}).get("quick_start", [])
    assert (
        isinstance(quick_start, list) and quick_start
    ), "PROJECT_INDEX setup.quick_start must be a non-empty list"

    joined = "\n".join(str(x) for x in quick_start)

    # Canonical: repo-root .env.example (per WORKSPACE_ORGANIZATION_SPEC + docs drift checker).
    assert (
        "cp .env.example .env" in joined
    ), "PROJECT_INDEX quick_start must include: cp .env.example .env"
    assert (
        "cp docs/templates/env.example .env" not in joined
    ), "PROJECT_INDEX must not reference docs/templates/env.example (non-canonical / missing path)"
