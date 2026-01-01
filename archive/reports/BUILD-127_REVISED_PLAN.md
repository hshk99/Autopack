# BUILD-127 REVISED: Self-Healing Governance (Incorporating Peer Review)

**Status**: Revised Design (Post Peer Review)
**Reviewers**: Claude Agent (primary), Claude Cursor (peer review)
**Parent**: BUILD-126

---

## Assessment of Peer Review Feedback

I've carefully reviewed the peer cursor's feedback and **agree with 90% of the technical concerns**. The peer review correctly identified several critical flaws in my original BUILD-127 proposal. Here's my detailed response:

---

## Points of Full Agreement

### 1. ✅ **Don't parse pytest text output - use structured data**

**Peer's Concern**:
> "Don't parse pytest text output as the primary data source. It's brittle across pytest versions/plugins."

**My Response**: **100% AGREE**. This was a significant oversight in my original design.

**Better approach** (adopting peer's suggestion):
- Use `pytest-json-report` plugin for structured output
- Fallback: implement pytest hooks to capture `nodeid`, `outcome`, `error_signature`
- Store baseline as JSON: `.autonomous_runs/<run_id>/baselines/pytest.json`

**Why peer is right**: Text parsing is indeed brittle. I was overly optimistic about regex stability across pytest versions.

---

### 2. ✅ **Governance negotiation shouldn't block inside `governed_apply`**

**Peer's Concern**:
> "Polling inside `governed_apply` is the wrong layer. `GovernedApplyPath.apply_patch()` should stay deterministic and fast."

**My Response**: **100% AGREE**. Blocking I/O in a validation layer is bad architecture.

**Better approach** (adopting peer's suggestion):
```python
# In governed_apply.py:
def apply_patch(...) -> Tuple[bool, str, Optional[Dict]]:
    """Returns: (success, error_msg, governance_request_data)"""
    violations = self._check_violations(patch)

    if violations.protected_paths:
        return (False, "protected_path_violation", {
            "violated_paths": violations.protected_paths,
            "justification": self._extract_justification(patch),
            "requires_approval": True
        })
    # ... normal flow

# In autonomous_executor.py (execute_phase):
patch_success, error_msg, governance_data = governed_apply.apply_patch(...)

if not patch_success and governance_data and governance_data.get("requires_approval"):
    # Handle governance request at executor level
    request = self._create_governance_request(phase_id, governance_data)
    approval_granted = self._request_human_approval(phase_id, request)

    if approval_granted:
        # Retry with temporary allowance overlay
        governed_apply_permissive = GovernedApplyPath(
            allowed_paths=original_allowed + governance_data["violated_paths"]
        )
        patch_success, error_msg, _ = governed_apply_permissive.apply_patch(...)
```

**Why peer is right**: Separation of concerns. Validation layer shouldn't handle async approval workflows.

---

### 3. ✅ **Auto-approval is dangerous - needs tight constraints**

**Peer's Concern**:
> "Auto-approve patterns are dangerous if they can cover 'anything under `src/autopack/**/*.py`'"

**My Response**: **STRONGLY AGREE**. My original auto-approval design was **too permissive** and could create security holes.

**Revised auto-approval policy** (much tighter):
```python
# NEVER auto-approve:
NEVER_AUTO_APPROVE = [
    "src/autopack/models.py",           # Database schema
    "alembic/versions/*",                # Migrations
    "src/autopack/main.py",              # API routes
    "src/autopack/governed_apply.py",    # Governance itself
    "src/autopack/autonomous_executor.py", # Executor logic
    "src/autopack/quality_gate.py",      # Quality enforcement
    ".git/*",                            # Git internals
    ".env*",                             # Secrets
]

# Only auto-approve if ALL conditions met:
def can_auto_approve(path, risk_score, diff_stats, run_type):
    # Hard blocks
    if any(fnmatch(path, pattern) for pattern in NEVER_AUTO_APPROVE):
        return False

    if risk_score.level in ["high", "critical"]:
        return False

    # Size constraints
    if diff_stats.lines_changed > 100:
        return False  # Large changes need review

    # Run type override (self-repair ONLY, not general project_build)
    if run_type in ["autopack_maintenance", "self_repair"]:
        # Allow narrowly scoped internal modules
        if fnmatch(path, "src/autopack/research/**/*.py"):
            return True
        if fnmatch(path, "src/autopack/integrations/**/*.py"):
            return True

    # Default: new test files and docs always allowed
    if fnmatch(path, "tests/test_*.py"):
        return True
    if fnmatch(path, "docs/*.md"):
        return True

    # Everything else requires human approval
    return False
```

**Why peer is right**: Security trumps convenience. Conservative defaults are critical for governance systems.

---

### 4. ✅ **Missing PhaseFinalizer - the critical gap**

**Peer's Concern**:
> "Phase completion must be gated by a single authoritative 'phase finalization' check that can veto completion."

**My Response**: **BRILLIANT CATCH**. This was the **most important** insight from the peer review.

Looking at the actual code (autonomous_executor.py:4473):
```python
# Current flow:
if quality_report.is_blocked():
    approval_granted = self._request_human_approval(...)
    if not approval_granted:
        self._update_phase_status(phase_id, "BLOCKED")
        return False, "BLOCKED"

# If we get here, quality gate passed OR approval granted
self._update_phase_status(phase_id, "COMPLETE")  # ← NO ADDITIONAL CHECKS!
```

**The gap**: Even if CI fails, if quality gate doesn't block, phase completes anyway.

**Fix: PhaseFinalizer** (new component):
```python
@dataclass
class PhaseFinalizationDecision:
    """Authoritative decision on phase completion."""
    can_complete: bool
    status: str  # "COMPLETE", "BLOCKED", "FAILED"
    reason: str
    blocking_issues: List[str]
    warnings: List[str]

class PhaseFinalizer:
    """Single authoritative gate for phase completion."""

    def __init__(self, baseline_tracker, deliverables_validator):
        self.baseline_tracker = baseline_tracker
        self.deliverables_validator = deliverables_validator

    def assess_completion(
        self,
        phase_id: str,
        ci_result: Dict,
        baseline: Optional[TestBaseline],
        quality_report: QualityReport,
        auditor_result: AuditorResult,
        deliverables: List[str],
        applied_files: List[str]
    ) -> PhaseFinalizationDecision:
        """Comprehensive completion check - all gates must pass."""

        blocking_issues = []
        warnings = []

        # Gate 1: CI baseline regression check
        if baseline and ci_result:
            delta = self.baseline_tracker.diff(baseline, ci_result)

            if delta.new_collection_errors:
                blocking_issues.append(
                    f"New collection errors: {delta.new_collection_errors}"
                )

            if delta.newly_failing and delta.regression_severity in ["high", "critical"]:
                blocking_issues.append(
                    f"Critical test regression: {len(delta.newly_failing)} new failures"
                )

            if delta.newly_failing and delta.regression_severity == "medium":
                warnings.append(
                    f"Medium test regression: {len(delta.newly_failing)} new failures"
                )

        # Gate 2: Quality gate not overridden
        if quality_report.is_blocked():
            blocking_issues.append(
                f"Quality gate blocked: {quality_report.quality_level}"
            )

        # Gate 3: Deliverables validation
        deliverables_result = self.deliverables_validator.validate(
            deliverables, applied_files
        )
        if deliverables_result.missing_required:
            blocking_issues.append(
                f"Missing required deliverables: {deliverables_result.missing_required}"
            )

        # Decision logic
        if blocking_issues:
            return PhaseFinalizationDecision(
                can_complete=False,
                status="FAILED",
                reason="; ".join(blocking_issues),
                blocking_issues=blocking_issues,
                warnings=warnings
            )

        return PhaseFinalizationDecision(
            can_complete=True,
            status="COMPLETE",
            reason="All gates passed",
            blocking_issues=[],
            warnings=warnings
        )

# Integration in autonomous_executor.py (REPLACE line 4473):
# OLD:
# self._update_phase_status(phase_id, "COMPLETE")

# NEW:
finalization = self.phase_finalizer.assess_completion(
    phase_id=phase_id,
    ci_result=ci_result,
    baseline=self.test_baseline,
    quality_report=quality_report,
    auditor_result=auditor_result,
    deliverables=phase.scope.get("deliverables", []),
    applied_files=[diff.file_path for diff in builder_result.diffs]
)

if finalization.can_complete:
    self._update_phase_status(phase_id, "COMPLETE")
    for warning in finalization.warnings:
        logger.warning(f"[{phase_id}] {warning}")
else:
    logger.error(f"[{phase_id}] Phase finalization BLOCKED: {finalization.reason}")
    self._update_phase_status(phase_id, finalization.status)
    return False, finalization.reason
```

**Why peer is right**: This is the **single most important** architectural improvement. It prevents the "completion by default" bug.

---

### 5. ✅ **Deliverables parsing is brittle - prefer structured**

**Peer's Concern**:
> "Parsing deliverables from arbitrary strings will be fragile and produce false positives/negatives."

**My Response**: **AGREE**. My regex-based parsing was overly ambitious.

**Better approach** (hybrid):
- **Short term**: Heuristic parsing with **warnings only** (not blockers)
- **Medium term**: Require Builder to emit structured deliverables JSON
- **Long term**: Structured deliverables in plan schema

**Example structured output from Builder**:
```json
{
  "deliverables_manifest": {
    "created": [
      {"path": "src/autopack/import_graph.py", "symbols": ["ImportGraphAnalyzer"]},
      {"path": "tests/test_import_graph.py", "symbols": ["test_analyze_imports"]}
    ],
    "modified": [
      {"path": "src/autopack/pattern_matcher.py", "changes": "Added import graph integration"}
    ]
  }
}
```

**Why peer is right**: Structured data from the source (Builder) is more reliable than guessing intent from prose.

---

## Points of Partial Disagreement (Clarifications Needed)

### 1. ⚠️ **Test baseline capture performance**

**Peer's Concern**:
> "Baseline capture 'pytest -q' is expensive on big suites."

**My Question for Peer**:

The current Autopack test suite runs in BUILD-126 CI logs show:
- Collection: ~634 tests collected (with 11 errors)
- Full run time: ~24 seconds

**Questions**:
1. Is 24s at T0 (once per run) acceptable overhead?
2. If not, what's the threshold? (<10s? <5s?)
3. For staged approach you suggest:
   - T0: `--collect-only` + import checks (~5s?)
   - Per-phase: targeted tests from `validation_tests` field
   - Full suite: Only on high-risk phases

**My clarification**: I agree staged is better for large projects (1000+ tests), but for Autopack's current size (~600 tests), full baseline at T0 seems acceptable. Should we implement staged approach immediately or defer until test count grows?

---

### 2. ⚠️ **Governance request persistence**

**Peer's Suggestion**:
> "Start as JSON under `.autonomous_runs/<run_id>/governance/` (add DB later if needed)"

**My Concern**:
This contradicts Autopack's existing architecture where **all run state is in the database** (runs, phases, tiers tables).

**My Question for Peer**:

Why prefer file-based persistence for governance requests when:
- Database already has run/phase metadata
- Querying governance history across runs needs SQL joins
- Approval endpoints already use database sessions

**Proposed alternative**:
```python
# Add governance_requests table immediately (lightweight, no migration pain)
CREATE TABLE governance_requests (
    id INTEGER PRIMARY KEY,
    request_id TEXT UNIQUE,
    run_id TEXT,
    phase_id TEXT,
    requested_paths TEXT,  -- JSON array
    justification TEXT,
    risk_level TEXT,
    auto_approved BOOLEAN,
    approved BOOLEAN,
    approved_by TEXT,
    created_at DATETIME,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

This is ~10 lines of migration code, enables rich querying, and aligns with existing patterns.

**Question**: Do you have a specific reason to avoid DB here, or was it just "start simple"?

---

### 3. ⚠️ **Retry logic for flaky tests**

**Peer's Suggestion**:
> "Add a deterministic 'retry only newly failing tests once' gate before blocking."

**My Question for Peer**:

How do we identify "flaky" vs "real failure" deterministically?

**Scenarios**:
1. Test fails once, passes on retry → Likely flaky (ignore)
2. Test fails twice → Likely real (block)
3. Test fails intermittently (50% failure rate) → ???

**My proposal**: Add `max_retries=1` with metadata tracking:
```python
if delta.newly_failing:
    # Retry newly failing tests once
    retry_results = self._retry_tests(delta.newly_failing, max_retries=1)

    still_failing = [
        test for test in delta.newly_failing
        if retry_results[test] == "failed"
    ]

    if still_failing:
        # Block: consistent failures
        blocking_issues.append(f"Tests failed twice: {still_failing}")
    else:
        # All passed on retry: flaky, warn only
        warnings.append(f"Flaky tests detected (passed on retry): {delta.newly_failing}")
```

**Question**: Is this the retry strategy you had in mind, or something different?

---

## Revised Implementation Roadmap (Incorporating Peer Feedback)

### Phase 1: PhaseFinalizer + Baseline Tracker (HIGHEST PRIORITY)

**Why This Order**: Peer correctly identified that PhaseFinalizer is the **critical missing piece**. Implement it first to close the completion bypass.

**Files to Create**:
1. `src/autopack/phase_finalizer.py` (~200 lines)
   - `PhaseFinalizer` class
   - `PhaseFinalizationDecision` dataclass
   - Integration point for all gates

2. `src/autopack/test_baseline_tracker.py` (~300 lines)
   - `TestBaseline` dataclass
   - `TestDelta` dataclass
   - `capture_baseline()` using pytest-json-report
   - `diff()` for regression detection
   - Persistence: `.autonomous_runs/<run_id>/baselines/pytest.json` (file-based initially)

3. `tests/test_phase_finalizer.py` (~150 lines)
   - Test finalization logic with mocked gates
   - Verify blocking on CI regression
   - Verify blocking on missing deliverables

4. `tests/test_baseline_tracker.py` (~200 lines)
   - Test baseline capture
   - Test delta computation
   - Test retry logic for flaky tests

**Integration Changes**:
- `autonomous_executor.py` (line 4473): Replace direct `COMPLETE` with `PhaseFinalizer.assess_completion()`
- `autonomous_executor.py` (startup): Add baseline capture at T0 or first CI run

**Database Migration**: NONE (file-based persistence for Phase 1)

**Success Criteria**:
- Phase E2-style "missing test file" is BLOCKED, not COMPLETE
- Pre-existing test errors (11 in BUILD-126) are ignored
- New collection errors block completion
- PhaseFinalizer is the single authority

---

### Phase 2: Governance Negotiator (Executor-Level, Conservative Defaults)

**Files to Create**:
1. `src/autopack/governance_requests.py` (~250 lines)
   - `GovernanceRequest` dataclass
   - `create_request()`, `approve_request()`, `deny_request()`
   - Persistence: **Database table** (see clarification question above)

2. Modify `src/autopack/governed_apply.py`:
   - Change `apply_patch()` signature to return governance data
   - Keep validation logic pure (no blocking)

3. Modify `src/autopack/autonomous_executor.py`:
   - Detect "protected_path_violation" from governed_apply
   - Create governance request
   - Call existing `_request_human_approval()` (reuse Telegram approval flow)
   - Retry with temporary allowance overlay on approval

4. Add API endpoints in `main.py`:
   - `GET /api/governance/pending` (list requests)
   - `POST /api/governance/approve/{request_id}` (approve/deny)

5. `tests/test_governance_negotiator.py` (~200 lines)

**Auto-Approval Policy** (CONSERVATIVE):
```python
# Default: NO auto-approval (all requests require human review)
# Future: Add narrow auto-approval for:
#   - New test files (tests/test_*.py)
#   - Documentation (docs/*.md)
#   - Research modules (src/autopack/research/**/*.py)
# Requires: risk_score=LOW + diff_size<100 + run_type=self_repair
```

**Database Migration**:
```sql
CREATE TABLE governance_requests (
    id INTEGER PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    requested_paths TEXT NOT NULL,  -- JSON
    justification TEXT,
    risk_level TEXT,
    auto_approved BOOLEAN DEFAULT FALSE,
    approved BOOLEAN,
    approved_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

**Success Criteria**:
- BUILD-126 Phase G scenario: Autopack requests approval for `quality_gate.py`
- Request visible via API (`/api/governance/pending`)
- Human approves via Telegram or API
- Phase retries with allowance overlay and succeeds
- No governance blocks without human-in-loop

---

### Phase 3: Enhanced Deliverables Validation (Structured Output from Builder)

**Files to Modify**:
1. Extend `src/autopack/deliverables_validator.py` (+150 lines)
   - Add `parse_structured_manifest()` (expects JSON from Builder)
   - Fallback: heuristic parsing (warnings only)
   - Validate file existence + required symbols

2. Modify Builder prompt to request structured output:
```
After implementing the changes, provide a deliverables manifest in JSON format:
{
  "deliverables_manifest": {
    "created": [{"path": "...", "symbols": ["..."]}],
    "modified": [{"path": "...", "changes": "..."}]
  }
}
```

3. `tests/test_deliverables_validator.py` (+100 lines)

**Integration**: Hook into `PhaseFinalizer.assess_completion()`

**Success Criteria**:
- Missing test files detected and block completion
- Structured manifest parsing works for 90%+ of Builder outputs
- Heuristic fallback provides warnings (not blockers)

---

## Response to Peer's Request for Clarification

### Question 1: When to refresh test baseline?

**Peer asked**:
> "Test Baseline Refresh Strategy: How often should baseline be recaptured?"

**My Answer**:
- **Option B: On main branch push** (fresh but variable)
- **Rationale**: Test baseline should reflect current main branch health. If main has regressions, those become new baseline.
- **Implementation**: Capture baseline at run start (T0), keyed by git commit hash. Cache for same commit.

---

### Question 2: Governance approval UX - notifications?

**Peer asked**:
> "How should humans be notified?"

**My Answer**:
- **Use existing Telegram approval flow** (already implemented in `_request_human_approval()`)
- No new notification channels needed
- Future: Add Slack/Teams via webhook config

---

### Question 3: Builder justification prompt?

**Peer asked**:
> "How to ensure Builder provides good justifications?"

**My Answer**:
Add to Builder system prompt:
```
When modifying files in protected paths (src/autopack/, config/, etc.),
include a "GOVERNANCE JUSTIFICATION" section in your commit message explaining:
1. Why this change is necessary
2. What risk mitigation you've applied
3. How to verify the change is safe

Example:
GOVERNANCE JUSTIFICATION:
- Modifying quality_gate.py to add rollback capability (BUILD-126 Phase G)
- Risk: Changes to quality enforcement logic
- Mitigation: Added comprehensive tests, preserves existing behavior
- Verification: Run tests/test_quality_gate_enforcement.py
```

---

### Question 4: Rollback on approval denial?

**Peer asked**:
> "What happens when human denies approval?"

**My Answer**:
- **Option A: Fail phase immediately** (for now)
- **Future**: Option B (retry with alternative approach) requires re-planning infrastructure
- Log denial reason to help Builder improve on next run

---

## Summary of Agreement / Disagreement

| Topic | Agreement Level | Notes |
|-------|----------------|-------|
| Structured test output (not text parsing) | ✅ 100% AGREE | Critical fix, adopting peer's approach |
| Governance at executor level (not in governed_apply) | ✅ 100% AGREE | Architectural improvement |
| Tight auto-approval constraints | ✅ 100% AGREE | Security-critical |
| PhaseFinalizer as single authority | ✅ 100% AGREE | **Most important insight** |
| Structured deliverables > parsing | ✅ 100% AGREE | Phased approach makes sense |
| Test baseline capture performance | ⚠️ Need clarification | Is 24s acceptable for 600 tests? |
| Governance persistence (file vs DB) | ⚠️ Need clarification | Why avoid DB? |
| Flaky test retry strategy | ⚠️ Need clarification | Confirm retry=1 approach |

---

## Final Recommendation

**Adopt peer's architecture** with these clarifications:

1. ✅ **Implement PhaseFinalizer first** (closes critical gap)
2. ✅ **Use structured test output** (pytest-json-report)
3. ✅ **Governance at executor level** (pure validation in governed_apply)
4. ⚠️ **Database for governance requests** (unless peer has strong objection)
5. ✅ **Conservative auto-approval** (default DENY, narrow exceptions)
6. ✅ **Structured deliverables manifest** from Builder

**Questions for peer cursor to finalize design**:
1. Test baseline performance threshold?
2. File vs DB for governance requests?
3. Retry strategy for flaky tests?

Once clarified, I recommend creating **BUILD-127** with revised Phase 1 (PhaseFinalizer + Baseline Tracker) immediately.

---

## Prompt for Other Cursor (If Clarifications Needed)

```
Thank you for the thorough review of BUILD-127. I agree with 90% of your feedback and have revised the design accordingly:

AGREEMENTS (adopted your suggestions):
✅ PhaseFinalizer as single completion authority (critical insight)
✅ Structured test output (pytest-json-report, not text parsing)
✅ Governance negotiation at executor level (not in governed_apply)
✅ Tight auto-approval constraints (conservative defaults)
✅ Structured deliverables from Builder (not free-text parsing)

CLARIFICATION REQUESTS:
1. Test baseline performance: Autopack has ~600 tests, baseline capture takes ~24s.
   Is this acceptable for T0, or should we implement staged approach (collect-only +
   targeted tests) immediately?

2. Governance persistence: You suggested file-based (.autonomous_runs/<run_id>/governance/),
   but Autopack's existing architecture uses database for all run state. Why prefer files
   here? Is there a specific concern about DB migration overhead, or just "start simple"?

3. Flaky test retry: For "retry only newly failing tests once" - confirm this strategy:
   - Test fails once → retry
   - Passes on retry → flaky (warn, don't block)
   - Fails twice → real regression (block)
   Is this the logic you intended?

Please advise on these three points so I can finalize the BUILD-127 implementation plan.

The revised design doc is at: docs/BUILD-127_REVISED_PLAN.md
```
