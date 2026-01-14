# Second Opinion Triage System

## Overview

The Second Opinion Triage System provides an optional bounded "second opinion" diagnostic capability for the autonomous build system. When a phase fails, this system can invoke a strong language model (e.g., Claude Opus 4) to analyze the failure and produce a comprehensive triage report.

## Purpose

The system addresses the challenge of diagnosing complex build failures by:

1. **Generating Hypotheses**: Identifying potential root causes with likelihood estimates
2. **Identifying Missing Evidence**: Highlighting gaps in diagnostic information
3. **Suggesting Next Probes**: Recommending specific checks or commands to gather more data
4. **Proposing Minimal Patch Strategies**: Outlining targeted approaches to fix the issue

## Architecture

### Core Components

#### SecondOpinionConfig

Configuration dataclass controlling the triage system behavior:

```python
from src.autopack.diagnostics.second_opinion import SecondOpinionConfig

config = SecondOpinionConfig(
    enabled=True,              # Enable/disable the system
    model="claude-opus-4",     # LLM model to use
    max_tokens=8192,           # Maximum tokens per request
    temperature=0.3,           # Model temperature (lower = more focused)
    token_budget=50000         # Total token budget across all calls
)
```

**Configuration Parameters:**

- `enabled` (bool): Master switch for the triage system. Default: `False`
- `model` (str): Language model identifier. Default: `"claude-opus-4"`
- `max_tokens` (int): Maximum tokens per triage request. Default: `8192`
- `temperature` (float): Model temperature for response generation. Default: `0.3`
- `token_budget` (int): Total token budget to prevent runaway costs. Default: `50000`

#### TriageReport

Structured output from the triage analysis:

```python
from src.autopack.diagnostics.second_opinion import TriageReport

report = TriageReport(
    hypotheses=[
        {
            "description": "Token budget exceeded during code generation",
            "likelihood": 0.9,
            "evidence_for": ["Truncated output", "Large file modifications"],
            "evidence_against": []
        }
    ],
    missing_evidence=[
        "Actual token counts from LLM API",
        "Size of files being modified"
    ],
    next_probes=[
        {
            "type": "check",
            "description": "Check LLM API logs for token usage",
            "command": "grep 'total_tokens' logs/llm_api.log"
        }
    ],
    minimal_patch_strategy={
        "approach": "Increase token budget or split large files",
        "files_to_modify": ["config.py"],
        "key_changes": ["Increase max_tokens to 16384"],
        "risks": ["Higher API costs"]
    },
    confidence=0.85,
    reasoning="Token truncation is the most likely cause based on..."
)
```

**Report Fields:**

- `hypotheses` (list): Potential root causes with likelihood scores (0.0-1.0)
- `missing_evidence` (list): Information gaps that would improve diagnosis
- `next_probes` (list): Recommended diagnostic actions
- `minimal_patch_strategy` (dict): Proposed fix approach with risks
- `confidence` (float): Overall confidence in the analysis (0.0-1.0)
- `reasoning` (str): Detailed explanation of the triage logic
- `timestamp` (str): ISO 8601 timestamp of report generation

#### SecondOpinionTriageSystem

Main system class orchestrating the triage process:

```python
from src.autopack.diagnostics.second_opinion import (
    SecondOpinionTriageSystem,
    SecondOpinionConfig
)

# Initialize with custom config
config = SecondOpinionConfig(enabled=True, token_budget=100000)
system = SecondOpinionTriageSystem(config)

# Generate triage report
handoff_bundle = {
    "phase": {
        "name": "implement-feature",
        "description": "Add new API endpoint",
        "state": "FAILED",
        "builder_attempts": 2,
        "max_builder_attempts": 5
    },
    "failure_reason": "Deliverables validation failed",
    "diagnostics": {
        "error_type": "MissingFiles",
        "missing_files": ["src/api/endpoint.py"]
    }
}

report = system.generate_triage(handoff_bundle)
```

## Usage

### Basic Usage

```python
from src.autopack.diagnostics.second_opinion import (
    SecondOpinionTriageSystem,
    SecondOpinionConfig
)

# 1. Create configuration
config = SecondOpinionConfig(
    enabled=True,
    model="claude-opus-4",
    token_budget=50000
)

# 2. Initialize system
triage_system = SecondOpinionTriageSystem(config)

# 3. Check if enabled and within budget
if triage_system.is_enabled() and triage_system.within_budget():
    # 4. Generate triage report
    report = triage_system.generate_triage(handoff_bundle)

    if report:
        print(f"Confidence: {report.confidence}")
        print(f"Hypotheses: {len(report.hypotheses)}")
        print(f"Tokens used: {triage_system.get_tokens_used()}")
```

### Integration with Phase Execution

```python
def handle_phase_failure(phase, handoff_bundle):
    """Handle phase failure with optional second opinion."""

    # Load triage configuration
    config = SecondOpinionConfig(
        enabled=os.getenv("ENABLE_SECOND_OPINION", "false").lower() == "true",
        token_budget=int(os.getenv("TRIAGE_TOKEN_BUDGET", "50000"))
    )

    triage_system = SecondOpinionTriageSystem(config)

    # Generate triage if enabled and within budget
    if triage_system.is_enabled() and triage_system.within_budget():
        phase_context = {
            "complexity": phase.complexity,
            "category": phase.category,
            "attempts": phase.builder_attempts
        }

        report = triage_system.generate_triage(
            handoff_bundle,
            phase_context
        )

        if report:
            # Save report for later analysis
            report_path = Path(f".autonomous_runs/{phase.name}/triage_report.json")
            triage_system.save_triage_report(report, report_path)

            # Log key findings
            logger.info(f"Triage confidence: {report.confidence}")
            for hypothesis in report.hypotheses:
                logger.info(
                    f"Hypothesis: {hypothesis['description']} "
                    f"(likelihood: {hypothesis['likelihood']})"
                )
```

### Saving and Loading Reports

```python
from pathlib import Path

# Generate and save report
report = triage_system.generate_triage(handoff_bundle)
if report:
    output_path = Path(".autonomous_runs/phase-name/triage_report.json")
    triage_system.save_triage_report(report, output_path)

# Load existing report
loaded_report = triage_system.load_triage_report(output_path)
if loaded_report:
    print(f"Loaded report with confidence: {loaded_report.confidence}")
```

### Token Budget Management

```python
# Check remaining budget
remaining = triage_system.get_tokens_remaining()
print(f"Tokens remaining: {remaining}")

# Check if within budget before generating
if triage_system.within_budget():
    report = triage_system.generate_triage(handoff_bundle)
    print(f"Tokens used this call: {triage_system.get_tokens_used()}")
else:
    print("Token budget exceeded, skipping triage")
```

## Triage Report Structure

### Hypotheses

Each hypothesis includes:

```python
{
    "description": "Clear description of the potential root cause",
    "likelihood": 0.85,  # Probability estimate (0.0-1.0)
    "evidence_for": [
        "Supporting evidence item 1",
        "Supporting evidence item 2"
    ],
    "evidence_against": [
        "Contradicting evidence item 1"
    ]
}
```

### Missing Evidence

List of information gaps:

```python
[
    "Actual token counts from LLM API responses",
    "File sizes of modified files",
    "Memory usage during code generation"
]
```

### Next Probes

Recommended diagnostic actions:

```python
[
    {
        "type": "check",
        "description": "Verify token usage in logs",
        "command": "grep 'total_tokens' logs/llm_api.log | tail -n 10"
    },
    {
        "type": "inspect",
        "description": "Check file sizes",
        "command": "ls -lh src/autopack/*.py | sort -k5 -h"
    },
    {
        "type": "test",
        "description": "Run with increased token budget",
        "command": "MAX_TOKENS=16384 python run_phase.py"
    }
]
```

### Minimal Patch Strategy

Proposed fix approach:

```python
{
    "approach": "Increase token budget and add output validation",
    "files_to_modify": [
        "src/autopack/config.py",
        "src/autopack/llm/client.py"
    ],
    "key_changes": [
        "Increase max_tokens from 8192 to 16384",
        "Add token usage logging",
        "Implement output truncation detection"
    ],
    "risks": [
        "Higher API costs",
        "Potential for longer response times"
    ]
}
```

## Configuration

### Environment Variables

```bash
# Enable second opinion triage
export ENABLE_SECOND_OPINION=true

# Set token budget
export TRIAGE_TOKEN_BUDGET=100000

# Set model
export TRIAGE_MODEL=claude-opus-4

# Set temperature
export TRIAGE_TEMPERATURE=0.3
```

### Configuration File

```yaml
# config/triage.yaml
second_opinion:
  enabled: true
  model: claude-opus-4
  max_tokens: 8192
  temperature: 0.3
  token_budget: 50000
```

## Best Practices

### 1. Enable Selectively

Only enable second opinion triage for:
- Complex phases (MEDIUM, HIGH complexity)
- Repeated failures (attempts > 2)
- Critical production issues

```python
def should_enable_triage(phase, handoff_bundle):
    """Determine if triage should be enabled for this phase."""
    return (
        phase.complexity in ["MEDIUM", "HIGH"] or
        phase.builder_attempts > 2 or
        phase.category == "FIX_CRITICAL_BUG"
    )
```

### 2. Monitor Token Usage

```python
# Log token usage after each triage
logger.info(
    f"Triage tokens: {triage_system.get_tokens_used()} / "
    f"{config.token_budget} ({triage_system.get_tokens_remaining()} remaining)"
)
```

### 3. Archive Reports

```python
# Save reports with timestamps for historical analysis
from datetime import datetime

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
report_path = Path(
    f".autonomous_runs/{phase.name}/triage_{timestamp}.json"
)
triage_system.save_triage_report(report, report_path)
```

### 4. Act on Recommendations

```python
def apply_triage_recommendations(report, phase):
    """Apply triage recommendations to phase execution."""

    # Execute next probes
    for probe in report.next_probes:
        if probe["type"] == "check":
            result = subprocess.run(
                probe["command"],
                shell=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Probe result: {result.stdout}")

    # Consider patch strategy
    strategy = report.minimal_patch_strategy
    if report.confidence > 0.8:
        logger.info(f"High-confidence fix: {strategy['approach']}")
        # Potentially auto-apply low-risk fixes
```

## Error Handling

### Graceful Degradation

The system is designed to fail gracefully:

```python
try:
    report = triage_system.generate_triage(handoff_bundle)
    if report:
        # Use report
        pass
except Exception as e:
    logger.warning(f"Triage generation failed: {e}")
    # Continue without triage
```

### Budget Exhaustion

```python
if not triage_system.within_budget():
    logger.warning(
        f"Triage token budget exhausted: "
        f"{triage_system.get_tokens_used()} / {config.token_budget}"
    )
    # Skip triage or request budget increase
```

### Invalid Responses

The system validates LLM responses:

```python
try:
    report = triage_system._parse_triage_response(response)
except ValueError as e:
    logger.error(f"Invalid triage response: {e}")
    # Fall back to basic diagnostics
```

## Performance Considerations

### Token Budget Planning

- **Small projects**: 10,000-25,000 tokens
- **Medium projects**: 25,000-50,000 tokens
- **Large projects**: 50,000-100,000 tokens

### Response Time

- Typical triage generation: 5-15 seconds
- Complex analyses: 15-30 seconds
- Budget for latency in phase execution

### Cost Estimation

For Claude Opus 4 (example pricing):
- Input: $15 per million tokens
- Output: $75 per million tokens
- Average triage: ~2,000 input + 1,000 output tokens
- Cost per triage: ~$0.10-$0.15

## Testing

The system includes comprehensive tests:

```bash
# Run all triage tests
pytest tests/autopack/diagnostics/test_second_opinion.py -v

# Run specific test categories
pytest tests/autopack/diagnostics/test_second_opinion.py::TestSecondOpinionConfig -v
pytest tests/autopack/diagnostics/test_second_opinion.py::TestTriageReport -v
pytest tests/autopack/diagnostics/test_second_opinion.py::TestSecondOpinionTriageSystem -v
```

## Limitations

1. **Token Budget**: Hard limit prevents runaway costs but may limit analysis depth
2. **Model Availability**: Requires access to strong language models (Claude Opus, GPT-4)
3. **Latency**: Adds 5-30 seconds to failure handling
4. **Accuracy**: Triage quality depends on handoff bundle completeness
5. **Cost**: Each triage incurs API costs

## Future Enhancements

### Planned Features

1. **Multi-Model Support**: Compare triage from different models
2. **Historical Learning**: Learn from past successful fixes
3. **Auto-Fix**: Automatically apply high-confidence, low-risk fixes
4. **Interactive Mode**: Allow human review and refinement of triage
5. **Metrics Dashboard**: Track triage accuracy and effectiveness

### Potential Improvements

```python
# Multi-model consensus
reports = [
    triage_system_opus.generate_triage(handoff_bundle),
    triage_system_gpt4.generate_triage(handoff_bundle)
]
consensus_report = merge_triage_reports(reports)

# Historical learning
historical_fixes = load_successful_fixes(phase.category)
report = triage_system.generate_triage(
    handoff_bundle,
    historical_context=historical_fixes
)

# Auto-fix for high-confidence, low-risk cases
if report.confidence > 0.9 and is_low_risk(report.minimal_patch_strategy):
    apply_patch(report.minimal_patch_strategy)
```

## Troubleshooting

### Triage Not Running

1. Check if enabled: `config.enabled == True`
2. Verify token budget: `triage_system.within_budget()`
3. Check API credentials: Ensure LLM API keys are configured

### Low-Quality Reports

1. Increase `max_tokens` for more detailed analysis
2. Lower `temperature` for more focused responses
3. Provide more context in handoff bundle
4. Try different model (e.g., switch to GPT-4)

### Budget Exhaustion

1. Increase `token_budget` in configuration
2. Enable triage only for critical failures
3. Reset token counter between runs if needed

### Invalid JSON Responses

1. Check model output format
2. Verify prompt includes clear JSON schema
3. Increase `temperature` slightly if responses are too rigid

## Examples

### Example 1: Token Budget Exceeded

```python
handoff_bundle = {
    "phase": {
        "name": "implement-api",
        "state": "FAILED",
        "builder_attempts": 2
    },
    "failure_reason": "Output truncated",
    "diagnostics": {
        "error_type": "TokenBudgetExceeded",
        "truncated_at": 8000
    }
}

report = triage_system.generate_triage(handoff_bundle)

# Expected output:
# - Hypothesis: Token budget too low (likelihood: 0.95)
# - Missing evidence: Actual file sizes
# - Next probe: Check file sizes with ls -lh
# - Strategy: Increase max_tokens or split files
```

### Example 2: Missing Deliverables

```python
handoff_bundle = {
    "phase": {
        "name": "add-tests",
        "state": "FAILED"
    },
    "failure_reason": "Deliverables validation failed",
    "diagnostics": {
        "missing_files": [
            "tests/test_new_feature.py",
            "tests/test_integration.py"
        ]
    }
}

report = triage_system.generate_triage(handoff_bundle)

# Expected output:
# - Hypothesis: Files created in wrong directory (likelihood: 0.8)
# - Missing evidence: Directory structure
# - Next probe: find . -name "test_*.py"
# - Strategy: Move files to correct location
```

### Example 3: Test Failures

```python
handoff_bundle = {
    "phase": {
        "name": "fix-bug",
        "state": "FAILED"
    },
    "failure_reason": "Tests failed",
    "diagnostics": {
        "failed_tests": [
            "test_authentication",
            "test_authorization"
        ],
        "error_messages": [
            "AssertionError: Expected 200, got 401"
        ]
    }
}

report = triage_system.generate_triage(handoff_bundle)

# Expected output:
# - Hypothesis: Authentication logic broken (likelihood: 0.85)
# - Missing evidence: Auth token generation code
# - Next probe: Check auth middleware
# - Strategy: Review and fix token validation
```

## Related Documentation

- [Diagnostics System Overview](diagnostics_overview.md)
- [Handoff Bundle Specification](handoff_bundle.md)
- [Phase Execution Guide](phase_execution.md)
- [LLM Integration](../llm/integration.md)

## API Reference

For detailed API documentation, see:
- `src/autopack/diagnostics/second_opinion.py`
- `tests/autopack/diagnostics/test_second_opinion.py`
