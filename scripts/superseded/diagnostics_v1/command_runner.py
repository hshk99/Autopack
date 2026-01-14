"""
Governed command execution for diagnostics.

Applies strict allowlist/denylist validation, per-run budgets, timeouts,
redaction, and path scoping before invoking subprocesses. Results are
written to .autonomous_runs/<run_id>/diagnostics for auditability.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from autopack.config import settings


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass
class CommandResult:
    """Captured result from a governed command execution."""

    command: str
    redacted_command: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_sec: float
    timed_out: bool
    skipped: bool
    reason: Optional[str] = None
    artifact_path: Optional[str] = None
    label: Optional[str] = None


@dataclass
class PaletteEntry:
    """Allowlisted command specification."""

    name: str
    pattern: str
    default_timeout: int = 60
    allow_network: bool = False


# --------------------------------------------------------------------------- #
# Command palette + safety controls
# --------------------------------------------------------------------------- #


BANNED_SUBSTRINGS = [
    "rm -rf",
    "sudo",
    "mkfs",
    "dd if=",
    ":(){",
    "shutdown",
    "reboot",
    ">",
    ">>",
    "2>",
    "|",
    "&&",
    "||",
]

BANNED_METACHARACTERS = ["`", "$(", "${", "\n", "\r"]


# Palette intentionally conservative; add commands via explicit patterns only.
COMMAND_PALETTE: List[PaletteEntry] = [
    PaletteEntry("git_status", r"^git\s+status(\s+--short|\s+--porcelain)?$", default_timeout=20),
    PaletteEntry(
        "git_diff",
        r"^git\s+diff(\s+--stat|\s+--shortstat|\s+--name-only)?(\s+--cached)?(\s+[^\s]+)?$",
        default_timeout=40,
    ),
    PaletteEntry("ls", r"^(ls|dir)(\s+[-a-zA-Z0-9]+)?(\s+[^\s]+)?$", default_timeout=15),
    PaletteEntry("find", r"^find\s+[^\s]+\s+-maxdepth\s+\d+\s+-name\s+.+$", default_timeout=40),
    PaletteEntry("du", r"^du\s+-sh\s+[^\s]+$", default_timeout=40),
    PaletteEntry("tail", r"^tail\s+-n\s+\d+\s+.+$", default_timeout=20),
    PaletteEntry("head", r"^head\s+-n\s+\d+\s+.+$", default_timeout=20),
    PaletteEntry(
        "pytest",
        r"^pytest(\s+-q)?(\s+-k\s+\"?[A-Za-z0-9_\-\.\s]+\"?)?(\s+--maxfail=1)?(\s+-x)?(\s+-vv)?(\s+[^\s]+)?$",
        default_timeout=360,
    ),
    PaletteEntry("pip_check", r"^(pip|python\s+-m\s+pip)\s+check$", default_timeout=120),
    PaletteEntry(
        "pip_list", r"^(pip|python\s+-m\s+pip)\s+list(\s+--format=columns)?$", default_timeout=90
    ),
    PaletteEntry(
        "python_site", r"^python\s+-m\s+site(\s+--user-site|\s+--user-base)?$", default_timeout=60
    ),
    PaletteEntry("python_sysconfig", r"^python\s+-m\s+sysconfig$", default_timeout=60),
    PaletteEntry("disk_df", r"^df\s+-h(\s+[^\s]+)?$", default_timeout=30),
    PaletteEntry("disk_usage", r"^du\s+-sh\s+\.$", default_timeout=30),
    PaletteEntry("mem_free", r"^free\s+-h$", default_timeout=20),
    PaletteEntry(
        "curl", r"^curl\s+(-I\s+)?https?://[^\s]+$", default_timeout=60, allow_network=True
    ),
    PaletteEntry(
        "ping", r"^ping\s+(-c|-n)\s+\d+\s+[A-Za-z0-9\.-]+$", default_timeout=40, allow_network=True
    ),
    PaletteEntry(
        "traceroute",
        r"^(traceroute|tracert)\s+[A-Za-z0-9\.-]+$",
        default_timeout=120,
        allow_network=True,
    ),
    PaletteEntry("dig", r"^dig\s+[A-Za-z0-9\.-]+$", default_timeout=60, allow_network=True),
    PaletteEntry(
        "nslookup", r"^nslookup\s+[A-Za-z0-9\.-]+$", default_timeout=60, allow_network=True
    ),
]


# --------------------------------------------------------------------------- #
# Governed runner
# --------------------------------------------------------------------------- #


class GovernedCommandRunner:
    """
    Safe subprocess runner for diagnostics.

    - Validates commands against allowlist/denylist
    - Enforces per-run budgets (count + cumulative time)
    - Redacts secrets in logs
    - Captures stdout/stderr to artifacts
    - Provides optional sandboxed working directory
    """

    def __init__(
        self,
        run_id: str,
        workspace: Path,
        diagnostics_dir: Optional[Path] = None,
        *,
        max_commands: int = 20,
        max_seconds: int = 600,
        default_timeout: int = 90,
        allowed_hosts: Optional[List[str]] = None,
        sandbox_paths: Optional[List[str]] = None,
        process_runner: Optional[
            Callable[[List[str], Dict[str, object]], subprocess.CompletedProcess]
        ] = None,
    ):
        self.run_id = run_id
        self.workspace = workspace.resolve()
        self.default_timeout = default_timeout
        self.max_commands = max_commands
        self.max_seconds = max_seconds
        self.allowed_hosts = allowed_hosts or ["localhost", "127.0.0.1"]
        self._sandbox_paths = sandbox_paths or []
        self._sandbox_prepared = False
        self._process_runner = process_runner or self._default_runner

        base_diag = diagnostics_dir or Path(settings.autonomous_runs_dir) / run_id / "diagnostics"
        self.diagnostics_dir = base_diag.resolve()
        (self.diagnostics_dir / "commands").mkdir(parents=True, exist_ok=True)

        self._command_log_path = self.diagnostics_dir / "command_log.jsonl"
        self._lock = threading.Lock()
        self._command_count = 0
        self._seconds_used = 0.0

    # -------------------------- public API ---------------------------------

    def run(
        self,
        command: str,
        *,
        label: Optional[str] = None,
        timeout: Optional[int] = None,
        allow_network: bool = False,
        sandbox: bool = False,
    ) -> CommandResult:
        """Validate and execute a single command safely."""
        with self._lock:
            if self._command_count >= self.max_commands:
                return self._skipped(command, "command_budget_exhausted", label)
            if self._seconds_used >= self.max_seconds:
                return self._skipped(command, "time_budget_exhausted", label)

            ok, reason = self._validate_command(command, allow_network=allow_network)
            if not ok:
                return self._skipped(command, reason, label)

            palette_entry = self._match_palette(command)
            effective_timeout = timeout or (
                palette_entry.default_timeout if palette_entry else self.default_timeout
            )

            start = time.monotonic()
            try:
                proc = self._process_runner(
                    shlex.split(command),
                    {
                        "cwd": str(self._resolve_workdir(sandbox)),
                        "capture_output": True,
                        "text": True,
                        "timeout": effective_timeout,
                    },
                )
                duration = time.monotonic() - start
                self._command_count += 1
                self._seconds_used += duration

                result = CommandResult(
                    command=command,
                    redacted_command=self._redact(command),
                    exit_code=proc.returncode,
                    stdout=self._redact(proc.stdout or ""),
                    stderr=self._redact(proc.stderr or ""),
                    duration_sec=duration,
                    timed_out=False,
                    skipped=False,
                    artifact_path=None,
                    label=label,
                )
            except subprocess.TimeoutExpired as e:
                duration = time.monotonic() - start
                self._command_count += 1
                self._seconds_used += duration
                result = CommandResult(
                    command=command,
                    redacted_command=self._redact(command),
                    exit_code=None,
                    stdout=self._redact((e.stdout or "").strip() if hasattr(e, "stdout") else ""),
                    stderr=self._redact((e.stderr or "").strip() if hasattr(e, "stderr") else ""),
                    duration_sec=duration,
                    timed_out=True,
                    skipped=False,
                    reason="timeout",
                    label=label,
                )
            except Exception as e:  # pragma: no cover - defensive
                duration = time.monotonic() - start
                self._command_count += 1
                self._seconds_used += duration
                result = CommandResult(
                    command=command,
                    redacted_command=self._redact(command),
                    exit_code=None,
                    stdout="",
                    stderr=str(e),
                    duration_sec=duration,
                    timed_out=False,
                    skipped=False,
                    reason="exception",
                    label=label,
                )

            result.artifact_path = self._write_artifact(result)
            self._append_log(result)
            return result

    # -------------------------- helpers ------------------------------------

    def _skipped(self, command: str, reason: str, label: Optional[str]) -> CommandResult:
        """Return a synthetic result when execution is denied."""
        result = CommandResult(
            command=command,
            redacted_command=self._redact(command),
            exit_code=None,
            stdout="",
            stderr="",
            duration_sec=0.0,
            timed_out=False,
            skipped=True,
            reason=reason,
            artifact_path=None,
            label=label,
        )
        self._append_log(result)
        return result

    def _validate_command(self, command: str, *, allow_network: bool) -> Tuple[bool, str]:
        lowered = command.lower()
        for banned in BANNED_SUBSTRINGS:
            if banned in lowered:
                return False, f"blocked:banned:{banned}"
        for meta in BANNED_METACHARACTERS:
            if meta in command:
                return False, f"blocked:metachar:{meta}"

        palette_entry = self._match_palette(command)
        if not palette_entry:
            return False, "blocked:not_allowlisted"

        if palette_entry.allow_network and not allow_network:
            return False, "blocked:network_disallowed"

        if palette_entry.allow_network and not self._host_is_allowed(command):
            return False, "blocked:host_not_allowlisted"

        path_ok, reason = self._paths_are_scoped(command)
        if not path_ok:
            return False, reason

        return True, ""

    def _paths_are_scoped(self, command: str) -> Tuple[bool, str]:
        """Ensure referenced paths stay within workspace."""
        tokens = shlex.split(command)
        for tok in tokens:
            if tok.startswith("-"):
                continue
            if tok.startswith("http://") or tok.startswith("https://"):
                continue
            if re.match(r"^[A-Za-z0-9\.-]+$", tok):
                # Likely host or simple token, skip
                continue
            if tok in {
                "find",
                "pytest",
                "git",
                "curl",
                "ping",
                "traceroute",
                "tracert",
                "dig",
                "nslookup",
            }:
                continue

            path = self._safe_resolve_path(tok)
            if path and not self._is_within_workspace(path):
                return False, f"blocked:path_out_of_scope:{tok}"
        return True, ""

    def _match_palette(self, command: str) -> Optional[PaletteEntry]:
        for entry in COMMAND_PALETTE:
            if re.match(entry.pattern, command.strip()):
                return entry
        return None

    def _host_is_allowed(self, command: str) -> bool:
        hosts = re.findall(r"https?://([^/\s]+)", command)
        hosts += re.findall(r"\s([A-Za-z0-9\.-]+\.[A-Za-z]{2,})", command)
        for host in hosts:
            normalized = host.split(":")[0]
            if normalized in self.allowed_hosts:
                continue
            return False
        return True if hosts else True

    def _resolve_workdir(self, sandbox: bool) -> Path:
        if not sandbox:
            return self.workspace
        sandbox_dir = self.diagnostics_dir / "sandbox"
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        if not self._sandbox_prepared and self._sandbox_paths:
            self._prepare_sandbox(sandbox_dir)
        return sandbox_dir

    def _prepare_sandbox(self, sandbox_dir: Path) -> None:
        """Create a lightweight copy of selected paths inside sandbox."""
        for rel in self._sandbox_paths:
            resolved = self._safe_resolve_path(rel)
            if not resolved or not self._is_within_workspace(resolved):
                continue
            target = sandbox_dir / Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            if resolved.is_dir():
                shutil.copytree(resolved, target, dirs_exist_ok=True)
            elif resolved.is_file():
                shutil.copy2(resolved, target)
        self._sandbox_prepared = True

    def _safe_resolve_path(self, maybe_path: str) -> Optional[Path]:
        try:
            p = Path(maybe_path)
            if not p.is_absolute():
                p = (self.workspace / p).resolve()
            return p
        except Exception:
            return None

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace)
            return True
        except Exception:
            return False

    def _redact(self, text: str) -> str:
        if not text:
            return ""
        patterns = [
            r"(?i)api_key=[A-Za-z0-9_\-]+",
            r"(?i)token=[A-Za-z0-9_\-]+",
            r"(?i)secret=[A-Za-z0-9_\-]+",
        ]
        redacted = text
        for pat in patterns:
            redacted = re.sub(pat, "***", redacted)
        return redacted

    def _write_artifact(self, result: CommandResult) -> str:
        safe_label = result.label or self._sanitize_label(result.command)
        filename = f"{int(time.time())}_{safe_label}.log"
        path = self.diagnostics_dir / "commands" / filename
        body = [
            f"# Command: {result.redacted_command}",
            f"# Exit: {result.exit_code if result.exit_code is not None else 'n/a'}",
            f"# Duration: {result.duration_sec:.2f}s",
        ]
        if result.timed_out:
            body.append("# Timed out")
        if result.skipped:
            body.append(f"# Skipped: {result.reason}")
        body.append("\n# STDOUT\n")
        body.append(result.stdout or "")
        body.append("\n# STDERR\n")
        body.append(result.stderr or "")
        path.write_text("\n".join(body), encoding="utf-8", errors="ignore")
        # Return relative path from workspace for portability
        try:
            return str(path.relative_to(self.workspace))
        except ValueError:
            # If path is not relative to workspace, return as-is
            return str(path)

    def _append_log(self, result: CommandResult) -> None:
        record = {
            "command": result.redacted_command,
            "exit_code": result.exit_code,
            "duration_sec": result.duration_sec,
            "timed_out": result.timed_out,
            "skipped": result.skipped,
            "reason": result.reason,
            "artifact_path": result.artifact_path,
            "label": result.label,
            "timestamp": time.time(),
        }
        with self._command_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _sanitize_label(self, command: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", command.strip())
        return cleaned[:60] or "command"

    @staticmethod
    def _default_runner(cmd: List[str], kwargs: Dict[str, object]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, **kwargs)

    # Exposed for testing/telemetry
    @property
    def command_count(self) -> int:
        return self._command_count

    @property
    def seconds_used(self) -> float:
        return self._seconds_used
