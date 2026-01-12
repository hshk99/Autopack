# Phase Execution Orchestrator Design (PR-EXE-8)

## Overview

This document describes the extraction of the phase execution orchestrator from `autonomous_executor.py`, which is the CORE refactoring that addresses the god file problem (9,626 lines).

**Problem**: The `execute_phase()` method in `autonomous_executor.py` was 800 lines (lines 1898-2608) and handled:
- Phase initialization and scope setup
- Retry loop orchestration with failure handling
- Doctor integration for debugging and intervention
- Mid-run replanning based on approach flaw detection
- Intention-first stuck handling (BUILD-161)
- Model escalation and safety profiles (BUILD-188)
- Scope reduction (BUILD-190)
- Database state persistence
- Health budget tracking

**Solution**: Extract into 4 focused modules with clear separation of concerns:

1. **phase_orchestrator.py** (~1,300 lines) - Main orchestration logic
2. **doctor_integration.py** (~550 lines) - Doctor invocation and budget tracking
3. **replan_trigger.py** (~400 lines) - Approach flaw detection and replanning
4. **intention_stuck_handler.py** (~300 lines) - Stuck scenario handling

## Impact

### Line Count Reduction
- **Before**: `autonomous_executor.py` = 9,626 lines
- **After**: `autonomous_executor.py` = 9,019 lines
- **Reduction**: 607 lines (~6.3%)
- **New modules**: 4 files, ~2,550 total lines
- **Net change**: Extracted complex logic into well-structured modules

### File Size Target Progress
- **Current**: 9,019 lines
- **Target**: < 5,000 lines (god file threshold)
- **Remaining**: ~4,019 lines to extract (~44.5% reduction needed)

This is the first major step in the god file refactoring initiative.

## Architecture

### Module Responsibilities

#### 1. PhaseOrchestrator (phase_orchestrator.py)

**Core responsibility**: Orchestrate the execution flow for a single phase attempt.

**Key classes**:
```python
class PhaseResult(Enum):
    """Phase execution outcomes"""
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    REPLAN_REQUESTED = "REPLAN_REQUESTED"
    BLOCKED = "BLOCKED"

@dataclass
class ExecutionContext:
    """All dependencies and state for phase execution"""
    phase: Dict
    attempt_index: int
    max_attempts: int
    escalation_level: int
    allowed_paths: List[str]
    run_id: str
    llm_service: Any
    # ... 20+ more dependencies

@dataclass
class ExecutionResult:
    """Result of phase execution attempt"""
    success: bool
    status: str
    phase_result: PhaseResult
    updated_counters: Dict[str, int]
    should_continue: bool

class PhaseOrchestrator:
    """Orchestrates phase execution with retry, doctor, and replan logic"""
    def execute_phase_attempt(self, context: ExecutionContext) -> ExecutionResult
```

**Flow**:
1. Initialize phase (goal anchoring, scope manifest)
2. Check if attempts exhausted
3. Execute single attempt via attempt_runner
4. Handle success (deliverables validation, quality gates)
5. Handle failure (doctor, replan, stuck detection)
6. Update database and return result

**Key features**:
- Goal anchoring (GPT_RESPONSE27) - stores original intent
- Scope manifest generation (BUILD-123v2)
- Database-backed retry state persistence
- Health budget tracking
- Token efficiency telemetry

#### 2. DoctorIntegration (doctor_integration.py)

**Core responsibility**: Manage Doctor invocation with budget tracking.

**Key class**:
```python
class DoctorIntegration:
    """Handles Doctor invocation, budget tracking, and action execution"""

    def should_invoke_doctor(...) -> bool:
        """Determine if Doctor should be invoked based on thresholds"""

    def invoke_doctor(...) -> Optional[DoctorResponse]:
        """Invoke the Autopack Doctor to diagnose a phase failure"""

    def handle_doctor_action(...) -> Tuple[Optional[str], bool]:
        """Handle Doctor's recommended action"""
```

**Budget tracking**:
- Per-phase limits: `max_doctor_calls_per_phase` (default: 2)
- Run-level limits: `max_doctor_calls_per_run` (default: 10)
- Strong model limits: `max_doctor_strong_calls_per_run` (default: 5)
- Infra error limits: `max_doctor_infra_calls_per_run` (default: 3)

**Doctor actions**:
- `retry_with_fix` - Provide builder hint and retry
- `replan` - Trigger mid-run replanning
- `skip_phase` - Mark phase as skipped
- `fatal_error` - Stop execution (unrecoverable)
- `rollback_provider` - Disable failing provider

**Invocation logic**:
- Minimum attempts before Doctor: 2 (except infra errors)
- Infra errors invoke Doctor immediately
- Tracks distinct error categories per phase
- Supports model selection (cheap vs strong)

#### 3. ReplanTrigger (replan_trigger.py)

**Core responsibility**: Detect approach flaws and trigger mid-run replanning.

**Key classes**:
```python
@dataclass
class ReplanConfig:
    """Configuration for replan triggering"""
    trigger_threshold: int = 3  # Consecutive same-error failures
    similarity_threshold: float = 0.8  # Message similarity (0.0-1.0)
    min_message_length: int = 30
    similarity_enabled: bool = True
    fatal_error_types: List[str] = []  # Immediate triggers

class ReplanTrigger:
    """Detects approach flaws via error pattern analysis"""

    def should_trigger_replan(...) -> Tuple[bool, Optional[str]]:
        """Determine if re-planning should be triggered"""

    def detect_approach_flaw(...) -> Optional[str]:
        """Analyze error history for fundamental flaws"""

    def revise_phase_approach(...) -> Optional[Dict]:
        """Invoke LLM to revise phase approach (with goal anchoring)"""
```

**Approach flaw detection**:
1. Check for fatal error types (immediate trigger)
2. Require minimum consecutive same-type failures (threshold)
3. Normalize error messages (strip paths, line numbers, timestamps)
4. Calculate message similarity between consecutive errors
5. Trigger if similarity >= threshold

**Configuration** (from `config/models.yaml`):
```yaml
replan:
  trigger_threshold: 2  # Consecutive same-error failures
  message_similarity_enabled: true
  similarity_threshold: 0.8
  min_message_length: 30
  max_replans_per_phase: 1
  max_replans_per_run: 5
  fatal_error_types:
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

**Goal anchoring** (GPT_RESPONSE27):
- Stores `original_intent` before any replanning
- Includes HARD CONSTRAINT in replan prompt
- Prevents scope reduction or context drift
- Only changes HOW goal is achieved, not WHAT

#### 4. IntentionStuckHandler (intention_stuck_handler.py)

**Core responsibility**: Handle stuck scenarios in intention-first mode (BUILD-161).

**Key class**:
```python
class IntentionStuckHandler:
    """Handles stuck scenarios with intention-first logic"""

    def handle_stuck_scenario(...) -> Tuple[str, str]:
        """Handle stuck scenario and return (decision, message)"""
        # Returns: REPLAN, ESCALATE_MODEL, REDUCE_SCOPE,
        #          BLOCKED_NEEDS_HUMAN, STOP, or CONTINUE
```

**Decision logic**:
1. Check budget exhaustion (token/failure limits)
2. Check truncation issues
3. Decide stuck action based on:
   - Budget proximity
   - Anchor availability (for replanning)
   - Model escalation availability
   - Scope reduction feasibility

**Actions**:
- `REPLAN` - Re-plan with revised approach
- `ESCALATE_MODEL` - Switch to stronger model
- `REDUCE_SCOPE` - Cut scope to minimal viable deliverable
- `BLOCKED_NEEDS_HUMAN` - Request human intervention
- `STOP` - Give up on phase
- `CONTINUE` - Keep trying (error case)

### Integration with AutonomousExecutor

The refactored `execute_phase()` method in `autonomous_executor.py` is now a thin delegator:

```python
def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
    """Execute Builder -> Auditor -> QualityGate pipeline for a phase

    Delegates to PhaseOrchestrator for execution flow (PR-EXE-8).
    """
    from autopack.executor.phase_orchestrator import (
        PhaseOrchestrator, ExecutionContext, PhaseResult,
    )

    # Build execution context with all dependencies
    context = ExecutionContext(
        phase=phase,
        attempt_index=phase_db.retry_attempt,
        max_attempts=MAX_RETRY_ATTEMPTS,
        escalation_level=phase_db.escalation_level,
        allowed_paths=allowed_scope_paths,
        run_id=self.run_id,
        llm_service=self.llm_service,
        # ... 20+ more parameters
    )

    # Execute phase via orchestrator
    orchestrator = PhaseOrchestrator(max_retry_attempts=MAX_RETRY_ATTEMPTS)
    result = orchestrator.execute_phase_attempt(context)

    # Update counters and return result
    for key, value in result.updated_counters.items():
        setattr(self, f"_run_{key}", value)

    if result.phase_result == PhaseResult.COMPLETE:
        return True, "COMPLETE"
    elif result.phase_result == PhaseResult.REPLAN_REQUESTED:
        return False, "REPLAN_REQUESTED"
    # ...
```

**Key points**:
- Original `execute_phase()` signature preserved (backward compatibility)
- All state passed via `ExecutionContext` (no hidden dependencies)
- Result mapping handled at boundary
- Counter updates delegated back to executor

## Testing

### Test Strategy

**Contract tests**: Verify module interfaces and core behavior without full integration.

**Test files**:
1. `test_phase_orchestrator_flow.py` (10 tests) - Orchestrator structure and exhaustion
2. `test_doctor_integration_contract.py` (12 tests) - Doctor invocation and budget tracking
3. `test_replan_trigger_contract.py` (14 tests) - Approach flaw detection and similarity
4. `test_intention_stuck_handler_contract.py` (15 tests) - Stuck handling structure

**Total**: 51 new tests, all passing

### Test Coverage

Tests verify:
- Module imports and instantiation
- Configuration loading from YAML
- Budget enforcement (per-phase, per-run)
- Error pattern detection with message similarity
- Normalization of error messages (paths, line numbers, timestamps)
- Fatal error immediate triggering
- Goal anchoring in replan prompts
- Stuck decision logic
- Enum values and dataclass structures

### Regression Testing

All existing executor tests pass (334 tests) with no regressions.

## Configuration

### models.yaml Integration

The new modules load configuration from `config/models.yaml`:

**Doctor settings**:
```yaml
doctor_models:
  cheap: claude-sonnet-4-5
  strong: claude-opus-4-5
  min_confidence_for_cheap: 0.7
  health_budget_near_limit_ratio: 0.8
  max_builder_attempts_before_complex: 4
  high_risk_categories:
    - import
    - logic
    - patch_apply_error
  low_risk_categories:
    - encoding
    - network
    - file_io
    - validation
  max_escalations_per_phase: 1

doctor:
  allow_execute_fix_global: true
  max_execute_fix_per_phase: 1
```

**Replan settings**:
```yaml
replan:
  trigger_threshold: 2
  message_similarity_enabled: true
  similarity_threshold: 0.8
  min_message_length: 30
  max_replans_per_phase: 1
  max_replans_per_run: 5
  fatal_error_types:
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

## Design Decisions

### 1. Why Dataclasses for Context?

**Problem**: The original `execute_phase()` method had 20+ parameters passed through multiple helper functions.

**Solution**: Use `ExecutionContext` dataclass to bundle all dependencies.

**Benefits**:
- Single source of truth for execution state
- Easy to add new dependencies without signature changes
- Type-safe access to context fields
- Clear documentation of what's needed for execution

### 2. Why Separate Replan from Doctor?

**Problem**: Both Doctor and replan trigger can initiate replanning.

**Decision**: Keep them separate with different triggers.

**Rationale**:
- Doctor is reactive (invoked after N failures)
- Replan trigger is proactive (detects patterns)
- Different invocation criteria
- Different budget tracking
- Doctor can also skip, rollback, or fatal error
- Replan is purely about approach revision

### 3. Why Message Similarity?

**Problem**: Distinguish "approach flaw" from "transient failure".

**Solution**: Normalize error messages and check similarity.

**Example**:
```
Error 1: "ModuleNotFoundError: No module named 'foo' at /path/file.py:42"
Error 2: "ModuleNotFoundError: No module named 'foo' at /path/file.py:52"
After normalization: Both become "modulenotfounderror: no module named 'foo' at [PATH]:[N]"
Similarity: 1.0 (identical approach flaw)
```

**Benefits**:
- Reduces false positives (different errors don't trigger replan)
- Robust to transient changes (line numbers, timestamps)
- Configurable threshold (0.8 default)

### 4. Why Goal Anchoring?

**Problem**: Mid-run replanning can drift from original intent.

**Solution**: Store `original_intent` and include HARD CONSTRAINT in replan prompt.

**Example prompt**:
```
## CRITICAL CONSTRAINT - GOAL ANCHORING
The revised approach MUST still achieve this core goal:
**Original Intent**: {original_intent}

Do NOT reduce scope, skip functionality, or change what the phase achieves.
Only change HOW it achieves the goal, not WHAT it achieves.
```

**Benefits**:
- Prevents scope creep in reverse (scope reduction)
- Maintains project requirements
- Provides LLM with clear constraint
- Traceable through `_original_intent` field

## Future Work

### Remaining God File Reduction

**Current status**: 9,019 lines in `autonomous_executor.py`
**Target**: < 5,000 lines
**Remaining**: ~4,019 lines to extract

**Next refactorings** (from cursor24_pr_exe_series.md):
1. **PR-EXE-9**: Extract Builder/Auditor/QualityGate pipeline (~500 lines)
2. **PR-EXE-10**: Extract deliverables validation (~300 lines)
3. **PR-EXE-11**: Extract scope management (~400 lines)
4. **PR-EXE-12**: Extract model escalation logic (~300 lines)
5. **PR-EXE-13**: Extract health budget tracking (~250 lines)
6. **PR-EXE-14**: Extract learning hints system (~350 lines)

**Estimated final size**: ~4,000-4,500 lines (under threshold)

### Module Enhancements

1. **Replan trigger improvements**:
   - Add support for multiple similarity algorithms (Levenshtein, Jaccard)
   - Track replan effectiveness (did it help?)
   - Machine learning for pattern detection

2. **Doctor integration enhancements**:
   - Doctor response caching (avoid duplicate calls)
   - Doctor confidence tracking and learning
   - Multi-turn Doctor conversations

3. **Stuck handler improvements**:
   - More sophisticated budget prediction
   - Learning from past stuck scenarios
   - Automated scope reduction suggestions

4. **Testing enhancements**:
   - Full integration tests (not just contract tests)
   - Performance regression tests
   - Chaos testing (random failures)

## References

- **PR-EXE-8**: This refactoring (Phase Execution Orchestrator extraction)
- **BUILD-041**: Phase execution orchestration design
- **BUILD-161**: Intention-first stuck handling
- **BUILD-188**: Model escalation and safety profiles
- **BUILD-190**: Scope reduction
- **GPT_RESPONSE8**: Doctor integration budget tracking
- **GPT_RESPONSE27**: Goal anchoring to prevent context drift
- **BUILD-123v2**: Scope manifest generation
- **BUILD-146**: Failure hardening

## Summary

This refactoring successfully extracted the phase execution orchestrator from the 9,626-line god file `autonomous_executor.py`. The 800-line `execute_phase()` method is now a thin delegator to 4 focused modules:

1. **PhaseOrchestrator** - Main execution flow
2. **DoctorIntegration** - Debugging and intervention
3. **ReplanTrigger** - Approach flaw detection
4. **IntentionStuckHandler** - Stuck scenario handling

**Achievements**:
- ✅ 607 lines removed from god file (~6.3% reduction)
- ✅ Clear separation of concerns
- ✅ 51 new tests, all passing
- ✅ 334 existing tests, no regressions
- ✅ Passes ruff linting
- ✅ Backward compatible (same external interface)
- ✅ Configuration-driven (models.yaml)

This is the **CORE refactoring** that makes future god file reduction possible by establishing the pattern for extraction.
