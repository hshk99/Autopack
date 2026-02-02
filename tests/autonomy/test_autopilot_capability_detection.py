"""Tests for IMP-BLOCKED-002: Autopilot capability auto-detection.

This module tests the capability detection functionality that helps users
understand what's needed before enabling autopilot mode.
"""

import pytest


class TestAutopilotCapabilities:
    """Tests for AutopilotCapabilities dataclass."""

    def test_capabilities_default_values(self):
        """Test default values for AutopilotCapabilities."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities()
        assert caps.workspace_valid is False
        assert caps.intention_anchor_found is False
        assert caps.gap_scanner_available is True  # Default True
        assert caps.plan_proposer_available is True  # Default True
        assert caps.executor_context_available is True  # Default True
        assert caps.missing_components == []
        assert caps.recommendations == []

    def test_capabilities_is_ready_all_true(self):
        """Test is_ready returns True when all components available."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=True,
            intention_anchor_found=True,
            gap_scanner_available=True,
            plan_proposer_available=True,
            executor_context_available=True,
        )
        assert caps.is_ready is True

    def test_capabilities_is_ready_missing_workspace(self):
        """Test is_ready returns False when workspace is invalid."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=False,
            intention_anchor_found=True,
            gap_scanner_available=True,
            plan_proposer_available=True,
            executor_context_available=True,
        )
        assert caps.is_ready is False

    def test_capabilities_is_ready_missing_anchor(self):
        """Test is_ready returns False when intention anchor missing."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=True,
            intention_anchor_found=False,
            gap_scanner_available=True,
            plan_proposer_available=True,
            executor_context_available=True,
        )
        assert caps.is_ready is False

    def test_capabilities_to_dict(self):
        """Test to_dict serialization."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=True,
            intention_anchor_found=True,
            missing_components=["test_component"],
            recommendations=["test_recommendation"],
        )
        d = caps.to_dict()

        assert d["workspace_valid"] is True
        assert d["intention_anchor_found"] is True
        assert d["is_ready"] is True
        assert d["missing_components"] == ["test_component"]
        assert d["recommendations"] == ["test_recommendation"]

    def test_capabilities_get_status_message_ready(self):
        """Test status message when ready."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=True,
            intention_anchor_found=True,
        )
        msg = caps.get_status_message()
        assert "All components available" in msg
        assert "Ready to enable" in msg

    def test_capabilities_get_status_message_not_ready(self):
        """Test status message when not ready."""
        from autopack.autonomy.autopilot import AutopilotCapabilities

        caps = AutopilotCapabilities(
            workspace_valid=False,
            intention_anchor_found=True,
            missing_components=["workspace_directory"],
        )
        msg = caps.get_status_message()
        assert "Missing components" in msg
        assert "workspace_directory" in msg


class TestDetectAutopilotCapabilities:
    """Tests for detect_autopilot_capabilities function."""

    def test_detect_valid_workspace(self, tmp_path):
        """Test detection with valid workspace."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        caps = detect_autopilot_capabilities(tmp_path, check_intention_anchor=False)
        assert caps.workspace_valid is True

    def test_detect_invalid_workspace(self, tmp_path):
        """Test detection with non-existent workspace."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        non_existent = tmp_path / "does_not_exist"
        caps = detect_autopilot_capabilities(non_existent, check_intention_anchor=False)
        assert caps.workspace_valid is False
        assert "workspace_directory" in caps.missing_components
        assert len(caps.recommendations) > 0

    def test_detect_intention_anchor_in_root(self, tmp_path):
        """Test detection finds intention_anchor.yaml in root."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        # Create anchor file
        anchor_file = tmp_path / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.intention_anchor_found is True

    def test_detect_intention_anchor_in_autopack_dir(self, tmp_path):
        """Test detection finds intention_anchor.yaml in .autopack/."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        # Create .autopack directory and anchor file
        autopack_dir = tmp_path / ".autopack"
        autopack_dir.mkdir()
        anchor_file = autopack_dir / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.intention_anchor_found is True

    def test_detect_intention_anchor_in_config_dir(self, tmp_path):
        """Test detection finds intention_anchor.yaml in config/."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        # Create config directory and anchor file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        anchor_file = config_dir / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.intention_anchor_found is True

    def test_detect_missing_intention_anchor(self, tmp_path):
        """Test detection when intention_anchor.yaml is missing."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.intention_anchor_found is False
        assert "intention_anchor" in caps.missing_components
        assert any("intention_anchor.yaml" in r for r in caps.recommendations)

    def test_detect_skip_intention_anchor_check(self, tmp_path):
        """Test detection can skip intention anchor check."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        caps = detect_autopilot_capabilities(tmp_path, check_intention_anchor=False)
        assert caps.intention_anchor_found is True  # Skipped, defaults to True

    def test_detect_core_modules_available(self, tmp_path):
        """Test that core modules are detected as available."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        # Create anchor to make workspace valid
        anchor_file = tmp_path / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.gap_scanner_available is True
        assert caps.plan_proposer_available is True
        assert caps.executor_context_available is True

    def test_detect_all_ready(self, tmp_path):
        """Test detection when everything is available."""
        from autopack.autonomy.autopilot import detect_autopilot_capabilities

        # Create anchor to make workspace valid
        anchor_file = tmp_path / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        caps = detect_autopilot_capabilities(tmp_path)
        assert caps.is_ready is True
        assert caps.missing_components == []


class TestAutopilotControllerCapabilities:
    """Tests for AutopilotController capability methods."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=False,
        )

    def test_check_capabilities_caches_result(self, controller):
        """Test that check_capabilities caches the result."""
        caps1 = controller.check_capabilities(check_intention_anchor=False)
        caps2 = controller.get_capabilities()

        assert caps1 is caps2

    def test_get_capabilities_returns_none_before_check(self, controller):
        """Test get_capabilities returns None if not checked."""
        assert controller.get_capabilities() is None

    def test_is_ready_when_disabled(self, controller):
        """Test is_ready_for_autonomous_execution when disabled."""
        is_ready, reason, caps = controller.is_ready_for_autonomous_execution()

        assert is_ready is False
        assert "disabled" in reason.lower()
        assert "AUTOPACK_AUTOPILOT_ENABLED" in reason

    def test_is_ready_when_enabled_but_missing_caps(self, tmp_path):
        """Test is_ready when enabled but capabilities missing."""
        from autopack.autonomy.autopilot import AutopilotController

        controller = AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

        is_ready, reason, caps = controller.is_ready_for_autonomous_execution()

        assert is_ready is False
        assert "missing" in reason.lower()

    def test_is_ready_when_all_available(self, tmp_path):
        """Test is_ready when enabled and all capabilities available."""
        from autopack.autonomy.autopilot import AutopilotController

        # Create anchor to make workspace valid
        anchor_file = tmp_path / "intention_anchor.yaml"
        anchor_file.write_text("test: content")

        controller = AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

        is_ready, reason, caps = controller.is_ready_for_autonomous_execution()

        assert is_ready is True
        assert "ready" in reason.lower()

    def test_get_enable_instructions_returns_string(self, controller):
        """Test get_enable_instructions returns documentation."""
        instructions = controller.get_enable_instructions()

        assert isinstance(instructions, str)
        assert "AUTOPACK_AUTOPILOT_ENABLED" in instructions
        assert "AUTOPILOT_ENABLED" in instructions
        assert "Prerequisites" in instructions
        assert "detect_autopilot_capabilities" in instructions
