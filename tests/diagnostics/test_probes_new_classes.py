"""Tests for new diagnostic probe failure classes.

Tests IMP-DIAG-007: Missing Diagnostic Probes for Critical Failure Classes.
Verifies probes for: memory_error, timeout, permission_denied, environment_error, concurrency.
"""

import pytest

from autopack.diagnostics.probes import Probe, ProbeLibrary


class TestMemoryErrorProbes:
    """Tests for memory_error/oom failure class probes."""

    @pytest.mark.parametrize("failure_class", ["memory_error", "oom", "out_of_memory"])
    def test_memory_error_probes_returned(self, failure_class: str):
        """Verify memory error probes are returned for relevant failure classes."""
        probes = ProbeLibrary.for_failure(failure_class)

        assert len(probes) > 0
        assert isinstance(probes[0], Probe)
        assert probes[0].name == "memory_usage"

    def test_memory_probes_contain_expected_commands(self):
        """Verify memory probes contain memory-related diagnostic commands."""
        probes = ProbeLibrary.for_failure("memory_error")

        # Find the memory_usage probe
        memory_probe = next((p for p in probes if p.name == "memory_usage"), None)
        assert memory_probe is not None
        assert memory_probe.description == "Check current process and system memory usage."

        # Check for expected command labels
        labels = [cmd.label for cmd in memory_probe.commands]
        assert "process_memory" in labels
        assert "system_memory" in labels

    def test_memory_probes_include_baseline(self):
        """Verify memory probes include baseline probes."""
        probes = ProbeLibrary.for_failure("memory_error")

        probe_names = [p.name for p in probes]
        assert "baseline_git_state" in probe_names


class TestTimeoutProbes:
    """Tests for timeout/hung failure class probes."""

    @pytest.mark.parametrize("failure_class", ["timeout", "hung", "timed_out"])
    def test_timeout_probes_returned(self, failure_class: str):
        """Verify timeout probes are returned for relevant failure classes."""
        probes = ProbeLibrary.for_failure(failure_class)

        assert len(probes) > 0
        assert isinstance(probes[0], Probe)
        assert probes[0].name == "hung_processes"

    def test_timeout_probes_contain_thread_diagnostics(self):
        """Verify timeout probes contain thread diagnostic commands."""
        probes = ProbeLibrary.for_failure("timeout")

        # Find the hung_processes probe
        hung_probe = next((p for p in probes if p.name == "hung_processes"), None)
        assert hung_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in hung_probe.commands]
        assert "thread_state" in labels
        assert "async_tasks" in labels

    def test_timeout_probes_include_baseline(self):
        """Verify timeout probes include baseline probes."""
        probes = ProbeLibrary.for_failure("timeout")

        probe_names = [p.name for p in probes]
        assert "baseline_git_state" in probe_names


class TestPermissionDeniedProbes:
    """Tests for permission_denied failure class probes."""

    @pytest.mark.parametrize(
        "failure_class", ["permission_denied", "access_denied", "permission_error"]
    )
    def test_permission_probes_returned(self, failure_class: str):
        """Verify permission probes are returned for relevant failure classes."""
        probes = ProbeLibrary.for_failure(failure_class)

        assert len(probes) > 0
        assert isinstance(probes[0], Probe)
        assert probes[0].name == "permission_context"

    def test_permission_probes_contain_user_diagnostics(self):
        """Verify permission probes contain user context commands."""
        probes = ProbeLibrary.for_failure("permission_denied")

        # Find the permission_context probe
        perm_probe = next((p for p in probes if p.name == "permission_context"), None)
        assert perm_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in perm_probe.commands]
        assert "current_user" in labels
        assert "whoami" in labels

    def test_permission_probes_with_file_path_context(self):
        """Verify permission probes include file-specific commands when path provided."""
        probes = ProbeLibrary.for_failure(
            "permission_denied", context={"file_path": "/tmp/test.txt"}
        )

        perm_probe = next((p for p in probes if p.name == "permission_context"), None)
        assert perm_probe is not None

        # Should include file-specific commands
        labels = [cmd.label for cmd in perm_probe.commands]
        assert "file_permissions" in labels
        assert "stat_file" in labels

    def test_permission_probes_include_baseline(self):
        """Verify permission probes include baseline probes."""
        probes = ProbeLibrary.for_failure("permission_denied")

        probe_names = [p.name for p in probes]
        assert "baseline_git_state" in probe_names


class TestEnvironmentErrorProbes:
    """Tests for environment_error failure class probes."""

    @pytest.mark.parametrize("failure_class", ["environment_error", "env_error", "config_error"])
    def test_environment_probes_returned(self, failure_class: str):
        """Verify environment probes are returned for relevant failure classes."""
        probes = ProbeLibrary.for_failure(failure_class)

        assert len(probes) > 0
        assert isinstance(probes[0], Probe)
        assert probes[0].name == "env_vars"

    def test_environment_probes_contain_env_diagnostics(self):
        """Verify environment probes contain environment variable commands."""
        probes = ProbeLibrary.for_failure("environment_error")

        # Find the env_vars probe
        env_probe = next((p for p in probes if p.name == "env_vars"), None)
        assert env_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in env_probe.commands]
        assert "critical_env_vars" in labels
        assert "python_path" in labels

    def test_environment_probes_contain_python_config(self):
        """Verify environment probes include Python configuration diagnostics."""
        probes = ProbeLibrary.for_failure("environment_error")

        # Find the python_config probe
        config_probe = next((p for p in probes if p.name == "python_config"), None)
        assert config_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in config_probe.commands]
        assert "python_version" in labels
        assert "python_location" in labels

    def test_environment_probes_include_baseline(self):
        """Verify environment probes include baseline probes."""
        probes = ProbeLibrary.for_failure("environment_error")

        probe_names = [p.name for p in probes]
        assert "baseline_git_state" in probe_names


class TestConcurrencyProbes:
    """Tests for concurrency/race_condition failure class probes."""

    @pytest.mark.parametrize(
        "failure_class", ["concurrency", "race_condition", "deadlock", "thread_error"]
    )
    def test_concurrency_probes_returned(self, failure_class: str):
        """Verify concurrency probes are returned for relevant failure classes."""
        probes = ProbeLibrary.for_failure(failure_class)

        assert len(probes) > 0
        assert isinstance(probes[0], Probe)
        assert probes[0].name == "thread_state"

    def test_concurrency_probes_contain_thread_diagnostics(self):
        """Verify concurrency probes contain thread state commands."""
        probes = ProbeLibrary.for_failure("concurrency")

        # Find the thread_state probe
        thread_probe = next((p for p in probes if p.name == "thread_state"), None)
        assert thread_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in thread_probe.commands]
        assert "active_threads" in labels
        assert "switch_interval" in labels

    def test_concurrency_probes_contain_lock_diagnostics(self):
        """Verify concurrency probes include lock diagnostic commands."""
        probes = ProbeLibrary.for_failure("concurrency")

        # Find the lock_diagnostics probe
        lock_probe = next((p for p in probes if p.name == "lock_diagnostics"), None)
        assert lock_probe is not None

        # Check for expected command labels
        labels = [cmd.label for cmd in lock_probe.commands]
        assert "thread_identity" in labels

    def test_concurrency_probes_include_baseline(self):
        """Verify concurrency probes include baseline probes."""
        probes = ProbeLibrary.for_failure("concurrency")

        probe_names = [p.name for p in probes]
        assert "baseline_git_state" in probe_names


class TestProbeLibraryDocstring:
    """Tests to verify the ProbeLibrary docstring is updated."""

    def test_docstring_includes_new_failure_classes(self):
        """Verify ProbeLibrary docstring documents new failure classes."""
        docstring = ProbeLibrary.__doc__ or ""

        assert "memory_error" in docstring
        assert "oom" in docstring
        assert "timeout" in docstring
        assert "hung" in docstring
        assert "permission_denied" in docstring
        assert "environment_error" in docstring
        assert "concurrency" in docstring
        assert "race_condition" in docstring


class TestBaselineProbesNotDuplicated:
    """Tests to ensure baseline probes are properly included."""

    @pytest.mark.parametrize(
        "failure_class",
        [
            "memory_error",
            "timeout",
            "permission_denied",
            "environment_error",
            "concurrency",
        ],
    )
    def test_new_probes_include_baseline_exactly_once(self, failure_class: str):
        """Verify each new probe set includes baseline probes exactly once."""
        probes = ProbeLibrary.for_failure(failure_class)

        probe_names = [p.name for p in probes]

        # Count occurrences of baseline probes
        baseline_count = probe_names.count("baseline_git_state")
        assert baseline_count == 1, f"baseline_git_state appears {baseline_count} times"

        env_count = probe_names.count("baseline_env")
        assert env_count == 1, f"baseline_env appears {env_count} times"
