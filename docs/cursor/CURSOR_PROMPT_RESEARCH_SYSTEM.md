# Cursor Prompt: Research System Implementation via Autopack

## Context

You are helping implement the **Universal Research & Marketing Intelligence System** for Autopack using autonomous execution. This system will gather and analyze data from GitHub, Reddit, and Web sources to produce evidence-based research reports with zero hallucinations.

## Implementation Plan Location

The complete implementation plan has been split into 8 autonomous execution chunks (YAML files):

**Location**: `C:\dev\Autopack\.autonomous_runs\file-organizer-app-v1\archive\research\active\requirements\`

**Files**:
- ✅ `chunk0-tracer-bullet.yaml` - Phase 0: Feasibility validation (READY)
- ✅ `chunk1a-foundation-orchestrator.yaml` - Phase 1A: Orchestrator + Evidence model (READY)
- ✅ `chunk1b-foundation-intent-discovery.yaml` - Phase 1B: Intent discovery + Source evaluation (READY)
- ✅ `chunk2a-gatherers-social.yaml` - Phase 2A: GitHub + Reddit gatherers (READY)
- ✅ `chunk2b-gatherers-web-compilation.yaml` - Phase 2B: Web scraper + Compilation (READY)
- ✅ `chunk3-meta-analysis.yaml` - Phase 3: Decision frameworks + Meta-auditor (READY)
- ✅ `chunk4-integration.yaml` - Phase 4: Autopack core integration (READY)
- ✅ `chunk5-testing-polish.yaml` - Phase 5: Testing + Polish (READY)

**Summary Document**: `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/ALL_CHUNKS_SUMMARY.md`

**Main Plan**: `.autonomous_runs/file-organizer-app-v1/archive/research/active/UNIFIED_RESEARCH_SYSTEM_IMPLEMENTATION_V2_REVISED.md`

## Your Task

Execute the Research System implementation using Autopack's autonomous executor, starting with **Chunk 0 (Tracer Bullet)**.

### Step 1: Create Run and Launch Executor

**SIMPLE METHOD** (Recommended - uses helper script):

```bash
cd c:/dev/Autopack

# Step 1a: Create run with Chunk 0 phase
PYTHONUTF8=1 PYTHONPATH=src python scripts/create_research_run.py chunk0-tracer-bullet

# Step 1b: Start API server (in separate terminal)
PYTHONUTF8=1 PYTHONPATH=src uvicorn autopack.main:app --reload --port 8000

# Step 1c: Launch autonomous executor
PYTHONUTF8=1 PYTHONPATH=src python -m autopack.autonomous_executor \
  --run-id research-system-v1 \
  --api-url http://localhost:8000
```

**ADVANCED METHOD** (Manual database creation):

<details>
<summary>Click to expand manual method</summary>

```bash
cd c:/dev/Autopack

# Create run and phase manually
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import Run, Phase, PhaseState, RunState
from datetime import datetime, timezone
import yaml

db = SessionLocal()
try:
    # Load YAML requirements
    with open('.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk0-tracer-bullet.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Create run
    run = Run(
        id='research-system-v1',
        state=RunState.RUN_CREATED,
        created_at=datetime.now(timezone.utc),
        run_scope={'allowed_paths': config.get('allowed_paths', [])},
        token_cap=200000
    )
    db.add(run)

    # Create phase from YAML
    phase = Phase(
        phase_id=config['phase_id'],
        run_id='research-system-v1',
        tier_id='tier-0',
        phase_index=0,
        name='Tracer Bullet',
        description=config['description'],
        state=PhaseState.QUEUED,
        task_category=config.get('task_category', 'research'),
        complexity=config.get('complexity', 'high'),
        builder_mode='structured_edit',
        scope=config
    )
    db.add(phase)

    db.commit()
    print('✅ Run created: research-system-v1')
except Exception as e:
    print(f'❌ Error: {e}')
    db.rollback()
finally:
    db.close()
"

# Then launch executor
PYTHONUTF8=1 PYTHONPATH=src python -m autopack.autonomous_executor \
  --run-id research-system-v1 \
  --api-url http://localhost:8000
```

</details>

**Note**: You may need to start the Autopack API server first:
```bash
# In a separate terminal
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src uvicorn autopack.main:app --reload --port 8000
```

### Step 2: Monitor Execution

Watch the execution logs in real-time:

```bash
# Monitor executor output (stdout)
# The executor will print progress to console

# OR: Check the run's log file if it creates one
tail -f .autonomous_runs/research-system-v1/executor.log

# Check phase status via API
curl http://localhost:8000/runs/research-system-v1 | python -m json.tool

# Or via database query
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import Phase

db = SessionLocal()
phase = db.query(Phase).filter_by(run_id='research-system-v1', phase_id='research-tracer-bullet').first()
if phase:
    print(f'Phase: {phase.phase_id}')
    print(f'State: {phase.state.value}')
    print(f'Attempts: {phase.builder_attempts}/{phase.auditor_attempts}')
    print(f'Tokens: {phase.tokens_used}')
else:
    print('Phase not found')
db.close()
"
```

### Step 3: Review Results

After Chunk 0 completes, review:
1. **Functionality**: Does the minimal pipeline work end-to-end?
2. **Test Results**: Did it process 10/10 test topics successfully?
3. **Evaluation Score**: Is the score ≥7.0/10?
4. **Factuality**: Is factuality ≥80%?
5. **Citation Validity**: Is citation validity ≥75%?

**CRITICAL**: Chunk 0 is a **GO/NO-GO decision point**. If it fails these criteria, STOP and analyze before proceeding.

### Step 4: Review and Decide Next Steps

After Chunk 0 completes, review the results manually:

```bash
# Check test results
cat .autonomous_runs/research-system-v1/ci/pytest_*.log

# Check code quality
ls -la src/autopack/research/

# Evaluate success criteria
# - Pipeline execution: 10/10 topics?
# - Evaluation score: ≥7.0/10?
# - Factuality: ≥80%?
# - Citation validity: ≥75%?
```

**Manual decision**: Based on your review:
- ✅ **If passing criteria**: Proceed to Chunk 1A (create new run with chunk1a YAML)
- ❌ **If failing criteria**: Analyze issues, fix, and re-run Chunk 0

**Note**: There is no automated review/approval command. You make the decision manually based on test results and quality assessment.

### Step 5: Proceed to Next Chunks

If Chunk 0 passes, continue with Chunks 1A through 5 using the same pattern.

---

## Critical Information: Recent Fixes & Known Issues

### ✅ RESOLVED ISSUES (Safe to Proceed)

#### 1. **DBG-009: Multiple Executor Instances** (FIXED: BUILD-048)
- **Issue**: Multiple executor instances running simultaneously caused token waste
- **Status**: ✅ Resolved
- **Fix**: Single-instance enforcement with PID-based locking
- **Validation**: No duplicate executors detected in recent runs
- **No action needed**: Fix is already deployed

#### 2. **DBG-008: API Contract Mismatch** (FIXED)
- **Issue**: Builder result submission payload format mismatch
- **Status**: ✅ Resolved
- **Fix**: Corrected payload structure to match API expectations
- **No action needed**: Fix is already deployed

#### 3. **DBG-007: Token Limits Need Dynamic Escalation** (FIXED: BUILD-046)
- **Issue**: Fixed token budgets caused truncation for complex phases
- **Status**: ✅ Resolved
- **Fix**: Dynamic token escalation based on phase complexity
  - Low complexity: 8,192 tokens
  - Medium complexity: 16,384 tokens
  - High complexity: 32,768 tokens
- **Validation**: All phases now complete without truncation
- **No action needed**: Your research phases will automatically get appropriate token budgets

#### 4. **DBG-006: Classification Threshold Calibration** (FIXED: BUILD-047)
- **Issue**: LLM-generated classification thresholds too strict (0.75 → realistic documents scored 0.31)
- **Status**: ✅ Resolved
- **Fix**: Calibrated thresholds to 0.43, refined keyword lists
- **No action needed**: FileOrg-specific issue, not relevant to research system

#### 5. **DBG-003: Executor Infinite Failure Loop** (FIXED: BUILD-041)
- **Issue**: Phases stuck in retry loops due to state desynchronization
- **Status**: ✅ Resolved
- **Fix**: Database-backed state persistence with atomic updates
- **Validation**: FileOrg Phase 2 completed 14/15 phases (93.3% success)
- **No action needed**: Retry logic now works correctly

#### 6. **Module Caching Issue** (FIXED: BUILD-042)
- **Issue**: Python module caching prevented code changes from being applied
- **Status**: ✅ Resolved
- **Solution**: Always restart executor after code changes
- **Best Practice**: If you commit fixes during a run, restart the executor to ensure they're applied

---

## What to Monitor During Execution

### 1. Token Budget Utilization
Watch for truncation warnings in logs:
```
WARNING: [Builder] Output was truncated (stop_reason=max_tokens)
```

**Expected behavior**: With BUILD-046, phases should NOT truncate:
- Research Tracer Bullet: High complexity → 32,768 tokens
- Research Foundation: Medium complexity → 16,384 tokens

**If truncation occurs**: Phase will auto-retry with proper token budget. If it persists after 2+ attempts, the complexity may need manual adjustment.

### 2. Phase State Transitions
Monitor phase state in logs:
```
[PhaseExecutor] Phase research-tracer-bullet: QUEUED → IN_PROGRESS
[PhaseExecutor] Phase research-tracer-bullet: IN_PROGRESS → COMPLETE
```

**Expected flow**:
- QUEUED → IN_PROGRESS → COMPLETE (success)
- QUEUED → IN_PROGRESS → FAILED → IN_PROGRESS (retry)
- QUEUED → IN_PROGRESS → AWAITING_REVIEW (manual review needed)

**Red flags**:
- Same phase stays IN_PROGRESS for >2 hours → Check logs for stalls
- Phase cycles QUEUED → IN_PROGRESS → QUEUED repeatedly → State sync issue (should be fixed by BUILD-041, but report if seen)

### 3. Test Results
Each chunk runs pytest tests automatically:
```
============================= test session starts =============================
collected 25 items

tests/test_research_tracer_bullet.py::test_pipeline_execution PASSED     [ 4%]
tests/test_research_tracer_bullet.py::test_evaluation_score PASSED       [ 8%]
...
============================= 25 passed, 0 failed in 45.2s ====================
```

**Expected**: ≥80% tests passing for COMPLETE status, ≥60% for NEEDS_REVIEW

**Red flags**:
- <60% pass rate → Phase should auto-fail, investigate test failures
- Test import errors → Code structure issue, needs manual fix

### 4. Citation Validity Checks
The research system has built-in citation validation:
```
[CitationValidator] Checking citation validity...
[CitationValidator] Valid: 14/18 citations (77.8%)
[CitationValidator] Failures: extraction_span not found (3), numeric mismatch (1)
```

**Expected for Chunk 0**: ≥75% citation validity (baseline from BUILD-039/040 improvements: 77.8%)

**Red flags**:
- <70% validity → LLM extraction quality issue (not validator bug per DBG-003 analysis)
- >30% "extraction_span not found" → Text normalization issue (should be fixed by Phase 2 improvements)

### 5. Retry Attempts
Monitor retry behavior:
```
[PhaseExecutor] Attempt 1/5 for research-tracer-bullet
[PhaseExecutor] Attempt 2/5 for research-tracer-bullet (retry after PATCH_FAILED)
```

**Expected**: Average 1.5-2.0 attempts per phase (based on FileOrg Phase 2 baseline)

**Red flags**:
- >3 attempts on same phase → Persistent issue needs investigation
- Infinite retry loop (same attempt number repeating) → BUILD-041 regression (should not occur)

---

## Prerequisites (Verify Before Starting)

### 1. API Keys Configured
```bash
# Check if API keys are set
echo $ANTHROPIC_API_KEY  # Should output: sk-ant-...
echo $GITHUB_API_KEY     # Should output: ghp_... or github_pat_...

# If not set, configure them
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_API_KEY="ghp_..."
```

### 2. Database Ready
```bash
# Verify PostgreSQL is running
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" python -c "from autopack.database import SessionLocal; print('DB OK')"
```

### 3. Qdrant Ready (Optional for Phase 0, Required for Phase 3+)
```bash
# Check if Qdrant is running
curl http://localhost:6333/collections
```

### 4. No Executor Running
```bash
# Check for running executors
ps aux | grep "autopack.*execute"

# If found, kill them
pkill -f "autopack.*execute"
```

---

## Quality Gate Criteria

### COMPLETE (Proceed to Next Chunk)
- ✅ All deliverable files created
- ✅ ≥80% of tests passing
- ✅ No critical bugs or regressions
- ✅ Human review approved

### NEEDS_REVIEW (Human Decision Required)
- ⚠️ 60-80% tests passing
- ⚠️ Code quality issues detected
- ⚠️ Performance below targets
- ⚠️ Unclear requirements or edge cases

### FAILED (Must Fix Before Proceeding)
- ❌ Build errors (syntax, imports, etc.)
- ❌ <60% tests passing
- ❌ Critical bugs detected
- ❌ Fundamental architectural issues

---

## Troubleshooting Guide

### Issue: Phase Stuck in IN_PROGRESS for >2 Hours
**Diagnosis**:
```bash
# Check executor logs
tail -n 100 .autonomous_runs/research-system-v1/research-tracer-bullet.log

# Check if executor process is alive
ps aux | grep "autopack.*execute"
```

**Solutions**:
1. If executor crashed: Restart with `--resume` flag
2. If stalled on API call: Check API rate limits, restart executor
3. If stuck in loop: Check for BUILD-041 regression, report issue

### Issue: Tests Failing with Import Errors
**Diagnosis**:
```bash
# Check if all files were created
ls -la src/autopack/research/

# Try importing manually
PYTHONPATH=src python -c "from autopack.research.tracer_bullet import TracerBullet"
```

**Solutions**:
1. Check if `__init__.py` files exist in all directories
2. Verify file paths match requirements in YAML
3. Check for syntax errors: `python -m py_compile src/autopack/research/*.py`

### Issue: Citation Validity Below 75%
**Diagnosis**:
```bash
# Review failure breakdown
grep "CitationValidator" .autonomous_runs/research-system-v1/research-tracer-bullet.log
```

**Solutions**:
1. If "extraction_span not found" (>30%): Text normalization issue, may need Phase 2 fix
2. If "numeric mismatch": LLM extraction quality, acceptable if <20%
3. If "source_url invalid": Validator bug, report for investigation

**Note**: Per DBG-003 analysis, 75-78% validity is acceptable for Phase 0. Remaining issues are LLM quality, not validator bugs.

### Issue: Token Budget Truncation
**Diagnosis**:
```bash
# Check token utilization in logs
grep "TOKEN_BUDGET" .autonomous_runs/research-system-v1/research-tracer-bullet.log
```

**Solutions**:
1. Verify BUILD-046 is active (should show complexity-based budgets)
2. If still truncating: Increase complexity level in phase requirements
3. If truncation persists after 3 retries: Manual intervention needed

---

## Success Metrics for Chunk 0 (Tracer Bullet)

### Primary Metrics
- **Pipeline Execution**: 10/10 test topics processed successfully
- **Evaluation Score**: ≥7.0/10 average across topics
- **Factuality**: ≥80% of claims verified against sources
- **Citation Validity**: ≥75% of citations validate correctly

### Secondary Metrics
- **Test Pass Rate**: ≥80% (20+ of 25 tests)
- **Execution Time**: <30 minutes per topic (median)
- **Token Efficiency**: <32K tokens per topic (with BUILD-046)
- **Retry Rate**: <2.0 attempts per phase (with BUILD-041)

### Qualitative Assessment
- **Code Quality**: Readable, maintainable, well-structured
- **Documentation**: Clear docstrings and inline comments
- **Integration**: Fits with existing Autopack patterns
- **Error Handling**: Graceful failures with informative messages

---

## After Chunk 0 Completes

### If Success (All Criteria Met)
1. ✅ Approve phase with: `autopack review-phase --decision approve`
2. 📋 Document any learnings or adjustments needed
3. 🚀 Launch Chunk 1A using: `chunk1a-foundation-orchestrator.yaml`
4. 🔁 Repeat monitoring process

### If Failure (Criteria Not Met)
1. ❌ Reject phase with: `autopack review-phase --decision reject --reason "..."`
2. 🔍 Analyze root cause from logs and test results
3. 📝 Document issues in `.autonomous_runs/research-system-v1/chunk0-issues.md`
4. 🛠️ Decide: Fix and retry, or revise approach
5. ⛔ **DO NOT PROCEED** to Chunk 1A until Chunk 0 passes

---

## Execution Timeline Estimate

| Chunk | Duration | Cumulative |
|-------|----------|------------|
| 0: Tracer Bullet | 2-3 days | Day 3 |
| 1A: Foundation (Orchestrator) | 2-3 days | Day 6 |
| 1B: Foundation (Intent) | 2-3 days | Day 9 |
| 2A: Gatherers (Social) | 3-4 days | Day 13 |
| 2B: Gatherers (Web) | 2-3 days | Day 16 |
| 3: Meta-Analysis | 3-4 days | Day 20 |
| 4: Integration | 3-4 days | Day 24 |
| 5: Testing & Polish | 4-5 days | Day 29 |

**Total**: ~1 month of autonomous execution + human review time

---

## Questions to Ask During Review

### Chunk 0 Review Questions
1. Does the minimal pipeline demonstrate feasibility?
2. Are the evaluation metrics accurate and reliable?
3. Is the code quality acceptable for building upon?
4. Are there any fundamental architectural concerns?
5. Should we adjust scope or approach before proceeding?

### General Review Questions (All Chunks)
1. Does the implementation match the requirements?
2. Are all tests passing and meaningful?
3. Is the code maintainable and well-documented?
4. Are there any integration issues with existing code?
5. Should we make any adjustments before the next chunk?

---

## Contact & Support

**If you encounter issues**:
1. Check this troubleshooting guide first
2. Review relevant DEBUG_LOG.md entries (DBG-001 through DBG-009)
3. Check BUILD_HISTORY.md for similar past issues
4. Review `.autonomous_runs/research-system-v1/` logs for details

**Recent fixes you can reference**:
- BUILD-041: Executor state persistence (infinite loop fix)
- BUILD-042: Max tokens adjustment (module caching fix)
- BUILD-046: Dynamic token escalation (complexity-based budgets)
- BUILD-047: Classification threshold calibration (FileOrg-specific)
- BUILD-048: Executor instance management (duplicate prevention)

**Key documentation**:
- Implementation plan: `.autonomous_runs/file-organizer-app-v1/archive/research/active/UNIFIED_RESEARCH_SYSTEM_IMPLEMENTATION_V2_REVISED.md`
- Execution summary: `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/ALL_CHUNKS_SUMMARY.md`
- Debug history: `docs/DEBUG_LOG.md`
- Build history: `docs/BUILD_HISTORY.md`

---

## Ready to Start?

✅ **Prerequisites verified** (API keys, database, no running executors)
✅ **Recent fixes understood** (DBG-003 through DBG-009)
✅ **Monitoring plan ready** (token budgets, state transitions, tests, citations)
✅ **Quality gates clear** (COMPLETE, NEEDS_REVIEW, FAILED criteria)

**Launch Chunk 0 now**:
```bash
cd c:/dev/Autopack

# Start API server (in separate terminal)
PYTHONUTF8=1 PYTHONPATH=src uvicorn backend.main:app --reload --port 8000

# Create run and launch executor (see Step 1 above for full commands)
# Then monitor execution logs
```

**Good luck! 🚀**

---

**Document Created**: 2025-12-18
**Purpose**: Cursor prompt for Research System implementation via Autopack
**Status**: ✅ Ready for use in new Cursor session

---

## Quick Start Cheat Sheet

### First Time Setup
```bash
cd c:/dev/Autopack

# 1. Create run
PYTHONUTF8=1 PYTHONPATH=src python scripts/create_research_run.py chunk0-tracer-bullet

# 2. Start API (separate terminal)
PYTHONUTF8=1 PYTHONPATH=src uvicorn backend.main:app --reload --port 8000

# 3. Launch executor
PYTHONUTF8=1 PYTHONPATH=src python -m autopack.autonomous_executor --run-id research-system-v1
```

### Monitoring Commands
```bash
# Check phase status (API)
curl http://localhost:8000/runs/research-system-v1 | python -m json.tool

# Check phase status (Database)
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import Phase
db = SessionLocal()
phase = db.query(Phase).filter_by(run_id='research-system-v1', phase_id='research-tracer-bullet').first()
print(f'State: {phase.state.value}, Attempts: {phase.builder_attempts}')
"

# Watch logs
tail -f .autonomous_runs/research-system-v1/executor.log
```

### After Chunk 0 Completes
```bash
# Check test results
cat .autonomous_runs/research-system-v1/ci/pytest_*.log

# If passing: Proceed to Chunk 1A
PYTHONUTF8=1 PYTHONPATH=src python scripts/create_research_run.py chunk1a-foundation-orchestrator
PYTHONUTF8=1 PYTHONPATH=src python -m autopack.autonomous_executor --run-id research-system-v1
```
