"""Shared fixtures for diagnostics tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def create_scenario(temp_project_dir):
    """Fixture that creates a package scenario in a temporary directory."""

    def _create(scenario):
        """Create the scenario files and return the directory path."""
        return scenario.create_in_directory(temp_project_dir)

    return _create
