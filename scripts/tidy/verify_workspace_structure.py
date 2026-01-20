#!/usr/bin/env python3
"""
Workspace Structure Verifier

Validates that the workspace structure matches WORKSPACE_ORGANIZATION_SPEC.md.
Can be run standalone or integrated into CI.

Usage:
    # Verify Autopack project structure
    python scripts/tidy/verify_workspace_structure.py

    # Verify specific project
    python scripts/tidy/verify_workspace_structure.py --project file-organizer-app-v1

    # Output JSON report
    python scripts/tidy/verify_workspace_structure.py --json-output verify_report.json

Exit codes:
    0 - Structure is valid
    1 - Structure has violations
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Ensure sibling imports work
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

# ---------------------------------------------------------------------------
# Configuration from WORKSPACE_ORGANIZATION_SPEC.md
# ---------------------------------------------------------------------------

ROOT_ALLOWED_FILES = {
    ".gitignore",
    ".dockerignore",
    ".eslintrc.cjs",
    ".env",
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "docker-compose.yml",
    "Dockerfile",
    "requirements.txt",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    ".coverage",
    ".coverage.json",
    # Common repo-root config files used by this repo
    "docker-compose.dev.yml",
    "pytest.ini",
    "requirements-dev.txt",
    "Makefile",
    "nginx.conf",
    "index.html",
    # Primary development database (active)
    "autopack.db",
    # Security scanning config (gitleaks)
    ".gitleaks.toml",
    ".gitleaksignore",
    # Cross-platform hygiene (BUILD-189)
    ".gitattributes",
    ".editorconfig",
    ".env.example",
    ".pre-commit-config.yaml",
    # GitHub security policy
    "SECURITY.md",
}

ROOT_ALLOWED_PATTERNS = [
    # NOTE: "*.db" pattern REMOVED - only autopack.db allowed (see ROOT_ALLOWED_FILES)
    # This enables automatic cleanup of historical/test databases
    "Dockerfile*",
    "docker-compose*.yml",
    "requirements*.txt",
    "tsconfig*.json",
    "vite.config.*",
    # Optional: allow a scoped tidy config file at root if used
    "tidy_scope.yaml",
]

ROOT_ALLOWED_DIRS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".autopack",
    ".claude",
    ".cursor",
    ".autonomous_runs",
    "__pycache__",
    "node_modules",
    ".ruff_cache",
    "src",
    "tests",
    "scripts",
    "docs",
    "archive",
    "backend",
    "frontend",
    "config",
    "venv",
    ".venv",
    "dist",
    "build",
    "ralph",
    # BUILD-183: security/ is allowed at root by design - contains security
    # baselines, threat models, and audit artifacts for visibility.
    "security",
}

DOCS_SOT_FILES = {
    "PROJECT_INDEX.json",
    "BUILD_HISTORY.md",
    "DEBUG_LOG.md",
    "ARCHITECTURE_DECISIONS.md",
    "FUTURE_PLAN.md",
    "LEARNED_RULES.json",
}

DOCS_ALLOWED_FILES = {
    # Core documentation files
    "INDEX.md",
    "CHANGELOG.md",
    "WORKSPACE_ORGANIZATION_SPEC.md",
    "ARCHITECTURE.md",
    "QUICKSTART.md",
    "CONTRIBUTING.md",
    # Canonical guides (truth sources)
    "DEPLOYMENT.md",
    "GOVERNANCE.md",
    "TROUBLESHOOTING.md",
    "TESTING_GUIDE.md",
    "CONFIG_GUIDE.md",
    "AUTHENTICATION.md",
    "ERROR_HANDLING.md",
    "TELEMETRY_GUIDE.md",
    "TELEMETRY_COLLECTION_GUIDE.md",
    "TIDY_SYSTEM_USAGE.md",
    "PARALLEL_RUNS.md",
    "PHASE_LIFECYCLE.md",
    "MODEL_INTELLIGENCE_SYSTEM.md",
    # Completed plan stub (kept for AI navigation; points to archived plan)
    "TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md",
    # Additional specific files that are canonical
    "API_BASICS.md",
    "DOCKER_DEPLOYMENT_GUIDE.md",
    "phase_spec_schema.md",
    "stage2_structured_edits.md",
    "circuit_breaker_usage.md",
    "telemetry_utils_api.md",
}

DOCS_ALLOWED_PATTERNS = [
    "CURSOR_PROMPT_*.md",
    "IMPLEMENTATION_PLAN_*.md",
    "PRODUCTION_*.md",
    "SOT_*.md",
    "IMPROVEMENTS_*.md",
    "IMPLEMENTATION_SUMMARY_*.md",
    "RUNBOOK_*.md",
    "*_GUIDE.md",
    "CANONICAL_*.md",
    "*_SYSTEM.md",
    "TELEMETRY_*.md",  # Keep for backwards compat
    # BUILD-183: Additional allowlisted patterns for known intentional docs.
    # These are NOT converted to SOT; they are simply allowed without warning.
    # Unknown docs files still emit warnings (default-warn preserved).
    "BUILD-*.md",  # Per-task build documentation
    "BUILD_*.md",  # Alternate build doc naming convention
    "*_COMPLETION*.md",  # Task completion reports
    "*_REPORT*.md",  # Analysis and status reports
    "*_OPERATIONS*.md",  # Operations documentation
    "*_PLAYBOOK*.md",  # Operational playbooks
    "*_HOWTO*.md",  # How-to guides
    "*_STATUS*.md",  # Status tracking documents
    "*_PLAN*.md",  # Planning documents
    "*_SUMMARY*.md",  # Summary documents
    "*_DECISIONS*.md",  # Decision records (ARCHITECTURE_DECISIONS.md is SOT)
    "*_POLICY*.md",  # Policy documents
    "*_LOG*.md",  # Log files (security, debug, etc.)
    "*_STANDARDS*.md",  # Standards documentation
    "PROMPT_*.md",  # Prompt documentation
    "P0_*.md",  # Priority-0 documents
    "PRE_*.md",  # Pre-task analysis docs
    "REMAINING_*.md",  # Remaining work docs
    "LEARNED_*.json",  # Learned rules/mitigations JSON
    "CHAT_HISTORY_*.md",  # Chat history extracts
    "CHAT_HISTORY_*.json",  # Chat history extracts JSON
    "CONSOLIDATED_*.md",  # Consolidated documents
    "STORAGE_*.md",  # Storage optimizer docs
    "SECURITY_*.md",  # Security documentation
    "INTENTION_*.md",  # Intention tracking docs
    "DOC_*.md",  # Doc-related analysis
    "EXIT_*.md",  # Exit code standards, etc.
]

DOCS_ALLOWED_SUBDIRS = {
    "guides",
    "cli",
    "cursor",
    "examples",
    "api",
    "autopack",
    "research",
    "reports",
}

ARCHIVE_REQUIRED_BUCKETS = {
    "plans",
    "reports",
    "research",
    "prompts",
    "diagnostics",
    "scripts",
    "superseded",
    "unsorted",
}

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def matches_pattern(filename: str, pattern: str) -> bool:
    """Check if filename matches a wildcard pattern."""
    # Use stdlib glob matching (safer and supports ?, [], etc.)
    return fnmatch.fnmatchcase(filename, pattern)


def is_root_file_allowed(filename: str) -> bool:
    """Check if a file is allowed at repo root."""
    if filename in ROOT_ALLOWED_FILES:
        return True
    for pattern in ROOT_ALLOWED_PATTERNS:
        if matches_pattern(filename, pattern):
            return True
    return False


def is_docs_file_allowed(filename: str) -> bool:
    """Check if a file is allowed in docs/."""
    if filename in DOCS_SOT_FILES or filename in DOCS_ALLOWED_FILES:
        return True
    for pattern in DOCS_ALLOWED_PATTERNS:
        if matches_pattern(filename, pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# Verification Functions
# ---------------------------------------------------------------------------


def verify_root_structure(repo_root: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Verify repo root structure.
    Returns (is_valid, errors, warnings).

    Files that are disallowed but already queued in tidy_pending_moves.json
    are treated as warnings (not errors) to support first-run resilience.
    """
    errors = []
    warnings = []

    # Load pending queue to check if disallowed files are already queued for retry
    pending_srcs: Set[str] = set()
    queue_path = repo_root / ".autonomous_runs" / "tidy_pending_moves.json"

    if queue_path.exists():
        try:
            queue_data = json.loads(queue_path.read_text(encoding="utf-8"))
            for item in queue_data.get("items", []):
                if item.get("status") in {"pending", "failed"}:
                    src = item.get("src")
                    if src:
                        # Normalize path separators for comparison
                        pending_srcs.add(src.replace("\\", "/"))
        except Exception:
            # If queue is malformed, proceed with normal verification
            pass

    # Check for disallowed files
    for item in repo_root.iterdir():
        if item.is_file():
            # Special case: .git file is allowed in worktrees (it's a pointer file, not a directory)
            if item.name == ".git":
                continue
            if not is_root_file_allowed(item.name):
                # Check if this file is already queued for retry
                if item.name in pending_srcs or str(item.name).replace("\\", "/") in pending_srcs:
                    warnings.append(f"Queued for retry (locked): {item.name}")
                else:
                    errors.append(f"Disallowed file at root: {item.name}")
        elif item.is_dir():
            if item.name not in ROOT_ALLOWED_DIRS and not item.name.startswith("."):
                warnings.append(f"Unexpected directory at root: {item.name}")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def verify_docs_structure(docs_dir: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Verify docs/ structure.
    Returns (is_valid, errors, warnings).
    """
    errors = []
    warnings = []

    if not docs_dir.exists():
        errors.append(f"Docs directory does not exist: {docs_dir}")
        return False, errors, warnings

    # Check SOT files
    missing_sot = []
    for sot_file in DOCS_SOT_FILES:
        if not (docs_dir / sot_file).exists():
            missing_sot.append(sot_file)

    if missing_sot:
        errors.append(f"Missing SOT files: {', '.join(missing_sot)}")

    # Check files in docs/
    for item in docs_dir.iterdir():
        if item.is_file():
            if not is_docs_file_allowed(item.name):
                warnings.append(f"Non-SOT file in docs/: {item.name}")
        elif item.is_dir():
            if item.name not in DOCS_ALLOWED_SUBDIRS:
                errors.append(f"Disallowed subdirectory in docs/: {item.name}/")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def verify_archive_structure(archive_dir: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Verify archive/ structure.
    Returns (is_valid, errors, warnings).
    """
    errors = []
    warnings = []

    if not archive_dir.exists():
        warnings.append("Archive directory does not exist (will be created)")
        return True, errors, warnings

    # Check required buckets
    missing_buckets = []
    for bucket in ARCHIVE_REQUIRED_BUCKETS:
        if not (archive_dir / bucket).exists():
            missing_buckets.append(bucket)

    if missing_buckets:
        warnings.append(f"Missing archive buckets: {', '.join(missing_buckets)}")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def verify_project_structure(project_root: Path) -> Tuple[bool, List[str], List[str]]:
    """
    Verify .autonomous_runs project structure.
    Returns (is_valid, errors, warnings).
    """
    errors = []
    warnings = []

    if not project_root.exists():
        warnings.append(f"Project directory does not exist: {project_root}")
        return True, errors, warnings

    # Check for docs/ and archive/
    project_docs = project_root / "docs"
    project_archive = project_root / "archive"

    if not project_docs.exists():
        warnings.append(f"Project docs/ does not exist: {project_docs}")
    else:
        # Verify project docs structure
        _, doc_errors, doc_warnings = verify_docs_structure(project_docs)
        errors.extend([f"[{project_root.name}] {e}" for e in doc_errors])
        warnings.extend([f"[{project_root.name}] {w}" for w in doc_warnings])

    if not project_archive.exists():
        warnings.append(f"Project archive/ does not exist: {project_archive}")
    else:
        # Verify project archive structure
        _, arch_errors, arch_warnings = verify_archive_structure(project_archive)
        errors.extend([f"[{project_root.name}] {e}" for e in arch_errors])
        warnings.extend([f"[{project_root.name}] {w}" for w in arch_warnings])

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


# ---------------------------------------------------------------------------
# Main Verification
# ---------------------------------------------------------------------------


def generate_report(
    results: Dict[str, Tuple[bool, List[str], List[str]]], repo_root: Path, project: str
) -> Dict:
    """Generate verification report."""
    total_errors = sum(len(r[1]) for r in results.values())
    total_warnings = sum(len(r[2]) for r in results.values())
    overall_valid = all(r[0] for r in results.values())

    report = {
        "timestamp": datetime.now().isoformat(),
        "repo_root": str(repo_root),
        "project": project,
        "overall_valid": overall_valid,
        "summary": {
            "total_errors": total_errors,
            "total_warnings": total_warnings,
        },
        "results": {},
    }

    for section, (is_valid, errors, warnings) in results.items():
        report["results"][section] = {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
        }

    return report


def print_report(report: Dict) -> None:
    """Print verification report to console."""
    print("=" * 70)
    print("WORKSPACE STRUCTURE VERIFICATION REPORT")
    print("=" * 70)
    print(f"Timestamp: {report['timestamp']}")
    print(f"Project: {report['project']}")
    # Windows consoles are often cp1252; avoid emojis to prevent UnicodeEncodeError.
    print(f"Overall Valid: {'YES' if report['overall_valid'] else 'NO'}")
    print(f"Total Errors: {report['summary']['total_errors']}")
    print(f"Total Warnings: {report['summary']['total_warnings']}")
    print("=" * 70)

    for section, result in report["results"].items():
        print(f"\n{section.upper()}")
        print("-" * 70)
        print(f"Valid: {'YES' if result['valid'] else 'NO'}")

        if result["errors"]:
            print("\nErrors:")
            for error in result["errors"]:
                print(f"  ERROR: {error}")

        if result["warnings"]:
            print("\nWarnings:")
            for warning in result["warnings"]:
                print(f"  WARNING: {warning}")

    print("\n" + "=" * 70)
    if report["overall_valid"]:
        print("WORKSPACE STRUCTURE IS VALID")
    else:
        print("WORKSPACE STRUCTURE HAS VIOLATIONS")
        print("   Run tidy_up.py to fix issues")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Verify workspace structure matches WORKSPACE_ORGANIZATION_SPEC.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--project", default="autopack", help="Project to verify (default: autopack)"
    )
    parser.add_argument("--json-output", type=Path, help="Write JSON report to file")
    parser.add_argument("--markdown-output", type=Path, help="Write markdown report to file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (fail verification if any warnings present)",
    )

    args = parser.parse_args()

    repo_root = REPO_ROOT
    if args.project == "autopack":
        docs_dir = repo_root / "docs"
        archive_dir = repo_root / "archive"
    else:
        project_root = repo_root / ".autonomous_runs" / args.project
        docs_dir = project_root / "docs"
        archive_dir = project_root / "archive"

    # Run verifications
    results = {}

    # Verify root (only for autopack project)
    if args.project == "autopack":
        results["root"] = verify_root_structure(repo_root)

    # Verify docs
    results["docs"] = verify_docs_structure(docs_dir)

    # Verify archive
    results["archive"] = verify_archive_structure(archive_dir)

    # Verify .autonomous_runs projects (only for autopack)
    if args.project == "autopack":
        autonomous_runs = repo_root / ".autonomous_runs"
        if autonomous_runs.exists():
            # Heuristic: only treat directories as "projects" if they look like projects.
            #
            # We intentionally avoid verifying every directory under `.autonomous_runs/` because
            # many entries are run directories, logs, caches, or infrastructure folders.
            #
            # EXCLUSION: `.autonomous_runs/autopack/` is a runtime workspace (not a project SOT root).
            # It stores executor runtime artifacts and does NOT require the 6-file SOT structure.
            # The main project SOT lives in repo root `docs/`.
            #
            # A directory is considered a "project" if:
            # - it's explicitly known (e.g., `file-organizer-app-v1`), OR
            # - it contains a `docs/` or `archive/` directory at its top level.
            known_projects = {"file-organizer-app-v1"}  # Removed "autopack" - it's runtime only
            runtime_workspaces = {"autopack"}  # Explicitly excluded from project validation

            for project_dir in autonomous_runs.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    # Skip runtime workspaces
                    if project_dir.name in runtime_workspaces:
                        continue

                    if project_dir.name in known_projects:
                        results[f"project:{project_dir.name}"] = verify_project_structure(
                            project_dir
                        )
                        continue
                    if (project_dir / "docs").exists() or (project_dir / "archive").exists():
                        results[f"project:{project_dir.name}"] = verify_project_structure(
                            project_dir
                        )
                        continue
                    # Otherwise: skip (run directories / infra / caches)

    # Generate report
    report = generate_report(results, repo_root, args.project)

    # Print report
    print_report(report)

    # Apply --strict mode: treat warnings as errors
    if args.strict:
        total_warnings = report["summary"]["total_warnings"]
        if total_warnings > 0:
            print("\n" + "=" * 70)
            print("STRICT MODE: Warnings treated as errors")
            print("=" * 70)
            print(f"Found {total_warnings} warnings (treated as errors in strict mode)")
            print()
            report["overall_valid"] = False  # Override validity

    # Write JSON output
    if args.json_output:
        args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report written to: {args.json_output}")

    # Write markdown output
    if args.markdown_output:
        md_lines = [
            "# Workspace Structure Verification Report",
            "",
            f"**Timestamp**: {report['timestamp']}",
            f"**Project**: {report['project']}",
            f"**Overall Valid**: {'YES' if report['overall_valid'] else 'NO'}",
            f"**Total Errors**: {report['summary']['total_errors']}",
            f"**Total Warnings**: {report['summary']['total_warnings']}",
            "",
            "---",
            "",
        ]

        for section, result in report["results"].items():
            md_lines.append(f"## {section.upper()}")
            md_lines.append("")
            md_lines.append(f"**Valid**: {'[OK]' if result['valid'] else '[X]'}")
            md_lines.append("")

            if result["errors"]:
                md_lines.append("### Errors")
                md_lines.append("")
                for error in result["errors"]:
                    md_lines.append(f"- ERROR: {error}")
                md_lines.append("")

            if result["warnings"]:
                md_lines.append("### Warnings")
                md_lines.append("")
                for warning in result["warnings"]:
                    md_lines.append(f"- WARNING: {warning}")
                md_lines.append("")

        md_lines.append("---")
        md_lines.append("")
        if report["overall_valid"]:
            md_lines.append("**WORKSPACE STRUCTURE IS VALID**")
        else:
            md_lines.append("**WORKSPACE STRUCTURE HAS VIOLATIONS**")
            md_lines.append("")
            md_lines.append("Run `python scripts/tidy/tidy_up.py --execute` to fix issues.")

        args.markdown_output.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"Markdown report written to: {args.markdown_output}")

    # Exit with appropriate code
    return 0 if report["overall_valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
