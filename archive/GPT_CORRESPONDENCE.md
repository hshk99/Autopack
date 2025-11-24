# GPT Architect Correspondence

**Consolidated from**: gpt_response.md, gpt_response2.md, PROMPT_FOR_V7_GPT.md, PROMPT_FOR_V7_GPT_INTEGRATION.md, FILES_TO_SEND_TO_GPT.md, PROGRESS_REPORT_FOR_V7_GPT.md

---

## Key Recommendations Summary

### 1. Builder Integration (Response 2)
**Question**: Cursor API, file-based, or Claude API?

**Recommendation**: **Option D - Direct OpenAI API**
- Treat Builder as "LLM + tools", not "Cursor"
- Use OpenAI API with clean abstraction (BuilderClient protocol)
- Keep Cursor as local interactive dev environment only

**Architecture**:
```
BuilderClient
  -> ModelSelector (picks model based on complexity)
  -> OpenAI API (GPT-4.1, o4-mini, Codex family)
  -> Returns structured patch (unified diff)
```

**Why**:
- Cleanest architecture (no vendor lock-in)
- Easier to abstract and test
- OpenAI GPT 4.1/Codex family designed for long-horizon coding tasks
- Can add CursorCloudBuilderClient later if needed

### 2. Auditor Integration (Response 2)
**Question**: OpenAI, Azure, Claude, or local model?

**Recommendation**: **OpenAI GPT-4.1 (Option A)**
- Mature, well-documented, stable
- Easy JSON schema outputs for structured issues
- Good fit with budget + complexity model

**Architecture**:
```
AuditorClient
  -> ModelSelector
  -> OpenAI API (gpt-4.1 or gpt-4.1-turbo)
  -> Returns structured issues (severity, category, evidence)
```

**Future Enhancement**: Dual reviews with Claude on HIGH_RISK phases

### 3. Dynamic Model Selection (Response 2)
**Question**: Should we implement it? How does it fit with StrategyEngine?

**Recommendation**: **Yes, implement in StrategyEngine**

**Pattern**:
```yaml
# config/models.yaml - Part of CategoryDefaults
category_defaults:
  feature_scaffolding:
    complexity: medium
    builder_model:
      low: gpt-4.1-mini
      medium: gpt-4.1
      high: gpt-4.1
    auditor_model:
      low: gpt-4.1-mini
      medium: gpt-4.1
      high: gpt-4.1

  external_feature_reuse:  # HIGH_RISK
    complexity: high
    builder_model:
      any: gpt-4.1-turbo  # Always best model
    auditor_model:
      any: gpt-4.1-turbo
```

**Benefits**:
- Cheap models for simple tasks (40-80% cost savings)
- Best models for complex/risky tasks (quality)
- Aligns perfectly with v7 budget control philosophy

### 4. Token Budget Mapping (Response 2)
**Question**: How do LLM costs map to token budgets?

**Recommendation**:
1. Keep budgets in **tokens**, not dollars
   - `incident_token_cap` per phase
   - `run_token_cap` per run
2. Maintain price table in `config/pricing.yaml`
3. For each LLM call:
   - Pass `max_tokens` bound from remaining cap
   - Record `prompt_tokens` + `completion_tokens` from API
   - Update: `phase.tokens_used`, `tier.tokens_used`, `run.tokens_used`
4. Optionally derive cost: `cost = total_tokens * price_per_token(model)`
5. If cap exceeded: mark phase budget exhausted, transition to `DONE_FAILED_BUDGET_EXHAUSTED`

**Budget Tracking**: Single phase cap, but track builder vs auditor tokens separately in metrics

### 5. Integration Path (Response 2)
**Question**: Quick win (Option A), build right (Option B), or hybrid (Option C)?

**Recommendation**: **Option C - Hybrid Approach**

**Steps** (3-5 days):
1. Define abstractions (1 day)
   - BuilderClient, AuditorClient, ModelSelector protocols
   - Document in INTEGRATION_GUIDE.md
2. Implement OpenAI clients minimally (1-2 days)
   - Single API call per Builder/Auditor
   - JSON schema outputs
   - No advanced tool calling yet
3. Wire into integrations/supervisor.py
   - Replace stubs with real clients
   - Keep orchestration untouched
4. Run end-to-end build on toy repo
   - Prove state machine works with live LLMs
5. Iterate toward production

**Why**: Gives real autonomy quickly without locking into fragile decisions

### 6. Feature Catalog Integration (Response 2)
**Question**: How should Builder use stack_profiles.yaml and feature_catalog.yaml?

**Recommendation**: **Planning Phase 0**

**Workflow**:
1. User provides `comprehensive_plan.md` + project type
2. Autopack planning endpoint:
   - Parses plan into structured requirements
   - Calls Feature Lookup Service:
     - Selects stack from `stack_profiles.yaml`
     - Finds features from `feature_catalog.yaml`
   - Writes:
     - `feature_requirements.json`
     - `feature_lookup_plan_{run_id}.md`
     - Enriched phases with `task_category = external_feature_reuse`
3. PHASE_QUEUEING creates reuse + normal build phases

**Decision Model**:
- **Automatic**: For whitelisted repos in feature_catalog.yaml
- **Manual**: For out-of-catalog sources (add to catalog first)

**Budget Impact**:
- Reuse phases: Lower token budgets (40-60% reduction)
- But: HIGH_RISK for CI (strict profile, always audit)

### 7. Testing Requirements (Response 2)
**Question**: What's minimum testing before first autonomous build?

**Recommendation**: **5-Test Minimum**

1. **Unit Tests**: BuilderClient/AuditorClient with tiny inputs
   - Validate schema compliance, token tracking, error handling
2. **Integration Test**: Single phase run on toy repo
   - QUEUED → EXECUTING → COMPLETE flow
   - Integration branch commit, CI trigger
3. **Integration Test**: Failing phase
   - Issues file written, retry logic, caps respected
   - Final state: DONE_FAILED_* with incident pack
4. **Budget Exhaustion Test**: Mock high token usage
   - Run stops at run_token_cap
   - Budget failure recorded
5. **Smoke Test**: Real CI workflow trigger
   - GitHub Actions executes preflight_gate.sh
   - Autopack sees CI status

**After these pass**: Ready for limited autonomous build on non-critical project

### 8. Git Operations in Docker (Response 1)
**Question**: Does adding git to Docker violate v7 playbook?

**Recommendation**: **Option 1 - Add Git to Docker**
- Add git to Dockerfile
- Mount repository and .git directory
- Maintains v7 governed apply path (§8)
- Minimal code changes

**Why**: Maintains architecture integrity, enables integration branches

---

## Implementation Decisions Made

Based on GPT architect recommendations, we implemented:

### ✅ Implemented (Nov 24)

1. **Direct OpenAI API Integration**
   - Created `src/autopack/llm_client.py` with BuilderClient/AuditorClient protocols
   - Created `src/autopack/openai_clients.py` with OpenAI implementations
   - No Cursor Cloud Agents dependency

2. **Dynamic Model Selection**
   - Implemented `ModelSelector` class in llm_client.py
   - Created `config/models.yaml` with complexity mappings
   - HIGH_RISK categories always get best models (gpt-4-turbo)

3. **Token Budget Tracking**
   - Created `config/pricing.yaml` with per-model pricing
   - Token tracking in BuilderResult/AuditorResult
   - Cost calculation formulas ready

4. **Hybrid Integration Approach**
   - Clean abstractions first (protocols)
   - Minimal OpenAI implementation
   - Ready to iterate after first build

5. **Git in Docker**
   - Added git to Dockerfile
   - Mounted .git directory in docker-compose.yml
   - All 19 endpoints now functional

### ⏳ Pending (Future Work)

1. **Planning Phase 0** (Feature Lookup)
   - Not yet implemented
   - Will add when ready to integrate feature_catalog.yaml
   - Low priority for first autonomous build

2. **Testing Suite**
   - Unit tests for LLM clients
   - Integration tests (single phase, failing phase, budget exhaustion)
   - CI smoke test
   - Ready to write after first manual build succeeds

3. **Dual Auditor (Claude)**
   - Future enhancement for HIGH_RISK phases
   - Not needed for MVP

4. **Advanced Tool Calling**
   - Current: Single API call per Builder/Auditor
   - Future: Multi-step loops, file operations, test runs
   - Will add based on real-world needs

---

## Key Questions & Answers

### Q1: Mid-Run Plan Adjustments
**Question**: Can I chat with Builder during run to amend plan?

**Answer**: No, v7 is zero-intervention by design. To change plan:
1. Stop current run (or let it complete)
2. Revise comprehensive_plan.md
3. Start new run with revised plan

### Q2: When System Stops
**Question**: Does it stop at each tier/phase?

**Answer**: No, fully autonomous within run scope:
- Run continues until: all phases complete, budget exhausted, or critical failure
- No human intervention required between phases/tiers
- Review results after run completes

### Q3: Feature Catalog Workflow
**Question**: How does Planning Phase 0 work with chatbot?

**Answer**: Two-phase approach:
1. **Planning (human-in-loop)**: User + chatbot create comprehensive_plan.md
   - Ask questions, clarify requirements
   - Look up GitHub repos, evaluate options
   - Decide stack profile and reusable features
2. **Execution (zero-intervention)**: Autopack runs autonomous build
   - No chatbot during build
   - Uses plan + feature catalog
   - Fully automated

### Q4: Multi-Project Isolation
**Question**: How to prevent code mixing between projects?

**Answer**: Use `target_repo_path` parameter:
```python
supervisor = Supervisor(
    target_repo_path="c:\\Projects\\my-app"
)
```
Each project gets:
- Own directory (outside Autopack)
- Own git repo
- Own .autonomous_runs/ tracking
- No code mixing

---

## Architecture Slots Added (Per GPT)

### 1. Core Abstractions
- ✅ `ModelSelector` (StrategyEngine side)
- ✅ `BuilderClient` (integration layer)
- ✅ `AuditorClient` (integration layer)

### 2. Configuration Files
- ✅ `config/models.yaml` - Category/complexity → model mapping
- ✅ `config/pricing.yaml` - Per-token prices for cost metrics

### 3. Planning Phase 0 (Future)
- ⏳ API endpoints for feature lookup
- ⏳ `feature_requirements.json`
- ⏳ `feature_lookup_plan_{run_id}.md`

### 4. Metrics Wiring
- ✅ Tokens used (builder vs auditor)
- ✅ Costs calculation
- ⏳ Failure reasons tracking
- ⏳ Budget hit metrics

---

## Direct Quotes from GPT

### On Builder Integration
> "Treat Builder as 'LLM + tools', not 'Cursor'. Use direct OpenAI API for now (Option D), with a clean abstraction."

### On Integration Path
> "The biggest risk is never actually running a real build because you over design the integration."

### On Model Selection
> "Do not hard code model names in integrations. Put them in StrategyEngine / CategoryDefaults."

### On Feature Catalog
> "Automatic within the constraints of the catalog. If a feature is in feature_catalog.yaml and its source repo is whitelisted, the system may auto choose 'reuse with adaptation'."

### On Testing
> "Once these pass on a toy repo, you can try a real, but limited autonomous build on a non-critical project."

---

## Files Referenced

For detailed original correspondence:
- Original questions: `PROMPT_FOR_V7_GPT_INTEGRATION.md` (archived)
- GPT Response 1: `gpt_response.md` (archived)
- GPT Response 2: `gpt_response2.md` (archived)
- Progress report: `PROGRESS_REPORT_FOR_V7_GPT.md` (archived)

For current implementation:
- Setup guide: `../SETUP_OPENAI_KEY.md`
- Integration guide: `../INTEGRATION_GUIDE.md`
- Multi-project: `../QUICK_START_MULTI_PROJECT.md`

---

**Last Updated**: 2025-11-24
**Status**: All key recommendations implemented
**Next**: Run first autonomous build on toy repo
