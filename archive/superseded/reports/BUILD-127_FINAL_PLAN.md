# BUILD-127 FINAL: Self-Healing Governance Implementation Plan

**Status**: Final Design (Peer Review Complete)
**Reviewers**: Claude Agent (primary) + Claude Cursor (peer)
**Parent**: BUILD-126
**Priority**: CRITICAL

---

## Peer Review Outcomes - All Questions Resolved

### Question 1: Test Baseline Performance ✅ RESOLVED
**Decision**: Full T0 baseline with commit-hash caching

**Peer's Answer**:
> "Yes, acceptable for now given ~600 tests—but implement caching by commit hash immediately."

**Implementation**:
- Capture baseline once per run at T0
- Cache by git commit SHA: `.autonomous_runs/baselines/<commit_sha>/pytest.json`
- Reuse cached baseline if commit hasn't changed
- Staged approach deferred until: runtime >60s OR suite >2000 tests OR high flake rate

---

### Question 2: Governance Persistence ✅ RESOLVED
**Decision**: Use database table from start

**Peer's Answer**:
> "Use DB (table) from the start. Queryability and audit trails across runs is the point of governance; DB makes that trivial."

**Implementation**:
- Create `governance_requests` table in database
- Store `requested_paths` as JSON text
- Minimal schema (avoid complex foreign keys)
- Aligns with existing Autopack architecture

---

### Question 3: Flaky Test Retry ✅ RESOLVED
**Decision**: Retry-once on newly failing + newly erroring, block if still failing

**Peer's Answer**:
> "Retry only newly failing tests and only once. Also retry newly introduced collection/import errors once. fail once → retry; pass on retry → warn; fail twice → block"

**Implementation**:
- Retry newly failing tests once
- Retry newly introduced collection/import errors once
- Pass on retry → log as `flaky_suspects` (warn, don't block)
- Fail twice → block completion
- Track flaky tests across runs (future: elevate if consistently flaky)

---

## Critical Architectural Corrections (From Peer Review)

### 1. PhaseFinalizer - Single Completion Authority

**Current Bug** (autonomous_executor.py:4473):
```python
# If quality gate passes OR approval granted:
self._update_phase_status(phase_id, "COMPLETE")  # ← NO ADDITIONAL CHECKS
```

**Fix**: Add PhaseFinalizer before completion
```python
# NEW: Comprehensive finalization check
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
    logger.error(f"[{phase_id}] Finalization BLOCKED: {finalization.reason}")
    self._update_phase_status(phase_id, finalization.status)
    return False, finalization.reason
```

---

### 2. Structured Test Output (No Text Parsing)

**Implementation**: Use pytest-json-report plugin
```python
# In test_baseline_tracker.py:
def capture_baseline(run_id: str, workspace: Path, commit_sha: str) -> TestBaseline:
    """Capture test baseline using structured output."""

    # Check cache first
    cache_file = workspace / f".autonomous_runs/baselines/{commit_sha}/pytest.json"
    if cache_file.exists():
        logger.info(f"[Baseline] Using cached baseline for commit {commit_sha[:8]}")
        return TestBaseline.from_json(cache_file.read_text())

    # Run pytest with JSON reporter
    result = subprocess.run(
        ["pytest", "--json-report", "--json-report-file=baseline.json", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120
    )

    # Parse structured JSON output
    report = json.loads((workspace / "baseline.json").read_text())

    baseline = TestBaseline(
        run_id=run_id,
        commit_sha=commit_sha,
        timestamp=datetime.now(timezone.utc),
        total_tests=report["summary"]["total"],
        passing_tests=report["summary"].get("passed", 0),
        failing_tests=report["summary"].get("failed", 0),
        error_tests=report["summary"].get("error", 0),
        skipped_tests=report["summary"].get("skipped", 0),
        failing_test_ids=[
            test["nodeid"] for test in report["tests"]
            if test["outcome"] in ["failed", "error"]
        ],
        error_signatures={
            test["nodeid"]: extract_error_signature(test)
            for test in report["tests"]
            if test["outcome"] == "error"
        }
    )

    # Cache for this commit
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(baseline.to_json())

    return baseline
```

---

### 3. Governance at Executor Level (Not in governed_apply)

**Peer's Important Note**:
> "Don't change `apply_patch()` to return a 3-tuple unless you really need to. Prefer returning `(success: bool, error_msg: str)` where `error_msg` is structured/typed."

**Revised Implementation**:
```python
# In governed_apply.py (NO signature change):
def apply_patch(self, patch_content: str, full_file_mode: bool = False) -> Tuple[bool, str]:
    """Apply patch with governance checks. Returns (success, error_msg)."""

    violations = self._check_violations(patch_content)

    if violations.protected_paths:
        # Return structured error message (JSON-encoded)
        error_data = {
            "error_type": "protected_path_violation",
            "violated_paths": violations.protected_paths,
            "justification": self._extract_justification(patch_content),
            "requires_approval": True
        }
        return False, json.dumps(error_data)

    # Normal validation continues...
    if violations.has_violations():
        return False, f"Governance violations: {violations}"

    # Apply patch
    return self._apply_patch_to_filesystem(patch_content)


# In autonomous_executor.py (detect structured error):
patch_success, error_msg = governed_apply.apply_patch(...)

if not patch_success:
    # Try to parse as structured error
    try:
        error_data = json.loads(error_msg)
        if error_data.get("error_type") == "protected_path_violation":
            # Handle governance request
            return self._handle_governance_request(phase_id, error_data)
    except (json.JSONDecodeError, KeyError):
        pass  # Not structured, treat as regular error

    # Regular failure
    logger.error(f"[{phase_id}] Failed to apply patch: {error_msg}")
    self._update_phase_status(phase_id, "FAILED")
    return False, "PATCH_FAILED"
```

**Why This Is Better**:
- No signature change (backward compatible)
- Structured error via JSON in error message
- Minimal code churn

---

### 4. Additional PhaseFinalizer Improvement (From Peer)

**Peer's Recommendation**:
> "Block on any new failures within the phase's own declared `validation_tests` (even if overall severity is 'medium')."

**Enhanced Blocking Logic**:
```python
class PhaseFinalizer:
    def assess_completion(
        self,
        phase_id: str,
        phase_spec: Dict,
        ci_result: Dict,
        baseline: Optional[TestBaseline],
        ...
    ) -> PhaseFinalizationDecision:
        """Comprehensive completion check."""

        blocking_issues = []
        warnings = []

        # Gate 1: CI baseline regression check
        if baseline and ci_result:
            delta = self.baseline_tracker.diff(baseline, ci_result)

            # ALWAYS BLOCK on new collection/import errors (after retry)
            if delta.new_collection_errors_persistent:  # Failed twice
                blocking_issues.append(
                    f"New collection errors: {delta.new_collection_errors_persistent}"
                )

            # ALWAYS BLOCK if newly failing tests intersect phase's validation_tests
            phase_validation_tests = set(phase_spec.get("validation", {}).get("tests", []))
            if phase_validation_tests:
                newly_failing_set = set(delta.newly_failing_persistent)
                overlap = phase_validation_tests & newly_failing_set
                if overlap:
                    blocking_issues.append(
                        f"Phase validation tests failed: {overlap}"
                    )

            # BLOCK on high/critical overall regression
            if delta.regression_severity in ["high", "critical"]:
                blocking_issues.append(
                    f"{delta.regression_severity.upper()} regression: "
                    f"{len(delta.newly_failing_persistent)} new failures"
                )

            # WARN on medium regression (unless overlap with validation_tests above)
            elif delta.regression_severity == "medium":
                warnings.append(
                    f"Medium regression: {len(delta.newly_failing_persistent)} new failures"
                )

            # Log flaky suspects
            if delta.flaky_suspects:
                warnings.append(
                    f"Flaky tests detected (passed on retry): {delta.flaky_suspects}"
                )

        # Gate 2: Quality gate decision
        if quality_report.is_blocked():
            blocking_issues.append(f"Quality gate blocked: {quality_report.quality_level}")

        # Gate 3: Deliverables validation
        deliverables_result = self.deliverables_validator.validate(
            phase_spec.get("deliverables", []),
            applied_files
        )
        if deliverables_result.missing_required:
            blocking_issues.append(
                f"Missing required deliverables: {deliverables_result.missing_required}"
            )

        # Decision
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
```

---

## Final Implementation Roadmap

### Phase 1: PhaseFinalizer + Test Baseline Tracker

**Priority**: CRITICAL (fixes BUILD-126 false completion bug)

**Files to Create**:

1. **`src/autopack/phase_finalizer.py`** (~250 lines)
```python
@dataclass
class PhaseFinalizationDecision:
    can_complete: bool
    status: str  # "COMPLETE", "FAILED", "BLOCKED"
    reason: str
    blocking_issues: List[str]
    warnings: List[str]

class PhaseFinalizer:
    def __init__(self, baseline_tracker, deliverables_validator):
        self.baseline_tracker = baseline_tracker
        self.deliverables_validator = deliverables_validator

    def assess_completion(...) -> PhaseFinalizationDecision:
        # Comprehensive gate checks (see enhanced logic above)
        pass
```

2. **`src/autopack/test_baseline_tracker.py`** (~350 lines)
```python
@dataclass
class TestBaseline:
    run_id: str
    commit_sha: str
    timestamp: datetime
    total_tests: int
    passing_tests: int
    failing_tests: int
    error_tests: int
    skipped_tests: int
    failing_test_ids: List[str]
    error_signatures: Dict[str, str]  # nodeid → error type + first line

    def to_json(self) -> str:
        """Serialize for caching."""

    @classmethod
    def from_json(cls, json_str: str) -> 'TestBaseline':
        """Deserialize from cache."""

@dataclass
class TestDelta:
    newly_failing: List[str]
    newly_failing_persistent: List[str]  # Failed twice (after retry)
    newly_passing: List[str]
    new_collection_errors: List[str]
    new_collection_errors_persistent: List[str]  # Failed twice
    flaky_suspects: List[str]  # Passed on retry
    regression_severity: str  # "none", "low", "medium", "high", "critical"

class TestBaselineTracker:
    def capture_baseline(
        self,
        run_id: str,
        workspace: Path,
        commit_sha: str
    ) -> TestBaseline:
        """Capture baseline with commit-hash caching."""
        # Implementation above (using pytest-json-report)

    def diff(
        self,
        baseline: TestBaseline,
        current: Dict  # pytest-json-report output
    ) -> TestDelta:
        """Compute regression delta."""

    def retry_newly_failing(
        self,
        newly_failing: List[str],
        workspace: Path
    ) -> Dict[str, str]:
        """Retry tests once. Returns {nodeid: 'passed'|'failed'}."""
        # Run: pytest <nodeid1> <nodeid2> ... --json-report -q
        # Parse results
```

3. **`tests/test_phase_finalizer.py`** (~200 lines)
   - Mock all gates, verify blocking logic
   - Test phase validation_tests overlap blocking
   - Test warnings vs blocking thresholds

4. **`tests/test_baseline_tracker.py`** (~250 lines)
   - Test baseline capture and caching
   - Test delta computation
   - Test retry logic (flaky detection)

**Integration Changes**:

1. **`autonomous_executor.py`** - Add T0 baseline capture:
```python
# In __init__ or run_autonomous_loop startup:
self.test_baseline = None
self.baseline_tracker = TestBaselineTracker()
self.phase_finalizer = PhaseFinalizer(
    baseline_tracker=self.baseline_tracker,
    deliverables_validator=self.deliverables_validator
)

# At T0 or first CI run:
if self.test_baseline is None:
    commit_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=self.workspace
    ).decode().strip()

    self.test_baseline = self.baseline_tracker.capture_baseline(
        run_id=self.run_id,
        workspace=Path(self.workspace),
        commit_sha=commit_sha
    )
    logger.info(
        f"[T0] Test baseline: {self.test_baseline.passing_tests}/"
        f"{self.test_baseline.total_tests} passing (commit {commit_sha[:8]})"
    )
```

2. **`autonomous_executor.py`** - Replace completion logic (line ~4473):
```python
# OLD:
# self._update_phase_status(phase_id, "COMPLETE")

# NEW:
finalization = self.phase_finalizer.assess_completion(
    phase_id=phase_id,
    phase_spec=phase,
    ci_result=ci_result,
    baseline=self.test_baseline,
    quality_report=quality_report,
    auditor_result=auditor_result,
    deliverables=phase.scope.get("deliverables", []),
    applied_files=[diff.file_path for diff in builder_result.diffs]
)

if finalization.can_complete:
    self._update_phase_status(phase_id, "COMPLETE")
    logger.info(f"[{phase_id}] Phase completed successfully")
    for warning in finalization.warnings:
        logger.warning(f"[{phase_id}] {warning}")
else:
    logger.error(f"[{phase_id}] Finalization BLOCKED: {finalization.reason}")
    for issue in finalization.blocking_issues:
        logger.error(f"  - {issue}")
    self._update_phase_status(phase_id, finalization.status)
    return False, finalization.reason
```

**Dependencies**:
- Install: `pip install pytest-json-report`
- No database migration needed (file-based caching)

**Success Criteria**:
- ✅ BUILD-126 Phase E2 scenario: BLOCKED for missing test file (not COMPLETE)
- ✅ Pre-existing errors (11 in BUILD-126) ignored in baseline
- ✅ New collection error → retry once → if persistent, BLOCK
- ✅ New test failure in phase's validation_tests → BLOCK (even if medium severity)
- ✅ Flaky tests (pass on retry) → WARN only, not BLOCK
- ✅ Baseline cached by commit SHA (fast second run)

---

### Phase 2: Governance Request Handler (Executor-Level)

**Priority**: HIGH (enables self-negotiation for protected paths)

**Files to Create**:

1. **`src/autopack/governance_requests.py`** (~200 lines)
```python
@dataclass
class GovernanceRequest:
    request_id: str
    run_id: str
    phase_id: str
    requested_paths: List[str]
    justification: str
    risk_level: str
    auto_approved: bool
    approved: Optional[bool]
    approved_by: Optional[str]
    created_at: datetime

def create_governance_request(
    db_session,
    run_id: str,
    phase_id: str,
    violated_paths: List[str],
    justification: str,
    risk_scorer
) -> GovernanceRequest:
    """Create request in database."""

def approve_request(db_session, request_id: str, approved_by: str) -> bool:
    """Approve request."""

def deny_request(db_session, request_id: str, denied_by: str) -> bool:
    """Deny request."""
```

2. **Modify `autonomous_executor.py`** - Add governance handler:
```python
def _handle_governance_request(
    self,
    phase_id: str,
    error_data: Dict
) -> Tuple[bool, str]:
    """Handle protected path governance request."""

    from autopack.governance_requests import create_governance_request, approve_request

    # Create request
    request = create_governance_request(
        db_session=self.db,
        run_id=self.run_id,
        phase_id=phase_id,
        violated_paths=error_data["violated_paths"],
        justification=error_data["justification"],
        risk_scorer=self.risk_scorer  # Use existing risk scorer if available
    )

    logger.warning(
        f"[Governance] Protected paths requested: {request.requested_paths}"
    )
    logger.info(f"[Governance] Justification: {request.justification}")

    # Check auto-approval (conservative defaults)
    if request.auto_approved:
        logger.info(f"[Governance] Auto-approved: {request.request_id}")
        # Retry with temporary allowance
        return self._retry_with_allowance(phase_id, request.requested_paths)

    # Require human approval
    logger.info(
        f"[Governance] Requesting human approval for: {request.request_id}"
    )
    logger.info(
        f"[Governance] Approve via: POST /api/governance/approve/{request.request_id}"
    )

    # Use existing Telegram approval flow
    approval_granted = self._request_human_approval(
        phase_id=phase_id,
        quality_report=None,  # Pass governance request instead
        governance_request=request,
        timeout_seconds=3600
    )

    if approval_granted:
        approve_request(self.db, request.request_id, approved_by="human")
        return self._retry_with_allowance(phase_id, request.requested_paths)
    else:
        logger.error(f"[Governance] Approval denied or timed out")
        self._update_phase_status(phase_id, "BLOCKED")
        return False, "GOVERNANCE_DENIED"

def _retry_with_allowance(
    self,
    phase_id: str,
    allowed_paths: List[str]
) -> Tuple[bool, str]:
    """Retry phase with temporary path allowance overlay."""

    logger.info(f"[Governance] Retrying with temporary allowance: {allowed_paths}")

    # Create permissive governed_apply instance
    governed_apply_permissive = GovernedApplyPath(
        workspace=Path(self.workspace),
        run_type=self.run_type,
        autopack_internal_mode=self.is_maintenance_run,
        scope_paths=self.current_scope_paths,
        allowed_paths=self.original_allowed_paths + allowed_paths  # Overlay
    )

    # Retry patch application
    patch_success, error_msg = governed_apply_permissive.apply_patch(
        self.current_patch_content,
        full_file_mode=True
    )

    if patch_success:
        logger.info(f"[Governance] Retry succeeded with allowance")
        return True, "GOVERNANCE_APPROVED"
    else:
        logger.error(f"[Governance] Retry failed even with allowance: {error_msg}")
        return False, "RETRY_FAILED"
```

3. **Add API endpoints in `main.py`**:
```python
from autopack.governance_requests import approve_request, deny_request

@app.get("/api/governance/pending")
def list_pending_governance_requests(db: Session = Depends(get_db)):
    """List all pending governance requests."""
    from autopack.models import GovernanceRequest

    pending = db.query(GovernanceRequest).filter(
        GovernanceRequest.approved.is_(None)
    ).all()

    return {
        "pending_requests": [
            {
                "request_id": req.request_id,
                "run_id": req.run_id,
                "phase_id": req.phase_id,
                "requested_paths": json.loads(req.requested_paths),
                "justification": req.justification,
                "risk_level": req.risk_level,
                "created_at": req.created_at.isoformat()
            }
            for req in pending
        ]
    }

@app.post("/api/governance/approve/{request_id}")
def approve_governance_request(
    request_id: str,
    approved: bool,
    user_id: str = "human",
    db: Session = Depends(get_db)
):
    """Approve or deny governance request."""

    if approved:
        success = approve_request(db, request_id, approved_by=user_id)
    else:
        success = deny_request(db, request_id, denied_by=user_id)

    if success:
        return {"status": "approved" if approved else "denied", "request_id": request_id}
    else:
        raise HTTPException(404, "Request not found")
```

4. **Database migration**:
```sql
CREATE TABLE governance_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT UNIQUE NOT NULL,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    requested_paths TEXT NOT NULL,  -- JSON array
    justification TEXT,
    risk_level TEXT,
    auto_approved BOOLEAN DEFAULT 0,
    approved BOOLEAN,
    approved_by TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX idx_governance_pending ON governance_requests(approved)
    WHERE approved IS NULL;
```

5. **`tests/test_governance_requests.py`** (~200 lines)

**Auto-Approval Policy** (CONSERVATIVE):
```python
# In governance_requests.py:
NEVER_AUTO_APPROVE = [
    "src/autopack/models.py",
    "alembic/versions/*",
    "src/autopack/main.py",
    "src/autopack/governed_apply.py",
    "src/autopack/autonomous_executor.py",
    "src/autopack/quality_gate.py",
    ".git/*",
    ".env*",
]

def can_auto_approve(path: str, risk_level: str, diff_stats: Dict, run_type: str) -> bool:
    """Conservative auto-approval check."""

    # Hard blocks
    if any(fnmatch(path, pattern) for pattern in NEVER_AUTO_APPROVE):
        return False

    if risk_level in ["high", "critical"]:
        return False

    if diff_stats.get("lines_changed", 0) > 100:
        return False  # Large changes need review

    # Default: Only new tests and docs auto-approved
    if fnmatch(path, "tests/test_*.py"):
        return True

    if fnmatch(path, "docs/*.md"):
        return True

    # Everything else requires human approval
    return False
```

**Success Criteria**:
- ✅ BUILD-126 Phase G scenario: Autopack requests approval for `quality_gate.py`
- ✅ Request visible via `GET /api/governance/pending`
- ✅ Human approves via `POST /api/governance/approve/<id>` or Telegram
- ✅ Phase retries with temporary allowance overlay
- ✅ Phase succeeds on retry
- ✅ Audit trail persisted in database
- ✅ Conservative auto-approval (tests/docs only by default)

---

### Phase 3: Enhanced Deliverables Validation

**Priority**: MEDIUM (improves deliverable enforcement)

**Implementation**: Request Builder emit structured manifest

**Modify Builder System Prompt**:
```
After implementing the changes, provide a deliverables manifest at the end of your response:

DELIVERABLES_MANIFEST:
```json
{
  "created": [
    {"path": "src/autopack/import_graph.py", "symbols": ["ImportGraphAnalyzer", "ImportGraph"]},
    {"path": "tests/test_import_graph.py", "symbols": ["test_analyze_imports", "test_build_graph"]}
  ],
  "modified": [
    {"path": "src/autopack/pattern_matcher.py", "changes": "Added import graph integration"}
  ]
}
```

This manifest will be validated to ensure all required deliverables are created.
```

**Extend `deliverables_validator.py`**:
```python
def validate_structured_manifest(
    manifest: Dict,
    workspace: Path
) -> ValidationResult:
    """Validate Builder's deliverables manifest."""

    missing = []
    issues = []

    for created in manifest.get("created", []):
        path = created["path"]
        if not (workspace / path).exists():
            missing.append(path)
        else:
            # Validate symbols exist
            content = (workspace / path).read_text()
            for symbol in created.get("symbols", []):
                if symbol not in content:
                    issues.append(f"{path} missing symbol: {symbol}")

    return ValidationResult(
        passed=len(missing) == 0 and len(issues) == 0,
        missing_required=missing,
        issues=issues
    )
```

**Integration**: Hook into PhaseFinalizer

**Success Criteria**:
- ✅ Missing test files detected (BUILD-126 Phase E2 scenario)
- ✅ Missing symbols detected
- ✅ Structured manifest parsing works

---

## Summary: What This Fixes

### BUILD-126 Issues Resolved:

1. **Phase E2 False Completion** ✅
   - Current: CI fails, phase completes anyway
   - Fixed: PhaseFinalizer blocks on missing test file + test regressions

2. **Phase G Governance Block** ✅
   - Current: Manual ALLOWED_PATHS edit required
   - Fixed: Autopack requests approval, human approves via API, retry succeeds

3. **Pre-existing Test Errors Noise** ✅
   - Current: 11 import errors mask new regressions
   - Fixed: Baseline diff ignores pre-existing, blocks only new errors

### Architectural Improvements:

- **Single Completion Authority**: PhaseFinalizer prevents bypasses
- **Structured Test Data**: No brittle text parsing
- **Separation of Concerns**: Governance at executor level, validation stays pure
- **Conservative Security**: Tight auto-approval defaults
- **Audit Trail**: All decisions logged in database

---

## Recommendation: Implement BUILD-127 Phase 1 Immediately

**Why**:
- Fixes critical "false completion" bug from BUILD-126
- Peer review complete, all design questions resolved
- Clear success criteria
- Minimal risk (backward compatible)

**Next Steps**:
1. Create BUILD-127 run with Phase 1 (PhaseFinalizer + Baseline Tracker)
2. Validate fix on BUILD-126 Phase E2 scenario (should block now)
3. Implement Phase 2 (Governance) once Phase 1 validated
4. Implement Phase 3 (Deliverables) for completeness

Ready to proceed!
