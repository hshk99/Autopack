"""BUILD-112 Phase 3: Production validation tests for deep retrieval escalation.

Tests Stage 2 deep retrieval triggers in production scenarios:
- Verify escalation from Stage 1 (basic) to Stage 2 (deep) retrieval
- Validate snippet caps (≤3 per category, ≤120 lines each)
- Check token budget compliance (≤12 snippets total)
- Verify citation format (file path + line range)

Run with:
    pytest tests/test_build112_phase3_deep_retrieval_validation.py -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.diagnostics.retrieval_triggers import RetrievalTriggerDetector
from autopack.diagnostics.deep_retrieval import DeepRetrievalEngine
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent


class TestDeepRetrievalEscalation:
    """Test Stage 2 deep retrieval escalation triggers."""

    def test_stage2_trigger_on_repeated_failures(self):
        """Test that Stage 2 triggers after repeated Stage 1 failures."""
        detector = RetrievalTriggerDetector()

        # Simulate 3 consecutive Stage 1 failures
        for i in range(3):
            result = detector.should_escalate_to_stage2(
                phase_id=f"test-phase-{i}",
                attempt_number=i + 1,
                previous_errors=["ImportError: module not found"] * (i + 1),
                stage1_retrieval_count=5
            )

        # After 3 failures, should trigger Stage 2
        assert result is True, "Stage 2 should trigger after 3 consecutive failures"

    def test_stage2_trigger_on_complex_error_pattern(self):
        """Test that Stage 2 triggers on complex multi-file error patterns."""
        detector = RetrievalTriggerDetector()

        complex_errors = [
            "ImportError: cannot import name 'ModelA' from 'module_a'",
            "AttributeError: 'ModelB' object has no attribute 'field_x'",
            "TypeError: ModelC.__init__() missing 1 required positional argument: 'config'"
        ]

        result = detector.should_escalate_to_stage2(
            phase_id="test-complex-errors",
            attempt_number=2,
            previous_errors=complex_errors,
            stage1_retrieval_count=8
        )

        assert result is True, "Stage 2 should trigger on complex multi-file error patterns"

    def test_stage2_snippet_caps(self):
        """Test that Stage 2 respects snippet caps (≤3 per category, ≤120 lines each)."""
        # Mock embedding model
        mock_embedding_model = Mock()
        mock_embedding_model.search.return_value = [
            {"path": "src/module_a.py", "content": "\n" * 100, "score": 0.95},
            {"path": "src/module_b.py", "content": "\n" * 100, "score": 0.90},
            {"path": "src/module_c.py", "content": "\n" * 100, "score": 0.85},
            {"path": "src/module_d.py", "content": "\n" * 100, "score": 0.80},  # Should be capped
        ]

        engine = DeepRetrievalEngine(embedding_model=mock_embedding_model)

        results = engine.retrieve_deep_context(
            query="ImportError in module_a",
            categories=["implementation", "tests", "config"],
            max_snippets_per_category=3,
            max_lines_per_snippet=120
        )

        # Verify caps
        for category, snippets in results.items():
            assert len(snippets) <= 3, f"Category '{category}' exceeds 3 snippets: {len(snippets)}"
            for snippet in snippets:
                line_count = snippet["content"].count("\n") + 1
                assert line_count <= 120, f"Snippet exceeds 120 lines: {line_count}"

    def test_stage2_token_budget_compliance(self):
        """Test that Stage 2 respects total token budget (≤12 snippets)."""
        mock_embedding_model = Mock()
        # Return 20 snippets (should be capped to 12)
        mock_embedding_model.search.return_value = [
            {"path": f"src/module_{i}.py", "content": "\n" * 50, "score": 0.9 - (i * 0.01)}
            for i in range(20)
        ]

        engine = DeepRetrievalEngine(embedding_model=mock_embedding_model)

        results = engine.retrieve_deep_context(
            query="Complex error pattern",
            categories=["implementation", "tests", "config", "docs"],
            max_snippets_per_category=3,
            max_lines_per_snippet=120
        )

        # Count total snippets across all categories
        total_snippets = sum(len(snippets) for snippets in results.values())
        assert total_snippets <= 12, f"Total snippets exceed budget: {total_snippets} > 12"

    def test_stage2_citation_format(self):
        """Test that Stage 2 snippets include proper citations (file path + line range)."""
        mock_embedding_model = Mock()
        mock_embedding_model.search.return_value = [
            {
                "path": "src/autopack/models.py",
                "content": "class Run(Base):\n    id = Column(String)\n    state = Column(String)",
                "score": 0.95,
                "start_line": 42,
                "end_line": 44
            }
        ]

        engine = DeepRetrievalEngine(embedding_model=mock_embedding_model)

        results = engine.retrieve_deep_context(
            query="Run model definition",
            categories=["implementation"],
            max_snippets_per_category=3,
            max_lines_per_snippet=120
        )

        # Verify citation format
        for category, snippets in results.items():
            for snippet in snippets:
                assert "path" in snippet, "Snippet missing 'path' field"
                assert "start_line" in snippet, "Snippet missing 'start_line' field"
                assert "end_line" in snippet, "Snippet missing 'end_line' field"
                assert snippet["path"].startswith("src/"), f"Invalid path format: {snippet['path']}"
                assert snippet["start_line"] > 0, "start_line must be positive"
                assert snippet["end_line"] >= snippet["start_line"], "end_line must be >= start_line"

    def test_diagnostics_agent_stage2_integration(self):
        """Test that DiagnosticsAgent properly integrates Stage 2 deep retrieval."""
        # Mock dependencies
        mock_embedding_model = Mock()
        mock_embedding_model.search.return_value = [
            {
                "path": "src/autopack/executor.py",
                "content": "def execute_phase():\n    pass",
                "score": 0.90,
                "start_line": 100,
                "end_line": 101
            }
        ]

        mock_memory_service = Mock()
        mock_memory_service.get_recent_context.return_value = []

        # Create DiagnosticsAgent with mocked dependencies
        agent = DiagnosticsAgent(
            run_id="test-run",
            workspace=Path("."),
            embedding_model=mock_embedding_model,
            memory_service=mock_memory_service,
            enable_second_opinion=False
        )

        # Simulate Stage 2 escalation scenario
        error_context = {
            "phase_id": "test-phase",
            "attempt_number": 3,
            "errors": [
                "ImportError: cannot import name 'execute_phase'",
                "ImportError: cannot import name 'execute_phase'",
                "ImportError: cannot import name 'execute_phase'"
            ],
            "stage1_retrieval_count": 5
        }

        # Trigger Stage 2 retrieval
        with patch.object(agent.trigger_detector, 'should_escalate_to_stage2', return_value=True):
            deep_context = agent.retrieve_deep_context_if_needed(
                error_context=error_context,
                query="ImportError in execute_phase"
            )

        # Verify Stage 2 was triggered and returned results
        assert deep_context is not None, "Stage 2 should return deep context"
        assert len(deep_context) > 0, "Stage 2 should return non-empty results"

    def test_stage2_no_false_positives(self):
        """Test that Stage 2 does NOT trigger on first attempt or simple errors."""
        detector = RetrievalTriggerDetector()

        # First attempt - should NOT trigger
        result = detector.should_escalate_to_stage2(
            phase_id="test-phase",
            attempt_number=1,
            previous_errors=["SyntaxError: invalid syntax"],
            stage1_retrieval_count=3
        )
        assert result is False, "Stage 2 should NOT trigger on first attempt"

        # Simple single-file error - should NOT trigger
        result = detector.should_escalate_to_stage2(
            phase_id="test-phase",
            attempt_number=2,
            previous_errors=["NameError: name 'x' is not defined"],
            stage1_retrieval_count=2
        )
        assert result is False, "Stage 2 should NOT trigger on simple single-file errors"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
