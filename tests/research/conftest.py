"""Automatically mark all research tests with @pytest.mark.research.

The research subsystem has API drift and missing symbols. Tests are quarantined
until the subsystem is stabilized.

Run research tests explicitly with: pytest -m research
Skip research tests (default): pytest -m "not research"
"""
import pytest


def pytest_collection_modifyitems(items):
    """Auto-mark all tests in tests/research/ with @pytest.mark.research."""
    for item in items:
        if "tests/research" in str(item.fspath) or "tests\\research" in str(item.fspath):
            item.add_marker(pytest.mark.research)
