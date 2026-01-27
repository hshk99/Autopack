"""
Tests for Replan Trigger Contract (PR-EXE-8)

These tests verify the approach flaw detection and replanning logic.
"""


def test_replan_trigger_imports():
    """Verify replan trigger can be imported"""
    from autopack.executor.replan_trigger import ReplanConfig, ReplanTrigger

    assert ReplanTrigger is not None
    assert ReplanConfig is not None


def test_replan_config_defaults():
    """Verify ReplanConfig default values"""
    from autopack.executor.replan_trigger import ReplanConfig

    config = ReplanConfig()
    assert config.trigger_threshold == 3
    assert config.similarity_threshold == 0.8
    assert config.min_message_length == 30
    assert config.similarity_enabled is True
    assert config.fatal_error_types == []


def test_replan_trigger_instantiation():
    """Verify ReplanTrigger can be instantiated"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger(max_replans_per_phase=2, max_replans_per_run=5)
    assert trigger.max_replans_per_phase == 2
    assert trigger.max_replans_per_run == 5


def test_should_trigger_replan_below_threshold():
    """Test that replan is not triggered below error threshold"""
    from autopack.executor.replan_trigger import ReplanConfig, ReplanTrigger

    # Explicitly set threshold to 3 to avoid YAML config override
    config = ReplanConfig(trigger_threshold=3)
    trigger = ReplanTrigger(config=config)

    # Only 2 errors, threshold is 3
    error_history = [
        {"attempt": 0, "error_type": "auditor_reject", "error_details": "Error 1"},
        {"attempt": 1, "error_type": "auditor_reject", "error_details": "Error 2"},
    ]

    should_replan, flaw_type = trigger.should_trigger_replan(
        phase={"phase_id": "test-phase"},
        error_history=error_history,
        replan_count=0,
        run_replan_count=0,
    )

    assert should_replan is False
    assert flaw_type is None


def test_should_trigger_replan_at_threshold():
    """Test that replan is triggered at error threshold"""
    from autopack.executor.replan_trigger import ReplanConfig, ReplanTrigger

    config = ReplanConfig(trigger_threshold=3, similarity_enabled=False)
    trigger = ReplanTrigger(config=config)

    # 3 consecutive same-type errors
    error_history = [
        {"attempt": 0, "error_type": "auditor_reject", "error_details": "Error 1"},
        {"attempt": 1, "error_type": "auditor_reject", "error_details": "Error 2"},
        {"attempt": 2, "error_type": "auditor_reject", "error_details": "Error 3"},
    ]

    should_replan, flaw_type = trigger.should_trigger_replan(
        phase={"phase_id": "test-phase"},
        error_history=error_history,
        replan_count=0,
        run_replan_count=0,
    )

    assert should_replan is True
    assert flaw_type == "auditor_reject"


def test_should_trigger_replan_max_phase_replans():
    """Test that replan is not triggered if max per-phase replans reached"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger(max_replans_per_phase=2)

    error_history = [
        {"attempt": 0, "error_type": "auditor_reject", "error_details": "Error 1"},
        {"attempt": 1, "error_type": "auditor_reject", "error_details": "Error 2"},
        {"attempt": 2, "error_type": "auditor_reject", "error_details": "Error 3"},
    ]

    # Already replanned 2 times for this phase
    should_replan, flaw_type = trigger.should_trigger_replan(
        phase={"phase_id": "test-phase"},
        error_history=error_history,
        replan_count=2,
        run_replan_count=2,
    )

    assert should_replan is False
    assert flaw_type is None


def test_should_trigger_replan_max_run_replans():
    """Test that replan is not triggered if max run replans reached"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger(max_replans_per_run=5)

    error_history = [
        {"attempt": 0, "error_type": "auditor_reject", "error_details": "Error 1"},
        {"attempt": 1, "error_type": "auditor_reject", "error_details": "Error 2"},
        {"attempt": 2, "error_type": "auditor_reject", "error_details": "Error 3"},
    ]

    # Already replanned 5 times in this run
    should_replan, flaw_type = trigger.should_trigger_replan(
        phase={"phase_id": "test-phase"},
        error_history=error_history,
        replan_count=0,
        run_replan_count=5,
    )

    assert should_replan is False
    assert flaw_type is None


# NOTE: Tests for detect_approach_flaw, normalize_error_message, and calculate_message_similarity
# have been moved to test_error_analysis_contract.py since these methods are now in ErrorAnalyzer class


def test_revise_phase_approach_no_llm_service():
    """Test that revise_phase_approach returns None without llm_service"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger()

    result = trigger.revise_phase_approach(
        phase={"phase_id": "test-phase", "description": "Test"},
        flaw_type="auditor_reject",
        error_history=[],
        original_intent="Do something",
        llm_service=None,  # No LLM service
    )

    assert result is None


# NOTE: test_fatal_error_types has been moved to test_error_analysis_contract.py
# since fatal error detection is now handled by ErrorAnalyzer class
