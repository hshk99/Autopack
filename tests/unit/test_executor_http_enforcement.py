"""
Enforcement test: "executor never talks raw HTTP" (BUILD-135).

Phase 2: Full enforcement across all executor code.

This test ensures:
- NO module under `src/autopack/executor/` makes direct `requests.*` calls
- `src/autopack/autonomous_executor.py` also uses `SupervisorApiClient` (migrated in PR #142)

Why this is useful:
- Prevents the raw-HTTP pattern from spreading to any executor code
- All HTTP communication flows through the typed SupervisorApiClient
- HTTP concerns are isolated to a single, testable boundary

Allowed raw HTTP zones:
- `src/autopack/supervisor/api_client.py` — The ONLY place `requests.*` should exist
  for executor-to-supervisor communication. All other executor code must use this client.
- Future contributors: If you need to add HTTP transport, extend SupervisorApiClient
  rather than adding raw `requests.*` calls elsewhere.
"""

import re
from pathlib import Path


RAW_HTTP_PATTERN = re.compile(r"\brequests\.(get|post|put|patch|delete|request)\s*\(")


def _is_raw_http_violation_line(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return False
    return bool(RAW_HTTP_PATTERN.search(line))


def _find_raw_http_violations(path: Path) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if _is_raw_http_violation_line(line):
            violations.append((idx, stripped))
    return violations


def test_executor_package_never_uses_raw_http_requests():
    """
    BUILD-135 (Phase 2): no raw `requests.*` calls in any executor code.

    Enforces on:
    - `src/autopack/executor/` package (all modules)
    - `src/autopack/autonomous_executor.py` (migrated in PR #142)
    """
    executor_pkg = Path("src/autopack/executor")
    assert executor_pkg.exists(), f"Executor package not found at {executor_pkg}"

    all_violations: list[tuple[Path, int, str]] = []

    # Check executor package
    for py_file in sorted(executor_pkg.rglob("*.py")):
        for line_no, line in _find_raw_http_violations(py_file):
            all_violations.append((py_file, line_no, line))

    # Check autonomous_executor.py (Phase 2: now included)
    autonomous_executor = Path("src/autopack/autonomous_executor.py")
    if autonomous_executor.exists():
        for line_no, line in _find_raw_http_violations(autonomous_executor):
            all_violations.append((autonomous_executor, line_no, line))

    if all_violations:
        lines = [
            "",
            "=" * 80,
            "BUILD-135 VIOLATION: executor package uses raw HTTP (requests.*)",
            "=" * 80,
            "",
            "Raw HTTP must be isolated behind SupervisorApiClient. Offending lines:",
            "",
        ]
        for path, line_no, line in all_violations:
            lines.append(f"  {path.as_posix()}:{line_no}: {line[:120]}")
        lines.append("")
        lines.append(
            "Fix: route calls through SupervisorApiClient (src/autopack/supervisor/api_client.py)."
        )
        lines.append("=" * 80)
        assert False, "\n".join(lines)


def test_executor_http_enforcement_test_is_comprehensive():
    """
    Meta-test: Verify that the enforcement test can detect violations.

    This ensures the grep pattern works correctly by testing it against
    known patterns that should and should not trigger violations.
    """
    # Should match (violations)
    violations = [
        "response = requests.get(url, headers=headers)",
        '    requests.post(f"{api_url}/runs", json=data)',
        "result = requests.put(endpoint, timeout=30)",
        "  resp = requests.delete(url)",
        "    response = requests.request('GET', url)",
    ]

    for code in violations:
        assert _is_raw_http_violation_line(code), f"Pattern should match: {code}"

    # Should NOT match (allowed)
    allowed = [
        "import requests",
        "from requests import Timeout",
        "# requests.get() is deprecated, use SupervisorApiClient",
        "except requests.HTTPError as e:",
        "client.check_health()  # internally uses requests",
        "self.api_client.get_run(run_id)",
    ]

    for code in allowed:
        assert not _is_raw_http_violation_line(code), f"Pattern should NOT match: {code}"
