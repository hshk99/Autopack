"""
Policy loader for storage retention and safety rules.

Loads and enforces policies from the canonical unified policy file:
- config/protection_and_retention_policy.yaml

Backward compatibility:
- Legacy config/storage_policy.yaml is still supported.

This policy ensures:
- Protected paths are never deleted
- Retention windows are respected
- Coordination with Tidy system
"""

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class ExecutionLimits:
    """Execution safety caps for a category (BUILD-152)."""

    max_gb_per_run: float
    max_files_per_run: int
    max_retries: int
    retry_backoff_seconds: List[int]


@dataclass
class CategoryPolicy:
    """Policy for a storage category."""

    name: str
    match_globs: List[str]
    delete_enabled: bool
    delete_requires_approval: bool
    compress_enabled: bool
    compress_requires_approval: bool
    execution_limits: Optional["ExecutionLimits"] = None


@dataclass
class RetentionPolicy:
    """Retention windows for a category."""

    compress_after_days: Optional[int]
    delete_after_days: Optional[int]
    delete_requires_approval: bool


@dataclass
class StoragePolicy:
    """Complete storage policy loaded from YAML."""

    version: str
    protected_globs: List[str]
    pinned_globs: List[str]
    categories: Dict[str, CategoryPolicy]
    retention: Dict[str, RetentionPolicy]


@dataclass
class CategoryDefinition:
    """
    Lightweight category definition used by optional intelligence features
    (e.g., SmartCategorizer) for prompt construction.
    """

    name: str
    patterns: List[str]
    description: str = ""


def load_policy(policy_path: Optional[Path] = None) -> StoragePolicy:
    """
    Load storage policy from YAML.

    Args:
        policy_path: Path to policy YAML file. If None, loads from
                     config/protection_and_retention_policy.yaml relative to repo root.

    Returns:
        StoragePolicy object with all parsed policy data.

    Raises:
        FileNotFoundError: If policy file doesn't exist
        yaml.YAMLError: If policy file is invalid YAML
    """
    if policy_path is None:
        # Default to repo config
        policy_path = (
            Path(__file__).parent.parent.parent.parent
            / "config"
            / "protection_and_retention_policy.yaml"
        )

    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with open(policy_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid policy format (expected YAML mapping) in {policy_path}")

    # Dispatch based on schema
    if "protected_paths" in data:
        return _parse_unified_policy(data)
    if "paths" in data:
        return _parse_legacy_policy(data)

    raise ValueError(f"Unrecognized policy schema in {policy_path}")


def _parse_legacy_policy(data: Dict) -> StoragePolicy:
    """Parse legacy config/storage_policy.yaml schema."""
    # Parse protected paths
    paths_section = data.get("paths", {})
    protected_globs = paths_section.get("protected_globs", [])
    pinned_globs = paths_section.get("pinned_globs", [])

    # Parse categories
    categories: Dict[str, CategoryPolicy] = {}
    for cat_name, cat_data in data.get("categories", {}).items():
        match_globs = cat_data.get("match_globs", [])
        actions = cat_data.get("allowed_actions", {})

        delete_action = actions.get("delete", {})
        compress_action = actions.get("compress", {})

        # Parse execution limits (BUILD-152)
        execution_limits = None
        if "execution_limits" in cat_data:
            limits_data = cat_data["execution_limits"]
            execution_limits = ExecutionLimits(
                max_gb_per_run=limits_data.get("max_gb_per_run", 10.0),
                max_files_per_run=limits_data.get("max_files_per_run", 100),
                max_retries=limits_data.get("max_retries", 3),
                retry_backoff_seconds=limits_data.get("retry_backoff_seconds", [2, 5, 10]),
            )

        categories[cat_name] = CategoryPolicy(
            name=cat_name,
            match_globs=match_globs,
            delete_enabled=delete_action.get("enabled", False),
            delete_requires_approval=delete_action.get("requires_approval", True),
            compress_enabled=compress_action.get("enabled", False),
            compress_requires_approval=compress_action.get("requires_approval", False),
            execution_limits=execution_limits,
        )

    # Parse retention
    retention: Dict[str, RetentionPolicy] = {}
    for ret_name, ret_data in data.get("retention_days", {}).items():
        retention[ret_name] = RetentionPolicy(
            compress_after_days=ret_data.get("compress_after"),
            delete_after_days=ret_data.get("delete_after"),
            delete_requires_approval=ret_data.get("delete_requires_approval", True),
        )

    return StoragePolicy(
        version=data.get("version", "1.0"),
        protected_globs=protected_globs,
        pinned_globs=pinned_globs,
        categories=categories,
        retention=retention,
    )


def _parse_unified_policy(data: Dict) -> StoragePolicy:
    """Parse unified config/protection_and_retention_policy.yaml schema."""
    protected_globs: List[str] = []
    pinned_globs: List[str] = []

    protected_paths = data.get("protected_paths", {}) or {}
    for k, v in protected_paths.items():
        if k == "description":
            continue
        if isinstance(v, list):
            protected_globs.extend(v)

    categories: Dict[str, CategoryPolicy] = {}
    retention: Dict[str, RetentionPolicy] = {}

    for cat_name, cat_data in (data.get("categories", {}) or {}).items():
        match_globs = cat_data.get("patterns", []) or []
        actions = cat_data.get("allowed_actions", {}) or {}

        delete_action = actions.get("delete", {}) or {}
        compress_action = actions.get("compress", {}) or {}

        execution_limits = None
        if "execution_limits" in cat_data:
            limits_data = cat_data.get("execution_limits") or {}
            execution_limits = ExecutionLimits(
                max_gb_per_run=limits_data.get("max_gb_per_run", 10.0),
                max_files_per_run=limits_data.get("max_files_per_run", 100),
                max_retries=limits_data.get("max_retries", 3),
                retry_backoff_seconds=limits_data.get("retry_backoff_seconds", [2, 5, 10]),
            )

        delete_requires_approval = bool(delete_action.get("requires_approval", True))
        retention_days = cat_data.get("retention_days", None)
        retention[cat_name] = RetentionPolicy(
            compress_after_days=None,
            delete_after_days=retention_days if isinstance(retention_days, int) else None,
            delete_requires_approval=delete_requires_approval,
        )

        categories[cat_name] = CategoryPolicy(
            name=cat_name,
            match_globs=match_globs,
            delete_enabled=bool(delete_action.get("enabled", False)),
            delete_requires_approval=delete_requires_approval,
            compress_enabled=bool(compress_action.get("enabled", False)),
            compress_requires_approval=bool(compress_action.get("requires_approval", False)),
            execution_limits=execution_limits,
        )

    return StoragePolicy(
        version=data.get("version", "1.0"),
        protected_globs=protected_globs,
        pinned_globs=pinned_globs,
        categories=categories,
        retention=retention,
    )


def is_path_protected(path: str, policy: StoragePolicy) -> bool:
    """
    Check if a path is protected by policy.

    Protected paths should NEVER be deleted or modified by Storage Optimizer.

    Args:
        path: File or directory path to check (can be absolute or relative)
        policy: StoragePolicy object with protection rules

    Returns:
        True if path matches any protected glob pattern, False otherwise
    """
    # Normalize path to POSIX style (forward slashes)
    normalized = path.replace("\\", "/")

    # Also check without drive letter for Windows paths
    if ":" in normalized:
        # Extract path after drive letter (e.g., "C:/dev/..." -> "/dev/...")
        no_drive = "/" + "/".join(normalized.split("/")[1:])
    else:
        no_drive = normalized

    # Check against protected globs
    all_globs = policy.protected_globs + policy.pinned_globs

    for glob_pattern in all_globs:
        # Try matching both full path and path without drive
        if fnmatch.fnmatch(normalized, glob_pattern):
            return True
        if fnmatch.fnmatch(no_drive, glob_pattern):
            return True

        # Also try matching if pattern or path starts with /**
        if glob_pattern.startswith("**/"):
            pattern_suffix = glob_pattern[3:]
            if normalized.endswith(pattern_suffix) or no_drive.endswith(pattern_suffix):
                return True

        # Check if any part of the path matches the pattern
        path_parts = normalized.split("/")
        for i in range(len(path_parts)):
            partial_path = "/".join(path_parts[i:])
            if fnmatch.fnmatch(partial_path, glob_pattern):
                return True

    return False


def get_category_for_path(path: str, policy: StoragePolicy) -> Optional[str]:
    """
    Determine which category a path belongs to based on policy.

    Args:
        path: File or directory path
        policy: StoragePolicy object with category rules

    Returns:
        Category name if path matches a category, None if no match
    """
    normalized = path.replace("\\", "/")

    # Check each category in order (except 'unknown' which is catch-all)
    for cat_name, cat_policy in policy.categories.items():
        if cat_name == "unknown":
            continue

        for glob_pattern in cat_policy.match_globs:
            if fnmatch.fnmatch(normalized, glob_pattern):
                return cat_name

            # Check path components for ** patterns
            if "**" in glob_pattern:
                path_parts = normalized.split("/")
                for i in range(len(path_parts)):
                    partial_path = "/".join(path_parts[i:])
                    if fnmatch.fnmatch(partial_path, glob_pattern):
                        return cat_name

    # Default to 'unknown' if it exists
    if "unknown" in policy.categories:
        return "unknown"

    return None
