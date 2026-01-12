"""Context loading heuristics for repository file selection.

Extracted from autonomous_executor.py for PR-EXE-6.
Provides heuristic-based file loading functions:
- Token-aware context loading with budget management
- Priority-based file selection (modified, mentioned, config)
- Pattern-based loading for templates, frontend, docker phases

This module focuses on reusable heuristic functions that don't require
executor instance state.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Token budget constants
DEFAULT_TARGET_INPUT_TOKENS = 20000
DEFAULT_MAX_FILES = 40
DEFAULT_CONTENT_TRIM_LIMIT = 15000


@dataclass
class ContextLoadResult:
    """Result of context loading operation.

    Attributes:
        existing_files: Dictionary of {path: content} for loaded files
        files_loaded: Total count of files loaded
        modified_files_loaded: Count of recently modified files
        mentioned_files_loaded: Count of files mentioned in phase
        tokens_estimated: Estimated total token count
        token_budget: Target token budget
    """
    existing_files: Dict[str, str]
    files_loaded: int = 0
    modified_files_loaded: int = 0
    mentioned_files_loaded: int = 0
    tokens_estimated: int = 0
    token_budget: int = DEFAULT_TARGET_INPUT_TOKENS


@dataclass
class FileLoader:
    """Context-aware file loader with token budgeting.

    Tracks loaded files and token budget to prevent context overflow.
    """
    workspace: Path
    max_files: int = DEFAULT_MAX_FILES
    target_tokens: int = DEFAULT_TARGET_INPUT_TOKENS
    content_trim_limit: int = DEFAULT_CONTENT_TRIM_LIMIT

    existing_files: Dict[str, str] = field(default_factory=dict)
    loaded_paths: Set[str] = field(default_factory=set)
    current_token_estimate: int = 0

    def estimate_tokens(self, content: str) -> int:
        """Estimate token count for content (~4 chars per token)."""
        return len(content) // 4

    def load_file(self, filepath: Path) -> bool:
        """Load a single file if not already loaded.

        Args:
            filepath: Path to file to load

        Returns:
            True if file was loaded, False otherwise
        """
        if len(self.existing_files) >= self.max_files:
            return False

        try:
            rel_path = str(filepath.relative_to(self.workspace)).replace("\\", "/")
        except ValueError:
            return False

        if rel_path in self.loaded_paths:
            return False
        if not filepath.exists() or not filepath.is_file():
            return False
        if "__pycache__" in rel_path or ".pyc" in rel_path:
            return False

        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            content_trimmed = content[:self.content_trim_limit]

            # Check token budget
            file_tokens = self.estimate_tokens(content_trimmed)
            if self.current_token_estimate + file_tokens > self.target_tokens:
                logger.debug(
                    f"[Context] Skipping {rel_path} - would exceed token budget "
                    f"({self.current_token_estimate + file_tokens} > {self.target_tokens})"
                )
                return False

            self.existing_files[rel_path] = content_trimmed
            self.loaded_paths.add(rel_path)
            self.current_token_estimate += file_tokens
            return True
        except Exception as e:
            logger.warning(f"Failed to read {filepath}: {e}")
            return False

    def get_result(self) -> ContextLoadResult:
        """Get the loading result."""
        return ContextLoadResult(
            existing_files=self.existing_files,
            files_loaded=len(self.existing_files),
            tokens_estimated=self.current_token_estimate,
            token_budget=self.target_tokens,
        )


def get_recently_modified_files(workspace: Path, timeout: int = 10) -> List[str]:
    """Get list of recently modified files from git status.

    Ensures Builder sees the latest state after earlier phases applied patches.

    Args:
        workspace: Workspace path
        timeout: Subprocess timeout in seconds

    Returns:
        List of relative file paths that have been modified
    """
    recently_modified = []

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                line = line.rstrip()  # Only strip trailing whitespace
                if line and len(line) > 3:
                    # Parse git status format: "XY filename" or "XY old -> new"
                    file_part = line[3:].strip()
                    if " -> " in file_part:
                        file_part = file_part.split(" -> ")[1]
                    if file_part:
                        recently_modified.append(file_part)
    except subprocess.TimeoutExpired:
        logger.debug("Timeout getting git status for fresh context")
    except Exception as e:
        logger.debug(f"Could not get git status for fresh context: {e}")

    return recently_modified


def extract_mentioned_files(phase_text: str) -> List[str]:
    """Extract file paths mentioned in phase description.

    Args:
        phase_text: Combined phase description and criteria text

    Returns:
        List of file patterns found in the text
    """
    # Match patterns like: src/autopack/file.py, config/models.yaml, etc.
    file_patterns = re.findall(
        r"[a-zA-Z_][a-zA-Z0-9_/\\.-]*\.(?:py|yaml|json|ts|js|md)",
        phase_text,
    )
    return file_patterns[:10]  # Limit to 10 mentioned files


def load_priority_config_files(loader: FileLoader) -> int:
    """Load priority configuration files.

    Args:
        loader: FileLoader instance

    Returns:
        Count of files loaded
    """
    priority_files = [
        "package.json",
        "setup.py",
        "requirements.txt",
        "pyproject.toml",
        "README.md",
        ".gitignore",
    ]

    loaded = 0
    for filename in priority_files:
        if loader.load_file(loader.workspace / filename):
            loaded += 1

    return loaded


def load_source_directories(
    loader: FileLoader,
    source_dirs: Optional[List[str]] = None,
) -> int:
    """Load Python files from common source directories.

    Args:
        loader: FileLoader instance
        source_dirs: List of source directory names to search

    Returns:
        Count of files loaded
    """
    if source_dirs is None:
        source_dirs = ["src", "backend", "app", "lib"]

    loaded = 0
    for source_dir in source_dirs:
        dir_path = loader.workspace / source_dir
        if not dir_path.exists():
            continue

        for py_file in dir_path.rglob("*.py"):
            if len(loader.existing_files) >= loader.max_files:
                break
            if loader.load_file(py_file):
                loaded += 1

    return loaded


def load_repository_context_heuristic(
    workspace: Path,
    phase: Dict,
    max_files: int = DEFAULT_MAX_FILES,
    target_tokens: int = DEFAULT_TARGET_INPUT_TOKENS,
) -> ContextLoadResult:
    """Load repository context using heuristics.

    Priority order:
    1. Recently modified files (git status) - for freshness
    2. Files mentioned in phase description
    3. Priority config files
    4. Source directory files

    Args:
        workspace: Workspace path
        phase: Phase specification dict
        max_files: Maximum files to load
        target_tokens: Target token budget

    Returns:
        ContextLoadResult with loaded files
    """
    loader = FileLoader(
        workspace=workspace,
        max_files=max_files,
        target_tokens=target_tokens,
    )

    # Priority 0: Recently modified files from git status (ALWAYS FRESH)
    recently_modified = get_recently_modified_files(workspace)
    modified_count = 0

    for rel_path in recently_modified[:15]:  # Limit to 15 recently modified files
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        try:
            filepath = workspace / rel_path
            if loader.load_file(filepath):
                modified_count += 1
        except (TypeError, ValueError) as e:
            logger.warning(f"[Context] Error processing rel_path '{rel_path}': {e}")
            continue

    if modified_count > 0:
        logger.info(
            f"[Context] Loaded {modified_count} recently modified files for fresh context"
        )

    # Priority 1: Files mentioned in phase description
    phase_description = phase.get("description", "")
    phase_criteria = " ".join(phase.get("acceptance_criteria", []))
    combined_text = f"{phase_description} {phase_criteria}"

    file_patterns = extract_mentioned_files(combined_text)
    mentioned_count = 0

    for pattern in file_patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        try:
            # Try exact match first
            filepath = workspace / pattern
            if loader.load_file(filepath):
                mentioned_count += 1
                continue
            # Try finding in src/ or config/ directories
            for prefix in ["src/autopack/", "config/", "src/", ""]:
                filepath = workspace / prefix / pattern
                if loader.load_file(filepath):
                    mentioned_count += 1
                    break
        except (TypeError, ValueError) as e:
            logger.warning(f"[Context] Error processing pattern '{pattern}': {e}")
            continue

    if mentioned_count > 0:
        logger.info(f"[Context] Loaded {mentioned_count} files mentioned in phase description")

    # Priority 2: Key config files
    load_priority_config_files(loader)

    # Priority 3: Source files from common directories
    load_source_directories(loader)

    # Log token budget usage
    result = loader.get_result()
    result.modified_files_loaded = modified_count
    result.mentioned_files_loaded = mentioned_count

    logger.info(
        f"[Context] Total: {result.files_loaded} files loaded for Builder context "
        f"(modified={modified_count}, mentioned={mentioned_count})"
    )
    logger.info(
        f"[TOKEN_BUDGET] Context loading: ~{result.tokens_estimated} tokens "
        f"({result.tokens_estimated * 100 // result.token_budget}% of {result.token_budget} budget)"
    )

    return result


def load_targeted_context_for_patterns(
    workspace: Path,
    patterns: List[str],
    exclude_dirs: Optional[Set[str]] = None,
    content_limit: int = DEFAULT_CONTENT_TRIM_LIMIT,
) -> Dict[str, str]:
    """Load files matching specific patterns.

    Args:
        workspace: Workspace path
        patterns: Glob patterns to match
        exclude_dirs: Directories to exclude (default: node_modules, __pycache__)
        content_limit: Maximum content length per file

    Returns:
        Dictionary of {path: content}
    """
    if exclude_dirs is None:
        exclude_dirs = {"node_modules", "__pycache__"}

    existing_files = {}

    for pattern in patterns:
        for filepath in workspace.glob(pattern):
            if not filepath.is_file():
                continue
            if any(excluded in str(filepath) for excluded in exclude_dirs):
                continue
            try:
                rel_path = str(filepath.relative_to(workspace)).replace("\\", "/")
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                existing_files[rel_path] = content[:content_limit]
            except Exception as e:
                logger.debug(f"Could not load {filepath}: {e}")

    return existing_files


def load_template_context(workspace: Path) -> Dict[str, str]:
    """Load minimal context for country template phases.

    Templates for UK, CA, AU typically create:
    - templates/countries/{country}/template.yaml
    - src/autopack/document_categories.py (or similar)

    Args:
        workspace: Workspace path

    Returns:
        Dictionary of {path: content} for template-related files
    """
    patterns = [
        "templates/**/*.yaml",
        "src/autopack/document_categories.py",
        "src/autopack/validation.py",
        "src/autopack/models.py",
        "config/**/*.yaml",
    ]

    existing_files = load_targeted_context_for_patterns(workspace, patterns)
    logger.info(f"[Context] Loaded {len(existing_files)} template-related files (targeted)")

    return existing_files


def load_frontend_context(workspace: Path) -> Dict[str, str]:
    """Load minimal context for frontend phases.

    Frontend phases only need:
    - frontend/ directory contents
    - package.json, vite.config.ts, tsconfig.json

    Args:
        workspace: Workspace path

    Returns:
        Dictionary of {path: content} for frontend files
    """
    patterns = [
        "frontend/**/*.ts",
        "frontend/**/*.tsx",
        "frontend/**/*.css",
        "frontend/**/*.json",
        "package.json",
        "vite.config.ts",
        "tsconfig.json",
        "tailwind.config.js",
    ]

    existing_files = load_targeted_context_for_patterns(
        workspace, patterns, exclude_dirs={"node_modules"}
    )
    logger.info(f"[Context] Loaded {len(existing_files)} frontend files (targeted)")

    return existing_files


def load_docker_context(workspace: Path) -> Dict[str, str]:
    """Load minimal context for Docker/deployment phases.

    Docker phases only need:
    - Dockerfile, docker-compose.yml, .dockerignore
    - Database initialization scripts
    - Configuration files

    Args:
        workspace: Workspace path

    Returns:
        Dictionary of {path: content} for docker/deployment files
    """
    patterns = [
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "scripts/init-db.sql",
        "scripts/**/*.sh",
        "config/**/*.yaml",
        "requirements.txt",
        "package.json",
    ]

    existing_files = load_targeted_context_for_patterns(workspace, patterns)
    logger.info(f"[Context] Loaded {len(existing_files)} docker/deployment files (targeted)")

    return existing_files


# Repo root bucket identifiers for workspace determination
REPO_ROOT_BUCKETS = frozenset({
    "src",
    "docs",
    "tests",
    "config",
    "scripts",
    "migrations",
    "archive",
    "examples",
})


# Allowed file extensions for scope loading
ALLOWED_SCOPE_EXTENSIONS = frozenset({
    ".py",
    ".pyi",
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".csv",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".css",
    ".scss",
})


# Directories to exclude from scope loading
SCOPE_DENYLIST_DIRS = frozenset({
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
})


def normalize_rel_path(path_str: str) -> str:
    """Normalize a relative path string.

    Replaces backslashes with forward slashes and removes leading ./

    Args:
        path_str: Path string to normalize

    Returns:
        Normalized path string
    """
    if not path_str:
        return path_str
    normalized = path_str.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_file_in_scope(
    file_path: str,
    scope_set: Set[str],
    scope_dir_prefixes: List[str],
) -> bool:
    """Check if a file path is within scope.

    Args:
        file_path: File path to check
        scope_set: Set of exact scope paths
        scope_dir_prefixes: List of directory prefixes that are in scope

    Returns:
        True if file is in scope
    """
    if file_path in scope_set:
        return True
    return any(file_path.startswith(prefix) for prefix in scope_dir_prefixes)
