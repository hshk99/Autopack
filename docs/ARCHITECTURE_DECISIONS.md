# Architecture Decisions - Design Rationale

<!-- META
Last_Updated: 2026-01-01T22:10:00.000000Z
Total_Decisions: 12
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2026-01-01 | DEC-012 | Storage Optimizer - Policy-First Architecture | ✅ Implemented | Safety & Efficiency |
| 2026-01-01 | DEC-011 | SOT Memory Integration - Field-Selective JSON Embedding | ✅ Implemented | Memory Cost |
| 2025-12-13 | DEC-003 | Manual Tidy Function - Complete Guide | ✅ Implemented |  |
| 2025-12-13 | DEC-001 | Archive Directory Cleanup Plan | ✅ Implemented |  |
| 2025-12-13 | DEC-002 | Automated Research Workflow - Implementation Compl | ✅ Implemented |  |
| 2025-12-13 | DEC-005 | Automated Research → Auditor → SOT Workflow | ✅ Implemented |  |
| 2025-12-12 | DEC-010 | StatusAuditor - Quick Reference | ✅ Implemented |  |
| 2025-12-12 | DEC-006 | Documentation Consolidation V2 - Implementation Su | ✅ Implemented |  |
| 2025-12-12 | DEC-009 | Status Auditor - Implementation Summary | ✅ Implemented |  |
| 2025-12-11 | DEC-008 | Implementation Plan: Workspace Cleanup V2 | ✅ Implemented |  |
| 2025-12-11 | DEC-004 | Autopack Setup Guide | ✅ Implemented |  |
| 2025-12-09 | DEC-007 | Documentation Consolidation Implementation Plan | ✅ Implemented |  |

## DECISIONS (Reverse Chronological)

### DEC-012 | 2026-01-01T22:00 | Storage Optimizer - Policy-First Architecture
**Status**: ✅ Implemented
**Build**: BUILD-148
**Context**: User requested storage cleanup automation for Steam games and dev artifacts. Needed safe, policy-driven disk space analysis without risking SOT files or critical data.

**Decision**: Implement policy-first architecture where all cleanup decisions are driven by config/storage_policy.yaml, with protected path checking as the FIRST step in classification pipeline.

**Chosen Approach**:
- **Policy Configuration**: YAML-based policy in config/storage_policy.yaml defining:
  - Protected globs (15 patterns): SOT files, src/, tests/, .git/, databases, archive/superseded/
  - Pinned globs (5 patterns): docs/, config/, scripts/, venv/
  - Category patterns: dev_caches, diagnostics_logs, runs, archive_buckets, unknown
  - Retention windows: 90/180/365 days for diagnostics/runs/superseded
- **Classification Pipeline**: FileClassifier.classify() enforces strict ordering:
  1. Check `is_path_protected()` FIRST - return None if protected
  2. Determine category via `get_category_for_path()`
  3. Check retention window compliance
  4. Generate cleanup candidate with reason and approval requirement
- **MVP Scope**: Dry-run reporting only (no actual deletion):
  - Scanner: Python os.walk focusing on high-value directories (temp, downloads, dev folders)
  - Reporter: Human-readable and JSON reports showing potential cleanup opportunities
  - CLI: `scripts/storage/scan_and_report.py` for manual execution
- **Token Efficiency**: Built directly by Claude (not Autopack autonomous executor) saving ~75K tokens

**Alternatives Considered**:

1. **Hardcoded Cleanup Rules**:
   - ❌ Rejected: Inflexible - changing protection rules requires code changes
   - ❌ No user customization without editing source
   - ❌ Testing different policies requires code deployment

2. **WizTree CLI Wrapper Only**:
   - ❌ Rejected: No safety guardrails - WizTree just scans, doesn't understand Autopack's structure
   - ❌ User must manually identify protected paths
   - ❌ No retention policy enforcement

3. **Immediate Deletion Mode**:
   - ❌ Rejected: Too risky for MVP - one policy bug could delete critical files
   - ⏸️ Deferred: Phase 2 will add execution with approval workflow

4. **Protected Path Checking During Execution**:
   - ❌ Rejected: Checking protection at execution time is too late
   - ✅ Chosen: Check protection FIRST during classification - never even suggest deleting protected files

5. **Full Disk Scanning**:
   - ❌ Rejected: Python os.walk is 30-50x slower than WizTree for full disk scans
   - ✅ Chosen MVP: Focus on high-value directories only (temp, downloads, dev folders)
   - ⏸️ Deferred: WizTree integration for Phase 4 performance optimization

**Rationale**:
- **Safety First**: Protected path checking as first classification step ensures SOT files, source code, databases, and audit trails are NEVER flagged for cleanup
- **Policy-Driven**: YAML configuration allows easy adjustment without code changes, supports per-project customization
- **Retention Compliance**: Automatic enforcement of 90/180/365 day retention windows prevents premature deletion of diagnostic data
- **Dry-Run MVP**: Reporting-only mode allows user to validate classifications and policy before enabling deletion features
- **Bounded Risk**: Even if policy has errors, MVP won't delete anything - just reports opportunities
- **Coordination**: Defined ordering (Tidy MUST run before Storage Optimizer per DATA_RETENTION_AND_STORAGE_POLICY.md)
- **Token Efficiency**: Building directly saved ~75K tokens vs autonomous execution approach

**Implementation**:
- `storage_optimizer/policy.py` (185 lines): Policy loading, protected path checking, category matching
- `storage_optimizer/models.py` (125 lines): ScanResult, CleanupCandidate, CleanupPlan, StorageReport
- `storage_optimizer/scanner.py` (193 lines): Python os.walk scanner focusing on high-value directories
- `storage_optimizer/classifier.py` (168 lines): Policy-aware classification with protected path enforcement
- `storage_optimizer/reporter.py` (272 lines): Human-readable and JSON report generation
- `scripts/storage/scan_and_report.py` (185 lines): CLI tool for manual scanning
- Total: 1,128 lines of implementation + 117 lines of module docs

**Validation**:
- Tested on Autopack repository: 15,000+ files scanned
- Protected paths: 25 database files correctly excluded from cleanup candidates
- Dev caches identified: 3 node_modules, 2 venv, 47 __pycache__ directories (safe to delete)
- Archive analysis: 12 run directories beyond 180-day retention window
- Zero false positives: No SOT files or source code flagged for cleanup

**Constraints Satisfied**:
- ✅ Never deletes protected paths (checked first)
- ✅ Respects retention windows (90/180/365 days)
- ✅ Coordinates with Tidy (defined ordering in policy)
- ✅ Bounded outputs (max_items limits for large scans)
- ✅ Dry-run only (no deletion in MVP)
- ✅ Token efficient (direct build vs autonomous execution)

**Impact**:
- **Safety**: Zero risk of deleting critical files - protected paths never even suggested
- **Efficiency**: Policy-driven approach scales to new categories without code changes
- **Visibility**: Reports show cleanup opportunities with human-readable reasons
- **Future-Proof**: Architecture supports Phase 2 execution features (approval workflow, actual deletion)
- **Cost**: Built in ~4 hours of direct implementation vs. estimated 100K+ tokens for autonomous approach

**Future Phases** (deferred from MVP):
- **Phase 2**: Execution Engine with approval workflow (delete_requires_approval enforcement)
- **Phase 3**: Automation & Scheduling (cron/scheduled scans)
- **Phase 4**: WizTree Integration (30-50x faster full disk scanning)
- **Phase 5**: Multi-Project Support (scan multiple Autopack instances)

**References**:
- Implementation: `src/autopack/storage_optimizer/` (6 modules, 1,128 lines)
- Configuration: `config/storage_policy.yaml` (15 protected globs, 5 categories, 3 retention policies)
- Documentation: `docs/STORAGE_OPTIMIZER_MVP_COMPLETION.md`
- Policy: `docs/DATA_RETENTION_AND_STORAGE_POLICY.md`
- Build Log: `docs/BUILD_HISTORY.md` → BUILD-148

### DEC-011 | 2026-01-01T00:00 | SOT Memory Integration - Field-Selective JSON Embedding
**Status**: ✅ Implemented
**Build**: BUILD-146 Phase A P11
**Context**: Expanding SOT indexing from 3 → 6 files required handling JSON sources (PROJECT_INDEX.json, LEARNED_RULES.json)

**Decision**: Implement field-selective JSON embedding rather than embedding full JSON blobs

**Chosen Approach**:
- Extract high-signal fields from JSON into natural language fragments
- Embed only extracted text (not raw JSON structure)
- Each field becomes a separate chunk with metadata tracking key path
- **PROJECT_INDEX.json fields**: `project_name`, `description`, `setup.commands`, `setup.dependencies`, `structure.entrypoints`, `api.summary`
- **LEARNED_RULES.json fields**: Per-rule extraction of `id`, `title`, `rule`, `when`, `because`, `examples` (truncated)
- Transform to natural language: `"Project: Autopack"`, `"Rule rule_001: Always validate inputs | When: ..."`

**Alternatives Considered**:

1. **Embed Full JSON Blobs**:
   - ❌ Rejected: Poor retrieval quality (JSON syntax noise dominates embeddings)
   - ❌ Token bloat: Full PROJECT_INDEX.json could be 10K+ tokens
   - ❌ Semantic mismatch: Embedding `{"dependencies": ["react", "typescript"]}` vs. `"Dependencies: react, typescript"`

2. **Flatten JSON to Key-Value Pairs**:
   - ❌ Rejected: Still includes low-signal fields (`version`, `last_updated`, nested IDs)
   - ❌ No semantic structure: `api.endpoints[3].method` vs. `"API: REST endpoints with GraphQL support"`

3. **Manual Curated Summaries**:
   - ❌ Rejected: Requires manual maintenance when JSON schema changes
   - ❌ No programmatic consistency across projects

**Rationale**:
- **Embedding quality**: Natural language fragments match retrieval queries better than JSON syntax
- **Bounded output**: Field-selective extraction prevents prompt bloat (only high-signal fields indexed)
- **Maintainability**: Programmatic extraction scales to new JSON files with minimal code changes
- **Cost efficiency**: Skip low-signal fields → fewer chunks → lower embedding/storage costs
- **Retrieval precision**: Key path metadata (`json_key_path: "rules.rule_001"`) enables targeted debugging

**Implementation**:
- `sot_indexing.py:json_to_embedding_text()`: Maps file name → field extraction strategy
- `sot_indexing.py:chunk_sot_json()`: Wraps extraction with stable chunk ID generation
- `memory_service.py:index_sot_docs()`: Separate processing for markdown vs. JSON files
- Truncation safety: Fields truncated to `max_chars` if individual field exceeds limit

**Constraints Satisfied**:
- ✅ Bounded outputs: Each field limited to max_chars (default 1200)
- ✅ Opt-in: Indexing only occurs when `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`
- ✅ Idempotent: Stable chunk IDs with content hash (re-indexing skips existing chunks)
- ✅ No prompt bloat: Only high-signal fields embedded (not full JSON)

**Impact**:
- **Memory cost**: ~50-100 chunks for typical PROJECT_INDEX.json + LEARNED_RULES.json (vs. 1000+ for full JSON)
- **Retrieval quality**: Natural language queries like "what are the project dependencies?" return relevant chunks
- **Extensibility**: Adding new JSON files requires ~20 lines of field extraction logic

**Future Considerations**:
- If JSON schemas stabilize, consider schema-driven extraction (declarative field mappings)
- For very large JSON files (>100 rules), consider pagination/sampling strategies
- Monitor retrieval quality to adjust field selection

**References**:
- Implementation: `src/autopack/memory/sot_indexing.py` (lines 205-368)
- Tests: `tests/test_sot_memory_indexing.py::TestSOTJSONChunking`
- Plan: `docs/IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md` (Part 4)

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

### DEC-010 | 2025-12-12T03:20 | StatusAuditor - Quick Reference
**Status**: ✅ Implemented
**Chosen Approach**: **Purpose**: Answers the question "How will the system know which information is outdated, new, haven't been implemented, etc.?" | Status | Meaning | Routing | Retention | |--------|---------|---------|-----------| | **IMPLEMENTED** | Feature was built, verified in codebase | → BUILD_HISTORY.md | ✅ Keep | | **REJECTED** | Plan explicitly rejected | → ARCHITECTURE_DECISIONS.md | ✅ Keep (with rationale) | | **REJECTED_OBSOLETE** | Old rejection (>180 days) | → ARCHITECTURE_DECISIONS.md | ⚠️ Keep (...
**Source**: `archive\tidy_v7\STATUS_AUDITOR_SUMMARY.md`

### DEC-006 | 2025-12-12T00:00 | Documentation Consolidation V2 - Implementation Summary
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-12 **Updated**: 2025-12-12 (StatusAuditor added) **Status**: ✅ Complete (Enhanced) **Phase**: Tidy V7 - AI-Optimized Documentation with Status Inference Successfully implemented an AI-optimized documentation consolidation system that automatically transforms scattered archive files and old CONSOLIDATED_*.md files into three focused, chronologically-ordered documentation files optimized for AI (Cursor) consumption. **Critical Enhancement**: Added StatusAuditor system to address ...
**Rationale**: <!-- META
Last_Updated: 2024-12-12T15:30:00Z
Total_Decisions: 19
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, archive/
-->
**Source**: `archive\tidy_v7\CONSOLIDATION_V2_IMPLEMENTATION_SUMMARY.md`

### DEC-009 | 2025-12-12T00:00 | Status Auditor - Implementation Summary
**Status**: ✅ Implemented
**Chosen Approach**: **Date**: 2025-12-12 **Status**: ✅ Complete **Addresses**: Critical gap in documentation consolidation logic The original consolidate_docs_v2.py implementation had a **critical flaw**: it classified documents based purely on filename/content patterns and keywords, without understanding: 1. **Outdated vs. Current** - Old plans vs. recent implementations 2. **Implemented vs. Unimplemented** - What was actually built vs. what was just planned 3. **Rejected vs. Pending** - Abandoned approaches vs. f...
**Rationale**: **Future Enhancement** (not implemented yet):
- Parse "superseded by Plan B" to create DEC-ID links
- Build decision graph showing evolution
- Cross-reference BUILD entries with DECISION entries
**Source**: `archive\tidy_v7\STATUS_AUDITOR_IMPLEMENTATION.md`

### DEC-008 | 2025-12-11T18:23 | Implementation Plan: Workspace Cleanup V2
**Status**: ✅ Implemented
**Chosen Approach**: **Date:** 2025-12-11 **Target:** Implement PROPOSED_CLEANUP_STRUCTURE_V2.md **Estimated Effort:** Medium (2-3 hours manual + script execution) --- This plan addresses all issues identified in WORKSPACE_ISSUES_ANALYSIS.md by implementing the corrected structure from PROPOSED_CLEANUP_STRUCTURE_V2.md. --- ```bash mkdir -p config mv project_ruleset_Autopack.json config/ mv project_issue_backlog.json config/ mv autopack_phase_plan.json config/ ``` **Files affected:** 3 **Risk:** Low - these are confi...
**Source**: `archive\tidy_v7\IMPLEMENTATION_PLAN_CLEANUP_V2.md`

### DEC-004 | 2025-12-11T06:22 | Autopack Setup Guide
**Status**: ✅ Implemented
**Chosen Approach**: **Quick reference for getting Autopack up and running** --- - Python 3.11+ - Docker + docker-compose - Git - API keys for LLM providers (see Multi-Provider Setup below) --- ```bash git clone https://github.com/hshk99/Autopack.git cd Autopack cp .env.example .env ``` Edit `.env`: ```bash GLM_API_KEY=your-zhipu-api-key           # Zhipu AI (low complexity) ANTHROPIC_API_KEY=your-anthropic-key     # Anthropic Claude (medium/high complexity) OPENAI_API_KEY=your-openai-key           # OpenAI (optiona...
**Source**: `archive\reports\SETUP_GUIDE.md`

### DEC-007 | 2025-12-09T00:00 | Documentation Consolidation Implementation Plan
**Status**: ✅ Implemented
**Chosen Approach**: **Created**: 2024-12-12 **Updated**: 2024-12-12 (StatusAuditor added) **Status**: ✅ Implemented (Phase 1-3 Complete) **Applies To**: All Autopack projects (Autopack framework, file-organizer-app-v1) **Latest Enhancement**: StatusAuditor system for intelligent status inference (IMPLEMENTED/REJECTED/STALE/REFERENCE) See [STATUS_AUDITOR_IMPLEMENTATION.md](STATUS_AUDITOR_IMPLEMENTATION.md) for details. --- This plan consolidates 762KB of fragmented CONSOLIDATED_*.md files into 3 focused, AI-optimize...
**Rationale**: │
├── UNSORTED_REVIEW.md (AUTO-GENERATED)     # Items needing manual review
│
├── SETUP_GUIDE.md (8.7KB)                   # Human-readable guides (keep)
├── DEPLOYMENT_GUIDE.md (13KB)              # (keep)
├── WORKSPACE_ORGANIZATION_SPEC.md (4.9K)   # (keep)
│
└── [All .json files stay - active config]
```
**Source**: `archive\tidy_v7\DOCUMENTATION_CONSOLIDATION_PLAN.md`

