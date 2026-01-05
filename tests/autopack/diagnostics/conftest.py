"""Shared fixtures for diagnostics tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
