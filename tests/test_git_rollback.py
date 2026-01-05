"""Unit tests for the GitRollback helper."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from typing import List

import pytest

from autopack.git_rollback import GitRollback


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a disposable git repo folder with a .git marker."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    return repo_path


@pytest.fixture
def rollback(repo: Path) -> GitRollback:
    """Instantiate GitRollback against the temp repo."""
    return GitRollback(repo_path=repo)


def _fake_result(stdout: str = "", returncode: int = 0) -> SimpleNamespace:
    """Return a minimal CompletedProcess-like stub."""
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_create_rollback_point_creates_branch(
    monkeypatch: pytest.MonkeyPatch, rollback: GitRollback
):
    calls: List[list[str]] = []

    def fake_run(args: list[str], check: bool = True, capture_output: bool = True):
        calls.append(args)
        return _fake_result()

    monkeypatch.setattr(rollback, "_run_git_command", fake_run)
    monkeypatch.setattr(rollback, "_has_uncommitted_changes", lambda: False)
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: False)

    branch = rollback.create_rollback_point("run-123")

    assert branch == "autopack/pre-run-run-123"
    assert ["branch", branch] in calls


def test_create_rollback_point_overwrites_existing(
    monkeypatch: pytest.MonkeyPatch, rollback: GitRollback
):
    calls: List[list[str]] = []

    def fake_run(args: list[str], check: bool = True, capture_output: bool = True):
        calls.append(args)
        return _fake_result()

    monkeypatch.setattr(rollback, "_run_git_command", fake_run)
    monkeypatch.setattr(rollback, "_has_uncommitted_changes", lambda: False)
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: True)

    branch = rollback.create_rollback_point("run-123")

    assert branch == "autopack/pre-run-run-123"
    assert ["branch", "-D", branch] in calls
    assert ["branch", branch] in calls


def test_create_rollback_point_stashes_changes(
    monkeypatch: pytest.MonkeyPatch, rollback: GitRollback
):
    calls: List[list[str]] = []
    stash_called = {"called": False}

    def fake_run(args: list[str], check: bool = True, capture_output: bool = True):
        calls.append(args)
        return _fake_result()

    def fake_stash() -> bool:
        stash_called["called"] = True
        return True

    monkeypatch.setattr(rollback, "_run_git_command", fake_run)
    monkeypatch.setattr(rollback, "_has_uncommitted_changes", lambda: True)
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: False)
    monkeypatch.setattr(rollback, "_stash_changes", fake_stash)

    branch = rollback.create_rollback_point("run-456")

    assert branch == "autopack/pre-run-run-456"
    assert stash_called["called"] is True
    assert ["branch", branch] in calls


def test_rollback_to_point_success(monkeypatch: pytest.MonkeyPatch, rollback: GitRollback):
    calls: List[list[str]] = []

    def fake_run(args: list[str], check: bool = True, capture_output: bool = True):
        calls.append(args)
        return _fake_result()

    monkeypatch.setattr(rollback, "_run_git_command", fake_run)
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: True)

    assert rollback.rollback_to_point("run-123") is True
    branch_name = "autopack/pre-run-run-123"
    assert ["reset", "--hard", branch_name] in calls


def test_rollback_to_point_missing_branch(monkeypatch: pytest.MonkeyPatch, rollback: GitRollback):
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: False)

    assert rollback.rollback_to_point("run-123") is False


def test_cleanup_rollback_point_success(monkeypatch: pytest.MonkeyPatch, rollback: GitRollback):
    calls: List[list[str]] = []

    def fake_run(args: list[str], check: bool = True, capture_output: bool = True):
        calls.append(args)
        return _fake_result()

    monkeypatch.setattr(rollback, "_run_git_command", fake_run)
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: True)

    assert rollback.cleanup_rollback_point("run-123") is True
    branch_name = "autopack/pre-run-run-123"
    assert ["branch", "-D", branch_name] in calls


def test_cleanup_rollback_point_noop_when_missing(
    monkeypatch: pytest.MonkeyPatch, rollback: GitRollback
):
    monkeypatch.setattr(rollback, "_branch_exists", lambda name: False)

    assert rollback.cleanup_rollback_point("run-123") is True
