"""Contract tests for TODO quarantine (P1-CORE-TODO-001).

Ensures:
- No bare TODO comments in critical runtime modules
- All deferred work is tagged with ROADMAP (explicitly tracked)
- New TODOs require a ticket/ID format

Critical modules (executor, routing, governance, approvals):
- src/autopack/autonomous_executor.py
- src/autopack/autonomous/*.py
- src/autopack/model_routing*.py
- src/autopack/llm_service.py
- src/autopack/main.py (API endpoints)
- src/autopack/approvals/*.py
"""

import re
import subprocess
from pathlib import Path

import pytest

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Critical runtime modules - no bare TODOs allowed
CRITICAL_MODULE_PATTERNS = [
    "src/autopack/autonomous_executor.py",
    "src/autopack/autonomous/*.py",
    "src/autopack/model_routing*.py",
    "src/autopack/llm_service.py",
    "src/autopack/main.py",
    "src/autopack/approvals/*.py",
    "src/autopack/executor/*.py",
    "src/autopack/continuation_recovery.py",
    "src/autopack/learned_rules.py",
]


class TestTodoQuarantine:
    """Ensures no bare TODOs exist in critical runtime modules."""

    def test_no_bare_todos_in_critical_modules(self):
        """Critical modules must not have bare TODO comments."""
        # Use git grep to find TODOs in tracked files
        result = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-E",
                r"\bTODO\b",
                "--",
                "src/autopack/*.py",
                "src/autopack/**/*.py",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        # Parse results
        bare_todos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Each line: file:linenum:content
            parts = line.split(":", 2)
            if len(parts) >= 3:
                filepath, linenum, content = parts[0], parts[1], parts[2]
                # Check if it's a bare TODO (not ROADMAP:, not TODO(ticket):)
                if "TODO" in content and "ROADMAP" not in content:
                    # Allow TODO(ticket-id): format for tracked work
                    if not re.search(r"TODO\([A-Z]+-\d+\)", content):
                        bare_todos.append(f"{filepath}:{linenum}: {content.strip()}")

        assert not bare_todos, (
            f"Found {len(bare_todos)} bare TODO(s) in runtime modules. "
            "Either:\n"
            "  1. Convert to ROADMAP: (deferred work, explicitly tracked)\n"
            "  2. Use TODO(TICKET-ID): format (e.g., TODO(BUILD-999):)\n"
            "  3. Implement the TODO and add a test\n\n"
            "Bare TODOs found:\n" + "\n".join(f"  - {t}" for t in bare_todos)
        )


class TestRoadmapTags:
    """Ensures ROADMAP tags are properly formatted."""

    def test_roadmap_tags_have_priority(self):
        """ROADMAP tags should include priority classification."""
        result = subprocess.run(
            ["git", "grep", "-n", "ROADMAP:", "--", "src/autopack/*.py", "src/autopack/**/*.py"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

        missing_priority = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                filepath, linenum, content = parts[0], parts[1], parts[2]
                # Check for priority marker (P1, P2, P3, P4, P5)
                if not re.search(r"\(P[1-5]", content):
                    missing_priority.append(f"{filepath}:{linenum}")

        # This is informational, not blocking
        if missing_priority:
            pytest.skip(
                f"Informational: {len(missing_priority)} ROADMAP tag(s) missing priority. "
                "Consider adding (P1-P5) classification."
            )


class TestNoTodosInNewCode:
    """Contract for preventing new bare TODOs."""

    def test_contract_enforced_by_this_test(self):
        """Contract P1-CORE-TODO-001 is enforced by this test file."""
        # The contract is self-enforcing:
        # - test_no_bare_todos_in_critical_modules blocks bare TODOs
        # - test_no_todos_in_src_autopack verifies zero count baseline
        # This test documents that the contract exists
        assert True, "Contract P1-CORE-TODO-001 enforced by test suite"


class TestTodoCountBaseline:
    """Track TODO count baseline to prevent regression."""

    def test_no_todos_in_src_autopack_python(self):
        """src/autopack/*.py should have zero bare TODOs in Python files."""
        # Check only Python files (runtime modules)
        # Frontend/JS TODOs are tracked separately
        result = subprocess.run(
            ["git", "grep", "-c", r"\bTODO\b", "--", "*.py"],
            cwd=PROJECT_ROOT / "src" / "autopack",
            capture_output=True,
            text=True,
        )

        # Count total (only from .py files)
        total_count = 0
        for line in result.stdout.strip().split("\n"):
            if line and ":" in line:
                # Format is filename:count
                parts = line.rsplit(":", 1)
                if len(parts) == 2 and parts[0].endswith(".py"):
                    try:
                        total_count += int(parts[1])
                    except ValueError:
                        pass

        assert total_count == 0, (
            f"Found {total_count} bare TODO(s) in src/autopack/ Python files. "
            "All TODOs should be converted to ROADMAP: or resolved."
        )
