---
name: llm-community-scanner
description: Scan community feedback on LLM models from Reddit, HuggingFace, and Ollama
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Community Scanner Sub-Agent

Scan community for: {{query}}
Platforms: {{platforms}}
Recency: {{recency}}

## Platform-Specific Searches

### Reddit r/LocalLLaMA (2026)
```
WebSearch: site:reddit.com/r/LocalLLaMA "multi-document" "8B" 2026
WebSearch: site:reddit.com/r/LocalLLaMA "reasoning" "small model" January 2026
WebSearch: site:reddit.com/r/LocalLLaMA "best 8B model" "complex tasks" 2026
WebSearch: site:reddit.com/r/LocalLLaMA "qwen3" OR "gemma 3" OR "phi-4" 2026
WebSearch: site:reddit.com/r/LocalLLaMA "ollama" "recommendation" 2026
```

### Reddit r/Ollama (2026)
```
WebSearch: site:reddit.com/r/ollama "best model" "reasoning" 2026
WebSearch: site:reddit.com/r/ollama "8GB VRAM" recommendation 2026
WebSearch: site:reddit.com/r/ollama "complex prompts" small model 2026
```

### HuggingFace (2026)
```
WebSearch: site:huggingface.co "8B" "reasoning" 2026 model
WebSearch: site:huggingface.co "multi-document" LLM 2026
WebSearch: "huggingface trending" "8B" January 2026
```

### Ollama Community
```
WebSearch: site:ollama.com "library" "8b" 2026
WebSearch: "ollama" "new models" January 2026
WebSearch: "ollama" "best for reasoning" 2026
```

### Hacker News
```
WebSearch: site:news.ycombinator.com "small LLM" "reasoning" 2026
WebSearch: site:news.ycombinator.com "local LLM" "8B" 2026
```

## Sentiment Extraction

For each discussion found, extract:
- Model mentioned
- Use case described
- Positive/negative sentiment
- Specific capability praised/criticized
- Hardware mentioned (if any)
- Date of discussion

## Multi-Document Reasoning Signals

Look for mentions of:
- "multi-step reasoning"
- "context understanding"
- "JSON parsing"
- "following complex instructions"
- "multiple inputs"
- "document understanding"
- "RAG performance"

## Red Flags to Capture

- "hallucinations"
- "doesn't follow instructions"
- "loses context"
- "rambles"
- "can't parse JSON"
- "invents things"

## Output Format

```json
{
  "discussions_analyzed": 45,
  "models_mentioned": [
    {
      "model": "qwen3-8b",
      "mention_count": 23,
      "sentiment": {
        "positive": 18,
        "neutral": 3,
        "negative": 2
      },
      "praised_for": [
        "instruction following",
        "JSON output",
        "reasoning ability"
      ],
      "criticized_for": [
        "verbose responses sometimes"
      ],
      "multi_doc_mentions": 5,
      "community_score": 0.85,
      "representative_quotes": [
        {
          "source": "reddit",
          "quote": "Qwen3-8B handles my complex prompts better than...",
          "date": "2026-01-25",
          "url": "..."
        }
      ]
    }
  ],
  "emerging_models": [
    {
      "model": "new-model-name",
      "first_mentioned": "2026-01-20",
      "hype_level": "high",
      "capabilities_claimed": ["reasoning", "speed"]
    }
  ],
  "consensus_recommendations": {
    "for_reasoning": "model-x",
    "for_speed": "model-y",
    "for_8gb_vram": "model-z"
  }
}
```

## Constraints

- Only include discussions from 2026
- Require at least 3 mentions to include a model
- Weight recent discussions higher (last 30 days)
- Distinguish between hype and validated claims
