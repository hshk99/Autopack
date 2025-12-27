# Autopack Framework

**Autonomous AI Code Generation Framework**

Autopack is a framework for orchestrating autonomous AI agents (Builder and Auditor) to plan, build, and verify software projects. It uses a structured approach with phased execution, quality gates, and self-healing capabilities.

---

## Recent Updates (v0.4.6 - BUILD-129 Telemetry Production Ready)

### BUILD-129 Phase 3 P4-P9 Truncation Mitigation (2025-12-25) - ✅ COMPLETE
**Comprehensive Truncation Reduction** - Multi-layered approach reducing truncation from 52.6% toward target ≤2%
- **Problem Solved**: 52.6% truncation rate (20/38 events) blocking Tier-1 risk targets, wasting tokens on retries/continuations
- **Root Cause**: Budget enforcement bypassed by overrides, category misrecording, overly broad buffers wasting tokens
- **Solution**: 6-part mitigation strategy (P4-P9)
- **Implementation**:
  - **P4 (Budget Enforcement)**: Relocated enforcement to immediately before API call - catches all override paths (builder_mode, change_size forcing max_tokens=16384)
  - **P5 (Category Recording)**: Use estimated_category from token estimator instead of task_category from phase_spec - fixes SOT/DOC_SYNTHESIS misclassification
  - **P6 (Truncation-Aware SMAPE)**: Separate truncated events (lower bounds) from clean measurements - eliminates censored data bias in metrics
  - **P7 (Confidence-Based Buffering)**: Adaptive buffer margins based on risk factors (1.4x low confidence, 1.6x high deliverable count, 2.2x doc_synthesis/sot)
  - **P8 (Telemetry Budget Recording)**: Store actual enforced max_tokens in metadata - fixes confusion when P4 bumps budget or overrides apply
  - **P9 (Narrow 2.2x Buffer)**: Restrict 2.2x buffer to only doc_synthesis/doc_sot_update (was: all documentation) - prevents token waste on simple DOC_WRITE tasks
- **Triage Analysis**: Identified documentation (low complexity) as primary truncation driver (7 events, 2.12x underestimation = 112% error)
- **Expected Impact**:
  - Truncation reduction: 52.6% → ~25% (approaching ≤2% target)
  - Token efficiency: P9 preserves truncation reduction where needed without ballooning waste
  - Clean telemetry: P6+P8 enable accurate SMAPE analysis
- **Test Coverage**: All validation tests passing
  - [scripts/test_budget_enforcement.py](scripts/test_budget_enforcement.py) - P4 validation (3 scenarios)
  - [scripts/test_category_recording.py](scripts/test_category_recording.py) - P5 validation (SOT/DOC_SYNTHESIS detection)
  - [scripts/test_confidence_buffering.py](scripts/test_confidence_buffering.py) - P7+P9 validation (6 buffer scenarios)
- **Files Modified**:
  - [src/autopack/anthropic_clients.py](src/autopack/anthropic_clients.py) - P4 enforcement relocated (lines 673-679, 767-769, 1004-1007), P5 category recording (lines 369, 905, 948), P8 actual budget storage
  - [src/autopack/token_estimator.py](src/autopack/token_estimator.py) - P7 confidence-based buffering (lines 610-625), P9 narrowed buffer (lines 623-628)
  - [scripts/analyze_token_telemetry_v3.py](scripts/analyze_token_telemetry_v3.py) - P6 truncation-aware SMAPE
  - [scripts/truncation_triage_report.py](scripts/truncation_triage_report.py) - NEW: Truncation segment analysis tool
- **Next Steps**: Validation batch (10-15 phases) with intentional coverage, Go/No-Go rule if truncation >25-30%

### BUILD-129 Phase 3 P10 Validation Unblocked + P10-First Draining (2025-12-26) - ✅ COMPLETE (Infra)
**Deterministic P10 Validation** - P10 validation is now representative (distribution-based) and DB-backed (no log scraping required).
- **API identity + DB health gating** (removes `/runs/{id}` 500s from wrong service / wrong DB):
  - `src/autopack/main.py`: `/health` validates DB and returns `service="autopack"`; returns 503 when DB is misconfigured.
  - `src/autopack/autonomous_executor.py`: requires `service=="autopack"` and refuses incompatible/non-JSON `/health`.
  - Fixed API auto-start target to `autopack.main:app` (correct under `PYTHONPATH=src`).
- **DB-backed P10 events**:
  - New table `token_budget_escalation_events` (migration: `migrations/005_add_p10_escalation_events.sql`).
  - Executor writes an escalation event when P10 triggers (base/source/retry tokens), making validation deterministic.
- **P10-first draining**:
  - New ranked plan generator: `scripts/create_p10_first_drain_plan.py` (prioritizes queued phases likely to hit truncation/≥95% utilization).
  - New helper selector: `scripts/pick_next_run.py` (prints `run_id` + inferred `run_type`, preferring P10-first ranking and falling back to highest queued count).
  - Updated validator: `scripts/check_p10_validation_status.py` now checks escalation events table.
- **SQLite migration runner hardened**:
  - `scripts/run_migrations.py` now runs **root** migrations by default (use `--include-scripts` to also run legacy `scripts/migrations/*.sql`).
  - Fixed broken telemetry view `v_truncation_analysis` to match `phases.name` (migration: `migrations/006_fix_v_truncation_analysis_view.sql`).

**Stability confirmation (draining)**:
- **Stateful retries are working**: `retry_attempt`/`revision_epoch` persist in SQLite (`phases` table), so repeated drain batches no longer “forget” attempt counters.
- **P10 retry budgets are actually applied** on subsequent attempts (e.g., retry uses `max_tokens=35177` after a recorded escalation with `retry_max_tokens=35177`), aligning with the intended self-healing behavior.
- **NDJSON deliverables validation is compatible**: NDJSON outputs now include a lightweight diff-like header so deliverables validation can “see” created paths.

### BUILD-129 Phase 3 NDJSON Convergence Hardening (2025-12-27) - ✅ COMPLETE (Parser)
**Systemic NDJSON robustness fix**: eliminated `ndjson_no_operations` for a common model output pattern where the model ignores NDJSON and emits a single JSON payload with `{"files":[{"path","mode","new_content"}, ...]}`.
- **Parser behavior**:
  - Expands `{"files":[...]}` into NDJSON operations
  - Salvages inner file objects even if the outer wrapper is truncated/incomplete
- **Observed effect (research-system-v9 draining)**:
  - `ndjson_no_operations` trends toward zero
  - Remaining failures shift to expected truncation-driven partial deliverables + P10 escalation
- **Commit**: `b0fe3cc6`

### BUILD-129 Phase 3 Convergence Hardening (research-system-v9) (2025-12-27) - ✅ COMPLETE (Systemic)
**Root-cause fixes to ensure phases can converge across attempts** under NDJSON + truncation, without workspace drift or destructive “fixes”.
- **Deliverables validation is now cumulative**: required deliverables already present on disk satisfy validation (enables multi-attempt convergence under NDJSON truncation).
- **Scope/workspace root correctness**:
  - Fixed deliverables-aware scope inference to **flatten bucketed deliverables dicts** (`{"code/tests/docs":[...]}`) into real paths (no more accidental `code/tests/docs` as scope roots).
  - `project_build` workspace root now correctly resolves to the **repo root** for standard buckets (`src/`, `docs/`, `tests/`, etc.), preventing false “outside scope” rejections.
- **NDJSON apply correctness**: `governed_apply` treats the synthetic “NDJSON Operations Applied …” header as **already-applied** (skips `git apply` while still enforcing path restrictions).
- **Safety / traceability**:
  - **Blocked** Doctor `execute_fix` of type `git` for `project_build` runs (prevents `git reset --hard` / `git clean -fd` wiping partially-generated deliverables).
  - P10 `TOKEN_ESCALATION` no longer triggers Doctor/replan; retries remain stateful and deterministic.
  - CI logs now always persist a `report_path` to support PhaseFinalizer and later forensic review.

### BUILD-129 Phase 3 Drain Reliability + CI Artifact Correctness + execute_fix Traceability (2025-12-27) - ✅ COMPLETE (Systemic)
- **Drain reliability**: `scripts/drain_queued_phases.py` defaults to an ephemeral `AUTOPACK_API_URL` (free localhost port) when not explicitly set, preventing silent API/DB mismatches that stall draining.
- **Run serialization**: `RunResponse` includes a top-level `phases` list so queued work is visible even when Tier rows are missing (patch-scoped/legacy runs).
- **CI artifact correctness**: pytest CI now emits a pytest-json-report file and returns it as `report_path`; PhaseFinalizer is fail-safe if parsing fails.
- **execute_fix traceability**: blocked actions are always recorded (issue auto-created if needed) and include `run_id` / `phase_id` / `outcome`.

### BUILD-129 Phase 3 DOC_SYNTHESIS Implementation (2025-12-24) - ✅ COMPLETE
**Phase-Based Documentation Estimation** - 76.4% improvement in documentation token prediction accuracy
- **Problem Solved**: Documentation tasks severely underestimated (SMAPE 103.6% on real sample: predicted 5,200 vs actual 16,384 tokens)
- **Root Cause**: Token estimator assumed "documentation = just writing" using flat 500 tokens/deliverable, missing code investigation + API extraction + examples work
- **Solution**: Phase-based additive model with automatic DOC_SYNTHESIS detection
- **Implementation**:
  - **Feature Extraction**: Detects API_REFERENCE.md, EXAMPLES.md, "from scratch" patterns to classify DOC_SYNTHESIS vs DOC_WRITE
  - **Phase-Based Model**: Additive phases (investigation: 2500/2000/1500 tokens based on context | API extraction: 1200 | examples: 1400 | writing: 850/deliverable | coordination: 12% overhead)
  - **Context-Aware**: Adjusts investigation tokens based on code context quality (none/some/strong)
  - **Truncation Handling**: New `is_truncated_output` flag for proper censored data treatment in calibration
  - **Feature Tracking**: 6 new telemetry columns (api_reference_required, examples_required, research_required, usage_guide_required, context_quality, is_truncated_output)
- **Performance Impact**: SMAPE 103.6% → 24.4% (76.4% relative improvement, meets <50% target ✅)
- **Test Coverage**: 10/10 tests passing in [test_doc_synthesis_detection.py](tests/test_doc_synthesis_detection.py)
- **Files Modified**:
  - [src/autopack/token_estimator.py](src/autopack/token_estimator.py) - Feature extraction + classification + phase model
  - [src/autopack/anthropic_clients.py](src/autopack/anthropic_clients.py) - Integration + feature persistence
  - [src/autopack/models.py](src/autopack/models.py) - 6 new telemetry columns
  - [scripts/migrations/add_telemetry_features.py](scripts/migrations/add_telemetry_features.py) - NEW: Database migration
  - [tests/test_doc_synthesis_detection.py](tests/test_doc_synthesis_detection.py) - NEW: 10 comprehensive tests
- **Impact**: Automatic DOC_SYNTHESIS detection, explainable phase breakdown, 2.46x token prediction multiplier, backward compatible

### BUILD-129 Phase 3 Infrastructure Complete (2025-12-24) - ✅ COMPLETE
**Production-Ready Telemetry Collection** - All infrastructure blockers resolved, comprehensive automation in place
- **Problem Solved**: 6 critical infrastructure blockers preventing large-scale telemetry collection (config.py deletion, scope validation failures, Qdrant connection errors, malformed phase specs, run_id tracking, workspace detection)
- **Solution**: Fixed all blockers + implemented comprehensive automation layer with 13 regression tests passing
- **Critical Fixes**:
  1. **Config.py Deletion Prevention**: Restored + PROTECTED_PATHS + fail-fast logic + regression test
  2. **Scope Precedence**: Verified scope.paths checked FIRST before targeted context (fixes 80%+ of validation failures)
  3. **Run_id Backfill**: Best-effort DB lookup prevents "unknown" run_id in telemetry exports
  4. **Workspace Root Detection**: Handles modern project layouts (`fileorganizer/frontend/...`)
  5. **Qdrant Auto-Start**: Docker compose integration + FAISS fallback for zero-friction collection
  6. **Phase Auto-Fixer**: Normalizes deliverables, derives scope.paths, tunes timeouts before execution
- **Automation Layer**:
  - **Batch Drain Script**: [scripts/drain_queued_phases.py](scripts/drain_queued_phases.py) - Safe processing of 160 queued phases
  - **Phase Auto-Fixer**: [src/autopack/phase_auto_fixer.py](src/autopack/phase_auto_fixer.py) - Normalizes specs before execution
  - **Qdrant Auto-Start**: [src/autopack/memory/memory_service.py](src/autopack/memory/memory_service.py) - Zero-friction collection
- **Test Coverage** (13/13 passing):
  - test_governed_apply_no_delete_protected_on_new_file_conflict.py (1 test)
  - test_token_estimation_v2_telemetry.py (5 tests)
  - test_executor_scope_overrides_targeted_context.py (1 test)
  - test_phase_auto_fixer.py (4 tests)
  - test_memory_service_qdrant_fallback.py (3 tests)
- **Initial Collection Results**: 7 samples collected (SMAPE avg: 42.3%, below 50% target ✅)
- **Expected Success Rate**: 40-60% (up from 7% before fixes)
- **Impact**: Zero-friction telemetry collection, 40-60% success rate improvement, safe batch processing of 160 queued phases
- **Files Created/Modified**:
  - [src/autopack/phase_auto_fixer.py](src/autopack/phase_auto_fixer.py) - NEW: Phase normalization
  - [src/autopack/memory/memory_service.py](src/autopack/memory/memory_service.py) - Qdrant auto-start + FAISS fallback
  - [scripts/drain_queued_phases.py](scripts/drain_queued_phases.py) - NEW: Batch processing
  - [docker-compose.yml](docker-compose.yml) - Added Qdrant service
- **Docs**: [BUILD-129_PHASE3_FINAL_SUMMARY.md](docs/BUILD-129_PHASE3_FINAL_SUMMARY.md), [RUNBOOK_QDRANT_AND_TELEMETRY_DRAIN.md](docs/RUNBOOK_QDRANT_AND_TELEMETRY_DRAIN.md)

### BUILD-130 Schema Validation & Circuit Breaker (2025-12-23) - ✅ COMPLETE
**Prevention Infrastructure** - Eliminates infinite retry loops and schema drift errors
- **Problem Solved**: BUILD-127/129 blocked by 500 errors from invalid database enum values (e.g., `state='READY'` not in RunState enum), infinite retry loops burning tokens
- **Solution**: Multi-layer prevention system with schema validation, error classification, and emergency repair
- **Key Components**:
  - **ErrorClassifier**: Classify errors as TRANSIENT (retry) vs DETERMINISTIC (fail-fast) - prevents infinite retries on enum violations, schema errors, bad requests
  - **SchemaValidator**: Startup validation using raw SQL to detect invalid enum values, fuzzy matching for suggested fixes, bypass ORM serialization issues
  - **BreakGlassRepair**: Emergency repair CLI tool with diagnose and repair modes, transaction-safe SQL repairs, audit logging to `.autonomous_runs/break_glass_repairs.jsonl`
  - **Circuit Breaker**: Integrated into executor's `get_run_status()` - classifies API errors, provides remediation suggestions, prevents retry loops
- **Files Created**:
  - [src/autopack/error_classifier.py](src/autopack/error_classifier.py) - Error classification (257 lines)
  - [src/autopack/schema_validator.py](src/autopack/schema_validator.py) - Schema validation (233 lines)
  - [src/autopack/break_glass_repair.py](src/autopack/break_glass_repair.py) - Repair tool (169 lines)
  - [scripts/break_glass_repair.py](scripts/break_glass_repair.py) - CLI interface (122 lines)
- **Integration Points**:
  - [autonomous_executor.py:665-690](src/autopack/autonomous_executor.py#L665-L690) - Startup schema validation
  - [autonomous_executor.py:1040-1106](src/autopack/autonomous_executor.py#L1040-L1106) - Circuit breaker in get_run_status()
  - [config.py:49-66](src/autopack/config.py#L49-L66) - get_database_url() helper
- **Usage**:
  ```bash
  # Diagnose schema issues (read-only)
  python scripts/break_glass_repair.py diagnose

  # Repair schema violations (with confirmation)
  python scripts/break_glass_repair.py repair

  # Auto-repair (use with caution)
  python scripts/break_glass_repair.py repair --auto-approve
  ```
- **Impact**: Prevents infinite retry loops, enables autonomous self-improvement (unblocks BUILD-127/129), provides clear remediation paths for schema issues
- **Status**: Manually implemented (autonomous attempt failed - code already existed from prior manual work)

### BUILD-129 Token Efficiency & Continuation Recovery (2025-12-23) - ✅ COMPLETE
**All 3 Phases Complete** - Proactive truncation prevention and intelligent continuation recovery
- **Phase 1: Output-Size Predictor (Token Estimator) + Validation Infrastructure**
  - Proactive token estimation to prevent truncation before it occurs
  - Calculates base cost (system prompt + context) + per-file generation cost (350 tokens/file for patches, 200 tokens/file for structured edits)
  - Dynamic max_tokens adjustment with 20% safety margin
  - **V2 Telemetry**: Logs real TokenEstimator predictions vs actual output tokens with full metadata (success, truncation, category, complexity)
  - **V3 Analyzer**: Production-ready validation with 2-tier metrics (Risk: underestimation ≤5%, truncation ≤2%; Cost: waste ratio P90 < 3x), success-only filtering, stratification by category/complexity/deliverable-count
  - **Key Learnings**: Second opinion from parallel cursor prevented catastrophic coefficient changes - original baseline measured test inputs, not real predictions
  - **Impact**: 60% truncation rate reduction, saves retries and API costs, enables data-driven coefficient tuning
  - **Status**: Production-ready, awaiting 20+ successful samples for validation
  - **Files**: [token_estimator.py](src/autopack/token_estimator.py) (135 lines), [anthropic_clients.py:652-699](src/autopack/anthropic_clients.py#L652-L699) (V2 telemetry), [analyze_token_telemetry_v3.py](scripts/analyze_token_telemetry_v3.py) (505 lines), [tests/test_token_estimator.py](tests/test_token_estimator.py) (8 tests)
  - **Docs**: [BUILD-129_PHASE1_VALIDATION_COMPLETE.md](docs/BUILD-129_PHASE1_VALIDATION_COMPLETE.md), [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](docs/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md), [TOKEN_ESTIMATION_V3_ENHANCEMENTS.md](docs/TOKEN_ESTIMATION_V3_ENHANCEMENTS.md)
- **Phase 2: Continuation-Based Recovery**
  - Robust continuation recovery for truncated Builder responses using structured continuation plans
  - Builder emits continuation plan when output exceeds token budget, executor resumes from last completed file
  - Smart resume filters patch content to remove already-applied files, re-prompts Builder with "continue from FILE X" instruction
  - **Impact**: 70% token waste reduction (resume from checkpoint vs full regeneration), prevents re-application of already-applied patches
  - **Files**: [autonomous_executor.py:3890-4010](src/autopack/autonomous_executor.py#L3890-L4010), [tests/test_continuation_recovery.py](tests/test_continuation_recovery.py) (6 tests, 184 lines)
- **Phase 3: NDJSON Truncation-Tolerant Format**
  - Newline-delimited JSON (NDJSON) format for all phase outputs enables graceful degradation during truncation
  - Each line is a complete JSON object (event record), so partial output remains parsable
  - NDJSON parser extracts continuation_plan and validates all records, tolerates truncated trailing records
  - **Impact**: Eliminates silent data loss during truncation, enables reliable continuation recovery
  - **Files**: [anthropic_clients.py:2294-2322](src/autopack/anthropic_clients.py#L2294-L2322), [autonomous_executor.py:3950-3990](src/autopack/autonomous_executor.py#L3950-L3990), [tests/test_ndjson_format.py](tests/test_ndjson_format.py) (15 tests, 331 lines)
- **Total**: 29 unit tests passing across all 3 phases
- **Docs**: [BUILD-129_TOKEN_ESTIMATOR.md](docs/BUILD-129_TOKEN_ESTIMATOR.md), [BUILD-129_CONTINUATION_RECOVERY.md](docs/BUILD-129_CONTINUATION_RECOVERY.md), [BUILD-129_NDJSON_FORMAT.md](docs/BUILD-129_NDJSON_FORMAT.md)

### BUILD-128 Deliverables-Aware Manifest System (2025-12-23) - ✅ COMPLETE
**Prevention for Category Mismatches** - Deliverables-first scope inference to prevent pattern matching errors
- **Problem Solved**: ManifestGenerator ignored deliverables field, used pattern matching which incorrectly classified BUILD-127 backend implementation as "frontend" (62%)
- **Solution**: Category inference from deliverable paths via regex patterns (backend/frontend/tests/database/docs/config), path sanitization for human annotations, scope expansion with category-specific context files
- **Impact**: Prevents incorrect phase categorization, fixes BUILD-127 governance rejection, emphasizes future reusability - NOT a one-off fix
- **Files**: [manifest_generator.py](src/autopack/manifest_generator.py) (+270 lines), [deliverables_validator.py](src/autopack/deliverables_validator.py) (sanitize_deliverable_path +48 lines), [tests/test_manifest_deliverables_aware.py](tests/test_manifest_deliverables_aware.py) (19 tests)
- **Docs**: [BUILD-128_DELIVERABLES_AWARE_MANIFEST.md](docs/BUILD-128_DELIVERABLES_AWARE_MANIFEST.md)

### BUILD-127 Self-Healing Governance Foundation (2025-12-23) - ✅ COMPLETE
**All 3 Phases Complete** - Authoritative completion gates and self-negotiation for protected paths
- **Phase 1: Test Baseline Tracker & Phase Finalizer** (Previously completed)
  - TestBaselineTracker: Track test suite baselines across phases, detect regressions
  - PhaseFinalizer: 5-gate completion authority (CI success, quality metrics, deliverables, auditor approval, optional manifest validation)
- **Phase 2: Governance Request Handler**
  - Self-negotiation system for protected path modifications with conservative auto-approval policy
  - Auto-approve tests/docs for low/medium risk, require human approval for core autopack files, block high/critical risk and large changes >100 lines
  - Database audit trail with GovernanceRequest model, CRUD operations (create/approve/deny/get_pending)
  - Pattern-based risk scoring: critical (models.py/governed_apply.py/migrations), high (other autopack files), low (tests/docs), medium (default)
  - **Impact**: Enables controlled self-modification with audit trail, prevents unauthorized changes to core files while allowing safe test/doc updates
  - **Files**: [governance_requests.py](src/autopack/governance_requests.py) (396 lines), [tests/test_governance_requests.py](tests/test_governance_requests.py) (18 tests, 236 lines), [scripts/migrate_governance_table.py](scripts/migrate_governance_table.py) (70 lines)
- **Phase 3: Enhanced Deliverables Validation**
  - Structured manifest validation to ensure Builder creates all expected deliverables with required symbols
  - Builder emits JSON manifest listing created/modified files and their key symbols (classes, functions)
  - PhaseFinalizer Gate 3.5 validates manifest against expected deliverables and file contents
  - Manifest extraction via regex, validation checks file existence + symbol presence via substring search, supports directory deliverables matching
  - **Impact**: Catches missing test files and symbols (BUILD-126 Phase E2 scenario), improves deliverable enforcement beyond file existence
  - **Files**: [anthropic_clients.py:2331-2360](src/autopack/anthropic_clients.py#L2331-L2360), [deliverables_validator.py:942-1079](src/autopack/deliverables_validator.py#L942-L1079), [phase_finalizer.py:177-197](src/autopack/phase_finalizer.py#L177-L197), [tests/test_manifest_validation.py](tests/test_manifest_validation.py) (15 tests, 237 lines)
- **Total**: 33 unit tests passing across Phase 2 & 3 (Phase 1 tests included in earlier builds)
- **Docs**: [BUILD-127-129_IMPLEMENTATION_STATUS.md](docs/BUILD-127-129_IMPLEMENTATION_STATUS.md) (comprehensive implementation status)

### BUILD-123v2 Manifest Generator - Deterministic Scope Generation (2025-12-22) - ✅ COMPLETE
**Meta-Layer Enhancement** - Automatic scope generation from unorganized implementation plans
- **Problem Solved**: BUILD-123v1 (Plan Analyzer) had high token overhead (N LLM calls per phase), ungrounded scope generation (hallucination risk), and governance mismatch
- **Solution**: Deterministic-first manifest generator with 0 LLM calls for >80% of cases
- **Key Architecture**: `Minimal Plan → RepoScanner → PatternMatcher → PreflightValidator → scope.paths → ContextSelector`
- **Core Innovation**:
  - **Earned confidence** from multiple signals (anchor files 40%, match density 30%, locality 20%)
  - **Repo-grounded** (scans actual file structure, respects .gitignore)
  - **Compiles globs to explicit file lists** (not glob patterns for enforcement)
  - **Reuses existing primitives** (emits `scope.paths` for ContextSelector)
  - **85-100% token savings** vs LLM-based approach
- **New Capabilities**:
  - Deterministic repo scanning: Detects anchor files (auth/, api/, database/, etc.)
  - Pattern matching: Keyword → category → scope with confidence scoring
  - Preflight validation: Hard checks before execution (path existence, governance, size caps)
  - Adaptive scope expansion: Controlled strategies (file→parent, add sibling, LLM fallback)
  - Quality gates generation: Default success criteria and validation tests
- **Components Created**:
  - [src/autopack/repo_scanner.py](src/autopack/repo_scanner.py) - Deterministic repo structure analysis (0 LLM calls)
  - [src/autopack/pattern_matcher.py](src/autopack/pattern_matcher.py) - Earned confidence scoring (9 categories)
  - [src/autopack/preflight_validator.py](src/autopack/preflight_validator.py) - Validation (reuses governed_apply logic)
  - [src/autopack/scope_expander.py](src/autopack/scope_expander.py) - Controlled scope expansion (deterministic-first)
  - [src/autopack/manifest_generator.py](src/autopack/manifest_generator.py) - Main orchestrator
  - Docs: [docs/BUILD-123v2_MANIFEST_GENERATOR.md](docs/BUILD-123v2_MANIFEST_GENERATOR.md)
- **Critical Design Decisions** (per GPT-5.2 validation):
  - ✅ Compile globs → explicit list (not glob patterns for enforcement)
  - ✅ Preflight validation (not governed_apply modification)
  - ✅ Earned confidence scores (not assumed from keywords)
  - ✅ Reuse ContextSelector (emit scope.paths, not file_manifest)
  - ✅ Quality gates from deliverables + defaults
  - ✅ Adaptive scope expansion (for underspecified manifests)
- **Impact**: 85-100% token savings, repo-grounded scope (no hallucination), deterministic for >80% cases, reuses existing infrastructure

### BUILD-122 Lovable Integration Setup (2025-12-22) - PHASE 0 READY FOR EXECUTION ✅
**Lovable Integration** - 12 high-value architectural patterns from Lovable AI platform
- Autonomous run created: [`.autonomous_runs/lovable-integration-v1/`](.autonomous_runs/lovable-integration-v1/)
- **GPT-5.2 Independent Validation**: GO WITH REVISIONS (80% confidence) - [VALIDATION_COMPLETE.md](.autonomous_runs/lovable-integration-v1/VALIDATION_COMPLETE.md)
- **Phase 0 Implementation Package**: [PHASE0_EXECUTION_READY.md](.autonomous_runs/lovable-integration-v1/PHASE0_EXECUTION_READY.md) ✅
  - Autonomous run config: [run_config_phase0.json](.autonomous_runs/lovable-integration-v1/run_config_phase0.json)
  - Execution script: [execute_phase0_foundation.py](scripts/execute_phase0_foundation.py)
  - Feasibility assessment: [AUTONOMOUS_IMPLEMENTATION_FEASIBILITY.md](.autonomous_runs/lovable-integration-v1/AUTONOMOUS_IMPLEMENTATION_FEASIBILITY.md)
  - Quality gates checklist: [AUTONOMOUS_IMPLEMENTATION_CHECKLIST.md](.autonomous_runs/lovable-integration-v1/AUTONOMOUS_IMPLEMENTATION_CHECKLIST.md)
- **Critical Corrections Made**:
  - SSE Streaming RESTORED (was incorrectly removed - serves different consumers than Claude Chrome)
  - Architecture rebased onto actual Autopack modules (not Lovable's `file_manifest/`)
  - Semantic embeddings enforced (hash embeddings blocked for Lovable features)
  - Protected-path strategy defined (`src/autopack/lovable/` subtree + narrow allowlist)
- **Expected Impact**: **60% token reduction** (50k→20k), **95% patch success** (+20pp), **75% hallucination reduction**, **50% faster execution**
- **Timeline (Revised)**:
  - **Realistic**: 9 weeks (50% confidence)
  - **Conservative**: 11 weeks (80% confidence) - recommended for stakeholder communication
  - **Aggressive**: 7 weeks (20% confidence)
- **Phase Structure**:
  - **Phase 0**: Foundation & Governance (1 week) - **READY FOR EXECUTION** ✅
  - **Phase 1**: Core Precision (3.5 weeks) - Agentic Search, File Selection, Build Validation, Retry Delays
  - **Phase 1.5**: SSE Streaming (0.5 weeks) - RESTORED
  - **Phase 2**: Quality + Browser Synergy (2.5 weeks)
  - **Phase 3**: Advanced Features (1.5 weeks)
- **Infrastructure Requirements**:
  - sentence-transformers (local semantic embeddings) - `pip install sentence-transformers torch`
  - Morph API subscription ($100/month for Phase 3)
- **Execution Instructions**:
  ```bash
  # Check prerequisites
  python scripts/execute_phase0_foundation.py --dry-run

  # Execute Phase 0 (with approval prompts)
  python scripts/execute_phase0_foundation.py
  ```
- See: [REVISED_IMPLEMENTATION_PLAN.md](.autonomous_runs/lovable-integration-v1/REVISED_IMPLEMENTATION_PLAN.md) for full details

### BUILD-113 Autonomous Investigation + BUILD-114/115 Hotfixes (2025-12-22)
**BUILD-113**: Iterative Autonomous Investigation with Goal-Aware Judgment - COMPLETE ✅
- Proactive decision analysis: Analyzes patches before applying (risk assessment, confidence scoring)
- Auto-apply CLEAR_FIX decisions, request approval for RISKY changes
- Integrated into executor with `--enable-autonomous-fixes` CLI flag
- Validation: Successfully triggered for research-build113-test (decision: risky, HIGH risk, +472 lines)

**BUILD-114**: Structured Edit Support for BUILD-113 Proactive Mode - COMPLETE ✅
- Fixed: BUILD-113 integration now checks BOTH `patch_content` AND `edit_plan` (not just patch_content)
- Builder uses `edit_plan` (structured edits) when context ≥30 files
- Modified: [`src/autopack/integrations/build_history_integrator.py:66-67`](src/autopack/integrations/build_history_integrator.py#L66-L67)

**BUILD-115**: Remove Obsolete models.py Dependencies (7 parts) - COMPLETE ✅
- **Architecture Change**: Executor now fully API-based (no direct database ORM queries)
- Phase selection: Uses `get_next_queued_phase(run_data)` from API instead of DB queries
- Phase execution: Uses `PhaseDefaults` class when database state unavailable
- Database methods: All `_mark_phase_*_in_db()` methods return None (no-ops)
- Result: No more ImportError crashes, executor fully functional with API-only mode

See [`docs/BUILD-114-115-COMPLETION-SUMMARY.md`](docs/BUILD-114-115-COMPLETION-SUMMARY.md) for full details.

### Adaptive structured edits for large scopes (2025-12-09)
- Builder now auto-falls back to structured_edit when full-file outputs truncate or fail JSON parsing on large, multi-path phases (e.g., search, batch-upload).
- Phases can opt into structured_edit via `builder_mode` in the phase spec; large scopes (many files) default to structured_edit to avoid token-cap truncation.
- CI logs can be captured on success per phase (`ci.log_on_success: true`) to aid “needs_review” follow-up.
- Workspace prep: ensure scoped directories exist in the run workspace (e.g., `models/`, `migrations/`) to avoid missing-path scope warnings.
- Reusable hardening templates: see `templates/hardening_phases.json` and `templates/phase_defaults.json` plus `scripts/plan_hardening.py` to assemble project plans; kickoff multi-agent planning with `planning/kickoff_prompt.md`.

### Memory & Context System (IMPLEMENTED & VERIFIED 2025-12-09)
Vector memory for context retrieval and goal-drift detection:

- **Database Architecture**:
  - **Transactional DB**: **PostgreSQL** (default) - Stores phases, runs, decision logs, plan changes, etc.
  - **Vector DB**: **Qdrant** (default) - Production vector search with HNSW indexing, UUID-based point IDs
  - **Fallbacks**: SQLite for transactional (dev/offline via explicit `DATABASE_URL` override); FAISS for vectors (dev/offline)
  - Run PostgreSQL locally: `docker-compose up -d db` (listens on port 5432)
  - Run Qdrant locally: `docker run -p 6333:6333 qdrant/qdrant`
  - Migration: Use `scripts/migrate_sqlite_to_postgres.py` to transfer data from SQLite to PostgreSQL
  - **Status**: ✅ PostgreSQL and Qdrant integration verified with decision logs, phase summaries, and smoke tests passing

- **Vector Memory** (`src/autopack/memory/`):
  - `embeddings.py` - OpenAI + local fallback embeddings
  - `qdrant_store.py` - **Qdrant backend (default)** - Production vector store with deterministic UUID conversion (MD5-based)
  - `faiss_store.py` - FAISS backend (dev/offline fallback)
  - `memory_service.py` - Collections: code_docs, run_summaries, decision_logs, task_outcomes, error_patterns
  - `maintenance.py` - TTL pruning (30 days default)
  - `goal_drift.py` - Detects semantic drift from run goals

- **YAML Validation** (`src/autopack/validators/yaml_validator.py`):
  - Pre-apply syntax validation for YAML/docker-compose files
  - Truncation marker detection
  - Docker Compose schema validation

- **Executor Integration**:
  - Retrieved context injected into builder prompts
  - Post-phase hooks write summaries/errors to vector memory
  - Goal drift check before apply (advisory mode by default)

- **Configuration** (`config/memory.yaml`):
  ```yaml
  enable_memory: true
  use_qdrant: true  # Default to Qdrant (set false for FAISS fallback)
  qdrant:
    host: localhost
    port: 6333
    api_key: ""  # Optional for Qdrant Cloud
  top_k_retrieval: 5
  goal_drift:
    enabled: true
    mode: advisory  # or 'blocking'
    threshold: 0.7
  ```

See `docs/IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md` for full details.

### Intent Router (2025-12-09)
Natural-language entrypoint that maps user intents to safe Autopack actions (no raw commands):
- Script: `scripts/intent_router.py`
- Supports: refresh planning artifacts (ingest + embeddings), memory maintenance (TTL + tombstones), show plan changes/decision log, query planning context.
- Usage examples:
  ```bash
  python scripts/intent_router.py --query "refresh planning artifacts" --project-id file-organizer-app-v1
  python scripts/intent_router.py --query "run memory maintenance" --project-id file-organizer-app-v1 --ttl-days 30
  python scripts/intent_router.py --query "show plan changes" --project-id file-organizer-app-v1
  python scripts/intent_router.py --query "planning context for kickoff" --project-id file-organizer-app-v1
  ```

### Diagnostics (governed troubleshooting)
- Governed diagnostics agent runs allowlisted probes with budgets/timeouts and saves artifacts to `.autonomous_runs/<run_id>/diagnostics`.
- Evidence-first: collects git status/diff, executor logs, env/dependency info, and probe outputs before any mutations; summaries land in DecisionLog + vector memory.
- Intent router supports `diagnose patch failure` and `diagnose ci failure` for manual, read-only runs (uses the same governed palette).
- Executor triggers diagnostics automatically on patch/CI/infra failures to capture signals and hypotheses for Doctor/maintainers.
- Config: `config/diagnostics.yaml` controls budgets, allowed hosts, baseline logs, and sandbox copy paths for risky probes (sandboxed commands run inside `.autonomous_runs/<run_id>/diagnostics/sandbox`).
- Dashboard: `/api/diagnostics/latest` and the dashboard “Latest Diagnostics” card show the most recent diagnostic summary (failure, ledger, probes) read-only.

### Backlog Maintenance (OPTIMIZED 2025-12-10)
Autonomous maintenance system for processing backlog items with propose-first diagnostics and optional patching:

**Core Features**:
- Mode: opt-in "maintenance/backlog" run that ingests a curated backlog file (e.g., `consolidated_debug.md`) and turns items into scoped phases with `allowed_paths`, budgets, and targeted probes/tests.
- Safety: propose-first by default (generate patch + diagnostics + tests); apply only after validation/approval. Use governed_apply, diagnostics runner, and allowlisted commands only.
- Checkpoints: branch per maintenance run; checkpoint commit (or stash) before apply; auto-revert on failed apply/tests; prefer PR generation for higher risk.
- Budgets: one item at a time; caps on probes/commands/time per item; execute_fix remains opt-in/disabled by default.

**Efficiency Optimizations (2025-12-10)** ⚡:
- **Test Execution**: Workspace tests run once before processing items (not per-item) - saves ~63s per 10 items
- **Test Output Storage**: Reference-based deduplication using SHA256 hashes - reduces storage by 80% (~90KB → ~18KB)
- **Artifact Paths**: Relative paths for cross-platform portability (no more absolute Windows paths)
- **File Operations**: Smart existence checks before tail operations - eliminates 30-40 failed commands per run
- **Overall Impact**: 33% faster execution (240s → 160s), 80% smaller artifacts, 100% fewer error logs

**Tooling**:
- `scripts/backlog_maintenance.py --backlog consolidated_debug.md --allowed-path src/` - emits maintenance plan JSON (propose-first)
- `scripts/run_backlog_plan.py --plan .autonomous_runs/backlog_plan.json` - runs diagnostics over plan (propose-first, no apply)
- `scripts/run_backlog_maintenance.py --backlog consolidated_debug.md --allowed-path src/ --checkpoint --test-cmd "pytest -q tests/smoke/"` - end-to-end: parse → plan → diagnostics with test deduplication
- Optional apply: `--apply --patch-dir patches/` applies per-item patches (named `<item_id>.patch`) only if auditor approves

**Observability**:
- Artifacts: `.autonomous_runs/<run_id>/diagnostics/` with command logs, summaries, and test cache
- Test Cache: `test_output_cache.json` stores unique test outputs by hash reference
- Summaries: `backlog_diagnostics_summary.json` with `test_hashes` field for efficient lookups
- DecisionLog + dashboard diagnostics card surface latest run

**Maintenance Auditor** (FIXED 2025-12-10):
- Proposals must satisfy scope/diff/test safety to be auto-approved
- Properly handles `None` diffs (no patch provided) without AttributeError
- Rejects if protected paths touched; requires human review for out-of-scope or oversized changes
- Targeted tests: auditor sees results and will require_human if tests missing/failing

**Low-risk Auto-apply** (recommended safeguards):
- Keep checkpoints on by default
- Only auto-apply auditor-approved patches that are in-scope, small (files/lines), with passing targeted tests
- Anything else remains propose-first for human review

**Executor CLI Flags**:
- `--maintenance-plan`, `--maintenance-patch-dir`, `--maintenance-apply`, `--maintenance-checkpoint`, `--maintenance-auto-apply-low-risk` control maintenance mode
- Low-risk auto-apply enforces extra size/test guards and requires checkpoint

### Universal Research Analysis System (IMPLEMENTED 2025-12-13)
Strategic decision-making system that analyzes research files against project state to identify implementation opportunities:

**Purpose**: Turn research (product vision, market analysis, domain requirements) into actionable implementation decisions.

**4-Phase Pipeline**:
1. **Context Assembly** - Builds comprehensive project context from:
   - SOT files (current state): BUILD_HISTORY, ARCHITECTURE_DECISIONS, DEBUG_LOG, FUTURE_PLAN, LEARNED_RULES
   - Research files (strategy): product vision, market research, domain requirements
   - Database: PostgreSQL + Qdrant semantic search

2. **Research Analysis** - Finds gaps between current state and research:
   - Feature gaps (market opportunities vs implemented features)
   - Compliance gaps (regulatory requirements vs current state)
   - Competitive gaps (competitors' features vs our features)
   - Vision alignment gaps (vision vs current implementation)

3. **Decision Making** - Makes strategic decisions with full context:
   - Uses Claude Sonnet for strategic reasoning
   - Considers: vision alignment, user impact, competitive necessity, dependencies, ROI
   - Outputs: IMPLEMENT_NOW, IMPLEMENT_LATER, REVIEW, or REJECT

4. **Decision Routing** - Routes decisions to appropriate locations:
   - IMPLEMENT_NOW → `archive/research/active/`
   - IMPLEMENT_LATER → `docs/FUTURE_PLAN.md`
   - REVIEW → `archive/research/reviewed/deferred/`
   - REJECT → `archive/research/reviewed/rejected/`

**Universal Design**: Works for ANY project (Autopack, file-organizer-app-v1, or future projects).

**Usage**:
```bash
# Run full analysis pipeline
python scripts/research/run_universal_analysis.py file-organizer-app-v1

# Run individual components
python scripts/research/context_assembler.py file-organizer-app-v1
python scripts/research/research_analyzer.py file-organizer-app-v1
python scripts/research/decision_engine.py file-organizer-app-v1
```

**Outputs**:
- `context.json` - Assembled project context
- `opportunity_analysis.json` - Gap analysis with prioritized opportunities
- `decision_report.json` - Strategic decisions with rationale
- Updated `docs/FUTURE_PLAN.md` - IMPLEMENT_LATER items appended
- Routed research files in appropriate directories

**Key Features**:
- Supports both **initial planning** AND **ongoing improvement**
- **Comprehensive context** about current state, market, domain, vision
- **Strategic decisions** based on full context awareness
- **Transparent reasoning** (every decision includes rationale, alignment, impact, ROI)

See `archive/reports/BUILD_universal_research_analysis_system.md` for full documentation.

## Repository Structure (Autopack + Projects)
- Autopack core lives at the repo root and includes executor, diagnostics, dashboard, and tooling.
- Project artifacts live under `.autonomous_runs/<project>/` (plans, diagnostics, consolidated logs); e.g., `file-organizer-app-v1` is the first project built with Autopack.
- Additional projects stay under `.autonomous_runs/<project>/` within this repo (not separate repos).
- Use branches per project/maintenance effort when applying automated fixes to keep histories clean; checkpoints are recommended for maintenance/apply flows.

### Multi-Project Documentation & Tidy System (2025-12-13)

**Standardized 6-File SOT Structure**:
All projects follow a consistent documentation structure for AI navigation:
1. **PROJECT_INDEX.json** - Quick reference (setup, API, structure)
2. **BUILD_HISTORY.md** - Implementation history (auto-updated)
3. **DEBUG_LOG.md** - Troubleshooting log (auto-updated)
4. **ARCHITECTURE_DECISIONS.md** - Design decisions (auto-updated)
5. **FUTURE_PLAN.md** - Roadmap and backlog (manual)
6. **LEARNED_RULES.json** - Auto-updated learned rules (auto-updated)

**Autonomous Tidy Workflow**:
Automatically consolidates archive files into SOT documentation using AI-powered classification:

```bash
# Tidy a project's archive directory
cd .autonomous_runs/your-project
python ../../scripts/tidy/autonomous_tidy.py archive --dry-run    # Preview changes
python ../../scripts/tidy/autonomous_tidy.py archive --execute    # Apply changes

# The system auto-detects the project from your working directory
```

**Excluded Directories**:
The tidy system automatically excludes these directories from processing:
- `superseded/` - Already classified files moved here after manual review
- `.git/` - Version control files
- `.autonomous_runs/` - Runtime artifacts
- `__pycache__/`, `node_modules/` - Build artifacts

Files in `archive/superseded/` have been reviewed and classified into SOT files and will not be processed again.

**Adding New Projects**:
1. Create project structure under `.autonomous_runs/<project-id>/`
2. Add configuration to database OR add default config in `scripts/tidy/project_config.py`:
   ```python
   elif project_id == "your-project":
       return {
           'project_id': 'your-project',
           'project_root': '.autonomous_runs/your-project',
           'docs_dir': 'docs',
           'archive_dir': 'archive',
           'sot_build_history': 'BUILD_HISTORY.md',
           'sot_debug_log': 'DEBUG_LOG.md',
           'sot_architecture': 'ARCHITECTURE_DECISIONS.md',
           'sot_unsorted': 'UNSORTED_REVIEW.md',
           'project_context': {
               'keywords': {
                   'build': ['implementation', 'feature', 'build'],
                   'debug': ['error', 'bug', 'fix'],
                   'architecture': ['decision', 'design', 'architecture']
               }
           },
           'enable_database_logging': True,
           'enable_research_workflow': True
       }
   ```

3. Run tidy from within your project directory - it will auto-detect the project and update the correct docs/ folder

**File Organization**:
- ✅ **SOT files** (6 files) go in `<project>/docs/`
- ✅ **Runtime cache** (phase plans, issue backlogs) go in `.autonomous_runs/`
- ✅ **Historical files** go in `<project>/archive/` (organized by type: plans/, reports/, research/, etc.)

See [PROJECT_INDEX.json](docs/PROJECT_INDEX.json) for complete configuration reference.

#### Script Organization System (Step 0 of Autonomous Tidy)

The Script Organization System automatically moves scattered scripts, patches, and configuration files from various locations into organized directories within the `scripts/` and `archive/` folders as **Step 0** of the autonomous tidy workflow.

**What Gets Organized:**

1. **Root Scripts** → `scripts/archive/root_scripts/`
   - Scripts at the repository root level: `*.py`, `*.sh`, `*.bat`
   - Example: `probe_script.py`, `test_auditor_400.py`, `run_full_probe_suite.sh`

2. **Root Reports** → `archive/reports/`
   - Markdown documentation from root: `*.md` (will be consolidated by tidy)
   - Example: `REPORT_TIDY_V7.md`, `ANALYSIS_PHASE_PLAN.md`

3. **Root Logs** → `archive/diagnostics/`
   - Log and debug files from root: `*.log`, `*.diff`
   - Example: `tidy_execution.log`, `patch_apply.diff`

4. **Root Config** → `config/`
   - Configuration files from root: `*.yaml`, `*.yml`
   - Example: `tidy_scope.yaml`, `models.yaml`

5. **Examples** → `scripts/examples/`
   - All files from `examples/` directory
   - Example: `multi_project_example.py`

6. **Tasks** → `archive/tasks/`
   - Task configuration files: `*.yaml`, `*.yml`, `*.json`
   - Example: `tidy_consolidation.yaml`

7. **Patches** → `archive/patches/`
   - Git patches and diff files: `*.patch`, `*.diff`
   - Example: `oi-fo-ci-failure.patch`

**What Stays in Place** (Never Moved):

Special Files:
- `setup.py`, `manage.py` - Package setup
- `conftest.py` - Pytest configuration
- `wsgi.py`, `asgi.py` - WSGI/ASGI entry points
- `__init__.py` - Python package markers
- `README.md` - Project README (stays at root)
- `docker-compose.yml`, `docker-compose.dev.yml` - Docker configs (stay at root)

Directories (Never Scanned):
- `scripts/` - Already organized
- `src/` - Source code
- `tests/` - Test suites (pytest)
- `config/` - Configuration files
- `.autonomous_runs/` - Sub-project workspaces
- `archive/` - Already archived
- `.git/`, `venv/`, `node_modules/`, `__pycache__/` - System directories

**Usage:**

```bash
# Manual standalone script organization (preview)
python scripts/organize_scripts.py

# Execute the organization
python scripts/organize_scripts.py --execute

# Automatic organization (integrated with tidy - runs as Step 0)
python scripts/tidy/autonomous_tidy.py archive --execute
```

**Note:** Script organization only runs for the **main Autopack project**, not for sub-projects in `.autonomous_runs/`.

**Integration with Autonomous Tidy:**

The script organizer runs as **Step 0** before the main tidy workflow:

```
AUTONOMOUS TIDY WORKFLOW
═══════════════════════════════════════════════════════════

Step 0: Script Organization (Autopack only)
   ↓
Step 1: Pre-Tidy Auditor
   ↓
Step 2: Documentation Consolidation
   ↓
Step 3: Archive Cleanup (sub-projects only)
   ↓
Step 4: Database Synchronization
   ↓
Post-Tidy Verification
```

**Configuration:** The script organization rules are defined in [scripts/tidy/script_organizer.py](scripts/tidy/script_organizer.py). To add new organization rules, edit the `script_patterns` configuration in that file.

## Plan Conversion (Markdown -> phase_spec)
- Use `scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/<project>/plan_generated.json` to convert markdown tasks into phase specs matching `docs/phase_spec_schema.md`.
- Inline tags in bullets override defaults: `[complexity:low]`, `[category:tests]`, `[paths:src/,tests/]`, `[read_only:docs/]`.
- Defaults: complexity=medium, task_category=feature; acceptance criteria come from indented bullets under each task.
- Fully automated run: `scripts/auto_run_markdown_plan.py --plan-md docs/PLAN.md --run-id my-run --patch-dir patches --apply --auto-apply-low-risk --test-cmd "pytest -q tests/smoke"` converts → plan JSON → runs maintenance mode (diagnostics first, gated apply). Checkpoints are on by default for maintenance runs.

## Owner Intent (Troubleshooting Autonomy)
- Autopack should approach Cursor “tier 4” troubleshooting depth: when failures happen, it should autonomously run governed probes/commands (from a vetted allowlist), gather evidence (logs, test output, patch traces), iterate hypotheses, and log decisions—without requiring the user to type raw commands.
- Natural-language control is preferred: the intent router (and future dashboard hooks) should trigger safe actions like planning ingest, memory maintenance, diagnostics, and context queries.
- Safety is mandatory: all actions must respect allowlists/denylists, timeouts, budgets, and avoid destructive ops; writes happen only in approved worktrees/contexts.
- See `docs/IMPLEMENTATION_PLAN_DIAGNOSTICS_PARITY_WITH_CURSOR.md` for the implementation plan to reach this capability.

### Patch Apply Hardening (2025-12-06)
- `GovernedApplyPath` now refuses the direct-write fallback whenever a patch touches existing files; fallback is limited to clean new-file-only patches and must write all expected files.
- Patch validation still runs first (dry-run git apply, lenient/3-way) and preserves backups; scope + protected-path enforcement remains unchanged.
- SQLite dev DB (`autopack.db`) now includes the `phases.scope` column to match the production schema (run_id already present).

### Comprehensive Error Reporting System (NEW)
Detailed error context capture and reporting for easier debugging:
- **Automatic Error Capture**: All exceptions automatically captured with full context
- **Rich Context**: Stack traces, phase/run info, request data, environment details
- **Error Reports**: Saved to `.autonomous_runs/{run_id}/errors/` as JSON + human-readable text
- **API Endpoints**:
  - `GET /runs/{run_id}/errors` - Get all error reports for a run
  - `GET /runs/{run_id}/errors/summary` - Get error summary
- **Stack Frame Analysis**: Captures local variables and function context at each stack level
- **Component Tracking**: Identifies where errors occurred (api, executor, builder, etc.)

**Error Report Location**:
```
.autonomous_runs/
  {run_id}/
    errors/
      20251203_013555_api_AttributeError.json  # Detailed JSON
      20251203_013555_api_AttributeError.txt   # Human-readable summary
```

**Usage**:
```bash
# View error summary for a run
curl http://localhost:8000/runs/my-run-id/errors/summary

# Get all error reports
curl http://localhost:8000/runs/my-run-id/errors
```

### Deletion Safeguards & Telegram Notifications (NEW - BUILD-107 to BUILD-111)
Two-tier deletion protection system with mobile notifications:

**Two-Tier Notification System**:
| Net Deletion   | Action            | Rationale                                      |
|----------------|-------------------|------------------------------------------------|
| < 100 lines    | No notification   | Small changes, safe to proceed automatically   |
| 100-200 lines  | **Notify only**   | Send Telegram notification, execution continues|
| > 200 lines    | **Block + Notify**| Require human approval via Telegram            |
| 50+ lines      | **Auto-save**     | Create git tag save point before deletion      |

**Key Features**:
- **Automatic Save Points**: Git tags created before deletions >50 lines for easy recovery
- **Telegram Integration**: Mobile notifications for large deletions and phase failures
- **Interactive Approval**: Optional approve/reject buttons via webhook (requires ngrok)
- **Smart Detection**: Net deletion calculation (lines removed - lines added)

**Configuration** (`.env`):
```bash
# Required for Telegram notifications
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"

# Optional for interactive buttons
NGROK_URL="https://your-domain.ngrok.app"
AUTOPACK_CALLBACK_URL="http://localhost:8001"
```

**Setup & Testing**:
```bash
# Interactive setup wizard
python scripts/setup_telegram.py

# Verify credentials
python scripts/verify_telegram_credentials.py

# Test notifications (no actual deletions)
python scripts/test_deletion_safeguards.py --test-telegram

# Test full approval workflow (requires ngrok + backend)
python scripts/test_deletion_safeguards.py --test-approval

# Test threshold sensitivity
python scripts/test_deletion_safeguards.py --test-thresholds
```

**Recovery from Deletions**:
```bash
# List save points
git tag | grep save-before-deletion

# Restore from save point
git reset --hard save-before-deletion-{phase_id}-{timestamp}
```

See [docs/BUILD-107-108_SAFEGUARDS_SUMMARY.md](docs/BUILD-107-108_SAFEGUARDS_SUMMARY.md) for complete documentation.

### Iterative Autonomous Investigation (NEW - BUILD-113)
Multi-round autonomous debugging that resolves failures without human intervention when safe, plus **proactive decision-making** for fresh feature implementations:

**Key Features**:
- **Goal-Aware Decisions**: Uses deliverables + acceptance criteria to guide fixes
- **Multi-Round Investigation**: Iteratively collects evidence until root cause found (reactive mode)
- **Proactive Patch Analysis**: Analyzes fresh patches BEFORE applying them (NEW)
- **Autonomous Low-Risk Fixes**: Auto-applies fixes <100 lines with no side effects
- **Full Audit Trails**: All decisions logged with rationale and alternatives
- **Safety Nets**: Git save points, automatic rollback, risk-based gating

**How It Works**:

*Reactive Mode* (after failure):
1. **Investigation**: Autopack runs multi-round diagnostics, collecting evidence iteratively
2. **Goal Analysis**: Compares evidence against phase deliverables and acceptance criteria
3. **Risk Assessment**: LOW (<100 lines, safe), MEDIUM (100-200, notify), HIGH (>200, block)
4. **Autonomous Fix**: For low-risk fixes, auto-applies with git save point + rollback on failure
5. **Smart Escalation**: Only blocks for truly risky (protected paths, large deletions) or ambiguous situations

*Proactive Mode* (NEW - before applying):
1. **Patch Analysis**: Builder generates patch, BUILD-113 analyzes it before application
2. **Risk Classification**: Database files → HIGH, >200 lines → HIGH, 100-200 → MEDIUM, <100 → LOW
3. **Confidence Scoring**: Based on deliverables coverage, patch size, code clarity
4. **Decision**:
   - **CLEAR_FIX** (LOW/MED risk + high confidence) → Auto-apply with DecisionExecutor
   - **RISKY** (HIGH risk) → Request human approval via Telegram before applying
   - **AMBIGUOUS** (low confidence or missing deliverables) → Request clarification
5. **Safe Execution**: All CLEAR_FIX patches applied with save points, validation, rollback on failure

**Enable** (experimental, default: false):
```bash
python -m autopack.autonomous_executor \
  --run-id my-run \
  --enable-autonomous-fixes
```

**Review Decision Logs**:
```bash
# View autonomous decisions
cat .autonomous_runs/my-run/decision_log.json

# Each decision includes:
# - Rationale (why this fix?)
# - Alternatives considered (what else was possible?)
# - Risk assessment (why low/medium/high?)
# - Deliverables met (which goals achieved?)
# - Files modified + net deletion count
# - Git save point for rollback
```

**Example Autonomous Fix**:
```
Phase: research-tracer-bullet
Failure: ImportError - cannot import 'TracerBullet'

Round 1: Initial diagnostics
- Found: TracerBullet class exists in tracer_bullet.py
- Missing: Import statement in __init__.py

Decision: CLEAR_FIX (auto-applied)
- Fix: Add "from .tracer_bullet import TracerBullet" to __init__.py
- Risk: LOW (1 line added, within allowed_paths, no side effects)
- Result: Tests passed, deliverable met, committed automatically
- Save point: git tag save-before-fix-research-tracer-bullet-20251221
```

See [docs/BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md](docs/BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md) for complete documentation.

### Autopack Doctor
LLM-based diagnostic system for intelligent failure recovery:
- **Failure Diagnosis**: Analyzes phase failures and recommends recovery actions
- **Model Routing**: Uses Claude Sonnet 4.5 for routine failures and Claude Opus 4.5 for complex ones
- **Actions**: `retry_with_fix` (with hint), `replan`, `skip_phase`, `mark_fatal`, `rollback_run`
- **Budgets**: Per-phase limit (2 calls) and run-level limit (10 calls) to prevent loops
- **Confidence Escalation**: Upgrades to strong model if confidence < 0.7
- **Rule Refresh**: Project learned rules auto-reload mid-run when updated, so replans use the latest hints/rules without restarting.

**Configuration** (`config/models.yaml`):
```yaml
doctor_models:
  cheap: claude-sonnet-4-5
  strong: claude-opus-4-5
  min_confidence_for_cheap: 0.7
  health_budget_near_limit_ratio: 0.8
  high_risk_categories: [import, logic]
```

### Model Escalation System
Automatically escalates to more powerful models when phases fail repeatedly:
- **Intra-tier escalation**: Within complexity level (e.g., glm-4.6 -> claude-sonnet-4-5)
- **Cross-tier escalation**: Bump complexity level after N failures (low -> medium -> high)
- **Configurable thresholds**: `config/models.yaml` defines `complexity_escalation` settings

### Mid-Run Re-Planning with Message Similarity
Detects "approach flaws" vs transient failures using error message similarity:
- `_normalize_error_message()` - Strips variable content (paths, UUIDs, timestamps, line numbers)
- `_calculate_message_similarity()` - Uses `difflib.SequenceMatcher` with 0.8 threshold
- `_detect_approach_flaw()` - Triggers re-planning after consecutive same-type failures with similar messages

**Configuration** (`config/models.yaml`):
```yaml
replan:
  trigger_threshold: 2
  message_similarity_enabled: true
  similarity_threshold: 0.8
  fatal_error_types: [wrong_tech_stack, schema_mismatch, api_contract_wrong]
```

### Run-Level Health Budget
Prevents infinite retry loops by tracking failures across the run:
- `MAX_HTTP_500_PER_RUN`: 10 (stop after too many server errors)
- `MAX_PATCH_FAILURES_PER_RUN`: 15 (stop after too many patch failures)
- `MAX_TOTAL_FAILURES_PER_RUN`: 25 (hard cap on total failures)

### LLM Multi-Provider Routing
- Routes primarily to Anthropic (Claude Sonnet/Opus). GLM is disabled; OpenAI is fallback.
- **Provider tier strategy**:
  - Low/Medium/High: Claude Sonnet 4.5 (primary), escalate to Claude Opus 4.5 when needed
- Automatic fallback chain: Anthropic -> OpenAI
- Per-category routing policies (BEST_FIRST, PROGRESSIVE, CHEAP_FIRST)

**Environment Variables**:
```bash
# Required for each provider you want to use
ANTHROPIC_API_KEY=your-anthropic-key   # Anthropic - primary
OPENAI_API_KEY=your-openai-key         # OpenAI - optional fallback

# Backend auth (JWT, RS256)
JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----...dev or prod key...-----END PRIVATE KEY-----"
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----...dev or prod key...-----END PUBLIC KEY-----"
# Optional overrides
JWT_ISSUER=autopack-backend
JWT_AUDIENCE=autopack-clients
```

### Auth tokens & JWKS
- Tokens are RS256 JWTs with `iss`/`aud` enforced.
- JWKS endpoint: `/api/auth/.well-known/jwks.json` (share with verifiers).
- Key load status: `/api/auth/key-status` (reports env vs generated keys).

### 📊 Real-Time Dashboard
- Provides run status, usage, and models list. Refer to `tests/test_dashboard_integration.py` for expected payloads/fields.
- Key routes (FastAPI):
  - `GET /dashboard/status` — overall health/version.
  - `GET /dashboard/usage` — recent token/phase usage aggregates.
  - `GET /dashboard/models` — current model routing table (source: `config/models.yaml`).
- Start the dashboard/API: `python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8100` (set `PYTHONPATH=src`, `DATABASE_URL=sqlite:///autopack.db`).
- Architecture: **LlmService (Model Router + Usage Track)** is the central control-plane routing layer feeding dashboard/model metadata.

### Hardening: Syntax + Unicode + Incident Fatigue
- Pre-emptive encoding fix at startup
- `PYTHONUTF8=1` environment variable for all subprocesses
- UTF-8 encoding on all file reads
- SyntaxError detection in CI checks

### Stage 2: Structured Edits for Large Files (NEW)
Enables safe modification of files of any size using targeted edit operations:
- **Automatic Mode Selection**: Files >1000 lines automatically use structured edit mode
- **Operation Types**: INSERT, REPLACE, DELETE, APPEND, PREPEND
- **Safety Features**: Validation, context matching, rollback on failure
- **No Truncation Risk**: Only generates changed lines, not entire file content
- **Format Contract**: Builder outputs must be JSON with a `files` array; legacy git-diff fallback is disabled for malformed outputs.

**3-Bucket Policy**:
- **Bucket A (≤500 lines)**: Full-file mode - LLM outputs complete file content
- **Bucket B (501-1000 lines)**: Diff mode - LLM generates git diff patches  
- **Bucket C (>1000 lines)**: Structured edit mode - LLM outputs targeted operations

For details, see [Stage 2 Documentation](docs/stage2_structured_edits.md) and [Phase Spec Schema](docs/phase_spec_schema.md).

---

## Phase 3 Preview: Direct Fix Execution

### Doctor `execute_fix` Action (Coming Soon)
Enables Doctor to execute infrastructure-level fixes directly without going through Builder:
- **Problem Solved**: Merge conflicts, missing files, Docker issues currently require manual intervention
- **Solution**: Doctor emits shell commands (`git checkout`, `docker restart`, etc.) executed directly
- **Safety**: Strict whitelist, workspace-only paths, opt-in via config, no sudo/admin

**Configuration** (`config/models.yaml`):
```yaml
doctor:
  allow_execute_fix_global: true    # Enabled (whitelisted commands only)
  max_execute_fix_per_phase: 1      # One attempt per phase
  allowed_fix_types: ["git", "file"] # Typed categories
```

**Supported Fix Types** (v1):
- `git`: `checkout`, `reset`, `stash`, `clean`, `merge --abort`
- `file`: `rm`, `mkdir`, `cp`, `mv` (workspace only)
- `python`: `pip install`, `pytest` (planned)

See [IMPLEMENTATION_PLAN.md](archive/IMPLEMENTATION_PLAN.md) for full design details.

---

## Documentation

### Core Documentation
- **[Phase Spec Schema](docs/phase_spec_schema.md)**: Phase specification format, safety flags, and file size limits
- **[Stage 2: Structured Edits](docs/stage2_structured_edits.md)**: Guide to structured edit mode for large files
- **[IMPLEMENTATION_PLAN2.md](IMPLEMENTATION_PLAN2.md)**: File truncation bug fix and safety improvements
- **[IMPLEMENTATION_PLAN3.md](IMPLEMENTATION_PLAN3.md)**: Structured edits implementation plan
- **Planner Prompt (Autopack-ready)**: `prompts/claude/planner_prompt.md` now enforces non-empty descriptions, explicit scope (modifiable paths + read-only context), acceptance criteria, and token/attempt caps for every phase.

### Archive Documentation
Detailed historical documentation is available in the `archive/` directory:

- **[Archive Index](archive/ARCHIVE_INDEX.md)**: Master index of all archived documentation
- **[Claude-GPT Consultation](archive/CONSOLIDATED_CORRESPONDENCE.md)**: Index of all Claude-GPT consultation exchanges
- **[Consultation Summary](archive/GPT_CLAUDE_CONSULTATION_SUMMARY.md)**: Executive summary of all Phase 1 implementation decisions
- **[Autonomous Executor](archive/CONSOLIDATED_REFERENCE.md#autonomous-executor-readme)**: Guide to the orchestration system
- **[Learned Rules](LEARNED_RULES_README.md)**: System for preventing recurring errors
- **[Implementation Plan](archive/IMPLEMENTATION_PLAN.md)**: Historical roadmap and Phase 3+ planning

For detailed decision history, see the `archive/correspondence/` directory (52 individual exchanges).

## Project Structure

```
C:/dev/Autopack/
├── .autonomous_runs/         # Runtime data and project-specific archives
│   ├── file-organizer-app-v1/# Example Project: File Organizer
│   └── ...
├── archive/                  # Framework documentation archive
├── config/
│   └── models.yaml           # Model configuration, escalation, routing policies
├── logs/
│   └── archived_runs/        # Archived log files from previous runs
├── src/
│   └── autopack/             # Core framework code
│       ├── autonomous_executor.py  # Main orchestration loop
│       ├── llm_service.py          # Multi-provider LLM abstraction
│       ├── model_router.py         # Model selection with quota awareness
│       ├── model_selection.py      # Escalation chains and routing policies
│       ├── error_recovery.py       # Error categorization and recovery
│       ├── archive_consolidator.py # Documentation management
│       ├── debug_journal.py        # Self-healing system wrapper
│       ├── memory/                 # Vector memory for context retrieval
│       │   ├── embeddings.py       # Text embeddings (OpenAI + local)
│       │   ├── faiss_store.py      # FAISS backend
│       │   ├── memory_service.py   # High-level insert/search
│       │   ├── maintenance.py      # TTL pruning
│       │   └── goal_drift.py       # Goal drift detection
│       ├── validators/             # Pre-apply validation
│       │   └── yaml_validator.py   # YAML/compose validation
│       └── ...
├── scripts/                  # Utility scripts
│   └── consolidate_docs.py   # Documentation consolidation
└── tests/                    # Framework tests
```

## Key Features

- **Autonomous Orchestration**: Wires Builder and Auditor agents to execute phases automatically.
- **Model Escalation**: Automatically escalates to more powerful models after failures.
- **Mid-Run Re-Planning**: Detects approach flaws and revises phase strategy.
- **Self-Healing**: Automatically logs errors, fixes, and extracts prevention rules.
- **Quality Gates**: Enforces risk-based checks before code application.
- **Multi-Provider LLM**: Routes to Gemini, GLM, Anthropic, or OpenAI with automatic fallback.
- **Project Separation**: Strictly separates runtime data and docs for different projects.

## Usage

### Running an Autonomous Build

```bash
python src/autopack/autonomous_executor.py --run-id my-new-run
```

### File Organization & Storage Structure

#### 🗂️ Directory Structure by Project

**Autopack Core** (`C:\dev\Autopack\`):
```
C:\dev\Autopack/
├── docs/                          # Truth sources for Autopack project
│   ├── README.md                  # Main Autopack documentation
│   └── consolidated_*.md          # Consolidated reference docs
├── scripts/                       # Active scripts (organized by type)
│   ├── backend/                   # Backend-related scripts (API, database)
│   ├── frontend/                  # Frontend-related scripts (UI, components)
│   ├── test/                      # Test scripts (pytest, unittest)
│   ├── temp/                      # Temporary/scratch scripts
│   └── utility/                   # General utility scripts (.sql, runners)
├── archive/                       # Archived Autopack artifacts
│   ├── plans/                     # Archived planning documents (.md, .json, .yaml)
│   ├── analysis/                  # Archived analysis & reviews (.md)
│   ├── logs/                      # Archived logs (.log, failure .json)
│   ├── prompts/                   # Archived prompts & delegations (.md)
│   ├── scripts/                   # Archived scripts (.py, .sh, .ps1)
│   ├── superseded/                # Old/superseded documents
│   └── unsorted/                  # Inbox for unclassified files
└── .autonomous_runs/              # Runtime data (see below)
```

**File Organizer Project** (`.autonomous_runs/file-organizer-app-v1/`):
```
.autonomous_runs/file-organizer-app-v1/
├── docs/                          # Truth sources for File Organizer
│   ├── WHATS_LEFT_TO_BUILD.md     # Current build plan
│   ├── CONSOLIDATED_*.md          # Consolidated docs
│   └── README.md                  # Project documentation
├── runs/                          # Active run outputs (NEW STRUCTURE)
│   ├── fileorg-country-uk/        # Family: UK country pack runs
│   │   ├── fileorg-country-uk-20251205-132826/
│   │   │   ├── run.log            # Run logs inside run folder
│   │   │   ├── errors/            # Error reports
│   │   │   ├── diagnostics/       # Diagnostic outputs
│   │   │   └── issues/            # Issue tracking
│   │   └── fileorg-country-uk-20251206-173917/
│   ├── fileorg-docker/            # Family: Docker-related runs
│   │   └── fileorg-docker-build-20251204-194513/
│   ├── fileorg-p2/                # Family: Phase 2 runs
│   └── backlog-maintenance/       # Family: Backlog maintenance runs
├── archive/                       # Archived project artifacts
│   ├── plans/                     # Archived planning documents (.md, .json, .yaml)
│   ├── analysis/                  # Archived analysis & reviews (.md)
│   ├── reports/                   # Consolidated reports (.md)
│   ├── prompts/                   # Archived prompts (.md)
│   ├── diagnostics/               # Archived diagnostics (.md, .log)
│   ├── scripts/                   # Archived scripts (organized by type)
│   │   ├── backend/               # Backend scripts
│   │   ├── frontend/              # Frontend scripts
│   │   ├── test/                  # Test scripts
│   │   ├── temp/                  # Temporary scripts
│   │   └── utility/               # Utility scripts
│   ├── logs/                      # Archived logs (.log, .json)
│   └── superseded/                # Old run outputs
│       ├── runs/                  # Archived runs by family
│       │   ├── fileorg-country-uk/
│       │   ├── fileorg-docker/
│       │   └── ...
│       ├── research/              # Old research docs
│       ├── refs/                  # Old reference files
│       └── ...
└── fileorganizer/                 # Source code
    ├── backend/
    └── frontend/
```

#### 📝 File Creation Guidelines

**For Cursor-Created Files** (All File Types):

Cursor creates files in the workspace root. The tidy system **automatically detects and routes** files based on project and type:

**Automatic Classification** (Project-First Approach):
1. **Detects project** from filename/content:
   - `fileorg-*`, `backlog-*`, `maintenance-*` → File Organizer project
   - `autopack-*`, `tidy-*`, `autonomous-*` → Autopack project
   - Content keywords also used for detection

2. **Classifies file type** by extension and content:
   - **Markdown files** (`.md`):
     - `IMPLEMENTATION_PLAN_*` → `plans/`
     - `ANALYSIS_*`, `REVIEW_*`, `REVISION_*` → `analysis/`
     - `PROMPT_*`, `DELEGATION_*` → `prompts/`
     - `REPORT_*`, `SUMMARY_*`, `CONSOLIDATED_*` → `reports/`
     - `DIAGNOSTIC_*` → `diagnostics/`

   - **Python scripts** (`.py`):
     - Backend-related (FastAPI, SQLAlchemy, database) → `scripts/backend/`
     - Frontend-related (React, UI, components) → `scripts/frontend/`
     - Test scripts (`test_*`, pytest) → `scripts/test/`
     - Temporary/scratch scripts → `scripts/temp/`
     - Utility scripts (runners, executors) → `scripts/utility/`

   - **Log files** (`.log`):
     - All logs → `logs/`

   - **JSON files** (`.json`):
     - Plans/configs (`*plan*.json`, `*phase*.json`) → `plans/`
     - Failures/errors (`*failure*.json`, `*error*.json`) → `logs/`
     - Other JSON → `unsorted/`

   - **SQL files** (`.sql`):
     - All SQL → `scripts/utility/`

   - **Config files** (`.yaml`, `.yml`, `.toml`):
     - Config/settings → `plans/`
     - Other YAML/TOML → `unsorted/`

   - **Shell scripts** (`.sh`, `.ps1`, `.txt`):
     - Scripts → `scripts/utility/`

3. **Routes to destination**:
   - **Autopack files**: `C:\dev\Autopack\{archive or scripts}\{bucket}\{file}`
   - **File Organizer files**: `.autonomous_runs\file-organizer-app-v1\archive\{bucket}\{file}`
   - **Unsorted inbox**: Used when classification is uncertain

4. **Truth Sources** (never moved):
   - Autopack: `C:\dev\Autopack\docs\`
   - File Organizer: `.autonomous_runs\file-organizer-app-v1\docs\`
   - Protected files: `WHATS_LEFT_TO_BUILD*.md`, `*.db`, `project_learned_rules.json`

**For Autopack-Created Files** (Runs, Logs):

Autopack automatically creates files in the correct locations:
- Run directories: `.autonomous_runs/{project}/runs/{family}/{run-id}/`
- Run logs: Inside the run directory at `{run-id}/run.log`
- Errors: `{run-id}/errors/`
- Diagnostics: `{run-id}/diagnostics/`

#### 🛠️ Tidy & Archive Maintenance

**Memory-Based Classification System** (98%+ Accuracy):

The tidy system uses a sophisticated hybrid classification approach combining PostgreSQL, Qdrant vector DB, and pattern matching to achieve 98%+ accuracy in file routing:

**Three-Tier Classification Pipeline**:
1. **PostgreSQL Keyword Matching**: Fast lookup using routing rules with content keywords (checks user corrections FIRST for 100% confidence)
2. **Qdrant Semantic Similarity**: 384-dimensional embeddings using sentence-transformers for deep content understanding
3. **Enhanced Pattern Matching**: Multi-signal detection with content validation and structure heuristics

**Classification Confidence Hierarchy**:
- **User Corrections**: 1.00 (absolute truth from manual corrections)
- **PostgreSQL Rules**: 0.95-1.00 (explicit routing rules)
- **Qdrant Semantic**: 0.90-0.95 (learned patterns from successful classifications)
- **Pattern Matching**: 0.60-0.92 (enhanced fallback with validation) ← **Improved Dec 11, 2025**

**Recent Enhancements (2025-12-11)**:
- **PostgreSQL Connection Pooling**: Eliminates transaction errors with auto-commit mode (1-5 connection pool)
- **Enhanced Pattern Confidence (0.60-0.92)**: Improved from 0.55-0.88 via content validation + structure heuristics
  - Content validation scoring: Type-specific semantic markers (plans: "## goal", scripts: "import", logs: "[INFO]")
  - File structure heuristics: Rewards length (>500 chars) and organization (3+ headers, 4+ sections)
  - Base confidence increased: 0.55 → 0.60
  - Maximum confidence increased: 0.88 → 0.92
- **Smart Prioritization**: Boosts confidence when high-quality signals disagree (PostgreSQL ≥0.8 → 0.75, Qdrant ≥0.85 → 0.70)
- **Interactive Correction CLI** ([scripts/correction/interactive_correction.py](scripts/correction/interactive_correction.py)): Review and correct classifications interactively
- **Batch Correction Tool** ([scripts/correction/batch_correction.py](scripts/correction/batch_correction.py)): Pattern/CSV/directory-based bulk corrections
- **Regression Test Suite** ([tests/test_classification_regression.py](tests/test_classification_regression.py)): 15 comprehensive tests ensuring 98%+ accuracy (100% pass rate)

**Accuracy Enhancements**:
- **Multi-Signal Detection**: Combines filename indicators, content keywords, and extension patterns with confidence boosting when signals agree (3+ signals = 85% confidence)
- **Disagreement Resolution**: When methods disagree, uses weighted voting (PostgreSQL=2.0, Qdrant=1.5, Pattern=1.0) to select best classification
- **Extension-Specific Validation**: Content validation per file type with confidence multipliers (e.g., `.log` files get 1.3x boost)
- **User Feedback Loop**: Interactive correction tool ([scripts/correction/interactive_correction.py](scripts/correction/interactive_correction.py)) stores corrections with highest priority
- **LLM-Based Auditor**: Reviews low-confidence classifications (<80%) using contextual analysis to approve, override, or flag for manual review
- **Automatic Learning**: Successful classifications (>80% confidence) automatically stored back to Qdrant for continuous improvement

**If Accuracy Needs Further Improvement**:

The current system achieves 98%+ accuracy with optimal confidence ranges. **Do not artificially inflate pattern matching confidence beyond 0.92**, as this would collapse the confidence hierarchy and reduce system reliability. Instead, use these approaches:

1. **Add More PostgreSQL Routing Rules** (Explicit Knowledge):
   - Add project-specific keyword patterns to `routing_rules` table
   - Define explicit filename patterns for high-volume file types
   - Create content-based rules for domain-specific files
   - Best for: Known patterns with clear classification rules

2. **Improve Qdrant Pattern Learning** (Semantic Knowledge):
   - Seed Qdrant with more high-quality examples
   - Use interactive correction tool to fix misclassifications (auto-learns to Qdrant)
   - Manually add edge cases with `init_file_routing_patterns.py`
   - Best for: Ambiguous files requiring semantic understanding

3. **Adjust Auditor Threshold** (Review More Files):
   - Lower threshold from 80% to 70% to review more borderline cases
   - Configure in classification auditor to catch more low-confidence files
   - Best for: Projects with high accuracy requirements

4. **NOT: Inflate Pattern Matching Confidence Artificially**:
   - Pattern matching is fundamentally limited (lacks semantic understanding)
   - Artificially boosting beyond 0.92 would overlap with Qdrant (0.90-0.95)
   - Would cause hierarchy collapse and reduce system reliability
   - Current 0.92 cap is well-positioned in the confidence spectrum

**Classification Auditor** ([classification_auditor.py](scripts/classification_auditor.py)):
- Provides deep semantic understanding vs pattern matching
- Uses LLM with full file content and project context from database
- Only audits classifications below 80% confidence threshold
- Can approve (boost confidence 10%), override (correct to 95% confidence), or flag for manual review
- Not redundant: Vector DB provides "looks like X" while Auditor provides "IS about Y feature"

**Setup Requirements**:
```bash
# Install vector DB dependencies
pip install sentence-transformers qdrant-client

# Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# Initialize file routing patterns collection
QDRANT_HOST="http://localhost:6333" python scripts/init_file_routing_patterns.py

# Configure environment
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
export QDRANT_HOST="http://localhost:6333"
export EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
```

**User Feedback & Corrections**:

**Interactive Review** (NEW - Dec 11, 2025):
```bash
# Review recent classifications interactively (one-by-one)
python scripts/correction/interactive_correction.py --interactive

# Review files flagged by auditor
python scripts/correction/interactive_correction.py --flagged

# Show correction statistics
python scripts/correction/interactive_correction.py --stats
```

**Batch Corrections** (NEW - Dec 11, 2025):
```bash
# Correct files by pattern (dry-run)
python scripts/correction/batch_correction.py \
  --pattern "fileorg_*.md" \
  --project file-organizer-app-v1 \
  --type plan

# Execute corrections for directory
python scripts/correction/batch_correction.py \
  --directory .autonomous_runs/temp \
  --project autopack \
  --type log \
  --execute

# Export potential misclassifications to CSV
python scripts/correction/batch_correction.py --export misclassified.csv

# Import corrections from CSV
python scripts/correction/batch_correction.py --csv corrections.csv --execute
```

**Legacy Tool** (Still Available):
```bash
# Interactively correct misclassifications (legacy)
python scripts/correct_classification.py --interactive

# View recent corrections
python scripts/correct_classification.py --show --limit 20
```

Corrections are stored in PostgreSQL `classification_corrections` table and immediately added to Qdrant as high-priority patterns with 100% confidence. The new tools provide dual storage (PostgreSQL + Qdrant) with immediate learning feedback.

**Manual Tidy Operations**:
```bash
# One-shot tidy with semantic analysis
python scripts/run_tidy_all.py

# Dry run to preview changes (with memory-based classification)
python scripts/tidy_workspace.py --root .autonomous_runs --dry-run --verbose

# Execute cleanup for specific project
python scripts/tidy_workspace.py --root .autonomous_runs/file-organizer-app-v1 --execute
```

**Configuration** (`tidy_scope.yaml`):
- Sets roots to tidy (default: `.autonomous_runs/file-organizer-app-v1`, `.autonomous_runs`, `archive`)
- Optional `purge: true` for permanent deletion (default is archive)
- Optional `db_overrides` per root for Postgres DSN

**Tidy Operations**:
1. **Superseded Handling**:
   - Files route to appropriate buckets: `research`, `delegations`, `phases`, `tiers`, `prompts`, `diagnostics`, `runs`, `refs`, `reports`, `plans`, `analysis`, `logs`, `scripts`
   - Run folders grouped by family: `.../archive/superseded/runs/<family>/<run-id>`
   - Family derived from run ID prefix (e.g., `fileorg-country-uk-20251205-132826` → family: `fileorg-country-uk`)

2. **Cursor File Detection** (All File Types):
   - Automatically detects **all file types** in workspace root (`.md`, `.py`, `.json`, `.log`, `.sql`, etc.)
   - **Project-first classification**: Detects which project files belong to
   - **Type classification**: Routes by file extension and content analysis
   - **Script sub-classification**: Python files classified as backend/frontend/test/temp/utility
   - Processes files created within last 7 days
   - Fallback to `archive/unsorted/` if classification fails

3. **Truth Source Protection**:
   - Never moves: `WHATS_LEFT_TO_BUILD*.md`, `*.db`, `project_learned_rules.json`
   - Protected prefixes: `plan_`, `plan-generated`
   - Protected files remain in their canonical locations

**Creation-Time Routing Helpers**:
- `route_new_doc(name, purpose, project_hint, archived)` - Get destination path for new documents
- `route_run_output(project_hint, family, run_id, archived)` - Get path for run outputs
- CLI: `python scripts/run_output_paths.py --doc-name PLAN.md --doc-purpose plan --project file-organizer-app-v1`

**Database Logging**:
- Tidy operations logged to `tidy_activity` table in PostgreSQL (if `DATABASE_URL` set)
- Fallback: JSONL at `.autonomous_runs/tidy_activity.log`
- Tracks: project_id, action, src/dest paths, SHA256 hashes, timestamp

**Classification Learning**:
- Successful classifications (>80% confidence) automatically stored to Qdrant
- User corrections stored in PostgreSQL and Qdrant with highest priority
- System continuously improves accuracy over time
- Uses `sentence-transformers/all-MiniLM-L6-v2` for embeddings (384-dimensional vectors)

**Safety**:
- Dry-run by default (review changes before executing)
- Creates checkpoint archives before moves/deletes
- Git commits before/after (optional via `--git-commit-before`/`--git-commit-after`)
- Purge is opt-in only (default is archive, not delete)
- Flagged files (from Auditor) are never auto-moved

**Comprehensive Workspace Cleanup**:
- Target structure: `archive/` buckets (plans, reports, analysis, research, prompts, diagnostics/logs, scripts, refs) and project-scoped `.../.autonomous_runs/<project>/archive/superseded/` buckets (same + runs/<family>/<run-id>). Truth sources live in `C:\dev\Autopack\docs` (Autopack) and `.../<project>/docs` (projects).
- Routing: use `route_new_doc` / `route_run_output` (or CLI helpers `run_output_paths.py` / `create_run_with_routing.py`) so new docs/runs land in the right project/bucket up front; `archive\unsorted` is last-resort inbox only.
- Diagnostics truth: treat `CONSOLIDATED_DEBUG.md` and similar diagnostics (e.g., `ENHANCED_ERROR_LOGGING.md`) as truth candidates—review/merge into the active `docs` copy, then archive or discard if superseded.
- For the full, step-by-step cleanup, see **[Comprehensive Tidy Execution Plan](COMPREHENSIVE_TIDY_EXECUTION_PLAN.md)** and the architecture guide **[Autopack Tidy System Guide](docs/AUTOPACK_TIDY_SYSTEM_COMPREHENSIVE_GUIDE.md)**.

### Consolidating Documentation

To tidy up and consolidate documentation across projects:

```bash
python scripts/consolidate_docs.py
```

This will:
1. Scan all documentation files.
2. Sort them into project-specific archives (`archive/` vs `.autonomous_runs/<project>/archive/`).
3. Create consolidated reference files (`CONSOLIDATED_DEBUG.md`, etc.) and keep truth sources in the project docs roots (`C:\dev\Autopack\docs` for Autopack; `.../file-organizer-app-v1/docs` for File Organizer).
4. Move processed files to `superseded/`.

---

## Configuration

### Model Escalation (`config/models.yaml`)

```yaml
complexity_escalation:
  enabled: true
  thresholds:
    low_to_medium: 2    # Escalate after 2 failures at low complexity
    medium_to_high: 2   # Escalate after 2 failures at medium complexity
  max_attempts_per_phase: 5
  failure_types:
    - auditor_reject
    - ci_fail
    - patch_apply_error

escalation_chains:
  builder:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro, claude-sonnet-4-5]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5, gpt-5]
    high:
      models: [claude-sonnet-4-5, gpt-5]
  auditor:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5]
    high:
      models: [claude-sonnet-4-5, claude-opus-4-5]
```

### Re-Planning (`config/models.yaml`)

```yaml
replan:
  trigger_threshold: 2          # Consecutive same-type failures before re-plan
  message_similarity_enabled: true
  similarity_threshold: 0.8     # How similar messages must be (0.0-1.0)
  min_message_length: 30        # Skip similarity check for short messages
  max_replans_per_phase: 1      # Prevent infinite re-planning loops
  fatal_error_types:            # Immediate re-plan triggers
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

---

**Version**: 0.5.1 (Memory & Classification Enhancements)
**License**: MIT
**Milestone note**: The “tests-passing-v1.0” milestone refers to a scoped historical validation suite, not the full repository test run used in modern draining. See “CI / completion policy” below.
**Classification Tests**: 100% pass rate (15/15 regression tests passing)

## CI / completion policy (important for draining)

During draining, Autopack runs the repo’s CI (typically `pytest`) but **phase completion is based on regression delta**, not absolute “all tests green”:

- **Baseline-delta gating**: a phase may complete even if CI exitcode is non-zero when it introduces no new persistent regressions relative to the captured baseline.
- **Collection/import errors**: pytest collection failures (exitcode `2`, failed collectors / import errors) are treated as **hard blocks** and should not complete.
- **Human approval override**: quality-gate “BLOCKED” can be overridden only within the existing PhaseFinalizer rules (it still blocks on critical regressions and collection errors).


## Project Status

<!-- SOT_SUMMARY_START -->
**Last Updated**: 2025-12-27 14:07

- **Builds Completed**: 80
- **Latest Build**: ### BUILD-100 | 2025-12-20T20:26 | Hotfix | Executor startup fix: DiagnosticsAgent import path
- **Architecture Decisions**: 0
- **Debugging Sessions**: 0

*Auto-generated by Autopack Tidy System*
<!-- SOT_SUMMARY_END -->
