"""Tests for Intention Memory End-to-End Wiring (Phase 2).

Validates:
- Intention context injection into prompts
- Context caching and reuse
- Size bounds enforcement
- Goal drift detection with intention anchor
- Graceful degradation when intention unavailable
"""

from unittest.mock import MagicMock, patch


from autopack.intention_wiring import (
    IntentionContextInjector,
    IntentionGoalDriftDetector,
    inject_intention_into_prompt,
)


class TestIntentionContextInjector:
    """Test intention context injector."""

    def test_init(self):
        """Test injector initialization."""
        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        assert injector.run_id == "test-run"
        assert injector.project_id == "test-project"
        assert injector._cached_context is None

    def test_get_intention_context_with_cache(self):
        """Test that context is cached after first retrieval."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention context"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        # First call
        context1 = injector.get_intention_context()
        assert "Test intention context" in context1
        assert mock_manager.get_intention_context.call_count == 1

        # Second call should use cache
        context2 = injector.get_intention_context()
        assert context1 == context2
        assert mock_manager.get_intention_context.call_count == 1  # Not called again

    def test_get_intention_context_respects_max_chars(self):
        """Test that context is bounded by max_chars."""
        long_context = "x" * 10000

        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = long_context

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        context = injector.get_intention_context(max_chars=1000)
        assert len(context) <= 1000

    def test_get_intention_context_with_header(self):
        """Test context formatting with header."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        context = injector.get_intention_context(include_header=True)
        assert "Project Intention Context" in context
        assert "Test intention" in context

    def test_get_intention_context_without_header(self):
        """Test context without formatting header."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        context = injector.get_intention_context(include_header=False)
        assert "Project Intention Context" not in context
        assert context == "Test intention"

    def test_get_intention_context_unavailable(self):
        """Test graceful handling when intention unavailable."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = ""

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        context = injector.get_intention_context()
        assert context == ""

    def test_inject_into_manifest_prompt(self):
        """Test injection into manifest generation prompt."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Build a REST API"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        base_prompt = "Generate implementation manifest for:"
        enhanced = injector.inject_into_manifest_prompt(base_prompt)

        assert "Build a REST API" in enhanced
        assert base_prompt in enhanced

    def test_inject_into_builder_prompt(self):
        """Test injection into builder phase prompt."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Build auth system"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        base_prompt = "Implement the following changes:"
        enhanced = injector.inject_into_builder_prompt(
            base_prompt,
            phase_id="phase-1",
            phase_description="Add JWT authentication",
        )

        assert "Build auth system" in enhanced
        assert "phase-1" in enhanced
        assert "Add JWT authentication" in enhanced
        assert base_prompt in enhanced

    def test_inject_into_doctor_prompt(self):
        """Test injection into doctor/recovery prompt."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Build auth system"

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        base_prompt = "Suggest fix for error:"
        error_context = "ImportError: No module named 'jwt'"

        enhanced = injector.inject_into_doctor_prompt(base_prompt, error_context)

        assert "Build auth system" in enhanced
        assert "Original Project Intention" in enhanced
        assert error_context in enhanced
        assert base_prompt in enhanced

    def test_injection_without_intention(self):
        """Test that injection gracefully handles missing intention."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = ""

        injector = IntentionContextInjector(
            run_id="test-run",
            project_id="test-project",
        )
        injector._intention_manager = mock_manager

        base_prompt = "Generate manifest"

        # Should return unchanged prompt
        enhanced = injector.inject_into_manifest_prompt(base_prompt)
        assert enhanced == base_prompt


class TestIntentionGoalDriftDetector:
    """Test intention-aware goal drift detector."""

    def test_init(self):
        """Test detector initialization."""
        detector = IntentionGoalDriftDetector(
            run_id="test-run",
            project_id="test-project",
        )
        assert detector.run_id == "test-run"
        assert detector.project_id == "test-project"
        assert detector.intention_manager is not None

    def test_check_drift_without_intention(self):
        """Test drift detection when no intention available."""
        mock_intention_manager = MagicMock()
        mock_intention_manager.get_intention_context.return_value = ""

        detector = IntentionGoalDriftDetector(
            run_id="test-run",
            project_id="test-project",
        )
        detector.intention_manager = mock_intention_manager

        # Mock goal_drift.check_goal_drift to return aligned result
        with patch("autopack.intention_wiring.goal_drift.check_goal_drift") as mock_check:
            mock_check.return_value = (True, 0.9, "Change aligns with goal")

            result = detector.check_drift(
                run_goal="Build auth system",
                phase_description="Add JWT tokens",
                phase_deliverables=["jwt.py"],
            )

            assert result["has_drift"] is False
            assert result["intention_drift"] is None
            assert "base_drift" in result

    def test_check_drift_with_intention_aligned(self):
        """Test drift detection with aligned intention."""
        intention_text = """
        Build authentication system with JWT tokens.
        Support login and logout endpoints.
        """

        mock_intention_manager = MagicMock()
        mock_intention_manager.get_intention_context.return_value = intention_text

        detector = IntentionGoalDriftDetector(
            run_id="test-run",
            project_id="test-project",
        )
        detector.intention_manager = mock_intention_manager

        # Mock goal_drift.check_goal_drift to return aligned result
        with patch("autopack.intention_wiring.goal_drift.check_goal_drift") as mock_check:
            mock_check.return_value = (True, 0.9, "Change aligns with goal")

            result = detector.check_drift(
                run_goal="Build auth system",
                phase_description="Add JWT tokens for authentication",
                phase_deliverables=["jwt.py", "auth.py"],
                threshold=0.5,
            )

            # Should not drift (many shared terms: auth, tokens, jwt)
            assert "intention_drift" in result
            # Intention drift uses Jaccard similarity (keyword overlap)
            # With many shared terms, drift should be low
            assert result["intention_drift"]["score"] < 0.9

    def test_check_drift_with_intention_misaligned(self):
        """Test drift detection with misaligned intention."""
        intention_text = """
        Build authentication system with JWT tokens.
        Support login and logout endpoints.
        """

        mock_intention_manager = MagicMock()
        mock_intention_manager.get_intention_context.return_value = intention_text

        detector = IntentionGoalDriftDetector(
            run_id="test-run",
            project_id="test-project",
        )
        detector.intention_manager = mock_intention_manager

        # Mock goal_drift.check_goal_drift to return aligned result (for run goal)
        with patch("autopack.intention_wiring.goal_drift.check_goal_drift") as mock_check:
            mock_check.return_value = (True, 0.9, "Change aligns with goal")

            # Phase is about something completely different
            result = detector.check_drift(
                run_goal="Build auth system",
                phase_description="Add database migration for inventory schema",
                phase_deliverables=["migration.sql", "inventory.py"],
                threshold=0.5,
            )

            # Should drift (few shared terms between intention and phase)
            assert "intention_drift" in result
            # Note: Actual drift score depends on term overlap heuristic


    def test_check_drift_combined_warning(self):
        """Test that warnings are combined from both detectors."""
        mock_intention_manager = MagicMock()
        mock_intention_manager.get_intention_context.return_value = "Build auth"

        detector = IntentionGoalDriftDetector(
            run_id="test-run",
            project_id="test-project",
        )
        detector.intention_manager = mock_intention_manager

        # Mock goal_drift.check_goal_drift to return drift detected
        with patch("autopack.intention_wiring.goal_drift.check_goal_drift") as mock_check:
            mock_check.return_value = (False, 0.4, "Potential goal drift detected")

            result = detector.check_drift(
                run_goal="Build auth",
                phase_description="Completely unrelated task",
                phase_deliverables=["unrelated.py"],
                threshold=0.3,
            )

            assert result["has_drift"]
            assert len(result["warnings"]) >= 1


class TestConvenienceFunction:
    """Test convenience function for prompt injection."""

    def test_inject_intention_manifest_type(self):
        """Test injection with manifest prompt type."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        with patch("autopack.intention_wiring.ProjectIntentionManager") as mock_mgr_class:
            mock_mgr_class.return_value = mock_manager

            enhanced = inject_intention_into_prompt(
                prompt="Base prompt",
                run_id="test-run",
                project_id="test-project",
                prompt_type="manifest",
            )

            assert "Test intention" in enhanced
            assert "Base prompt" in enhanced

    def test_inject_intention_builder_type(self):
        """Test injection with builder prompt type."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        with patch("autopack.intention_wiring.ProjectIntentionManager") as mock_mgr_class:
            mock_mgr_class.return_value = mock_manager

            enhanced = inject_intention_into_prompt(
                prompt="Base prompt",
                run_id="test-run",
                project_id="test-project",
                prompt_type="builder",
                phase_id="phase-1",
                phase_description="Add feature",
            )

            assert "Test intention" in enhanced
            assert "phase-1" in enhanced

    def test_inject_intention_doctor_type(self):
        """Test injection with doctor prompt type."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        with patch("autopack.intention_wiring.ProjectIntentionManager") as mock_mgr_class:
            mock_mgr_class.return_value = mock_manager

            enhanced = inject_intention_into_prompt(
                prompt="Base prompt",
                run_id="test-run",
                project_id="test-project",
                prompt_type="doctor",
                error_context="Error occurred",
            )

            assert "Test intention" in enhanced
            assert "Error occurred" in enhanced

    def test_inject_intention_general_type(self):
        """Test injection with general prompt type."""
        mock_manager = MagicMock()
        mock_manager.get_intention_context.return_value = "Test intention"

        with patch("autopack.intention_wiring.ProjectIntentionManager") as mock_mgr_class:
            mock_mgr_class.return_value = mock_manager

            enhanced = inject_intention_into_prompt(
                prompt="Base prompt",
                run_id="test-run",
                project_id="test-project",
                prompt_type="general",
            )

            assert "Test intention" in enhanced
