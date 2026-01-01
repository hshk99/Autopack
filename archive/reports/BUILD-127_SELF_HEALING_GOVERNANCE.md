# BUILD-127: Self-Healing Governance & Test Failure Prevention

**Status**: Design Proposal
**Parent**: BUILD-126 (identified limitations during Phase E2-I implementation)
**Priority**: HIGH

---

## Problem Analysis

### Issue 1: CI Test Failures Not Preventing Completion

**Observed Behavior** (BUILD-126 Phase E2):
- Builder creates `import_graph.py` (17KB) ✅
- Patch applies successfully ✅
- CI runs pytest → **FAILS** (11 import errors, 634 tests couldn't collect) ❌
- Auditor reviews → `approved=False, issues=1` ⚠️
- Quality Gate → `needs_review` ⚠️
- **Phase marked COMPLETE anyway** ❌

**Root Cause Analysis**:
```
CI Test Failures (from pytest log):
1. Missing test file: tests/test_import_graph.py not created
2. Pre-existing errors (11 import errors):
   - ModuleNotFoundError: src.autopack.scope_expander (we deleted it)
   - ImportError: autopack.diagnostics.* (BUILD-112 incomplete)
   - SQLAlchemy table conflicts
   - Reddit API 401 errors
   - __pycache__ conflicts

Result: Real test failures masked by pre-existing errors
```

**Current Quality Gate Logic** (in `quality_gate.py`):
```python
# Phase completes if:
1. Patch applies successfully OR
2. Auditor approved=False is ADVISORY (not blocking) OR
3. CI failures are ignored (no hard validation)

# Missing:
- Differentiate new test failures from pre-existing ones
- Block completion on NEW test regressions
- Require deliverables validation (test file creation)
```

---

### Issue 2: Protected Path Governance Requires Manual Intervention

**Observed Behavior** (BUILD-126 Phase G):
- Builder generates patch to modify `quality_gate.py` ✅
- Governance check → **BLOCKED**: `src/autopack/quality_gate.py` is protected ❌
- Phase fails immediately, no retry ❌
- **Human manually adds to ALLOWED_PATHS** 🧑‍💻
- Phase reset to QUEUED manually 🧑‍💻
- Retry succeeds ✅

**Root Cause**:
```python
# governed_apply.py has static lists:
PROTECTED_PATHS = ["src/autopack/", ...]  # Broad protection
ALLOWED_PATHS = ["src/autopack/learned_rules.py", ...]  # Specific exceptions

# Problem:
- Builder cannot dynamically request path allowance
- No "request approval" mechanism for protected paths
- Autopack cannot self-heal governance blocks
```

**Why This Matters**:
- Autopack's goal: autonomous operation
- Current behavior: human-in-the-loop for governance decisions
- This breaks autonomy for self-improvement tasks

---

## Proposed Solutions

### Solution 1: Baseline-Aware CI Validation

**Design: Differential Test Failure Detection**

Create `test_baseline_tracker.py` to distinguish new failures from pre-existing ones:

```python
@dataclass
class TestBaseline:
    """Snapshot of test suite health at run start."""
    run_id: str
    timestamp: datetime
    total_tests: int
    passing_tests: int
    failing_tests: int
    error_tests: int
    skipped_tests: int
    failing_test_ids: List[str]  # test::module::TestClass::test_method
    error_messages: Dict[str, str]  # test_id -> error message
    baseline_hash: str  # Hash of all test outcomes for comparison

@dataclass
class TestDelta:
    """Difference between baseline and current test results."""
    newly_failing: List[str]  # Tests that passed in baseline, now fail
    newly_passing: List[str]  # Tests that failed in baseline, now pass
    newly_erroring: List[str]  # New import/collection errors
    resolved_errors: List[str]  # Errors that existed in baseline, now fixed
    regression_severity: str  # "none", "low", "medium", "high", "critical"

class TestBaselineTracker:
    """Track test baseline and detect regressions."""

    def __init__(self, workspace: Path, db_session):
        self.workspace = workspace
        self.db = db_session

    def capture_baseline(self, run_id: str) -> TestBaseline:
        """Capture test suite baseline at T0 (run start)."""
        # Run: pytest --collect-only --quiet
        # Parse output to get test inventory
        # Run: pytest --tb=no -q (fast, minimal output)
        # Record all failures/errors
        # Store in database: runs_test_baseline table
        pass

    def analyze_delta(
        self,
        baseline: TestBaseline,
        current_results: TestResults
    ) -> TestDelta:
        """Compare current results to baseline."""
        # Compute set differences
        # Classify severity:
        #   - critical: newly_failing > 10 OR core tests regressed
        #   - high: newly_failing > 5
        #   - medium: newly_failing > 2
        #   - low: newly_failing == 1-2
        #   - none: no new failures
        pass

    def should_block_completion(self, delta: TestDelta) -> Tuple[bool, str]:
        """Decide if test delta should block phase completion."""
        if delta.regression_severity in ["critical", "high"]:
            return True, f"Critical regression: {len(delta.newly_failing)} new test failures"

        if delta.newly_erroring:
            return True, f"New import errors introduced: {delta.newly_erroring}"

        # Allow completion if only pre-existing failures persist
        return False, "No new test regressions"
```

**Integration Points**:

1. **T0 Health Checks** (autonomous_executor.py startup):
```python
# After existing T0 checks:
test_baseline = tracker.capture_baseline(run_id)
db.add(test_baseline)
db.commit()
logger.info(f"[T0] Test baseline: {baseline.passing_tests}/{baseline.total_tests} passing")
```

2. **CI Execution** (after pytest run):
```python
# In execute_phase, after CI runs:
current_results = parse_pytest_output(ci_output)
baseline = db.query(TestBaseline).filter_by(run_id=run_id).first()

delta = tracker.analyze_delta(baseline, current_results)
should_block, reason = tracker.should_block_completion(delta)

if should_block:
    logger.error(f"[CI_BLOCK] {reason}")
    return PhaseResult(
        status="FAILED",
        reason="test_regression",
        details={"delta": delta, "reason": reason}
    )
```

3. **Quality Gate Enhancement**:
```python
# In quality_gate.py:
def evaluate_ci_results(
    self,
    ci_output: str,
    test_baseline: TestBaseline
) -> QualityGateResult:
    """Evaluate CI results against baseline."""
    delta = self.tracker.analyze_delta(baseline, current)

    if delta.regression_severity == "none":
        return QualityGateResult(passed=True, gate="ci_validation")

    if delta.regression_severity in ["low", "medium"]:
        # Advisory: log warning but allow completion
        return QualityGateResult(
            passed=True,
            gate="ci_validation",
            warnings=[f"Minor regression: {len(delta.newly_failing)} new failures"]
        )

    # Block on high/critical regressions
    return QualityGateResult(
        passed=False,
        gate="ci_validation",
        reason=f"{delta.regression_severity.upper()} regression detected"
    )
```

**Benefits**:
- ✅ Distinguishes new failures from pre-existing ones
- ✅ Blocks completion only on genuine regressions
- ✅ Tolerates unstable test suites (common in active development)
- ✅ Provides clear feedback on what broke

**Limitations**:
- Requires stable test execution environment
- Baseline capture adds ~30s to T0 startup
- Flaky tests may cause false positives (mitigate with retry logic)

---

### Solution 2: Dynamic Governance with Approval Requests

**Design: Self-Service Path Allowance with Approval Gates**

Create `governance_negotiator.py` to handle protected path access requests:

```python
@dataclass
class PathAccessRequest:
    """Request to access a protected path."""
    request_id: str  # UUID
    run_id: str
    phase_id: str
    requested_path: str
    justification: str  # From Builder: "Need to extend quality_gate.py with rollback"
    risk_level: str  # "low", "medium", "high" (from RiskScorer)
    auto_approved: bool  # True if risk_level == "low"
    requires_human_approval: bool  # True if risk_level in ["medium", "high"]
    approved: Optional[bool] = None
    approved_by: Optional[str] = None  # "system" or human user ID
    approved_at: Optional[datetime] = None

@dataclass
class GovernancePolicy:
    """Rules for auto-approving path access requests."""
    auto_approve_patterns: List[str] = field(default_factory=lambda: [
        # Patterns that can be auto-approved for BUILD-126-style tasks
        "src/autopack/{import_graph,scope_refiner,risk_scorer,context_summarizer}.py",
        "tests/test_*.py",  # New test files always allowed
        "docs/*.md",  # Documentation always allowed
    ])

    require_approval_patterns: List[str] = field(default_factory=lambda: [
        "src/autopack/models.py",  # Database schema changes
        "alembic/versions/*",  # Migrations require human review
        "src/autopack/main.py",  # API router changes
        ".git/*",  # Git internals never allowed
    ])

    run_type_overrides: Dict[str, List[str]] = field(default_factory=lambda: {
        # Run types that get broader access
        "autopack_maintenance": ["src/autopack/**/*.py"],  # Self-repair gets full access
        "autopack_upgrade": ["src/autopack/**/*.py"],
        "self_repair": ["src/autopack/**/*.py"],
    })

class GovernanceNegotiator:
    """Manages dynamic path access requests with approval gates."""

    def __init__(
        self,
        workspace: Path,
        db_session,
        policy: GovernancePolicy,
        risk_scorer: RiskScorer
    ):
        self.workspace = workspace
        self.db = db_session
        self.policy = policy
        self.risk_scorer = risk_scorer

    def request_path_access(
        self,
        run_id: str,
        phase_id: str,
        requested_paths: List[str],
        justification: str
    ) -> PathAccessRequest:
        """Request access to protected paths."""
        # Score risk for each path
        risk_scores = [
            self.risk_scorer.score_path_modification(path)
            for path in requested_paths
        ]
        max_risk = max(risk_scores)

        # Check auto-approval eligibility
        auto_approved = self._can_auto_approve(requested_paths, max_risk)

        request = PathAccessRequest(
            request_id=str(uuid.uuid4()),
            run_id=run_id,
            phase_id=phase_id,
            requested_path=", ".join(requested_paths),
            justification=justification,
            risk_level=max_risk.level,
            auto_approved=auto_approved,
            requires_human_approval=not auto_approved
        )

        if auto_approved:
            request.approved = True
            request.approved_by = "system"
            request.approved_at = datetime.now(timezone.utc)
            logger.info(f"[Governance] Auto-approved: {requested_paths} (risk={max_risk.level})")
        else:
            logger.warning(f"[Governance] Human approval required: {requested_paths} (risk={max_risk.level})")

        # Persist request
        self.db.add(request)
        self.db.commit()

        return request

    def _can_auto_approve(self, paths: List[str], risk: RiskScore) -> bool:
        """Check if paths can be auto-approved."""
        # Never auto-approve HIGH risk
        if risk.level == "high":
            return False

        # Check if all paths match auto-approve patterns
        for path in paths:
            if not any(fnmatch.fnmatch(path, pattern) for pattern in self.policy.auto_approve_patterns):
                return False

            # Hard block if path matches require-approval patterns
            if any(fnmatch.fnmatch(path, pattern) for pattern in self.policy.require_approval_patterns):
                return False

        return True

    def wait_for_approval(
        self,
        request: PathAccessRequest,
        timeout_seconds: int = 300
    ) -> bool:
        """Wait for human approval (blocking, with timeout)."""
        if request.auto_approved:
            return True

        logger.info(f"[Governance] Waiting for approval: {request.request_id}")
        logger.info(f"[Governance] Justification: {request.justification}")
        logger.info(f"[Governance] Approve via: POST /api/governance/approve/{request.request_id}")

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            # Poll database for approval
            self.db.refresh(request)
            if request.approved is not None:
                return request.approved
            time.sleep(10)  # Poll every 10s

        logger.error(f"[Governance] Approval timeout for {request.request_id}")
        return False

    def apply_temporary_allowance(
        self,
        request: PathAccessRequest,
        governed_apply: GovernedApplyPath
    ):
        """Temporarily add approved paths to allowed list (for current phase only)."""
        if not request.approved:
            raise ValueError(f"Cannot apply allowance for unapproved request {request.request_id}")

        paths = [p.strip() for p in request.requested_path.split(",")]
        governed_apply.allowed_paths.extend(paths)

        logger.info(f"[Governance] Temporarily allowed: {paths} (request={request.request_id})")
```

**Integration with GovernedApplyPath**:

```python
# In governed_apply.py:
class GovernedApplyPath:
    def apply_patch(self, patch: str, phase_id: str, run_id: str) -> ApplyResult:
        """Apply patch with governance negotiation."""
        violations = self._check_violations(patch)

        if violations.protected_paths:
            # NEW: Request approval for protected paths
            logger.warning(f"[Governance] Protected paths detected: {violations.protected_paths}")

            # Extract justification from patch (Builder should include this in commit message)
            justification = self._extract_justification(patch)

            # Request access
            request = self.negotiator.request_path_access(
                run_id=run_id,
                phase_id=phase_id,
                requested_paths=violations.protected_paths,
                justification=justification
            )

            if request.auto_approved:
                # Grant temporary allowance and proceed
                self.negotiator.apply_temporary_allowance(request, self)
                logger.info(f"[Governance] Auto-approved, proceeding with patch")
                # Re-check violations (should pass now)
                violations = self._check_violations(patch)
            else:
                # Pause and wait for human approval
                logger.info(f"[Governance] Pausing phase for approval (request={request.request_id})")
                approved = self.negotiator.wait_for_approval(request, timeout_seconds=300)

                if approved:
                    self.negotiator.apply_temporary_allowance(request, self)
                    violations = self._check_violations(patch)
                else:
                    return ApplyResult(
                        success=False,
                        reason="governance_approval_denied",
                        details=f"Request {request.request_id} not approved"
                    )

        # Proceed with patch application (violations should be clear now)
        if violations.has_violations():
            return ApplyResult(success=False, reason="governance_violation", ...)

        # Apply patch normally
        ...
```

**API Endpoint for Human Approval**:

```python
# In main.py:
@app.post("/api/governance/approve/{request_id}")
def approve_governance_request(
    request_id: str,
    approved: bool,
    user_id: str = "human"
):
    """Approve or deny a governance access request."""
    request = db.query(PathAccessRequest).filter_by(request_id=request_id).first()
    if not request:
        raise HTTPException(404, "Request not found")

    request.approved = approved
    request.approved_by = user_id
    request.approved_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "approved" if approved else "denied", "request_id": request_id}

@app.get("/api/governance/pending")
def list_pending_requests():
    """List all pending governance requests."""
    requests = db.query(PathAccessRequest).filter(
        PathAccessRequest.approved.is_(None)
    ).all()
    return {"pending_requests": [r.to_dict() for r in requests]}
```

**Benefits**:
- ✅ Autopack can self-request path access
- ✅ Low-risk paths auto-approved (no human needed)
- ✅ High-risk paths pause for human approval
- ✅ Full audit trail of governance decisions
- ✅ Maintains security while enabling autonomy

**Limitations**:
- Adds complexity to governance logic
- Timeout on approval (5 min default) may block run progress
- Requires clear justification from Builder (need prompt engineering)

---

### Solution 3: Builder-Directed Deliverables Validation

**Problem**: Phase E2 completed without creating `tests/test_import_graph.py`

**Current**: Deliverables are listed in phase YAML but not validated:
```yaml
deliverables:
  - "src/autopack/import_graph.py with ImportGraphAnalyzer class"
  - "tests/test_import_graph.py with comprehensive tests"  # ← NOT CREATED
```

**Proposed**: Extend `deliverables_validator.py` to parse and validate structured deliverables:

```python
@dataclass
class DeliverableSpec:
    """Parsed deliverable specification."""
    file_path: str  # Extracted path (e.g., "tests/test_import_graph.py")
    must_exist: bool  # True if deliverable is a file that must be created
    must_contain: List[str]  # Required symbols/patterns (e.g., ["ImportGraphAnalyzer"])
    optional: bool  # True if deliverable is optional (e.g., "Documentation if needed")
    description: str  # Original deliverable text

class DeliverableParser:
    """Extract file paths and requirements from deliverable strings."""

    # Patterns to extract file paths from deliverable text
    PATH_PATTERNS = [
        r"([a-z_/]+\.py)",  # Matches: "src/autopack/import_graph.py"
        r"([a-z_/]+\.md)",  # Matches: "docs/BUILD-126.md"
        r"Create `([^`]+)`",  # Matches: "Create `test_import_graph.py`"
        r"Update `([^`]+)`",  # Matches: "Update `manifest_generator.py`"
    ]

    def parse_deliverable(self, deliverable_text: str) -> DeliverableSpec:
        """Parse deliverable text into structured spec."""
        # Extract file path
        file_path = None
        for pattern in self.PATH_PATTERNS:
            match = re.search(pattern, deliverable_text)
            if match:
                file_path = match.group(1)
                break

        # Determine if file must exist (CREATE vs UPDATE)
        must_exist = "create" in deliverable_text.lower() or \
                     "with" in deliverable_text.lower()

        # Extract required contents
        must_contain = []
        # Look for: "with X class" or "containing Y function"
        if "with" in deliverable_text:
            parts = deliverable_text.split("with")
            if len(parts) > 1:
                # Extract identifiers (e.g., "ImportGraphAnalyzer class")
                identifiers = re.findall(r"(\w+)\s+(?:class|function|method)", parts[1])
                must_contain.extend(identifiers)

        # Check if optional
        optional = "optional" in deliverable_text.lower() or \
                   "if needed" in deliverable_text.lower()

        return DeliverableSpec(
            file_path=file_path or "",
            must_exist=must_exist,
            must_contain=must_contain,
            optional=optional,
            description=deliverable_text
        )

class EnhancedDeliverablesValidator:
    """Validate that Builder delivered all required artifacts."""

    def validate_structured_deliverables(
        self,
        deliverables: List[str],
        applied_files: List[str],
        workspace: Path
    ) -> ValidationResult:
        """Validate deliverables with structured parsing."""
        parser = DeliverableParser()
        issues = []
        warnings = []

        for deliverable_text in deliverables:
            spec = parser.parse_deliverable(deliverable_text)

            if not spec.file_path:
                warnings.append(f"Could not extract file path from: {deliverable_text}")
                continue

            # Check if file was created/modified
            file_exists = (workspace / spec.file_path).exists()
            file_in_patch = spec.file_path in applied_files

            if spec.must_exist and not file_exists:
                if spec.optional:
                    warnings.append(f"Optional deliverable missing: {spec.file_path}")
                else:
                    issues.append(f"Required file not created: {spec.file_path}")

            # Validate contents if file exists
            if file_exists and spec.must_contain:
                content = (workspace / spec.file_path).read_text()
                for required_symbol in spec.must_contain:
                    if required_symbol not in content:
                        issues.append(
                            f"{spec.file_path} missing required symbol: {required_symbol}"
                        )

        return ValidationResult(
            passed=len(issues) == 0,
            issues=issues,
            warnings=warnings
        )
```

**Integration**:
```python
# In autonomous_executor.py, after patch application:
validator = EnhancedDeliverablesValidator()
validation = validator.validate_structured_deliverables(
    deliverables=phase.scope["deliverables"],
    applied_files=[diff.file_path for diff in builder_result.diffs],
    workspace=self.workspace
)

if not validation.passed:
    logger.error(f"[Deliverables] Validation failed: {validation.issues}")
    # Provide feedback to Builder for retry
    feedback = format_validation_feedback_for_builder(validation)
    # Retry with feedback OR fail phase
```

---

## Implementation Plan

### Phase 1: Test Baseline Tracker (HIGH PRIORITY)
**Files**:
- `src/autopack/test_baseline_tracker.py` (~300 lines)
- `tests/test_baseline_tracker.py` (~200 lines)
- Modify `autonomous_executor.py` (T0 capture + CI comparison)
- Modify `quality_gate.py` (integrate baseline-aware validation)

**Database Migration**:
```sql
CREATE TABLE runs_test_baseline (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    total_tests INTEGER,
    passing_tests INTEGER,
    failing_tests INTEGER,
    error_tests INTEGER,
    failing_test_ids TEXT,  -- JSON array
    error_messages TEXT,  -- JSON object
    baseline_hash TEXT
);
```

**Success Criteria**:
- T0 baseline captures in <30s
- Differential analysis detects new failures accurately
- Pre-existing errors (11 in BUILD-126) ignored
- New import errors block completion

---

### Phase 2: Dynamic Governance Negotiator (HIGH PRIORITY)
**Files**:
- `src/autopack/governance_negotiator.py` (~400 lines)
- `tests/test_governance_negotiator.py` (~250 lines)
- Modify `governed_apply.py` (integrate negotiator)
- Modify `main.py` (add approval endpoints)

**Database Migration**:
```sql
CREATE TABLE governance_access_requests (
    id INTEGER PRIMARY KEY,
    request_id TEXT UNIQUE NOT NULL,
    run_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    requested_path TEXT NOT NULL,
    justification TEXT,
    risk_level TEXT,
    auto_approved BOOLEAN,
    requires_human_approval BOOLEAN,
    approved BOOLEAN,
    approved_by TEXT,
    approved_at DATETIME
);
```

**Success Criteria**:
- Low-risk paths auto-approved (<1s)
- High-risk paths pause for approval
- Approval API works correctly
- BUILD-126 Phase G would succeed without manual intervention

---

### Phase 3: Enhanced Deliverables Validation (MEDIUM PRIORITY)
**Files**:
- Extend `src/autopack/deliverables_validator.py` (+200 lines)
- `tests/test_deliverables_parser.py` (~150 lines)
- Modify `autonomous_executor.py` (use structured validation)

**Success Criteria**:
- Parse 90%+ of deliverable specifications correctly
- Detect missing test files (BUILD-126 Phase E2)
- Provide actionable feedback to Builder for retry

---

## Risk Assessment

### Phase 1 Risks:
- **Baseline capture overhead**: +30s to T0 (mitigate: cache results, run in background)
- **Flaky tests**: May cause false positives (mitigate: retry flaky tests 3x before flagging)
- **Test environment drift**: Baseline may become stale (mitigate: refresh every 24h)

### Phase 2 Risks:
- **Security**: Auto-approval could allow malicious code (mitigate: conservative risk scoring, audit trail)
- **Approval timeout**: Blocks run progress (mitigate: configurable timeout, notification system)
- **Complexity**: Adds governance logic overhead (mitigate: thorough testing, clear documentation)

### Phase 3 Risks:
- **Parsing accuracy**: May misinterpret deliverable text (mitigate: fallback to human-readable warnings)
- **False negatives**: May miss subtle deliverable violations (mitigate: combine with CI tests)

---

## Metrics & Success Criteria

**Key Metrics**:
1. **Test Regression Detection Rate**: % of new test failures correctly identified
2. **False Positive Rate**: % of pre-existing failures incorrectly flagged as new
3. **Governance Auto-Approval Rate**: % of protected path requests auto-approved
4. **Governance Approval Latency**: Time from request to approval (target: <5min for human)
5. **Deliverable Validation Accuracy**: % of deliverable specs correctly parsed

**Success Thresholds**:
- Test regression detection: ≥95%
- False positive rate: ≤5%
- Auto-approval rate: ≥70% (for self-improvement tasks)
- Governance latency: <5min (95th percentile)
- Deliverable parsing: ≥90%

---

## Open Questions

1. **Test Baseline Refresh Strategy**: How often should baseline be recaptured?
   - Option A: Every 24h (stale but stable)
   - Option B: On main branch push (fresh but variable)
   - Option C: Manual trigger only

2. **Governance Approval UX**: How should humans be notified?
   - Option A: Polling-only (current design)
   - Option B: Webhook/email notifications
   - Option C: Slack/Teams integration

3. **Builder Justification Prompt**: How to ensure Builder provides good justifications?
   - Need prompt engineering to extract rationale from Builder output
   - Example prompt addition: "If modifying protected paths, explain why this change is necessary and safe."

4. **Rollback on Approval Denial**: What happens when human denies approval?
   - Option A: Fail phase immediately
   - Option B: Retry with alternative approach (Builder re-plans)
   - Option C: Escalate to higher-tier model

---

## Conclusion

These three solutions address the core autonomy limitations identified in BUILD-126:

1. ✅ **Test Baseline Tracker**: Prevents false completions by detecting real regressions
2. ✅ **Dynamic Governance**: Enables self-service path access while maintaining security
3. ✅ **Deliverables Validation**: Ensures all required artifacts are delivered

Together, they move Autopack closer to true autonomous operation with intelligent self-healing for common blockers.

**Recommended Implementation Order**: Phase 1 → Phase 2 → Phase 3
**Estimated Effort**: 3-4 autonomous runs (BUILD-127, BUILD-128, BUILD-129)
