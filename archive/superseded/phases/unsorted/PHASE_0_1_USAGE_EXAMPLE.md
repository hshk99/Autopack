# Phase 0/1 Usage Examples

This document shows how to use the Project Intention Memory and Plan Normalizer modules.

---

## Example 1: Basic Project Intention Capture

```python
from pathlib import Path
from autopack.project_intention import create_and_store_intention
from autopack.memory.memory_service import MemoryService

# Initialize memory service (optional)
memory = MemoryService(enabled=True)

# Create and store intention
intention = create_and_store_intention(
    run_id="my-run-001",
    raw_input="""
    Build a user authentication system with the following requirements:
    - JWT-based authentication
    - Login and logout endpoints
    - Password hashing
    - Session management
    """,
    project_id="auth-system",
    memory_service=memory,
    intent_facts=[
        "Must support JWT tokens",
        "Requires secure password hashing (bcrypt)",
        "RESTful API design"
    ],
    non_goals=[
        "No OAuth integration (future phase)",
        "No social login (future phase)"
    ],
    acceptance_criteria=[
        "All tests pass",
        "API documented with OpenAPI spec",
        "Security audit completed"
    ],
    constraints={
        "token_budget": 420000,
        "max_duration_minutes": 120
    },
    toolchain_hypotheses=["python", "fastapi", "sqlalchemy"],
    open_questions=[
        "Which database? (PostgreSQL vs SQLite)",
        "Token expiration policy?"
    ]
)

print(f"Intention created: {intention.project_id}")
print(f"Digest: {intention.raw_input_digest}")
print(f"Anchor size: {len(intention.intent_anchor)} chars")
```

---

## Example 2: Retrieve Intention for Context Injection

```python
from autopack.project_intention import ProjectIntentionManager

# Initialize manager
manager = ProjectIntentionManager(
    run_id="my-run-001",
    project_id="auth-system",
    memory_service=memory
)

# Get compact context for prompt injection
context = manager.get_intention_context(max_chars=2048)

# Use in phase prompt
phase_prompt = f"""
{context}

Current Phase: Implement JWT token generation
Task: Create jwt.py module with sign/verify functions
"""
```

---

## Example 3: Basic Plan Normalization

```python
from pathlib import Path
from autopack.plan_normalizer import normalize_plan

# Normalize unstructured plan
result = normalize_plan(
    workspace=Path.cwd(),
    run_id="my-run-002",
    raw_plan="""
    I want to add user authentication to my API.

    Should include:
    - Login endpoint
    - Logout endpoint
    - JWT tokens
    - Password hashing

    Tests must pass before deployment.
    """,
    project_id="auth-system"
)

if result.success:
    print(f"✅ Normalization succeeded!")
    print(f"Confidence: {result.confidence:.2%}")
    print(f"Deliverables: {len(result.normalization_decisions['deliverables'])}")
    print(f"Scope files: {len(result.normalization_decisions['scope_paths'])}")

    # Use structured plan
    structured_plan = result.structured_plan
    run_config = structured_plan["run"]
    phases = structured_plan["phases"]

    print(f"Generated {len(phases)} phase(s)")
    for phase in phases:
        print(f"  - {phase['name']}: {phase['description']}")
        print(f"    Test command: {phase['scope']['test_cmd']}")
else:
    print(f"❌ Normalization failed: {result.error}")
    for warning in result.warnings:
        print(f"⚠️  {warning}")
```

---

## Example 4: End-to-End Integration

```python
from pathlib import Path
from autopack.project_intention import create_and_store_intention
from autopack.plan_normalizer import PlanNormalizer
from autopack.memory.memory_service import MemoryService

# Step 1: Initialize memory service
memory = MemoryService(enabled=True)

# Step 2: Capture project intention
raw_plan = """
Build a REST API for managing user profiles:
1. User registration endpoint
2. Profile update endpoint
3. Profile retrieval endpoint
4. JWT authentication
5. PostgreSQL database
"""

intention = create_and_store_intention(
    run_id="profile-api-run",
    raw_input=raw_plan,
    project_id="profile-api",
    memory_service=memory,
    intent_facts=[
        "RESTful design",
        "JWT authentication required",
        "PostgreSQL database"
    ],
    acceptance_criteria=[
        "All API tests pass",
        "OpenAPI documentation complete"
    ]
)

# Step 3: Create normalizer with intention context
normalizer = PlanNormalizer(
    workspace=Path.cwd(),
    run_id="profile-api-run",
    project_id="profile-api",
    memory_service=memory,
    intention_manager=intention.manager  # Pass intention manager
)

# Step 4: Normalize plan (will use intention context)
result = normalizer.normalize(
    raw_plan=raw_plan,
    run_config={
        "token_cap": 300000,
        "max_phases": 8,
        "max_duration_minutes": 90
    }
)

# Step 5: Execute (hand off to Autopack executor)
if result.success:
    structured_plan = result.structured_plan
    # ... execute phases with Autopack ...

    # Each phase can retrieve intention context:
    context = intention.manager.get_intention_context()
    # Inject into phase prompts for semantic guidance
```

---

## Example 5: Custom Budget and Validation

```python
from pathlib import Path
from autopack.plan_normalizer import normalize_plan

result = normalize_plan(
    workspace=Path.cwd(),
    run_id="custom-run",
    raw_plan="Add dark mode toggle to settings page",
    run_config={
        "token_cap": 150000,         # Lower budget for small task
        "max_phases": 3,             # Only 3 phases needed
        "max_duration_minutes": 30   # Quick task
    }
)

if result.success:
    plan = result.structured_plan
    assert plan["run"]["token_cap"] == 150000
    assert plan["run"]["max_phases"] == 3
```

---

## Example 6: Handling Normalization Failures

```python
from autopack.plan_normalizer import normalize_plan
from pathlib import Path

# Vague plan with no clear deliverables
result = normalize_plan(
    workspace=Path.cwd(),
    run_id="vague-run",
    raw_plan="Make it better",
)

if not result.success:
    print(f"Error: {result.error}")
    # Output: "No deliverables detected in plan. Please specify explicit deliverables..."

    # Ask user to clarify:
    clarified_plan = """
    Improve performance by:
    - Adding caching layer
    - Optimizing database queries
    - Implementing connection pooling
    """

    # Try again with clearer input
    result2 = normalize_plan(
        workspace=Path.cwd(),
        run_id="vague-run-clarified",
        raw_plan=clarified_plan
    )

    if result2.success:
        print("✅ Normalization succeeded after clarification")
```

---

## Example 7: Memory-Free Operation (Graceful Degradation)

```python
from autopack.project_intention import create_and_store_intention
from autopack.plan_normalizer import normalize_plan
from pathlib import Path

# No memory service provided (e.g., in minimal Docker environment)
intention = create_and_store_intention(
    run_id="minimal-run",
    raw_input="Add login endpoint",
    memory_service=None  # Explicitly disabled
)

# Intention is still stored to disk artifacts
assert intention.project_id is not None

# Normalization still works without memory
result = normalize_plan(
    workspace=Path.cwd(),
    run_id="minimal-run",
    raw_plan="Add login endpoint",
    memory_service=None  # Explicitly disabled
)

# Still succeeds, just no semantic retrieval
assert result.success
```

---

## Integration with Autopack Executor

To integrate with the existing Autopack executor, add these hooks:

### At Run Start (Before Planning)

```python
from autopack.project_intention import create_and_store_intention

# In your run initialization code:
def initialize_run(run_id: str, user_input: str, memory: MemoryService):
    # Capture intention
    intention = create_and_store_intention(
        run_id=run_id,
        raw_input=user_input,
        memory_service=memory,
        # ... extract facts/criteria from user_input if available
    )

    return intention
```

### During Plan Normalization

```python
from autopack.plan_normalizer import normalize_plan

# In your planning pipeline:
def create_execution_plan(run_id: str, raw_plan: str, workspace: Path):
    result = normalize_plan(
        workspace=workspace,
        run_id=run_id,
        raw_plan=raw_plan,
    )

    if not result.success:
        raise ValueError(f"Plan normalization failed: {result.error}")

    return result.structured_plan
```

### During Phase Execution

```python
from autopack.project_intention import ProjectIntentionManager

# In your phase prompt builder:
def build_phase_prompt(run_id: str, phase: dict, memory: MemoryService):
    # Retrieve intention context
    manager = ProjectIntentionManager(run_id=run_id, memory_service=memory)
    intention_context = manager.get_intention_context(max_chars=2048)

    prompt = f"""
    {intention_context}

    Current Phase: {phase['name']}
    Deliverables: {phase['scope']['acceptance_criteria']}

    [... rest of phase prompt ...]
    """

    return prompt
```

---

## Best Practices

### 1. Always Capture Intention Early
```python
# ✅ Good: Capture at run start
intention = create_and_store_intention(run_id=run_id, raw_input=user_input)

# ❌ Bad: Try to normalize without intention context
result = normalize_plan(run_id=run_id, raw_plan=user_input)
```

### 2. Use Bounded Contexts
```python
# ✅ Good: Respect size caps
context = manager.get_intention_context(max_chars=2048)

# ❌ Bad: Unbounded context injection
context = manager.get_intention_context(max_chars=100000)  # Too large!
```

### 3. Fail Fast on Unclear Plans
```python
# ✅ Good: Check result and provide actionable error
result = normalize_plan(workspace, run_id, raw_plan)
if not result.success:
    return f"Cannot normalize plan: {result.error}\n\nPlease clarify..."

# ❌ Bad: Silent fallback or guessing
result = normalize_plan(workspace, run_id, raw_plan)
# ... proceed anyway even if failed
```

### 4. Store Normalization Decisions
```python
# ✅ Good: Decisions stored in memory for reuse
normalizer = PlanNormalizer(memory_service=memory)
result = normalizer.normalize(raw_plan)
# Decisions automatically stored for later phases

# ❌ Bad: Re-normalize every phase
for phase in phases:
    normalize_plan(...)  # Wasteful!
```

---

## Summary

Phase 0/1 provides two key capabilities:

1. **Project Intention Memory**: Capture semantic intention once, reuse everywhere
2. **Plan Normalization**: Accept messy input, output safe structured plans

Both are **optional**, **backward compatible**, and **token-efficient**.

See [PHASE_0_1_IMPLEMENTATION_SUMMARY.md](PHASE_0_1_IMPLEMENTATION_SUMMARY.md) for full details.
