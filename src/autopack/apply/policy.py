"""Patch policy configuration and path validation.

Extracted from governed_apply.py for PR-APPLY-2.

This module handles:
- Protected path definitions (paths that should never be modified)
- Allowed path definitions (paths that override protection)
- Path validation for workspace isolation
- Scope enforcement for patch paths
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


# Protected paths that Builder should never modify
# These are Autopack's own source/config directories
PROTECTED_PATHS = [
    "src/autopack/",  # Autopack core modules
    # CRITICAL: individual core modules that must remain protected even in internal mode
    # (internal mode removes the broad "src/autopack/" prefix)
    "src/autopack/config.py",
    "src/autopack/database.py",
    "src/autopack/models.py",
    "src/autopack/governed_apply.py",
    "src/autopack/autonomous_executor.py",
    "src/autopack/main.py",
    "src/autopack/quality_gate.py",
    "config/",  # Configuration files
    ".autonomous_runs/",  # Run state and logs
    ".git/",  # Git internals
]

# Paths that are always allowed (can override protection if needed)
ALLOWED_PATHS = [
    # Core maintenance paths that Autopack may update in self-repair runs
    "src/autopack/learned_rules.py",
    "src/autopack/llm_service.py",
    "src/autopack/openai_clients.py",
    "src/autopack/gemini_clients.py",
    "src/autopack/glm_clients.py",
    # Research system deliverables live under src/autopack/research/* and must be writable in project runs.
    "src/autopack/research/",
    # Research CLI is a required deliverable in Chunk 1A (and is safe to allow in project runs).
    "src/autopack/cli/",
    # Research integration deliverables (Chunk 4) are safe, narrow subtrees under src/autopack/.
    "src/autopack/integrations/",
    "src/autopack/phases/",
    "src/autopack/autonomous/",
    "src/autopack/workflow/",
    # Diagnostics parity deliverables (follow-ups): safe internal tooling, narrow subtree.
    "src/autopack/diagnostics/",
    # Dashboard integration for handoff/prompt generation (follow-up): narrow subtree.
    "src/autopack/dashboard/",
    # Research API router integration requires narrow update to main.py (followup-4).
    "src/autopack/main.py",
    "config/models.yaml",
    # BUILD-126: Large file handling modules (Phases E2-I)
    "src/autopack/import_graph.py",
    "src/autopack/scope_refiner.py",
    "src/autopack/risk_scorer.py",
    "src/autopack/context_summarizer.py",
    "src/autopack/quality_gate.py",
]

# Run types that support internal mode
MAINTENANCE_RUN_TYPES = ["autopack_maintenance", "autopack_upgrade", "self_repair"]


def is_path_protected(
    file_path: str,
    protected_paths: List[str],
    allowed_paths: List[str],
) -> bool:
    """
    Check if a file path is protected from modification.

    Args:
        file_path: Relative file path to check
        protected_paths: List of protected path prefixes
        allowed_paths: List of allowed path prefixes (override protection)

    Returns:
        True if path is protected, False otherwise
    """
    # Normalize path separators
    normalized_path = file_path.replace("\\", "/")

    # Check if path is explicitly allowed (overrides protection)
    for allowed in allowed_paths:
        if normalized_path.startswith(allowed.replace("\\", "/")):
            return False

    # Check if path matches any protected prefix
    for protected in protected_paths:
        if normalized_path.startswith(protected.replace("\\", "/")):
            return True

    return False


def normalize_relpath(path: object) -> str:
    """
    Normalize relative paths for scope comparison.

    Important for Windows drains where scope paths may come from `Path` stringification
    (backslashes) while patch paths are POSIX-style.

    Args:
        path: Path string or Path object

    Returns:
        Normalized relative path string
    """
    s = str(path or "").strip()
    s = s.replace("\\", "/")
    # Strip common leading prefixes
    while s.startswith("./"):
        s = s[2:]
    s = s.lstrip("/")  # keep relative
    # Collapse duplicate separators
    s = re.sub(r"/{2,}", "/", s)
    return s


def validate_patch_paths(
    files: List[str],
    protected_paths: List[str],
    allowed_paths: List[str],
    scope_paths: List[str] | None = None,
) -> Tuple[bool, List[str]]:
    """
    Validate that patch does not touch protected directories or violate scope.

    This is a critical workspace isolation check that prevents Builder
    from corrupting Autopack's own source code.

    Also enforces scope configuration if present (Option C - Layer 2).

    Args:
        files: List of file paths from the patch
        protected_paths: List of protected path prefixes
        allowed_paths: List of allowed path prefixes
        scope_paths: Optional list of allowed file paths (scope enforcement)

    Returns:
        Tuple of (is_valid, list of violations)
    """
    violations = []

    # Check 1: Protected paths
    for file_path in files:
        if is_path_protected(file_path, protected_paths, allowed_paths):
            violations.append(f"Protected path: {file_path}")
            logger.warning(
                f"[Isolation] BLOCKED: Patch attempts to modify protected path: {file_path}"
            )

    # Check 2: Scope enforcement (Option C Layer 2)
    if scope_paths:
        # Normalize scope paths for comparison, supporting directory prefixes
        normalized_scope = set()
        scope_prefixes: List[str] = []
        for path in scope_paths:
            raw = str(path or "")
            norm = normalize_relpath(raw)
            if not norm:
                continue
            is_prefix = raw.strip().endswith(("/", "\\"))
            if is_prefix:
                # Keep prefixes in canonical "dir/" form
                scope_prefixes.append(norm.rstrip("/") + "/")
            else:
                normalized_scope.add(norm.rstrip("/"))

        for file_path in files:
            normalized_file = normalize_relpath(file_path).rstrip("/")
            in_exact = normalized_file in normalized_scope
            in_prefix = any(normalized_file.startswith(prefix) for prefix in scope_prefixes)
            if not in_exact and not in_prefix:
                violations.append(f"Outside scope: {file_path}")
                logger.warning(
                    f"[Scope] BLOCKED: Patch attempts to modify file outside scope: {file_path}"
                )

        if len(violations) > len([v for v in violations if v.startswith("Protected")]):
            logger.error(
                f"[Scope] Patch rejected - {len([v for v in violations if v.startswith('Outside')])} files outside scope"
            )

    if violations:
        logger.error(
            f"[Isolation] Patch rejected - {len(violations)} violations (protected paths + scope)"
        )
        return False, violations

    return True, []


def get_effective_protected_paths(
    additional_protected: List[str] | None = None,
    autopack_internal_mode: bool = False,
) -> List[str]:
    """
    Get the effective list of protected paths based on mode.

    Args:
        additional_protected: Additional paths to protect
        autopack_internal_mode: If True, removes src/autopack/ from protection

    Returns:
        List of protected path prefixes
    """
    protected = list(PROTECTED_PATHS)

    if additional_protected:
        protected.extend(additional_protected)

    # In internal mode, unlock src/autopack/ but keep critical paths protected
    if autopack_internal_mode:
        logger.info(
            "[Isolation] autopack_internal_mode enabled - unlocking src/autopack/ for maintenance"
        )
        protected = [p for p in protected if p != "src/autopack/"]

    return protected


def get_effective_allowed_paths(additional_allowed: List[str] | None = None) -> List[str]:
    """
    Get the effective list of allowed paths.

    Args:
        additional_allowed: Additional paths to allow

    Returns:
        List of allowed path prefixes
    """
    allowed = list(ALLOWED_PATHS)

    if additional_allowed:
        for path in additional_allowed:
            normalized = path.replace("\\", "/")
            if not normalized:
                continue
            target = normalized
            if not target.endswith("/"):
                # Check if it has a file extension
                from pathlib import Path

                suffix = Path(target).suffix
                if not suffix:  # Treat as directory prefix
                    target += "/"
            allowed.append(target)

    return allowed


def extract_justification_from_patch(patch_content: str) -> str:
    """
    Extract Builder's justification from patch content (BUILD-127 Phase 2).

    Args:
        patch_content: Patch content to analyze

    Returns:
        Extracted justification string or generic message
    """
    justification_lines = []

    for line in patch_content.split("\n")[:50]:  # Check first 50 lines
        line = line.strip()

        # Diff comments (starting with '#')
        if line.startswith("# ") and len(line) > 3:
            justification_lines.append(line[2:].strip())

        # Git commit message format
        if line.startswith("Subject:") or line.startswith("Summary:"):
            justification_lines.append(line.split(":", 1)[1].strip())

    if justification_lines:
        return " ".join(justification_lines[:3])  # First 3 lines

    return "No justification provided in patch"
