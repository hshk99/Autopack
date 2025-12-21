# Diagnostics Iteration Loop Enhancements

This document describes the iteration loop enhancements for Cursor-like steering in Autopack, specifically the evidence request system and human response ingestion mechanism.

## Overview

The diagnostics iteration loop allows Autopack to:
1. **Request missing evidence** explicitly from humans without token blowups
2. **Ingest human responses** through a compact mechanism
3. **Steer execution** based on human guidance during autonomous runs

This enables a collaborative workflow where Autopack can pause, ask for clarification, and incorporate human decisions into its execution path.

## Evidence Request System

### Request Types

Autopack supports five types of evidence requests:

| Type | Purpose | Default Blocking |
|------|---------|------------------|
| `clarification` | Unclear requirements or ambiguous specifications | Yes |
| `example` | Need sample data or input format | No |
| `context` | Missing background information | Yes |
| `validation` | Confirm approach before proceeding | Yes |
| `decision` | Choose between multiple valid options | Yes |

### Creating Evidence Requests

```python
from autopack.diagnostics.evidence_requests import (
    EvidenceRequest,
    EvidenceRequestType,
    create_clarification_request,
    create_decision_request,
    create_example_request
)

# Clarification request
request = create_clarification_request(
    phase_id="implement-api",
    question="Should we use async or sync API patterns?",
    context="Implementing database layer with potential high concurrency"
)

# Decision request with options
request = create_decision_request(
    phase_id="choose-framework",
    question="Which API style should we use?",
    options=["REST", "GraphQL", "gRPC"],
    context="Building public-facing API for mobile clients"
)

# Example request (non-blocking by default)
request = create_example_request(
    phase_id="parse-input",
    question="What format should the input data be in?",
    context="Need sample data structure for parser implementation"
)
```

### Request Structure

```python
@dataclass
class EvidenceRequest:
    phase_id: str           # Phase requesting evidence
    request_type: EvidenceRequestType
    question: str           # The specific question
    context: str            # Background context
    options: list[str] | None = None  # For decision requests
    blocking: bool = True   # Whether to pause execution
```

### Formatting for Prompts

Evidence requests are formatted compactly to avoid token blowups:

```python
from autopack.diagnostics.evidence_requests import (
    format_evidence_request,
    format_multiple_requests
)

# Single request
formatted = format_evidence_request(request)
# Output:
# 🔍 EVIDENCE REQUEST [implement-api]
# Type: clarification
# Question: Should we use async or sync API patterns?
# Context: Implementing database layer with potential high concurrency
# ⏸️ BLOCKING - Awaiting human response

# Multiple requests
formatted = format_multiple_requests(requests)
# Output:
# 📋 EVIDENCE REQUESTS (3 pending)
# [Request 1/3] ...
# [Request 2/3] ...
# [Request 3/3] ...
# Use: autopack respond <phase_id> <response>
```

### Persistence

```python
from autopack.diagnostics.evidence_requests import (
    save_evidence_requests,
    load_evidence_requests
)

# Save pending requests
save_evidence_requests(requests, ".autonomous_runs/pending_requests.json")

# Load for processing
requests = load_evidence_requests(".autonomous_runs/pending_requests.json")
```

## Human Response Ingestion

### Response Structure

```python
@dataclass
class HumanResponse:
    phase_id: str           # Phase this responds to
    response_text: str      # The actual response
    timestamp: datetime     # When response was provided
    metadata: dict | None = None  # Optional metadata
```

### Parsing Responses

The parser handles multiple input formats:

```python
from autopack.diagnostics.human_response_parser import (
    parse_human_response,
    create_response_from_cli_args
)

# Plain text response
response = parse_human_response(
    phase_id="implement-api",
    response_text="Yes, use async API for better performance"
)

# JSON response with metadata
response = parse_human_response(
    phase_id="implement-api",
    response_text='{"answer": "Use async", "reasoning": "Better performance", "confidence": "high"}'
)
# Extracts: response_text="Use async", metadata={"reasoning": "Better performance", "confidence": "high"}

# From CLI arguments
response = create_response_from_cli_args(
    phase_id="implement-api",
    response_parts=["Use", "async", "API"]
)
# response_text = "Use async API"
```

### Decision Response Validation

For decision requests, validate that the response contains a valid choice:

```python
from autopack.diagnostics.human_response_parser import (
    extract_choice_number,
    validate_response_for_decision
)

# Extract choice number from various formats
extract_choice_number("2")              # Returns: 2
extract_choice_number("Option 2")       # Returns: 2
extract_choice_number("Choice 2: REST") # Returns: 2
extract_choice_number("I prefer REST")  # Returns: None

# Validate against number of options
is_valid, error = validate_response_for_decision(response, num_options=3)
if not is_valid:
    print(f"Invalid response: {error}")
```

### Context Injection

Inject human responses into the context for subsequent phases:

```python
from autopack.diagnostics.human_response_parser import (
    format_response_for_context,
    inject_response_into_context
)

# Format for display
formatted = format_response_for_context(response)
# Output:
# 💬 HUMAN GUIDANCE [implement-api]
# Response: Use async API for better performance
# Received: 2025-12-17 10:30 UTC
# Reasoning: Better performance (if metadata present)
# Confidence: high (if metadata present)

# Inject into existing context
new_context = inject_response_into_context(original_context, response)
# Prepends formatted response with separator
```

### Response Summaries

```python
from autopack.diagnostics.human_response_parser import format_response_summary

# Compact summary for logs
summary = format_response_summary(response, max_length=50)
# Output: "[implement-api] Use async API for..."
```

### Persistence

```python
from autopack.diagnostics.human_response_parser import (
    save_human_response,
    load_human_response
)

# Save response
save_human_response(response, ".autonomous_runs/responses/implement-api.json")

# Load response
response = load_human_response(".autonomous_runs/responses/implement-api.json")
```

## CLI Integration

The evidence request and response system integrates with the Autopack CLI:

```bash
# View pending evidence requests
autopack status
# Shows: 📋 EVIDENCE REQUESTS (2 pending)
#        [1] implement-api: Should we use async or sync API patterns?
#        [2] choose-framework: Which API style should we use?

# Respond to a request
autopack respond implement-api "Use async API for better performance"

# Respond to a decision request
autopack respond choose-framework 2
# or
autopack respond choose-framework "Option 2: GraphQL"

# Respond with JSON for metadata
autopack respond implement-api '{"answer": "Use async", "confidence": "high"}'
```

## Workflow Example

### Phase Execution with Evidence Requests

```python
from autopack.diagnostics.evidence_requests import (
    create_clarification_request,
    format_evidence_request,
    save_evidence_requests
)
from autopack.diagnostics.human_response_parser import (
    load_human_response,
    inject_response_into_context
)

def execute_phase(phase_id: str, context: str) -> str:
    # Check for pending human response
    response_path = f".autonomous_runs/responses/{phase_id}.json"
    if Path(response_path).exists():
        response = load_human_response(response_path)
        context = inject_response_into_context(context, response)
    
    # Execute phase logic...
    result = run_llm_with_context(context)
    
    # If evidence is needed, create request
    if needs_clarification(result):
        request = create_clarification_request(
            phase_id=phase_id,
            question=extract_question(result),
            context=extract_context(result)
        )
        save_evidence_requests([request], ".autonomous_runs/pending_requests.json")
        print(format_evidence_request(request))
        return "AWAITING_EVIDENCE"
    
    return result
```

### Blocking vs Non-Blocking Requests

**Blocking requests** pause execution until a human response is provided:
- Clarification requests
- Decision requests
- Validation requests

**Non-blocking requests** allow execution to continue with a best guess:
- Example requests (by default)
- Any request with `blocking=False`

```python
# Non-blocking request
request = create_example_request(
    phase_id="parse-input",
    question="Example input format?",
    context="Will use reasonable defaults if not provided",
    blocking=False  # Default for examples
)

# Formatted output includes:
# ⚠️ NON-BLOCKING - Will proceed with best guess if no response
```

## Token Efficiency

The evidence request system is designed to minimize token usage:

1. **Compact formatting**: Requests use minimal formatting with clear structure
2. **Single-line summaries**: For logs and status displays
3. **Selective metadata**: Only include reasoning/confidence when provided
4. **No redundant context**: Avoid repeating information already in the phase

### Size Guidelines

| Component | Target Size |
|-----------|-------------|
| Basic request format | < 200 characters |
| Request with options | < 300 characters |
| Response format | < 200 characters |
| Response summary | Configurable max_length |

## Error Handling

### Invalid Decision Responses

```python
response = parse_human_response("implement-api", "I prefer the second option")
is_valid, error = validate_response_for_decision(response, num_options=3)
# is_valid = False
# error = "Response does not contain a valid choice number (1-3)"
```

### Missing Response Files

```python
try:
    response = load_human_response("nonexistent.json")
except FileNotFoundError:
    # Handle missing response
    pass
```

### Malformed JSON Responses

JSON responses without an `answer` field are treated as plain text:

```python
response = parse_human_response(
    "test-phase",
    '{"reasoning": "Some reasoning"}'
)
# response_text contains the entire JSON string
# No metadata extracted
```

## Best Practices

1. **Be specific in questions**: Avoid vague questions that require lengthy responses
2. **Provide context**: Include enough context for informed decisions
3. **Use decision requests for choices**: When there are clear options, enumerate them
4. **Mark non-critical requests as non-blocking**: Allow progress when possible
5. **Include reasoning in responses**: Helps future phases understand decisions
6. **Use compact response formats**: Prefer numbered choices over prose for decisions

## Related Documentation

- [Autonomous Run System](./autonomous_runs.md)
- [Phase Execution](./phase_execution.md)
- [CLI Reference](./cli_reference.md)
