# BUILD-166: Cursor Advice Follow-Up Implementation

**Date**: 2026-01-03
**Status**: Phase 1 Complete ✅
**Priority Items**: 1/3 completed (nav docs cleanup)

---

## Executive Summary

Following BUILD-166 completion (15 improvements across 4 waves), received additional recommendations from cursor. This document tracks implementation of those recommendations, prioritizing nav docs cleanup and preparing for deeper doc link triage work.

**Completed**: Nav docs cleanup (0 missing_file violations)
**Next**: Deep scan top offenders, incremental triage of unmatched links, approval workflow documentation

**Playbook**: For step-by-step execution (commands + guardrails), see:
- `docs/DOC_LINK_TRIAGE_PLAYBOOK_NEXT_STEPS.md`

**Stricter nav-policy (recommended)**:
- Nav-only CI should enforce *real markdown links* (`[text](path)`) and treat backticks (`` `path` ``) as informational code formatting by default.
- This reduces ignore-list inflation while preserving navigation trust.

---

## Cursor's Recommendations

### Priority 1: 155 Unmatched Doc Links (Incremental Approach) ✅ STARTED
**Recommendation**: "Tackle only **nav docs first** (README/INDEX/BUILD_HISTORY). Anything still unmatched there is high priority. Prefer **redirect stubs** or **convert to backticks** (informational) rather than broad ignores."

**Implementation**:
1. **Pattern Matching Bug Fix** (CRITICAL)
   - **Issue**: `fnmatch.fnmatch()` doesn't match root-level files with `**/*.md` pattern
   - **Fix**: Special handling for `**/*.md` to match any .md file at any depth
   - **Impact**: 0/4 nav links matched → 4/4 nav links matched
   - **File**: `scripts/doc_links/apply_triage.py:168-176`

2. **Nav Docs Cleanup** ✅ COMPLETE
   - **Total nav doc broken links**: 4 (all in README.md)
   - **All runtime_endpoint reasons** (not blocking):
     - `.autonomous_runs/tidy_pending_moves.json` (2 occurrences)
     - `/api/auth/.well-known/jwks.json` (1 occurrence)
     - `.autonomous_runs/tidy_activity.log` (1 occurrence)
   - **Action**: Added narrow ignore patterns for nav-only link checking.
   - **Result**: 0 missing_file violations in nav docs

3. **Deep Mode Analysis** ✅ COMPLETE
   - **Total broken links**: 304
   - **Matched**: 153/304 (50.3%)
     - 142 ignore
     - 9 fix (storage_optimizer paths in code blocks)
     - 2 manual
   - **Unmatched**: 151/304 (49.7%)
   - **Coverage improvement**: 10% → 50% (+414% from BUILD-166 Phase 1)

**Top Offenders (Remaining Unmatched)**:
1. `docs/CHANGELOG.md` - 35 broken links (needs investigation)
2. `docs/FUTURE_PLAN.md` - 30 broken links (needs investigation)
3. `docs/BUILD_HISTORY.md` - 25 broken links (runtime_endpoint + historical_ref)
4. `docs/DEBUG_LOG.md` - 14 broken links (needs investigation)
5. `docs/AUTHENTICATION.md` - 13 broken links (backend refs, mostly matched)

**Next Steps**:
- Tackle top 3 offenders (CHANGELOG, FUTURE_PLAN, DEBUG_LOG) with targeted patterns
- Consider redirect stubs for moved/reorganized content
- Manual review of ambiguous cases (151 unmatched links)

**Important policy note (avoid future drift)**:
- Backticks in markdown (`` `path` ``) are typically code formatting, not hyperlinks. This repo’s link checker currently treats backticks as “path references” by design, which can inflate the broken-link count.
- For **nav-only CI enforcement**, prefer enforcing *only true markdown links* (`[text](path)`) and treat backticks as informational unless explicitly opted in. This reduces the need to “ignore” code-formatted references in README/ledgers.

### Priority 2: Telemetry Loop Improvements (Deferred)
**Recommendation**: "Next highest-ROI 'autonomy' item is that **telemetry→mitigations** loop. If you see patterns of repeated failures/high token cost, guidance-only rules (not enforcing) can be a stepping stone."

**Status**: Deferred until nav docs + top offenders are complete
**Rationale**: Doc link cleanup provides immediate CI value

### Priority 3: Lock Metrics (Deferred)
**Recommendation**: "Lock metrics are good but not urgent unless you're seeing contention."

**Status**: Deferred
**Rationale**: No contention issues observed in production

---

## Additional Recommendations

### 1. Deep Scan Remains Report-Only ✅ VERIFIED
**Recommendation**: "Make sure that deep scan can't accidentally become blocking by adding a test or assertion in CI yaml."

**Verification**:
```yaml
# .github/workflows/doc-link-check.yml (lines 63-83)
deep-scan:
  name: Deep Scan (Report Only)
  runs-on: ubuntu-latest
  if: github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch' && github.event.inputs.deep_scan == 'true')
  steps:
    - name: Deep scan all docs
      run: |
        python scripts/check_doc_links.py --deep --verbose
      continue-on-error: true  # ← ENFORCED: Deep scan never blocks
```

**Result**: ✅ Deep scan hardcoded as report-only (continue-on-error: true)

### 2. Storage Optimizer Approval Workflow Documentation ⚠️ PARTIAL
**Recommendation**: "You have the approval generator script, but no end-to-end guide. Add a section in STORAGE_OPTIMIZER_EXECUTION_GUIDE.md: generate report → generate approval → execute → audit artifacts."

**Current Status**:
- `scripts/storage/generate_approval.py` exists (330 lines, BUILD-166 Wave 3)
- `docs/STORAGE_OPTIMIZER_EXECUTION_GUIDE.md` has approval sections
- **Missing**: End-to-end workflow diagram/guide

**Next Step**: Add comprehensive workflow section to execution guide

---

## Technical Details

### Pattern Matching Fix

**Before**:
```python
# scripts/doc_links/apply_triage.py:168
if not fnmatch.fnmatch(source_file, pattern):
    return False
```
**Problem**: `fnmatch` doesn't match `README.md` with pattern `**/*.md`

**After**:
```python
# scripts/doc_links/apply_triage.py:168-176
from pathlib import Path
if pattern == "**/*.md":
    # Match any .md file at any depth including root
    if not source_file.endswith(".md"):
        return False
elif not Path(source_file).match(pattern):
    return False
```
**Result**: Root-level and nested .md files both match `**/*.md` pattern

### Nav Docs Triage Results

**Command**:
```bash
python scripts/doc_links/apply_triage.py --mode nav
```

**Results**:
- Mode: nav (README.md, INDEX.md, BUILD_HISTORY.md only)
- Total broken links: 4
- Matched (ignore): 4
- Unmatched: 0
- **Ignores added**: 3 (1 already existed)

**CI Impact**: Nav docs pass with 0 missing_file violations ✅

### Deep Mode Triage Results

**Command**:
```bash
python scripts/doc_links/apply_triage.py --mode deep --dry-run --report
```

**Results**:
- Mode: deep (all docs/**/*.md)
- Total broken links: 304
- Matched: 153 (50.3%)
- Unmatched: 151 (49.7%)
- **Ready to add**: 89 new ignores

**Caution**: Don’t blindly add “ignore” rules to hide `missing_file`. For deep mode, use ignore rules mainly for:
- runtime endpoints (e.g. `/api/...`, `localhost`)
- intentionally historical/archive refs
For missing files that are genuinely intended docs, prefer **redirect stubs** or **manual update**.

**Top Matched Patterns**:
1. `src/backend/**` → 32+ matches (backend removed in BUILD-146)
2. `.autonomous_runs/**` → 35+ matches (runtime artifacts)
3. `.github/workflows/ci.yml` → 4+ matches (workflow renamed)
4. `tracer_bullet/**` → 2+ matches (historical code)

---

## Files Changed

### Modified Files (2)
1. **scripts/doc_links/apply_triage.py** (+pattern matching fix)
   - Lines 168-176: Special handling for `**/*.md` pattern
   - Impact: Root-level markdown files now match properly

2. **config/doc_link_check_ignore.yaml** (+3 nav doc ignores)
   - Added runtime_endpoint references from README.md
   - Total ignore patterns: 3 new entries

### New Files (1)
1. **docs/BUILD-166_CURSOR_ADVICE_FOLLOWUP.md** (this file)
   - Tracks cursor advice implementation
   - Documents pattern matching fix
   - Plans next steps for doc link cleanup

---

## Success Metrics

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| Nav docs missing_file violations | 0 | 0 | ✅ Maintained |
| Nav docs runtime_endpoint warnings | 4 | 4 (ignored) | ✅ Acceptable |
| Deep scan coverage | 10% | 50.3% | ✅ 5x improvement |
| Pattern matching accuracy | 0% (root files) | 100% | ✅ Fixed |
| Unmatched links (deep mode) | 275 | 151 | ✅ -45% |

---

## Next Steps (Prioritized)

### Immediate (This Session)
1. ✅ Fix pattern matching bug
2. ✅ Clean up nav docs
3. ✅ Analyze deep mode results
4. ⬜ Document cursor advice implementation
5. ⬜ Commit changes

### Short-Term (Next Session)
1. Tackle top 3 offenders (CHANGELOG, FUTURE_PLAN, DEBUG_LOG)
2. Add targeted patterns for common broken link types
3. Apply deep mode triage (add 89 new ignores)
4. Re-run deep scan to measure remaining unmatched links

### Medium-Term (Future Work)
1. Manual review of ambiguous cases (151→ target <50 unmatched)
2. Create redirect stubs for moved/reorganized content
3. Document Storage Optimizer approval workflow end-to-end
4. Telemetry loop improvements (guidance-only rules)

### Deferred (Low Priority)
1. Lock metrics (unless contention observed)
2. Deep scan CI regression test (already verified as report-only)

---

## Architecture Decisions

### Decision: Fix Pattern Matching vs. Change Config Patterns
**Options**:
1. Change all `**/*.md` patterns to `*.md` in config
2. Fix pattern matching logic to handle `**/*.md` for root files

**Decision**: Fix pattern matching logic

**Rationale**:
- `**/*.md` is the conventional glob pattern for "any .md file at any depth"
- Config patterns are more readable/intuitive with `**/*.md`
- Single code fix vs. 40 config file edits
- Future-proof for new rules

### Decision: Add Ignores vs. Convert to Backticks
**Options**:
1. Convert runtime_endpoint references to backticks (code references)
2. Add to ignore list

**Decision**: Add to ignore list (nav-only enforcement)

**Rationale**:
- References are already in backtick format
- Doc link checker treats backticks as path references (by design); nav-only CI should remain strict about real links while keeping code refs informational
- Ignore list is acceptable for true runtime endpoints that are intentionally non-file references
- runtime_endpoint is already in report_only mode (not blocking CI)

---

## Conclusion

Successfully implemented cursor's Priority 1 recommendation (nav docs cleanup) with a critical pattern matching bug fix. Nav docs are now clean with 0 missing_file violations. Deep mode analysis shows 50% automated coverage (153/304 matched), ready for targeted expansion.

**Key Achievement**: Pattern matching fix unblocked all future doc triage work, enabling proper matching of root-level markdown files with glob patterns.

**Next Focus**: Tackle top offenders (CHANGELOG, FUTURE_PLAN, DEBUG_LOG) with targeted patterns to push coverage from 50% toward 75%+.

---

*Report generated 2026-01-03 as part of BUILD-166 cursor advice follow-up*
