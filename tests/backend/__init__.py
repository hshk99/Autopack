"""Backend tests package."""

import sys
from pathlib import Path

# Ensure backend package is importable
_project_root = Path(__file__).resolve().parent.parent.parent
_src_path = _project_root / "src"
_backend_path = _src_path / "backend"

for _path in (_project_root, _src_path, _backend_path):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)
