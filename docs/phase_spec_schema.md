# Phase Specification Schema

## Core Fields

- `id`: Unique phase identifier
- `description`: Human-readable description
- `complexity`: One of: `low`, `medium`, `high`
- `task_category`: One of: `feature`, `refactor`, `bugfix`, `tests`, `docs`, etc.
- `acceptance_criteria`: List of criteria for phase completion

## Safety Flags (NEW in v2)

### allow_mass_deletion

**Type**: `boolean`  
**Default**: `false`  
**Purpose**: Allows phases to shrink files by >60% without triggering safety guards

**When to use**:
- Cleanup phases that remove deprecated code
- Phases that delete large sections of code
- Refactors that consolidate duplicate code

**Example**:
```yaml
phases:
  - id: cleanup-old-api
    description: "Remove deprecated API v1 endpoints"
    complexity: medium
    task_category: refactor
    allow_mass_deletion: true  # Allows >60% shrinkage
```

### allow_mass_addition

**Type**: `boolean`  
**Default**: `false`  
**Purpose**: Allows phases to grow files by >3x without triggering safety guards

**When to use**:
- Phases that add large amounts of new code
- Phases that expand minimal stubs into full implementations
- Phases that add comprehensive test coverage

**Example**:
```yaml
phases:
  - id: implement-auth-system
    description: "Implement complete authentication system"
    complexity: high
    task_category: feature
    allow_mass_addition: true  # Allows >3x growth
```

## Safety Thresholds

Without explicit opt-in flags, the following limits apply:

- **Max shrinkage**: 60% (files cannot shrink by more than 60%)
- **Max growth**: 3x (files cannot grow by more than 3x their original size)

These thresholds prevent:
- Accidental truncation (catastrophic data loss)
- Unintended code duplication
- Malformed LLM outputs

## File Size Limits

Autopack uses a 3-bucket policy for file modifications:

- **Bucket A (≤500 lines)**: Full-file mode - LLM outputs complete file content
- **Bucket B (501-1000 lines)**: Diff mode - LLM generates git diff patches
- **Bucket C (>1000 lines)**: Structured edit mode (Stage 2) - LLM outputs targeted operations

Files >1000 lines are automatically routed to structured edit mode to prevent truncation.

## Output Modes

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

**Example structured edit**:
```json
{
  "summary": "Add telemetry to autonomous_executor.py",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 500,
      "content": "    self.telemetry.record_event(event)\n"
    }
  ]
}
```

For more details, see [Stage 2: Structured Edits Guide](stage2_structured_edits.md).

## Best Practices

1. **Use safety flags sparingly**: Only enable `allow_mass_deletion` or `allow_mass_addition` when you explicitly need large-scale changes
2. **Break down large changes**: Instead of one phase that modifies a 2000-line file, consider multiple phases that each modify smaller sections
3. **Test incrementally**: Apply changes in smaller phases to catch issues early
4. **Document intent**: When using safety flags, add comments explaining why they're needed

## Migration Guide

If you have existing phase specs that trigger safety guards:

1. Review the phase to confirm it intentionally makes large changes
2. Add the appropriate safety flag (`allow_mass_deletion` or `allow_mass_addition`)
3. Test the phase to ensure it works as expected
4. Document why the flag was needed

## Related Documentation

- [IMPLEMENTATION_PLAN2.md](../IMPLEMENTATION_PLAN2.md) - File truncation bug fix
- [IMPLEMENTATION_PLAN3.md](../IMPLEMENTATION_PLAN3.md) - Structured edits for large files

