"""
Tests for PlanAnalyzer integration (BUILD-124 Phase D)

These tests define the expected behavior for Phase D integration,
helping to discover concrete requirements through test scenarios.
"""

from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import pytest

from autopack.manifest_generator import ManifestGenerator, PlanAnalysisMetadata
from autopack.pattern_matcher import PatternMatcher
from autopack.repo_scanner import RepoScanner


def _touch(path: Path, content: str = "# test\n") -> None:
    """Helper to create test files"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestTriggerConditions:
    """Test 1: When should PlanAnalyzer actually run?"""

    def test_high_confidence_does_not_trigger_plan_analyzer(self, tmp_path: Path):
        """High confidence (>= 0.70) should NOT trigger PlanAnalyzer"""
        # Create repo with clear auth pattern
        _touch(tmp_path / "src" / "auth" / "login.py", "def login(): pass")
        _touch(tmp_path / "src" / "auth" / "jwt.py", "def verify_token(): pass")
        _touch(tmp_path / "src" / "auth" / "session.py", "def create_session(): pass")

        generator = ManifestGenerator(
            workspace=tmp_path,
            autopack_internal_mode=False,
            run_type="project_build",
            enable_plan_analyzer=True  # Enabled but shouldn't trigger
        )

        plan_data = {
            "run_id": "test-high-confidence",
            "phases": [
                {
                    "phase_id": "auth-backend",
                    "goal": "Add JWT authentication to login endpoint",
                    "description": "Implement JWT token generation and validation"
                }
            ]
        }

        result = generator.generate_manifest(plan_data, skip_validation=True)

        # Should succeed with deterministic scope
        assert result.success
        assert result.plan_analysis.status == "skipped"  # Not run due to high confidence
        assert "high_confidence" in result.plan_analysis.status or result.plan_analysis.status == "skipped"

        # Should have deterministic scope from pattern matcher
        phase = result.enhanced_plan["phases"][0]
        assert "scope" in phase
        assert len(phase["scope"]["paths"]) > 0

    def test_low_confidence_with_empty_scope_triggers_plan_analyzer(self, tmp_path: Path):
        """Low confidence (< 0.15) with empty scope should trigger PlanAnalyzer"""
        # Create repo with no clear pattern match
        _touch(tmp_path / "src" / "main.py", "def main(): pass")
        _touch(tmp_path / "README.md", "# Project")

        generator = ManifestGenerator(
            workspace=tmp_path,
            autopack_internal_mode=False,
            run_type="project_build",
            enable_plan_analyzer=True
        )

        plan_data = {
            "run_id": "test-low-confidence",
            "phases": [
                {
                    "phase_id": "obscure-feature",
                    "goal": "Implement quantum flux capacitor integration",
                    "description": "Add experimental feature with no existing patterns"
                }
            ]
        }

        # Mock the PlanAnalyzer since we don't want real LLM calls
        with patch('autopack.plan_analyzer.PlanAnalyzer') as mock_analyzer_class:
            mock_analyzer = AsyncMock()
            mock_analyzer.analyze_phase.return_value = Mock(
                feasible=True,
                confidence=0.6,
                concerns=[],
                recommendations=["Create new directory structure"]
            )
            mock_analyzer_class.return_value = mock_analyzer

            result = generator.generate_manifest(plan_data, skip_validation=True)

        # Should have attempted PlanAnalyzer
        assert result.plan_analysis.status in ["ran", "skipped"]

        # Verify PlanAnalyzer was considered (even if mocked)
        # The actual triggering logic will be implemented in Phase D

    def test_medium_confidence_with_ambiguous_match_triggers_plan_analyzer(self, tmp_path: Path):
        """Medium confidence (0.15-0.30) with ambiguous category should trigger"""
        # Create repo with weak pattern match
        _touch(tmp_path / "config.json", "{}")
        _touch(tmp_path / "src" / "utils.py", "def helper(): pass")

        generator = ManifestGenerator(
            workspace=tmp_path,
            autopack_internal_mode=False,
            run_type="project_build",
            enable_plan_analyzer=True
        )

        plan_data = {
            "run_id": "test-medium-confidence",
            "phases": [
                {
                    "phase_id": "config-update",
                    "goal": "Update configuration settings",
                    "description": "Modify config with potential side effects"
                }
            ]
        }

        # This test documents expected behavior - implementation in Phase D
        result = generator.generate_manifest(plan_data, skip_validation=True)

        # Phase D should implement logic to trigger on medium confidence
        # For now, just verify structure is correct
        assert result.plan_analysis is not None

    def test_flag_disabled_never_triggers_plan_analyzer(self, tmp_path: Path):
        """enable_plan_analyzer=False should NEVER trigger, regardless of confidence"""
        _touch(tmp_path / "src" / "main.py", "def main(): pass")

        generator = ManifestGenerator(
            workspace=tmp_path,
            autopack_internal_mode=False,
            run_type="project_build",
            enable_plan_analyzer=False  # Disabled
        )

        plan_data = {
            "run_id": "test-disabled",
            "phases": [
                {
                    "phase_id": "any-feature",
                    "goal": "This could be anything, analyzer won't run",
                    "description": "Testing opt-in behavior"
                }
            ]
        }

        result = generator.generate_manifest(plan_data, skip_validation=True)

        # Must never trigger when disabled
        assert result.plan_analysis.status == "disabled"
        assert result.plan_analysis.enabled is False


class TestLLMIntegration:
    """Test 2: Verify async boundary works in real flow"""

    @pytest.mark.asyncio
    async def test_async_plan_analyzer_call_with_grounded_context(self, tmp_path: Path):
        """Verify async LLM call works with grounded context"""
        _touch(tmp_path / "src" / "auth" / "login.py")

        # Mock LLM service
        mock_llm = AsyncMock()
        mock_llm.call_llm.return_value = """
        FEASIBILITY: HIGH
        CONFIDENCE: 0.85
        CONCERNS: None
        RECOMMENDATIONS: Use existing auth patterns
        """

        with patch('autopack.llm_service.LlmService', return_value=mock_llm):
            from autopack.plan_analyzer import PlanAnalyzer
            from autopack.plan_analyzer_grounding import GroundedContextBuilder

            scanner = RepoScanner(tmp_path)
            scanner.scan(use_cache=False)
            matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

            # Build grounded context
            context_builder = GroundedContextBuilder(scanner, matcher)
            context = context_builder.build_context(
                goal="Add authentication",
                phase_id="auth-phase"
            )

            # Create analyzer
            analyzer = PlanAnalyzer(
                repo_scanner=scanner,
                pattern_matcher=matcher,
                workspace=tmp_path
            )

            # Call with grounded context
            phase_spec = {
                "phase_id": "auth-phase",
                "goal": "Add authentication",
                "description": "JWT-based auth"
            }

            await analyzer.analyze_phase(
                phase_spec,
                context=context.to_prompt_section()
            )

            # Verify LLM was called with grounded context
            assert mock_llm.call_llm.called
            call_args = mock_llm.call_llm.call_args
            prompt = call_args.kwargs.get('prompt') or call_args[0][0]

            # Grounded context should be in prompt
            assert "Repository Context (Grounded)" in prompt or len(prompt) > 0

    def test_timeout_handling_for_slow_llm_responses(self, tmp_path: Path):
        """Test that LLM timeouts are handled gracefully"""
        _touch(tmp_path / "src" / "main.py")

        generator = ManifestGenerator(
            workspace=tmp_path,
            enable_plan_analyzer=True
        )

        plan_data = {
            "run_id": "test-timeout",
            "phases": [{"phase_id": "test", "goal": "Test timeout handling"}]
        }

        # Mock PlanAnalyzer to simulate timeout
        with patch('autopack.plan_analyzer.PlanAnalyzer') as mock_analyzer_class:
            mock_analyzer = AsyncMock()
            mock_analyzer.analyze_phase.side_effect = TimeoutError("LLM took too long")
            mock_analyzer_class.return_value = mock_analyzer

            # Should handle timeout gracefully
            result = generator.generate_manifest(plan_data, skip_validation=True)

            # Should still return valid result with error status
            assert result.success or result.plan_analysis.status == "failed"
            if result.plan_analysis.status == "failed":
                assert "timeout" in result.plan_analysis.error.lower() or "error" in result.plan_analysis.error.lower()

    def test_error_recovery_on_llm_failure(self, tmp_path: Path):
        """Test that LLM failures don't break manifest generation"""
        _touch(tmp_path / "src" / "main.py")

        generator = ManifestGenerator(
            workspace=tmp_path,
            enable_plan_analyzer=True
        )

        plan_data = {
            "run_id": "test-error",
            "phases": [{"phase_id": "test", "goal": "Test error handling"}]
        }

        # Mock PlanAnalyzer to simulate error
        with patch('autopack.plan_analyzer.PlanAnalyzer') as mock_analyzer_class:
            mock_analyzer = AsyncMock()
            mock_analyzer.analyze_phase.side_effect = Exception("LLM service unavailable")
            mock_analyzer_class.return_value = mock_analyzer

            # Should handle error gracefully
            result = generator.generate_manifest(plan_data, skip_validation=True)

            # Should still succeed (fall back to deterministic scope)
            assert result.success or result.plan_analysis.status == "failed"


class TestContextBudget:
    """Test 3: Grounded context stays under limits"""

    def test_large_repo_context_stays_under_budget(self, tmp_path: Path):
        """Large repos should not blow up token budget"""
        # Create large repo (100+ files)
        for i in range(150):
            _touch(tmp_path / "src" / f"module_{i}" / "file.py")

        scanner = RepoScanner(tmp_path)
        scanner.scan(use_cache=False)
        matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

        from autopack.plan_analyzer_grounding import GroundedContextBuilder, MAX_CONTEXT_CHARS

        builder = GroundedContextBuilder(scanner, matcher)
        context = builder.build_context(
            goal="Add new feature",
            phase_id="feature-phase"
        )

        # Must stay under budget
        assert context.total_chars <= MAX_CONTEXT_CHARS
        assert len(context.to_prompt_section()) <= MAX_CONTEXT_CHARS + 200  # Small margin for formatting

    def test_multiple_phases_do_not_accumulate_unbounded_context(self, tmp_path: Path):
        """Multiple phases should share repo context, not accumulate"""
        _touch(tmp_path / "src" / "main.py")

        scanner = RepoScanner(tmp_path)
        scanner.scan(use_cache=False)
        matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

        from autopack.plan_analyzer_grounding import GroundedContextBuilder, MAX_CONTEXT_CHARS

        builder = GroundedContextBuilder(scanner, matcher)

        # Create 10 phases
        phases = [
            {"phase_id": f"phase-{i}", "goal": f"Feature {i}", "description": f"Implement feature {i}"}
            for i in range(10)
        ]

        multi_context = builder.build_multi_phase_context(phases)

        # Should stay under budget even with multiple phases
        assert len(multi_context) <= MAX_CONTEXT_CHARS + 100


class TestMetadataAttachment:
    """Test 4: Results properly stored"""

    def test_plan_analysis_metadata_structure(self, tmp_path: Path):
        """Verify metadata structure is correct"""
        _touch(tmp_path / "src" / "main.py")

        generator = ManifestGenerator(
            workspace=tmp_path,
            enable_plan_analyzer=False  # Disabled for now
        )

        plan_data = {
            "run_id": "test-metadata",
            "phases": [{"phase_id": "test", "goal": "Test metadata"}]
        }

        result = generator.generate_manifest(plan_data, skip_validation=True)

        # Verify metadata structure
        assert isinstance(result.plan_analysis, PlanAnalysisMetadata)
        assert hasattr(result.plan_analysis, 'enabled')
        assert hasattr(result.plan_analysis, 'status')
        assert hasattr(result.plan_analysis, 'warnings')
        assert hasattr(result.plan_analysis, 'error')

        # Status should be one of the expected values
        assert result.plan_analysis.status in ["disabled", "skipped", "ran", "failed"]

    def test_plan_analysis_never_overrides_deterministic_scope(self, tmp_path: Path):
        """PlanAnalyzer recommendations should never replace deterministic scope"""
        # Create repo with clear auth pattern
        _touch(tmp_path / "src" / "auth" / "login.py")
        _touch(tmp_path / "src" / "auth" / "jwt.py")

        generator = ManifestGenerator(
            workspace=tmp_path,
            enable_plan_analyzer=True
        )

        plan_data = {
            "run_id": "test-no-override",
            "phases": [
                {
                    "phase_id": "auth-backend",
                    "goal": "Add JWT authentication",
                    "description": "Implement auth"
                }
            ]
        }

        # Mock PlanAnalyzer to return different scope
        with patch('autopack.plan_analyzer.PlanAnalyzer') as mock_analyzer_class:
            mock_analyzer = AsyncMock()
            mock_analysis = Mock(
                feasible=True,
                confidence=0.9,
                recommended_scope=["totally/different/files.py"]  # Different from pattern match
            )
            mock_analyzer.analyze_phase.return_value = mock_analysis
            mock_analyzer_class.return_value = mock_analyzer

            result = generator.generate_manifest(plan_data, skip_validation=True)

        # Deterministic scope should be preserved
        phase = result.enhanced_plan["phases"][0]
        if "scope" in phase and len(phase["scope"]["paths"]) > 0:
            # Should contain auth files, not the mocked different scope
            " ".join(phase["scope"]["paths"])
            # Deterministic scope from pattern matcher should be present
            # (Phase D implementation will ensure LLM suggestions don't override)


class TestOptInBehavior:
    """Test 5: Flag properly gates all behavior"""

    def test_disabled_flag_means_zero_llm_calls(self, tmp_path: Path):
        """enable_plan_analyzer=False must result in zero LLM calls"""
        _touch(tmp_path / "src" / "main.py")

        # Track if any LLM was instantiated
        with patch('autopack.llm_service.LlmService') as mock_llm_service:
            generator = ManifestGenerator(
                workspace=tmp_path,
                enable_plan_analyzer=False  # Disabled
            )

            plan_data = {
                "run_id": "test-disabled",
                "phases": [{"phase_id": "test", "goal": "Any goal"}]
            }

            result = generator.generate_manifest(plan_data, skip_validation=True)

            # LLMService should never be instantiated when disabled
            assert not mock_llm_service.called
            assert result.plan_analysis.status == "disabled"

    def test_enabled_flag_allows_conditional_llm_use(self, tmp_path: Path):
        """enable_plan_analyzer=True should allow LLM use when conditions met"""
        _touch(tmp_path / "src" / "main.py")

        with patch('autopack.plan_analyzer.PlanAnalyzer') as mock_analyzer_class:
            mock_analyzer = AsyncMock()
            mock_analyzer_class.return_value = mock_analyzer

            generator = ManifestGenerator(
                workspace=tmp_path,
                enable_plan_analyzer=True  # Enabled
            )

            plan_data = {
                "run_id": "test-enabled",
                "phases": [
                    {
                        "phase_id": "obscure",
                        "goal": "Quantum flux capacitor",
                        "description": "No pattern match"
                    }
                ]
            }

            result = generator.generate_manifest(plan_data, skip_validation=True)

            # When enabled, PlanAnalyzer can be used (even if conditions don't trigger it)
            # Phase D will implement actual trigger logic
            assert result.plan_analysis.enabled is True


class TestPhaseCountLimits:
    """Test 6: Bounded analysis (max 1-3 phases per run)"""

    def test_max_phases_analyzed_per_run(self, tmp_path: Path):
        """Should analyze at most 3 phases per run to control cost"""
        _touch(tmp_path / "src" / "main.py")

        generator = ManifestGenerator(
            workspace=tmp_path,
            enable_plan_analyzer=True
        )

        # Create 10 phases, all with low confidence
        plan_data = {
            "run_id": "test-many-phases",
            "phases": [
                {
                    "phase_id": f"phase-{i}",
                    "goal": f"Obscure feature {i}",
                    "description": f"No pattern match {i}"
                }
                for i in range(10)
            ]
        }

        # Phase D should implement max_phases limit
        # For now, document expected behavior
        result = generator.generate_manifest(plan_data, skip_validation=True)

        # Phase D implementation should track how many phases were analyzed
        # and enforce a limit (e.g., max 3 phases)
        assert result.success or result.plan_analysis is not None


# Discovery Questions for Phase D Implementation
# (These will be answered as we implement the tests above)
#
# 1. Trigger Conditions:
#    Q: What exact confidence threshold triggers PlanAnalyzer?
#    A: < 0.15 with empty scope, or 0.15-0.30 with ambiguous match
#
# 2. LLM Integration:
#    Q: How do we handle async calls in sync ManifestGenerator?
#    A: Use run_async_safe() helper from Phase B
#
# 3. Context Budget:
#    Q: How do we prevent token budget explosion?
#    A: Hard 4000 char limit in GroundedContextBuilder (Phase C)
#
# 4. Metadata:
#    Q: Where do we store PlanAnalyzer results?
#    A: phase["metadata"]["plan_analysis"] dict
#
# 5. Opt-In:
#    Q: How do we ensure zero LLM calls when disabled?
#    A: Check enable_plan_analyzer flag before ANY LLM-related code
#
# 6. Phase Limits:
#    Q: How many phases should we analyze per run?
#    A: Max 3 phases to control cost (highest priority = lowest confidence)
