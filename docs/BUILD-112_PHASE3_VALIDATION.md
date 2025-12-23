# BUILD-112 Phase 3: Deep Retrieval Production Validation

**Status**: ✅ COMPLETE (95% → 100%)
**Date**: 2025-12-22
**Goal**: Validate deep retrieval escalation triggers in production scenarios

---

## Overview

Phase 3 completes BUILD-112's deep retrieval escalation system by running production validation tests. All code was already implemented in previous phases:

- ✅ `src/autopack/diagnostics/retrieval_triggers.py` (Stage 1 → Stage 2 escalation logic)
- ✅ `src/autopack/diagnostics/deep_retrieval.py` (Stage 2 deep retrieval engine)
- ✅ Integration in `diagnostics_agent.py` (orchestration)

This phase validates the system meets all acceptance criteria through automated tests.

---

## Validation Tests

### Test Suite: `tests/test_build112_phase3_deep_retrieval_validation.py`

**Test Coverage**:

1. **Stage 2 Trigger on Repeated Failures**
   - ✅ Verifies escalation after 3 consecutive Stage 1 failures
   - ✅ Confirms trigger logic activates correctly

2. **Stage 2 Trigger on Complex Error Patterns**
   - ✅ Tests multi-file error pattern detection
   - ✅ Validates escalation on cross-module dependencies

3. **Snippet Caps Enforcement**
   - ✅ Verifies ≤3 snippets per category
   - ✅ Confirms ≤120 lines per snippet
   - ✅ Tests cap enforcement across all categories

4. **Token Budget Compliance**
   - ✅ Validates ≤12 total snippets across all categories
   - ✅ Tests budget enforcement with 20+ candidate snippets

5. **Citation Format Validation**
   - ✅ Confirms file path + line range format
   - ✅ Validates start_line/end_line consistency
   - ✅ Tests path format (src/ prefix)

6. **DiagnosticsAgent Integration**
   - ✅ Tests end-to-end Stage 2 escalation flow
   - ✅ Validates integration with trigger detector
   - ✅ Confirms deep context retrieval

7. **False Positive Prevention**
   - ✅ Verifies Stage 2 does NOT trigger on first attempt
   - ✅ Confirms no escalation on simple single-file errors

---

## Acceptance Criteria

### ✅ All Criteria Met

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Stage 2 triggers after 3 consecutive failures | ✅ PASS | `test_stage2_trigger_on_repeated_failures` |
| Stage 2 triggers on complex error patterns | ✅ PASS | `test_stage2_trigger_on_complex_error_pattern` |
| Snippet caps enforced (≤3 per category) | ✅ PASS | `test_stage2_snippet_caps` |
| Line caps enforced (≤120 per snippet) | ✅ PASS | `test_stage2_snippet_caps` |
| Token budget enforced (≤12 total snippets) | ✅ PASS | `test_stage2_token_budget_compliance` |
| Citations include file path + line range | ✅ PASS | `test_stage2_citation_format` |
| DiagnosticsAgent integration works | ✅ PASS | `test_diagnostics_agent_stage2_integration` |
| No false positives on first attempt | ✅ PASS | `test_stage2_no_false_positives` |

---

## Running the Tests

```bash
# Run validation tests
pytest tests/test_build112_phase3_deep_retrieval_validation.py -v

# Run with coverage
pytest tests/test_build112_phase3_deep_retrieval_validation.py --cov=autopack.diagnostics --cov-report=html
```

**Expected Output**:
```
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_trigger_on_repeated_failures PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_trigger_on_complex_error_pattern PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_snippet_caps PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_token_budget_compliance PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_citation_format PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_diagnostics_agent_stage2_integration PASSED
tests/test_build112_phase3_deep_retrieval_validation.py::TestDeepRetrievalEscalation::test_stage2_no_false_positives PASSED

======== 7 passed in 2.34s ========
```

---

## Production Behavior

### Stage 1 → Stage 2 Escalation Flow

1. **Initial Failure** (Attempt 1)
   - Stage 1 retrieval (basic context)
   - Builder attempts fix
   - If fails → Attempt 2

2. **Second Failure** (Attempt 2)
   - Stage 1 retrieval (expanded context)
   - Builder attempts fix
   - If fails → Attempt 3

3. **Third Failure** (Attempt 3)
   - **Stage 2 TRIGGERED** (deep retrieval)
   - Retrieves up to 12 snippets across 4 categories:
     - Implementation (≤3 snippets)
     - Tests (≤3 snippets)
     - Config (≤3 snippets)
     - Docs (≤3 snippets)
   - Each snippet ≤120 lines
   - Citations include file path + line range
   - Builder receives enriched context

### Stage 2 Caps Summary

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Snippets per category | 3 | Hard cap in `DeepRetrievalEngine` |
| Lines per snippet | 120 | Truncation in retrieval |
| Total snippets | 12 | Budget enforcement (3 × 4 categories) |
| Categories | 4 | implementation, tests, config, docs |

---

## Integration Points

### DiagnosticsAgent

```python
# Stage 2 escalation check
if self.trigger_detector.should_escalate_to_stage2(
    phase_id=phase_id,
    attempt_number=attempt_number,
    previous_errors=previous_errors,
    stage1_retrieval_count=stage1_count
):
    # Trigger deep retrieval
    deep_context = self.deep_retrieval_engine.retrieve_deep_context(
        query=error_query,
        categories=["implementation", "tests", "config", "docs"],
        max_snippets_per_category=3,
        max_lines_per_snippet=120
    )
```

### RetrievalTriggerDetector

```python
def should_escalate_to_stage2(
    self,
    phase_id: str,
    attempt_number: int,
    previous_errors: List[str],
    stage1_retrieval_count: int
) -> bool:
    # Escalate after 3 consecutive failures
    if attempt_number >= 3:
        return True

    # Escalate on complex multi-file error patterns
    if self._detect_complex_pattern(previous_errors):
        return True

    return False
```

---

## Completion Checklist

- ✅ Test suite created (`tests/test_build112_phase3_deep_retrieval_validation.py`)
- ✅ All 7 validation tests passing
- ✅ Snippet caps verified (≤3 per category, ≤120 lines each)
- ✅ Token budget verified (≤12 total snippets)
- ✅ Citation format verified (file path + line range)
- ✅ DiagnosticsAgent integration verified
- ✅ False positive prevention verified
- ✅ Documentation complete (`BUILD-112_PHASE3_VALIDATION.md`)

---

## Next Steps

**Phase 3 Complete** → Proceed to **Phase 4: Second Opinion Production Testing**

Phase 4 will validate the second opinion triage system with:
- `--enable-second-opinion` flag testing
- `second_opinion.json` output validation
- Hypotheses, evidence, probes, strategy verification
- Token usage compliance (≤20,000 tokens)

---

## References

- **Implementation**: `src/autopack/diagnostics/retrieval_triggers.py`
- **Deep Retrieval**: `src/autopack/diagnostics/deep_retrieval.py`
- **Integration**: `src/autopack/diagnostics/diagnostics_agent.py`
- **Test Suite**: `tests/test_build112_phase3_deep_retrieval_validation.py`
- **BUILD-112 Spec**: `docs/BUILD-112_DIAGNOSTICS_PARITY.md`
