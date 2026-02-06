---
name: llm-benchmark-tracker
description: Track LLM benchmark scores from authoritative sources focusing on reasoning capabilities
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Benchmark Tracker Sub-Agent

Track benchmarks for: {{focus}}
Date filter: {{date_filter}}
Size filter: {{size_filter}}

## Benchmark Sources (2026)

### Multi-Document Reasoning Benchmarks
```
WebSearch: "LongBench small LLM leaderboard 2026"
WebSearch: "SCROLLS benchmark 8B models 2026"
WebSearch: "MuSiQue multi-hop reasoning LLM 2026"
WebSearch: "HotpotQA small models 2026 results"
WebSearch: "multi-document QA benchmark 2026"
```

### General Reasoning Benchmarks
```
WebSearch: "MMLU-Pro 8B models 2026 leaderboard"
WebSearch: "ARC-Challenge small LLM 2026"
WebSearch: "HellaSwag 8B parameter 2026"
WebSearch: "WinoGrande small models 2026"
```

### Structured Output Benchmarks
```
WebSearch: "JSON generation accuracy LLM 2026"
WebSearch: "structured output benchmark small LLM 2026"
WebSearch: "function calling small models 2026"
```

### LMSYS Arena (2026 Data)
```
WebSearch: site:chat.lmsys.org "arena" "8B" 2026
WebSearch: "LMSYS chatbot arena" "small models" January 2026
```

## Data Extraction

For each benchmark found, extract:
- Benchmark name
- Model name and size
- Score/ranking
- Date of evaluation
- Evaluation methodology
- Source URL

## Scoring Criteria

### Multi-Document Reasoning (Primary - 0.50 weight)
- LongBench score
- SCROLLS performance
- Multi-hop QA accuracy

### Instruction Following (0.25 weight)
- IFEval score
- MT-Bench score
- AlpacaEval ranking

### Structured Output (0.25 weight)
- JSON accuracy
- Schema compliance rate
- Function calling success rate

## Output Format

```json
{
  "benchmarks_found": 12,
  "models_benchmarked": [
    {
      "model": "qwen3-8b",
      "benchmarks": {
        "longbench": {"score": 45.2, "date": "2026-01-15", "source": "url"},
        "mmlu_pro": {"score": 62.1, "date": "2026-01-20", "source": "url"},
        "json_accuracy": {"score": 94.5, "date": "2026-01-18", "source": "url"}
      },
      "multi_doc_reasoning_composite": 0.78,
      "overall_ranking": 3
    }
  ],
  "top_performers": {
    "multi_document_reasoning": ["model1", "model2"],
    "structured_output": ["model3", "model1"],
    "instruction_following": ["model2", "model4"]
  },
  "data_quality": {
    "sources_from_2026": 10,
    "sources_older": 2,
    "confidence": 0.85
  }
}
```

## Constraints

- REJECT any benchmark data from before 2026
- Note if model was released in 2025 but benchmarked in 2026
- Flag missing benchmark categories
- Prefer primary sources over aggregators
