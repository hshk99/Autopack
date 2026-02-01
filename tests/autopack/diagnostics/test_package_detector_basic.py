"""Basic tests for package detector functionality"""

import pytest

from autopack.diagnostics.package_detector import PackageDetector
from tests.autopack.diagnostics.fixtures.package_scenarios import \
    BASIC_PACKAGE_SCENARIOS


class TestPackageDetectorBasic:
    """Basic functionality tests for PackageDetector"""

    def test_detector_initialization(self):
        """Test that PackageDetector can be initialized"""
        detector = PackageDetector()
        assert detector is not None

    def test_detect_simple_requirements(self, temp_project_dir):
        """Test detection of simple requirements.txt"""
        # Create requirements.txt
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("requests==2.28.0\nnumpy>=1.20.0\npandas\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages
        assert len(packages) == 3

    def test_detect_pyproject_toml_poetry(self, temp_project_dir):
        """Test detection of Poetry-style pyproject.toml"""
        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text("""[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
fastapi = ">=0.95.0"

[tool.poetry.dev-dependencies]
pytest = "^7.0.0"
""")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "fastapi" in packages
        assert "pytest" in packages
        # python is not a package, should be filtered
        assert "python" not in packages

    def test_detect_setup_py(self, temp_project_dir):
        """Test detection of setup.py with install_requires"""
        setup_file = temp_project_dir / "setup.py"
        setup_file.write_text("""from setuptools import setup

setup(
    name='test-package',
    version='1.0.0',
    install_requires=[
        'flask>=2.0.0',
        'sqlalchemy',
        'pydantic>=1.9.0',
    ],
    extras_require={
        'dev': ['pytest', 'black'],
    },
)
""")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "flask" in packages
        assert "sqlalchemy" in packages
        assert "pydantic" in packages
        assert "pytest" in packages
        assert "black" in packages

    def test_detect_pipfile(self, temp_project_dir):
        """Test detection of Pipfile"""
        pipfile = temp_project_dir / "Pipfile"
        pipfile.write_text("""[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
django = "*"
celery = ">=5.0.0"

[dev-packages]
pylint = "*"
""")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "django" in packages
        assert "celery" in packages
        assert "pylint" in packages

    def test_detect_pyproject_toml_pep621(self, temp_project_dir):
        """Test detection of PEP 621 style pyproject.toml"""
        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text("""[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "numpy",
]

[project.optional-dependencies]
dev = ["pytest", "black"]
test = ["coverage"]
""")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "requests" in packages
        assert "numpy" in packages
        assert "pytest" in packages
        assert "black" in packages
        assert "coverage" in packages

    @pytest.mark.parametrize("scenario", BASIC_PACKAGE_SCENARIOS, ids=lambda s: s.name)
    def test_basic_scenarios(self, scenario, create_scenario):
        """Test all basic package detection scenarios"""
        project_dir = create_scenario(scenario)

        detector = PackageDetector()
        packages = detector.detect_packages(str(project_dir))

        # Convert to sets for comparison
        detected = set(packages)
        expected = set(scenario.expected_packages)

        assert detected == expected, (
            f"Scenario '{scenario.name}' failed: "
            f"expected {expected}, got {detected}. "
            f"Missing: {expected - detected}, Extra: {detected - expected}"
        )

    def test_version_specifiers_stripped(self, temp_project_dir):
        """Test that version specifiers are properly stripped"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("""requests==2.28.0
numpy>=1.20.0,<2.0.0
pandas~=1.4.0
flask===2.0.0
""")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # All packages should be detected without version info
        assert "requests" in packages
        assert "numpy" in packages
        assert "pandas" in packages
        assert "flask" in packages

        # No version info should be in package names
        for pkg in packages:
            assert "==" not in pkg
            assert ">=" not in pkg
            assert "~=" not in pkg
            assert "<" not in pkg

    def test_case_insensitive_detection(self, temp_project_dir):
        """Test that package detection is case-insensitive"""
        req_file = temp_project_dir / "requirements.txt"
        req_file.write_text("Requests\nNumPy\nPANDAS\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Packages should be normalized to lowercase
        packages_lower = [p.lower() for p in packages]
        assert "requests" in packages_lower
        assert "numpy" in packages_lower
        assert "pandas" in packages_lower

    def test_no_package_files(self, temp_project_dir):
        """Test detection when no package files exist"""
        # Create some non-package files
        (temp_project_dir / "README.md").write_text("# Test Project")
        (temp_project_dir / "src").mkdir()
        (temp_project_dir / "src" / "main.py").write_text("print('hello')")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert len(packages) == 0

    def test_empty_directory(self, temp_project_dir):
        """Test detection in empty directory"""
        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert len(packages) == 0

    def test_nonexistent_directory(self):
        """Test detection with nonexistent directory"""
        detector = PackageDetector()
        packages = detector.detect_packages("/nonexistent/path/to/project")

        assert len(packages) == 0

    def test_duplicate_packages_deduplicated(self, temp_project_dir):
        """Test that duplicate packages across files are deduplicated"""
        # Create multiple files with overlapping packages
        (temp_project_dir / "requirements.txt").write_text("requests\nnumpy\n")
        (temp_project_dir / "requirements-dev.txt").write_text("requests\npytest\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should have unique packages only
        assert len(packages) == len(set(packages))
        assert "requests" in packages
        assert "numpy" in packages
        assert "pytest" in packages
        assert packages.count("requests") == 1
