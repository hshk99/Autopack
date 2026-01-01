# BUILD-113: Iterative Autonomous Investigation with Goal-Aware Judgment

**Date**: 2025-12-21
**Status**: IN PROGRESS
**Priority**: P1 (High Priority - Completes Diagnostics Parity)
**Build Type**: Enhancement (Autonomous Investigation)

---

## 1. Objective

Implement **multi-round autonomous investigation** that enables Autopack to:
1. Iteratively collect evidence through targeted probes (no human copy/paste)
2. Make goal-aware judgment calls using phase deliverables and acceptance criteria
3. Auto-decide on low/medium-risk fixes with full audit trails
4. Block only for truly risky or ambiguous situations
5. Log all decisions with rationale and alternatives for human review

**Key Insight**: The original "Evidence Requests Loop" design was flawed - it asked humans to copy/paste data that Autopack can collect autonomously. BUILD-113 focuses on **autonomous investigation** with **goal-aware judgment**, not human copy/paste.

---

## 2. Problem Statement

### Current State (BUILD-112 - 90% Parity):
- ✅ Rich diagnostics with probes, handoff bundles, Cursor prompts
- ✅ Deep retrieval and second opinion triage
- ❌ **Single-round diagnostics** - if initial probes miss something, Autopack gives up
- ❌ **No autonomous judgment** - always escalates to human even for clear fixes
- ❌ **No goal awareness** - doesn't use deliverables/acceptance criteria to guide decisions

### Desired State (BUILD-113 - 95%+ Parity):
- ✅ **Multi-round investigation** - Autopack iteratively collects evidence until root cause found
- ✅ **Goal-aware decisions** - Uses phase deliverables, acceptance criteria, and constraints
- ✅ **Autonomous low-risk fixes** - Auto-applies fixes that clearly meet goals with no side effects
- ✅ **Auditable decisions** - All choices logged with rationale, alternatives, and risk assessment
- ✅ **Smart escalation** - Only blocks for risky operations (>200 line deletions, protected paths, ambiguity)

---

## 3. Design Principles

### A. Autonomous Investigation Over Human Copy/Paste
- Autopack has full filesystem and command access (like Cursor)
- Multi-round probing: analyze → identify gaps → run targeted probes → repeat
- Human input only for strategic judgment, never for mechanical data collection

### B. Goal-Oriented Decision Making
Every phase has:
- **Deliverables**: Files that must be created/modified
- **Acceptance Criteria**: Tests that must pass
- **Allowed Paths**: Safe modification zones
- **Protected Paths**: Hard boundaries

Decisions must:
- Advance toward deliverables
- Not violate constraints
- Pass acceptance tests

### C. Safety Nets Enable Autonomy
Existing safeguards allow autonomous decisions:
- **Git save points** before risky changes (BUILD-107)
- **Automatic rollback** if tests fail
- **Telegram notifications** for medium/high-risk changes (BUILD-108)
- **Decision logging** for audit trails

### D. Risk-Based Gating
- **LOW RISK** (auto-proceed): <100 lines changed, within allowed_paths, meets deliverables
- **MEDIUM RISK** (notify + proceed): 100-200 lines, multiple files, notify via Telegram
- **HIGH RISK** (block for approval): >200 lines, protected paths, ambiguous failures

---

## 4. Architecture

### 4.1 Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                   AutonomousExecutor                        │
│  (existing - enhanced with iterative investigation)         │
└───────────────┬─────────────────────────────────────────────┘
                │
                │ on_failure()
                ↓
┌─────────────────────────────────────────────────────────────┐
│              IterativeInvestigator (NEW)                    │
│  • Multi-round evidence collection                          │
│  • Gap analysis (what's missing?)                           │
│  • Targeted probe generation                                │
│  • Goal-aware decision orchestration                        │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├─→ DiagnosticsAgent (existing)
                │   • Run probes (Stage 1)
                │   • Deep retrieval (Stage 2)
                │   • Evidence collection
                │
                ├─→ GoalAwareDecisionMaker (NEW)
                │   • Analyze evidence vs deliverables
                │   • Risk assessment
                │   • Rationale generation
                │   • Alternative ranking
                │
                └─→ DecisionExecutor (NEW)
                    • Create git save points
                    • Apply fixes
                    • Validate deliverables
                    • Run acceptance tests
                    • Auto-rollback on failure
                    • Log decisions with metadata
```

### 4.2 Investigation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Phase Failure Detected                     │
└───────────────┬─────────────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────────────┐
│  ROUND 1: Initial Diagnostics                               │
│  • Run standard probes (git status, logs, tests)            │
│  • Deep retrieval (if triggered)                            │
│  • Evidence collection                                      │
└───────────────┬─────────────────────────────────────────────┘
                │
                ↓
┌─────────────────────────────────────────────────────────────┐
│  Gap Analysis                                                │
│  • What evidence is missing?                                │
│  • What files need inspection?                              │
│  • What commands should run?                                │
└───────────────┬─────────────────────────────────────────────┘
                │
                ↓
        ┌───────┴────────┐
        │ Gaps found?    │
        └───┬────────┬───┘
            │ YES    │ NO
            ↓        ↓
┌─────────────────┐  ┌──────────────────────────────────────┐
│  ROUND 2+:      │  │  Goal-Aware Decision Making          │
│  • Generate     │  │  • Analyze evidence vs deliverables  │
│    targeted     │  │  • Assess risk (low/medium/high)     │
│    probes       │  │  • Generate rationale                │
│  • Run probes   │  │  • Rank alternatives                 │
│  • Update       │  │  • Decide: CLEAR_FIX / AMBIGUOUS /   │
│    evidence     │  │           NEED_MORE / RISKY          │
│  • Repeat       │  └──────────────┬───────────────────────┘
│    (max 5       │                 │
│     rounds)     │                 ↓
└─────────────────┘         ┌───────┴────────┐
                            │ Decision Type? │
                            └───┬────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ↓               ↓               ↓
        ┌──────────────┐ ┌──────────────┐ ┌─────────────┐
        │  CLEAR_FIX   │ │  RISKY       │ │  AMBIGUOUS  │
        │  • Save      │ │  • Block     │ │  • Generate │
        │    point     │ │  • Notify    │ │    handoff  │
        │  • Apply     │ │  • Escalate  │ │  • Escalate │
        │  • Validate  │ │    to human  │ │    to human │
        │  • Test      │ └──────────────┘ └─────────────┘
        │  • Rollback  │
        │    if fail   │
        │  • Log       │
        │    decision  │
        └──────────────┘
```

---

## 5. Component Specifications

### 5.1 IterativeInvestigator

**Location**: `src/autopack/diagnostics/iterative_investigator.py`

**Responsibilities**:
- Orchestrate multi-round investigation (max 5 rounds)
- Analyze evidence gaps after each round
- Generate targeted probes based on gaps
- Coordinate with DiagnosticsAgent for probe execution
- Invoke GoalAwareDecisionMaker when sufficient evidence collected
- Return investigation result with decision or escalation

**Key Methods**:
```python
def investigate_and_resolve(
    self,
    failure_context: Dict[str, Any],
    phase_spec: PhaseSpec
) -> InvestigationResult:
    """
    Multi-round investigation until resolved or escalation needed.

    Args:
        failure_context: Error details, stack trace, attempt number
        phase_spec: Deliverables, acceptance criteria, path constraints

    Returns:
        InvestigationResult with decision, evidence, audit trail
    """

def _analyze_evidence_gaps(
    self,
    evidence: Dict[str, Any],
    failure_context: Dict[str, Any]
) -> List[EvidenceGap]:
    """
    Identify what evidence is missing.

    Example gaps:
    - Missing pytest output (need to run tests)
    - Missing file content (need to read specific file)
    - Missing command output (need to run diagnostic command)
    """

def _generate_targeted_probes(
    self,
    gaps: List[EvidenceGap]
) -> List[Probe]:
    """
    Convert evidence gaps into executable probes.

    Example:
    Gap: "Missing pytest output for test_tracer_bullet.py"
    → Probe: ProbeCommand("pytest tests/test_tracer_bullet.py -v")
    """
```

**Configuration**:
- `max_rounds`: 5 (prevent infinite loops)
- `max_probes_per_round`: 3 (token efficiency)
- `evidence_sufficiency_threshold`: Heuristic for "enough evidence"

---

### 5.2 GoalAwareDecisionMaker

**Location**: `src/autopack/diagnostics/goal_aware_decision.py`

**Responsibilities**:
- Analyze evidence against phase deliverables and constraints
- Generate fix strategies aligned with goals
- Assess risk level (LOW/MEDIUM/HIGH)
- Produce detailed rationale with alternatives
- Decide: CLEAR_FIX, NEED_MORE_EVIDENCE, AMBIGUOUS, or RISKY

**Key Methods**:
```python
def make_decision(
    self,
    evidence: Dict[str, Any],
    phase_spec: PhaseSpec
) -> Decision:
    """
    Make goal-aware decision based on evidence and constraints.

    Returns:
        Decision object with:
        - type: CLEAR_FIX, NEED_MORE_EVIDENCE, AMBIGUOUS, RISKY
        - fix_strategy: Description of fix approach
        - rationale: Why this decision was made
        - alternatives_considered: Other options and why rejected
        - risk_level: LOW, MEDIUM, HIGH
        - deliverables_met: Which deliverables this satisfies
        - files_modified: What files will change
        - net_deletion: Lines removed - lines added
    """

def _assess_risk(
    self,
    fix_strategy: FixStrategy,
    phase_spec: PhaseSpec
) -> RiskLevel:
    """
    Risk assessment logic:

    HIGH RISK:
    - Deletes >200 lines (requires approval per BUILD-107)
    - Touches protected_paths
    - Modifies files outside allowed_paths
    - Breaking API changes

    MEDIUM RISK:
    - Deletes 100-200 lines (notify via Telegram)
    - Multiple file changes
    - Schema migrations

    LOW RISK:
    - <100 lines changed
    - Within allowed_paths
    - Clearly meets deliverables
    - No side effects
    """

def _check_goal_alignment(
    self,
    fix_strategy: FixStrategy,
    deliverables: List[str],
    acceptance_criteria: List[str]
) -> GoalAlignment:
    """
    Verify fix advances toward goals:
    - Does it create/modify required deliverables?
    - Will it pass acceptance criteria?
    - Does it introduce unrelated changes?
    """
```

**Decision Types**:

```python
class DecisionType(Enum):
    CLEAR_FIX = "clear_fix"           # Low risk, goal-aligned, auto-apply
    NEED_MORE_EVIDENCE = "need_more"  # Continue investigation
    AMBIGUOUS = "ambiguous"           # Multiple valid approaches, ask human
    RISKY = "risky"                   # High risk, block for approval
```

---

### 5.3 DecisionExecutor

**Location**: `src/autopack/diagnostics/decision_executor.py`

**Responsibilities**:
- Execute CLEAR_FIX decisions with full safety net
- Create git save points before changes
- Apply patches/fixes
- Validate deliverables
- Run acceptance tests
- Auto-rollback if validation or tests fail
- Log decisions with full metadata

**Key Methods**:
```python
def execute_decision(
    self,
    decision: Decision,
    phase_spec: PhaseSpec
) -> ExecutionResult:
    """
    Execute a CLEAR_FIX decision with safety nets.

    Steps:
    1. Create git save point: save-before-fix-{phase_id}-{timestamp}
    2. Apply patch/fix
    3. Validate deliverables (expected files created)
    4. Run acceptance tests
    5. If failure: auto-rollback to save point
    6. If success: commit with decision metadata
    7. Log decision to decision_log
    """

def _create_save_point(self, phase_id: str) -> str:
    """Create git tag for rollback capability."""

def _validate_deliverables(
    self,
    patch: str,
    deliverables: List[str]
) -> ValidationResult:
    """Use existing DeliverableValidator."""

def _run_acceptance_tests(
    self,
    acceptance_criteria: List[str]
) -> TestResult:
    """Execute acceptance tests from phase spec."""

def _rollback(self, save_point: str) -> None:
    """Rollback to save point on failure."""

def _log_decision_with_metadata(
    self,
    decision: Decision,
    execution_result: ExecutionResult
) -> None:
    """
    Log to decision_log with full context:
    - trigger, choice, rationale
    - alternatives_considered
    - risk_assessment
    - files_modified, net_deletion
    - deliverables_met
    - acceptance_criteria_passed
    - safety_net (git tag)
    - timestamp
    """
```

---

## 6. Integration with Existing Systems

### 6.1 Wire into AutonomousExecutor

**File**: `src/autopack/autonomous_executor.py`

**Current Flow** (BUILD-112):
```python
def _handle_phase_failure(self, phase_id, error_context):
    # Run diagnostics (single round)
    outcome = self.diagnostics_agent.run_diagnostics(
        failure_class=error_context['failure_class'],
        context=error_context,
        phase_id=phase_id
    )

    # Generate handoff bundle (always escalate to human)
    handoff = self.handoff_bundler.create_bundle(outcome)

    # Human intervention required
    return "needs_human_intervention"
```

**New Flow** (BUILD-113):
```python
def _handle_phase_failure(self, phase_id, error_context):
    # Get phase spec for goal awareness
    phase_spec = self._get_phase_spec(phase_id)

    # Iterative investigation with goal-aware decisions
    investigation = self.iterative_investigator.investigate_and_resolve(
        failure_context=error_context,
        phase_spec=phase_spec
    )

    if investigation.decision.type == DecisionType.CLEAR_FIX:
        # Auto-apply fix with safety net
        result = self.decision_executor.execute_decision(
            decision=investigation.decision,
            phase_spec=phase_spec
        )

        if result.success:
            return "fixed_autonomously"
        else:
            # Rollback happened, escalate
            handoff = self.handoff_bundler.create_bundle(investigation)
            return "needs_human_intervention"

    elif investigation.decision.type in [DecisionType.RISKY, DecisionType.AMBIGUOUS]:
        # Escalate to human with full context
        handoff = self.handoff_bundler.create_bundle(investigation)

        # Notify via Telegram if configured
        if investigation.decision.risk_level == RiskLevel.HIGH:
            self.telegram_notifier.send_approval_request(
                phase_id=phase_id,
                decision=investigation.decision
            )

        return "needs_human_intervention"
```

### 6.2 Use Existing Safeguards

**Deletion Safeguards** (BUILD-107):
- `net_deletion` calculation already implemented
- Thresholds: <100 (auto), 100-200 (notify), >200 (block)
- Git save points before large deletions

**Telegram Notifications** (BUILD-108):
- `TelegramNotifier.send_approval_request()` for high-risk decisions
- `TelegramNotifier.send_completion_notice()` for autonomous fixes

**Decision Logging**:
- `MemoryService.write_decision_log()` already exists
- Enhanced with alternatives, risk assessment, audit trail

**Deliverables Validation**:
- `DeliverableValidator` already validates patches against deliverables
- Used in decision execution flow

---

## 7. Data Models

### 7.1 PhaseSpec

```python
@dataclass
class PhaseSpec:
    """Phase specification from requirements YAML."""
    phase_id: str
    deliverables: List[str]  # Files that must be created/modified
    acceptance_criteria: List[str]  # Tests that must pass
    allowed_paths: List[str]  # Safe modification zones
    protected_paths: List[str]  # Cannot be touched
    complexity: str  # low, medium, high
    category: str  # feature, bugfix, refactor, etc.
```

### 7.2 EvidenceGap

```python
@dataclass
class EvidenceGap:
    """Missing evidence identified during investigation."""
    gap_type: str  # "missing_file", "missing_command_output", "missing_test_output"
    description: str  # Human-readable description
    priority: int  # 1 (critical), 2 (high), 3 (medium)
    probe_suggestion: Optional[ProbeCommand]  # Suggested probe to fill gap
```

### 7.3 Decision

```python
@dataclass
class Decision:
    """Result of goal-aware decision making."""
    type: DecisionType  # CLEAR_FIX, NEED_MORE_EVIDENCE, AMBIGUOUS, RISKY
    fix_strategy: str  # Description of fix approach
    rationale: str  # Why this decision was made
    alternatives_considered: List[str]  # Other options and why rejected
    risk_level: RiskLevel  # LOW, MEDIUM, HIGH
    deliverables_met: List[str]  # Which deliverables this satisfies
    files_modified: List[str]  # What files will change
    net_deletion: int  # Lines removed - lines added
    patch: Optional[str]  # Patch content if CLEAR_FIX
    questions_for_human: Optional[List[str]]  # If AMBIGUOUS
```

### 7.4 InvestigationResult

```python
@dataclass
class InvestigationResult:
    """Result of multi-round investigation."""
    decision: Decision
    evidence: Dict[str, Any]  # All collected evidence
    rounds: int  # Number of investigation rounds
    probes_executed: List[ProbeRunResult]  # All probes run
    timeline: List[str]  # Investigation timeline for audit
    total_time_seconds: float
```

---

## 8. Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)
**Tasks**:
- [ ] Create `src/autopack/diagnostics/iterative_investigator.py`
- [ ] Create `src/autopack/diagnostics/goal_aware_decision.py`
- [ ] Create `src/autopack/diagnostics/decision_executor.py`
- [ ] Add data models (PhaseSpec, EvidenceGap, Decision, etc.)
- [ ] Unit tests for core logic

**Acceptance Criteria**:
- IterativeInvestigator can run multi-round investigation
- GoalAwareDecisionMaker produces decisions with rationale
- DecisionExecutor creates save points and validates deliverables

### Phase 2: Integration (1-2 hours)
**Tasks**:
- [ ] Wire IterativeInvestigator into AutonomousExecutor
- [ ] Enhance decision logging with alternatives tracking
- [ ] Integrate with existing safeguards (deletion thresholds, Telegram)
- [ ] Add `--enable-autonomous-fixes` CLI flag (default: false for safety)

**Acceptance Criteria**:
- Executor uses iterative investigation on failures
- Low-risk fixes auto-apply with full audit trail
- High-risk decisions block and notify via Telegram

### Phase 3: Testing & Validation (1-2 hours)
**Tasks**:
- [ ] Create test scenarios (import errors, missing files, test failures)
- [ ] Validate goal alignment logic
- [ ] Verify rollback on test failure
- [ ] Test decision logging and audit trail
- [ ] Manual testing with real failure scenarios

**Acceptance Criteria**:
- Import errors auto-fixed autonomously
- Large deletions block for approval
- All decisions logged with rationale and alternatives
- Rollback works correctly on test failures

### Phase 4: Documentation (30 min)
**Tasks**:
- [ ] Update README.md with BUILD-113 overview
- [ ] Update BUILD_HISTORY.md
- [ ] Update PROJECT_INDEX.json
- [ ] Create user guide for reviewing decision logs

**Acceptance Criteria**:
- All SOT files updated
- Clear documentation for operators

---

## 9. Success Metrics

### Quantitative:
- **Autonomous Fix Rate**: % of failures resolved without human intervention
  - Target: 40-60% for low-complexity failures
- **Investigation Rounds**: Average number of rounds to decision
  - Target: 2-3 rounds average
- **False Positive Rate**: % of auto-fixes that break tests
  - Target: <5% (rollback mechanism should catch)
- **Decision Log Completeness**: % of decisions with rationale + alternatives
  - Target: 100%

### Qualitative:
- **Audit Trail Quality**: Can human understand why decision was made?
- **Goal Alignment**: Do autonomous fixes actually meet deliverables?
- **Risk Assessment Accuracy**: Are low-risk fixes actually safe?
- **Human Review Efficiency**: Easier to review decision logs than investigate from scratch?

---

## 10. Risk Mitigation

### Risk 1: Over-Confidence in Auto-Fixes
**Mitigation**:
- Conservative risk assessment (prefer escalation over bad fix)
- Automatic rollback on test failure
- CLI flag `--enable-autonomous-fixes` (default: false initially)

### Risk 2: Investigation Loops
**Mitigation**:
- Hard cap: max 5 investigation rounds
- Escalate if no progress after 3 rounds

### Risk 3: Poor Goal Alignment
**Mitigation**:
- Strict deliverables validation (existing system)
- Acceptance test gating (must pass)
- Decision logging for human review

### Risk 4: Token Blowup from Multiple Rounds
**Mitigation**:
- Max 3 probes per round
- Evidence compression and prioritization
- Reuse existing evidence across rounds (no redundant collection)

---

## 11. Rollout Plan

### Week 1: Build + Internal Testing
- Implement Phase 1-3
- Test with synthetic failures (import errors, missing files)
- Validate safety nets (rollback, save points)

### Week 2: Gradual Rollout
- Enable `--enable-autonomous-fixes` for low-complexity phases only
- Monitor decision logs and audit trails
- Collect metrics (fix rate, rounds, false positives)

### Week 3: Refinement
- Tune risk assessment thresholds based on data
- Expand to medium-complexity phases
- Add more sophisticated goal alignment heuristics

---

## 12. Future Enhancements (Beyond BUILD-113)

### BUILD-114: Learning from Decisions
- Analyze decision logs to improve future decisions
- Pattern recognition: "Similar failures → similar fixes"
- Confidence scoring based on historical success rate

### BUILD-115: Strategic Human Consultation
- For AMBIGUOUS decisions, ask targeted questions
- "Should I refactor module A or just fix the import?"
- Dashboard UI for strategic decisions (not mechanical data)

### BUILD-116: Cross-Phase Learning
- Share successful fix patterns across phases
- Build up "fix library" for common failures
- Reduce investigation rounds through pattern matching

---

## 13. Dependencies

### Required (Existing):
- ✅ DiagnosticsAgent (BUILD-112)
- ✅ Deep Retrieval (BUILD-112)
- ✅ HandoffBundler (BUILD-112)
- ✅ Deletion Safeguards (BUILD-107)
- ✅ Telegram Notifications (BUILD-108)
- ✅ Deliverables Validator
- ✅ Decision Logging (MemoryService)

### New (BUILD-113):
- IterativeInvestigator
- GoalAwareDecisionMaker
- DecisionExecutor
- Enhanced decision logging with alternatives

---

## 14. Testing Strategy

### Unit Tests:
- `test_iterative_investigator.py`: Multi-round logic, gap analysis
- `test_goal_aware_decision.py`: Risk assessment, goal alignment
- `test_decision_executor.py`: Save points, rollback, validation

### Integration Tests:
- End-to-end: failure → investigation → autonomous fix
- Rollback scenarios: fix fails tests → auto-rollback
- Escalation scenarios: risky fix → block → Telegram notify

### Manual Testing Scenarios:
1. **Import Error**: Missing import in `__init__.py`
   - Expected: Auto-fixed (add import statement)
2. **Large Deletion**: Delete >200 lines
   - Expected: Blocked, Telegram notification
3. **Protected Path**: Modify `src/autopack/database.py`
   - Expected: Blocked, escalate to human
4. **Ambiguous Failure**: Multiple possible root causes
   - Expected: Escalate with questions

---

## 15. Documentation Updates

### README.md
Add section:
```markdown
### Iterative Autonomous Investigation (BUILD-113)
Multi-round autonomous debugging that resolves failures without human intervention when safe:

**Key Features**:
- **Goal-Aware Decisions**: Uses deliverables + acceptance criteria to guide fixes
- **Multi-Round Investigation**: Iteratively collects evidence until root cause found
- **Autonomous Low-Risk Fixes**: Auto-applies fixes <100 lines with no side effects
- **Full Audit Trails**: All decisions logged with rationale and alternatives
- **Safety Nets**: Git save points, automatic rollback, risk-based gating

**Enable** (experimental):
```bash
python -m autopack.autonomous_executor \
  --run-id my-run \
  --enable-autonomous-fixes
```

**Review Decision Logs**:
```bash
# View autonomous decisions
cat .autonomous_runs/my-run/decision_log.json

# Each decision includes:
# - Rationale (why this fix?)
# - Alternatives considered
# - Risk assessment
# - Deliverables met
# - Files modified
# - Git save point for rollback
```
```

### BUILD_HISTORY.md
```markdown
## BUILD-113 | 2025-12-21 | Iterative Autonomous Investigation
**Type**: Enhancement
**Parity**: 90% → 95% (Cursor-level autonomous debugging)

Implemented multi-round autonomous investigation with goal-aware judgment:
- IterativeInvestigator for multi-round evidence collection
- GoalAwareDecisionMaker using deliverables + acceptance criteria
- DecisionExecutor with safety nets (save points, rollback)
- Enhanced decision logging with alternatives tracking
- Risk-based gating: LOW (auto), MEDIUM (notify), HIGH (block)

**Impact**: 40-60% of low-complexity failures now resolve autonomously with full audit trails.
```

---

## Appendix: Example Decision Log

```json
{
  "decision_id": "fix-research-tracer-bullet-20251221-164500",
  "trigger": "investigation_round_2",
  "phase_id": "research-tracer-bullet",
  "failure_class": "import_error",
  "decision_type": "CLEAR_FIX",

  "choice": "Add missing import to __init__.py",

  "rationale": "Phase deliverable requires working tracer_bullet module. Round 1 evidence showed TracerBullet class exists in tracer_bullet.py. Round 2 investigation revealed __init__.py missing import statement. Adding 'from .tracer_bullet import TracerBullet' meets deliverable (working module) with zero side effects. No code deletion, no protected paths touched, within allowed_paths.",

  "alternatives_considered": [
    {
      "option": "Refactor entire research module structure",
      "reason_rejected": "Too risky, out of scope for current phase, would touch multiple files and require extensive testing"
    },
    {
      "option": "Create new __init__.py file",
      "reason_rejected": "File already exists at src/autopack/research/__init__.py, only needs import addition"
    },
    {
      "option": "Add import statement (SELECTED)",
      "reason_selected": "Minimal change, goal-aligned, safe, clearly meets deliverable"
    }
  ],

  "risk_assessment": {
    "level": "LOW",
    "factors": {
      "net_deletion": -1,
      "files_modified": ["src/autopack/research/__init__.py"],
      "protected_paths_touched": false,
      "within_allowed_paths": true,
      "breaking_changes": false
    }
  },

  "goal_alignment": {
    "deliverables_met": [
      "src/autopack/research/tracer_bullet.py (working module)"
    ],
    "acceptance_criteria_passed": [
      "import works: from autopack.research import TracerBullet",
      "tests pass: pytest tests/test_tracer_bullet.py"
    ]
  },

  "execution": {
    "safety_net": "git tag save-before-fix-research-tracer-bullet-20251221-164500",
    "patch_applied": true,
    "deliverables_validated": true,
    "acceptance_tests_passed": true,
    "rollback_needed": false,
    "committed": true,
    "commit_sha": "abc123def456"
  },

  "investigation_timeline": [
    "Round 1: Initial diagnostics - found ImportError",
    "Round 1: Deep retrieval - no prior similar failures",
    "Gap Analysis: Missing file content for __init__.py",
    "Round 2: Read src/autopack/research/__init__.py",
    "Round 2: Confirmed TracerBullet import missing",
    "Decision: CLEAR_FIX - add import statement",
    "Execution: Created save point, applied fix, tests passed"
  ],

  "metadata": {
    "investigation_rounds": 2,
    "probes_executed": 8,
    "total_time_seconds": 45.3,
    "timestamp": "2025-12-21T16:45:00Z",
    "autopack_version": "0.1.0-build113"
  }
}
```

---

**END OF BUILD-113 DESIGN DOCUMENT**
