#!/usr/bin/env python3
"""
CI contract: if security baselines changed => SECURITY_LOG must include a new SECBASE entry.

Policy:
  - If any files under `security/baselines/` changed in this branch/PR relative to the base branch,
    then `docs/SECURITY_LOG.md` MUST contain at least one new entry with heading:
      "## SECBASE-YYYYMMDD"
    compared to the base branch version of the file.

Rationale:
  - Baselines are "derived truth" and must be auditable.
  - The SECBASE entry captures the canonical workflow run + commit SHA + delta summary.

Exit codes:
  0 = pass (not a PR context, no baseline changes, or baseline changes + new SECBASE entry present)
  1 = fail (baseline changed but no new SECBASE entry)
  2 = runtime error (git missing, ref missing, unexpected exception)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Set

SECURITY_LOG_PATH = Path("docs/SECURITY_LOG.md")
BASELINES_DIR = Path("security/baselines")

SECBASE_RE = re.compile(r"^##\s+SECBASE-\d{8}\b", re.MULTILINE)
STUB_SECBASE_RE = re.compile(r"^##\s+SECBASE-TODO-", re.MULTILINE)
TODO_MARKER_RE = re.compile(r"\bTODO\b")


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _is_pr_context() -> bool:
    """
    Check if we're running in a GitHub Actions PR context.

    Returns True if both conditions are met:
      - GITHUB_EVENT_NAME == "pull_request"
      - GITHUB_BASE_REF is set (the base branch name)
    """
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    return event_name == "pull_request" and bool(base_ref)


def _get_base_ref() -> str:
    """
    Get the base ref for PR comparison.

    Returns the value of GITHUB_BASE_REF (e.g., "main").
    Raises RuntimeError if not set (should not happen if _is_pr_context() returned True).
    """
    base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
    if not base_ref:
        raise RuntimeError("GITHUB_BASE_REF is not set (expected in PR context)")
    return base_ref


def _ensure_base_ref_fetched(base_ref: str) -> str:
    """
    Ensure we have origin/<base_ref> available for comparison.

    Returns the fully-qualified remote ref: origin/<base_ref>
    Raises RuntimeError if the ref cannot be fetched/resolved.
    """
    remote_ref = f"origin/{base_ref}"

    # Check if we already have it
    result = _run(["git", "rev-parse", "--verify", "--quiet", remote_ref], check=False)
    if result.returncode == 0:
        return remote_ref

    # Try fetching it (shallow fetch is sufficient)
    try:
        _run(["git", "fetch", "origin", base_ref, "--depth=1"], check=True)
        _run(["git", "rev-parse", "--verify", "--quiet", remote_ref], check=True)
        return remote_ref
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Unable to resolve base ref for comparison: {remote_ref}\n"
            f"  This is a CI infrastructure error.\n"
            f"  Git stderr: {e.stderr}"
        ) from e


def _changed_files_against(remote_ref: str) -> list[str]:
    """
    Get list of changed files using triple-dot diff (changes on branch since merge-base).
    """
    res = _run(["git", "diff", "--name-only", f"{remote_ref}...HEAD"], check=True)
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def _extract_secbase_ids(text: str) -> Set[str]:
    """
    Extract SECBASE-YYYYMMDD IDs from markdown headings.

    Returns a set of IDs (e.g., {"SECBASE-20260105"}).
    """
    ids: Set[str] = set()
    for match in SECBASE_RE.finditer(text):
        # Extract the "SECBASE-YYYYMMDD" token
        tokens = match.group(0).strip().split()
        if len(tokens) >= 2:
            # Strip trailing punctuation (e.g., "SECBASE-20260105:" -> "SECBASE-20260105")
            secbase_id = tokens[1].rstrip(":,;.")
            ids.add(secbase_id)
    return ids


def _has_stub_secbase_entry(text: str) -> bool:
    """
    Check if SECURITY_LOG.md contains a stub SECBASE entry with TODO markers.

    Returns True if either:
    - A heading starts with "SECBASE-TODO-"
    - A SECBASE entry section contains "TODO" markers (indicating incomplete entry)
    """
    # Check for stub heading
    if STUB_SECBASE_RE.search(text):
        return True

    # Check for TODO markers in SECBASE sections
    # Extract sections starting with ## SECBASE- until next ## or end of file
    secbase_sections = re.split(r"(?=^##\s+SECBASE-)", text, flags=re.MULTILINE)
    for section in secbase_sections:
        if section.startswith("## SECBASE-") and TODO_MARKER_RE.search(section):
            return True

    return False


def _read_file_text(path: Path) -> str:
    """Read file from working tree."""
    return path.read_text(encoding="utf-8")


def _git_show_text(remote_ref: str, path: Path) -> str:
    """
    Read file content from a git ref.

    Returns empty string if the file didn't exist in that ref.
    """
    spec = f"{remote_ref}:{path.as_posix()}"
    try:
        res = _run(["git", "show", spec], check=True)
        return res.stdout
    except subprocess.CalledProcessError:
        # File didn't exist in base ref
        return ""


def main() -> int:
    # CI-only enforcement: skip if not in PR context
    if not _is_pr_context():
        print("Skipping SECBASE check (not a PR context)")
        return 0

    # Get base ref from environment
    try:
        base_ref = _get_base_ref()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Ensure we have the base ref fetched
    try:
        remote_ref = _ensure_base_ref_fetched(base_ref)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Get list of changed files
    try:
        changed_files = _changed_files_against(remote_ref)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to get changed files: {e}", file=sys.stderr)
        return 2

    # Check if any baseline files changed
    baselines_changed_list = [
        p for p in changed_files if Path(p).as_posix().startswith(BASELINES_DIR.as_posix() + "/")
    ]

    if not baselines_changed_list:
        print("OK: No security baseline changes detected.")
        return 0

    # Baselines changed - require SECBASE entry
    if not SECURITY_LOG_PATH.exists():
        print(
            f"ERROR: Baselines changed, but {SECURITY_LOG_PATH} is missing.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Detected baseline changes in:", file=sys.stderr)
        for p in sorted(baselines_changed_list):
            print(f"  - {p}", file=sys.stderr)
        return 1

    # Extract SECBASE IDs from HEAD and base
    head_log = _read_file_text(SECURITY_LOG_PATH)
    base_log = _git_show_text(remote_ref, SECURITY_LOG_PATH)

    head_ids = _extract_secbase_ids(head_log)
    base_ids = _extract_secbase_ids(base_log)

    new_ids = sorted(head_ids - base_ids)

    if not new_ids:
        print(
            "ERROR: Security baselines changed, but no new SECBASE entry was added.",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Required:", file=sys.stderr)
        print(
            "  - Add a new top-level heading like: '## SECBASE-YYYYMMDD: ...' to docs/SECURITY_LOG.md",
            file=sys.stderr,
        )
        print(
            "  - Include workflow run URL + commit SHA + delta summary (see template in docs/SECURITY_LOG.md)",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Detected baseline changes in:", file=sys.stderr)
        for p in sorted(baselines_changed_list):
            print(f"  - {p}", file=sys.stderr)
        return 1

    # Check for stub SECBASE entries (automated PR workflow safety)
    if _has_stub_secbase_entry(head_log):
        print(
            "ERROR: Security baselines changed, but SECBASE entry is incomplete (contains TODO markers).",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Required before merge:", file=sys.stderr)
        print("  - Complete the SECBASE entry in docs/SECURITY_LOG.md", file=sys.stderr)
        print("  - Replace all TODO markers with actual content:", file=sys.stderr)
        print("    - Add before/after finding counts", file=sys.stderr)
        print("    - Explain rationale for baseline changes", file=sys.stderr)
        print("    - Add security team reviewer name", file=sys.stderr)
        print("  - Ensure heading is 'SECBASE-YYYYMMDD' (not 'SECBASE-TODO-...')", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "This safety check prevents merging automated baseline refresh PRs without human review.",
            file=sys.stderr,
        )
        return 1

    print("OK: Security baselines changed and new SECBASE entry detected.")
    print(f"  - New SECBASE entries: {', '.join(new_ids)}")
    print(f"  - Baseline files changed: {len(baselines_changed_list)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: check_security_baseline_log_entry.py crashed: {e}", file=sys.stderr)
        raise SystemExit(2)
