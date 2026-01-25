"""Pytest configuration for memory_module tests.

This ensures sys.path is set up correctly for pytest-xdist parallel execution.
"""

import sys
from pathlib import Path

# Ensure src directory is in Python path before imports
_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"

_src_path_str = str(_src_path)
if _src_path_str not in sys.path:
    sys.path.insert(0, _src_path_str)
