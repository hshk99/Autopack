---
name: llm-benchmark-tracker
description: Track and compare LLM performance benchmarks from authoritative sources
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Benchmark Tracker

Track and compare LLM performance across standardized benchmarks.

## Benchmark Sources

### Primary Sources
1. **HuggingFace Open LLM Leaderboard**
   - URL: https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard
   - Metrics: MMLU, ARC, HellaSwag, TruthfulQA, GSM8K, MATH
   - Updated: Weekly

2. **LMSYS Chatbot Arena**
   - URL: https://chat.lmsys.org/?arena
   - Methodology: ELO-based human preferences
   - Coverage: 50+ models

3. **OpenRouter LLM Rankings**
   - URL: https://openrouter.ai/models
   - Metrics: Speed, quality, cost
   - Updated: Real-time

4. **Model-Specific Benchmarks**
   - Anthropic Claude benchmarks
   - OpenAI GPT benchmarks
   - Meta Llama benchmarks

## Benchmark Categories

### Language Understanding
```
MMLU (Massive Multitask Language Understanding)
- General knowledge across 57 domains
- 0-100 scale
- Target: 90+ for production models

ARC (AI2 Reasoning Challenge)
- Science reasoning tasks
- Multiple difficulty levels
- Target: 80+ for good models

HellaSwag
- Commonsense reasoning
- Natural language understanding
- Target: 85+

TruthfulQA
- Factual accuracy
- Hallucination resistance
- Target: 70+
```

### Mathematical Reasoning
```
GSM8K
- Grade school math problems
- Chain-of-thought reasoning
- Target: 80+ for models with reasoning

MATH
- University-level mathematics
- Advanced problem solving
- Target: 50+ for strong models
```

### Code Generation
```
HumanEval
- Python code generation
- 164 programming problems
- Target: 80+ for coding models

MBPP
- Mostly Basic Programming Problems
- Easier than HumanEval
- Target: 85+

DS1000
- Data science coding
- Real pandas/numpy tasks
- Target: 70+
```

### Speed & Efficiency
```
Time to First Token (TTFT)
- Latency before streaming starts
- Target: <500ms for interactive use

Tokens Per Second (TPS)
- Throughput during generation
- Target: >50 for reasonable UX

Memory Efficiency
- VRAM required (BFLOAT16)
- Target: <model_size * 1.5
```

## Data Collection Method

For each model:
1. Search official benchmark results
2. Compile from authoritative sources
3. Calculate derived metrics
4. Normalize scores (0-100 scale)
5. Note methodology and date

## Output Format

Return benchmark comparison:

```json
{
  "benchmark_snapshot": {
    "date": "2024-02-01",
    "sources": [
      "huggingface_leaderboard",
      "lmsys_arena",
      "openrouter",
      "model_papers"
    ]
  },
  "models": [
    {
      "name": "Claude 3.5 Sonnet",
      "provider": "Anthropic",
      "release_date": "2024-10",
      "benchmarks": {
        "mmlu": {
          "score": 95,
          "max": 100,
          "percentile": 99,
          "source": "anthropic_paper"
        },
        "mtbench": {
          "score": 9.2,
          "max": 10,
          "percentile": 98,
          "source": "lmsys"
        },
        "humaneval": {
          "score": 92,
          "max": 100,
          "percentile": 95,
          "source": "anthropic"
        },
        "gsm8k": {
          "score": 96.4,
          "max": 100,
          "percentile": 99,
          "source": "anthropic"
        },
        "agentic_reasoning": {
          "score": 98,
          "max": 100,
          "percentile": 99,
          "source": "anthropic_evals"
        }
      },
      "inference_metrics": {
        "ttft_ms": 400,
        "tps": 60,
        "memory_bf16_gb": 150,
        "quantization_friendly": false
      },
      "overall_score": 95.5,
      "strengths": [
        "Exceptional reasoning",
        "Code generation",
        "Long context understanding"
      ],
      "weaknesses": [
        "API-only (no local deployment)",
        "Higher cost"
      ]
    },
    {
      "name": "Mistral Large",
      "provider": "Mistral AI",
      "release_date": "2024-02",
      "benchmarks": {
        "mmlu": {
          "score": 84.0,
          "max": 100,
          "percentile": 85,
          "source": "huggingface"
        },
        "mtbench": {
          "score": 8.7,
          "max": 10,
          "percentile": 80,
          "source": "lmsys"
        },
        "humaneval": {
          "score": 85.2,
          "max": 100,
          "percentile": 88,
          "source": "huggingface"
        },
        "cost_efficiency": {
          "score": 95,
          "max": 100,
          "percentile": 99,
          "source": "openrouter"
        }
      },
      "inference_metrics": {
        "ttft_ms": 200,
        "tps": 250,
        "memory_bf16_gb": 55,
        "quantization_friendly": true
      },
      "overall_score": 85.5,
      "strengths": [
        "Good performance/cost ratio",
        "Fast inference",
        "Quantization support"
      ],
      "weaknesses": [
        "Lower reasoning than Claude",
        "Smaller context window"
      ]
    }
  ],
  "benchmark_rankings": {
    "by_mmlu": [
      { "rank": 1, "model": "Claude 3 Opus", "score": 96.2 },
      { "rank": 2, "model": "GPT-4 Turbo", "score": 95.8 },
      { "rank": 3, "model": "Claude 3.5 Sonnet", "score": 95.0 }
    ],
    "by_speed": [
      { "rank": 1, "model": "Phi-3", "tps": 600, "ttft_ms": 50 },
      { "rank": 2, "model": "Mistral 7B", "tps": 400, "ttft_ms": 100 },
      { "rank": 3, "model": "Qwen 14B", "tps": 300, "ttft_ms": 150 }
    ],
    "by_cost_efficiency": [
      { "rank": 1, "model": "Mistral 7B", "cost_per_1m_tokens": 0.14 },
      { "rank": 2, "model": "Qwen 7B", "cost_per_1m_tokens": 0.10 },
      { "rank": 3, "model": "Llama 2 70B", "cost_per_1m_tokens": 0.50 }
    ]
  },
  "benchmark_methodology": {
    "mmlu": "57-task knowledge evaluation",
    "mtbench": "Human-evaluated instruction following",
    "humaneval": "Python code generation correctness",
    "gsm8k": "Math reasoning with chain-of-thought",
    "reasoning": "Complex multi-step problem solving"
  },
  "data_quality": {
    "sources_consulted": 10,
    "data_freshness": "recent",
    "methodology_verified": true,
    "cross_validation": "complete"
  }
}
```

## Key Insights

### Top Performers
- Claude 3 Opus: Best overall reasoning
- GPT-4 Turbo: Best instruction following
- Mistral Large: Best value
- Phi-3: Best for resource-constrained

### Emerging Trends
- Reasoning models improving rapidly
- Speed improvements through quantization
- Cost-per-token decreasing
- Specialized models increasing

## Limitations

- Benchmarks may not reflect real-world performance
- Different models tested under different conditions
- Hallucination not fully captured by benchmarks
- Safety evaluations limited in scope
