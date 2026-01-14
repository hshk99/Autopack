#!/usr/bin/env python3
"""CI guard to block DEBUG enablement in production configs (BUILD-180).

Closes SECURITY_BURNDOWN.md TODO: implement scripts/ci/check_production_config.py.

This script checks production configuration files for DEBUG patterns that
should never be enabled in production environments.

Exit codes:
    0: No violations found
    1: DEBUG violations found in production configs
    2: Script error (e.g., invalid arguments)

Usage:
    python scripts/ci/check_production_config.py [--repo-root PATH]
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class DebugViolation:
    """A DEBUG violation found in a production config."""

    file_path: str
    line_number: int
    pattern: str
    line_content: str


@dataclass
class CheckResult:
    """Result of checking production configs."""

    exit_code: int
    violations: List[DebugViolation]
    remediation_message: Optional[str] = None


# Patterns that indicate DEBUG is enabled
DEBUG_ENABLED_PATTERNS = [
    # Environment variable patterns
    (r"^\s*DEBUG\s*=\s*1\s*$", "DEBUG=1"),
    (r"^\s*DEBUG\s*=\s*['\"]1['\"]\s*$", "DEBUG='1' or DEBUG=\"1\""),
    (r"^\s*DEBUG\s*=\s*['\"]?true['\"]?\s*$", "DEBUG=true"),
    (r"^\s*DEBUG\s*=\s*['\"]?True['\"]?\s*$", "DEBUG=True"),
    (r"^\s*DEBUG\s*=\s*['\"]?yes['\"]?\s*$", "DEBUG=yes"),
    (r"^\s*DEBUG\s*=\s*['\"]?on['\"]?\s*$", "DEBUG=on"),
    # YAML patterns
    (r"^\s*debug\s*:\s*true\s*$", "debug: true"),
    (r"^\s*debug\s*:\s*True\s*$", "debug: True"),
    (r"^\s*debug\s*:\s*1\s*$", "debug: 1"),
    (r"^\s*debug\s*:\s*['\"]true['\"]\s*$", "debug: 'true'"),
    (r"^\s*DEBUG\s*:\s*true\s*$", "DEBUG: true"),
    (r"^\s*DEBUG\s*:\s*1\s*$", "DEBUG: 1"),
    # JSON patterns (less common in configs but check anyway)
    (r'["\']debug["\']\s*:\s*true', '"debug": true'),
    (r'["\']DEBUG["\']\s*:\s*true', '"DEBUG": true'),
]

# Patterns that are safe (DEBUG disabled) - ignore these
DEBUG_DISABLED_PATTERNS = [
    r"^\s*#",  # Commented lines
    r"^\s*DEBUG\s*=\s*0\s*$",
    r"^\s*DEBUG\s*=\s*['\"]0['\"]\s*$",
    r"^\s*DEBUG\s*=\s*['\"]?false['\"]?\s*$",
    r"^\s*DEBUG\s*=\s*['\"]?False['\"]?\s*$",
    r"^\s*DEBUG\s*=\s*['\"]?no['\"]?\s*$",
    r"^\s*DEBUG\s*=\s*['\"]?off['\"]?\s*$",
    r"^\s*debug\s*:\s*false\s*$",
    r"^\s*debug\s*:\s*False\s*$",
    r"^\s*debug\s*:\s*0\s*$",
]

# Production config file patterns
PRODUCTION_CONFIG_PATTERNS = [
    ".env.production",
    ".env.prod",
    "production.yaml",
    "production.yml",
    "prod.yaml",
    "prod.yml",
    "config/production.yaml",
    "config/production.yml",
    "config/prod.yaml",
    "config/prod.yml",
    "deploy/production.yaml",
    "deploy/production.yml",
]


def is_production_config(file_path: Path) -> bool:
    """Check if a file is a production config file.

    Args:
        file_path: Path to check

    Returns:
        True if file is a production config
    """
    path_str = str(file_path).replace("\\", "/").lower()

    for pattern in PRODUCTION_CONFIG_PATTERNS:
        if path_str.endswith(pattern.lower()):
            return True

    # Also check for "production" in the path with config extensions
    if "production" in path_str or "prod" in path_str:
        if any(path_str.endswith(ext) for ext in [".yaml", ".yml", ".env", ".json"]):
            return True

    return False


def is_debug_disabled_line(line: str) -> bool:
    """Check if a line explicitly disables DEBUG.

    Args:
        line: Line to check

    Returns:
        True if line disables DEBUG or is commented
    """
    for pattern in DEBUG_DISABLED_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def check_content_for_debug(content: str, file_path: str) -> List[DebugViolation]:
    """Check file content for DEBUG enablement.

    Args:
        content: File content
        file_path: Path for reporting

    Returns:
        List of violations found
    """
    violations = []

    for line_num, line in enumerate(content.split("\n"), 1):
        # Skip if line disables DEBUG
        if is_debug_disabled_line(line):
            continue

        # Check for DEBUG enabled patterns
        for pattern, description in DEBUG_ENABLED_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                violations.append(
                    DebugViolation(
                        file_path=file_path,
                        line_number=line_num,
                        pattern=description,
                        line_content=line.strip()[:100],
                    )
                )
                break  # Only report first match per line

    return violations


def check_file_for_debug(file_path: Path) -> List[DebugViolation]:
    """Check a file for DEBUG enablement.

    Args:
        file_path: Path to file

    Returns:
        List of violations found
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        return check_content_for_debug(content, str(file_path))
    except Exception as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)
        return []


def find_production_configs(repo_root: Path) -> List[Path]:
    """Find all production config files in repo.

    Args:
        repo_root: Repository root directory

    Returns:
        List of production config file paths
    """
    configs = []

    # Check known patterns
    for pattern in PRODUCTION_CONFIG_PATTERNS:
        # Handle both direct paths and glob patterns
        if "*" in pattern:
            configs.extend(repo_root.glob(pattern))
        else:
            full_path = repo_root / pattern
            if full_path.exists():
                configs.append(full_path)

    # Also search for production configs in common locations
    for search_pattern in ["**/production.*", "**/*prod*.*"]:
        for path in repo_root.glob(search_pattern):
            if path.is_file() and is_production_config(path):
                if path not in configs:
                    configs.append(path)

    return configs


def check_production_configs(repo_root: Path) -> CheckResult:
    """Check all production configs for DEBUG enablement.

    Args:
        repo_root: Repository root directory

    Returns:
        CheckResult with violations and exit code
    """
    all_violations = []

    # Find production configs
    configs = find_production_configs(repo_root)

    if not configs:
        return CheckResult(
            exit_code=0,
            violations=[],
            remediation_message=None,
        )

    # Check each config
    for config_path in configs:
        violations = check_file_for_debug(config_path)
        all_violations.extend(violations)

    if all_violations:
        remediation = """
REMEDIATION REQUIRED:

Production configuration files must NOT have DEBUG enabled.
DEBUG mode can expose sensitive information like stack traces,
internal paths, and credentials in error responses.

To fix:
1. Remove DEBUG=1, DEBUG=true, debug: true from production configs
2. If DEBUG is needed for development, use .env.development instead
3. Production should always use DEBUG=0, DEBUG=false, or omit DEBUG entirely

See docs/SECURITY_BURNDOWN.md for security policy details.
"""
        return CheckResult(
            exit_code=1,
            violations=all_violations,
            remediation_message=remediation,
        )

    return CheckResult(
        exit_code=0,
        violations=[],
        remediation_message=None,
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check production configs for DEBUG enablement")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help="Repository root directory",
    )
    args = parser.parse_args()

    print(f"Checking production configs in: {args.repo_root}")

    result = check_production_configs(args.repo_root)

    if result.violations:
        print(f"\nFOUND {len(result.violations)} DEBUG VIOLATION(S):\n")
        for v in result.violations:
            print(f"  {v.file_path}:{v.line_number}")
            print(f"    Pattern: {v.pattern}")
            print(f"    Content: {v.line_content}")
            print()

        if result.remediation_message:
            print(result.remediation_message)

        return 1

    print("\nSUCCESS: No DEBUG enablement found in production configs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
