# Phase Specification Schema

This document describes the phase specification format used by Autopack's autonomous execution system.

## Schema Definition

Phases are defined using the `PhaseCreate` schema from [`src/autopack/schemas.py`](../src/autopack/schemas.py):

```python
class PhaseCreate(BaseModel):
    """Phase to be created within a tier"""

    phase_id: str           # Phase identifier (e.g. "F2.3")
    phase_index: int        # Order index for this phase
    tier_id: str            # Parent tier identifier
    name: str               # Human-readable phase name
    description: Optional[str]       # Phase description
    task_category: Optional[str]     # Task category (e.g. "schema_change", "backend", "tests")
    complexity: Optional[str]        # Complexity: "low", "medium", or "high"
    builder_mode: Optional[str]      # Builder mode (e.g. "tweak_light", "default")
    scope: Optional[Dict[str, Any]]  # Scope configuration (see below)
```

## Scope Configuration

The `scope` field defines file paths, context, and acceptance criteria for the phase:

```json
{
  "paths": [
    "src/autopack/file1.py",
    "src/autopack/file2.py"
  ],
  "read_only_context": [
    {
      "path": "tests/test_integration.py",
      "reason": "Reference existing test patterns"
    }
  ],
  "acceptance_criteria": [
    "All tests must pass",
    "No regressions in existing functionality"
  ],
  "test_cmd": "pytest tests/ -v",
  "notes": [
    "Additional guidance for the Builder"
  ]
}
```

### Scope Fields

- **paths**: List of file paths that the Builder can modify
- **read_only_context**: Files to load for context but not modify
  - `path`: File path to load
  - `reason`: Why this context is needed
- **acceptance_criteria**: List of success criteria for phase completion
- **test_cmd**: Command to run tests for this phase
- **notes**: Additional guidance or constraints

## Task Categories

Common `task_category` values:

- `backend`: Backend implementation
- `frontend`: Frontend/UI changes
- `tests`: Test implementation
- `docs`: Documentation updates
- `schema_change`: Database schema modifications
- `refactoring`: Code refactoring
- `bug_fix`: Bug fixes

## Complexity Levels

- `low`: Simple, low-risk changes (uses cheaper models)
- `medium`: Standard complexity (balanced models)
- `high`: Complex, high-risk changes (uses strongest models)

## Builder Modes

- `default`: Standard patch generation (recommended)
- `tweak_light`: Minimal changes only
- **Stage 2 (large files)**: `full_file` or `structured_edit` (see [stage2_structured_edits.md](stage2_structured_edits.md))

## Example Phase Specification

```json
{
  "phase_id": "F1.exact-token-accounting",
  "phase_index": 0,
  "tier_id": "T1",
  "name": "Implement exact token accounting",
  "description": "Remove heuristic token splits and use exact prompt/completion counts from providers",
  "task_category": "backend",
  "complexity": "medium",
  "builder_mode": "default",
  "scope": {
    "paths": [
      "src/autopack/llm_service.py",
      "src/autopack/llm_client.py",
      "src/autopack/openai_clients.py",
      "src/autopack/gemini_clients.py",
      "src/autopack/anthropic_clients.py"
    ],
    "read_only_context": [
      {
        "path": "src/autopack/usage_recorder.py",
        "reason": "Understand LlmUsageEvent schema"
      }
    ],
    "acceptance_criteria": [
      "No heuristic 40/60 or 60/40 splits remain",
      "All providers return exact prompt_tokens and completion_tokens",
      "LlmUsageEvent records exact values"
    ],
    "test_cmd": "pytest tests/autopack/test_exact_token_accounting.py -v"
  }
}
```

## File Size Limits and Safety

- **Standard mode** (default): Suitable for files <30KB
- **Large file mode**: For files >30KB or context >30 files, use Stage 2 structured edits
- **Safety flags**: Protected paths are enforced by governance system (see [`governed_apply.py`](../src/autopack/governed_apply.py))

## Creating Runs

To start a run with phases, use the `RunStartRequest` schema:

```json
{
  "run": {
    "run_id": "my-run-id",
    "safety_profile": "normal",
    "run_scope": "multi_tier",
    "token_cap": 450000,
    "max_phases": 10,
    "max_duration_minutes": 120
  },
  "tiers": [
    {
      "tier_id": "T1",
      "tier_index": 0,
      "name": "Implementation",
      "description": "Core implementation tasks"
    }
  ],
  "phases": [
    /* PhaseCreate objects as shown above */
  ]
}
```

## See Also

- [Stage 2: Structured Edits](stage2_structured_edits.md) - Large file handling
- [RunStartRequest Schema](../src/autopack/schemas.py) - Full API schema
- [Model Router](../src/autopack/model_router.py) - Model selection based on category/complexity
