# BUILD-127/129 Root Cause Analysis for GPT-5.2 Second Opinion

## Executive Summary

While attempting to run BUILD-127 (self-healing governance) and BUILD-129 (token budget intelligence) in parallel, I encountered multiple cascading failures that prevented autonomous execution. This report analyzes the root causes and identifies what capabilities Autopack needs to autonomously navigate these issues itself.

**Date**: 2025-12-23
**Context**: Parallel execution of BUILD-127 (retry with GPT-5.2's token escalation fix) and BUILD-129 (self-improvement implementing 4-layer token budget policy)
**Outcome**: Both builds stuck in error loops, unable to execute

---

## Issues Encountered

### Issue #1: Invalid Enum Value Causing API 500 Errors

**Symptom**: Both executors stuck in retry loop with `500 Internal Server Error` from API endpoint `/runs/{run_id}`

**Root Cause**: Database schema/enum mismatch
- Database contains runs with `state='READY'`
- `RunState` enum in [models.py:23-38](src/autopack/models.py#L23-L38) does NOT have `READY` value
- Valid enum values: `QUEUED`, `PLAN_BOOTSTRAP`, `RUN_CREATED`, `PHASE_EXECUTION`, `GATE`, `CI_RUNNING`, `SNAPSHOT_CREATED`, `DONE_SUCCESS`, `DONE_FAILED_*`
- When API tries to deserialize run from database via SQLAlchemy ORM:
  ```python
  run.state.value  # Fails with: LookupError: 'READY' is not among the defined enum values
  ```

**Evidence**:
```
BUILD-127 run data:
  state: READY  ← Database value

RunState enum (models.py):
  QUEUED, PLAN_BOOTSTRAP, RUN_CREATED, ...  ← No 'READY' value

Error: 'READY' is not among the defined enum values. Enum name: runstate
```

**Impact**: Critical - API endpoint returns 500, executor cannot fetch run status, infinite retry loop

---

### Issue #2: Missing Run Entry for BUILD-129

**Symptom**: Initially BUILD-129 phase existed in database but had no corresponding run entry

**Root Cause**: Manual database creation workflow confusion
- I created BUILD-129 phase directly in phases table
- Forgot to create corresponding entry in runs table
- Executor requires both run AND phase records to function
- API endpoint `/runs/{run_id}` failed with 404 because run didn't exist

**Evidence**:
```
Initial state:
  runs table: build127-... (exists), build129-... (MISSING)
  phases table: build127-phase1-..., build129-phase1-...

Error: 404 Client Error: Not Found for url: http://localhost:8000/runs/build129-token-budget-intelligence
```

**Resolution**: Fixed by creating run entry via SQL INSERT, but this revealed Issue #1

---

### Issue #3: Run ID vs Phase ID Confusion

**Symptom**: BUILD-129 initially used same ID for both run and phase (`build129-phase1-output-size-predictor`)

**Root Cause**: Unclear naming convention for single-phase runs
- BUILD-127: `run_id = phase_id = "build127-phase1-self-healing-governance"`
- BUILD-129: Should run_id be the phase ID or a parent ID?
- API routing expects `run_id` that contains phases as children
- When `run_id == phase_id`, unclear if this is a run or a phase

**Evidence**:
```python
# Confusing structure - is this ID for run or phase?
run_id = "build129-phase1-output-size-predictor"  # Looks like a phase ID!

# vs clearer structure
run_id = "build129-token-budget-intelligence"  # Parent run
phase_id = "build129-phase1-output-size-predictor"  # Child phase
```

**Resolution**: Renamed BUILD-129 run to `build129-token-budget-intelligence` (parent), kept phase as `build129-phase1-output-size-predictor` (child)

---

### Issue #4: No API Endpoint for Run Creation

**Symptom**: `POST /run/create` returned 404 Not Found

**Root Cause**: API endpoint doesn't exist
- [src/backend/api/runs.py](src/backend/api/runs.py) only implements 3 endpoints:
  - `GET /runs/{run_id}` - fetch run
  - `PUT /runs/{run_id}/phases/{phase_id}` - update phase
  - `POST /runs/{run_id}/phases/{phase_id}/builder_result` - submit results
- Missing: `POST /runs` (create run), `POST /runs/{run_id}/phases` (create phase)
- Commented in file: "This is a bootstrap implementation. Once functional, Autopack will autonomously build the full REST API"

**Workaround**: Direct SQL INSERT into database bypassing API

---

### Issue #5: Complex Database Schema with Many NOT NULL Constraints

**Symptom**: Multiple `sqlite3.IntegrityError: NOT NULL constraint failed` errors during manual run creation

**Root Cause**: Extensive schema with many required fields, unclear which are truly required
- Runs table: 20 columns, 15+ NOT NULL constraints
- Phases table: 25+ columns, 18+ NOT NULL constraints
- Trial-and-error required to discover all required fields:
  - Missing `updated_at` → Error
  - Missing `token_cap, max_phases, max_duration_minutes` → Error
  - Missing `tokens_used, ci_runs_used, minor/major_issues_count` → Error
  - Missing `promotion_eligible_to_main, debt_status` → Error
  - phases table: Missing `tier_id, builder_attempts, auditor_attempts, retry_attempt, revision_epoch, escalation_level` → Error

**Example**:
```python
# Required fields not obvious from schema documentation
cursor.execute('''
    INSERT INTO runs (
        id, state, created_at, updated_at,  # These 4 obvious
        safety_profile, run_scope, token_cap, max_phases, max_duration_minutes,  # Needed to avoid errors
        tokens_used, ci_runs_used, minor_issues_count, major_issues_count,  # Default to 0?
        promotion_eligible_to_main, debt_status, goal_anchor  # Which are truly required?
    ) VALUES (...)
''')
```

---

### Issue #6: Phase Scope Structure Confusion

**Symptom**: `sqlite3.OperationalError: table phases has no column named goal`

**Root Cause**: Phase `goal` goes inside `scope` JSON, not as separate column
- Expected: `INSERT INTO phases (phase_id, goal, scope, ...) VALUES (...)`
- Actual: `INSERT INTO phases (phase_id, scope, ...) VALUES (..., '{"goal": "...", "deliverables": [...]}', ...)`
- `scope` column is JSON containing: `goal`, `deliverables`, `protected_paths`, `read_only_context`
- This structure not documented in schema

---

## What Would Make Autopack Smart Enough to Self-Navigate?

### 1. **Schema Validation and Self-Repair** (CRITICAL)

**Problem**: Invalid database states silently accumulate (e.g., `state='READY'` when enum doesn't have `READY`)

**Solution**: Autopack needs:
- **Startup Schema Validator**: On executor init, run `SELECT DISTINCT state FROM runs` and validate all values against `RunState` enum
  - If invalid value found: LOG ERROR with remediation suggestion
  - Auto-fix: `UPDATE runs SET state='RUN_CREATED' WHERE state='READY'` (map invalid → valid)
  - Add to DEBUG_JOURNAL.md with escalation if auto-fix unsafe

```python
# Pseudo-code
class SchemaValidator:
    def validate_on_startup(self):
        """Validate database state matches code expectations"""
        invalid_states = self.db.query("SELECT id, state FROM runs WHERE state NOT IN ?", RunState.values())
        if invalid_states:
            for run_id, bad_state in invalid_states:
                logger.error(f"[Schema] Run {run_id} has invalid state: {bad_state}")
                logger.error(f"  Valid states: {list(RunState.values())}")

                # Attempt auto-repair
                closest_match = self.fuzzy_match(bad_state, RunState.values())
                logger.info(f"  Suggesting: {bad_state} → {closest_match}")

                if self.is_safe_to_auto_fix(run_id):
                    self.db.execute("UPDATE runs SET state=? WHERE id=?", closest_match, run_id)
                    log_fix(f"Auto-repaired invalid state: {bad_state} → {closest_match}")
                else:
                    report_error(f"Manual intervention required: {run_id} has invalid state {bad_state}")
```

**Benefit**: Prevents silent failures, provides actionable error messages, auto-repairs safe cases

---

### 2. **API Endpoint Discovery and Fallback** (HIGH PRIORITY)

**Problem**: Executor assumes API endpoint exists (`POST /run/create`), no fallback when 404

**Solution**: Autopack needs:
- **Endpoint Discovery**: Introspect API on startup, cache available endpoints
- **Graceful Degradation**: If endpoint missing, fall back to direct database access
- **Self-Documentation**: API should expose OpenAPI spec at `/openapi.json`

```python
class APIClient:
    def __init__(self):
        self.available_endpoints = self.discover_endpoints()

    def discover_endpoints(self):
        """Query API for available endpoints"""
        try:
            spec = requests.get(f"{API_URL}/openapi.json").json()
            return {path: methods for path, methods in spec['paths'].items()}
        except:
            # Fallback: try common endpoints and cache which work
            return self.probe_common_endpoints()

    def create_run(self, plan):
        """Create run with fallback strategy"""
        if "POST /runs" in self.available_endpoints:
            return self._create_via_api(plan)
        else:
            logger.warning("[API] POST /runs not available, falling back to direct DB")
            return self._create_via_database(plan)
```

**Benefit**: Executor works even with incomplete API, gracefully degrades, logs gaps for future builds

---

### 3. **Smart ID Convention Inference** (MEDIUM PRIORITY)

**Problem**: Unclear whether single-phase runs should have `run_id == phase_id` or distinct IDs

**Solution**: Autopack needs:
- **Convention Detector**: Analyze existing runs in database, infer ID patterns
- **Validator**: When creating run, check if ID structure matches convention
- **Documentation Generator**: Auto-generate ID convention rules from observed patterns

```python
class IDConventionDetector:
    def infer_convention(self):
        """Learn ID conventions from existing runs"""
        runs = self.db.query("SELECT id, (SELECT COUNT(*) FROM phases WHERE run_id=runs.id) as phase_count FROM runs")

        patterns = {
            'single_phase_same_id': [],  # run_id == phase_id
            'single_phase_parent_child': [],  # run_id = "build-X", phase_id = "build-X-phase1"
            'multi_phase_parent_child': [],
        }

        for run_id, phase_count in runs:
            phases = self.db.query(f"SELECT phase_id FROM phases WHERE run_id='{run_id}'")
            if phase_count == 1:
                if run_id == phases[0]:
                    patterns['single_phase_same_id'].append(run_id)
                else:
                    patterns['single_phase_parent_child'].append((run_id, phases[0]))

        # Determine dominant pattern
        if len(patterns['single_phase_parent_child']) > len(patterns['single_phase_same_id']):
            self.convention = "parent_child"
        else:
            self.convention = "same_id"

        logger.info(f"[IDConvention] Inferred: {self.convention}")
        return self.convention

    def validate_id(self, run_id, phase_id):
        """Check if ID structure matches convention"""
        if self.convention == "parent_child" and run_id == phase_id:
            logger.warning(f"[IDConvention] run_id==phase_id violates convention (expected parent-child)")
            return False
        return True
```

**Benefit**: Consistent ID structures, automatic validation, self-documenting

---

### 4. **Required Fields Auto-Discovery** (HIGH PRIORITY)

**Problem**: NOT NULL constraints cause errors, unclear which fields are required without trial-and-error

**Solution**: Autopack needs:
- **Schema Introspector**: Query database schema for NOT NULL constraints
- **Default Value Generator**: Provide sensible defaults for all required fields
- **Validation Pre-flight**: Before INSERT, check all NOT NULL columns have values

```python
class SchemaIntrospector:
    def get_required_fields(self, table_name):
        """Get all NOT NULL columns for a table"""
        schema = self.db.execute(f"PRAGMA table_info({table_name})")
        required = {}
        for col in schema:
            col_name, col_type, not_null, default_value = col[1], col[2], col[3], col[4]
            if not_null and default_value is None:
                required[col_name] = self.infer_default(col_name, col_type)
        return required

    def infer_default(self, col_name, col_type):
        """Infer sensible default for a column"""
        defaults = {
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'tokens_used': 0,
            'builder_attempts': 0,
            'state': 'QUEUED',  # or first valid enum value
            # ... more patterns
        }
        if col_name in defaults:
            return defaults[col_name]
        elif 'count' in col_name.lower():
            return 0
        elif col_type.lower().startswith('int'):
            return 0
        elif col_type.lower().startswith('bool'):
            return False
        else:
            return None  # Flag for manual intervention

    def validate_insert(self, table_name, values):
        """Validate all required fields present before INSERT"""
        required = self.get_required_fields(table_name)
        missing = [k for k in required if k not in values]
        if missing:
            logger.error(f"[Schema] Missing required fields for {table_name}: {missing}")
            logger.error(f"  Suggested defaults: {{{k: required[k] for k in missing}}}")
            raise ValueError(f"Missing required fields: {missing}")
```

**Benefit**: No more trial-and-error for required fields, auto-completion of sensible defaults, clear error messages

---

### 5. **Embedded Documentation in Database** (MEDIUM PRIORITY)

**Problem**: `scope` JSON structure not documented, unclear that `goal` goes inside `scope`

**Solution**: Autopack needs:
- **Schema Comments**: SQLite supports comments via `--` but not in table definitions; use separate documentation table
- **Example Data**: Store example rows in `schema_examples` table
- **JSON Schema Validation**: For JSON columns like `scope`, validate against JSON schema

```sql
-- Schema documentation table
CREATE TABLE schema_documentation (
    table_name TEXT NOT NULL,
    column_name TEXT,
    description TEXT,
    example_value TEXT,
    json_schema TEXT,  -- For JSON columns
    PRIMARY KEY (table_name, column_name)
);

-- Example entries
INSERT INTO schema_documentation VALUES (
    'phases', 'scope',
    'JSON containing goal, deliverables, protected_paths, read_only_context',
    '{"goal": "Implement feature X", "deliverables": ["src/foo.py"], "protected_paths": ["src/core/"]}',
    '{"type": "object", "required": ["goal", "deliverables"], "properties": {...}}'
);
```

```python
class ScopeBuilder:
    def __init__(self):
        self.schema = self.load_json_schema('phases', 'scope')

    def build_scope(self, goal, deliverables, protected_paths=None, read_only_context=None):
        """Build phase scope with validation"""
        scope = {
            "goal": goal,
            "deliverables": deliverables,
            "protected_paths": protected_paths or [],
            "read_only_context": read_only_context or [],
        }
        self.validate(scope)
        return json.dumps(scope)

    def validate(self, scope):
        """Validate scope against JSON schema"""
        jsonschema.validate(scope, self.schema)
```

**Benefit**: Self-documenting database, validation at insertion time, examples available at runtime

---

### 6. **Diagnostic Error Messages with Remediation** (CRITICAL)

**Problem**: Errors like "500 Internal Server Error" or "NOT NULL constraint failed: runs.token_cap" lack context and remediation

**Solution**: Autopack needs:
- **Error Context Enrichment**: Catch low-level errors, add high-level context
- **Remediation Suggestions**: For common errors, suggest fixes
- **Link to Documentation**: Reference relevant docs/examples

```python
class DiagnosticErrorHandler:
    def handle_api_error(self, response, operation):
        """Enrich API errors with diagnostics"""
        if response.status_code == 500:
            # Try to get more detail
            run_id = extract_run_id_from_url(response.url)
            db_state = self.db.query(f"SELECT state FROM runs WHERE id='{run_id}'")[0]

            logger.error(f"[API] 500 error for {operation}")
            logger.error(f"  URL: {response.url}")
            logger.error(f"  Run {run_id} has state: {db_state}")

            # Check if state is valid
            if db_state not in RunState.values():
                logger.error(f"  ❌ ROOT CAUSE: Invalid state '{db_state}' in database")
                logger.error(f"  Valid states: {list(RunState.values())}")
                logger.error(f"  REMEDIATION: Update database or add '{db_state}' to RunState enum")
                logger.error(f"    SQL: UPDATE runs SET state='RUN_CREATED' WHERE id='{run_id}'")
                logger.error(f"    Code: Add {db_state} to src/autopack/models.py:RunState")

    def handle_db_error(self, error, operation):
        """Enrich database errors with remediation"""
        if "NOT NULL constraint failed" in str(error):
            match = re.search(r'NOT NULL constraint failed: (\w+)\.(\w+)', str(error))
            if match:
                table, column = match.groups()
                required_fields = self.introspector.get_required_fields(table)

                logger.error(f"[Database] NOT NULL constraint violation")
                logger.error(f"  Table: {table}")
                logger.error(f"  Column: {column}")
                logger.error(f"  REMEDIATION: Provide value for '{column}'")
                logger.error(f"    Suggested default: {required_fields.get(column, 'unknown')}")
                logger.error(f"    All required fields for {table}: {list(required_fields.keys())}")
```

**Benefit**: Errors become actionable, faster root cause diagnosis, reduces debugging time

---

### 7. **Autonomous Run Creation Agent** (HIGH PRIORITY)

**Problem**: Creating runs manually requires deep knowledge of schema, API, conventions

**Solution**: Autopack needs:
- **RunBuilder Agent**: High-level interface for run creation
- **Validation Pipeline**: Check all constraints before committing
- **API-First with DB Fallback**: Try API, fall back to database if needed

```python
class AutonomousRunBuilder:
    """Smart run creator that handles all complexity"""

    def create_run(self, plan: Dict) -> str:
        """Create run from high-level plan, handling all details"""
        # 1. Validate plan structure
        self.validate_plan(plan)

        # 2. Infer ID convention
        run_id = self.generate_run_id(plan)

        # 3. Prepare run data with all required fields
        run_data = self.prepare_run_data(plan, run_id)

        # 4. Prepare phase data with all required fields
        phases_data = [self.prepare_phase_data(p, run_id, idx) for idx, p in enumerate(plan['phases'])]

        # 5. Validate before creation
        self.validate_run_data(run_data)
        for phase in phases_data:
            self.validate_phase_data(phase)

        # 6. Try API first, fall back to database
        try:
            if self.api.has_endpoint('POST /runs'):
                return self.create_via_api(run_data, phases_data)
            else:
                logger.info("[RunBuilder] POST /runs not available, using database")
                return self.create_via_database(run_data, phases_data)
        except Exception as e:
            logger.error(f"[RunBuilder] Failed to create run: {e}")
            self.diagnostics.handle_error(e, "create_run")
            raise

    def prepare_run_data(self, plan, run_id):
        """Prepare run data with ALL required fields"""
        required = self.introspector.get_required_fields('runs')

        data = {
            'id': run_id,
            'state': 'RUN_CREATED',  # Use valid enum value
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'goal_anchor': plan.get('goal', '')[:200],  # Truncate to reasonable length
            # Auto-fill all other required fields
            **{k: v for k, v in required.items() if k not in data}
        }

        return data
```

**Benefit**: Run creation becomes one-liner, all complexity hidden, handles edge cases automatically

---

## Recommendations for GPT-5.2 Review

### Question 1: **Priority Assessment**
Which of these 7 capabilities should be implemented first for maximum impact on autonomous execution reliability?

My ranking:
1. **Schema Validation & Self-Repair** (#1) - Prevents silent failures
2. **Diagnostic Error Messages** (#6) - Accelerates all debugging
3. **Required Fields Auto-Discovery** (#4) - Eliminates trial-and-error
4. **API Endpoint Discovery** (#2) - Graceful degradation
5. **Autonomous Run Creation Agent** (#7) - Integrates above capabilities
6. **Smart ID Convention Inference** (#3) - Nice-to-have validation
7. **Embedded Documentation** (#5) - Long-term maintainability

### Question 2: **Architectural Concerns**
Are there architectural issues in the current design that make these problems inevitable?

Concerns I see:
- **Enum values hardcoded in two places**: Database as string, code as enum → drift
- **API as thin wrapper over ORM**: ORM errors bubble up as 500, not caught/translated
- **No schema migration strategy**: Adding/removing enum values requires manual DB updates
- **Heavy coupling to database state**: Executor can't function if DB state invalid

### Question 3: **Self-Improvement Paradox**
BUILD-129 aims to implement token budget improvements autonomously, but it can't start because of these issues. How should Autopack bootstrap improvements when it can't run itself?

Strategies:
1. **Manual bootstrap** of BUILD-129 (fix schema, run manually) then let it improve itself going forward
2. **Hybrid mode**: Human fixes critical bugs (schema validation), Autopack builds remaining capabilities
3. **Degraded mode**: Autopack runs with reduced capabilities (direct DB access, no API) to build improvements

### Question 4: **Error Recovery vs. Error Prevention**
Current approach emphasizes error RECOVERY (retry loops, self-healing). Should we shift toward error PREVENTION (validation, pre-flight checks)?

Trade-off:
- **Recovery**: Flexible, handles unexpected issues, but burns tokens on retries
- **Prevention**: Stricter, catches issues early, but may be too rigid for edge cases

### Question 5: **Database as Source of Truth**
Should database state be considered authoritative, or should code schemas be authoritative?

Options:
- **Database authoritative**: Code adapts to whatever's in DB (dynamic enum loading)
- **Code authoritative**: DB must match code, migrations enforce (current approach)
- **Bidirectional sync**: Code and DB validate against each other, conflicts escalate

---

## Immediate Action Items (Pending GPT-5.2 Feedback)

1. **Fix immediate blocker**: Add `READY` to `RunState` enum OR update database `state='READY'` → `state='RUN_CREATED'`
2. **Implement minimal schema validator**: Check enum values on executor startup
3. **Add diagnostic context to API 500 errors**: Catch ORM serialization errors, log schema mismatches
4. **Document current ID conventions**: Single-phase runs - what's the pattern?
5. **Create RunBuilder utility**: Wrap run creation with validation and defaults

---

## Conclusion

The root cause of BUILD-127/129 failures is a **schema validation gap**: invalid database states (e.g., `state='READY'`) silently accumulate and cause cascading failures when the API/ORM tries to deserialize them.

**Core insight**: Autopack has robust error RECOVERY (retry loops, self-healing, doctor agent) but weak error PREVENTION (schema validation, pre-flight checks, diagnostic errors).

**Path forward**: Implement **Schema Validator** (#1) and **Diagnostic Error Messages** (#6) as prerequisites for autonomous self-improvement. These enable Autopack to:
- Detect invalid states before they cause 500 errors
- Provide actionable remediation instead of generic error messages
- Bootstrap improvements (BUILD-129) without human intervention

**Question for GPT-5.2**: Do you agree with this diagnosis? Are there deeper architectural issues I'm missing? What would you prioritize differently?
