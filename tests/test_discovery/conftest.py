"""Test configuration for discovery module tests."""

import sys
from pathlib import Path

# Ensure src directory is on sys.path for discovery module imports
_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = str(_project_root / "src")

if _src_path not in sys.path:
    sys.path.insert(0, _src_path)
