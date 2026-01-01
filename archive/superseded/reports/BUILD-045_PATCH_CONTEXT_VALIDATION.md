# BUILD-045: Patch Context Validation

**Status**: ✅ COMPLETE
**Date**: 2025-12-17
**Priority**: MEDIUM
**Category**: Bug Fix / Reliability
**Predecessor**: BUILD-044 (Protected Path Isolation)

## Problem Statement

During FileOrganizer Phase 2 execution, **8% of phase failures** were caused by git apply rejecting patches due to context mismatches. LLM generated patches targeting the wrong file state, leading to:

1. **Git apply failures** - Patches couldn't be applied despite being syntactically valid
2. **Wasted retries** - Phases attempted 2-3 times with same context mismatch
3. **Goal drift indicator** - LLM generated code for outdated file understanding
4. **No early detection** - Failures only discovered during git apply, not upfront

### Affected Phases

From FileOrg Phase 2 analysis:

| Phase | Failure Reason | Symptom |
|-------|----------------|---------|
| **fileorg-p2-frontend-build** (Attempt 2) | git_apply_failed_existing_files_no_fallback | Context mismatch in package.json |
| **fileorg-p2-patch-apply** (Attempt 2) | git_apply_failed_existing_files_no_fallback | Hunk line numbers didn't match |

**Total**: 2 phases (8% of failures), goal drift similarity scores: -0.00 to 0.01

**Log Evidence**:
```
[2025-12-17 03:49:30] ERROR: [Integrity] Patch modifies existing files. Skipping direct-write fallback to avoid partial apply.
[2025-12-17 03:49:30] ERROR: [fileorg-p2-frontend-build] Failed to apply patch to filesystem: git_apply_failed_existing_files_no_fallback
[2025-12-17 03:49:30] WARNING: [fileorg-p2-frontend-build] ADVISORY: Potential goal drift detected (similarity=-0.00 < 0.7)
```

---

## Root Cause Analysis

### Why Git Apply Fails with Context Mismatch

**Problem**: LLM generates patch hunks with context lines that don't match actual file content.

**Example Scenario**:
```diff
# LLM-generated patch (based on stale understanding)
@@ -10,3 +10,4 @@ def example():
     old_line_that_was_changed
+    new_line

# Actual file state (after previous phase modified it)
10: new_line_from_previous_phase  # ← Different from LLM's expectation
```

**Git apply behavior**:
1. Reads hunk header: expects line 10 to be "old_line_that_was_changed"
2. Finds line 10 is actually "new_line_from_previous_phase"
3. **Rejects patch** due to context mismatch
4. Even 3-way merge mode fails if context is completely different

### Why This Happens (Goal Drift)

**Causes**:
1. **Stale file context** - LLM's understanding of file state lags behind actual state
2. **Multi-phase dependencies** - Phase N modifies file, Phase N+1 patches based on pre-Phase-N state
3. **Replan side effects** - Doctor triggers replan, LLM generates patch for original goal vs current state

**Goal Drift Detection**:
```
[GoalDrift] Goal: Fix 20+ test failures in backend/test_api.py...
[GoalDrift] Intent: Build/verify backlog maintenance system...
[GoalDrift] Potential goal drift detected (similarity=-0.02 < 0.7)
```

Low similarity score → LLM is working on wrong task → Generates patches for wrong file state

---

## Solution: Proactive Context Validation

### Implementation

**Strategy**: Validate patch hunk context lines match actual file content BEFORE calling git apply.

**File**: [src/autopack/governed_apply.py:1533-1543](../src/autopack/governed_apply.py#L1533-L1543)

```python
# BUILD-045: Validate patch context matches actual file state before applying
# This prevents git apply failures due to goal drift / context mismatch
context_errors = self._validate_patch_context(patch_content)
if context_errors:
    error_details = "\n".join(f"  - {err}" for err in context_errors)
    error_msg = f"Patch context validation failed - hunks don't match actual file state:\n{error_details}"
    logger.error(f"[BUILD-045] {error_msg}")
    logger.warning("[BUILD-045] This typically indicates goal drift - LLM generated patch for wrong file state")
    # Don't fail immediately - let git apply attempt and provide feedback
    # This allows 3-way merge to potentially resolve minor context mismatches
    logger.info("[BUILD-045] Proceeding with git apply - 3-way merge may resolve context differences")
```

**Context Validation Method**: [src/autopack/governed_apply.py:959-1032](../src/autopack/governed_apply.py#L959-L1032)

```python
def _validate_patch_context(self, patch_content: str) -> List[str]:
    """
    BUILD-045: Validate that patch hunk context lines match actual file content.

    This detects goal drift where LLM generates patches for the wrong file state,
    preventing git apply failures due to context mismatches.

    Returns:
        List of validation error messages (empty if context matches)
    """
    import re
    from pathlib import Path

    errors = []

    # Parse patch to extract file paths and hunks
    current_file = None
    current_hunks = []

    lines = patch_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        # Extract file path from diff header
        if line.startswith('diff --git'):
            # Save previous file's hunks for validation
            if current_file and current_hunks:
                file_errors = self._validate_file_hunks(current_file, current_hunks)
                errors.extend(file_errors)

            # Extract new file path (e.g., "diff --git a/src/file.py b/src/file.py")
            parts = line.split()
            if len(parts) >= 4:
                # Remove a/ or b/ prefix
                current_file = parts[3].lstrip('b/')
                current_hunks = []

        # Parse hunk header (e.g., "@@ -10,5 +12,6 @@")
        elif line.startswith('@@'):
            match = re.match(r'^@@\s+-(\d+),(\d+)\s+\+(\d+),(\d+)\s+@@', line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2))

                # Extract context lines from this hunk
                hunk_lines = []
                j = i + 1
                while j < len(lines) and not lines[j].startswith('@@') and not lines[j].startswith('diff --git'):
                    hunk_lines.append(lines[j])
                    j += 1

                # Extract context lines (lines without + or - prefix, or lines with - prefix)
                context_lines = []
                for hunk_line in hunk_lines:
                    if hunk_line.startswith(' ') or hunk_line.startswith('-'):
                        # Remove the prefix to get actual line content
                        context_lines.append(hunk_line[1:] if hunk_line else '')

                if context_lines:
                    current_hunks.append({
                        'start_line': old_start,
                        'count': old_count,
                        'context': context_lines[:5]  # First 5 context lines for validation
                    })

        i += 1

    # Validate last file's hunks
    if current_file and current_hunks:
        file_errors = self._validate_file_hunks(current_file, current_hunks)
        errors.extend(file_errors)

    return errors
```

**Hunk Validation Method**: [src/autopack/governed_apply.py:1034-1096](../src/autopack/governed_apply.py#L1034-L1096)

```python
def _validate_file_hunks(self, file_path: str, hunks: List[Dict]) -> List[str]:
    """
    Validate that hunk context lines match actual file content.

    Args:
        file_path: Relative path to file
        hunks: List of hunk dictionaries with start_line, count, and context

    Returns:
        List of validation error messages
    """
    errors = []

    # Check if file exists
    full_path = self.workspace / file_path
    if not full_path.exists():
        # File doesn't exist yet - this is a new file, skip validation
        return errors

    try:
        # Read actual file content
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            actual_lines = f.readlines()

        # Validate each hunk
        for hunk in hunks:
            start_line = hunk['start_line']
            context = hunk['context']

            # Check if start_line is within file bounds
            if start_line < 1 or start_line > len(actual_lines):
                errors.append(
                    f"{file_path}: Hunk starts at line {start_line} but file only has {len(actual_lines)} lines"
                )
                continue

            # Check if context lines match (allowing for minor whitespace differences)
            for i, context_line in enumerate(context[:3]):  # Check first 3 context lines
                actual_line_num = start_line + i - 1  # 0-indexed
                if actual_line_num < 0 or actual_line_num >= len(actual_lines):
                    continue

                actual_line = actual_lines[actual_line_num].rstrip('\n')
                context_line_normalized = context_line.rstrip()
                actual_line_normalized = actual_line.rstrip()

                # Compare normalized lines (ignore trailing whitespace)
                if context_line_normalized != actual_line_normalized:
                    # Allow minor differences (e.g., tabs vs spaces) for first line
                    if i == 0 and context_line_normalized.strip() == actual_line_normalized.strip():
                        continue

                    errors.append(
                        f"{file_path}:{start_line + i}: Context mismatch - "
                        f"expected '{context_line_normalized}' but found '{actual_line_normalized}'"
                    )
                    break  # Don't flood with errors for same hunk

    except Exception as e:
        # Don't fail validation if we can't read the file - let git apply handle it
        logger.debug(f"[BUILD-045] Could not validate {file_path}: {e}")

    return errors
```

---

## Impact Analysis

### Before BUILD-045

**Typical Git Apply Failure Flow**:
```
Attempt 1: LLM generates patch → Git apply checks context → Context mismatch → REJECTED
Attempt 2: Replan narrows scope → LLM still targets old state → Git apply fails again → REJECTED
Attempt 3: Escalate to Opus → Same context mismatch → Git apply fails → FAILED
```

**Costs**:
- **3 attempts** per phase (all fail)
- **$0.10 per phase** (wasted on futile retries)
- **10-15 minutes** per phase
- **No actionable feedback** - just "git apply failed"

### After BUILD-045

**Expected Flow**:
```
Pre-validation: Detect context mismatch BEFORE git apply
Logging: "[BUILD-045] Context mismatch - expected 'old_line' but found 'new_line'"
Feedback: "This typically indicates goal drift - LLM generated patch for wrong file state"
Outcome: Still attempts git apply (3-way merge may resolve), but provides diagnostic info
```

**Benefits**:
- **Early detection** - Know WHY git apply will fail before trying
- **Diagnostic logging** - Specific line numbers and mismatched content
- **Goal drift correlation** - Links context mismatches to low similarity scores
- **Actionable feedback** - Doctor/Replan can use specific mismatch details

**Expected Results**:
- Context mismatch detection rate: **100%** (was 0%)
- Diagnostic accuracy: **95%+** (specific line/content mismatches)
- Developer debugging time: **-60%** (clear logs vs guessing)
- Does NOT prevent failures (still 8%), but makes them diagnosable

---

## Design Decisions

### Why Not Fail Immediately on Context Mismatch?

**Decision**: Log warnings but proceed with git apply attempt.

**Rationale**:
1. **3-way merge may resolve** - Minor context differences can be auto-merged
2. **Whitespace tolerance** - Our validation normalizes whitespace, but git apply has own rules
3. **New file detection** - Skip validation for files that don't exist yet
4. **Defensive logging** - Capture diagnostics even if git apply surprisingly succeeds

**Trade-off**:
- ✅ Doesn't block legitimate patches with minor context differences
- ✅ Provides diagnostic info for ALL failures (not just validated ones)
- ⚠️ Still allows git apply to fail, but now with clear logs explaining why

### Validation Scope: First 3 Context Lines

**Decision**: Validate first 3 context lines per hunk, not all context.

**Rationale**:
1. **Performance** - Checking 3 lines is fast, checking 50+ lines is slow
2. **Early failure detection** - If first 3 lines mismatch, rest likely mismatch too
3. **Noise reduction** - Don't flood logs with 20 errors for same hunk

### Allow Minor Whitespace Differences

**Decision**: Normalize trailing whitespace, allow tabs vs spaces on first line.

**Rationale**:
- Editor auto-formatting can change whitespace without changing semantics
- Git apply has `--ignore-whitespace` option for this reason
- Avoid false positives for cosmetic differences

---

## Validation & Monitoring

### Pre-Deployment Validation ✅

```bash
# Syntax validation
python -m py_compile src/autopack/governed_apply.py  # ✓ PASS

# Import validation
PYTHONPATH=src python -c "from autopack import governed_apply"  # ✓ PASS
```

### Post-Deployment Monitoring

**Key Metrics**:
1. **Context mismatch detection rate** (target: 100% of git apply failures with context issues)
2. **False positive rate** (target: <5% - warnings for patches that git apply accepts)
3. **Diagnostic usefulness** (manual review - do logs help developers?)

**Monitoring Commands**:
```bash
# Check for context mismatch detections
grep "\[BUILD-045\] Patch context validation failed" executor.log

# Check for goal drift correlation
grep -A 2 "BUILD-045.*goal drift" executor.log

# Validate warnings correlate with git apply failures
grep -B 5 "git_apply_failed" executor.log | grep "BUILD-045"
```

**Expected Log Output**:
```
[2025-12-17 10:00:00] ERROR: [BUILD-045] Patch context validation failed - hunks don't match actual file state:
  - package.json:15: Context mismatch - expected '"scripts": {' but found '"dependencies": {'
[2025-12-17 10:00:00] WARNING: [BUILD-045] This typically indicates goal drift - LLM generated patch for wrong file state
[2025-12-17 10:00:00] INFO: [BUILD-045] Proceeding with git apply - 3-way merge may resolve context differences
[2025-12-17 10:00:05] ERROR: [Integrity] Patch modifies existing files. Skipping direct-write fallback to avoid partial apply.
[2025-12-17 10:00:05] ERROR: [frontend-build] Failed to apply patch to filesystem: git_apply_failed_existing_files_no_fallback
```

---

## Integration with Other Builds

### BUILD-043: Token Efficiency Optimization

- BUILD-043 reduces token truncation → Fewer incomplete patches
- BUILD-045 detects context issues independent of truncation
- **Synergy**: BUILD-043 prevents truncation-caused context errors, BUILD-045 catches goal drift issues

### BUILD-044: Protected Path Isolation

- BUILD-044 prevents LLM from targeting protected paths
- BUILD-045 validates context for allowed paths only
- **Synergy**: Both prevent wasted retries, BUILD-044 upfront, BUILD-045 diagnostic

### Goal Drift Detection (autonomous_executor.py)

- Existing goal drift detection calculates similarity scores
- BUILD-045 provides CONCRETE evidence of drift (specific line mismatches)
- **Enhancement**: Combine similarity score < 0.7 + context mismatch = high-confidence drift signal

---

## SOT References

**Primary Implementation**:
- [src/autopack/governed_apply.py:1533-1543](../src/autopack/governed_apply.py#L1533-L1543) - Validation invocation
- [src/autopack/governed_apply.py:959-1032](../src/autopack/governed_apply.py#L959-L1032) - Context validation logic
- [src/autopack/governed_apply.py:1034-1096](../src/autopack/governed_apply.py#L1034-L1096) - Hunk validation logic

**Related Systems**:
- [src/autopack/governed_apply.py:1535-1595](../src/autopack/governed_apply.py#L1535-L1595) - Git apply execution with fallback modes
- [src/autopack/autonomous_executor.py:3000-3200](../src/autopack/autonomous_executor.py#L3000-L3200) - Goal drift detection

**Documentation**:
- [Failure Analysis](../.autonomous_runs/fileorg-phase2-beta-release/FAILURE_ANALYSIS_AND_FIXES.md) - Root cause investigation
- [BUILD-043](./BUILD-043_TOKEN_EFFICIENCY_OPTIMIZATION.md) - Token optimization
- [BUILD-044](./BUILD-044_PROTECTED_PATH_ISOLATION.md) - Protected path guidance

---

## Future Enhancements

### 1. Auto-Refresh File Context Before Patch Generation

Update LLM's file understanding right before generating patch:

```python
# Before calling builder
fresh_file_content = read_latest_file_state(modified_files)
file_context['existing_files'] = fresh_file_content

builder_result = self.llm_service.execute_builder_phase(
    phase_spec=phase,
    file_context=file_context,  # Fresh content
    ...
)
```

### 2. Patch Hunk Auto-Repair

Attempt to fix context mismatches by adjusting line numbers:

```python
def _attempt_context_repair(self, patch_content: str, context_errors: List[str]) -> str:
    """Try to fix context mismatches by searching for context in nearby lines"""
    # Parse errors to find which hunks failed
    # Search actual file for matching context within ±10 lines
    # Regenerate hunk with corrected line numbers
    # Return repaired patch
```

### 3. Goal Drift Auto-Correction

When context mismatch + low similarity detected, trigger targeted replan:

```python
if context_errors and goal_drift_score < 0.3:
    logger.warning("[BUILD-045] High-confidence goal drift - triggering targeted replan")
    replan_prompt = f"""
    Previous patch failed due to context mismatch:
    {context_errors}

    The file state has changed. Please regenerate patch based on CURRENT file state:
    {fresh_file_content}
    """
```

---

## Lessons Learned

1. **Early detection > late failure** - Catching context issues before git apply saves debugging time
2. **Diagnostic logging is valuable even without prevention** - Knowing WHY a patch failed is 60% of the solution
3. **Whitespace normalization is essential** - Avoid false positives from cosmetic differences
4. **3-way merge is powerful** - Don't block it by failing validation too aggressively
5. **Goal drift + context mismatch = high-confidence signal** - Combine multiple indicators for better diagnostics

---

## Changelog

**2025-12-17**: Initial implementation
- Added patch context validation before git apply
- Validates hunk context lines match actual file content
- Logs specific line numbers and mismatched content
- Correlates with goal drift detection

**Next Steps**:
- Deploy to fresh FileOrg Phase 2 run
- Monitor context mismatch detection rate vs git apply failure rate
- Assess diagnostic value (developer feedback)
- Consider auto-repair enhancement if false positive rate is low

---

## Success Criteria

✅ **Implementation Complete**:
- Patch context validation implemented (lines 959-1032)
- Hunk validation logic implemented (lines 1034-1096)
- Validation invoked before git apply (lines 1533-1543)
- Syntax validation passed
- Import validation passed

⏳ **Pending Validation** (after deployment):
- Context mismatch detection rate: 100% (for git apply failures with context issues)
- False positive rate: <5%
- Diagnostic usefulness: Developer feedback positive
- Does NOT reduce git apply failure rate (8% remains), but makes failures diagnosable
