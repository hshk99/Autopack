"""Deliverables Validator - Ensures patches create expected files

This module validates that Builder-generated patches actually create/modify
the files specified in the phase scope's deliverables configuration.

Key features:
- Extracts file paths from patch content (both diff and JSON formats)
- Compares against expected deliverables from phase scope
- Provides detailed feedback for Builder self-correction
- Identifies missing, misplaced, or extra files
"""

import logging
import json
import re
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

logger = logging.getLogger(__name__)

def sanitize_deliverable_path(raw: str) -> str:
    """
    Normalize deliverable strings that include human annotations.

    Some requirements YAMLs include deliverables like:
      - "tests/autopack/integration/test_research_end_to_end.py (10+ integration tests)"
      - "tests/research/unit/ (100+ unit tests across all modules)"
      - "requirements.txt updated with pytest-json-report"
      - "src/autopack/models.py modifications (baseline capture)"
      - "Documentation in docs/BUILD-127_PHASE1_COMPLETION.md"
    These are not literal file paths and will cause deliverables validation and manifest gating
    to fail deterministically.

    Policy:
    - Strip any trailing parenthetical annotation: "path (comment...)" -> "path"
    - Strip " with " annotations: "path [verb] with description" -> "path"
    - Strip action verbs like " updated", " modifications", etc.
    - Strip " in " prefix: "Documentation in path" -> "path"
    - Trim whitespace.
    """
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""

    # BUILD-128: Handle "Documentation in docs/..." format
    if s.startswith("Documentation in "):
        s = s[len("Documentation in "):].strip()

    # BUILD-128: Remove " with " annotations like "requirements.txt updated with pytest-json-report"
    # First split on " with " to remove the description part
    if " with " in s:
        s = s.split(" with ", 1)[0].rstrip()

    # Remove trailing inline annotation like " (10+ integration tests)"
    if " (" in s:
        s = s.split(" (", 1)[0].rstrip()

    # BUILD-128: Remove common action verbs that describe changes rather than paths
    # e.g., "requirements.txt updated" -> "requirements.txt"
    # e.g., "src/autopack/models.py modifications" -> "src/autopack/models.py"
    action_verbs = [" updated", " modifications", " modified", " changes", " additions"]
    for verb in action_verbs:
        if s.endswith(verb):
            s = s[:-len(verb)].rstrip()
            break

    return s

def _extract_new_file_contents_from_unified_diff(patch_content: str) -> Dict[str, str]:
    """
    Best-effort extraction of NEW FILE contents from a unified diff (git apply style).

    We only support `new file mode` blocks because reconstructing modified files from diffs
    requires applying hunks. This is sufficient for validating JSON deliverables like
    `gold_set.json` which are typically created new in Chunk 0.
    """
    contents: Dict[str, List[str]] = {}
    current_path: Optional[str] = None
    in_new_file_block = False

    for raw_line in patch_content.splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("diff --git "):
            # Reset block state; path will be discovered via +++ b/...
            current_path = None
            in_new_file_block = False
            continue

        if line.startswith("new file mode"):
            in_new_file_block = True
            continue

        if line.startswith("+++ b/"):
            current_path = line[len("+++ b/"):].strip()
            if current_path and in_new_file_block:
                contents.setdefault(current_path, [])
            continue

        # Content lines for a new file are expressed as '+' additions.
        if in_new_file_block and current_path:
            if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                contents[current_path].append(line[1:])
            # ignore context/removed lines for new files

    return {p: "\n".join(lines).rstrip() + ("\n" if lines else "") for p, lines in contents.items()}


def validate_new_json_deliverables_in_patch(
    patch_content: str,
    expected_paths: List[str],
    workspace: Optional[Path] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate that NEW .json deliverables created by the patch are non-empty and valid JSON.

    Returns (ok, errors, details).
    """
    errors: List[str] = []
    details: Dict[str, Any] = {"invalid_json_files": []}

    expected_json = {
        normalize_path(p, workspace)
        for p in expected_paths
        if isinstance(p, str) and p.strip().lower().endswith(".json")
    }
    if not expected_json:
        return True, [], details

    # Handle JSON-format patch_content (structured mode) if present
    try:
        data = json.loads(patch_content)
        if isinstance(data, dict) and "files" in data:
            for f in data.get("files", []):
                path = normalize_path(str(f.get("path", "")).strip(), workspace)
                if path in expected_json and (f.get("mode") in ("create", "replace", "modify")):
                    new_content = f.get("new_content") or ""
                    if not str(new_content).strip():
                        details["invalid_json_files"].append({"path": path, "reason": "empty"})
                        errors.append(f"Invalid JSON deliverable (empty): {path}")
                    else:
                        try:
                            json.loads(str(new_content))
                        except Exception as e:
                            details["invalid_json_files"].append({"path": path, "reason": f"invalid_json: {str(e)[:120]}"})
                            errors.append(f"Invalid JSON deliverable ({str(e)[:120]}): {path}")
            return (len(errors) == 0), errors, details
    except Exception:
        pass

    # Diff format: only validate new-file JSON by extracting its full content from the diff
    new_file_contents = _extract_new_file_contents_from_unified_diff(patch_content)
    for path in sorted(expected_json):
        if path not in new_file_contents:
            continue
        content = new_file_contents[path]
        if not content.strip():
            details["invalid_json_files"].append({"path": path, "reason": "empty"})
            errors.append(f"Invalid JSON deliverable (empty): {path}")
            continue
        try:
            json.loads(content)
        except Exception as e:
            details["invalid_json_files"].append({"path": path, "reason": f"invalid_json: {str(e)[:120]}"})
            errors.append(f"Invalid JSON deliverable ({str(e)[:120]}): {path}")

    return (len(errors) == 0), errors, details


def repair_empty_required_json_deliverables_in_patch(
    patch_content: str,
    expected_paths: List[str],
    workspace: Optional[Path] = None,
    *,
    minimal_json: str = "[]\n",
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Best-effort repair: if a required JSON deliverable is present in the patch but empty/invalid,
    rewrite it to a minimal valid JSON placeholder (default: []\\n).

    This is intentionally conservative: we only repair JSON deliverable paths that are explicitly
    required by the phase scope and that appear to be created by this patch.

    Returns:
      (repaired, new_patch_content, repairs)
    """
    repairs: List[Dict[str, Any]] = []

    expected_json = {
        normalize_path(p, workspace)
        for p in expected_paths
        if isinstance(p, str) and p.strip().lower().endswith(".json")
    }
    if not expected_json:
        return False, patch_content, repairs

    # JSON-format patch (structured mode)
    try:
        data = json.loads(patch_content)
        if isinstance(data, dict) and "files" in data and isinstance(data.get("files"), list):
            changed = False
            for f in data["files"]:
                path = normalize_path(str(f.get("path", "")).strip(), workspace)
                if path not in expected_json:
                    continue
                mode = f.get("mode")
                if mode not in ("create", "replace", "modify"):
                    continue
                new_content = f.get("new_content")
                # Repair empty / invalid JSON
                needs_repair = False
                if not str(new_content or "").strip():
                    needs_repair = True
                    reason = "empty"
                else:
                    try:
                        json.loads(str(new_content))
                        reason = ""
                    except Exception as e:
                        needs_repair = True
                        reason = f"invalid_json: {str(e)[:120]}"
                if needs_repair:
                    f["new_content"] = minimal_json
                    changed = True
                    repairs.append({"path": path, "reason": reason, "applied": minimal_json.strip()})

            if changed:
                return True, json.dumps(data, indent=2), repairs
    except Exception:
        pass

    # Diff-format patch: patch up new-file JSON blocks by injecting a +[] line if content is empty/invalid.
    lines = patch_content.splitlines()
    out: List[str] = []

    current_path: Optional[str] = None
    in_block = False
    in_new_file = False
    saw_content_plus = False
    block_lines: List[str] = []

    def _flush_block():
        nonlocal block_lines, current_path, in_new_file, saw_content_plus
        if current_path and in_new_file and normalize_path(current_path, workspace) in expected_json:
            # Determine if the new file content is empty/invalid JSON by collecting '+' lines (excluding headers)
            content_lines: List[str] = []
            for bl in block_lines:
                if bl.startswith("+++ ") or bl.startswith("--- ") or bl.startswith("diff --git "):
                    continue
                if bl.startswith("+") and not bl.startswith("+++"):
                    content_lines.append(bl[1:])
            content = "\n".join(content_lines).strip()
            needs_repair = False
            reason = ""
            if not content:
                needs_repair = True
                reason = "empty"
            else:
                try:
                    json.loads(content)
                except Exception as e:
                    needs_repair = True
                    reason = f"invalid_json: {str(e)[:120]}"
            if needs_repair:
                injected = False
                saw_hunk = any(bl.startswith("@@") for bl in block_lines)
                new_block: List[str] = []
                for bl in block_lines:
                    new_block.append(bl)
                    if not injected and bl.startswith("@@"):
                        # Inject immediately after first hunk header
                        new_block.append("+" + minimal_json.rstrip("\n"))
                        injected = True
                if not injected and not saw_hunk:
                    # No hunks at all: we must create a minimal hunk, otherwise '+' lines are invalid in unified diff.
                    final_block: List[str] = []
                    inserted = False
                    for bl in new_block:
                        final_block.append(bl)
                        if (not inserted) and bl.startswith("+++ b/"):
                            final_block.append("@@ -0,0 +1 @@")
                            final_block.append("+" + minimal_json.rstrip("\n"))
                            inserted = True
                    new_block = final_block
                elif not injected:
                    # Fallback: hunks exist but we didn't see them for some reason; inject after +++ as last resort.
                    final_block = []
                    inserted = False
                    for bl in new_block:
                        final_block.append(bl)
                        if (not inserted) and bl.startswith("+++ b/"):
                            final_block.append("+" + minimal_json.rstrip("\n"))
                            inserted = True
                    new_block = final_block
                repairs.append(
                    {"path": normalize_path(current_path, workspace), "reason": reason, "applied": minimal_json.strip()}
                )
                block_lines = new_block
        out.extend(block_lines)
        block_lines = []
        current_path = None
        in_new_file = False
        saw_content_plus = False

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            if in_block:
                _flush_block()
            in_block = True
            block_lines = [line]
            current_path = None
            in_new_file = False
            saw_content_plus = False
            i += 1
            continue

        if not in_block:
            out.append(line)
            i += 1
            continue

        # Inside a diff block
        if line.startswith("new file mode") or line.startswith("--- /dev/null"):
            in_new_file = True
        if line.startswith("+++ b/"):
            current_path = line[len("+++ b/"):].strip()

        if line.startswith("+") and not line.startswith("+++"):
            saw_content_plus = True

        block_lines.append(line)
        i += 1

    if in_block:
        _flush_block()

    repaired = len(repairs) > 0
    return repaired, "\n".join(out) + ("\n" if patch_content.endswith("\n") else ""), repairs


def extract_paths_from_patch(patch_content: str) -> Set[str]:
    """Extract all file paths mentioned in a patch

    Handles both formats:
    - Git diff format: +++ b/path/to/file.py
    - JSON format: {"files": [{"path": "path/to/file.py", ...}]}

    Args:
        patch_content: Patch content (diff or JSON)

    Returns:
        Set of normalized file paths
    """
    paths = set()

    # Try JSON format first
    try:
        data = json.loads(patch_content)
        if isinstance(data, dict) and "files" in data:
            for file_entry in data.get("files", []):
                if "path" in file_entry:
                    paths.add(file_entry["path"].strip())
            return paths
    except (json.JSONDecodeError, KeyError):
        pass  # Not JSON, try diff format

    # Parse diff format
    # Look for: +++ b/path/to/file.py or diff --git a/path b/path
    diff_patterns = [
        r'\+\+\+ b/(.+?)(?:\s|$)',  # +++ b/path/to/file.py
        r'diff --git a/.+ b/(.+?)(?:\s|$)',  # diff --git a/old b/new
        r'--- /dev/null\s+\+\+\+ b/(.+?)(?:\s|$)',  # New file
    ]

    for pattern in diff_patterns:
        matches = re.findall(pattern, patch_content, re.MULTILINE)
        paths.update(m.strip() for m in matches)

    return paths


def normalize_path(path: str, workspace: Optional[Path] = None) -> str:
    """Normalize a file path for comparison

    Args:
        path: File path (may be relative or absolute)
        workspace: Optional workspace root for relative resolution

    Returns:
        Normalized path string (forward slashes, relative to workspace)
    """
    # Convert backslashes to forward slashes
    path = path.replace("\\", "/")

    # Collapse accidental double slashes (e.g. "docs//", "code//tests").
    while "//" in path:
        path = path.replace("//", "/")

    # Remove leading ./
    if path.startswith("./"):
        path = path[2:]

    # If workspace provided and path is absolute, make it relative
    if workspace:
        path_obj = Path(path)
        if path_obj.is_absolute():
            try:
                relative = path_obj.relative_to(workspace)
                path = str(relative).replace("\\", "/")
            except ValueError:
                pass  # Not relative to workspace, keep as-is

    return path


def extract_deliverables_from_scope(scope: Dict[str, Any]) -> List[str]:
    """Extract expected deliverable paths from phase scope

    Args:
        scope: Phase scope configuration (from YAML)

    Returns:
        List of expected file paths
    """
    deliverables = []

    if not scope:
        return deliverables

    # Format 1: scope["deliverables"]["code"] + scope["deliverables"]["tests"] + scope["deliverables"]["docs"]
    if "deliverables" in scope:
        d = scope["deliverables"]
        if isinstance(d, dict):
            for category in ["code", "tests", "docs", "config", "scripts"]:
                if category in d:
                    items = d[category]
                    if isinstance(items, list):
                        deliverables.extend([sanitize_deliverable_path(p) for p in items])
                    elif isinstance(items, str):
                        deliverables.append(sanitize_deliverable_path(items))

    # Format 2: scope["paths"] (legacy format)
    # IMPORTANT: In newer runs, `scope["paths"]` often represents *context roots* (e.g. ["code", "tests", "docs"])
    # rather than literal deliverables. Treat only "file-like" entries as deliverables and ignore bare bucket roots.
    if "paths" in scope and isinstance(scope["paths"], list):
        bucket_roots = {"docs", "tests", "code", "polish"}
        for p in scope["paths"]:
            sp = sanitize_deliverable_path(p)
            if not isinstance(sp, str):
                continue
            sp_norm = sp.replace("\\", "/").strip()
            sp_base = sp_norm.rstrip("/")
            # Ignore bare bucket roots like "docs", "tests", "code", "polish"
            if sp_base in bucket_roots and "/" not in sp_base and "." not in sp_base:
                continue
            deliverables.append(sp_norm)

    # Normalize common top-level directory markers to prefixes.
    # Many phase specs include deliverables like "docs", "tests", "polish", "code" as *root buckets*.
    # These are not literal files and will never appear in diffs; treat them as directory prefixes (e.g. "docs/").
    normalized: List[str] = []
    for p in deliverables:
        if not isinstance(p, str):
            continue
        p = p.strip()
        if not p:
            continue
        if p in {"docs", "tests", "polish", "code"}:
            p = p.rstrip("/") + "/"
        normalized.append(p)

    # Drop empties after normalization
    return [p for p in normalized if isinstance(p, str) and p.strip()]


def validate_new_file_diffs_have_complete_structure(
    patch_content: str,
    expected_paths: List[str],
    workspace: Optional[Path] = None,
    *,
    allow_empty_suffixes: Optional[List[str]] = None,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate that NEW file diffs for expected deliverables are structurally complete.

    Why:
    - Some LLM patches emit only diff headers for new files (no ---/+++ and/or no @@ hunks).
    - `git apply` can fail with "diff header lacks filename information".
    - Direct-write fallback cannot reconstruct new-file content without hunks.

    Policy:
    - Only validates expected deliverable paths (so we don't accidentally restrict unrelated diffs).
    - Allows truly-empty new files for a small allowlist of suffixes (e.g., __init__.py).

    Returns:
      (ok, errors, details)
    """
    details: Dict[str, Any] = {
        "missing_headers": [],
        "missing_hunks": [],
        "empty_content": [],
    }
    errors: List[str] = []

    expected_set = {
        normalize_path(p, workspace)
        for p in (expected_paths or [])
        if isinstance(p, str) and p.strip()
    }
    if not expected_set:
        return True, [], details

    allow_empty_suffixes = allow_empty_suffixes or ["__init__.py", ".gitkeep"]

    # Structured JSON patch mode: best-effort check that "create" operations include some content.
    try:
        data = json.loads(patch_content)
        if isinstance(data, dict) and isinstance(data.get("files"), list):
            for f in data.get("files", []):
                path = normalize_path(str(f.get("path", "")).strip(), workspace)
                if path not in expected_set:
                    continue
                mode = f.get("mode")
                if mode not in ("create", "replace", "modify"):
                    continue
                # content key varies across implementations; accept any of these.
                new_content = f.get("new_content")
                if new_content is None:
                    new_content = f.get("content")
                if new_content is None:
                    new_content = f.get("contents")
                if not str(new_content or "").strip() and not any(path.endswith(s) for s in allow_empty_suffixes):
                    details["empty_content"].append(path)
                    errors.append(f"New file content empty/missing in structured patch: {path}")
            return (len(errors) == 0), errors, details
    except Exception:
        pass

    # Unified diff mode.
    lines = patch_content.splitlines()
    current_path: Optional[str] = None
    block: List[str] = []

    def _flush():
        nonlocal current_path, block, errors, details
        if not current_path:
            block = []
            return
        path = normalize_path(current_path, workspace)
        block_lines = block
        block = []
        current_path = None

        if path not in expected_set:
            return

        is_new = any(
            (l.startswith("new file mode") or l.strip() == "--- /dev/null")
            for l in block_lines
        )
        if not is_new:
            return

        has_minus = any(l.startswith("--- ") for l in block_lines)
        has_plus = any(l.startswith("+++ ") for l in block_lines)
        if not (has_minus and has_plus):
            details["missing_headers"].append(path)
            errors.append(f"New file diff missing ---/+++ headers: {path}")

        has_hunk = any(l.startswith("@@") for l in block_lines)
        if not has_hunk and not any(path.endswith(s) for s in allow_empty_suffixes):
            details["missing_hunks"].append(path)
            errors.append(f"New file diff missing @@ hunk header (cannot reconstruct content): {path}")
            return

        if has_hunk:
            has_added = any(l.startswith("+") and not l.startswith("+++") for l in block_lines)
            if not has_added and not any(path.endswith(s) for s in allow_empty_suffixes):
                details["empty_content"].append(path)
                errors.append(f"New file diff has hunks but no added content: {path}")

    for line in lines:
        if line.startswith("diff --git "):
            _flush()
            parts = line.split()
            # diff --git a/foo b/foo
            if len(parts) >= 4:
                # Prefer b/ path.
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_path = b_path[len("b/"):]
                else:
                    # Fallback: strip leading prefixes if present.
                    current_path = b_path.lstrip("b/").lstrip("a/")
            else:
                current_path = None
            block = [line]
            continue
        if current_path is not None:
            block.append(line)

    _flush()
    return (len(errors) == 0), errors, details


def validate_deliverables(
    patch_content: str,
    phase_scope: Dict[str, Any],
    phase_id: str,
    workspace: Optional[Path] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Validate that patch creates expected deliverables

    Args:
        patch_content: Patch content from Builder
        phase_scope: Phase scope configuration
        phase_id: Phase identifier (for logging)
        workspace: Workspace root directory

    Returns:
        Tuple of (is_valid, error_messages, details_dict)
        - is_valid: True if all deliverables present, False otherwise
        - error_messages: List of validation errors (empty if valid)
        - details_dict: Diagnostic information for Builder feedback
    """
    errors = []
    details = {
        "expected_paths": [],
        "actual_paths": [],
        "missing_paths": [],
        "extra_paths": [],
        "misplaced_paths": {},
        "forbidden_roots_detected": [],
        "allowed_roots": [],
        "paths_outside_allowed_roots": [],
        "manifest_paths": [],
        "paths_outside_manifest": [],
    }

    # Extract expected deliverables
    expected_paths = extract_deliverables_from_scope(phase_scope)
    if not expected_paths:
        logger.info(f"[{phase_id}] No deliverables specified in scope, skipping validation")
        return True, [], details

    # Normalize expected paths
    expected_normalized = {normalize_path(p, workspace) for p in expected_paths}
    details["expected_paths"] = sorted(expected_normalized)

    # Some phases (notably research-testing-polish) specify directory deliverables like:
    #   - "tests/research/unit/"
    # These are not literal files and won't appear in diffs. Treat any expected path ending
    # with "/" as a *prefix requirement* satisfied by creating at least one file under it.
    expected_prefixes = sorted([p for p in expected_normalized if p.endswith("/")])
    expected_exact = {p for p in expected_normalized if not p.endswith("/")}

    # Derive allowed roots from expected deliverables (tight allowlist, but must cover ALL expected paths).
    expected_list = sorted(expected_normalized)
    allowed_roots: List[str] = []
    preferred_roots = [
        "src/autopack/research/",
        "src/autopack/cli/",
        "tests/research/",
        "docs/research/",
        "examples/",
    ]
    for r in preferred_roots:
        if any(p.startswith(r) for p in expected_list) and r not in allowed_roots:
            allowed_roots.append(r)

    def _covered_by_roots(path: str, roots: List[str]) -> bool:
        return any(path.startswith(r) for r in roots)

    # If preferred roots do not cover all expected paths, expand to first-2-segments roots.
    # Fix: if second segment looks like a filename (contains '.'), use first segment + "/" as root.
    if not allowed_roots or not all(_covered_by_roots(p, allowed_roots) for p in expected_list):
        expanded: List[str] = []
        for p in expected_list:
            p_norm = p.rstrip("/")
            parts = [seg for seg in p_norm.split("/") if seg]
            if len(parts) >= 2:
                # If second segment contains '.', it's likely a filename, not a directory
                if "." in parts[1]:
                    root = parts[0] + "/"
                else:
                    root = "/".join(parts[:2]) + "/"
            else:
                root = (parts[0] + "/") if parts else ""
            if root not in expanded:
                expanded.append(root)
        allowed_roots = expanded

    details["allowed_roots"] = allowed_roots

    # Optional: strict manifest (if provided by executor for this attempt).
    manifest_paths_raw = phase_scope.get("deliverables_manifest") if isinstance(phase_scope, dict) else None
    manifest_set: Set[str] = set()
    manifest_prefixes: List[str] = []
    if isinstance(manifest_paths_raw, list):
        for p in manifest_paths_raw:
            if isinstance(p, str) and p.strip():
                norm = normalize_path(p.strip(), workspace)
                manifest_set.add(norm)
                if norm.endswith("/"):
                    manifest_prefixes.append(norm)
        details["manifest_paths"] = sorted(manifest_set)

    # Extract actual paths from patch
    actual_paths = extract_paths_from_patch(patch_content)
    actual_normalized = {normalize_path(p, workspace) for p in actual_paths}
    details["actual_paths"] = sorted(actual_normalized)

    # NDJSON + truncation convergence: allow multi-attempt completion.
    # NDJSON operations are applied directly to disk and the executor emits a lightweight synthetic diff
    # containing only files applied in *this attempt*. If we only validate against patch_content, then
    # multi-attempt convergence will fail even when earlier attempts already created some deliverables.
    #
    # Treat any expected deliverable that already exists in the workspace as "present", while still
    # enforcing allowed-roots/manifest constraints on *newly created paths in this patch*.
    workspace_present_exact: Set[str] = set()
    workspace_present_prefixes: Set[str] = set()
    try:
        if workspace:
            for p in expected_exact:
                try:
                    fp = workspace / p
                    if fp.exists() and fp.is_file():
                        workspace_present_exact.add(p)
                except Exception:
                    continue

            # Prefix deliverables: satisfied if any file exists under that directory in workspace.
            for prefix in expected_prefixes:
                try:
                    root = workspace / prefix.rstrip("/")
                    if not root.exists() or not root.is_dir():
                        continue
                    found_any = False
                    # Bounded walk: stop after the first file.
                    for dirpath, _dirnames, filenames in os.walk(root):
                        if filenames:
                            found_any = True
                            break
                        # also treat encountering subdirectories with files later; walk continues
                    if found_any:
                        workspace_present_prefixes.add(prefix)
                except Exception:
                    continue
    except Exception:
        # Best-effort only; never fail validation due to workspace probing.
        pass

    # Expose workspace-derived satisfaction for diagnostics/debugging.
    details["workspace_present_paths"] = sorted(workspace_present_exact)
    details["workspace_present_prefixes"] = sorted(workspace_present_prefixes)

    # Detect common "wrong root" patterns and record them for feedback.
    forbidden_roots = ("tracer_bullet/", "src/tracer_bullet/", "tests/tracer_bullet/")
    detected_forbidden = sorted({r for r in forbidden_roots if any(p.startswith(r) for p in actual_normalized)})
    details["forbidden_roots_detected"] = detected_forbidden

    logger.info(f"[{phase_id}] Deliverables validation:")
    logger.info(f"  Expected: {len(expected_normalized)} files")
    if workspace:
        logger.info(
            f"  Found in patch: {len(actual_normalized)} files "
            f"(+{len(workspace_present_exact)} existing files in workspace)"
        )
    else:
        logger.info(f"  Found in patch: {len(actual_normalized)} files")

    # Find missing deliverables
    satisfied_exact = set(actual_normalized).union(workspace_present_exact)
    missing_exact = expected_exact - satisfied_exact
    missing_prefixes = []
    for prefix in expected_prefixes:
        if not any(a.startswith(prefix) for a in actual_normalized) and prefix not in workspace_present_prefixes:
            missing_prefixes.append(prefix)
    missing = set(missing_exact).union(set(missing_prefixes))
    details["missing_paths"] = sorted(missing)

    # Find extra files (not necessarily an error, but worth noting)
    # Note: for prefix deliverables, treat any files under the prefix as "expected enough".
    extra = set()
    for a in actual_normalized:
        if a in expected_exact:
            continue
        if any(a.startswith(prefix) for prefix in expected_prefixes):
            continue
        extra.add(a)
    details["extra_paths"] = sorted(extra)

    # Hard enforcement: any files outside the allowed roots is a hard deliverables violation.
    outside_allowed = sorted(
        p for p in actual_normalized
        if allowed_roots and not any(p.startswith(r) for r in allowed_roots)
    )
    details["paths_outside_allowed_roots"] = outside_allowed

    # Manifest consistency: if a manifest was provided, any created path not in manifest is a hard violation.
    # Support directory/prefix entries in manifest (paths ending with "/") to allow phases to approve
    # "any file under this directory" where requirements express a directory deliverable.
    def _in_manifest(path: str) -> bool:
        if not manifest_set:
            return True
        if path in manifest_set:
            return True
        return any(path.startswith(prefix) for prefix in manifest_prefixes)

    outside_manifest = sorted([p for p in actual_normalized if manifest_set and not _in_manifest(p)])
    details["paths_outside_manifest"] = outside_manifest

    # Check for potential misplacements (similar filenames in wrong locations)
    if missing:
        for missing_path in missing:
            missing_filename = Path(missing_path).name
            # Look for similar filenames in actual paths
            for actual_path in actual_normalized:
                actual_filename = Path(actual_path).name
                if missing_filename == actual_filename:
                    details["misplaced_paths"][missing_path] = actual_path

    # Heuristic misplacements for wrong-root patterns (filename mismatch is common, so help anyway).
    # If the builder created a top-level tracer_bullet/* tree but required deliverables live under:
    # - src/autopack/research/tracer_bullet/*
    # - tests/research/tracer_bullet/*
    # then add explicit root-mapping examples into misplaced_paths to drive self-correction.
    if detected_forbidden and missing:
        def _map_root(actual: str) -> Optional[str]:
            if actual.startswith("tracer_bullet/"):
                rel = actual[len("tracer_bullet/"):]
                if rel.startswith("tests/"):
                    rel2 = rel[len("tests/"):]
                    return f"tests/research/tracer_bullet/{rel2}"
                return f"src/autopack/research/tracer_bullet/{rel}"
            if actual.startswith("src/tracer_bullet/"):
                rel = actual[len("src/tracer_bullet/"):]
                return f"src/autopack/research/tracer_bullet/{rel}"
            if actual.startswith("tests/tracer_bullet/"):
                rel = actual[len("tests/tracer_bullet/"):]
                return f"tests/research/tracer_bullet/{rel}"
            return None

        expected_missing = set(missing)
        for actual in sorted(actual_normalized)[:30]:
            mapped = _map_root(actual)
            if not mapped:
                continue
            if mapped in expected_missing and mapped not in details["misplaced_paths"]:
                details["misplaced_paths"][mapped] = actual

    # Generate error messages
    if missing:
        errors.append(f"Missing {len(missing)} required deliverables:")
        for path in sorted(missing)[:5]:  # Show first 5
            if path in details["misplaced_paths"]:
                errors.append(f"  - {path} (found at: {details['misplaced_paths'][path]})")
            else:
                errors.append(f"  - {path}")
        if len(missing) > 5:
            errors.append(f"  ... and {len(missing) - 5} more")

    if details["misplaced_paths"]:
        errors.append(f"\n⚠️  File placement issue detected:")
        errors.append(f"   Builder created files in wrong locations.")
        errors.append(f"   Please verify file paths match the deliverables specification.")

    if outside_allowed:
        errors.append("\n🚫 Files created OUTSIDE allowed roots (hard violation):")
        for p in outside_allowed[:10]:
            errors.append(f"  - {p}")
        if len(outside_allowed) > 10:
            errors.append(f"  ... and {len(outside_allowed) - 10} more")

    if outside_manifest:
        errors.append("\n🚫 Files created OUTSIDE the approved manifest (hard violation):")
        for p in outside_manifest[:10]:
            errors.append(f"  - {p}")
        if len(outside_manifest) > 10:
            errors.append(f"  ... and {len(outside_manifest) - 10} more")

    if detected_forbidden:
        errors.append("\n🚫 Forbidden root folder(s) detected in your patch:")
        for r in detected_forbidden[:5]:
            errors.append(f"  - {r}  (DO NOT create files under this root)")

    is_valid = len(missing) == 0

    if is_valid:
        logger.info(f"[{phase_id}] ✅ Deliverables validation PASSED")
        if extra:
            logger.info(f"[{phase_id}]    Note: {len(extra)} additional files created (not required)")
    else:
        logger.error(f"[{phase_id}] ❌ Deliverables validation FAILED")
        for error in errors:
            logger.error(f"[{phase_id}]    {error}")

    return is_valid, errors, details


def format_validation_feedback_for_builder(
    errors: List[str],
    details: Dict[str, Any],
    phase_description: str
) -> str:
    """Format validation errors as feedback for Builder to self-correct

    Args:
        errors: List of validation error messages
        details: Validation details dictionary
        phase_description: Phase description (for context)

    Returns:
        Formatted feedback message for Builder
    """
    feedback = []

    feedback.append("❌ DELIVERABLES VALIDATION FAILED")
    feedback.append("")
    feedback.append("Your patch does not create the required deliverable files.")
    feedback.append("")

    # Show phase requirements
    feedback.append("📋 REQUIRED DELIVERABLES:")
    for path in details.get("expected_paths", [])[:10]:
        feedback.append(f"  ✓ {path}")
    if len(details.get("expected_paths", [])) > 10:
        feedback.append(f"  ... and {len(details['expected_paths']) - 10} more")
    feedback.append("")

    # Show what was found
    feedback.append("📄 FILES IN YOUR PATCH:")
    if details.get("actual_paths"):
        for path in details.get("actual_paths", [])[:10]:
            feedback.append(f"  • {path}")
        if len(details.get("actual_paths", [])) > 10:
            feedback.append(f"  ... and {len(details['actual_paths']) - 10} more")
    else:
        feedback.append("  (none)")
    feedback.append("")

    # Highlight misplacements
    if details.get("misplaced_paths"):
        feedback.append("⚠️  WRONG FILE LOCATIONS:")
        for expected, actual in list(details["misplaced_paths"].items())[:5]:
            feedback.append(f"  Expected: {expected}")
            feedback.append(f"  Created:  {actual}")
            feedback.append("")

    # Highlight forbidden roots explicitly (strongest guidance for repeated tracer_bullet misplacement).
    forbidden_roots_detected = details.get("forbidden_roots_detected") or []
    if forbidden_roots_detected:
        feedback.append("🚫 FORBIDDEN ROOTS DETECTED:")
        for r in forbidden_roots_detected[:5]:
            feedback.append(f"  - {r}")
        feedback.append("")
        feedback.append("✅ Correct roots to use instead:")
        feedback.append("  - src/autopack/research/tracer_bullet/")
        feedback.append("  - tests/research/tracer_bullet/")
        feedback.append("  - docs/research/")
        feedback.append("")

    # Highlight allowed roots for this phase (tight allowlist).
    allowed_roots = details.get("allowed_roots") or []
    if allowed_roots:
        feedback.append("✅ ALLOWED ROOTS (you may ONLY create files under these prefixes):")
        for r in allowed_roots[:10]:
            feedback.append(f"  - {r}")
        feedback.append("")

    outside_allowed = details.get("paths_outside_allowed_roots") or []
    if outside_allowed:
        feedback.append("🚫 OUTSIDE-ALLOWED FILES (hard violation):")
        for p in outside_allowed[:10]:
            feedback.append(f"  - {p}")
        if len(outside_allowed) > 10:
            feedback.append(f"  ... and {len(outside_allowed) - 10} more")
        feedback.append("")

    outside_manifest = details.get("paths_outside_manifest") or []
    if outside_manifest:
        feedback.append("🚫 OUTSIDE-MANIFEST FILES (hard violation):")
        for p in outside_manifest[:10]:
            feedback.append(f"  - {p}")
        if len(outside_manifest) > 10:
            feedback.append(f"  ... and {len(outside_manifest) - 10} more")
        feedback.append("")

    # If we have JSON deliverables validation details, show explicit guidance (esp. gold_set.json).
    invalid_json_files = details.get("invalid_json_files") or []
    if invalid_json_files:
        feedback.append("🧾 JSON DELIVERABLE CONTENT REQUIREMENTS:")
        feedback.append("- JSON deliverable files must be non-empty valid JSON.")
        feedback.append("- Minimal acceptable placeholder is `[]` (empty array) or `{}` (empty object).")
        feedback.append("- Do NOT leave JSON files blank.")
        for item in invalid_json_files[:5]:
            p = item.get("path")
            r = item.get("reason")
            feedback.append(f"  - {p}: {r}")
        feedback.append("")

    # Show missing files
    if details.get("missing_paths"):
        feedback.append("❌ MISSING FILES:")
        for path in details.get("missing_paths", [])[:10]:
            feedback.append(f"  - {path}")
        if len(details.get("missing_paths", [])) > 10:
            feedback.append(f"  ... and {len(details['missing_paths']) - 10} more")
        feedback.append("")

    feedback.append("🔧 ACTION REQUIRED:")
    feedback.append("Please regenerate the patch with files in the correct locations.")
    feedback.append("Ensure all file paths match the deliverables specification exactly.")

    return "\n".join(feedback)


def _validate_python_symbols(file_path: Path, expected_symbols: List[str], path: str) -> List[str]:
    """Validate Python symbols using AST parsing (BUILD-127 Phase 3 Enhancement).

    Uses AST parsing instead of substring search to avoid false positives
    (symbol name in comments/strings) and false negatives (commented out code).

    Args:
        file_path: Path to Python file
        expected_symbols: List of expected symbol names (classes, functions)
        path: Relative path for error messages

    Returns:
        List of validation issues (empty if all symbols found)
    """
    import ast

    issues = []

    try:
        content = file_path.read_text(encoding='utf-8')

        # Try AST parsing first (most robust)
        try:
            tree = ast.parse(content, filename=str(file_path))

            # Extract actual symbols from AST
            actual_symbols = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    actual_symbols.add(node.name)

            # Check expected symbols
            for symbol in expected_symbols:
                if symbol not in actual_symbols:
                    issues.append(f"{path} missing expected symbol: {symbol}")

        except SyntaxError:
            # Fallback to substring search if AST parsing fails (syntax errors)
            # This is acceptable because syntax errors will be caught by CI anyway
            logger.warning(f"[ManifestValidator] AST parsing failed for {path}, falling back to substring search")
            for symbol in expected_symbols:
                if symbol not in content:
                    issues.append(f"{path} missing expected symbol: {symbol}")

    except Exception as e:
        issues.append(f"Error reading {path}: {e}")

    return issues


def extract_manifest_from_output(output: str) -> Optional[Dict]:
    """Extract deliverables manifest from Builder output (BUILD-127 Phase 3).

    Builder should include a manifest at the end of output like:

    DELIVERABLES_MANIFEST:
    ```json
    {
      "created": [...],
      "modified": [...]
    }
    ```

    Returns:
        Dict with manifest data, or None if not found
    """
    import re

    # Look for DELIVERABLES_MANIFEST marker
    pattern = r'DELIVERABLES_MANIFEST:\s*```json\s*(\{.*?\})\s*```'
    match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)

    if not match:
        return None

    try:
        manifest = json.loads(match.group(1))
        return manifest
    except json.JSONDecodeError:
        logger.warning("[ManifestValidator] Failed to parse deliverables manifest JSON")
        return None


def validate_structured_manifest(
    manifest: Dict,
    workspace: Path,
    expected_deliverables: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """Validate Builder's deliverables manifest (BUILD-127 Phase 3).

    Args:
        manifest: Parsed deliverables manifest from Builder
        workspace: Workspace path for file validation
        expected_deliverables: Optional list of expected file paths

    Returns:
        Tuple of (passed: bool, issues: List[str])
    """
    issues = []

    # Validate manifest structure
    if not isinstance(manifest, dict):
        issues.append("Manifest is not a dictionary")
        return False, issues

    created = manifest.get("created", [])
    modified = manifest.get("modified", [])

    if not isinstance(created, list):
        issues.append("Manifest 'created' field is not a list")
    if not isinstance(modified, list):
        issues.append("Manifest 'modified' field is not a list")

    if issues:
        return False, issues

    # Validate created files
    for item in created:
        if not isinstance(item, dict):
            issues.append(f"Created item is not a dictionary: {item}")
            continue

        path = item.get("path")
        if not path:
            issues.append(f"Created item missing 'path' field: {item}")
            continue

        # Check file exists
        file_path = workspace / path
        if not file_path.exists():
            issues.append(f"Created file does not exist: {path}")
            continue

        # Validate symbols if provided
        symbols = item.get("symbols", [])
        if symbols:
            symbol_issues = _validate_python_symbols(file_path, symbols, path)
            issues.extend(symbol_issues)

    # Validate modified files
    for item in modified:
        if not isinstance(item, dict):
            issues.append(f"Modified item is not a dictionary: {item}")
            continue

        path = item.get("path")
        if not path:
            issues.append(f"Modified item missing 'path' field: {item}")
            continue

        # Check file exists
        file_path = workspace / path
        if not file_path.exists():
            issues.append(f"Modified file does not exist: {path}")

    # Check against expected deliverables if provided
    if expected_deliverables:
        manifest_paths = set()
        for item in created:
            if isinstance(item, dict) and "path" in item:
                manifest_paths.add(item["path"])
        for item in modified:
            if isinstance(item, dict) and "path" in item:
                manifest_paths.add(item["path"])

        # Normalize expected deliverables
        expected_normalized = set()
        for deliv in expected_deliverables:
            normalized = sanitize_deliverable_path(deliv)
            if normalized:
                expected_normalized.add(normalized)

        # Check for missing deliverables
        for expected in expected_normalized:
            # Allow partial matches (e.g., tests/ directory matches test_foo.py)
            if not any(
                path == expected or path.startswith(expected)
                for path in manifest_paths
            ):
                issues.append(f"Expected deliverable not in manifest: {expected}")

    passed = len(issues) == 0
    return passed, issues
