# Git Worktree Vibe Coding Guide - Parallel Implementation

**Generated**: 2026-01-13
**Purpose**: Step-by-step prompts for parallel Cursor execution
**Strategy**: Maximum parallelization with zero conflicts

---

## ⚠️ CRITICAL REQUIREMENT: Code Formatting

**ALL Cursors MUST run formatting before every commit:**

```bash
# Run pre-commit checks on your modified files
pre-commit run --all-files
# OR for specific files only:
pre-commit run --files src/your/modified/file.py tests/your/test.py

# If ruff-format modifies files, stage the changes:
git add .
```

**Why**: CI runs `ruff format --check` and will FAIL if code isn't formatted. This is NOT optional.

**When**: Before EVERY `git commit` command in this guide.

---

## 🎯 Overview: Parallel Run Groups

**Total Improvements**: 20
**Parallel Groups**: 5 groups (maximize simultaneous work, zero conflicts)
**Sequential Phases**: 5 phases (must complete previous phase before next)

### Parallel Group Summary

| Phase | Cursors | Improvements | Can Merge | Dependencies |
|-------|---------|--------------|-----------|--------------|
| **Phase 1** | 3 cursors | IMP-P04, IMP-R04, IMP-DOC-1 | Any order | None |
| **Phase 2** | 5 cursors | IMP-R02, IMP-P02, IMP-P03, IMP-S03, IMP-S04 | Any order | Phase 1 complete |
| **Phase 3** | 3 cursors | IMP-T01, IMP-T02, IMP-T03 | Any order | None |
| **Phase 4** | 2 cursors | IMP-P01, IMP-R03 | Sequential | Phase 1 complete |
| **Phase 5** | 3 cursors | Batched improvements | Any order | Phase 1+2 complete |

---

## ✈️ PRE-FLIGHT CHECKLIST (Run BEFORE Every Commit)

**CRITICAL**: Follow this checklist IN ORDER before every `git commit` in ANY cursor. This prevents 45-70 minutes of failure loops per cursor.

**Time Savings**: ~45-70 minutes per cursor by preventing:
- Temp file commits → rebase conflicts (10-15min wasted)
- Formatting discrepancies → CI failures (25min+ wasted)
- Dirty working tree → rebase errors (20-30min wasted)

```bash
# 1. Clean git state (remove temp files, check for unintended changes)
git status
rm -f tmpclaude-*-cwd 2>/dev/null || true
git status  # Verify no temp files remain

# 2. Run formatting (MANDATORY - CI will fail without this)
pre-commit run --all-files
# If pre-commit modifies files, stage them:
git add .

# 3. Verify clean state before commit
git status
# Should show only your intended changes

# 4. Run local tests (optional but recommended for critical changes)
pytest tests/path/to/your_tests.py -v

# 5. Commit with clear message
git commit -m "your commit message"

# 6. Push to trigger CI
git push
```

**Common Mistakes (DO NOT DO THIS)**:
- ❌ Committing without running pre-commit (causes CI formatting failures)
- ❌ Leaving temp files (tmpclaude-*-cwd) in commits (causes rebase conflicts)
- ❌ Committing with dirty working tree (causes rebase errors)
- ❌ Skipping git status verification (commits unintended changes)

**Why This Matters**:
- Evidence from ref3.md: Cursor #1 spent 30+ minutes investigating temp file issues (preventable)
- Evidence from ref3.md: Cursor #2 spent 20+ minutes on git rebase recovery (preventable)
- Evidence from PR #191, #192, #193: Multiple formatting CI failures post-rebase (preventable)

---

## 🔵 PHASE 1: Setup Worktrees (Original Cursor)

**Prompt for Original Cursor (main repo):**

```
Create git worktrees for Phase 1 parallel work (3 improvements, zero conflicts):

git worktree add C:\dev\Autopack\devAutopack-dashboard -b perf/dashboard-n1-query-fix
git worktree add C:\dev\Autopack\devAutopack-file-leak -b reliability/fix-file-handle-leak
git worktree add C:\dev\Autopack\devAutopack-docs -b docs/memory-service-operator-guide

Verify: git worktree list
```

---

## 🔵 PHASE 1: Cursor #1 (Dashboard Fix)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-dashboard**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-dashboard
Branch: perf/dashboard-n1-query-fix

Task: Implement IMP-P04 - Optimize Dashboard N+1 Query

Files to modify:
- src/autopack/api/routes/dashboard.py (lines 105-141)

Implementation (from EXECUTION_PLAN_SAFE.md):
BEFORE (lines 105-141):
```python
events = session.query(Event).all()  # Loads entire table
aggregated = {}
for event in events:
    key = event.run_id
    if key not in aggregated:
        aggregated[key] = []
    aggregated[key].append(event)
```

AFTER (use SQL GROUP BY):
```python
from sqlalchemy import func
aggregated = (
    session.query(
        Event.run_id,
        func.count(Event.id).label('event_count'),
        func.max(Event.created_at).label('latest_event')
    )
    .group_by(Event.run_id)
    .all()
)
```

Steps:
1. Read dashboard.py to understand current implementation
2. Replace Python aggregation with SQL GROUP BY
3. Update response serialization to match new structure
4. Update tests in tests/api/test_dashboard.py
5. Run tests: pytest tests/api/test_dashboard.py -v
6. **CRITICAL - Run formatting**: pre-commit run --all-files (or --files <your modified files>)
   - If ruff-format modifies files, stage them: git add .
7. Commit: git commit -am "perf(api): optimize dashboard query with SQL GROUP BY (saves 2-10s)"
8. Push: git push -u origin perf/dashboard-n1-query-fix
9. Create PR: gh pr create --title "perf(api): optimize dashboard query with SQL GROUP BY"

Start implementation now.
```

---

## 🔵 PHASE 1: Cursor #2 (File Leak Fix)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-file-leak**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-file-leak
Branch: reliability/fix-file-handle-leak

Task: Implement IMP-R04 - Fix File Handle Leak

Files to modify:
- src/autopack/executor/server_lifecycle.py (line 142)

Implementation (from EXECUTION_PLAN_SAFE.md):
BEFORE (line 142):
```python
f = open(pidfile, 'r')
pid = int(f.read())
# f.close() missing!
```

AFTER:
```python
with open(pidfile, 'r') as f:
    pid = int(f.read())
```

Additional steps:
1. Search for other open() calls without context managers
2. Replace all with `with open(...) as f:` pattern
3. Check for other resource leaks (sockets, DB connections)
4. Add tests to verify proper resource cleanup

Steps:
1. Read server_lifecycle.py line 142
2. Replace open() with context manager
3. Search for other unclosed file handles: grep -rn "open(" src/autopack/executor/
4. Fix all occurrences
5. Run tests: pytest tests/executor/test_server_lifecycle.py -v
6. **CRITICAL - Run formatting**: pre-commit run --all-files (or --files <your modified files>)
   - If ruff-format modifies files, stage them: git add .
7. Commit: git commit -am "fix(reliability): fix file handle leak in server_lifecycle.py"
8. Push: git push -u origin reliability/fix-file-handle-leak
9. Create PR: gh pr create --title "fix(reliability): fix file handle leak"

Start implementation now.
```

---

## 🔵 PHASE 1: Cursor #3 (Documentation)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-docs**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-docs
Branch: docs/memory-service-operator-guide

Task: Implement IMP-DOC-1 - Memory Service Operator Guide

Files to create/modify:
- docs/operators/MEMORY_SERVICE_GUIDE.md (new file)
- README.md (add link)

Implementation:
Create comprehensive operator guide covering:
1. Overview: What is memory service, why it's important
2. Architecture: Qdrant integration, vector embeddings, retrieval
3. Setup: Installation, configuration, environment variables
4. Operations: Starting/stopping, health checks, monitoring
5. Troubleshooting: Common issues, debugging steps
6. Performance: Tuning, scaling, optimization

Update README.md with link:
```markdown
## Documentation
- [Memory Service Operator Guide](docs/operators/MEMORY_SERVICE_GUIDE.md)
```

Steps:
1. Create docs/operators/MEMORY_SERVICE_GUIDE.md (see plan for detailed structure)
2. Add comprehensive content (architecture, setup, operations, troubleshooting)
3. Update README.md with link to new guide
4. Run SOT integrity check: python scripts/ci/check_docs_sot_integrity.py
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
6. Commit: git commit -am "docs: add memory service production operator guide"
7. Push: git push -u origin docs/memory-service-operator-guide
8. Create PR: gh pr create --title "docs: add memory service operator guide"

Start implementation now.
```

---

## 🔵 PHASE 1: Complete
**After all 3 PRs merge:**
- ✅ Phase 1 complete
- ⏭️ Proceed to Phase 2 (leave Cursor windows open for now)

---

## 🟢 PHASE 2: Setup Worktrees (Original Cursor)
**Prompt for Original Cursor (main repo):**

```
git checkout main
git pull

Create git worktrees for Phase 2 parallel work (5 improvements, zero conflicts):

git worktree add C:\dev\Autopack\devAutopack-transaction -b critical/transaction-management
git worktree add C:\dev\Autopack\devAutopack-indexes -b perf/add-db-indexes
git worktree add C:\dev\Autopack\devAutopack-cache -b perf/cache-file-context
git worktree add C:\dev\Autopack\devAutopack-ratelimit -b security/auth-rate-limiting
git worktree add C:\dev\Autopack\devAutopack-cve -b security/cve-monitoring

Verify: git worktree list
```

---

## 🟢 PHASE 2: Cursor #1 (Transaction Management - CRITICAL)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-transaction**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-transaction
Branch: critical/transaction-management

Task: Implement IMP-R02 - Transaction Management (CRITICAL)

Files to modify:
- src/autopack/executor/phase_state_manager.py

Implementation (from EXECUTION_PLAN_SAFE.md):
PROBLEM: Session used across multiple phases without commits, causing connection leaks

BEFORE:
```python
def save_phase_state(self, phase_id, state_data):
    session.query(PhaseState).filter_by(phase_id=phase_id).update(state_data)
    # No commit!
```

AFTER:
```python
def save_phase_state(self, phase_id, state_data):
    session.query(PhaseState).filter_by(phase_id=phase_id).update(state_data)
    session.commit()  # Explicit commit
```

Additional steps:
1. Find all session.query() calls without commits
2. Add explicit commits or use context managers
3. Add tests to verify transaction boundaries
4. Check for connection leak prevention

Steps:
1. Read phase_state_manager.py to understand current implementation
2. Add explicit commits to all state mutations
3. Add transaction context managers where appropriate
4. Update tests in tests/executor/test_phase_state_manager.py
5. Run tests: pytest tests/executor/test_phase_state_manager.py -v
6. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
6. Commit: git commit -am "fix(critical): add transaction management to prevent connection leaks"
7. Push: git push -u origin critical/transaction-management
8. Create PR: gh pr create --title "fix(critical): add transaction management to prevent connection leaks"

Start implementation now.
```

---

## 🟢 PHASE 2: Cursor #2 (DB Indexes)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-indexes**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-indexes
Branch: perf/add-db-indexes

Task: Implement IMP-P02 - Add Database Indexes

Files to modify:
- src/autopack/models.py
- migrations/add_performance_indexes.py (new file)

Implementation (from EXECUTION_PLAN_SAFE.md):
Add indexes to frequently queried columns:
1. Event.run_id (frequently used in dashboard queries)
2. PhaseState.phase_id (frequently used in state lookups)
3. FileChange.file_path (frequently used in context loading)

BEFORE (models.py):
```python
class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    run_id = Column(String)  # No index!
```

AFTER (models.py):
```python
class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    run_id = Column(String, index=True)  # Add index
```

Steps:
1. Read models.py to understand current schema
2. Add indexes to Event.run_id, PhaseState.phase_id, FileChange.file_path
3. Create migration file: migrations/add_performance_indexes.py
4. Add tests to verify indexes exist
5. Run tests: pytest tests/models/test_indexes.py -v
6. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
6. Commit: git commit -am "perf(db): add indexes to frequently queried columns"
7. Push: git push -u origin perf/add-db-indexes
8. Create PR: gh pr create --title "perf(db): add indexes to frequently queried columns"

Start implementation now.
```

---

## 🟢 PHASE 2: Cursor #3 (Cache File Context)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-cache**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-cache
Branch: perf/cache-file-context

Task: Implement IMP-P03 - Cache File Context

Files to modify:
- src/autopack/executor/scoped_context_loader.py

Implementation (from EXECUTION_PLAN_SAFE.md):
PROBLEM: File context loaded from disk every phase (30+ file reads per phase)

BEFORE:
```python
def load_context(self, file_path):
    with open(file_path, 'r') as f:
        return f.read()
```

AFTER:
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def load_context(self, file_path):
    with open(file_path, 'r') as f:
        return f.read()
```

Additional steps:
1. Add cache invalidation on file changes
2. Add tests to verify cache hit rate
3. Monitor memory usage

Steps:
1. Read scoped_context_loader.py to understand current implementation
2. Add LRU cache to load_context method
3. Add cache invalidation logic on file modifications
4. Update tests in tests/executor/test_scoped_context_loader.py
5. Run tests: pytest tests/executor/test_scoped_context_loader.py -v
6. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
6. Commit: git commit -am "perf(executor): cache file context to reduce disk I/O"
7. Push: git push -u origin perf/cache-file-context
8. Create PR: gh pr create --title "perf(executor): cache file context to reduce disk I/O"

Start implementation now.
```

---

## 🟢 PHASE 2: Cursor #4 (Auth Rate Limiting)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-ratelimit**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-ratelimit
Branch: security/auth-rate-limiting

Task: Implement IMP-S03 - Auth Rate Limiting

Files to modify:
- src/autopack/auth/router.py
- src/autopack/auth/rate_limiter.py (new file)

Implementation (from EXECUTION_PLAN_SAFE.md):
Add rate limiting to auth endpoints to prevent brute force attacks

Create rate_limiter.py:
```python
from functools import wraps
from time import time

class RateLimiter:
    def __init__(self, max_requests=5, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def check_rate_limit(self, client_ip):
        now = time()
        if client_ip not in self.requests:
            self.requests[client_ip] = []

        # Remove old requests outside window
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if now - req_time < self.window_seconds
        ]

        if len(self.requests[client_ip]) >= self.max_requests:
            return False

        self.requests[client_ip].append(now)
        return True
```

Update router.py to use rate limiter on login endpoint

Steps:
1. Create src/autopack/auth/rate_limiter.py with RateLimiter class
2. Update router.py to add rate limiting to /login endpoint
3. Add tests in tests/auth/test_rate_limiter.py
4. Run tests: pytest tests/auth/test_rate_limiter.py -v
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
5. Commit: git commit -am "security(auth): add rate limiting to prevent brute force attacks"
6. Push: git push -u origin security/auth-rate-limiting
7. Create PR: gh pr create --title "security(auth): add rate limiting to prevent brute force attacks"

Start implementation now.
```

---

## 🟢 PHASE 2: Cursor #5 (CVE Monitoring)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-cve**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-cve
Branch: security/cve-monitoring

Task: Implement IMP-S04 - CVE Monitoring

Files to create/modify:
- scripts/ci/check_dependency_cves.py (new)
- .github/workflows/ci.yml (add CVE check job)
- .github/workflows/weekly_cve_scan.yml (new)

Implementation (from EXECUTION_PLAN_SAFE.md):
Add automated CVE scanning using pip-audit or safety

Create check_dependency_cves.py:
```python
import subprocess
import sys

def check_cves():
    result = subprocess.run(['pip-audit', '--format', 'json'], capture_output=True)
    if result.returncode != 0:
        print("CVE vulnerabilities found!")
        print(result.stdout.decode())
        sys.exit(1)
    print("No CVE vulnerabilities found")

if __name__ == '__main__':
    check_cves()
```

Update ci.yml to add CVE check job
Create weekly_cve_scan.yml for scheduled scans

Steps:
1. Create scripts/ci/check_dependency_cves.py
2. Update .github/workflows/ci.yml to add cve-check job
3. Create .github/workflows/weekly_cve_scan.yml for weekly scans
4. Test locally: python scripts/ci/check_dependency_cves.py
5. Commit: git commit -am "security(deps): add automated CVE monitoring"
6. Push: git push -u origin security/cve-monitoring
7. Create PR: gh pr create --title "security(deps): add automated CVE monitoring"

Start implementation now.
```

---

## 🟢 PHASE 2: Complete
**After all 5 PRs merge:**
- ✅ Phase 2 complete
- ⏭️ Proceed to Phase 3 (leave Cursor windows open for now)

---

## 🟠 PHASE 3: Setup Worktrees (Original Cursor)

**Prompt for Original Cursor (main repo):**

```
git checkout main
git pull

Create git worktrees for Phase 3 parallel work (3 improvements, zero conflicts):

git worktree add C:\dev\Autopack\devAutopack-test-lifecycle -b test/phase-lifecycle-e2e
git worktree add C:\dev\Autopack\devAutopack-test-dual-audit -b test/dual-audit-wiring
git worktree add C:\dev\Autopack\devAutopack-test-e2e-pipeline -b test/e2e-autonomous-pipeline

Verify: git worktree list
```

---

## 🟠 PHASE 3: Cursor #1 (Phase Lifecycle Tests)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-test-lifecycle**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-test-lifecycle
Branch: test/phase-lifecycle-e2e

Task: Implement IMP-T01 - Phase Lifecycle E2E Tests

Files to create:
- tests/integration/test_phase_lifecycle_e2e.py (new)

Implementation (from EXECUTION_PLAN_SAFE.md):
Create E2E test that verifies complete phase lifecycle:
1. Phase initialization
2. State transitions (pending → running → completed)
3. Checkpoint saving/loading
4. Error handling and recovery

Create test_phase_lifecycle_e2e.py:
```python
import pytest

@pytest.mark.aspirational  # Mark as aspirational for fast CI
def test_phase_lifecycle_complete():
    # Test complete phase lifecycle
    pass

@pytest.mark.aspirational
def test_phase_state_transitions():
    # Test state transitions
    pass

@pytest.mark.aspirational
def test_phase_checkpoint_recovery():
    # Test checkpoint recovery
    pass
```

Steps:
1. Create tests/integration/test_phase_lifecycle_e2e.py
2. Implement comprehensive lifecycle tests
3. Mark all tests with @pytest.mark.aspirational for fast CI
4. Run tests: pytest tests/integration/test_phase_lifecycle_e2e.py -v
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
5. Commit: git commit -am "test(integration): add phase lifecycle E2E tests"
6. Push: git push -u origin test/phase-lifecycle-e2e
7. Create PR: gh pr create --title "test(integration): add phase lifecycle E2E tests"

Start implementation now.
```

---

## 🟠 PHASE 3: Cursor #2 (Dual-Audit Tests)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-test-dual-audit**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-test-dual-audit
Branch: test/dual-audit-wiring

Task: Implement IMP-T02 - Dual-Audit Wiring Tests

Files to create:
- tests/llm_service/test_dual_audit_wiring.py (new)

Implementation (from EXECUTION_PLAN_SAFE.md):
Create tests that verify dual-audit system is properly wired:
1. Audit trail is created for all LLM calls
2. Tool use is properly logged
3. Token usage is tracked
4. Errors are captured in audit trail

Create test_dual_audit_wiring.py:
```python
import pytest

@pytest.mark.aspirational
def test_llm_call_creates_audit_trail():
    # Test audit trail creation
    pass

@pytest.mark.aspirational
def test_tool_use_logged_in_audit():
    # Test tool use logging
    pass

@pytest.mark.aspirational
def test_token_usage_tracked():
    # Test token tracking
    pass
```

Steps:
1. Create tests/llm_service/test_dual_audit_wiring.py
2. Implement comprehensive dual-audit tests
3. Mark all tests with @pytest.mark.aspirational
4. Run tests: pytest tests/llm_service/test_dual_audit_wiring.py -v
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
5. Commit: git commit -am "test(llm): add dual-audit wiring tests"
6. Push: git push -u origin test/dual-audit-wiring
7. Create PR: gh pr create --title "test(llm): add dual-audit wiring tests"

Start implementation now.
```

---

## 🟠 PHASE 3: Cursor #3 (E2E Pipeline Test)

**Open new Cursor window at: C:\dev\Autopack\devAutopack-test-e2e-pipeline**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-test-e2e-pipeline
Branch: test/e2e-autonomous-pipeline

Task: Implement IMP-T03 - E2E Autonomous Pipeline Test

Files to create:
- tests/integration/test_autonomous_pipeline_e2e.py (new)

Implementation (from EXECUTION_PLAN_SAFE.md):
Create E2E test that verifies complete autonomous pipeline:
1. Task ingestion
2. Phase orchestration
3. Code generation and validation
4. Error recovery
5. Deliverable creation

Create test_autonomous_pipeline_e2e.py:
```python
import pytest

@pytest.mark.aspirational
def test_autonomous_pipeline_complete():
    # Test complete pipeline execution
    pass

@pytest.mark.aspirational
def test_pipeline_error_recovery():
    # Test error recovery
    pass

@pytest.mark.aspirational
def test_pipeline_deliverable_creation():
    # Test deliverable creation
    pass
```

Steps:
1. Create tests/integration/test_autonomous_pipeline_e2e.py
2. Implement comprehensive pipeline tests
3. Mark all tests with @pytest.mark.aspirational
4. Run tests: pytest tests/integration/test_autonomous_pipeline_e2e.py -v
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
5. Commit: git commit -am "test(integration): add autonomous pipeline E2E test"
6. Push: git push -u origin test/e2e-autonomous-pipeline
7. Create PR: gh pr create --title "test(integration): add autonomous pipeline E2E test"

Start implementation now.
```

---

## ⚠️ PHASE 3 BLOCKER: Black vs Ruff Format Discrepancy

**Issue Detected**: Phase 3 PRs (#191, #192, #193) blocked by formatting discrepancy:
- Pre-commit uses `ruff format` (passes locally) ✅
- CI uses `black` (fails on 68 files) ❌

**Action Required**: Create infrastructure fix PR to standardize on black.

**Commands:**

```bash
cd C:/dev/Autopack
git checkout main
git pull
git worktree add C:/dev/Autopack/devAutopack-format-fix -b infra/standardize-formatting-tool
```

**Open Cursor #4 at**: `C:/dev/Autopack/devAutopack-format-fix`

**Prompt for Cursor #4:**

```
cd C:/dev/Autopack/devAutopack-format-fix

Task: Standardize on black formatter across entire project

Problem: Pre-commit uses ruff format (passes) but CI uses black (fails on 68 files), blocking Phase 3 PRs.

Solution: Remove ruff format, add black to pre-commit, format all files with black.

Steps:

1. Edit .pre-commit-config.yaml:
   - Remove the ruff-format hook
   - Add black hook:
     ```yaml
     - repo: https://github.com/psf/black
       rev: 24.1.1
       hooks:
         - id: black
           language_version: python3.11
     ```

2. Run black on all 68 files that need formatting:
   ```bash
   black .
   ```

3. Update documentation to reflect black as standard:
   - README.md: Change "ruff format" to "black"
   - docs/CI_EFFICIENT_DEVELOPMENT.md: Change "ruff format" to "black"

4. Run formatting check:
   ```bash
   pre-commit run --all-files
   ```
   - If black modifies files, stage them: git add .

5. Commit:
   ```bash
   git commit -m "ci: standardize on black formatter (remove ruff format)

   - Remove ruff-format hook from pre-commit
   - Add black hook to pre-commit
   - Format all files with black (68 files updated)
   - Update documentation to reflect black as standard
   - Resolves Phase 3 CI formatting failures"
   ```

6. Push:
   ```bash
   git push -u origin infra/standardize-formatting-tool
   ```

7. Create PR:
   ```bash
   gh pr create --title "ci: standardize on black formatter (remove ruff format)" --body "Resolves formatting discrepancy blocking Phase 3 PRs (#191, #192, #193).

   Changes:
   - Remove ruff-format from .pre-commit-config.yaml
   - Add black to .pre-commit-config.yaml
   - Format all 68 files with black
   - Update README.md and CI_EFFICIENT_DEVELOPMENT.md

   Impact: After merge, Phase 3 PRs need to rebase to inherit black formatting."
   ```

Start implementation now.
```

**After Infrastructure Fix PR Merges**:
1. Close Cursor #4 (devAutopack-format-fix)
2. In Phase 3 Cursors (#1, #2, #3):
   ```bash
   git fetch origin
   git rebase origin/main
   git push --force-with-lease
   ```
3. CI should now pass on Phase 3 PRs
4. Merge Phase 3 PRs

---

## 🟠 PHASE 3: Complete
**After infrastructure fix merges AND all 3 PRs merge:**
- ✅ Infrastructure fix complete
- ✅ Phase 3 complete
- ⏭️ Proceed to Phase 4 (leave Cursor windows open for now)

---

## 🔴 PHASE 4: Sequential Workflow (Conflicts)
**Note: Phase 4 has conflicts - use sequential workflow, not worktrees**

**Prompt for Original Cursor:**

```
cd C:\dev\Autopack
git checkout main
git pull

Create PR #1 (IMP-P01):
git checkout -b perf/reduce-polling-interval

Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

Task: Implement IMP-P01 - Reduce Polling Interval

Files to modify:
- src/autopack/executor/autonomous_loop.py (lines 285-288 only)

BEFORE (lines 285-288):
```python
sleep_time = 10  # 10 second polling interval
```

AFTER:
```python
sleep_time = 1  # 1-2 second polling interval (saves 8-9s per phase)
```

Steps:
1. Modify autonomous_loop.py lines 285-288 only
2. Run tests: pytest tests/executor/test_autonomous_executor.py -v
3. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
3. Commit: git commit -am "perf(executor): reduce polling interval to 1-2s (saves 8-9s/phase)"
4. Push: git push -u origin perf/reduce-polling-interval
5. Create PR: gh pr create --title "perf(executor): reduce polling interval to 1-2s"

After PR #1 is created and CI passes, merge it immediately.
```

**Prompt for Original Cursor (after PR #1 merges):**

```
cd C:\dev\Autopack
git checkout main
git pull

Create PR #2 (IMP-R03):
git checkout -b reliability/fix-bare-except

Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

Task: Implement IMP-R03 - Fix Bare Except Clauses

Files to modify:
- src/autopack/executor/autonomous_loop.py
- src/autopack/llm_service.py
- Other files with bare except:

PROBLEM: Bare except clauses catch all exceptions including KeyboardInterrupt

BEFORE:
```python
try:
    do_something()
except:  # Catches everything!
    log_error()
```

AFTER:
```python
try:
    do_something()
except Exception as e:  # Only catch Exception, not BaseException
    log_error(f"Error: {e}")
```

Steps:
1. Search for all bare except: grep -rn "except:" src/autopack/
2. Replace with `except Exception as e:`
3. Run tests: pytest tests/ -v
4. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
4. Commit: git commit -am "fix(reliability): replace bare except clauses with specific exception handling"
5. Push: git push -u origin reliability/fix-bare-except
6. Create PR: gh pr create --title "fix(reliability): replace bare except clauses"

Start implementation now.
```

---

## 🟣 PHASE 5: Setup Worktrees (Original Cursor)
**WAIT for Phase 1 and Phase 2 to fully merge before starting Phase 5**

**Prompt for Original Cursor:**

```
cd C:\dev\Autopack
git checkout main
git pull

Verify Phase 1 and Phase 2 are fully merged:
git log --oneline | head -n 10

Create git worktrees for Phase 5 parallel work (3 batched PRs, zero conflicts):

git worktree add C:\dev\Autopack\devAutopack-batch1 -b perf/token-caching-and-parallel-ci
git worktree add C:\dev\Autopack\devAutopack-batch2 -b reliability/mock-races-and-state-validation
git worktree add C:\dev\Autopack\devAutopack-batch3 -b reliability/api-safety-improvements

Verify: git worktree list
```

---

## 🟣 PHASE 5: Cursor #1 (Batched: Token + Parallel CI)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-batch1**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-batch1
Branch: perf/token-caching-and-parallel-ci

Task: Implement BATCHED improvements (IMP-P05 + IMP-P06)

Files to modify:
- src/autopack/llm_service/token_estimator.py (IMP-P05)
- src/autopack/executor/autonomous_loop.py (IMP-P06)
- src/autopack/executor/phase_orchestrator.py (new, IMP-P06)

IMP-P05 - Token Estimation Caching:
BEFORE:
```python
def estimate_tokens(text):
    return len(text) / 4  # Rough estimate, no caching
```

AFTER:
```python
from functools import lru_cache

@lru_cache(maxsize=256)
def estimate_tokens(text):
    return len(text) / 4
```

IMP-P06 - Parallel CI Phase Execution:
Create phase_orchestrator.py to run non-dependent phases in parallel

Steps:
1. Implement IMP-P05 (token caching in token_estimator.py)
2. Implement IMP-P06 (create phase_orchestrator.py, update autonomous_loop.py)
3. Run tests: pytest tests/llm_service/ tests/executor/ -v
4. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
4. Commit: git commit -am "perf(executor): add token caching and parallel phase execution"
5. Push: git push -u origin perf/token-caching-and-parallel-ci
6. Create PR: gh pr create --title "perf(executor): add token caching and parallel phase execution"

Start implementation now.
```

---

## 🟣 PHASE 5: Cursor #2 (Batched: Mock Races + Validation)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-batch2**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-batch2
Branch: reliability/mock-races-and-state-validation

Task: Implement BATCHED improvements (IMP-R01 + IMP-R05)

Files to modify:
- tests/executor/test_phase_approach_reviser.py (IMP-R01)
- src/autopack/executor/phase_state_manager.py (IMP-R05)

IMP-R01 - Fix Mock Thread Race Conditions:
PROBLEM: test_phase_approach_reviser.py has flaky tests due to mock races

BEFORE:
```python
@patch('time.sleep')
def test_approach_reviser(mock_sleep):
    # Race condition with threads
    pass
```

AFTER:
```python
@patch('time.sleep')
def test_approach_reviser(mock_sleep):
    # Use threading.Event for synchronization
    pass
```

IMP-R05 - Phase State Validation:
Add validation to phase_state_manager.py to prevent invalid state transitions

Steps:
1. Fix mock races in test_phase_approach_reviser.py (IMP-R01)
2. Add state validation to phase_state_manager.py (IMP-R05)
3. Run tests: pytest tests/executor/ -v
4. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
4. Commit: git commit -am "fix(reliability): fix mock races and add state validation"
5. Push: git push -u origin reliability/mock-races-and-state-validation
6. Create PR: gh pr create --title "fix(reliability): fix mock races and add state validation"

Start implementation now.
```

---

## 🟣 PHASE 5: Cursor #3 (Batched: API Safety)
**Open new Cursor window at: C:\dev\Autopack\devAutopack-batch3**

**Prompt:**

```
Read: C:\dev\Autopack\docs\COMPREHENSIVE_SCAN_2026-01-13_EXECUTION_PLAN_SAFE.md

I'm working in git worktree: C:\dev\Autopack\devAutopack-batch3
Branch: reliability/api-safety-improvements

Task: Implement BATCHED improvements (IMP-R06 + IMP-S01 + IMP-S02)

Files to modify:
- src/autopack/executor/autonomous_executor.py (IMP-R06)
- src/autopack/executor/code_validator.py (IMP-S01)
- src/autopack/diagnostics/package_detector.py (IMP-S02)

IMP-R06 - API Key Validation:
Add validation to autonomous_executor.py to check API keys before execution

IMP-S01 - Sanitize Code Validation Input:
Add input sanitization to code_validator.py to prevent injection

IMP-S02 - Shell Injection Prevention:
Add shell command sanitization to package_detector.py

Steps:
1. Implement IMP-R06 (API key validation in autonomous_executor.py)
2. Implement IMP-S01 (input sanitization in code_validator.py)
3. Implement IMP-S02 (shell command sanitization in package_detector.py)
4. Run tests: pytest tests/executor/ tests/diagnostics/ -v
5. **CRITICAL - Run formatting**: pre-commit run --all-files
   - If ruff-format modifies files, stage them: git add .
5. Commit: git commit -am "fix(reliability): add API safety and injection prevention"
6. Push: git push -u origin reliability/api-safety-improvements
7. Create PR: gh pr create --title "fix(reliability): add API safety and injection prevention"

Start implementation now.
```

---

## 🟣 PHASE 5: Complete
**After all 3 PRs merge:**
- ✅ Phase 5 complete
- ⏭️ Proceed to Final Cleanup

---

## 🆘 REBASE RECOVERY GUIDE (When Git State Goes Wrong)

**Use this guide when you encounter rebase errors or dirty working tree issues.**

**Time Savings**: ~20-30 minutes by avoiding trial-and-error recovery loops.

### Scenario 1: Dirty Working Tree During Rebase

**Error Message**:
```
error: cannot rebase: You have unstaged changes.
error: Please commit or stash them.
```

**Recovery Steps**:
```bash
# Step 1: Check what's dirty
git status

# Step 2: If you want to keep changes, stash them
git stash push -m "WIP: temporary stash during rebase"

# Step 3: Rebase
git fetch origin
git rebase origin/main

# Step 4: Restore stashed changes (if needed)
git stash pop

# Step 5: If conflicts occur, resolve them
git status  # See conflicting files
# Edit conflicting files manually
git add .
git rebase --continue
```

### Scenario 2: Rebase Conflict with Temp Files

**Symptoms**: Rebase conflict on tmpclaude-*-cwd files

**Recovery Steps**:
```bash
# Step 1: Abort the rebase
git rebase --abort

# Step 2: Remove temp files
rm -f tmpclaude-*-cwd

# Step 3: Verify clean state
git status

# Step 4: Try rebase again
git fetch origin
git rebase origin/main
```

### Scenario 3: Formatting Failures After Rebase

**Symptoms**: CI fails on formatting check after successful local rebase

**Recovery Steps**:
```bash
# Step 1: Pull latest main (inherits formatting fixes)
git fetch origin
git rebase origin/main

# Step 2: Run formatting on ALL files
pre-commit run --all-files
git add .

# Step 3: If rebase is in progress, continue it
git rebase --continue

# Step 4: Force push (if already pushed)
git push --force-with-lease
```

### Scenario 4: Multiple Rounds of Formatting Post-Rebase

**Symptoms**: Rebase succeeds, but CI keeps failing on different files each time

**Root Cause**: black vs ruff format discrepancy (resolved in PR #194)

**Recovery Steps**:
```bash
# Step 1: Ensure you've rebased AFTER PR #194 merge
git log origin/main --oneline | grep "standardize-formatting-tool"
# Should see: "ci: standardize on black formatter"

# Step 2: If PR #194 is merged, rebase again
git fetch origin
git rebase origin/main

# Step 3: Run black on all files
pre-commit run --all-files
git add .
git rebase --continue

# Step 4: Push
git push --force-with-lease
```

### Scenario 5: Emergency Reset (Last Resort)

**WARNING**: This discards ALL local commits. Only use if you're stuck.

```bash
# Step 1: Backup your changes
git diff > my_changes.patch

# Step 2: Hard reset to remote
git fetch origin
git reset --hard origin/main

# Step 3: Recreate branch
git checkout -b your-branch-name

# Step 4: Apply your changes manually
# Review my_changes.patch and manually apply relevant changes
```

**Prevention**: Always follow the [PRE-FLIGHT CHECKLIST](#-pre-flight-checklist-run-before-every-commit) above to avoid these scenarios.

---

## ✅ FINAL CLEANUP - All Phases Complete

**IMPORTANT**: Only do this cleanup AFTER all phases (1-5) are complete and all PRs are merged.

**Step 1: Close ALL Cursor Windows**
Close all Cursor instances EXCEPT the original one at `C:\dev\Autopack` (main):
- Phase 1: dashboard, file-leak, docs, infra-fix
- Phase 2: transaction, indexes, cache, ratelimit, cve
- Phase 3: test-lifecycle, test-dual-audit, test-e2e-pipeline
- Phase 4: polling-interval (if applicable)
- Phase 5: batch1, batch2, batch3

**Step 2: Pull Latest Main**
```bash
git checkout main
git pull origin main
```

**Step 3: Remove ALL Worktrees**
```bash
# Remove all Phase 1-5 worktrees at once
git worktree remove --force devAutopack-dashboard || true
git worktree remove --force devAutopack-file-leak || true
git worktree remove --force devAutopack-docs || true
git worktree remove --force devAutopack-infra-fix || true
git worktree remove --force devAutopack-transaction || true
git worktree remove --force devAutopack-indexes || true
git worktree remove --force devAutopack-cache || true
git worktree remove --force devAutopack-ratelimit || true
git worktree remove --force devAutopack-cve || true
git worktree remove --force devAutopack-test-lifecycle || true
git worktree remove --force devAutopack-test-dual-audit || true
git worktree remove --force devAutopack-test-e2e-pipeline || true
git worktree remove --force devAutopack-polling-interval || true
git worktree remove --force devAutopack-batch1 || true
git worktree remove --force devAutopack-batch2 || true
git worktree remove --force devAutopack-batch3 || true
```

**Step 4: Delete ALL Branches**
```bash
git branch -D \
  perf/dashboard-n1-query-fix \
  reliability/fix-file-handle-leak \
  docs/memory-service-operator-guide \
  infra/fix-lint-blockers \
  critical/transaction-management \
  perf/add-db-indexes \
  perf/cache-file-context \
  security/auth-rate-limiting \
  security/cve-monitoring \
  test/phase-lifecycle-e2e \
  test/dual-audit-wiring \
  test/e2e-autonomous-pipeline \
  perf/reduce-polling-interval \
  reliability/fix-bare-except \
  perf/token-caching-and-parallel-ci \
  reliability/mock-races-and-state-validation \
  reliability/api-safety-improvements \
  2>/dev/null || true
```

**Step 5: Verify Clean State**
```bash
git worktree list
# Should show only: C:/dev/Autopack [main]

git branch | grep -E "(perf/|reliability/|security/|test/|docs/|infra/|critical/)"
# Should show nothing
```

**Step 6: Celebrate! 🎉**
All 20 improvements implemented, PRs merged, and workspace cleaned up!

**Verify all improvements merged:**

```
cd C:\dev\Autopack
git checkout main
git pull
git log --oneline | head -n 20
```

**Total Implementation:**
- Phase 1: 3 PRs (parallel)
- Phase 2: 5 PRs (parallel)
- Phase 3: 3 PRs (parallel)
- Phase 4: 2 PRs (sequential)
- Phase 5: 3 PRs (parallel)
- **Total: 16 PRs, 20 improvements**

**Total Time: ~5 hours (vs 15+ hours sequential)**

---

**Generated**: 2026-01-13
**For**: Parallel Cursor execution with maximum parallelization
**Worktree paths**: C:\dev\Autopack\devAutopack-*
