"""Subprocess output streaming utilities to prevent RAM spikes during parallel runs.

Per PARALLEL_RUNS_HARDENING_STATUS.md Priority 3:
- Stream subprocess stdout/stderr to log files instead of capturing in memory
- Return log_path + bounded tail excerpt
- Critical for long-running parallel jobs with large outputs

Usage:
    result = run_with_streaming(
        command=["pytest", "tests/"],
        log_path=Path(".autonomous_runs/run-001/ci/pytest.log"),
        timeout=120
    )

    if result.returncode == 0:
        print(f"Success! Log: {result.log_path}")
        print(f"Last lines:\n{result.tail}")
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreamedProcessResult:
    """Result from subprocess execution with streamed output."""

    returncode: int
    log_path: Path
    tail: str  # Last N lines for quick inspection
    command: List[str]
    timeout_occurred: bool = False


def read_last_n_lines(file_path: Path, n: int = 50, encoding: str = "utf-8") -> str:
    """Read last N lines from a file efficiently.

    Args:
        file_path: Path to file
        n: Number of lines to read from end
        encoding: File encoding

    Returns:
        Last N lines as string
    """
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            lines = f.readlines()
            tail_lines = lines[-n:] if len(lines) > n else lines
            return "".join(tail_lines)
    except Exception as e:
        logger.warning(f"Failed to read tail from {file_path}: {e}")
        return f"(Failed to read tail: {e})"


def run_with_streaming(
    command: List[str],
    log_path: Path,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    timeout: Optional[int] = None,
    tail_lines: int = 50,
    encoding: str = "utf-8",
) -> StreamedProcessResult:
    """Run subprocess with stdout/stderr streamed to log file.

    Args:
        command: Command to execute as list
        log_path: Path where stdout+stderr will be written
        cwd: Working directory for subprocess
        env: Environment variables (None = inherit)
        timeout: Timeout in seconds (None = no timeout)
        tail_lines: Number of lines to return in tail (default: 50)
        encoding: Output encoding (default: utf-8)

    Returns:
        StreamedProcessResult with returncode, log_path, and tail

    Raises:
        subprocess.TimeoutExpired: If timeout is exceeded (result still available)
    """
    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug(
        f"[StreamingSubprocess] Running command: {' '.join(command)}\n"
        f"  Log: {log_path}\n"
        f"  Timeout: {timeout}s"
    )

    timeout_occurred = False
    returncode = -1

    try:
        # Open log file for writing (stdout + stderr merged)
        with open(log_path, "w", encoding=encoding, errors="replace") as log_file:
            process = subprocess.run(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                cwd=cwd,
                env=env,
                timeout=timeout,
                encoding=encoding,
                errors="replace",
            )
            returncode = process.returncode

    except subprocess.TimeoutExpired:
        logger.warning(f"[StreamingSubprocess] Command timed out after {timeout}s: {command}")
        timeout_occurred = True
        returncode = -1  # Indicate timeout failure

        # Append timeout message to log
        try:
            with open(log_path, "a", encoding=encoding) as log_file:
                log_file.write(
                    f"\n\n[TIMEOUT] Process exceeded {timeout}s timeout and was terminated.\n"
                )
        except Exception as append_error:
            logger.error(f"Failed to append timeout message to log: {append_error}")

    except Exception as e:
        logger.error(f"[StreamingSubprocess] Command failed: {e}", exc_info=True)
        returncode = -1

        # Append error message to log
        try:
            with open(log_path, "a", encoding=encoding) as log_file:
                log_file.write(f"\n\n[ERROR] Process execution failed: {e}\n")
        except Exception as append_error:
            logger.error(f"Failed to append error message to log: {append_error}")

    # Read tail from log file
    tail = read_last_n_lines(log_path, n=tail_lines, encoding=encoding)

    result = StreamedProcessResult(
        returncode=returncode,
        log_path=log_path,
        tail=tail,
        command=command,
        timeout_occurred=timeout_occurred,
    )

    logger.debug(
        f"[StreamingSubprocess] Command completed: returncode={returncode}, "
        f"timeout={timeout_occurred}, log={log_path}"
    )

    return result


def run_with_streaming_legacy_compat(
    command: List[str],
    log_path: Path,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    timeout: Optional[int] = None,
    tail_lines: int = 50,
    encoding: str = "utf-8",
) -> dict:
    """Legacy-compatible wrapper that returns dict matching subprocess.run interface.

    This function provides backward compatibility for code expecting subprocess.run results
    by returning a dict with stdout/stderr fields containing bounded tail excerpts.

    Args:
        command: Command to execute as list
        log_path: Path where stdout+stderr will be written
        cwd: Working directory for subprocess
        env: Environment variables (None = inherit)
        timeout: Timeout in seconds (None = no timeout)
        tail_lines: Number of lines to return in tail (default: 50)
        encoding: Output encoding (default: utf-8)

    Returns:
        Dict with: returncode, stdout (tail), stderr (empty), log_path (str)
    """
    result = run_with_streaming(
        command=command,
        log_path=log_path,
        cwd=cwd,
        env=env,
        timeout=timeout,
        tail_lines=tail_lines,
        encoding=encoding,
    )

    # Return legacy-compatible dict
    return {
        "returncode": result.returncode,
        "stdout": result.tail,  # Bounded tail instead of full output
        "stderr": "",  # Merged into stdout in log file
        "log_path": str(result.log_path),  # Path for full output
        "timeout_occurred": result.timeout_occurred,
    }
