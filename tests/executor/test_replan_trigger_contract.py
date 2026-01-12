"""
Tests for Replan Trigger Contract (PR-EXE-8)

These tests verify the approach flaw detection and replanning logic.
"""



def test_replan_trigger_imports():
    """Verify replan trigger can be imported"""
    from autopack.executor.replan_trigger import ReplanTrigger, ReplanConfig

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
    from autopack.executor.replan_trigger import ReplanTrigger, ReplanConfig

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
    from autopack.executor.replan_trigger import ReplanTrigger, ReplanConfig

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


def test_detect_approach_flaw_mixed_errors():
    """Test that approach flaw is not detected for mixed error types"""
    from autopack.executor.replan_trigger import ReplanTrigger, ReplanConfig

    config = ReplanConfig(trigger_threshold=3)
    trigger = ReplanTrigger(config=config)

    # Mixed error types - not a pattern
    error_history = [
        {"attempt": 0, "error_type": "auditor_reject", "error_details": "Error 1"},
        {"attempt": 1, "error_type": "patch_error", "error_details": "Error 2"},
        {"attempt": 2, "error_type": "ci_fail", "error_details": "Error 3"},
    ]

    flaw_type = trigger.detect_approach_flaw({"phase_id": "test-phase"}, error_history)

    assert flaw_type is None


def test_normalize_error_message():
    """Test error message normalization"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger()

    message = "Error in /path/to/file.py:42 at 2024-01-15T10:30:00"
    normalized = trigger._normalize_error_message(message)

    # Should replace paths, line numbers, timestamps
    assert "/path/to/file.py" not in normalized
    assert ":42" not in normalized
    assert "2024-01-15" not in normalized
    assert "[path]" in normalized.lower() or "[n]" in normalized


def test_calculate_message_similarity_identical():
    """Test message similarity for identical messages"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger()

    msg1 = "Error: Module not found"
    msg2 = "Error: Module not found"

    similarity = trigger._calculate_message_similarity(msg1, msg2)
    assert similarity == 1.0


def test_calculate_message_similarity_different():
    """Test message similarity for completely different messages"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger()

    msg1 = "Error: Module not found"
    msg2 = "Success: Everything works fine"

    similarity = trigger._calculate_message_similarity(msg1, msg2)
    assert similarity < 0.5


def test_calculate_message_similarity_similar():
    """Test message similarity for similar messages"""
    from autopack.executor.replan_trigger import ReplanTrigger

    trigger = ReplanTrigger()

    msg1 = "Error at line 10: Variable x is undefined"
    msg2 = "Error at line 25: Variable y is undefined"

    similarity = trigger._calculate_message_similarity(msg1, msg2)
    # Should be similar after normalization (line numbers removed)
    assert similarity > 0.7


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


def test_fatal_error_types():
    """Test that fatal error types trigger immediately"""
    from autopack.executor.replan_trigger import ReplanTrigger, ReplanConfig

    config = ReplanConfig(
        trigger_threshold=3, fatal_error_types=["fatal_error", "unrecoverable"]
    )
    trigger = ReplanTrigger(config=config)

    # Only 1 error, but it's fatal
    error_history = [
        {"attempt": 0, "error_type": "fatal_error", "error_details": "Critical failure"}
    ]

    flaw_type = trigger.detect_approach_flaw({"phase_id": "test-phase"}, error_history)

    assert flaw_type == "fatal_error"
