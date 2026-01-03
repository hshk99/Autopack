# Documentation Link Triage Report

**Generated**: 2026-01-03
**Total Missing File Links**: 115
**Auto-Fixed (High Confidence)**: 2 links in COMPLETION_REPORT_2026-01-03.md
**Remaining for Manual Triage**: 113 links

---

## Executive Summary

After automated fixes, 113 `missing_file` links remain for manual triage. These fall into clear categories with recommended actions:

### Quick Wins (Can be batch-processed) - 27 links
- **Path Examples** (5 links): Generic examples in documentation (e.g., `path/to/file.md`)
- **Historical References** (15 links): References to intentionally removed/never-existed files
  - Storage optimizer planned features (11)
  - Backend refs (1)
  - Migrations (2)
  - Gitignored runtime (1)
- **GitHub CI** (7 links): Need to verify if `.github/workflows/ci.yml` exists or should be marked historical

### Complex Cases (Require investigation) - 86 links
- **Other** (63 links): Mixed references needing individual assessment
- **Python Module Refs** (20 links): Documentation references that may be stubs or moved
- **Config Templates** (3 links): Need to verify if templates exist or are planned

---

## Triage Decision Framework

For each link, apply ONE of these actions:

### 1. IGNORE (Mark as historical_ref)
**When to use**: File intentionally removed or never existed, reference provides historical context
**How**: Add to `scripts/doc_link_checker_config.yaml` under `ignore_patterns` with comment
**Example**:
```yaml
ignore_patterns:
  - pattern: "src/backend/"
    reason: "Backend removed in BUILD-146, historical refs intentional"
```

### 2. UPDATE (Fix the link)
**When to use**: Clear canonical target exists
**How**: Create redirect stub OR update link directly
**Example**:
```markdown
<!-- Before -->
[link](old_path.md)

<!-- After with redirect stub -->
# old_path.md
See [new_path.md](new_path.md)

<!-- OR direct update -->
[link](new_path.md)
```

### 3. CREATE STUB
**When to use**: Old name referenced externally or in many places
**How**: Create minimal redirect document
**Example**:
```markdown
# [Old Name]

**Status**: Moved

See [New Location](../path/to/new_location.md).
```

---

## Category Analysis

### 1. Path Examples (5 links) - IGNORE

**Decision**: Mark as `path_example` pattern in ignore config

**Files**:
- `docs/BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md`:
  - Line 135: `path/to/file.md`
  - Line 136: `path/to/file.txt`
- `docs/BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md`:
  - Line 125: `target`, `new_target`
  - Line 397: `file.md`

**Rationale**: Generic placeholders in documentation examples, not actual file references

**Action**:
```yaml
# Add to scripts/doc_link_checker_config.yaml
ignore_patterns:
  - pattern: "^path/to/"
    reason: "Generic path examples in documentation"
  - pattern: "^(target|new_target|file\\.md)$"
    reason: "Generic placeholders in examples"
```

---

### 2. Storage Optimizer Planned Features (11 links) - IGNORE

**Decision**: Mark as historical_ref - these were planned features never implemented

**Files**:
- `docs/ARCHITECTURE_DECISIONS.md` (lines 507-510, 615-619):
  - `storage_optimizer/approval_pattern_analyzer.py`
  - `storage_optimizer/smart_categorizer.py`
  - `storage_optimizer/recommendation_engine.py`
  - `storage_optimizer/steam_detector.py`
  - `storage_optimizer/policy.py`
  - `storage_optimizer/models.py`
  - `storage_optimizer/scanner.py`
  - `storage_optimizer/classifier.py`
  - `storage_optimizer/reporter.py`

**Rationale**: Phase 1/2 storage optimizer architecture evolved differently. Documents describe original plan for historical context.

**Action**:
```yaml
ignore_patterns:
  - pattern: "^storage_optimizer/.*\\.py$"
    reason: "Original architecture plan (never implemented, revised in Phase 3+)"
    scope: "docs/ARCHITECTURE_DECISIONS.md"
```

---

### 3. Backend References (1 link) - IGNORE

**Decision**: Historical reference to removed backend

**Files**:
- `docs/CANONICAL_API_CONSOLIDATION_PLAN.md`:
  - Line 69: `backend.api.auth`

**Rationale**: Backend removed in BUILD-146, document describes historical consolidation plan

**Action**:
```yaml
ignore_patterns:
  - pattern: "^backend\\."
    reason: "Backend removed in BUILD-146, historical architecture docs"
```

---

### 4. Migrations (2 links) - IGNORE

**Decision**: These migrations were referenced but never created

**Files**:
- `docs/CHANGELOG.md`:
  - Line 1841: `migrations/005_add_p10_escalation_events.sql`
  - Line 1849: `migrations/006_fix_v_truncation_analysis_view.sql`

**Rationale**: BUILD-129 telemetry added columns directly via Python migration scripts, not SQL files

**Action**:
```yaml
ignore_patterns:
  - pattern: "^migrations/.*\\.sql$"
    reason: "Migrations implemented via Python scripts, not SQL files"
```

---

### 5. Gitignored Runtime (1 link) - IGNORE

**Decision**: Local environment file

**Files**:
- `docs/GOVERNANCE.md`:
  - Line 127: `.env.local`

**Rationale**: Gitignored file for local development, reference is instructional

**Action**:
```yaml
ignore_patterns:
  - pattern: "^\\.env"
    reason: "Local environment files (gitignored)"
```

---

### 6. GitHub CI (8 links) - INVESTIGATE THEN UPDATE OR IGNORE

**Decision**: Need to check if `.github/workflows/ci.yml` exists

**Files**:
- Multiple references to `.github/workflows/ci.yml` in:
  - `docs/BUILD_155_SOT_TELEMETRY_COMPLETION.md`
  - `docs/CHANGELOG.md` (multiple)

**Investigation needed**:
```bash
ls -la .github/workflows/
```

**If CI exists**: Update links to correct path
**If no CI**: Mark as historical_ref (planned but not implemented)

**Pending action**: User to decide based on CI infrastructure status

---

### 7. Config Templates (4 links) - INVESTIGATE

**Decision**: Need to verify if these should exist

**Files**:
- `docs/CHANGELOG.md`:
  - Line 2123: `templates/hardening_phases.json`
  - Line 2123: `templates/phase_defaults.json`
- `docs/CURSOR_PROMPT_RUN_AUTOPACK.md`:
  - Line 69: `config/learned_rules.yaml`
  - Line 213: `scripts/runs/my-build.json`

**Investigation needed**:
- Check if `config/` or `templates/` directories exist
- Determine if these were planned features or docs need update

**Pending action**: User to review based on current architecture

---

### 8. Python Module/Doc References (20 links) - MANUAL REVIEW

**Decision**: Each needs individual assessment

**Pattern**: Missing `.md` or `.py` files referenced as if they exist

**Sample**:
- `docs/ARCHITECTURE_DECISIONS.md`: `STATUS_AUDITOR_IMPLEMENTATION.md`
- `docs/autopack/diagnostics_second_opinion.md`: `diagnostics_overview.md`
- `docs/autopack/diagnostics_second_opinion.md`: `handoff_bundle.md`

**Action**: Systematically check each:
1. Search codebase for target name
2. If moved: Update link or create redirect stub
3. If removed: Mark as historical_ref
4. If planned: Mark as TODO or remove reference

---

### 9. Other (63 links) - MANUAL REVIEW

**Decision**: Mixed bag requiring case-by-case analysis

**High-priority subset** (sample):
- `docs/autopack/diagnostics_handoff_bundle.md`:
  - Line 58, 59: `excerpts/log_tail.txt` (likely example path)
- `docs/autopack/diagnostics_iteration_loop.md`:
  - Line 96: `./autonomous_runs.md` (likely should be top-level doc)
- `docs/BUILD-165_SUBSYSTEM_LOCKS.md`:
  - Line 5: `archive/superseded/reports/BUILD-162_LOCK_STATUS_UX.md` (CHECK if exists)

**Triage process**:
1. Export list to CSV/JSON for systematic review
2. For each link:
   - Check if file exists elsewhere in repo
   - Check git history for moves/renames
   - Apply decision framework (IGNORE/UPDATE/CREATE STUB)
3. Document rationale in triage log

---

## Recommended Next Steps

### Phase 1: Quick Wins (30 minutes)
1. **Apply path example ignores** (5 links)
   ```bash
   # Edit scripts/doc_link_checker_config.yaml
   # Add ignore patterns from categories 1-5
   ```

2. **Apply historical ref ignores** (15 links)
   - Storage optimizer planned (11)
   - Backend refs (1)
   - Migrations (2)
   - Gitignored runtime (1)

3. **Verify reduction**
   ```bash
   python scripts/check_doc_links.py --deep
   # Should reduce missing_file from 115 → 93
   ```

### Phase 2: Investigations (1-2 hours)
1. **GitHub CI check** (8 links)
   ```bash
   ls -la .github/workflows/
   # If exists: Update links
   # If not: Add to ignore_patterns
   ```

2. **Config templates check** (4 links)
   ```bash
   find . -name "*.json" -path "*/templates/*"
   find . -name "*.yaml" -path "*/config/*"
   # Decide based on findings
   ```

### Phase 3: Manual Triage (2-4 hours)
1. **Python module refs** (20 links)
   - Systematic search for each missing doc
   - Update or ignore based on findings

2. **Other category** (63 links)
   - Export to structured format
   - Prioritize by document importance
   - Apply decision framework systematically

### Phase 4: Validation
1. Re-run deep scan
2. Verify no nav-only failures
3. Document all ignore decisions
4. Create PR with triage results

---

## Ignore Config Template

**Location**: `scripts/doc_link_checker_config.yaml`

```yaml
# Documentation Link Checker Configuration
# Triage Date: 2026-01-03
# Triage Report: docs/DOC_LINK_TRIAGE_REPORT.md

ignore_patterns:
  # Generic path examples in documentation
  - pattern: "^path/to/"
    reason: "Generic path examples in documentation"
    date_added: "2026-01-03"

  - pattern: "^(target|new_target|file\\.md)$"
    reason: "Generic placeholders in examples"
    date_added: "2026-01-03"

  # Historical references - intentionally removed features
  - pattern: "^storage_optimizer/.*\\.py$"
    reason: "Original architecture plan (never implemented, revised in Phase 3+)"
    scope: "docs/ARCHITECTURE_DECISIONS.md"
    date_added: "2026-01-03"

  - pattern: "^backend\\."
    reason: "Backend removed in BUILD-146, historical architecture docs"
    date_added: "2026-01-03"

  - pattern: "^migrations/.*\\.sql$"
    reason: "Migrations implemented via Python scripts, not SQL files"
    date_added: "2026-01-03"

  # Local/gitignored files
  - pattern: "^\\.env"
    reason: "Local environment files (gitignored)"
    date_added: "2026-01-03"

  # TODO: Add more after Phase 2 investigations
  # - pattern: "^.github/workflows/"
  #   reason: "TBD based on CI infrastructure check"

  # TODO: Add more after Phase 3 manual triage
  # Document each decision with clear rationale
```

---

## Triage Decision Log Template

**Format**: Append to this report as decisions are made

```markdown
### [File Path] - [Decision] - [Date]

**Broken Target**: [target]
**Line Number**: [line]
**Decision**: IGNORE | UPDATE | CREATE_STUB
**Rationale**: [why this decision was made]
**Action Taken**: [what was done]
```

---

## Success Criteria

**Goal**: Reduce `missing_file` links from 115 → <30 (nav-critical only)

**Targets**:
- Phase 1 (Quick Wins): 115 → 93 (-20%)
- Phase 2 (Investigations): 93 → 80 (-14%)
- Phase 3 (Manual Triage): 80 → <30 (-65%)

**Timeline**:
- Phase 1: Can be completed in single session (30 min)
- Phase 2: 1-2 hours split across 2 sessions
- Phase 3: 2-4 hours, recommend spread across multiple sessions

**Blocker Risk**: Phase 3 manual triage is time-intensive but not blocking CI (deep scan is report-only)

---

## Related Documents

- [BUILD-159: Deep Doc Link Checker](BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md)
- [Fix Plan JSON](../archive/diagnostics/doc_link_fix_plan.json)
- [Fix Plan Markdown](../archive/diagnostics/doc_link_fix_plan.md)
- [Doc Link Checker](../scripts/check_doc_links.py)
- [Auto-Fixer](../scripts/fix_doc_links.py)

---

**Status**: Triage framework complete, awaiting Phase 1 quick wins application
