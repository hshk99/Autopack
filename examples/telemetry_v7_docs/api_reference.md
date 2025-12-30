# Phase Executor API Reference

This document provides a comprehensive reference for the Phase Executor API, which orchestrates autonomous build phases in the autopack system.

## Table of Contents

- [Core Classes](#core-classes)
  - [PhaseExecutor](#phaseexecutor)
  - [PhaseOrchestrator](#phaseorchestrator)
- [Key Methods](#key-methods)
- [Code Examples](#code-examples)
- [Return Types](#return-types)

---

## Core Classes

### PhaseExecutor

The `PhaseExecutor` class is responsible for executing individual build phases with LLM assistance.

#### Constructor

```python
class PhaseExecutor:
    def __init__(
        self,
        llm_client: Any,
        repo_root: Path,
        db_path: Path,
        max_tokens: int = 200000
    )
```

**Parameters:**
- `llm_client`: LLM client instance for generating code changes
- `repo_root`: Path to the repository root directory
- `db_path`: Path to the SQLite database for storing execution history
- `max_tokens`: Maximum token budget for LLM context (default: 200000)

**Description:**
Initializes a phase executor with the necessary dependencies for executing autonomous build phases.

---

### PhaseOrchestrator

The `PhaseOrchestrator` class manages the overall execution flow of multiple phases.

#### Constructor

```python
class PhaseOrchestrator:
    def __init__(
        self,
        executor: PhaseExecutor,
        max_retries: int = 3,
        enable_health_checks: bool = True
    )
```

**Parameters:**
- `executor`: PhaseExecutor instance to use for executing phases
- `max_retries`: Maximum number of retry attempts per phase (default: 3)
- `enable_health_checks`: Whether to run health checks after each phase (default: True)

**Description:**
Orchestrates the execution of multiple phases with retry logic and health monitoring.

---

## Key Methods

### PhaseExecutor.execute_phase

Executes a single build phase with LLM-generated code changes.

```python
def execute_phase(
    self,
    phase_spec: Dict[str, Any],
    context_files: List[str],
    protected_paths: List[str] = None
) -> Dict[str, Any]
```

**Parameters:**
- `phase_spec`: Dictionary containing phase specification with keys:
  - `description`: Phase description and requirements
  - `category`: Phase category (e.g., 'docs', 'feature', 'refactor')
  - `complexity`: Complexity level ('low', 'medium', 'high')
  - `acceptance_criteria`: List of acceptance criteria
  - `deliverables`: List of required file paths
- `context_files`: List of file paths to include in LLM context
- `protected_paths`: List of paths that cannot be modified (default: ['.autonomous_runs/', '.git/', 'autopack.db'])

**Returns:**
```python
{
    "success": bool,
    "files_changed": List[str],
    "summary": str,
    "errors": List[str],
    "token_usage": int
}
```

**Description:**
Executes a phase by generating an LLM prompt, parsing the response, and applying file changes.

---

### PhaseOrchestrator.run_phases

Runs a sequence of phases with orchestration logic.

```python
def run_phases(
    self,
    phases: List[Dict[str, Any]],
    stop_on_failure: bool = True
) -> Dict[str, Any]
```

**Parameters:**
- `phases`: List of phase specifications to execute
- `stop_on_failure`: Whether to stop execution on first failure (default: True)

**Returns:**
```python
{
    "total_phases": int,
    "successful_phases": int,
    "failed_phases": int,
    "phase_results": List[Dict[str, Any]],
    "total_duration": float
}
```

**Description:**
Executes multiple phases in sequence with retry logic and aggregated results.

---

### PhaseExecutor.validate_changes

Validates proposed file changes before applying them.

```python
def validate_changes(
    self,
    changes: List[Dict[str, Any]],
    protected_paths: List[str]
) -> Tuple[bool, List[str]]
```

**Parameters:**
- `changes`: List of file change dictionaries with keys:
  - `path`: File path
  - `mode`: Change mode ('create', 'modify', 'delete')
  - `new_content`: New file content (or None for delete)
- `protected_paths`: List of protected path prefixes

**Returns:**
- Tuple of (is_valid: bool, errors: List[str])

**Description:**
Validates that proposed changes don't violate protected path rules and have valid structure.

---

## Code Examples

### Example 1: Basic Phase Execution

```python
from pathlib import Path
from autopack.phase_executor import PhaseExecutor
from autopack.llm_client import LLMClient

# Initialize components
llm_client = LLMClient(api_key="your-api-key")
repo_root = Path("/path/to/repo")
db_path = Path(".autonomous_runs/execution.db")

executor = PhaseExecutor(
    llm_client=llm_client,
    repo_root=repo_root,
    db_path=db_path,
    max_tokens=150000
)

# Define phase specification
phase_spec = {
    "description": "Add logging to authentication module",
    "category": "feature",
    "complexity": "medium",
    "acceptance_criteria": [
        "Add structured logging to all auth functions",
        "Include user ID and timestamp in logs",
        "Use appropriate log levels"
    ],
    "deliverables": ["src/auth/login.py", "src/auth/logout.py"]
}

# Provide context files
context_files = [
    "src/auth/login.py",
    "src/auth/logout.py",
    "src/utils/logger.py"
]

# Execute phase
result = executor.execute_phase(
    phase_spec=phase_spec,
    context_files=context_files
)

if result["success"]:
    print(f"Phase completed successfully!")
    print(f"Files changed: {result['files_changed']}")
    print(f"Summary: {result['summary']}")
else:
    print(f"Phase failed: {result['errors']}")
```

### Example 2: Orchestrating Multiple Phases

```python
from autopack.phase_executor import PhaseExecutor, PhaseOrchestrator
from autopack.llm_client import LLMClient
from pathlib import Path

# Setup
llm_client = LLMClient(api_key="your-api-key")
executor = PhaseExecutor(
    llm_client=llm_client,
    repo_root=Path("/path/to/repo"),
    db_path=Path(".autonomous_runs/execution.db")
)

orchestrator = PhaseOrchestrator(
    executor=executor,
    max_retries=3,
    enable_health_checks=True
)

# Define multiple phases
phases = [
    {
        "description": "Create user model",
        "category": "feature",
        "complexity": "low",
        "acceptance_criteria": ["Define User class with fields"],
        "deliverables": ["src/models/user.py"]
    },
    {
        "description": "Add user authentication",
        "category": "feature",
        "complexity": "medium",
        "acceptance_criteria": ["Implement login/logout functions"],
        "deliverables": ["src/auth/handlers.py"]
    },
    {
        "description": "Document authentication API",
        "category": "docs",
        "complexity": "low",
        "acceptance_criteria": ["Create API documentation"],
        "deliverables": ["docs/auth_api.md"]
    }
]

# Run all phases
results = orchestrator.run_phases(
    phases=phases,
    stop_on_failure=True
)

print(f"Completed {results['successful_phases']}/{results['total_phases']} phases")
print(f"Total duration: {results['total_duration']:.2f}s")

for i, phase_result in enumerate(results['phase_results']):
    print(f"\nPhase {i+1}: {'✓' if phase_result['success'] else '✗'}")
    print(f"  Summary: {phase_result['summary']}")
```

### Example 3: Custom Protected Paths

```python
from autopack.phase_executor import PhaseExecutor
from pathlib import Path

executor = PhaseExecutor(
    llm_client=llm_client,
    repo_root=Path("/path/to/repo"),
    db_path=Path(".autonomous_runs/execution.db")
)

# Define custom protected paths
protected_paths = [
    ".autonomous_runs/",
    ".git/",
    "autopack.db",
    "config/production.yaml",  # Custom: protect production config
    "secrets/"                  # Custom: protect secrets directory
]

phase_spec = {
    "description": "Refactor configuration loading",
    "category": "refactor",
    "complexity": "medium",
    "acceptance_criteria": [
        "Create new config loader",
        "Do not modify production config"
    ],
    "deliverables": ["src/config/loader.py"]
}

context_files = [
    "src/config/loader.py",
    "config/development.yaml"
]

result = executor.execute_phase(
    phase_spec=phase_spec,
    context_files=context_files,
    protected_paths=protected_paths
)
```

---

## Return Types

### PhaseResult

Returned by `PhaseExecutor.execute_phase()`:

```python
{
    "success": bool,              # Whether phase completed successfully
    "files_changed": List[str],   # List of file paths that were modified
    "summary": str,               # Human-readable summary of changes
    "errors": List[str],          # List of error messages (empty if success)
    "token_usage": int,           # Number of tokens used in LLM call
    "duration": float,            # Execution time in seconds
    "retry_count": int            # Number of retries attempted
}
```

### OrchestrationResult

Returned by `PhaseOrchestrator.run_phases()`:

```python
{
    "total_phases": int,                    # Total number of phases
    "successful_phases": int,               # Number of successful phases
    "failed_phases": int,                   # Number of failed phases
    "phase_results": List[PhaseResult],     # Individual phase results
    "total_duration": float,                # Total execution time in seconds
    "health_check_results": List[Dict]      # Health check results per phase
}
```

### ValidationResult

Returned by `PhaseExecutor.validate_changes()`:

```python
Tuple[
    bool,        # is_valid: True if all changes are valid
    List[str]    # errors: List of validation error messages
]
```

---

## Error Handling

The Phase Executor API uses structured error handling:

- **Protected Path Violations**: Raised when attempting to modify protected files
- **Invalid JSON Response**: Raised when LLM returns malformed JSON
- **Missing Deliverables**: Raised when required files are not included in output
- **File System Errors**: Raised when file operations fail

All errors are captured in the `errors` field of return dictionaries, allowing graceful degradation and retry logic.

---

## Best Practices

1. **Context Management**: Provide minimal but sufficient context files (8-10 files recommended)
2. **Protected Paths**: Always specify protected paths to prevent accidental modifications
3. **Token Budget**: Monitor token usage and adjust `max_tokens` based on phase complexity
4. **Retry Logic**: Use `PhaseOrchestrator` for automatic retry handling
5. **Health Checks**: Enable health checks to catch issues early
6. **Acceptance Criteria**: Write clear, testable acceptance criteria for better results

---

*Last Updated: 2024*
*Version: 7.0*
