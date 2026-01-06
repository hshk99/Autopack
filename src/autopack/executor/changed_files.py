"""Deterministic changed-files extraction (BUILD-187 Phase 6).

Extracts changed files from git diff in a deterministic, sorted manner.
Explicitly distinguishes between "empty" (no changes) and "unknown" (git unavailable).

Properties:
- Same repo state -> same output
- Sorted output for determinism
- Explicit None when git unavailable (not empty list)
- Evidence flags when extraction fails
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..file_layout import RunFileLayout

logger = logging.getLogger(__name__)

# Deterministic timestamp for reproducible artifacts
DETERMINISTIC_TIMESTAMP = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@dataclass
class ChangedFilesResult:
    """Result of changed files extraction.

    Attributes:
        files: Sorted list of changed files, or None if unknown
        status: "available", "empty", or "unknown"
        evidence_flag: Reason for unknown status (e.g., "git_unavailable", "git_error")
        error_message: Error details when status is "unknown"
    """

    files: Optional[List[str]] = None
    status: str = "unknown"  # "available", "empty", "unknown"
    evidence_flag: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "files": self.files,
            "status": self.status,
            "evidence_flag": self.evidence_flag,
            "error_message": self.error_message,
        }

    @property
    def is_known(self) -> bool:
        """Check if result is known (not unknown)."""
        return self.status != "unknown"

    @property
    def file_count(self) -> Optional[int]:
        """Get file count, or None if unknown."""
        if self.files is None:
            return None
        return len(self.files)


@dataclass
class ChangedFilesEvidence:
    """Evidence artifact for changed files extraction."""

    run_id: str
    phase_id: str
    timestamp: datetime = field(default_factory=lambda: DETERMINISTIC_TIMESTAMP)
    result: ChangedFilesResult = field(default_factory=ChangedFilesResult)
    git_available: bool = False
    workspace: str = ""
    diff_command: str = ""

    def to_dict(self) -> Dict:
        """Convert to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "timestamp": self.timestamp.isoformat(),
            "result": self.result.to_dict(),
            "git_available": self.git_available,
            "workspace": self.workspace,
            "diff_command": self.diff_command,
        }


def is_git_available(workspace: Path) -> bool:
    """Check if git is available in the workspace.

    Args:
        workspace: Workspace path

    Returns:
        True if git is available and workspace is a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def extract_changed_files(
    workspace: Path,
    base_ref: str = "HEAD",
    compare_ref: Optional[str] = None,
) -> ChangedFilesResult:
    """Extract changed files from git diff.

    Uses `git diff --name-only` with sorted output.

    Args:
        workspace: Workspace path
        base_ref: Base reference (default HEAD)
        compare_ref: Compare reference (default: working tree)

    Returns:
        ChangedFilesResult with deterministic output
    """
    # Check git availability first
    if not is_git_available(workspace):
        return ChangedFilesResult(
            files=None,
            status="unknown",
            evidence_flag="git_unavailable",
            error_message="Git is not available or workspace is not a git repository",
        )

    # Build diff command
    cmd = ["git", "diff", "--name-only"]
    if compare_ref:
        cmd.extend([base_ref, compare_ref])
    else:
        cmd.append(base_ref)

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return ChangedFilesResult(
                files=None,
                status="unknown",
                evidence_flag="git_error",
                error_message=f"git diff failed: {result.stderr.strip()[:200]}",
            )

        # Parse and sort output
        output = result.stdout.strip()
        if not output:
            # Empty output means no changes - this is known, not unknown
            return ChangedFilesResult(
                files=[],
                status="empty",
            )

        files = sorted(output.split("\n"))
        return ChangedFilesResult(
            files=files,
            status="available",
        )

    except subprocess.TimeoutExpired:
        return ChangedFilesResult(
            files=None,
            status="unknown",
            evidence_flag="git_timeout",
            error_message="git diff timed out after 30 seconds",
        )
    except Exception as e:
        return ChangedFilesResult(
            files=None,
            status="unknown",
            evidence_flag="git_exception",
            error_message=f"{type(e).__name__}: {str(e)[:200]}",
        )


def extract_changed_files_from_patch(patch_content: str) -> ChangedFilesResult:
    """Extract changed files from patch content.

    Parses diff headers to find file paths.

    Args:
        patch_content: Git diff/patch content

    Returns:
        ChangedFilesResult with deterministic output
    """
    if not patch_content or not patch_content.strip():
        return ChangedFilesResult(
            files=None,
            status="unknown",
            evidence_flag="empty_patch",
            error_message="Patch content is empty",
        )

    try:
        files = set()

        for line in patch_content.split("\n"):
            # Match diff header lines
            if line.startswith("diff --git "):
                # Format: diff --git a/path/to/file b/path/to/file
                parts = line.split()
                if len(parts) >= 4:
                    # Extract b/path (the destination path)
                    b_path = parts[3]
                    if b_path.startswith("b/"):
                        files.add(b_path[2:])  # Remove b/ prefix
            elif line.startswith("+++ "):
                # Format: +++ b/path/to/file or +++ /dev/null
                path = line[4:].strip()
                if path.startswith("b/"):
                    files.add(path[2:])
                elif path != "/dev/null":
                    files.add(path)

        if not files:
            return ChangedFilesResult(
                files=[],
                status="empty",
            )

        return ChangedFilesResult(
            files=sorted(files),
            status="available",
        )

    except Exception as e:
        return ChangedFilesResult(
            files=None,
            status="unknown",
            evidence_flag="parse_error",
            error_message=f"Failed to parse patch: {type(e).__name__}: {str(e)[:200]}",
        )


def write_changed_files_evidence(
    layout: "RunFileLayout",
    phase_id: str,
    result: ChangedFilesResult,
    workspace: Path,
    diff_command: str = "",
) -> Path:
    """Write changed files evidence artifact.

    Args:
        layout: RunFileLayout for artifact paths
        phase_id: Phase identifier
        result: ChangedFilesResult to record
        workspace: Workspace path used
        diff_command: Git diff command used

    Returns:
        Path to evidence artifact
    """
    evidence = ChangedFilesEvidence(
        run_id=layout.run_id,
        phase_id=phase_id,
        result=result,
        git_available=is_git_available(workspace),
        workspace=str(workspace),
        diff_command=diff_command,
    )

    # Ensure evidence directory exists
    evidence_dir = layout.base_dir / "evidence" / "changed_files"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Write evidence file
    safe_phase_id = phase_id.replace("/", "_").replace("\\", "_")
    artifact_path = evidence_dir / f"changed_files_{safe_phase_id}.json"
    artifact_path.write_text(
        json.dumps(evidence.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.debug(f"[ChangedFiles] Wrote evidence for {phase_id}: {result.status}")
    return artifact_path


def format_changed_files_for_display(result: ChangedFilesResult) -> str:
    """Format changed files result for human display.

    Args:
        result: ChangedFilesResult

    Returns:
        Human-readable string
    """
    if result.status == "unknown":
        return f"Changed files: unknown ({result.evidence_flag})"
    elif result.status == "empty":
        return "Changed files: none"
    else:
        count = len(result.files) if result.files else 0
        if count == 0:
            return "Changed files: none"
        elif count <= 5:
            return f"Changed files ({count}): {', '.join(result.files)}"
        else:
            preview = ", ".join(result.files[:3])
            return f"Changed files ({count}): {preview}, ... (+{count - 3} more)"
