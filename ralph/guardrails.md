# Autopack Evolution Guardrails

This file accumulates learnings across Ralph evolution cycles. **Read this FIRST before any action.**

**Last Updated**: 2026-01-17

---

## Authentication Pattern

**DO NOT** suggest OAuth token refresh improvements.

- Autopack uses **API key authentication** (no expiry)
- OAuth is ONLY for external service credentials (GitHub, Google APIs)
- The primary auth mechanism does NOT expire

**Validation**: Check `src/autopack/auth/` - you'll see `api_key.py` is the primary auth.

---

## Distribution Model

**DO NOT** add enterprise security features.

- Autopack is **personal/internal use ONLY** (never distributed)
- Skip: SARIF normalization, multi-tenant auth, supply chain security
- Focus on: API key security, local data protection, development efficiency

**Validation**: README.md states "for personal/internal use only (not distributed)"

---

## Import Paths in Tests

**ALWAYS** use `from autopack.X import Y`
**NEVER** use `from src.autopack.X import Y`

This causes SQLAlchemy namespace conflicts where models register in different module namespaces, leading to "relation does not exist" errors.

**Example**:
```python
# CORRECT
from autopack.models import GeneratedTask
from autopack.roadc.task_generator import TaskGenerator

# WRONG - causes SQLAlchemy issues
from src.autopack.models import GeneratedTask
from src.autopack.roadc.task_generator import TaskGenerator
```

---

## Pre-Existing Mypy Errors

**DO NOT** try to fix all 708 mypy errors.

- Autopack uses **adoption ladder strategy**
- Only Tier 1 files block CI: `config.py`, `schemas.py`, `version.py`, `safe_print.py`, `file_hashing.py`, `__version__.py`
- Pre-existing errors in other files are tracked technical debt, NOT blocking

**Action**: Write clean type-annotated code for NEW files. Ignore red squiggles in existing files you didn't modify.

---

## Database Session Injection

**ALWAYS** accept optional session parameter for classes that use SessionLocal().

```python
# CORRECT - allows test injection
class MyService:
    def __init__(self, session: Optional[Session] = None):
        self._session = session

    def do_query(self):
        session = self._session or SessionLocal()
        should_close = self._session is None
        try:
            # ... query logic
            return results
        finally:
            if should_close:
                session.close()
```

**Pattern Reference**: See `src/autopack/telemetry/analyzer.py` for correct implementation.

---

## Pre-Commit Formatting

**ALWAYS** run before every commit:
```bash
pre-commit run --all-files
git add .  # Stage any formatter changes
```

CI uses `black` formatter (standardized in PR #194). Local pre-commit also uses black.

**Common Mistake**: Committing without running pre-commit → CI fails on formatting → wasted 25+ minutes.

---

## Temp File Cleanup

**ALWAYS** remove temp files before git add:
```bash
rm -f tmpclaude-*-cwd 2>/dev/null || true
git status  # Verify clean
git add -A
```

These temp files cause rebase conflicts if committed.

---

## Test Database Fixtures

When writing tests that need database:

1. Use the `db_session` fixture from conftest.py
2. Inject session into class constructor
3. DO NOT create new SessionLocal() in tests

```python
# CORRECT
def test_my_feature(db_session):
    service = MyService(session=db_session)
    result = service.do_something()
    assert result is not None

# WRONG - connects to production DB
def test_my_feature():
    service = MyService()  # Uses SessionLocal() internally
    result = service.do_something()  # Queries wrong DB!
```

---

## ROAD Component Locations

When implementing ROAD-related features:

| Component | Location |
|-----------|----------|
| ROAD-A | `src/autopack/telemetry/` (phase outcomes) |
| ROAD-B | `src/autopack/telemetry/analyzer.py` |
| ROAD-C | `src/autopack/roadc/task_generator.py` |
| ROAD-G | `src/autopack/telemetry/` (anomaly detection) |
| ROAD-H | `src/autopack/roadh/` |
| ROAD-I | `src/autopack/roadi/regression_protector.py` |
| ROAD-J | `src/autopack/roadj/` |
| ROAD-K | `src/autopack/roadk/` |
| ROAD-L | `src/autopack/roadl/` |

---

## Executor Integration Points

Key locations in `src/autopack/executor/autonomous_loop.py`:

- `_finalize_execution()`: Where cleanup happens (around line 585-600)
- `_persist_telemetry_insights()`: Existing telemetry persistence
- `_generate_improvement_tasks()`: Task generation method (line ~780, NOT CALLED)

**Gap**: `_generate_improvement_tasks()` exists but is never invoked. Needs to be called in `_finalize_execution()`.

---

## Memory Service Methods

Existing methods in `src/autopack/memory/memory_service.py`:

- `search_code()` - Search code-related memories
- `search_errors()` - Search error patterns
- `search_summaries()` - Search phase summaries
- `search_doctor_hints()` - Search diagnostic hints
- `search_sot()` - Search SOT entries
- `search_planning()` - Search planning context

**Missing**: `retrieve_insights()` - needed by TaskGenerator

---

## Learnings from Evolution Runs

*(Ralph will add entries here as it discovers new patterns)*

### Template for New Learnings

```markdown
### [YYYY-MM-DD] [Category]: [Brief Title]

**Discovered During**: Cycle N, Phase X
**Pattern**: [What went wrong]
**Root Cause**: [Why it happened]
**Solution**: [How to avoid in future]
**Files Affected**: [List of files]
```

---

## CI/Lint Recovery Procedures

### Formatting Failures (ruff format --check)

If CI fails with "X files would be reformatted":

```bash
pre-commit run --all-files
git add .
git commit --amend --no-edit
git push --force-with-lease
```

### Dependency Drift (requirements.txt)

If CI fails with "requirements missing core deps":

```bash
# Needs Linux/WSL
bash scripts/regenerate_requirements.sh
git add requirements.txt requirements-dev.txt
git commit -m "fix(deps): regenerate requirements.txt"
git push
```

### Test Failures: "relation does not exist"

Two root causes:

1. **Wrong imports**: Using `src.autopack.X` instead of `autopack.X`
   - Fix: Change all test imports to `from autopack.X import Y`

2. **Missing session injection**: Class uses `SessionLocal()` directly
   - Fix: Add `session: Optional[Session] = None` parameter
   - Follow TelemetryAnalyzer pattern

---

## Priority Filter (CRITICAL)

**ONLY implement CRITICAL and HIGH priority IMPs.**

Skip:
- MEDIUM: Code quality, minor performance
- LOW: Refactoring, cosmetic
- BONUS: Nice-to-have features

---

## PR Workflow (MANDATORY)

**NEVER push directly to main. Always use the PR workflow:**

```bash
# 1. Create feature branch
git checkout -b fix/IMP-XXX-description

# 2. Make changes, commit
git add -A
git commit -m "[IMP-XXX] description"

# 3. Push branch (NOT main!)
git push -u origin fix/IMP-XXX-description

# 4. Create PR
gh pr create --title "[IMP-XXX] description" --body "..."

# 5. WAIT for CI (mandatory!)
gh pr checks [PR_NUMBER] --watch

# 6. Merge only after ALL checks pass
gh pr merge [PR_NUMBER] --merge --delete-branch

# 7. Return to main
git checkout main && git pull
```

**Why this matters:**
- CI catches bugs before they hit main
- PRs create audit trail
- Prevents broken code from blocking other work

---

## Cycle Rules

**You CANNOT claim ideal state in the same cycle you implement something.**

Flow must be:
1. Discovery → finds gaps → Implementation → PR → CI → Merge
2. **NEW CYCLE**: Discovery (fresh scan to verify implementation)
3. Only if fresh discovery finds 0 gaps → can claim ideal state

This prevents false confidence from untested implementations.

---

## Deep Verification Requirement

**Shallow verification is NOT acceptable. You MUST provide:**

1. **Actual code shown** - paste 5+ lines of actual code, not just "exists at line X"
2. **Full call chain traced** - who calls this function? with what arguments?
3. **Pytest results** - run pytest and show actual pass/fail counts
4. **9/9 verification steps** - all steps must pass including pytest

**WRONG (shallow):**
```
| Step | File:Line | Status |
| TelemetryAnalyzer accepts memory | analyzer.py:30 | PASS |
```

**RIGHT (deep):**
```
| Step | Verification Evidence | Status |
| TelemetryAnalyzer accepts memory | **Code**: `def __init__(self, db_session, memory_service=None): self.memory_service = memory_service` **Stores it**: yes **Call sites found**: autonomous_loop.py:65 passes executor.memory_service **Pytest**: 12 passed, 0 failed | PASS |
```

**Why this matters:**
- Shallow verification misses bugs where code exists but is never called
- Shallow verification misses bugs where code is called with wrong arguments
- Only deep verification + pytest proves the integration actually works

---

## Quick Reference: What NOT To Do

1. ❌ Suggest OAuth token refresh (we use API keys)
2. ❌ Add enterprise security features (personal use only)
3. ❌ Use `from src.autopack` imports in tests
4. ❌ Fix pre-existing mypy errors (adoption ladder)
5. ❌ Skip pre-commit before committing
6. ❌ Commit tmpclaude-* temp files
7. ❌ Create SessionLocal() in tests (use fixture)
8. ❌ Force push or amend pushed commits
9. ❌ Modify .env or credentials files
10. ❌ Skip tests before committing
11. ❌ Work on MEDIUM/LOW/BONUS priority IMPs (focus on CRITICAL/HIGH only)
12. ❌ **Push directly to main** (use PR workflow)
13. ❌ **Skip CI checks** (wait for all green before merge)
14. ❌ **Claim ideal state after implementing** (must run fresh discovery first)
