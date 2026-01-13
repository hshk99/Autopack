"""Contract tests for PatchApplicationFlow module.

Validates that PatchApplicationFlow correctly:
1. Applies structured edits (Stage 2) with StructuredEditApplicator
2. Applies regular git diff patches with GovernedApplyPath
3. Validates YAML/Docker Compose files pre-apply
4. Checks for goal drift before applying
5. Handles governance requests for protected paths
6. Derives allowed paths from deliverables
7. Writes phase summaries with apply stats
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


from autopack.executor.patch_application_flow import PatchApplicationFlow


def make_patch_flow(tmp_path: Path) -> PatchApplicationFlow:
    """Create a PatchApplicationFlow with mocked executor."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_type = "project_build"
    executor.run_layout = Mock()
    executor._run_goal_anchor = None
    executor._update_phase_status = Mock()
    executor._try_handle_governance_request = Mock(return_value=False)
    return PatchApplicationFlow(executor)


def test_apply_patch_routes_to_structured_edits(tmp_path: Path):
    """Test that apply_patch_with_validation routes to structured edits when edit_plan exists."""
    patch_flow = make_patch_flow(tmp_path)

    builder_result = Mock()
    builder_result.edit_plan = Mock()
    builder_result.edit_plan.operations = []
    builder_result.patch_content = None

    with patch.object(
        patch_flow, "_apply_structured_edits", return_value=(True, "", {"mode": "structured_edit"})
    ):
        success, error, stats = patch_flow.apply_patch_with_validation(
            "phase-1", {}, builder_result, None
        )

    assert success is True
    assert stats["mode"] == "structured_edit"


def test_apply_patch_routes_to_regular_patch(tmp_path: Path):
    """Test that apply_patch_with_validation routes to regular patch when no edit_plan."""
    patch_flow = make_patch_flow(tmp_path)

    builder_result = Mock()
    builder_result.edit_plan = None
    builder_result.patch_content = "diff --git a/file.txt"

    with patch.object(
        patch_flow, "_apply_regular_patch", return_value=(True, "", {"mode": "patch"})
    ):
        success, error, stats = patch_flow.apply_patch_with_validation(
            "phase-1", {}, builder_result, None
        )

    assert success is True
    assert stats["mode"] == "patch"


def test_apply_structured_edits_applies_operations(tmp_path: Path):
    """Test that _apply_structured_edits applies operations successfully."""
    patch_flow = make_patch_flow(tmp_path)

    # Create mock edit plan
    operation = Mock()
    operation.file_path = "src/test.py"

    edit_plan = Mock()
    edit_plan.operations = [operation]

    builder_result = Mock()
    builder_result.edit_plan = edit_plan

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.operations_applied = 1
        mock_result.operations_failed = 0
        mock_applicator.apply_edit_plan.return_value = mock_result
        mock_applicator_class.return_value = mock_applicator

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {"existing_files": {}}
        )

    assert success is True
    assert stats["operations_applied"] == 1
    assert stats["operations_failed"] == 0


def test_apply_structured_edits_handles_failure(tmp_path: Path):
    """Test that _apply_structured_edits handles application failures."""
    patch_flow = make_patch_flow(tmp_path)

    edit_plan = Mock()
    edit_plan.operations = []

    builder_result = Mock()
    builder_result.edit_plan = edit_plan

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.error_message = "Failed to apply operation"
        mock_result.operations_failed = 1
        mock_applicator.apply_edit_plan.return_value = mock_result
        mock_applicator_class.return_value = mock_applicator

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {}
        )

    assert success is False
    assert error == "STRUCTURED_EDIT_FAILED"


def test_apply_regular_patch_validates_yaml(tmp_path: Path):
    """Test that _apply_regular_patch validates YAML before applying."""
    patch_flow = make_patch_flow(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "--- a/docker-compose.yml\n+++ b/docker-compose.yml"

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(False, "YAML invalid")):
        success, error, stats = patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

    assert success is False
    assert error == "YAML invalid"


def test_apply_regular_patch_checks_goal_drift(tmp_path: Path):
    """Test that _apply_regular_patch checks for goal drift."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor._run_goal_anchor = "Implement authentication"

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/file.txt"

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)):
        with patch.object(
            patch_flow, "_check_goal_drift", return_value=(True, "Goal drift detected")
        ):
            success, error, stats = patch_flow._apply_regular_patch(
                "phase-1", {"description": "Add logging"}, builder_result, None
            )

    assert success is False
    assert error == "Goal drift detected"


def test_apply_regular_patch_applies_with_governance(tmp_path: Path):
    """Test that _apply_regular_patch applies patch with governance checks."""
    patch_flow = make_patch_flow(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/src/test.py"

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)):
        with patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)):
            with patch(
                "autopack.executor.patch_application_flow.GovernedApplyPath"
            ) as mock_governed:
                mock_instance = Mock()
                mock_instance.apply_patch.return_value = (True, "")
                mock_governed.return_value = mock_instance

                success, error, stats = patch_flow._apply_regular_patch(
                    "phase-1", {}, builder_result, None
                )

    assert success is True
    assert stats["mode"] == "patch"
    assert stats["patch_nonempty"] is True


def test_apply_regular_patch_handles_governance_request(tmp_path: Path):
    """Test that _apply_regular_patch handles governance requests."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor._try_handle_governance_request = Mock(return_value=True)

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/src/autopack/internal.py"

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)):
        with patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)):
            with patch(
                "autopack.executor.patch_application_flow.GovernedApplyPath"
            ) as mock_governed:
                mock_instance = Mock()
                mock_instance.apply_patch.return_value = (False, "Protected path")
                mock_governed.return_value = mock_instance

                success, error, stats = patch_flow._apply_regular_patch(
                    "phase-1", {}, builder_result, None
                )

    # Governance was handled and approved
    assert patch_flow.executor._try_handle_governance_request.called


def test_validate_yaml_in_patch_validates_docker_compose(tmp_path: Path):
    """Test that _validate_yaml_in_patch validates Docker Compose files."""
    patch_flow = make_patch_flow(tmp_path)

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

    with patch("autopack.executor.patch_application_flow.validate_docker_compose") as mock_validate:
        mock_result = Mock()
        mock_result.valid = True
        mock_result.warnings = []
        mock_validate.return_value = mock_result

        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert mock_validate.called


def test_validate_yaml_in_patch_validates_generic_yaml(tmp_path: Path):
    """Test that _validate_yaml_in_patch validates generic YAML files."""
    patch_flow = make_patch_flow(tmp_path)

    patch_content = json.dumps(
        {"files": [{"path": "config.yaml", "content": "key: value\nlist:\n  - item1\n  - item2"}]}
    )

    with patch("autopack.executor.patch_application_flow.validate_yaml_syntax") as mock_validate:
        mock_result = Mock()
        mock_result.valid = True
        mock_result.warnings = []
        mock_validate.return_value = mock_result

        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert mock_validate.called


def test_validate_yaml_in_patch_returns_error_on_invalid(tmp_path: Path):
    """Test that _validate_yaml_in_patch returns error when YAML is invalid."""
    patch_flow = make_patch_flow(tmp_path)

    patch_content = json.dumps(
        {"files": [{"path": "config.yaml", "content": "invalid: yaml: content: ["}]}
    )

    with patch("autopack.executor.patch_application_flow.validate_yaml_syntax") as mock_validate:
        mock_result = Mock()
        mock_result.valid = False
        mock_result.errors = ["Invalid YAML syntax"]
        mock_validate.return_value = mock_result

        valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is False
    assert "YAML validation failed" in error


def test_validate_yaml_in_patch_skips_non_yaml_patches(tmp_path: Path):
    """Test that _validate_yaml_in_patch skips validation for non-YAML patches."""
    patch_flow = make_patch_flow(tmp_path)

    patch_content = "diff --git a/src/test.py\n--- a/src/test.py\n+++ b/src/test.py"

    valid, error = patch_flow._validate_yaml_in_patch("phase-1", patch_content)

    assert valid is True
    assert error is None


def test_check_goal_drift_blocks_when_drift_detected(tmp_path: Path):
    """Test that _check_goal_drift blocks when drift is detected."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor._run_goal_anchor = "Implement user authentication"

    phase = {"description": "Add logging to unrelated module"}

    with patch(
        "autopack.executor.patch_application_flow.should_block_on_drift",
        return_value=(True, "BLOCKED: Goal drift"),
    ):
        should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is True
    assert "drift" in message.lower()


def test_check_goal_drift_allows_when_no_drift(tmp_path: Path):
    """Test that _check_goal_drift allows when no drift detected."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor._run_goal_anchor = "Implement authentication"

    phase = {"description": "Add login form validation"}

    with patch(
        "autopack.executor.patch_application_flow.should_block_on_drift", return_value=(False, "OK")
    ):
        should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is False


def test_check_goal_drift_returns_false_when_no_anchor(tmp_path: Path):
    """Test that _check_goal_drift returns False when no goal anchor set."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor._run_goal_anchor = None

    phase = {"description": "Any change"}

    should_block, message = patch_flow._check_goal_drift("phase-1", phase)

    assert should_block is False
    assert message is None


def test_derive_allowed_paths_from_deliverables_for_research(tmp_path: Path):
    """Test that _derive_allowed_paths_from_deliverables derives research paths."""

    patch_flow = make_patch_flow(tmp_path)

    phase = {"scope": {"deliverables": ["src/autopack/research/analysis.md"]}}

    # Create a mock module for the import
    mock_module = MagicMock()
    mock_module.extract_deliverables_from_scope = Mock(
        return_value=["src/autopack/research/analysis.md"]
    )

    # Patch sys.modules so the local import finds our mock
    with patch.dict("sys.modules", {"autopack.executor.deliverables_validator": mock_module}):
        allowed = patch_flow._derive_allowed_paths_from_deliverables("phase-1", phase)

    assert allowed is not None
    assert "src/autopack/research/" in allowed


def test_derive_allowed_paths_handles_no_scope(tmp_path: Path):
    """Test that _derive_allowed_paths_from_deliverables handles missing scope."""
    patch_flow = make_patch_flow(tmp_path)

    phase = {}

    with patch("autopack.deliverables_validator.extract_deliverables_from_scope", return_value=[]):
        allowed = patch_flow._derive_allowed_paths_from_deliverables("phase-1", phase)

    assert allowed is None


def test_write_phase_summary_writes_apply_stats(tmp_path: Path):
    """Test that _write_phase_summary writes apply stats to summary."""
    patch_flow = make_patch_flow(tmp_path)

    phase = {"phase_index": 1, "name": "Test Phase"}
    apply_stats_lines = ["Apply mode: patch", "Patch bytes: 1234"]

    patch_flow._write_phase_summary("phase-1", phase, apply_stats_lines)

    # Verify write_phase_summary was called
    assert patch_flow.executor.run_layout.write_phase_summary.called


def test_write_phase_summary_handles_errors_gracefully(tmp_path: Path):
    """Test that _write_phase_summary handles errors gracefully (non-blocking)."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.executor.run_layout.write_phase_summary.side_effect = Exception("Write failed")

    phase = {"phase_index": 1, "name": "Test Phase"}

    # Should not raise exception
    patch_flow._write_phase_summary("phase-1", phase, ["Apply mode: patch"])


def test_apply_regular_patch_uses_maintenance_mode_for_self_repair(tmp_path: Path):
    """Test that _apply_regular_patch enables internal mode for maintenance runs."""
    patch_flow = make_patch_flow(tmp_path)
    patch_flow.run_type = "self_repair"

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/src/autopack/internal.py"

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)):
        with patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)):
            with patch(
                "autopack.executor.patch_application_flow.GovernedApplyPath"
            ) as mock_governed:
                mock_instance = Mock()
                mock_instance.apply_patch.return_value = (True, "")
                mock_governed.return_value = mock_instance

                patch_flow._apply_regular_patch("phase-1", {}, builder_result, None)

                # Verify autopack_internal_mode was True
                call_kwargs = mock_governed.call_args[1]
                assert call_kwargs.get("autopack_internal_mode") is True


def test_apply_structured_edits_caps_touched_paths_at_50(tmp_path: Path):
    """Test that _apply_structured_edits caps touched_paths list at 50 entries."""
    patch_flow = make_patch_flow(tmp_path)

    # Create 100 operations
    operations = [Mock(file_path=f"file_{i}.py") for i in range(100)]

    edit_plan = Mock()
    edit_plan.operations = operations

    builder_result = Mock()
    builder_result.edit_plan = edit_plan

    with patch("autopack.structured_edits.StructuredEditApplicator") as mock_applicator_class:
        mock_applicator = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.operations_applied = 100
        mock_result.operations_failed = 0
        mock_applicator.apply_edit_plan.return_value = mock_result
        mock_applicator_class.return_value = mock_applicator

        success, error, stats = patch_flow._apply_structured_edits(
            "phase-1", {}, builder_result, {}
        )

    assert len(stats["touched_paths"]) == 50


def test_apply_regular_patch_derives_allowed_paths_when_not_provided(tmp_path: Path):
    """Test that _apply_regular_patch derives allowed_paths from deliverables when not provided."""
    patch_flow = make_patch_flow(tmp_path)

    builder_result = Mock()
    builder_result.patch_content = "diff --git a/src/autopack/research/test.md"

    phase = {"scope": {"deliverables": ["src/autopack/research/test.md"]}}

    with patch.object(patch_flow, "_validate_yaml_in_patch", return_value=(True, None)):
        with patch.object(patch_flow, "_check_goal_drift", return_value=(False, None)):
            with patch.object(
                patch_flow,
                "_derive_allowed_paths_from_deliverables",
                return_value=["src/autopack/research/"],
            ):
                with patch(
                    "autopack.executor.patch_application_flow.GovernedApplyPath"
                ) as mock_governed:
                    mock_instance = Mock()
                    mock_instance.apply_patch.return_value = (True, "")
                    mock_governed.return_value = mock_instance

                    patch_flow._apply_regular_patch("phase-1", phase, builder_result, None)

                    # Verify derive was called
                    patch_flow._derive_allowed_paths_from_deliverables.assert_called_once()
