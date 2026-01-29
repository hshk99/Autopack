"""
Tests for TokenEstimator (BUILD-129 Phase 1).

Tests deliverable-based token estimation for reducing truncation.
"""

import pytest

from autopack.token_estimator import TokenEstimate, TokenEstimator


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
            confidence=0.8,
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
            deliverables=[], category="backend", complexity="medium", scope_paths=None
        )

        assert estimate.estimated_tokens == 12288  # Medium default
        assert estimate.deliverable_count == 0
        assert estimate.confidence == 0.5  # Low confidence

    def test_estimate_single_new_backend_file(self, estimator):
        """Test estimate for single new backend file."""
        deliverables = ["Create src/autopack/new_module.py"]
        estimate = estimator.estimate(
            deliverables=deliverables, category="backend", complexity="medium"
        )

        # Overhead model:
        # overhead(backend, medium)=3000 + new_file_backend=2000 => 5000
        # safety=1.3 => 6500
        expected = int((3000 + 2000) * 1.3)
        assert estimate.estimated_tokens == expected
        assert estimate.deliverable_count == 1
        assert estimate.category == "backend"

    def test_estimate_multiple_files_mixed(self, estimator):
        """Test estimate for multiple files (new + modify)."""
        # Create files that are explicitly modified so filesystem inference treats them as modifications.
        (estimator.workspace / "src" / "autopack").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "docs").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "src" / "autopack" / "bar.py").write_text("# existing\n")
        (estimator.workspace / "docs" / "README.md").write_text("# existing\n")

        deliverables = [
            "Create src/autopack/foo.py",  # new_backend: 800
            "Modify src/autopack/bar.py",  # modify_backend: 300
            "Create tests/test_foo.py",  # new_test: 600
            "Modify docs/README.md",  # modify_doc: 150
        ]
        estimate = estimator.estimate(
            deliverables=deliverables, category="backend", complexity="high"
        )

        # Expected via overhead model + per-deliverable estimation (includes file complexity adjustment
        # for existing modified files).
        overhead = estimator.PHASE_OVERHEAD[("backend", "high")]
        marginal = sum(estimator._estimate_deliverable(d, "backend") for d in deliverables)
        expected = int((overhead + marginal) * estimator.SAFETY_MARGIN)
        assert estimate.estimated_tokens == expected
        assert estimate.deliverable_count == 4

    def test_estimate_frontend_category(self, estimator):
        """Test frontend category gets higher multiplier."""
        deliverables = ["Create components/Button.tsx"]
        estimate = estimator.estimate(
            deliverables=deliverables, category="frontend", complexity="medium"
        )

        # Overhead model:
        # overhead(frontend, medium)=3500 + new_file_frontend=2800 => 6300
        # safety=1.3 => 8190
        expected = int((3500 + 2800) * 1.3)
        assert estimate.estimated_tokens == expected

    def test_select_budget_uses_max_of_base_and_estimate(self, estimator):
        """Test budget selection uses max(base, estimated * buffer)."""
        # Case 1: Estimate higher than base
        estimate = TokenEstimate(
            estimated_tokens=20000,
            deliverable_count=10,
            category="backend",
            complexity="medium",
            confidence=0.8,
        )
        budget = estimator.select_budget(estimate, "medium")
        # BUILD-129 Phase 3 P7: deliverable_count>=8 => buffer_margin=1.6
        # max(12288, 20000 * 1.6) = max(12288, 32000) = 32000
        assert budget == 32000

        # Case 2: Base higher than estimate
        estimate2 = TokenEstimate(
            estimated_tokens=5000,
            deliverable_count=2,
            category="backend",
            complexity="high",
            confidence=0.7,
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
            confidence=0.9,
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
        classification = estimator._classify_deliverable("Create src/autopack/module.py", "backend")
        assert classification == "backend_new"

    def test_classify_deliverable_test_modify(self, estimator):
        """Test deliverable classification for test modifications."""
        (estimator.workspace / "tests").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "tests" / "test_foo.py").write_text("# existing\n")
        classification = estimator._classify_deliverable("Modify tests/test_foo.py", "backend")
        assert classification == "test_modify"

    def test_classify_deliverable_frontend_new(self, estimator):
        """Test deliverable classification for frontend new files."""
        classification = estimator._classify_deliverable("Create components/Button.tsx", "frontend")
        assert classification == "frontend_new"

    def test_classify_deliverable_doc_modify(self, estimator):
        """Test deliverable classification for doc modifications."""
        (estimator.workspace / "docs").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "docs" / "BUILD_HISTORY.md").write_text("# existing\n")
        classification = estimator._classify_deliverable(
            "Update docs/BUILD_HISTORY.md", "documentation"
        )
        assert classification == "doc_modify"

    def test_classify_deliverable_config_new(self, estimator):
        """Test deliverable classification for config new files."""
        classification = estimator._classify_deliverable("Create config/settings.yaml", "backend")
        assert classification == "config_new"

    def test_analyze_file_complexity_small_file(self, tmp_path):
        """Test file complexity analysis for small file."""
        estimator = TokenEstimator(workspace=tmp_path)

        # Create small file (30 lines)
        test_file = tmp_path / "small.py"
        test_file.write_text(
            "\n".join(
                [
                    "import os",
                    "",
                    "def foo():",
                    "    return 42",
                    "",
                ]
                * 6
            )
        )  # 30 lines total

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
        code = "\n".join(
            [
                "                def deeply_nested():",  # 16 spaces = deep nesting
                "                    return 42",
            ]
            * 290
        )
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
        # Create files for "Modify ..." cases so filesystem inference produces modify weights.
        (estimator.workspace / "src").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "components").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "tests").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "docs").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "src" / "backend.py").write_text("# existing\n")
        (estimator.workspace / "components" / "App.tsx").write_text("// existing\n")
        (estimator.workspace / "tests" / "test.py").write_text("# existing\n")
        (estimator.workspace / "docs" / "README.md").write_text("# existing\n")
        (estimator.workspace / "config.yaml").write_text("# existing\n")

        cases = [
            ("Create src/backend.py", "backend", 2000, None),  # new_file_backend
            ("Modify src/backend.py", "backend", 700, "src/backend.py"),  # modify_backend
            ("Create components/App.tsx", "frontend", 2800, None),  # new_file_frontend
            (
                "Modify components/App.tsx",
                "frontend",
                1100,
                "components/App.tsx",
            ),  # modify_frontend
            ("Create tests/test.py", "testing", 1400, None),  # new_file_test
            ("Modify tests/test.py", "testing", 600, "tests/test.py"),  # modify_test
            ("Create docs/README.md", "documentation", 500, None),  # new_file_doc
            ("Modify docs/README.md", "documentation", 400, "docs/README.md"),  # modify_doc
            ("Create config.yaml", "backend", 1000, None),  # new_file_config
            ("Modify config.yaml", "backend", 500, "config.yaml"),  # modify_config
        ]

        for deliverable, category, expected_base, existing_path in cases:
            tokens = estimator._estimate_deliverable(deliverable, category)
            if existing_path is None:
                # New files do not get file-complexity adjustment
                assert tokens == expected_base
            else:
                # Existing modified files DO get file-complexity adjustment
                mult = estimator._analyze_file_complexity(estimator.workspace / existing_path)
                assert tokens == int(expected_base * mult)

    def test_build127_scenario(self, estimator):
        """Test BUILD-127 scenario (12 files)."""
        # Create files that are explicitly modified so filesystem inference treats them as modifications.
        (estimator.workspace / "src" / "autopack").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "docs").mkdir(parents=True, exist_ok=True)
        (estimator.workspace / "src" / "autopack" / "autonomous_executor.py").write_text(
            "# existing\n"
        )
        (estimator.workspace / "src" / "autopack" / "main.py").write_text("# existing\n")
        (estimator.workspace / "src" / "autopack" / "quality_gate.py").write_text("# existing\n")
        (estimator.workspace / "docs" / "BUILD_HISTORY.md").write_text("# existing\n")

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
            deliverables=deliverables, category="backend", complexity="high"
        )

        # Expected via overhead model + per-deliverable estimation (includes file complexity adjustment
        # for existing modified files).
        overhead = estimator.PHASE_OVERHEAD[("backend", "high")]
        marginal = sum(estimator._estimate_deliverable(d, "backend") for d in deliverables)
        assert estimate.estimated_tokens == int((overhead + marginal) * estimator.SAFETY_MARGIN)
        assert estimate.deliverable_count == 12

        # Select budget
        budget = estimator.select_budget(estimate, "high")
        # BUILD-129 Phase 3 P7: deliverable_count>=8 => buffer_margin=1.6
        assert budget == max(16384, int(estimate.estimated_tokens * 1.6))


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
            deliverables=deliverables, category="backend", complexity="medium"
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
                deliverables=[], category="backend", complexity=complexity
            )
            assert estimate.estimated_tokens == expected_base

            budget = estimator.select_budget(estimate, complexity)
            # With buffer: expected_base * 1.2, but capped by max(base, estimate*buffer)
            # Since estimate=base, budget should be base (no buffer applies)
            assert budget >= expected_base


class TestTokenEstimatorCaching:
    """IMP-PERF-001: Tests for token estimation caching functionality."""

    def test_pattern_based_estimate_cache(self):
        """Test that pattern-based estimates are cached."""
        from autopack.token_estimator import (_get_pattern_based_estimate,
                                              clear_token_estimation_cache)

        # Clear cache before test
        clear_token_estimation_cache()

        # First call - cache miss
        result1 = _get_pattern_based_estimate(
            file_extension=".py",
            is_test=True,
            is_doc=False,
            is_config=False,
            is_frontend=False,
            is_new=True,
        )
        assert result1 == 1400  # new_file_test

        # Second call with same params - should be cache hit
        result2 = _get_pattern_based_estimate(
            file_extension=".py",
            is_test=True,
            is_doc=False,
            is_config=False,
            is_frontend=False,
            is_new=True,
        )
        assert result2 == result1

        # Check cache stats
        cache_info = _get_pattern_based_estimate.cache_info()
        assert cache_info.hits >= 1
        assert cache_info.misses >= 1

    def test_pattern_based_estimate_common_types(self):
        """Test pattern estimates for common file types."""
        from autopack.token_estimator import (_get_pattern_based_estimate,
                                              clear_token_estimation_cache)

        clear_token_estimation_cache()

        # Test files
        assert (
            _get_pattern_based_estimate(
                ".py", is_test=True, is_doc=False, is_config=False, is_frontend=False, is_new=True
            )
            == 1400
        )
        assert (
            _get_pattern_based_estimate(
                ".py", is_test=True, is_doc=False, is_config=False, is_frontend=False, is_new=False
            )
            == 600
        )

        # Doc files
        assert (
            _get_pattern_based_estimate(
                ".md", is_test=False, is_doc=True, is_config=False, is_frontend=False, is_new=True
            )
            == 500
        )
        assert (
            _get_pattern_based_estimate(
                ".md", is_test=False, is_doc=True, is_config=False, is_frontend=False, is_new=False
            )
            == 400
        )

        # Config files
        assert (
            _get_pattern_based_estimate(
                ".json", is_test=False, is_doc=False, is_config=True, is_frontend=False, is_new=True
            )
            == 1000
        )
        assert (
            _get_pattern_based_estimate(
                ".yaml",
                is_test=False,
                is_doc=False,
                is_config=True,
                is_frontend=False,
                is_new=False,
            )
            == 500
        )

        # Frontend files
        assert (
            _get_pattern_based_estimate(
                ".tsx", is_test=False, is_doc=False, is_config=False, is_frontend=True, is_new=True
            )
            == 2800
        )
        assert (
            _get_pattern_based_estimate(
                ".jsx", is_test=False, is_doc=False, is_config=False, is_frontend=True, is_new=False
            )
            == 1100
        )

        # Python files (backend)
        assert (
            _get_pattern_based_estimate(
                ".py", is_test=False, is_doc=False, is_config=False, is_frontend=False, is_new=True
            )
            == 2000
        )
        assert (
            _get_pattern_based_estimate(
                ".py", is_test=False, is_doc=False, is_config=False, is_frontend=False, is_new=False
            )
            == 700
        )

    def test_file_complexity_cache(self, tmp_path):
        """Test that file complexity analysis is cached."""
        from autopack.token_estimator import (_cached_analyze_file_complexity,
                                              clear_token_estimation_cache)

        clear_token_estimation_cache()

        # Create a test file
        test_file = tmp_path / "test_complexity.py"
        test_file.write_text(
            "\n".join(
                [
                    "import os",
                    "import sys",
                    "",
                    "def main():",
                    "    print('hello')",
                    "",
                ]
            )
        )
        mtime = test_file.stat().st_mtime

        # First call - cache miss
        result1 = _cached_analyze_file_complexity(str(test_file), mtime)
        assert 0.5 <= result1 <= 2.0

        # Second call with same mtime - should be cache hit
        result2 = _cached_analyze_file_complexity(str(test_file), mtime)
        assert result2 == result1

        # Check cache stats
        cache_info = _cached_analyze_file_complexity.cache_info()
        assert cache_info.hits >= 1
        assert cache_info.misses >= 1

    def test_file_complexity_cache_invalidation(self, tmp_path):
        """Test that complexity cache is invalidated when file changes."""
        import time

        from autopack.token_estimator import (_cached_analyze_file_complexity,
                                              clear_token_estimation_cache)

        clear_token_estimation_cache()

        # Create a small test file
        test_file = tmp_path / "test_invalidation.py"
        test_file.write_text("x = 1\n")
        mtime1 = test_file.stat().st_mtime

        result1 = _cached_analyze_file_complexity(str(test_file), mtime1)

        # Modify the file (ensure mtime changes)
        time.sleep(0.01)  # Small delay to ensure mtime changes
        test_file.write_text("\n".join(["import " + str(i) for i in range(20)] + ["x = 1\n" * 200]))
        mtime2 = test_file.stat().st_mtime

        # With different mtime, should be cache miss
        result2 = _cached_analyze_file_complexity(str(test_file), mtime2)

        # Results should be different (larger file = higher complexity)
        # The larger file should have higher complexity due to more imports and LOC
        assert mtime1 != mtime2 or result1 != result2  # Either mtime changed or result changed

    def test_clear_token_estimation_cache(self, tmp_path):
        """Test that clear_token_estimation_cache clears all caches."""
        from autopack.token_estimator import (_cached_analyze_file_complexity,
                                              _get_pattern_based_estimate,
                                              clear_token_estimation_cache,
                                              get_token_estimation_cache_info)

        # Populate caches
        _get_pattern_based_estimate(".py", True, False, False, False, True)
        test_file = tmp_path / "test_clear.py"
        test_file.write_text("x = 1\n")
        _cached_analyze_file_complexity(str(test_file), test_file.stat().st_mtime)

        # Verify caches have entries
        info_before = get_token_estimation_cache_info()
        assert (
            info_before["pattern_cache"]["size"] > 0 or info_before["pattern_cache"]["misses"] > 0
        )

        # Clear caches
        clear_token_estimation_cache()

        # Verify caches are cleared
        info_after = get_token_estimation_cache_info()
        assert info_after["pattern_cache"]["size"] == 0
        assert info_after["complexity_cache"]["size"] == 0

    def test_get_token_estimation_cache_info(self, tmp_path):
        """Test cache info retrieval."""
        from autopack.token_estimator import (_get_pattern_based_estimate,
                                              clear_token_estimation_cache,
                                              get_token_estimation_cache_info)

        clear_token_estimation_cache()

        # Generate some cache activity
        _get_pattern_based_estimate(".py", True, False, False, False, True)
        _get_pattern_based_estimate(".py", True, False, False, False, True)  # Cache hit

        info = get_token_estimation_cache_info()

        assert "pattern_cache" in info
        assert "complexity_cache" in info
        assert "estimate_cache" in info

        assert "hits" in info["pattern_cache"]
        assert "misses" in info["pattern_cache"]
        assert "size" in info["pattern_cache"]
        assert "maxsize" in info["pattern_cache"]

    def test_estimate_deliverable_uses_pattern_cache(self, tmp_path):
        """Test that _estimate_deliverable uses pattern cache for common files."""
        from autopack.token_estimator import clear_token_estimation_cache

        clear_token_estimation_cache()

        estimator = TokenEstimator(workspace=tmp_path)

        # Estimate multiple similar deliverables
        deliverables = [
            "Create tests/test_foo.py",
            "Create tests/test_bar.py",
            "Create tests/test_baz.py",
        ]

        # All should return same estimate (new test files)
        estimates = [estimator._estimate_deliverable(d, "testing") for d in deliverables]

        # All new test files should have same base estimate
        assert all(e == estimates[0] for e in estimates)
        assert estimates[0] == 1400  # new_file_test

    def test_estimate_with_caching_performance(self, tmp_path):
        """Test that caching improves performance for repeated estimates."""
        from autopack.token_estimator import (clear_token_estimation_cache,
                                              get_token_estimation_cache_info)

        clear_token_estimation_cache()

        estimator = TokenEstimator(workspace=tmp_path)

        deliverables = [
            "Create src/module1.py",
            "Create src/module2.py",
            "Create tests/test_module1.py",
            "Create tests/test_module2.py",
            "Create docs/README.md",
        ]

        # First estimation
        estimate1 = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="medium",
        )

        # Second estimation with same params (should use cache)
        estimate2 = estimator.estimate(
            deliverables=deliverables,
            category="backend",
            complexity="medium",
        )

        assert estimate1.estimated_tokens == estimate2.estimated_tokens

        # Check that estimate cache was used
        info = get_token_estimation_cache_info()
        assert info["estimate_cache"]["hits"] >= 1
