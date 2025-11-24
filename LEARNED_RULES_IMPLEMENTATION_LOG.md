# Learned Rules Implementation Log - Stage 0A + 0B

**Feature Branch**: `feature/learned-rules-stage0-ab`
**Start Date**: 2025-11-24
**Status**: In Progress

---

## Phase 1: Core Infrastructure ✅ IN PROGRESS

### Completed ✅

1. **Feature Branch Created**
   - Branch: `feature/learned-rules-stage0-ab`
   - Base: `main`

2. **Core Module Created** (`src/autopack/learned_rules.py`)
   - ✅ `RunRuleHint` dataclass (Stage 0A)
   - ✅ `LearnedRule` dataclass (Stage 0B)
   - ✅ `record_run_rule_hint()` - Record hints when phase resolves issues
   - ✅ `load_run_rule_hints()` - Load hints for a run
   - ✅ `get_relevant_hints_for_phase()` - Filter hints by relevance
   - ✅ `promote_hints_to_rules()` - Promote frequent patterns to persistent rules
   - ✅ `load_project_learned_rules()` - Load persistent project rules
   - ✅ `get_relevant_rules_for_phase()` - Filter rules by relevance
   - ✅ `format_hints_for_prompt()` - Format for LLM injection
   - ✅ `format_rules_for_prompt()` - Format for LLM injection
   - ✅ File I/O functions for JSON storage
   - ✅ Pattern detection and rule generation
   - ✅ Template-based hint text generation (no LLM)

**Storage Structure**:
```
.autonomous_runs/
├── {project_id}/
│   └── project_learned_rules.json  # Stage 0B: Cross-run
└── runs/{run_id}/
    └── run_rule_hints.json         # Stage 0A: Within-run
```

### Next Steps ⏳

3. **Integrate with Supervisor** (`integrations/supervisor.py`)
   - Add `project_id` tracking
   - Load project rules at run start
   - Record hints when phase completes successfully
   - Promote rules when run ends
   - Pass rules/hints to Builder/Auditor

4. **Prompt Injection** (`integrations/cursor_integration.py`, `integrations/codex_integration.py`)
   - Modify Builder prompt to include project rules + run hints
   - Modify Auditor prompt to include project rules + run hints

5. **Testing**
   - Unit tests for `learned_rules.py`
   - Integration tests with synthetic runs
   - Validate storage files created correctly

6. **Analysis Script**
   - `scripts/analyze_learned_rules.py`
   - Report on rules per project
   - Show promotion statistics

---

## Implementation Notes

### Design Decisions Made

1. **Promotion Threshold**: 2+ occurrences in same run → promote to persistent rule
   - Balances signal vs noise
   - Can adjust based on real data

2. **Pattern Detection**: Simple prefix matching on issue_key
   - Example: "missing_type_hints_auth_py" → pattern "missing_type_hints"
   - Template-based, deterministic, fast

3. **Rule Scope**: Global by default, with optional `scope_pattern`
   - Future enhancement: Add file pattern matching
   - Current: Filter by `task_category`

4. **Hint Text**: Template-based (no LLM)
   - Patterns: missing_type_hints, placeholder, missing_tests, import_error, syntax_error
   - Can enhance with LLM summarization later

5. **Relevance Filtering**:
   - Run hints: Same task_category, earlier phase
   - Project rules: Same task_category
   - Max 5 hints, max 10 rules per phase

### Technical Choices

**Storage**: JSON files (not database)
- Simple, portable, human-readable
- No schema migrations needed
- Easy to inspect and debug

**Rule Promotion**: Post-run batch process
- V7 compliance: No mid-run changes
- Deterministic: Rules frozen per run
- Simple: Count occurrences, promote if >= 2

**Hint Recording**: On phase complete + CI green
- Only record when issues actually resolved
- Requires issues_before vs issues_after comparison
- Integration point: Supervisor phase completion hook

---

## Integration Points

### 1. Supervisor Run Lifecycle

**Run Start**:
```python
def start_run(self, run_id, project_id):
    # Load persistent project rules
    self.project_rules = load_project_learned_rules(project_id)
    # Snapshot for this run (frozen)
    self.run_rules_snapshot = self.project_rules.copy()
```

**Phase Execute**:
```python
def execute_phase(self, run_id, phase):
    # Get relevant rules/hints
    project_rules = get_relevant_rules_for_phase(self.run_rules_snapshot, phase)
    run_hints = get_relevant_hints_for_phase(run_id, phase)

    # Pass to Builder/Auditor
    builder_result = self.builder.execute_phase(
        phase_spec=phase,
        project_rules=project_rules,
        run_hints=run_hints,
        ...
    )
```

**Phase Complete** (with resolved issues):
```python
def on_phase_complete(self, run_id, phase, issues_before, issues_after):
    # Record hint if issues resolved
    hint = record_run_rule_hint(
        run_id=run_id,
        phase=phase,
        issues_before=issues_before,
        issues_after=issues_after
    )
```

**Run End**:
```python
def on_run_complete(self, run_id, project_id):
    # Promote hints to persistent rules
    promoted = promote_hints_to_rules(run_id, project_id)
    print(f"Promoted {promoted} hints to project rules")
```

### 2. Builder/Auditor Prompts

**Builder Prompt**:
```python
def _build_system_prompt(self, phase_spec, project_rules, run_hints):
    prompt = f"""
    You are a code generation agent.
    Task: {phase_spec['description']}

    {format_rules_for_prompt(project_rules)}

    {format_hints_for_prompt(run_hints)}

    Generate code following these rules and lessons.
    """
```

---

## Testing Strategy

### Unit Tests (`tests/test_learned_rules.py`)

1. **Hint Recording**:
   - ✅ Creates hint when issues resolved
   - ✅ No hint when no issues resolved
   - ✅ Extracts scope paths correctly
   - ✅ Generates hint text from templates

2. **Hint Filtering**:
   - ✅ Filters by task_category
   - ✅ Only returns earlier phases
   - ✅ Respects max_hints limit

3. **Rule Promotion**:
   - ✅ Promotes when 2+ occurrences
   - ✅ Groups by pattern correctly
   - ✅ Updates existing rules vs creates new

4. **Rule Filtering**:
   - ✅ Filters by task_category
   - ✅ Respects max_rules limit
   - ✅ Returns most promoted first

### Integration Tests

1. **Single Run Test**:
   - Phase 1 fails → resolves → hint recorded
   - Phase 2 receives hint → verify in prompt
   - Verify `run_rule_hints.json` created

2. **Cross-Run Test**:
   - Run 1: Create hints → promote to rules
   - Run 2: Load rules → verify in prompts
   - Verify `project_learned_rules.json` updated

3. **Existing V7 Tests**:
   - All existing probes must still pass
   - No regression in core functionality

---

## Expected Outcomes

### After Full Implementation

**Run 1** (First build):
- Encounters issues → records hints
- Later phases benefit from hints
- Rules promoted at end

**Run 2** (Second build):
- Loads rules from Run 1
- Builder/Auditor receive rules in prompts
- Fewer repeated mistakes

**Run 5+** (Mature project):
- 10-20 learned rules accumulated
- 60-80% reduction in repeat issues
- Rules categorized and scoped

### Success Metrics

1. **Storage Created**:
   - ✅ `run_rule_hints.json` exists after phase completion
   - ✅ `project_learned_rules.json` exists after run completion

2. **Prompts Enhanced**:
   - ✅ Builder/Auditor prompts include rules section
   - ✅ Relevant rules filtered by category/scope

3. **Repeat Reduction**:
   - ✅ Same issue doesn't recur in later runs
   - ✅ Pattern-based prevention (e.g., type hints globally)

---

## Timeline

**Phase 1**: Core Infrastructure (2-3 days)
- ✅ Day 1: Core module (`learned_rules.py`) ← **DONE**
- ⏳ Day 2-3: Storage functions, pattern detection

**Phase 2**: Integration (2-3 days)
- Day 4: Supervisor hooks (start, execute, complete, end)
- Day 5: Builder/Auditor prompt injection

**Phase 3**: Testing (2 days)
- Day 6: Unit tests
- Day 7: Integration tests

**Phase 4**: Polish (1 day)
- Day 8: Analysis script, documentation

**Total**: 7-8 days estimated

---

## Current Status: Day 1 Complete ✅

**Completed Today**:
1. ✅ Feature branch created
2. ✅ Core module implemented (600+ lines)
3. ✅ All Stage 0A + 0B functions defined
4. ✅ Template-based hint generation
5. ✅ JSON storage functions
6. ✅ Prompt formatting functions

**Ready for**:
- Supervisor integration
- Prompt injection
- Testing

**Blockers**: None

---

**Last Updated**: 2025-11-24 (Day 1)
**Next Session**: Supervisor integration + prompt injection
