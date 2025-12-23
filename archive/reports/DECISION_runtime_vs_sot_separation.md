# DECISION: Runtime Configuration vs SOT File Separation

**Date**: 2025-12-13
**Status**: ✅ IMPLEMENTED
**Category**: architecture

## Context
During the LEARNED_RULES.json architecture restructure, we discovered that Autopack's `docs/LEARNED_RULES.json` contained runtime configuration (category_defaults, safety_profiles) rather than actual learned rules. This led to the decision to clearly separate runtime configuration from Single Source of Truth (SOT) files.

## Problem
- `docs/LEARNED_RULES.json` mixed two concerns: **runtime configuration** and **learned rules**
- File-organizer's LEARNED_RULES.json properly contained only learned rules (2830 lines)
- Autopack's LEARNED_RULES.json was purely configuration, not rules
- No clear distinction between what belongs in SOT vs what belongs in runtime cache
- Users and developers confused about file purpose

## Decision

**We will separate runtime configuration from SOT files by:**

1. **Runtime Configuration** → `.autonomous_runs/{project}/RUN_CONFIG.json`
   - Purpose: Transient runtime settings, execution parameters
   - Location: `.autonomous_runs/` (runtime cache directory)
   - Not tracked as SOT
   - Can be regenerated or modified per run

2. **Learned Rules (SOT)** → `docs/LEARNED_RULES.json`
   - Purpose: Permanent learned rules from autonomous execution
   - Location: `docs/` (SOT directory)
   - Tracked as 6th SOT file
   - Auto-updated by executor, not manually edited

## Rationale

### Why Separate?
1. **Different Lifecycles**:
   - Runtime config: Modified per execution, temporary
   - Learned rules: Accumulate over time, permanent

2. **Different Update Mechanisms**:
   - Runtime config: Set at start of run, modified during execution
   - Learned rules: Appended at end of successful runs via `promote_hints_to_rules()`

3. **Different Visibility**:
   - Runtime config: Internal execution details
   - Learned rules: Part of project knowledge base (SOT)

4. **Different Volatility**:
   - Runtime config: High volatility (can change every run)
   - Learned rules: Low volatility (only grows with new learnings)

### Why RUN_CONFIG.json?
- Clear naming: "RUN_CONFIG" explicitly indicates runtime purpose
- Consistent location: `.autonomous_runs/` is already established as runtime cache
- Parallel structure: Each project can have its own RUN_CONFIG.json
- No confusion: Can't be mistaken for SOT file

### Why Keep LEARNED_RULES.json in docs/?
- Historical consistency: File-organizer already uses this pattern
- SOT integration: Part of 6-file SOT structure
- Auto-update mechanism: Executor already has `promote_hints_to_rules()` logic
- Semantic search: Can be indexed by Qdrant for learning retrieval

## Alternatives Considered

### Alternative 1: Keep Everything in LEARNED_RULES.json
**Rejected because**:
- Mixes concerns (config + learned rules)
- Unclear file purpose
- Difficult to distinguish what's SOT vs what's runtime

### Alternative 2: Move LEARNED_RULES.json to .autonomous_runs/
**Rejected because**:
- Breaks file-organizer's existing 2830 lines of learned rules
- Loses SOT status
- Makes learned rules invisible to documentation sync
- Harder to version control and track

### Alternative 3: Create config/ directory for runtime config
**Rejected because**:
- `config/` directory is for static configuration (YAML files)
- Runtime config is dynamic, not static
- Confuses static vs dynamic config

## Consequences

### Positive
✅ Clear separation of concerns (runtime vs permanent knowledge)
✅ LEARNED_RULES.json now properly represents actual learned rules
✅ Runtime config isolated and easy to modify per run
✅ 6-file SOT structure clarified with LEARNED_RULES.json as 6th file
✅ No data loss during migration
✅ Consistent architecture across Autopack and sub-projects

### Negative
⚠️ Requires migration of existing Autopack config to RUN_CONFIG.json (DONE)
⚠️ Developers need to understand the distinction
⚠️ Two files instead of one (but clear purpose for each)

### Trade-offs
- **Simplicity vs Clarity**: Chose clarity (two files with clear purposes) over simplicity (one file mixing concerns)
- **Migration Cost vs Long-term Maintainability**: One-time migration cost for long-term architectural clarity

## Implementation

### Files Created
1. `.autonomous_runs/autopack/RUN_CONFIG.json` - Runtime configuration
   ```json
   {
     "category_defaults": {...},
     "safety_profiles": {...},
     "high_risk_categories": [...],
     "run_token_cap": 200000
   }
   ```

2. `docs/LEARNED_RULES.json` - Learned rules (empty initially)
   ```json
   {
     "rules": []
   }
   ```

### Files Modified
1. `src/autopack/learned_rules.py:665-675` - Updated path resolution
2. `docs/LEARNED_RULES.json` - Replaced config with empty rules

### Files Preserved
1. `.autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json` - 2830 lines intact

## Verification

```bash
# Runtime config in correct location
cat .autonomous_runs/autopack/RUN_CONFIG.json
# Should show: category_defaults, safety_profiles, etc.

# Learned rules in SOT location (empty for Autopack)
cat docs/LEARNED_RULES.json
# Should show: {"rules": []}

# File-organizer learned rules preserved
wc -l .autonomous_runs/file-organizer-app-v1/docs/LEARNED_RULES.json
# Should show: 2830 lines
```

## Related Decisions
- **DECISION-XXX**: 6-File SOT Structure (LEARNED_RULES.json as 6th file)
- **BUILD-XXX**: LEARNED_RULES.json Architecture Restructure
- **BUILD-XXX**: Database Sync Integration (doesn't sync LEARNED_RULES.json - different trigger)

## Status
✅ **IMPLEMENTED** - Migration complete, all data preserved, architecture clarified.

## Next Steps
- ✅ Update ref2.md to document this separation
- ✅ Update tidy system documentation
- 🎯 Monitor executor runs to ensure LEARNED_RULES.json auto-update working correctly
