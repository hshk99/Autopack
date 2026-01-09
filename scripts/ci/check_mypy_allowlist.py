#!/usr/bin/env python3
"""CI Check: Mypy Allowlist Verification.

Runs mypy on files listed in config/mypy_allowlist.txt with strict settings.
Files on the allowlist must pass mypy without errors.

Exit codes:
    0: All allowlisted files pass mypy
    1: Mypy errors found in allowlisted files
    2: Runtime error (allowlist not found, mypy not installed, etc.)

GAP reference: GAP-8.3.1 (Mypy adoption ladder)
"""

import subprocess
import sys
from pathlib import Path


def load_allowlist(allowlist_path: Path) -> list[str]:
    """Load and parse the mypy allowlist file."""
    if not allowlist_path.exists():
        print(f"[X] ERROR: Allowlist not found at {allowlist_path}", file=sys.stderr)
        sys.exit(2)

    files = []
    for line in allowlist_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue
        files.append(line)

    return files


def check_mypy_installed() -> bool:
    """Check if mypy is installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def run_mypy(files: list[str], repo_root: Path) -> tuple[int, str, str]:
    """Run mypy on the specified files.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    if not files:
        return 0, "No files to check", ""

    # Convert relative paths to absolute
    abs_files = [str(repo_root / f) for f in files if (repo_root / f).exists()]

    if not abs_files:
        return 0, "No existing files to check", ""

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(repo_root / "pyproject.toml"),
            "--no-error-summary",
            *abs_files,
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )

    return result.returncode, result.stdout, result.stderr


def main() -> int:
    """Run mypy checks on allowlisted files."""
    repo_root = Path(__file__).parent.parent.parent
    allowlist_path = repo_root / "config" / "mypy_allowlist.txt"

    print("=" * 60)
    print("Mypy Allowlist Verification (GAP-8.3.1)")
    print("=" * 60)
    print()

    # Check mypy is installed
    if not check_mypy_installed():
        print("[X] ERROR: mypy not installed", file=sys.stderr)
        print("  Install with: pip install mypy", file=sys.stderr)
        return 2

    # Load allowlist
    files = load_allowlist(allowlist_path)
    print(f"Allowlist: {allowlist_path}")
    print(f"Files to check: {len(files)}")
    print()

    if not files:
        print("[OK] No files in allowlist (empty)")
        return 0

    # Check which files exist
    existing_files = [f for f in files if (repo_root / f).exists()]
    missing_files = [f for f in files if not (repo_root / f).exists()]

    if missing_files:
        print(f"[!] Warning: {len(missing_files)} files in allowlist do not exist:")
        for f in missing_files:
            print(f"    - {f}")
        print()

    print(f"Checking {len(existing_files)} files with mypy...")
    print()

    # Run mypy
    returncode, stdout, stderr = run_mypy(existing_files, repo_root)

    if stdout.strip():
        print(stdout)
    if stderr.strip():
        print(stderr, file=sys.stderr)

    print()
    print("=" * 60)

    if returncode == 0:
        print(f"[OK] All {len(existing_files)} allowlisted files pass mypy")
        return 0
    else:
        print("[X] Mypy errors found in allowlisted files", file=sys.stderr)
        print()
        print("To fix:")
        print("  1. Fix the type errors shown above")
        print("  2. Or remove the file from config/mypy_allowlist.txt (not recommended)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
