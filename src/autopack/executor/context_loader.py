"""Context loading utilities for AutonomousExecutor.

Extracted from autonomous_executor.py as part of IMP-MAINT-006.
Handles workspace root determination, scope path resolution, and targeted context loading.

This module provides:
- Workspace root determination based on scope configuration
- Scope path resolution to absolute and builder-relative paths
- Allowed paths derivation from scope configuration
- Targeted context loading for templates, frontend, and docker phases
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class ExecutorContextLoader:
    """Loads and manages context for phase execution.

    Centralizes workspace resolution and targeted context loading that
    enables efficient context selection based on phase characteristics.

    This class handles:
    - Determining the appropriate workspace root for scope-based execution
    - Resolving scope paths to filesystem locations
    - Deriving allowed paths for governed file access
    - Loading targeted context for specific phase types (templates, frontend, docker)
    """

    # Standard repo-level bucket directories that indicate we should use repo root
    REPO_ROOT_BUCKETS = {
        "src",
        "docs",
        "tests",
        "config",
        "scripts",
        "migrations",
        "archive",
        "examples",
    }

    def __init__(
        self,
        workspace: Path,
        run_type: str = "project_build",
    ):
        """Initialize context loader.

        Args:
            workspace: Base workspace directory
            run_type: Run type - 'project_build', 'autopack_maintenance',
                     'autopack_upgrade', or 'self_repair'
        """
        self.workspace = Path(workspace)
        self.run_type = run_type

    def determine_workspace_root(self, scope_config: Dict) -> Path:
        """Determine workspace root based on scope configuration.

        For external projects (project_build), derive workspace from first scope path.
        For autopack_maintenance, use Autopack root.

        Args:
            scope_config: Scope configuration dict

        Returns:
            Workspace root Path
        """
        # For autopack_maintenance, always use workspace (Autopack root)
        if self.run_type in ["autopack_maintenance", "autopack_upgrade", "self_repair"]:
            return self.workspace

        # For project_build, derive workspace from first scope path.
        # Scope paths can be either:
        # - ".autonomous_runs/<project>/(...)" (historical)
        # - "<project_slug>/(...)" e.g. "fileorganizer/frontend/..." (current layout)
        scope_paths = scope_config.get("paths", [])
        if scope_paths:
            first_path = scope_paths[0]
            parts = Path(first_path).parts

            # Look for .autonomous_runs prefix
            if len(parts) >= 2 and parts[0] == ".autonomous_runs":
                project_root = self.workspace / parts[0] / parts[1]
                logger.info(f"[Scope] Workspace root determined: {project_root}")
                return project_root

            # Autopack monorepo heuristic: if scope paths start with standard repo-level
            # buckets, the workspace root should be the repo root (NOT the bucket directory).
            # This prevents accidental scope isolation where writes to e.g. "src/*" are blocked
            # because the derived workspace is "docs/" or "tests/".
            if parts and parts[0] in self.REPO_ROOT_BUCKETS:
                repo_root = self.workspace.resolve()
                logger.info(
                    f"[Scope] Workspace root determined as repo root for bucket '{parts[0]}': {repo_root}"
                )
                return repo_root

            # Common external project layouts: "fileorganizer/<...>" or "file-organizer-app-v1/<...>"
            # If the first segment exists as a directory under repo root, treat it as workspace root.
            if parts:
                candidate = (self.workspace / parts[0]).resolve()
                if candidate.exists() and candidate.is_dir():
                    logger.info(f"[Scope] Workspace root determined from scope prefix: {candidate}")
                    return candidate

        # Fallback to default workspace
        logger.warning(
            f"[Scope] Could not determine workspace from scope paths, using default: {self.workspace}"
        )
        return self.workspace

    def resolve_scope_target(
        self, scope_path: str, workspace_root: Path, *, must_exist: bool = False
    ) -> Optional[Tuple[Path, str]]:
        """Resolve a scope path to an absolute file/dir and builder-relative path.

        Args:
            scope_path: Path from scope configuration (relative or .autonomous_runs prefixed)
            workspace_root: Project workspace root (from determine_workspace_root)
            must_exist: If True, only return when the path exists on disk

        Returns:
            Tuple of (absolute_path, builder_relative_path) or None if outside workspace.
        """
        base_workspace = self.workspace.resolve()
        workspace_root = workspace_root.resolve()
        path_obj = Path(scope_path.strip())

        candidates = []
        if path_obj.is_absolute():
            candidates.append(path_obj)
        else:
            candidates.append(base_workspace / path_obj)
            candidates.append(workspace_root / path_obj)

        seen = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)

            # Ensure target is under workspace root
            try:
                resolved.relative_to(workspace_root)
            except ValueError:
                continue

            if must_exist and not resolved.exists():
                continue

            try:
                rel_to_base = resolved.relative_to(base_workspace)
            except ValueError:
                continue

            rel_key = str(rel_to_base).replace("\\", "/")
            return resolved, rel_key

        return None

    def derive_allowed_paths_from_scope(
        self, scope_config: Optional[Dict], workspace_root: Optional[Path] = None
    ) -> List[str]:
        """Derive allowed path prefixes for GovernedApply from scope configuration.

        Args:
            scope_config: Scope configuration dict (may be None)
            workspace_root: Optional workspace root (computed if not provided)

        Returns:
            List of allowed path prefixes (may be empty)
        """
        if not scope_config or not scope_config.get("paths"):
            return []

        workspace_root = workspace_root or self.determine_workspace_root(scope_config)
        base_workspace = self.workspace.resolve()

        try:
            rel_prefix = workspace_root.resolve().relative_to(base_workspace)
        except ValueError:
            return []

        rel_str = str(rel_prefix).replace("\\", "/")
        if not rel_str.endswith("/"):
            rel_str += "/"

        return [rel_str]

    def load_targeted_context_for_templates(self, workspace: Path) -> Dict:
        """Load minimal context for country template phases (UK, CA, AU).

        These phases typically create:
        - templates/countries/{country}/template.yaml
        - src/autopack/document_categories.py (or similar)

        We only need to load template-related files, not the entire codebase.

        Args:
            workspace: Workspace directory to load from

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        existing_files = {}

        # Load only template-related files
        patterns = [
            "templates/**/*.yaml",
            "src/autopack/document_categories.py",
            "src/autopack/validation.py",
            "src/autopack/models.py",
            "config/**/*.yaml",
        ]

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file() and "__pycache__" not in str(filepath):
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} template-related files (targeted)")
        return {"existing_files": existing_files}

    def load_targeted_context_for_frontend(self, workspace: Path) -> Dict:
        """Load minimal context for frontend phases.

        Frontend phases only need:
        - frontend/ directory contents
        - package.json, vite.config.ts, tsconfig.json

        Args:
            workspace: Workspace directory to load from

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        existing_files = {}

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

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file() and "node_modules" not in str(filepath):
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} frontend files (targeted)")
        return {"existing_files": existing_files}

    def load_targeted_context_for_docker(self, workspace: Path) -> Dict:
        """Load minimal context for Docker/deployment phases.

        Docker phases only need:
        - Dockerfile, docker-compose.yml, .dockerignore
        - Database initialization scripts
        - Configuration files

        Args:
            workspace: Workspace directory to load from

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        existing_files = {}

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

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file():
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} docker/deployment files (targeted)")
        return {"existing_files": existing_files}


# Convenience functions for backward compatibility with executor methods


def determine_workspace_root(executor: "AutonomousExecutor", scope_config: Dict) -> Path:
    """Determine workspace root based on scope configuration.

    Wrapper for backward compatibility with existing executor code.
    """
    loader = ExecutorContextLoader(
        workspace=Path(executor.workspace),
        run_type=executor.run_type,
    )
    return loader.determine_workspace_root(scope_config)


def resolve_scope_target(
    executor: "AutonomousExecutor",
    scope_path: str,
    workspace_root: Path,
    *,
    must_exist: bool = False,
) -> Optional[Tuple[Path, str]]:
    """Resolve a scope path to an absolute file/dir and builder-relative path.

    Wrapper for backward compatibility with existing executor code.
    """
    loader = ExecutorContextLoader(
        workspace=Path(executor.workspace),
        run_type=executor.run_type,
    )
    return loader.resolve_scope_target(scope_path, workspace_root, must_exist=must_exist)


def derive_allowed_paths_from_scope(
    executor: "AutonomousExecutor",
    scope_config: Optional[Dict],
    workspace_root: Optional[Path] = None,
) -> List[str]:
    """Derive allowed path prefixes for GovernedApply from scope configuration.

    Wrapper for backward compatibility with existing executor code.
    """
    loader = ExecutorContextLoader(
        workspace=Path(executor.workspace),
        run_type=executor.run_type,
    )
    return loader.derive_allowed_paths_from_scope(scope_config, workspace_root)
