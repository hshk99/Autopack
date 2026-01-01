# Token Estimation Guide

This guide explains the TokenEstimationV2 system used in autopack for predicting and managing token budgets during autonomous build phases.

## Table of Contents

- [Overview](#overview)
- [How Token Estimation Works](#how-token-estimation-works)
- [Configuration Constants](#configuration-constants)
  - [PHASE_OVERHEAD](#phase_overhead)
  - [TOKEN_WEIGHTS](#token_weights)
- [Budget Selection Logic](#budget-selection-logic)
- [Real-World Example](#real-world-example)
- [Best Practices](#best-practices)

---

## Overview

The TokenEstimationV2 system provides accurate token budget predictions for LLM context windows during phase execution. It accounts for:

- **System prompts and instructions**: Fixed overhead per phase
- **Context files**: Variable cost based on file size and type
- **Phase specifications**: Description, criteria, and metadata
- **Output buffer**: Reserved space for LLM responses

Accurate token estimation is critical for:
- Preventing context window overflow
- Optimizing context file selection
- Ensuring sufficient output space
- Managing API costs

---

## How Token Estimation Works

The token estimation process follows these steps:

### 1. Calculate Base Overhead

Every phase has fixed overhead from system prompts and instructions:

```python
base_overhead = PHASE_OVERHEAD['system_prompt'] + \
                PHASE_OVERHEAD['instructions'] + \
                PHASE_OVERHEAD['output_buffer']
```

### 2. Estimate Phase Specification Cost

The phase spec includes description, criteria, and metadata:

```python
phase_spec_tokens = len(phase_description) // 4 + \
                    len(acceptance_criteria) // 4 + \
                    PHASE_OVERHEAD['metadata']
```

**Note**: The `// 4` approximation assumes ~4 characters per token (standard for English text).

### 3. Calculate Context File Costs

Each context file is weighted based on its type:

```python
for file_path in context_files:
    file_size = get_file_size(file_path)
    file_type = get_file_extension(file_path)
    weight = TOKEN_WEIGHTS.get(file_type, TOKEN_WEIGHTS['default'])
    
    # Estimate tokens: (size in chars / 4) * weight
    file_tokens = (file_size // 4) * weight
    total_context_tokens += file_tokens
```

### 4. Sum Total Estimate

```python
total_estimate = base_overhead + \
                 phase_spec_tokens + \
                 total_context_tokens
```

### 5. Apply Safety Margin

A 10% safety margin accounts for estimation variance:

```python
final_estimate = total_estimate * 1.10
```

---

## Configuration Constants

### PHASE_OVERHEAD

Fixed token costs for phase execution components:

```python
PHASE_OVERHEAD = {
    'system_prompt': 1500,      # Base system instructions
    'instructions': 2000,       # Phase execution guidelines
    'metadata': 500,            # Phase metadata (category, complexity)
    'output_buffer': 8000,      # Reserved space for LLM response
    'json_structure': 300       # JSON formatting overhead
}
```

**Breakdown:**

- **system_prompt** (1500 tokens): Core system instructions defining the autonomous build agent's role and capabilities
- **instructions** (2000 tokens): Detailed guidelines for code generation, including:
  - Output format requirements (JSON structure)
  - File modification rules
  - Protected path constraints
  - Code quality standards
- **metadata** (500 tokens): Phase-specific metadata:
  - Category (docs, feature, refactor, etc.)
  - Complexity level (low, medium, high)
  - Deliverable file paths
  - Acceptance criteria count
- **output_buffer** (8000 tokens): Reserved space for LLM-generated code:
  - Allows for complete file content generation
  - Accommodates multiple file changes
  - Includes JSON structure overhead
- **json_structure** (300 tokens): JSON formatting overhead:
  - Object delimiters and keys
  - Array structures
  - String escaping

**Total Base Overhead**: ~12,300 tokens before any context files

---

### TOKEN_WEIGHTS

Weighting factors for different file types, reflecting their token density:

```python
TOKEN_WEIGHTS = {
    '.py': 1.2,          # Python: docstrings, type hints increase density
    '.js': 1.1,          # JavaScript: similar to Python
    '.ts': 1.2,          # TypeScript: type annotations
    '.md': 0.9,          # Markdown: lower density (formatting chars)
    '.txt': 0.8,         # Plain text: lowest density
    '.json': 1.0,        # JSON: baseline
    '.yaml': 0.95,       # YAML: slightly below baseline
    '.yml': 0.95,        # YAML (alternate extension)
    '.toml': 0.95,       # TOML: similar to YAML
    '.html': 1.1,        # HTML: tags increase density
    '.css': 1.0,         # CSS: baseline
    '.sql': 1.1,         # SQL: keywords and structure
    'default': 1.0       # Unknown types: baseline
}
```

**Rationale:**

- **Python/TypeScript (1.2x)**: Higher weight due to:
  - Type annotations and hints
  - Docstrings and comments
  - Import statements
  - Decorator syntax
  
- **Markdown (0.9x)**: Lower weight due to:
  - Formatting characters (*, #, -, etc.)
  - Whitespace for readability
  - Link syntax overhead
  
- **Plain Text (0.8x)**: Lowest weight:
  - No syntax overhead
  - Natural language (fewer tokens per char)
  - Minimal structure

---

## Budget Selection Logic

The system selects an appropriate token budget based on the estimated requirement:

### Budget Tiers

```python
BUDGET_TIERS = [
    50000,      # Small phases: simple docs, minor fixes
    100000,     # Medium phases: feature additions, refactoring
    150000,     # Large phases: complex features, major refactors
    200000      # Maximum: comprehensive changes, multiple files
]
```

### Selection Algorithm

```python
def select_budget(estimated_tokens: int) -> int:
    """
    Select the smallest budget tier that accommodates the estimate.
    
    Args:
        estimated_tokens: Total estimated token requirement
        
    Returns:
        Selected budget from BUDGET_TIERS
    """
    for budget in BUDGET_TIERS:
        if estimated_tokens <= budget * 0.85:  # Use 85% threshold
            return budget
    
    # If estimate exceeds all tiers, return maximum
    return BUDGET_TIERS[-1]
```

**Key Points:**

1. **85% Threshold**: Budget is selected when estimate is ≤85% of tier capacity
   - Provides 15% headroom for variance
   - Prevents context window overflow
   - Accounts for estimation inaccuracies

2. **Tier Progression**: Each tier roughly doubles the previous
   - Allows efficient scaling
   - Minimizes over-allocation
   - Covers wide range of phase complexities

3. **Maximum Fallback**: If estimate exceeds all tiers:
   - Returns maximum budget (200K)
   - Logs warning for review
   - May require context reduction

---

## Real-World Example

Here's a real example from the autopack codebase showing token estimation for a documentation phase:

### Phase Specification

```python
phase_spec = {
    "description": "Create token estimation guide (≤350 lines). "
                   "Explain TokenEstimationV2: how it works, PHASE_OVERHEAD, "
                   "TOKEN_WEIGHTS, budget selection logic. Include 1 real example.",
    "category": "docs",
    "complexity": "medium",
    "acceptance_criteria": [
        "Document TokenEstimationV2 system comprehensively",
        "Explain PHASE_OVERHEAD constants with rationale",
        "Explain TOKEN_WEIGHTS with file type examples",
        "Document budget selection algorithm",
        "Include 1 real example from codebase"
    ],
    "deliverables": [
        "examples/telemetry_v7_docs/token_estimation_guide.md"
    ]
}
```

### Context Files

```python
context_files = [
    "src/autopack/token_estimator.py",           # 450 lines, .py
    "src/autopack/phase_executor.py",            # 380 lines, .py
    "src/autopack/context_builder.py",           # 290 lines, .py
    "examples/telemetry_v7_docs/api_reference.md",  # 405 lines, .md
    "README.md",                                  # 180 lines, .md
    "pyproject.toml"                              # 65 lines, .toml
]
```

### Token Estimation Calculation

```python
# Step 1: Base overhead
base_overhead = 1500 + 2000 + 500 + 8000 + 300  # 12,300 tokens

# Step 2: Phase spec
phase_description_chars = 250
phase_criteria_chars = 400
phase_spec_tokens = (250 // 4) + (400 // 4) + 500  # ~662 tokens

# Step 3: Context files
context_tokens = 0

# token_estimator.py: 450 lines * 80 chars/line = 36,000 chars
context_tokens += (36000 // 4) * 1.2  # 10,800 tokens

# phase_executor.py: 380 lines * 80 chars/line = 30,400 chars
context_tokens += (30400 // 4) * 1.2  # 9,120 tokens

# context_builder.py: 290 lines * 80 chars/line = 23,200 chars
context_tokens += (23200 // 4) * 1.2  # 6,960 tokens

# api_reference.md: 405 lines * 70 chars/line = 28,350 chars
context_tokens += (28350 // 4) * 0.9  # 6,379 tokens

# README.md: 180 lines * 70 chars/line = 12,600 chars
context_tokens += (12600 // 4) * 0.9  # 2,835 tokens

# pyproject.toml: 65 lines * 50 chars/line = 3,250 chars
context_tokens += (3250 // 4) * 0.95  # 772 tokens

# Total context: ~36,866 tokens

# Step 4: Sum total
total_estimate = 12300 + 662 + 36866  # 49,828 tokens

# Step 5: Apply 10% safety margin
final_estimate = 49828 * 1.10  # 54,811 tokens

# Step 6: Select budget
# 54,811 <= 100,000 * 0.85 (85,000)? Yes!
selected_budget = 100000  # 100K tier
```

### Result

```python
{
    "estimated_tokens": 54811,
    "selected_budget": 100000,
    "utilization": "54.8%",
    "headroom": 45189,
    "breakdown": {
        "base_overhead": 12300,
        "phase_spec": 662,
        "context_files": 36866,
        "safety_margin": 4983
    }
}
```

**Analysis:**

- **Efficient Budget Use**: 54.8% utilization leaves ample headroom
- **Context Optimization**: 6 files provide sufficient context without bloat
- **Safety Margin**: 45K tokens available for variance and output
- **Tier Selection**: 100K tier is appropriate (50K would be too tight)

---

## Best Practices

### 1. Minimize Context Files

**Goal**: Include only files directly relevant to the phase.

```python
# ❌ Bad: Including entire module
context_files = glob.glob("src/autopack/**/*.py")

# ✅ Good: Targeted selection
context_files = [
    "src/autopack/token_estimator.py",
    "src/autopack/phase_executor.py"
]
```

### 2. Prefer Smaller Files

**Goal**: Use focused modules over large monoliths.

```python
# ❌ Bad: Large file with many unrelated functions
context_files = ["src/utils/helpers.py"]  # 2000 lines

# ✅ Good: Specific utility module
context_files = ["src/utils/token_utils.py"]  # 150 lines
```

### 3. Monitor Token Usage

**Goal**: Track actual vs. estimated usage to improve accuracy.

```python
from autopack.telemetry import track_token_usage

result = executor.execute_phase(phase_spec, context_files)

track_token_usage(
    phase_id=phase_spec['id'],
    estimated=estimated_tokens,
    actual=result['token_usage'],
    variance=(result['token_usage'] - estimated_tokens) / estimated_tokens
)
```

### 4. Adjust Weights for Custom File Types

**Goal**: Fine-tune weights based on your codebase characteristics.

```python
# Add custom weights for domain-specific files
TOKEN_WEIGHTS.update({
    '.proto': 1.15,      # Protocol buffers
    '.graphql': 1.1,     # GraphQL schemas
    '.tf': 1.2,          # Terraform configs
})
```

### 5. Handle Large Context Gracefully

**Goal**: Reduce context when estimates exceed budgets.

```python
def optimize_context(context_files, max_budget):
    """
    Reduce context files if estimate exceeds budget.
    """
    estimated = estimate_tokens(context_files)
    
    if estimated > max_budget * 0.85:
        # Sort by relevance score
        sorted_files = sort_by_relevance(context_files)
        
        # Include files until budget threshold
        optimized = []
        running_total = PHASE_OVERHEAD['total']
        
        for file in sorted_files:
            file_tokens = estimate_file_tokens(file)
            if running_total + file_tokens <= max_budget * 0.85:
                optimized.append(file)
                running_total += file_tokens
            else:
                break
        
        return optimized
    
    return context_files
```

---

*Last Updated: 2024*
*Version: 7.0*
