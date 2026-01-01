# Research Directory - Auditor Workflow Integration

**Purpose**: Staging area for research files awaiting Auditor review and processing

---

## Directory Structure

```
archive/research/
├── README.md (this file)
├── active/ (files awaiting Auditor review - NEVER auto-tidied)
├── reviewed/ (Auditor-processed files - safe to tidy)
└── archived/ (historical research - optional tidy)
```

---

## Lifecycle States

### 1. Active Research (`active/`)
**Status**: Awaiting Auditor Review
**Tidy Behavior**: **EXCLUDED** - Never auto-tidied

**Usage**:
```bash
# Research agents compile files here
scripts/plan_hardening.py --project myproject --features auth,search
# → Outputs to archive/research/active/myproject-20251213/
```

**Contents**:
- Research agent outputs
- Planning kickoff prompts
- Template compilations
- Gathered context files

**When to Archive**: After Auditor review completes

---

### 2. Reviewed (`reviewed/`)
**Status**: Auditor Review Complete
**Tidy Behavior**: **INCLUDED** - Safe to consolidate

**Auditor Actions**:
- ✅ Implemented → Mark as IMPLEMENTED, move to `reviewed/implemented/`
- ⏸️  Deferred → Mark as PENDING, move to `reviewed/deferred/`
- ❌ Discarded → Mark as REJECTED, move to `reviewed/rejected/`

**Tidy Process**:
```bash
# After Auditor review, tidy the reviewed files
python scripts/tidy/unified_tidy_directory.py archive/research/reviewed --full --execute

# Result:
# - .md files → docs/BUILD_HISTORY.md (status: IMPLEMENTED/PENDING/REJECTED)
# - Other files → organized by type
```

---

### 3. Archived (`archived/`)
**Status**: Long-term Reference
**Tidy Behavior**: **OPTIONAL** - User decides

**Purpose**:
- Historical research projects
- Reference material for future planning
- Preserved in original structure

**Tidy Decision**:
```bash
# Option A: Preserve as-is (don't tidy)
# → Keep original directory structure for historical reference

# Option B: Consolidate (tidy)
python scripts/tidy/unified_tidy_directory.py archive/research/archived --docs-only --execute
# → Extract strategic insights into SOT files
```

---

## Integration with Tidy Function

### Current Exclusion (Default)
The tidy function currently **excludes** entire `archive/research/` directory by default.

### Recommended Update
Exclude only `active/` subdirectory:

**In `enhanced_file_cleanup.py` and `consolidate_docs_v2.py`**:
```python
# Exclusion patterns
keep_dirs = {
    self.archive_dir / "tidy_v7",
    self.archive_dir / "prompts",
    self.archive_dir / "research" / "active",  # ← Exclude active research only
    # ... other exclusions
}
```

**Result**:
- `archive/research/active/` → NEVER tidied (safe staging area)
- `archive/research/reviewed/` → Can be tidied
- `archive/research/archived/` → Can be tidied (if you want)

---

## Workflow Example

### Step 1: Research Agents Gather Files
```bash
# Planning trigger creates research compilation
python scripts/plan_hardening.py --project file-organizer-app-v1 --features auth,search,batch,frontend

# Output location
archive/research/active/file-organizer-app-v1-20251213/
├── phase_templates.json
├── research_auth.md
├── research_search.md
├── planning_context.md
└── kickoff_prompt.md
```

### Step 2: Auditor Reviews Files
**Auditor Process**:
1. Read all files in `archive/research/active/file-organizer-app-v1-20251213/`
2. Analyze, revise, produce comprehensive plan
3. Mark each file:
   - IMPLEMENTED → `reviewed/implemented/file-organizer-app-v1-20251213/`
   - PENDING → `reviewed/deferred/file-organizer-app-v1-20251213/`
   - REJECTED → `reviewed/rejected/file-organizer-app-v1-20251213/`

**Manual Move**:
```bash
# After Auditor review, move to appropriate reviewed/ subdirectory
mv archive/research/active/file-organizer-app-v1-20251213 \
   archive/research/reviewed/implemented/
```

### Step 3: Tidy Reviewed Files
```bash
# Preview consolidation
python scripts/tidy/unified_tidy_directory.py archive/research/reviewed --docs-only --dry-run

# Execute consolidation
python scripts/tidy/unified_tidy_directory.py archive/research/reviewed --docs-only --execute

# Result:
# - Research files consolidated into docs/ARCHITECTURE_DECISIONS.md
# - Original project context preserved in SOT files
# - Chronologically sorted for historical reference
```

### Step 4: Long-term Archival (Optional)
```bash
# Optionally move to archived/ for long-term reference
mv archive/research/reviewed/implemented/file-organizer-app-v1-20251213 \
   archive/research/archived/2025/
```

---

## Integration with StatusAuditor

### Auditor Metadata
When Auditor processes files, it can add status metadata:

**Example Entry in SOT File**:
```markdown
### DECISION-20251213-143022-file-organizer-auth-strategy
| Date | 2025-12-13 |
| Status | IMPLEMENTED |
| Auditor Review | 2025-12-13 |
| Implementation | auth-v2-hardening |
| Deferred Items | OAuth integration (Q2 2026) |

## Summary
Authentication strategy for file-organizer-app-v1 based on research compilation...

## Auditor Decision
- ✅ Implemented: JWT-based auth, session management
- ⏸️  Deferred: OAuth providers (complexity vs. value)
- ❌ Rejected: Basic auth (security concerns)

## Source Files
- archive/research/active/file-organizer-app-v1-20251213/research_auth.md
- templates/hardening_phases.json (auth phase)
```

---

## Automation Opportunities

### Option A: Post-Auditor Hook
Create a script that runs after Auditor review:

```bash
# scripts/post_auditor_review.py
# Automatically moves files from active/ to reviewed/ based on Auditor status
```

### Option B: Auditor Integration
Enhance Auditor to automatically:
1. Mark files with status (IMPLEMENTED/PENDING/REJECTED)
2. Move from `active/` to `reviewed/<status>/`
3. Optionally trigger tidy consolidation

---

## Best Practices

### DO:
✅ Keep `active/` for **current research** only
✅ Move to `reviewed/` **after Auditor processes**
✅ Tidy `reviewed/` **periodically** to prevent clutter
✅ Use subdirectories (`implemented/`, `deferred/`, `rejected/`) for organization
✅ Preserve Auditor decisions in SOT file metadata

### DON'T:
❌ Run tidy on `active/` (breaks workflow)
❌ Leave files in `active/` indefinitely
❌ Delete research files before Auditor review
❌ Mix active and reviewed files in same directory

---

## Current State Recommendations

### Immediate Action
1. Create directory structure:
   ```bash
   mkdir -p archive/research/active
   mkdir -p archive/research/reviewed/implemented
   mkdir -p archive/research/reviewed/deferred
   mkdir -p archive/research/reviewed/rejected
   mkdir -p archive/research/archived
   ```

2. Move existing research files to appropriate locations:
   ```bash
   # If files are already reviewed → move to reviewed/
   # If files are awaiting review → move to active/
   ```

3. Update tidy exclusions to exclude only `archive/research/active/`

### Future Enhancements
1. **Auditor Integration**: Enhance StatusAuditor to automatically manage lifecycle transitions
2. **Automated Tidy**: Trigger tidy on `reviewed/` after batch of files reviewed
3. **Research Dashboard**: Track active vs. reviewed research projects
4. **Retention Policy**: Auto-archive reviewed files older than X months

---

## Summary

**Lifecycle Flow**:
```
Research Agents
    ↓
archive/research/active/
    ↓
Auditor Review
    ↓
archive/research/reviewed/{implemented,deferred,rejected}/
    ↓
Tidy Consolidation
    ↓
docs/ARCHITECTURE_DECISIONS.md (with Auditor metadata)
    ↓ (optional)
archive/research/archived/ (long-term reference)
```

**Tidy Behavior**:
- `active/` → ❌ EXCLUDED (never tidied)
- `reviewed/` → ✅ INCLUDED (safe to tidy)
- `archived/` → ⚙️ OPTIONAL (user decides)

**Benefits**:
- ✅ Research workflow preserved (no accidental tidying during Auditor review)
- ✅ Historical research consolidated (prevents clutter accumulation)
- ✅ Auditor decisions tracked (IMPLEMENTED/PENDING/REJECTED metadata)
- ✅ Flexibility maintained (manual vs. automated transitions)
