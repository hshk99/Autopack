"""Scope context validator for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-13.
Validates that loaded file context matches scope configuration.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class ScopeContextValidator:
    """Validates file context against scope configuration (Layer 1 validation).

    This is the first validation layer (pre-Builder).
    Second layer is in GovernedApplyPath (patch application).

    Responsibilities:
    1. Normalize scope paths to consistent format
    2. Check loaded files against scope configuration
    3. Allow read-only context files
    4. Raise errors for files outside scope
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def validate(self, phase: Dict, file_context: Dict, scope_config: Dict):
        """Validate that loaded context matches scope configuration (Option C - Layer 1).

        This is the first validation layer (pre-Builder).
        Second layer is in GovernedApplyPath (patch application).

        Args:
            phase: Phase specification
            file_context: Loaded file context from _load_repository_context
            scope_config: Scope configuration dict

        Raises:
            RuntimeError: If validation fails
        """
        phase.get("phase_id")
        scope_paths = scope_config.get("paths", [])
        loaded_files = set(file_context.get("existing_files", {}).keys())

        workspace_root = self.executor._determine_workspace_root(scope_config)
        normalized_scope: List[str] = []
        scope_dir_prefixes: List[str] = []
        for path_str in scope_paths:
            resolved = self.executor._resolve_scope_target(
                path_str, workspace_root, must_exist=False
            )
            if resolved:
                abs_path, rel_key = resolved
                normalized_scope.append(rel_key)
                # If scope entry is a directory, treat all children as in-scope
                if abs_path.exists() and abs_path.is_dir():
                    prefix = rel_key if rel_key.endswith("/") else f"{rel_key}/"
                    scope_dir_prefixes.append(prefix)
            else:
                norm = path_str.replace("\\", "/")
                normalized_scope.append(norm)
                if norm.endswith("/"):
                    scope_dir_prefixes.append(norm)

        # Check for files outside scope (indicating scope loading bug)
        scope_set = set(normalized_scope)

        def _is_in_scope(file_path: str) -> bool:
            if file_path in scope_set:
                return True
            # Allow directory scope entries as prefixes
            if any(file_path.startswith(prefix) for prefix in scope_dir_prefixes):
                return True
            return False

        outside_scope = {f for f in loaded_files if not _is_in_scope(f)}

        if outside_scope:
            readonly_context = scope_config.get("read_only_context", [])
            readonly_exact: set[str] = set()
            readonly_prefixes: List[str] = []

            for entry in readonly_context:
                # BUILD-145 P0: Handle both dict and legacy string format
                if isinstance(entry, dict):
                    path_str = entry.get("path", "")
                else:
                    path_str = entry

                if not path_str:
                    continue

                resolved = self.executor._resolve_scope_target(
                    path_str, workspace_root, must_exist=False
                )
                if resolved:
                    _, rel_key = resolved
                    if rel_key.endswith("/"):
                        readonly_prefixes.append(rel_key)
                    elif Path(rel_key).suffix:
                        readonly_exact.add(rel_key)
                    else:
                        readonly_prefixes.append(rel_key + "/")
                else:
                    normalized = path_str.replace("\\", "/")
                    if normalized.endswith("/"):
                        readonly_prefixes.append(normalized)
                    else:
                        readonly_exact.add(normalized)

            def _is_readonly_allowed(file_path: str) -> bool:
                if file_path in readonly_exact:
                    return True
                for prefix in readonly_prefixes:
                    if file_path.startswith(prefix):
                        return True
                return False

            truly_outside = {path for path in outside_scope if not _is_readonly_allowed(path)}

            if truly_outside:
                error_msg = (
                    f"[Scope] VALIDATION FAILED: {len(truly_outside)} files loaded outside scope:\n"
                    f"  Scope paths: {normalized_scope}\n"
                    f"  Read-only context prefixes: {readonly_prefixes or readonly_exact}\n"
                    f"  Files outside scope: {list(truly_outside)[:10]}"
                )
                logger.error(error_msg)
                raise RuntimeError("Scope validation failed: loaded files outside scope.paths")

        logger.info(
            f"[Scope] Validation passed: {len(loaded_files)} files match scope configuration"
        )
