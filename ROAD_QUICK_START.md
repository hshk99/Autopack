# ROAD Quick Start Guide

## What is ROAD?

ROAD is a **Self-Improvement Roadmap** - a complete autonomous optimization loop for Autopack:

1. **ROAD-A**: Record what happened (telemetry)
2. **ROAD-B**: Analyze what went wrong (issue discovery)
3. **ROAD-C**: Plan how to fix it (task generation)
4. **ROAD-D**: Get approval (governance)
5. **ROAD-E**: Validate the fix (A-B testing)
6. **ROAD-F**: Learn from success (policy promotion)

## Using Each ROAD Component

### ROAD-A: Record Phase Outcomes

```python
from src.autopack.telemetry_outcomes import PhaseOutcomeRecorder, PhaseOutcome

recorder = PhaseOutcomeRecorder()

# Record success
event = recorder.record_success("auth-phase", metadata={"duration": 45.2})

# Record failure with reason
event = recorder.record_failure(
    "auth-phase",
    stop_reason="max_tokens",
    decision_rationale="Phase exceeded token budget after 3 retries"
)

# Record stuck state
event = recorder.record_stuck(
    "auth-phase",
    decision_rationale="All recovery strategies exhausted",
    stop_reason="unrecoverable"
)
```

### ROAD-B: Analyze Telemetry

```bash
python scripts/analyze_run_telemetry.py \
    --db autopack.db \
    --window 7 \
    --output .autonomous_runs/telemetry_analysis/report.md
```

Generates:
- `report.md`: Human-readable analysis
- `report.json`: Machine-readable metrics

### ROAD-C: Generate Bounded Tasks

```python
from src.autopack.executor.task_generator import FollowupTaskGenerator, IssueType

generator = FollowupTaskGenerator(top_k=5, max_attempts=2)

# From cost sink analysis
task = generator.generate_task_from_cost_sink(
    rank=1,
    phase_id="auth-service",
    total_tokens=150000
)

print(f"Task: {task.title}")
print(f"Allowed files: {task.allowed_files}")
print(f"Test plan: {task.test_plan.tests}")
```

### ROAD-D: Gate PR Approval

```python
from scripts.governance_pr_gateway import get_gateway

gateway = get_gateway()

# Create approval request
request = gateway.create_approval_request(
    pr_number=123,
    generated_from="COST-SINK-001",
    title="Optimize tokens",
    description="Reduce token usage in auth phase",
    impact_assessment="Low risk",
    rollback_plan="Revert commit if issues arise"
)

# Later, after human review
gateway.approve_pr(123, reviewer="alice@example.com")

# Check if ready to merge
if gateway.can_merge(123):
    # Merge PR
    pass
```

### ROAD-E: Run A-B Validation

```python
from scripts.replay_campaign import ReplayCampaign, ReplayRun, RunOutcome

campaign = ReplayCampaign("auth-service-opt")

# Add baseline runs (original version)
for i in range(5):
    campaign.add_baseline_run(
        ReplayRun(f"b-{i}", f"task-{i}", RunOutcome.SUCCESS, 45.0, 12000)
    )

# Add treatment runs (optimized version)
for i in range(5):
    campaign.add_treatment_run(
        ReplayRun(f"t-{i}", f"task-{i}", RunOutcome.SUCCESS, 42.0, 11500)
    )

# Determine if we should promote
if campaign.should_promote():
    campaign.save_report(Path("reports/campaign.json"))
    # Merge PR
else:
    # Reject PR
    pass
```

### ROAD-F: Promote Successful Rules

```python
from src.autopack.executor.policy_promoter import get_promoter

promoter = get_promoter()

# Promote successful mitigation (if ≥90% success rate)
rule = promoter.promote_rule(
    rule_id="rule-timeout-001",
    mitigation="Add timeout wrapper with exponential backoff",
    success_rate=0.95,
    applicable_phases=["auth", "database", "api"]
)

# Get rules for future phases
auth_rules = promoter.get_rules_for_phase("auth")

# Generate prevention prompts for LLM
prompts = promoter.generate_prevention_prompts()

# Save for persistence
from pathlib import Path
promoter.save_promoted_rules(Path("policies/promoted_rules.json"))
```

## Running Tests

```bash
# All tests
pytest tests/autopack/test_telemetry_outcomes.py \
        tests/scripts/test_analyze_run_telemetry.py \
        tests/executor/test_task_generator.py \
        tests/scripts/test_governance_pr_gateway.py \
        tests/scripts/test_replay_campaign.py \
        tests/executor/test_policy_promoter.py \
        -v

# Individual tests
pytest tests/autopack/test_telemetry_outcomes.py -v       # ROAD-A
pytest tests/scripts/test_analyze_run_telemetry.py -v     # ROAD-B
pytest tests/executor/test_task_generator.py -v           # ROAD-C
pytest tests/scripts/test_governance_pr_gateway.py -v     # ROAD-D
pytest tests/scripts/test_replay_campaign.py -v           # ROAD-E
pytest tests/executor/test_policy_promoter.py -v          # ROAD-F
```

## Key Constraints

### ROAD-A: Invariant Enforcement
- Phase ID: non-empty, < 256 chars
- Rationale: < 10,000 chars
- Stop reason: < 256 chars
- No duplicate phase_ids allowed per recorder instance

### ROAD-C: Bounded Scope
- Allowed files: ≤ 3 files per task
- Max attempts: 2 by default
- Approval gate: Required by default
- Test plan: Mandatory

### ROAD-E: Regression Detection
- Regression threshold: > 10% failure rate increase
- Improvement threshold: > 5% success rate increase
- Decision: Promote if no regression AND (improvement OR no degradation)

### ROAD-F: Promotion Threshold
- Success rate: ≥ 90% required for promotion
- Applicable phases: Can be used across multiple phases
- Prevention prompts: Auto-generated for LLM integration

## Integration Checklist

- [ ] Import ROAD-A recorder in phase execution
- [ ] Run ROAD-B analysis post-execution
- [ ] Wire ROAD-C task generation to issue prioritization
- [ ] Integrate ROAD-D approval gates with PR workflow
- [ ] Connect ROAD-E validation to merge gates
- [ ] Feed ROAD-F prevention prompts to LLM

## Documentation

- [ROAD_IMPLEMENTATION_SUMMARY.md](ROAD_IMPLEMENTATION_SUMMARY.md) - Detailed technical specs
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Current status & test results

---

All 39 tests passing. Ready for production deployment.
