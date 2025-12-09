# Autopack Test Run Checklist

**Date**: 2025-12-09
**Status**: Ready for Test Spin
**Test Target**: WHATS_LEFT_TO_BUILD.md (file-organizer-app-v1 Phase 2 tasks)

---

## Recent Updates to Test

Based on recent commits (last 15):

### 1. ✅ Qdrant Vector Memory Integration (Commit: 8ebdc37c)

**What was implemented**:
- Qdrant as default vector backend (replacing FAISS)
- Deterministic UUID conversion for Qdrant point IDs (MD5-based)
- Collections: code_docs, decision_logs, run_summaries, task_outcomes, error_patterns

**What to look for during test run**:
- [ ] Memory service initializes with backend="qdrant"
- [ ] Decision logs stored successfully with UUID conversion
- [ ] Phase summaries written to run_summaries collection
- [ ] No "Qdrant point ID error" messages
- [ ] Document counts increase in Qdrant collections
- [ ] Original string IDs preserved in payload["_original_id"]
- [ ] Qdrant container remains running (docker ps | grep qdrant)

**How to verify**:
```bash
# Check Qdrant is running
docker ps | grep qdrant

# During run, watch for:
grep -i "qdrant" .autonomous_runs/<run_id>/executor.log
grep -i "memory" .autonomous_runs/<run_id>/executor.log

# After run, check collection counts
python -c "from autopack.memory import MemoryService; m=MemoryService(use_qdrant=True); print(m.store.count('decision_logs'))"
```

**Potential issues**:
- Qdrant container not running → fallback to FAISS
- UUID conversion errors → check for string IDs in error messages
- Collections not created → verify use_qdrant: true in config/memory.yaml

---

### 2. ✅ Markdown Plan Converter (Commits: fe0bcc7e, 1100b945, 2ab603d9)

**What was implemented**:
- `scripts/plan_from_markdown.py` - Convert markdown tasks to phase JSON
- `scripts/autorun_markdown_plan.py` - Wrapper to convert + execute in one step
- Plan merge support for combining multiple markdown sources

**What to look for during test run**:
- [ ] Markdown tasks (WHATS_LEFT_TO_BUILD.md) converted to valid phase JSON
- [ ] Phase IDs match task descriptions (e.g., fileorg-p2-test-fixes)
- [ ] Complexity/category/acceptance_criteria properly extracted
- [ ] Dependencies tracked between phases
- [ ] Estimated tokens and confidence preserved

**How to verify**:
```bash
# Convert markdown to JSON
python scripts/plan_from_markdown.py --markdown .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md --output test_plan.json

# Verify JSON structure
cat test_plan.json | jq '.phases | length'  # Should show number of tasks
cat test_plan.json | jq '.phases[0] | keys'  # Should have phase_id, description, etc.

# Auto-run (convert + execute)
python scripts/autorun_markdown_plan.py --markdown .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md --project-id file-organizer-app-v1
```

**Potential issues**:
- Malformed markdown → conversion errors (check Task header format)
- Missing phase_id → generated from description
- Duplicate phase IDs → merge conflict warnings

---

### 3. ✅ Backlog Maintenance System (Commits: 0a6f8f54, 3b75f328)

**What was implemented**:
- `scripts/run_backlog_maintenance.py` - Execute maintenance from backlog
- Propose-first approach: diagnostics → patches → auditor review → apply (if approved)
- Checkpoint support: git commits before apply, rollback on failure
- Auditor gating: low-risk auto-apply with size/test guards

**What to look for during test run**:
- [ ] Backlog items parsed from WHATS_LEFT_TO_BUILD.md Task 7 (maintenance)
- [ ] Diagnostics run for each item (stored in .autonomous_runs/<run_id>/diagnostics/)
- [ ] Patches generated and saved to patches/ directory
- [ ] Auditor verdict visible in backlog_executor_summary.json
- [ ] Git checkpoint created before apply (if apply enabled)
- [ ] Compact JSON summaries (not full logs inline) to keep token usage low
- [ ] DecisionLog entries created for each maintenance decision

**How to verify**:
```bash
# Run maintenance on Task 7
python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --allowed-path .autonomous_runs/file-organizer-app-v1/ \
  --checkpoint

# Check diagnostics
ls .autonomous_runs/<run_id>/diagnostics/

# Check patches
ls patches/

# Check auditor summary
cat .autonomous_runs/<run_id>/diagnostics/backlog_executor_summary.json | jq '.[].auditor_verdict'

# Check git checkpoints
git log --oneline | head -5
```

**Potential issues**:
- No backlog items found → check markdown format (Task header with Phase ID)
- Auditor always says "require_human" → patches too large or tests failing
- Checkpoint creation fails → git not in clean state
- Token budget exceeded → diagnostics logs too verbose (should be compact JSON)

---

### 4. ✅ Pre-Publication Checklist (Commits: 8075bbcc, 72ad1a7f)

**What was implemented**:
- `scripts/pre_publish_checklist.py` - Automated 40+ publication readiness checks
- Intent router integration: natural language "check publication readiness"
- Severity levels: errors, warnings, recommendations
- Strict mode and JSON output support

**What to look for during test run**:
- [ ] Intent router recognizes "check publication readiness" queries
- [ ] Checklist runs on .autonomous_runs/file-organizer-app-v1
- [ ] Results categorized: errors, warnings, recommendations
- [ ] Exit code 0 = ready, 1 = not ready
- [ ] JSON output option works (--output results.json)

**How to verify**:
```bash
# Via intent router
PYTHONPATH=src python scripts/intent_router.py \
  --query "check publication readiness" \
  --project-id file-organizer-app-v1

# Direct invocation
python scripts/pre_publish_checklist.py \
  --project-path .autonomous_runs/file-organizer-app-v1

# Strict mode
python scripts/pre_publish_checklist.py \
  --project-path .autonomous_runs/file-organizer-app-v1 \
  --strict

# With JSON output
python scripts/pre_publish_checklist.py \
  --project-path .autonomous_runs/file-organizer-app-v1 \
  --output pub_check.json
```

**Potential issues**:
- Unicode errors on Windows → UTF-8 encoding should be fixed
- Intent not recognized → check keyword matching
- False negatives → missing files that actually exist (path issues)

---

### 5. ✅ Tidy Workspace Orchestrator (Commits: 7d6a6e1a, df5a7c37, 84f8e564, a7b65c2f, 6460a56c)

**What was implemented**:
- `scripts/tidy_workspace.py` - Clean up .autonomous_runs with safeguards
- Semantic mode: move superseded files to archive/ based on content
- Cache support: remember previous tidy decisions
- Git checkpoint support: commit before/after tidy
- Dryrun mode: preview changes without applying

**What to look for during test run**:
- [ ] Legacy files identified and moved to archive/superseded/
- [ ] Consolidated docs preserved
- [ ] Diagnostic artifacts preserved
- [ ] Cache file (.tidy_cache.json) created and reused
- [ ] Git checkpoints created (if --checkpoint flag used)
- [ ] Semantic analysis detects superseded/duplicate content

**How to verify**:
```bash
# Dry run first
python scripts/tidy_workspace.py --project-id file-organizer-app-v1 --dryrun

# Actual tidy with checkpoint
python scripts/tidy_workspace.py --project-id file-organizer-app-v1 --checkpoint

# Semantic mode (slower, more thorough)
python scripts/tidy_workspace.py --project-id file-organizer-app-v1 --semantic --checkpoint

# Check cache
cat .autonomous_runs/file-organizer-app-v1/.tidy_cache.json | jq '.decisions | length'

# Check git log
git log --oneline | grep tidy
```

**Potential issues**:
- Over-aggressive archiving → check semantic analysis thresholds
- Cache false positives → clear cache with --clear-cache
- Git conflicts → ensure clean working tree before tidy

---

## Overall Test Plan for Maintenance Run

### Pre-Test Setup

1. **Verify Qdrant is running**:
   ```bash
   docker ps | grep qdrant
   # If not running:
   docker run -p 6333:6333 qdrant/qdrant
   ```

2. **Verify PostgreSQL database is running**:
   ```bash
   docker ps | grep postgres
   # If not running:
   docker-compose up -d db

   # Wait 5 seconds for initialization, then verify connection:
   PYTHONPATH=src python -c "from autopack.database import SessionLocal; s = SessionLocal(); print(f'Connected to: {s.bind.url}'); s.close()"

   # Default DATABASE_URL (should already be set in environment):
   # postgresql://autopack:autopack@localhost:5432/autopack
   ```

   **Note**: PostgreSQL is the primary database. SQLite (`DATABASE_URL="sqlite:///autopack.db"`) can be used as override for quick testing but is not recommended for production.

3. **Check config/memory.yaml**:
   ```yaml
   use_qdrant: true
   qdrant:
     host: localhost
     port: 6333
   ```

4. **Verify git clean state**:
   ```bash
   git status  # Should be clean for checkpoints
   ```

5. **Backup current state** (optional):
   ```bash
   git tag pre-test-run-20251209
   ```

---

### Test Run Execution

#### Option A: Full Maintenance Run (Task 7)

```bash
# Run backlog maintenance on Task 7 with all features (uses PostgreSQL by default)
PYTHONPATH=src python scripts/run_backlog_maintenance.py \
  --backlog .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --allowed-path .autonomous_runs/file-organizer-app-v1/ \
  --allowed-path docs/ \
  --allowed-path patches/ \
  --checkpoint \
  --test-cmd "pytest -q tests/smoke/"
```

**What to monitor**:
- Terminal output for Qdrant connection messages
- Decision log entries being written
- Diagnostics artifacts created
- Patch generation
- Auditor verdicts
- Git checkpoints

#### Option B: Markdown Plan Auto-Run (All Tasks)

```bash
# Convert and execute all Phase 2 tasks from markdown (uses PostgreSQL by default)
PYTHONPATH=src python scripts/autorun_markdown_plan.py \
  --markdown .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --project-id file-organizer-app-v1 \
  --allowed-path .autonomous_runs/file-organizer-app-v1/ \
  --checkpoint
```

**What to monitor**:
- Markdown → JSON conversion success
- Phase execution order (dependencies respected)
- Memory writes to Qdrant
- Phase summaries stored
- Token usage tracking

#### Option C: Manual Step-by-Step

```bash
# 1. Convert markdown to JSON
python scripts/plan_from_markdown.py \
  --markdown .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md \
  --output .autonomous_runs/file-organizer-app-v1/plan_phase2.json

# 2. Review plan
cat .autonomous_runs/file-organizer-app-v1/plan_phase2.json | jq '.phases[] | {phase_id, complexity, category}'

# 3. Run single phase (Task 1: test-fixes) - uses PostgreSQL by default
PYTHONPATH=src python src/autopack/autonomous_executor.py \
  --run-id fileorg-p2-test-run \
  --api-url http://localhost:8000 \
  --plan .autonomous_runs/file-organizer-app-v1/plan_phase2.json

# 4. Check results
ls .autonomous_runs/fileorg-p2-test-run/
cat .autonomous_runs/fileorg-p2-test-run/executor.log
```

---

### Post-Test Verification

1. **Qdrant Collections**:
   ```bash
   PYTHONPATH=src python -c "
   from autopack.memory import MemoryService
   m = MemoryService(use_qdrant=True)
   for col in ['code_docs', 'decision_logs', 'run_summaries', 'task_outcomes', 'error_patterns']:
       print(f'{col}: {m.store.count(col)} documents')
   "
   ```

2. **Decision Logs** (PostgreSQL):
   ```bash
   PYTHONPATH=src python -c "
   from autopack.database import SessionLocal
   from autopack.models import DecisionLog
   session = SessionLocal()
   print(f'Connected to: {session.bind.url}')
   decisions = session.query(DecisionLog).filter_by(project_id='file-organizer-app-v1').all()
   print(f'Decision log entries: {len(decisions)}')
   for d in decisions[:5]:
       print(f'  {d.timestamp}: {d.trigger} -> {d.choice}')
   session.close()
   "
   ```

3. **Git Checkpoints**:
   ```bash
   git log --oneline --grep="checkpoint" | head -10
   ```

4. **Diagnostics Artifacts**:
   ```bash
   find .autonomous_runs -name "backlog_executor_summary.json" -exec cat {} \; | jq '.[].auditor_verdict'
   ```

5. **Patches Generated**:
   ```bash
   ls -lh patches/
   ```

6. **Publication Readiness**:
   ```bash
   PYTHONPATH=src python scripts/intent_router.py \
     --query "check publication readiness" \
     --project-id file-organizer-app-v1
   ```

7. **Smoke Tests**:
   ```bash
   PYTHONPATH=src pytest tests/smoke/ -v
   ```

---

## Success Criteria

The test run is successful if:

### Critical (Must Pass)
- [ ] Qdrant vector memory stores decision logs and phase summaries
- [ ] No UUID conversion errors in Qdrant operations
- [ ] Markdown plan converts to valid JSON with all phases
- [ ] At least one maintenance phase completes diagnostics
- [ ] Auditor produces verdicts (approve/require_human/reject)
- [ ] Git checkpoints created before apply operations
- [ ] Smoke tests pass (5/5)

### Important (Should Pass)
- [ ] Memory retrieval works (search_code, search_context)
- [ ] Token usage tracking functional
- [ ] DecisionLog entries visible in database
- [ ] Patches generated for at least one maintenance item
- [ ] Diagnostics artifacts stored under .autonomous_runs/<run_id>/diagnostics/
- [ ] Publication checklist identifies missing artifacts (README, LICENSE, etc.)
- [ ] Intent router recognizes all new natural language commands

### Nice to Have (May Pass)
- [ ] Low-risk patches auto-applied with auditor approval
- [ ] Semantic tidy mode correctly identifies superseded files
- [ ] Cache reuse reduces redundant decisions
- [ ] All Phase 2 tasks from WHATS_LEFT_TO_BUILD.md complete successfully

---

## Known Issues & Workarounds

### Issue 1: Qdrant Search Method Error
**Symptom**: `'QdrantClient' object has no attribute 'search'`
**Impact**: Code search returns 0 results
**Workaround**: Write operations work fine; search compatibility to be fixed
**Status**: Non-blocking for test run

### Issue 2: FAISS Fallback Warning
**Symptom**: `faiss library not installed; FaissStore will use in-memory fallback`
**Impact**: FAISS not needed if Qdrant is primary backend
**Workaround**: Ignore warning, or install faiss-cpu for dev/offline mode
**Status**: Non-blocking

### Issue 3: Disk Usage Timeout
**Symptom**: `Disk usage check timed out (40s timeout)`
**Impact**: Expected on large repos
**Workaround**: Increase timeout in diagnostics config or skip
**Status**: Expected behavior

### Issue 4: Test Directory Not Found (First Run)
**Symptom**: `tests/smoke not found`
**Impact**: Smoke tests can't run
**Workaround**: Already fixed - tests/smoke/test_basic.py created
**Status**: Resolved

---

## Rollback Plan

If test run fails catastrophically:

1. **Stop running processes**:
   ```bash
   # Kill any running executor
   pkill -f autonomous_executor
   ```

2. **Restore from checkpoint**:
   ```bash
   # Find last good checkpoint
   git log --oneline | grep checkpoint

   # Reset to checkpoint
   git reset --hard <checkpoint-hash>
   ```

3. **Clean up partial artifacts**:
   ```bash
   # Remove failed run directory
   rm -rf .autonomous_runs/<failed-run-id>
   ```

4. **Restore Qdrant collections** (if needed):
   ```bash
   # Qdrant data is persistent; restart container to reset
   docker stop qdrant
   docker rm qdrant
   docker run -p 6333:6333 qdrant/qdrant
   ```

5. **Restore database** (SQLite):
   ```bash
   # Backup before run
   cp autopack.db autopack.db.backup

   # Restore if needed
   cp autopack.db.backup autopack.db
   ```

---

## Expected Output

### Successful Run Indicators
```
✓ Memory service initialized with backend: qdrant
✓ Decision log stored: decision:file-organizer-app-v1:...
✓ Phase summary stored: summary:fileorg-p2-test-fixes
✓ Patch generated: patches/fileorg-backlog-maintenance.patch
✓ Auditor verdict: approved (low-risk auto-apply)
✓ Git checkpoint created: [abc123] Maintenance checkpoint fileorg-backlog-20251209
✓ Tests passed: 5/5 smoke tests
```

### Failed Run Indicators
```
✗ Qdrant connection failed: Connection refused
✗ UUID conversion error: Invalid point ID format
✗ Markdown parsing failed: Missing phase_id
✗ Auditor verdict: reject (protected path violation)
✗ Git checkpoint failed: Uncommitted changes
✗ Tests failed: 2/5 smoke tests
```

---

## Summary

**Yes, Autopack is ready for a test spin** with the following new capabilities:

1. **Qdrant vector memory** - Production-ready persistent storage
2. **Markdown plan conversion** - Natural task format → executable JSON
3. **Backlog maintenance** - Propose-first diagnostics + auditor gating
4. **Publication checklist** - 40+ automated readiness checks
5. **Workspace tidying** - Semantic cleanup with safeguards

**Recommended first test**: Run backlog maintenance (Task 7) with checkpoints enabled to verify all systems working together.

**Expected duration**: 15-30 minutes for full maintenance run (depends on diagnostics depth)

**Risk level**: Low (checkpoints + rollback plan in place)
