"""
Integration tests for Intention Anchor usage in prompts (Milestone 2).

Intention behind these tests: demonstrate end-to-end usage of the Intention
Anchor system with phase binding and prompt rendering.
"""

import tempfile
from pathlib import Path

from autopack.intention_anchor import (
    IntentionConstraints,
    create_anchor,
    load_and_render_for_auditor,
    load_and_render_for_builder,
    load_and_render_for_doctor,
    save_anchor,
)
from autopack.plan_utils import validate_intention_refs
from autopack.schemas import IntentionRefs, PhaseCreate


# =============================================================================
# End-to-End Integration Tests
# =============================================================================


def test_full_workflow_builder_prompt_with_anchor():
    """Full workflow: create anchor → create phase with refs → render for Builder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Create and save intention anchor
        anchor = create_anchor(
            run_id="integration-test-001",
            project_id="test-project",
            north_star="Build a robust file upload feature with validation.",
            success_criteria=[
                "Support multiple file formats (PDF, DOCX, images)",
                "Validate file size (max 10MB)",
                "Show upload progress",
                "Handle errors gracefully",
            ],
            constraints=IntentionConstraints(
                must=[
                    "Use async file processing",
                    "Add comprehensive error handling",
                ],
                must_not=[
                    "Block the main thread during upload",
                    "Store files in memory",
                ],
                preferences=[
                    "Use chunked uploads for large files",
                ],
            ),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Step 2: Create phase with intention_refs
        phase = PhaseCreate(
            phase_id="F1.1",
            phase_index=1,
            tier_id="T1",
            name="Implement file validation logic",
            description="Add file type and size validation",
            intention_refs=IntentionRefs(
                success_criteria=[0, 1],  # Refs to "Support multiple formats" and "Validate file size"
                constraints_must=[1],      # Ref to "Add comprehensive error handling"
                constraints_must_not=[1],  # Ref to "Don't store files in memory"
            ),
        )

        # Step 3: Validate intention_refs (should pass)
        anchor_dict = anchor.model_dump()
        refs_dict = phase.intention_refs.model_dump() if phase.intention_refs else None

        warnings = validate_intention_refs(
            phase_id=phase.phase_id,
            intention_refs=refs_dict,
            anchor_data=anchor_dict,
            strict_mode=False,
        )

        assert len(warnings) == 0, f"Expected no warnings, got: {warnings}"

        # Step 4: Render anchor for Builder prompt
        builder_prompt = load_and_render_for_builder(
            run_id="integration-test-001",
            phase_id=phase.phase_id,
            base_dir=tmpdir,
        )

        # Verify rendered content
        assert builder_prompt is not None
        assert "# Project Intent (Phase: F1.1)" in builder_prompt
        assert "North star: Build a robust file upload feature with validation." in builder_prompt
        assert "Support multiple file formats" in builder_prompt
        assert "Validate file size" in builder_prompt
        assert "Add comprehensive error handling" in builder_prompt
        assert "Store files in memory" in builder_prompt  # Under "Must not:" section


def test_full_workflow_auditor_prompt_with_anchor():
    """Full workflow: create anchor → render for Auditor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="auditor-integration-001",
            project_id="test-project",
            north_star="Refactor authentication to use JWT tokens.",
            success_criteria=[
                "Replace session-based auth with JWT",
                "Add token refresh mechanism",
            ],
            constraints=IntentionConstraints(
                must=["Maintain backwards compatibility with existing endpoints"],
                must_not=["Break existing client integrations"],
            ),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Render for Auditor
        auditor_prompt = load_and_render_for_auditor(
            run_id="auditor-integration-001",
            base_dir=tmpdir,
        )

        # Verify rendered content
        assert auditor_prompt is not None
        assert "# Project Intent (for validation)" in auditor_prompt
        assert "Refactor authentication to use JWT tokens." in auditor_prompt
        assert "Replace session-based auth with JWT" in auditor_prompt
        assert "Maintain backwards compatibility" in auditor_prompt
        assert "Break existing client integrations" in auditor_prompt


def test_full_workflow_doctor_prompt_with_anchor():
    """Full workflow: create anchor → render for Doctor (error recovery)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="doctor-integration-001",
            project_id="test-project",
            north_star="Optimize database queries to reduce latency.",
            success_criteria=[
                "Achieve <100ms response time for read queries",
                "Reduce query count per request",
            ],
            constraints=IntentionConstraints(
                must=["Preserve data integrity"],
                must_not=["Introduce N+1 query problems"],
            ),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Render for Doctor (compact for error context)
        doctor_prompt = load_and_render_for_doctor(
            run_id="doctor-integration-001",
            base_dir=tmpdir,
        )

        # Verify rendered content
        assert doctor_prompt is not None
        assert "# Project Intent (original goal)" in doctor_prompt
        assert "Optimize database queries to reduce latency." in doctor_prompt
        # Doctor uses max_bullets=3, so should be compact
        assert len(doctor_prompt.split("\n")) < 15  # Compact output


def test_validation_catches_out_of_range_refs():
    """Integration test: validator catches invalid intention_refs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor with limited criteria
        anchor = create_anchor(
            run_id="validation-test-001",
            project_id="test-project",
            north_star="Test validation.",
            success_criteria=["SC1", "SC2"],  # Only 2 items (indices 0, 1)
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Create phase with out-of-range refs
        phase = PhaseCreate(
            phase_id="F1.1",
            phase_index=1,
            tier_id="T1",
            name="Test phase",
            intention_refs=IntentionRefs(
                success_criteria=[0, 1, 5, 10],  # 5 and 10 are out of range
            ),
        )

        # Validate (should produce warnings)
        anchor_dict = anchor.model_dump()
        refs_dict = phase.intention_refs.model_dump() if phase.intention_refs else None

        warnings = validate_intention_refs(
            phase_id=phase.phase_id,
            intention_refs=refs_dict,
            anchor_data=anchor_dict,
            strict_mode=False,
        )

        # Should have 2 warnings (for indices 5 and 10)
        assert len(warnings) == 2
        assert "success_criteria[5]" in warnings[0]
        assert "success_criteria[10]" in warnings[1]
        assert "out of range" in warnings[0]


def test_graceful_degradation_when_anchor_missing():
    """Integration test: system gracefully handles missing anchor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Try to render for Builder without creating anchor
        builder_prompt = load_and_render_for_builder(
            run_id="nonexistent-run",
            phase_id="F1.1",
            base_dir=tmpdir,
        )

        # Should return None (graceful degradation)
        assert builder_prompt is None

        # Same for Auditor
        auditor_prompt = load_and_render_for_auditor(
            run_id="nonexistent-run",
            base_dir=tmpdir,
        )
        assert auditor_prompt is None

        # Same for Doctor
        doctor_prompt = load_and_render_for_doctor(
            run_id="nonexistent-run",
            base_dir=tmpdir,
        )
        assert doctor_prompt is None


def test_mixed_phases_with_and_without_intention_refs():
    """Integration test: run can have phases with and without intention_refs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="mixed-phases-test",
            project_id="test-project",
            north_star="Incremental feature rollout.",
            success_criteria=["Deploy to staging", "Monitor metrics"],
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Phase 1: with intention_refs
        phase1 = PhaseCreate(
            phase_id="F1.1",
            phase_index=1,
            tier_id="T1",
            name="Phase with refs",
            intention_refs=IntentionRefs(success_criteria=[0]),
        )

        # Phase 2: without intention_refs (legacy-style)
        phase2 = PhaseCreate(
            phase_id="F1.2",
            phase_index=2,
            tier_id="T1",
            name="Phase without refs",
        )

        # Both should be valid
        anchor_dict = anchor.model_dump()

        # Validate phase1 (should pass)
        warnings1 = validate_intention_refs(
            phase_id=phase1.phase_id,
            intention_refs=phase1.intention_refs.model_dump() if phase1.intention_refs else None,
            anchor_data=anchor_dict,
            strict_mode=False,
        )
        assert len(warnings1) == 0

        # Validate phase2 (should produce warning about missing refs)
        warnings2 = validate_intention_refs(
            phase_id=phase2.phase_id,
            intention_refs=None,
            anchor_data=anchor_dict,
            strict_mode=False,
        )
        # In warn-first mode, missing refs produces a warning
        assert len(warnings2) == 1
        assert "no intention_refs provided" in warnings2[0]


def test_anchor_updates_preserve_refs():
    """Integration test: anchor updates don't break existing intention_refs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create initial anchor
        anchor = create_anchor(
            run_id="update-test-001",
            project_id="test-project",
            north_star="Original goal.",
            success_criteria=["SC1", "SC2", "SC3"],
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Create phase with refs to indices 0, 1
        phase = PhaseCreate(
            phase_id="F1.1",
            phase_index=1,
            tier_id="T1",
            name="Test phase",
            intention_refs=IntentionRefs(success_criteria=[0, 1]),
        )

        # Validate (should pass)
        anchor_dict = anchor.model_dump()
        warnings = validate_intention_refs(
            phase_id=phase.phase_id,
            intention_refs=phase.intention_refs.model_dump() if phase.intention_refs else None,
            anchor_data=anchor_dict,
            strict_mode=False,
        )
        assert len(warnings) == 0

        # Update anchor (append new criterion - doesn't break existing refs)
        from autopack.intention_anchor import update_anchor

        updated_anchor = anchor.model_copy(deep=True)
        updated_anchor.success_criteria.append("SC4")
        updated_anchor = update_anchor(updated_anchor, save=True, base_dir=tmpdir)

        # Validate again (existing refs to indices 0, 1 should still be valid)
        updated_dict = updated_anchor.model_dump()
        warnings_after = validate_intention_refs(
            phase_id=phase.phase_id,
            intention_refs=phase.intention_refs.model_dump() if phase.intention_refs else None,
            anchor_data=updated_dict,
            strict_mode=False,
        )
        assert len(warnings_after) == 0
