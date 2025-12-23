"""Test fixtures and scenarios for package detector tests"""

import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import pytest


class PackageScenario:
    """Represents a test scenario for package detection"""

    def __init__(
        self,
        name: str,
        files: Dict[str, str],
        expected_packages: List[str],
        description: str = "",
    ):
        self.name = name
        self.files = files
        self.expected_packages = expected_packages
        self.description = description

    def create_in_directory(self, base_path: Path) -> Path:
        """Create the scenario files in the given directory"""
        for file_path, content in self.files.items():
            full_path = base_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
        return base_path


# Basic Python package scenarios
BASIC_PACKAGE_SCENARIOS = [
    PackageScenario(
        name="simple_requirements",
        files={
            "requirements.txt": "requests==2.28.0\nnumpy>=1.20.0\npandas\n",
        },
        expected_packages=["requests", "numpy", "pandas"],
        description="Simple requirements.txt with various version specifiers",
    ),
    PackageScenario(
        name="pyproject_toml_poetry",
        files={
            "pyproject.toml": """[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
fastapi = ">=0.95.0"

[tool.poetry.dev-dependencies]
pytest = "^7.0.0"
""",
        },
        expected_packages=["requests", "fastapi", "pytest"],
        description="Poetry-style pyproject.toml",
    ),
    PackageScenario(
        name="setup_py",
        files={
            "setup.py": """from setuptools import setup

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
""",
        },
        expected_packages=["flask", "sqlalchemy", "pydantic", "pytest", "black"],
        description="Traditional setup.py with install_requires and extras_require",
    ),
    PackageScenario(
        name="pipfile",
        files={
            "Pipfile": """[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
django = "*"
celery = ">=5.0.0"

[dev-packages]
pylint = "*"
""",
        },
        expected_packages=["django", "celery", "pylint"],
        description="Pipenv Pipfile",
    ),
]

# Edge case scenarios
EDGE_CASE_SCENARIOS = [
    PackageScenario(
        name="empty_requirements",
        files={"requirements.txt": ""},
        expected_packages=[],
        description="Empty requirements file",
    ),
    PackageScenario(
        name="comments_and_whitespace",
        files={
            "requirements.txt": """# This is a comment
requests==2.28.0

# Another comment
numpy  # inline comment


pandas>=1.0.0
""",
        },
        expected_packages=["requests", "numpy", "pandas"],
        description="Requirements with comments and whitespace",
    ),
    PackageScenario(
        name="git_urls",
        files={
            "requirements.txt": """git+https://github.com/user/repo.git@v1.0#egg=mypackage
git+ssh://git@github.com/user/another.git
requests==2.28.0
""",
        },
        expected_packages=["mypackage", "requests"],
        description="Requirements with git URLs",
    ),
    PackageScenario(
        name="editable_installs",
        files={
            "requirements.txt": "-e ./local-package\n-e git+https://github.com/user/repo.git#egg=remote-pkg\nrequests\n",
        },
        expected_packages=["remote-pkg", "requests"],
        description="Editable installs with -e flag",
    ),
    PackageScenario(
        name="complex_version_specifiers",
        files={
            "requirements.txt": """package1>=1.0.0,<2.0.0
package2~=1.4.2
package3===1.0.0
package4!=1.5.0
""",
        },
        expected_packages=["package1", "package2", "package3", "package4"],
        description="Complex version specifiers",
    ),
    PackageScenario(
        name="extras",
        files={
            "requirements.txt": "requests[security,socks]\ndjango[argon2]>=3.0\n",
        },
        expected_packages=["requests", "django"],
        description="Packages with extras",
    ),
    PackageScenario(
        name="environment_markers",
        files={
            "requirements.txt": """requests==2.28.0
pywin32>=1.0; sys_platform == 'win32'
uvloop; platform_system != 'Windows'
""",
        },
        expected_packages=["requests", "pywin32", "uvloop"],
        description="Packages with environment markers",
    ),
    PackageScenario(
        name="malformed_lines",
        files={
            "requirements.txt": """requests==2.28.0
===invalid===
numpy
@@@malformed@@@
pandas>=1.0.0
""",
        },
        expected_packages=["requests", "numpy", "pandas"],
        description="Requirements with some malformed lines",
    ),
]

# Integration scenarios with multiple files
INTEGRATION_SCENARIOS = [
    PackageScenario(
        name="multiple_requirement_files",
        files={
            "requirements.txt": "requests==2.28.0\nnumpy\n",
            "requirements-dev.txt": "pytest>=7.0.0\nblack\n",
            "requirements-prod.txt": "gunicorn\npsycopg2-binary\n",
        },
        expected_packages=["requests", "numpy", "pytest", "black", "gunicorn", "psycopg2-binary"],
        description="Multiple requirements files",
    ),
    PackageScenario(
        name="mixed_formats",
        files={
            "requirements.txt": "requests==2.28.0\n",
            "pyproject.toml": """[tool.poetry.dependencies]
fastapi = "^0.95.0"
""",
            "setup.py": """from setuptools import setup
setup(
    name='test',
    install_requires=['flask'],
)
""",
        },
        expected_packages=["requests", "fastapi", "flask"],
        description="Mixed package definition formats",
    ),
    PackageScenario(
        name="nested_directories",
        files={
            "requirements.txt": "requests\n",
            "backend/requirements.txt": "fastapi\n",
            "frontend/package.json": '{"dependencies": {"react": "^18.0.0"}}',
            "services/api/requirements.txt": "sqlalchemy\n",
        },
        expected_packages=["requests", "fastapi", "sqlalchemy"],
        description="Requirements files in nested directories",
    ),
    PackageScenario(
        name="pyproject_toml_pep621",
        files={
            "pyproject.toml": """[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "numpy",
]

[project.optional-dependencies]
dev = ["pytest", "black"]
test = ["coverage"]
""",
        },
        expected_packages=["requests", "numpy", "pytest", "black", "coverage"],
        description="PEP 621 style pyproject.toml",
    ),
    PackageScenario(
        name="requirements_with_includes",
        files={
            "requirements.txt": "-r base.txt\n-r dev.txt\nrequests\n",
            "base.txt": "numpy\npandas\n",
            "dev.txt": "pytest\nblack\n",
        },
        expected_packages=["numpy", "pandas", "pytest", "black", "requests"],
        description="Requirements with -r includes",
    ),
]

# No packages scenarios
NO_PACKAGES_SCENARIOS = [
    PackageScenario(
        name="no_package_files",
        files={
            "README.md": "# Test Project\n",
            "src/main.py": "print('hello')\n",
        },
        expected_packages=[],
        description="Project with no package definition files",
    ),
    PackageScenario(
        name="empty_directory",
        files={},
        expected_packages=[],
        description="Empty directory",
    ),
]


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test projects"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def create_scenario(temp_project_dir):
    """Factory fixture to create package scenarios"""

    def _create(scenario: PackageScenario) -> Path:
        return scenario.create_in_directory(temp_project_dir)

    return _create
