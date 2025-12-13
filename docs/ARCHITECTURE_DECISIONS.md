# Architecture Decisions - Design Rationale

<!-- META
Last_Updated: 2025-12-13T18:25:58.814554Z
Total_Decisions: 5
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2025-12-13 | DEC-003 | Manual Tidy Function - Complete Guide | ✅ Implemented |  |
| 2025-12-13 | DEC-001 | Archive Directory Cleanup Plan | ✅ Implemented |  |
| 2025-12-13 | DEC-002 | Automated Research Workflow - Implementation Compl | ✅ Implemented |  |
| 2025-12-13 | DEC-005 | Automated Research → Auditor → SOT Workflow | ✅ Implemented |  |
| 2025-12-11 | DEC-004 | Autopack Setup Guide | ✅ Implemented |  |

## DECISIONS (Reverse Chronological)

### DEC-003 | 2025-12-13T09:51 | Manual Tidy Function - Complete Guide
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Reusable manual tidy-up function that works on ANY directory within Autopack workspace **Supports**: ALL file types (.md, .py, .log, .json, .yaml, .txt, .csv, .sql, and more) **Mode**: Manual (on-demand) - NOT automatic --- ```bash python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --dry-run python scripts/tidy/unified_tidy_directory.py <directory> --docs-only --execute python scripts/tidy/unified_tidy_directory.py <directory> --full --dry-run python scripts/tidy/...
**Source**: `archive\reports\MANUAL_TIDY_FUNCTION_GUIDE.md`

### DEC-001 | 2025-12-13T00:00 | Archive Directory Cleanup Plan
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-13 **Status**: READY TO EXECUTE **Commit**: 4f95c6a5 (post-tidy) --- All 225 .md files from archive/ have been successfully consolidated into SOT files: - ✅ docs/BUILD_HISTORY.md - 97 entries - ✅ docs/DEBUG_LOG.md - 17 entries - ✅ docs/ARCHITECTURE_DECISIONS.md - 19 entries - ✅ docs/UNSORTED_REVIEW.md - 41 items (manual review needed) **Safe to delete**: All .md files in archive/ (except excluded directories) --- **Why**: Contains active prompt templates for agents **Files**: 2...
**Source**: `archive\reports\ARCHIVE_CLEANUP_PLAN.md`

### DEC-002 | 2025-12-13T00:00 | Automated Research Workflow - Implementation Complete
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-13 **Status**: ✅ READY TO USE --- You asked: > "Each research agents gathers info and creates file in active folder, then when we trigger 'scripts/plan_hardening.py' for us to tidy up those research files and analyse, then compiled files will be generated in reviewed folder. Then with discussion, information will move between 'deferred', 'implemented', or 'rejected'. **All of this gotta be automatically sorted.**" **Fully automated pipeline** from research gathering to SOT file...
**Rationale**: Complexity vs. value analysis - not needed for MVP...
**Source**: `archive\reports\AUTOMATED_RESEARCH_WORKFLOW_SUMMARY.md`

### DEC-005 | 2025-12-13T00:00 | Automated Research → Auditor → SOT Workflow
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Fully automated pipeline from research gathering to SOT file consolidation **Status**: ✅ IMPLEMENTED **Date**: 2025-12-13 --- ``` Research Agents ↓ (gather info) archive/research/active/<project-name-date>/ ↓ (trigger planning) scripts/plan_hardening.py ↓ (Auditor analyzes) archive/research/reviewed/temp/<compiled-files> ↓ (discussion/refinement) archive/research/reviewed/{implemented,deferred,rejected}/ ↓ (automated consolidation) scripts/research/auto_consolidate_research.py ↓ (sm...
**Rationale**: - Complexity: Requires managing multiple OAuth providers (Google, GitHub, Microsoft)
- Current Value: Limited - most users ok with email/password
- Blocker: Need to establish user base first, then assess demand
**Source**: `archive\research\AUTOMATED_WORKFLOW_GUIDE.md`

### DEC-004 | 2025-12-11T06:22 | Autopack Setup Guide
**Status**: ✅ Implemented
**Chosen Approach**: **Quick reference for getting Autopack up and running** --- - Python 3.11+ - Docker + docker-compose - Git - API keys for LLM providers (see Multi-Provider Setup below) --- ```bash git clone https://github.com/hshk99/Autopack.git cd Autopack cp .env.example .env ``` Edit `.env`: ```bash GLM_API_KEY=your-zhipu-api-key           # Zhipu AI (low complexity) ANTHROPIC_API_KEY=your-anthropic-key     # Anthropic Claude (medium/high complexity) OPENAI_API_KEY=your-openai-key           # OpenAI (optiona...
**Source**: `archive\reports\SETUP_GUIDE.md`

