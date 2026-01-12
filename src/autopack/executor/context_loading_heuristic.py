"""Heuristic context loading for autonomous executor.

Extracted from autonomous_executor.py as part of Item 1.1 god file refactoring (PR-EXE-6).

The heuristic loader determines which files to include in LLM context using a
priority-based approach with deterministic ordering.

Priority order:
1. Git status files (modified/staged/untracked) - ensures fresh state after patches
2. Explicitly mentioned files (from phase description)
3. Priority files (key config files like package.json, setup.py)
4. Source files (from common directories like src/, backend/)

Enforces max_files cap and token budget while maintaining deterministic ordering.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FileSource:
    """Classification of why a file was included in context."""

    GIT_STATUS = "git_status"
    MENTIONED = "mentioned"
    PRIORITY = "priority"
    SOURCE = "source"


@dataclass
class ContextFile:
    """A file selected for LLM context with metadata."""

    path: str
    source: str  # FileSource value
    priority: int  # Lower = higher priority
    content: Optional[str] = None
    token_estimate: int = 0


class HeuristicContextLoader:
    """Loads repository context using priority-based heuristics.

    Priority order (deterministic):
    1. Git status files (modified/staged/untracked)
    2. Explicitly mentioned files (from phase spec description)
    3. Priority files (from configuration)
    4. Source files (pattern-based inference)

    Enforces max_files cap and token budget while maintaining deterministic ordering.
    """

    # Default config values
    DEFAULT_MAX_FILES = 40
    DEFAULT_TARGET_TOKENS = 20000
    DEFAULT_MAX_CHARS_PER_FILE = 15000

    # File patterns for extraction from descriptions
    FILE_PATTERN = r"[a-zA-Z_][a-zA-Z0-9_/\\.-]*\.(?:py|yaml|json|ts|js|md)"

    def __init__(
        self,
        max_files: int = DEFAULT_MAX_FILES,
        target_tokens: int = DEFAULT_TARGET_TOKENS,
        max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE,
    ):
        """Initialize heuristic loader.

        Args:
            max_files: Maximum number of files to include in context
            target_tokens: Target token budget (files may be skipped to stay under)
            max_chars_per_file: Maximum characters to read from each file
        """
        self.max_files = max_files
        self.target_tokens = target_tokens
        self.max_chars_per_file = max_chars_per_file

    def load_context_files(
        self,
        workspace: Path,
        git_status_files: List[str],
        mentioned_files: List[str],
        priority_files: List[str],
        source_dirs: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Load context files using priority heuristics.

        Args:
            workspace: Root directory of the workspace
            git_status_files: Files from git status (modified/staged/untracked)
            mentioned_files: Files explicitly mentioned in phase description
            priority_files: Files marked as priority in configuration
            source_dirs: Source directories to scan (defaults to ["src", "backend", "app", "lib"])

        Returns:
            Dict mapping file paths to content strings
        """
        if source_dirs is None:
            source_dirs = ["src", "backend", "app", "lib"]

        loaded_paths: Set[str] = set()
        existing_files: Dict[str, str] = {}
        current_token_estimate = 0

        def _load_file(filepath: Path) -> bool:
            """Load a single file if not already loaded. Returns True if loaded."""
            nonlocal current_token_estimate

            if len(existing_files) >= self.max_files:
                return False

            try:
                rel_path = str(filepath.relative_to(workspace))
            except ValueError:
                # File is outside workspace
                return False

            if rel_path in loaded_paths:
                return False
            if not filepath.exists() or not filepath.is_file():
                return False
            if "__pycache__" in rel_path or ".pyc" in rel_path:
                return False

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                content_trimmed = content[: self.max_chars_per_file]

                # Check if adding this file would exceed token budget
                file_tokens = self._estimate_file_tokens(content_trimmed)
                if current_token_estimate + file_tokens > self.target_tokens:
                    logger.debug(
                        f"[Context] Skipping {rel_path} - would exceed token budget "
                        f"({current_token_estimate + file_tokens} > {self.target_tokens})"
                    )
                    return False

                existing_files[rel_path] = content_trimmed
                loaded_paths.add(rel_path)
                current_token_estimate += file_tokens
                return True
            except Exception as e:
                logger.warning(f"Failed to read {filepath}: {e}")
                return False

        # Priority 0: Recently modified files from git status (ALWAYS FRESH)
        modified_count = 0
        for rel_path in git_status_files[:15]:  # Limit to 15 git status files
            if not self._is_valid_path_string(rel_path):
                continue
            try:
                filepath = workspace / rel_path
                if _load_file(filepath):
                    modified_count += 1
            except (TypeError, ValueError) as e:
                logger.warning(f"[Context] Error processing git status path '{rel_path}': {e}")
                continue

        if modified_count > 0:
            logger.info(
                f"[Context] Loaded {modified_count} recently modified files for fresh context"
            )

        # Priority 1: Files mentioned in phase description
        mentioned_count = 0
        for pattern in mentioned_files[:10]:  # Limit to 10 mentioned files
            if not self._is_valid_path_string(pattern):
                continue
            try:
                # Try exact match first
                filepath = workspace / pattern
                if _load_file(filepath):
                    mentioned_count += 1
                    continue
                # Try finding in src/ or config/ directories
                for prefix in ["src/autopack/", "config/", "src/", ""]:
                    filepath = workspace / prefix / pattern
                    if _load_file(filepath):
                        mentioned_count += 1
                        break
            except (TypeError, ValueError) as e:
                logger.warning(f"[Context] Error processing mentioned file '{pattern}': {e}")
                continue

        if mentioned_count > 0:
            logger.info(f"[Context] Loaded {mentioned_count} files mentioned in phase description")

        # Priority 2: Key config files (always include if they exist)
        for filename in priority_files:
            _load_file(workspace / filename)

        # Priority 3: Source files from common directories
        for source_dir in source_dirs:
            dir_path = workspace / source_dir
            if not dir_path.exists():
                continue

            # Load Python files
            for py_file in dir_path.rglob("*.py"):
                if len(existing_files) >= self.max_files:
                    break
                _load_file(py_file)

        # Log final results
        logger.info(
            f"[Context] Total: {len(existing_files)} files loaded for Builder context "
            f"(modified={modified_count}, mentioned={mentioned_count})"
        )
        logger.info(
            f"[TOKEN_BUDGET] Context loading: ~{current_token_estimate} tokens "
            f"({current_token_estimate * 100 // self.target_tokens}% of {self.target_tokens} budget)"
        )

        return existing_files

    def extract_git_status_files(self, workspace: Path) -> List[str]:
        """Extract list of files from git status.

        Args:
            workspace: Root directory of the workspace

        Returns:
            List of file paths (relative to workspace) that have changes
        """
        recently_modified = []
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line and len(line) > 3:
                        # Parse git status format: "XY filename" or "XY old -> new"
                        file_part = line[3:].strip()
                        if " -> " in file_part:
                            file_part = file_part.split(" -> ")[1]
                        if file_part:
                            recently_modified.append(file_part)
        except Exception as e:
            logger.debug(f"Could not get git status for fresh context: {e}")

        return recently_modified

    def extract_mentioned_files(
        self, phase_description: str, acceptance_criteria: Optional[List[str]] = None
    ) -> List[str]:
        """Extract file paths mentioned in phase description.

        Args:
            phase_description: Phase description text
            acceptance_criteria: Optional list of acceptance criteria strings

        Returns:
            List of file paths extracted from text
        """
        if acceptance_criteria is None:
            acceptance_criteria = []

        phase_criteria = " ".join(acceptance_criteria)
        combined_text = f"{phase_description} {phase_criteria}"

        # Match patterns like: src/autopack/file.py, config/models.yaml, etc.
        file_patterns = re.findall(self.FILE_PATTERN, combined_text)
        return file_patterns

    @staticmethod
    def _estimate_file_tokens(content: str) -> int:
        """Estimate token count for file content (~4 chars per token)."""
        return len(content) // 4

    @staticmethod
    def _is_valid_path_string(path: str) -> bool:
        """Validate that path is a non-empty string."""
        if not isinstance(path, str):
            logger.warning(f"[Context] Skipping non-string path: {path} (type: {type(path)})")
            return False
        if not path or not path.strip():
            return False
        return True


def get_default_priority_files() -> List[str]:
    """Return default list of priority config files.

    Returns:
        List of config file names that should be prioritized
    """
    return [
        "package.json",
        "setup.py",
        "requirements.txt",
        "pyproject.toml",
        "README.md",
        ".gitignore",
    ]
