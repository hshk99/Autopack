# Root SOT Duplicate Report

**Timestamp**: 2026-01-01T22:12:29.681878
**Repo root**: `C:\dev\Autopack`
**Docs dir**: `C:\dev\Autopack\docs`
**Divergent duplicates found**: YES

---

## BUILD_HISTORY.md

- **status**: divergent
- **root_sha256**: `5e0e91775ad4704961f2bebabbaa61a920ad11bffcc8215d848ab67fe96d9b84`
- **docs_sha256**: `2774d15a02a5ced83ffb3c67383b9fcccec0ba54b9fcade20a50b65b0f0d07e6`
- **root_size_bytes**: `103163`
- **docs_size_bytes**: `218404`

Suggested merge commands:
- `git diff --no-index BUILD_HISTORY.md docs/BUILD_HISTORY.md`

Truncated unified diff (root -> docs):

```
--- root/BUILD_HISTORY.md
+++ docs/BUILD_HISTORY.md
@@ -1,1770 +1,1940 @@
-# Build History

-

-Chronological index of all completed builds in the Autopack project.

-

-## Format

-

-Each entry includes:

-- **Build ID**: Unique identifier (e.g., BUILD-132)

-- **Date**: Completion date

-- **Status**: COMPLETE, IN_PROGRESS, or BLOCKED

-- **Summary**: Brief description of changes

-- **Files Modified**: Key files affected

-- **Impact**: Effect on system functionality

-

----

-

-## Chronological Index

-

-### BUILD-146 Phase A P17.x: DB Idempotency Hardening (2026-01-01)

-

-**Status**: ✅ COMPLETE

-

-**Summary**: Database-level idempotency enforcement for token efficiency telemetry to prevent duplicate records under concurrent writers.

-

-**Problem**:

-- BUILD-146 P17.1 added app-level idempotency guard (check-then-insert pattern)

-- This prevents most duplicates but fails under concurrent writers (classic race condition)

-- Two writers can both query (no existing row), both insert (duplicate created)

-- No operator visibility into missing DB schema until runtime failures

-

-**Solution**:

-

-1. **Migration Script** (new file)

-   - [scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py](scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py)

-   - Creates partial unique index: `ux_token_eff_metrics_run_phase_outcome`

-   - Columns: `(run_id, phase_id, phase_outcome)`

-   - Predicate: `WHERE phase_outcome IS NOT NULL` (backward compatible)

-   - PostgreSQL: `CREATE INDEX CONCURRENTLY` (non-transactional, autocommit mode)

-   - SQLite: Best-effort partial index (requires SQLite 3.8+)

-   - Idempotent: Safe to run multiple times

-

-2. **Race-Safe IntegrityError Handling** (src/autopack/usage_recorder.py)

-   - Fast-path: Query for existing record before insert (app-level guard)

-   - Slow-path: Try commit → catch IntegrityError → rollback → re-query → return existing

-   - Handles concurrent writer race: another writer beats us to insert, we recover gracefully

-   - No duplicates created, existing record returned

-

-3. **Test Coverage** (tests/autopack/test_token_efficiency_observability.py)

-   - New test: `test_integrity_error_fallback()`

-   - Simulates concurrent writer race condition via mock

-   - Validates: IntegrityError caught, rollback executed, existing record returned

-   - Verifies: Only one DB record exists after race

-

-4. **Production Smoke Test** (scripts/smoke_autonomy_features.py)

-   - New check: `check_idempotency_index()`

-   - Detects missing index via SQLAlchemy inspector

-   - Reports NO-GO with migration command when index missing

-   - New check: `check_config_conflicts()` - warns if SQLite used with telemetry in production

-

-**Files Modified**:

-- `scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py` - NEW migration (277 lines)

-- `src/autopack/usage_recorder.py` - Added IntegrityError import, try/except/rollback/re-query (lines 8, 378-403)

-- `tests/autopack/test_token_efficiency_observability.py` - Added test_integrity_error_fallback() (lines 17, 782-858)

-- `scripts/smoke_autonomy_features.py` - Added check_idempotency_index() + check_config_conflicts() (lines 107-191, 220-249)

-

-**Test Results**:

-- test_token_efficiency_observability.py::TestTelemetryInvariants: 8/8 passed ✅

-- Includes new test_integrity_error_fallback() ✅

-- Smoke test correctly detects missing index (NO-GO) ✅

-

-**End State**:

-- DB enforces uniqueness: at most one row per (run_id, phase_id, terminal_outcome) ✅

-- Backward compatible: NULL phase_outcome not enforced (legacy paths safe) ✅

-- Concurrent safe: IntegrityError caught, rollback, existing record returned ✅

-- Operator safe: Smoke test blocks deployment when index missing ✅

-

-**Deployment**:

+# Build History - Implementation Log

+

+<!-- META

+Last_Updated: 2026-01-01T22:05:00Z

+Total_Builds: 148

+Format_Version: 2.0

+Auto_Generated: False

+Sources: CONSOLIDATED files, archive/, manual updates, BUILD-148 Storage Optimizer MVP

+-->

+

+## INDEX (Chronological - Most Recent First)

+

+| Timestamp | BUILD-ID | Phase | Summary | Files Changed |

+|-----------|----------|-------|---------|---------------|

+| 2026-01-01 | BUILD-147 | Phase A P11 Observability (100% COMPLETE ✅) | **SOT Runtime + Model Intelligence Integration**: Completed Phase A P11 - integrated SOT memory retrieval and model intelligence systems into production runtime. All 8 parts of IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md already implemented in prior builds (BUILD-146 P18, BUILD-147 SOT). **Validation Hardening**: Fixed test infrastructure issues preventing proper validation - (1) `retrieve_context` return structure made consistent (always returns dict with all 8 keys including 'sot', even when empty), prevents KeyError when checking for SOT results; (2) Test environment handling fixed - added settings module reload after `patch.dict(os.environ)` in 7 test functions to ensure singleton settings object picks up environment variable changes (tests were creating new Settings() instances but code was using global singleton). **Validation Results**: All 26 SOT memory indexing tests passing ✅ (chunking, indexing, retrieval, multi-project, re-index optimization, 6-file support). **Implementation Status Review**: Part 1 (SOT retrieval wiring) - already complete, all 4 `retrieve_context` calls in autonomous_executor.py include `include_sot=bool(settings.autopack_sot_retrieval_enabled)` at lines 4089, 5489, 6100, 6489. Part 2 (startup SOT indexing) - `_maybe_index_sot_docs()` helper exists at line 7857, called at executor init line 279. Part 3 (multi-project docs_dir resolution) - `_resolve_project_docs_dir()` exists at line 7826, `docs_dir` parameter supported in `index_sot_docs()` at line 793. Part 4 (6-file indexing) - markdown (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS, FUTURE_PLAN) + JSON (PROJECT_INDEX, LEARNED_RULES) at lines 828-839 with `chunk_sot_json()` + `json_to_embedding_text()` helpers. Part 5 (re-index cost optimization) - skip existing chunks using `get_payload()` check at lines 868-875. Part 6 (chunking quality) - sentence boundaries (`. `, `? `, `! `) at line 63, paragraph breaks (`\n\n`) at line 51, markdown headings (`\n#`) at line 56. Part 7 (operator visibility) - comprehensive logging in `_maybe_index_sot_docs` at lines 7867-7872. Part 8 (model intelligence) - `scripts/model_audit.py` with `--fail-on` parameter exists, `scripts/model_intel.py` with `refresh-all` command exists (BUILD-146 P18). **Impact**: SOT runtime integration validated and production-ready with comprehensive test coverage, all parts implemented and tested, opt-in design ensures safety (all features disabled by default via env vars). Files: src/autopack/memory/memory_service.py (consistent return structure fix lines 1279-1288), tests/test_sot_memory_indexing.py (settings reload fixes in 7 test functions) | 2 |

+| 2026-01-01 | BUILD-147 | SOT Memory Integration (100% COMPLETE ✅) | **Tidy SOT → Runtime Retrieval Integration**: Implemented complete integration allowing Autopack to index and retrieve SOT documentation (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS) from vector memory at runtime. **Part 1 - Stable Entry ID Generation**: Enhanced consolidate_docs_v2.py with stable, idempotent entry ID generation - (1) `_extract_explicit_entry_id()` extracts explicit IDs like BUILD-146, DBG-078, DEC-042 from content via regex, (2) `_stable_entry_id()` generates deterministic hash-based IDs (BUILD-HASH-3f2a91c4) when explicit IDs absent using MD5(normalized_path + heading + timestamp), (3) Updated `_extract_entries()` to prefer explicit IDs over generated IDs. Impact: Re-running tidy produces identical entry IDs → db_sync.py upserts become truly idempotent (no duplicate sot_entries). **Part 2 - Runtime SOT Memory Indexing**: Created comprehensive SOT indexing infrastructure - (1) **Configuration** (config.py): 7 opt-in env vars (AUTOPACK_ENABLE_SOT_MEMORY_INDEXING, AUTOPACK_SOT_RETRIEVAL_ENABLED, AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000, AUTOPACK_SOT_RETRIEVAL_TOP_K=3, chunk sizing controls), all default OFF for safety. (2) **SOT Indexing Helper** (memory/sot_indexing.py, NEW 170 lines): `chunk_text()` splits with sentence-boundary-aware overlap, `chunk_sot_file()` indexes entire SOT file with metadata extraction (headings, timestamps), `stable_chunk_id()` generates content-hash IDs for re-indexing idempotency. (3) **MemoryService Enhancement** (memory/memory_service.py): Added COLLECTION_SOT_DOCS to collections, `index_sot_docs()` chunks + embeds + indexes all 3 SOT files (opt-in), `search_sot()` semantic search over SOT chunks, updated `retrieve_context()` with `include_sot` parameter (opt-in), enhanced `format_retrieved_context()` with SOT rendering respecting strict max_chars cap. **Test Coverage**: 100% comprehensive - (1) test_tidy_entry_id_stability.py (NEW, 10 tests): explicit ID extraction, stable hash determinism, normalization, idempotent extraction, explicit ID preference over generated. (2) test_sot_memory_indexing.py (NEW, 17 tests): chunking logic (short/long content, sentence boundaries), metadata extraction, indexing (disabled by default, respects flags), retrieval (opt-in, max_chars limits), idempotency (re-indexing same IDs). **Documentation**: (1) Updated scripts/tidy/README.md with pointer to TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md, (2) Created docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md (NEW 240 lines) with configuration guide, autonomous executor integration pattern, standalone script examples, re-indexing workflow, troubleshooting. **Key Properties**: No information deletion (only move/organize), opt-in via env flags (all disabled by default), strictly capped retrieval (4000 chars prevents prompt bloat), Qdrant or FAISS fallback, idempotent tidy re-runs (stable entry_id + chunk_id). **Integration Pattern**: (1) Enable via env: AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true, AUTOPACK_SOT_RETRIEVAL_ENABLED=true, (2) Index at startup: `memory.index_sot_docs("autopack", workspace_root)`, (3) Retrieve in phases: `memory.retrieve_context(..., include_sot=True)`. **Impact**: Tidy's SOT ledgers now retrievable "when needed" by Autopack (semantic search), historical knowledge accessible without re-reading full archives, token-efficient retrieval with strict caps (top-3 chunks, 4000 char limit), idempotent indexing enables safe re-runs after tidy updates, production-ready with comprehensive test coverage (27 tests all passing ✅). Files: scripts/tidy/consolidate_docs_v2.py (+123 lines stable ID logic), src/autopack/config.py (+18 lines SOT config), src/autopack/memory/sot_indexing.py (NEW 170 lines), src/autopack/memory/memory_service.py (+193 lines SOT methods), scripts/tidy/README.md (+4 lines plan pointer), tests/test_tidy_entry_id_stability.py (NEW 10 tests), tests/test_sot_memory_indexing.py (NEW 17 tests), docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md (NEW 240 lines) | 9 |

+| 2026-01-01 | BUILD-146 | P18 Model Intelligence (100% COMPLETE ✅) | **Model Catalog + Recommendation System**: Postgres-backed model intelligence eliminating manual model bump hunts with evidence-based recommendations. **Schema**: 6 tables (models_catalog, model_pricing, model_benchmarks, model_runtime_stats, model_sentiment_signals, model_recommendations) with migration add_model_intelligence_tables_build146_p18.py requiring explicit DATABASE_URL. **Module** (src/autopack/model_intelligence/): models.py (SQLAlchemy ORM), db.py (sessions), catalog_ingest.py (config/models.yaml + pricing.yaml → DB), runtime_stats.py (llm_usage_events aggregation with cost estimates + percentiles), sentiment_ingest.py (community signals), recommender.py (composite scoring: 35% price + 40% benchmarks + 20% runtime + 5% sentiment), patcher.py (YAML diff generation). **CLI** (scripts/model_intel.py): ingest-catalog, compute-runtime-stats --window-days 30, ingest-sentiment --model X --source reddit --url Y --snippet Z --sentiment positive, recommend --use-case tidy_semantic --current-model glm-4.6 --persist, report --latest, propose-patch --recommendation-id N. **Scoring**: Price (1.0 cheaper, penalize >2x), benchmarks (official coding scores), runtime (telemetry success rate + efficiency), sentiment (5% weight, supporting only). Confidence: 0.9 with runtime data, 0.6 pricing/benchmarks only. **Safety**: No auto-upgrades (status=proposed requires approval), evidence IDs persisted (pricing/benchmark/runtime_stats/sentiment references), DATABASE_URL enforcement, bounded outputs. **Tests**: 17 passing (catalog_ingest 6, runtime_stats 6, recommender 5) using in-memory SQLite. **Docs**: MODEL_INTELLIGENCE_SYSTEM.md (500 lines) with setup/usage/troubleshooting. Files: 16 (migration, 9 module files, CLI, 3 test suites, docs, INDEX/README updates) | 16 |

+| 2025-12-31 | BUILD-146 | P17 Close-the-Gap (100% COMPLETE ✅) | **P17 Production Polish - Telemetry Idempotency + P1.3 Coverage + Rollout Infrastructure**: Closed remaining production-readiness gaps by hardening token efficiency observability and artifact substitution features. **P17.1 Telemetry Correctness Hardening**: Added idempotency guards to prevent duplicate `TokenEfficiencyMetrics` rows across retries/crashes - checks for existing `(run_id, phase_id, phase_outcome)` record before insertion, returns existing record without duplication. Created `TestTelemetryInvariants` test suite (7 tests) validating: (1) idempotent recording for same outcome (returns existing record), (2) different outcomes allowed (FAILED vs COMPLETE as separate records), (3) retry same failed outcome idempotent, (4) no outcome always creates new (backward compat), (5) token categories non-overlapping (budget_used vs tokens_saved_artifacts), (6) recording failures never raise exceptions, (7) embedding cache metrics optional (default 0). **P17.2 P1.3 Test Coverage Completion**: Added `TestP17SafetyAndFallback` test suite (9 tests) filling coverage gaps for artifact history pack + SOT substitution: (1) no substitution when all disabled (feature flags OFF), (2) only SOT docs substituted (BUILD_HISTORY/BUILD_LOG allowed, src/main.py denied), (3) fallback when history pack missing (returns None), (4) fallback to original when no artifacts, (5) max_tiers cap strictly enforced (includes exactly N tiers, not more), (6) max_phases cap strictly enforced, (7) zero cap excludes all (validation of cap=0 behavior), (8) no silent substitutions in regular files (security rule), (9) caps use recency ordering (reverse lexical sort). **P17.3 Rollout Checklist + Smoke Tooling**: Created `docs/PRODUCTION_ROLLOUT_CHECKLIST.md` (500+ lines) with: (1) Environment variables matrix (core config, LLM keys, feature toggles, observability settings), (2) Database tables to monitor (llm_usage_events, token_efficiency_metrics, phase6_metrics, token_budget_escalation_events with SQL query examples), (3) Staged rollout plan (Stage 0 pre-production validation, Stage 1 telemetry-only, Stage 2 history pack + SOT, Stage 3 full autonomy), (4) Kill switches (emergency rollback commands), (5) Success metrics to watch (phase success rate, token efficiency, telemetry completeness), (6) Troubleshooting guide (duplicate telemetry entries, no artifact substitutions, cap violations, silent substitutions). Created `scripts/smoke_autonomy_features.py` (250+ lines, no LLM calls) for pre-deployment validation: (1) Checks LLM provider keys (GLM primary, Anthropic/OpenAI fallback), (2) Verifies database reachable + schema complete (6 required tables), (3) Reports feature toggle status (telemetry, history pack, SOT substitution, extended contexts), (4) Validates memory backend config (Qdrant optional), (5) Outputs GO/NO-GO verdict with next steps (Stage 0/1/2/3 based on enabled features). **P17.4 README Drift Fix**: Updated README "Known Limitations" section from STALE to CURRENT: Removed "(1) Test coverage gap: No dedicated tests for P1.3" (now `test_artifact_history_pack.py` exists with 9 P17 safety tests), Removed "(2) Minor wiring needed: Telemetry recording not yet integrated" (telemetry wiring already present in `autonomous_executor.py` lines 1555-1575 and 1910-1930), Kept "(1) Dashboard integration: token_efficiency field optional for backwards compatibility" as valid limitation, Added new "BUILD-146 P17 Production Hardening" completion summary with rollout guide pointer. **Impact**: Telemetry idempotency prevents duplicate metrics (1 row per terminal outcome even with retries/crashes), P1.3 test coverage complete (18 total tests: 9 existing + 9 P17 safety), production rollout infrastructure complete (staged deployment guide + automated smoke test), README drift eliminated (limitations match actual state). **Test Results**: All 53 tests passing ✅ (22 token efficiency + 31 artifact history pack tests), telemetry idempotency validated (same outcome returns existing record), P17 safety tests validate caps enforcement + SOT-only substitution + fallback behavior. Files: src/autopack/usage_recorder.py (idempotency check lines 334-342), tests/autopack/test_token_efficiency_observability.py (TestTelemetryInvariants class, 7 tests, +250 lines), tests/autopack/test_artifact_history_pack.py (TestP17SafetyAndFallback class, 9 tests, +300 lines), docs/PRODUCTION_ROLLOUT_CHECKLIST.md (NEW, 500+ lines), scripts/smoke_autonomy_features.py (NEW, 250+ lines), README.md (Known Limitations section updated) | 6 |

+| 2025-12-31 | BUILD-146 | P12 API Consolidation (100% COMPLETE ✅) | **API Consolidation - One Canonical Server**: Successfully consolidated dual FastAPI control plane into one canonical Autopack server (`autopack.main:app`). **Phase 0 - Contract Documentation**: Created CANONICAL_API_CONTRACT.md documenting 40+ required endpoints with kill switch defaults (all OFF) and authentication methods (X-API-Key primary, Bearer compatible). **Phase 1 - Enhanced Endpoints**: Enhanced canonical server with backend-only endpoints - (1) Enhanced `/health` endpoint (lines 1625-1726) with `database_identity` (12-char hash for drift detection), `kill_switches` dict (all default OFF), `qdrant` status, `version` field, database connectivity check (200/503 status codes); (2) Added `/dashboard/runs/{run_id}/consolidated-metrics` endpoint (lines 1460-1596) with kill switch `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` (default OFF), pagination validation (max 10k, offset validation), 4 independent token categories (actual spend, artifact efficiency, doctor counterfactual, A/B delta) with no double-counting. **Phase 2 - Auth**: Already canonical (X-API-Key primary, executor aligned, no changes needed). **Phase 3 - Backend Deprecation**: Hard-deprecated `src/backend/main.py` (lines 1-97) - exits with clear error message on direct execution directing to canonical server, library imports still work for backward compatibility. **Phase 4 - Contract Tests + CI**: Created `tests/test_canonical_api_contract.py` (15 tests) covering enhanced health, kill switches default OFF, backend deprecation, consolidated metrics, pagination validation, database identity format; created `scripts/check_docs_drift.py` CI drift detector with 8 forbidden patterns preventing backend server reference regression. **Documentation Cleanup**: Fixed 7 files with outdated backend server references (BUILD-107-108_SAFEGUARDS_SUMMARY.md, DEPLOYMENT.md, NEXT_CURSOR_TAKEOVER_PROMPT.md, TELEGRAM_APPROVAL_SETUP.md, cursor/CURSOR_PROMPT_RESEARCH_SYSTEM.md, guides/NGROK_SETUP_GUIDE.md, .autonomous_runs/file-organizer-app-v1/README.md) - replaced all `uvicorn backend.main:app` with `PYTHONPATH=src uvicorn autopack.main:app`. **Target End-State Achieved**: One canonical server, no dual drift, clean deprecation path, comprehensive testing. **Migration Path**: OLD `PYTHONPATH=src uvicorn backend.main:app --port 8001` → NEW `PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000`. **Impact**: Eliminated dual control plane drift (42%), enabled database identity drift detection, established kill switch safety defaults (all OFF), provided CI guardrails preventing docs regression, backward compatible with additive changes only. **Definition of Done**: ✅ One canonical server documented (CANONICAL_API_CONTRACT.md), ✅ All 40+ endpoints served by canonical server, ✅ Enhanced health + consolidated metrics with kill switches OFF, ✅ Backend server deprecated with library compat, ✅ 15 contract tests enforcing surface, ✅ CI drift check preventing regression, ✅ 7 docs cleaned. **Optional Phase 5**: Migrate auth to `autopack.auth.*` namespace (deferred - backend remains as library, not blocking). Files: docs/CANONICAL_API_CONTRACT.md (NEW, 270+ lines), docs/API_CONSOLIDATION_COMPLETION_SUMMARY.md (NEW, 440+ lines), src/autopack/main.py (enhanced health lines 1625-1726, consolidated metrics lines 1460-1596), src/backend/main.py (deprecated lines 1-97), tests/test_canonical_api_contract.py (NEW, 15 tests), scripts/check_docs_drift.py (NEW, 150+ lines, 8 patterns), docs/BUILD-107-108_SAFEGUARDS_SUMMARY.md (2 lines updated), docs/DEPLOYMENT.md (1 line), docs/NEXT_CURSOR_TAKEOVER_PROMPT.md (1 line), docs/TELEGRAM_APPROVAL_SETUP.md (2 lines), docs/cursor/CURSOR_PROMPT_RESEARCH_SYSTEM.md (2 lines), docs/guides/NGROK_SETUP_GUIDE.md (1 line), .autonomous_runs/file-organizer-app-v1/README.md (2 lines) | 13 |

+| 2025-12-31 | BUILD-146 | P12 Production Hardening (100% COMPLETE ✅) | Production Hardening + Staging Validation + Pattern Automation + Performance + A/B Persistence + Replay Campaign: Completed 5 operational maturity improvements for production rollout readiness. **Task 1 - Rollout Playbook + Safety Rails**: Created comprehensive STAGING_ROLLOUT.md (600+ lines) with production readiness checklist (environment vars, database migration steps, endpoint verification, rollback procedures, performance baselines), added kill switches (AUTOPACK_ENABLE_PHASE6_METRICS default OFF, AUTOPACK_ENABLE_CONSOLIDATED_METRICS default OFF) to consolidated metrics endpoint with pagination (limit 10K max, offset validation), enhanced health check endpoint with database connectivity check + Qdrant status + kill switch state reporting, created test_kill_switches.py (10 tests) validating defaults OFF and feature toggling. **Task 2 - Pattern Expansion → PR Automation**: Extended pattern_expansion.py to auto-generate Python detector/mitigation stubs (src/autopack/patterns/pattern_*.py), pytest skeletons (tests/patterns/test_pattern_*.py), and backlog entries (docs/backlog/PATTERN_*.md) from real failure telemetry, created pattern registry (__init__.py) for auto-importing detectors, generates code for top 5 patterns by frequency (min 3 occurrences), includes TODO comments for human review with sample errors and mitigation suggestions. **Task 3 - Data Quality + Performance Hardening**: Created add_performance_indexes.py migration script adding 10 database indexes (phase_metrics, dashboard_events, phases, llm_usage_events, token_efficiency_metrics, phase6_metrics on run_id/created_at/event_type/state), supports both SQLite and PostgreSQL with idempotent IF NOT EXISTS, includes query plan verification examples (EXPLAIN QUERY PLAN), pagination and kill switch already implemented in Task 1, created test_performance_indexes.py (11 tests) validating index creation and query optimization. **Task 4 - A/B Results Persistence**: Added ABTestResult model to models.py with strict validity checks (control/treatment must have same commit SHA and model hash - not warnings, ERRORS), created add_ab_test_results.py migration script, implemented ab_analysis.py script with validate_pair() enforcing strict validity (exits 1 if invalid), calculate_deltas() for metrics comparison, and persist_result() saving to database, added /api/dashboard/ab-results endpoint with valid_only filter (default True) and limit validation (max 1000), created test_ab_results_persistence.py (9 tests) validating validity enforcement and phase metrics. **Task 5 - Replay Campaign**: Created replay_campaign.py to clone failed runs with new IDs, enable Phase 6 features via env vars (AUTOPACK_ENABLE_PHASE6_METRICS=1, AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1), execute using run_parallel.py --executor api for async execution, generate comparison reports in archive/replay_results/ with token/time/success rate deltas, supports filters (--run-id, --from-date, --to-date, --state, --dry-run), batch execution with configurable parallelism (default 5), created test_replay_campaign.py (7 tests) validating run cloning with metadata preservation and phase state reset. **Impact**: Production deployment infrastructure complete with rollout playbook, emergency kill switches default OFF for safety, automated pattern detection generates actionable code stubs from real failures, database query optimization with 10 indexes for dashboard performance (<100ms target for 10K records), A/B testing infrastructure with strict validity enforcement prevents invalid comparisons, replay campaign enables Phase 6 validation on historical failed runs with automated comparison reporting. **Test Coverage**: 47 new tests across 5 test files, all kill switches verified to default OFF. Files: docs/STAGING_ROLLOUT.md (NEW, 600+ lines), src/backend/api/dashboard.py (kill switch + pagination lines 129-149, A/B endpoint lines 370-438), src/backend/api/health.py (enhanced lines 24-136), tests/test_kill_switches.py (NEW, 10 tests), scripts/pattern_expansion.py (code generation +550 lines), src/autopack/patterns/__init__.py (NEW registry), scripts/migrations/add_performance_indexes.py (NEW, 350+ lines), tests/test_performance_indexes.py (NEW, 11 tests), src/autopack/models.py (ABTestResult model lines 503-550), scripts/migrations/add_ab_test_results.py (NEW), scripts/ab_analysis.py (NEW, 450+ lines), tests/test_ab_results_persistence.py (NEW, 9 tests), scripts/replay_campaign.py (NEW, 500+ lines), tests/test_replay_campaign.py (NEW, 7 tests) | 15 |

+| 2025-12-31 | BUILD-145 | Deployment Hardening (100% COMPLETE ✅) | Database Migration + Dashboard Exposure + Telemetry Enrichment: Completed production deployment infrastructure with 100% test coverage (29/29 passing). **Idempotent Database Migration**: Created add_telemetry_enrichment_build145_deploy.py migration script to safely add 7 new nullable columns (embedding_cache_hits, embedding_cache_misses, embedding_calls_made, embedding_cap_value, embedding_fallback_reason, deliverables_count, context_files_total) to token_efficiency_metrics table - supports both SQLite and PostgreSQL, detects existing columns, safe to run multiple times. **Dashboard Token Efficiency Exposure**: Enhanced /dashboard/runs/{run_id}/status endpoint to include optional token_efficiency field with aggregated stats (total_phases, artifact_substitutions, tokens_saved, budget_utilization) and phase_outcome_counts breakdown by terminal states (COMPLETE/FAILED/BLOCKED/UNKNOWN) - graceful error handling returns null if stats unavailable, backward compatible with existing clients. **Telemetry Enrichment**: Extended TokenEfficiencyMetrics model and record_token_efficiency_metrics() function with 7 new optional parameters for embedding cache observability (hits/misses/calls/cap/fallback_reason) and budgeting context observability (deliverables_count/context_files_total) - all parameters optional with sensible defaults, enhanced get_token_efficiency_stats() to include phase outcome breakdown. **Comprehensive Dashboard Tests**: Created test_dashboard_token_efficiency.py with 7 integration tests covering all scenarios (no metrics, basic metrics, phase outcomes, enriched telemetry, backward compatibility, mixed budget modes, graceful error handling) using in-memory SQLite with proper database dependency mocking. **Impact**: Existing deployments can upgrade without data loss (migration idempotent), token efficiency stats exposed via REST API for monitoring/analysis, embedding cache and budgeting context decisions now observable, phase outcome tracking enables failure analysis, zero regressions (all 29 tests passing). Files: scripts/migrations/add_telemetry_enrichment_build145_deploy.py (NEW migration script), src/autopack/usage_recorder.py (7 new columns lines 88-100, extended function signature lines 255-327), src/autopack/main.py (dashboard integration lines 1247-1276), tests/autopack/test_dashboard_token_efficiency.py (NEW, 7 tests, 322 lines) | 4 |

+| 2025-12-31 | BUILD-145 | P1 Hardening (100% COMPLETE ✅) | Token Efficiency Observability - Production Hardening: Completed minimum required hardening (P1.1-P1.3) with 100% test coverage (28/28 passing). **Telemetry Correctness Fix**: Recomputed artifact savings AFTER budgeting to only count kept files (not omitted files), added substituted_paths_sample list capped at 10 entries for compact logging. **Terminal Outcome Coverage**: Extended telemetry to capture COMPLETE/FAILED/BLOCKED phase outcomes (not just success), added phase_outcome column (nullable for backward compatibility), created best-effort _record_token_efficiency_telemetry() helper that never fails the phase. **Per-Phase Embedding Reset**: Called reset_embedding_cache() at start of _load_scoped_context() to enforce true per-phase cap behavior (ensures _PHASE_CALL_COUNT starts at 0). **Test Coverage**: Added 2 per-phase reset tests (test_embedding_cache.py), 3 kept-only telemetry tests (test_token_efficiency_observability.py), all 28 tests passing (100%). **Impact**: Observability trustworthy (kept-only savings prevent over-reporting), failure visibility (metrics recorded for all outcomes), embedding cap correctly bounded per-phase. Production-ready with backward-compatible schema. Files: src/autopack/autonomous_executor.py (kept-only recomputation lines 7294-7318, per-phase reset line 7307-7308, telemetry helper lines 1444-1517), src/autopack/usage_recorder.py (phase_outcome column line 86), tests/autopack/test_embedding_cache.py (+2 tests), tests/autopack/test_token_efficiency_observability.py (+3 tests) | 4 |

+| 2025-12-31 | BUILD-145 | P1.1 + P1.2 + P1.3 (95% COMPLETE ✅) | Token Efficiency Infrastructure (Observability + Embedding Cache + Artifact Expansion): Implemented three-phase token efficiency system achieving 95% test coverage (20/21 tests passing). **Phase A (P1.1) Token Efficiency Observability**: Created TokenEfficiencyMetrics database model tracking per-phase metrics (artifact_substitutions, tokens_saved_artifacts, budget_mode, budget_used/cap, files_kept/omitted), implemented record_token_efficiency_metrics() and get_token_efficiency_stats() for aggregation, 11/12 tests passing (92%, 1 skipped due to RunFileLayout setup). **Phase B (P1.2) Embedding Cache with Cap**: Implemented local in-memory cache keyed by (path, content_hash, model) using SHA256 hashing for content-based invalidation, per-phase call counting with configurable cap (default: 100, 0=disabled, -1=unlimited), automatic lexical fallback when cap exceeded, 9/9 tests passing (100%). **Phase C (P1.3) Artifact Expansion**: Implemented build_history_pack() aggregating recent run/tier/phase summaries (max 5 phases, 3 tiers, 10k chars cap), should_substitute_sot_doc() + get_sot_doc_summary() for large BUILD_HISTORY/BUILD_LOG replacement, load_with_extended_contexts() applying artifact-first to phase descriptions/tier summaries, all methods 100% implemented with conservative opt-in design. **Configuration**: All features disabled by default (opt-in via env vars: AUTOPACK_ARTIFACT_HISTORY_PACK, AUTOPACK_ARTIFACT_SUBSTITUTE_SOT_DOCS, AUTOPACK_ARTIFACT_EXTENDED_CONTEXTS), added context_budget_tokens: int = 100_000 setting for budget selection. **Known Limitations**: P1.3 lacks dedicated tests (methods verified via code review), telemetry recording not yet wired into autonomous_executor, dashboard integration backwards-compatible (token_efficiency field optional). **Impact**: Observability for token savings tracking, embedding cache reduces API calls ~80% for unchanged files, history pack/SOT substitution reduces context bloat 50-80%, production-ready with opt-in safety. Files: src/autopack/usage_recorder.py (TokenEfficiencyMetrics model + recording functions), src/autopack/file_hashing.py (NEW, SHA256 content hashing), src/autopack/context_budgeter.py (embedding cache + cap enforcement), src/autopack/artifact_loader.py (history pack, SOT substitution, extended contexts), src/autopack/config.py (added context_budget_tokens + embedding cache config), tests/autopack/test_token_efficiency_observability.py (12 tests), tests/autopack/test_embedding_cache.py (9 tests), tests/autopack/test_context_budgeter.py (existing tests updated) | 8 |

+| 2025-12-30 | BUILD-145 | P1 (COMPLETE ✅) | Artifact-First Context Loading (Token Efficiency): Implemented token-efficient read-only context loading by preferring run artifacts (.autonomous_runs/<run_id>/) over full file contents, achieving estimated 50-80% token savings for historical reference files. **Problem**: Scoped context loading read full file contents for read_only_context even when concise phase/tier/run summaries existed in .autonomous_runs/, causing context bloat. **Solution**: Created ArtifactLoader (artifact_loader.py, 244 lines) with artifact resolution priority: (1) Phase summaries (phases/phase_*.md) - most specific, (2) Tier summaries (tiers/tier_*.md) - broader scope, (3) Diagnostics (diagnostics/diagnostic_summary.json, handoff_*.md), (4) Run summary (run_summary.md) - last resort. Artifact substitution: Loads artifact content if smaller than full file (token efficient), calculates token savings (conservative 4 chars/token), logs substitutions for observability. Integration: Enhanced autonomous_executor._load_scoped_context() (lines 7019-7227) to use artifact loader for read_only_context files, tracks artifact_stats (substitutions count, tokens_saved), returns stats in context metadata for downstream reporting. **Token Efficiency Metrics**: Artifact content typically 100-400 tokens vs full file 1000-5000 tokens, estimated savings ~900 tokens per substituted file, conservative matching (only substitutes when artifact clearly references file path). **Safety**: Read-only consumption (no writes to .autonomous_runs/), fallback to full file if no artifact found, graceful error handling (artifact read errors → full file fallback), .autonomous_runs/ confirmed protected by rollback manager (PROTECTED_PATTERNS). **Test Coverage**: 19 comprehensive tests (all passing ✅) validating artifact resolution priority, token savings calculation, fallback behavior, artifact type detection, file basename matching, error handling, Windows path normalization. **Quality**: Conservative token estimation (matches context_budgeter.py), robust artifact search (phase/tier/diagnostics/run summaries), graceful degradation on missing artifacts. Files: src/autopack/artifact_loader.py (NEW, 244 lines), src/autopack/autonomous_executor.py (artifact integration lines 7019-7227), tests/autopack/test_artifact_first_summaries.py (NEW, 278 lines, 19 tests) | 3 |

+| 2025-12-30 | BUILD-145 | P0 Schema (COMPLETE ✅) | API Boundary Schema Normalization for read_only_context: Implemented canonical format normalization at PhaseCreate schema boundary ensuring all consumers receive consistent dict format `[{"path": "...", "reason": ""}]` regardless of whether legacy string format `["path"]` or new dict format is provided. **Problem**: BUILD-145 P0.2 fixed executor-side normalization, but API boundary lacked validation—clients could still send mixed formats. **Solution**: Added field_validator to PhaseCreate.scope (schemas.py:43-86) normalizing read_only_context at API ingestion: (1) Legacy string entries converted to `{"path": entry, "reason": ""}`, (2) Dict entries validated for non-empty 'path' field (skip if path missing/empty/None), (3) Extra fields cleaned (only path+reason preserved), (4) Invalid types skipped (int/list/None). **Impact**: Complements BUILD-145 P0.2 executor fix with upstream validation, ensures database always stores canonical format, prevents format drift at API boundary, maintains backward compatibility with legacy clients. **Test Coverage**: 20 comprehensive tests (all passing ✅) validating legacy string format, new dict format, mixed lists, invalid entry filtering, empty/None path skipping, path preservation (spaces/relative/absolute), normalization idempotency, API boundary integration (RunStartRequest). **Quality**: Graceful degradation (skips invalid entries with empty path), preserves other scope fields during normalization, Pydantic validation ensures type safety. Files: src/autopack/schemas.py (normalize_read_only_context validator, 44 lines), tests/test_schema_read_only_context_normalization.py (NEW, 437 lines, 20 tests) | 2 |

+| 2025-12-30 | BUILD-145 | P0 Safety (COMPLETE ✅) | Rollback Safety Guardrails (Protected Files + Per-Run Retention): Enhanced BUILD-145 P0.3 rollback with production-grade safety features addressing user's P0 hardening guidance. **Safe Clean Mode** (default enabled): Detects protected files before git clean (.env, *.db, .autonomous_runs/, *.log, .vscode/, .idea/), skips git clean if protected untracked files detected, prevents accidental deletion of important development files, configurable via safe_clean parameter (default: True), works with both exact patterns and glob patterns (*.ext). Pattern matching: exact match (.env), glob patterns (*.db), directory patterns (.autonomous_runs/), basename matching for nested files (config/.env matches .env pattern), Windows path normalization (backslash → forward slash). **Per-Run Savepoint Retention** (default enabled): Keeps last N savepoints per run for audit purposes (default: 3, configurable via max_savepoints_per_run parameter), automatically deletes oldest savepoints beyond threshold, provides audit trail for rollback investigations, original behavior (immediate deletion) available via keep_last_n=False. Safety verification: .autonomous_runs/ confirmed in .gitignore (line 84), protected patterns cover development essentials (.env, *.db, logs, IDE settings), safe_clean guards prevent data loss. **Test Coverage**: 16 new safety guardrail tests (all passing), 24 existing rollback tests (all passing), total: 40 rollback tests passing. Implementation: Enhanced rollback_manager.py with _check_protected_untracked_files() method (uses git clean -fdn dry run + pattern matching), updated rollback_to_savepoint() with safe_clean parameter + protected file detection, enhanced cleanup_savepoint() with keep_last_n parameter + per-run retention logic, added _get_run_savepoint_tags() and _delete_tag() helper methods. Files: src/autopack/rollback_manager.py (enhanced from 280→451 lines with protected patterns, safe clean check, retention logic), tests/autopack/test_rollback_safety_guardrails.py (NEW, 299 lines, 16 tests), tests/autopack/test_executor_rollback.py (updated cleanup test for new default behavior) | 3 |

+| 2025-12-30 | BUILD-145 | P0 (COMPLETE ✅) | Migration Runbook + Executor Rollback (Ops + Safety Hardening): **P0.1 Migration Runbook**: Created operator-grade BUILD-144 migration runbook providing step-by-step database migration guidance with prerequisites, environment variables, verification commands (SQL + Python), troubleshooting, and rollback instructions. Runbook documents: total_tokens column migration, nullable token splits schema changes, idempotent migration script usage, verification of schema changes and dashboard aggregation. Added comprehensive smoke tests (12 tests) validating runbook completeness. Updated README.md with runbook reference. **P0.2 Scope Normalization Fix (CRITICAL BLOCKER RESOLVED)**: Fixed autonomous_executor scope parsing bug where read_only_context entries were expected to be strings but docs defined dict format {path, reason}. Added normalization logic supporting both legacy (string list) and new (dict list) formats at lines 7099-7121. Backward compatible with existing runs. Added 17 comprehensive tests validating all edge cases (legacy strings, new dicts, mixed lists, invalid entries, path preservation, filtering). **P0.3 Git-Based Executor Rollback**: Implemented deterministic, opt-in rollback for failed patch applies using git savepoints. Rollback creates git tag savepoint before patch apply (save-before-{run_id}-{phase_id}-{timestamp}), rolls back on failure (apply error, validation error, exception) via git reset --hard + git clean -fd, cleans up savepoint on success. Rollback logs actions to .autonomous_runs/{run_id}/rollback.log for audit trail. Windows-safe subprocess execution (no shell=True). Protected paths never touched except via git commands. Configuration: executor_rollback_enabled (default: false, opt-in via AUTOPACK_ROLLBACK_ENABLED env var). Added rollback manager (rollback_manager.py, 280 lines) integrated into GovernedApplyPath with savepoint creation, rollback triggers, cleanup. Added 24 comprehensive tests (12 rollback unit tests with temp git repo, 12 smoke tests) - ALL PASSING ✅. Files: docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md (NEW, 444 lines), tests/autopack/test_build144_migration_runbook_smoke.py (NEW, 152 lines, 12 tests), README.md (runbook reference), src/autopack/autonomous_executor.py (scope normalization fix lines 7099-7121), tests/autopack/test_scope_read_only_context_normalization.py (NEW, 155 lines, 17 tests), src/autopack/config.py (executor_rollback_enabled flag), src/autopack/rollback_manager.py (NEW, 280 lines), src/autopack/governed_apply.py (rollback integration lines 1806-2116), tests/autopack/test_executor_rollback.py (NEW, 332 lines, 12 tests), tests/autopack/test_build145_rollback_smoke.py (NEW, 110 lines, 12 tests), BUILD_HISTORY.md (this entry) | 10 |

+| 2025-12-30 | BUILD-144 | P0.3 + P0.4 (COMPLETE ✅) | Total Tokens Column + Migration Safety: Fixed critical semantic gap where total-only usage events lost token totals (NULL→0 coalescing under-reported totals). Problem: P0.2 made prompt_tokens/completion_tokens nullable for total-only recording, but dashboard aggregation treated NULL as 0, causing total-only events to lose their totals. Solution: (P0.3 Migration Safety) Created idempotent migration script add_total_tokens_build144.py - checks if column exists, adds total_tokens INTEGER NOT NULL DEFAULT 0, backfills existing rows with COALESCE(prompt_tokens,0)+COALESCE(completion_tokens,0), handles SQLite vs PostgreSQL differences, verification output shows row counts. (P0.4 Total Tokens Column) Added total_tokens column to LlmUsageEvent (usage_recorder.py:25, nullable=False, always populated), updated UsageEventData to require total_tokens:int (line 78), modified _record_usage() to set total_tokens=prompt_tokens+completion_tokens (llm_service.py:616), modified _record_usage_total_only() to explicitly set total_tokens parameter (line 660), changed dashboard aggregation to use event.total_tokens directly instead of sum of splits (main.py:1314-1349), keeps COALESCE NULL→0 for split subtotals only. Test Coverage: 33 tests passing ✅ (8 schema drift + 4 dashboard integration + 7 no-guessing + 7 exact token + 7 provider parity). Impact: Total-only events now preserve totals (not under-reported), dashboard totals accurate for all recording patterns, migration-ready for existing databases, P1 test hardening complete (in-memory SQLite + StaticPool for parallel-safe testing). Success Criteria ALL PASS ✅: total_tokens column exists and non-null, always populated for every usage event, dashboard uses total_tokens for totals (not sum of NULL splits), migration script successfully upgrades existing DBs, all tests pass, zero regressions. Files: src/autopack/usage_recorder.py (total_tokens column + dataclass), src/autopack/llm_service.py (_record_usage + _record_usage_total_only updates), src/autopack/main.py (dashboard aggregation fix), scripts/migrations/add_total_tokens_build144.py (NEW idempotent migration), tests/autopack/test_llm_usage_schema_drift.py (total_tokens tests + all inserts updated), tests/autopack/test_dashboard_null_tokens.py (refactored to in-memory SQLite + StaticPool + assertions updated), README.md (P0.3+P0.4 section), BUILD_HISTORY.md (this entry) | 10 |

+| 2025-12-30 | BUILD-144 | P0 + P0.1 + P0.2 (COMPLETE ✅) | Exact Token Accounting - Replaced Heuristic Splits with Provider SDK Values: Eliminated 40/60 and 60/40 heuristic token splits across all providers (OpenAI, Gemini, Anthropic), replacing with exact prompt_tokens and completion_tokens from provider SDKs. Problem: Dashboard usage aggregation and token accounting relied on guessed splits instead of actual values from APIs. Solution: (1) Schema Extensions - added prompt_tokens/completion_tokens fields to BuilderResult/AuditorResult (llm_client.py:34-35, 47-48), (2) LLM Service Updates - execute_builder_phase/execute_auditor_review use exact tokens when available, fallback to heuristic splits with "BUILD-143" warning when missing (llm_service.py:403-427, 516-548), (3) OpenAI Client - extract response.usage.prompt_tokens and response.usage.completion_tokens (openai_clients.py:207-238, 475-495), (4) Gemini Client - extract usage_metadata.prompt_token_count and usage_metadata.candidates_token_count (gemini_clients.py:231-267, 477-500), (5) Anthropic Client - updated all 27 BuilderResult returns with response.usage.input_tokens and response.usage.output_tokens, (6) Documentation - created phase_spec_schema.md (PhaseCreate schema reference, scope config, task categories, builder modes) and stage2_structured_edits.md (structured edit mode for large files >30KB, EditOperation types, safety validation). Test Coverage: 16 tests passing ✅ (7 exact token accounting tests + 9 dashboard integration tests). Impact: Eliminated token estimation drift (exact values replace guesses), dashboard usage stats now 100% accurate, calibration data quality improved, backward compatible (fallback logic preserves legacy behavior), fixed README doc drift (created 2 missing docs). Success Criteria ALL PASS ✅: All provider clients return exact tokens, LlmUsageEvent records exact values, dashboard aggregates exact tokens, fallback logic works, zero regressions, documentation complete. Files: src/autopack/llm_client.py, src/autopack/llm_service.py, src/autopack/openai_clients.py, src/autopack/gemini_clients.py, src/autopack/anthropic_clients.py, tests/autopack/test_exact_token_accounting.py (NEW), docs/phase_spec_schema.md (NEW), docs/stage2_structured_edits.md (NEW), tests/autopack/test_exact_token_accounting.py (test fixes for quality gate mocking) | 9 |

+| 2025-12-30 | BUILD-143 | Dashboard Parity (COMPLETE ✅) | Dashboard Parity Implementation - README Spec Drift Closed: Implemented all 5 `/dashboard/*` endpoints referenced in README but previously missing from main API. Problem: README claimed dashboard endpoints existed, but tests/test_dashboard_integration.py was globally skipped ("not implemented yet") and main.py had no `/dashboard` routes. Solution: Added GET /dashboard/runs/{run_id}/status (run progress + token usage + issue counts using run_progress.py), GET /dashboard/usage?period=week (token usage aggregated by provider/model from LlmUsageEvent with time-range filtering), GET /dashboard/models (model mappings from ModelRouter), POST /dashboard/human-notes (timestamped notes to .autopack/human_notes.md), POST /dashboard/models/override (global/run-scoped model overrides). Test Coverage: All 9 integration tests passing ✅. Impact: Closed biggest spec drift item from "ideal state" gap analysis, all dashboard functionality now operational. Files: src/autopack/main.py (dashboard endpoints lines 1243-1442), tests/test_dashboard_integration.py (removed pytest skip marker) | 2 |

+| 2025-12-30 | BUILD-142 | Provider Parity + Docs (COMPLETE ✅) | Provider Parity + Telemetry Schema Enhancement + Production Readiness: Extended BUILD-142 category-aware budget optimization to all providers (Anthropic, OpenAI, Gemini) + added telemetry schema separation + migration support + CI drift prevention. **Provider Parity**: OpenAI/Gemini clients now have full BUILD-142 implementation (TokenEstimator integration, conditional override logic preserving docs-like category budgets, P4 enforcement with telemetry separation). OpenAI: 16384 floor conditionally applied, Gemini: 8192 floor conditionally applied. **Telemetry Schema**: Added `actual_max_tokens` column to TokenEstimationV2Event model (final provider ceiling AFTER P4 enforcement), separated from `selected_budget` (estimator intent BEFORE P4). Migration script: add_actual_max_tokens_to_token_estimation_v2.py with idempotent backfill. **Telemetry Writers**: Updated _write_token_estimation_v2_telemetry signature to accept actual_max_tokens, modified both call sites in anthropic_clients.py. **Calibration Script**: Updated waste calculation to use `actual_max_tokens / actual_output_tokens` instead of selected_budget, added fallback for backward compatibility, added coverage warning if <80% samples have actual_max_tokens populated. **Documentation**: (1) BUILD-142_MIGRATION_RUNBOOK.md (200+ lines with prerequisites, step-by-step migration, verification, troubleshooting, rollback), (2) Updated TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md with BUILD-142 semantics section (budget terminology, category-aware base budgets table, verification snippet, migration notes), (3) Updated README.md with BUILD-142 Provider Parity entry. **CI Drift Prevention**: Created test_token_estimation_v2_schema_drift.py (4 tests) to prevent future schema/writer signature regressions using inspect.signature(). **Test Coverage**: 30 tests total (26 BUILD-142 existing + 4 new CI drift). **Impact**: All 3 providers benefit from 50-75% waste reduction for docs/test phases, accurate waste measurement using true API costs, migration-ready for existing telemetry databases, CI-protected against accidental schema regressions. **Budget Terminology** (consistent across all docs): selected_budget = estimator **intent**, actual_max_tokens = final provider **ceiling**, waste calculation always uses actual_max_tokens. Files: src/autopack/openai_clients.py (BUILD-142 parity implementation), src/autopack/gemini_clients.py (BUILD-142 parity implementation), src/autopack/anthropic_clients.py (telemetry writer updates), src/autopack/models.py (actual_max_tokens column), scripts/calibrate_token_estimator.py (coverage warnings + waste calculation fix), scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py (NEW migration script), tests/autopack/test_token_estimation_v2_schema_drift.py (NEW, 4 CI drift tests), docs/guides/BUILD-142_MIGRATION_RUNBOOK.md (NEW), docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md (updated), docs/BUILD-142-PROVIDER-PARITY-REPORT.md (560+ lines), README.md (updated) | 11 |

+| 2025-12-30 | BUILD-142 | COMPLETE ✅ | Category-Aware Conditional Override Fix + V8b Validation: Fixed critical override conflict where unconditional 16384 floor in anthropic_clients.py nullified category-aware base budgets from TokenEstimator. Problem: V8 validation showed docs/low phases using selected_budget=8192 instead of expected 4096, causing 9.07x budget waste. Solution: (1) Conditional override logic (lines 566-597) - only apply 16384 floor for non-docs categories OR when selected_budget >=16384, preserving category-aware reductions for docs-like categories (docs, documentation, doc_synthesis, doc_sot_update). (2) Telemetry semantics fix (lines 697-708) - separated selected_budget (estimator intent, recorded BEFORE P4 enforcement) from actual_max_tokens (final ceiling, recorded AFTER P4 enforcement). (3) Telemetry writer fix (lines 971-973, 1016-1018) - use selected_budget field for accurate calibration data. (4) Complexity fallback fix (lines 406-417) - check token_selected_budget first before applying complexity defaults. **V8b Validation Results** (3 docs/low phases): Phase d1-installation-steps (selected=4096, actual=1252, waste=3.27x, truncated=False), d2-configuration-basics (selected=4096, actual=1092, waste=3.75x, truncated=False), d3-troubleshooting-tips (selected=4096, actual=1198, waste=3.42x, truncated=False). Pre-fix avg waste 7.25x → Post-fix avg waste 3.48x = **52% waste reduction** with zero truncations. **Test Coverage**: 26 tests total (15 conditional override tests + 11 TokenEstimator base budget tests), all passing. **Impact**: docs/low phases correctly use 4096 base budget (down from 8192), projected savings ~665k tokens per 500-phase run (121 docs/low phases × 4096 tokens saved + 83 tests/low phases × 2048 tokens saved), safety preserved for code phases (implementation/refactoring still get 16384 floor), telemetry semantics fixed for accurate calibration. **Success Criteria** (ALL PASS ✅): docs/low uses base=4096 ✅, zero truncations ✅, 52% waste reduction ✅, non-docs categories protected ✅, telemetry accuracy ✅, comprehensive test coverage ✅. Files: src/autopack/anthropic_clients.py (4 fix locations), tests/autopack/test_anthropic_clients_category_aware_override.py (NEW, 15 tests, 317 lines), tests/autopack/test_token_estimator_base_budgets.py (NEW, 11 tests, 190 lines), scripts/create_telemetry_v8_budget_floor_validation.py (NEW), scripts/create_telemetry_v8b_override_fix_validation.py (NEW), docs/BUILD-142-COMPLETION-SUMMARY.md (NEW, 298 lines), examples/telemetry_v8*_docs/ + examples/telemetry_v8b_docs/ (validation deliverables). Commit: 4c96a1ad | 14 |

+| 2025-12-29 | BUILD-141 | Part 10 (COMPLETE ✅) | Telemetry-Collection-V6 Pilot Validation - V6 Targeted Sampling + 3-Issue Root Cause Fix: Successfully validated v6 pipeline with 3-phase pilot (100% success). Run: telemetry-collection-v6 (telemetry_seed_v6_pilot.db). Pilot results: 3/3 COMPLETE (docs/low: d1-quickstart, d2-contributing, d3-architecture-overview), 3 TokenEstimationV2Event records (100% success, 0% truncated), category validation: all 3 phases correctly categorized as `docs` (not `doc_synthesis`) ✅, SMAPE spread: 3.7% to 36.9% (healthy variance). **3 Critical Issues Fixed**: (1) Wrong Runner - batch_drain_controller.py only processes FAILED phases but v6 creates QUEUED phases → Fix: Updated v6 seed script instructions to use drain_queued_phases.py instead, validated via static code check + successful 3-phase drain. (2) DB Misconfiguration Risk - v6 seed script didn't require DATABASE_URL, risking silent fallback to Postgres → Fix: Added mandatory DATABASE_URL guard with helpful error message (PowerShell + bash examples), script exits with clear instructions if not set. (3) Doc Classification Bug - doc phase goals contained trigger words ("comprehensive", "example", "endpoints") causing TokenEstimator to classify as `doc_synthesis` instead of `docs`, breaking sampling plan → Fix: Removed all trigger words from v6 doc goals ("comprehensive"→"Keep it brief", "example"→"snippet/scenario", "endpoints overview"→"API routes overview", "exhaustive API reference"→"exhaustive reference"), validated via TokenEstimator test + actual telemetry events (all show category=`docs`). **DB Schema Fixes** (discovered via trial-and-error): Run model: run_id→id, status→state (enum), goal→goal_anchor (JSON); Phase model: phase_number→phase_index, added tier_id FK, added name, goal→description; Added Tier creation: tier_id="telemetry-v6-T1" (required parent for phases). Impact: V6 pipeline validated (seed→drain→telemetry) with 100% success ✅, doc categorization fixed (trigger word removal prevents doc_synthesis misclassification) ✅, database safety (explicit DATABASE_URL prevents accidental Postgres writes) ✅, correct tooling (drain_queued_phases.py confirmed as proper runner) ✅. Next: Full 20-phase v6 collection to stabilize docs/low (n=3→13), docs/medium (n=0→2), tests/medium (n=3→9). Files: scripts/create_telemetry_v6_targeted_run.py (+150 lines across 8 edits: DB guard, drain instructions, trigger word removal, schema fixes) | 1 |

+| 2025-12-29 | BUILD-141 | Part 9 (COMPLETE ✅) | Telemetry-Collection-V5 + Batch Drain Race Condition Fix + Safe Calibration: Successfully collected 25 clean telemetry samples (exceeds ≥20 target by 25%). Run: telemetry-collection-v5 (telemetry_seed_v5.db), Duration: ~40 minutes batch drain + 2 minutes final phase completion. Results: 25/25 COMPLETE (100% success), 0 FAILED, 26 TokenEstimationV2Event records, 25 clean samples (success=True, truncated=False) ready for calibration, 96.2% success rate. **Investigation & Fixes**: Issue: Batch drain controller reported 2 "failures" but database showed phases COMPLETE. Root Cause #1: Race condition - controller checked phase state before DB transaction committed. Root Cause #2: TOKEN_ESCALATION treated as permanent failure instead of retryable. Fix (scripts/batch_drain_controller.py:791-819): Added 30-second polling loop to wait for phase state to stabilize (not QUEUED/EXECUTING), marked TOKEN_ESCALATION as [RETRYABLE] in error messages, prevents false "failed" reports. **Safe Calibration (Part 1)**: Applied geometric damping (sqrt) to v5 telemetry (25 samples) to avoid over-correction: implementation/low 2000→1120 (ratio=0.313, sqrt≈0.56, -44%), implementation/medium 3000→1860 (ratio=0.379, sqrt≈0.62, -38%), tests/low 1500→915 (ratio=0.370, sqrt≈0.61, -39%). Docs coefficients unchanged (n=3 inadequate, awaiting v6). Updated src/autopack/token_estimator.py PHASE_OVERHEAD with v5 calibration version tracking (CALIBRATION_VERSION="v5-step1", CALIBRATION_DATE="2025-12-29", CALIBRATION_SAMPLES=25). **Documentation**: docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md (best practices for preventing doc-phase truncation: cap output sizes, context loading 5-10 files, token budget 4K-8K). Impact: Telemetry target exceeded (25 vs ≥20) ✅, batch drain reliability (race condition eliminated) ✅, production quality (100% success validates robustness) ✅, token efficiency (best practices documented) ✅, safe calibration (damped partial update prevents over-fitting) ✅. Commits: 26983337 (batch drain fix), f97251e6 (doc best practices), 0e6e4849 (v5 seeding + calibration). Files: scripts/batch_drain_controller.py (+39 lines, -4 lines), docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md (+41 lines), src/autopack/token_estimator.py (PHASE_OVERHEAD calibration), .autopack/telemetry_archives/20251229_222812/ (sanity check + calibration proposal) | 4 |

+| 2025-12-29 | BUILD-141 | Part 8 (COMPLETE ✅ - 100% VALIDATED) | AUTOPACK_SKIP_CI Support + Full Telemetry Collection Rollout: Implemented environment variable flag to bypass CI checks during telemetry collection runs, eliminating blocker from pre-existing test import errors. **ROLLOUT VALIDATION**: Successfully completed 10/10 phase telemetry seed drain (telemetry-collection-v4 run) with ZERO FAILURES, proving BUILD-141 Part 7+8 fixes production-ready end-to-end. **Root Cause**: Test import errors from research system refactoring (ResearchHookManager, ResearchTriggerConfig, etc.) unrelated to idempotent phase fix but blocking PhaseFinalizer via CI collection error detection. **Solution**: (1) src/autopack/autonomous_executor.py:7530-7536 - Added AUTOPACK_SKIP_CI=1 check at start of _run_ci_checks(), returns None (not dict) so PhaseFinalizer doesn't run collection error detection. (2) scripts/probe_telemetry_phase.py - Set AUTOPACK_SKIP_CI=1 by default via env.setdefault() for telemetry runs, display flag status in probe header for observability. (3) tests/autopack/test_skip_ci_flag.py - 3 unit tests validating skip behavior (flag=1 returns None, flag not set runs normally, flag=0 doesn't skip). **Validation Results (Initial Probe)**: Probe test exits 0 ✅, CI skip logged correctly (`[telemetry-p1-string-util] CI skipped (AUTOPACK_SKIP_CI=1 - telemetry seeding mode)`), no PhaseFinalizer CI collection block, telemetry collection working (token_estimation_v2_events 2→3, llm_usage_events 2→4), phase completed successfully. All 3 unit tests PASSED. **Rollout Validation (Full 10-Phase Drain)**: Database: telemetry_seed_fullrun.db (fresh clean room), Duration: ~12 minutes (19:03-19:15 UTC), Results: 10/10 COMPLETE (100% success), 0/10 FAILED (0% failure), telemetry_delta: token_estimation_v2_events 0→10 (meets ≥10 requirement ✅), llm_usage_events 0→20 (2.0 avg per phase, meets ≥2 requirement ✅), DB identity stable: same sqlite file (telemetry_seed_fullrun.db) throughout all phases ✅, No regressions: zero "No valid file changes generated" errors ✅, zero DB mismatch errors ✅, Telemetry success rate: 10/10 events (100% success, 0% truncated). **Evidence**: Phase states (10 COMPLETE, 0 QUEUED, 0 FAILED), /health endpoint confirmed stable db_identity throughout, AUTOPACK_SKIP_CI flag logged correctly for all 10 phases, All phases completed on first attempt with human-approval override (auto-approved). **Impact**: BUILD-141 100% RESOLVED - Production validation proves (1) idempotent phase fix working (Part 7), (2) CI skip bypass working (Part 8), (3) telemetry collection operational, (4) DB identity drift eliminated (Part 7 DB fixes), (5) ready for token estimation calibration with 10 high-quality samples. Test import errors remain separate issue (to address via research test suite rewrite). Commits: 767efae4 (Part 8 implementation), e1950ab3 (rollout docs), c5835e0d (final push). Files: src/autopack/autonomous_executor.py (+6 lines), scripts/probe_telemetry_phase.py (+8 lines), tests/autopack/test_skip_ci_flag.py (NEW, 94 lines), drain_all_telemetry.sh (rollout automation) | 3 |

+| 2025-12-29 | BUILD-141 | Part 7 (COMPLETE) | Idempotent Phase No-Op Success Handling: Fixed "No valid file changes generated" error blocking telemetry collection when Builder regenerates content matching existing files (idempotent phases). **Root Cause**: Full-file mode generates git diffs locally - when Builder output matches existing file content, diff_parts is empty, causing failure instead of success. **Solution**: (1) src/autopack/anthropic_clients.py:1577-1839 - Track attempted file paths during Builder execution loop, check if all attempted files exist on disk, return BuilderResult(success=True) with empty patch and descriptive message when all files exist (idempotent phase). (2) src/autopack/autonomous_executor.py:4073-4091 - Allow executor to accept full-file no-op success (empty patch with "Full-file produced no diffs" message) alongside existing structured edit no-op handling. **Validation Results**: Builder correctly returns success for idempotent phase (examples/telemetry_utils/string_helper.py already exists and matches generated content), executor accepts empty patch, telemetry collected successfully (token_estimation_v2_events 0→1) ✅. **Blocker Identified**: Probe still fails exit code 1 due to pre-existing test import errors from BUILD-141 Part 8 research refactoring (10+ files with ImportError: ResearchTriggerConfig, ResearchPhaseManager, Citation, ReviewConfig, etc.) - UNRELATED to idempotent phase fix but blocks PhaseFinalizer. **Workaround**: Renamed tests/autopack/autonomous/test_research_hooks.py to .disabled (pytest.skip at module level treated as CI collection error). **Impact**: CORE FIX PRODUCTION-READY - idempotent phases now succeed with telemetry collection instead of failing. Remaining blocker (test import errors) addressed in Part 8 via AUTOPACK_SKIP_CI flag. Commits: [see Part 8]. Files: src/autopack/anthropic_clients.py (+61 lines), src/autopack/autonomous_executor.py (+3 lines), tests/autopack/autonomous/test_research_hooks.py → .disabled (renamed) | 3 |

+| 2025-12-29 | BUILD-141 | Part 8 (DB Identity - VALIDATED) | Database Identity Drift - 100% Resolution Validation: Comprehensive 3-run validation (Run A/B/C) proving database identity drift fully eliminated. **Actual Root Cause** (corrected from Part 7): Relative SQLite paths resolving differently based on working directory + silent fallback to autopack.db (NOT database clearing or import-time binding). **P0 Fixes** (commit 78820b3d): (1) src/autopack/config.py:63-88 - SQLite path normalization to absolute using **repo root** (Path(__file__).resolve().parents[2]), NOT working directory (Path.cwd()), ensuring sqlite:///db.db executed from C:/ creates C:/dev/Autopack/db.db; (2) scripts/drain_one_phase.py:18-26 - Removed silent fallback, require explicit DATABASE_URL with clear error; (3) src/autopack/autonomous_executor.py:8844-8882 - Run-exists sanity check after API server starts, fail-fast with [DB_MISMATCH] diagnostics in <5 seconds instead of hours of wasted execution; (4) src/autopack/main.py + database.py - Enhanced debug logging with /health endpoint db_identity when DEBUG_DB_IDENTITY=1. **Validation Results**: Run A (baseline, absolute path): DATABASE_URL identical at all 3 checkpoints, /health shows correct db_identity, run verification succeeded, telemetry collected (token_estimation_v2_events 0→1) ✅. Run B (historical drift trigger, relative path from C:/): Database created at C:/dev/Autopack/telemetry_seed_debug_B.db (repo root) NOT C:/telemetry_seed_debug_B.db (working dir), proves repo-root normalization ✅. Run C (negative test, intentional mismatch): Clear [DB_MISMATCH] error with diagnostics, exit code 1, proves detection works ✅. **Success Criteria**: All met - DB identity maintained across processes, no 404 errors, telemetry working, robust to historical triggers, mismatch detection loud. **Test Skip Note**: tests/autopack/autonomous/test_research_hooks.py temporarily disabled (pytest.skip) - test suite targets old API (ResearchHookManager/ResearchHookResult) but implementation uses ResearchHooks/ResearchDecision with different methods. Needs test rewrite for new architecture. **Impact**: DATABASE IDENTITY DRIFT 100% ELIMINATED - validation proves fixes work across all scenarios (baseline, different CWD, intentional mismatch). Telemetry collection fully unblocked. Commits: 78820b3d (P0 fixes), e03775ed (validation prep). Docs: .autopack/PROBE_FAILURE_ANALYSIS.md (updated to RESOLVED with full validation evidence) | 5 |

+| 2025-12-28 | BUILD-141 | Critical Fix | Database Identity Drift Resolution - EXECUTOR/API SERVER DB ALIGNMENT: Fixed critical blocker where executor and API server used different databases causing 404 errors and apparent "database clearing". **Root Cause**: NOT database clearing but DB identity drift from 3 sources: (1) database.py import-time binding used settings.database_url instead of runtime get_database_url(), (2) autonomous_executor.py partial schema creation (only llm_usage_events table, missing runs/phases/token_estimation_v2_events), (3) API server load_dotenv() overriding DATABASE_URL from parent executor. **Solution**: (1) src/autopack/database.py:11-12 - Changed settings.database_url → get_database_url() for runtime binding, (2) src/autopack/autonomous_executor.py:232-245 - Changed partial schema → init_db() for complete schema (all tables), (3) src/autopack/main.py:64 - Changed load_dotenv() → load_dotenv(override=False) to preserve parent env vars, (4) scripts/create_telemetry_collection_run.py:31-37 - Added explicit DATABASE_URL requirement check. **Evidence**: Before: Executor uses autopack_telemetry_seed.db (1 run, 10 phases) → API server uses autopack.db (0 runs) → 404 errors. After: Both use autopack_telemetry_seed.db (verified in API logs) → No 404s → Database PRESERVED (1 run, 10 phases maintained). Database persistence verified: Before drain (1 run, 10 QUEUED) → After drain (1 run, 1 FAILED + 9 QUEUED). **Impact**: CRITICAL BLOCKER RESOLVED - was preventing ALL autonomous execution. Unblocks T1-T5 telemetry collection, batch drain controller, all future autonomous runs. Commits: 2c2ac87b (core DB fixes), 40c70db7 (.env override fix), fee59b13 (diagnostic logging). Docs: .autopack/TELEMETRY_DB_ROOT_CAUSE.md | 4 |

+| 2025-12-28 | BUILD-141 | Part 7 | Telemetry Collection Unblock (T1-T6-T8): Fixed Builder returning empty `files: []` array (41 output tokens vs expected 5200), blocking telemetry seeding. **Root Cause**: Prompt ambiguity - model didn't understand paths ending with `/` (like `examples/telemetry_utils/`) are directory prefixes where creating files is allowed. **T1 (Prompt Fixes)**: src/autopack/anthropic_clients.py:3274-3308 - (a) Directory prefix clarification: annotate `path/` entries with "(directory prefix - creating/modifying files under this path is ALLOWED)", (b) Required deliverables contract: add "## REQUIRED DELIVERABLES" section listing expected files + hard requirement "Empty files array is NOT allowed". **T2 (Targeted Retry)**: src/autopack/autonomous_executor.py:4091-4120 - Detect "empty files array" errors, retry EXACTLY ONCE with stronger emphasis (safety net for edge cases), fail fast after 1 retry to avoid token waste. **T4 (Telemetry Probe)**: scripts/probe_telemetry_phase.py (new) - Go/no-go gate script: drains single phase, reports Builder output tokens, files array status, DB telemetry row delta, verdict (SUCCESS/FAILED with specific diagnostics). **T5 (Probe Hardening)**: (a) subprocess.run() instead of os.system() for reliable Windows exit codes, (b) Dual table counting (token_estimation_v2_events + llm_usage_events), (c) Deterministic empty-files detection (only report "EMPTY (confirmed)" when verifiable from failure reason, avoid false positives). **T6 (Regression Tests)**: tests/autopack/test_telemetry_unblock_fixes.py (new, 212 lines) - 7 tests covering directory prefix annotation, required deliverables contract, deliverables extraction (top-level + scope), empty files retry logic (exactly once). **T8 (Documentation)**: README.md Part 7, BUILD_HISTORY.md this entry. **Expected Impact**: Builder produces non-empty files array (800-2000 tokens), telemetry events recorded (success=True), zero-yield prevention via probe-first workflow. **Format Switch Recommendation**: If T1 prompt fixes insufficient, next experiment is full_file → NDJSON format switch. **Next Steps**: (1) Test probe script on telemetry-p1-string-util, (2) If SUCCESS: drain remaining 9 phases with --no-dual-auditor, collect ≥20 success=True samples, (3) If FAILED: analyze specific failure mode (empty files confirmed, validity guard triggered, etc.), root cause analysis. Commits: 83414615 (T1-T4), c80dfa35 (T5-T6-T8). Docs: README.md Part 7, .autopack/format_mode_investigation.md (simple prompt for other cursor) | 5 |

+| 2025-12-28 | BUILD-140 | Infrastructure | Database Hygiene & Telemetry Seeding Automation: Comprehensive DB management infrastructure for safe telemetry collection and legacy backlog processing. **Two-Database Strategy**: Established separate databases - `autopack_legacy.db` (70 runs, 456 phases from production) for failure analysis, `autopack_telemetry_seed.db` (fresh) for collecting ≥20 success samples - both `.gitignore`d to prevent accidental commits. **DB Identity Checker** (scripts/db_identity_check.py): Standalone inspector showing URL/path/mtime, row counts, phase state breakdown, telemetry success rates - prevents silent DB confusion. **Quickstart Automation**: Created scripts/telemetry_seed_quickstart.ps1 (Windows PowerShell) and scripts/telemetry_seed_quickstart.sh (Unix/Linux) for end-to-end workflow: DB creation → run seeding → API server start → batch drain → validation. **Key Design Decision**: DATABASE_URL must be set BEFORE importing autopack (import-time binding in config.py) - solution documented: start API server in separate terminal with explicit DATABASE_URL, then batch drain with --api-url flag. **Comprehensive Docs**: docs/guides/DB_HYGIENE_README.md (quick start), docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md (90+ line runbook with troubleshooting), docs/guides/DB_HYGIENE_IMPLEMENTATION_SUMMARY.md (status tracker). Impact: Zero DB confusion (explicit DATABASE_URL enforcement), safe telemetry collection (isolated from legacy failures), automated workflow (quickstart handles entire pipeline), production-ready runbook. Files: scripts/db_identity_check.py (new), scripts/telemetry_seed_quickstart.ps1 (new), scripts/telemetry_seed_quickstart.sh (new), docs/guides/DB_HYGIENE_README.md (new), docs/guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md (new), docs/guides/DB_HYGIENE_IMPLEMENTATION_SUMMARY.md (new) | 6 |

+| 2025-12-28 | BUILD-139 | Infrastructure | T1-T5 Telemetry & Triage Framework: Complete telemetry infrastructure for token estimation calibration and intelligent batch draining. **T1 (Telemetry Seeding)**: Fixed create_telemetry_collection_run.py for ORM compliance (Run/Tier/Phase), creates 10 achievable phases (6 impl, 3 tests, 1 docs), deprecated broken collect_telemetry_data.py, added smoke tests. **T2 (DB Identity Guardrails)**: Created db_identity.py with print_db_identity() (shows URL/path/mtime/counts), check_empty_db_warning() (exits on 0 runs/phases unless --allow-empty-db), integrated into batch_drain_controller.py and drain_one_phase.py. **T3 (Sample-First Triage)**: Drain 1 phase per run → evaluate (success/yield/fingerprint) → continue if promising OR deprioritize if repeating failure with 0 telemetry; prioritization: unsampled > promising > others. **T4 (Telemetry Clarity)**: Added reached_llm_boundary (detects message/context limits) and zero_yield_reason (success_no_llm_calls, timeout, failed_before_llm, llm_boundary_hit, execution_error, unknown) to DrainResult; real-time logging + summary stats. **T5 (Calibration Job)**: Created calibrate_token_estimator.py - reads llm_usage_events (success=True AND truncated=False), groups by category/complexity, computes actual/estimated ratios, generates markdown report + JSON patch with proposed coefficient multipliers; read-only, no auto-edits, gated behind min samples (5) and confidence (0.7). **Legacy DB**: Restored autopack.db from git history to autopack_legacy.db (456 phases). Impact: Unblocked telemetry data collection, reduced token waste on failing runs, clear zero-yield diagnostics, safe calibration workflow. Files: scripts/create_telemetry_collection_run.py (fixed), scripts/collect_telemetry_data.py (deprecated), tests/scripts/test_create_telemetry_run.py (new), src/autopack/db_identity.py (new), scripts/batch_drain_controller.py (T3+T4 enhancements), scripts/drain_one_phase.py (T2 integration), scripts/calibrate_token_estimator.py (new). Commits: 08a7f8a9 (T1), 8eaee3c2 (T2), ad46799b (T3), 36db646a (T4), a093f0d0 (T5) | 7 |

+| 2025-12-28 | BUILD-138 | Tooling | Telemetry Collection Validation & Token-Safe Triage: Fixed critical bug where TELEMETRY_DB_ENABLED=1 was missing from subprocess environment (causing 100% telemetry loss). Added adaptive controls: --skip-run-prefix to exclude systematic failure clusters, --max-consecutive-zero-yield for early detection of telemetry issues. Diagnostic batch validated fix (3 events collected vs 0 before). Created analyze_batch_session.py for auto-analysis. All 10 integration tests passing. Ready for 274-phase backlog with token-safe triage settings. | 4 |

+| 2025-12-28 | BUILD-137 | System | API schema hardening: prevent `GET /runs/{run_id}` 500s for legacy runs where `Phase.scope` is stored as a JSON string / plain string. Added Pydantic normalization in `PhaseResponse` to coerce non-dict scopes into a dict (e.g., `{\"_legacy_text\": ...}`) so the API can serialize and the executor can keep draining (scope auto-fix can then derive `scope.paths`). Added regression tests for plain-string and JSON-string scopes. | 2 |

+| 2025-12-27 | BUILD-136 | System | Structured edits: allow applying structured edit operations even when target files are missing from Builder context (new file creation or scope-limited context). `StructuredEditApplicator` now reads missing existing files from disk or uses empty content for new files (with basic path safety). Added regression tests. Unblocked `build130-schema-validation-prevention` Phase 0 which failed with `[StructuredEdit] File not in context` and `STRUCTURED_EDIT_FAILED`. | 2 |

+| 2025-12-23 | BUILD-129 | Phase 1 Validation (V3) | Token Estimation Telemetry V3 Analyzer - Final Refinements: Enhanced V3 analyzer with production-ready validation framework based on second opinion feedback. Additions: (1) Deliverable-count bucket stratification (1 file / 2-5 files / 6+ files) to identify multi-file phase behavior differences, (2) --under-multiplier flag for configurable underestimation tolerance (default 1.0 strict, recommended 1.1 for 10% tolerance) - implements actual > predicted * multiplier to avoid flagging trivial 1-2 token differences, (3) Documentation alignment - updated TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md Phase 2/3 to reference V3 analyzer commands instead of older analyzer. Production-ready command: `python scripts/analyze_token_telemetry_v3.py --log-dir .autonomous_runs --success-only --stratify --under-multiplier 1.1 --output reports/telemetry_success_stratified.md`. V3 methodology complete: 2-tier metrics (Tier 1 Risk: underestimation ≤5%, truncation ≤2%; Tier 2 Cost: waste ratio P90 < 3x), success-only filtering, category/complexity/deliverable-count stratification. Status: PRODUCTION-READY, awaiting representative data (need 20+ successful production samples). Files: scripts/analyze_token_telemetry_v3.py (+50 lines deliverable-count stratification, --under-multiplier parameter handling), docs/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md (Phase 2/3 command updates), reports/v3_parser_smoke.md (smoke test results). Docs: TOKEN_ESTIMATION_V3_ENHANCEMENTS.md, TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md | 3 |

+| 2025-12-23 | BUILD-133 | Planning | BUILD-132 Coverage Delta Integration Plan: Comprehensive implementation plan (2-3 hours) for integrating pytest-cov coverage tracking with Quality Gate. Problem: coverage_delta currently hardcoded to 0.0 at 8 sites in autonomous_executor.py, preventing Quality Gate from detecting coverage regressions. Solution: (1) Enable pytest-cov in pytest.ini with JSON output format, (2) Create CoverageTracker module to calculate delta (current - baseline), (3) Integrate at 8 executor call sites, (4) Establish baseline coverage. 4-phase plan includes: coverage collection setup (30 min), CoverageTracker implementation with unit tests (45 min), executor integration (30 min), documentation and baseline establishment (30 min). Deliverables: BUILD-132_COVERAGE_DELTA_INTEGRATION.md (600 lines) with complete module design, test specifications, rollout plan, and success criteria. Benefits: Enhanced Quality Gate decision-making with coverage regression detection (<5% threshold), data-driven quality assessment. Status: PLANNED, ready for implementation. Prerequisites: pytest-cov 7.0.0 already installed. Risk: LOW (graceful fallback to 0.0 on errors). Docs: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md | 1 |

+| 2025-12-23 | BUILD-131 | Tooling | Token Estimation Telemetry Analysis Infrastructure: Created comprehensive analysis script (400 lines) to monitor and validate BUILD-129 Phase 1 token estimation accuracy. Components: (1) TelemetryAnalyzer - Scans log files for [TokenEstimation] entries, calculates statistics (mean/median/std dev/min/max error rates), identifies over/under-estimation bias, generates recommendations for coefficient tuning. (2) Reporting - Produces markdown reports with error rate analysis, bias assessment, tuning recommendations based on thresholds (>50% critical, 30-50% warning, <30% good). (3) Pattern Analysis - Shows worst predictions to identify systematic estimation errors. Target: <30% mean error rate. Usage: python scripts/analyze_token_telemetry.py [--output report.md] [--worst N]. Includes 4-step monitoring workflow: (1) Run after every 10-20 production executions, (2) Review error rate and bias, (3) Tune TokenEstimator coefficients if >30% error, (4) Track improvement over time. Documentation: Updated BUILD-127-128-129_GAPS_AND_IMPROVEMENTS.md Part 5.5 with implementation summary, usage guide, monitoring workflow, and validation steps. Benefits: Data-driven validation of TokenEstimator accuracy, automated analysis reduces manual effort, clear metrics for coefficient optimization. Status: COMPLETE, awaiting production telemetry data collection. Files: scripts/analyze_token_telemetry.py (400 lines), docs/BUILD-127-128-129_GAPS_AND_IMPROVEMENTS.md (+70 lines Part 5.5). Docs: BUILD-127-128-129_GAPS_AND_IMPROVEMENTS.md Part 5.5 | 2 |

+| 2025-12-23 | BUILD-129 | Phase 1 Validation | Token Estimation Validation Telemetry (Layer 1 Monitoring): Added [TokenEstimation] logging to anthropic_clients.py to validate BUILD-129 Phase 1 TokenEstimator accuracy. Logs predicted vs actual output tokens with error percentage after each Builder execution. Implementation: anthropic_clients.py lines 631-652 - extracts _estimated_output_tokens from phase_spec, compares with actual_output_tokens from API response, calculates error percentage |actual - predicted| / predicted * 100%, logs with [TokenEstimation] tag. Non-intrusive: Only activates when _estimated_output_tokens is present in phase_spec (set by ManifestGenerator). Example output: "[TokenEstimation] Predicted: 500 output tokens, Actual: 114 output tokens, Error: 77.2%". Test script (scripts/test_token_telemetry.py) validates telemetry logging. Benefits: Enables data-driven validation of token estimation accuracy (target <30% error), supports coefficient tuning based on real production data, monitoring infrastructure for BUILD-129 effectiveness. Next steps: Collect 10-20 production runs with telemetry, run analysis script to establish baseline, tune TokenEstimator if error rate >30%. Files: anthropic_clients.py (+25 lines telemetry logging), scripts/test_token_telemetry.py (70 lines test script). Docs: BUILD-127-128-129_GAPS_AND_IMPROVEMENTS.md Part 5.5 | 2 |

+| 2025-12-23 | BUILD-130 | Prevention | Schema Validation & Circuit Breaker (Manual Implementation): Comprehensive prevention infrastructure to eliminate infinite retry loops and 500 errors from database schema drift. Components: (1) **ErrorClassifier** - Classify errors as TRANSIENT vs DETERMINISTIC (prevents retrying deterministic failures), detect enum violations, suggest remediation. (2) **SchemaValidator** - Startup validation of database enum values against code definitions, fuzzy matching for suggested fixes, raw SQL queries to bypass ORM. (3) **BreakGlassRepair** - Emergency repair CLI using raw SQL to fix schema violations when ORM fails, transaction-safe repairs with audit logging. (4) **Circuit Breaker Integration** - classify_api_error() in executor's get_run_status() to prevent infinite retries on 500 enum errors. Impact: Prevents BUILD-127/129 retry loops, enables autonomous self-improvement. Files: error_classifier.py (257 lines), schema_validator.py (233 lines), break_glass_repair.py (169 lines), scripts/break_glass_repair.py (122 lines CLI), autonomous_executor.py (circuit breaker integration lines 1040-1106, schema validation lines 665-690), config.py (get_database_url helper). Status: MANUALLY IMPLEMENTED (autonomous attempt failed on deliverables validation - code already existed). Docs: BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md (to be created) | 6 |

+| 2025-12-23 | BUILD-129 | Phase 3 | NDJSON Truncation-Tolerant Format: Implemented newline-delimited JSON (NDJSON) format for all phase outputs to enable graceful degradation during truncation. Each line is a complete JSON object (event record), so partial output remains parsable. Components: (1) **NDJSON Emitter** - ndjson_emitter() wrapper for structured logging (continuation_plan, file_record, summary_record, validation_errors), automatic fallback to text blocks when NDJSON parsing fails. (2) **NDJSON Parser** - parse_ndjson_output() extracts continuation_plan and validates all records, tolerates truncated trailing records. (3) **Integration** - anthropic_clients.py requests NDJSON format via system prompt, autonomous_executor.py attempts NDJSON parsing before text-based continuation recovery. (4) **15 Comprehensive Tests** - tests/test_ndjson_format.py validates emission, parsing, truncation tolerance, and fallback behavior. Impact: Eliminates silent data loss during truncation, enables reliable continuation recovery. Files: anthropic_clients.py (NDJSON format request in system prompt lines 2294-2322), autonomous_executor.py (NDJSON parsing in continuation recovery lines 3950-3990), tests/test_ndjson_format.py (15 tests, 331 lines). Docs: BUILD-129_NDJSON_FORMAT.md | 3 |

+| 2025-12-23 | BUILD-129 | Phase 2 | Continuation-Based Recovery: Implemented robust continuation recovery for truncated Builder responses using structured continuation plans. Builder emits continuation plan when output exceeds token budget, executor resumes from last completed file. Components: (1) **Continuation Plan Extraction** - extract_continuation_plan() parses JSON/NDJSON continuation plans with file completion status and next steps. (2) **Smart Resume** - _handle_continuation() filters patch content to remove already-applied files, re-prompts Builder with "continue from FILE X" instruction and context of completed work. (3) **Integration** - Integrated into autonomous_executor.py truncation recovery flow (lines 3890-4010), replaces naive token-doubling with stateful resume. (4) **6 Comprehensive Tests** - tests/test_continuation_recovery.py validates plan extraction, filtering, and resume prompt generation. Impact: Reduces wasted tokens by 70% (resume from checkpoint vs full regeneration), prevents re-application of already-applied patches. Files: autonomous_executor.py (continuation recovery logic lines 3890-4010), tests/test_continuation_recovery.py (6 tests, 184 lines). Docs: BUILD-129_CONTINUATION_RECOVERY.md | 2 |

+| 2025-12-23 | BUILD-129 | Phase 1 | Output-Size Predictor (Token Estimator): Implemented proactive token estimation to prevent truncation before it occurs. Estimates Builder output size based on deliverables and context, adjusts max_tokens upfront. Components: (1) **TokenEstimator** - estimate_builder_output_tokens() calculates base cost (system prompt + context) + per-file generation cost (350 tokens/file for patches, 200 tokens/file for structured edits). (2) **Dynamic Adjustment** - _calculate_dynamic_max_tokens() in anthropic_clients.py uses TokenEstimator to set max_tokens with 20% safety margin. (3) **Integration** - Integrated into anthropic_clients.py _build_with_truncation_handling() (lines 1823-1840), autonomous_executor.py logs estimated vs actual tokens. (4) **8 Comprehensive Tests** - tests/test_token_estimator.py validates estimation accuracy across scenarios (small/large phases, patches vs structured edits, long context). Impact: Reduces truncation rate by 60% (proactive sizing vs reactive recovery), saves retries and API costs. Files: token_estimator.py (135 lines), anthropic_clients.py (token estimation integration lines 1823-1840), autonomous_executor.py (logging), tests/test_token_estimator.py (8 tests, 243 lines). Docs: BUILD-129_TOKEN_ESTIMATOR.md | 4 |

+| 2025-12-23 | BUILD-128 | Prevention | Deliverables-Aware Manifest System (Prevention for Category Mismatches): Implemented deliverables-first scope inference to prevent pattern matching from incorrectly categorizing phases. Root cause: ManifestGenerator ignored deliverables field, used pattern matching which incorrectly classified BUILD-127 backend implementation as "frontend" (62%). Solution: (1) Category inference from deliverable paths via regex patterns (backend/frontend/tests/database/docs/config), (2) Path sanitization for human annotations (" with ", action verbs, "Documentation in "), (3) Scope expansion with category-specific context files (models.py for backend, conftest.py for tests), (4) Fixed allowed_roots derivation to detect files vs directories (check '.' in last segment). Includes 19 comprehensive tests validating all scenarios including BUILD-127 regression. Emphasizes future reusability - NOT a one-off fix. Files: manifest_generator.py (+270 lines with _infer_category_from_deliverables, _expand_scope_from_deliverables, enhanced _enhance_phase), deliverables_validator.py (sanitize_deliverable_path +48 lines), autonomous_executor.py (4 locations for allowed_roots derivation), preflight_validator.py (pass allowed_paths), tests/test_manifest_deliverables_aware.py (19 tests), docs/BUILD-128_DELIVERABLES_AWARE_MANIFEST.md | 6 |

+| 2025-12-23 | BUILD-127 | Phase 3 | Enhanced Deliverables Validation: Implemented structured manifest validation to ensure Builder creates all expected deliverables with required symbols. Builder emits JSON manifest listing created/modified files and their key symbols (classes, functions), PhaseFinalizer validates manifest against expected deliverables and file contents. Components: (1) **Manifest Request** - anthropic_clients.py requests deliverables manifest in system prompt with format specification (lines 2331-2360). (2) **Manifest Extraction & Validation** - deliverables_validator.py: extract_manifest_from_output() parses manifest from Builder output (regex-based), validate_structured_manifest() checks file existence + symbol presence via substring search, supports directory deliverables matching (lines 942-1079). (3) **Gate 3.5 Integration** - phase_finalizer.py: added builder_output parameter to assess_completion(), Gate 3.5 validates manifest if present (optional - backward compatible), blocks completion if validation fails (lines 177-197). (4) **15 Comprehensive Tests** - tests/test_manifest_validation.py validates extraction, validation, edge cases (empty symbols, missing files, invalid structure). Impact: Catches missing test files and symbols (BUILD-126 Phase E2 scenario), improves deliverable enforcement beyond file existence. Files: anthropic_clients.py (manifest request lines 2331-2360), deliverables_validator.py (extraction + validation lines 942-1079), phase_finalizer.py (Gate 3.5 lines 177-197, builder_output parameter), tests/test_manifest_validation.py (15 tests, 237 lines). Docs: Covered in BUILD-127-129_IMPLEMENTATION_STATUS.md | 4 |

+| 2025-12-23 | BUILD-127 | Phase 2 | Governance Request Handler: Implemented self-negotiation system for protected path modifications with conservative auto-approval policy and database audit trail. Enables Builder to request approval for protected file changes, with automatic approval for low-risk paths (tests, docs) and human approval required for core files. Components: (1) **GovernanceRequest Model** - dataclass + SQLAlchemy model for tracking requests (request_id, run_id, phase_id, paths, justification, risk_level, approval status). (2) **Auto-Approval Policy** - can_auto_approve() conservative policy: auto-approve tests/docs for low/medium risk, block high/critical risk, block core autopack files, block large changes >100 lines, default deny for unknown paths. (3) **Risk Assessment** - assess_risk_level() pattern-based risk scoring (critical: models.py/governed_apply.py/migrations, high: other autopack files, low: tests/docs, medium: default). (4) **CRUD Operations** - create_governance_request() creates DB record with auto-approval decision, approve_request()/deny_request() for human review, get_pending_requests() for API/UI. (5) **Structured Errors** - create_protected_path_error() JSON-encoded error for autonomous_executor.py to parse and trigger governance flow. (6) **18 Comprehensive Tests** - tests/test_governance_requests.py validates auto-approval policy, risk assessment, CRUD operations, structured errors. (7) **Migration Script** - scripts/migrate_governance_table.py for existing databases. Integration points prepared in governed_apply.py, autonomous_executor.py, main.py. Impact: Enables controlled self-modification with audit trail, prevents unauthorized changes to core files while allowing safe test/doc updates. Files: governance_requests.py (396 lines), models.py (GovernanceRequest model), migrate_governance_table.py (70 lines), tests/test_governance_requests.py (18 tests, 236 lines), governed_apply.py (integration hooks), autonomous_executor.py (integration hooks), main.py (API endpoints prepared). Docs: Covered in BUILD-127-129_IMPLEMENTATION_STATUS.md | 7 |

+| 2025-12-23 | BUILD-127 | Phase 1 | Self-Healing Governance Foundation - Phase 1 (Initial Attempt): Attempted to implement authoritative completion gates (TestBaselineTracker, PhaseFinalizer, GovernanceRequestHandler) but blocked by manifest categorization bug. Issue discovered: BUILD-127 deliverables explicitly list backend files (src/autopack/*.py, alembic migration, tests/*.py) but ManifestGenerator ignored deliverables, ran pattern matching on goal text "completion gates", matched frontend dashboard files, incorrectly categorized as "frontend" with 62% confidence. Violation: Builder attempted to modify protected frontend files, governance rejection. Multiple retry attempts failed with same root cause. Exposed critical gap: deliverables field was being ignored. Led to BUILD-128 prevention system. Status: SUPERSEDED by BUILD-127 Phase 2 & 3 manual implementations. BUILD-128 fix validated - category now "tests" (41.7%) NOT "frontend". BUILD-129 truncation fixes enabled Phase 2 & 3 completion | 0 |

+| 2025-12-23 | BUILD-126 | Feature | Quality Gate Full Implementation by Autopack (Phase F+G Complete): Autopack autonomously replaced quality_gate.py stub with full 535-line implementation during BUILD-126 Phase F/G execution. Features implemented: (1) Git checkpoint creation with stash support (save working tree state before validation), (2) Validation test execution with pytest subprocess and structured output parsing, (3) Rollback mechanism on validation failure (restore checkpoint via git reset --hard + stash pop), (4) Risk-based enforcement with configurable thresholds (skip validation for low-risk phases, enforce for high-risk/protected paths). Integration: Called by autonomous_executor.py during phase completion. Validates BUILD-112/113/114 inference - Autopack successfully used deep retrieval (BUILD-112) and goal-aware decision making (BUILD-113) to implement complex feature autonomously. Demonstrates system's ability to self-improve. Code shows sophisticated error handling, atomic git operations, and proper state restoration. This represents a milestone: Autopack writing Autopack's own quality gates | 1 |

+| 2025-12-22 | BUILD-122 | Setup | Lovable Integration Setup: Created autonomous run folder (.autonomous_runs/lovable-integration-v1/) with 12 phases organized by priority (P1: Agentic File Search → P12: Context Truncation). Revised plan based on Claude Code in Chrome analysis - removed SSE Streaming, upgraded browser synergy patterns (HMR Error Detection, Missing Import Auto-Fix). Expected impact: 60% token reduction (50k→20k), 95% patch success (+20pp), 75% hallucination reduction, 50% faster execution. Timeline: 5-6 weeks (vs 10 weeks original). Strategic pivot: Cancelled BUILD-112 Phase 5 Evidence Requests (replaced by Claude Chrome). Ready for autonomous execution or manual implementation via Cursor | 0 |

+| 2025-12-22 | BUILD-121 | Validation | Approval Polling Fix Validation: Test run build112-completion with BUILD-120 fix - zero approval polling 404 errors (vs hundreds in BUILD-120), executor correctly extracts approval_id from POST response and uses GET /approval/status/{approval_id} endpoint. Validates auto-approve mode detection before polling. Bug confirmed fixed | 0 |

+| 2025-12-22 | BUILD-120 | Hotfix | Approval Polling Bug Fix + Telegram Notification Fix: (1) Fixed executor calling wrong endpoint - was GET /approval/status/{phase_id} (string), now extracts approval_id from POST response and uses GET /approval/status/{approval_id} (integer). Added immediate approval check for auto-approve mode. Fixed in 2 locations (autonomous_executor.py lines 7138-7162, 7263-7288). (2) Fixed Telegram notification - removed "Show Details" button causing API 400 error (localhost URL invalid for Telegram inline buttons). Telegram notifications now send successfully | 2 |

+| 2025-12-22 | BUILD-117 | Feature | Approval Endpoint for BUILD-113 Integration (Complete with all 4 enhancements): (1) Telegram integration ✅ - approval requests to phone with Approve/Reject buttons, real-time notifications, completion notices. (2) Database audit trail ✅ - ApprovalRequest model tracks all requests, who/when approved/rejected, timeout tracking. (3) Timeout mechanism ✅ - configurable timeout (15min default), background cleanup task, auto-apply default action. (4) Dashboard UI support ✅ - /approval/pending and /approval/status endpoints ready for UI. See docs/BUILD-117-ENHANCEMENTS.md | 3 |

+| 2025-12-22 | BUILD-116 | Completion | BUILD-112 Completion Run (build112-completion): 3/4 phases complete via autonomous execution - Phase 3 (Deep Retrieval Validation) 95%→100% ✅, Phase 4 (Second Opinion Testing) 90%→100% ✅, Phase 5 Part 1 (Evidence Request Integration) 20%→50% ✅, Phase 5 Part 2 (Dashboard UI) queued. Run state: DONE_FAILED_REQUIRES_HUMAN_REVIEW. Overall BUILD-112 progress: 70%→85% complete | 0 |

+| 2025-12-22 | BUILD-115 | Hotfix | Remove obsolete models.py dependencies (7 parts): Executor now fully API-based with no direct database ORM queries - disabled all models.py imports, replaced database queries with API calls (get_next_queued_phase), execute_phase uses PhaseDefaults when no DB state, all database write methods return None. Architecture change: hybrid API+DB → pure API | 1 |

+| 2025-12-22 | BUILD-114 | Hotfix | BUILD-113 Structured Edit Support: Fix proactive mode integration to check both patch_content AND edit_plan (not just patch_content) - modified build_history_integrator.py line 66-67 to support structured edits used when context ≥30 files. VALIDATED: BUILD-113 decision triggered successfully for research-build113-test (risky, HIGH risk, +472 lines) | 1 |

+| 2025-12-21 | BUILD-113 | Feature | Iterative Autonomous Investigation (Phase 1+2+3 COMPLETE): multi-round evidence collection with goal-aware judgment - IterativeInvestigator, GoalAwareDecisionMaker, DecisionExecutor with safety nets (save points, rollback), enhanced decision logging with alternatives tracking, **NEW: Proactive mode integration** - analyzes fresh patches before applying (risk assessment, confidence scoring, auto-apply CLEAR_FIX or request approval for RISKY), integrated into autonomous_executor with --enable-autonomous-fixes CLI flag - 90% → 100% diagnostics parity | 10 |

+| 2025-12-21 | BUILD-112 | Feature | Diagnostics Parity with Cursor (70% → 90%): fix README.md doc link, complete rewrite of cursor_prompt_generator.py (40 → 434 lines with 8 rich sections), add deep retrieval auto-triggers to diagnostics_agent.py, wire --enable-second-opinion CLI flag to autonomous_executor.py | 5 |

+| 2025-12-21 | BUILD-111 | Tooling | Telegram setup and testing scripts: create setup_telegram.py (interactive bot config), verify_telegram_credentials.py (credential validation), check_telegram_id.py (bot token vs chat ID identification) | 3 |

+| 2025-12-21 | BUILD-110 | Feature | Automatic save points for deletions >50 lines: create git tags (save-before-deletion-{phase_id}-{timestamp}) with recovery instructions before large deletions | 1 |

+| 2025-12-21 | BUILD-109 | Hotfix | Update test_deletion_safeguards.py to use new flag names (deletion_notification_needed, deletion_approval_required) and add dotenv support for .env loading | 1 |

+| 2025-12-21 | BUILD-108 | Feature | Two-tier deletion safeguards: 100-200 lines = notification only (don't block), 200+ lines = require approval (block execution) + phase failure notifications | 3 |

+| 2025-12-21 | BUILD-107 | Feature | Telegram approval system: TelegramNotifier class with send_approval_request(), send_completion_notice(), webhook-based approve/reject buttons | 1 |

+| 2025-12-21 | BUILD-106 | Quality | Fix handoff_bundler.py test failures: add missing 'version' field to index.json, change glob() to rglob() for recursive artifact discovery (nested dirs, binary files), add *.txt and *.bin patterns - achieves 100% test pass rate (45 passed / 47 total, 2 skipped) for diagnostics parity implementation | 1 |

+| 2025-12-21 | BUILD-105 | System | Add executor-side batching for diagnostics parity phases 1, 2, 4 (handoff-bundle, cursor-prompt, second-opinion): prevent truncation/malformed-diff convergence failures by splitting 3-4 file phases into smaller batches (code → tests → docs) | 1 |

+| 2025-12-21 | BUILD-104 | Hotfix | Fix ImportError in autonomous_executor.py: incorrect `log_error` import should be `report_error` (function doesn't exist in error_reporter.py), blocking all phase execution after max attempts | 1 |

+| 2025-12-21 | BUILD-103 | Integration | Mount research router in main.py + fix import issues: corrected router.py relative import, aligned __init__.py exports with actual schemas, added router mounting with /research prefix | 3 |

+| 2025-12-20 | BUILD-102 | Completion | Diagnostics parity phases 3 & 5 completed autonomously via autopack-diagnostics-parity-v5 (BUILD-101 batching enabled convergence for deep_retrieval + iteration_loop phases) | 0 |

+| 2025-12-20 | BUILD-101 | System | Executor-side batching mechanism for diagnostics phases: added generic batched deliverables execution with per-batch manifest gates, validation, and docs-truncation fallback | 1 |

+| 2025-12-20 | BUILD-100 | Hotfix | Executor startup fix: import `DiagnosticsAgent` from `autopack.diagnostics.diagnostics_agent` (namespace package has no re-export), unblocking diagnostics parity runs | 2 |

+| 2025-12-20 | BUILD-099 | Hotfix | Executor: add in-phase batching for diagnostics followups (`diagnostics-deep-retrieval`, `diagnostics-iteration-loop`) to prevent multi-file patch truncation/malformed diffs + tighten per-batch manifest enforcement | 3 |

+| 2025-12-20 | BUILD-098 | Hotfix | Fix TypeError in autonomous_executor.py line 3617 where phase.get() returned None instead of default value 5, causing "NoneType - int" crash during truncation recovery | 1 |

+| 2025-12-20 | BUILD-097 | Hotfix | Clean merge conflict markers from src/autopack/main.py left by retry-api-router-v2 failed patch attempts, enabling research-api-router phase to converge successfully with Claude Sonnet 4.5 | 1 |

+| 2025-12-20 | BUILD-096 | Hotfix | Add `src/autopack/main.py` to ALLOWED_PATHS in governed_apply.py to enable research-api-router followup (narrowly unblocks main.py for FastAPI router registration, per followup-4 requirements) | 1 |

+| 2025-12-20 | BUILD-095 | Hotfix | Fix autonomous_executor.py manifest gate allowed_roots computation (3 locations): add `examples/` to preferred_roots and fix fallback logic to detect filenames, matching BUILD-094 fix in deliverables_validator.py | 1 |

+| 2025-12-20 | BUILD-094 | Hotfix | Fix deliverables_validator.py root computation bug: add `examples/` to preferred_roots and fix fallback logic to detect filenames (containing `.`) in second segment, preventing false "outside allowed roots" failures | 2 |

+| 2025-12-20 | BUILD-093 | Hotfix | Reset `retry_attempt` counter to allow phases 2-3 retry after ImportError fix; phases successfully completed on second execution | 0 |

+| 2025-12-20 | BUILD-092 | Hotfix | Implement missing `format_rules_for_prompt` and `format_hints_for_prompt` functions in learned_rules.py to fix ImportError blocking Builder execution | 1 |

+| 2025-12-20 | BUILD-091 | Hotfix | Fix YAML syntax errors in follow-up requirements: quote backtick-prefixed feature strings to prevent YAML parsing failures during run seeding | 4 |

+| 2025-12-20 | BUILD-090 | Hotfix | Allowlist diagnostics parity subtrees (`src/autopack/diagnostics/`, `src/autopack/dashboard/`) so Followups 1–3 can apply under governed isolation | 1 |

+| 2025-12-20 | BUILD-089 | Quality | Chunk 2B quality gate: implement missing `src/autopack/research/*` deliverables for web compilation + fix/expand tests to meet ≥25 tests and ≥80% coverage | 8 |

+| 2025-12-19 | BUILD-088 | Hotfix | Executor: prevent best-effort run_summary writes from prematurely finalizing `runs.state` to DONE_* while phases are still retryable/resumable | 1 |

+| 2025-12-19 | BUILD-087 | Tooling | Research system preflight + requirements normalization: unify chunk deliverable roots to `src/autopack/research/*`, add missing deps, add preflight analyzer | 8 |

+| 2025-12-19 | BUILD-086 | Docs | Update capability gap report + runbook to reflect post-stabilization reality; add next-cursor takeover prompt | 3 |

+| 2025-12-19 | BUILD-085 | Hotfix | Chunk 5 convergence: allow prefix entries in deliverables manifests (paths ending in `/`) so manifest enforcement doesn’t reject files created under approved directories | 1 |

+| 2025-12-19 | BUILD-084 | Hotfix | Chunk 5 convergence: support directory deliverables (paths ending in `/`) in deliverables validation so phases can specify test/doc directories without deterministic failure | 1 |

+| 2025-12-19 | BUILD-083 | Hotfix | Chunk 4 convergence: allow safe integration subtrees under `src/autopack/` (integrations/phases/autonomous/workflow) so governed apply doesn’t block required deliverables | 1 |

+| 2025-12-19 | BUILD-082 | Hotfix | Deliverables convergence: sanitize annotated deliverable strings from requirements (e.g., `path (10+ tests)`) so manifest gating + deliverables validation can converge for Chunk 4/5 | 1 |

+| 2025-12-19 | BUILD-081 | Hotfix | Chunk 2B convergence: add in-phase batching for `research-gatherers-web-compilation` to reduce patch size and prevent truncated/unclosed-quote diffs and header-only doc diffs | 1 |

+| 2025-12-19 | BUILD-080 | Hotfix | Chunk 1A convergence: allow research CLI deliverable paths under `src/autopack/cli/` without expanding allowlist to `src/autopack/` (prevents protected-path apply rejection) | 3 |

+| 2025-12-19 | BUILD-079 | Hotfix | Executor/back-end compatibility: on auditor_result POST 422 missing `success`, retry with BuilderResultRequest wrapper to support stale backends and eliminate noisy telemetry failures | 1 |

+| 2025-12-19 | BUILD-078 | Hotfix | Chunk 0 convergence: add in-phase batching for research-tracer-bullet + reject malformed header-only new-file diffs (missing ---/+++ or @@ hunks) to prevent truncation/no-hunk apply failures | 3 |

+| 2025-12-19 | BUILD-077 | Hotfix | Fix JSON auto-repair: when new-file diff has no hunks, inject a minimal hunk header so +[] is actually applied | 1 |

+| 2025-12-19 | BUILD-076 | Hotfix | Patch robustness: accept unified diff hunk headers with omitted counts (e.g. @@ -1 +1 @@) to prevent extractor from dropping hunks | 5 |

+| 2025-12-19 | BUILD-075 | Hotfix | Auto-repair empty required JSON deliverables: rewrite gold_set.json to minimal valid JSON [] before apply | 2 |

+| 2025-12-19 | BUILD-074 | Hotfix | Chunk 0 contract hardening: require non-empty valid JSON for gold_set.json and provide explicit Builder guidance | 2 |

+| 2025-12-19 | BUILD-071 | Hotfix | Manifest/allowed-roots derivation: ensure allowed roots cover all expected deliverables (prevents false manifest-gate failures) | 2 |

+| 2025-12-19 | BUILD-072 | Hotfix | Backend API: fix auditor_result schema to match executor payload (prevent 422 on POST auditor_result) | 1 |

+| 2025-12-19 | BUILD-073 | Hotfix | Executor memory summary: fix undefined ci_success when writing phase summaries | 1 |

+| 2025-12-19 | BUILD-070 | Hotfix | Pre-apply JSON validation: reject patches that create empty/invalid JSON deliverables (e.g. gold_set.json) before apply | 2 |

+| 2025-12-19 | BUILD-069 | Hotfix | Patch apply: allow `src/autopack/research/` to override default `src/autopack/` protection (research deliverables must be writable) | 1 |

+| 2025-12-19 | BUILD-068 | Hotfix | Patch apply allowlist: derive allowed_paths from deliverables so GovernedApply can write to protected-by-default roots (src/autopack/research/*) | 1 |

+| 2025-12-19 | BUILD-067 | Hotfix | Fix isolation policy: do not mark `src/autopack/` as protected (blocked research deliverables patch apply) | 1 |

+| 2025-12-19 | BUILD-066 | Hotfix | Manifest enforcement: inject deliverables contract/manifest into Builder prompts and reject patches that create files outside the approved manifest | 4 |

+| 2025-12-19 | BUILD-065 | Hotfix | Deliverables manifest gate: require exact JSON file-path plan before running Builder patch generation | 2 |

+| 2025-12-19 | BUILD-064 | Hotfix | Deliverables enforcement: strict allowed-roots allowlist + hard error for any files outside allowed roots | 2 |

+| 2025-12-19 | BUILD-063 | Hotfix | OpenAI fallback: fix client base_url + accept full-file pipeline kwargs; skip Anthropic-only replanning when Anthropic disabled | 2 |

+| 2025-12-19 | BUILD-062 | Hotfix | Provider fallback: auto-disable Anthropic on “credit balance too low” and route Doctor/Builder to OpenAI/Gemini | 1 |

+| 2025-12-19 | BUILD-061 | Hotfix | Executor: don’t finalize run as DONE_* when stopping due to max-iterations/stop-signal; only finalize when no executable phases remain | 1 |

+| 2025-12-19 | BUILD-060 | Hotfix | Anthropic streaming resilience: retry transient incomplete chunked reads so phases don’t burn attempts on flaky streams | 1 |

+| 2025-12-19 | BUILD-059 | Hotfix | Deliverables validation: detect forbidden roots + provide explicit root-mapping guidance to drive self-correction | 1 |

+| 2025-12-19 | BUILD-058 | Hotfix | Qdrant availability: add docker-compose service + T0 health check guidance (non-fatal) | 2 |

(diff truncated)
```

## DEBUG_LOG.md

- **status**: divergent
- **root_sha256**: `4787e0dab650dc766addbe5cfce6b3d20e3fde93eaca376a2ef3115153a6d4bb`
- **docs_sha256**: `f63f940bda536e3e92c67603c74479c449e9a9cd1410baaccd3e0d67ae853d58`
- **root_size_bytes**: `53029`
- **docs_size_bytes**: `102209`

Suggested merge commands:
- `git diff --no-index DEBUG_LOG.md docs/DEBUG_LOG.md`

Truncated unified diff (root -> docs):

```
--- root/DEBUG_LOG.md
+++ docs/DEBUG_LOG.md
@@ -1,1104 +1,1478 @@
-# Debug Log

-

-Developer journal for tracking implementation progress, debugging sessions, and technical decisions.

+# Debug Log - Problem Solving History

+

+<!-- META

+Last_Updated: 2025-12-31T23:55:00Z

+Total_Issues: 75

+Format_Version: 2.0

+Auto_Generated: True

+Sources: CONSOLIDATED_DEBUG, archive/, fileorg-phase2-beta-release, BUILD-144, BUILD-145, BUILD-146-P6, BUILD-146-P12, BUILD-146-Phase-A-P13, BUILD-146-P17

+-->

+

+## INDEX (Chronological - Most Recent First)

+

+| Timestamp | DBG-ID | Severity | Summary | Status |

+|-----------|--------|----------|---------|--------|

+| 2026-01-01 | DBG-079 | LOW | BUILD-147 Phase A P11 - Test Infrastructure Hardening (100% Success): Fixed test suite infrastructure issues preventing proper validation of SOT runtime integration. **Problem**: All SOT memory indexing tests failing with two root causes - (1) `retrieve_context` return inconsistency: method initialized empty dict `results = {}` then conditionally added keys, causing `KeyError` when tests checked for `'sot' in results` (key only added when `include_sot=True AND settings.autopack_sot_retrieval_enabled`); (2) Settings singleton not reloading: tests used `patch.dict(os.environ)` to set flags but code imported global `settings` singleton before patches applied, tests created new `Settings()` instances that weren't used by production code. **Solution**: (1) Fixed return structure consistency in `memory_service.py:1279-1288` - changed from empty dict to pre-initialized dict with all 8 keys (`{"code": [], "summaries": [], "errors": [], "hints": [], "planning": [], "plan_changes": [], "decisions": [], "sot": []}`), ensures consistent structure regardless of which collections included; (2) Fixed test environment handling - added `importlib.reload(sys.modules["autopack.config"])` after `patch.dict(os.environ)` in 7 test functions (`test_index_sot_docs_enabled`, `test_search_sot`, `test_retrieve_context_with_sot_enabled`, `test_format_retrieved_context_includes_sot`, `test_index_sot_docs_with_explicit_docs_dir`, `test_index_sot_docs_fallback_to_default`, `test_all_6_sot_files_indexed`) to reload singleton settings object with patched environment variables. **Implementation**: Both fixes were simple and clean - return structure fix was 9-line change (adding dict initialization), test fixes were uniform pattern (4 lines import + reload before `MemoryService()` creation). Zero production code bugs, zero architectural issues, issue was purely test infrastructure setup. **Validation Results**: All 26 SOT memory indexing tests passing ✅ (7 chunking + 10 memory indexing + 4 JSON + 3 boundaries + 2 multi-project + 1 skip-existing + 1 6-file support). **Impact**: SOT runtime integration fully validated, test suite provides reliable safety net for future changes, opt-in design confirmed working (all features disabled by default). | ✅ Complete (Test Infrastructure Fix - 100% Success) |

+| 2025-12-31 | DBG-078 | LOW | BUILD-146 P17 Close-the-Gap - Zero Bugs (100% Success): Closed remaining production-readiness gaps with telemetry idempotency hardening, P1.3 test coverage completion, rollout infrastructure, and README drift fixes. **Problem**: Telemetry could record duplicate `TokenEfficiencyMetrics` rows across retries/crashes (no idempotency guard), P1.3 artifact features lacked comprehensive tests for safety rules (caps enforcement, SOT-only substitution, fallback behavior), production deployment lacked rollout guide and pre-deployment smoke test, README "Known Limitations" contained stale claims about missing telemetry wiring and P1.3 tests. **Solution**: (P17.1) Added idempotency check in `record_token_efficiency_metrics()` - queries for existing `(run_id, phase_id, phase_outcome)` record before insertion, returns existing record without duplication; created `TestTelemetryInvariants` suite with 7 tests validating idempotency, token category separation, graceful error handling. (P17.2) Created `TestP17SafetyAndFallback` suite with 9 tests: no substitution when disabled, SOT-only substitution (BUILD_HISTORY/BUILD_LOG allowed, regular files denied), history pack fallback when missing, max_tiers/max_phases caps strictly enforced, zero cap excludes all, no silent substitutions, recency ordering. (P17.3) Created `PRODUCTION_ROLLOUT_CHECKLIST.md` (500+ lines) with staged deployment guide (Stage 0 pre-prod → Stage 1 telemetry-only → Stage 2 history pack + SOT → Stage 3 full autonomy), environment variables matrix, database monitoring queries, kill switches, troubleshooting; created `smoke_autonomy_features.py` (250+ lines, no LLM calls) validating LLM keys, database connectivity, schema completeness, feature toggles, memory backend, GO/NO-GO verdict. (P17.4) Updated README removing stale limitations (telemetry wiring exists, P1.3 tests exist), added BUILD-146 P17 completion summary. **Implementation**: One minor test fix - schema default for embedding fields is `0` not `None` (line 757 test_embedding_cache_metrics_optional assertion updated from `is None` to `== 0`). All 53 tests passing on first run (22 token efficiency + 31 artifact history pack). Zero production code bugs, zero runtime errors, zero architectural rework needed. Achievement validates mature codebase design - production hardening integrates cleanly with comprehensive test coverage and documentation. Impact: Telemetry correctness guaranteed (1 row per terminal outcome even with retries), safety hardening complete (18 total tests), production deployment ready (staged rollout guide + smoke test), documentation accurate (README matches reality). | ✅ Complete (Clean Implementation - 100% First-Pass Success) |

+| 2025-12-31 | DBG-077 | LOW | BUILD-146 Phase A P13 Test Suite Stabilization - Targeted Fixes (100% Success): Fixed all 18 test failures revealed by Phase 5 auth consolidation through root cause analysis and targeted fixes. **Issue 1**: test_parallel_orchestrator.py (16 failures) - tests relied on removed `lock_manager`/`workspace_manager` instance attributes and `workspace_root` parameter that doesn't exist in ParallelRunConfig. **Fix**: Complete test rewrite (572 lines) - mocked WorkspaceManager/ExecutorLockManager at class level instead of instance attributes, changed all `workspace_root` → `worktree_base` parameter. Result: 13 passing, 3 xfail (aspirational WorkspaceManager integration tests). **Issue 2**: test_package_detector_integration.py - test created `req1.txt`/`req2.txt` which don't match glob pattern `requirements*.txt`. **Fix**: Renamed to `requirements-1.txt`/`requirements-2.txt` to match detection pattern. **Issue 3**: test_retrieval_triggers.py - pattern "investigate" doesn't match "investigation". **Fix**: Changed pattern from "investigate" to "investigat" (matches both forms). **Issue 4**: test_parallel_runs.py - Windows path assertion with forward vs backslashes. **Fix**: Added path normalization with `.replace(os.sep, "/")` and fixed assertion logic. **Extended Test Management**: Added `@pytest.mark.xfail` to 9 extended test suite files (114 tests total) instead of hiding via --ignore flags. Restored 2 high-signal tests (build_history_integrator, memory_service_extended) from quarantine to align with README North Star. Final result: 1393 passing, 0 failing, 117 xfailed, core CI green. All aspirational tests now visible with tracking reasons. Achievement: Complete test stabilization with 3 actual fixes + proper extended test tracking. | ✅ Complete (Targeted Fixes - 100% Success, Zero Debugging Required) |

+| 2025-12-31 | DBG-076 | LOW | BUILD-146 P12 API Consolidation - Zero Bugs (100% Success): Consolidated dual FastAPI control plane (backend.main:app + autopack.main:app) into single canonical server with zero debugging required. **Phase 0**: Documented canonical API contract (40+ endpoints) in CANONICAL_API_CONTRACT.md. **Phase 1**: Enhanced /health endpoint with database_identity hash (drift detection), kill_switches dict, qdrant status, version field; added /dashboard/runs/{run_id}/consolidated-metrics endpoint with kill switch AUTOPACK_ENABLE_CONSOLIDATED_METRICS (default OFF), pagination (max 10k), 4 independent token categories. **Phase 2**: Auth already canonical (X-API-Key primary, Bearer compatible) - no changes needed. **Phase 3**: Hard-deprecated backend.main:app with clear error message on direct execution, library imports still work. **Phase 4**: Created 15 contract tests (test_canonical_api_contract.py), CI drift detector (scripts/check_docs_drift.py) with 8 forbidden patterns. **Documentation Cleanup**: Fixed 7 files with outdated backend server references. All changes additive (backward compatible), kill switches default OFF, zero performance impact. Target end-state achieved: one canonical server (PYTHONPATH=src uvicorn autopack.main:app), no dual drift. Production ready. | ✅ Complete (Clean Implementation - 100% Success, Zero Bugs) |

+| 2025-12-31 | DBG-075 | LOW | BUILD-146 P12 Production Hardening - Clean Implementation (100% Success): Completed 5-task production hardening suite with 30/30 tests passing (100% success). **Task 1**: Rollout Playbook + Safety Rails created [STAGING_ROLLOUT.md](STAGING_ROLLOUT.md) (600+ lines), added kill switches to dashboard.py (AUTOPACK_ENABLE_CONSOLIDATED_METRICS defaults OFF), enhanced health.py with dependency checks (database + Qdrant), created 9 kill switch tests. **Task 2**: Pattern Expansion → PR Automation extended pattern_expansion.py with generate_pattern_detector(), generate_pattern_test(), generate_backlog_entry() functions; auto-generates code stubs from top 5 patterns (min 3 occurrences). **Task 3**: Data Quality + Performance Hardening added add_performance_indexes.py migration (10 indexes for phase_metrics, dashboard_events, llm_usage_events, token_efficiency_metrics, phase6_metrics), created 10 index tests, pagination max=10000. **Task 4**: A/B Results Persistence created ABTestResult model with strict validity enforcement (commit SHA + model hash must match), add_ab_test_results.py migration, ab_analysis.py script, /ab-results dashboard endpoint, 6 tests. **Task 5**: Replay Campaign created replay_campaign.py with async execution, clone_run() + execute_run() functions, 5 tests. **Issues Fixed**: Test failures due to Run model not having git_commit_sha/model_mapping_hash fields (stored in ABTestResult instead), Phase model requiring phase_index field, kill switch tests needing FastAPI app setup (simplified to env var logic tests). All kill switches default to OFF (opt-in), support SQLite + PostgreSQL, Windows compatible. Achievement: Production-ready hardening with zero breaking changes, 100% backward compatibility. | ✅ Complete (Clean Implementation - 100% Test Success) |

+| 2025-12-31 | DBG-074 | LOW | BUILD-146 P6 Integration - Minimal Issues (94% Success): Completed integration of True Autonomy features (Phases 0-5) into autonomous_executor hot-path with 132/140 tests passing (94%). **P6.1**: Plan Normalizer CLI added `--raw-plan-file` and `--enable-plan-normalization` flags (autonomous_executor.py:9600-9657), transforms unstructured plans to structured JSON at ingestion. **P6.2**: Intention Context integration injected ≤2KB semantic anchors into Builder prompts (4047-4073) and ≤512B reminders into Doctor prompts (3351-3361) via `AUTOPACK_ENABLE_INTENTION_CONTEXT` flag. **P6.3**: Failure Hardening positioned BEFORE diagnostics/Doctor (1960-2002), detects 6 patterns deterministically, saves ~12K tokens per mitigated failure via `AUTOPACK_ENABLE_FAILURE_HARDENING` flag. **P6.4**: Created scripts/run_parallel.py production CLI for bounded concurrent runs. **P6.5**: Integration tests created (6/14 passing validates hot-path), 8 failures due to API signature mismatches in test code (non-blocking). **P6.6**: Comprehensive README documentation added (292-433 lines). **P6.7**: Benchmark report created with token impact analysis (7.2M tokens/year savings @ 50% detection). **Issues**: None in production code - all failures in test code due to incorrect API expectations. All features opt-in via env flags, zero breaking changes, graceful degradation. Token impact: -12K/failure (hardening), +2KB/Builder +512B/Doctor (intention context). Achievement: Production-ready integration with 100% backward compatibility. | ✅ Complete (Clean Integration - 94% Test Success, 100% Production Success) |

+| 2025-12-31 | DBG-073 | LOW | BUILD-145 Deployment Hardening - Zero Bugs (Clean Implementation): Completed production deployment infrastructure (database migration, dashboard exposure, telemetry enrichment) with zero debugging required. All 29 tests passed on first run (100% success - 22 existing + 7 new dashboard tests). Fixed 2 trivial enum value errors in tests (RUNNING→PHASE_EXECUTION, DONE_COMPLETED→DONE_SUCCESS via sed) and 1 test fixture pattern alignment (StaticPool + dependency override from working pattern). **Database Migration**: Idempotent script adds 7 nullable columns (embedding_cache_hits/misses/calls_made/cap_value/fallback_reason, deliverables_count, context_files_total) with multi-DB support. **Dashboard Exposure**: Enhanced /dashboard/runs/{run_id}/status endpoint with optional token_efficiency field (aggregated stats + phase_outcome_counts breakdown), graceful error handling (try/except returns null on failures). **Telemetry Enrichment**: Extended TokenEfficiencyMetrics model with 7 new optional parameters for embedding cache and budgeting context observability, enhanced get_token_efficiency_stats() to include phase outcome breakdown. **Test Coverage**: Created test_dashboard_token_efficiency.py with 7 integration tests (no metrics, basic metrics, phase outcomes, enriched telemetry, backward compatibility, mixed modes, error handling) using in-memory SQLite. Backward compatible: nullable columns, optional fields, graceful degradation. Achievement: 95%→100% deployment-ready with minimal friction (2 sed commands + fixture refactor). | ✅ Complete (Clean Implementation - 100% First-Pass Success) |

+| 2025-12-31 | DBG-072 | LOW | BUILD-145 P1 Hardening - Zero Bugs (Clean Implementation): Completed minimum required hardening (kept-only telemetry, terminal outcome coverage, per-phase embedding reset, test coverage) with zero debugging required. All 28 tests passed on first run (100% success). Implementation leveraged existing infrastructure (BudgetSelection, scope_metadata, reset_embedding_cache function, best-effort telemetry pattern). No test failures, no runtime errors, no code rework needed - validates mature codebase design. Telemetry correctness fix prevents over-reporting (only counts kept files after budgeting), terminal outcome coverage makes failures visible (COMPLETE/FAILED/BLOCKED tracking), per-phase reset enforces true cap behavior (counter starts at 0 each phase). Backward compatible schema (phase_outcome nullable). Achievement: 95%→100% completion with zero friction. | ✅ Complete (Clean Implementation - 100% First-Pass Success) |

+| 2025-12-31 | DBG-071 | LOW | BUILD-145 P1.1/P1.2/P1.3 Token Efficiency Infrastructure - Minimal Issues (95% Success): Implemented three-phase token efficiency system with 20/21 tests passing (95% coverage). Phase A observability: 11/12 tests (1 skipped RunFileLayout setup), Phase B embedding cache: 9/9 tests (100%), Phase C artifact expansion: all methods implemented (no dedicated tests). Only issues: (1) Fixed embedding cap semantics (0=disabled not unlimited) with 1-line check, (2) Fixed test syntax error by removing orphaned code block, (3) Added missing context_budget_tokens config setting. Zero runtime errors, zero architectural rework needed - clean implementation validates mature codebase design. Implementation leveraged existing infrastructure (Pydantic, conservative token estimation, content hashing) for seamless integration. | ✅ Complete (Clean Implementation - 95% First-Pass Success) |

+| 2025-12-30 | DBG-070 | LOW | BUILD-145 Read-Only Context Parity - Zero Bugs (Clean Implementation): Implemented P0 schema normalization (API boundary validation) + P1 artifact-first context loading (token efficiency) + P0 safety hardening (rollback protected files) with zero debugging required. All components leveraged clean architecture (Pydantic validators, conservative token estimation matching context_budgeter, existing rollback infrastructure). All 59 tests passed on first run (20 schema + 19 artifact + 16 safety + 4 legacy API). No test failures, no runtime errors, no code rework needed. Schema validator fixed 3 test failures (empty path detection) via simple `if path:` check. Achievement validates mature codebase architecture - new features integrate cleanly when existing modules are well-designed. Token efficiency: artifact content 100-400 tokens vs full file 1000-5000 tokens = 50-80% reduction. Safety: .autonomous_runs/ protected, per-run savepoint retention, graceful fallbacks. | ✅ Complete (Clean Implementation - Zero Debug Needed) |

+| 2025-12-30 | DBG-069 | MEDIUM | BUILD-144 NULL Token Accounting Schema Drift: P0 elimination of heuristic token splits (40/60, 60/40, 70/30) introduced total-only recording (prompt_tokens=NULL, completion_tokens=NULL), but schema had nullable=False causing potential INSERT failures. Dashboard aggregation also crashed on NULL with TypeError (+= None). Fixed with schema migration to nullable=True, dashboard COALESCE handling (NULL→0), and comprehensive regression tests. | ✅ Complete (Schema + Dashboard NULL-Safety) |

+| 2025-12-30 | DBG-068 | LOW | BUILD-143 Dashboard Parity - Zero Bugs (Clean Implementation): Implemented all 5 dashboard endpoints from README spec drift analysis with zero debugging required. All endpoints leveraged existing infrastructure (run_progress.py, usage_recorder.py, model_router.py). All 9 integration tests passed on first run after removing pytest skip marker. No test failures, no runtime errors, no code rework needed. Achievement validates mature codebase architecture - new features integrate cleanly when existing modules are well-designed. | ✅ Complete (Clean Implementation - Zero Debug Needed) |

+| 2025-12-30 | DBG-067 | LOW | BUILD-142 production readiness: Added telemetry schema enhancement documentation, migration runbook, calibration coverage warnings, and CI drift prevention tests to complete BUILD-142 ideal state. No bugs encountered - pure documentation and safety infrastructure. | ✅ Complete (Documentation + CI Hardening) |

+| 2025-12-29 | DBG-066 | MEDIUM | Batch drain controller race condition: checked phase state immediately after subprocess completion before DB transaction committed, causing successful COMPLETE phases to be misreported as "failed" when state was still QUEUED. Also TOKEN_ESCALATION treated as permanent failure instead of retryable condition. | ✅ Resolved (Production Fix: TELEMETRY-V5) |

+| 2025-12-21 | DBG-065 | MEDIUM | Diagnostics parity test suite had 4 failures in handoff_bundler tests (test_index_json_structure, test_nested_directory_structure, test_binary_file_handling, test_regenerate_overwrites): missing 'version' field in index.json, glob() instead of rglob() prevented recursive artifact discovery, missing *.txt and *.bin patterns | ✅ Resolved (Manual Quality Fix: BUILD-106) |

+| 2025-12-21 | DBG-064 | HIGH | Diagnostics parity phases 1, 2, 4 risk same multi-file truncation/malformed-diff convergence failures as phases 3 & 5 (which needed BUILD-101 batching); each phase creates 3-4 deliverables (code + tests + docs) susceptible to patch truncation and manifest violations | ✅ Resolved (Manual System Fix: BUILD-105) |

+| 2025-12-21 | DBG-063 | HIGH | Executor ImportError when logging phase max attempts: tries to import non-existent `log_error` function from error_reporter.py (correct function is `report_error`), causing executor crash after phase exhausts retries | ✅ Resolved (Manual Hotfix: BUILD-104) |

+| 2025-12-21 | DBG-062 | MEDIUM | Research API router deliverables created but not integrated: router.py had absolute import causing circular dependency, __init__.py expected non-existent schema names, router not mounted in main.py | ✅ Resolved (Manual Integration: BUILD-103) |

+| 2025-12-20 | DBG-061 | LOW | Diagnostics parity Phase 3 & 5 completed successfully after BUILD-101 batching fix; marked as completion note (no new system bugs encountered) | ✅ Complete (Autonomous: BUILD-102) |

+| 2025-12-20 | DBG-060 | HIGH | Diagnostics followups Phase 3 & 5 failed repeatedly due to docs-batch markdown truncation (ellipsis placeholders triggering validator rejections); batching mechanism with fallback enabled convergence | ✅ Resolved (System Fix: BUILD-101) |

+| 2025-12-20 | DBG-059 | HIGH | Executor failed to start (ImportError: cannot import DiagnosticsAgent from autopack.diagnostics); diagnostics parity runs could not execute any phases | ✅ Resolved (Manual Hotfix: BUILD-100) |

+| 2025-12-20 | DBG-058 | HIGH | Diagnostics followups (deep-retrieval + iteration-loop) repeatedly failed after 5 attempts due to multi-file Builder patch truncation/malformed diffs and deliverables manifest violations (extra/missing files), blocking autonomous convergence | ✅ Resolved (Manual Hotfix: BUILD-099) |

+| 2025-12-20 | DBG-057 | HIGH | Diagnostics-deep-retrieval phase failed with TypeError "unsupported operand type(s) for -: 'NoneType' and 'int'" at autonomous_executor.py:3617 during truncation recovery - SQLAlchemy model .get() method doesn't support default values like dict.get() | ✅ Resolved (Manual Hotfix: BUILD-098) |

+| 2025-12-20 | DBG-056 | HIGH | Research-api-router retry-v2/v3 failed due to merge conflict markers (`<<<<<<< ours`) left in src/autopack/main.py from previous failed patch attempts, causing context mismatch errors and preventing convergence despite BUILD-096 fix | ✅ Resolved (Manual Hotfix: BUILD-097) |

+| 2025-12-20 | DBG-055 | HIGH | Research-api-router phase blocked by protected-path isolation: patch attempts to modify `src/autopack/main.py` for FastAPI router registration, but main.py not in ALLOWED_PATHS (narrower than diagnostics subtrees in BUILD-090) | ✅ Resolved (Manual Hotfix: BUILD-096) |

+| 2025-12-20 | DBG-054 | HIGH | Autonomous_executor.py had 3 duplicate copies of allowed_roots computation logic (lines 3474, 4300, 4678) with same bug as DBG-053; manifest gate rejected examples/ deliverables despite deliverables_validator.py being fixed in BUILD-094 | ✅ Resolved (Manual Hotfix: BUILD-095) |

+| 2025-12-20 | DBG-053 | HIGH | Deliverables validator incorrectly computed allowed_roots for file deliverables like `examples/market_research_example.md`, creating root `examples/market_research_example.md/` instead of `examples/`, causing false "outside allowed roots" failures for research-examples-and-docs phase | ✅ Resolved (Manual Hotfix: BUILD-094) |

+| 2025-12-20 | DBG-052 | MEDIUM | After fixing ImportError (DBG-051), phases 2-3 could not retry because `retry_attempt` counter was at 5/5 (MAX_RETRY_ATTEMPTS); reset counter to 0 to enable successful retry | ✅ Resolved (Manual DB Reset: BUILD-093) |

+| 2025-12-20 | DBG-051 | HIGH | LLM clients (OpenAI, Gemini, GLM) attempt to import missing `format_rules_for_prompt` and `format_hints_for_prompt` functions from learned_rules.py, causing ImportError and blocking Builder execution in all follow-up phases | ✅ Resolved (Manual Hotfix: BUILD-092) |

+| 2025-12-20 | DBG-050 | HIGH | Follow-up requirements YAML files contain invalid syntax: backtick-prefixed strings in feature lists cause YAML parser failures during run seeding, blocking `autopack-followups-v1` creation | ✅ Resolved (Manual Hotfix: BUILD-091) |

+| 2025-12-20 | DBG-049 | HIGH | Followups 1–3 (Diagnostics Parity) blocked by protected-path isolation because deliverables live under `src/autopack/diagnostics/` and `src/autopack/dashboard/` which were not allowlisted | ✅ Resolved (Manual Hotfix: BUILD-090) |

+| 2025-12-20 | DBG-048 | MEDIUM | Chunk 2B quality gate not met: missing `src/autopack/research/*` deliverables and insufficient unit test/coverage confirmation; implement modules + expand tests and verify ≥25 tests + ≥80% coverage | ✅ Resolved (Manual Quality Fix: BUILD-089) |

+| 2025-12-19 | DBG-047 | HIGH | Executor could incorrectly flip a resumable run to DONE_FAILED during best-effort run_summary writes after a single phase failure (retries still remaining) | ✅ Resolved (Manual Hotfix: BUILD-088) |

+| 2025-12-19 | DBG-046 | MEDIUM | Research requirements root mismatch + missing deps caused predictable churn; unify requirements to `src/autopack/research/*` and add preflight analyzer to catch blockers before execution | ✅ Resolved (Manual Tooling: BUILD-087) |

+| 2025-12-19 | DBG-045 | LOW | Runbook/capability report became stale after stabilization fixes; update docs and add explicit next-cursor takeover prompt to prevent protocol drift | ✅ Resolved (Manual Docs: BUILD-086) |

+| 2025-12-19 | DBG-044 | HIGH | Chunk 5 manifests may contain directory prefixes (ending in `/`); strict manifest enforcement treated created files under those prefixes as outside-manifest | ✅ Resolved (Manual Hotfixes: BUILD-085) |

+| 2025-12-19 | DBG-043 | HIGH | Chunk 5 uses directory deliverables (e.g., `tests/research/unit/`), but deliverables validator treated them as literal files causing deterministic failures | ✅ Resolved (Manual Hotfixes: BUILD-084) |

+| 2025-12-19 | DBG-042 | HIGH | Chunk 4 (`research-integration`) patches blocked by protected-path isolation because required deliverables are under `src/autopack/*` and safe subtrees weren’t allowlisted | ✅ Resolved (Manual Hotfixes: BUILD-083) |

+| 2025-12-19 | DBG-041 | HIGH | Requirements include annotated deliverable strings (e.g., `path (10+ tests)`), causing deterministic deliverables/manifest failures and exhausting retries for Chunk 4/5 | ✅ Resolved (Manual Hotfixes: BUILD-082) |

+| 2025-12-19 | DBG-040 | HIGH | Chunk 2B (`research-gatherers-web-compilation`) frequently fails patch apply due to truncated/unclosed-quote patches and occasional header-only new-file doc diffs when generating many deliverables at once | ✅ Resolved (Manual Hotfixes: BUILD-081) |

+| 2025-12-19 | DBG-039 | HIGH | Chunk 1A patches rejected because deliverables include `src/autopack/cli/commands/research.py` but `src/autopack/` is protected in project runs; allowlist/roots derivation over-expanded or blocked CLI | ✅ Resolved (Manual Hotfixes: BUILD-080) |

+| 2025-12-19 | DBG-038 | MEDIUM | Backend auditor_result endpoint still validated as BuilderResultRequest (missing `success`); executor POSTs fail with 422 causing noisy telemetry | ✅ Resolved (Manual Hotfixes: BUILD-079) |

+| 2025-12-19 | DBG-037 | HIGH | Chunk 0 patch output frequently truncated or emitted header-only new-file diffs (no ---/+++ or @@ hunks), causing git apply failures and direct-write fallback writing 0 files | ✅ Resolved (Manual Hotfixes: BUILD-078) |

+| 2025-12-19 | DBG-036 | MEDIUM | JSON auto-repair inserted +[] without a hunk header for new files; git apply ignored it leading to continued JSON corruption | ✅ Resolved (Manual Hotfixes: BUILD-077) |

+| 2025-12-19 | DBG-035 | MEDIUM | Diff extractor too strict on hunk headers (requires ,count); valid @@ -1 +1 @@ was treated malformed causing hunks to be dropped and patches to fail apply | ✅ Resolved (Manual Hotfixes: BUILD-076) |

+| 2025-12-19 | DBG-034 | MEDIUM | Chunk 0 repeatedly blocked by empty gold_set.json; implement safe auto-repair to minimal valid JSON [] before apply | ✅ Resolved (Manual Hotfixes: BUILD-075) |

+| 2025-12-19 | DBG-033 | MEDIUM | Chunk 0 gold_set.json frequently empty; harden deliverables contract + feedback to require non-empty valid JSON (allow []) | ✅ Resolved (Manual Hotfixes: BUILD-074) |

+| 2025-12-19 | DBG-030 | MEDIUM | Allowed-roots allowlist too narrow causes false manifest-gate failures when deliverables span multiple subtrees | ✅ Resolved (Manual Hotfixes: BUILD-071) |

+| 2025-12-19 | DBG-031 | MEDIUM | Backend rejects auditor_result payload with 422 due to schema mismatch | ✅ Resolved (Manual Hotfixes: BUILD-072) |

+| 2025-12-19 | DBG-032 | LOW | Memory summary warning: ci_success undefined when writing phase summary to memory | ✅ Resolved (Manual Hotfixes: BUILD-073) |

+| 2025-12-19 | DBG-029 | HIGH | Post-apply corruption from invalid JSON deliverable (gold_set.json); add pre-apply JSON deliverable validation to fail fast | ✅ Resolved (Manual Hotfixes: BUILD-070) |

+| 2025-12-19 | DBG-028 | HIGH | Patch apply blocked by default `src/autopack/` protection; explicitly allow `src/autopack/research/` for research deliverables | ✅ Resolved (Manual Hotfixes: BUILD-069) |

+| 2025-12-19 | DBG-027 | HIGH | GovernedApply default protection blocks research writes; need derived allowed_paths from deliverables when scope.paths absent | ✅ Resolved (Manual Hotfixes: BUILD-068) |

+| 2025-12-19 | DBG-026 | HIGH | Patch apply blocked by overly-broad protected_paths (`src/autopack/` protected) preventing research deliverables from being written | ✅ Resolved (Manual Hotfixes: BUILD-067) |

+| 2025-12-19 | DBG-025 | MEDIUM | Manifest gate passes but Builder still diverges; enforce manifest inside Builder prompt + validator (OUTSIDE-MANIFEST hard fail) | ✅ Resolved (Manual Hotfixes: BUILD-066) |

+| 2025-12-19 | DBG-024 | MEDIUM | Deliverables keep failing despite feedback; add manifest gate to force exact file-path commitment before patch generation | ✅ Resolved (Manual Hotfixes: BUILD-065) |

+| 2025-12-19 | DBG-023 | MEDIUM | Deliverables enforcement too permissive: near-miss outputs outside required roots (e.g. src/autopack/tracer_bullet.py) | ✅ Resolved (Manual Hotfixes: BUILD-064) |

+| 2025-12-19 | DBG-022 | HIGH | Provider fallback chain broken: OpenAI builder signature mismatch + OpenAI base_url/auth confusion; replanning hard-depends on Anthropic | ✅ Resolved (Manual Hotfixes: BUILD-063) |

+| 2025-12-19 | DBG-021 | HIGH | Anthropic “credit balance too low” causes repeated failures; Doctor also hard-defaults to Claude | ✅ Resolved (Manual Hotfixes: BUILD-062) |

+| 2025-12-19 | DBG-020 | HIGH | Executor incorrectly finalizes run as DONE_* after stopping due to max-iterations (run should remain resumable) | ✅ Resolved (Manual Hotfixes: BUILD-061) |

+| 2025-12-19 | DBG-019 | MEDIUM | Anthropic streaming can drop mid-response (incomplete chunked read) causing false phase failures | ✅ Resolved (Manual Hotfixes: BUILD-060) |

+| 2025-12-19 | DBG-018 | MEDIUM | Deliverables validator misplacement detection too weak for wrong-root patches (tracer_bullet/) | ✅ Resolved (Manual Hotfixes: BUILD-059) |

+| 2025-12-19 | DBG-017 | MEDIUM | Qdrant unreachable on localhost:6333 (no docker + compose missing qdrant) | ✅ Resolved (Manual Hotfixes: BUILD-058) |

+| 2025-12-19 | DBG-016 | LOW | Research runs: noisy Qdrant-fallback + missing consolidated journal logs; deliverables forbidden patterns not surfacing | ✅ Resolved (Manual Hotfixes: BUILD-057) |

+| 2025-12-19 | DBG-015 | LOW | Qdrant recovery re-ingest is manual/on-demand (not automatic) to avoid surprise indexing overhead | ✅ Documented (BUILD-056) |

+| 2025-12-19 | DBG-013 | MEDIUM | Qdrant not running caused memory disable; tier_id int/string mismatch; consolidated docs dropped events | ✅ Resolved (Manual Hotfixes: BUILD-055) |

+| 2025-12-19 | DBG-012 | MEDIUM | Windows executor startup noise + failures (lock PermissionError, missing /health, Unix-only diagnostics cmds) | ✅ Resolved (Manual Hotfixes: BUILD-054) |

+| 2025-12-19 | DBG-011 | MEDIUM | Backend API missing executor phase status route (`/update_status`) caused 404 spam | ✅ Resolved (Manual Hotfixes: BUILD-053) |

+| 2025-12-19 | DBG-010 | HIGH | Research System Chunk 0 Stuck: Skip-Loop Abort + Doctor Interference | ✅ Resolved (Manual Hotfixes: BUILD-051) |

+| 2025-12-17 | DBG-009 | HIGH | Multiple Executor Instances Causing Token Waste | ✅ Resolved (BUILD-048-T1) |

+| 2025-12-17 | DBG-008 | MEDIUM | API Contract Mismatch - Builder Result Submission | ✅ Resolved (Payload Fix) |

+| 2025-12-17 | DBG-007 | MEDIUM | BUILD-042 Token Limits Need Dynamic Escalation | ✅ Resolved (BUILD-046) |

+| 2025-12-17 | DBG-006 | MEDIUM | CI Test Failures Due to Classification Threshold Calibration | ✅ Resolved (BUILD-047) |

+| 2025-12-17 | DBG-005 | HIGH | Advanced Search Phase: max_tokens Truncation | ✅ Resolved (BUILD-042) |

+| 2025-12-17 | DBG-004 | HIGH | BUILD-042 Token Scaling Not Active in Running Executor | ✅ Resolved (Module Cache) |

+| 2025-12-17 | DBG-003 | CRITICAL | Executor Infinite Failure Loop | ✅ Resolved (BUILD-041) |

+| 2025-12-13 | DBG-001 | MEDIUM | Post-Tidy Verification Report | ✅ Resolved |

+| 2025-12-11 | DBG-002 | CRITICAL | Workspace Organization Issues - Root Cause Analysis | ✅ Resolved |

+

+## DEBUG ENTRIES (Reverse Chronological)

+

+### DBG-070 | 2025-12-30T23:00 | BUILD-145 Read-Only Context Parity - Clean Implementation

+**Severity**: LOW

+**Status**: ✅ Complete (Clean Implementation - Zero Debug Needed)

+

+**Context**:

+- BUILD-145 P0: Schema normalization for read_only_context at API boundary

+- BUILD-145 P1: Artifact-first context loading for token efficiency

+- BUILD-145 P0 Safety: Rollback manager production hardening

+- All components built on existing clean architecture with zero major issues

+

+**Symptoms**:

+- None (preventive implementation)

+- P0: API boundary lacked validation for read_only_context format (clients could send mixed string/dict)

+- P1: Context loading read full files even when concise artifacts existed in .autonomous_runs/

+- P0 Safety: Rollback needed protected file detection and per-run retention

+

+**Implementation Success**:

+1. **P0 Schema Normalization** (schemas.py:43-86):

+   - Added Pydantic field_validator to PhaseCreate.scope

+   - Normalizes read_only_context entries to canonical `{"path": "...", "reason": ""}` format

+   - Supports legacy string format `["path"]` and new dict format `[{"path": "...", "reason": "..."}]`

+   - Validates dict entries have non-empty 'path' (skips None/empty/missing)

+   - Test suite: 20 tests covering all edge cases (legacy, new, mixed, invalid entries)

+   - **Bug Fix**: Initial tests failed (3/20) - validator used `if "path" in entry:` which returns True for empty strings

+   - **Fix**: Changed to `if path:` which properly evaluates False for None/empty/missing

+   - **Result**: 20/20 tests passing ✅

+

+2. **P1 Artifact-First Context Loading** (artifact_loader.py, autonomous_executor.py):

+   - Created ArtifactLoader module (244 lines) with artifact resolution priority:

+     - Phase summaries (.autonomous_runs/{run_id}/phases/phase_*.md) - most specific

+     - Tier summaries (.autonomous_runs/{run_id}/tiers/tier_*.md) - broader scope

+     - Diagnostics (.autonomous_runs/{run_id}/diagnostics/*.json, handoff_*.md)

+     - Run summary (.autonomous_runs/{run_id}/run_summary.md) - last resort

+   - Smart substitution: only uses artifact if smaller than full file (token efficient)

+   - Conservative token estimation: 4 chars/token (matches context_budgeter.py)

+   - Integrated into autonomous_executor._load_scoped_context() (lines 7019-7227)

+   - Test suite: 19 tests covering resolution, token savings, fallback, error handling

+   - **Result**: 19/19 tests passing ✅, zero implementation issues

+

+3. **P0 Safety Hardening** (rollback_manager.py):

+   - Safe clean mode: detects protected files before git clean (.env, *.db, .autonomous_runs/, *.log)

+   - Per-run retention: keeps last N savepoints for audit (default: 3, configurable)

+   - Pattern matching: exact, glob (*.ext), directory (.autonomous_runs/), basename

+   - Test suite: 16 new safety tests + 24 existing rollback tests = 40 total

+   - **Result**: 40/40 tests passing ✅, zero implementation issues

+

+**Root Cause Analysis**:

+- **Why Zero Bugs?**: Clean architecture with well-defined interfaces

+  - Pydantic validators provide clean extension point for schema normalization

+  - Conservative token estimation (4 chars/token) already established in context_budgeter.py

+  - Rollback manager already existed with clean extension points for new features

+- **Minor Fix**: Schema validator `if "path" in entry:` → `if path:` (lines 68-72 in schemas.py)

+  - Required for empty string/None detection (3 test failures → all passing)

+

+**Token Efficiency Metrics**:

+- Artifact content: 100-400 tokens (phase/tier summaries)

+- Full file content: 1000-5000 tokens (typical source files)

+- Estimated savings: ~900 tokens per substituted file (50-80% reduction)

+- Conservative matching: only substitutes when artifact clearly references file path

+

+**Safety Guarantees**:

+- ✅ Read-only consumption (no writes to .autonomous_runs/)

+- ✅ Fallback to full file if no artifact found

+- ✅ Graceful error handling (artifact read errors → full file fallback)

+- ✅ .autonomous_runs/ confirmed protected by rollback manager (PROTECTED_PATTERNS)

+- ✅ Protected file detection prevents accidental deletion

+- ✅ Per-run savepoint retention provides audit trail

+

+**Test Coverage**: All 59 tests passing ✅

+- 20 tests: [test_schema_read_only_context_normalization.py](tests/test_schema_read_only_context_normalization.py)

+- 19 tests: [test_artifact_first_summaries.py](tests/autopack/test_artifact_first_summaries.py)

+- 16 tests: [test_rollback_safety_guardrails.py](tests/autopack/test_rollback_safety_guardrails.py)

+- 4 tests: [test_api_schema_scope_normalization.py](tests/test_api_schema_scope_normalization.py) (legacy API compatibility)

+

+**Achievement Significance**:

+- **Mature Codebase Validation**: Zero major debugging required demonstrates clean architecture

+- **Token Efficiency**: 50-80% reduction for read-only context (artifact summaries vs full files)

+- **Production Safety**: Protected file detection + per-run retention = production-grade rollback

+- **Backward Compatibility**: Legacy string format still supported (gradual migration)

+

+**Files Modified**:

+- src/autopack/schemas.py (+44 lines validator)

+- src/autopack/artifact_loader.py (NEW, 244 lines)

+- src/autopack/autonomous_executor.py (+208 lines artifact integration)

+- src/autopack/rollback_manager.py (+171 lines safety features)

+- tests/test_schema_read_only_context_normalization.py (NEW, 437 lines, 20 tests)

+- tests/autopack/test_artifact_first_summaries.py (NEW, 278 lines, 19 tests)

+- tests/autopack/test_rollback_safety_guardrails.py (NEW, 299 lines, 16 tests)

+

+**Lessons Learned**:

+- Clean architecture enables rapid feature development with minimal debugging

+- Conservative token estimation (matching existing patterns) prevents integration issues

+- Comprehensive test suites (59 tests) catch edge cases early

+- Pydantic validators provide clean extension points for schema normalization

 

 ---

 

-## 2026-01-01: BUILD-146 P17.x DB Idempotency Hardening (COMPLETE)

-

(diff truncated)
```

---

## Next steps
- For each divergent file: merge unique content into docs/ version, then delete the root copy.
- Suggested commands:
-   - git diff --no-index BUILD_HISTORY.md docs/BUILD_HISTORY.md
-   - git diff --no-index DEBUG_LOG.md docs/DEBUG_LOG.md
