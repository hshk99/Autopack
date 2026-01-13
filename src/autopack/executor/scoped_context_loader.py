"""Scoped context loading for phase execution.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles context loading with scope restrictions and token budget management.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class ScopedContextLoader:
    """Loads scoped context for phase execution.

    Responsibilities:
    1. Load files within scope
    2. Apply token budget constraints
    3. Handle retrieval injection
    4. Generate context strings
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def load_context(self, phase: Dict, scope_config: Dict) -> Dict:
        """Load context using scope configuration (GPT recommendation).

        BUILD-145 P1: Artifact-first context loading for token efficiency.
        For read_only_context, prefers loading run artifacts (.autonomous_runs/<run_id>/)
        over full file contents when available, reducing token usage.

        Args:
            phase: Phase specification
            scope_config: Scope configuration with paths and read_only_context

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        workspace_root = self._determine_workspace_root(scope_config).resolve()
        base_workspace = Path(self.executor.workspace).resolve()
        existing_files: Dict[str, str] = {}
        scope_metadata: Dict[str, Dict[str, Any]] = {}
        missing_files: List[str] = []

        # BUILD-145 P1: Initialize artifact loader for token-efficient context loading
        from autopack.artifact_loader import ArtifactLoader

        # Use executor's run_id (always available) instead of phase.get("run_id")
        artifact_loader = (
            ArtifactLoader(base_workspace, self.executor.run_id) if self.executor.run_id else None
        )
        total_tokens_saved = 0
        artifact_substitutions = 0

        def _normalize_rel_path(path_str: str) -> str:
            if not path_str:
                return path_str
            normalized = path_str.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            return normalized

        def _add_file(abs_path: Path, rel_key: str) -> None:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
                existing_files[rel_key] = content
            except Exception as exc:
                logger.warning(f"[Scope] Failed to read {abs_path}: {exc}")

        # Load modifiable scope paths
        for scoped_path in scope_config.get("paths", []):
            resolved = self._resolve_scope_target(scoped_path, workspace_root, must_exist=False)
            if not resolved:
                # Path doesn't exist yet - compute proper relative key using same logic as _resolve_scope_target
                # to prevent fileorganizer/fileorganizer/... duplicate paths
                path_obj = Path(scoped_path.strip())
                if path_obj.is_absolute():
                    try:
                        rel_key = str(path_obj.relative_to(base_workspace)).replace("\\", "/")
                    except ValueError:
                        # Absolute path outside workspace - skip
                        continue
                else:
                    # Try relative to workspace_root first, then base_workspace
                    candidate = workspace_root / path_obj
                    try:
                        rel_key = str(candidate.resolve().relative_to(base_workspace)).replace(
                            "\\", "/"
                        )
                    except ValueError:
                        # Fall back to treating as relative to base_workspace
                        rel_key = str(path_obj).replace("\\", "/")

                rel_key = _normalize_rel_path(rel_key)
                missing_files.append(rel_key)  # Store normalized rel_key, not scoped_path
                scope_metadata[rel_key] = {"category": "modifiable", "missing": True}
                existing_files.setdefault(rel_key, "")
                continue
            abs_path, rel_key = resolved
            rel_key = _normalize_rel_path(rel_key)
            scope_metadata[rel_key] = {"category": "modifiable", "missing": not abs_path.exists()}
            if not abs_path.exists():
                missing_files.append(scoped_path)
                existing_files.setdefault(rel_key, "")
                continue
            if abs_path.is_file():
                _add_file(abs_path, rel_key)
            elif abs_path.is_dir():
                # Load a bounded set of files from the directory to avoid empty context
                allowed_exts_mod = {
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
                }
                dir_limit = 200
                loaded_dir = 0
                for file_path in abs_path.rglob("*"):
                    if loaded_dir >= dir_limit:
                        logger.warning("[Scope] Modifiable dir limit reached (200 files).")
                        break
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in allowed_exts_mod:
                        continue
                    rel_sub = _normalize_rel_path(
                        str(file_path.relative_to(base_workspace)).replace("\\", "/")
                    )
                    _add_file(file_path, rel_sub)
                    loaded_dir += 1
            else:
                logger.warning(f"[Scope] Path is not a file: {abs_path}")

        # Load read-only context (limited set of extensions)
        allowed_exts = {
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
        }
        denylist_dirs = {".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
        max_readonly_files = 200
        readonly_count = 0

        for readonly_entry in scope_config.get("read_only_context", []):
            # BUILD-145: Normalize read_only_context entry to support both formats:
            # - Legacy: ["path/to/file.py", ...]
            # - New: [{"path": "path/to/file.py", "reason": "..."}, ...]
            if isinstance(readonly_entry, dict):
                readonly_path = readonly_entry.get("path")
                readonly_reason = readonly_entry.get("reason", "")
                if not readonly_path:
                    logger.warning(
                        f"[Scope] Skipping invalid read_only_context entry (missing 'path'): {readonly_entry}"
                    )
                    continue
                if readonly_reason:
                    logger.debug(
                        f"[Scope] Read-only context: {readonly_path} (reason: {readonly_reason})"
                    )
            elif isinstance(readonly_entry, str):
                readonly_path = readonly_entry
            else:
                logger.warning(
                    f"[Scope] Skipping invalid read_only_context entry (expected str or dict): {type(readonly_entry).__name__}"
                )
                continue

            resolved = self._resolve_scope_target(readonly_path, workspace_root, must_exist=False)
            if not resolved:
                continue
            abs_path, rel_key = resolved
            rel_key = _normalize_rel_path(rel_key)

            if abs_path.is_file():
                if rel_key not in existing_files:
                    # BUILD-145 P1: Try artifact-first loading for read-only context
                    if artifact_loader:
                        try:
                            full_content = abs_path.read_text(encoding="utf-8", errors="ignore")
                            content, tokens_saved, source_type = (
                                artifact_loader.load_with_artifacts(
                                    rel_key, full_content, prefer_artifacts=True
                                )
                            )
                            existing_files[rel_key] = content

                            if tokens_saved > 0:
                                total_tokens_saved += tokens_saved
                                artifact_substitutions += 1
                                scope_metadata.setdefault(rel_key, {})
                                scope_metadata[rel_key].update(
                                    {
                                        "category": "read_only",
                                        "missing": False,
                                        "source": source_type,
                                        "tokens_saved": tokens_saved,
                                    }
                                )
                            else:
                                scope_metadata.setdefault(
                                    rel_key, {"category": "read_only", "missing": False}
                                )
                        except Exception as exc:
                            logger.warning(
                                f"[Scope] Artifact loading failed for {rel_key}, using full file: {exc}"
                            )
                            _add_file(abs_path, rel_key)
                            scope_metadata.setdefault(
                                rel_key, {"category": "read_only", "missing": False}
                            )
                    else:
                        _add_file(abs_path, rel_key)
                        scope_metadata.setdefault(
                            rel_key, {"category": "read_only", "missing": False}
                        )
                else:
                    scope_metadata.setdefault(rel_key, {"category": "read_only", "missing": False})
                continue

            if not abs_path.is_dir():
                continue

            for file_path in abs_path.rglob("*"):
                if readonly_count >= max_readonly_files:
                    logger.warning("[Scope] Read-only context limit reached (200 files).")
                    break
                if not file_path.is_file():
                    continue
                if any(part in denylist_dirs for part in file_path.parts):
                    continue
                if file_path.suffix and file_path.suffix.lower() not in allowed_exts:
                    continue
                try:
                    rel_builder = str(file_path.resolve().relative_to(base_workspace)).replace(
                        "\\", "/"
                    )
                except ValueError:
                    continue
                if rel_builder in existing_files:
                    continue
                _add_file(file_path, rel_builder)
                scope_metadata.setdefault(rel_builder, {"category": "read_only", "missing": False})
                readonly_count += 1

        if missing_files:
            logger.warning(f"[Scope] Missing scope files: {missing_files}")
            # Auto-create empty stubs for common manifest/lockfiles to reduce churn and truncation
            for missing in list(missing_files):
                if missing.endswith(("package-lock.json", "yarn.lock")):
                    # missing is already a normalized relative path from base_workspace
                    missing_path = (base_workspace / missing).resolve()
                    missing_path.parent.mkdir(parents=True, exist_ok=True)
                    missing_path.write_text("{}", encoding="utf-8")
                    logger.info(f"[Scope] Created stub for missing file: {missing}")
                    _add_file(missing_path, missing.replace("\\", "/"))
                    scope_metadata.setdefault(
                        missing.replace("\\", "/"), {"category": "modifiable", "missing": False}
                    )
                    set(existing_files.keys())
                    if missing in missing_files:
                        missing_files.remove(missing)

        logger.info(f"[Scope] Loaded {len(existing_files)} files from scope configuration")
        logger.info(f"[Scope] Scope paths: {scope_config.get('paths', [])}")
        preview_paths = list(existing_files.keys())[:10]
        logger.info(f"[Scope] Loaded paths: {preview_paths}...")

        # BUILD-145 P1: Report artifact-first loading token savings
        if artifact_substitutions > 0:
            logger.info(
                f"[Scope] Artifact-first loading: {artifact_substitutions} files substituted, "
                f"~{total_tokens_saved:,} tokens saved"
            )

        # BUILD-145 P1.1: Apply context budgeting to loaded files
        from autopack.context_budgeter import select_files_for_context, reset_embedding_cache
        from autopack.config import settings

        # BUILD-145 P1 (hardening): Reset embedding cache per phase to enforce per-phase cap
        reset_embedding_cache()

        budget_selection = select_files_for_context(
            files=existing_files,
            scope_metadata=scope_metadata,
            deliverables=phase.get("deliverables", []),
            query=phase.get("description", ""),
            budget_tokens=settings.context_budget_tokens,
        )

        # Replace existing_files with budgeted selection
        existing_files = budget_selection.kept
        logger.info(
            f"[Context Budget] Mode: {budget_selection.mode}, "
            f"Used: {budget_selection.used_tokens_est}/{budget_selection.budget_tokens} tokens, "
            f"Files: {budget_selection.files_kept_count} kept, {budget_selection.files_omitted_count} omitted"
        )

        # BUILD-145 P1 (hardening): Recompute artifact stats for kept files only
        # Original artifact_stats were computed before budgeting, so some substituted files may have been omitted
        kept_artifact_substitutions = 0
        kept_tokens_saved = 0
        substituted_paths_sample = []
        kept_files = set(existing_files.keys())

        for path, metadata in scope_metadata.items():
            if path in kept_files and metadata.get("source", "").startswith("artifact:"):
                kept_artifact_substitutions += 1
                kept_tokens_saved += metadata.get("tokens_saved", 0)
                if len(substituted_paths_sample) < 10:
                    substituted_paths_sample.append(path)

        return {
            "existing_files": existing_files,
            "scope_metadata": scope_metadata,
            "missing_scope_files": missing_files,
            "artifact_stats": (
                {
                    "substitutions": kept_artifact_substitutions,
                    "tokens_saved": kept_tokens_saved,
                    "substituted_paths_sample": substituted_paths_sample,
                }
                if kept_artifact_substitutions > 0
                else None
            ),
            "budget_selection": budget_selection,  # Store for telemetry
        }

    def _determine_workspace_root(self, scope_config: Dict) -> Path:
        """Determine workspace root based on scope configuration.

        For external projects (project_build), derive workspace from first scope path.
        For autopack_maintenance, use Autopack root.

        Args:
            scope_config: Scope configuration dict

        Returns:
            Workspace root Path
        """
        # For autopack_maintenance, always use self.workspace (Autopack root)
        if self.executor.run_type in ["autopack_maintenance", "autopack_upgrade", "self_repair"]:
            return Path(self.executor.workspace)

        # For project_build, derive workspace from first scope path.
        # Scope paths can be either:
        # - ".autonomous_runs/<project>/(...)" (historical)
        # - "<project_slug>/(...)" e.g. "fileorganizer/frontend/..." (current external-project layout)
        scope_paths = scope_config.get("paths", [])
        if scope_paths:
            first_path = scope_paths[0]
            parts = Path(first_path).parts

            # Look for .autonomous_runs prefix
            if len(parts) >= 2 and parts[0] == ".autonomous_runs":
                project_root = Path(self.executor.workspace) / parts[0] / parts[1]
                logger.info(f"[Scope] Workspace root determined: {project_root}")
                return project_root

            # Autopack monorepo heuristic: if scope paths start with standard repo-top-level buckets,
            # the workspace root should be the repo root (NOT the bucket directory). This prevents
            # accidental scope isolation where writes to e.g. "src/*" are blocked because the derived
            # workspace is "docs/" or "tests/".
            repo_root_buckets = {
                "src",
                "docs",
                "tests",
                "config",
                "scripts",
                "migrations",
                "archive",
                "examples",
            }
            if parts and parts[0] in repo_root_buckets:
                repo_root = Path(self.executor.workspace).resolve()
                logger.info(
                    f"[Scope] Workspace root determined as repo root for bucket '{parts[0]}': {repo_root}"
                )
                return repo_root

            # Common external project layouts: "fileorganizer/<...>" or "file-organizer-app-v1/<...>"
            # If the first segment exists as a directory under repo root, treat it as workspace root.
            if parts:
                candidate = (Path(self.executor.workspace) / parts[0]).resolve()
                if candidate.exists() and candidate.is_dir():
                    logger.info(f"[Scope] Workspace root determined from scope prefix: {candidate}")
                    return candidate

        # Fallback to default workspace
        logger.warning(
            f"[Scope] Could not determine workspace from scope paths, using default: {self.executor.workspace}"
        )
        return Path(self.executor.workspace)

    def _resolve_scope_target(
        self, scope_path: str, workspace_root: Path, *, must_exist: bool = False
    ) -> Optional[Tuple[Path, str]]:
        """
        Resolve a scope path to an absolute file/dir and builder-relative path.

        Args:
            scope_path: Path from scope configuration (can be relative or prefixed with .autonomous_runs)
            workspace_root: Project workspace root (from _determine_workspace_root)
            must_exist: If True, only return when the path exists on disk

        Returns:
            Tuple of (absolute_path, builder_relative_path) or None if outside workspace.
        """
        base_workspace = Path(self.executor.workspace).resolve()
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
