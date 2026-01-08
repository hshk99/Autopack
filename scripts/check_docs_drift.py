#!/usr/bin/env python3
"""CI script to detect documentation drift.

BUILD-146 P12 API Consolidation - Phase 4 + BUILD-195 comprehensive sweeps:
Prevents re-introduction of legacy patterns in documentation.

Drift categories detected:
1. Backend server / uvicorn target drift (BUILD-146)
2. Env template drift (.env.example vs docs/templates/env.example)
3. Compose service-name drift (api/postgres vs backend/db)
4. Run-layout drift (.autonomous_runs/<run_id> vs project/family/run_id)

Exit codes:
    0: No drift detected
    1: Drift detected
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns to detect (these indicate drift back to legacy patterns)
FORBIDDEN_PATTERNS = [
    # === BUILD-146: Backend server / uvicorn drift ===
    # Direct backend server uvicorn commands
    (r"uvicorn\s+backend\.main:app", "Direct backend.main:app uvicorn command"),
    (r"uvicorn\s+src\.backend\.main:app", "Direct src.backend.main:app uvicorn command"),

    # BUILD-189: Legacy uvicorn targets without PYTHONPATH
    # Correct: PYTHONPATH=src uvicorn autopack.main:app
    # Wrong: uvicorn src.autopack.main:app (needs PYTHONPATH, not dotted src path)
    # Note: We check for src.autopack.main:app pattern - false positives with PYTHONPATH= prefix
    # are acceptable since they should use autopack.main:app anyway
    (r"uvicorn\s+src\.autopack\.main:app",
     "Legacy uvicorn src.autopack.main:app (should be PYTHONPATH=src uvicorn autopack.main:app)"),
    (r'"uvicorn",\s*"src\.autopack\.main:app"',
     "Legacy Docker CMD with src.autopack.main:app (should be autopack.main:app with PYTHONPATH env)"),

    # BUILD-189: Legacy autopack.api.server entrypoint (deprecated)
    # This was the old API server before consolidation
    (r"uvicorn\s+autopack\.api\.server:app",
     "Legacy uvicorn autopack.api.server:app (should be autopack.main:app)"),
    (r"python\s+-m\s+autopack\.api\.server",
     "Legacy python -m autopack.api.server (should use autopack.main)"),

    # Python module execution of backend main
    (r"python\s+-m\s+backend\.main", "Direct python -m backend.main"),
    (r"python\s+src/backend/main\.py", "Direct python src/backend/main.py"),
    (r"python\s+src\\backend\\main\.py", "Direct python src\\backend\\main.py (Windows)"),

    # Backend server recommendation language
    (r"run\s+the\s+backend\s+server", "Instruction to run backend server"),
    (r"start\s+the\s+backend\s+server", "Instruction to start backend server"),
    (r"use\s+the\s+backend\s+server", "Recommendation to use backend server"),

    # BUILD-146 P12 Phase 5: Auth endpoints must be at /api/auth/* (not root paths)
    # These patterns detect auth endpoints at wrong paths
    (r"POST\s+/register\b", "Auth endpoint at wrong path (should be /api/auth/register)"),
    (r"POST\s+/login\b", "Auth endpoint at wrong path (should be /api/auth/login)"),
    (r"GET\s+/me\b", "Auth endpoint at wrong path (should be /api/auth/me)"),
    (r"from\s+backend\.api\.auth", "Import from deprecated backend.api.auth (use autopack.auth)"),
    (r"import\s+backend\.api\.auth", "Import from deprecated backend.api.auth (use autopack.auth)"),

    # === BUILD-195: Env template drift ===
    # Canonical template is docs/templates/env.example, not .env.example
    (r"cp\s+\.env\.example\s+\.env",
     "Env template drift (should be: cp docs/templates/env.example .env)"),

    # === BUILD-195: Compose service-name drift ===
    # Services are: backend (not api), db (not postgres)
    (r"docker-compose\s+logs\s+-f\s+api\b",
     "Compose service-name drift (should be: docker-compose logs -f backend)"),
    (r"docker-compose\s+up\s+.*\s+postgres\b",
     "Compose service-name drift (should be: docker-compose up ... db)"),
    (r"docker-compose\s+restart\s+postgres\b",
     "Compose service-name drift (should be: docker-compose restart db)"),

    # === BUILD-195: Run-layout drift ===
    # Canonical: .autonomous_runs/<project>/runs/<family>/<run_id>/...
    # Legacy: .autonomous_runs/<run_id>/... (missing project/family hierarchy)
    # Note: We detect the legacy pattern in instructional contexts (not historical records)
    (r"\.autonomous_runs/<run_id>",
     "Run-layout drift (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/ via RunFileLayout)"),
    (r"\.autonomous_runs/\{run_id\}",
     "Run-layout drift (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/ via RunFileLayout)"),
    (r"\.autonomous_runs/\$\{run_id\}",
     "Run-layout drift (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/ via RunFileLayout)"),
]

# Files/directories to exclude from checking
EXCLUDED_PATHS = [
    # API consolidation migration docs (document both old and new)
    "docs/CANONICAL_API_CONSOLIDATION_PLAN.md",
    "docs/API_CONSOLIDATION_COMPLETION_SUMMARY.md",
    "docs/CANONICAL_API_CONTRACT.md",

    # Historical records (legitimately contain legacy patterns)
    "docs/BUILD_HISTORY.md",
    "docs/DEBUG_LOG.md",
    "docs/CHANGELOG.md",
    "docs/ARCHITECTURE_DECISIONS.md",  # Decision records document evolution

    # Gap analysis and cursor prompts (discuss drift patterns)
    "docs/IMPROVEMENTS_GAP_ANALYSIS.md",
    "docs/IMPROVEMENTS_AUDIT.md",
    "docs/CURSOR_PROMPT_IMPLEMENT_IMPROVEMENTS_GAP_ANALYSIS.md",
    "docs/CURSOR_PROMPT_EXECUTE_IMPLEMENT_IMPROVEMENTS_GAP_ANALYSIS.md",
    "docs/CURSOR_PROMPT_IMPLEMENT_P0_BROKEN.md",
    "docs/FURTHER_IMPROVEMENTS_COMPREHENSIVE_SCAN",

    # Implementation plans and completion summaries (historical, describe evolution)
    "docs/IMPLEMENTATION_PLAN_INTENTION_ANCHOR_CONSOLIDATION.md",
    "docs/IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md",
    "docs/INTENTION_ANCHOR_COMPLETION_SUMMARY.md",
    "docs/P0_RELIABILITY_DECISIONS.md",

    # Self-reference
    "scripts/check_docs_drift.py",

    # Build artifacts and caches
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",

    # Archives (historical content)
    "archive",

    # Runtime artifacts (generated, not canonical docs)
    ".autonomous_runs",
    ".autopack",
]


def should_check_file(file_path: Path) -> bool:
    """Determine if file should be checked for drift."""
    # Normalize path separators for cross-platform comparison
    normalized_path = str(file_path).replace("\\", "/")

    # Check if any excluded path is in the file path
    for excluded in EXCLUDED_PATHS:
        if excluded in normalized_path:
            return False

    # Only check markdown and text documentation files
    return file_path.suffix in [".md", ".txt", ".rst"]


def check_file_for_drift(file_path: Path) -> List[Tuple[int, str, str]]:
    """Check a single file for backend server references.

    Returns:
        List of (line_number, pattern_description, line_content) tuples
    """
    violations = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Check each forbidden pattern
                for pattern, description in FORBIDDEN_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        violations.append((line_num, description, line.strip()))

    except Exception as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)

    return violations


def main():
    """Main entry point for drift detection."""
    repo_root = Path(__file__).parent.parent
    print(f"Checking for docs drift in: {repo_root}")
    print(f"Forbidden patterns: {len(FORBIDDEN_PATTERNS)}")
    print()

    # Find all documentation files
    doc_files = []
    for pattern in ["**/*.md", "**/*.txt", "**/*.rst"]:
        doc_files.extend(repo_root.glob(pattern))

    # Filter to files we should check
    files_to_check = [f for f in doc_files if should_check_file(f)]
    print(f"Checking {len(files_to_check)} documentation files...")
    print()

    # Check each file
    total_violations = 0
    files_with_violations = 0

    for file_path in files_to_check:
        violations = check_file_for_drift(file_path)

        if violations:
            files_with_violations += 1
            total_violations += len(violations)

            # Print violations for this file
            rel_path = file_path.relative_to(repo_root)
            print(f"DRIFT DETECTED: {rel_path}")

            for line_num, description, line_content in violations:
                print(f"   Line {line_num}: {description}")
                print(f"   > {line_content}")
                print()

    # Summary
    print("=" * 80)
    if total_violations == 0:
        print("SUCCESS: No documentation drift detected!")
        print()
        print("All documentation correctly references:")
        print("  - Canonical server: PYTHONPATH=src uvicorn autopack.main:app")
        print("  - Auth endpoints: /api/auth/* (not root paths)")
        print("  - Auth imports: autopack.auth (not backend.api.auth)")
        print("  - Env template: cp docs/templates/env.example .env")
        print("  - Compose services: backend, db (not api, postgres)")
        print("  - Run layout: .autonomous_runs/<project>/runs/<family>/<run_id>/")
        return 0
    else:
        print(f"FAILURE: Documentation drift detected!")
        print()
        print(f"Found {total_violations} violations in {files_with_violations} files.")
        print()
        print("REQUIRED FIX:")
        print("  1. Canonical server: PYTHONPATH=src uvicorn autopack.main:app")
        print("     NOT: uvicorn backend.main:app (DEPRECATED)")
        print()
        print("  2. Auth endpoints at: /api/auth/* (e.g., /api/auth/login)")
        print("     NOT: root paths (e.g., /login)")
        print()
        print("  3. Auth imports: from autopack.auth import ...")
        print("     NOT: from backend.api.auth import ... (DEPRECATED)")
        print()
        print("See docs/CANONICAL_API_CONTRACT.md for canonical API documentation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
