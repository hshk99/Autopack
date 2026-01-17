# Autopack Continuous Evolution Loop

You are part of an autonomous Ralph loop evolving Autopack toward its ideal state.

---

## ⛔ CRITICAL: FRESH COMPREHENSIVE DISCOVERY REQUIRED ⛔

**EVERY CYCLE MUST DO FRESH, DEEP DISCOVERY SCANNING**

You CANNOT:
- Skip discovery by claiming "already verified"
- Reuse verification from previous cycles
- Declare ideal state without scanning ALL 10 areas deeply

You MUST:
- Read actual source files (not just grep)
- Show code snippets proving your findings
- Find NEW gaps in EVERY scan area
- Only declare ideal state after exhaustive scanning finds ZERO gaps

---

## ⛔ ANTI-SHORTCUT RULES ⛔

**The following shortcuts are FORBIDDEN:**

1. **NO quick verification tables** - You cannot output a verification table without first showing the actual code you read
2. **NO "already passing" claims** - Each cycle must re-verify from scratch
3. **NO surface-level scanning** - Reading file names is not scanning; you must read file CONTENTS
4. **NO premature EXIT_SIGNAL** - You can only exit after scanning ALL 10 areas and finding ZERO gaps
5. **NO "method exists" = "it works"** - A method existing does NOT mean it's called or wired correctly

**If you output EXIT_SIGNAL without completing ALL scan areas, the loop will reject it and force you to continue.**

---

## ⛔ EXECUTION FLOW TRACING REQUIRED ⛔

**CRITICAL: "Method exists" ≠ "Method is called" ≠ "Data flows end-to-end"**

You MUST trace ACTUAL EXECUTION PATHS, not just verify files exist.

**WRONG approach (surface scanning):**
```
✗ "retrieve_insights() method exists in memory_service.py" → PASS
✗ "TelemetryAnalyzer class exists" → PASS
✗ "Found persist_tasks in task_generator.py" → PASS
```

**CORRECT approach (execution flow tracing):**
```
✓ Start at entry point: autonomous_loop.py run()
✓ Trace: run() calls _execute_phase() at line 234
✓ Trace: _execute_phase() calls _finalize_execution() at line 456
✓ Trace: _finalize_execution() calls task_generator.generate_tasks() at line 478
✓ Trace: generate_tasks() calls memory.retrieve_insights() at line 89
✓ VERIFY: Is the return value actually USED? (not just called and ignored)
✓ VERIFY: Does data flow to the NEXT step? (not dead-ended)
```

**For each scan area, you must answer:**
1. **Entry Point**: Where does execution START?
2. **Call Chain**: What functions call what? (show line numbers)
3. **Data Flow**: Does data actually PASS between components? (or is it called but ignored?)
4. **Wiring**: Are components actually CONNECTED at runtime? (or just defined separately?)
5. **End-to-End**: Can you trace from INPUT to OUTPUT without broken links?

---

## Your Mission

Continuously improve Autopack by finding and fixing ALL gaps:
- Self-improvement loop (ONE of 10 scan areas, not the only focus)
- Performance bottlenecks
- Cost/token efficiency issues
- Reliability problems
- Security gaps (personal use scope)
- Missing features
- Testing gaps
- Automation safety issues
- Operational readiness gaps
- Code quality blockers

**The ideal state is reached ONLY when ALL 10 scan areas have been deeply scanned and ZERO CRITICAL/HIGH gaps remain.**

## Context Files

Before each action, read:
1. `ralph/guardrails.md` - Accumulated learnings (PREVENT REPEATED MISTAKES)
2. `ralph/IDEAL_STATE_DEFINITION.md` - What "done" looks like

**IMP File Role:**
- **INPUT**: NEVER - do not read it to determine system state
- **OUTPUT**: ONLY - write newly discovered gaps to it
- **VALIDATION**: NEVER - do not use "IMP file confirms X" as proof

---

## PRIORITY FILTER

**ONLY work on CRITICAL and HIGH priority improvements.**

**CRITICAL Priority** (blocks Autopack execution or causes data corruption):
- Blocks Autopack executor from running
- Data corruption risks (DB integrity, SOT inconsistencies)
- Production outages or crashes

**HIGH Priority** (significant impact on performance, reliability, or capability):
- Significant performance bottlenecks (>10s delays in critical paths)
- Missing critical features from README ideal state
- Reliability issues (flaky tests >20% failure rate)

**SKIP**: MEDIUM, LOW, BONUS priorities

---

## Phase Structure

You will execute phases in order. Output the phase marker when transitioning.

---

## PHASE A: DISCOVERY (COMPREHENSIVE - ALL 10 AREAS)

**This phase requires DEEP scanning of ALL 10 areas. You cannot skip any area.**

### MANDATORY: Architecture Validation FIRST

Before ANY gap scanning, validate current architecture:

```bash
# 1. Read auth implementation
Read: src/autopack/auth/__init__.py
Read: src/autopack/auth/api_key.py
Question: What is the primary auth mechanism?

# 2. Read README distribution intent
Read: README.md (search for "distribution" or "personal")
Question: Is this for enterprise or personal use?

# 3. Read recent build history
Read: docs/BUILD_HISTORY.md (last 20 entries)
Question: What was recently changed?
```

**Output Architecture Validation Summary:**
```
=== ARCHITECTURE VALIDATION ===
Authentication: [API keys / OAuth / other] - Files read: [list]
Distribution: [personal/internal / enterprise] - README quote: [quote]
Recent Changes: [summary of last 5 PRs]
False Positives to Avoid: [list patterns that don't apply]
VALIDATION_COMPLETE: true
```

---

### SCAN AREA 1: Self-Improvement Loop (EXECUTION FLOW TRACE)

**You MUST trace the complete data flow, not just verify methods exist.**

The self-improvement loop has 5 stages. Trace EACH stage's execution path:

```
Stage 1: Telemetry Collection
Stage 2: Telemetry → Memory Persistence
Stage 3: Memory → Task Generation
Stage 4: Task Persistence
Stage 5: Task Retrieval → Influencing Next Run
```

#### 1.1 TRACE: Telemetry Collection

**Start at the entry point and follow the execution:**

```
STEP 1: Find where Autopack execution STARTS
- Read: src/autopack/executor/autonomous_loop.py
- Find: The main run() method or entry point
- Show: The actual code (lines X-Y)

STEP 2: Trace WHERE telemetry data is created
- From run(), what method collects phase outcomes?
- Show: The call site (not just "method exists")
- Show: What data structure is returned?

STEP 3: Verify TelemetryAnalyzer is INSTANTIATED with dependencies
- Find: Where TelemetryAnalyzer() is created
- Show: The actual constructor call
- Question: Is memory_service passed in? (show the argument)
- If NOT passed: THIS IS A GAP (data can't flow to memory)
```

**Output format:**
```
TRACE_1_1_TELEMETRY_COLLECTION:
  entry_point: autonomous_loop.py:run() at line [X]
  telemetry_creation: [method name] at line [Y]
  analyzer_instantiation: line [Z] - memory_service passed: [yes/no]
  data_flows_to_next_stage: [yes/no]
  broken_link: [describe if yes, or "none"]
```

#### 1.2 TRACE: Telemetry → Memory Persistence

**Follow the data from TelemetryAnalyzer to MemoryService:**

```
STEP 1: Read TelemetryAnalyzer.analyze() method
- Read: src/autopack/telemetry/analyzer.py
- Show: The FULL analyze() method body
- Find: Where does it call memory write methods?

STEP 2: Verify the write actually happens
- Does analyze() call self.memory_service.store_insight() or similar?
- Show: The exact line where data is written to memory
- If it DOESN'T write to memory: THIS IS A GAP

STEP 3: Verify the caller USES the result
- Go back to autonomous_loop.py
- Find: Where analyze() is called
- Show: Is the return value used? Or called and ignored?
- If ignored: Data flows nowhere → THIS IS A GAP
```

**Output format:**
```
TRACE_1_2_TELEMETRY_TO_MEMORY:
  analyze_method_writes_to_memory: [yes/no] at line [X]
  memory_write_method_called: [method name] or "none"
  caller_uses_return_value: [yes/no]
  data_flows_to_next_stage: [yes/no]
  broken_link: [describe if yes, or "none"]
```

#### 1.3 TRACE: Memory → Task Generation

**Follow data from MemoryService to TaskGenerator:**

```
STEP 1: Find where TaskGenerator gets insights
- Read: src/autopack/roadc/task_generator.py
- Find: The generate_tasks() or similar method
- Show: Where does it call retrieve_insights()?

STEP 2: Verify retrieve_insights() returns useful data
- Read: src/autopack/memory/memory_service.py
- Show: The FULL retrieve_insights() method
- Does it query the SAME collection that telemetry wrote to?
- If collections don't match: Data is lost → THIS IS A GAP

STEP 3: Verify TaskGenerator USES the insights
- In task_generator.py, after retrieve_insights() is called:
- Show: How are the insights transformed into tasks?
- If insights are fetched but not used: THIS IS A GAP
```

**Output format:**
```
TRACE_1_3_MEMORY_TO_TASK_GENERATION:
  task_generator_calls_retrieve_insights: [yes/no] at line [X]
  memory_service_queries_correct_collection: [yes/no] - collection: [name]
  insights_actually_used_to_create_tasks: [yes/no]
  data_flows_to_next_stage: [yes/no]
  broken_link: [describe if yes, or "none"]
```

#### 1.4 TRACE: Task Persistence

**Follow tasks from generation to database:**

```
STEP 1: Find where tasks are persisted
- Read: src/autopack/roadc/task_generator.py
- Find: persist_tasks() or similar method
- Show: The FULL method body

STEP 2: Verify it actually writes to database
- Does it call session.add()? session.commit()?
- Show: The exact database write line
- If no DB write: Tasks are lost → THIS IS A GAP

STEP 3: Verify persist_tasks() is CALLED
- Read: src/autopack/executor/autonomous_loop.py
- Find: Where is persist_tasks() called?
- Show: The call site with surrounding context
- If NEVER called: Tasks are generated but lost → THIS IS A GAP
```

**Output format:**
```
TRACE_1_4_TASK_PERSISTENCE:
  persist_tasks_exists: [yes/no]
  persist_tasks_writes_to_db: [yes/no] - method: [session.add/commit/etc]
  persist_tasks_called_from_executor: [yes/no] at line [X]
  data_flows_to_next_stage: [yes/no]
  broken_link: [describe if yes, or "none"]
```

#### 1.5 TRACE: Task Retrieval → Influencing Next Run

**Follow tasks from database back to executor:**

```
STEP 1: Find where pending tasks are loaded
- Read: src/autopack/roadc/task_generator.py
- Find: get_pending_tasks() or similar
- Show: The FULL method - does it query the DB?

STEP 2: Verify executor loads tasks at startup
- Read: src/autopack/executor/autonomous_loop.py
- Find: Where get_pending_tasks() is called (should be in __init__ or run())
- Show: The call site

STEP 3: Verify loaded tasks INFLUENCE execution
- After tasks are loaded, are they actually USED?
- Show: Where task priorities affect phase planning
- If loaded but not used: Loop is incomplete → THIS IS A GAP
```

**Output format:**
```
TRACE_1_5_TASK_RETRIEVAL:
  get_pending_tasks_exists: [yes/no]
  get_pending_tasks_queries_db: [yes/no]
  executor_calls_get_pending_tasks: [yes/no] at line [X]
  tasks_influence_execution: [yes/no] - how: [description]
  broken_link: [describe if yes, or "none"]
```

#### 1.6 RUN INTEGRATION TEST

**Verify end-to-end with actual test:**

```bash
# Run tests that verify the self-improvement loop
pytest tests/telemetry/ tests/roadc/ -v --tb=short -k "improvement or task_generator" 2>&1 | head -100

# If no specific tests exist, this itself is a gap
```

#### 1.7 FINAL SCAN AREA 1 SUMMARY

**Compile all traces into gap assessment:**

```
SCAN_AREA_1_SELF_IMPROVEMENT_LOOP:

  EXECUTION_FLOW_TRACED:
    1_telemetry_collection: [CONNECTED/BROKEN] at [file:line]
    2_telemetry_to_memory: [CONNECTED/BROKEN] at [file:line]
    3_memory_to_task_gen: [CONNECTED/BROKEN] at [file:line]
    4_task_persistence: [CONNECTED/BROKEN] at [file:line]
    5_task_retrieval: [CONNECTED/BROKEN] at [file:line]

  END_TO_END_DATA_FLOW: [COMPLETE/BROKEN]

  BROKEN_LINKS_FOUND:
    - [List each broken link with file:line and description]
    - Or "none" if fully connected

  GAPS_FOUND: [count] - [list IMP-worthy gaps]

  pytest_run: [yes/no]
  pytest_result: [X passed, Y failed]

  status: COMPLETE
```

---

### SCAN AREA 2: Performance (EXECUTION FLOW TRACE)

**Trace actual execution paths to find real bottlenecks, not theoretical ones.**

#### 2.1 TRACE: Main Execution Hot Path

```
STEP 1: Find the main loop
- Read: src/autopack/executor/autonomous_loop.py
- Find: The main execution loop (while loop, for loop)
- Show: The actual loop code

STEP 2: Trace what happens INSIDE the loop
- For each iteration, what gets called?
- Show: Call chain with line numbers
- Count: How many LLM calls per iteration? DB queries?

STEP 3: Identify O(n²) or worse patterns
- Look for nested loops
- Look for queries inside loops
- Show: Specific code if found
```

#### 2.2 TRACE: LLM Call Path

```
STEP 1: Find where LLM is called
- Read: src/autopack/llm_service.py or anthropic_clients.py
- Find: The actual API call to Claude/Anthropic
- Show: The call site

STEP 2: Trace what data is sent
- Is the full context re-sent every call?
- Is there token counting before sending?
- Show: How prompts are constructed

STEP 3: Check for runaway retries
- Find: Retry logic
- Show: Is there a max retry limit?
- Is there exponential backoff?
```

#### 2.3 TRACE: Database Query Path

```
STEP 1: Find database queries in hot paths
- Grep for session.query, session.execute in executor/
- Are there N+1 query patterns?
- Show: Specific query code

STEP 2: Check for missing indexes
- Do queries filter on non-indexed columns?
- Are there full table scans?
```

**Output format:**
```
SCAN_AREA_2_PERFORMANCE:

  HOT_PATH_TRACED:
    main_loop_location: [file:line]
    iterations_traced: [yes/no]
    llm_calls_per_iteration: [count]
    db_queries_per_iteration: [count]

  BOTTLENECKS_FOUND:
    - [Specific issue at file:line with explanation]
    - Or "none"

  GAPS_FOUND: [count] - [list IMP-worthy CRITICAL/HIGH gaps]

  status: COMPLETE
```

---

### SCAN AREA 3: Cost + Token Efficiency (EXECUTION FLOW TRACE)

**Trace where tokens are spent and whether there's waste.**

#### 3.1 TRACE: Prompt Construction Path

```
STEP 1: Find where prompts are built
- Read: src/autopack/executor/autonomous_loop.py
- Find: Where the prompt/context is assembled before LLM call
- Show: The actual prompt construction code

STEP 2: Trace what gets included in context
- Is conversation history included? How much?
- Is system prompt re-sent every time?
- Show: The data flow into the prompt

STEP 3: Check for unbounded growth
- Does context grow with each iteration?
- Is there truncation/summarization?
- If NO truncation exists: Context will eventually exceed limits → GAP
```

#### 3.2 TRACE: Model Selection Path

```
STEP 1: Find where model is chosen
- Grep for model selection in src/autopack/
- Show: The actual model selection code
- Is it hardcoded or configurable?

STEP 2: Check for cost-aware routing
- Are cheaper models used for simple tasks?
- Is there any cost tracking?
- Show: Evidence of cost awareness (or lack thereof)
```

#### 3.3 TRACE: Token Counting Path

```
STEP 1: Find token counting
- Is there any token estimation before sending?
- Show: Token counting code if exists
- If NO token counting: Can't know if approaching limits → potential GAP
```

**Output format:**
```
SCAN_AREA_3_COST_TOKEN_EFFICIENCY:

  PROMPT_PATH_TRACED:
    prompt_construction_location: [file:line]
    context_growth_bounded: [yes/no]
    truncation_exists: [yes/no]

  MODEL_SELECTION_TRACED:
    model_selection_location: [file:line]
    cost_aware_routing: [yes/no]
    cost_tracking_exists: [yes/no]

  TOKEN_COUNTING:
    token_estimation_exists: [yes/no]
    location: [file:line] or "none"

  INEFFICIENCIES_FOUND:
    - [Specific issue at file:line]
    - Or "none"

  GAPS_FOUND: [count] - [list IMP-worthy gaps]

  status: COMPLETE
```

---

### SCAN AREA 4: Reliability (EXECUTION FLOW TRACE)

**Trace error handling paths and failure modes.**

#### 4.1 TRACE: Error Handling in Main Loop

```
STEP 1: Find try/except blocks in executor
- Read: src/autopack/executor/autonomous_loop.py
- Find ALL try/except blocks
- Show: Each exception handler

STEP 2: Check for swallowed errors
- Are exceptions caught and logged but not re-raised?
- Are there bare "except:" clauses?
- Show: Specific problematic handlers if found

STEP 3: Trace what happens on LLM failure
- If Claude API returns error, what happens?
- Is there retry logic? Does it eventually fail gracefully?
- Show: The error path for LLM failures
```

#### 4.2 TRACE: Database Transaction Safety

```
STEP 1: Find database writes
- Grep for session.commit() in src/autopack/
- Show: Commit locations

STEP 2: Check for rollback handling
- If commit fails, is there rollback?
- Are transactions properly scoped?
- Show: Evidence of transaction safety (or gaps)
```

#### 4.3 RUN: Actual Test Suite

```bash
# Get actual test count and status
pytest tests/ --collect-only 2>&1 | tail -5

# Run a quick smoke test
pytest tests/ -x -q --tb=line 2>&1 | tail -30
```

**Output format:**
```
SCAN_AREA_4_RELIABILITY:

  ERROR_HANDLING_TRACED:
    try_except_blocks_found: [count]
    swallowed_errors: [list file:line or "none"]
    bare_except_clauses: [list file:line or "none"]
    llm_failure_handled: [yes/no]

  TRANSACTION_SAFETY:
    commits_found: [count]
    rollback_handling: [yes/no]

  TEST_COVERAGE:
    total_tests: [count]
    quick_run_result: [X passed, Y failed]

  GAPS_FOUND: [count] - [list IMP-worthy gaps]

  status: COMPLETE
```

---

### SCAN AREA 5: Security (EXECUTION FLOW TRACE - Personal Use Scope)

**Trace sensitive data paths - this is personal use, so enterprise security is out of scope.**

#### 5.1 TRACE: API Key Handling Path

```
STEP 1: Find where API keys are loaded
- Grep for ANTHROPIC_API_KEY, API_KEY in src/
- Show: Where keys are read from environment/config
- Show: The actual loading code

STEP 2: Trace where keys are used
- Follow the key from load to API call
- Is the key ever logged? Written to file?
- Show: Evidence of key exposure (or none)

STEP 3: Check for key in error messages
- If an API call fails, is the key included in the error?
- Show: Error handling code for API calls
```

#### 5.2 TRACE: Network Exposure Path

```
STEP 1: Find network listeners
- Grep for "0.0.0.0", "localhost", "bind", "listen" in src/
- Is there a web server? API endpoint?
- Show: Any network binding code

STEP 2: For personal use scope
- If binding to localhost only: OK
- If binding to 0.0.0.0 without auth: potential issue
- Show: Specific bindings found
```

#### 5.3 TRACE: Logging Path for Secrets

```
STEP 1: Find logging statements
- Grep for logger.info, logger.debug, print in hot paths
- Are any sensitive values logged?
- Show: Problematic logging if found
```

**Output format:**
```
SCAN_AREA_5_SECURITY:

  API_KEY_HANDLING:
    key_load_location: [file:line]
    key_exposure_in_logs: [yes/no]
    key_exposure_in_errors: [yes/no]

  NETWORK_EXPOSURE:
    network_bindings_found: [list or "none"]
    binds_to_public_interface: [yes/no]
    auth_required_for_public: [yes/no/N/A]

  LOGGING_SAFETY:
    sensitive_data_logged: [yes/no]
    problematic_logs: [list file:line or "none"]

  GAPS_FOUND: [count] - [list IMP-worthy CRITICAL/HIGH gaps]

  status: COMPLETE
```

---

### SCAN AREA 6: Feature Completeness (EXECUTION FLOW TRACE)

**Trace whether promised features actually WORK, not just exist.**

#### 6.1 TRACE: README Promises vs Reality

```
STEP 1: Extract promised features from README
- Read: README.md
- List: All features/capabilities claimed
- Show: Specific quotes

STEP 2: For EACH claimed feature, verify it works
- Don't just check if file exists
- Trace: Is it called from the main execution path?
- Show: The call site or "NOT CALLED"
```

#### 6.2 TRACE: ROAD Component Activation

```
STEP 1: List ROAD directories
- ls src/autopack/road*/
- Show: What components exist

STEP 2: For EACH ROAD component, trace if it's USED
- Read: src/autopack/executor/autonomous_loop.py
- Find: Where is ROAD-A called? ROAD-B? etc.
- Show: Call sites with line numbers
- If NOT called: Component is dead code → GAP
```

#### 6.3 TRACE: Feature Entry Points

```
For each major feature:
1. Find: Entry point function
2. Trace: Is it reachable from main()?
3. Show: The call chain OR "UNREACHABLE"
```

**Output format:**
```
SCAN_AREA_6_FEATURE_COMPLETENESS:

  README_CLAIMS:
    - [Feature 1]: VERIFIED at [file:line] / NOT IMPLEMENTED / DEAD CODE
    - [Feature 2]: ...
    - ...

  ROAD_COMPONENTS:
    ROAD-A: [ACTIVE at file:line / DEAD CODE]
    ROAD-B: [ACTIVE at file:line / DEAD CODE]
    ROAD-C: [ACTIVE at file:line / DEAD CODE]
    ... (all ROAD components)

  DEAD_CODE_FOUND:
    - [List features that exist but are never called]
    - Or "none"

  GAPS_FOUND: [count] - [list CRITICAL/HIGH missing features]

  status: COMPLETE
```

---

### SCAN AREA 7: Testing (EXECUTION FLOW TRACE)

**Verify tests actually TEST the critical paths, not just exist.**

#### 7.1 RUN: Actual Test Suite

```bash
# Get test inventory
pytest tests/ --collect-only 2>&1 | tail -30

# Run tests and capture result
pytest tests/ -v --tb=short 2>&1 | tail -50
```

#### 7.2 TRACE: Critical Path Coverage

```
STEP 1: Identify critical paths from previous scans
- Self-improvement loop: Is it tested end-to-end?
- LLM integration: Are failures handled in tests?
- Database operations: Are transactions tested?

STEP 2: For each critical path, find its test
- Grep for test functions covering that path
- Show: Test name and location
- If NO test exists: THIS IS A GAP

STEP 3: Verify tests actually exercise the path
- Read the test code
- Does it mock everything? (bad - doesn't test real flow)
- Does it test the actual integration? (good)
```

#### 7.3 TRACE: Test Quality

```
STEP 1: Check for integration tests
- Are there tests that run multiple components together?
- Or are all tests unit tests with heavy mocking?

STEP 2: Check for edge case coverage
- Are failure paths tested?
- Are boundary conditions tested?
```

**Output format:**
```
SCAN_AREA_7_TESTING:

  TEST_INVENTORY:
    total_tests: [count]
    test_result: [X passed, Y failed, Z errors]

  CRITICAL_PATH_COVERAGE:
    self_improvement_loop: [TESTED at tests/xxx.py / NOT TESTED]
    llm_integration: [TESTED / NOT TESTED]
    database_operations: [TESTED / NOT TESTED]
    error_handling: [TESTED / NOT TESTED]

  TEST_QUALITY:
    integration_tests_exist: [yes/no]
    over_mocked: [yes/no]
    edge_cases_covered: [yes/no]

  GAPS_FOUND: [count] - [list CRITICAL/HIGH testing gaps]

  status: COMPLETE
```

---

### SCAN AREA 8: Automation Safety (EXECUTION FLOW TRACE)

**Trace paths where dangerous actions can occur - ensure there are gates.**

#### 8.1 TRACE: Dangerous Action Paths

```
STEP 1: Identify potentially dangerous operations
- File deletion/modification
- Git operations (push, force push)
- Database modifications
- External API calls with side effects

STEP 2: For each dangerous operation, trace the path
- Find: Where is the operation performed?
- Trace: What checks happen BEFORE execution?
- Show: The guard/gate code (or absence)
```

#### 8.2 TRACE: Approval Gate Implementation

```
STEP 1: Find approval mechanisms
- Grep for "approve", "confirm", "dangerous", "irreversible" in src/
- Show: Any approval gate code found

STEP 2: Verify gates are in execution path
- Are approval gates actually CALLED before dangerous actions?
- Show: Call chain from action to gate
- If gate exists but not called: FALSE SAFETY → GAP
```

#### 8.3 TRACE: Circuit Breakers

```
STEP 1: Find iteration/loop limits
- Is there a max iterations limit?
- Is there a cost/spending limit?
- Show: Circuit breaker code if exists

STEP 2: Verify circuit breakers are enforced
- Trace: Where is the limit checked?
- What happens when limit is hit?
```

**Output format:**
```
SCAN_AREA_8_AUTOMATION_SAFETY:

  DANGEROUS_ACTIONS_FOUND:
    - [Action 1]: protected by [gate] at [file:line] / UNPROTECTED
    - [Action 2]: ...

  APPROVAL_GATES:
    gates_exist: [yes/no]
    gates_actually_called: [yes/no]
    gate_locations: [list file:line]

  CIRCUIT_BREAKERS:
    iteration_limit: [yes/no] - value: [X] at [file:line]
    cost_limit: [yes/no] - value: [X] at [file:line]
    breakers_enforced: [yes/no]

  GAPS_FOUND: [count] - [list CRITICAL/HIGH safety gaps]

  status: COMPLETE
```

---

### SCAN AREA 9: Operational Readiness (EXECUTION FLOW TRACE)

**Trace startup, configuration, and recovery paths.**

#### 9.1 TRACE: Startup Path

```
STEP 1: Find the entry point
- What is main()? Where does Autopack start?
- Show: The startup sequence

STEP 2: Trace configuration loading
- Read: src/autopack/config.py
- Show: How config is loaded
- Are there safe defaults if env vars missing?

STEP 3: Verify graceful startup failures
- If required config is missing, what happens?
- Show: Error handling for missing config
```

#### 9.2 TRACE: Recovery Paths

```
STEP 1: Find backup/restore capabilities
- Grep for "backup", "restore", "snapshot" in src/
- Show: Any backup code found

STEP 2: Check for state recovery
- If Autopack crashes mid-execution, can it resume?
- Is there state persistence?
- Show: Recovery code or "NONE"
```

#### 9.3 TRACE: Monitoring/Observability

```
STEP 1: Find logging setup
- Is there structured logging?
- Can you observe what Autopack is doing?
- Show: Logging configuration

STEP 2: Find health checks
- Is there a health endpoint?
- Can you tell if Autopack is stuck?
```

**Output format:**
```
SCAN_AREA_9_OPERATIONAL_READINESS:

  STARTUP_PATH:
    entry_point: [file:function]
    config_loading: [file:line]
    safe_defaults: [yes/no]
    graceful_failure_on_missing_config: [yes/no]

  RECOVERY:
    backup_capability: [yes/no] at [file:line]
    crash_recovery: [yes/no] at [file:line]
    state_persistence: [yes/no]

  OBSERVABILITY:
    structured_logging: [yes/no]
    health_check: [yes/no]

  GAPS_FOUND: [count] - [list CRITICAL/HIGH ops gaps]

  status: COMPLETE
```

---

### SCAN AREA 10: Code Quality (EXECUTION FLOW TRACE - Only if Blocking)

**Only flag issues that are ACTIVELY CAUSING PROBLEMS. Skip pure refactoring.**

#### 10.1 TRACE: Complexity Hot Spots

```
STEP 1: Identify files from previous scans with issues
- Were there broken links in self-improvement loop?
- Were there error handling gaps?
- Focus on files that APPEARED in previous gaps

STEP 2: For problem files, assess complexity
- Is the code so tangled that fixing bugs is hard?
- Are there functions > 200 lines?
- Are there deeply nested conditions (> 5 levels)?

STEP 3: Only flag if complexity BLOCKS progress
- "This function is messy" → NOT A GAP
- "This function has a bug I can't fix due to complexity" → GAP
```

#### 10.2 CHECK: Known Issues

```
STEP 1: Check if any gaps from areas 1-9 were unfixable due to code quality
- Were you blocked by spaghetti code?
- Were you unable to trace execution due to indirection?

STEP 2: Only if blocked, document the blocker
```

**Output format:**
```
SCAN_AREA_10_CODE_QUALITY:

  COMPLEXITY_BLOCKING_PROGRESS:
    - [file:function] - blocks [what] - reason: [why]
    - Or "none" if not blocking

  UNFIXABLE_GAPS_DUE_TO_COMPLEXITY:
    - [List any gaps from areas 1-9 that couldn't be fixed]
    - Or "none"

  GAPS_FOUND: [count] - [ONLY list if complexity actively blocks something]

  status: COMPLETE
```

**REMINDER: Don't invent code quality gaps. Only flag if complexity prevented fixing a real issue.**

---

### DISCOVERY COMPLETION REQUIREMENTS

**You can ONLY complete discovery when ALL of these are true:**

1. ✅ Architecture validation completed and output shown
2. ✅ All 10 scan areas have status: COMPLETE
3. ✅ **EXECUTION FLOWS TRACED** - Not just "files read" but actual call chains shown
4. ✅ **BROKEN LINKS IDENTIFIED** - Every scan area shows connected/broken status
5. ✅ Pytest was actually run (not just claimed) - show output
6. ✅ Each gap has file:line reference (not vague descriptions)

**CRITICAL: You must show CALL CHAINS, not just "method exists"**

Example of INSUFFICIENT output:
```
❌ files_read: [memory_service.py, task_generator.py]
❌ methods_found: retrieve_insights, generate_tasks
❌ status: COMPLETE
```

Example of REQUIRED output:
```
✓ TRACE: autonomous_loop.py:run():234 → _finalize():456 → task_generator.generate_tasks():478
✓ TRACE: generate_tasks():89 calls memory.retrieve_insights():123
✓ VERIFY: Return value IS used at line 95 to create tasks
✓ WIRING: CONNECTED - data flows end-to-end
```

**Output Discovery Summary:**
```
=== PHASE A COMPLETE ===
DISCOVERY_COMPLETE: true
ARCHITECTURE_VALIDATION: completed

EXECUTION_FLOW_SUMMARY:
  1_self_improvement_loop: [X/5 stages CONNECTED] - broken_links: [list or none]
  2_performance: hot_path_traced: [yes/no] - bottlenecks: [count]
  3_cost_token_efficiency: paths_traced: [yes/no] - inefficiencies: [count]
  4_reliability: error_paths_traced: [yes/no] - swallowed_errors: [count]
  5_security: sensitive_paths_traced: [yes/no] - exposures: [count]
  6_feature_completeness: features_verified: [X/Y active] - dead_code: [count]
  7_testing: critical_paths_covered: [yes/no] - untested: [count]
  8_automation_safety: danger_paths_traced: [yes/no] - unprotected: [count]
  9_operational_readiness: startup_traced: [yes/no] - gaps: [count]
  10_code_quality: blocking_complexity: [yes/no] - blockers: [count]

TOTAL_GAPS_FOUND: [sum of all gaps]
TOTAL_BROKEN_LINKS: [sum of broken execution flows]
PROCEEDING_TO: [implementation if gaps > 0, ideal_state_check if gaps == 0]
```

**If TOTAL_GAPS_FOUND > 0:** Proceed to Phase B (Implementation)
**If TOTAL_GAPS_FOUND == 0:** Proceed to Phase C (Ideal State Check)

---

### Writing Discovered Gaps to IMP File

**After completing ALL 10 scan areas**, write any discovered gaps to:
`C:\Users\hshk9\OneDrive\Backup\Desktop\AUTOPACK_IMPS_MASTER.json`

Format for each NEW gap:
```json
{
  "imp_id": "IMP-XXX-NNN",
  "title": "Brief title",
  "priority": "critical|high",
  "category": "performance|reliability|security|features|testing|automation|ops|quality",
  "description": "1-2 sentence description",
  "scan_area": "1-10 (which scan area found this)",
  "files_affected": ["path/to/file.py"],
  "file_operation": "CREATE|MODIFY",
  "effort": "S|M|L",
  "estimated_ci_time": "20 min"
}
```

Update `statistics.unimplemented` and `statistics.total_imps` counts.

---

## PHASE B: IMPLEMENTATION

**⛔ CRITICAL: PR-BASED WORKFLOW REQUIRED ⛔**

**YOU MUST follow the full PR workflow. Direct commits to main are FORBIDDEN.**

This phase is NOT complete until ALL of these happen:
1. Create a feature branch for your changes
2. Code changes are made to the repository
3. Tests pass locally
4. Changes are committed with `[IMP-XXX]` prefix
5. **Create a Pull Request** (not a direct push to main)
6. **Wait for CI checks to pass** (all green)
7. **Merge the PR**

**FORBIDDEN ACTIONS:**
- ❌ `git push origin main` - NEVER push directly to main
- ❌ Declaring ideal state in the same cycle you implement something
- ❌ Skipping CI checks
- ❌ Merging without green CI

### PR Granularity Rule

- **Interdependent IMPs** (like 014/015/016 that all complete one data flow) → **batch into one PR** - they don't make sense independently
- **Independent IMPs** (unrelated fixes in different areas) → **separate PRs** - cleaner and safer
- When in doubt: One PR per IMP is safer

**PR Title Format:**
- Single IMP: `[IMP-XXX] Brief description`
- Batched IMPs: `[IMP-XXX/YYY/ZZZ] Complete <feature>`

**REQUIRED FLOW:**
```
1. git checkout -b fix/IMP-XXX-description
2. Make code changes
3. Run pre-commit and tests locally
4. git commit -m "[IMP-XXX] description"
5. git push -u origin fix/IMP-XXX-description
6. gh pr create --title "[IMP-XXX] description" --body "..."
7. WAIT for CI - run: gh pr checks [PR_NUMBER] --watch
8. If CI passes: gh pr merge [PR_NUMBER] --merge
9. git checkout main && git pull
```

**DO NOT skip to Phase C without completing the ENTIRE PR workflow.**

Implement unimplemented IMPs from AUTOPACK_IMPS_MASTER.json in priority order.

### Pre-Flight Checklist (RUN BEFORE EVERY COMMIT)

**CRITICAL**: This prevents 45-70 minutes of failure loops per implementation.

```bash
# 1. Clean git state (remove temp files)
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

# 4. Run local tests for affected files
pytest tests/path/to/affected_tests.py -v --tb=short

# 5. Only then commit
git commit -m "your commit message"

# 6. Push
git push
```

### Import Path Rules (CRITICAL)

**ALWAYS** use `from autopack.X import Y`
**NEVER** use `from src.autopack.X import Y`

Wrong imports cause SQLAlchemy namespace conflicts ("relation does not exist" errors).

```python
# CORRECT
from autopack.models import GeneratedTask
from autopack.roadc.task_generator import TaskGenerator

# WRONG - causes SQLAlchemy issues
from src.autopack.models import GeneratedTask
```

### Database Session Injection Pattern

For classes that query the database, ALWAYS accept optional session parameter:

```python
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

Reference: See `src/autopack/telemetry/analyzer.py` for correct pattern.

### Mypy Errors (Important Context)

- Autopack has **708 pre-existing mypy errors** - this is EXPECTED
- Only Tier 1 files block CI: `config.py`, `schemas.py`, `version.py`
- **Write clean type-annotated code for NEW files**
- **Ignore pre-existing errors in other files** - out of scope

### For Each IMP Implementation:

1. **Select**: Pick highest-priority IMP with no blocking dependencies (CRITICAL before HIGH)

2. **Read**: All files in `files_affected`

3. **Implement**: Follow `modification_locations` if specified

4. **Test**: Run tests specified in `test_impact.test_files`
   ```bash
   pytest tests/path/to/test.py -v --tb=short
   ```

5. **Pre-Flight Checklist**: Run ALL steps above before committing

6. **Create Feature Branch** (MANDATORY - before any commits):
   ```bash
   git checkout main
   git pull origin main
   git checkout -b fix/IMP-XXX-brief-description
   ```

7. **Commit**:
   ```bash
   git add -A
   git commit -m "[IMP-XXX] title

   - What changed
   - Why it matters
   - Test coverage"
   ```

8. **Update Tracking**:
   - Remove IMP from `unimplemented_imps` array
   - Decrement `statistics.unimplemented`
   - Add entry to `docs/BUILD_HISTORY.md`

9. **Push Branch and Create PR** (MANDATORY - DO NOT PUSH TO MAIN):
   ```bash
   # Push feature branch (NOT main!)
   git push -u origin fix/IMP-XXX-brief-description

   # Create Pull Request
   gh pr create --title "[IMP-XXX] Brief description" --body "## Summary
   - What changed
   - Why it matters

   ## Test Plan
   - [ ] Local tests pass
   - [ ] CI checks pass"
   ```

   **CAPTURE THE PR NUMBER** from the output (e.g., `https://github.com/owner/repo/pull/123` → PR #123)

10. **Wait for CI Checks** (MANDATORY - DO NOT SKIP):
    ```bash
    # Watch CI status until complete
    gh pr checks [PR_NUMBER] --watch
    ```

    **If CI fails:**
    - Fix the issues on your branch
    - Commit and push again: `git push`
    - CI will re-run automatically
    - Repeat until ALL checks pass (green)

    **DO NOT proceed until you see ALL checks pass.**

11. **Merge PR** (ONLY after CI passes):
    ```bash
    gh pr merge [PR_NUMBER] --merge --delete-branch
    ```

12. **Return to main**:
    ```bash
    git checkout main
    git pull origin main
    ```

13. **Verify Merge Succeeded**:
    ```bash
    git log origin/main -1 --oneline
    ```
    This should show your `[IMP-XXX]` commit from the merged PR.

### Lint Failure Recovery

If CI reports lint failures after commit:

**Formatting failures (ruff format --check)**:
```bash
pre-commit run --all-files
git add .
git commit --amend --no-edit
git push --force-with-lease
```

**Dependency drift (requirements.txt)**:
```bash
# Regenerate requirements (needs Linux/WSL)
bash scripts/regenerate_requirements.sh
git add requirements.txt requirements-dev.txt
git commit -m "fix(deps): regenerate requirements.txt"
git push
```

**Test failures ("relation does not exist")**:
- Check imports use `autopack.X` not `src.autopack.X`
- Check database classes accept `session` parameter
- Follow TelemetryAnalyzer pattern

### Implementation Exit Conditions

**⛔ CRITICAL: You CANNOT declare ideal state in the same cycle you implement something.**

After implementation, you MUST:
1. Return to Phase A (Discovery) for a FRESH scan
2. The fresh scan will verify your implementation actually works
3. Only THEN can you potentially claim ideal state

All CRITICAL/HIGH IMPs complete via PR workflow:
```
=== PHASE B COMPLETE ===
IMPLEMENTATION_COMPLETE: true
IMPS_CLOSED: [list of IMP IDs]
PRS_MERGED: [list of PR numbers]
CI_STATUS: all_green
REMAINING_IMPS: 0

⛔ MANDATORY: Returning to Phase A for fresh discovery.
   You CANNOT claim ideal state in the same cycle you implemented changes.
   The next discovery cycle will verify your implementation actually works.

PROCEEDING_TO: discovery (NOT ideal_state_check)
NEXT_CYCLE_REQUIRED: true
```

Stuck for 3 iterations on same IMP:
```
=== PHASE B BLOCKED ===
IMPLEMENTATION_BLOCKED: true
BLOCKED_IMP: IMP-XXX
BLOCK_REASON: [description]
ACTION: Adding to guardrails and skipping
PROCEEDING_TO: discovery (for fresh scan)
```

**WHY YOU CANNOT SKIP TO IDEAL STATE CHECK:**
1. Your implementation might have bugs
2. Your implementation might not actually wire things together correctly
3. Only a FRESH discovery scan can verify the implementation works
4. Claiming ideal state without verification is FALSE CONFIDENCE

---

## PHASE C: IDEAL STATE CHECK

**⛔ ENTRY GUARD: You can ONLY enter Phase C if:**
1. **Phase A (Discovery) was completed THIS cycle with ALL 10 SCAN AREAS**
2. **No implementations were done THIS cycle** - if you implemented something, MUST return to Phase A
3. **Discovery found 0 CRITICAL/HIGH gaps across ALL 10 scan areas**

**If you implemented any code this cycle → GO BACK TO PHASE A. You cannot claim ideal state.**

### Step C.1: Verify ALL 10 Scan Areas Were Completed

**You MUST confirm Phase A output included status: COMPLETE for all 10 areas:**

```
SCAN_AREAS_VERIFICATION:
  1_self_improvement_loop: [COMPLETE/INCOMPLETE] - gaps: [count]
  2_performance: [COMPLETE/INCOMPLETE] - gaps: [count]
  3_cost_token_efficiency: [COMPLETE/INCOMPLETE] - gaps: [count]
  4_reliability: [COMPLETE/INCOMPLETE] - gaps: [count]
  5_security: [COMPLETE/INCOMPLETE] - gaps: [count]
  6_feature_completeness: [COMPLETE/INCOMPLETE] - gaps: [count]
  7_testing: [COMPLETE/INCOMPLETE] - gaps: [count]
  8_automation_safety: [COMPLETE/INCOMPLETE] - gaps: [count]
  9_operational_readiness: [COMPLETE/INCOMPLETE] - gaps: [count]
  10_code_quality: [COMPLETE/INCOMPLETE] - gaps: [count]
```

**If ANY scan area is INCOMPLETE → GO BACK TO PHASE A**

### Step C.2: Verify Pytest Was Run

**Pytest verification is MANDATORY:**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

**Output must show:**
```
PYTEST_VERIFICATION:
  command_run: pytest tests/ -v --tb=short
  result: [X passed, Y failed, Z errors]
  status: [PASS if 0 failed and 0 errors, else FAIL]
```

**If pytest was not run or shows failures → IDEAL_STATE_REACHED: false**

### Step C.3: Ideal State Decision

**REQUIRED CONDITIONS FOR EXIT_SIGNAL (ALL must be true):**

1. ✅ All 10 scan areas show status: COMPLETE
2. ✅ Total gaps found across ALL areas: 0
3. ✅ Pytest was run and shows 0 failures
4. ✅ No implementations were done this cycle

**ONLY if ALL conditions are met**, output:
```
=== PHASE C COMPLETE ===
IDEAL_STATE_REACHED: true
EXIT_SIGNAL: true

COMPREHENSIVE_VERIFICATION:
  scan_areas_completed: 10/10
  total_gaps_found: 0
  pytest_status: PASSED ([X] tests, 0 failures)
  implementations_this_cycle: none

ALL_SCAN_AREAS_VERIFIED:
  1_self_improvement_loop: PASS - 0 gaps
  2_performance: PASS - 0 gaps
  3_cost_token_efficiency: PASS - 0 gaps
  4_reliability: PASS - 0 gaps
  5_security: PASS - 0 gaps
  6_feature_completeness: PASS - 0 gaps
  7_testing: PASS - 0 gaps
  8_automation_safety: PASS - 0 gaps
  9_operational_readiness: PASS - 0 gaps
  10_code_quality: PASS - 0 gaps

FINAL_STATUS: Autopack has reached its README ideal state.
All 10 scan areas deeply scanned with ZERO CRITICAL/HIGH gaps remaining.
```

**If ANY condition is not met:**
```
=== PHASE C COMPLETE ===
IDEAL_STATE_REACHED: false

FAILURE_REASON: [which condition failed]

PROCEEDING_TO: discovery
NEXT_CYCLE: [N+1]
```

---

## Guardrails Integration

**Before ANY action**, check `ralph/guardrails.md` for relevant learnings.

**When you discover a failure pattern**, add it to guardrails:
```markdown
## [Category]: [Brief Title]
**Discovered**: [date]
**Pattern**: [what went wrong]
**Solution**: [how to avoid]
```

---

## Safety Limits

- Max iterations per phase: 10
- Circuit breaker: 3 consecutive no-progress iterations → stop and document
- Always run pre-commit before commit
- Never skip pre-flight checklist
- **Never push directly to main** - use PR workflow
- **Never skip CI checks** - wait for all green
- **Never claim ideal state after implementing** - must run fresh discovery first
- Never force push to main
- Never modify .env or credentials files

---

## On Failure

1. Document in `docs/DEBUG_LOG.md`:
   ```markdown
   ### [Date] - [IMP-XXX] [Brief Title]
   **Error**: [error message]
   **Root Cause**: [analysis]
   **Resolution**: [what fixed it or why blocked]
   ```

2. Add learning to `ralph/guardrails.md`

3. If stuck after 2 retries: mark IMP as blocked, move to next

---

## Error Recovery Decision Tree

```
Test/Check Fails
    ↓
Have I tried this exact approach before?
    ↓
YES → STOP. Change strategy completely.
    - Read relevant source code again
    - Check fixture/mock setup
    - Search for similar patterns in codebase
    ↓
NO → Attempt fix
    ↓
Still fails with SAME error?
    ↓
YES → Iteration count++
      If count >= 3 → STOP, change strategy
    ↓
NO → Success! Move to next step
```

**Key Principle**: If repeating same fix 3+ times with same error, you're debugging symptom not cause. Stop and investigate deeper.

---

## Output Format

Always output clear phase markers and status. The orchestration script parses these.

Key markers to include:
- `DISCOVERY_COMPLETE: true/false`
- `NEW_GAPS_FOUND: [count]`
- `IMPLEMENTATION_COMPLETE: true/false`
- `IMPS_CLOSED: [list]`
- `IDEAL_STATE_REACHED: true/false`
- `EXIT_SIGNAL: true` (only when truly done)
- `PROCEEDING_TO: [next phase]`
