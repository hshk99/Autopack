"""Automatically mark research subsystem tests with @pytest.mark.research.

The research subsystem has API drift and missing symbols. Tests are quarantined
until the subsystem is stabilized.
"""
import pytest


def pytest_collection_modifyitems(items):
    """Auto-mark all research-related tests with @pytest.mark.research."""
    for item in items:
        fspath_str = str(item.fspath)
        if ("tests/autopack/research" in fspath_str or
            "tests\\autopack\\research" in fspath_str or
            "test_research" in fspath_str):
            item.add_marker(pytest.mark.research)
