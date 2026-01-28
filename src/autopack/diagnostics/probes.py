"""
Declarative probe library keyed by failure class.

Each probe is a small, ordered set of safe commands executed by the governed
command runner. Probes are intentionally cheap-first and may short-circuit once
useful evidence is gathered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from autopack.diagnostics.command_runner import CommandResult


@dataclass
class ProbeCommand:
    """Single command within a probe."""

    command: str
    allow_network: bool = False
    sandbox: bool = False
    label: Optional[str] = None


@dataclass
class Probe:
    """A named probe consisting of one or more commands."""

    name: str
    description: str
    commands: List[ProbeCommand]
    stop_on_success: bool = True  # short-circuit when a command succeeds


@dataclass
class ProbeRunResult:
    """Result bundle for a probe execution."""

    probe: Probe
    command_results: List[CommandResult]
    resolved: bool


class ProbeLibrary:
    """
    Source of truth for diagnostic probes.

    Failure classes currently supported:
    - patch_apply_error
    - ci_fail / test_failure
    - deps_missing
    - missing_path
    - yaml_schema
    - network
    - memory_error / oom
    - timeout / hung
    - permission_denied
    - environment_error
    - concurrency / race_condition
    """

    @staticmethod
    def for_failure(failure_class: str, context: Optional[Dict] = None) -> List[Probe]:
        normalized = (failure_class or "").lower()
        context = context or {}
        if normalized in {"patch_apply_error", "patch_failed", "patch_failed_status"}:
            return ProbeLibrary._patch_apply_probes()
        if normalized in {"ci_fail", "ci_failed", "test_failure", "ci_failed_status"}:
            return ProbeLibrary._ci_probes(context)
        if normalized in {"deps_missing", "dependency_missing", "import_error"}:
            return ProbeLibrary._dependency_probes()
        if normalized in {"missing_path", "file_not_found", "path_error"}:
            return ProbeLibrary._missing_path_probes(context)
        if normalized in {"yaml_schema", "yaml_error", "schema_error"}:
            return ProbeLibrary._yaml_probes(context)
        if normalized in {"network", "network_error"}:
            return ProbeLibrary._network_probes(context)
        if normalized in {"memory_error", "oom", "out_of_memory"}:
            return ProbeLibrary._memory_error_probes()
        if normalized in {"timeout", "hung", "timed_out"}:
            return ProbeLibrary._timeout_probes()
        if normalized in {"permission_denied", "access_denied", "permission_error"}:
            return ProbeLibrary._permission_denied_probes(context)
        if normalized in {"environment_error", "env_error", "config_error"}:
            return ProbeLibrary._environment_error_probes()
        if normalized in {"concurrency", "race_condition", "deadlock", "thread_error"}:
            return ProbeLibrary._concurrency_probes()
        # Default to a lightweight baseline probe set
        return ProbeLibrary._baseline_probes()

    # ------------------------------------------------------------------ #
    # Probe definitions
    # ------------------------------------------------------------------ #

    @staticmethod
    def _baseline_probes() -> List[Probe]:
        return [
            Probe(
                name="baseline_git_state",
                description="Collect git status and short diff for context.",
                commands=[
                    ProbeCommand("git status --short", label="git_status"),
                    ProbeCommand("git diff --stat", label="git_diff_stat"),
                ],
            ),
            Probe(
                name="baseline_env",
                description="Capture Python environment basics.",
                commands=[
                    ProbeCommand("python -m site --user-base", label="python_site"),
                    ProbeCommand("python -m sysconfig", label="python_sysconfig"),
                ],
            ),
        ]

    @staticmethod
    def _patch_apply_probes() -> List[Probe]:
        return [
            Probe(
                name="patch_state",
                description="Inspect git state and recent patch artifacts.",
                commands=[
                    ProbeCommand("git status --short", label="git_status"),
                    ProbeCommand("git diff --stat", label="git_diff_stat"),
                    ProbeCommand('find . -maxdepth 4 -name "*.rej"', label="find_rejects"),
                    ProbeCommand("tail -n 200 last_patch_debug.diff", label="tail_patch_debug"),
                    ProbeCommand("tail -n 200 logs/autopack/builder.log", label="tail_builder"),
                ],
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _ci_probes(context: Dict) -> List[Probe]:
        target = context.get("test_target")
        pytest_cmd = "pytest -q --maxfail=1"
        if target:
            pytest_cmd = f'pytest -q --maxfail=1 -k "{target}"'
        return [
            Probe(
                name="ci_logs",
                description="Collect failing test output and recent executor logs.",
                commands=[
                    ProbeCommand(pytest_cmd, label="pytest_repro", sandbox=True),
                    ProbeCommand(
                        "tail -n 200 logs/autopack/autonomous_executor.log",
                        label="tail_executor_log",
                    ),
                    ProbeCommand("tail -n 200 logs/autopack/auditor.log", label="tail_auditor_log"),
                ],
                stop_on_success=False,
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _dependency_probes() -> List[Probe]:
        return [
            Probe(
                name="dependency_health",
                description="Check installed packages and environment configuration.",
                commands=[
                    ProbeCommand("pip check", label="pip_check"),
                    ProbeCommand("pip list --format=columns", label="pip_list"),
                    ProbeCommand("python -m site --user-base", label="python_site"),
                    ProbeCommand("python -m sysconfig", label="python_sysconfig"),
                ],
            ),
        ]

    @staticmethod
    def _missing_path_probes(context: Dict) -> List[Probe]:
        missing_path = context.get("missing_path")
        commands = [ProbeCommand("ls -la .", label="ls_root")]
        if missing_path:
            commands.append(
                ProbeCommand(
                    f"find {missing_path} -maxdepth 1 -name '*'", label="find_missing_path"
                )
            )
        else:
            commands.append(ProbeCommand("find . -maxdepth 3 -name '*.py'", label="find_py"))
        return [
            Probe(
                name="path_validation",
                description="Inspect filesystem layout for missing path hints.",
                commands=commands,
            ),
        ]

    @staticmethod
    def _yaml_probes(context: Dict) -> List[Probe]:
        yaml_path = context.get("yaml_path")
        commands = [
            ProbeCommand("find . -maxdepth 3 -name '*.yaml'", label="find_yaml"),
        ]
        if yaml_path:
            commands.append(ProbeCommand(f"head -n 80 {yaml_path}", label="head_yaml"))
            commands.append(ProbeCommand(f"tail -n 80 {yaml_path}", label="tail_yaml"))
        return [
            Probe(
                name="yaml_schema",
                description="Collect YAML snippets for schema validation clues.",
                commands=commands,
            ),
        ]

    @staticmethod
    def _network_probes(context: Dict) -> List[Probe]:
        host = context.get("host") or "localhost"
        url = context.get("url")
        commands = [
            ProbeCommand(f"ping -c 2 {host}", allow_network=True, label="ping_host"),
            ProbeCommand(f"traceroute {host}", allow_network=True, label="traceroute_host"),
        ]
        if url:
            commands.append(ProbeCommand(f"curl -I {url}", allow_network=True, label="curl_head"))
            commands.append(
                ProbeCommand(f"curl -I {url}", allow_network=True, label="curl_head_repeat")
            )
        return [
            Probe(
                name="network_health",
                description="Check connectivity to target host.",
                commands=commands,
            ),
        ]

    @staticmethod
    def _memory_error_probes() -> List[Probe]:
        """Probes for memory_error and OOM failure classes."""
        return [
            Probe(
                name="memory_usage",
                description="Check current process and system memory usage.",
                commands=[
                    ProbeCommand(
                        'python -c "import psutil; p=psutil.Process(); '
                        "print(f'RSS: {p.memory_info().rss/1024/1024:.1f}MB')\"",
                        label="process_memory",
                    ),
                    ProbeCommand(
                        'python -c "import psutil; m=psutil.virtual_memory(); '
                        "print(f'Available: {m.available/1024/1024:.1f}MB, "
                        "Used: {m.percent}%')\"",
                        label="system_memory",
                    ),
                ],
            ),
            Probe(
                name="large_objects",
                description="Identify potentially large objects in Python environment.",
                commands=[
                    ProbeCommand(
                        "python -c \"import sys; print('Python version:', sys.version); "
                        "print('Recursion limit:', sys.getrecursionlimit())\"",
                        label="python_limits",
                    ),
                ],
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _timeout_probes() -> List[Probe]:
        """Probes for timeout and hung process failure classes."""
        return [
            Probe(
                name="hung_processes",
                description="Check for hung or long-running processes.",
                commands=[
                    ProbeCommand(
                        'python -c "import threading; '
                        "print('Active threads:', threading.active_count()); "
                        "[print(f'  {t.name}: alive={t.is_alive()}') "
                        'for t in threading.enumerate()]"',
                        label="thread_state",
                    ),
                    ProbeCommand(
                        'python -c "import asyncio; '
                        "print('Pending tasks:', len(asyncio.all_tasks()) "
                        "if hasattr(asyncio, 'all_tasks') else 'N/A')\"",
                        label="async_tasks",
                    ),
                ],
            ),
            Probe(
                name="io_state",
                description="Check for pending I/O operations.",
                commands=[
                    ProbeCommand(
                        "python -c \"import os; print('Open file descriptors:', "
                        "len(os.listdir('/proc/self/fd')) if os.path.exists('/proc/self/fd') "
                        "else 'N/A (not Linux)')\"",
                        label="open_fds",
                    ),
                ],
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _permission_denied_probes(context: Dict) -> List[Probe]:
        """Probes for permission_denied failure class."""
        file_path = context.get("file_path") or context.get("path")
        commands = [
            ProbeCommand(
                "python -c \"import os, getpass; print('User:', getpass.getuser()); "
                "print('UID:', os.getuid() if hasattr(os, 'getuid') else 'N/A'); "
                "print('GID:', os.getgid() if hasattr(os, 'getgid') else 'N/A')\"",
                label="current_user",
            ),
            ProbeCommand("whoami", label="whoami"),
        ]
        if file_path:
            commands.append(ProbeCommand(f"ls -la {file_path}", label="file_permissions"))
            commands.append(
                ProbeCommand(
                    f"python -c \"import os, stat; s=os.stat('{file_path}'); "
                    f"print('Mode:', oct(s.st_mode)[-3:], 'UID:', s.st_uid, 'GID:', s.st_gid)\"",
                    label="stat_file",
                )
            )
        return [
            Probe(
                name="permission_context",
                description="Check user context and file permissions.",
                commands=commands,
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _environment_error_probes() -> List[Probe]:
        """Probes for environment_error failure class."""
        return [
            Probe(
                name="env_vars",
                description="Check critical environment variables.",
                commands=[
                    ProbeCommand(
                        'python -c "import os; '
                        "[print(f'{k}={v}') for k,v in sorted(os.environ.items()) "
                        "if 'PATH' in k or 'HOME' in k or 'PYTHON' in k]\"",
                        label="critical_env_vars",
                    ),
                    ProbeCommand(
                        "python -c \"import sys; print('sys.path:'); "
                        "[print(f'  {p}') for p in sys.path]\"",
                        label="python_path",
                    ),
                ],
            ),
            Probe(
                name="python_config",
                description="Check Python configuration and installation.",
                commands=[
                    ProbeCommand("python --version", label="python_version"),
                    ProbeCommand("which python", label="python_location"),
                    ProbeCommand("python -m site", label="python_site_info"),
                ],
            ),
        ] + ProbeLibrary._baseline_probes()

    @staticmethod
    def _concurrency_probes() -> List[Probe]:
        """Probes for concurrency and race_condition failure classes."""
        return [
            Probe(
                name="thread_state",
                description="Check threading state for potential deadlocks.",
                commands=[
                    ProbeCommand(
                        'python -c "import threading; '
                        "print('Active threads:', threading.active_count()); "
                        "[print(f'  {t.name}: daemon={t.daemon}, alive={t.is_alive()}') "
                        'for t in threading.enumerate()]"',
                        label="active_threads",
                    ),
                    ProbeCommand(
                        'python -c "import sys; '
                        "print('Check interval:', sys.getswitchinterval())\"",
                        label="switch_interval",
                    ),
                ],
            ),
            Probe(
                name="lock_diagnostics",
                description="Gather information about potential lock contention.",
                commands=[
                    ProbeCommand(
                        'python -c "import threading; '
                        "print('Main thread:', threading.main_thread().name); "
                        "print('Current thread:', threading.current_thread().name)\"",
                        label="thread_identity",
                    ),
                ],
            ),
        ] + ProbeLibrary._baseline_probes()
