# Error Recovery Guide

This guide documents error recovery strategies used in the autopack autonomous build system, including retry logic, fallback patterns, error categorization, and recovery mechanisms.

## Table of Contents

- [Overview](#overview)
- [Error Categories](#error-categories)
- [Retry Logic](#retry-logic)
- [Fallback Patterns](#fallback-patterns)
- [Recovery Strategies](#recovery-strategies)
- [Code Examples](#code-examples)
- [Best Practices](#best-practices)

---

## Overview

The autopack system implements robust error recovery to handle:

- **Transient failures**: Network issues, rate limits, temporary unavailability
- **Model failures**: Invalid responses, context overflow, capability limitations
- **Validation failures**: Protected path violations, malformed output, missing deliverables
- **System failures**: File system errors, database issues, resource constraints

**Key Principles:**
- Fail gracefully with informative error messages
- Retry transient failures with exponential backoff
- Escalate to more capable models when needed
- Preserve execution state for debugging
- Never lose work due to recoverable errors

---

## Error Categories

Errors are categorized by severity and recoverability:

### Category 1: Transient Errors (Recoverable)

**Characteristics:**
- Temporary in nature
- High probability of success on retry
- No code changes required

**Examples:**
- Network timeouts
- API rate limits (429 errors)
- Temporary service unavailability (503 errors)
- Database lock conflicts

**Recovery Strategy:**
- Immediate retry with exponential backoff
- Maximum 3-5 retry attempts
- Log each attempt for monitoring

---

### Category 2: Model Errors (Escalatable)

**Characteristics:**
- Model-specific limitations
- May succeed with different model
- Requires model escalation or fallback

**Examples:**
- Context window overflow
- Invalid JSON response format
- Incomplete code generation
- Model capability limitations

**Recovery Strategy:**
- Escalate to higher-tier model
- Reduce context if token budget exceeded
- Retry with adjusted parameters

---

### Category 3: Validation Errors (Fixable)

**Characteristics:**
- Output doesn't meet requirements
- Can be fixed with clarified prompt
- Requires regeneration

**Examples:**
- Protected path violations
- Missing required deliverables
- Incomplete file content
- Invalid file modes

**Recovery Strategy:**
- Regenerate with stricter constraints
- Add explicit validation rules to prompt
- Reduce scope if too complex

---

### Category 4: Fatal Errors (Non-Recoverable)

**Characteristics:**
- Cannot be resolved automatically
- Requires human intervention
- Indicates system or configuration issue

**Examples:**
- Invalid API credentials
- Corrupted database
- Missing required files
- Insufficient permissions

**Recovery Strategy:**
- Log detailed error information
- Halt execution gracefully
- Provide actionable error message
- Preserve state for debugging

---

## Retry Logic

The system implements intelligent retry logic with exponential backoff:

### Basic Retry Pattern

```python
def execute_with_retry(
    operation: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0
) -> Any:
    """
    Execute operation with exponential backoff retry.

    Args:
        operation: Function to execute
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries

    Returns:
        Operation result if successful

    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            result = operation()
            if attempt > 0:
                logger.info(f"Operation succeeded on attempt {attempt + 1}")
            return result

        except TransientError as e:
            last_exception = e

            if attempt < max_retries:
                # Exponential backoff: 1s, 2s, 4s, 8s, ...
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries} retries exhausted")
                raise last_exception

        except FatalError as e:
            # Don't retry fatal errors
            logger.error(f"Fatal error, not retrying: {e}")
            raise

    raise last_exception
```

### Retry Configuration

**Default Settings:**
- `max_retries`: 3 attempts
- `base_delay`: 1.0 seconds
- `max_delay`: 60.0 seconds
- `backoff_multiplier`: 2.0 (exponential)

**Retry Schedule:**
- Attempt 1: Immediate
- Attempt 2: 1 second delay
- Attempt 3: 2 second delay
- Attempt 4: 4 second delay

---

## Fallback Patterns

The system uses multiple fallback strategies:

### Pattern 1: Model Fallback Chain

**Strategy**: Try alternative models in order of capability.

```python
MODEL_FALLBACK_CHAINS = {
    'tier_1': [
        'claude-3-opus-20240229',      # Primary
        'gpt-4-turbo-preview',         # Alternative 1
        'claude-3-sonnet-20240229'     # Alternative 2
    ],
    'tier_2': [
        'claude-3-sonnet-20240229',    # Primary
        'gpt-4-1106-preview',          # Alternative 1
        'claude-3-haiku-20240307'      # Alternative 2
    ],
    'tier_3': [
        'claude-3-haiku-20240307',     # Primary
        'gpt-3.5-turbo-16k',           # Alternative 1
        'claude-instant-1.2'           # Alternative 2
    ]
}

def execute_with_model_fallback(
    phase_spec: Dict,
    tier: int
) -> Dict[str, Any]:
    """
    Execute phase with model fallback chain.
    """
    fallback_chain = MODEL_FALLBACK_CHAINS[f'tier_{tier}']
    last_error = None

    for model in fallback_chain:
        try:
            logger.info(f"Attempting execution with {model}")
            result = execute_phase(phase_spec, model=model)
            return result

        except ModelError as e:
            last_error = e
            logger.warning(f"Model {model} failed: {e}")
            continue

    raise ModelError(f"All models in tier {tier} failed: {last_error}")
```

### Pattern 2: Context Reduction Fallback

**Strategy**: Reduce context size if token budget exceeded.

```python
def execute_with_context_fallback(
    phase_spec: Dict,
    context_files: List[str],
    max_budget: int
) -> Dict[str, Any]:
    """
    Execute with progressive context reduction.
    """
    reduction_levels = [1.0, 0.75, 0.5, 0.25]  # 100%, 75%, 50%, 25%

    for level in reduction_levels:
        try:
            # Select top N% of context files by relevance
            reduced_context = select_top_context(
                context_files,
                percentage=level
            )

            estimated_tokens = estimate_tokens(
                phase_spec,
                reduced_context
            )

            if estimated_tokens <= max_budget:
                logger.info(
                    f"Using {level*100}% of context "
                    f"({len(reduced_context)} files)"
                )
                return execute_phase(phase_spec, reduced_context)

        except ContextOverflowError:
            continue

    raise ContextOverflowError(
        "Cannot fit phase in budget even with minimal context"
    )
```

### Pattern 3: Scope Reduction Fallback

**Strategy**: Break large phases into smaller sub-phases.

```python
def execute_with_scope_fallback(
    phase_spec: Dict
) -> Dict[str, Any]:
    """
    Split complex phase into smaller sub-phases.
    """
    try:
        # Try full phase first
        return execute_phase(phase_spec)

    except ComplexityError:
        logger.warning("Phase too complex, splitting into sub-phases")

        # Split deliverables into groups
        sub_phases = split_phase(phase_spec, max_files_per_phase=3)

        results = []
        for i, sub_phase in enumerate(sub_phases):
            logger.info(f"Executing sub-phase {i+1}/{len(sub_phases)}")
            result = execute_phase(sub_phase)
            results.append(result)

        # Aggregate results
        return aggregate_results(results)
```

---

## Recovery Strategies

### Strategy 1: Checkpoint and Resume

**Goal**: Save progress and resume from last successful point.

**Implementation:**
- Save phase state after each successful step
- Store in database with timestamp
- Resume from checkpoint on failure
- Clean up checkpoints after completion

**Benefits:**
- No lost work on transient failures
- Faster recovery (skip completed steps)
- Debugging support (inspect intermediate state)

---

### Strategy 2: Graceful Degradation

**Goal**: Deliver partial results when full execution fails.

**Implementation:**
- Mark successfully completed files
- Return partial results with error details
- Allow continuation with manual intervention
- Preserve all generated content

**Benefits:**
- Some progress better than none
- Easier to debug and fix issues
- Reduces wasted LLM calls

---

### Strategy 3: Error Context Preservation

**Goal**: Capture detailed context for debugging.

**Implementation:**
- Log full error stack traces
- Save LLM request/response pairs
- Record system state at failure time
- Include relevant file contents

**Benefits:**
- Faster root cause analysis
- Better error reporting
- Improved system reliability over time

---

## Code Examples

### Example 1: Phase Execution with Full Recovery

```python
from autopack.phase_executor import PhaseExecutor
from autopack.errors import TransientError, ModelError, ValidationError

def execute_phase_with_recovery(
    executor: PhaseExecutor,
    phase_spec: Dict[str, Any],
    context_files: List[str]
) -> Dict[str, Any]:
    """
    Execute phase with comprehensive error recovery.
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Attempt execution
            result = executor.execute_phase(
                phase_spec=phase_spec,
                context_files=context_files
            )

            # Validate result
            if not result.get('success'):
                raise ValidationError(
                    f"Phase failed validation: {result.get('errors')}"
                )

            return result

        except TransientError as e:
            # Retry transient errors with backoff
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                logger.warning(
                    f"Transient error on attempt {attempt + 1}: {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error("Max retries exceeded for transient error")
                raise

        except ModelError as e:
            # Try fallback model
            logger.warning(f"Model error: {e}. Trying fallback...")
            executor.escalate_model()
            continue

        except ValidationError as e:
            # Regenerate with stricter constraints
            logger.warning(f"Validation error: {e}. Regenerating...")
            phase_spec['constraints'] = add_strict_constraints(
                phase_spec.get('constraints', [])
            )
            continue

    raise RuntimeError(f"Phase execution failed after {max_retries} attempts")
```

### Example 2: Orchestrator with Recovery

```python
from autopack.phase_orchestrator import PhaseOrchestrator

def run_phases_with_recovery(
    orchestrator: PhaseOrchestrator,
    phases: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Run multiple phases with checkpoint recovery.
    """
    results = []
    checkpoint = load_checkpoint()  # Resume from last successful phase

    start_index = checkpoint.get('last_completed_phase', -1) + 1

    for i, phase in enumerate(phases[start_index:], start=start_index):
        try:
            logger.info(f"Executing phase {i+1}/{len(phases)}")

            result = orchestrator.execute_phase(phase)
            results.append(result)

            # Save checkpoint after each success
            save_checkpoint({
                'last_completed_phase': i,
                'results': results,
                'timestamp': datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Phase {i+1} failed: {e}")

            # Save error state
            save_checkpoint({
                'last_completed_phase': i - 1,
                'failed_phase': i,
                'error': str(e),
                'results': results
            })

            # Decide whether to continue or stop
            if orchestrator.stop_on_failure:
                raise
            else:
                results.append({
                    'success': False,
                    'phase_index': i,
                    'error': str(e)
                })

    # Clean up checkpoint on full success
    if all(r.get('success', False) for r in results):
        clear_checkpoint()

    return {
        'total_phases': len(phases),
        'successful_phases': sum(1 for r in results if r.get('success')),
        'failed_phases': sum(1 for r in results if not r.get('success')),
        'results': results
    }
```

---

## Best Practices

### 1. Categorize Errors Correctly

**Goal**: Apply appropriate recovery strategy for each error type.

**Guidelines:**
- Use specific exception types (not generic `Exception`)
- Document error categories in code
- Test error handling paths
- Log error categories for monitoring

---

### 2. Implement Exponential Backoff

**Goal**: Avoid overwhelming services during outages.

**Guidelines:**
- Start with short delays (1-2 seconds)
- Double delay on each retry
- Cap maximum delay (60 seconds)
- Add jitter to prevent thundering herd

---

### 3. Preserve Execution Context

**Goal**: Enable debugging and recovery.

**Guidelines:**
- Log all retry attempts with details
- Save LLM request/response pairs
- Store intermediate results
- Include timestamps and attempt numbers

---

### 4. Set Reasonable Retry Limits

**Goal**: Balance recovery vs. fast failure.

**Guidelines:**
- 3-5 retries for transient errors
- 2-3 model fallbacks per tier
- 2-3 context reduction attempts
- No retries for fatal errors

---

### 5. Monitor Recovery Metrics

**Goal**: Identify systemic issues.

**Metrics to Track:**
- Retry success rate by error type
- Average retries per phase
- Model fallback frequency
- Context reduction frequency
- Time spent in recovery

---

### 6. Fail Fast for Fatal Errors

**Goal**: Don't waste time on unrecoverable errors.

**Guidelines:**
- Detect fatal errors early
- Provide clear error messages
- Include remediation steps
- Log for post-mortem analysis

---

### 7. Test Recovery Paths

**Goal**: Ensure recovery logic works correctly.

**Testing Strategies:**
- Inject transient errors in tests
- Simulate rate limits and timeouts
- Test with invalid model responses
- Verify checkpoint/resume logic
- Test graceful degradation

---

*Last Updated: 2024*
*Version: 7.0*
