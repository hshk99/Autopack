# Architecture Decisions - Design Rationale

<!-- META
Last_Updated: 2026-01-02T14:45:00.000000Z
Total_Decisions: 15
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/, BUILD-153
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2026-01-02 | DEC-016 | Storage Optimizer - Protection Policy Unification | ✅ Implemented | Safety & Maintainability |
| 2026-01-02 | DEC-015 | Storage Optimizer - Delta Reporting Architecture | ✅ Implemented | Performance & Usability |
| 2026-01-02 | DEC-013 | Storage Optimizer Intelligence - Zero-Token Pattern Learning | ✅ Implemented | Automation & Cost |
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

### DEC-016 | 2026-01-02T14:30 | Storage Optimizer - Protection Policy Unification
**Status**: ✅ Implemented
**Build**: BUILD-153 Phase 4
**Context**: After BUILD-152 execution safeguards, needed unified protection policy shared by both Tidy System and Storage Optimizer. Before this, both systems had separate protection definitions leading to potential policy drift.

**Decision**: Implement single YAML source of truth (`config/protection_and_retention_policy.yaml`) with system-specific override sections, rather than duplicating protection rules across both systems.

**Chosen Approach**:
- **Centralized Policy File**: Single YAML defining protections, retention windows, category policies, and system overrides
  - **5 Main Sections**:
    1. Protected Paths (15 categories): SOT docs, source code, databases, VCS, config, audit trails, active state
    2. Retention Policies (4 windows): short-term (30 days), medium-term (90 days), long-term (180 days), permanent
    3. Category-Specific Policies: dev_caches, diagnostics_logs, runs, archive_buckets (with execution limits)
    4. System-Specific Overrides: Tidy vs Storage Optimizer behaviors from shared policy
    5. Database Retention (future): Disabled placeholder for BUILD-154+ database cleanup
- **Protection Coverage**:
  - Source code: `src/**`, `tests/**`, `**/*.py/js/ts`
  - SOT core: PROJECT_INDEX, BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS, FUTURE_PLAN, LEARNED_RULES, CHANGELOG
  - Databases: `*.db`, `*.sqlite`, autopack.db, fileorganizer.db, telemetry_*.db
  - Audit trails: archive/superseded/**, checkpoints/**, execution.log
  - VCS: .git/**, .github/**
- **System Overrides**:
  - Tidy: `respect_sot_markers: true` (don't consolidate `<!-- SOT_SUMMARY_START/END -->`), `skip_readme: true`
  - Storage Optimizer: `analyze_protected: true` (can scan for size reporting), `delete_protected: false` (NEVER delete)

**Alternatives Considered**:

1. **Duplicated Protection Rules** (status quo):
   - ❌ Rejected: Policy drift risk - Tidy and Storage Optimizer protect different paths over time
   - ❌ Maintenance burden: Changes require updating 2+ locations
   - ❌ No consistency guarantee: Easy to forget updating one system

2. **Hardcoded Shared Constants**:
   - ❌ Rejected: Still requires code changes for policy updates
   - ❌ No user customization without editing source
   - ❌ Python module import required for both systems

3. **Database-Stored Policy**:
   - ❌ Rejected: Overkill for configuration data (YAML sufficient)
   - ❌ Requires migration for policy changes
   - ❌ Less transparent than file-based config

4. **Separate YAML Files with Cross-References**:
   - ❌ Rejected: More complex than single file
   - ❌ Still has policy drift risk if references break
   - ✅ Could be future enhancement for multi-project setups

**Rationale**:
- **Single Source of Truth**: One file eliminates policy drift between Tidy and Storage Optimizer
- **System-Specific Overrides**: Both systems share protections but have different behaviors (Tidy skips protected paths, Storage Optimizer can analyze but not delete)
- **Extensible**: YAML structure supports adding new categories/systems without breaking existing sections
- **Future-Proof**: Database retention section included (disabled) for BUILD-154+ database cleanup implementation
- **User-Friendly**: YAML format is human-readable and easy to customize per project

**Implementation**:
- `config/protection_and_retention_policy.yaml` (213 lines): Unified policy with 5 sections
- `docs/PROTECTION_AND_RETENTION_POLICY.md` (357 lines): Comprehensive guide explaining policy structure, usage examples, troubleshooting
- `docs/INDEX.md`: Added pointer to protection policy doc
- Integration: Both Tidy and Storage Optimizer reference same policy file

**Validation**:
- ✅ Protected paths coverage: 15 categories covering all critical files
- ✅ Retention windows codified: 30/90/180 days + permanent
- ✅ Category policies defined: 4 categories with execution limits
- ✅ System overrides clear: Tidy vs Storage Optimizer behaviors documented
- ✅ Documentation comprehensive: 357-line guide + usage examples

**Constraints Satisfied**:
- ✅ No policy drift: Single YAML source for both systems
- ✅ System flexibility: Override sections allow different behaviors from shared policy
- ✅ Maintainability: Policy updates in one place
- ✅ Transparency: YAML format human-readable and version-controlled
- ✅ Extensibility: Structure supports future systems/categories

**Impact**:
- **Safety**: Clear boundaries for automation - both systems respect same protections
- **Maintainability**: Policy updates only require YAML edit (not code changes)
- **Clarity**: Users know exactly what systems can/cannot touch
- **Future-Proof**: Database retention section ready for BUILD-154+

**References**:
- Policy: [config/protection_and_retention_policy.yaml](../config/protection_and_retention_policy.yaml)
- Guide: [docs/PROTECTION_AND_RETENTION_POLICY.md](PROTECTION_AND_RETENTION_POLICY.md)
- Completion: [docs/BUILD-153_COMPLETION_SUMMARY.md](BUILD-153_COMPLETION_SUMMARY.md)

---

### DEC-015 | 2026-01-02T14:00 | Storage Optimizer - Delta Reporting Architecture
**Status**: ✅ Implemented
**Build**: BUILD-153 Phase 3
**Context**: After BUILD-152 lock-aware execution, needed weekly automated scans to track storage trends over time. Required efficient comparison of scan results to show "what changed since last scan."

**Decision**: Implement path-based set comparison for delta reporting rather than content-based (SHA256) comparison or full file-by-file diffing.

**Chosen Approach**:
- **Path-Based Set Operations**:
  - Current scan candidates: `current_paths = {c.path for c in current_candidates}`
  - Previous scan candidates: `previous_paths = {c.path for c in previous_candidates}`
  - New files: `new_paths = current_paths - previous_paths`
  - Removed files: `removed_paths = previous_paths - current_paths`
- **Previous Scan Lookup**:
  - Query: `SELECT * FROM storage_scans WHERE scan_target = ? ORDER BY timestamp DESC LIMIT 1`
  - Finds most recent scan for same target path
  - Handles first scan gracefully (`is_first_scan: true` when no previous baseline)
- **Category-Level Aggregation**:
  - Per-category count/size changes: `category_changes[cat] = {current_count, previous_count, delta_count, delta_size_gb}`
  - Identifies which categories accumulating fastest
- **Report Formats**:
  - Text: Human-readable delta summary (new/removed counts, size change, category breakdown, sample paths)
  - JSON: Machine-parseable for visualization/trending

**Alternatives Considered**:

1. **Content-Based (SHA256) Comparison**:
   - ❌ Rejected: Expensive - requires computing SHA256 for every file on every scan
   - ❌ Overkill: Don't need to detect file content changes, only path existence
   - ❌ Slower: ~10x slower than path comparison for large scans (1000+ files)

2. **Full File-by-File Diffing**:
   - ❌ Rejected: Quadratic complexity for large scans (compare every file to every other)
   - ❌ Memory-intensive: Requires loading all candidates into memory for comparison

3. **Database-Side Comparison (SQL JOIN)**:
   - ⚠️ Considered: Could use `FULL OUTER JOIN` on paths to detect new/removed
   - ❌ Rejected: More complex SQL, harder to debug, not significantly faster for small scans (<10K files)
   - ✅ Could be future optimization for very large scans (100K+ files)

4. **Incremental State Tracking**:
   - ❌ Rejected: Requires persistent state between scans (what was already reported?)
   - ❌ Breaks on manual scan deletion or database cleanup
   - ✅ Path-based comparison is stateless - only needs current + previous scan

**Rationale**:
- **Efficiency**: Set operations are O(n) for path comparison vs O(n log n) or O(n²) for content-based/diffing approaches
- **Correctness**: Path existence is the right signal for "cleanup opportunities changed" - content changes don't matter
- **Simplicity**: Python set operations are trivial to implement and debug (`current_paths - previous_paths`)
- **Scalability**: Works for small scans (10 files) and large scans (10K+ files) with minimal memory overhead
- **Stateless**: No persistent tracking needed - comparison is pure function of current + previous scan

**Implementation**:
- `scripts/storage/scheduled_scan.py::compute_delta_report()` (100 lines): Path-based delta computation
- `scripts/storage/scheduled_scan.py::format_delta_report()` (150 lines): Text report generation
- `scripts/storage/scheduled_scan.py::get_last_scan()` (20 lines): Previous scan lookup by target path
- Delta outputs: `archive/reports/storage/weekly/weekly_delta_YYYYMMDD_HHMMSS.{txt,json}`

**Validation**:
- ✅ First scan: 0 candidates baseline, `is_first_scan: true`
- ✅ Second scan: 10 new files created, delta correctly shows +10 files, 0 removed
- ✅ Category breakdown: `dev_caches: 0 → 10 (+10)`
- ✅ Size change: `+0.00015 GB` calculated correctly
- ✅ JSON structure validated: `new_paths_sample`, `removed_paths_sample`, `category_changes`

**Constraints Satisfied**:
- ✅ Performance: Set operations scale linearly with scan size
- ✅ Correctness: Path-based comparison matches user mental model ("what files appeared/disappeared")
- ✅ Simplicity: ~100 lines of Python code, no external dependencies
- ✅ Extensibility: JSON format ready for visualization/trending dashboards

**Impact**:
- **Storage Trends**: Weekly delta reports show accumulation patterns (e.g., "dev_caches growing 10GB/month")
- **Operator Visibility**: Clear "what changed since last scan" summary without manual diff
- **Automation-Ready**: JSON output enables programmatic analysis and alerting
- **Low Overhead**: Path comparison adds <1 second to scan time for typical workloads (1000 files)

**Future Enhancements** (deferred):
- **Database-Side Comparison**: Use SQL JOIN for scans >100K files (performance optimization)
- **Trend Analysis**: Multi-scan comparison (show 4-week trend, not just last-to-current)
- **Visual Reports**: HTML delta reports with charts (line graph: category size over time, pie chart: category breakdown)

**References**:
- Implementation: [scripts/storage/scheduled_scan.py](../scripts/storage/scheduled_scan.py) (lines 180-280)
- Documentation: [docs/STORAGE_OPTIMIZER_AUTOMATION.md](STORAGE_OPTIMIZER_AUTOMATION.md) (Delta Reporting section)
- Completion: [docs/BUILD-153_COMPLETION_SUMMARY.md](BUILD-153_COMPLETION_SUMMARY.md)

---

### DEC-013 | 2026-01-02T13:45 | Storage Optimizer Intelligence - Zero-Token Pattern Learning
**Status**: ✅ Implemented
**Build**: BUILD-151 Phase 4
**Context**: After BUILD-148 MVP (dry-run scanning) and BUILD-150 Phase 2 (execution engine), user needed intelligence features to reduce manual approval burden. Goal: learn cleanup patterns from approval history without LLM costs.

**Decision**: Implement deterministic pattern detection for approval learning + minimal-token LLM categorization for edge cases only (~5-10% of files).

**Chosen Approach**:
- **Approval Pattern Analyzer** (zero tokens): Detects 4 pattern types from approval/rejection history:
  - Path patterns: "always approve node_modules in temp directories"
  - File type patterns: "always approve .log files older than 90 days"
  - Age thresholds: "approve diagnostics older than 6 months"
  - Size thresholds: "approve .cache files > 1GB"
  - Confidence scoring (default 75% minimum, 5 samples minimum)
  - Creates `LearnedRule` database entries for review/approval
- **Smart Categorizer** (minimal tokens): LLM-powered classification for unknowns only:
  - Batches 20 files per LLM call (~9,400 tokens per 100 unknowns)
  - Falls back to 'unknown' if LLM fails
  - GLM-first provider selection (cost optimization)
  - Only runs on ~5-10% of files (deterministic rules handle majority)
- **Recommendation Engine** (zero tokens): Statistical analysis of scan history:
  - Growth alerts: "dev_caches growing 10GB/month"
  - Recurring waste: "same node_modules deleted every 2 weeks"
  - Policy adjustments: "consider increasing retention window"
  - Top consumers: "Top 3 categories = 80% of disk space"
  - Requires 2+ scans for basic recommendations, 3+ for trends
- **Steam Game Detector** (manual trigger): Registry-based detection + filtering:
  - Windows registry scan for Steam installation path
  - Game library parsing for installed games
  - Size/age filtering (manual trigger only, not automated)

**Alternatives Considered**:

1. **LLM-First Classification for All Files**:
   - ❌ Rejected: ~100-200K tokens per 1000-file scan (too expensive)
   - ❌ Requires LLM provider for basic operations
   - ❌ Slower than deterministic rules

2. **Hardcoded Learning Rules**:
   - ❌ Rejected: Cannot adapt to user-specific patterns
   - ❌ Requires code changes for new patterns

3. **Machine Learning Model Training**:
   - ❌ Rejected: Overkill for pattern detection (simple path/filetype matching sufficient)
   - ❌ Requires training data collection pipeline
   - ❌ Adds deployment complexity

4. **Always Auto-Apply Learned Rules**:
   - ❌ Rejected: Too risky - user should review before auto-deletion
   - ✅ Chosen: Learned rules require manual approval before application

**Rationale**:
- **Zero-Token Pattern Learning**: Deterministic analysis of approval history costs zero tokens, handles 90-95% of cases
- **Minimal-Token Edge Cases**: LLM only for truly unknown files (~5-10%), batch processing minimizes cost
- **Statistical Recommendations**: Trend analysis from scan history provides strategic guidance without LLM
- **Manual Trigger Steam Detection**: Prevents automated intrusion into gaming library, user controls when to analyze
- **Approval Workflow**: Learned rules require review before application (safety-first design)

**Implementation**:
- `storage_optimizer/approval_pattern_analyzer.py` (520 lines): Pattern detection + learned rule creation
- `storage_optimizer/smart_categorizer.py` (350 lines): LLM-powered edge case handling
- `storage_optimizer/recommendation_engine.py` (420 lines): Strategic recommendations from scan history
- `storage_optimizer/steam_detector.py` (360 lines): Manual-trigger game analysis
- `scripts/storage/learn_patterns.py` (280 lines): CLI for pattern analysis, rule approval, recommendations
- `scripts/storage/analyze_steam_games.py` (280 lines): Manual Steam analysis CLI
- `scripts/migrations/add_storage_intelligence_features.py` (165 lines): Database migration
- Total: 2,375 lines of new code

**Validation**:
- Tested with 44 approvals of temp_files category
- Pattern detection: 4 high-confidence patterns found (100% approval rate)
  - Path pattern: "parent:Temp" (44 approvals, 0 rejections)
  - Path pattern: "grandparent:Local/Temp" (44 approvals, 0 rejections)
  - Path pattern: "contains:temp" (44 approvals, 0 rejections)
  - File type: ".node files in temp_files" (44 approvals, 0 rejections)
- Recommendations generated: 10 strategic insights
  - Growth alert: "temp_files growing at 13,154 GB/month"
  - Top consumer: "temp_files = 100% of storage"
  - Recurring waste: 8 patterns detected (*.node files appearing in every scan)

**Token Costs**:
- Approval Pattern Analyzer: **0 tokens** (deterministic)
- Smart Categorizer: ~9,400 tokens per 100 unknowns (~235K/year for typical usage)
- Recommendation Engine: **0 tokens** (statistical)
- **Total**: ~235K tokens/year (only for 5-10% edge case categorization)

**Constraints Satisfied**:
- ✅ Zero-token pattern learning (deterministic analysis)
- ✅ Minimal-token categorization (LLM only for unknowns)
- ✅ Manual approval required for learned rules (safety-first)
- ✅ PostgreSQL + SQLite compatibility (database migration handles both)
- ✅ Batch processing minimizes LLM calls (20 files per request)
- ✅ Steam detection manual-trigger only (no automated intrusion)

**Impact**:
- **Automation**: Learned rules reduce manual approval burden by suggesting auto-approval patterns
- **Cost**: 99% of pattern learning costs zero tokens (deterministic analysis)
- **Safety**: Learned rules require manual review before application
- **Efficiency**: Strategic recommendations guide cleanup priorities based on actual data
- **Flexibility**: Works with both PostgreSQL (production) and SQLite (development)

**References**:
- Implementation: [docs/STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md](STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md)
- Design: [docs/STORAGE_OPTIMIZER_PHASE4_PLAN.md](STORAGE_OPTIMIZER_PHASE4_PLAN.md)
- Code: `src/autopack/storage_optimizer/` (4 new modules, 1,650 lines)

---

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


### DEC-013 | 2026-01-02 | Tidy System - Windows File Lock Handling Strategy
**Status**: ✅ Implemented
**Build**: BUILD-145
**Context**: Tidy system encounters Windows file locks (13 telemetry databases locked by SearchIndexer.exe) preventing complete workspace cleanup. Need strategy that balances automation with Windows OS constraints.

**Decision**: Implement "Option B: Accept Partial Tidy" as default strategy - tidy skips locked files gracefully and continues with all other cleanup, with prevention mechanisms and documented escalation paths.

**Chosen Approach**:
- **Graceful Skip Pattern**: `execute_moves()` catches PermissionError and continues instead of crashing
  - Locked files reported in cleanup summary
  - Tidy completes successfully with warning about locked items
  - Idempotent design - rerun after reboot to finish cleanup
- **Prevention Layer**: `exclude_db_from_indexing.py` uses `attrib +N` to exclude .db files from Windows Search
  - Prevents future locks by marking files as "not content indexed"
  - Applied proactively to all telemetry databases
  - Zero performance impact on database usage
- **Escalation Paths**: Documented 4 strategies in TIDY_LOCKED_FILES_HOWTO.md:
  - **Option A** (prevention): Exclude from indexing - stops new locks
  - **Option B** (daily use): Accept partial tidy - skip locks, rerun later
  - **Option C** (complete cleanup): Stop locking processes (`net stop WSearch`) - requires admin
  - **Option D** (stubborn locks): Reboot + early tidy - cleanest but most disruptive

**Alternatives Considered**:
1. **Force-delete approach**: Use handle.exe to kill locking processes
   - Rejected: Too aggressive, risks data corruption, requires admin rights
2. **Retry with delays**: Implement exponential backoff retry logic
   - Rejected: SearchIndexer holds locks for hours/days, not transient
3. **Move entire .autonomous_runs/**: Avoid granular cleanup
   - Rejected: Would corrupt active runtime workspaces

**Rationale**:
- **Windows reality check**: Cannot reliably move/delete locked files on Windows - only options are skip or remove lock
- **Following community advice**: Cursor community recommended Option B as safe default for daily use
- **Graceful degradation**: Partial cleanup (955 items) better than no cleanup (crashed tidy)
- **Progressive enhancement**: Prevention layer reduces lock frequency over time
- **User control**: Clear escalation paths when complete cleanup needed

**Implementation**:
```python
# Locked file handling in execute_moves()
try:
    shutil.move(str(src), str(dest))
except PermissionError:
    print(f"[SKIPPED] {src} (locked by another process)")
    failed_moves.append((src, str(e)))
    # Continue with remaining moves instead of crashing
```

**Constraints Satisfied**:
- ✅ **No data loss**: Locked files remain in place, can be cleaned later
- ✅ **No corruption**: Doesn't attempt force operations on locked files
- ✅ **Idempotent**: Rerunning tidy is safe, picks up where it left off
- ✅ **Transparent**: Clear reporting of what was skipped and why
- ✅ **Preventable**: Indexing exclusion reduces future lock frequency

**Impact**:
- **Before**: Tidy crashed on first locked file, no cleanup performed
- **After**: Tidy completes successfully, cleans 955 items, reports 13 locked items
- **Prevention**: 13 databases excluded from indexing, no new locks expected
- **Operator experience**: Clear guidance on when/how to escalate for complete cleanup

**Validation**:
- 45 orphaned files archived successfully
- 910 empty directories deleted successfully
- 13 databases remain locked (expected - Windows Search Indexer)
- Tidy system completes with exit code 0 (success)
- No crashes, no data loss, no corruption

**Files Modified**:
- scripts/tidy/tidy_up.py (locked file handling in execute_moves)
- scripts/tidy/exclude_db_from_indexing.py (NEW - prevention script)
- docs/TIDY_LOCKED_FILES_HOWTO.md (NEW - escalation guide)

**See Also**: DEC-003 (Manual Tidy Function), DEC-014 (Persistent Queue for Locked Files), DBG-080 (BUILD-145 debug log)

---

### DEC-014 | 2026-01-02 | Persistent Queue System for Locked File Retry
**Status**: ✅ Implemented
**Build**: BUILD-145 Follow-up
**Context**: DEC-013 implemented graceful skip for locked files, but required manual rerun after locks released. Need automated retry mechanism that survives reboots and requires zero operator intervention.

**Decision**: Implement persistent JSON-based queue with exponential backoff, bounded attempts, and Windows Task Scheduler integration for automatic retry.

**Chosen Approach**:
- **Persistent Queue** (`.autonomous_runs/tidy_pending_moves.json`):
  - JSON format (human-readable, survives crashes)
  - Atomic writes (temp file + rename pattern)
  - Stable item IDs: SHA256(src+dest+action) prevents duplicates
  - Full error context: exception type, errno, winerror, truncated message
  - Status tracking: `pending`, `succeeded`, `abandoned`
- **Exponential Backoff**:
  - Base: 5 minutes (responsive for transient locks)
  - Formula: `base * (2 ^ (attempt - 1))`
  - Cap: 24 hours (prevents excessive delays)
  - Example: 5min → 10min → 20min → 40min → ... → 24hr (capped)
- **Bounded Attempts**:
  - Max 10 retries OR 30 days (whichever comes first)
  - Status becomes `abandoned` after limit reached
  - Operator can inspect/manually retry abandoned items
- **Automatic Retry**:
  - Phase -1 (new): Load queue and retry eligible items at tidy startup
  - Windows Task Scheduler integration: Run tidy at logon + daily 3am
  - Idempotent: Safe to run multiple times, won't re-move already-moved files

**Alternatives Considered**:
1. **In-Memory Queue**: Simple, no persistence needed
   - Rejected: Lost on crash/reboot, defeats purpose of "automatic retry after reboot"
2. **Database Queue**: More structured, query support
   - Rejected: Overkill for small queue (~10-50 items), adds DB dependency
3. **No Backoff (immediate retry)**: Simpler logic
   - Rejected: Wastes CPU/disk if locks persist for hours/days
4. **Unlimited Retries**: Never give up
   - Rejected: Queue bloat for permanently locked files (e.g., open in editor indefinitely)

**Rationale**:
- **Operational truth**: "Auto-archive after locks release" only true if retry happens automatically
- **Windows reality**: Locks clear on reboot/logon, perfect trigger for retry
- **Zero-touch automation**: Task Scheduler + persistent queue = no operator action needed
- **Graceful degradation**: Queue prevents infinite retries via bounded attempts
- **Debugging-friendly**: JSON format allows manual inspection/editing

**Implementation**:
```python
# Phase -1: Retry pending moves from previous runs
pending_queue = PendingMovesQueue(
    queue_file=repo_root / ".autonomous_runs" / "tidy_pending_moves.json",
    workspace_root=repo_root,
    queue_id="autopack-root"
)
pending_queue.load()
retried, retry_succeeded, retry_failed = retry_pending_moves(
    queue=pending_queue, dry_run=dry_run
)

# On move failure: enqueue for retry
if pending_queue:
    pending_queue.enqueue(
        src=src, dest=dest, action="move", reason="locked",
        error_info=e, bytes_estimate=size, tags=["tidy_move"]
    )
```

**Queue File Schema**:
```json
{
  "schema_version": 1,
  "queue_id": "autopack-root",
  "items": [
    {
      "id": "a1b2c3d4e5f6g7h8",
      "src": "telemetry_seed_v5.db",
      "dest": "archive/data/databases/telemetry_seeds/telemetry_seed_v5.db",
      "status": "pending",
      "reason": "locked",
      "attempt_count": 2,
      "next_eligible_at": "2026-01-02T15:40:00Z",
      "last_error": "[WinError 32] The process cannot access the file..."
    }
  ]
}
```

**Constraints Satisfied**:
- ✅ **Survives reboots**: Queue persisted to JSON file
- ✅ **No manual intervention**: Task Scheduler automates retry
- ✅ **Bounded resource usage**: Max 10 attempts prevents queue bloat
- ✅ **Transparent**: Queue summary printed at tidy end, JSON is human-readable
- ✅ **Safe**: Exponential backoff prevents CPU/disk waste on persistent locks

**Impact**:
- **Before**: Locked files skipped, operator must manually rerun tidy after reboot
- **After**: Locked files queued, automatically retried at logon/daily, operator sees completion without action
- **Task Scheduler**: Opt-in automation (documented setup, not auto-installed)
- **Queue Growth**: Bounded by max_attempts (10) and abandon_after_days (30)

**Validation**:
- ✅ Dry-run test passes (Phase -1 handles empty queue correctly)
- ✅ Module imports successfully, no syntax errors
- ✅ Integration validated (queue lifecycle: load → retry → enqueue → save)
- ⏳ Real lock test pending (needs actual locked files for end-to-end validation)

**Files Modified**:
- scripts/tidy/pending_moves.py (NEW, 570 lines - queue implementation)
- scripts/tidy/tidy_up.py (Phase -1 retry, queue-aware execute_moves, queue summary)
- docs/guides/WINDOWS_TASK_SCHEDULER_TIDY.md (NEW, 280 lines - automation guide)
- README.md (queue behavior documentation)

**See Also**: DEC-013 (Windows File Lock Handling), docs/BUILD-145-FOLLOWUP-QUEUE-SYSTEM.md
