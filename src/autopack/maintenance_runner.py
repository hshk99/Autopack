"""
Maintenance test executor for backlog items.

Runs targeted tests (if provided) and summarizes results for auditor input.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class TestExecResult:
    name: str
    status: str  # passed|failed|skipped|error
    stdout: str
    stderr: str


def run_tests(
    test_commands: List[str], workspace: Path, timeout: int = 600
) -> List[TestExecResult]:
    results: List[TestExecResult] = []
    for cmd in test_commands:
        try:
            # Parse command string into argument list safely (prevents shell injection)
            args = shlex.split(cmd)
            proc = subprocess.run(
                args,
                shell=False,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            status = "passed" if proc.returncode == 0 else "failed"
            results.append(
                TestExecResult(
                    name=cmd,
                    status=status,
                    stdout=proc.stdout or "",
                    stderr=proc.stderr or "",
                )
            )
        except subprocess.TimeoutExpired as e:
            results.append(
                TestExecResult(
                    name=cmd,
                    status="error",
                    stdout=getattr(e, "stdout", "") or "",
                    stderr="timeout",
                )
            )
        except Exception as e:  # pragma: no cover
            results.append(
                TestExecResult(
                    name=cmd,
                    status="error",
                    stdout="",
                    stderr=str(e),
                )
            )
    return results
