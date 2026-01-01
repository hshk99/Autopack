# Research Directory Integration with Tidy Function

**Date**: 2025-12-13
**Status**: ✅ IMPLEMENTED

---

## Problem Solved

**User Workflow**:
- Research agents gather files → `archive/research/`
- Auditor reviews files → produces comprehensive plan
- Implementation decisions: IMPLEMENTED / PENDING / REJECTED

**Challenge**: How to prevent tidy function from consolidating files **during** Auditor review, while still cleaning up **after** review?

---

## Solution: Lifecycle-Based Exclusion

### Directory Structure

```
archive/research/
├── README.md (documentation)
├── active/ (awaiting Auditor review - EXCLUDED from tidy)
├── reviewed/ (Auditor-processed - SAFE to tidy)
│   ├── implemented/
│   ├── deferred/
│   └── rejected/
└── archived/ (long-term reference - OPTIONAL tidy)
```

### Tidy Behavior

| Directory | Tidy Behavior | Purpose |
|-----------|--------------|---------|
| `active/` | ❌ EXCLUDED | Research files awaiting Auditor review |
| `reviewed/` | ✅ INCLUDED | Auditor-processed files ready to consolidate |
| `archived/` | ⚙️ OPTIONAL | Long-term reference (user decides) |

---

## Implementation Changes

### 1. Exclusion Added to `consolidate_docs_v2.py`

**File**: [scripts/tidy/consolidate_docs_v2.py](../../scripts/tidy/consolidate_docs_v2.py) (lines 599-617)

```python
# Exclusion paths (never tidy these)
exclusion_paths = [
    self.archive_dir / "tidy_v7",
    self.archive_dir / "prompts",
    self.archive_dir / "research" / "active",  # Active research awaiting Auditor review
]

for file_path in md_files:
    # Skip excluded directories
    if any(file_path.is_relative_to(excluded) for excluded in exclusion_paths if excluded.exists()):
        print(f"  [SKIP] Excluded: {file_path.relative_to(self.project_dir)}")
        continue
```

### 2. Exclusion Added to `enhanced_file_cleanup.py`

**File**: [scripts/tidy/enhanced_file_cleanup.py](../../scripts/tidy/enhanced_file_cleanup.py) (lines 46-51, 94-96)

```python
# Exclusion paths (never tidy these)
self.exclusion_paths = [
    REPO_ROOT / "archive" / "tidy_v7",
    REPO_ROOT / "archive" / "prompts",
    REPO_ROOT / "archive" / "research" / "active",  # Active research awaiting Auditor review
]

def _is_excluded(self, file_path: Path) -> bool:
    """Check if file is in excluded directory"""
    return any(file_path.is_relative_to(excluded) for excluded in self.exclusion_paths if excluded.exists())
```

Applied to all file processing methods:
- `_process_python_files()` (line 105)
- `_process_log_files()` (line 160)
- `_process_json_files()` (line 189)
- `_process_yaml_files()` (line 252)
- `_process_txt_files()` (line 291)
- `_process_data_files()` (line 351)
- `_process_sql_files()` (line 375)
- `_process_other_files()` (line 411)

---

## Workflow Example

### Step 1: Research Agents Compile Files

```bash
# Planning trigger
python scripts/plan_hardening.py --project file-organizer-app-v1 --features auth,search,batch,frontend

# Output
archive/research/active/file-organizer-app-v1-20251213/
├── phase_templates.json
├── research_auth.md
├── research_search.md
├── planning_context.md
└── kickoff_prompt.md
```

### Step 2: Auditor Reviews Files

**Auditor Process**:
1. Read files from `active/file-organizer-app-v1-20251213/`
2. Analyze, produce comprehensive plan
3. Mark files: IMPLEMENTED / PENDING / REJECTED
4. Move to appropriate `reviewed/` subdirectory

```bash
# After Auditor review
mv archive/research/active/file-organizer-app-v1-20251213 \
   archive/research/reviewed/implemented/
```

### Step 3: Tidy Reviewed Files

```bash
# Consolidate reviewed files
python scripts/tidy/unified_tidy_directory.py archive/research/reviewed --docs-only --execute

# Result:
# - .md files → docs/ARCHITECTURE_DECISIONS.md (with Auditor status metadata)
# - Other files → organized by type
# - Active research → UNTOUCHED (safe staging area)
```

---

## Benefits

### 1. Workflow Preserved
✅ Active research never tidied during Auditor review
✅ Files remain in staging area until Auditor completes
✅ No accidental consolidation of pending research

### 2. Cleanup After Review
✅ Reviewed files can be tidied periodically
✅ Prevents long-term accumulation in `reviewed/`
✅ Historical research preserved in SOT files

### 3. Auditor Decisions Tracked
✅ IMPLEMENTED files consolidated with metadata
✅ PENDING files preserved for future reference
✅ REJECTED files documented for historical context

### 4. Flexibility
✅ Manual control over lifecycle transitions
✅ Optional long-term archival
✅ User decides when to tidy `archived/`

---

## Integration with StatusAuditor

### Future Enhancement: Automated Lifecycle Management

**Potential Auditor Integration**:
1. Auditor marks files with status during review
2. Automatically moves from `active/` to `reviewed/<status>/`
3. Optionally triggers tidy consolidation after review batch
4. Preserves Auditor decisions in SOT file metadata

**Example Entry in SOT File**:
```markdown
### DECISION-20251213-143022-file-organizer-auth-strategy
| Date | 2025-12-13 |
| Status | IMPLEMENTED |
| Auditor Review | 2025-12-13 |
| Implementation | auth-v2-hardening |
| Deferred Items | OAuth integration (Q2 2026) |

## Auditor Decision
- ✅ Implemented: JWT-based auth, session management
- ⏸️  Deferred: OAuth providers (complexity vs. value)
- ❌ Rejected: Basic auth (security concerns)

## Source Files
- archive/research/active/file-organizer-app-v1-20251213/research_auth.md
```

---

## Testing

### Verify Exclusion Works

```bash
# Create test files in active/
mkdir -p archive/research/active/test-project
echo "# Test File" > archive/research/active/test-project/test.md

# Run tidy (should skip active/)
python scripts/tidy/unified_tidy_directory.py archive/research --docs-only --dry-run

# Expected output:
# [SKIP] Excluded: archive/research/active/test-project/test.md
```

### Verify Reviewed Files Get Tidied

```bash
# Create test files in reviewed/
mkdir -p archive/research/reviewed/implemented/test-project
echo "# Implemented Feature" > archive/research/reviewed/implemented/test-project/feature.md

# Run tidy (should process reviewed/)
python scripts/tidy/unified_tidy_directory.py archive/research/reviewed --docs-only --dry-run

# Expected output:
# Processing archive/research/reviewed/implemented/test-project/feature.md...
```

---

## Documentation

**Created Files**:
1. ✅ [archive/research/README.md](README.md) - Complete lifecycle documentation
2. ✅ [archive/research/INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) - This file

**Updated Files**:
1. ✅ [scripts/tidy/consolidate_docs_v2.py](../../scripts/tidy/consolidate_docs_v2.py) - Added exclusion logic
2. ✅ [scripts/tidy/enhanced_file_cleanup.py](../../scripts/tidy/enhanced_file_cleanup.py) - Added exclusion logic

---

## Summary

**Problem**: Research directory used for Auditor workflow conflicted with tidy function

**Solution**: Lifecycle-based exclusion (active → reviewed → archived)

**Implementation**:
- `archive/research/active/` → EXCLUDED from tidy (safe staging)
- `archive/research/reviewed/` → INCLUDED in tidy (post-Auditor cleanup)
- `archive/research/archived/` → OPTIONAL tidy (user decides)

**Result**:
- ✅ Research workflow preserved
- ✅ No accidental tidying during Auditor review
- ✅ Historical research consolidated after review
- ✅ Auditor decisions tracked in SOT files

**Status**: ✅ Implemented and ready to use
