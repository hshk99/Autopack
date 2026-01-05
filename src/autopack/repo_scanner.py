"""
Deterministic Repository Structure Analysis

Scans repository file tree, detects anchor files/directories,
and builds a structure summary for pattern matching.

Key Features:
- Respects .gitignore
- Detects anchor files (auth/, api/, etc.)
- 0 LLM calls (fully deterministic)
- Fast (caches results)
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
import fnmatch


class RepoScanner:
    """
    Scan repository structure (respects .gitignore).

    Used by PatternMatcher to ground manifest generation
    in actual repo layout.
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.gitignore_patterns = self._load_gitignore()
        self._scan_cache = None

    def scan(self, use_cache: bool = True) -> Dict[str, any]:
        """
        Scan repo and build structure summary.

        Returns:
            {
                "tree": {...},           # Directory tree
                "anchor_files": {...},   # Key modules detected
                "file_count": int,
                "directory_map": {...}   # Path → category hints
            }
        """

        if use_cache and self._scan_cache:
            return self._scan_cache

        tree = {}
        all_files = []

        # Walk directory tree
        for root, dirs, files in os.walk(self.workspace):
            root_path = Path(root)

            # Respect .gitignore
            dirs[:] = [d for d in dirs if not self._should_ignore(root_path / d)]
            files = [f for f in files if not self._should_ignore(root_path / f)]

            try:
                rel_root = root_path.relative_to(self.workspace)
            except ValueError:
                continue

            rel_root_str = rel_root.as_posix()
            tree[rel_root_str] = {"dirs": dirs, "files": files}

            for f in files:
                if rel_root_str in {"", "."}:
                    all_files.append(Path(f).as_posix())
                else:
                    all_files.append((Path(rel_root_str) / f).as_posix())

        # Detect anchor files
        anchor_files = self._detect_anchor_files(tree)

        # Build directory map
        directory_map = self._build_directory_map(tree, anchor_files)

        result = {
            "tree": tree,
            "anchor_files": anchor_files,
            "file_count": len(all_files),
            "all_files": all_files,
            "directory_map": directory_map,
        }

        self._scan_cache = result
        return result

    def _load_gitignore(self) -> List[str]:
        """Load .gitignore patterns"""

        gitignore_file = self.workspace / ".gitignore"
        if not gitignore_file.exists():
            return []

        patterns = []
        with open(gitignore_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)

        return patterns

    def _should_ignore(self, path: Path) -> bool:
        """
        Check if path should be ignored (.gitignore + defaults).

        Default ignores (always):
        - .git/
        - venv/, .venv/
        - node_modules/
        - __pycache__/
        - .pytest_cache/
        - *.pyc, *.pyo
        """

        # Default ignores
        default_ignores = {
            ".git",
            "venv",
            ".venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "build",
            "dist",
            ".egg-info",
            ".tox",
            "coverage",
            ".coverage",
        }

        # Check if any part of path matches default ignores
        for part in path.parts:
            if part in default_ignores:
                return True

        # Check file extensions
        if path.suffix in {".pyc", ".pyo", ".pyd", ".so", ".dylib"}:
            return True

        # Check .gitignore patterns
        try:
            rel_path = path.relative_to(self.workspace)
        except ValueError:
            return False

        rel_str = str(rel_path).replace("\\", "/")

        for pattern in self.gitignore_patterns:
            if fnmatch.fnmatch(rel_str, pattern):
                return True

            # Directory pattern (ends with /)
            if pattern.endswith("/"):
                dir_pattern = pattern.rstrip("/")
                if rel_str.startswith(dir_pattern):
                    return True

        return False

    def _detect_anchor_files(self, tree: Dict) -> Dict[str, List[str]]:
        """
        Detect anchor files/directories that hint at structure.

        Examples:
        - src/auth/ → authentication category
        - src/api/endpoints/ → api_endpoint category
        - src/frontend/ → frontend category
        - tests/auth/ → test files for auth
        """

        anchors = {}

        # Authentication anchors
        auth_dirs = ["src/auth", "src/authentication", "backend/auth", "api/auth"]
        for dir_path in auth_dirs:
            if dir_path in tree:
                anchors.setdefault("authentication", []).append(dir_path + "/")

        # API endpoint anchors
        api_dirs = [
            "src/api/endpoints",
            "src/api/routes",
            "src/api/routers",
            "backend/api",
            "api/endpoints",
        ]
        for dir_path in api_dirs:
            if dir_path in tree:
                anchors.setdefault("api_endpoint", []).append(dir_path + "/")

        # Frontend anchors
        frontend_dirs = ["src/frontend", "frontend", "src/ui", "ui", "src/components", "components"]
        for dir_path in frontend_dirs:
            if dir_path in tree:
                anchors.setdefault("frontend", []).append(dir_path + "/")

        # Database anchors
        db_dirs = ["src/database", "src/db", "src/models", "backend/database", "api/models"]
        for dir_path in db_dirs:
            if dir_path in tree:
                anchors.setdefault("database", []).append(dir_path + "/")

        # Config anchors
        config_files = []
        for dir_path, data in tree.items():
            if "config.py" in data["files"] or "settings.py" in data["files"]:
                config_files.append(dir_path + "/")

        if config_files:
            anchors["config"] = config_files

        # Test anchors
        test_dirs = [d for d in tree.keys() if "test" in d.lower()]
        if test_dirs:
            anchors["tests"] = [d + "/" for d in test_dirs]

        return anchors

    def _build_directory_map(
        self, tree: Dict, anchor_files: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """
        Build directory → category hints map.

        Uses anchor files to infer which directories belong
        to which categories.
        """

        directory_map = {}

        for category, anchors in anchor_files.items():
            for anchor in anchors:
                anchor_clean = anchor.rstrip("/")

                # All dirs under anchor belong to this category
                for dir_path in tree.keys():
                    if dir_path.startswith(anchor_clean):
                        directory_map.setdefault(dir_path, []).append(category)

        return directory_map

    def get_files_in_category(self, category: str) -> List[str]:
        """Get all files in a category (based on anchor detection)"""

        structure = self.scan()
        anchor_files = structure["anchor_files"]

        if category not in anchor_files:
            return []

        files = []
        for anchor in anchor_files[category]:
            anchor_clean = anchor.rstrip("/")

            # Get all files under anchor
            for dir_path, data in structure["tree"].items():
                if dir_path.startswith(anchor_clean):
                    for file_name in data["files"]:
                        file_path = str(Path(dir_path) / file_name)
                        files.append(file_path)

        return files

    def get_anchor_dirs(self, category: str) -> List[str]:
        """Get anchor directories for a category"""

        structure = self.scan()
        return structure["anchor_files"].get(category, [])

    def path_exists(self, path: str) -> bool:
        """Check if path exists in repo"""

        full_path = self.workspace / path
        return full_path.exists()

    def get_parent_dir(self, file_path: str) -> Optional[str]:
        """Get parent directory of a file"""

        parent = Path(file_path).parent
        if parent == Path("."):
            return None

        return parent.as_posix() + "/"

    def get_sibling_files(self, file_path: str) -> List[str]:
        """Get sibling files in same directory"""

        parent = Path(file_path).parent
        file_name = Path(file_path).name

        structure = self.scan()
        tree = structure["tree"]

        parent_str = parent.as_posix()
        if parent_str not in tree:
            return []

        siblings = tree[parent_str]["files"]
        return [(parent / s).as_posix() for s in siblings if s != file_name]
