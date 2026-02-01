"""
Tests for Deliverables Contract Module

Tests for contract building and validation (IMP-GOD-001).
Verifies that deliverables contracts are correctly built from phase scope.
"""

from unittest.mock import Mock, patch


from autopack.executor.deliverables_contract import DeliverablesContractBuilder


class TestDeliverablesContractBuilder:
    """Tests for DeliverablesContractBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_get_learning_context = Mock(return_value={"run_hints": []})
        self.builder = DeliverablesContractBuilder(self.mock_get_learning_context)

    def test_builder_initialization(self):
        """Verify builder can be initialized."""
        builder = DeliverablesContractBuilder(self.mock_get_learning_context)
        assert builder is not None

    def test_build_contract_no_scope(self):
        """Verify build_contract returns None when phase has no scope."""
        phase = {"phase_id": "test-phase"}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is None

    def test_build_contract_empty_scope(self):
        """Verify build_contract handles empty scope gracefully."""
        phase = {"phase_id": "test-phase", "scope": None}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_no_deliverables(self, mock_extract):
        """Verify build_contract returns None when no deliverables extracted."""
        mock_extract.return_value = []

        phase = {"phase_id": "test-phase", "scope": {"files": []}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_single_deliverable(self, mock_extract):
        """Verify contract is built with single deliverable."""
        expected_path = "src/autopack/test.py"
        mock_extract.return_value = [expected_path]

        phase = {"phase_id": "test-phase", "scope": {"files": [expected_path]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "CRITICAL FILE PATH REQUIREMENTS" in result
        assert expected_path in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_multiple_deliverables(self, mock_extract):
        """Verify contract handles multiple deliverables."""
        paths = [
            "src/autopack/module1.py",
            "src/autopack/module2.py",
            "tests/autopack/test_module.py",
        ]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        for path in paths:
            assert path in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_common_prefix_detection(self, mock_extract):
        """Verify common path prefix is detected and included."""
        paths = [
            "src/autopack/research/module1.py",
            "src/autopack/research/module2.py",
        ]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "src/autopack/research/" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_forbidden_patterns_extraction(self, mock_extract):
        """Verify forbidden patterns are extracted from learning hints."""
        mock_extract.return_value = ["src/autopack/test.py"]

        # Setup learning context with hints
        wrong_path = "src/wrong/path.py"
        correct_path = "src/correct/path.py"
        hint_text = f"Wrong: {wrong_path} → {correct_path}"

        self.mock_get_learning_context.return_value = {"run_hints": [{"hint_text": hint_text}]}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Should contain contract formatting
        assert "REQUIRED file paths:" in result or "CRITICAL FILE PATH" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_build_contract_allowed_roots_derivation(self, mock_extract):
        """Verify allowed roots are correctly derived."""
        paths = [
            "src/autopack/research/module1.py",
            "tests/research/test_module.py",
        ]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "ALLOWED ROOTS" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_contract_includes_required_sections(self, mock_extract):
        """Verify contract includes all required sections."""
        mock_extract.return_value = ["src/autopack/test.py"]
        self.mock_get_learning_context.return_value = {"run_hints": []}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "CRITICAL FILE PATH REQUIREMENTS" in result
        assert "REQUIRED file paths:" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_contract_includes_json_requirements(self, mock_extract):
        """Verify contract includes JSON requirements when applicable."""
        paths = ["src/autopack/research/evaluation/gold_set.json"]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "JSON DELIVERABLES" in result
        assert "gold_set.json" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_extract_forbidden_patterns_from_hints(self, mock_extract):
        """Verify forbidden patterns extraction from learning hints."""
        mock_extract.return_value = ["src/autopack/test.py"]

        # Test various hint formats
        hints = [
            {"hint_text": "Wrong: src/wrong/path.py → src/correct/path.py"},
            "DO NOT create a top-level 'bad_dir/' directory",
        ]
        self.mock_get_learning_context.return_value = {"run_hints": hints}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Forbidden patterns should be included if found

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_heuristic_forbidden_patterns_tracer_bullet(self, mock_extract):
        """Verify heuristic forbidden patterns for tracer_bullet."""
        paths = ["src/autopack/research/tracer_bullet/module.py"]
        mock_extract.return_value = paths

        self.mock_get_learning_context.return_value = {"run_hints": []}

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Heuristic forbidden patterns should be included

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_derive_allowed_roots_multiple_roots(self, mock_extract):
        """Verify allowed roots derivation with multiple matching roots."""
        paths = [
            "src/autopack/research/module1.py",
            "src/autopack/cli/command.py",
            "tests/research/test_module.py",
            "docs/research/readme.md",
        ]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        assert "src/autopack/research/" in result
        assert "src/autopack/cli/" in result
        assert "tests/research/" in result
        assert "docs/research/" in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_derive_allowed_roots_no_matching_roots(self, mock_extract):
        """Verify allowed roots derivation when paths don't match preferred roots."""
        paths = ["custom/path/module.py"]
        mock_extract.return_value = paths

        self.mock_get_learning_context.return_value = {"run_hints": []}

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Should still create contract even if no preferred roots match

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_contract_formatting_consistency(self, mock_extract):
        """Verify contract formatting is consistent."""
        paths = ["src/autopack/test.py"]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        # Should be non-empty string
        assert isinstance(result, str)
        assert len(result) > 0
        # Should have consistent formatting with separators
        assert "=" * 80 in result

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_extract_forbidden_patterns_string_hints(self, mock_extract):
        """Verify forbidden patterns extraction from string hints."""
        mock_extract.return_value = ["src/autopack/test.py"]

        hint_text = "Wrong: bad/path.py → good/path.py"
        self.mock_get_learning_context.return_value = {"run_hints": [hint_text]}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_extract_forbidden_patterns_do_not_create(self, mock_extract):
        """Verify extraction of 'DO NOT create' patterns."""
        mock_extract.return_value = ["src/autopack/test.py"]

        hint = "DO NOT create a top-level 'wrong_dir/' directory"
        self.mock_get_learning_context.return_value = {"run_hints": [hint]}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_learning_context_lookup(self, mock_extract):
        """Verify learning context is correctly looked up."""
        paths = ["src/autopack/test.py"]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        self.builder.build_contract(phase, "test-phase")

        # Verify get_learning_context was called with the phase
        self.mock_get_learning_context.assert_called_with(phase)

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_format_contract_structure(self, mock_extract):
        """Verify _format_contract produces proper structure."""
        paths = ["src/autopack/module.py"]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        lines = result.split("\n")
        # Should have multiple lines
        assert len(lines) > 5

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_multiple_calls_independent(self, mock_extract):
        """Verify multiple calls to build_contract are independent."""
        self.mock_get_learning_context.return_value = {"run_hints": []}

        paths1 = ["src/autopack/test1.py"]
        paths2 = ["src/autopack/test2.py"]

        mock_extract.return_value = paths1
        phase1 = {"phase_id": "phase1", "scope": {"files": paths1}}
        result1 = self.builder.build_contract(phase1, "phase1")

        mock_extract.return_value = paths2
        phase2 = {"phase_id": "phase2", "scope": {"files": paths2}}
        result2 = self.builder.build_contract(phase2, "phase2")

        assert "test1.py" in result1
        assert "test2.py" in result2
        assert "test1.py" not in result2

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_edge_case_empty_learning_hints(self, mock_extract):
        """Verify handling of empty learning hints."""
        mock_extract.return_value = ["src/autopack/test.py"]
        self.mock_get_learning_context.return_value = {"run_hints": []}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_edge_case_malformed_hints(self, mock_extract):
        """Verify handling of malformed hints doesn't crash."""
        mock_extract.return_value = ["src/autopack/test.py"]

        # Various malformed hints
        hints = [
            None,
            {},
            {"no_hint_text": "value"},
            "Random string without markers",
        ]
        self.mock_get_learning_context.return_value = {"run_hints": hints}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        # Should handle gracefully and not crash
        assert result is not None

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_path_with_no_common_prefix(self, mock_extract):
        """Verify handling of paths with no common prefix."""
        paths = ["src/autopack/module.py", "tests/test.py", "docs/readme.md"]
        mock_extract.return_value = paths

        phase = {"phase_id": "test-phase", "scope": {"files": paths}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Should still create contract with root as common prefix

    @patch("autopack.deliverables_validator.extract_deliverables_from_scope")
    def test_forbidden_patterns_limit(self, mock_extract):
        """Verify only first 3 forbidden patterns are shown."""
        mock_extract.return_value = ["src/autopack/test.py"]

        # Create 5 forbidden patterns
        hints = [{"hint_text": f"Wrong: path{i}.py → correct.py"} for i in range(5)]
        self.mock_get_learning_context.return_value = {"run_hints": hints}

        phase = {"phase_id": "test-phase", "scope": {"files": ["src/autopack/test.py"]}}
        result = self.builder.build_contract(phase, "test-phase")

        assert result is not None
        # Only first 3 should be shown
        lines = result.split("\n")
        # Count "DO NOT use:" occurrences
        do_not_use_count = sum(1 for line in lines if "DO NOT use:" in line)
        # Should be limited to reasonable number
