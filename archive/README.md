# Archive

This directory contains historical documentation and reference materials from the Autopack v7 implementation.

---

## Current Consolidated Documents

### [IMPLEMENTATION_HISTORY.md](IMPLEMENTATION_HISTORY.md)
Complete implementation history from v7 playbook to LLM integration to multi-project support.

**Contains key points from**:
- COMPLETION_SUMMARY.md
- IMPLEMENTATION_STATUS.md
- DEPLOYMENT_COMPLETE.md
- INTEGRATION_COMPLETE.md
- V7_ARCHITECT_RECOMMENDATIONS_IMPLEMENTED.md
- LLM_INTEGRATION_STATUS.md

**What's Inside**:
- Timeline (3 phases: v7 playbook, LLM integration, multi-project)
- V7 compliance matrix (12/12 sections)
- LLM integration architecture (protocols, OpenAI clients, model selection)
- Key technical achievements
- Testing results
- File structure evolution
- Metrics (code volume, documentation, test coverage)

### [GPT_CORRESPONDENCE.md](GPT_CORRESPONDENCE.md)
All GPT architect recommendations and our responses.

**Contains key points from**:
- gpt_response.md
- gpt_response2.md
- PROMPT_FOR_V7_GPT.md
- PROMPT_FOR_V7_GPT_INTEGRATION.md
- FILES_TO_SEND_TO_GPT.md
- PROGRESS_REPORT_FOR_V7_GPT.md

**What's Inside**:
- 8 key recommendations (Builder integration, Auditor integration, model selection, etc.)
- Implementation decisions made
- Questions & answers (mid-run adjustments, when system stops, etc.)
- Architecture slots added
- Direct quotes from GPT
- Status: All recommendations implemented

---

## Reference Specifications

### [autonomous_build_playbook_v7_consolidated.md](autonomous_build_playbook_v7_consolidated.md)
Original v7 autonomous build playbook specification (23KB).

**Key Sections**:
- §2: Supervisor roles and Builder/Auditor API contracts
- §3: Deterministic lifecycle (11-state run machine)
- §4: Phases, tiers, run scope
- §5: Three-level issue tracking
- §6: High-risk categories (5 categories)
- §7: Strategy engine and rulesets
- §8: Builder/Auditor modes
- §9: Cost controls and budgets
- §10: CI profiles (normal vs strict)
- §11: Observability and metrics
- §12: Implementation notes

**Use When**: Need to verify v7 compliance or understand original spec

### [cursor_chunk_prompts_v7.md](cursor_chunk_prompts_v7.md)
Implementation prompts for building v7 in 6 chunks (10KB).

**Chunks**:
- A: Core state machines
- B: Issue tracking
- C: Strategy engine
- D: Governed apply path
- E: CI workflows
- F: Observability

**Use When**: Need to understand chunk-by-chunk build approach

### [project_context_autopack.md](project_context_autopack.md)
Original project context and goals (7KB).

**Contains**:
- Project overview
- Core concepts
- Architecture decisions
- Technology stack

**Use When**: Need historical context on why decisions were made

---

## Superseded Guides (Consolidated into Current Docs)

These files are now superseded by current documentation in the root directory:

### NEXT_STEPS.md → Superseded by current README.md
- Old: Next steps after v7 completion
- Current: Up-to-date next steps in [README.md](../README.md)

### DEPLOYMENT_GUIDE.md → Superseded by Docker setup in README
- Old: Detailed deployment steps
- Current: Simplified deployment in [README.md](../README.md) + Docker Compose

### QUICK_START.md → Superseded by current quick start guides
- Old: Quick start for v7 playbook only
- Current: [QUICK_START_MULTI_PROJECT.md](../QUICK_START_MULTI_PROJECT.md)

---

## File Inventory

### Consolidated (2 files - READ THESE)
- ✅ **IMPLEMENTATION_HISTORY.md** - Complete implementation history
- ✅ **GPT_CORRESPONDENCE.md** - GPT recommendations and Q&A

### Reference Specs (3 files - Keep for reference)
- 📚 **autonomous_build_playbook_v7_consolidated.md** - V7 specification
- 📚 **cursor_chunk_prompts_v7.md** - Implementation prompts
- 📚 **project_context_autopack.md** - Project context

### Superseded (3 files - Kept for historical record)
- 🗂️ **NEXT_STEPS.md** - Old next steps
- 🗂️ **DEPLOYMENT_GUIDE.md** - Old deployment guide
- 🗂️ **QUICK_START.md** - Old quick start

**Total**: 8 files (down from 19)

---

## Current Documentation (Root Directory)

For up-to-date documentation, see:
- [README.md](../README.md) - Project overview and setup
- [SETUP_OPENAI_KEY.md](../SETUP_OPENAI_KEY.md) - OpenAI API key setup
- [QUICK_START_MULTI_PROJECT.md](../QUICK_START_MULTI_PROJECT.md) - Multi-project quick start
- [MULTI_PROJECT_SETUP.md](../MULTI_PROJECT_SETUP.md) - Detailed multi-project setup
- [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) - Builder/Auditor integration
- [SUMMARY_FOR_USER.md](../SUMMARY_FOR_USER.md) - Current implementation summary

---

## When to Use Archive Files

**Use IMPLEMENTATION_HISTORY.md when**:
- Need to understand what was built and when
- Looking for specific technical decisions and rationale
- Want to see timeline of features
- Need metrics on code/docs volume

**Use GPT_CORRESPONDENCE.md when**:
- Need to understand why we chose OpenAI over Cursor
- Want to see GPT architect's original recommendations
- Looking for guidance on feature catalog or planning phase
- Need answers to specific Q&A (mid-run adjustments, etc.)

**Use Reference Specs when**:
- Need to verify v7 compliance
- Want to understand original playbook design
- Looking for specific section references (§2, §3, etc.)
- Need chunk-by-chunk implementation approach

**Use Superseded Guides when**:
- Need historical context on old workflows
- Comparing old vs new approaches
- Archive/audit purposes only

---

**Last Updated**: 2025-11-24
**Status**: Archive consolidated and organized
**Maintenance**: Update when major implementation milestones occur
