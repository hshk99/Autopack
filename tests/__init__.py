"""Test package marker.

Pytest can import test modules by basename. When two test files share the same
basename (e.g. `test_orchestrator.py` in multiple directories), Python import
cache collisions can occur.

Making `tests/` a package ensures fully-qualified module names and prevents
`import file mismatch` collection errors.
"""

"""Test package for Autopack."""

import sys
from pathlib import Path

# Ensure src directory is in Python path for all test modules
_project_root = Path(__file__).resolve().parent.parent
_src_path = _project_root / "src"
_backend_path = _src_path / "backend"

for _path in (_project_root, _src_path, _backend_path):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)
