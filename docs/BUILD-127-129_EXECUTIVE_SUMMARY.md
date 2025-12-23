# BUILD-127/129 Executive Summary - For GPT-5.2 Review

## What Happened

Attempted to run BUILD-127 (self-healing governance) and BUILD-129 (token budget intelligence) in parallel. Both executors started successfully but became stuck in infinite retry loops due to API 500 errors.

## Root Cause (5-Second Version)

**Database contains `state='READY'` but RunState enum only has `QUEUED`, `RUN_CREATED`, `PHASE_EXECUTION`, etc.**

When API tries to serialize run from database via SQLAlchemy ORM:
```python
run.state.value  # Fails: LookupError: 'READY' is not among the defined enum values
```

Result: 500 Internal Server Error → Executor retry loop → No progress

## Core Problem

**Autopack has strong error RECOVERY but weak error PREVENTION**

Strengths:
- ✅ Retry loops with exponential backoff
- ✅ Self-healing mechanisms
- ✅ Doctor agent for autonomous fixes

Gaps:
- ❌ No schema validation on startup
- ❌ Invalid database states silently accumulate
- ❌ Generic error messages without remediation
- ❌ No pre-flight checks before operations

## The Self-Improvement Paradox

BUILD-129 aims to autonomously implement token budget improvements (Autopack improving Autopack), but it **can't start because of schema issues**. How should Autopack bootstrap self-improvements when it can't run itself?

## 7 Capabilities Needed for Autonomous Navigation

1. **Schema Validation & Self-Repair** (CRITICAL)
   - Validate database state vs code enums on startup
   - Auto-fix safe mismatches, escalate dangerous ones
   - Example: `UPDATE runs SET state='RUN_CREATED' WHERE state='READY'`

2. **Diagnostic Error Messages with Remediation** (CRITICAL)
   - Not just "500 Internal Server Error"
   - But "Invalid state 'READY' in database. Valid: [QUEUED, RUN_CREATED, ...]. Fix: UPDATE runs SET state='RUN_CREATED' WHERE id='...'"

3. **Required Fields Auto-Discovery** (HIGH)
   - Query database schema for NOT NULL constraints
   - Provide sensible defaults automatically
   - Validate before INSERT, not after

4. **API Endpoint Discovery & Fallback** (HIGH)
   - Introspect API on startup, cache available endpoints
   - Gracefully degrade to direct database access if endpoint missing
   - Example: `POST /run/create` doesn't exist → use direct SQL INSERT

5. **Autonomous Run Creation Agent** (HIGH)
   - Hide complexity of run creation behind simple interface
   - Handle all validation, defaults, conventions
   - API-first with database fallback

6. **Smart ID Convention Inference** (MEDIUM)
   - Learn from existing runs: single-phase uses same ID or parent-child?
   - Validate new runs match convention
   - Auto-document inferred patterns

7. **Embedded Documentation in Database** (MEDIUM)
   - Store schema documentation in `schema_documentation` table
   - JSON schema for JSON columns (`scope`, `metadata`)
   - Example rows for complex structures

## Questions for GPT-5.2

### Q1: Priority Ranking
Which capabilities should be implemented first? My ranking:
1. Schema Validation (#1) - prevents silent failures
2. Diagnostic Errors (#2) - accelerates all debugging
3. Required Fields (#3) - eliminates trial-and-error
4. API Discovery (#4), Run Builder (#5), ID Convention (#6), Documentation (#7)

Do you agree?

### Q2: Architectural Issues
Are there deeper architectural problems that make these issues inevitable?

Observations:
- Enum values duplicated in database (string) and code (enum) → drift
- API as thin ORM wrapper → low-level errors bubble up as 500
- No migration strategy for enum changes
- Can't operate with invalid database state

### Q3: Bootstrap Strategy
BUILD-129 can't start due to schema issues. How to bootstrap self-improvement?

Options:
- A) Manual fix (update database schema), then let Autopack improve itself
- B) Hybrid mode (human fixes critical bugs, Autopack builds capabilities)
- C) Degraded mode (bypass API, use direct DB access to build improvements)

Which approach?

### Q4: Recovery vs Prevention
Should we shift from error RECOVERY emphasis to error PREVENTION?

Trade-offs:
- Recovery: Flexible, handles unexpected issues, but burns tokens
- Prevention: Catches issues early, but may be too rigid

### Q5: Source of Truth
Should database state or code schemas be authoritative?

Options:
- Database authoritative: Code adapts (dynamic enum loading)
- Code authoritative: DB must match (migrations enforce)
- Bidirectional: Validate both, escalate conflicts

## Immediate Action to Unblock

**Option A**: Fix database
```sql
UPDATE runs SET state='RUN_CREATED' WHERE state='READY';
```

**Option B**: Fix code
```python
# src/autopack/models.py
class RunState(str, Enum):
    READY = "READY"  # Add this
    QUEUED = "QUEUED"
    # ... rest
```

**Recommendation**: Option A (fix database) because:
- `READY` not a documented state in RunState enum
- Likely from manual database manipulation
- `RUN_CREATED` is the correct semantic equivalent

## Request for GPT-5.2

**Full analysis**: [BUILD-127-129_ROOT_CAUSE_ANALYSIS_FOR_GPT52.md](BUILD-127-129_ROOT_CAUSE_ANALYSIS_FOR_GPT52.md)

**Questions**:
1. Do you agree with root cause diagnosis?
2. Are there architectural issues I'm missing?
3. What should be prioritized differently?
4. How should Autopack bootstrap self-improvements when it can't run?
5. Recovery-focused vs prevention-focused - which philosophy?

**Goal**: Make Autopack smart enough to autonomously navigate these issues itself, enabling true self-improvement.
