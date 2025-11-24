# Prompt for V7 Autonomous Build Playbook Architect - Integration Decisions

---

## Context

I have successfully implemented **all v7 architect recommendations** from your previous guidance:

✅ **GitAdapter abstraction layer** - Git operations now working in Docker
✅ **Stack profiles and feature catalog** - Curated approach for feature reuse
✅ **All validation probes passing** - 6/6 chunks validated
✅ **Docker deployment working** - Containers running with git support

**Repository:** https://github.com/hshk99/Autopack

---

## Current Status Summary

### What's Working ✅

1. **Complete v7 Playbook Implementation**
   - 19 API endpoints operational
   - Three-level issue tracking (phase → run → project)
   - Strategy engine with high-risk mappings
   - Git operations in Docker via GitAdapter
   - CI workflows and preflight gate
   - Metrics and observability

2. **Recent Completions**
   - GitAdapter Protocol + LocalGitCliAdapter implemented
   - Docker container has git installed and repository mounted
   - Stack profiles (5 curated technology stacks)
   - Feature catalog (15+ pre-whitelisted features)
   - External code treated as HIGH_RISK with strict governance

3. **Infrastructure Ready**
   - Docker Compose running (Postgres + FastAPI)
   - All state machines implemented (Run: 11 states, Tier: 5, Phase: 7)
   - File layout system operational
   - Budget controls and cost management

### What Needs Implementation 🔄

**CRITICAL:** Builder (Cursor) and Auditor (Codex) integration stubs need real AI implementation.

**Current status:** Integration framework exists but uses simulated responses.

**Files:**
- `integrations/cursor_integration.py` - Builder stub (simulated)
- `integrations/codex_integration.py` - Auditor stub (simulated)
- `integrations/supervisor.py` - Orchestration loop (ready)

---

## Files for Your Review

I'm providing these key files to help you make recommendations:

### Essential Files (Please review in this order):

1. **V7_ARCHITECT_RECOMMENDATIONS_IMPLEMENTED.md** - Complete status of your previous recommendations
2. **integrations/cursor_integration.py** - Current Builder stub implementation
3. **integrations/codex_integration.py** - Current Auditor stub implementation
4. **integrations/supervisor.py** - Orchestration loop
5. **INTEGRATION_GUIDE.md** - Integration architecture and patterns
6. **src/autopack/main.py** - API endpoints (especially Builder/Auditor endpoints)
7. **src/autopack/strategy_engine.py** - Budget and complexity mapping

### Supporting Files (for reference):

8. **config/stack_profiles.yaml** - Technology stacks
9. **config/feature_catalog.yaml** - Pre-whitelisted features
10. **src/autopack/git_adapter.py** - Git operations abstraction

---

## Key Questions for You

### Question 1: Builder (Cursor) Integration Approach

**Context:** The Builder needs to:
- Receive a phase specification (task_category, complexity, description)
- Write code to implement the phase
- Return a git patch/diff

**Current stub:** Simulates Cursor by returning fake diffs

**Options I'm considering:**

**A) Cursor Composer API Integration**
- Pros: Direct integration with Cursor's AI
- Cons: Need Cursor API access, documentation unclear
- Question: Does Cursor have a public API for this?

**B) File-based Prompt System**
- Write phase spec to `.autopack/pending_phase.json`
- Cursor watches file and executes
- Cursor writes result to `.autopack/phase_result.json`
- Supervisor reads result and extracts diff
- Pros: Simple, no API needed
- Cons: Manual Cursor intervention required

**C) VS Code Extension API**
- Build custom VS Code extension
- Extension coordinates between Autopack API and Cursor
- Pros: Full control, native integration
- Cons: Complex, requires extension development

**D) Claude API as Builder** (Alternative)
- Use Anthropic Claude API instead of Cursor
- Use Claude Code Generation with MCP for file ops
- Pros: Well-documented API, reliable
- Cons: Different from original Cursor vision

**Your recommendation:** Which approach best fits the v7 autonomous build vision?

---

### Question 2: Auditor (Codex) Integration Approach

**Context:** The Auditor needs to:
- Receive a git patch and phase specification
- Review code for issues (security, quality, tests, etc.)
- Return list of issues with severity (minor/major)

**Current stub:** Simulates Codex by returning fake issues

**Options I'm considering:**

**A) OpenAI GPT-4 API**
- Use OpenAI API directly
- Send patch + review prompt
- Parse structured response (JSON)
- Pros: Well-documented, reliable
- Cons: Cost per review

**B) Azure OpenAI**
- Same as A but via Azure
- Pros: Enterprise support, compliance
- Cons: Requires Azure setup

**C) Claude API as Auditor**
- Use Anthropic Claude for code review
- Pros: Strong code understanding, longer context
- Cons: Different from original Codex vision

**D) Local Model (Code Llama, etc.)**
- Run local model for code review
- Pros: No API costs, data privacy
- Cons: Slower, requires GPU

**Your recommendation:** Which Auditor approach best balances quality, cost, and v7 compliance?

---

### Question 3: Dynamic LLM Model Selection (My Proposal)

**Idea:** Instead of using one model for all tasks, dynamically select the best model based on task complexity.

**Proposed Mapping:**

```python
# From strategy_engine.py complexity levels
COMPLEXITY_TO_MODEL = {
    "low": {
        "builder": "gpt-3.5-turbo",      # Fast, cheap for simple tasks
        "auditor": "gpt-3.5-turbo"
    },
    "medium": {
        "builder": "gpt-4",               # Balanced
        "auditor": "gpt-4"
    },
    "high": {
        "builder": "gpt-4-turbo",         # Best quality for complex tasks
        "auditor": "gpt-4-turbo"
    }
}

# HIGH_RISK categories always get best models
if task_category in ["external_feature_reuse", "security_auth_change", ...]:
    use_model = "gpt-4-turbo"  # Override complexity
```

**Benefits:**
- Cost optimization (use cheap models for simple tasks)
- Quality optimization (use best models for complex/risky tasks)
- Budget alignment (model cost matches phase budget)

**Integration with v7:**
- Strategy engine already maps task_category → complexity
- Phase budgets (incident_token_cap) could include LLM costs
- High-risk categories automatically get best models

**Questions:**
1. Does this align with v7 budget control philosophy?
2. Should model selection be part of CategoryDefaults in StrategyEngine?
3. How should we track LLM costs vs token budgets?

**Your recommendation:** Should we implement dynamic model selection? How should it integrate with the strategy engine?

---

### Question 4: Integration Priority and Approach

**Given the current state, what's the best path forward?**

**Option A: Get Something Working Fast**
- Use OpenAI API for both Builder and Auditor (simplest)
- Replace stubs with real API calls
- Run first end-to-end autonomous build
- Iterate and improve
- Timeline: 1-2 days

**Option B: Build It Right**
- Research proper Cursor integration
- Implement clean separation of concerns
- Add model selection logic
- Full testing before first run
- Timeline: 1-2 weeks

**Option C: Hybrid Approach**
- Start with OpenAI API for both (quick win)
- Design abstraction layer for future Cursor integration
- Add model selection incrementally
- Timeline: 3-5 days

**Your recommendation:** Which approach best serves the v7 autonomous build goals?

---

### Question 5: Feature Catalog and Reuse Integration

**Context:** We have stack_profiles.yaml and feature_catalog.yaml implemented.

**How should the Builder use these during planning?**

**Scenario:** User requests "Build a FastAPI service with JWT auth"

**Should the Builder:**
1. Look up `stack_profiles.yaml` → find `web_fastapi_pg`
2. Check `feature_catalog.yaml` → find `jwt_authentication` feature
3. See feature points to `fastapi_users` repo (pre-whitelisted)
4. Decision: Reuse fastapi_users vs build from scratch?

**Questions:**
1. Should this be automatic (Builder decides) or manual (require approval)?
2. How does this integrate with the phase planning process?
3. Should there be a separate "Planning Phase" (Phase 0) for feature lookup?
4. How do budget calculations adjust for reuse (40-60% reduction)?

**Your recommendation:** How should feature catalog integration work in practice?

---

### Question 6: Testing and Validation Strategy

**Before running first autonomous build, what should be tested?**

**Current validation:**
- ✅ All 6 chunks validated via probes
- ✅ Model tests passing (6/6)
- ✅ Git operations tested in Docker
- ✅ API endpoints responding

**Missing validation:**
- ⏳ End-to-end Builder → Auditor → Apply workflow
- ⏳ Issue tracking with real issues
- ⏳ Budget exhaustion and retry logic
- ⏳ CI workflow trigger on patch apply

**Your recommendation:** What's the minimum testing needed before attempting first real autonomous build?

---

## Additional Context

### Budget Constraints

From strategy_engine.py, we have:

```python
# Run-level budgets
run_token_cap: 5_000_000 tokens
run_max_phases: 25 phases
run_max_duration_minutes: 120 minutes

# Phase-level budgets (varies by complexity)
low_complexity: 200_000 tokens
medium_complexity: 500_000 tokens
high_complexity: 1_000_000 tokens

# High-risk categories (external code, security, etc.)
incident_token_cap: 800_000 - 1_500_000 tokens
max_builder_attempts: 1-2
max_auditor_attempts: 2-3
```

**Question:** How do LLM API costs map to token budgets? Should we track:
- Input tokens (prompt) + Output tokens (response)?
- Model cost multipliers (GPT-4 costs more than GPT-3.5)?
- Separate budget for Builder vs Auditor?

---

## My Current Understanding

Based on v7 playbook implementation, here's what I believe should happen:

### Ideal Workflow (Per §8 of v7 playbook):

1. **Supervisor** creates run via `POST /runs/start`
2. **Planning** (future enhancement): Resolve stack profile, check feature catalog
3. **For each phase:**
   - **Builder** (Cursor/GPT-4):
     - Reads phase spec
     - Writes code
     - Submits patch via `POST /phases/{id}/builder_result`
   - **GitAdapter**: Applies patch to integration branch
   - **Auditor** (Codex/GPT-4):
     - Reviews patch
     - Finds issues
     - Submits via `POST /phases/{id}/auditor_result`
   - **If issues found**: Builder retries (up to max_builder_attempts)
   - **If clean**: Phase → COMPLETE, move to next
4. **Tier completion**: Check tier budgets, issue counts
5. **Run completion**: Promote if eligible, update project backlog

**Questions:**
1. Is this workflow correct per v7 vision?
2. Where does feature catalog lookup happen?
3. How does dynamic model selection fit in?

---

## What I Need From You

### Primary Request

**Recommendations for AI integration approach:**
1. Builder integration method (Cursor API, file-based, Claude API, etc.)
2. Auditor integration method (OpenAI, Azure, Claude, local)
3. Dynamic model selection strategy
4. Integration with feature catalog
5. Testing requirements before first build

### Secondary Request

**Architecture guidance:**
1. Should model selection be part of StrategyEngine?
2. How should LLM costs map to token budgets?
3. Should there be a Planning Phase (Phase 0)?
4. What's the minimal viable integration for first autonomous build?

### Tertiary Request

**Best practices:**
1. Error handling for LLM API failures
2. Retry logic for rate limits
3. Cost monitoring and alerts
4. Security considerations (API keys, etc.)

---

## Files Attached

1. V7_ARCHITECT_RECOMMENDATIONS_IMPLEMENTED.md
2. integrations/cursor_integration.py
3. integrations/codex_integration.py
4. integrations/supervisor.py
5. INTEGRATION_GUIDE.md
6. src/autopack/main.py (Builder/Auditor endpoints)
7. src/autopack/strategy_engine.py

---

## Thank You

The v7 playbook implementation is solid and all your previous recommendations have been implemented successfully. I'm confident that with your guidance on the AI integration approach, we can have a fully functional autonomous build system operational soon.

Looking forward to your architectural recommendations!

---

**Date:** 2025-11-24
**Status:** Awaiting integration architecture guidance
**Repository:** https://github.com/hshk99/Autopack
**Next Milestone:** First autonomous build with real AI integration
