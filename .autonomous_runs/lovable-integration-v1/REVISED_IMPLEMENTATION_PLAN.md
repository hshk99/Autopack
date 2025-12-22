# Revised Lovable Integration Implementation Plan

**Date:** 2025-12-22
**Based on:** GPT-5.2 Independent Validation + Clarifications
**Status:** Ready for Implementation

---

## Changes from Original Plan

### Critical Corrections

1. ✅ **SSE Streaming RESTORED** (was incorrectly removed)
2. ✅ **Architecture rebased** onto actual Autopack modules (not `file_manifest/`)
3. ✅ **Semantic embeddings enforced** (fail-closed if only hash available)
4. ✅ **Protected-path strategy defined** (narrow allowlist + scope_paths)
5. ✅ **Timeline adjusted** to 7-9 weeks realistic (was 5-6 aggressive)
6. ✅ **Browser telemetry ingestion added** (mini-phase enables P6/P7)
7. ✅ **Phase 5 Evidence Request downgraded** (not cancelled, re-scoped)

---

## Revised Phase Structure

### Phase 0: Foundation & Governance (Week 1)

**NEW - Critical prerequisites before any implementation**

#### 0.1 Protected-Path Strategy (2 days)

**Objective:** Enable safe modification of `src/autopack/` for Lovable patterns

**Implementation:**
- Create new subtree: `src/autopack/lovable/` for all new Lovable code
- Add to `ALLOWED_PATHS`: `src/autopack/lovable/`
- Add minimal existing files to `ALLOWED_PATHS`:
  - `src/autopack/context_selector.py`
  - `src/autopack/llm_service.py`
  - `src/autopack/autonomous_executor.py` (executor hook)
  - `src/autopack/governed_apply.py` (validation hook)
- Configure `scope_paths` per phase to restrict writes to planned files only

**Deliverables:**
- [ ] `src/autopack/lovable/` directory created
- [ ] `ALLOWED_PATHS` configuration updated
- [ ] `scope_paths` enforcement documented per phase
- [ ] Governance model documented in README

#### 0.2 Semantic Embedding Backend (2 days)

**Objective:** Ensure semantic embeddings available (fail-closed if not)

**Implementation:**
- Add sentence-transformers as **default semantic backend**
- Keep OpenAI embeddings as optional upgrade
- Add validation: fail Phase 1 startup if only hash embeddings available
- Update `src/autopack/memory/embeddings.py`:
  - Add sentence-transformers support
  - Add `validate_semantic_embeddings()` function
  - Fail-closed enforcement for Lovable features

**Deliverables:**
- [ ] sentence-transformers integration added
- [ ] `validate_semantic_embeddings()` implemented
- [ ] Phase 1 startup validation in place
- [ ] Documentation updated with embedding requirements

**Dependencies:**
```bash
pip install sentence-transformers torch
```

#### 0.3 Browser Telemetry Ingestion (Mini-Phase, 3 days)

**Objective:** Enable P6/P7 browser synergy patterns

**Phase 0: Manual Artifact (1 day)**
- Define artifact format: `.autonomous_runs/<run_id>/browser_telemetry.json`
- Schema:
```json
{
  "run_id": "lovable-integration-v1",
  "phase_id": "lovable-p2-hmr-error-detection",
  "ts": "2025-12-22T18:12:03Z",
  "source": "claude_chrome|manual|playwright",
  "type": "console_error|network_error|page_load",
  "message": "Cannot find module 'react'",
  "stack": "...optional...",
  "url": "http://localhost:3000/...",
  "extra": {}
}
```

**Phase 1: API Endpoint (2 days)**
- Add endpoint in `src/autopack/main.py`: `POST /api/browser/telemetry`
- Store events under `.autonomous_runs/<run_id>/browser/`
- Normalize all sources to canonical schema

**Deliverables:**
- [ ] Telemetry schema defined
- [ ] Manual artifact ingestion working
- [ ] API endpoint implemented
- [ ] Storage pipeline complete

---

### Phase 1: Core Precision (Weeks 2-4, 3 weeks + 1 week evaluation)

**Revised from 2-3 weeks to account for foundation work**

#### P1: Agentic File Search (4 days)

**Primary Module:** `src/autopack/lovable/agentic_search.py`

**Integration Points:**
- `src/autopack/memory/memory_service.py` (semantic retrieval)
- `src/autopack/memory/embeddings.py` (semantic backend)
- `src/autopack/context_selector.py` (add semantic candidate set step)

**Implementation:**
```python
# src/autopack/lovable/agentic_search.py
class AgenticSearch:
    def __init__(self, memory_service: MemoryService):
        self.memory = memory_service
        validate_semantic_embeddings()  # Fail-closed

    def search_relevant_files(self, query: str, max_files: int = 10) -> List[str]:
        # Use semantic embeddings to find relevant files
        candidates = self.memory.semantic_search(query, limit=max_files)
        # Write to run artifacts for audit
        return [c.file_path for c in candidates]
```

**Touchpoints (via ALLOWED_PATHS):**
- `src/autopack/context_selector.py`: Add optional semantic candidate set
- Gated by: `lovable_agentic_search=true`

**Validation:**
- Fail if only hash embeddings available
- Token reduction: 40%+ (50k → 30k target)
- Hallucination reduction: 50%+ (20% → 10% target)

#### P2: Intelligent File Selection (4 days)

**Primary Module:** `src/autopack/lovable/intelligent_file_selection.py`

**Integration Points:**
- `src/autopack/context_selector.py` (enhance `_rank_and_limit_context()`)

**Implementation:**
- Incorporate semantic relevance scores from P1
- Token-budget enforcement (already exists)
- Deterministic tie-breakers (recency/type priority)

**Touchpoints:**
- `src/autopack/context_selector.py._rank_and_limit_context()`

**Validation:**
- Token reduction: cumulative 60% (50k → 20k target)
- Patch success: 80%+ (from 75% baseline)

#### P3: Build Validation Pipeline (3 days)

**Primary Module:** `src/autopack/lovable/build_validation.py`

**Integration Points:**
- `src/autopack/governed_apply.py` (post-apply, pre-commit hook)

**Implementation:**
```python
# src/autopack/lovable/build_validation.py
class BuildValidator:
    def validate_pre_commit(self, applied_files: List[str]) -> ValidationResult:
        # Syntax checks (AST parsing)
        # Import checks (static analysis)
        # Optional: targeted test execution
        # Route failures to diagnostics artifacts
        pass
```

**Touchpoints:**
- `src/autopack/governed_apply.py`: Add validation hook
- Configurable: fast checks by default, full tests optional

**Validation:**
- Patch success: 90%+ (syntax errors caught pre-commit)
- Reduced rework: fewer failed patches

#### P4: Dynamic Retry Delays (3 days)

**Primary Module:** `src/autopack/lovable/retry_policy.py`

**Integration Points:**
- `src/autopack/llm_service.py` (or LLM client retry layer)

**Implementation:**
- Classify errors: rate_limit, timeout, transient, permanent
- Apply backoff based on category
- Integrate into existing retry layer

**Touchpoints:**
- LLM call retry layer (wherever retries currently happen)

**Validation:**
- Reduced API errors: 30%+
- Faster recovery from transient failures

#### Phase 1 Go/No-Go Evaluation (Week 5)

**Hard gate before Phase 2**

**Criteria:**
- Token reduction ≥40% (measured via `llm_usage_events` table)
- Patch success ≥85% (measured via run outcomes)
- No P0/P1 bugs in production runs
- Semantic embeddings confirmed working
- User feedback ≥4.0/5.0

**If PASS:** Proceed to Phase 2
**If FAIL:** Re-evaluate patterns, potentially stop project

---

### Phase 1.5: SSE Streaming (Week 6, 2-3 days)

**NEW - Restored based on GPT-5.2 finding**

**Objective:** Replace dashboard polling with push updates

**Scope (Option C - Start Narrow):**
- Run/phase state + progress
- Approval status changes (pending → approved/rejected/timeout)
- **Defer:** Full logs, diagnostics payloads (explode scope + security issues)

**Primary Module:** `src/autopack/lovable/sse_streaming.py`

**Integration Points:**
- `src/autopack/main.py` (add SSE endpoint)
- Dashboard: `src/autopack/dashboard/components/DiagnosticsSummary.tsx`

**Implementation:**
```python
# src/autopack/main.py
from fastapi.responses import StreamingResponse

@app.get("/api/sse/run/{run_id}/progress")
async def sse_run_progress(run_id: str):
    async def event_generator():
        while True:
            # Poll DB for run/phase state changes
            # Yield SSE events
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**Dashboard Integration:**
```typescript
// Replace polling with SSE
const eventSource = new EventSource(`/api/sse/run/${runId}/progress`);
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  setRunState(data);
};
```

**Validation:**
- Dashboard polling eliminated (5s → real-time)
- Reduced server load
- Improved UX responsiveness

---

### Phase 2: Quality + Browser Synergy (Weeks 7-9, 3 weeks)

**Revised from 2 weeks to account for browser integration complexity**

#### P5: Automatic Package Detection (3 days)

**Primary Module:** `src/autopack/lovable/package_detection.py`

**Integration Points:**
- Diagnostics pipeline (detect missing modules from tracebacks)

**Implementation:**
- Detect missing modules from import errors
- **Propose-first** (don't auto-install by default)
- Optional: auto-install with explicit approval

**Validation:**
- Import error reduction: 70%+ (15% → 5% target)

#### P6: HMR Error Detection (3 days)

**Primary Module:** `src/autopack/lovable/hmr_detector.py`

**Dependencies:**
- Phase 0.3 Browser Telemetry Ingestion

**Integration Points:**
- Browser telemetry consumer
- `DiagnosticsAgent` (classify HMR-specific failures)

**Implementation:**
```python
# src/autopack/lovable/hmr_detector.py
class HMRDetector:
    def classify_error(self, telemetry_event: dict) -> Optional[HMRError]:
        # Detect HMR reload loops
        # Detect Vite/Next overlay errors
        # Detect module resolution failures in dev server
        pass
```

**Validation:**
- HMR errors detected: >90% of console errors
- Faster debugging cycles

#### P7: Missing Import Auto-Fix (3 days)

**Primary Module:** `src/autopack/lovable/import_autofix.py`

**Dependencies:**
- Phase 0.3 Browser Telemetry Ingestion

**Integration Points:**
- Browser telemetry consumer
- `governed_apply.py` (scoped patch suggestions)

**Implementation:**
- Consume "missing module / missing symbol" from telemetry
- Generate scoped patch suggestions (limited to P1/P2 file set)
- Run through governed apply + build validation

**Validation:**
- Import fixes validated in browser: >80% success rate

#### P8: Conversation State Management (4 days)

**Primary Module:** `src/autopack/lovable/conversation_state.py`

**Integration Points:**
- DB (new table) or `.autonomous_runs/<run>/conversation_state.json`
- Prompt injection points

**Implementation:**
```python
# src/autopack/lovable/conversation_state.py
class ConversationState:
    def persist_state(self, run_id: str, phase_id: str, state: dict):
        # Save to DB or JSON artifact
        pass

    def load_state(self, run_id: str) -> dict:
        # Load previous state
        pass

    def inject_into_prompt(self, base_prompt: str, state: dict) -> str:
        # Feed summaries into prompts
        pass
```

**Validation:**
- Multi-turn intelligence improved
- Context retention across phases

#### P9: Fallback Chain Architecture (3 days)

**Primary Module:** `src/autopack/lovable/fallback_chain.py`

**Integration Points:**
- Model/provider routing (`model_router.py`)
- File read/write operations
- Diagnostics probes

**Implementation:**
- Standardize fallbacks (library-first, pure functions)
- Small adapters to avoid broad refactors

**Validation:**
- Resilience to failures improved
- Graceful degradation working

---

### Phase 3: Advanced Features (Weeks 10-11, 2 weeks)

**Revised from 1 week to account for Morph integration complexity**

#### P10: Morph Fast Apply (7 days)

**Primary Module:** `src/autopack/lovable/morph_fast_apply.py`

**Integration Points:**
- `src/autopack/governed_apply.py` (optional patch transformation)

**Implementation:**
- Optional transformation step before `apply_patch()`
- Privacy policy for code sent to Morph
- Strict fallback when Morph fails

**Hard Requirements:**
- Morph API subscription (~$100/month)
- Privacy/security approval
- Contractual assurances

**Validation:**
- Code preservation: 99% (surgical edits vs full rewrites)
- Easier review (smaller diffs)

#### P11: Comprehensive System Prompts (4 days)

**Primary Module:** `src/autopack/lovable/system_prompts.py` (or `config/system_prompts.yaml`)

**Integration Points:**
- `src/autopack/llm_service.py` (inject prompts per role)

**Implementation:**
- Consistent prompt injection per role (builder/auditor/doctor)
- Regression tests for prompt composition

**Validation:**
- Better instruction following
- Consistent quality
- Reduced hallucinations

#### P12: Context Truncation (3 days)

**Primary Module:** `src/autopack/lovable/context_truncation.py`

**Integration Points:**
- `src/autopack/context_selector.py` (aggressive truncation)

**Implementation:**
- Apply truncation only when:
  - Token budget exceeded
  - High confidence selected files cover required symbols
  - Safe fallback to current behavior

**Validation:**
- Additional 30% token savings (on top of P1/P2)
- Total: 60% token reduction (50k → 20k)

---

### Phase 4: Optimization (DEFERRED)

**Rationale:** Lower priority, can be added incrementally based on production metrics

**Deferred Patterns:**
- Lazy Manifest Loading
- AI Gateway with Fallback
- Comprehensive Logging Enhancements

---

## Revised Architecture Mapping

### Lovable Patterns → Autopack Modules

| Pattern | Lovable Reference | Autopack Implementation | Integration Point |
|---------|------------------|------------------------|-------------------|
| P1: Agentic Search | `file_manifest/agentic_search.py` | `lovable/agentic_search.py` | `ContextSelector` |
| P2: File Selection | `file_manifest/intelligent_file_selection.py` | `lovable/intelligent_file_selection.py` | `ContextSelector._rank_and_limit_context()` |
| P3: Build Validation | `patching/build_validator.py` | `lovable/build_validation.py` | `governed_apply.py` hook |
| P4: Retry Delays | `llm/retry_policy.py` | `lovable/retry_policy.py` | `llm_service.py` retry layer |
| P5: Package Detection | `diagnostics/package_detector.py` | `lovable/package_detection.py` | Diagnostics pipeline |
| P6: HMR Detection | `browser/hmr_detector.py` | `lovable/hmr_detector.py` | Browser telemetry + DiagnosticsAgent |
| P7: Import Auto-Fix | `browser/import_autofix.py` | `lovable/import_autofix.py` | Browser telemetry + governed_apply |
| P8: Conversation State | `state/conversation_state.py` | `lovable/conversation_state.py` | DB or JSON artifacts |
| P9: Fallback Chain | `core/fallback_chain.py` | `lovable/fallback_chain.py` | model_router + file ops |
| P10: Morph Fast Apply | `patching/morph_integrator.py` | `lovable/morph_fast_apply.py` | governed_apply pre-hook |
| P11: System Prompts | `prompts/system_prompts.yaml` | `lovable/system_prompts.py` | llm_service prompt injection |
| P12: Context Truncation | `file_manifest/context_truncator.py` | `lovable/context_truncation.py` | ContextSelector enhancement |
| P1.5: SSE Streaming | (new) | `lovable/sse_streaming.py` | main.py + dashboard |
| P0.3: Browser Telemetry | (new) | `lovable/browser_telemetry.py` | main.py endpoint + artifact storage |

---

## Revised Timeline

### Conservative (80% confidence): 11 weeks
- Phase 0: 1 week (foundation)
- Phase 1: 4 weeks (3 weeks impl + 1 week eval)
- Phase 1.5: 0.5 weeks (SSE)
- Phase 2: 3 weeks
- Phase 3: 2 weeks
- Buffer: 0.5 weeks

### Realistic (50% confidence): 9 weeks
- Phase 0: 1 week
- Phase 1: 3.5 weeks (3 weeks impl + 0.5 week eval)
- Phase 1.5: 0.5 weeks
- Phase 2: 2.5 weeks
- Phase 3: 1.5 weeks

### Aggressive (20% confidence): 7 weeks
- Phase 0: 0.5 weeks
- Phase 1: 3 weeks (2.5 weeks impl + 0.5 week eval)
- Phase 1.5: 0.5 weeks
- Phase 2: 2 weeks
- Phase 3: 1 week

**Recommended:** Plan for **9 weeks realistic**, communicate 11 weeks conservative to stakeholders.

---

## Revised Success Metrics

### Phase 1 (After Week 5)
- Token reduction ≥40% (50k → 30k)
- Patch success ≥85% (from 75%)
- Hallucination reduction ≥50% (20% → 10%)
- Semantic embeddings confirmed working

### Phase 2 (After Week 9)
- Import error reduction ≥70% (15% → 5%)
- Browser synergy: HMR errors detected >90%
- Import fixes validated >80% success rate
- SSE eliminates dashboard polling

### Phase 3 (After Week 11)
- Code preservation 99% (Morph)
- Total token reduction 60% (50k → 20k)
- Patch success 95%
- Execution time 50% faster (3min → 1.5min)

---

## Implementation Order (Critical Path)

1. **Week 1:** Phase 0 (Foundation)
   - 0.1 Protected-Path Strategy
   - 0.2 Semantic Embeddings
   - 0.3 Browser Telemetry Ingestion

2. **Weeks 2-4:** Phase 1 (Core Precision)
   - P1: Agentic Search
   - P2: Intelligent File Selection
   - P3: Build Validation
   - P4: Dynamic Retry Delays

3. **Week 5:** Phase 1 Evaluation (Hard Gate)

4. **Week 6:** Phase 1.5 (SSE Streaming)

5. **Weeks 7-9:** Phase 2 (Quality + Browser)
   - P5: Package Detection
   - P6: HMR Error Detection
   - P7: Missing Import Auto-Fix
   - P8: Conversation State
   - P9: Fallback Chain

6. **Weeks 10-11:** Phase 3 (Advanced)
   - P10: Morph Fast Apply
   - P11: System Prompts
   - P12: Context Truncation

---

## Risks & Mitigation (Updated)

### P0 Risks (Blocking)

1. **Semantic embeddings not configured**
   - Mitigation: Fail-closed validation at Phase 1 startup
   - sentence-transformers as default semantic backend

2. **Protected-path isolation**
   - Mitigation: `src/autopack/lovable/` subtree + narrow ALLOWED_PATHS
   - `scope_paths` enforcement per phase

3. **Browser telemetry not ingested**
   - Mitigation: Manual artifact format first, API endpoint second
   - Canonical schema defined up front

### P1 Risks (High Priority)

4. **Phase 1 doesn't hit go/no-go metrics**
   - Mitigation: Hard evaluation gate, re-evaluate if fail
   - Conservative metrics targets (85% patch success)

5. **Morph API privacy/reliability concerns**
   - Mitigation: Strict fallback, privacy policy, contractual assurances
   - Feature flag default-off

### P2 Risks (Medium Priority)

6. **Performance regressions from indexing**
   - Mitigation: Incremental indexing, caching, sampling-based re-embed

7. **Team capacity constraints**
   - Mitigation: Phased rollout, hard gates, option to stop after Phase 1

---

## Phase 5 Evidence Request (Re-Scoped)

**Original Decision:** CANCELLED (100% overlap with Claude Chrome)
**GPT-5.2 Finding:** Serves headless/asynchronous workflows (not just Chrome)
**Revised Decision:** DOWNGRADE + RE-SCOPE

**New Plan:**
- Minimal headless evidence request capability
- Integration with existing approval/Telegram channels
- Claude Chrome as optional "rich evidence provider"
- Effort: 2-3 days (lightweight)
- Priority: Phase 2 or deferred to Phase 4 based on demand

---

## Next Actions

1. ✅ **Accept GPT-5.2's recommendations** (COMPLETE)
2. ⏳ **Update run_config.json** with revised phases and timeline
3. ⏳ **Rewrite Phase 0, 1, 1.5 docs** with actual Autopack file paths
4. ⏳ **Create architecture mapping document** (Lovable → Autopack)
5. ⏳ **Update README.md** with revised timeline and scope
6. ⏳ **Commit all revisions** to git
7. ⏳ **Seek stakeholder approval** for 9-week realistic plan

---

**Status:** ✅ Ready for implementation
**Confidence:** 80% (matches GPT-5.2's GO WITH REVISIONS)
**Next Milestone:** Phase 0 Foundation (Week 1)

---

**Prepared By:** Claude Sonnet 4.5 (based on GPT-5.2 validation)
**Date:** 2025-12-22
**Version:** 2.0 (Revised Post-Validation)
