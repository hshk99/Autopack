from pathlib import Path

from autopack.diagnostics.command_runner import CommandResult, GovernedCommandRunner
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.diagnostics.probes import ProbeLibrary


def test_command_runner_allows_safe_command(tmp_path: Path):
    runner = GovernedCommandRunner(
        run_id="test-run",
        workspace=tmp_path,
        diagnostics_dir=tmp_path / "diag",
        max_commands=5,
        max_seconds=120,
    )

    result = runner.run("python -m site --user-base", label="python_site")

    assert result.skipped is False
    assert result.timed_out is False
    assert result.exit_code == 0
    assert runner.command_count == 1


def test_command_runner_blocks_banned(tmp_path: Path):
    runner = GovernedCommandRunner(
        run_id="test-run",
        workspace=tmp_path,
        diagnostics_dir=tmp_path / "diag",
        max_commands=1,
        max_seconds=30,
    )

    result = runner.run("rm -rf /", label="danger")

    assert result.skipped is True
    assert "blocked" in (result.reason or "")


def test_command_runner_sandbox_copy(tmp_path: Path):
    diag_dir = tmp_path / "diag"
    tracked = tmp_path / "data.txt"
    tracked.write_text("hello")

    runner = GovernedCommandRunner(
        run_id="test-run",
        workspace=tmp_path,
        diagnostics_dir=diag_dir,
        max_commands=2,
        max_seconds=60,
        sandbox_paths=["data.txt"],
    )

    result = runner.run("python -m site --user-base", label="sandbox_cmd", sandbox=True)

    sandbox_copy = diag_dir / "sandbox" / "data.txt"
    assert sandbox_copy.exists()
    assert result.skipped is False


def test_probe_library_returns_expected_sets():
    patch_probes = ProbeLibrary.for_failure("patch_apply_error")
    ci_probes = ProbeLibrary.for_failure("ci_fail")

    assert patch_probes[0].name == "patch_state"
    assert any(cmd.command.startswith("pytest") for cmd in ci_probes[0].commands)


class _StubRunner:
    """Stub runner to avoid real subprocess calls in diagnostics agent tests."""

    def __init__(self, diagnostics_dir: Path):
        self.diagnostics_dir = diagnostics_dir
        (self.diagnostics_dir / "commands").mkdir(parents=True, exist_ok=True)
        self.command_count = 0
        self.max_commands = 10

    def run(self, command: str, label=None, timeout=None, allow_network=False, sandbox=False):
        self.command_count += 1
        return CommandResult(
            command=command,
            redacted_command=command,
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_sec=0.1,
            timed_out=False,
            skipped=False,
            reason=None,
            artifact_path=str(self.diagnostics_dir / "commands" / f"{label or 'cmd'}.log"),
            label=label,
        )


def test_diagnostics_agent_with_stub_runner(tmp_path: Path):
    diagnostics_dir = tmp_path / "diag"
    runner = _StubRunner(diagnostics_dir)
    agent = DiagnosticsAgent(
        run_id="manual-test",
        workspace=tmp_path,
        memory_service=None,
        decision_logger=None,
        diagnostics_dir=diagnostics_dir,
        max_probes=2,
        max_seconds=10,
        runner=runner,
    )

    outcome = agent.run_diagnostics("patch_apply_error", context={"status": "PATCH_FAILED"})

    assert outcome.probe_results, "Diagnostics should run probes"
    assert "Investigate" in outcome.ledger_summary
    assert runner.command_count > 0

