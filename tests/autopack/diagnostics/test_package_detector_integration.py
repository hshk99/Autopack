"""Integration tests for package detector with complex scenarios"""

import pytest
from pathlib import Path

from autopack.diagnostics.package_detector import PackageDetector
from tests.autopack.diagnostics.fixtures.package_scenarios import (
    INTEGRATION_SCENARIOS,
    create_scenario,
    temp_project_dir,
)


class TestPackageDetectorIntegration:
    """Integration tests for PackageDetector with complex scenarios"""

    def test_multiple_requirement_files(self, temp_project_dir):
        """Test detection across multiple requirements files"""
        (temp_project_dir / "requirements.txt").write_text("requests==2.28.0\nnumpy\n")
        (temp_project_dir / "requirements-dev.txt").write_text("pytest>=7.0.0\nblack\n")
        (temp_project_dir / "requirements-prod.txt").write_text("gunicorn\npsycopg2-binary\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all requirements files
        assert "requests" in packages
        assert "numpy" in packages
        assert "pytest" in packages
        assert "black" in packages
        assert "gunicorn" in packages
        assert "psycopg2-binary" in packages

    def test_mixed_formats(self, temp_project_dir):
        """Test detection with mixed package definition formats"""
        # requirements.txt
        (temp_project_dir / "requirements.txt").write_text("requests==2.28.0\n")

        # pyproject.toml
        (temp_project_dir / "pyproject.toml").write_text(
            """[tool.poetry.dependencies]
fastapi = "^0.95.0"
"""
        )

        # setup.py
        (temp_project_dir / "setup.py").write_text(
            """from setuptools import setup
setup(
    name='test',
    install_requires=['flask'],
)
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all formats
        assert "requests" in packages
        assert "fastapi" in packages
        assert "flask" in packages

    def test_nested_directories(self, temp_project_dir):
        """Test detection in nested directory structures"""
        # Root level
        (temp_project_dir / "requirements.txt").write_text("requests\n")

        # Backend directory
        backend_dir = temp_project_dir / "backend"
        backend_dir.mkdir()
        (backend_dir / "requirements.txt").write_text("fastapi\n")

        # Services directory
        services_dir = temp_project_dir / "services" / "api"
        services_dir.mkdir(parents=True)
        (services_dir / "requirements.txt").write_text("sqlalchemy\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all nested directories
        assert "requests" in packages
        assert "fastapi" in packages
        assert "sqlalchemy" in packages

    def test_requirements_with_includes(self, temp_project_dir):
        """Test requirements files that include other requirements files"""
        # Base requirements
        (temp_project_dir / "base.txt").write_text("numpy\npandas\n")

        # Dev requirements
        (temp_project_dir / "dev.txt").write_text("pytest\nblack\n")

        # Main requirements with includes
        (temp_project_dir / "requirements.txt").write_text(
            "-r base.txt\n-r dev.txt\nrequests\n"
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all included files
        assert "numpy" in packages
        assert "pandas" in packages
        assert "pytest" in packages
        assert "black" in packages
        assert "requests" in packages

    def test_monorepo_structure(self, temp_project_dir):
        """Test detection in monorepo structure with multiple projects"""
        # Project A
        project_a = temp_project_dir / "projects" / "project_a"
        project_a.mkdir(parents=True)
        (project_a / "requirements.txt").write_text("flask\nsqlalchemy\n")

        # Project B
        project_b = temp_project_dir / "projects" / "project_b"
        project_b.mkdir(parents=True)
        (project_b / "requirements.txt").write_text("fastapi\npydantic\n")

        # Shared
        shared = temp_project_dir / "shared"
        shared.mkdir()
        (shared / "requirements.txt").write_text("requests\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all projects
        assert "flask" in packages
        assert "sqlalchemy" in packages
        assert "fastapi" in packages
        assert "pydantic" in packages
        assert "requests" in packages

    def test_poetry_with_groups(self, temp_project_dir):
        """Test Poetry pyproject.toml with dependency groups"""
        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text(
            """[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
fastapi = ">=0.95.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0.0"
black = "^23.0.0"

[tool.poetry.group.docs.dependencies]
sphinx = "^5.0.0"
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages from all groups
        assert "requests" in packages
        assert "fastapi" in packages
        assert "pytest" in packages
        assert "black" in packages
        assert "sphinx" in packages

    def test_setup_cfg(self, temp_project_dir):
        """Test detection from setup.cfg"""
        setup_cfg = temp_project_dir / "setup.cfg"
        setup_cfg.write_text(
            """[metadata]
name = test-package
version = 1.0.0

[options]
install_requires =
    flask>=2.0.0
    sqlalchemy
    pydantic>=1.9.0

[options.extras_require]
dev =
    pytest
    black
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        assert "flask" in packages
        assert "sqlalchemy" in packages
        assert "pydantic" in packages
        assert "pytest" in packages
        assert "black" in packages

    def test_conda_environment_yml(self, temp_project_dir):
        """Test detection from conda environment.yml"""
        env_file = temp_project_dir / "environment.yml"
        env_file.write_text(
            """name: test-env
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.9
  - numpy
  - pandas>=1.3.0
  - pip:
    - requests
    - fastapi
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect both conda and pip packages
        assert "numpy" in packages
        assert "pandas" in packages
        assert "requests" in packages
        assert "fastapi" in packages

    def test_real_world_django_project(self, temp_project_dir):
        """Test detection in a realistic Django project structure"""
        # Main requirements
        (temp_project_dir / "requirements.txt").write_text(
            """Django>=4.0.0
django-environ
psycopg2-binary
celery[redis]
gunicorn
"""
        )

        # Dev requirements
        (temp_project_dir / "requirements-dev.txt").write_text(
            """-r requirements.txt
pytest-django
black
flake8
ipython
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Main packages
        assert "Django" in packages or "django" in [p.lower() for p in packages]
        assert "django-environ" in packages
        assert "psycopg2-binary" in packages
        assert "celery" in packages
        assert "gunicorn" in packages

        # Dev packages
        assert "pytest-django" in packages
        assert "black" in packages
        assert "flake8" in packages
        assert "ipython" in packages

    def test_real_world_fastapi_project(self, temp_project_dir):
        """Test detection in a realistic FastAPI project structure"""
        pyproject = temp_project_dir / "pyproject.toml"
        pyproject.write_text(
            """[tool.poetry]
name = "fastapi-app"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.9"
fastapi = "^0.95.0"
uvicorn = {extras = ["standard"], version = "^0.21.0"}
sqlalchemy = "^2.0.0"
alembic = "^1.10.0"
pydantic = {extras = ["email"], version = "^1.10.0"}
python-jose = {extras = ["cryptography"], version = "^3.3.0"}
passlib = {extras = ["bcrypt"], version = "^1.7.4"}

[tool.poetry.group.dev.dependencies]
pytest = "^7.2.0"
pytest-asyncio = "^0.20.0"
httpx = "^0.23.0"
black = "^23.0.0"
mypy = "^1.0.0"
"""
        )

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Main packages
        assert "fastapi" in packages
        assert "uvicorn" in packages
        assert "sqlalchemy" in packages
        assert "alembic" in packages
        assert "pydantic" in packages
        assert "python-jose" in packages
        assert "passlib" in packages

        # Dev packages
        assert "pytest" in packages
        assert "pytest-asyncio" in packages
        assert "httpx" in packages
        assert "black" in packages
        assert "mypy" in packages

    @pytest.mark.parametrize("scenario", INTEGRATION_SCENARIOS, ids=lambda s: s.name)
    def test_integration_scenarios(self, scenario, create_scenario):
        """Test all integration scenarios"""
        project_dir = create_scenario(scenario)

        detector = PackageDetector()
        packages = detector.detect_packages(str(project_dir))

        detected = set(packages)
        expected = set(scenario.expected_packages)

        assert detected == expected, (
            f"Scenario '{scenario.name}' failed: "
            f"expected {expected}, got {detected}. "
            f"Missing: {expected - detected}, Extra: {detected - expected}"
        )

    def test_large_project_performance(self, temp_project_dir):
        """Test performance with a large number of files"""
        import time

        # Create many requirements files
        for i in range(50):
            req_file = temp_project_dir / f"requirements-{i}.txt"
            req_file.write_text(f"package{i}\nrequests\n")

        start_time = time.time()
        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0, f"Detection took too long: {elapsed:.2f}s"

        # Should detect all packages
        assert "requests" in packages
        assert len(packages) >= 50  # At least 50 unique packages

    def test_circular_includes(self, temp_project_dir):
        """Test handling of circular includes in requirements files"""
        # Create circular reference
        (temp_project_dir / "req1.txt").write_text("-r req2.txt\nrequests\n")
        (temp_project_dir / "req2.txt").write_text("-r req1.txt\nnumpy\n")

        detector = PackageDetector()
        # Should handle gracefully without infinite loop
        packages = detector.detect_packages(str(temp_project_dir))

        # Should detect packages despite circular reference
        assert isinstance(packages, list)
        assert "requests" in packages or "numpy" in packages

    def test_deep_nesting(self, temp_project_dir):
        """Test detection in deeply nested directory structures"""
        # Create deep nesting
        deep_path = temp_project_dir
        for i in range(10):
            deep_path = deep_path / f"level{i}"
            deep_path.mkdir()

        (deep_path / "requirements.txt").write_text("requests\nnumpy\n")

        detector = PackageDetector()
        packages = detector.detect_packages(str(temp_project_dir))

        # Should find packages in deeply nested directories
        assert "requests" in packages
        assert "numpy" in packages
