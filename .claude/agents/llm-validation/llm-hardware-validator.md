---
name: llm-hardware-validator
description: Validate LLM models against specific hardware constraints
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Hardware Validator Sub-Agent

Validate models for: {{target_gpu}}
Models to validate: {{models}}

## Hardware Specification

**Target GPU: RTX 3060 Ti**
- VRAM: 8GB GDDR6
- CUDA Cores: 4864
- Memory Bandwidth: 448 GB/s
- Compute Capability: 8.6

## Validation Queries

### VRAM Usage
```
WebSearch: "{{model_name}}" VRAM usage "8GB" 2026
WebSearch: "{{model_name}}" Q4_K_M memory footprint
WebSearch: "ollama" "{{model_name}}" "RTX 3060" 2026
WebSearch: "{{model_name}}" quantization VRAM requirements
```

### Performance Benchmarks
```
WebSearch: "{{model_name}}" tokens per second "RTX 3060"
WebSearch: "{{model_name}}" inference speed consumer GPU 2026
WebSearch: "ollama" "{{model_name}}" performance benchmarks
```

### Community Reports
```
WebSearch: site:reddit.com/r/LocalLLaMA "{{model_name}}" "8GB VRAM"
WebSearch: site:reddit.com/r/ollama "{{model_name}}" "RTX 3060"
```

## Validation Criteria

### VRAM Compatibility
| Quantization | Max Model Size | VRAM Headroom |
|--------------|----------------|---------------|
| Q4_K_M | 8B | ~2.5GB free |
| Q5_K_M | 7B | ~1.5GB free |
| Q6_K | 6B | ~1GB free |
| FP16 | 4B | ~1GB free |

### Performance Thresholds
- Minimum: 20 tokens/second
- Acceptable: 35 tokens/second
- Good: 50+ tokens/second

### Stability Requirements
- Must not OOM during inference
- Must handle 4K context window
- Should handle 8K context (degraded OK)

## Output Format

```json
{
  "target_gpu": "RTX 3060 Ti 8GB",
  "models_validated": [
    {
      "model": "qwen3-8b",
      "quantization": "Q4_K_M",
      "vram_required": "5.5GB",
      "vram_headroom": "2.5GB",
      "fits_8gb": true,
      "tokens_per_second": 45,
      "max_context_stable": 8192,
      "validation_source": "reddit + ollama docs",
      "confidence": 0.90,
      "notes": "Runs comfortably, tested by multiple users"
    },
    {
      "model": "some-10b-model",
      "quantization": "Q4_K_M",
      "vram_required": "7.2GB",
      "vram_headroom": "0.8GB",
      "fits_8gb": true,
      "tokens_per_second": 28,
      "max_context_stable": 4096,
      "validation_source": "community report",
      "confidence": 0.70,
      "notes": "Tight fit, may OOM with long context"
    }
  ],
  "rejected_models": [
    {
      "model": "large-12b-model",
      "reason": "Requires 9.5GB VRAM even with Q4",
      "alternative": "Use 8B variant instead"
    }
  ]
}
```

## Constraints

- FAIL models that require >7.5GB VRAM (need headroom)
- WARN models between 6.5-7.5GB (marginal)
- PASS models under 6.5GB (comfortable)
- Require at least 2 independent sources for validation
