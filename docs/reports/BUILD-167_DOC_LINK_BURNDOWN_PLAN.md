# BUILD-167: Deep-Scan `missing_file` Burndown Plan

**Date**: 2026-01-03
**Status**: Phase 1 - Analysis Complete
**Goal**: Reduce deep-scan `missing_file` violations by 50-80%

---

## Executive Summary

Deep scan baseline shows **746 `missing_file` violations** across 163 docs. Nav docs (README/INDEX/BUILD_HISTORY) remain at **0 `missing_file` violations** in nav-only mode (backticks ignored).

**Key Finding**: Many violations are backtick-wrapped paths that should be informational (code references), not enforced links. Deep mode includes these for comprehensive reporting, but they should not be treated as CI-blocking.

---

## Baseline Metrics (2026-01-03)

| Metric | Count |
|--------|-------|
| Total broken links (deep scan) | 1,099 |
| **missing_file violations** | **746** |
| runtime_endpoint (report-only) | 249 |
| historical_ref (report-only) | 104 |
| Auto-fixable (high confidence) | 18 |
| Auto-fixable (medium confidence) | 12 |
| Manual review required | 716 |

---

## Top 10 Offenders by `missing_file` Count

| Rank | File | Count | Category |
|------|------|-------|----------|
| 1 | README.md | 62 | Nav doc (informational backticks in deep mode) |
| 2 | docs/BUILD_HISTORY.md | 58 | Nav doc (code path references) |
| 3 | docs/CHANGELOG.md | 58 | Ledger (historical references) |
| 4 | docs/PRE_TIDY_GAP_ANALYSIS_2026-01-01.md | 51 | Analysis doc |
| 5 | docs/DOC_LINK_TRIAGE_REPORT.md | 34 | Report |
| 6 | docs/reports/AUTOPACK_DRAIN_SECOND_OPINION_REVIEW.md | 29 | Report |
| 7 | docs/DEBUG_LOG.md | 26 | Ledger (code references) |
| 8 | docs/TIDY_SYSTEM_REVISION_PLAN_2026-01-01.md | 19 | Plan |
| 9 | docs/BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md | 16 | Completion doc |
| 10 | docs/guides/RESEARCH_SYSTEM_CI_COLLECTION_REMEDIATION_PLAN.md | 15 | Remediation plan |

---

## Top 20 Missing Targets by Frequency

**Note**: This section contains many path-like tokens intended as analysis examples. It is wrapped in a fenced code block so the doc-link checker (deep mode) does not treat them as actionable references.

```
| Rank | Target | Count | Classification |
|------|--------|-------|----------------|
| 1 | `fileorganizer/` | 17 | Code path (historical) |
| 2 | `.log` | 14 | File extension (backtick) |
| 3 | `/health` | 14 | API endpoint (backtick) |
| 4 | `.md` | 13 | File extension (backtick) |
| 5 | `__init__.py` | 12 | Code file (backtick) |
| 6 | `.git/` | 11 | VCS directory (backtick) |
| 7 | `.json` | 11 | File extension (backtick) |
| 8 | `autonomous_executor.py` | 10 | Code file |
| 9 | `.github/workflows/ci.yml` | 10 | Renamed workflow |
| 10 | `SOT_BUNDLE.md` | 10 | Missing doc |
| 11 | `.gitignore` | 9 | Config file (backtick) |
| 12 | `tidy_up.py` | 8 | Code file |
| 13 | `research_tracer/` | 8 | Historical code |
| 14 | `.env` | 7 | Config file (backtick) |
| 15 | `logs/` | 7 | Runtime directory |
| 16 | `.txt` | 7 | File extension (backtick) |
| 17 | `drain_one_phase.py` | 7 | Code file |
| 18 | `.yaml` | 6 | File extension (backtick) |
| 19 | `CONSOLIDATED_DEBUG.md` | 6 | Missing doc |
| 20 | `backend/` | 6 | Removed code |
```

---

## Analysis & Strategy

### Key Observations

1. **Backtick Inflation**: Many violations are file extensions (`.log`, `.md`, `.json`) or code paths in backticks
   - These are **informational references** in documentation
   - Deep mode correctly reports them, but they should not be "fixed" as broken links
   - Nav mode already ignores these (working as intended)

2. **Historical Code References**: `fileorganizer/`, `research_tracer/`, `backend/`
   - Historical project components removed/renamed
   - References are intentional (historical context)
   - Should be marked as `historical_ref`, not `missing_file`

3. **Legitimate Missing Docs**: `docs/SOT_BUNDLE.md`, `archive/docs/CONSOLIDATED_DEBUG.md`
   - These may need to be created or references updated
   - Requires manual investigation

4. **Renamed Workflows**: `.github/workflows/ci.yml`
   - Workflow was renamed/restructured
   - Need redirect stub or update references

### Recommended Fixes (Priority Order)

#### Priority 1: Reclassify Backtick Code References
**Action**: Update reason classification for backtick-wrapped code paths/extensions
**Impact**: Moves ~300-400 items from `missing_file` to informational categories
**Method**: These are already correctly ignored in nav mode; no action needed in doc content

#### Priority 2: Historical Code Path Markers
**Action**: Add triage rules for historical code references
**Targets**:
**Note**: This is an analysis checklist; wrap in a fenced code block to avoid being counted as path references in deep scans.

```
- `fileorganizer/` → historical_ref
- `research_tracer/` → historical_ref
- `backend/` → historical_ref (already partially covered)
- `tracer_bullet/` → historical_ref (already covered)
```

#### Priority 3: Create Redirect Stubs for Renamed/Moved Docs
**Action**: Create minimal redirect stubs with canonical links
**Candidates**:
**Note**: Analysis checklist; wrap in a fenced code block to avoid being counted as path references in deep scans.

```
- `SOT_BUNDLE.md` → Investigate if this should point to BUILD-163 docs
- `CONSOLIDATED_DEBUG.md` → Point to DEBUG_LOG.md or archive
- Renamed workflow files → Point to current workflows
```

#### Priority 4: Update Direct References in Top Offenders
**Action**: Fix real broken markdown links in top 5 files
**Method**: Use `apply_triage.py` with `fix` action for deterministic path rewrites

#### Priority 5: Manual Review Tail
**Action**: Triage remaining ~50-100 ambiguous cases
**Method**: Mark as `manual` in triage overrides with justification

---

## Implementation Plan

### Phase 1: Baseline & Analysis ✅ COMPLETE
- [x] Run deep scan baseline
- [x] Analyze top offenders
- [x] Categorize violation types
- [x] Create burndown plan

### Phase 2: Quick Wins - Triage Rules (Next)
**Goal**: Reclassify backtick/historical refs to reduce `missing_file` count by ~40%

**Tasks**:
1. Add triage rules for file extensions in backticks (informational)
2. Add triage rules for historical code paths
3. Validate with dry-run
4. Apply and measure impact

**Expected Outcome**: missing_file: 746 → ~450

### Phase 3: Redirect Stubs for Moved Docs
**Goal**: Create redirect stubs for frequently referenced missing docs

**Tasks**:
1. Investigate `docs/SOT_BUNDLE.md` - determine canonical target
2. Investigate `archive/docs/CONSOLIDATED_DEBUG.md` - create redirect or merge
3. Add redirect stub support to `apply_triage.py` (if not present)
4. Create stubs with proper frontmatter

**Expected Outcome**: missing_file: ~450 → ~420

### Phase 4: Top Offender File Cleanup
**Goal**: Fix real broken links in top 5 source files

**Tasks**:
1. README.md - audit markdown links, convert code refs to plain backticks if needed
2. BUILD_HISTORY.md - ensure code path references are informational
3. CHANGELOG.md - similar to BUILD_HISTORY
4. PRE_TIDY_GAP_ANALYSIS - update references or archive
5. DOC_LINK_TRIAGE_REPORT - update internal references

**Expected Outcome**: missing_file: ~420 → ~300

### Phase 5: Manual Review & Final Triage
**Goal**: Triage remaining tail

**Tasks**:
1. Review remaining violations by category
2. Add targeted triage rules with justification
3. Mark truly ambiguous cases as `manual`
4. Document decisions in triage overrides

**Expected Outcome**: missing_file: ~300 → ~150-200 (manageable tail)

---

## Constraints & Guardrails

### NEVER Ignore `missing_file` Broadly
- ❌ **Bad**: `action: ignore, reason_filter: missing_file` (broad pattern)
- ✅ **Good**: Specific patterns with clear justification

### Prefer Redirect Stubs Over Ignores
- For moved/renamed docs, create redirect stub pointing to new location
- Only ignore if reference is truly historical/non-actionable

### Nav Docs Remain Strict
- README.md, INDEX.md, BUILD_HISTORY.md must have **0 `missing_file`** in nav mode
- Deep mode can report violations for comprehensive coverage (informational)

### Justify All Triage Rules
- Every new ignore pattern must have clear `note:` explaining why
- Historical references should be marked as `historical_ref`, not ignored as `missing_file`

---

## Success Criteria

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| Total `missing_file` violations | 746 | <200 | 🔴 Not started |
| Nav mode `missing_file` | 0 | 0 | ✅ Maintained |
| Triage coverage (missing_file) | 0% | 70%+ | 🔴 0% |
| Redirect stubs created | 0 | 5-10 | 🔴 0 |
| Top offender files addressed | 0/5 | 5/5 | 🔴 0/5 |

---

## Next Steps

1. ✅ **Complete**: Generate baseline report and analysis
2. **Next**: Implement Phase 2 triage rules for backtick/historical refs
3. Validate with dry-run and measure impact
4. Proceed to Phase 3 (redirect stubs) after Phase 2 success

---

## Files Referenced

- `archive/diagnostics/doc_link_fix_plan.json` - Deep scan output
- `archive/diagnostics/doc_link_fix_plan.md` - Human-readable report
- `archive/diagnostics/top_offenders_analysis.txt` - Analysis output
- `config/doc_link_triage_overrides.yaml` - Triage rules (to be extended)
- `scripts/doc_links/apply_triage.py` - Triage automation tool

---

*Report generated 2026-01-03 as part of BUILD-167 Phase 1*
