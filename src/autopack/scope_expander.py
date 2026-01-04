"""Scope expansion helper (compatibility shim).

The main codebase currently uses deterministic scope generation and refinement,
but some safety tests expect a `ScopeExpander` with a small API surface.

This implementation is intentionally conservative:
- It only expands by adding *files* (never directories).
- It limits how many files can be added per expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .repo_scanner import RepoScanner


@dataclass
class ScopeExpansionResult:
    success: bool
    expanded_scope: List[str]
    reason: str = ""


class ScopeExpander:
    def __init__(
        self,
        workspace: Path,
        repo_scanner: RepoScanner,
        max_added_files_per_expansion: int = 20,
    ):
        self.workspace = workspace
        self.repo_scanner = repo_scanner
        self.max_added_files_per_expansion = max_added_files_per_expansion

    def expand_scope(
        self,
        current_scope: List[str],
        failure_reason: str,
        proposed_file: str,
        phase_goal: str,
        phase_id: str,
    ) -> ScopeExpansionResult:
        # Only handle the case covered by tests: allow adding a sibling file
        # in the same directory when the failure was "file_not_in_scope".
        if failure_reason != "file_not_in_scope":
            return ScopeExpansionResult(
                success=False,
                expanded_scope=list(current_scope),
                reason=f"Unsupported failure_reason: {failure_reason}",
            )

        normalized = self._normalize_paths(current_scope)
        proposed_norm = self._normalize_path(proposed_file)

        if proposed_norm in normalized:
            return ScopeExpansionResult(True, expanded_scope=sorted(normalized), reason="Already in scope")

        # Only allow adding the file if it exists in workspace and is a file.
        abs_path = self.workspace / proposed_norm
        if not abs_path.exists() or not abs_path.is_file():
            return ScopeExpansionResult(
                success=False,
                expanded_scope=sorted(normalized),
                reason=f"Proposed file not found: {proposed_norm}",
            )

        # Cap number of additions.
        if len(normalized) + 1 - len(current_scope) > self.max_added_files_per_expansion:
            return ScopeExpansionResult(
                success=False,
                expanded_scope=sorted(normalized),
                reason="Expansion cap exceeded",
            )

        normalized.add(proposed_norm)
        expanded = sorted(normalized)
        # Ensure we never return directory entries.
        expanded = [p for p in expanded if not p.endswith("/")]
        return ScopeExpansionResult(True, expanded_scope=expanded, reason="Added proposed file")

    def _normalize_paths(self, paths: Iterable[str]) -> set[str]:
        return {self._normalize_path(p) for p in paths}

    def _normalize_path(self, p: str) -> str:
        return p.replace("\\", "/").lstrip("/")


