"""
Unit tests for BUILD-127 Phase 3: Structured Deliverables Manifest Validation.

Tests:
- extract_manifest_from_output()
- validate_structured_manifest()
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from autopack.deliverables_validator import (
    extract_manifest_from_output,
    validate_structured_manifest,
)


class TestManifestExtraction:
    """Test manifest extraction from Builder output."""

    def test_extract_manifest_success(self):
        """Test extracting valid manifest from output."""
        output = """
Some build output here...

DELIVERABLES_MANIFEST:
```json
{
  "created": [
    {"path": "src/autopack/example.py", "symbols": ["ExampleClass"]}
  ],
  "modified": [
    {"path": "src/autopack/main.py", "changes": "Added example import"}
  ]
}
```

More output after...
"""
        manifest = extract_manifest_from_output(output)

        assert manifest is not None
        assert "created" in manifest
        assert "modified" in manifest
        assert len(manifest["created"]) == 1
        assert manifest["created"][0]["path"] == "src/autopack/example.py"

    def test_extract_manifest_case_insensitive(self):
        """Test case-insensitive manifest extraction."""
        output = """
deliverables_manifest:
```json
{"created": [], "modified": []}
```
"""
        manifest = extract_manifest_from_output(output)
        assert manifest is not None

    def test_extract_manifest_not_found(self):
        """Test when manifest is not present."""
        output = "No manifest here, just regular output."
        manifest = extract_manifest_from_output(output)
        assert manifest is None

    def test_extract_manifest_invalid_json(self):
        """Test when manifest has invalid JSON."""
        output = """
DELIVERABLES_MANIFEST:
```json
{invalid json here}
```
"""
        manifest = extract_manifest_from_output(output)
        assert manifest is None


class TestManifestValidation:
    """Test structured manifest validation."""

    def test_validate_manifest_success(self):
        """Test validating a correct manifest."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test files
            (workspace / "src").mkdir()
            (workspace / "src/example.py").write_text("class ExampleClass:\n    pass\n")
            (workspace / "src/main.py").write_text("from src.example import ExampleClass\n")

            manifest = {
                "created": [
                    {"path": "src/example.py", "symbols": ["ExampleClass"]}
                ],
                "modified": [
                    {"path": "src/main.py", "changes": "Added import"}
                ]
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is True
            assert len(issues) == 0

    def test_validate_manifest_created_file_missing(self):
        """Test when created file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            manifest = {
                "created": [
                    {"path": "src/missing.py", "symbols": ["MissingClass"]}
                ],
                "modified": []
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is False
            assert any("does not exist" in issue for issue in issues)

    def test_validate_manifest_missing_symbol(self):
        """Test when expected symbol is missing."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create file without expected symbol
            (workspace / "src").mkdir()
            (workspace / "src/example.py").write_text("# Empty file with no symbols\n")

            manifest = {
                "created": [
                    {"path": "src/example.py", "symbols": ["ExampleClass", "example_function"]}
                ],
                "modified": []
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is False
            assert any("missing expected symbol: ExampleClass" in issue for issue in issues)
            assert any("missing expected symbol: example_function" in issue for issue in issues)

    def test_validate_manifest_modified_file_missing(self):
        """Test when modified file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            manifest = {
                "created": [],
                "modified": [
                    {"path": "src/missing.py", "changes": "Some changes"}
                ]
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is False
            assert any("does not exist" in issue for issue in issues)

    def test_validate_manifest_invalid_structure(self):
        """Test when manifest has invalid structure."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Not a dictionary
            passed, issues = validate_structured_manifest("invalid", workspace)
            assert passed is False
            assert any("not a dictionary" in issue for issue in issues)

            # Invalid 'created' field
            manifest = {"created": "not a list", "modified": []}
            passed, issues = validate_structured_manifest(manifest, workspace)
            assert passed is False
            assert any("'created' field is not a list" in issue for issue in issues)

    def test_validate_manifest_with_expected_deliverables(self):
        """Test validation against expected deliverables list."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test files
            (workspace / "src").mkdir()
            (workspace / "tests").mkdir()
            (workspace / "src/example.py").write_text("class ExampleClass:\n    pass\n")
            (workspace / "tests/test_example.py").write_text("def test_example():\n    pass\n")

            manifest = {
                "created": [
                    {"path": "src/example.py", "symbols": ["ExampleClass"]},
                    {"path": "tests/test_example.py", "symbols": ["test_example"]}
                ],
                "modified": []
            }

            expected_deliverables = [
                "src/example.py",
                "tests/test_example.py"
            ]

            passed, issues = validate_structured_manifest(
                manifest, workspace, expected_deliverables
            )

            assert passed is True
            assert len(issues) == 0

    def test_validate_manifest_missing_expected_deliverable(self):
        """Test when manifest is missing an expected deliverable."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create only one file
            (workspace / "src").mkdir()
            (workspace / "src/example.py").write_text("class ExampleClass:\n    pass\n")

            manifest = {
                "created": [
                    {"path": "src/example.py", "symbols": ["ExampleClass"]}
                ],
                "modified": []
            }

            expected_deliverables = [
                "src/example.py",
                "tests/test_example.py"  # This is missing from manifest
            ]

            passed, issues = validate_structured_manifest(
                manifest, workspace, expected_deliverables
            )

            assert passed is False
            assert any("not in manifest: tests/test_example.py" in issue for issue in issues)

    def test_validate_manifest_directory_deliverable_matching(self):
        """Test that directory deliverables match created files within them."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create test files in directory
            (workspace / "tests").mkdir()
            (workspace / "tests/test_foo.py").write_text("def test_foo():\n    pass\n")
            (workspace / "tests/test_bar.py").write_text("def test_bar():\n    pass\n")

            manifest = {
                "created": [
                    {"path": "tests/test_foo.py", "symbols": ["test_foo"]},
                    {"path": "tests/test_bar.py", "symbols": ["test_bar"]}
                ],
                "modified": []
            }

            # Deliverable specified as directory
            expected_deliverables = ["tests/"]

            passed, issues = validate_structured_manifest(
                manifest, workspace, expected_deliverables
            )

            assert passed is True
            assert len(issues) == 0

    def test_validate_manifest_empty_symbols_list(self):
        """Test validation with empty symbols list (should pass)."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create file
            (workspace / "src").mkdir()
            (workspace / "src/example.py").write_text("# Empty file\n")

            manifest = {
                "created": [
                    {"path": "src/example.py", "symbols": []}  # No symbols to validate
                ],
                "modified": []
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is True
            assert len(issues) == 0

    def test_validate_manifest_item_missing_path(self):
        """Test when manifest item is missing path field."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            manifest = {
                "created": [
                    {"symbols": ["ExampleClass"]}  # Missing 'path' field
                ],
                "modified": []
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is False
            assert any("missing 'path' field" in issue for issue in issues)

    def test_validate_manifest_item_not_dict(self):
        """Test when manifest item is not a dictionary."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            manifest = {
                "created": [
                    "not a dictionary"  # Should be dict
                ],
                "modified": []
            }

            passed, issues = validate_structured_manifest(manifest, workspace)

            assert passed is False
            assert any("not a dictionary" in issue for issue in issues)
