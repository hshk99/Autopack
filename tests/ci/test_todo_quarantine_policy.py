"""TODO quarantine policy contract tests (PR10).

Ensures runtime code has minimal/zero TODOs while allowing flexibility
in scripts and tests. Critical runtime paths must have zero TODOs.

Contract: Runtime code must be complete - no placeholder behavior.
"""

import re
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
POLICY_FILE = REPO_ROOT / "config" / "todo_policy.yaml"


def load_policy() -> dict:
    """Load the TODO quarantine policy."""
    with open(POLICY_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_todos_in_file(file_path: Path) -> List[Tuple[int, str]]:
    """Find all TODO/FIXME/XXX markers in a file.

    Returns list of (line_number, line_content) tuples.

    Note: Only matches actual TODO markers, not words that happen to contain
    these letters (e.g., "fileorg-xxx" should not match XXX).
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    # Match TODO/FIXME patterns - must be followed by colon, whitespace, or EOL
    # Match XXX only when it's a standalone marker (not part of placeholder like "xxx")
    todo_pattern = re.compile(
        r"(?:\bTODO\b|\bFIXME\b)(?:\s*:|.*$)|"  # TODO: or FIXME: or TODO followed by anything
        r"#\s*XXX\b",  # XXX only when it's a comment marker (# XXX)
        re.IGNORECASE
    )

    todos = []
    for i, line in enumerate(content.split("\n"), 1):
        if todo_pattern.search(line):
            todos.append((i, line.strip()))

    return todos


def matches_pattern(path: Path, pattern: str) -> bool:
    """Check if path matches a glob-like pattern."""
    # Convert pattern to regex-friendly format
    pattern_parts = pattern.replace("**", "__DOUBLESTAR__").replace("*", "[^/]*")
    pattern_parts = pattern_parts.replace("__DOUBLESTAR__", ".*")
    regex = f"^{pattern_parts}$"

    # Normalize path separators
    path_str = str(path.relative_to(REPO_ROOT)).replace("\\", "/")

    return bool(re.match(regex, path_str))


def is_quarantined(path: Path, quarantined_patterns: List[str]) -> bool:
    """Check if a path is in a quarantined area."""
    for pattern in quarantined_patterns:
        if matches_pattern(path, pattern):
            return True
    return False


class TestTodoPolicyExists:
    """Verify the TODO policy file exists and is valid."""

    def test_policy_file_exists(self):
        """config/todo_policy.yaml must exist."""
        assert POLICY_FILE.exists(), (
            "config/todo_policy.yaml not found - "
            "TODO quarantine policy must be documented"
        )

    def test_policy_is_valid_yaml(self):
        """Policy must be valid YAML."""
        policy = load_policy()
        assert policy is not None, "Policy is empty or invalid YAML"
        assert "policy" in policy, "Policy must have a 'policy' section"

    def test_policy_has_limits(self):
        """Policy must define limits for each category."""
        policy = load_policy()
        limits = policy.get("policy", {}).get("limits", {})

        required_categories = ["runtime_critical", "runtime_other", "scripts", "tests"]
        for category in required_categories:
            assert category in limits, f"Missing limit for category: {category}"
            assert "max_todos" in limits[category], f"Missing max_todos for: {category}"


class TestRuntimeCriticalTodos:
    """Verify critical runtime paths have zero TODOs."""

    def test_main_py_has_no_todos(self):
        """src/autopack/main.py must have zero TODOs."""
        main_py = REPO_ROOT / "src" / "autopack" / "main.py"
        if not main_py.exists():
            pytest.skip("main.py not found")

        todos = find_todos_in_file(main_py)
        assert not todos, (
            f"main.py has {len(todos)} TODOs - critical runtime must be complete:\n"
            + "\n".join(f"  Line {n}: {line}" for n, line in todos)
        )

    def test_autonomous_executor_has_no_todos(self):
        """src/autopack/autonomous_executor.py must have zero TODOs."""
        executor = REPO_ROOT / "src" / "autopack" / "autonomous_executor.py"
        if not executor.exists():
            pytest.skip("autonomous_executor.py not found")

        todos = find_todos_in_file(executor)
        assert not todos, (
            f"autonomous_executor.py has {len(todos)} TODOs - "
            f"executor must be deterministic:\n"
            + "\n".join(f"  Line {n}: {line}" for n, line in todos)
        )

    def test_governed_apply_has_no_todos(self):
        """src/autopack/governed_apply.py must have zero TODOs."""
        governed = REPO_ROOT / "src" / "autopack" / "governed_apply.py"
        if not governed.exists():
            pytest.skip("governed_apply.py not found")

        todos = find_todos_in_file(governed)
        assert not todos, (
            f"governed_apply.py has {len(todos)} TODOs - "
            f"governance must be complete:\n"
            + "\n".join(f"  Line {n}: {line}" for n, line in todos)
        )

    def test_auth_modules_have_no_todos(self):
        """src/autopack/auth/**/*.py must have zero TODOs."""
        auth_dir = REPO_ROOT / "src" / "autopack" / "auth"
        if not auth_dir.exists():
            pytest.skip("auth directory not found")

        all_todos = []
        for py_file in auth_dir.rglob("*.py"):
            todos = find_todos_in_file(py_file)
            for line_num, line in todos:
                all_todos.append(f"{py_file.name}:{line_num}: {line}")

        assert not all_todos, (
            f"Auth modules have {len(all_todos)} TODOs - "
            f"authentication must be complete:\n"
            + "\n".join(f"  {todo}" for todo in all_todos)
        )


class TestRuntimeOtherTodos:
    """Verify other runtime code stays under TODO limit."""

    def test_runtime_todo_count_under_limit(self):
        """src/autopack/**/*.py must have limited TODOs."""
        policy = load_policy()
        limit = policy["policy"]["limits"]["runtime_other"]["max_todos"]
        quarantined = policy["policy"].get("quarantined_paths", [])

        src_dir = REPO_ROOT / "src" / "autopack"
        if not src_dir.exists():
            pytest.skip("src/autopack not found")

        all_todos = []
        for py_file in src_dir.rglob("*.py"):
            # Skip quarantined paths
            if is_quarantined(py_file, quarantined):
                continue

            todos = find_todos_in_file(py_file)
            for line_num, line in todos:
                rel_path = py_file.relative_to(REPO_ROOT)
                all_todos.append(f"{rel_path}:{line_num}: {line}")

        assert len(all_todos) <= limit, (
            f"Runtime code has {len(all_todos)} TODOs (limit: {limit}):\n"
            + "\n".join(f"  {todo}" for todo in all_todos[:20])
            + (f"\n  ... and {len(all_todos) - 20} more" if len(all_todos) > 20 else "")
        )


class TestSecurityTodosBlocked:
    """Verify no security-related TODOs exist anywhere."""

    def test_no_security_todos_in_runtime(self):
        """No TODOs mentioning 'security', 'secret', 'auth', 'credential'."""
        policy = load_policy()
        urgent_patterns = policy["policy"].get("urgent_patterns", [])

        src_dir = REPO_ROOT / "src" / "autopack"
        if not src_dir.exists():
            pytest.skip("src/autopack not found")

        security_todos = []
        for py_file in src_dir.rglob("*.py"):
            todos = find_todos_in_file(py_file)
            for line_num, line in todos:
                # Check if line matches any urgent pattern
                for pattern in urgent_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        rel_path = py_file.relative_to(REPO_ROOT)
                        security_todos.append(f"{rel_path}:{line_num}: {line}")
                        break

        assert not security_todos, (
            "Security-related TODOs found (must be addressed immediately):\n"
            + "\n".join(f"  {todo}" for todo in security_todos)
        )


class TestScriptsTodosTracked:
    """Track but don't block script TODOs."""

    def test_scripts_todo_count_tracked(self):
        """scripts/**/*.py TODO count is tracked in baseline."""
        policy = load_policy()
        baseline_count = policy.get("baseline", {}).get("counts", {}).get("scripts", 0)

        scripts_dir = REPO_ROOT / "scripts"
        if not scripts_dir.exists():
            pytest.skip("scripts directory not found")

        all_todos = []
        for py_file in scripts_dir.rglob("*.py"):
            todos = find_todos_in_file(py_file)
            all_todos.extend(todos)

        # This is informational - we track but don't necessarily fail
        current_count = len(all_todos)

        # Warn if count increased significantly from baseline
        if current_count > baseline_count * 1.2:  # 20% tolerance
            pytest.xfail(
                f"Script TODOs increased from baseline {baseline_count} to {current_count}. "
                f"Consider addressing some before adding more."
            )


class TestQuarantinedPathsRespected:
    """Verify quarantined paths are correctly identified."""

    def test_research_is_quarantined(self):
        """src/autopack/research/** should be quarantined."""
        policy = load_policy()
        quarantined = policy["policy"].get("quarantined_paths", [])

        research_path = REPO_ROOT / "src" / "autopack" / "research" / "api" / "router.py"
        assert is_quarantined(research_path, quarantined), (
            "Research subsystem should be quarantined (TODOs allowed)"
        )

    def test_archive_is_quarantined(self):
        """archive/** should be quarantined."""
        policy = load_policy()
        quarantined = policy["policy"].get("quarantined_paths", [])

        archive_path = REPO_ROOT / "archive" / "some_file.py"
        assert is_quarantined(archive_path, quarantined), (
            "Archive should be quarantined (historical files)"
        )


class TestClosurePlanDocumented:
    """Verify closure plan is documented."""

    def test_closure_plan_exists(self):
        """Policy must have a closure plan."""
        policy = load_policy()
        closure_plan = policy.get("closure_plan", {})

        assert "must_close" in closure_plan, "Closure plan must have 'must_close' items"
        assert len(closure_plan["must_close"]) > 0, "Must-close list cannot be empty"

    def test_security_todos_in_must_close(self):
        """Security TODOs must be in the must-close plan."""
        policy = load_policy()
        must_close = policy.get("closure_plan", {}).get("must_close", [])

        security_item = None
        for item in must_close:
            if "security" in item.get("description", "").lower():
                security_item = item
                break

        assert security_item is not None, (
            "Security-related TODOs must be in the must-close plan"
        )
        assert security_item.get("deadline") == "Immediate", (
            "Security TODOs must have 'Immediate' deadline"
        )
