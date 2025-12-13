# Architecture Decisions - Design Rationale

<!-- META
Last_Updated: 2025-12-13T11:09:02.375445Z
Total_Decisions: 19
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2025-12-13 | DEC-019 | Automated Research → Auditor → SOT Workflow | ✅ Implemented |  |
| 2025-12-11 | DEC-003 | Comprehensive Cleanup Plan | ✅ Implemented |  |
| 2025-12-11 | DEC-004 | Plan | ✅ Implemented |  |
| 2025-12-11 | DEC-005 | Autopack Tidy System - Comprehensive Technical Gui | ✅ Implemented |  |
| 2025-12-11 | DEC-009 | Directory Routing Update Summary | ✅ Implemented |  |
| 2025-12-09 | DEC-016 | Qdrant Setup - COMPLETE ✅ | ✅ Implemented |  |
| 2025-12-04 | DEC-015 | Universal Prompt: Submit GPT Response to Claude | ✅ Implemented |  |
| 2025-12-03 | DEC-006 | Claude's Report: Goal-Oriented Planning for Autopa | ✅ Implemented |  |
| 2025-12-02 | DEC-008 | Claude's Response to GPT's Analysis (GPT_RESPONSE1 | ✅ Implemented |  |
| 2025-12-02 | DEC-007 | Claude's Response to GPT's Analysis (GPT_RESPONSE1 | ✅ Implemented |  |
| 2025-12-02 | DEC-011 | Gpt Response17 | ✅ Implemented |  |
| 2025-12-02 | DEC-018 | Session Resume Summary | ✅ Implemented |  |
| 2025-12-01 | DEC-002 | Autopack Self Healing Plan | ✅ Implemented |  |
| 2025-11-28 | DEC-017 | Quick Start: Building a New Project with Autopack | ✅ Implemented |  |
| 2025-11-28 | DEC-014 | Project Initialization Automation | ✅ Implemented |  |
| 2025-11-28 | DEC-013 | GPT Strategic Analysis Template (Universal) | ✅ Implemented |  |
| 2025-11-28 | DEC-012 | GPT Review Prompt for MoAI-ADK Comparison Analysis | ✅ Implemented |  |
| 2025-11-28 | DEC-010 | Future Considerations Tracking | ✅ Implemented |  |
| 2025-11-26 | DEC-001 | chatbot_project Integration Analysis for Autopack | ✅ Implemented |  |

## DECISIONS (Reverse Chronological)

### DEC-019 | 2025-12-13T00:00 | Automated Research → Auditor → SOT Workflow
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Fully automated pipeline from research gathering to SOT file consolidation **Status**: ✅ IMPLEMENTED **Date**: 2025-12-13 --- ``` Research Agents ↓ (gather info) archive/research/active/<project-name-date>/ ↓ (trigger planning) scripts/plan_hardening.py ↓ (Auditor analyzes) archive/research/reviewed/temp/<compiled-files> ↓ (discussion/refinement) archive/research/reviewed/{implemented,deferred,rejected}/ ↓ (automated consolidation) scripts/research/auto_consolidate_research.py ↓ (sm...
**Rationale**: - Complexity: Requires managing multiple OAuth providers (Google, GitHub, Microsoft)
- Current Value: Limited - most users ok with email/password
- Blocker: Need to establish user base first, then assess demand
**Source**: `archive\research\AUTOMATED_WORKFLOW_GUIDE.md`

### DEC-003 | 2025-12-11T15:03 | Comprehensive Cleanup Plan
**Status**: ✅ Implemented
**Chosen Approach**: - ❌ `.cursor/` - Contains prompts that should be in archive/prompts/ - ❌ `logs/` - Contains archived runs that should be in archive/diagnostics/ - ❌ `planning/` - Contains kickoff_prompt.md that should be in archive/prompts/ - ❌ `templates/` - Contains phase templates that should be in archive/ or config/ - ❌ `integrations/` - Mix of active scripts and potentially outdated code - ❌ `docs/` - Contains MANY implementation plans/guides that should be in archive/, not truth sources **Current**: `C:\...
**Source**: `archive\plans\COMPREHENSIVE_CLEANUP_PLAN.md`

### DEC-004 | 2025-12-11T06:22 | Plan
**Status**: ✅ Implemented
**Chosen Approach**: Automate conversion of implementation plans (markdown) into Autopack phase specs that conform to `docs/phase_spec_schema.md`, so Autopack can ingest plans without manual reformatting. 1) Plan parser + schema mapper - Build a parser that ingests a markdown plan (headings/bullets) and extracts tasks into phase fields: id, description, complexity, task_category, acceptance_criteria, optional scope (paths/read_only_context), and safety flags. - Add heuristics/defaults for missing fields (e.g., compl...
**Source**: `archive\plans\plan.md`

### DEC-005 | 2025-12-11T00:00 | Autopack Tidy System - Comprehensive Technical Guide
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-11 **Version**: 0.5.1 **Classification Accuracy**: 98%+ --- 1. [Overview](#overview) 2. [System Architecture](#system-architecture) 3. [How to Use It](#how-to-use-it) 4. [Directory Designation & Scope](#directory-designation--scope) 5. [Execution Flow](#execution-flow) 6. [Core Scripts & Components](#core-scripts--components) 7. [Classification Algorithm](#classification-algorithm) 8. [Database Integration](#database-integration) 9. [Storage Destinations](#storage-destinations)...
**Source**: `archive\reports\AUTOPACK_TIDY_SYSTEM_COMPREHENSIVE_GUIDE.md`

### DEC-009 | 2025-12-11T00:00 | Directory Routing Update Summary
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-11 **Purpose**: Document updates to README and database schema for file organization and directory routing --- **Location**: `C:\dev\Autopack\README.md` **New Section Added**: "File Organization & Storage Structure" (lines 383-528) **Content Includes**: - 🗂️ **Directory Structure by Project** - Visual tree structure for Autopack core - Visual tree structure for File Organizer project - Shows NEW run organization: `.autonomous_runs/{project}/runs/{family}/{run-id}/` - 📝 **File C...
**Source**: `archive\reports\DIRECTORY_ROUTING_UPDATE_SUMMARY.md`

### DEC-016 | 2025-12-09T00:00 | Qdrant Setup - COMPLETE ✅
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-09 **Status**: OPERATIONAL Successfully set up Qdrant vector store for Autopack, following the pattern from the chatbot_project implementation. - **Transactional DB**: PostgreSQL (already default in [config.py:11](c:\dev\Autopack\src\autopack\config.py#L11)) - **Vector DB**: Qdrant (newly set as default in [memory.yaml](c:\dev\Autopack\config\memory.yaml)) - **Fallbacks**: SQLite (via explicit `DATABASE_URL` env var), FAISS (via `use_qdrant: false`) ```bash docker run -d -p 633...
**Source**: `archive\reports\QDRANT_SETUP_COMPLETE.md`

### DEC-015 | 2025-12-04T00:30 | Universal Prompt: Submit GPT Response to Claude
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Use this prompt to submit GPT Auditor's response back to Claude for implementation or follow-up discussion. --- ``` GPT Auditor has completed the review. Here is the response: [PASTE THE ENTIRE CONTENTS OF: archive/correspondence/GPT_RESPONSE_[ISSUE_NAME].md] Please: 1. Review GPT's analysis and recommendations 2. Identify what we should implement immediately vs defer 3. If GPT's analysis requires clarification or raises new questions, prepare a follow-up report 4. If ready to imple...
**Source**: `archive\reports\PROMPT_SUBMIT_GPT_RESPONSE.md`

### DEC-006 | 2025-12-03T00:55 | Claude's Report: Goal-Oriented Planning for Autopack
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: December 2, 2025 **Topic**: Should Autopack implement goal anchoring to prevent context drift during re-planning? **Requesting**: GPT's analysis and recommendations --- The user has raised a concern about **context drift** during Autopack's re-planning cycles. They reference a "goal-oriented planning" system used in another project (`chatbot_project`) that keeps the application tied to its goals during planning, re-planning, and troubleshooting. The core question is: **Does Autopack ne...
**Source**: `archive\reports\CLAUDE_REPORT_FOR_GPT_GOAL_ANCHORING.md`

### DEC-008 | 2025-12-02T22:31 | Claude's Response to GPT's Analysis (GPT_RESPONSE19)
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: December 2, 2025 **In response to**: GPT_RESPONSE19.md (GPT1 and GPT2 responses to Q1-Q4 and C1-C2) --- Both GPT responses provide clear, actionable guidance. I agree with the majority of recommendations, though there are some differences between GPT1 and GPT2 on Q3 and Q4 that need resolution. | Item | GPT's Recommendation | Status | |------|---------------------|--------| | Q1/C1: Data integrity recording | Use IssueTracker with category="data_integrity", record at phase level | ✅ Ag...
**Source**: `archive\reports\CLAUDE_RESPONSE19_TO_GPT.md`

### DEC-007 | 2025-12-02T21:32 | Claude's Response to GPT's Analysis (GPT_RESPONSE17)
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: December 2, 2025 **In response to**: GPT_RESPONSE17.md (GPT1 and GPT2 responses to Q1-Q6 and C1-C2) --- Both GPT responses provide clear, actionable guidance. I agree with the majority of recommendations, though there are some conflicts between GPT1 and GPT2 that need resolution. | Item | GPT's Recommendation | Status | |------|---------------------|--------| | Q3: HTTP status codes | Option A for now (422 for patch failures, 500 for system) | ✅ Agreed - GPT2's pragmatic approach | | Q...
**Source**: `archive\reports\CLAUDE_RESPONSE17_TO_GPT.md`

### DEC-011 | 2025-12-02T21:29 | Gpt Response17
**Status**: ✅ Implemented
**Chosen Approach**: GPT1'S RESPONSE Here are direct answers to Q1–Q6 and C1–C2. --- Given `main.py` lives in `src/autopack/main.py`, and `config.py` (or `config/__init__.py`) lives in the same `autopack` package, the correct pattern inside `main.py` is: ```python from .config import settings ``` This assumes: * You run the API as a module, e.g. `uvicorn src.autopack.main:app` (or equivalent), not `python src/autopack/main.py`. * `src` is your top-level “src layout” directory, and `autopack` is the actual package. I...
**Source**: `archive\reports\GPT_RESPONSE17.md`

### DEC-018 | 2025-12-02T19:44 | Session Resume Summary
**Status**: ✅ Implemented
**Chosen Approach**: From `ref2.md`, the last session ended with: - Test run `phase3-delegated-20251202-192817` failed with `WindowsPath / list` TypeError - Import error: `get_doctor_config` not found - API authentication issues (403 errors) **Fixed in:** `src/autopack/anthropic_clients.py` (3 locations) - Added safety checks to ensure `files`/`existing_files` is always a dict - Prevents TypeError when file_context is not in expected format **Fixed in:** `src/autopack/llm_service.py` - Changed import from `error_rec...
**Source**: `archive\reports\RESUME_SESSION_SUMMARY.md`

### DEC-002 | 2025-12-01T22:38 | Autopack Self Healing Plan
**Status**: ✅ Implemented
**Chosen Approach**: This document captures the implementation plan to make Autopack robustly self-heal and handle provider issues (GLM, Gemini, Claude, GPT‑5) while avoiding long failure loops. 1. **Centralize `.env` loading** - Add explicit `load_dotenv()` in `main.py` and `autonomous_executor.py` so all entrypoints load environment variables automatically. - Log presence/absence of critical vars: `OPENAI_API_KEY`, `GLM_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`. 2. **Provider health checks (T0 checks)** - Im...
**Source**: `archive\plans\AUTOPACK_SELF_HEALING_PLAN.md`

### DEC-017 | 2025-11-28T22:28 | Quick Start: Building a New Project with Autopack
**Status**: ✅ Implemented
**Chosen Approach**: **Last Updated**: 2025-11-26 --- Just say: **"I want to build [YOUR PROJECT IDEA]"** Autopack will automatically handle everything else. --- Tell Claude what you want to build. Include: - What it does - Key features - Target users - Constraints (if any) **Example**: ``` I want to build a context-aware file organizer desktop app that can automatically organize files, rename them contextually, understand file contents via OCR, and adapt to different use cases like legal case management. It should ...
**Source**: `archive\reports\QUICK_START_NEW_PROJECT.md`

### DEC-014 | 2025-11-28T22:28 | Project Initialization Automation
**Status**: ✅ Implemented
**Chosen Approach**: **Status**: ✅ Configured and Ready **Last Updated**: 2025-11-26 --- Autopack now automatically handles project initialization planning whenever you want to build something new. Simply describe your idea, and Autopack will: 1. ✅ Create build branch 2. ✅ Conduct extensive market research (web + GitHub) 3. ✅ Compile findings into reference files 4. ✅ Generate focused GPT strategic prompt 5. ✅ Set up project tracking structure **No extensive prompting needed** - just tell Claude what you want to bui...
**Source**: `archive\reports\PROJECT_INIT_AUTOMATION.md`

### DEC-013 | 2025-11-28T22:28 | GPT Strategic Analysis Template (Universal)
**Status**: ✅ Implemented
**Chosen Approach**: **Version**: 2.0 **Purpose**: Product-agnostic framework for GPT to provide rigorous strategic guidance **Last Updated**: 2025-11-27 --- You are receiving a **rigorous market research document** created using the `MARKET_RESEARCH_RIGOROUS_UNIVERSAL.md` template. Your role is to **validate the analysis** and provide **strategic guidance** that helps the founder decide: 1. **GO / CONDITIONAL GO / NO-GO** with clear scoring and justification 2. **Top 3 strategic imperatives** (if GO) 3. **Segment p...
**Source**: `archive\reports\GPT_STRATEGIC_ANALYSIS_UNIVERSAL.md`

### DEC-012 | 2025-11-28T22:28 | GPT Review Prompt for MoAI-ADK Comparison Analysis
**Status**: ✅ Implemented
**Chosen Approach**: I'm developing **Autopack v7**, an autonomous codebase building system using LLM agents (Builder + Auditor) in a supervisor loop with TDD workflow. A similar system called **MoAI-ADK** exists with a more mature architecture (35 agents, 135 skills, SPEC-First TDD). I've analyzed MoAI-ADK and created a detailed comparison report identifying patterns we could adopt. I need your second opinion on: 1. **Priority validation**: Are the HIGH/MEDIUM/LOW priorities correctly assigned? 2. **Implementation ...
**Source**: `archive\reports\GPT_REVIEW_PROMPT.md`

### DEC-010 | 2025-11-28T22:28 | Future Considerations Tracking
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: November 26, 2025 **Purpose**: Master list of items to be considered for future incorporation based on Autopack's runtime data --- This document tracks all features, optimizations, and enhancements that were discussed but deferred pending real-world data from Autopack's operation. Each item includes: - **What it is**: Brief description - **Why deferred**: Reason for not implementing immediately - **Data required**: What metrics/behavior we need to observe - **Decision criteria**: When/...
**Source**: `archive\reports\FUTURE_CONSIDERATIONS_TRACKING.md`

### DEC-001 | 2025-11-26T00:00 | chatbot_project Integration Analysis for Autopack
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-11-26 **Analysis Type**: Cross-codebase integration opportunities **Status**: Awaiting GPT review and recommendations --- After thorough exploration of both codebases, I've identified significant architectural overlap (60-70%) and numerous high-value integration opportunities. The chatbot_project is a **supervisor agent with persistent memory and governance**, while Autopack is a **self-improving autonomous build orchestrator**. Despite different primary purposes, they share subst...
**Source**: `archive\analysis\CHATBOT_PROJECT_INTEGRATION_ANALYSIS.md`

