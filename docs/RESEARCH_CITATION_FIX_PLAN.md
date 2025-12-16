# Research Citation Fix - Implementation Plan v2.1

**Project**: Autopack Research Citation Validity Improvement
**Goal**: Improve citation validity by fixing numeric verification and text normalization
**Current Status**: Phase 0 COMPLETE | Phase 1 Ready to Resume
**Last Updated**: 2025-12-16

---

## Project Overview

This plan addresses citation validation issues discovered during Autopack research runs. The problem: citations were failing validation due to overly strict numeric checks and inadequate text normalization.

### Root Causes Identified
1. **Numeric verification too strict**: Checked LLM's paraphrased content instead of only `extraction_span`
2. **Text normalization gaps**: HTML entities, Unicode variations, markdown artifacts not handled
3. **Format mismatch handling**: Auto-recovery not triggering for Builder format errors (FIXED in BUILD-038)

---

## Phase 0: Foundation Modules ✅ COMPLETE

**Status**: ✅ All files implemented and tested
**Completion Date**: 2025-12-16
**Implementation Type**: Direct (not via Autopack)

### Deliverables

1. **`src/autopack/text_normalization.py`** ✅
   - HTML entity decoding (`decode_html_entities`)
   - Unicode normalization (`normalize_unicode`)
   - Markdown artifact stripping (`strip_markdown_artifacts`)
   - Whitespace normalization (`normalize_whitespace`)
   - Main pipeline: `normalize_text()`
   - Tests: 27/27 passing in `tests/test_text_normalization.py`

2. **`src/autopack/verification.py`** ✅
   - Number extraction with tolerance (`extract_numbers`)
   - Numeric value verification (`verify_numeric_values`)
   - Citation text matching (`verify_citation_in_source`)
   - Combined verification (`verify_extraction`)
   - Tests: 27/27 passing in `tests/test_verification.py`

3. **`scripts/run_phase0_evaluation.py`** ✅
   - Evaluation script for measuring citation validity
   - Test discovery and execution
   - Metrics collection and reporting
   - JSON output for automation

### Test Results
```
tests/test_text_normalization.py: 27 passed ✅
tests/test_verification.py: 27 passed ✅
Total: 54/54 tests passing
```

---

## Phase 1: Relax Numeric Verification 🔄 READY TO RESUME

**Phase ID**: `phase_1_relax_numeric_verification`
**Status**: 🔄 QUEUED (ready to start with Autopack)
**Category**: feature
**Complexity**: medium
**Previous Attempts**: Multiple (encountered BUILD-037/BUILD-038 issues, now fixed)

### Objective
Modify citation verification logic to ONLY check numeric values in `extraction_span`, NOT in the LLM's paraphrased `extracted_content`.

### Implementation Strategy

**Files to Modify**:
1. Primary target: Find where citation verification happens (likely in research/evaluation code)
2. Update verification calls to use `verify_numeric_values(extraction_span, source_document)`
3. Remove or skip numeric checks on `extracted_content` (paraphrased text)

**Acceptance Criteria**:
- [ ] Numeric verification only checks `extraction_span`
- [ ] `extracted_content` (LLM paraphrase) excluded from numeric checks
- [ ] Text verification still applies to both fields
- [ ] Tests pass (pytest)
- [ ] Auditor approval (quality gate)

**Dependencies**:
- ✅ Phase 0 complete (text_normalization.py, verification.py available)
- ✅ BUILD-037 (truncation auto-recovery) implemented
- ✅ BUILD-038 (format mismatch auto-recovery) implemented and validated

**Next Steps**:
1. Reset phase_1 status to QUEUED in database
2. Start Autopack executor with `--run-id research-citation-fix --run-type autopack_maintenance`
3. Monitor for auto-recovery triggers (should handle format mismatches gracefully now)
4. Verify phase completes successfully with quality gate approval

---

## Phase 2: Evaluation After Phase 1

**Phase ID**: `phase_2_run_evaluation_after_phase1`
**Status**: ⏸️ QUEUED (blocked by Phase 1)
**Category**: test
**Complexity**: low

### Objective
Run Phase 0 evaluation script to measure citation validity improvement after Phase 1 fix.

### Implementation
```bash
PYTHONUTF8=1 PYTHONPATH=src python scripts/run_phase0_evaluation.py
```

**Success Metrics**:
- Baseline citation validity: [TBD from pre-Phase 1 run]
- Target improvement: +10-20% validity rate
- Zero regressions in passing citations

**Acceptance Criteria**:
- [ ] Evaluation script runs successfully
- [ ] Results show improved citation validity
- [ ] JSON report generated
- [ ] Results documented in phase summary

---

## Phase 3: Enhanced Normalization

**Phase ID**: `phase_3_enhanced_normalization`
**Status**: ⏸️ QUEUED (blocked by Phase 1-2)
**Category**: feature
**Complexity**: medium

### Objective
Integrate `text_normalization.normalize_text()` into citation verification pipeline to handle HTML entities, Unicode variations, and markdown artifacts.

### Implementation Strategy

**Integration Points**:
1. Update verification logic to call `normalize_text()` before comparisons
2. Ensure both `extraction_span` and `source_document` normalized before matching
3. Add tests for edge cases:
   - HTML entities: `&apos;`, `&quot;`, `&nbsp;`
   - Unicode: combining characters, different normalizations
   - Markdown: `**bold**`, `[links](url)`, `# headers`

**Acceptance Criteria**:
- [ ] `normalize_text()` integrated into verification pipeline
- [ ] HTML entity mismatches resolved
- [ ] Unicode variation mismatches resolved
- [ ] Markdown artifact mismatches resolved
- [ ] Tests pass with normalization enabled
- [ ] Auditor approval

---

## Phase 4-6: Evaluation and Iteration

**Phases**:
- **Phase 4**: `phase_4_run_evaluation_after_phase3`
- **Phase 5**: `phase_5_improve_extraction_prompt` (if needed based on Phase 4 results)
- **Phase 6**: `phase_6_final_evaluation`

**Status**: ⏸️ Planned (execution depends on Phase 1-3 results)

---

## Build History Integration

### BUILD-037: Builder Truncation Auto-Recovery ✅
**Status**: Implemented (2025-12-16T02:25)
**Impact**: Phase 1 execution
**Fix**: Added truncation metadata propagation in Builder parsers

### BUILD-038: Builder Format Mismatch Auto-Fallback ✅
**Status**: Implemented and Validated (2025-12-16T15:22)
**Impact**: Phase 1 execution
**Fix**: Extended fallback detection to format mismatches, not just truncation
**Validation**: Confirmed auto-recovery triggers correctly on format mismatch

These build fixes ensure Phase 1 can navigate Builder errors autonomously.

---

## Execution Instructions

### Resume Phase 1 with Autopack

1. **Ensure database is ready**:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" python -c "
from autopack.database import get_session
from autopack.models import Phase
session = get_session()
phase = session.query(Phase).filter_by(phase_id='phase_1_relax_numeric_verification').first()
if phase:
    phase.status = 'QUEUED'
    session.commit()
    print(f'✅ Reset {phase.phase_id} to QUEUED')
"
```

2. **Start Autopack executor**:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python -m autopack.autonomous_executor --run-id research-citation-fix --api-url http://localhost:8000 --poll-interval 10 --run-type autopack_maintenance > autopack_phase1.log 2>&1 &
```

3. **Monitor progress**:
```bash
tail -f autopack_phase1.log | grep -E "(phase_1|Falling back|SUCCESS|FAILED|Quality Gate)"
```

4. **Check for auto-recovery** (should see these if Builder has issues):
   - `WARNING: Falling back to structured_edit after full-file parse/truncation failure`
   - `INFO: Builder succeeded` (after fallback)

---

## Success Criteria (Overall Project)

### Phase 0 ✅
- [x] text_normalization.py implemented and tested
- [x] verification.py implemented and tested
- [x] run_phase0_evaluation.py created
- [x] All 54 tests passing

### Phase 1 (In Progress)
- [ ] Numeric verification relaxed to extraction_span only
- [ ] Tests pass
- [ ] Auditor approves
- [ ] Phase completes with quality gate: APPROVED or NEEDS_REVIEW

### Phase 2-3 (Pending)
- [ ] Evaluation shows improvement
- [ ] Normalization integrated
- [ ] Citation validity improved by 10-20%

### Phase 4-6 (Future)
- [ ] Final evaluation complete
- [ ] Extraction prompt improvements (if needed)
- [ ] Project goals achieved

---

## Risk Mitigation

### Known Issues (Resolved)
- ✅ BUILD-037: Truncation auto-recovery (fixed)
- ✅ BUILD-038: Format mismatch auto-recovery (fixed and validated)
- ✅ Isolation system blocking autopack/ paths (use `--run-type autopack_maintenance`)
- ✅ AttributeError `_rules_marker_path` (fixed - moved to __init__)

### Current Risks
- **Low**: Phase 1 implementation complexity (medium difficulty)
- **Low**: Builder format changes (auto-recovery now handles this)
- **Medium**: Finding correct verification integration points (may require exploration)

### Mitigation Strategies
- Use Autopack's auto-recovery (validated working)
- Monitor logs for fallback triggers
- Quality gate will catch issues before apply
- Can iterate on failed attempts with learned rules

---

## Notes

- **Plan Version**: 2.1 (referenced in user conversation)
- **Execution Mode**: Autopack autonomous with human approval gates
- **Testing**: pytest with targeted test suites
- **Documentation**: Updated in BUILD_HISTORY.md and this plan
- **Learned Rules**: Autopack learning pipeline active (48 total rules, 304 hints promoted)

---

**Document Status**: Ready for Phase 1 execution
**Next Action**: Resume Phase 1 using Autopack autonomous executor
**Expected Outcome**: Citation validity improved via relaxed numeric verification
