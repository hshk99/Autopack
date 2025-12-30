# Task: Monitor Autopack Autonomous Execution of Research System (Chunk 0 → Chunk 5)

## Executive Summary

**Research system stabilization status (updated 2025-12-19)**:
- ✅ Major convergence blockers were fixed (see `docs/BUILD_HISTORY.md` BUILD-078..085 and `docs/DEBUG_LOG.md` DBG-037..044).
- ✅ Chunk 2B/4/5 are now convergence-capable under normal project runs (no deterministic patch truncation / protected-path / deliverables-format blockers).
- ⚠️ CI/test failures (especially “pytest exit code 2” from import/dependency issues) are usually **deliverable correctness**, not executor mechanics.

**Your mission:**
1. **Launch Autopack autonomous executor** to complete remaining research system chunks
2. **Monitor execution** - watch logs, check phase progress, verify BUILD-050 features work
3. **Intervene only if needed** - if executor stalls, crashes, or asks for human input
4. **Report results** - document what Autopack completed, what failed, BUILD-050 validation

**DO NOT manually code** - Let Autopack autonomously complete all 8 chunks (Chunk 0 → Chunk 5).

**EXCEPTION / PROCESS RULE (SOT HYGIENE):**
If *you* (human/operator) apply **any manual fix** (code/config/docs/scripts/YAML) to unblock execution, you MUST immediately update the project SOT docs in `C:\dev\Autopack\docs`:
- `docs/DEBUG_LOG.md`: add/update a DBG entry with root cause + evidence + exact files changed + why intervention was necessary
- `docs/BUILD_HISTORY.md`: add a BUILD entry with the change summary + files changed
- If the fix changes operational protocol, also update this file (`PROMPT_FOR_OTHER_CURSOR_FILEORG.md`) so the rule is consistently followed going forward.
Autopack’s own changes are auto-logged; this rule is specifically for **manual/human changes**.

---

## Background

The Autopack project has just completed **BUILD-050** (Self-Correction Architecture Improvements) which includes:
- Deliverables contract as hard constraints in Builder prompts
- Decoupled attempt counters (retry_attempt, revision_epoch, escalation_level)
- Database schema fixes for production readiness
- Fixed executor bugs preventing phase execution

The executor is now confirmed working (tested with research-system-v1 run).

## Current Status

### ✅ Chunk 0 (Tracer Bullet) - PARTIALLY COMPLETE

**Code Implemented** (by previous cursor):
- ✅ `research_tracer/scraper.py` - Web scraper with robots.txt and rate limiting
- ✅ `research_tracer/extractor.py` - LLM extraction with prompt injection detection
- ✅ `research_tracer/calculator.py` - Python calculators (safe_divide, percentage, etc.)
- ✅ `research_tracer/pipeline.py` - End-to-end pipeline with token budget tracking
- ✅ `tests/test_tracer_bullet.py` - 22 unit tests

**Test Results**:
- ✅ **21/22 tests passing** (95.5% pass rate)
- ❌ 1 test failing: `test_rate_limiting` (timing assertion issue, not functional bug)

**What's MISSING from Chunk 0 requirements**:
- ❌ `src/autopack/research/tracer_bullet/orchestrator.py` - not in `src/`, exists in `research_tracer/`
- ❌ `src/autopack/research/tracer_bullet/gatherer.py` - only `src/autopack/research/gatherers/github_gatherer.py` exists
- ❌ `src/autopack/research/tracer_bullet/compiler.py` - missing
- ❌ `src/autopack/research/tracer_bullet/meta_auditor.py` - missing
- ❌ `src/autopack/research/evaluation/evaluator.py` - missing
- ❌ `src/autopack/research/evaluation/gold_set.json` - missing
- ❌ `tests/research/tracer_bullet/test_orchestrator.py` - missing (tests in root `tests/` not organized)
- ❌ `docs/research/TRACER_BULLET_RESULTS.md` - missing
- ❌ `docs/research/TRACER_BULLET_LEARNINGS.md` - missing

**Validation Status** (from chunk0-tracer-bullet.yaml):
- ❓ Functional: NOT VALIDATED (no end-to-end test with 10 topics)
- ❓ Quality: NOT VALIDATED (no evaluation harness)
- ❓ Performance: NOT VALIDATED (no timing tests)
- ⚠️ Tests: 21/22 passing (target was "10+ unit tests") - EXCEEDS TARGET but not organized properly

### ❌ Chunks 1A & 1B (Foundation) - NOT STARTED

**What exists**:
- ✅ Directory structure created: `src/autopack/research/discovery/`, `synthesis/`, `decision_frameworks/`, `models/`, `evaluation/`, `gatherers/`
- ✅ Partial models: `src/autopack/research/models/validators.py`
- ✅ Partial gatherers: `src/autopack/research/gatherers/github_gatherer.py`
- ✅ Partial evaluation: `src/autopack/research/evaluation/citation_validator.py`

**What's MISSING** (from chunk1a and chunk1b):
- ❌ All orchestrator code (5-stage pipeline)
- ❌ Evidence model (Finding, Recommendation dataclasses)
- ❌ Validators (evidence_validator, recency_validator, quality_validator)
- ❌ Intent clarifier agent
- ❌ Source discovery strategies (GitHub, Reddit, Web)
- ❌ Source evaluator agent
- ❌ Content sanitizer
- ❌ CLI command: `autopack research`
- ❌ All chunk1 tests

### ❌ Chunks 2A, 2B, 3, 4, 5 - NOT STARTED

### Previous Autopack Runs

There are **15 previous `fileorg-p2-*` runs from 2025-12-08**. Most recent (`fileorg-p2-20251208t`):
- Total Phases: 25
- Completed: 8 phases (different scope than research system)
- Failed: 17 phases (no retry logic, pre-BUILD-050)

**These are UNRELATED** to the research system chunks.

## Recommendation: Continue from Chunk 0, Not Fresh Start

**I recommend CONTINUING the existing work** because:

1. ✅ **Chunk 0 is ~70% complete** - Previous cursor made significant progress
2. ✅ **Code quality is good** - 21/22 tests passing, well-structured
3. ✅ **Core components work** - Scraper, extractor, calculator all functional
4. ⚠️ **Just needs reorganization & completion**:
   - Move `research_tracer/*` → `src/autopack/research/tracer_bullet/`
   - Complete missing deliverables (orchestrator, gatherer, compiler, meta_auditor, evaluator)
   - Add evaluation harness with 10 gold standard topics
   - Write feasibility validation report

5. 🎯 **BUILD-050 is now available** - Can leverage new improvements for retry logic

**Starting fresh would WASTE the ~10-15 hours** already invested in Chunk 0.

## Your Task: Monitor Autopack, Don't Code

**CRITICAL**: Your role is to **MONITOR** Autopack's autonomous execution, **NOT** to write code manually.

### What Autopack Will Do Autonomously:

Autopack will complete all remaining research system work:

**Chunk 0 (Tracer Bullet)** - 30% remaining:
- Create missing files (orchestrator, gatherer, compiler, meta_auditor, evaluator, gold_set.json)
- Reorganize code from `research_tracer/` → `src/autopack/research/tracer_bullet/`
- Fix failing test
- Run evaluation harness on 10 topics
- Generate validation reports

**Chunks 1A, 1B, 2A, 2B, 3, 4, 5** - All remaining phases:
- Autopack will autonomously implement ALL features from each chunk YAML
- Build orchestrator, agents, validators, CLI, integration, tests, docs
- Everything specified in the 8 chunk files

### What You Should Do:

**DO:**
- ✅ Monitor executor logs
- ✅ Check phase progress in database
- ✅ Verify BUILD-050 features (deliverables contract, attempt counters, replanning)
- ✅ Intervene if executor crashes or stalls
- ✅ Document results for the user

**DO NOT:**
- ❌ Write code manually
- ❌ Complete missing deliverables yourself
- ❌ Fix tests or bugs yourself
- ❌ Create files that Autopack should create

**Exception**: You may intervene if:
- Executor crashes and won't restart
- Executor stalls for >30 minutes with no progress
- Database or API issues prevent execution
- Autopack explicitly asks for human input

## Execution Steps

### Step 1: Start Backend API Server

**CRITICAL**:
- Use explicit env vars to ensure correct database + module paths.
- Use the canonical server (autopack.main:app) on port 8000.

```bash
cd C:\dev\Autopack
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

Keep this running in one terminal.

### Step 2: Launch Autopack Autonomous Executor

In a **separate terminal**, run the executor to complete ALL remaining chunks:

```bash
cd C:\dev\Autopack
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor --run-id <run-id> --api-url http://127.0.0.1:8001 --max-iterations 120
```

**Parameters Explained**:
- `--run-id research-system-v1`: Use the existing run (already has `research-tracer-bullet` phase)
- `--max-iterations 100`: Allow sufficient iterations to complete Chunk 0 + potentially start Chunk 1A
  - Chunk 0 remaining: ~10-20 iterations estimated
  - Chunk 1A full: ~30-50 iterations estimated
  - Adjust upward if needed (can go up to 200-300 for multiple chunks)

**What Will Happen**:
1. Autopack finds `research-tracer-bullet` phase (QUEUED state)
2. Reads chunk0-tracer-bullet.yaml requirements
3. Analyzes existing code in `research_tracer/`
4. Creates missing deliverables autonomously
5. Runs tests and validation
6. Marks phase COMPLETE when done
7. Proceeds to next phase (Chunk 1A) if it exists in the run

**Note**: If only Chunk 0 phase exists in database, Autopack will complete it and stop. To continue to Chunk 1A, you'll need to create that phase in the database or create a new run with all 8 chunk phases.

### Step 3: Monitor Execution (Your Primary Job)

**During execution, monitor**:

1. **Executor logs** in the terminal (real-time)

2. **Log file** (detailed output):
   ```bash
   tail -f C:\dev\Autopack\.autonomous_runs\research-system-v1\executor_*.log
   ```

3. **Database state** (check phase progress):
   ```bash
   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
   from autopack.database import SessionLocal
   from autopack.models import Phase

   db = SessionLocal()
   phase = db.query(Phase).filter(Phase.phase_id == 'research-tracer-bullet').first()

   if phase:
       print(f'Phase: {phase.phase_id}')
       print(f'State: {phase.state.value}')
       print(f'Builder attempts: {phase.builder_attempts}')
       print(f'Auditor attempts: {phase.auditor_attempts}')
       print(f'Tokens used: {phase.tokens_used}')
   else:
       print('Phase not found')

   db.close()
   "
   ```

4. **API endpoint** (check run status):
   ```bash
   curl -s http://127.0.0.1:8001/runs/<run-id>
   ```

5. **Test status** (verify Chunk 0 tests):
   ```bash
   PYTHONUTF8=1 PYTHONPATH=. python -m pytest tests/test_tracer_bullet.py -v --tb=line
   ```

### Step 4: Report Results to User

After Autopack completes (or reaches max_iterations), provide a comprehensive report:

**1. Overall Status**:
- How many chunks/phases did Autopack complete?
- Which phase is Autopack currently on?
- Any phases that failed? How many retry attempts?

**2. BUILD-050 Validation**:
- Did deliverables contract enforcement work?
- Were attempt counters properly decoupled (retry_attempt, revision_epoch, escalation_level)?
- Did non-destructive replanning preserve phase scope?
- Any quality issues or regressions?

**3. Chunk 0 Validation** (if completed):
- Did Autopack create all missing deliverables?
- Test results (how many passing/failing)?
- Evaluation harness results (score, factuality, citation validity)?
- Does it meet success criteria from chunk0-tracer-bullet.yaml?

**4. Issues Encountered**:
- Any executor crashes or errors?
- Any API or database issues?
- Any phases that stalled?

**5. Files to Attach**:
- Latest executor log file
- Database query showing final phase states
- Test results output
- Any error stack traces

## Key Things to Watch For During Monitoring

**BUILD-050 Features to Verify**:

1. **Deliverables Contract Enforcement**
   - Check if Builder prompts include hard constraints from deliverables
   - Look for validation that deliverables are met before phase completion

2. **Decoupled Attempt Counters**
   - `retry_attempt`: Increments on same-epoch retries (bugs/errors)
   - `revision_epoch`: Increments when deliverables not met (quality issues)
   - `escalation_level`: Tracks model escalation (haiku → sonnet → opus)

3. **Non-Destructive Replanning**
   - Phase scope should persist across retries
   - Original requirements should not be lost during replanning

4. **Error Handling**
   - Watch for phases that fail and verify retry logic kicks in
   - Check that `builder_attempts` and `auditor_attempts` increment correctly

## When to Intervene

**Only intervene if**:

1. **Executor crashes** - Process dies and won't restart
   - Check logs for error
   - Restart executor with same command
   - Report crash details to user

2. **Executor stalls** - No progress for >30 minutes
   - Check if API is responding
   - Check database connectivity
   - Consider killing and restarting executor

3. **API/Database errors** - Persistent connection failures
   - Verify backend API is running
   - Verify DATABASE_URL is correct
   - Check for process conflicts

4. **Autopack asks for human input** - Executor explicitly requests review
   - Read the request carefully
   - Provide minimal guidance
   - Let Autopack continue autonomously

**Remember**: Your job is to **monitor**, not to code. Let Autopack do its work!

## Important Notes

- **Windows Environment**: Use backslashes in Windows paths or forward slashes with proper quoting
- **Database Path**: Always use explicit `DATABASE_URL="sqlite:///autopack.db"` to avoid path mismatches
- **Process Management**: If you need to restart executor, kill all Python processes first:
  ```bash
  taskkill //F //IM python.exe
  ```
- **Safety First**: Start with `--max-iterations 10`, then increase once verified

## Environment

- **Working Directory**: `C:\dev\Autopack`
- **Database**: `autopack.db` (SQLite, in repo root)
- **Platform**: Windows (Git Bash or PowerShell)
- **Python**: Ensure `PYTHONUTF8=1` for proper encoding

## Success Criteria

✅ Autopack completes at least Chunk 0 (Tracer Bullet) autonomously
✅ BUILD-050 features (deliverables contract, decoupled counters) work correctly
✅ Failed phases retry with proper attempt tracking
✅ No crashes or schema mismatches
✅ You provide comprehensive report on Autopack's progress

---

**Remember**: You are **monitoring** Autopack's autonomous execution, **NOT** coding manually.

**Ready to launch Autopack! 🚀**
