# Automated Research → Auditor → SOT Workflow

**Purpose**: Fully automated pipeline from research gathering to SOT file consolidation
**Status**: ✅ IMPLEMENTED
**Date**: 2025-12-13

---

## Complete Automated Flow

```
Research Agents
    ↓ (gather info)
archive/research/active/<project-name-date>/
    ↓ (trigger planning)
scripts/plan_hardening.py
    ↓ (Auditor analyzes)
archive/research/reviewed/temp/<compiled-files>
    ↓ (discussion/refinement)
archive/research/reviewed/{implemented,deferred,rejected}/
    ↓ (automated consolidation)
scripts/research/auto_consolidate_research.py
    ↓ (smart routing)
docs/{BUILD_HISTORY.md, ARCHITECTURE_DECISIONS.md, REJECTED_IDEAS.md}
```

---

## SOT File Strategy

| Research Status | Destination SOT File | Status Tag | Purpose |
|-----------------|---------------------|------------|---------|
| **IMPLEMENTED** | `docs/BUILD_HISTORY.md` | IMPLEMENTED | Features/plans that got built |
| **DEFERRED** | `docs/ARCHITECTURE_DECISIONS.md` | PENDING_ACTIVE | Ideas we might adopt later (with deferral reasons) |
| **REJECTED** | `docs/ARCHITECTURE_DECISIONS.md` | REJECTED | Ideas to prevent re-considering (with rejection reasons) |

### Why This Approach?

**For IMPLEMENTED**:
- Goes to BUILD_HISTORY.md (what was built)
- Natural fit for completed features
- Chronologically sorted

**For DEFERRED** (NOT separate FUTURE_PLANS.md):
- Goes to ARCHITECTURE_DECISIONS.md with PENDING_ACTIVE status
- Reason: Deferred decisions ARE architectural decisions
- Includes deferral rationale, blockers, potential timeline
- Prevents duplication between FUTURE_PLANS and ARCHITECTURE_DECISIONS

**For REJECTED** (NOT separate REJECTED_IDEAS.md):
- Goes to ARCHITECTURE_DECISIONS.md with REJECTED status
- Reason: Cursor/Autopack can reference ARCHITECTURE_DECISIONS to avoid rejected approaches
- Includes rejection rationale, alternatives considered, lessons learned
- Prevents circular discussions about already-rejected ideas

---

## Automated Consolidation Script

### Location
`scripts/research/auto_consolidate_research.py`

### Usage

```bash
# Preview what will be consolidated
python scripts/research/auto_consolidate_research.py --dry-run

# Execute consolidation
python scripts/research/auto_consolidate_research.py --execute
```

### What It Does

1. **Scans reviewed/ subdirectories**:
   - `archive/research/reviewed/implemented/`
   - `archive/research/reviewed/deferred/`
   - `archive/research/reviewed/rejected/`

2. **Consolidates with forced routing**:
   - `implemented/` → BUILD_HISTORY.md (status: IMPLEMENTED)
   - `deferred/` → ARCHITECTURE_DECISIONS.md (status: PENDING_ACTIVE)
   - `rejected/` → ARCHITECTURE_DECISIONS.md (status: REJECTED)

3. **Preserves metadata**:
   - Deferral reasons (for PENDING_ACTIVE)
   - Rejection rationale (for REJECTED)
   - Source file references
   - Chronological ordering

---

## Integration with plan_hardening.py

### Current Planning Trigger

```bash
python scripts/plan_hardening.py --project file-organizer-app-v1 --features auth,search,batch,frontend
```

**Outputs research to**: (recommended)
```
archive/research/active/file-organizer-app-v1-20251213/
├── phase_templates.json
├── research_auth.md
├── research_search.md
├── kickoff_prompt.md
└── context_compilation.md
```

### Recommended Enhancement

**Add post-Auditor consolidation hook** to `plan_hardening.py`:

```python
# At end of plan_hardening.py, after Auditor review

def consolidate_research_post_auditor(project_name: str):
    """Automatically consolidate research files after Auditor review"""
    import subprocess

    print("\n" + "=" * 80)
    print("POST-AUDITOR: Consolidating Research")
    print("=" * 80)

    # Run automated consolidation
    result = subprocess.run([
        "python", "scripts/research/auto_consolidate_research.py", "--execute"
    ], cwd=REPO_ROOT)

    if result.returncode == 0:
        print("✅ Research consolidated to SOT files")
        print("   - IMPLEMENTED → docs/BUILD_HISTORY.md")
        print("   - DEFERRED → docs/ARCHITECTURE_DECISIONS.md (PENDING_ACTIVE)")
        print("   - REJECTED → docs/ARCHITECTURE_DECISIONS.md (REJECTED)")
    else:
        print("❌ Research consolidation failed")

# Call after Auditor completes
consolidate_research_post_auditor(args.project)
```

---

## Lifecycle Management

### 1. Research Agents → Active

**Research agents gather files**:
```
archive/research/active/<project-name-date>/
└── (all research files)
```

**Tidy behavior**: ❌ EXCLUDED (never tidied)

**Manual step**: None (automated)

---

### 2. Auditor Analysis → Temp

**plan_hardening.py triggers Auditor**:
```python
python scripts/plan_hardening.py --project myproject --features auth,search
```

**Auditor produces compiled files**:
```
archive/research/reviewed/temp/<project-name-date>/
├── auditor_analysis.md
├── comprehensive_plan.md
└── implementation_roadmap.md
```

**Tidy behavior**: ✅ INCLUDED (can be tidied after review)

**Manual step**: Review Auditor output, discuss with team

---

### 3. Discussion → Categorization

**Move files based on decisions**:
```bash
# Implemented features
mv archive/research/reviewed/temp/myproject-20251213 \
   archive/research/reviewed/implemented/

# Deferred features (good idea, but not now)
mv archive/research/reviewed/temp/other-project \
   archive/research/reviewed/deferred/

# Rejected features (won't do)
mv archive/research/reviewed/temp/discarded-idea \
   archive/research/reviewed/rejected/
```

**Tidy behavior**: ✅ INCLUDED (ready for consolidation)

**Manual step**: Move directories based on discussion outcomes

---

### 4. Automated Consolidation → SOT

**Run consolidation script**:
```bash
python scripts/research/auto_consolidate_research.py --execute
```

**Result**:
- `implemented/` files → `docs/BUILD_HISTORY.md` (IMPLEMENTED)
- `deferred/` files → `docs/ARCHITECTURE_DECISIONS.md` (PENDING_ACTIVE, with deferral reasons)
- `rejected/` files → `docs/ARCHITECTURE_DECISIONS.md` (REJECTED, with rejection rationale)

**Tidy behavior**: ✅ Files now in SOT files, originals can be archived

**Manual step**: None (fully automated)

---

## Example Workflow

### Scenario: Planning auth + search features

#### Step 1: Research Gathering

```bash
# Trigger planning
python scripts/plan_hardening.py --project file-organizer-app-v1 --features auth,search

# Research agents gather into:
archive/research/active/file-organizer-app-v1-20251213/
├── research_auth.md
├── research_search.md
├── phase_templates.json
└── planning_context.md
```

#### Step 2: Auditor Analysis

**Auditor reviews all active files, produces**:
```
archive/research/reviewed/temp/file-organizer-app-v1-20251213/
├── AUDITOR_ANALYSIS.md
├── AUTH_PLAN.md (recommended: JWT-based, defer OAuth)
├── SEARCH_PLAN.md (recommended: implement, high priority)
└── IMPLEMENTATION_ROADMAP.md
```

#### Step 3: Team Discussion & Categorization

**Team decides**:
- ✅ Auth (JWT-based): IMPLEMENT NOW
- ⏸️  Auth (OAuth): DEFER (complexity vs. value)
- ✅ Search: IMPLEMENT NOW
- ❌ Full-text search: REJECT (use simple filtering for now)

**Manual moves**:
```bash
# Implemented: JWT auth + search
mv archive/research/reviewed/temp/file-organizer-app-v1-20251213 \
   archive/research/reviewed/implemented/

# Create separate files for deferred/rejected items
# (or Auditor creates them automatically)
```

#### Step 4: Automated Consolidation

```bash
python scripts/research/auto_consolidate_research.py --execute
```

**Result in docs/BUILD_HISTORY.md**:
```markdown
### BUILD-20251213-143022-file-organizer-auth-implementation
| Date | 2025-12-13 |
| Status | IMPLEMENTED |
| Source | archive/research/reviewed/implemented/file-organizer-app-v1-20251213/AUTH_PLAN.md |

## Summary
JWT-based authentication for file-organizer-app-v1...

## Implementation Details
- JWT token generation and validation
- Session management with Redis
- Secure password hashing (bcrypt)

## Deferred
- OAuth integration (complexity vs. value analysis → PENDING_ACTIVE)

## Source Files
- research_auth.md
- phase_templates.json (auth phase)
```

**Result in docs/ARCHITECTURE_DECISIONS.md**:
```markdown
### DECISION-20251213-143030-file-organizer-auth-oauth-deferred
| Date | 2025-12-13 |
| Status | PENDING_ACTIVE |
| Deferred Until | Q2 2026 or user demand |
| Source | archive/research/reviewed/deferred/.../OAUTH_ANALYSIS.md |

## Summary
OAuth provider integration for file-organizer-app-v1

## Deferral Rationale
- Complexity: Requires managing multiple OAuth providers (Google, GitHub, Microsoft)
- Current Value: Limited - most users ok with email/password
- Blocker: Need to establish user base first, then assess demand

## When to Revisit
- User requests exceed 10/month
- Enterprise clients require SSO
- Security audit recommends it

## Implementation Path (when ready)
1. Start with Google OAuth (most common)
2. Add GitHub (developer users)
3. Add Microsoft (enterprise users)
```

**Result in docs/ARCHITECTURE_DECISIONS.md** (rejected):
```markdown
### DECISION-20251213-143035-file-organizer-fulltext-search-rejected
| Date | 2025-12-13 |
| Status | REJECTED |
| Source | archive/research/reviewed/rejected/.../FULLTEXT_ANALYSIS.md |

## Summary
Full-text search using Elasticsearch for file-organizer-app-v1

## Rejection Rationale
- Complexity: Requires Elasticsearch infrastructure (deployment, maintenance)
- Current Need: Simple filtering sufficient for MVP
- Costs: Additional infrastructure costs not justified by current scale
- Alternative: Use simple SQL LIKE queries, optimize later if needed

## Alternatives Considered
1. Elasticsearch - REJECTED (too complex for current scale)
2. PostgreSQL full-text search - REJECTED (still overkill)
3. Simple LIKE queries - CHOSEN (sufficient for MVP)

## If This Changes
- User base > 10,000 files per user
- Performance degradation with current approach
- User feedback demands better search
```

---

## Benefits of Automated Workflow

### 1. Zero Manual Consolidation
✅ No need to manually copy/paste research into SOT files
✅ No risk of forgetting to consolidate important research
✅ Consistent formatting and metadata

### 2. Prevent Re-Consideration of Rejected Ideas
✅ REJECTED entries in ARCHITECTURE_DECISIONS.md
✅ Cursor/Autopack can reference to avoid suggesting rejected approaches
✅ Rejection rationale preserved for future reference

### 3. Track Deferred Items with Context
✅ PENDING_ACTIVE entries in ARCHITECTURE_DECISIONS.md
✅ Deferral reasons, blockers, and revisit criteria preserved
✅ Easy to search/filter for deferred items

### 4. Preserve Auditor Decisions
✅ Auditor analysis included in SOT file metadata
✅ Implementation path documented
✅ Trade-offs and alternatives preserved

### 5. Clean Research Directory
✅ Active research never tidied (safe staging)
✅ Reviewed research consolidated automatically
✅ No long-term clutter accumulation

---

## Exclusions (Already Implemented)

### Files Modified

1. **consolidate_docs_v2.py** (lines 547-549, 631-653):
   - Added `force_status` and `force_category` overrides
   - Supports automated workflow with forced routing

2. **consolidate_docs_v2.py** (lines 599-617):
   - Excludes `archive/research/active/` from tidy
   - Preserves research staging area

3. **enhanced_file_cleanup.py** (lines 46-51, 87-89):
   - Excludes `archive/research/active/` from all file type processing
   - Consistent exclusion across all cleanup operations

### Exclusion Behavior

| Directory | Tidy Behavior | Purpose |
|-----------|--------------|---------|
| `archive/research/active/` | ❌ EXCLUDED | Research awaiting Auditor review |
| `archive/research/reviewed/temp/` | ✅ INCLUDED | Auditor output (can tidy after review) |
| `archive/research/reviewed/implemented/` | ✅ INCLUDED | Ready for consolidation |
| `archive/research/reviewed/deferred/` | ✅ INCLUDED | Ready for consolidation |
| `archive/research/reviewed/rejected/` | ✅ INCLUDED | Ready for consolidation |
| `archive/research/archived/` | ⚙️ OPTIONAL | Long-term reference (user decides) |

---

## Status

**Implementation**: ✅ COMPLETE

**Scripts Created**:
1. ✅ `scripts/research/auto_consolidate_research.py` - Automated consolidation
2. ✅ `archive/research/README.md` - Lifecycle documentation
3. ✅ `archive/research/INTEGRATION_SUMMARY.md` - Technical details
4. ✅ `archive/research/AUTOMATED_WORKFLOW_GUIDE.md` - This file

**Scripts Modified**:
1. ✅ `scripts/tidy/consolidate_docs_v2.py` - Added force overrides, exclusions
2. ✅ `scripts/tidy/enhanced_file_cleanup.py` - Added exclusions

**Ready to Use**: ✅ YES

**Next Step**: Integrate with `scripts/plan_hardening.py` for full automation (optional)

---

## Quick Reference

### Daily Operations

```bash
# 1. Research agents gather (automated)
# → archive/research/active/<project>/

# 2. Trigger planning
python scripts/plan_hardening.py --project myproject --features auth,search

# 3. Review Auditor output
# → archive/research/reviewed/temp/<project>/

# 4. Categorize based on decisions (manual)
mv archive/research/reviewed/temp/<project> archive/research/reviewed/implemented/
# or deferred/ or rejected/

# 5. Consolidate to SOT files (automated)
python scripts/research/auto_consolidate_research.py --execute
```

### Verification

```bash
# Check what will be consolidated
python scripts/research/auto_consolidate_research.py --dry-run

# Verify SOT files after consolidation
grep -A 5 "PENDING_ACTIVE" docs/ARCHITECTURE_DECISIONS.md
grep -A 5 "REJECTED" docs/ARCHITECTURE_DECISIONS.md
grep -A 5 "IMPLEMENTED" docs/BUILD_HISTORY.md
```

---

**END OF GUIDE**
