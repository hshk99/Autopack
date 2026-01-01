# BUILD-123v2 Pattern Matcher Refinements

## Date: 2025-12-22

## Changes Made

### 1. Removed Overly Broad Anchor Directories

**Problem**: Categories `autonomous_executor` and `governance` used `src/autopack/` as anchor directory, which includes 186+ files.

**Fix**: Changed to use specific file templates only, removed broad anchor_dirs:

```python
"autonomous_executor": {
    "keywords": ["autonomous executor", "builder client", "autonomous loop", ...],
    "anchor_dirs": [],  # Was: ["src/autopack"]
    "scope_templates": [
        "src/autopack/autonomous_executor.py",  # Specific files only
        "src/autopack/builder.py",
        "src/autopack/runner.py"
    ]
}
```

### 2. Made Keywords More Specific

**Problem**: Single-word keywords like "auth", "executor" caused false matches.

**Fix**: Changed to multi-word phrases for better specificity:

```python
# Before:
"keywords": ["autonomous", "executor", "builder", "runner", ...]

# After:
"keywords": ["autonomous executor", "builder client", "autonomous loop", ...]
```

### 3. Added File Count Limits

**Problem**: Pattern matching could expand to thousands of files from a single anchor directory.

**Fix**: Added `MAX_SCOPE_FILES = 100` constant and enforcement at three levels:

1. **Per anchor directory**: Limit files under each anchor to 100
2. **Per template**: Limit matches per template to 100
3. **Total scope**: Final check limits total scope to 100

```python
class PatternMatcher:
    MAX_SCOPE_FILES = 100

    def _generate_scope(self, category, patterns):
        # Limit 1: Per anchor
        if len(anchor_files_list) > self.MAX_SCOPE_FILES:
            anchor_files_list = anchor_files_list[:self.MAX_SCOPE_FILES]

        # Limit 2: Per template
        if len(matched) > self.MAX_SCOPE_FILES:
            matched = matched[:self.MAX_SCOPE_FILES]

        # Limit 3: Total
        if len(scope_paths) > self.MAX_SCOPE_FILES:
            scope_paths = scope_paths[:self.MAX_SCOPE_FILES]
```

### 4. Added Warning Logging

Added warnings when limits are hit to help debug and tune patterns:

```python
logger.warning(
    f"Category '{category}' anchor '{anchor}' has {len(anchor_files_list)} files, "
    f"limiting to {self.MAX_SCOPE_FILES} most recently modified"
)
```

## Current Status

### What Works ✅
1. **File count limits enforced** - No category can expand beyond 100 files
2. **Specific keywords** - Reduced false positive matches
3. **No broad anchors** - Removed problematic `src/autopack/` anchor
4. **Fix verification** - Bug fix from dict comparison to lambda key tested

### Remaining Issues ⚠️

1. **Readonly context not limited** - The `readonly_templates` expansion isn't counted in scope limits, causing validation failures when readonly files + scope files exceed limits

2. **Category fallthrough** - When no category matches well (e.g., authentication in a codebase without auth), it falls through to match unrelated categories like "config"

3. **Anchor detection too broad** - RepoScanner detects `src/autopack/` as an anchor for many categories because it contains files matching keywords (config.py, memory/, etc.)

4. **Multi-template accumulation** - Even with 100-file-per-template limit, multiple templates can accumulate to exceed preflight validator's 100-file-per-phase limit

## Recommended Next Steps

### Priority 1: Fix Readonly Context Counting
The preflight validator counts files expanded from readonly_context directories, which weren't limited in pattern_matcher. Two options:

**Option A**: Don't expand directories in readonly_context for counting purposes
**Option B**: Apply same limits to readonly_context as scope_paths

### Priority 2: Improve Category Matching
Add negative signals to scoring:
- Penalize categories when their anchor directories don't exist
- Require minimum keyword density (e.g., at least 2 keywords must match)
- Add category exclusion rules (e.g., "auth" goals shouldn't match "config")

### Priority 3: Tune Per Real Usage
Current patterns are theoretical. After real usage:
- Track which categories succeed/fail
- Identify common false positives
- Refine keyword lists based on actual goals
- Adjust confidence thresholds

## Testing

### Test Cases Created
1. `examples/minimal_plan_example.json` - Generic auth/API/database goals
2. `examples/autopack_maintenance_plan.json` - Autopack-specific goals

### Current Test Results
- **Generic goals** (auth, API): Correctly returns low confidence/empty scope (no auth files exist)
- **Autopack goals** (executor, governance): Matches too broadly, triggers size limits
- **Size limits**: Working as intended (prevents runaway expansion)
- **Governance**: Correctly blocks protected paths

## Additional Refinements (Part 2)

### 5. Applied File Limits to Readonly Context

**Problem**: Readonly context expansion wasn't counted in scope limits, causing validation failures.

**Fix**: Applied same `MAX_SCOPE_FILES = 100` limit to `_generate_readonly_context()` method:
- Per template: limit to 100 files
- Total readonly context: limit to 100 files
- Added warning logging

### 6. Required Keyword Match for All Categories

**Problem**: Categories with anchor directories but zero keyword matches were scoring high (e.g., "config" at 60% with 0% match_density).

**Fix**: Added hard requirement in `match()` method:
```python
if best_score["match_density"] == 0.0:
    # No keywords matched - return empty scope
    return self._generic_scope(goal, phase_id)
```

### 7. Lowered Confidence Threshold

**Problem**: After removing broad anchors, template-only matches scored 15-20% (below 30% threshold).

**Fix**: Lowered `MIN_CONFIDENCE_THRESHOLD` from 0.30 to 0.15 in both:
- `manifest_generator.py`
- `pattern_matcher.py`

This allows matches based on keyword + templates without requiring anchor directories.

### 8. Fixed Tests Category Anchor

**Problem**: Tests category used broad `anchor_dirs: ["tests", "test"]` which matched protected `src/autopack/tests/`.

**Fix**: Removed anchor_dirs, use specific templates only:
```python
"anchor_dirs": [],  # Don't use broad anchor
"scope_templates": [
    "tests/**/*.py",  # Root-level tests only
    "test/**/*.py"
]
```

## Conclusion

The "too broad" issue has been **significantly addressed**:
- ✅ File count limits prevent catastrophic expansion (5928 → 100 files)
- ✅ Removed broad `src/autopack/` anchors from autonomous_executor and governance
- ✅ Readonly context properly limited
- ✅ Keyword match required (no more 0% match_density wins)
- ✅ Tests category no longer includes protected paths
- ⚠️ Config category still has broad anchor (needs removal)

The system is now **much safer and more accurate**:
- **Safety**: File counts capped at 100, readonly context limited
- **Accuracy**: Requires keyword matches, prevents false positives
- **Flexibility**: Lower 15% threshold allows template-only matches

### Remaining Known Issue

**Config category still too broad**: The "config" category still has `anchor_dirs: ["src/autopack/"]` which causes it to score 60% even with zero keyword matches. Because of the keyword requirement, it correctly returns empty scope, but it's still the "best match" which is misleading.

**Fix needed**: Remove broad anchor from config category, use specific templates like `src/autopack/config.py`.

For production use, recommend:
1. Start with medium-confidence matches (>15%)
2. Empty scope (0%) triggers LLM fallback or manual definition
3. Collect metrics on category match accuracy for tuning
4. Refine patterns based on real-world goal keywords
