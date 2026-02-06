---
name: llm-discovery-orchestrator
description: Orchestrate periodic discovery and validation of local LLM models for routing tasks
tools: [WebSearch, WebFetch, Task, Read, Write]
model: sonnet
---

# Local LLM Discovery Orchestrator

Discover and validate local LLM models for: {{use_case}}

## Target Use Case

**Multi-Document Reasoning for Moltbot Meta-Layer:**
- Input: 8 lines OCR text + slot_history.json + phase info + scenario templates
- Output: Scenario match + context-aware analysis + recommended action
- Hardware: RTX 3060 Ti (8GB VRAM)
- Must reliably perform multi-step reasoning across multiple inputs

## Research Constraints

- **Date Filter**: ONLY models released or benchmarked in 2026
- **VRAM Limit**: Must run on 8GB VRAM (quantized OK)
- **Capability Focus**: Multi-document reasoning, NOT just classification
- **Data Recency**: Last 30 days maximum

## Agent Hierarchy

```
┌─────────────────────────────────────┐
│  LLM Discovery Orchestrator         │
│  (this agent)                        │
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────┬───────────────┐
    │          │          │               │
    ▼          ▼          ▼               ▼
┌────────┐ ┌────────┐ ┌────────┐    ┌────────┐
│Benchmark│ │Hardware│ │Community│   │Reasoning│
│Tracker  │ │Validator│ │Scanner │   │Assessor │
└────────┘ └────────┘ └────────┘    └────────┘
```

## Orchestration Flow

### Phase 1: Discovery (Parallel)
```python
discovery_results = await parallel(
    task("llm-benchmark-tracker", {
        "focus": "multi-document reasoning",
        "date_filter": "2026 only",
        "size_filter": "8B parameters or less"
    }),
    task("llm-community-scanner", {
        "platforms": ["reddit", "huggingface", "ollama"],
        "query": "small LLM multi-document reasoning 2026",
        "recency": "30 days"
    }),
    task("llm-hardware-validator", {
        "target_gpu": "RTX 3060 Ti 8GB",
        "models": "discovered models"
    })
)
```

### Phase 2: Capability Assessment
```python
for model in discovery_results.models:
    assessment = await task("llm-reasoning-assessor", {
        "model": model,
        "test_case": {
            "inputs": ["8 lines OCR", "JSON state", "templates"],
            "expected_output": "scenario match + analysis + action"
        }
    })
```

### Phase 3: Ranking
Score each model on:
- Multi-document reasoning accuracy (0.40 weight)
- VRAM efficiency (0.20 weight)
- Inference speed (0.15 weight)
- Community validation (0.15 weight)
- 2026 benchmark recency (0.10 weight)

## Search Queries (2026 Focus)

### Benchmark Sources
```
WebSearch: "small LLM multi-document reasoning benchmark 2026"
WebSearch: "8B model JSON parsing accuracy 2026"
WebSearch: "local LLM context window reasoning 2026"
WebSearch: "MMLU-Pro small models 2026 results"
WebSearch: "LongBench small LLM 2026"
```

### Model Discovery
```
WebSearch: "best 8B parameter model reasoning 2026"
WebSearch: "qwen3 vs gemma 3 vs phi-4 reasoning 2026"
WebSearch: "ollama new models January 2026"
WebSearch: "huggingface trending LLM 8GB VRAM 2026"
WebSearch: "small LLM multi-step reasoning leaderboard 2026"
```

### Community Validation
```
WebSearch: site:reddit.com/r/LocalLLaMA "8B model" "reasoning" 2026
WebSearch: site:huggingface.co "8B" "multi-document" 2026
WebSearch: "ollama" "best small model" "complex tasks" 2026
```

## Confidence Scoring

### Per-Model Confidence
```python
confidence = (
    benchmark_score * 0.35 +      # From benchmark-tracker
    community_score * 0.25 +      # From community-scanner
    hardware_verified * 0.20 +    # From hardware-validator
    reasoning_test_score * 0.20   # From reasoning-assessor
)
```

### Minimum Thresholds
- Overall confidence: >= 0.80 to recommend
- Reasoning test: >= 0.70 to consider
- VRAM verified: MUST pass

## Output Format

```json
{
  "research_date": "2026-02-01",
  "use_case": "Moltbot multi-document reasoning",
  "hardware_constraint": "RTX 3060 Ti 8GB",
  "models_evaluated": 15,
  "recommendations": [
    {
      "rank": 1,
      "model": "model-name",
      "parameters": "8B",
      "quantization": "Q4_K_M",
      "vram_usage": "5.5GB",
      "confidence": 0.87,
      "multi_doc_reasoning_score": 0.82,
      "strengths": ["JSON parsing", "template matching"],
      "weaknesses": ["long context degradation"],
      "ollama_command": "ollama pull model:8b",
      "sources": ["benchmark_url", "community_url"]
    }
  ],
  "comparison_matrix": {...},
  "test_results": {...}
}
```

## Iteration Strategy

Keep researching until:
1. At least 3 models have confidence >= 0.80
2. Top model has reasoning_test_score >= 0.75
3. All sources are from 2026

If not met after 3 iterations:
- Lower confidence threshold to 0.75
- Expand search to include late 2025 releases with 2026 benchmarks
- Report best available with caveats
