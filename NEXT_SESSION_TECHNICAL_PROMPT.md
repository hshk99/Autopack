# BUILD-146 P12: Production Hardening & Automation - Technical Context

## Executive Summary

You are continuing BUILD-146 after the API split-brain fix (P11 Ops). The project has achieved the README "ideal state" for True Autonomy with observability. What remains is **staging validation and production hardening** - NOT new feature phases.

Your task: Implement 5 high-impact production-facing improvements to close operational loops and prepare for production rollout.

## Current State (as of 2025-12-31)

### What's Complete (BUILD-146 P11 Ops)
1. **Experiment Metadata** - Git commit SHA, branch, model mapping hash tracking for reproducibility
2. **Consolidated Dashboard** - Unified token metrics preventing double-counting across 4 categories
3. **Pattern Expansion** - Automated discovery of uncaught failure patterns from real data
4. **CI DATABASE_URL Enforcement** - Prevents schema pollution in SQLite default DB
5. **API Split-Brain Fix** - Production API now has all endpoints needed by run_parallel.py and autonomous_executor.py

### Architecture Context

**Two FastAPI Applications** (split-brain now RESOLVED):
- `src/backend/main.py` - Production API (PRIMARY control plane)
- `src/autopack/main.py` - Supervisor API (legacy, being phased out)

**Key Executors**:
- `src/autopack/autonomous_executor.py` - Single-phase executor (uses X-API-Key auth)
- `scripts/run_parallel.py` - Multi-phase parallel executor (uses Bearer token auth, supports `--executor api` mode)

**Database Models** (`src/autopack/models.py`):
- `Run` - Top-level execution container
- `Tier` - Grouping of related phases
- `Phase` - Individual work unit (states: QUEUED, EXECUTING, COMPLETE, FAILED)
- `PhaseMetrics` - Phase 6 P3 telemetry (token tracking, timing)
- `DashboardEvent` - Phase 6 P9 observability events

**Token Tracking** (4 categories, must not double-count):
1. `retrieval_tokens` - Context retrieval (grep/read operations)
2. `second_opinion_tokens` - Quality checks and validation
3. `evidence_request_tokens` - Follow-up evidence gathering
4. `base_tokens` - Core phase execution

**Phase States** (`PhaseState` enum):
- `QUEUED` - Ready to execute
- `EXECUTING` - Currently running
- `COMPLETE` - Successfully finished
- `FAILED` - Execution failed

**Run States** (`RunState` enum):
- `RUN_CREATED` - Initialized
- `PHASE_EXECUTION` - Running (NOT "EXECUTING" - that doesn't exist!)
- `DONE_SUCCESS` - All phases complete
- `DONE_FAILED_REQUIRES_HUMAN_REVIEW` - Failed, needs human intervention

### Recent Implementation Patterns

**Kill Switch Pattern** (from BUILD-146 P6):
```python
# Environment variable toggle (default OFF for safety)
ENABLE_FEATURE = os.getenv("AUTOPACK_ENABLE_FEATURE_NAME") == "1"

if ENABLE_FEATURE:
    # New functionality
else:
    # Safe default behavior
```

**Dual Authentication** (`src/backend/api/api_key_auth.py`):
```python
async def verify_api_key_or_bearer(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """Support both X-API-Key AND Bearer token for backward compatibility."""
    if os.getenv("TESTING") == "1":
        return "test-auth-token"

    if x_api_key:
        # Validate X-API-Key
        return x_api_key

    if authorization and authorization.credentials:
        # Validate Bearer token
        return authorization.credentials

    raise HTTPException(status_code=401, detail="Authentication required")
```

**Background Task Execution** (`src/backend/api/runs.py`):
```python
@router.post("/{run_id}/execute")
async def execute_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: str = Depends(verify_api_key_or_bearer)
):
    # Update run state
    run.state = RunState.PHASE_EXECUTION
    db.commit()

    # Background task to spawn subprocess
    def execute_in_background():
        try:
            # New session for background task
            with Session(db.bind) as session:
                # Do work...
                session.commit()
        except Exception as e:
            logger.error(f"Background task error: {e}", exc_info=True)

    background_tasks.add_task(execute_in_background)
    return {"status": "started"}
```

**Pattern Expansion** (`scripts/pattern_expansion.py`):
- Analyzes `dashboard_events` table for uncaught failure patterns
- Groups by similarity (edit distance + keyword matching)
- Outputs markdown report with actionable patterns
- Currently: Analysis only, no code generation

**Consolidated Metrics** (`src/backend/api/dashboard.py`):
```python
@router.get("/runs/{run_id}/consolidated-metrics")
def get_consolidated_metrics(run_id: str, db: Session = Depends(get_db)):
    """Prevent double-counting across 4 token categories."""
    # Query PhaseMetrics table
    metrics = db.query(PhaseMetrics).filter(PhaseMetrics.run_id == run_id).all()

    # Aggregate without double-counting
    total_retrieval = sum(m.retrieval_tokens or 0 for m in metrics)
    total_second_opinion = sum(m.second_opinion_tokens or 0 for m in metrics)
    # ... etc

    return {
        "retrieval_tokens": total_retrieval,
        "second_opinion_tokens": total_second_opinion,
        # ...
        "total_tokens": total_retrieval + total_second_opinion + ...
    }
```

## Your 5 Tasks (All Must Be Completed)

### Task 1: Rollout Playbook + Safety Rails

**Goal**: Create production readiness checklist and emergency kill switches

**Deliverables**:

1. **Staging Rollout Checklist** (`docs/STAGING_ROLLOUT.md`):
   - Required environment variables (DATABASE_URL, QDRANT_HOST, API keys)
   - Database migration steps (Alembic or manual ALTER TABLE commands)
   - Endpoint verification (smoke test all critical endpoints)
   - Rollback procedure (how to disable Phase 6 features)
   - Performance baseline (expected query times for consolidated metrics)

2. **Kill Switches** (add to relevant modules):
   - `AUTOPACK_ENABLE_PHASE6_METRICS` - Controls Phase 6 P3 telemetry collection (default: `"0"`)
   - `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` - Controls consolidated metrics dashboard endpoint (default: `"0"`)
   - Update `src/autopack/autonomous_executor.py` to check `AUTOPACK_ENABLE_PHASE6_METRICS`
   - Update `src/backend/api/dashboard.py` to check `AUTOPACK_ENABLE_CONSOLIDATED_METRICS`

3. **Health Check Endpoint** (`src/backend/api/health.py`):
   ```python
   @router.get("/health")
   def health_check(db: Session = Depends(get_db)):
       """Production health check with dependency validation."""
       # Check DB connection
       # Check Qdrant connection (if enabled)
       # Check kill switch states
       # Return status + versions
   ```

**Testing**:
- Verify kill switches default to OFF
- Verify health endpoint returns 200 when dependencies healthy
- Verify rollback procedure in test environment

**Files to Create/Modify**:
- `docs/STAGING_ROLLOUT.md` (NEW)
- `src/autopack/autonomous_executor.py` (add kill switch check)
- `src/backend/api/dashboard.py` (add kill switch check)
- `src/backend/api/health.py` (NEW)
- `tests/test_kill_switches.py` (NEW)

---

### Task 2: Pattern Expansion → PR Automation

**Goal**: Extend pattern expansion to auto-generate code stubs, tests, and backlog entries

**Current State**:
- `scripts/pattern_expansion.py` analyzes `dashboard_events` and outputs markdown reports
- Identifies 3-5 high-frequency failure patterns
- No code generation

**Enhancement Required**:

1. **Extend `scripts/pattern_expansion.py`** to generate:

   **a) Python Detector Stub** (`src/autopack/patterns/pattern_{id}.py`):
   ```python
   """Auto-generated pattern detector for: {pattern_summary}

   Pattern ID: {pattern_id}
   Occurrences: {count}
   Generated: {timestamp}
   """

   def detect_{pattern_id}(error_message: str, context: dict) -> bool:
       """Detect if error matches pattern: {pattern_summary}

       Args:
           error_message: Error string from exception
           context: Execution context (phase_id, builder_mode, etc)

       Returns:
           True if pattern detected
       """
       # TODO: Implement detection logic based on pattern analysis
       # Pattern keywords: {top_keywords}
       # Sample errors:
       # - {sample_error_1}
       # - {sample_error_2}
       pass

   def mitigate_{pattern_id}(phase_id: str, context: dict) -> dict:
       """Attempt to mitigate pattern: {pattern_summary}

       Args:
           phase_id: Phase ID where pattern occurred
           context: Execution context

       Returns:
           Mitigation result with success status and actions taken
       """
       # TODO: Implement mitigation strategy
       # Suggested approach: {mitigation_hint}
       pass
   ```

   **b) Pytest Skeleton** (`tests/patterns/test_pattern_{id}.py`):
   ```python
   """Tests for pattern detector: {pattern_summary}"""
   import pytest
   from autopack.patterns.pattern_{id} import detect_{pattern_id}, mitigate_{pattern_id}

   def test_detect_{pattern_id}_positive():
       """Test detection with known positive case."""
       # Sample from real data
       error_msg = "{sample_error_1}"
       context = {{"phase_id": "test-phase", "builder_mode": "builder"}}

       assert detect_{pattern_id}(error_msg, context) is True

   def test_detect_{pattern_id}_negative():
       """Test detection with known negative case."""
       error_msg = "Unrelated error message"
       context = {{"phase_id": "test-phase"}}

       assert detect_{pattern_id}(error_msg, context) is False

   def test_mitigate_{pattern_id}():
       """Test mitigation strategy."""
       result = mitigate_{pattern_id}("test-phase", {{"builder_mode": "builder"}})

       assert "success" in result
       # TODO: Add specific assertions based on mitigation strategy
   ```

   **c) Backlog Entry** (`docs/backlog/PATTERN_{id}.md`):
   ```markdown
   # Pattern {id}: {pattern_summary}

   **Status**: TODO
   **Priority**: {priority_based_on_frequency}
   **Occurrences**: {count} times in dataset
   **Generated**: {timestamp}

   ## Pattern Description

   {detailed_description_from_clustering}

   ## Sample Errors

   ```
   {sample_error_1}
   {sample_error_2}
   {sample_error_3}
   ```

   ## Detection Strategy

   Keywords: {top_keywords}
   Regex: {suggested_regex_pattern}

   ## Mitigation Ideas

   {mitigation_suggestions_based_on_context}

   ## Implementation Checklist

   - [ ] Implement detector in `src/autopack/patterns/pattern_{id}.py`
   - [ ] Add tests in `tests/patterns/test_pattern_{id}.py`
   - [ ] Integrate with autonomous_executor.py error handling
   - [ ] Add telemetry tracking for pattern hits
   - [ ] Update dashboard to show pattern statistics
   ```

2. **Pattern Registry** (`src/autopack/patterns/__init__.py`):
   ```python
   """Pattern detector registry."""
   from typing import Dict, Callable

   # Auto-import all pattern modules
   PATTERN_DETECTORS: Dict[str, Callable] = {}
   PATTERN_MITIGATORS: Dict[str, Callable] = {}

   # TODO: Auto-register patterns from generated modules
   ```

3. **Command-Line Flags** for `scripts/pattern_expansion.py`:
   ```bash
   python scripts/pattern_expansion.py \
     --run-id telemetry-collection-v7 \
     --generate-code \
     --output-dir src/autopack/patterns \
     --min-occurrences 3
   ```

**Constraints**:
- Only generate stubs for patterns with >= 3 occurrences
- Limit to top 5 patterns by frequency
- Don't modify autonomous_executor.py directly (just generate hooks)
- Include TODO comments for human review

**Testing**:
- Verify generated Python is syntactically valid
- Verify pytest skeletons can be imported
- Verify markdown is properly formatted

**Files to Create/Modify**:
- `scripts/pattern_expansion.py` (add code generation)
- `src/autopack/patterns/__init__.py` (NEW - registry)
- `src/autopack/patterns/pattern_*.py` (GENERATED - 3-5 files)
- `tests/patterns/test_pattern_*.py` (GENERATED - 3-5 files)
- `docs/backlog/PATTERN_*.md` (GENERATED - 3-5 files)

---

### Task 3: Data Quality + Performance Hardening

**Goal**: Ensure consolidated metrics dashboard is fast on large databases and doesn't return unbounded data

**Current Issues**:
- `/dashboard/runs/{run_id}/consolidated-metrics` queries entire `phase_metrics` table
- No pagination or limits
- No database indexes on common query patterns
- No query plan analysis

**Enhancements Required**:

1. **Add Database Indexes** (`scripts/migrations/add_performance_indexes.py`):
   ```python
   """Add indexes for dashboard query performance.

   IMPORTANT: This is a manual migration script, NOT Alembic.
   Run with: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="..." python scripts/migrations/add_performance_indexes.py
   """
   from sqlalchemy import create_index, Index
   from autopack.database import engine, SessionLocal
   from autopack.models import PhaseMetrics, DashboardEvent, Run, Phase

   def add_indexes():
       """Add performance indexes for common query patterns."""
       with engine.begin() as conn:
           # PhaseMetrics indexes
           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_id
               ON phase_metrics(run_id);
           """)

           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_phase_metrics_created_at
               ON phase_metrics(created_at DESC);
           """)

           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_created
               ON phase_metrics(run_id, created_at DESC);
           """)

           # DashboardEvent indexes
           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_dashboard_events_run_id
               ON dashboard_events(run_id);
           """)

           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_dashboard_events_event_type
               ON dashboard_events(event_type);
           """)

           # Phase indexes for status queries
           conn.execute("""
               CREATE INDEX IF NOT EXISTS idx_phases_run_state
               ON phases(run_id, state);
           """)

   if __name__ == "__main__":
       add_indexes()
       print("✅ Performance indexes added successfully")
   ```

2. **Add Pagination to Consolidated Metrics** (`src/backend/api/dashboard.py`):
   ```python
   @router.get("/runs/{run_id}/consolidated-metrics")
   def get_consolidated_metrics(
       run_id: str,
       limit: int = 1000,  # Default limit
       offset: int = 0,
       db: Session = Depends(get_db)
   ):
       """Get consolidated metrics with pagination."""
       if limit > 10000:
           raise HTTPException(status_code=400, detail="Limit cannot exceed 10000")

       # Check kill switch
       if os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1":
           raise HTTPException(status_code=503, detail="Consolidated metrics disabled")

       # Query with limit
       metrics = db.query(PhaseMetrics)\
           .filter(PhaseMetrics.run_id == run_id)\
           .order_by(PhaseMetrics.created_at.desc())\
           .limit(limit)\
           .offset(offset)\
           .all()

       # Aggregate...
   ```

3. **Query Plan Analysis** (add to `docs/STAGING_ROLLOUT.md`):
   ```sql
   -- Verify index usage for consolidated metrics
   EXPLAIN QUERY PLAN
   SELECT * FROM phase_metrics
   WHERE run_id = 'telemetry-collection-v7'
   ORDER BY created_at DESC
   LIMIT 1000;

   -- Should show: SEARCH phase_metrics USING INDEX idx_phase_metrics_run_created
   ```

4. **Optional: Retention Strategy** (`scripts/metrics_retention.py`):
   ```python
   """Prune old raw metrics while keeping aggregates.

   Strategy:
   - Keep raw PhaseMetrics for 30 days
   - Aggregate to daily summaries
   - Keep daily summaries forever
   """
   import os
   from datetime import datetime, timedelta
   from autopack.database import SessionLocal
   from autopack.models import PhaseMetrics

   RETENTION_DAYS = int(os.getenv("AUTOPACK_METRICS_RETENTION_DAYS", "30"))

   def prune_old_metrics():
       """Delete PhaseMetrics older than retention period."""
       cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)

       with SessionLocal() as session:
           deleted = session.query(PhaseMetrics)\
               .filter(PhaseMetrics.created_at < cutoff_date)\
               .delete(synchronize_session=False)

           session.commit()
           print(f"✅ Pruned {deleted} old metrics (older than {cutoff_date})")

   if __name__ == "__main__":
       prune_old_metrics()
   ```

**Testing**:
- Run migration script against SQLite test DB
- Run migration script against PostgreSQL test DB
- Verify indexes created with `PRAGMA index_list('phase_metrics')`
- Verify query plans use indexes
- Test pagination with large datasets

**Files to Create/Modify**:
- `scripts/migrations/add_performance_indexes.py` (NEW)
- `src/backend/api/dashboard.py` (add pagination + kill switch)
- `scripts/metrics_retention.py` (NEW - optional)
- `docs/STAGING_ROLLOUT.md` (add query plan verification)
- `tests/test_performance_indexes.py` (NEW)

---

### Task 4: A/B Results Persistence

**Goal**: Store A/B test results in database instead of JSON artifacts, with strict validity checks

**Current State**:
- A/B results stored in JSON artifacts only (`archive/ab_results/*.json`)
- Dashboard reads from JSON files
- Validity checks are warnings only (not enforced)
- No requirement for same git commit SHA or model mapping hash

**Enhancement Required**:

1. **New Database Model** (`src/autopack/models.py`):
   ```python
   class ABTestResult(Base):
       """A/B test comparison results.

       Stores pair comparisons between control and treatment runs
       with strict validity checks.
       """
       __tablename__ = "ab_test_results"

       id = Column(Integer, primary_key=True)
       test_id = Column(String, nullable=False, index=True)  # e.g., "telemetry-v5-vs-v6"

       # Run pair
       control_run_id = Column(String, ForeignKey("runs.id"), nullable=False)
       treatment_run_id = Column(String, ForeignKey("runs.id"), nullable=False)

       # Validity checks (MUST match for valid comparison)
       control_commit_sha = Column(String, nullable=False)
       treatment_commit_sha = Column(String, nullable=False)
       control_model_hash = Column(String, nullable=False)
       treatment_model_hash = Column(String, nullable=False)

       # Validity status
       is_valid = Column(Boolean, nullable=False, default=True)
       validity_errors = Column(JSON)  # List of validation failures

       # Metrics deltas
       token_delta = Column(Integer)  # treatment - control
       time_delta_seconds = Column(Float)  # treatment - control
       success_rate_delta = Column(Float)  # treatment - control (percentage points)

       # Aggregated results
       control_total_tokens = Column(Integer)
       treatment_total_tokens = Column(Integer)
       control_phases_complete = Column(Integer)
       treatment_phases_complete = Column(Integer)
       control_phases_failed = Column(Integer)
       treatment_phases_failed = Column(Integer)

       # Metadata
       created_at = Column(DateTime, default=datetime.utcnow)
       created_by = Column(String)  # Script or user that generated result

       # Indexes
       __table_args__ = (
           Index('idx_ab_test_id', 'test_id'),
           Index('idx_ab_validity', 'is_valid'),
       )
   ```

2. **Migration Script** (`scripts/migrations/add_ab_test_results.py`):
   ```python
   """Add ab_test_results table."""
   from autopack.database import engine
   from autopack.models import Base, ABTestResult

   def migrate():
       """Create ab_test_results table."""
       ABTestResult.__table__.create(engine, checkfirst=True)
       print("✅ ab_test_results table created")

   if __name__ == "__main__":
       migrate()
   ```

3. **A/B Analysis Script** (`scripts/ab_analysis.py`):
   ```python
   """Analyze and persist A/B test results.

   Usage:
       python scripts/ab_analysis.py \
         --control-run telemetry-v5 \
         --treatment-run telemetry-v6 \
         --test-id v5-vs-v6
   """
   import argparse
   from autopack.database import SessionLocal
   from autopack.models import Run, Phase, ABTestResult

   def validate_pair(control: Run, treatment: Run) -> tuple[bool, list]:
       """Strict validation for A/B pair.

       Returns:
           (is_valid, error_list)
       """
       errors = []

       # MUST have same commit SHA (not just warning)
       if control.git_commit_sha != treatment.git_commit_sha:
           errors.append(f"Commit SHA mismatch: {control.git_commit_sha} != {treatment.git_commit_sha}")

       # MUST have same model mapping hash
       if control.model_mapping_hash != treatment.model_mapping_hash:
           errors.append(f"Model hash mismatch: {control.model_mapping_hash} != {treatment.model_mapping_hash}")

       # SHOULD have same phase count (warning, not error)
       control_phases = len(control.phases)
       treatment_phases = len(treatment.phases)
       if control_phases != treatment_phases:
           errors.append(f"WARNING: Phase count mismatch: {control_phases} != {treatment_phases}")

       is_valid = len([e for e in errors if not e.startswith("WARNING")]) == 0
       return is_valid, errors

   def calculate_deltas(control: Run, treatment: Run) -> dict:
       """Calculate metric deltas."""
       control_tokens = sum(p.tokens_used or 0 for p in control.phases)
       treatment_tokens = sum(p.tokens_used or 0 for p in treatment.phases)

       # ... calculate other deltas

       return {
           "token_delta": treatment_tokens - control_tokens,
           # ... other deltas
       }

   def persist_result(test_id: str, control: Run, treatment: Run, session):
       """Persist A/B result to database."""
       is_valid, errors = validate_pair(control, treatment)
       deltas = calculate_deltas(control, treatment)

       result = ABTestResult(
           test_id=test_id,
           control_run_id=control.id,
           treatment_run_id=treatment.id,
           control_commit_sha=control.git_commit_sha,
           treatment_commit_sha=treatment.git_commit_sha,
           is_valid=is_valid,
           validity_errors=errors,
           **deltas
       )

       session.add(result)
       session.commit()

       print(f"✅ A/B result persisted (valid={is_valid})")
       if errors:
           print("⚠️ Validation errors:")
           for e in errors:
               print(f"  - {e}")
   ```

4. **Dashboard Endpoint** (`src/backend/api/dashboard.py`):
   ```python
   @router.get("/ab-results")
   def get_ab_results(
       test_id: Optional[str] = None,
       valid_only: bool = True,
       db: Session = Depends(get_db)
   ):
       """Get A/B test results from database (not JSON files)."""
       query = db.query(ABTestResult)

       if test_id:
           query = query.filter(ABTestResult.test_id == test_id)

       if valid_only:
           query = query.filter(ABTestResult.is_valid == True)

       results = query.order_by(ABTestResult.created_at.desc()).all()

       return {
           "results": [
               {
                   "test_id": r.test_id,
                   "control_run_id": r.control_run_id,
                   "treatment_run_id": r.treatment_run_id,
                   "is_valid": r.is_valid,
                   "token_delta": r.token_delta,
                   # ... other fields
               }
               for r in results
           ]
       }
   ```

**Testing**:
- Create test runs with matching commit SHAs
- Create test runs with mismatched commit SHAs (should mark invalid)
- Verify database persistence
- Verify dashboard endpoint returns correct data

**Files to Create/Modify**:
- `src/autopack/models.py` (add ABTestResult model)
- `scripts/migrations/add_ab_test_results.py` (NEW)
- `scripts/ab_analysis.py` (NEW)
- `src/backend/api/dashboard.py` (add A/B endpoint)
- `tests/test_ab_results_persistence.py` (NEW)

---

### Task 5: Replay Campaign

**Goal**: Re-run previously failed runs/phases with Phase 6 features enabled, capturing metrics and patterns

**Current State**:
- Many failed runs exist in database
- Phase 6 features exist but not widely tested on real workloads
- No automated way to replay failed work with new features

**Enhancement Required**:

1. **Replay Script** (`scripts/replay_campaign.py`):
   ```python
   """Replay failed runs with Phase 6 features enabled.

   Usage:
       # Replay specific run
       python scripts/replay_campaign.py --run-id failed-run-123

       # Replay all failed runs from date range
       python scripts/replay_campaign.py \
         --from-date 2025-12-01 \
         --to-date 2025-12-31 \
         --state FAILED

       # Dry run (don't execute)
       python scripts/replay_campaign.py --state FAILED --dry-run
   """
   import argparse
   import asyncio
   from datetime import datetime
   from autopack.database import SessionLocal
   from autopack.models import Run, RunState

   async def replay_run(run_id: str, executor_mode: str = "api"):
       """Replay a single run with Phase 6 features enabled.

       Args:
           run_id: Original run ID to replay
           executor_mode: "api" or "local" (prefer "api" for async execution)
       """
       # Clone run with new ID
       new_run_id = f"{run_id}-replay-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

       # TODO: Clone run, tiers, phases to new run_id
       # TODO: Set Phase 6 env vars in environment
       # TODO: Call scripts/run_parallel.py --executor api --run-id new_run_id
       # TODO: Poll for completion
       # TODO: Generate comparison report

   async def find_failed_runs(from_date: str, to_date: str) -> list:
       """Find failed runs in date range."""
       with SessionLocal() as session:
           runs = session.query(Run).filter(
               Run.state == RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW,
               Run.created_at >= datetime.fromisoformat(from_date),
               Run.created_at <= datetime.fromisoformat(to_date)
           ).all()

           return [r.id for r in runs]

   async def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--run-id", help="Specific run to replay")
       parser.add_argument("--from-date", help="Start date (ISO format)")
       parser.add_argument("--to-date", help="End date (ISO format)")
       parser.add_argument("--state", default="FAILED", help="Run state filter")
       parser.add_argument("--dry-run", action="store_true")
       parser.add_argument("--executor", default="api", choices=["api", "local"])
       args = parser.parse_args()

       # Collect runs to replay
       if args.run_id:
           run_ids = [args.run_id]
       else:
           run_ids = await find_failed_runs(args.from_date, args.to_date)

       print(f"Found {len(run_ids)} runs to replay")

       if args.dry_run:
           print("DRY RUN - would replay:")
           for run_id in run_ids:
               print(f"  - {run_id}")
           return

       # Replay in parallel (batches of 5)
       for i in range(0, len(run_ids), 5):
           batch = run_ids[i:i+5]
           tasks = [replay_run(run_id, args.executor) for run_id in batch]
           await asyncio.gather(*tasks)

   if __name__ == "__main__":
       asyncio.run(main())
   ```

2. **Environment Setup** (ensure Phase 6 flags enabled):
   ```bash
   export AUTOPACK_ENABLE_PHASE6_METRICS="1"
   export AUTOPACK_ENABLE_CONSOLIDATED_METRICS="1"
   export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
   export QDRANT_HOST="http://localhost:6333"
   ```

3. **Comparison Report** (generate after replay):
   ```python
   def generate_comparison_report(original_run_id: str, replay_run_id: str):
       """Compare original vs replay results."""
       with SessionLocal() as session:
           original = session.query(Run).filter(Run.id == original_run_id).first()
           replay = session.query(Run).filter(Run.id == replay_run_id).first()

           report = {
               "original_run_id": original_run_id,
               "replay_run_id": replay_run_id,
               "original_state": original.state.value,
               "replay_state": replay.state.value,
               "original_tokens": original.tokens_used,
               "replay_tokens": replay.tokens_used,
               "token_delta": replay.tokens_used - original.tokens_used,
               # ... more metrics
           }

           # Save to archive
           output_path = f"archive/replay_results/{replay_run_id}_comparison.json"
           with open(output_path, "w") as f:
               json.dump(report, f, indent=2)

           print(f"✅ Comparison report saved to {output_path}")
   ```

4. **Pattern Expansion Integration**:
   ```bash
   # After replay campaign completes, run pattern expansion
   python scripts/pattern_expansion.py \
     --run-id {replay_run_id} \
     --generate-code \
     --output-dir src/autopack/patterns
   ```

**Testing**:
- Test replay with single failed run (dry-run mode)
- Test replay with date range filter
- Verify Phase 6 env vars are set in replayed runs
- Verify comparison reports are generated

**Files to Create/Modify**:
- `scripts/replay_campaign.py` (NEW)
- `archive/replay_results/` (NEW directory)
- `tests/test_replay_campaign.py` (NEW)

---

## Critical Constraints

**MUST FOLLOW** (from BUILD-146 patterns):

1. **Windows Compatibility**:
   - Use `Path()` objects, not string concatenation
   - Handle CRLF line endings
   - Use `sys.executable` for Python subprocess calls
   - Test on Windows if possible

2. **PostgreSQL + SQLite Support**:
   - All SQL must work on both databases
   - Use SQLAlchemy ORM when possible
   - Test migrations on both databases
   - Use `IF NOT EXISTS` for CREATE INDEX statements

3. **No Double-Counting Tokens**:
   - 4 categories: retrieval, second_opinion, evidence_request, base
   - Total = sum of 4 categories (not sum of all phase.tokens_used)
   - Document which category each token collection belongs to

4. **No New LLM Calls**:
   - All improvements are operational/infrastructure
   - Don't add new Claude API calls
   - Don't change autonomous_executor.py prompts

5. **Opt-In by Default**:
   - All new features OFF by default (kill switches)
   - Require explicit environment variable to enable
   - Document in STAGING_ROLLOUT.md

6. **Test Coverage**:
   - Every new endpoint needs integration test
   - Every migration needs test on SQLite + Postgres
   - Every kill switch needs test verifying default=OFF

7. **Minimal Refactor**:
   - Don't reorganize existing code
   - Don't rename existing functions
   - Add new code in new files when possible
   - Keep changes small and focused

## Success Criteria

**You will be done when**:

1. ✅ `docs/STAGING_ROLLOUT.md` exists with complete checklist
2. ✅ Kill switches added and default to OFF
3. ✅ Health check endpoint returns 200
4. ✅ Pattern expansion generates code stubs, tests, and backlog entries
5. ✅ Database indexes added with migration script
6. ✅ Consolidated metrics has pagination and kill switch
7. ✅ ABTestResult model exists with migration
8. ✅ A/B analysis script persists to database
9. ✅ Replay campaign script can replay failed runs
10. ✅ All tests pass: `PYTHONUTF8=1 PYTHONPATH=src pytest tests/ -v`
11. ✅ BUILD_HISTORY.md updated with BUILD-146 P12 entry
12. ✅ DEBUG_LOG.md updated with implementation notes
13. ✅ Changes committed with descriptive message
14. ✅ Changes pushed to `phase-a-p11-observability` branch

## File Structure Reference

```
c:/dev/Autopack/
├── src/
│   ├── autopack/
│   │   ├── models.py (add ABTestResult model here)
│   │   ├── autonomous_executor.py (add kill switch check)
│   │   ├── patterns/
│   │   │   ├── __init__.py (NEW - pattern registry)
│   │   │   └── pattern_*.py (GENERATED by pattern_expansion.py)
│   │   └── main.py (legacy Supervisor API)
│   └── backend/
│       ├── main.py (production API)
│       └── api/
│           ├── dashboard.py (add kill switch, pagination, A/B endpoint)
│           ├── health.py (NEW - health check)
│           └── runs.py (already has execute/status endpoints)
├── scripts/
│   ├── pattern_expansion.py (extend with code generation)
│   ├── ab_analysis.py (NEW - A/B persistence)
│   ├── replay_campaign.py (NEW - replay failed runs)
│   ├── metrics_retention.py (NEW - optional)
│   └── migrations/
│       ├── add_performance_indexes.py (NEW)
│       └── add_ab_test_results.py (NEW)
├── tests/
│   ├── test_kill_switches.py (NEW)
│   ├── test_performance_indexes.py (NEW)
│   ├── test_ab_results_persistence.py (NEW)
│   ├── test_replay_campaign.py (NEW)
│   └── patterns/
│       └── test_pattern_*.py (GENERATED)
├── docs/
│   ├── STAGING_ROLLOUT.md (NEW - rollout checklist)
│   └── backlog/
│       └── PATTERN_*.md (GENERATED)
├── archive/
│   └── replay_results/ (NEW directory)
├── BUILD_HISTORY.md (update with P12 entry)
└── DEBUG_LOG.md (update with session notes)
```

## Testing Commands

```bash
# Run all tests
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" pytest tests/ -v

# Test specific modules
PYTHONUTF8=1 PYTHONPATH=src pytest tests/test_kill_switches.py -v
PYTHONUTF8=1 PYTHONPATH=src pytest tests/test_ab_results_persistence.py -v

# Run migration on SQLite
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///test.db" python scripts/migrations/add_performance_indexes.py

# Run migration on Postgres
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" python scripts/migrations/add_performance_indexes.py

# Generate pattern stubs
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/pattern_expansion.py --run-id telemetry-collection-v7 --generate-code

# Run A/B analysis
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/ab_analysis.py --control-run v5 --treatment-run v6 --test-id v5-vs-v6

# Replay failed runs (dry run)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/replay_campaign.py --state FAILED --dry-run
```

## Git Workflow

```bash
# You should already be on this branch
git checkout phase-a-p11-observability

# After completing all tasks
git add .
git commit -m "feat: BUILD-146 P12 Production Hardening - Rollout+Patterns+Performance+AB+Replay"
git push origin phase-a-p11-observability
```

## Questions to Resolve

If you encounter ambiguity:

1. **Pattern generation format**: If unclear what format pattern stubs should have, use the template provided above
2. **Index strategy**: If unclear which indexes to add, focus on run_id + created_at combinations
3. **A/B validity**: If unclear what makes a valid comparison, REQUIRE same commit SHA and model hash
4. **Replay strategy**: If unclear how to replay, clone the run with new ID and use run_parallel.py --executor api

## Final Notes

- This is **production hardening**, not new features
- Focus on **operational maturity** (reliability, performance, observability)
- Keep kill switches **OFF by default**
- Document everything in `docs/STAGING_ROLLOUT.md`
- Test on both SQLite and PostgreSQL
- Windows compatibility is critical

Good luck! 🚀
