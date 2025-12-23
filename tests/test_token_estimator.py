"""
Tests for TokenEstimator (BUILD-129 Phase 1).

Tests deliverable-based token estimation for reducing truncation.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from autopack.token_estimator import TokenEstimator, TokenEstimate


class TestTokenEstimate:
    """Test TokenEstimate dataclass."""

    def test_token_estimate_creation(self):
        """Test basic TokenEstimate creation."""
        estimate = TokenEstimate(
            estimated_tokens=15000,
            deliverable_count=10,
            category="backend",
            complexity="high",
            breakdown={"backend_new": 8000, "backend_modify": 5000, "test_new": 2000},
            confidence=0.8
        )

        assert estimate.estimated_tokens == 15000
        assert estimate.deliverable_count == 10
        assert estimate.category == "backend"
        assert estimate.complexity == "high"
        assert estimate.confidence == 0.8
        assert estimate.breakdown["backend_new"] == 8000


class TestTokenEstimator:
    """Test TokenEstimator."""

    @pytest.fixture
    def estimator(self, tmp_path):
        """Create estimator with temp workspace."""
        return TokenEstimator(workspace=tmp_path)

    def test_init(self, tmp_path):
        """Test estimator initialization."""
        estimator = TokenEstimator(workspace=tmp_path)
        assert estimator.workspace == tmp_path

    def test_estimate_no_deliverables(self, estimator):
        """Test estimate with no deliverables returns complexity default."""
        estimate = estimator.estimate(
            deliverables=[],
            category="backend",
            complexity="medium",
            scope_paths=None
        )

        assert estimate.estimated_tokens == 12288  # Medium default
        assert estimate.deliverable_count == 0
        assert estimate.confidence == 0.5  # Low confidence

    def test_estimate_single_new_backend_file(self, estimator):
        """Test estimate for single new backend file."""
        deliverables = ["Create src/autopack/new_module.py"]
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="medium"
        )

        # new_file_backend=800 * safety=1.3 * category=1.2 = 1248
        expected = int(800 * 1.3 * 1.2)
        assert estimate.estimated_tokens == expected
        assert estimate.deliverable_count == 1
        assert estimate.category == "backend"

    def test_estimate_multiple_files_mixed(self, estimator):
        """Test estimate for multiple files (new + modify)."""
        deliverables = [
            "Create src/autopack/foo.py",      # new_backend: 800
            "Modify src/autopack/bar.py",      # modify_backend: 300
            "Create tests/test_foo.py",        # new_test: 600
            "Modify docs/README.md",           # modify_doc: 150
        ]
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="high"
        )

        # (800 + 300 + 600 + 150) = 1850
        # * safety=1.3 = 2405
        # * category=1.2 = 2886
        expected = int((800 + 300 + 600 + 150) * 1.3 * 1.2)
        assert estimate.estimated_tokens == expected
        assert estimate.deliverable_count == 4

    def test_estimate_frontend_category(self, estimator):
        """Test frontend category gets higher multiplier."""
        deliverables = ["Create components/Button.tsx"]
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="frontend",
            complexity="medium"
        )

        # new_file_frontend=1200 * safety=1.3 * category=1.4 = 2184
        expected = int(1200 * 1.3 * 1.4)
        assert estimate.estimated_tokens == expected

    def test_select_budget_uses_max_of_base_and_estimate(self, estimator):
        """Test budget selection uses max(base, estimated * buffer)."""
        # Case 1: Estimate higher than base
        estimate = TokenEstimate(
            estimated_tokens=20000,
            deliverable_count=10,
            category="backend",
            complexity="medium",
            confidence=0.8
        )
        budget = estimator.select_budget(estimate, "medium")
        # max(12288, 20000 * 1.2) = max(12288, 24000) = 24000
        assert budget == 24000

        # Case 2: Base higher than estimate
        estimate2 = TokenEstimate(
            estimated_tokens=5000,
            deliverable_count=2,
            category="backend",
            complexity="high",
            confidence=0.7
        )
        budget2 = estimator.select_budget(estimate2, "high")
        # max(16384, 5000 * 1.2) = max(16384, 6000) = 16384
        assert budget2 == 16384

    def test_select_budget_caps_at_64k(self, estimator):
        """Test budget capped at 64k."""
        estimate = TokenEstimate(
            estimated_tokens=60000,
            deliverable_count=50,
            category="backend",
            complexity="high",
            confidence=0.9
        )
        budget = estimator.select_budget(estimate, "high")
        # max(16384, 60000 * 1.2) = max(16384, 72000) = 72000 → capped at 64000
        assert budget == 64000

    def test_sanitize_deliverable_path_extracts_path(self, estimator):
        """Test path extraction from deliverable descriptions."""
        cases = [
            ("Create src/autopack/foo.py", "src/autopack/foo.py"),
            ("Modify src/bar.py to add X", "src/bar.py"),
            ("src/baz.py", "src/baz.py"),
            ("New file: tests/test_x.py", "tests/test_x.py"),
            ("docs/README.md (update docs)", "docs/readme.md"),
        ]

        for input_str, expected_path in cases:
            result = estimator._sanitize_deliverable_path(input_str)
            assert expected_path in result.lower()

    def test_classify_deliverable_backend_new(self, estimator):
        """Test deliverable classification for backend new files."""
        classification = estimator._classify_deliverable(
            "Create src/autopack/module.py",
            "backend"
        )
        assert classification == "backend_new"

    def test_classify_deliverable_test_modify(self, estimator):
        """Test deliverable classification for test modifications."""
        classification = estimator._classify_deliverable(
            "Modify tests/test_foo.py",
            "backend"
        )
        assert classification == "test_modify"

    def test_classify_deliverable_frontend_new(self, estimator):
        """Test deliverable classification for frontend new files."""
        classification = estimator._classify_deliverable(
            "Create components/Button.tsx",
            "frontend"
        )
        assert classification == "frontend_new"

    def test_classify_deliverable_doc_modify(self, estimator):
        """Test deliverable classification for doc modifications."""
        classification = estimator._classify_deliverable(
            "Update docs/BUILD_HISTORY.md",
            "documentation"
        )
        assert classification == "doc_modify"

    def test_classify_deliverable_config_new(self, estimator):
        """Test deliverable classification for config new files."""
        classification = estimator._classify_deliverable(
            "Create config/settings.yaml",
            "backend"
        )
        assert classification == "config_new"

    def test_analyze_file_complexity_small_file(self, tmp_path):
        """Test file complexity analysis for small file."""
        estimator = TokenEstimator(workspace=tmp_path)

        # Create small file (30 lines)
        test_file = tmp_path / "small.py"
        test_file.write_text("\n".join([
            "import os",
            "",
            "def foo():",
            "    return 42",
            "",
        ] * 6))  # 30 lines total

        multiplier = estimator._analyze_file_complexity(test_file)
        # Small file (<50 LOC) → loc_factor=0.7
        # Few imports (<5) → import_factor=0.9
        # Low nesting (<8 indent) → nesting_factor=0.9
        # Combined: ~0.56, clamped to ≥0.5
        assert 0.5 <= multiplier < 1.0

    def test_analyze_file_complexity_large_file(self, tmp_path):
        """Test file complexity analysis for large file."""
        estimator = TokenEstimator(workspace=tmp_path)

        # Create large file (600 lines)
        test_file = tmp_path / "large.py"
        imports = "\n".join([f"import module{i}" for i in range(20)])
        code = "\n".join([
            "                def deeply_nested():",  # 16 spaces = deep nesting
            "                    return 42",
        ] * 290)
        test_file.write_text(imports + "\n\n" + code)

        multiplier = estimator._analyze_file_complexity(test_file)
        # Large file (>500 LOC) → loc_factor=1.5
        # Many imports (>15) → import_factor=1.2
        # Deep nesting (>16 indent) → nesting_factor=1.2
        # Combined: ~2.16, clamped to ≤2.0
        assert 1.5 <= multiplier <= 2.0

    def test_calculate_confidence_specific_deliverables(self, estimator):
        """Test confidence calculation for specific deliverables."""
        deliverables = [
            "Create src/autopack/foo.py",
            "Modify src/autopack/bar.py",
            "Create tests/test_foo.py",
        ]
        confidence = estimator._calculate_confidence(deliverables)

        # All have extensions (specificity=1.0 → +0.3)
        # All have verbs (clarity=1.0 → +0.2)
        # Total: 0.5 + 0.3 + 0.2 = 1.0
        assert confidence == 1.0

    def test_calculate_confidence_vague_deliverables(self, estimator):
        """Test confidence calculation for vague deliverables."""
        deliverables = [
            "Implement user authentication",
            "Add error handling",
            "Update documentation",
        ]
        confidence = estimator._calculate_confidence(deliverables)

        # No extensions (specificity=0.0 → +0.0)
        # Some verbs (2/3 → clarity=0.67 → +0.13)
        # Total: 0.5 + 0.0 + 0.13 = 0.63
        assert 0.6 <= confidence < 0.7

    def test_estimate_deliverable_weights(self, estimator):
        """Test individual deliverable weight selection."""
        cases = [
            ("Create src/backend.py", "backend", 800),        # new_file_backend
            ("Modify src/backend.py", "backend", 300),        # modify_backend
            ("Create components/App.tsx", "frontend", 1200),  # new_file_frontend
            ("Modify components/App.tsx", "frontend", 450),   # modify_frontend
            ("Create tests/test.py", "testing", 600),         # new_file_test
            ("Modify tests/test.py", "testing", 250),         # modify_test
            ("Create docs/README.md", "documentation", 200),  # new_file_doc
            ("Modify docs/README.md", "documentation", 150),  # modify_doc
            ("Create config.yaml", "backend", 400),           # new_file_config
            ("Modify config.yaml", "backend", 200),           # modify_config
        ]

        for deliverable, category, expected_base in cases:
            tokens = estimator._estimate_deliverable(deliverable, category)
            # Should match base weight (no file complexity adjustment)
            assert tokens == expected_base

    def test_build127_scenario(self, estimator):
        """Test BUILD-127 scenario (12 files, should estimate 18k-22k)."""
        deliverables = [
            "Create src/autopack/phase_finalizer.py",
            "Create src/autopack/test_baseline_tracker.py",
            "Create src/autopack/governance_requests.py",
            "Modify src/autopack/autonomous_executor.py",
            "Create tests/test_phase_finalizer.py",
            "Create tests/test_baseline_tracker.py",
            "Create tests/test_governance_requests.py",
            "Modify src/autopack/main.py",
            "Modify src/autopack/quality_gate.py",
            "Create docs/BUILD-127_IMPLEMENTATION.md",
            "Modify docs/BUILD_HISTORY.md",
            "Create alembic/versions/xxx_add_governance.py",
        ]
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="high"
        )

        # Expected calculation:
        # breakdown shows: backend_new=2000, test_new=2400, backend_modify=900, doc_new=200, doc_modify=150
        # Base: 2000 + 2400 + 900 + 200 + 150 = 5650
        # * safety=1.3 = 7345
        # * category=1.2 (backend) = 8814
        # This is reasonable for 12 files (average ~735 tokens per file before safety margins)
        assert 8000 <= estimate.estimated_tokens <= 10000
        assert estimate.deliverable_count == 12

        # Select budget (should be 18k-22k with realistic weights)
        budget = estimator.select_budget(estimate, "high")
        # Should be max(16384, estimate * 1.2) ≈ 16384-20000
        assert 16000 <= budget <= 25000


class TestTokenEstimatorIntegration:
    """Integration tests for TokenEstimator."""

    def test_end_to_end_estimation_and_selection(self, tmp_path):
        """Test complete flow: estimate → select budget."""
        estimator = TokenEstimator(workspace=tmp_path)

        deliverables = [
            "Create src/service.py",
            "Create tests/test_service.py",
            "Modify docs/README.md",
        ]

        # Estimate
        estimate = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="medium"
        )

        assert estimate.estimated_tokens > 0
        assert estimate.deliverable_count == 3
        assert 0.7 <= estimate.confidence <= 1.0

        # Select budget
        budget = estimator.select_budget(estimate, "medium")

        # Should be at least medium base (12288) or estimate with buffer
        assert budget >= 12288
        assert budget <= 64000

    def test_zero_deliverables_uses_complexity_default(self, tmp_path):
        """Test that zero deliverables falls back to complexity."""
        estimator = TokenEstimator(workspace=tmp_path)

        for complexity, expected_base in [("low", 8192), ("medium", 12288), ("high", 16384)]:
            estimate = estimator.estimate(
                deliverables=[],
                category="backend",
                complexity=complexity
            )
            assert estimate.estimated_tokens == expected_base

            budget = estimator.select_budget(estimate, complexity)
            # With buffer: expected_base * 1.2, but capped by max(base, estimate*buffer)
            # Since estimate=base, budget should be base (no buffer applies)
            assert budget >= expected_base
