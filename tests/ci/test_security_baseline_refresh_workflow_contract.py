"""Contract tests for security-baseline-refresh workflow hardening (BUILD-188).

These tests mechanically enforce:
- workflow_dispatch has artifacts_run_id input for deterministic baseline refresh testing
- concurrency block exists to prevent overlapping runs
- git push uses --force-with-lease (no -f)

These are read-only checks: they parse the workflow file as text (no YAML dependency).
"""

from __future__ import annotations

import re
from pathlib import Path


def test_security_baseline_refresh_has_artifacts_run_id_input() -> None:
    repo_root = Path(__file__).parents[2]
    wf = (repo_root / ".github" / "workflows" / "security-baseline-refresh.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch" in wf
    assert re.search(r"^\s+inputs:\s*$", wf, flags=re.MULTILINE), "workflow_dispatch must define inputs"
    assert re.search(
        r"^\s+artifacts_run_id:\s*$", wf, flags=re.MULTILINE
    ), "workflow_dispatch.inputs.artifacts_run_id is required"


def test_security_baseline_refresh_has_concurrency_block() -> None:
    repo_root = Path(__file__).parents[2]
    wf = (repo_root / ".github" / "workflows" / "security-baseline-refresh.yml").read_text(
        encoding="utf-8"
    )

    # Basic structural enforcement (avoid YAML parsing)
    assert re.search(r"^concurrency:\s*$", wf, flags=re.MULTILINE), "concurrency block required"
    assert re.search(r"^\s+group:\s+security-baseline-refresh-\$\{\{\s*github\.ref\s*\}\}\s*$", wf, flags=re.MULTILINE), (
        "concurrency.group must scope to github.ref"
    )
    assert re.search(r"^\s+cancel-in-progress:\s+true\s*$", wf, flags=re.MULTILINE), (
        "concurrency.cancel-in-progress must be true"
    )


def test_security_baseline_refresh_uses_force_with_lease_not_force() -> None:
    repo_root = Path(__file__).parents[2]
    wf = (repo_root / ".github" / "workflows" / "security-baseline-refresh.yml").read_text(
        encoding="utf-8"
    )

    assert "git push --force-with-lease" in wf, "workflow must use --force-with-lease"
    assert "git push -f" not in wf, "workflow must not use -f"


def test_security_baseline_refresh_download_step_is_deterministic_when_input_provided() -> None:
    repo_root = Path(__file__).parents[2]
    wf = (repo_root / ".github" / "workflows" / "security-baseline-refresh.yml").read_text(
        encoding="utf-8"
    )

    # Ensure we have a dedicated step that uses inputs.artifacts_run_id and run_id field.
    # Note: Using `inputs.` (not `github.event.inputs.`) is the modern recommended approach
    # as it works for both workflow_dispatch and workflow_call, and preserves boolean types.
    assert "Download security artifacts from specified run_id" in wf
    assert "inputs.artifacts_run_id" in wf
    assert re.search(r"^\s+run_id:\s+\$\{\{\s*inputs\.artifacts_run_id\s*\}\}\s*$", wf, flags=re.MULTILINE), (
        "download step must pass run_id from workflow_dispatch input"
    )
