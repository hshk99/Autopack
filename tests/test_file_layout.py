"""Unit tests for file layout utilities"""


import pytest

from autopack.file_layout import RunFileLayout


@pytest.fixture
def file_layout(tmp_path):
    """Create a RunFileLayout instance with temp directory"""
    layout = RunFileLayout("test-run-001", base_dir=tmp_path)
    return layout


def test_ensure_directories(file_layout, tmp_path):
    """Test that ensure_directories creates all required directories"""
    file_layout.ensure_directories()

    # Path structure: base_dir / project_id / runs / family / run_id
    run_dir = tmp_path / "autopack" / "runs" / "test-run-001"
    assert run_dir.exists()
    assert (run_dir / "tiers").exists()
    assert (run_dir / "phases").exists()
    assert (run_dir / "issues").exists()


def test_get_run_summary_path(file_layout, tmp_path):
    """Test getting run summary path"""
    path = file_layout.get_run_summary_path()
    # Path structure: base_dir / project_id / runs / family / run_id / file
    assert path == tmp_path / "autopack" / "runs" / "test-run-001" / "run_summary.md"


def test_get_tier_summary_path(file_layout, tmp_path):
    """Test getting tier summary path"""
    path = file_layout.get_tier_summary_path(0, "Foundation")
    assert path == tmp_path / "autopack" / "runs" / "test-run-001" / "tiers" / "tier_00_Foundation.md"


def test_get_tier_summary_path_with_spaces(file_layout, tmp_path):
    """Test tier summary path with spaces in name"""
    path = file_layout.get_tier_summary_path(1, "Auth & Security")
    assert path == tmp_path / "autopack" / "runs" / "test-run-001" / "tiers" / "tier_01_Auth_&_Security.md"


def test_get_phase_summary_path(file_layout, tmp_path):
    """Test getting phase summary path"""
    path = file_layout.get_phase_summary_path(0, "F1.1")
    assert path == tmp_path / "autopack" / "runs" / "test-run-001" / "phases" / "phase_00_F1.1.md"


def test_write_run_summary(file_layout, tmp_path):
    """Test writing run summary file"""
    file_layout.ensure_directories()
    file_layout.write_run_summary(
        run_id="test-run-001",
        state="RUN_CREATED",
        safety_profile="normal",
        run_scope="multi_tier",
        created_at="2025-11-23T10:00:00",
        tier_count=2,
        phase_count=3,
    )

    path = file_layout.get_run_summary_path()
    assert path.exists()

    content = path.read_text()
    assert "# Run Summary: test-run-001" in content
    assert "State:** RUN_CREATED" in content
    assert "Safety Profile:** normal" in content
    assert "Tiers:** 2" in content
    assert "Phases:** 3" in content


def test_write_tier_summary(file_layout, tmp_path):
    """Test writing tier summary file"""
    file_layout.ensure_directories()
    file_layout.write_tier_summary(
        tier_index=0, tier_id="T1", tier_name="Foundation", state="PENDING", phase_count=2
    )

    path = file_layout.get_tier_summary_path(0, "Foundation")
    assert path.exists()

    content = path.read_text()
    assert "# Tier Summary: T1 - Foundation" in content
    assert "State:** PENDING" in content
    assert "Index:** 0" in content
    assert "Total:** 2" in content


def test_write_phase_summary(file_layout, tmp_path):
    """Test writing phase summary file"""
    file_layout.ensure_directories()
    file_layout.write_phase_summary(
        phase_index=0,
        phase_id="F1.1",
        phase_name="Setup DB",
        state="QUEUED",
        task_category="schema_change",
        complexity="medium",
    )

    path = file_layout.get_phase_summary_path(0, "F1.1")
    assert path.exists()

    content = path.read_text()
    assert "# Phase Summary: F1.1 - Setup DB" in content
    assert "State:** QUEUED" in content
    assert "Task Category:** schema_change" in content
    assert "Complexity:** medium" in content


def test_write_phase_summary_no_category(file_layout, tmp_path):
    """Test writing phase summary without category/complexity"""
    file_layout.ensure_directories()
    file_layout.write_phase_summary(
        phase_index=1, phase_id="F1.2", phase_name="Simple task", state="QUEUED"
    )

    path = file_layout.get_phase_summary_path(1, "F1.2")
    assert path.exists()

    content = path.read_text()
    assert "Task Category:** N/A" in content
    assert "Complexity:** N/A" in content
