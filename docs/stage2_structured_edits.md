# Stage 2: Structured Edits for Large Files

This document describes Autopack's structured edit mode for handling large files (>30KB) and contexts with >30 files.

## Overview

When working with large files or extensive file contexts, standard patch generation can hit token limits or become impractical. Stage 2 introduces **structured edits** as an alternative to traditional git diffs.

## When to Use Structured Edits

Use structured edits when:
- Individual files exceed 30KB
- Total file context exceeds 30 files
- Precise, surgical changes are needed (e.g., renaming a function across many call sites)
- Full-file rewrites would waste tokens

## Edit Operations

Structured edits use a JSON-based operation format defined in [`src/autopack/structured_edits.py`](../src/autopack/structured_edits.py):

```python
@dataclass
class EditOperation:
    operation_type: str    # "insert", "delete", "replace", "rename_symbol"
    file_path: str         # Target file path
    line_start: int        # Starting line number (1-indexed)
    line_end: int          # Ending line number (inclusive)
    new_content: str       # New content to insert/replace
    symbol_name: Optional[str]  # For rename operations
    new_symbol_name: Optional[str]  # For rename operations
```

### Operation Types

1. **insert**: Add new lines at a specific location
   ```json
   {
     "operation_type": "insert",
     "file_path": "src/example.py",
     "line_start": 42,
     "line_end": 42,
     "new_content": "    # New comment\n    new_function()\n"
   }
   ```

2. **delete**: Remove lines
   ```json
   {
     "operation_type": "delete",
     "file_path": "src/example.py",
     "line_start": 10,
     "line_end": 15
   }
   ```

3. **replace**: Replace existing lines
   ```json
   {
     "operation_type": "replace",
     "file_path": "src/example.py",
     "line_start": 20,
     "line_end": 25,
     "new_content": "def updated_function():\n    return True\n"
   }
   ```

4. **rename_symbol**: Rename a symbol across the file
   ```json
   {
     "operation_type": "rename_symbol",
     "file_path": "src/example.py",
     "symbol_name": "old_function_name",
     "new_symbol_name": "new_function_name"
   }
   ```

## Builder Integration

The Builder returns an `edit_plan` instead of `patch_content` when using structured edits:

```python
@dataclass
class BuilderResult:
    success: bool
    patch_content: str           # Empty for structured edits
    edit_plan: Optional[EditPlan]  # Populated for structured edits
    # ... other fields
```

The `EditPlan` contains:
```python
@dataclass
class EditPlan:
    operations: List[EditOperation]
    validation_rules: List[str]  # Safety checks before applying
```

## Applying Structured Edits

The [`StructuredEditApplicator`](../src/autopack/structured_edits.py) applies edit operations:

1. Validates operations (line ranges, file existence)
2. Applies operations in order
3. Verifies no conflicts or overlaps
4. Returns success/failure with detailed error messages

## Enabling Structured Edits

Set the phase's `builder_mode`:

```json
{
  "phase_id": "P1",
  "builder_mode": "structured_edit",
  "scope": {
    "paths": ["src/large_file.py"]
  }
}
```

Or let the executor auto-detect:
- Files >30KB trigger structured edit mode automatically
- Context with >30 files triggers structured edit mode

## Full File Mode

An alternative to structured edits is **full file mode**, where the Builder returns complete file contents:

```json
{
  "files": [
    {
      "path": "src/example.py",
      "content": "# Complete file content here\n..."
    }
  ]
}
```

Full file mode is useful for:
- Complete rewrites
- New file creation
- Files where line-based edits are impractical

## Safety and Validation

Structured edits go through the same validation as patches:

1. **Governance checks**: Protected paths enforced (see [`governed_apply.py`](../src/autopack/governed_apply.py))
2. **Auditor review**: Auditor validates the edit plan
3. **Quality gate**: Tests run after applying edits
4. **Rollback support**: Failed edits can be reverted via git

## Example: Large File Refactoring

```json
{
  "phase_id": "R1.rename-function",
  "name": "Rename get_user to fetch_user across codebase",
  "builder_mode": "structured_edit",
  "scope": {
    "paths": [
      "src/user_service.py",
      "src/api/users.py",
      "src/models/user.py"
    ]
  },
  "edit_operations": [
    {
      "operation_type": "rename_symbol",
      "file_path": "src/user_service.py",
      "symbol_name": "get_user",
      "new_symbol_name": "fetch_user"
    },
    {
      "operation_type": "rename_symbol",
      "file_path": "src/api/users.py",
      "symbol_name": "get_user",
      "new_symbol_name": "fetch_user"
    }
  ]
}
```

## Limitations

- Structured edits require precise line numbers (off-by-one errors can fail)
- Complex merge scenarios may need manual intervention
- Not all editors/IDEs support structured edit preview (use git diff fallback)

## See Also

- [Phase Spec Schema](phase_spec_schema.md) - Phase specification format
- [Structured Edits Implementation](../src/autopack/structured_edits.py) - Source code
- [Anthropic Clients](../src/autopack/anthropic_clients.py) - Builder implementation with structured edit support
