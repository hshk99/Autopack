#!/usr/bin/env python3
"""CI guardrail: enforce canonical build-surface uniqueness.

Purpose:
- Prevent "two truths" drift by ensuring build surfaces (frontend configs) are not duplicated
  across multiple active locations in the repo.

Design:
- CI evaluates only *tracked* files (via `git ls-files`) to avoid local/untracked noise.
- Duplicates are allowed only under `archive/` (explicitly historical).

Exit codes:
  0: OK (no violations)
  1: Violations found
  2: Script/runtime error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    paths: List[str]


@dataclass(frozen=True)
class CheckResult:
    exit_code: int
    violations: List[Violation]


CANONICAL_SINGLETONS: dict[str, str] = {
    # Frontend / build surface (canonical at repo root)
    "package.json": "package.json",
    "package-lock.json": "package-lock.json",
    "vite.config.ts": "vite.config.ts",
    "tsconfig.json": "tsconfig.json",
    "tsconfig.node.json": "tsconfig.node.json",
}

# Canonical compose variants (root-only). Any other tracked docker-compose*.yml outside archive/ is a
# "two truths" hazard (and can accidentally commit prod secrets).
CANONICAL_DOCKER_COMPOSE_FILES = {
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "docker-compose.prod.example.yml",
}

# Allowed "historical" buckets where duplicates are permitted (explicitly not canonical).
ALLOWED_DUPLICATE_PREFIXES = ("archive/",)

# Additional "frontend/build surface" patterns that should not appear outside repo root or archive/.
# These are common drift vectors when multiple sub-frontends accidentally get committed.
DISALLOW_OUTSIDE_ROOT_AND_ARCHIVE_GLOBS = [
    "tsconfig*.json",
    "vite.config.*",
]


def _normalize_relpath(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _git_ls_files(repo_root: Path) -> List[str]:
    try:
        r = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "git ls-files failed")
        raw = r.stdout
        items = [s for s in raw.split("\x00") if s]
        return [_normalize_relpath(p) for p in items]
    except Exception as e:
        raise RuntimeError(f"Failed to list tracked files: {e}") from e


def _is_allowed_duplicate(path: str) -> bool:
    p = _normalize_relpath(path)
    return any(p.startswith(prefix) for prefix in ALLOWED_DUPLICATE_PREFIXES)


def _find_occurrences(tracked_files: Iterable[str], filename: str) -> List[str]:
    suffix = f"/{filename}"
    hits: List[str] = []
    for p in tracked_files:
        p2 = _normalize_relpath(p)
        if p2 == filename or p2.endswith(suffix):
            hits.append(p2)
    return sorted(set(hits))


def _matches_any_glob(path: str, globs: Iterable[str]) -> bool:
    return any(fnmatchcase(path, g) for g in globs)


def check_canonical_build_surfaces(
    repo_root: Path, *, tracked_files: Optional[List[str]] = None
) -> CheckResult:
    tracked = tracked_files if tracked_files is not None else _git_ls_files(repo_root)
    violations: List[Violation] = []

    # ---------------------------------------------------------------------
    # Rule group 1: Frontend/build surface singletons
    # ---------------------------------------------------------------------
    for filename, canonical_path in CANONICAL_SINGLETONS.items():
        occurrences = _find_occurrences(tracked, filename)

        if canonical_path not in occurrences:
            violations.append(
                Violation(
                    rule="missing_canonical",
                    message=f"Canonical file missing: expected '{canonical_path}' to be tracked.",
                    paths=occurrences,
                )
            )
            # Continue gathering other errors rather than early exit.
            continue

        # Any occurrence not at canonical path must be under archive/
        non_canonical = [p for p in occurrences if p != canonical_path]
        bad = [p for p in non_canonical if not _is_allowed_duplicate(p)]
        if bad:
            violations.append(
                Violation(
                    rule="duplicate_build_surface",
                    message=(
                        f"Duplicate tracked '{filename}' outside archive/. "
                        f"Keep only '{canonical_path}' as canonical; move experiments to 'archive/'."
                    ),
                    paths=sorted([canonical_path, *bad]),
                )
            )

    # ---------------------------------------------------------------------
    # Rule group 2: docker-compose variants allowlist
    # ---------------------------------------------------------------------
    compose_hits = [p for p in tracked if fnmatchcase(p.split("/")[-1], "docker-compose*.yml")]
    bad_compose = [
        p
        for p in compose_hits
        if not _is_allowed_duplicate(p) and p not in CANONICAL_DOCKER_COMPOSE_FILES
    ]
    if bad_compose:
        violations.append(
            Violation(
                rule="unexpected_compose_variant",
                message=(
                    "Unexpected tracked docker-compose*.yml outside archive/. "
                    f"Allowed at repo root: {sorted(CANONICAL_DOCKER_COMPOSE_FILES)}."
                ),
                paths=sorted(bad_compose),
            )
        )

    # ---------------------------------------------------------------------
    # Rule group 3: Additional frontend/build config patterns must be root-only
    # ---------------------------------------------------------------------
    for p in tracked:
        # Ignore archive/ entirely
        if _is_allowed_duplicate(p):
            continue
        # Only enforce on the filename portion for root-only config globs
        name = p.split("/")[-1]
        if _matches_any_glob(name, DISALLOW_OUTSIDE_ROOT_AND_ARCHIVE_GLOBS):
            # Root is allowed; anywhere else is not.
            if "/" in p:
                violations.append(
                    Violation(
                        rule="non_root_frontend_config",
                        message=(
                            "Frontend/build config file must not exist outside repo root (unless under archive/). "
                            f"Matched one of: {DISALLOW_OUTSIDE_ROOT_AND_ARCHIVE_GLOBS}"
                        ),
                        paths=[p],
                    )
                )

    if violations:
        return CheckResult(exit_code=1, violations=violations)

    return CheckResult(exit_code=0, violations=[])


def _format_violations(violations: List[Violation]) -> str:
    lines: List[str] = []
    for v in violations:
        lines.append(f"- Rule: {v.rule}")
        lines.append(f"  Message: {v.message}")
        if v.paths:
            lines.append("  Paths:")
            for p in v.paths:
                lines.append(f"    - {p}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check canonical build surface uniqueness")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help="Repository root directory",
    )
    args = parser.parse_args()

    try:
        result = check_canonical_build_surfaces(args.repo_root)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if result.violations:
        print("FOUND CANONICAL BUILD SURFACE VIOLATIONS:\n")
        print(_format_violations(result.violations))
        print(
            "\nREMEDIATION:\n"
            "- Keep frontend/build config singletons at repo root.\n"
            "- Move experiments/legacy configs under archive/.\n"
            "- If you intentionally need a second active frontend, update this script's allowlist\n"
            "  AND document the decision (to avoid 'two truths').\n"
        )
        return result.exit_code

    print("SUCCESS: canonical build surfaces are unique (non-archive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
