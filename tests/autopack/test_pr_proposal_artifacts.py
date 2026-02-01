"""Tests for PR proposal artifacts (proposal_artifacts.py).

Per IMPLEMENTATION_PLAN_PR_APPROVAL_PIPELINE.md minimal test coverage:
- Proposal creation and serialization
- Storage save/load roundtrip
- Markdown formatting
"""

from __future__ import annotations

import json

from autopack.pr.proposal_artifacts import (PrProposal, PrProposalStorage,
                                            _format_proposal_md)


def test_proposal_dataclass():
    """Test PrProposal dataclass creation and serialization."""
    proposal = PrProposal(
        run_id="test-run-001",
        phase_set=["builder", "auditor"],
        branch="feat/test",
        base_branch="main",
        title="Test PR",
        summary_md="This is a test PR",
        files_changed=["src/foo.py", "src/bar.py"],
        loc_added=42,
        loc_removed=10,
        risk_score=25,
        checklist=["CI must pass", "Review code"],
        metadata={"commit_sha": "abc123"},
    )

    # Test to_dict
    data = proposal.to_dict()
    assert data["run_id"] == "test-run-001"
    assert data["phase_set"] == ["builder", "auditor"]
    assert data["files_changed"] == ["src/foo.py", "src/bar.py"]
    assert data["metadata"]["commit_sha"] == "abc123"

    # Test from_dict roundtrip
    loaded = PrProposal.from_dict(data)
    assert loaded == proposal


def test_proposal_storage_save_load(tmp_path):
    """Test PrProposalStorage save/load roundtrip."""
    # Create proposal
    proposal = PrProposal(
        run_id="storage-test-run",
        phase_set=["phase1"],
        branch="feat/storage",
        base_branch="main",
        title="Storage Test",
        summary_md="Testing storage",
        files_changed=["a.txt"],
        loc_added=5,
        loc_removed=2,
        risk_score=10,
        checklist=["Check"],
        metadata={},
    )

    # Mock RunFileLayout by setting up expected directory structure
    # Since RunFileLayout uses settings.autonomous_runs_dir, we can't easily mock it
    # Instead, we'll use proposal_paths directly with a custom run_id that includes tmp_path
    # For this test, we'll manually construct paths

    # Actually, let's test the internal methods directly
    # First, save
    from unittest.mock import patch

    with patch("autopack.pr.proposal_artifacts.RunFileLayout") as mock_layout:
        mock_layout.return_value.base_dir = tmp_path
        json_path, md_path = PrProposalStorage.save(proposal, project_id=None)

    # Verify files were created
    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content
    json_data = json.loads(json_path.read_text())
    assert json_data["run_id"] == "storage-test-run"
    assert json_data["title"] == "Storage Test"

    # Verify MD content
    md_content = md_path.read_text()
    assert "Storage Test" in md_content
    assert "feat/storage" in md_content

    # Test load
    with patch("autopack.pr.proposal_artifacts.RunFileLayout") as mock_layout:
        mock_layout.return_value.base_dir = tmp_path
        loaded = PrProposalStorage.load("storage-test-run", project_id=None)

    assert loaded is not None
    assert loaded == proposal


def test_proposal_storage_load_missing(tmp_path):
    """Test load returns None when proposal doesn't exist."""
    from unittest.mock import patch

    with patch("autopack.pr.proposal_artifacts.RunFileLayout") as mock_layout:
        mock_layout.return_value.base_dir = tmp_path / "nonexistent"
        loaded = PrProposalStorage.load("missing-run", project_id=None)

    assert loaded is None


def test_markdown_formatting():
    """Test markdown formatting for PR body."""
    proposal = PrProposal(
        run_id="md-test",
        phase_set=["p1", "p2"],
        branch="feat/md",
        base_branch="main",
        title="Markdown Test",
        summary_md="Test summary with **bold** and *italic*",
        files_changed=["file1.py", "file2.py", "file3.py"],
        loc_added=100,
        loc_removed=50,
        risk_score=60,
        checklist=["Item 1", "Item 2"],
        metadata={"commit_sha": "xyz789", "timestamp": "2025-01-01"},
    )

    md = _format_proposal_md(proposal)

    # Verify key sections
    assert "# Markdown Test" in md
    assert "Test summary with **bold** and *italic*" in md
    assert "**Files Changed**: 3" in md
    assert "**Lines Added**: 100" in md
    assert "**Lines Removed**: 50" in md
    assert "⚠️ 60/100" in md  # Risk emoji for score 60
    assert "- [ ] Item 1" in md
    assert "- [ ] Item 2" in md
    assert "`md-test`" in md
    assert "`feat/md`" in md
    assert "`p1`" in md
    assert "`p2`" in md


def test_markdown_formatting_many_files():
    """Test markdown truncates file list to 10 files."""
    files = [f"file{i}.py" for i in range(15)]

    proposal = PrProposal(
        run_id="many-files",
        phase_set=[],
        branch="feat/many",
        base_branch="main",
        title="Many Files",
        summary_md="Lots of files",
        files_changed=files,
        loc_added=10,
        loc_removed=5,
        risk_score=20,
        checklist=[],
        metadata={},
    )

    md = _format_proposal_md(proposal)

    # Should show first 10 files + "and 5 more"
    assert "file0.py" in md
    assert "file9.py" in md
    assert "...and 5 more" in md
    assert "file14.py" not in md  # Should be truncated


def test_risk_score_emojis():
    """Test risk score determines correct emoji."""
    # Low risk (< 40)
    low = PrProposal(
        run_id="low",
        phase_set=[],
        branch="b",
        base_branch="m",
        title="T",
        summary_md="S",
        files_changed=[],
        loc_added=0,
        loc_removed=0,
        risk_score=20,
        checklist=[],
        metadata={},
    )
    assert "✅ 20/100" in _format_proposal_md(low)

    # Medium risk (40-69)
    med = PrProposal(
        run_id="med",
        phase_set=[],
        branch="b",
        base_branch="m",
        title="T",
        summary_md="S",
        files_changed=[],
        loc_added=0,
        loc_removed=0,
        risk_score=55,
        checklist=[],
        metadata={},
    )
    assert "⚠️ 55/100" in _format_proposal_md(med)

    # High risk (>= 70)
    high = PrProposal(
        run_id="high",
        phase_set=[],
        branch="b",
        base_branch="m",
        title="T",
        summary_md="S",
        files_changed=[],
        loc_added=0,
        loc_removed=0,
        risk_score=85,
        checklist=[],
        metadata={},
    )
    assert "🔴 85/100" in _format_proposal_md(high)
