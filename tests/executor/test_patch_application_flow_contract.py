"""Contract tests for PatchApplicationFlow module.

Validates that PatchApplicationFlow correctly:
1. Applies structured edits (Stage 2) with StructuredEditApplicator
2. Applies regular git diff patches with GovernedApplyPath
3. Validates YAML/Docker Compose files pre-apply
4. Checks for goal drift before applying
5. Handles governance requests for protected paths
6. Derives allowed paths from deliverables
7. Writes phase summaries with apply stats

Refactored to reduce mock count by using shared fixtures and consolidating
repeated mock patterns. See IMP-TEST-009.
"""

import json
from pathlib import Path
from typing import Any, Callable
from unittest.mock import Mock, patch

import pytest

from autopack.executor.patch_application_flow import PatchApplicationFlow

# =============================================================================
# Shared Fixtures - Reduces mock duplication across tests
# =============================================================================


@pytest.fixture
def mock_executor(tmp_path: Path) -> Mock:
    """Create a mock executor with standard attributes."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_type = "project_build"
    executor.run_layout = Mock()
    executor._run_goal_anchor = None
    executor._update_phase_status = Mock()
    executor._try_handle_governance_request = Mock(return_value=False)
    return executor


@pytest.fixture
def patch_flow(mock_executor: Mock) -> PatchApplicationFlow:
    """Create a PatchApplicationFlow with mocked executor."""
    return PatchApplicationFlow(mock_executor)


@pytest.fixture
def mock_builder_result_with_edit_plan() -> Callable[[], Mock]:
    """Factory fixture for builder results with edit plans."""

    def _make(operations: list[Mock] | None = None) -> Mock:
        result = Mock()
        result.edit_plan = Mock()
        result.edit_plan.operations = operations or []
        result.patch_content = None
        return result

    return _make


@pytest.fixture
def mock_builder_result_with_patch() -> Callable[[str], Mock]:
    """Factory fixture for builder results with patch content."""

    def _make(patch_content: str = "diff --git a/file.txt") -> Mock:
        result = Mock()
        result.edit_plan = None
        result.patch_content = patch_content
        return result

    return _make


@pytest.fixture
def mock_structured_edit_result() -> Callable[[bool, int, int, str | None], Mock]:
    """Factory fixture for StructuredEditApplicator results."""

    def _make(
        success: bool = True,
        applied: int = 1,
        failed: int = 0,
        error_message: str | None = None,
    ) -> Mock:
        result = Mock()
        result.success = success
        result.operations_applied = applied
        result.operations_failed = failed
        result.error_message = error_message
        return result

    return _make


@pytest.fixture
def mock_yaml_validation_result() -> Callable[[bool, list[str] | None, list[str] | None], Mock]:
    """Factory fixture for YAML validation results."""

    def _make(
        valid: bool = True,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> Mock:
        result = Mock()
        result.valid = valid
        result.errors = errors or []
        result.warnings = warnings or []
        return result

    return _make


@pytest.fixture
def mock_governed_apply() -> Callable[[bool, str], tuple[Mock, Mock]]:
    """Factory fixture for GovernedApplyPath mocking."""

    def _make(success: bool = True, error: str = "") -> tuple[Mock, Mock]:
        instance = Mock()
        instance.apply_patch.return_value = (success, error)
        cls_mock = Mock(return_value=instance)
        return cls_mock, instance

    return _make


# Helper to set up common patches for regular patch tests
@pytest.fixture
def regular_patch_mocks(mock_governed_apply: Any) -> Callable[[bool, bool], dict[str, Any]]:
    """Create a context manager with common patches for regular patch tests."""

    def _make(yaml_valid: bool = True, drift_blocked: bool = False) -> dict[str, Any]:
        cls_mock, instance = mock_governed_apply(success=True, error="")
        return {
            "yaml_valid": yaml_valid,
            "drift_blocked": drift_blocked,
            "governed_cls": cls_mock,
            "governed_instance": instance,
        }

    return _make


# =============================================================================
# Routing Tests
# =============================================================================


def test_apply_patch_routes_to_structured_edits(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_edit_plan: Callable[[], Mock],
):
    """Test that apply_patch_with_validation routes to structured edits when edit_plan exists."""
    builder_result = mock_builder_result_with_edit_plan()

    with patch.object(
        patch_flow, "_apply_structured_edits", return_value=(True, "", {"mode": "structured_edit"})
    ):
        success, error, stats = patch_flow.apply_patch_with_validation(
            "phase-1", {}, builder_result, None
        )

    assert success is True
    assert stats["mode"] == "structured_edit"


def test_apply_patch_routes_to_regular_patch(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
):
    """Test that apply_patch_with_validation routes to regular patch when no edit_plan."""
    builder_result = mock_builder_result_with_patch()

    with patch.object(
        patch_flow, "_apply_regular_patch", return_value=(True, "", {"mode": "patch"})
    ):
        success, error, stats = patch_flow.apply_patch_with_validation(
            "phase-1", {}, builder_result, None
        )

    assert success is True
    assert stats["mode"] == "patch"


# =============================================================================
# Structured Edit Tests
# =============================================================================


def test_apply_structured_edits_applies_operations(
    patch_flow: PatchApplicationFlow,
    mock_structured_edit_result: Callable[[bool, int, int, str | None], Mock],
):
    """Test that _apply_structured_edits applies operations successfully."""
    operation = Mock(file_path="src/test.py")
    builder_result = Mock()
    builder_result.edit_plan = Mock(operations=[operation])

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator_class.return_value.apply_edit_plan.return_value = (
            mock_structured_edit_result(success=True, applied=1, failed=0)
        )

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {"existing_files": {}}
        )

    assert success is True
    assert stats["operations_applied"] == 1
    assert stats["operations_failed"] == 0


def test_apply_structured_edits_handles_failure(
    patch_flow: PatchApplicationFlow,
    mock_structured_edit_result: Callable[[bool, int, int, str | None], Mock],
):
    """Test that _apply_structured_edits handles application failures."""
    builder_result = Mock()
    builder_result.edit_plan = Mock(operations=[])

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator_class.return_value.apply_edit_plan.return_value = (
            mock_structured_edit_result(
                success=False, applied=0, failed=1, error_message="Failed to apply operation"
            )
        )

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {}
        )

    assert success is False
    assert error == "STRUCTURED_EDIT_FAILED"


# =============================================================================
# Regular Patch Tests
# =============================================================================


def test_apply_regular_patch_validates_yaml(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
):
    """Test that _apply_regular_patch validates YAML before applying."""
    builder_result = mock_builder_result_with_patch(
        "--- a/docker-compose.yml\n+++ b/docker-compose.yml"
    )

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(False, "YAML invalid")):
        success, error, stats = patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

    assert success is False
    assert error == "YAML invalid"


def test_apply_regular_patch_checks_goal_drift(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
):
    """Test that _apply_regular_patch checks for goal drift."""
    patch_flow.executor._run_goal_anchor = "Implement authentication"
    builder_result = mock_builder_result_with_patch()

    with (
        patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)),
        patch.object(patch_flow, "_check_goal_drift", return_value=(True, "Goal drift detected")),
    ):
        success, error, stats = patch_flow._apply_regular_patch(
            "phase-1", {"description": "Add logging"}, builder_result, None
        )

    assert success is False
    assert error == "Goal drift detected"


def test_apply_regular_patch_applies_with_governance(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
    mock_governed_apply: Callable[[bool, str], tuple[Mock, Mock]],
):
    """Test that _apply_regular_patch applies patch with governance checks."""
    builder_result = mock_builder_result_with_patch("diff --git a/src/test.py")
    governed_cls, _ = mock_governed_apply(success=True, error="")

    with (
        patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)),
        patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)),
        patch("autopack.executor.patch_application_flow.GovernedApplyPath", governed_cls),
    ):
        success, error, stats = patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

    assert success is True
    assert stats["mode"] == "patch"
    assert stats["patch_nonempty"] is True


def test_apply_regular_patch_handles_governance_request(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
    mock_governed_apply: Callable[[bool, str], tuple[Mock, Mock]],
):
    """Test that _apply_regular_patch handles governance requests."""
    patch_flow.executor._try_handle_governance_request = Mock(return_value=True)
    builder_result = mock_builder_result_with_patch("diff --git a/src/autopack/internal.py")
    governed_cls, _ = mock_governed_apply(success=False, error="Protected path")

    with (
        patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)),
        patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)),
        patch("autopack.executor.patch_application_flow.GovernedApplyPath", governed_cls),
    ):
        success, error, stats = patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

    # Governance was handled and approved
    assert patch_flow.executor._try_handle_governance_request.called


# =============================================================================
# YAML Validation Tests
# =============================================================================


def test_validate_yaml_in_patch_validates_docker_compose(
    patch_flow: PatchApplicationFlow,
    mock_yaml_validation_result: Callable[[bool, list[str] | None, list[str] | None], Mock],
):
    """Test that _validate_yaml_in_patch validates Docker Compose files."""
    patch_content = json.dumps(
        {
            "files": [
                {
                    "path": "docker-compose.yml",
                    "content": "version: '3'\nservices:\n  web:\n    image: nginx",
                }
            ]
        }
    )

    with patch(
        "autopack.executor.patch_application_flow.validate_docker_compose",
        return_value=mock_yaml_validation_result(valid=True),
    ) as mock_validate:
        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert mock_validate.called


def test_validate_yaml_in_patch_validates_generic_yaml(
    patch_flow: PatchApplicationFlow,
    mock_yaml_validation_result: Callable[[bool, list[str] | None, list[str] | None], Mock],
):
    """Test that _validate_yaml_in_patch validates generic YAML files."""
    patch_content = json.dumps(
        {"files": [{"path": "config.yaml", "content": "key: value\nlist:\n  - item1\n  - item2"}]}
    )

    with patch(
        "autopack.executor.patch_application_flow.validate_yaml_syntax",
        return_value=mock_yaml_validation_result(valid=True),
    ) as mock_validate:
        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert mock_validate.called


def test_validate_yaml_in_patch_returns_error_on_invalid(
    patch_flow: PatchApplicationFlow,
    mock_yaml_validation_result: Callable[[bool, list[str] | None, list[str] | None], Mock],
):
    """Test that _validate_yaml_in_patch returns error when YAML is invalid."""
    patch_content = json.dumps(
        {"files": [{"path": "config.yaml", "content": "invalid: yaml: content: ["}]}
    )

    with patch(
        "autopack.executor.patch_application_flow.validate_yaml_syntax",
        return_value=mock_yaml_validation_result(valid=False, errors=["Invalid YAML syntax"]),
    ):
        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is False
    assert "YAML validation failed" in error


def test_validate_yaml_in_patch_skips_non_yaml_patches(patch_flow: PatchApplicationFlow):
    """Test that _validate_yaml_in_patch skips validation for non-YAML patches."""
    patch_content = "diff --git a/src/test.py\n--- a/src/test.py\n+++ b/src/test.py"

    valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert error is None


# =============================================================================
# Goal Drift Tests
# =============================================================================


def test_check_goal_drift_blocks_when_drift_detected(patch_flow: PatchApplicationFlow):
    """Test that _check_goal_drift blocks when drift is detected."""
    patch_flow.executor._run_goal_anchor = "Implement user authentication"
    phase = {"description": "Add logging to unrelated module"}

    with patch(
        "autopack.executor.patch_application_flow.should_block_on_drift",
        return_value=(True, "BLOCKED: Goal drift"),
    ):
        should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is True
    assert "drift" in message.lower()


def test_check_goal_drift_allows_when_no_drift(patch_flow: PatchApplicationFlow):
    """Test that _check_goal_drift allows when no drift detected."""
    patch_flow.executor._run_goal_anchor = "Implement authentication"
    phase = {"description": "Add login form validation"}

    with patch(
        "autopack.executor.patch_application_flow.should_block_on_drift",
        return_value=(False, "OK"),
    ):
        should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is False


def test_check_goal_drift_returns_false_when_no_anchor(patch_flow: PatchApplicationFlow):
    """Test that _check_goal_drift returns False when no goal anchor set."""
    patch_flow.executor._run_goal_anchor = None
    phase = {"description": "Any change"}

    should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is False
    assert message is None


# =============================================================================
# Deliverables Path Derivation Tests
# =============================================================================


def test_derive_allowed_paths_from_deliverables_for_research(patch_flow: PatchApplicationFlow):
    """Test that _derive_allowed_paths_from_deliverables derives research paths."""
    phase = {"scope": {"deliverables": ["src/autopack/research/analysis.md"]}}

    # Create a mock module for the local import inside the function
    mock_module = Mock()
    mock_module.extract_deliverables_from_scope = Mock(
        return_value=["src/autopack/research/analysis.md"]
    )

    with patch.dict("sys.modules", {"autopack.executor.deliverables_validator": mock_module}):
        allowed = patch_flow._derive_allowed_paths_from_deliverables("phase-1", phase)

    assert allowed is not None
    assert "src/autopack/research/" in allowed


def test_derive_allowed_paths_handles_no_scope(patch_flow: PatchApplicationFlow):
    """Test that _derive_allowed_paths_from_deliverables handles missing scope."""
    phase = {}

    # Create a mock module for the local import inside the function
    mock_module = Mock()
    mock_module.extract_deliverables_from_scope = Mock(return_value=[])

    with patch.dict("sys.modules", {"autopack.executor.deliverables_validator": mock_module}):
        allowed = patch_flow._derive_allowed_paths_from_deliverables("phase-1", phase)

    assert allowed is None


# =============================================================================
# Phase Summary Tests
# =============================================================================


def test_write_phase_summary_writes_apply_stats(patch_flow: PatchApplicationFlow):
    """Test that _write_phase_summary writes apply stats to summary."""
    phase = {"phase_index": 1, "name": "Test Phase"}
    apply_stats_lines = ["Apply mode: patch", "Patch bytes: 1234"]

    patch_flow._write_phase_summary("phase-1", phase, apply_stats_lines)

    # Verify write_phase_summary was called
    assert patch_flow.executor.run_layout.write_phase_summary.called


def test_write_phase_summary_handles_errors_gracefully(patch_flow: PatchApplicationFlow):
    """Test that _write_phase_summary handles errors gracefully (non-blocking)."""
    patch_flow.executor.run_layout.write_phase_summary.side_effect = Exception("Write failed")
    phase = {"phase_index": 1, "name": "Test Phase"}

    # Should not raise exception
    patch_flow._write_phase_summary("phase-1", phase, ["Apply mode: patch"])


# =============================================================================
# Special Case Tests
# =============================================================================


def test_apply_regular_patch_uses_maintenance_mode_for_self_repair(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
):
    """Test that _apply_regular_patch enables internal mode for maintenance runs."""
    patch_flow.run_type = "self_repair"
    builder_result = mock_builder_result_with_patch("diff --git a/src/autopack/internal.py")

    with (
        patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)),
        patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)),
        patch("autopack.executor.patch_application_flow.GovernedApplyPath") as mock_governed,
    ):
        mock_governed.return_value.apply_patch.return_value = (True, "")

        patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

        # Verify autopack_internal_mode was True
        call_kwargs = mock_governed.call_args[1]
        assert call_kwargs.get("autopack_internal_mode") is True


def test_apply_structured_edits_caps_touched_paths_at_50(
    patch_flow: PatchApplicationFlow,
    mock_structured_edit_result: Callable[[bool, int, int, str | None], Mock],
):
    """Test that _apply_structured_edits caps touched_paths list at 50 entries."""
    # Create 100 operations
    operations = [Mock(file_path=f"file_{i}.py") for i in range(100)]
    builder_result = Mock()
    builder_result.edit_plan = Mock(operations=operations)

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator_class.return_value.apply_edit_plan.return_value = (
            mock_structured_edit_result(success=True, applied=100, failed=0)
        )

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {}
        )

    assert len(stats["touched_paths"]) == 50


def test_apply_regular_patch_derives_allowed_paths_when_not_provided(
    patch_flow: PatchApplicationFlow,
    mock_builder_result_with_patch: Callable[[str], Mock],
    mock_governed_apply: Callable[[bool, str], tuple[Mock, Mock]],
):
    """Test that _apply_regular_patch derives allowed_paths from deliverables when not provided."""
    builder_result = mock_builder_result_with_patch("diff --git a/src/autopack/research/test.md")
    phase = {"scope": {"deliverables": ["src/autopack/research/test.md"]}}
    governed_cls, _ = mock_governed_apply(success=True, error="")

    with (
        patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)),
        patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)),
        patch.object(
            patch_flow,
            "_derive_allowed_paths_from_deliverables",
            return_value=["src/autopack/research/"],
        ),
        patch("autopack.executor.patch_application_flow.GovernedApplyPath", governed_cls),
    ):
        patch_flow._apply_regular_patch("phase-1", phase, builder_result, None)

        # Verify derive was called
        patch_flow._derive_allowed_paths_from_deliverables.assert_called_once()
