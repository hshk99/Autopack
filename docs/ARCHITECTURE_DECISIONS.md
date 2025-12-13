# Architecture Decisions - Design Rationale

<!-- META
Last_Updated: 2025-12-13T15:00:00.000000Z
Total_Decisions: 4
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2025-12-13 | DEC-004 | Quota-Aware Multi-Provider LLM Routing | ⏭️ Pending Implementation | High |
| 2025-12-13 | DEC-003 | 6-File SOT Documentation Structure | ✅ Implemented | High |
| 2025-12-13 | DEC-002 | Automated Research → Auditor → SOT Workflow | ✅ Implemented |  |
| 2025-12-11 | DEC-001 | Autopack Setup Guide | ✅ Implemented |  |

## DECISIONS (Reverse Chronological)

### DEC-004 | 2025-12-13T00:00 | Quota-Aware Multi-Provider LLM Routing
**Status**: ⏭️ Pending Implementation
**Chosen Approach**: Intelligent routing across multiple LLM providers (Anthropic, OpenAI, Zhipu GLM) with quota tracking, automatic fallback, and fail-fast for high-risk categories
**Rationale**:
- **Problem**: Claude Max and other LLM subscriptions have weekly/daily token limits. Hitting limits mid-run blocks entire autonomous builds.
- **Solution**: Implement quota-aware routing with three-tier fallback:
  - **Tier 1 (Premium)**: Claude Opus 4.5 / Sonnet 4.5 for high/medium complexity
  - **Tier 2 (Efficient)**: GLM-4.6 for low complexity (92% cheaper than Sonnet)
  - **Tier 3 (Fallback)**: GLM-4.6 / Haiku when primary providers near quota limits
- **Key Features**:
  - Rolling window quota tracking (weekly/daily per provider)
  - Soft limit triggers (80% usage) for graceful degradation
  - High-risk categories (security, auth, schema) fail fast instead of silently downgrading
  - Aux agents can degrade to cheaper models without compromising core build quality
- **Benefits**:
  - Avoids ~10-20 blocked runs per year
  - Preserves premium quota for critical phases
  - Reduces cost by using GLM-4.6 ($0.70/1M) for safe low-complexity tasks
- **Implementation Status**: Configuration complete in `config/models.yaml`, tracking implementation pending
**Source**: `archive/research/QUOTA_AWARE_ROUTING.md`

### DEC-003 | 2025-12-13T00:00 | 6-File SOT Documentation Structure
**Status**: ✅ Implemented
**Chosen Approach**: Reduce from 10 SOT files to 6 standardized files for all projects
**Rationale**:
- **Problem**: 10 SOT files in docs/ made it difficult for AI (Cursor/Autopack) to quickly scan and understand project state. Many files contained overlapping or static information.
- **Solution**: Consolidated to 6 core files:
  1. **PROJECT_INDEX.json** - Machine-readable quick reference (setup, deployment, API, structure)
  2. **BUILD_HISTORY.md** - Implementation history (auto-updated by tidy)
  3. **DEBUG_LOG.md** - Troubleshooting log (auto-updated by tidy)
  4. **ARCHITECTURE_DECISIONS.md** - Design decisions (auto-updated by tidy)
  5. **FUTURE_PLAN.md** - Roadmap and backlog (manual planning)
  6. **LEARNED_RULES.json** - Auto-updated learned rules and strategies
- **Consolidations Made**:
  - DEPLOYMENT_GUIDE.md → PROJECT_INDEX.json (deployment section) + archive/reports/
  - SETUP_GUIDE.md → PROJECT_INDEX.json (setup section) + archive/reports/
  - WORKSPACE_ORGANIZATION_SPEC.md → PROJECT_INDEX.json (structure section) + archive/reports/
  - WHATS_LEFT_TO_BUILD_MAINTENANCE.md → FUTURE_PLAN.md (maintenance section)
  - CONSOLIDATED_RESEARCH.md → archive/research/
  - UNSORTED_REVIEW.md → Temporary file only (deleted after manual review)
- **Benefits**:
  - **Faster AI Scanning**: 6 files instead of 10
  - **Clear Hierarchy**: PROJECT_INDEX.json as single entry point
  - **JSON Format**: Machine-readable, faster parsing for AI agents
  - **Less Duplication**: Setup/deployment/workspace info in one place
  - **Better Archive Organization**: Static reference files moved to archive/
- **Multi-Project Support**: Same structure applied to all projects (Autopack, file-organizer-app-v1, etc.)
**Source**: `archive/reports/SOT_CONSOLIDATION_PROPOSAL.md`

### DEC-002 | 2025-12-13T00:00 | Automated Research → Auditor → SOT Workflow
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Fully automated pipeline from research gathering to SOT file consolidation **Status**: ✅ IMPLEMENTED **Date**: 2025-12-13 --- ``` Research Agents ↓ (gather info) archive/research/active/<project-name-date>/ ↓ (trigger planning) scripts/plan_hardening.py ↓ (Auditor analyzes) archive/research/reviewed/temp/<compiled-files> ↓ (discussion/refinement) archive/research/reviewed/{implemented,deferred,rejected}/ ↓ (automated consolidation) scripts/research/auto_consolidate_research.py ↓ (sm...
**Rationale**: - Complexity: Requires managing multiple OAuth providers (Google, GitHub, Microsoft)
- Current Value: Limited - most users ok with email/password
- Blocker: Need to establish user base first, then assess demand
**Source**: `archive\research\AUTOMATED_WORKFLOW_GUIDE.md`

### DEC-001 | 2025-12-11T06:22 | Autopack Setup Guide
**Status**: ✅ Implemented
**Chosen Approach**: **Quick reference for getting Autopack up and running** --- - Python 3.11+ - Docker + docker-compose - Git - API keys for LLM providers (see Multi-Provider Setup below) --- ```bash git clone https://github.com/hshk99/Autopack.git cd Autopack cp .env.example .env ``` Edit `.env`: ```bash GLM_API_KEY=your-zhipu-api-key           # Zhipu AI (low complexity) ANTHROPIC_API_KEY=your-anthropic-key     # Anthropic Claude (medium/high complexity) OPENAI_API_KEY=your-openai-key           # OpenAI (optiona...
**Source**: `archive\reports\SETUP_GUIDE.md`

