"""
Tests for IntentionAnchor prompt rendering (determinism + bullet caps).

Intention behind these tests: ensure rendered output is stable, deterministic,
and respects budget constraints (max bullets).
"""

from autopack.intention_anchor import (
    IntentionConstraints,
    create_anchor,
    render_compact,
    render_for_prompt,
)


def test_render_for_prompt_minimal():
    """Minimal anchor should render with just north_star."""
    anchor = create_anchor(
        run_id="render-test-001",
        project_id="test-project",
        north_star="Build a minimal test anchor.",
    )

    output = render_for_prompt(anchor)

    assert "## Intention Anchor (canonical)" in output
    assert "North star: Build a minimal test anchor." in output
    assert output.endswith("\n")


def test_render_for_prompt_exact_shape_minimal():
    """Exact output shape test: minimal anchor with no bullets."""
    anchor = create_anchor(
        run_id="shape-test-001",
        project_id="test-project",
        north_star="Exact shape test.",
    )

    output = render_for_prompt(anchor)
    lines = output.strip().split("\n")

    # Exact shape: 2 lines (header + north_star)
    assert len(lines) == 2
    assert lines[0] == "## Intention Anchor (canonical)"
    assert lines[1] == "North star: Exact shape test."


def test_render_for_prompt_with_success_criteria():
    """Anchor with success criteria should include bullets."""
    anchor = create_anchor(
        run_id="render-test-002",
        project_id="test-project",
        north_star="Test success criteria rendering.",
        success_criteria=["SC1: First criterion", "SC2: Second criterion"],
    )

    output = render_for_prompt(anchor)

    assert "Success criteria:" in output
    assert "- SC1: First criterion" in output
    assert "- SC2: Second criterion" in output


def test_render_for_prompt_with_constraints():
    """Anchor with constraints should render must/must_not sections."""
    anchor = create_anchor(
        run_id="render-test-003",
        project_id="test-project",
        north_star="Test constraint rendering.",
        constraints=IntentionConstraints(
            must=["Use strict typing", "Write tests"],
            must_not=["Break existing APIs", "Add dependencies"],
            preferences=["Prefer functional style"],
        ),
    )

    output = render_for_prompt(anchor)

    assert "Must:" in output
    assert "- Use strict typing" in output
    assert "- Write tests" in output

    assert "Must not:" in output
    assert "- Break existing APIs" in output
    assert "- Add dependencies" in output

    assert "Preferences:" in output
    assert "- Prefer functional style" in output


def test_render_for_prompt_caps_bullets():
    """Renderer should cap bullets at max_bullets."""
    anchor = create_anchor(
        run_id="render-test-004",
        project_id="test-project",
        north_star="Test bullet capping.",
        success_criteria=[f"SC{i}" for i in range(1, 21)],  # 20 criteria
    )

    output = render_for_prompt(anchor, max_bullets=5)

    # Should only include first 5
    assert "- SC1" in output
    assert "- SC5" in output
    assert "- SC6" not in output
    assert "- SC20" not in output


def test_render_for_prompt_deterministic():
    """Rendering the same anchor multiple times should produce identical output."""
    anchor = create_anchor(
        run_id="render-test-005",
        project_id="test-project",
        north_star="Test determinism.",
        success_criteria=["SC1", "SC2", "SC3"],
        constraints=IntentionConstraints(
            must=["M1", "M2"],
            must_not=["MN1"],
        ),
    )

    output1 = render_for_prompt(anchor)
    output2 = render_for_prompt(anchor)
    output3 = render_for_prompt(anchor)

    assert output1 == output2 == output3


def test_render_for_prompt_no_timestamps():
    """Rendered output should not include timestamps (for determinism)."""
    anchor = create_anchor(
        run_id="render-test-006",
        project_id="test-project",
        north_star="Test no timestamps in output.",
    )

    output = render_for_prompt(anchor)

    # Should not contain ISO datetime patterns
    assert "2026" not in output
    assert "2025" not in output
    assert "T" not in output or "Test" in output  # Allow 'T' in words
    assert "Z" not in output  # No UTC indicator


def test_render_for_prompt_strips_whitespace():
    """Renderer should strip leading/trailing whitespace from bullets."""
    anchor = create_anchor(
        run_id="render-test-007",
        project_id="test-project",
        north_star="  Whitespace test.  ",
        success_criteria=["  SC1  ", "SC2  ", "  SC3"],
    )

    output = render_for_prompt(anchor)

    assert "North star: Whitespace test." in output
    assert "- SC1" in output
    assert "- SC2" in output
    assert "- SC3" in output
    # No extra spaces
    assert "  SC1  " not in output


def test_render_for_prompt_stable_ordering():
    """Output order should be stable (north_star → criteria → must → must_not → prefs)."""
    anchor = create_anchor(
        run_id="render-test-008",
        project_id="test-project",
        north_star="Test stable ordering.",
        success_criteria=["SC1"],
        constraints=IntentionConstraints(
            must=["M1"],
            must_not=["MN1"],
            preferences=["P1"],
        ),
    )

    output = render_for_prompt(anchor)
    lines = output.strip().split("\n")

    # Find line indices
    north_star_idx = next(i for i, line in enumerate(lines) if "North star:" in line)
    criteria_idx = next(i for i, line in enumerate(lines) if "Success criteria:" in line)
    must_idx = next(i for i, line in enumerate(lines) if line.strip() == "Must:")
    must_not_idx = next(i for i, line in enumerate(lines) if line.strip() == "Must not:")
    prefs_idx = next(i for i, line in enumerate(lines) if "Preferences:" in line)

    # Verify order
    assert north_star_idx < criteria_idx < must_idx < must_not_idx < prefs_idx


def test_render_for_prompt_exact_shape_full():
    """Exact output shape test: fully-populated anchor with all sections."""
    anchor = create_anchor(
        run_id="shape-test-002",
        project_id="test-project",
        north_star="Full shape test.",
        success_criteria=["SC1", "SC2"],
        constraints=IntentionConstraints(
            must=["M1"],
            must_not=["MN1", "MN2"],
            preferences=["P1"],
        ),
    )

    output = render_for_prompt(anchor)
    expected_lines = [
        "## Intention Anchor (canonical)",
        "North star: Full shape test.",
        "Success criteria:",
        "- SC1",
        "- SC2",
        "Must:",
        "- M1",
        "Must not:",
        "- MN1",
        "- MN2",
        "Preferences:",
        "- P1",
    ]

    actual_lines = output.strip().split("\n")
    assert actual_lines == expected_lines, f"Expected:\n{expected_lines}\n\nGot:\n{actual_lines}"


def test_render_compact():
    """render_compact should produce a single-line summary."""
    anchor = create_anchor(
        run_id="compact-test-001",
        project_id="test-project",
        north_star="A very long north star description that exceeds eighty characters and should be truncated for compact rendering.",
        anchor_id="IA-compact-123",
    )

    output = render_compact(anchor)

    assert "[IA-compact-123 v1]" in output
    assert len(output.split("\n")) == 1  # Single line
    assert len(output) < 200  # Should be compact


def test_render_compact_includes_version():
    """render_compact should include version number."""
    anchor = create_anchor(
        run_id="compact-test-002",
        project_id="test-project",
        north_star="Test version in compact render.",
        anchor_id="IA-compact-456",
    )

    anchor_v1 = anchor
    output_v1 = render_compact(anchor_v1)
    assert "v1" in output_v1

    # Simulate version bump
    anchor_v2 = anchor_v1.model_copy(deep=True)
    anchor_v2.version = 2
    output_v2 = render_compact(anchor_v2)
    assert "v2" in output_v2


def test_render_for_prompt_empty_sections_omitted():
    """Sections with no content should not appear in output."""
    anchor = create_anchor(
        run_id="empty-sections-test",
        project_id="test-project",
        north_star="Test empty section handling.",
        # No success_criteria, no constraints
    )

    output = render_for_prompt(anchor)

    # Should have north_star but not empty sections
    assert "North star:" in output
    assert "Success criteria:" not in output
    assert "Must:" not in output
    assert "Must not:" not in output
    assert "Preferences:" not in output


def test_render_for_prompt_max_bullets_per_section():
    """Each section should independently respect max_bullets."""
    anchor = create_anchor(
        run_id="per-section-cap-test",
        project_id="test-project",
        north_star="Test per-section caps.",
        success_criteria=[f"SC{i}" for i in range(1, 11)],  # 10 items
        constraints=IntentionConstraints(
            must=[f"M{i}" for i in range(1, 11)],  # 10 items
            must_not=[f"MN{i}" for i in range(1, 11)],  # 10 items
            preferences=[f"P{i}" for i in range(1, 11)],  # 10 items
        ),
    )

    output = render_for_prompt(anchor, max_bullets=3)

    # Each section should cap at 3
    assert "- SC1" in output
    assert "- SC3" in output
    assert "- SC4" not in output

    assert "- M1" in output
    assert "- M3" in output
    assert "- M4" not in output

    assert "- MN1" in output
    assert "- MN3" in output
    assert "- MN4" not in output

    assert "- P1" in output
    assert "- P3" in output
    assert "- P4" not in output
