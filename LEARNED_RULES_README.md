# Learned Rules System (Stage 0A + 0B)

## Overview

The Learned Rules system enables Autopack to automatically learn from past mistakes and prevent their recurrence in future autonomous builds. This implements the consensus design from `FINAL_LEARNED_RULES_DECISION.md`.

**Core Benefit**: Never repeat the same mistake twice. Rules discovered during troubleshooting in Run 1 automatically prevent issues in Run 2, Run 3, etc.

## Architecture

### Stage 0A: Within-Run Hints

**Purpose**: Help later phases in the same run avoid mistakes from earlier phases.

**Lifecycle**:
1. Phase completes successfully after resolving issues
2. System records a "hint" capturing what went wrong and how it was fixed
3. Later phases in the same run receive relevant hints via prompt injection
4. Hints stored in `.autonomous_runs/runs/{run_id}/run_rule_hints.json`

**Example**:
```
Run 1, Phase 3: Missing type hints → mypy fails → Builder adds type hints → succeeds
└─> Hint recorded: "Ensure all functions have type annotations"

Run 1, Phase 7: Receives hint from Phase 3 → Builder adds type hints from start → succeeds ✅
```

### Stage 0B: Cross-Run Persistent Rules

**Purpose**: Help all future runs avoid mistakes discovered in past runs.

**Lifecycle**:
1. Run completes → System analyzes all hints from that run
2. Recurring patterns (2+ occurrences) promoted to persistent project rules
3. Future runs load project rules before starting
4. All phases receive relevant rules via prompt injection
5. Rules stored in `.autonomous_runs/{project_id}/project_learned_rules.json`

**Example**:
```
Run 1: Hit "missing type hints" issue 3 times → Rule promoted
Run 2: Rule loaded before run starts → All phases follow rule → No type hints issues ✅
Run 3+: Same rule continues preventing issues ✅
```

## Data Schema

### RunRuleHint (Stage 0A)

```python
@dataclass
class RunRuleHint:
    run_id: str                    # "auto-build-001"
    phase_index: int               # 3 (for ordering)
    phase_id: str                  # "P1.3"
    tier_id: Optional[str]         # "T1"
    task_category: Optional[str]   # "feature_scaffolding"
    scope_paths: List[str]         # ["auth.py", "auth_test.py"]
    source_issue_keys: List[str]   # ["missing_type_hints_auth_py"]
    hint_text: str                 # "Resolved missing_type_hints_auth_py..."
    created_at: str                # ISO datetime
```

### LearnedRule (Stage 0B)

```python
@dataclass
class LearnedRule:
    rule_id: str                   # "feature_scaffolding.missing_type_hints"
    task_category: str             # "feature_scaffolding"
    scope_pattern: Optional[str]   # "*.py" or None for global
    constraint: str                # "Ensure all functions have type annotations"
    source_hint_ids: List[str]     # ["run1:P1.3", "run1:P2.1"]
    promotion_count: int           # Number of times promoted (confidence)
    first_seen: str                # ISO datetime
    last_seen: str                 # ISO datetime
    status: str                    # "active" | "deprecated"
```

## File Structure

```
.autonomous_runs/
├── {project_id}/                          # e.g., "Autopack"
│   └── project_learned_rules.json        # Stage 0B: Persistent cross-run rules
│       {
│         "project_id": "Autopack",
│         "version": "1.0",
│         "rule_count": 5,
│         "rules": [
│           {
│             "rule_id": "feature_scaffolding.missing_type_hints",
│             "constraint": "Ensure all functions have type annotations",
│             "promotion_count": 3,
│             ...
│           }
│         ]
│       }
│
└── runs/{run_id}/                         # e.g., "auto-build-001"
    └── run_rule_hints.json                # Stage 0A: Within-run hints
        {
          "run_id": "auto-build-001",
          "hints": [
            {
              "phase_id": "P1.3",
              "hint_text": "Resolved missing_type_hints_auth_py...",
              "scope_paths": ["auth.py"],
              ...
            }
          ]
        }
```

## Integration Points

### 1. Supervisor Initialization

```python
supervisor = Supervisor(
    api_url="http://localhost:8000",
    project_id="MyProject"  # ← NEW: For multi-project isolation
)
```

### 2. Run Start (Load Rules)

```python
def run_autonomous_build(self, run_id, tiers, phases):
    # Stage 0B: Load persistent project rules
    self.project_rules = load_project_learned_rules(self.project_id)
    self.run_rules_snapshot = self.project_rules.copy()  # Freeze for determinism

    # ... execute phases ...
```

### 3. Phase Execution (Inject Rules/Hints)

```python
def execute_phase(self, run_id, phase):
    # Stage 0B: Get relevant project rules
    relevant_project_rules = get_relevant_rules_for_phase(
        self.run_rules_snapshot, phase, max_rules=10
    )

    # Stage 0A: Get relevant run hints from earlier phases
    relevant_run_hints = get_relevant_hints_for_phase(
        run_id, phase, max_hints=5
    )

    # Pass to Builder and Auditor
    builder_result = self.builder.execute_phase(
        phase_spec=phase_spec,
        project_rules=relevant_project_rules,  # ← NEW
        run_hints=relevant_run_hints           # ← NEW
    )

    auditor_result = self.auditor.review_patch(
        patch_content=builder_result.patch_content,
        phase_spec=phase_spec,
        project_rules=relevant_project_rules,  # ← NEW
        run_hints=relevant_run_hints           # ← NEW
    )
```

### 4. Phase Completion (Record Hint)

```python
if auditor_result.approved:
    # Stage 0A: Record hint if issues were resolved
    hint = record_run_rule_hint(
        run_id=run_id,
        phase=phase,
        issues_before=issues_before,  # From CI/test results
        issues_after=issues_after,
        context={"file_paths": []}
    )
```

### 5. Run End (Promote Rules)

```python
def run_autonomous_build(self, run_id, tiers, phases):
    # ... execute phases ...

    # Stage 0B: Promote hints to persistent rules
    promoted_count = promote_hints_to_rules(run_id, self.project_id)
    # Hints appearing 2+ times in this run → promoted to persistent rules
```

## Prompt Injection Format

### Builder/Auditor Receive:

**Project Rules (Stage 0B)**:
```
## Project Learned Rules (from past runs)

IMPORTANT: Follow these rules learned from past experience:

1. **feature_scaffolding.missing_type_hints**: Ensure all functions have type annotations
2. **feature_scaffolding.placeholder_code**: Never leave placeholder code like 'TODO' or 'INSERT CODE HERE'
3. **test_scaffolding.missing_tests**: Every feature must have corresponding unit tests
```

**Run Hints (Stage 0A)**:
```
## Lessons from Earlier Phases (this run only)

Do not repeat these mistakes:
1. Resolved missing_type_hints_auth_py in auth.py - ensure all functions have type annotations
2. Resolved placeholder_code_handler_py - removed placeholder code in handler.py
```

## Rule Promotion Logic

**Threshold**: Hints appearing **2+ times** in the same run are promoted to persistent rules.

**Why 2+?**: Balances:
- Too low (1): Too many noisy rules
- Too high (3+): Miss important patterns
- Just right (2): Captures recurring issues without noise

**Promotion Process**:
1. Load all hints from completed run
2. Group hints by pattern (extracted from issue_key + task_category)
3. For each pattern with 2+ occurrences:
   - Check if rule already exists (update promotion_count)
   - Else create new persistent rule
4. Save updated rules to project_learned_rules.json

**Pattern Extraction Example**:
```
"missing_type_hints_auth_py" → "missing_type_hints"
"missing_type_hints_models_py" → "missing_type_hints"
└─> Same pattern, count = 2 → PROMOTE ✅
```

## Relevance Filtering

### Hints: Relevant to Phase If...
- Same `task_category` (e.g., both "feature_scaffolding")
- From earlier phase in same run (phase_index < current)
- Limit: 5 most recent matching hints

### Rules: Relevant to Phase If...
- Same `task_category`
- Scope pattern matches (if specified)
- Limit: 10 highest promotion_count rules (highest confidence first)

## V7 Compliance

### Deterministic Runs ✅
- Rules loaded **before** run starts
- Rules frozen in `run_rules_snapshot` for entire run
- No mid-run changes to strategy or budgets

### Zero-Intervention ✅
- Fully automatic: No manual rule editing required
- Prompt-only guidance: Rules don't alter state machine
- Silent operation: Runs continue even if rules fail to load

### No Re-Planning ✅
- Rules don't trigger mid-run phase changes
- No PlanValidator (future consideration)
- Strategy frozen at run start

## Usage

### Running Autonomous Build with Learned Rules

```python
from integrations.supervisor import Supervisor

# Initialize with project_id
supervisor = Supervisor(
    api_url="http://localhost:8000",
    project_id="MyProject"
)

# Run build (rules automatically loaded/promoted)
result = supervisor.run_autonomous_build(
    run_id="auto-build-001",
    tiers=[...],
    phases=[...]
)

print(f"Rules promoted: {result['rules_promoted']}")
```

### Analyzing Learned Rules

```bash
# View all projects with rules
python scripts/analyze_learned_rules.py --all-projects

# View rules for specific project
python scripts/analyze_learned_rules.py --project-id Autopack

# View hints from specific run
python scripts/analyze_learned_rules.py --run-id auto-build-001

# Save analysis to JSON
python scripts/analyze_learned_rules.py --all-projects --output-json analysis.json
```

### Manual Rule Management (Advanced)

```python
from src.autopack.learned_rules import (
    load_project_learned_rules,
    LearnedRule
)

# Load existing rules
rules = load_project_learned_rules("MyProject")

# Manually deprecate a rule (rare)
for rule in rules:
    if rule.rule_id == "obsolete.rule":
        rule.status = "deprecated"

# (Saving handled automatically by promote_hints_to_rules)
```

## Testing

### Unit Tests

```bash
# Full pytest suite (requires env setup)
pytest tests/test_learned_rules.py -v

# Standalone test runner (bypasses conftest)
python test_learned_rules_standalone.py
```

### Integration Tests

```bash
# Run end-to-end with real Supervisor
python integrations/supervisor.py
# Check .autonomous_runs/ for generated hints and rules
```

## Common Patterns

### Pattern: Missing Type Hints
```json
{
  "rule_id": "feature_scaffolding.missing_type_hints",
  "constraint": "Resolved missing_type_hints in affected files - ensure all functions have type annotations",
  "promotion_count": 5
}
```

### Pattern: Placeholder Code
```json
{
  "rule_id": "feature_scaffolding.placeholder_code",
  "constraint": "Resolved placeholder_code - removed placeholder code in affected files",
  "promotion_count": 3
}
```

### Pattern: Missing Tests
```json
{
  "rule_id": "test_scaffolding.missing_tests",
  "constraint": "Resolved missing_tests - added tests for affected files",
  "promotion_count": 4
}
```

### Pattern: Import Errors
```json
{
  "rule_id": "feature_scaffolding.import_error",
  "constraint": "Resolved import_error - fixed imports in affected files",
  "promotion_count": 2
}
```

## Troubleshooting

### No Hints Recorded

**Symptoms**: `.autonomous_runs/runs/{run_id}/run_rule_hints.json` empty or missing

**Causes**:
1. No issues resolved in phases (all phases succeeded first try)
2. `issues_before` and `issues_after` both empty
3. No `scope_paths` in context (hints require file paths)

**Solution**: Check that CI/test results are being tracked properly

### No Rules Promoted

**Symptoms**: `.autonomous_runs/{project_id}/project_learned_rules.json` empty or not updated

**Causes**:
1. No recurring patterns (all hints unique)
2. Patterns appear only once (need 2+ for promotion)
3. Promotion logic not running at run end

**Solution**: Check `result['rules_promoted']` after run, ensure `promote_hints_to_rules()` called

### Rules Not Injected into Prompts

**Symptoms**: Builder/Auditor still making same mistakes despite rules

**Causes**:
1. Wrong `project_id` (rules exist for different project)
2. Relevance filtering excludes rules (wrong task_category)
3. Prompt injection not working (check `format_rules_for_prompt()`)

**Solution**: Check logs for "📚 Loading learned rules for phase..." message

### Permission Errors

**Symptoms**: Cannot write to `.autonomous_runs/`

**Causes**:
1. Directory doesn't exist
2. Insufficient write permissions
3. File locked by another process

**Solution**: Ensure `.autonomous_runs/` exists with write permissions

## Performance Considerations

### Disk I/O
- Hints: 1 read per phase + 1 write on phase complete (~10 KB/hint)
- Rules: 1 read at run start + 1 write at run end (~50 KB typical)
- Impact: Negligible (< 1 ms per operation)

### Memory
- Rules snapshot: ~1-5 MB typical (1000 rules)
- Hints per run: ~50-200 KB typical (20-100 hints)
- Impact: Negligible

### LLM Token Overhead
- Rules: ~50-500 tokens (10 rules × 50 tokens avg)
- Hints: ~25-125 tokens (5 hints × 25 tokens avg)
- Total: ~75-625 tokens per phase (~0.5-2% of typical budget)

## Future Enhancements (Not in Stage 0)

### Stage 1: Advanced Features
- LLM-based hint generation (vs templates)
- PlanValidator for mid-run plan revision
- Scope pattern matching (file globs)
- Cross-project rule sharing
- Rule deprecation logic (auto-expire old rules)
- Confidence scoring (beyond promotion_count)

### Stage 2: ML-Based Learning
- Pattern clustering (group similar rules)
- Anomaly detection (flag unusual patterns)
- Predictive hints (suggest rules before issues occur)
- Adaptive promotion threshold (learn optimal threshold)

## References

- `FINAL_LEARNED_RULES_DECISION.md` - Consensus design document
- `LEARNED_RULES_ANALYSIS.md` - Original proposal and gap analysis
- `GPT_RESPONSE_EVALUATION.md` - Analysis of GPT architect's recommendation
- `src/autopack/learned_rules.py` - Core implementation (600+ lines)
- `integrations/supervisor.py` - Integration with autonomous builds
- `src/autopack/openai_clients.py` - LLM prompt injection

## Support

For issues or questions:
1. Check this README first
2. Review `LEARNED_RULES_ANALYSIS.md` for design rationale
3. Run analysis script to inspect current state
4. Check logs for "Supervisor" or "learned rules" messages
5. File issue in GitHub repo

---

**Status**: ✅ Stage 0A + 0B fully implemented and tested

**Implementation Date**: 2025-11-24

**Authors**: Claude Code + User + GPT Architect Consensus

**License**: Same as Autopack project
