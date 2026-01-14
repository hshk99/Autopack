# Model Selection Guide

This guide explains the ModelSelector system used in autopack for intelligent LLM model selection based on phase complexity, token requirements, and cost optimization.

## Table of Contents

- [Overview](#overview)
- [Model Tiers](#model-tiers)
- [Selection Logic](#selection-logic)
- [Escalation Strategy](#escalation-strategy)
- [Fallback Mechanisms](#fallback-mechanisms)
- [Decision Flowchart](#decision-flowchart)
- [Examples](#examples)
- [Best Practices](#best-practices)

---

## Overview

The ModelSelector automatically chooses the most appropriate LLM model for each phase based on:

- **Phase complexity**: Low, medium, or high
- **Token budget**: Estimated context window requirements
- **Cost efficiency**: Balancing capability with API costs
- **Availability**: Handling rate limits and fallbacks

**Key Benefits:**
- Optimized cost-to-performance ratio
- Automatic escalation for complex tasks
- Graceful degradation when models unavailable
- Consistent quality across phase types

---

## Model Tiers

The system organizes models into capability tiers:

### Tier 1: High-Capability Models

**Primary Use**: Complex refactoring, architectural changes, multi-file coordination

```python
TIER_1_MODELS = [
    'claude-3-opus-20240229',      # Best reasoning, highest cost
    'gpt-4-turbo-preview',         # Strong alternative
    'claude-3-sonnet-20240229'     # Balanced option
]
```

**Characteristics:**
- Context window: 200K tokens
- Best code generation quality
- Highest API costs
- Best for complexity='high'

---

### Tier 2: Balanced Models

**Primary Use**: Feature additions, moderate refactoring, documentation

```python
TIER_2_MODELS = [
    'claude-3-sonnet-20240229',    # Primary choice
    'gpt-4-1106-preview',          # Alternative
    'claude-3-haiku-20240307'      # Fast option
]
```

**Characteristics:**
- Context window: 100K-200K tokens
- Good code quality
- Moderate API costs
- Best for complexity='medium'

---

### Tier 3: Efficient Models

**Primary Use**: Simple docs, minor fixes, small changes

```python
TIER_3_MODELS = [
    'claude-3-haiku-20240307',     # Fast and cheap
    'gpt-3.5-turbo-16k',           # Budget option
    'claude-instant-1.2'           # Legacy fallback
]
```

**Characteristics:**
- Context window: 16K-100K tokens
- Adequate code quality
- Lowest API costs
- Best for complexity='low'

---

## Selection Logic

The ModelSelector uses a multi-factor decision algorithm:

### Step 1: Initial Tier Selection

```python
def select_initial_tier(phase_spec: Dict) -> int:
    """
    Select starting tier based on phase complexity.
    """
    complexity = phase_spec.get('complexity', 'medium')

    if complexity == 'high':
        return 1  # Start with Tier 1
    elif complexity == 'medium':
        return 2  # Start with Tier 2
    else:  # 'low'
        return 3  # Start with Tier 3
```

### Step 2: Token Budget Validation

```python
def validate_token_budget(model: str, estimated_tokens: int) -> bool:
    """
    Ensure model can handle estimated token requirement.
    """
    model_limits = {
        'claude-3-opus-20240229': 200000,
        'claude-3-sonnet-20240229': 200000,
        'gpt-4-turbo-preview': 128000,
        'claude-3-haiku-20240307': 100000,
        'gpt-3.5-turbo-16k': 16000
    }

    limit = model_limits.get(model, 100000)
    return estimated_tokens <= limit * 0.85  # 85% safety margin
```

### Step 3: Cost-Benefit Analysis

```python
def calculate_cost_score(model: str, phase_spec: Dict) -> float:
    """
    Calculate cost-effectiveness score.
    Higher score = better value.
    """
    # Cost per 1M tokens (input)
    costs = {
        'claude-3-opus-20240229': 15.0,
        'claude-3-sonnet-20240229': 3.0,
        'gpt-4-turbo-preview': 10.0,
        'claude-3-haiku-20240307': 0.25,
        'gpt-3.5-turbo-16k': 0.5
    }

    # Capability scores (0-1)
    capabilities = {
        'claude-3-opus-20240229': 1.0,
        'claude-3-sonnet-20240229': 0.85,
        'gpt-4-turbo-preview': 0.9,
        'claude-3-haiku-20240307': 0.6,
        'gpt-3.5-turbo-16k': 0.5
    }

    cost = costs.get(model, 5.0)
    capability = capabilities.get(model, 0.7)

    # Score = capability / cost (higher is better)
    return capability / cost
```

### Step 4: Final Selection

```python
def select_model(phase_spec: Dict, estimated_tokens: int) -> str:
    """
    Select optimal model for phase execution.
    """
    tier = select_initial_tier(phase_spec)
    tier_models = get_tier_models(tier)

    # Filter by token budget
    valid_models = [
        m for m in tier_models
        if validate_token_budget(m, estimated_tokens)
    ]

    if not valid_models:
        # Escalate to higher tier
        return escalate_tier(tier, estimated_tokens)

    # Select best cost-benefit ratio
    best_model = max(
        valid_models,
        key=lambda m: calculate_cost_score(m, phase_spec)
    )

    return best_model
```

---

## Escalation Strategy

Automatic escalation occurs when:
1. Token budget exceeds current tier capacity
2. Phase fails with current model
3. Quality checks indicate insufficient capability

### Escalation Rules

```python
def escalate_tier(current_tier: int, estimated_tokens: int) -> str:
    """
    Escalate to higher tier when needed.
    """
    if current_tier >= 1:
        # Already at highest tier
        raise ValueError("Cannot escalate beyond Tier 1")

    # Move up one tier
    next_tier = current_tier - 1
    tier_models = get_tier_models(next_tier)

    # Find first model that can handle tokens
    for model in tier_models:
        if validate_token_budget(model, estimated_tokens):
            return model

    # If still insufficient, try Tier 1
    if next_tier > 1:
        return escalate_tier(next_tier, estimated_tokens)

    raise ValueError("No model can handle token requirement")
```

### Escalation Triggers

**Trigger 1: Token Overflow**
```python
if estimated_tokens > current_model_limit:
    model = escalate_tier(current_tier, estimated_tokens)
```

**Trigger 2: Phase Failure**
```python
if phase_result['success'] == False and retry_count < max_retries:
    # Try higher tier on retry
    model = escalate_tier(current_tier, estimated_tokens)
```

**Trigger 3: Quality Check Failure**
```python
if quality_score < threshold:
    # Re-run with more capable model
    model = escalate_tier(current_tier, estimated_tokens)
```

---

## Fallback Mechanisms

Robust fallback handling ensures continuous operation:

### Fallback Chain

```python
FALLBACK_CHAIN = [
    # Primary: Try selected model
    lambda: selected_model,

    # Fallback 1: Try alternative in same tier
    lambda: get_tier_alternative(selected_model),

    # Fallback 2: Try previous tier (if escalated)
    lambda: get_previous_tier_model(selected_model),

    # Fallback 3: Try any available model
    lambda: get_any_available_model(),

    # Fallback 4: Fail gracefully
    lambda: None
]
```

### Rate Limit Handling

```python
def handle_rate_limit(model: str, retry_after: int) -> str:
    """
    Switch to alternative model when rate limited.
    """
    tier = get_model_tier(model)
    tier_models = get_tier_models(tier)

    # Try other models in same tier
    for alternative in tier_models:
        if alternative != model and is_available(alternative):
            return alternative

    # Fall back to lower tier if needed
    if tier < 3:
        lower_tier_models = get_tier_models(tier + 1)
        for fallback in lower_tier_models:
            if is_available(fallback):
                return fallback

    # Wait and retry original model
    time.sleep(retry_after)
    return model
```

### Availability Checking

```python
def is_available(model: str) -> bool:
    """
    Check if model is currently available.
    """
    try:
        # Quick test request
        response = llm_client.test_availability(model)
        return response.status_code == 200
    except RateLimitError:
        return False
    except Exception:
        return False
```

---

## Decision Flowchart

```
┌─────────────────────────────────────────┐
│  Phase Specification Input              │
│  - complexity: low/medium/high          │
│  - estimated_tokens: int                │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Select Initial Tier                    │
│  high → Tier 1                          │
│  medium → Tier 2                        │
│  low → Tier 3                           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Validate Token Budget                  │
│  estimated_tokens <= model_limit?       │
└──────────────┬──────────────────────────┘
               │
         ┌─────┴─────┐
         │           │
        YES          NO
         │           │
         │           ▼
         │  ┌─────────────────────┐
         │  │  Escalate Tier      │
         │  │  tier = tier - 1    │
         │  └─────────┬───────────┘
         │            │
         └────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  Calculate Cost Scores                  │
│  For each valid model in tier           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Select Best Model                      │
│  max(capability / cost)                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Check Availability                     │
│  is_available(model)?                   │
└──────────────┬──────────────────────────┘
               │
         ┌─────┴─────┐
         │           │
        YES          NO
         │           │
         │           ▼
         │  ┌─────────────────────┐
         │  │  Try Fallback       │
         │  │  - Same tier alt    │
         │  │  - Lower tier       │
         │  │  - Any available    │
         │  └─────────┬───────────┘
         │            │
         └────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  Execute Phase with Selected Model      │
└─────────────────────────────────────────┘
```

---

## Examples

### Example 1: Simple Documentation Phase

**Scenario**: Create a README file with basic project information.

**Phase Specification:**
```python
phase_spec = {
    'description': 'Create README.md with project overview',
    'category': 'docs',
    'complexity': 'low',
    'estimated_tokens': 8000,
    'context_files': ['setup.py', 'src/__init__.py']
}
```

**Selection Process:**

1. **Initial Tier Selection**:
   - Complexity = 'low' → Start with Tier 3
   - Candidate models: claude-3-haiku, gpt-3.5-turbo-16k

2. **Token Budget Validation**:
   - Estimated: 8,000 tokens
   - claude-3-haiku limit: 100,000 tokens
   - gpt-3.5-turbo-16k limit: 16,000 tokens
   - Both models valid ✓

3. **Cost-Benefit Analysis**:
   - claude-3-haiku: capability=0.6, cost=$0.25/1M → score=2.4
   - gpt-3.5-turbo-16k: capability=0.5, cost=$0.5/1M → score=1.0
   - Winner: claude-3-haiku (better score)

4. **Availability Check**:
   - claude-3-haiku available ✓

**Selected Model**: `claude-3-haiku-20240307`

**Rationale**: Simple documentation task doesn't require high-capability model. Haiku provides adequate quality at lowest cost.

---

### Example 2: Complex Refactoring Phase

**Scenario**: Refactor authentication system to support OAuth2.

**Phase Specification:**
```python
phase_spec = {
    'description': 'Refactor auth system for OAuth2 support',
    'category': 'refactor',
    'complexity': 'high',
    'estimated_tokens': 145000,
    'context_files': [
        'src/auth/base.py',
        'src/auth/session.py',
        'src/auth/middleware.py',
        'src/models/user.py',
        'tests/test_auth.py',
        'docs/auth_architecture.md'
    ]
}
```

**Selection Process:**

1. **Initial Tier Selection**:
   - Complexity = 'high' → Start with Tier 1
   - Candidate models: claude-3-opus, gpt-4-turbo, claude-3-sonnet

2. **Token Budget Validation**:
   - Estimated: 145,000 tokens
   - claude-3-opus limit: 200,000 tokens ✓
   - gpt-4-turbo limit: 128,000 tokens ✗ (145k > 128k * 0.85)
   - claude-3-sonnet limit: 200,000 tokens ✓
   - Valid models: claude-3-opus, claude-3-sonnet

3. **Cost-Benefit Analysis**:
   - claude-3-opus: capability=1.0, cost=$15/1M → score=0.067
   - claude-3-sonnet: capability=0.85, cost=$3/1M → score=0.283
   - Winner: claude-3-sonnet (better score)

4. **Availability Check**:
   - claude-3-sonnet available ✓

**Selected Model**: `claude-3-sonnet-20240229`

**Rationale**: High complexity requires Tier 1 capability, but Sonnet provides excellent balance of quality and cost for this token budget. Opus would be overkill and 5x more expensive.

**Escalation Scenario**: If phase fails quality checks:
```python
if quality_score < 0.8:
    # Escalate to Opus for retry
    model = 'claude-3-opus-20240229'
```

---

## Best Practices

### 1. Set Appropriate Complexity Levels

**Goal**: Ensure correct initial tier selection.

```python
# Good: Accurate complexity assessment
phase_spec = {
    'description': 'Add type hints to existing functions',
    'complexity': 'low'  # Simple, mechanical task
}

# Bad: Over-estimating complexity
phase_spec = {
    'description': 'Add type hints to existing functions',
    'complexity': 'high'  # Wastes money on Tier 1 model
}
```

### 2. Monitor Escalation Patterns

**Goal**: Identify phases that consistently need escalation.

```python
def analyze_escalations(execution_history):
    """
    Find phases that frequently escalate.
    """
    escalation_rate = {}

    for phase in execution_history:
        category = phase['category']
        if phase['model_tier'] > phase['initial_tier']:
            escalation_rate[category] = escalation_rate.get(category, 0) + 1

    # Adjust default complexity for high-escalation categories
    for category, count in escalation_rate.items():
        if count > 5:
            print(f"Consider increasing default complexity for {category}")
```

### 3. Implement Cost Tracking

**Goal**: Monitor and optimize API spending.

```python
def track_model_costs(phase_result):
    """
    Calculate and log phase execution costs.
    """
    model = phase_result['model']
    tokens_used = phase_result['token_usage']

    cost_per_million = MODEL_COSTS[model]
    phase_cost = (tokens_used / 1_000_000) * cost_per_million

    log_metric('phase_cost', phase_cost, {'model': model})

    return phase_cost
```

### 4. Use Fallbacks Wisely

**Goal**: Balance reliability with cost.

```python
# Good: Try same-tier alternatives first
fallback_order = [
    'claude-3-sonnet-20240229',  # Primary
    'gpt-4-1106-preview',        # Same tier alternative
    'claude-3-haiku-20240307'    # Lower tier fallback
]

# Bad: Immediately falling back to expensive model
fallback_order = [
    'claude-3-haiku-20240307',   # Primary
    'claude-3-opus-20240229'     # Expensive fallback
]
```

### 5. Test Model Selection Logic

**Goal**: Verify selection algorithm works as expected.

```python
def test_model_selection():
    """
    Unit tests for model selection.
    """
    # Test 1: Low complexity → Tier 3
    result = select_model(
        {'complexity': 'low'},
        estimated_tokens=5000
    )
    assert get_model_tier(result) == 3

    # Test 2: High tokens → Escalation
    result = select_model(
        {'complexity': 'medium'},
        estimated_tokens=180000
    )
    assert get_model_tier(result) == 1

    # Test 3: Cost optimization
    result = select_model(
        {'complexity': 'medium'},
        estimated_tokens=50000
    )
    assert result == 'claude-3-sonnet-20240229'  # Best value
```

---

*Last Updated: 2024*
*Version: 7.0*
