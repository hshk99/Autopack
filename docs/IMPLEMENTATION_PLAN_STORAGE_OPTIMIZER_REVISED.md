# Storage Optimizer Implementation Plan (REVISED with Policy Integration)

**Date**: 2026-01-01
**Version**: 2.0 (Policy-Aware)
**Status**: Ready for Implementation

---

## 🔄 Key Changes from V1.0

### Policy Integration Added

The original plan has been updated to integrate with:
- **[DATA_RETENTION_AND_STORAGE_POLICY.md](DATA_RETENTION_AND_STORAGE_POLICY.md)** - Canonical policy
- **[config/storage_policy.yaml](../config/storage_policy.yaml)** - Machine-readable policy ✅ **Already exists!**

### Critical Policy Requirements

1. **NEVER delete protected paths** (SOT, src/, tests/, .git/, databases, archive/superseded/)
2. **Policy-first classification** - Load policy before classifying
3. **Retention windows respected** - Don't delete within retention periods
4. **Tidy-first coordination** - Storage Optimizer defers to Tidy for archive/ management
5. **Retrieval artifacts protected** - Don't break Autopack's runtime retrieval

---

## 📋 Simplified Build Plan

Given token constraints and the policy complexity, here's a streamlined approach:

### What's Already Done ✅

1. ✅ Research complete (Phase 1)
   - WizTree CLI integration researched
   - Scanner comparison complete
   - Windows cleanup APIs documented
   - Prototype scanner working

2. ✅ Policy infrastructure created
   - `config/storage_policy.yaml` exists
   - `docs/DATA_RETENTION_AND_STORAGE_POLICY.md` canonical

### What Needs to Be Built

**Option A: Full Implementation** (~20-26 hours)
- Build all 10 phases as originally planned
- High token cost
- Full-featured system

**Option B: Minimal Viable Product (MVP)** (~8-10 hours) **RECOMMENDED**
- Core scanning + classification + reporting
- Manual cleanup (no automation yet)
- Policy-aware from day 1
- Lower token cost
- Can expand later

---

## 🎯 MVP Approach (Recommended)

### MVP Scope

**Build**:
1. Policy loader (`policy.py`)
2. Basic scanner (Python fallback only, defer WizTree)
3. Policy-aware classifier
4. Dry-run cleanup planner
5. Report generator
6. CLI tools for manual execution

**Skip for MVP**:
- WizTree integration (use Python scanner)
- Automated scheduling
- send2trash integration (use dry-run only)
- Autopack executor integration
- Integration tests

**Rationale**:
- Get value quickly (reports showing cleanup opportunities)
- Validate policy integration first
- Avoid token-heavy executor integration
- Can add features incrementally

---

## MVP Implementation Guide

### Phase 1: Policy Loader (New)

**File**: `src/autopack/storage_optimizer/policy.py`

```python
"""
Policy loader for storage retention and safety rules.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class CategoryPolicy:
    """Policy for a storage category."""
    name: str
    match_globs: List[str]
    delete_enabled: bool
    delete_requires_approval: bool
    compress_enabled: bool
    compress_requires_approval: bool

@dataclass
class RetentionPolicy:
    """Retention windows for a category."""
    compress_after_days: Optional[int]
    delete_after_days: Optional[int]
    delete_requires_approval: bool

@dataclass
class StoragePolicy:
    """Complete storage policy."""
    version: str
    protected_globs: List[str]
    categories: Dict[str, CategoryPolicy]
    retention: Dict[str, RetentionPolicy]

def load_policy(policy_path: Optional[Path] = None) -> StoragePolicy:
    """Load storage policy from YAML."""
    if policy_path is None:
        # Default to repo config
        policy_path = Path(__file__).parent.parent.parent.parent / "config" / "storage_policy.yaml"

    with open(policy_path, 'r') as f:
        data = yaml.safe_load(f)

    # Parse protected paths
    protected_globs = data.get('paths', {}).get('protected_globs', [])

    # Parse categories
    categories = {}
    for cat_name, cat_data in data.get('categories', {}).items():
        match_globs = cat_data.get('match_globs', [])
        actions = cat_data.get('allowed_actions', {})

        delete_action = actions.get('delete', {})
        compress_action = actions.get('compress', {})

        categories[cat_name] = CategoryPolicy(
            name=cat_name,
            match_globs=match_globs,
            delete_enabled=delete_action.get('enabled', False),
            delete_requires_approval=delete_action.get('requires_approval', True),
            compress_enabled=compress_action.get('enabled', False),
            compress_requires_approval=compress_action.get('requires_approval', False)
        )

    # Parse retention
    retention = {}
    for ret_name, ret_data in data.get('retention_days', {}).items():
        retention[ret_name] = RetentionPolicy(
            compress_after_days=ret_data.get('compress_after'),
            delete_after_days=ret_data.get('delete_after'),
            delete_requires_approval=ret_data.get('delete_requires_approval', True)
        )

    return StoragePolicy(
        version=data.get('version', '1.0'),
        protected_globs=protected_globs,
        categories=categories,
        retention=retention
    )

def is_path_protected(path: str, policy: StoragePolicy) -> bool:
    """Check if a path is protected by policy."""
    import fnmatch

    # Normalize path to POSIX style
    normalized = path.replace('\\', '/')

    for glob_pattern in policy.protected_globs:
        if fnmatch.fnmatch(normalized, glob_pattern):
            return True

    return False
```

**Acceptance**: Can load policy, check protected paths

---

### Phase 2: Core Models (Simplified)

**File**: `src/autopack/storage_optimizer/models.py`

Only essential models for MVP:
- `ScanResult` - What we find
- `CleanupCandidate` - What could be deleted
- `CleanupPlan` - Collection of candidates
- `StorageReport` - Summary for user

Skip: `CleanupResult` (not executing yet), complex enums

---

### Phase 3: Simple Scanner

**File**: `src/autopack/storage_optimizer/scanner.py`

Use Python `os.walk` only (skip WizTree for MVP):
- Scan specified directories
- Return `ScanResult` objects
- Simple, no caching needed for MVP

---

### Phase 4: Policy-Aware Classifier

**File**: `src/autopack/storage_optimizer/classifier.py`

Key changes from original plan:
1. **Load policy first**
2. **Check protected paths** before classifying
3. **Use policy categories** instead of hardcoded rules
4. **Respect retention windows**

```python
class FileClassifier:
    def __init__(self, policy: StoragePolicy):
        self.policy = policy

    def classify(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        # 1. Check if protected
        if is_path_protected(scan_result.path, self.policy):
            return None  # Never classify protected paths

        # 2. Match against policy categories
        for cat_name, cat_policy in self.policy.categories.items():
            if self._matches_category(scan_result.path, cat_policy):
                # Check retention window
                if not self._within_retention(scan_result, cat_name):
                    return CleanupCandidate(
                        path=scan_result.path,
                        category=cat_name,
                        size_bytes=scan_result.size_bytes,
                        can_auto_delete=not cat_policy.delete_requires_approval,
                        reason=f"Matched category: {cat_name}"
                    )

        return None
```

---

### Phase 5: Report Generator

**File**: `src/autopack/storage_optimizer/reporter.py`

Generate human-readable reports:
- What was found
- Policy-protected items (excluded from cleanup)
- Cleanup candidates (by category)
- Potential savings
- Required approvals

---

### Phase 6: CLI Tool

**File**: `scripts/storage/scan_and_report.py`

Simple CLI:
```bash
# Scan and generate report
python scripts/storage/scan_and_report.py

# Scan specific directory
python scripts/storage/scan_and_report.py --dir c:/dev

# Output to file
python scripts/storage/scan_and_report.py --output report.txt
```

---

## MVP Deliverables

After implementing MVP, you'll have:

1. ✅ Working scanner (Python-based)
2. ✅ Policy-aware classification
3. ✅ Protected paths enforced
4. ✅ Retention windows respected
5. ✅ Detailed reports showing:
   - Total disk usage
   - What's protected (and why)
   - What could be cleaned (by category)
   - Potential savings
   - What requires approval
6. ✅ Manual execution via CLI

### What It Won't Do (Yet)

- ❌ Automated scheduling
- ❌ Actual deletion (dry-run only)
- ❌ WizTree integration (slower Python scan)
- ❌ Autopack executor integration
- ❌ send2trash (Recycle Bin)

---

## Future Expansion Path

### Phase 2: Add Execution

Once MVP is validated:
1. Add send2trash for safe deletion
2. Implement approval workflow
3. Add actual cleanup executor
4. Test on small directories first

### Phase 3: Add Automation

After manual execution works:
1. Add Windows Task Scheduler integration
2. Create automated reports
3. Add email notifications

### Phase 4: Optimize Performance

After automation works:
1. Integrate WizTree for faster scanning
2. Add caching layer
3. Parallelize scanning

### Phase 5: Full Integration

Final step:
1. Integrate with Autopack executor
2. Add to autonomous maintenance workflow
3. Create integration tests

---

## Estimated Effort

### MVP (Recommended First)
- **Policy loader**: 1 hour
- **Models**: 1 hour
- **Scanner (Python)**: 1-2 hours
- **Classifier (policy-aware)**: 2-3 hours
- **Reporter**: 1-2 hours
- **CLI tool**: 1 hour
- **Testing/validation**: 1-2 hours

**Total MVP**: ~8-10 hours

### Full System (After MVP)
- **Execution layer**: 2-3 hours
- **Automation**: 1-2 hours
- **WizTree integration**: 2-3 hours
- **Executor integration**: 2-3 hours
- **Integration tests**: 2-3 hours

**Total additional**: ~10-14 hours

**Grand Total**: ~20-24 hours (split across 2 phases)

---

## Recommendation: Build MVP First

**Why MVP First?**

1. **Validate policy integration** - Most complex part
2. **Get immediate value** - See what can be cleaned
3. **Lower risk** - No deletion, just reporting
4. **Incremental** - Add features as needed
5. **Token efficient** - Smaller scope

**Why Not Full Build?**

1. **High token cost** - Large implementation
2. **Risky** - Deletion is dangerous if policy is wrong
3. **May not need all features** - MVP might be enough
4. **Harder to test** - More moving parts

---

## Decision Point

**Choose one**:

### Option A: Build MVP Now
- Implement policy loader + scanner + classifier + reporter
- Get reports showing cleanup opportunities
- Validate policy works correctly
- Defer execution/automation

### Option B: Build Full System Now
- Implement all 10 phases from original plan
- Higher token cost
- More risk
- Longer time to value

### Option C: Build Nothing Now
- Review research and plans
- Wait for specific need
- Use manual cleanup for now

**My Recommendation**: **Option A (MVP)**

Start with reports and policy validation. Once you see the value and trust the policy, add execution features incrementally.

---

## Next Steps

If choosing **MVP** (recommended):

1. Review this plan
2. Confirm policy file (`config/storage_policy.yaml`) is correct
3. Decide: Who builds it?
   - Option 1: I build it now (fast, low token cost)
   - Option 2: Autopack builds it (autonomous, higher token cost)
   - Option 3: Defer for later

Let me know your preference!

---

**Status**: Ready for Decision
**Recommendation**: Build MVP (Option A)
**Build By**: Claude (most efficient)
**Time**: ~2-3 hours of implementation
