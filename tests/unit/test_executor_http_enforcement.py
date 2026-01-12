"""
Enforcement test: Executor never talks raw HTTP (BUILD-135).

This test ensures that autonomous_executor.py uses only the SupervisorApiClient
abstraction and never makes direct requests.* calls. This prevents:
- Scattered HTTP logic across the executor
- Inconsistent error handling
- Difficult testing (cannot mock/inject)
- Drift in URL construction patterns

Rationale (from IMPROVEMENT_GAPS_CURRENT_2026-01-12.md Section 1.3):
  "Prevent gaps reappearing by codifying recurring drift vectors"
  "Executor never talks raw HTTP: enforce that autonomous_executor.py only uses
   SupervisorApiClient (one grep-based test can enforce this if desired)."

This test will FAIL if someone adds direct HTTP calls to the executor.
"""

import re
from pathlib import Path


def test_executor_never_uses_raw_http_requests():
    """
    autonomous_executor.py must use SupervisorApiClient, not requests.* directly.

    This is a grep-based contract test that prevents drift where someone
    bypasses the client abstraction and adds raw HTTP calls.

    Allowed:
    - `import requests` (needed for type hints, exceptions)
    - `SupervisorApiClient` usage
    - Comments mentioning "requests."

    Not allowed:
    - `requests.get(...)`, `requests.post(...)`, etc in actual code

    BUILD-135: All HTTP communication should go through SupervisorApiClient.
    """
    executor_path = Path("src/autopack/autonomous_executor.py")
    assert executor_path.exists(), f"Executor not found at {executor_path}"

    content = executor_path.read_text(encoding="utf-8")

    # Pattern: requests.{get|post|put|patch|delete|request}(
    # This catches direct HTTP calls but not imports or comments
    # Negative lookbehind (?<!#) ensures we don't match lines that start with # (after optional whitespace)
    raw_http_pattern = re.compile(
        r"^\s*(?!#).*\brequests\.(get|post|put|patch|delete|request)\s*\(", re.MULTILINE
    )

    violations = []
    for match in raw_http_pattern.finditer(content):
        # Extract line number and context
        line_number = content[: match.start()].count("\n") + 1
        line_start = content.rfind("\n", 0, match.start()) + 1
        line_end = content.find("\n", match.start())
        if line_end == -1:
            line_end = len(content)
        line_text = content[line_start:line_end].strip()

        violations.append((line_number, line_text))

    # Construct error message with all violations
    if violations:
        error_lines = [
            "\n",
            "=" * 80,
            "BUILD-135 VIOLATION: Executor uses raw HTTP calls instead of SupervisorApiClient",
            "=" * 80,
            "",
            "The following lines in autonomous_executor.py make direct requests.* calls:",
            "",
        ]
        for line_num, line_text in violations:
            error_lines.append(f"  Line {line_num}: {line_text[:100]}")

        error_lines.extend(
            [
                "",
                "Fix: Replace with SupervisorApiClient methods:",
                '  - requests.get(f"{self.api_url}/health") → self.api_client.check_health()',
                "  - requests.post(..., json=payload) → self.api_client.update_phase_status(...)",
                "",
                "See: src/autopack/supervisor/api_client.py for available methods",
                "See: IMPROVEMENT_GAPS_CURRENT_2026-01-12.md Section 1.3 for rationale",
                "=" * 80,
            ]
        )

        assert False, "\n".join(error_lines)


def test_executor_http_enforcement_test_is_comprehensive():
    """
    Meta-test: Verify that the enforcement test can detect violations.

    This ensures the grep pattern works correctly by testing it against
    known patterns that should and should not trigger violations.
    """
    # Pattern from the main test
    raw_http_pattern = re.compile(
        r"^\s*(?!#).*\brequests\.(get|post|put|patch|delete|request)\s*\(", re.MULTILINE
    )

    # Should match (violations)
    violations = [
        "response = requests.get(url, headers=headers)",
        '    requests.post(f"{api_url}/runs", json=data)',
        "result = requests.put(endpoint, timeout=30)",
        "  resp = requests.delete(url)",
        "    response = requests.request('GET', url)",
    ]

    for code in violations:
        assert raw_http_pattern.search(code), f"Pattern should match: {code}"

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
        assert not raw_http_pattern.search(code), f"Pattern should NOT match: {code}"
