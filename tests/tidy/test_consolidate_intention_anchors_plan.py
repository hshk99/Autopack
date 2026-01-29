"""
Tests for Intention Anchor consolidation plan mode (Part B2).

Intention behind these tests: Verify that plan mode produces deterministic
plans with stable idempotency hashes and NEVER writes to SOT ledgers.
"""

import json
# Import the script functions directly
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "scripts" / "tidy"))

from consolidate_intention_anchors import (compute_idempotency_hash,
                                           generate_consolidation_block,
                                           generate_consolidation_plan,
                                           run_plan_mode)

# Import intention anchor utilities
sys.path.insert(0, str(project_root / "src"))

from autopack.intention_anchor import create_anchor, save_anchor

# =============================================================================
# Idempotency Hash Tests
# =============================================================================


def test_compute_idempotency_hash_stable():
    """Test idempotency hash is stable for same content."""
    content = "Test content for hashing."

    hash1 = compute_idempotency_hash(content)
    hash2 = compute_idempotency_hash(content)

    assert hash1 == hash2
    assert len(hash1) == 12  # First 12 chars of SHA256


def test_compute_idempotency_hash_different_content():
    """Test different content produces different hashes."""
    content1 = "First content."
    content2 = "Second content."

    hash1 = compute_idempotency_hash(content1)
    hash2 = compute_idempotency_hash(content2)

    assert hash1 != hash2


# =============================================================================
# Consolidation Block Tests
# =============================================================================


def test_generate_consolidation_block_deterministic():
    """Test consolidation block is deterministic."""
    analysis = {
        "run_id": "run-001",
        "project_id": "test",
        "anchor_id": "IA-001",
        "version": 1,
        "last_updated": "2024-01-01T00:00:00Z",
        "event_count": 5,
        "event_types": {
            "anchor_created": 1,
            "prompt_injected_builder": 2,
            "prompt_injected_auditor": 2,
        },
    }

    block1 = generate_consolidation_block(analysis, base_dir=Path("."))
    block2 = generate_consolidation_block(analysis, base_dir=Path("."))

    assert block1 == block2


def test_generate_consolidation_block_structure():
    """Test consolidation block contains expected elements."""
    analysis = {
        "run_id": "run-001",
        "project_id": "test",
        "anchor_id": "IA-001",
        "version": 1,
        "last_updated": "2024-01-01T00:00:00Z",
        "event_count": 5,
        "event_types": {"anchor_created": 1, "prompt_injected_builder": 4},
    }

    block = generate_consolidation_block(analysis, base_dir=Path("."))

    assert "### run-001" in block
    assert "IA-001" in block
    assert "v1" in block
    assert "test" in block  # project_id
    assert ".autonomous_runs/run-001/anchor_summary.md" in block


# =============================================================================
# Plan Generation Tests
# =============================================================================


def test_generate_consolidation_plan_format_version():
    """Test plan includes format_version."""
    plan = generate_consolidation_plan("autopack", [], base_dir=Path("."))

    assert "format_version" in plan
    assert plan["format_version"] == 1


def test_generate_consolidation_plan_project_id():
    """Test plan includes project_id."""
    plan = generate_consolidation_plan("test-project", [], base_dir=Path("."))

    assert plan["project_id"] == "test-project"


def test_generate_consolidation_plan_target_docs_autopack():
    """Test autopack project targets ./docs directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="run-001",
            project_id="autopack",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        analyses = [
            {
                "run_id": "run-001",
                "project_id": "autopack",
                "anchor_id": anchor.anchor_id,
                "version": 1,
                "last_updated": anchor.updated_at.isoformat(),
                "has_anchor": True,
                "has_summary": True,
                "event_count": 0,
                "event_types": {},
            }
        ]

        plan = generate_consolidation_plan("autopack", analyses, base_dir=tmpdir_path)

        assert len(plan["candidates"]) == 1
        candidate = plan["candidates"][0]
        assert "docs" in candidate["target_docs_dir"]
        assert candidate["target_file"].endswith("BUILD_HISTORY.md")


def test_generate_consolidation_plan_target_docs_project():
    """Test non-autopack project targets .autonomous_runs/<project>/docs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="run-001",
            project_id="other-project",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        analyses = [
            {
                "run_id": "run-001",
                "project_id": "other-project",
                "anchor_id": anchor.anchor_id,
                "version": 1,
                "last_updated": anchor.updated_at.isoformat(),
                "has_anchor": True,
                "has_summary": True,
                "event_count": 0,
                "event_types": {},
            }
        ]

        plan = generate_consolidation_plan("other-project", analyses, base_dir=tmpdir_path)

        assert len(plan["candidates"]) == 1
        candidate = plan["candidates"][0]
        assert ".autonomous_runs" in candidate["target_docs_dir"]
        assert "other-project" in candidate["target_docs_dir"]


def test_generate_consolidation_plan_idempotency_hash():
    """Test plan includes stable idempotency_hash for each candidate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        analyses = [
            {
                "run_id": "run-001",
                "project_id": "test",
                "anchor_id": anchor.anchor_id,
                "version": 1,
                "last_updated": anchor.updated_at.isoformat(),
                "has_anchor": True,
                "has_summary": True,
                "event_count": 0,
                "event_types": {},
            }
        ]

        # Generate plan twice
        plan1 = generate_consolidation_plan("test", analyses, base_dir=tmpdir_path)
        plan2 = generate_consolidation_plan("test", analyses, base_dir=tmpdir_path)

        # Idempotency hashes should match (ignoring generated_at timestamp)
        assert len(plan1["candidates"]) == 1
        assert len(plan2["candidates"]) == 1

        hash1 = plan1["candidates"][0]["idempotency_hash"]
        hash2 = plan2["candidates"][0]["idempotency_hash"]

        assert hash1 == hash2
        assert len(hash1) == 12


def test_generate_consolidation_plan_max_runs():
    """Test plan respects max_runs limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create 5 runs
        analyses = []
        for i in range(5):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

            analyses.append(
                {
                    "run_id": run_id,
                    "project_id": "test",
                    "anchor_id": anchor.anchor_id,
                    "version": 1,
                    "last_updated": anchor.updated_at.isoformat(),
                    "has_anchor": True,
                    "has_summary": True,
                    "event_count": 0,
                    "event_types": {},
                }
            )

        # Generate plan with max_runs=3
        plan = generate_consolidation_plan("test", analyses, base_dir=tmpdir_path, max_runs=3)

        # Should only include 3 candidates
        assert len(plan["candidates"]) == 3


def test_generate_consolidation_plan_skips_incomplete():
    """Test plan skips runs with incomplete artifacts."""
    analyses = [
        {
            "run_id": "run-001",
            "project_id": "test",
            "anchor_id": "IA-001",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": True,  # Complete
            "event_count": 0,
            "event_types": {},
        },
        {
            "run_id": "run-002",
            "project_id": "test",
            "anchor_id": "IA-002",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": False,  # Incomplete
            "event_count": 0,
            "event_types": {},
        },
    ]

    plan = generate_consolidation_plan("test", analyses, base_dir=Path("."))

    # Only run-001 should be included
    assert len(plan["candidates"]) == 1
    assert plan["candidates"][0]["run_id"] == "run-001"


# =============================================================================
# Integration Tests (run_plan_mode)
# =============================================================================


def test_run_plan_mode_success():
    """Test plan mode execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create runs
        for i in range(3):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run plan mode
        output_plan = tmpdir_path / "plan.json"

        exit_code = run_plan_mode(
            project_id="test",
            base_dir=tmpdir_path,
            out=output_plan,
            max_runs=10,
        )

        assert exit_code == 0
        assert output_plan.exists()

        # Verify plan structure
        plan = json.loads(output_plan.read_text(encoding="utf-8"))
        assert plan["format_version"] == 1
        assert plan["project_id"] == "test"
        assert len(plan["candidates"]) == 3


def test_run_plan_mode_filters_by_project():
    """Test plan mode filters runs by project_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create runs for different projects
        for project_id in ["project-a", "project-b"]:
            for i in range(2):
                run_id = f"{project_id}-run-{i}"
                anchor = create_anchor(
                    run_id=run_id,
                    project_id=project_id,
                    north_star=f"Run {i}.",
                )
                save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run plan mode for project-a only
        output_plan = tmpdir_path / "plan.json"

        run_plan_mode(
            project_id="project-a",
            base_dir=tmpdir_path,
            out=output_plan,
            max_runs=10,
        )

        plan = json.loads(output_plan.read_text(encoding="utf-8"))

        # Should only include project-a runs
        assert len(plan["candidates"]) == 2
        assert all("project-a" in c["run_id"] for c in plan["candidates"])


# =============================================================================
# Contract Tests (No SOT Writes)
# =============================================================================


def test_run_plan_mode_no_sot_writes():
    """
    CRITICAL CONTRACT TEST: Verify plan mode NEVER writes to SOT ledgers.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create fake SOT ledgers
        docs_dir = tmpdir_path / "docs"
        docs_dir.mkdir()

        sot_files = {
            "BUILD_HISTORY.md": "# Build History\n\nOriginal content.\n",
            "DEBUG_LOG.md": "# Debug Log\n\nOriginal content.\n",
            "ARCHITECTURE_DECISIONS.md": "# Architecture Decisions\n\nOriginal content.\n",
        }

        readme_path = tmpdir_path / "README.md"
        readme_path.write_text("# README\n\nOriginal content.\n", encoding="utf-8")

        # Create SOT files and record their state
        file_states = {}
        for filename, content in sot_files.items():
            file_path = docs_dir / filename
            file_path.write_text(content, encoding="utf-8")
            file_states[file_path] = {
                "content": content,
                "mtime": file_path.stat().st_mtime,
            }

        file_states[readme_path] = {
            "content": readme_path.read_text(encoding="utf-8"),
            "mtime": readme_path.stat().st_mtime,
        }

        # Create runs with anchors
        for i in range(3):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run plan mode
        output_plan = tmpdir_path / "plan.json"
        run_plan_mode(
            project_id="test",
            base_dir=tmpdir_path,
            out=output_plan,
            max_runs=10,
        )

        # CRITICAL: Verify SOT files are unchanged
        for file_path, original_state in file_states.items():
            assert file_path.exists(), f"{file_path} was deleted!"

            # Check content unchanged
            current_content = file_path.read_text(encoding="utf-8")
            assert (
                current_content == original_state["content"]
            ), f"{file_path} content was modified!"

            # Check mtime unchanged
            current_mtime = file_path.stat().st_mtime
            assert (
                current_mtime == original_state["mtime"]
            ), f"{file_path} mtime changed (file was written to)!"


# =============================================================================
# P0 Safety Tests (Path Traversal & Project ID Validation)
# =============================================================================


def test_plan_mode_rejects_path_traversal_project_id():
    """Test plan mode rejects project IDs with path traversal attempts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        output_plan = tmpdir_path / "plan.json"

        # Try various path traversal attacks
        malicious_ids = [
            "../docs",
            "../../etc",
            "..\\windows",
            "a/../b",
            "..",
        ]

        for malicious_id in malicious_ids:
            exit_code = run_plan_mode(
                project_id=malicious_id,
                base_dir=tmpdir_path,
                out=output_plan,
                max_runs=10,
            )
            # Should fail with exit code 2 (usage error)
            assert exit_code == 2, f"Failed to reject malicious project_id: {malicious_id}"


def test_plan_mode_rejects_path_separators_in_project_id():
    """Test plan mode rejects project IDs with path separators."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        output_plan = tmpdir_path / "plan.json"

        malicious_ids = [
            "a/b",
            "a\\b",
            "project/subdir",
            "c:\\path",
        ]

        for malicious_id in malicious_ids:
            exit_code = run_plan_mode(
                project_id=malicious_id,
                base_dir=tmpdir_path,
                out=output_plan,
                max_runs=10,
            )
            assert exit_code == 2, f"Failed to reject project_id with separator: {malicious_id}"


def test_plan_mode_rejects_invalid_project_id_patterns():
    """Test plan mode rejects invalid project ID patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        output_plan = tmpdir_path / "plan.json"

        invalid_ids = [
            ".hidden",  # Leading dot
            "",  # Empty
            "a" * 65,  # Too long (>64 chars)
            "a b",  # Space
            "project name",  # Spaces
        ]

        for invalid_id in invalid_ids:
            exit_code = run_plan_mode(
                project_id=invalid_id,
                base_dir=tmpdir_path,
                out=output_plan,
                max_runs=10,
            )
            assert exit_code == 2, f"Failed to reject invalid project_id: {invalid_id}"


def test_plan_mode_accepts_valid_project_ids():
    """Test plan mode accepts valid project IDs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        valid_ids = [
            "autopack",
            "project-a",
            "project_b",
            "proj.1",
            "Test123",
            "a" * 64,  # Exactly 64 chars
        ]

        for valid_id in valid_ids:
            output_plan = tmpdir_path / f"plan_{valid_id}.json"
            exit_code = run_plan_mode(
                project_id=valid_id,
                base_dir=tmpdir_path,
                out=output_plan,
                max_runs=10,
            )
            assert exit_code == 0, f"Should accept valid project_id: {valid_id}"


def test_plan_mode_excludes_unknown_project_runs_by_default():
    """Test plan mode excludes runs with unknown/None project_id by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create run with matching project_id
        anchor1 = create_anchor(
            run_id="run-001",
            project_id="project-a",
            north_star="Matching project.",
        )
        save_anchor(anchor1, base_dir=tmpdir_path, generate_artifacts=True)

        # Create run with different project_id
        anchor2 = create_anchor(
            run_id="run-002",
            project_id="project-b",
            north_star="Different project.",
        )
        save_anchor(anchor2, base_dir=tmpdir_path, generate_artifacts=True)

        # Create run with broken/malformed anchor (will result in project_id=None in analysis)
        anchor3 = create_anchor(
            run_id="run-003",
            project_id="project-c",
            north_star="Will be broken.",
        )
        save_anchor(anchor3, base_dir=tmpdir_path, generate_artifacts=True)

        # Corrupt the anchor JSON to make it unloadable (missing required field)
        anchor3_path = tmpdir_path / ".autonomous_runs" / "run-003" / "intention_anchor.json"
        anchor3_path.write_text("{}", encoding="utf-8")

        # Run plan mode for project-a WITHOUT --include-unknown-project
        output_plan = tmpdir_path / "plan.json"
        run_plan_mode(
            project_id="project-a",
            base_dir=tmpdir_path,
            out=output_plan,
            max_runs=10,
            include_unknown_project=False,
        )

        plan = json.loads(output_plan.read_text(encoding="utf-8"))

        # Should only include run-001 (exact match)
        assert len(plan["candidates"]) == 1
        assert plan["candidates"][0]["run_id"] == "run-001"


def test_plan_mode_includes_unknown_project_runs_with_flag():
    """Test plan mode includes runs with unknown project_id when flag is set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create run with matching project_id
        anchor1 = create_anchor(
            run_id="run-001",
            project_id="project-a",
            north_star="Matching project.",
        )
        save_anchor(anchor1, base_dir=tmpdir_path, generate_artifacts=True)

        # Create run with broken/malformed anchor (will result in project_id=None in analysis)
        anchor2 = create_anchor(
            run_id="run-002",
            project_id="project-b",
            north_star="Will be broken.",
        )
        save_anchor(anchor2, base_dir=tmpdir_path, generate_artifacts=True)

        # Corrupt the anchor JSON to make it unloadable
        anchor2_path = tmpdir_path / ".autonomous_runs" / "run-002" / "intention_anchor.json"
        anchor2_path.write_text("{}", encoding="utf-8")

        # Run plan mode WITH --include-unknown-project
        output_plan = tmpdir_path / "plan.json"
        run_plan_mode(
            project_id="project-a",
            base_dir=tmpdir_path,
            out=output_plan,
            max_runs=10,
            include_unknown_project=True,
        )

        plan = json.loads(output_plan.read_text(encoding="utf-8"))

        # Should only include run-001 (exact match), run-002 has no valid summary so won't be a candidate
        # Note: broken anchors won't have has_summary=True, so they're filtered out by the "incomplete" check
        assert len(plan["candidates"]) == 1
        assert plan["candidates"][0]["run_id"] == "run-001"


def test_plan_mode_metadata_includes_filter_flag():
    """Test plan metadata includes include_unknown_project flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Test with flag = False
        output_plan1 = tmpdir_path / "plan1.json"
        run_plan_mode(
            project_id="test",
            base_dir=tmpdir_path,
            out=output_plan1,
            max_runs=10,
            include_unknown_project=False,
        )

        plan1 = json.loads(output_plan1.read_text(encoding="utf-8"))
        assert plan1["filters"]["include_unknown_project"] is False

        # Test with flag = True
        output_plan2 = tmpdir_path / "plan2.json"
        run_plan_mode(
            project_id="test",
            base_dir=tmpdir_path,
            out=output_plan2,
            max_runs=10,
            include_unknown_project=True,
        )

        plan2 = json.loads(output_plan2.read_text(encoding="utf-8"))
        assert plan2["filters"]["include_unknown_project"] is True
