# Stage 2: Structured Edits for Large Files

## Overview

Stage 2 enables Autopack to safely modify files of any size by using targeted edit operations instead of full-file replacement.

## When is Stage 2 Used?

Stage 2 (structured edit mode) is automatically used when:
- A file in the phase context is >1000 lines
- Full-file mode would risk truncation
- Diff mode is not appropriate

## How It Works

### 1. LLM Generates Edit Operations

Instead of outputting the complete file, the LLM outputs specific operations:

```json
{
  "summary": "Add error handling to execute_phase",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 650,
      "content": "        try:\n            # Error handling\n        except Exception as e:\n            logger.error(e)\n"
    }
  ]
}
```

### 2. System Applies Operations

The system applies each operation in order:
1. Validates operation (line numbers, file exists, etc.)
2. Applies operation to file content
3. Verifies result (syntax check, context validation)

### 3. CI Verification

After all operations are applied, CI runs to verify the changes work correctly.

## Operation Types

### INSERT
Insert new lines at a specific position.

**Example**: Add a new function at line 500
```json
{
  "type": "insert",
  "file_path": "src/example.py",
  "line": 500,
  "content": "def new_function():\n    pass\n"
}
```

### REPLACE
Replace a range of lines with new content.

**Example**: Update function implementation (lines 100-110)
```json
{
  "type": "replace",
  "file_path": "src/example.py",
  "start_line": 100,
  "end_line": 110,
  "content": "def updated_function():\n    # New implementation\n    pass\n"
}
```

### DELETE
Delete a range of lines.

**Example**: Remove deprecated function (lines 200-220)
```json
{
  "type": "delete",
  "file_path": "src/example.py",
  "start_line": 200,
  "end_line": 220
}
```

### APPEND
Append lines to the end of a file.

**Example**: Add new function at end of file
```json
{
  "type": "append",
  "file_path": "src/example.py",
  "content": "\ndef new_function():\n    pass\n"
}
```

### PREPEND
Prepend lines to the start of a file.

**Example**: Add import at top of file
```json
{
  "type": "prepend",
  "file_path": "src/example.py",
  "content": "import logging\n"
}
```

## Safety Features

### 1. Validation
- Line numbers must be valid (within file bounds)
- Operations cannot overlap
- Context validation (optional)

### 2. Dry Run
- All operations are validated before applying
- No changes made if validation fails

### 3. Context Matching
- Optional `context_before` and `context_after` fields
- Ensures edits are applied to correct location

**Example with context**:
```json
{
  "type": "replace",
  "file_path": "src/example.py",
  "start_line": 100,
  "end_line": 105,
  "content": "updated code",
  "context_before": "# This is the section",
  "context_after": "# End of section"
}
```

### 4. Rollback
- If any operation fails, all changes are rolled back
- File is restored to original state

## Limitations

### Current Limitations
- Line numbers must be precise
- Cannot handle moving code between files
- Cannot handle complex refactorings (e.g., rename class used in 50 files)

### Future Enhancements
- Semantic anchors (find by function name, not line number)
- Multi-file refactorings
- Automatic conflict resolution

## Examples

### Example 1: Add Telemetry to Large File

**Task**: Add telemetry recording to `autonomous_executor.py` (2425 lines)

**Structured Edit**:
```json
{
  "summary": "Add telemetry recording in execute_phase",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 650,
      "content": "        # Record phase start\n        self.telemetry.record_phase_start(phase_id)\n"
    },
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 750,
      "content": "        # Record phase end\n        self.telemetry.record_phase_end(phase_id)\n"
    }
  ]
}
```

### Example 2: Fix Bug in Large File

**Task**: Fix error handling in `autonomous_executor.py` line 1200

**Structured Edit**:
```json
{
  "summary": "Fix error handling in execute_phase",
  "operations": [
    {
      "type": "replace",
      "file_path": "src/autopack/autonomous_executor.py",
      "start_line": 1200,
      "end_line": 1205,
      "content": "        except Exception as e:\n            logger.error(f\"Phase failed: {e}\")\n            return False\n",
      "context_before": "        try:",
      "context_after": "        # Continue execution"
    }
  ]
}
```

## Troubleshooting

### Operation Failed: Line Out of Range
**Cause**: Line number exceeds file length  
**Solution**: Check file has expected number of lines, adjust line number

### Operation Failed: Context Mismatch
**Cause**: `context_before` or `context_after` doesn't match actual file content  
**Solution**: Update context strings to match actual file content

### Operation Failed: Overlapping Edits
**Cause**: Two operations try to modify the same lines  
**Solution**: Combine operations or adjust line ranges

## Performance

**Compared to Full-File Mode**:
- ✅ **Faster**: Only generates changed lines, not entire file
- ✅ **More reliable**: No truncation risk
- ✅ **More precise**: Only modifies intended sections

**Compared to Diff Mode**:
- ✅ **More reliable**: LLMs better at structured operations than git diffs
- ✅ **Easier to validate**: Clear operation types
- ⚠️ **Requires line numbers**: Must know where to edit

## Migration from Full-File Mode

If you have phases that currently fail with "file_too_large_for_full_file_mode", they will automatically use structured edit mode after Stage 2 is implemented.

**No changes needed** - the system automatically routes to the appropriate mode based on file size.

## Output Modes Summary

Autopack supports three output modes for code generation:

### 1. Full-File Mode (≤500 lines)
**When**: Files are ≤500 lines  
**How**: LLM outputs complete file content in JSON  
**Pros**: Simple, reliable for small files  
**Cons**: Cannot handle large files

### 2. Diff Mode (501-1000 lines)
**When**: Files are 501-1000 lines  
**How**: LLM outputs git-compatible unified diff  
**Pros**: Can handle medium files  
**Cons**: LLMs sometimes generate incorrect diffs

### 3. Structured Edit Mode (>1000 lines) - Stage 2
**When**: Files are >1000 lines  
**How**: LLM outputs targeted edit operations (insert, replace, delete)  
**Pros**: Can handle files of any size, no truncation risk  
**Cons**: More complex, requires precise line numbers

