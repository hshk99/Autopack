"""
Policy loader for storage retention and safety rules.

Loads and enforces policies from config/storage_policy.yaml to ensure:
- Protected paths are never deleted
- Retention windows are respected
- Coordination with Tidy system
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import fnmatch


@dataclass
class CategoryPolicy:
    """Policy for a storage category."""
    name: str
    match_globs: List[str]
    delete_enabled: bool
    delete_requires_approval: bool
    compress_enabled: bool
    compress_requires_approval: bool


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


def load_policy(policy_path: Optional[Path] = None) -> StoragePolicy:
    """
    Load storage policy from YAML.

    Args:
        policy_path: Path to policy YAML file. If None, loads from
                     config/storage_policy.yaml relative to repo root.

    Returns:
        StoragePolicy object with all parsed policy data.

    Raises:
        FileNotFoundError: If policy file doesn't exist
        yaml.YAMLError: If policy file is invalid YAML
    """
    if policy_path is None:
        # Default to repo config
        policy_path = Path(__file__).parent.parent.parent.parent / "config" / "storage_policy.yaml"

    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with open(policy_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Parse protected paths
    paths_section = data.get('paths', {})
    protected_globs = paths_section.get('protected_globs', [])
    pinned_globs = paths_section.get('pinned_globs', [])

    # Parse categories
    categories = {}
    for cat_name, cat_data in data.get('categories', {}).items():
        match_globs = cat_data.get('match_globs', [])
        actions = cat_data.get('allowed_actions', {})

        delete_action = actions.get('delete', {})
        compress_action = actions.get('compress', {})

        categories[cat_name] = CategoryPolicy(
            name=cat_name,
            match_globs=match_globs,
            delete_enabled=delete_action.get('enabled', False),
            delete_requires_approval=delete_action.get('requires_approval', True),
            compress_enabled=compress_action.get('enabled', False),
            compress_requires_approval=compress_action.get('requires_approval', False)
        )

    # Parse retention
    retention = {}
    for ret_name, ret_data in data.get('retention_days', {}).items():
        retention[ret_name] = RetentionPolicy(
            compress_after_days=ret_data.get('compress_after'),
            delete_after_days=ret_data.get('delete_after'),
            delete_requires_approval=ret_data.get('delete_requires_approval', True)
        )

    return StoragePolicy(
        version=data.get('version', '1.0'),
        protected_globs=protected_globs,
        pinned_globs=pinned_globs,
        categories=categories,
        retention=retention
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
    normalized = path.replace('\\', '/')

    # Also check without drive letter for Windows paths
    if ':' in normalized:
        # Extract path after drive letter (e.g., "C:/dev/..." -> "/dev/...")
        no_drive = '/' + '/'.join(normalized.split('/')[1:])
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
        if glob_pattern.startswith('**/'):
            pattern_suffix = glob_pattern[3:]
            if normalized.endswith(pattern_suffix) or no_drive.endswith(pattern_suffix):
                return True

        # Check if any part of the path matches the pattern
        path_parts = normalized.split('/')
        for i in range(len(path_parts)):
            partial_path = '/'.join(path_parts[i:])
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
    normalized = path.replace('\\', '/')

    # Check each category in order (except 'unknown' which is catch-all)
    for cat_name, cat_policy in policy.categories.items():
        if cat_name == 'unknown':
            continue

        for glob_pattern in cat_policy.match_globs:
            if fnmatch.fnmatch(normalized, glob_pattern):
                return cat_name

            # Check path components for ** patterns
            if '**' in glob_pattern:
                path_parts = normalized.split('/')
                for i in range(len(path_parts)):
                    partial_path = '/'.join(path_parts[i:])
                    if fnmatch.fnmatch(partial_path, glob_pattern):
                        return cat_name

    # Default to 'unknown' if it exists
    if 'unknown' in policy.categories:
        return 'unknown'

    return None
