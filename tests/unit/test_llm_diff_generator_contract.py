"""Contract tests for llm/diff_generator.py module.

These tests verify the diff generator's public API and behavior.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_diff_result_attributes(self):
        """DiffResult stores diff data."""
        from autopack.llm.diff_generator import DiffResult

        result = DiffResult(
            diff_content="diff --git...",
            is_new_file=True,
            lines_added=10,
            lines_removed=0,
        )
        assert result.diff_content == "diff --git..."
        assert result.is_new_file is True
        assert result.is_deleted_file is False
        assert result.lines_added == 10
        assert result.lines_removed == 0


class TestChurnMetrics:
    """Tests for ChurnMetrics dataclass."""

    def test_churn_metrics_attributes(self):
        """ChurnMetrics stores churn data."""
        from autopack.llm.diff_generator import ChurnMetrics

        metrics = ChurnMetrics(
            churn_percent=50.0,
            lines_changed=100,
            original_lines=200,
            new_lines=200,
        )
        assert metrics.churn_percent == 50.0
        assert metrics.lines_changed == 100


class TestSymbolValidation:
    """Tests for SymbolValidation dataclass."""

    def test_symbol_validation_no_missing(self):
        """SymbolValidation with no missing symbols."""
        from autopack.llm.diff_generator import SymbolValidation

        result = SymbolValidation(
            missing_symbols=set(),
            has_missing=False,
        )
        assert result.has_missing is False
        assert len(result.missing_symbols) == 0

    def test_symbol_validation_with_missing(self):
        """SymbolValidation with missing symbols."""
        from autopack.llm.diff_generator import SymbolValidation

        result = SymbolValidation(
            missing_symbols={"foo", "bar"},
            has_missing=True,
            message="bar, foo",
        )
        assert result.has_missing is True
        assert "foo" in result.missing_symbols
        assert "bar" in result.missing_symbols


class TestDiffGenerator:
    """Tests for DiffGenerator class."""

    def test_generate_new_file_header(self):
        """Generates correct header for new file."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()
        header = generator._build_git_header(
            file_path="src/new.py",
            is_new_file=True,
            is_deleted_file=False,
        )

        assert "diff --git a/src/new.py b/src/new.py" in header
        assert "new file mode 100644" in header
        assert "--- /dev/null" in header
        assert "+++ b/src/new.py" in header

    def test_generate_deleted_file_header(self):
        """Generates correct header for deleted file."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()
        header = generator._build_git_header(
            file_path="src/old.py",
            is_new_file=False,
            is_deleted_file=True,
        )

        assert "diff --git a/src/old.py b/src/old.py" in header
        assert "deleted file mode 100644" in header
        assert "--- a/src/old.py" in header
        assert "+++ /dev/null" in header

    def test_generate_modified_file_header(self):
        """Generates correct header for modified file."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()
        header = generator._build_git_header(
            file_path="src/module.py",
            is_new_file=False,
            is_deleted_file=False,
        )

        assert "diff --git a/src/module.py b/src/module.py" in header
        assert "--- a/src/module.py" in header
        assert "+++ b/src/module.py" in header

    def test_generate_with_mocked_git(self):
        """Generates diff using mocked git command."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()

        # Mock subprocess.run to return a valid diff
        mock_diff = b"""diff --git a/old b/new
--- a/old
+++ b/new
@@ -1 +1,2 @@
 line1
+line2
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,  # git diff returns 1 when there are differences
                stdout=mock_diff,
                stderr=b"",
            )

            result = generator.generate(
                file_path="test.py",
                old_content="line1\n",
                new_content="line1\nline2\n",
                check_exists=False,
            )

            assert result.lines_added >= 1
            assert "test.py" in result.diff_content

    def test_generate_no_changes(self):
        """Returns empty diff when no changes."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,  # git diff returns 0 when no differences
                stdout=b"",
                stderr=b"",
            )

            result = generator.generate(
                file_path="test.py",
                old_content="same\n",
                new_content="same\n",
                check_exists=False,
            )

            assert result.diff_content == ""

    def test_generate_multiple(self):
        """Generates combined diff for multiple files."""
        from autopack.llm.diff_generator import DiffGenerator

        generator = DiffGenerator()

        # Mock to return simple diffs
        mock_diff = b"""@@ -1 +1,2 @@
 line1
+line2
"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=mock_diff,
                stderr=b"",
            )

            result = generator.generate_multiple([
                ("file1.py", "line1\n", "line1\nline2\n"),
                ("file2.py", "a\n", "a\nb\n"),
            ])

            assert "file1.py" in result
            assert "file2.py" in result


class TestChurnCalculator:
    """Tests for ChurnCalculator class."""

    def test_calculate_no_changes(self):
        """Zero churn for identical content."""
        from autopack.llm.diff_generator import ChurnCalculator

        calc = ChurnCalculator()
        metrics = calc.calculate("line1\nline2\n", "line1\nline2\n")

        assert metrics.churn_percent == 0.0
        assert metrics.lines_changed == 0

    def test_calculate_all_new(self):
        """100% churn for entirely new content."""
        from autopack.llm.diff_generator import ChurnCalculator

        calc = ChurnCalculator()
        metrics = calc.calculate("", "line1\nline2\n")

        assert metrics.churn_percent == 100.0
        assert metrics.original_lines == 0
        assert metrics.new_lines == 2

    def test_calculate_partial_change(self):
        """Partial churn for some changes."""
        from autopack.llm.diff_generator import ChurnCalculator

        calc = ChurnCalculator()
        old = "line1\nline2\nline3\nline4\n"
        new = "line1\nmodified\nline3\nline4\n"
        metrics = calc.calculate(old, new)

        # One line changed out of 4 = 25%
        assert 20.0 <= metrics.churn_percent <= 30.0
        assert metrics.lines_changed >= 1

    def test_is_high_churn_true(self):
        """Detects high churn above threshold."""
        from autopack.llm.diff_generator import ChurnCalculator

        calc = ChurnCalculator()
        old = "line1\n"
        new = "completely\ndifferent\ncontent\n"

        assert calc.is_high_churn(old, new, threshold=50.0) is True

    def test_is_high_churn_false(self):
        """Detects low churn below threshold."""
        from autopack.llm.diff_generator import ChurnCalculator

        calc = ChurnCalculator()
        old = "line1\nline2\nline3\nline4\n"
        new = "line1\nline2\nline3\nmodified4\n"

        assert calc.is_high_churn(old, new, threshold=50.0) is False


class TestSymbolValidator:
    """Tests for SymbolValidator class."""

    def test_validate_python_no_missing(self):
        """No missing symbols when all preserved."""
        from autopack.llm.diff_generator import SymbolValidator

        validator = SymbolValidator()
        old = "def hello():\n    pass\n\nclass Foo:\n    pass\n"
        new = "def hello():\n    print('hi')\n\nclass Foo:\n    def bar(self):\n        pass\n"

        result = validator.validate_python(old, new, "test.py")

        assert result.has_missing is False
        assert len(result.missing_symbols) == 0

    def test_validate_python_with_missing(self):
        """Detects missing symbols."""
        from autopack.llm.diff_generator import SymbolValidator

        validator = SymbolValidator()
        old = "def hello():\n    pass\n\ndef goodbye():\n    pass\n"
        new = "def hello():\n    pass\n"

        result = validator.validate_python(old, new, "test.py")

        assert result.has_missing is True
        assert "goodbye" in result.missing_symbols

    def test_validate_python_non_python_file(self):
        """Skips validation for non-Python files."""
        from autopack.llm.diff_generator import SymbolValidator

        validator = SymbolValidator()
        old = "function hello() { }\nfunction goodbye() { }"
        new = "function hello() { }"

        result = validator.validate_python(old, new, "test.js")

        assert result.has_missing is False

    def test_extract_symbols(self):
        """Extracts top-level symbols correctly."""
        from autopack.llm.diff_generator import SymbolValidator

        validator = SymbolValidator()
        content = """
def top_level_func():
    pass

class MyClass:
    def method(self):  # Not top-level
        pass

def another_func():
    pass
"""
        symbols = validator._extract_python_symbols(content)

        assert "top_level_func" in symbols
        assert "MyClass" in symbols
        assert "another_func" in symbols
        assert "method" not in symbols  # Method is indented


class TestChangeClassifier:
    """Tests for ChangeClassifier class."""

    def test_classify_small_fix_low_complexity(self):
        """Low complexity phases are small fixes."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {"complexity": "low"}

        assert classifier.classify(phase_spec) == "small_fix"

    def test_classify_small_fix_medium_few_criteria(self):
        """Medium complexity with few criteria is small fix."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {
            "complexity": "medium",
            "acceptance_criteria": ["criterion 1", "criterion 2"],
        }

        assert classifier.classify(phase_spec) == "small_fix"

    def test_classify_large_refactor_high_complexity(self):
        """High complexity is large refactor."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {"complexity": "high"}

        assert classifier.classify(phase_spec) == "large_refactor"

    def test_classify_large_refactor_explicit(self):
        """Explicit change_size override."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {
            "complexity": "low",
            "change_size": "large_refactor",
        }

        assert classifier.classify(phase_spec) == "large_refactor"

    def test_classify_large_refactor_lockfile(self):
        """Lockfile in scope triggers large refactor."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {"complexity": "low"}
        scope_paths = ["package-lock.json"]

        assert classifier.classify(phase_spec, scope_paths) == "large_refactor"

    def test_classify_large_refactor_yaml(self):
        """YAML pack files trigger large refactor."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        phase_spec = {"complexity": "low"}
        scope_paths = ["backend/packs/config.yaml"]

        assert classifier.classify(phase_spec, scope_paths) == "large_refactor"

    def test_classify_none_phase_spec(self):
        """None phase_spec defaults to small_fix."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        assert classifier.classify(None) == "small_fix"

    def test_get_churn_threshold_small_fix(self):
        """Small fix has lower churn threshold."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        threshold = classifier.get_churn_threshold("small_fix")

        assert threshold == 30.0

    def test_get_churn_threshold_large_refactor(self):
        """Large refactor has higher churn threshold."""
        from autopack.llm.diff_generator import ChangeClassifier

        classifier = ChangeClassifier()
        threshold = classifier.get_churn_threshold("large_refactor")

        assert threshold == 80.0
