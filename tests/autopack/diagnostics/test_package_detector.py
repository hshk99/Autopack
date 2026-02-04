"""Tests for package detection and validation."""

from pathlib import Path
from textwrap import dedent

from autopack.diagnostics.package_detector import (
    PackageDetectionResult,
    PackageDetector,
    PackageRequirement,
    detect_missing_packages,
)


class TestPackageDetector:
    """Test suite for PackageDetector."""

    def test_init_default_project_root(self):
        """Test initialization with default project root."""
        detector = PackageDetector()
        assert detector.project_root == Path.cwd()

    def test_init_custom_project_root(self, tmp_path):
        """Test initialization with custom project root."""
        detector = PackageDetector(project_root=tmp_path)
        assert detector.project_root == tmp_path

    def test_check_import_stdlib(self):
        """Test checking standard library imports."""
        detector = PackageDetector()
        is_available, suggested = detector.check_import("os")
        assert is_available is True
        assert suggested is None

    def test_check_import_installed(self):
        """Test checking installed package imports."""
        detector = PackageDetector()
        # pytest should be installed in test environment
        is_available, suggested = detector.check_import("pytest")
        assert is_available is True
        assert suggested is None

    def test_check_import_missing(self):
        """Test checking missing package imports."""
        detector = PackageDetector()
        is_available, suggested = detector.check_import("nonexistent_package_xyz")
        assert is_available is False
        assert suggested == "nonexistent_package_xyz"

    def test_check_import_with_mapping(self):
        """Test checking import with package name mapping."""
        detector = PackageDetector()
        is_available, suggested = detector.check_import("cv2")
        # cv2 is likely not installed, but should suggest opencv-python
        if not is_available:
            assert suggested == "opencv-python"

    def test_analyze_file_simple_imports(self, tmp_path):
        """Test analyzing file with simple imports."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                import os
                import sys
                import json
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        assert len(requirements) == 3
        assert all(req.is_stdlib for req in requirements)
        assert all(req.is_installed for req in requirements)

    def test_analyze_file_from_imports(self, tmp_path):
        """Test analyzing file with from imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                from pathlib import Path
                from typing import List, Dict
                from collections import defaultdict
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        assert len(requirements) == 3
        module_names = {req.name for req in requirements}
        assert module_names == {"pathlib", "typing", "collections"}

    def test_analyze_file_third_party_imports(self, tmp_path):
        """Test analyzing file with third-party imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                import pytest
                import requests
                from fastapi import FastAPI
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        assert len(requirements) == 3
        module_names = {req.name for req in requirements}
        assert module_names == {"pytest", "requests", "fastapi"}

        # pytest should be installed (test dependency)
        pytest_req = next(r for r in requirements if r.name == "pytest")
        assert pytest_req.is_installed is True

    def test_analyze_file_with_syntax_error(self, tmp_path):
        """Test analyzing file with syntax error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nthis is not valid python")

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        # Should return empty list on syntax error
        assert requirements == []

    def test_analyze_files_multiple(self, tmp_path):
        """Test analyzing multiple files."""
        # Create test files
        file1 = tmp_path / "file1.py"
        file1.write_text("import os\nimport sys")

        file2 = tmp_path / "file2.py"
        file2.write_text("import json\nimport pytest")

        detector = PackageDetector(project_root=tmp_path)
        result = detector.analyze_files([file1, file2])

        assert result.files_analyzed == 2
        assert result.total_imports == 4
        assert len(result.stdlib_imports) == 3  # os, sys, json

    def test_analyze_directory(self, tmp_path):
        """Test analyzing entire directory."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module1.py").write_text("import os")
        (tmp_path / "src" / "module2.py").write_text("import sys")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_module.py").write_text("import pytest")

        detector = PackageDetector(project_root=tmp_path)
        result = detector.analyze_directory()

        assert result.files_analyzed == 3
        assert result.total_imports == 3

    def test_analyze_directory_with_exclusions(self, tmp_path):
        """Test analyzing directory with exclusion patterns."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module.py").write_text("import os")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_module.py").write_text("import pytest")

        detector = PackageDetector(project_root=tmp_path)
        result = detector.analyze_directory(exclude_patterns=["**/test_*.py"])

        assert result.files_analyzed == 1
        assert result.total_imports == 1

    def test_get_missing_packages_summary_none_missing(self, tmp_path):
        """Test summary when no packages are missing."""
        detector = PackageDetector(project_root=tmp_path)
        result = PackageDetectionResult(
            missing_packages=[],
            installed_packages=[],
            stdlib_imports=[],
            total_imports=0,
            files_analyzed=0,
            errors=[],
        )

        summary = detector.get_missing_packages_summary(result)
        assert "All required packages are installed" in summary

    def test_get_missing_packages_summary_with_missing(self, tmp_path):
        """Test summary when packages are missing."""
        detector = PackageDetector(project_root=tmp_path)

        missing_req = PackageRequirement(
            name="requests",
            import_statement="import requests",
            file_path="src/module.py",
            line_number=1,
            is_stdlib=False,
            is_installed=False,
            suggested_package="requests",
        )

        result = PackageDetectionResult(
            missing_packages=[missing_req],
            installed_packages=[],
            stdlib_imports=[],
            total_imports=1,
            files_analyzed=1,
            errors=[],
        )

        summary = detector.get_missing_packages_summary(result)
        assert "Missing packages detected" in summary
        assert "requests" in summary
        assert "pip install" in summary

    def test_package_mappings(self):
        """Test that package mappings are correctly applied."""
        detector = PackageDetector()

        # Test common mappings
        assert detector.PACKAGE_MAPPINGS["cv2"] == "opencv-python"
        assert detector.PACKAGE_MAPPINGS["PIL"] == "Pillow"
        assert detector.PACKAGE_MAPPINGS["yaml"] == "PyYAML"

    def test_stdlib_detection(self):
        """Test standard library module detection."""
        detector = PackageDetector()

        # Test common stdlib modules
        assert detector._is_stdlib_module("os") is True
        assert detector._is_stdlib_module("sys") is True
        assert detector._is_stdlib_module("json") is True
        assert detector._is_stdlib_module("pathlib") is True

        # Test non-stdlib
        assert detector._is_stdlib_module("requests") is False
        assert detector._is_stdlib_module("pytest") is False

    def test_create_requirement(self, tmp_path):
        """Test creating PackageRequirement objects."""
        detector = PackageDetector(project_root=tmp_path)
        test_file = tmp_path / "test.py"

        req = detector._create_requirement("os", "import os", test_file, 1)

        assert req.name == "os"
        assert req.import_statement == "import os"
        assert req.line_number == 1
        assert req.is_stdlib is True
        assert req.is_installed is True

    def test_nested_module_imports(self, tmp_path):
        """Test handling of nested module imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                from os.path import join
                from collections.abc import Mapping
                import xml.etree.ElementTree
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        # Should extract top-level package names
        module_names = {req.name for req in requirements}
        assert module_names == {"os", "collections", "xml"}

    def test_relative_imports_skipped(self, tmp_path):
        """Test that relative imports are skipped."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                from . import module
                from .. import parent
                from ...package import something
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        # Relative imports should be skipped
        assert len(requirements) == 0

    def test_detect_missing_packages_convenience_function(self, tmp_path):
        """Test convenience function for package detection."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys")

        result = detect_missing_packages(paths=[test_file])

        assert isinstance(result, PackageDetectionResult)
        assert result.files_analyzed == 1
        assert result.total_imports == 2

    def test_detect_missing_packages_directory(self, tmp_path):
        """Test convenience function with directory analysis."""
        (tmp_path / "module.py").write_text("import os")

        result = detect_missing_packages(directory=tmp_path)

        assert isinstance(result, PackageDetectionResult)
        assert result.files_analyzed >= 1

    def test_error_handling_in_analyze_files(self, tmp_path):
        """Test error handling when analyzing files."""
        # Create a file that will cause an error
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        detector = PackageDetector(project_root=tmp_path)

        # Try to analyze a non-existent file
        result = detector.analyze_files([tmp_path / "nonexistent.py"])

        assert len(result.errors) > 0
        assert result.files_analyzed == 0

    def test_package_requirement_dataclass(self):
        """Test PackageRequirement dataclass."""
        req = PackageRequirement(
            name="requests",
            import_statement="import requests",
            file_path="src/module.py",
            line_number=5,
            is_stdlib=False,
            is_installed=True,
            suggested_package="requests",
        )

        assert req.name == "requests"
        assert req.line_number == 5
        assert req.is_stdlib is False
        assert req.is_installed is True

    def test_package_detection_result_dataclass(self):
        """Test PackageDetectionResult dataclass."""
        result = PackageDetectionResult(
            missing_packages=[],
            installed_packages=[],
            stdlib_imports=[],
            total_imports=10,
            files_analyzed=5,
            errors=[],
        )

        assert result.total_imports == 10
        assert result.files_analyzed == 5
        assert len(result.missing_packages) == 0

    def test_multiple_imports_same_package(self, tmp_path):
        """Test handling multiple imports of the same package."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                import os
                from os import path
                from os.path import join
                """)
        )

        detector = PackageDetector(project_root=tmp_path)
        requirements = detector._analyze_file(test_file)

        # Should detect all three imports
        assert len(requirements) == 3
        assert all(req.name == "os" for req in requirements)

    def test_summary_with_multiple_locations(self, tmp_path):
        """Test summary formatting with multiple import locations."""
        detector = PackageDetector(project_root=tmp_path)

        # Create multiple requirements for same package
        reqs = [
            PackageRequirement(
                name="requests",
                import_statement="import requests",
                file_path=f"src/module{i}.py",
                line_number=i,
                is_stdlib=False,
                is_installed=False,
                suggested_package="requests",
            )
            for i in range(5)
        ]

        result = PackageDetectionResult(
            missing_packages=reqs,
            installed_packages=[],
            stdlib_imports=[],
            total_imports=5,
            files_analyzed=5,
            errors=[],
        )

        summary = detector.get_missing_packages_summary(result)
        assert "5 location(s)" in summary
        assert "and 2 more" in summary  # Shows first 3, then "and 2 more"
