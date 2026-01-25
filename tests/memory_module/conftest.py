"""Pytest configuration for memory_module tests.

This ensures sys.path is set up correctly for pytest-xdist parallel execution.
Uses pytest_configure hook to run before any test collection.
"""

import sys
from pathlib import Path


def pytest_configure(config):
    """Configure pytest - runs before test collection in all workers."""
    _project_root = Path(__file__).resolve().parent.parent.parent
    _src_path = _project_root / "src"
    _src_path_str = str(_src_path)
    if _src_path_str not in sys.path:
        sys.path.insert(0, _src_path_str)


# Also run at module import time for good measure
_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
_src_path_str = str(_src_path)
if _src_path_str not in sys.path:
    sys.path.insert(0, _src_path_str)
