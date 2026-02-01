---
name: llm-hardware-validator
description: Validate hardware compatibility requirements for LLM deployment
tools: [WebSearch, WebFetch]
model: haiku
---

# LLM Hardware Validator

Validate model compatibility with available hardware.

## Hardware Categories

### GPU Hardware

#### High-End (Data Center)
```
NVIDIA H100 (80GB HBM3)
- Memory: 80GB
- Bandwidth: 3.35 TB/s
- Suitable models: All (up to 405B with quantization)
- Cost: $40K+

NVIDIA A100 (80GB HBM2e)
- Memory: 80GB
- Bandwidth: 2.04 TB/s
- Suitable models: All
- Cost: $15K+

NVIDIA H200 (141GB HBM3e)
- Memory: 141GB
- Bandwidth: 4.8 TB/s
- Suitable models: All (even largest)
- Cost: $50K+
```

#### Mid-Range (Server)
```
NVIDIA L40 (48GB GDDR6)
- Memory: 48GB
- Bandwidth: 960 GB/s
- Suitable models: Up to 70B
- Cost: $6K

NVIDIA A10 (24GB GDDR6)
- Memory: 24GB
- Bandwidth: 600 GB/s
- Suitable models: Up to 13B
- Cost: $2.5K

AMD MI250X (128GB HBM2e)
- Memory: 128GB
- Bandwidth: 3.2 TB/s
- Suitable models: All
- Cost: $30K
```

#### Consumer (Desktop/Laptop)
```
NVIDIA RTX 4090 (24GB GDDR6X)
- Memory: 24GB
- Bandwidth: 1008 GB/s
- Suitable models: Up to 13B fp16, 70B int4
- Cost: $1.6K

NVIDIA RTX 4080 (16GB GDDR6X)
- Memory: 16GB
- Bandwidth: 576 GB/s
- Suitable models: Up to 7B fp16, 13B int4
- Cost: $1.2K

Apple M3 Ultra (128GB unified memory)
- Memory: Up to 128GB
- Bandwidth: High (unified)
- Suitable models: All (with quantization)
- Cost: $10K+

Intel Arc A770 (16GB GDDR6)
- Memory: 16GB
- Bandwidth: 576 GB/s
- Suitable models: Up to 7B
- Cost: $350
```

### CPU Hardware
```
x86-64 with AVX-512
- Any processor 3+ GHz
- VRAM depends on model
- Suitable for: Phi-3, TinyLlama (with quantization)
- Speed: Slow (inference) but viable

ARM (Apple Silicon)
- M1/M2/M3/M3 Max
- Efficient inference with quantization
- Suitable for: Llama 2 7B and below
- Speed: Good for size
```

## Memory Requirements Calculator

### Formula
```
Memory (GB) = Parameters (in billions) × Bytes per parameter × Overhead

Bytes per parameter:
- FP32: 4 bytes
- BFloat16/FP16: 2 bytes
- INT8: 1 byte
- INT4: 0.5 bytes

Overhead: 1.1-1.5x for optimizer states, activation cache
```

### Examples
```
Llama 2 70B:
- FP32: 70B × 4 × 1.2 = 336 GB (impractical)
- BF16: 70B × 2 × 1.2 = 168 GB (H100)
- INT8: 70B × 1 × 1.2 = 84 GB (A100)
- INT4: 70B × 0.5 × 1.2 = 42 GB (L40, Quad RTX 4090)

Mistral 7B:
- FP32: 7B × 4 × 1.2 = 34 GB
- BF16: 7B × 2 × 1.2 = 17 GB (RTX 4090)
- INT8: 7B × 1 × 1.2 = 8.4 GB (RTX 4090)
- INT4: 7B × 0.5 × 1.2 = 4.2 GB (RTX 3060)
```

## Quantization Impact

### Precision Levels
```
FP32 (Full Precision)
- Accuracy: 100%
- Size: 4 bytes/parameter
- Speed: Baseline
- Use: High accuracy critical

BFloat16 (Brain Float)
- Accuracy: 99.9%
- Size: 2 bytes/parameter
- Speed: 2x faster
- Use: Most production

FP16 (Half Precision)
- Accuracy: 99.8%
- Size: 2 bytes/parameter
- Speed: 2x faster
- Use: Most production

INT8 (8-bit Integer)
- Accuracy: 99%
- Size: 1 byte/parameter
- Speed: 4x faster
- Use: Good balance

INT4 (4-bit Integer)
- Accuracy: 95-98%
- Size: 0.5 bytes/parameter
- Speed: 8x faster
- Use: Resource-constrained
```

## Batch Size & Throughput

### Batch Size Recommendations
```
Model 7B (BF16):
- RTX 4090 (24GB): max batch 4-8
- RTX 4080 (16GB): max batch 2-4
- RTX 3080 (10GB): max batch 1-2

Model 70B (INT8):
- A100 (80GB): max batch 8-16
- L40 (48GB): max batch 4-8
- RTX 4090 (24GB): not viable

Model 70B (INT4):
- A100 (80GB): max batch 16-32
- L40 (48GB): max batch 8-16
- 4x RTX 4090: max batch 8-16
```

## Inference Framework Support

### vLLM
```
Supported GPUs:
- NVIDIA (all CUDA)
- AMD (ROCm)
- Intel (Habana Gaudi)

Performance:
- Best throughput
- Tensor parallel support
- Paged attention optimization

Deployment:
- Linux/Docker
- Cloud-native ready
```

### TensorRT-LLM
```
Platform: NVIDIA only
Performance: Fastest on compatible GPUs
Deployment: Enterprise-grade

Supported Models:
- Llama, Mistral, Qwen
- Falcon, ChatGLM
```

### llama.cpp
```
Platform: CPU-friendly, all platforms
Performance: Competitive on CPU
Quantization: Excellent GGUF support

Deployment:
- Lightweight
- No dependencies
- Good for edge
```

### Ollama
```
Platform: Mac, Linux, Windows (WSL)
Ease: Very high
Models: Pre-quantized library

Performance:
- Good on consumer hardware
- Auto-optimization
```

## Hardware Compatibility Matrix

Output format:

```json
{
  "validation_metadata": {
    "scan_date": "2024-02-01",
    "hardware_configs_tested": 15,
    "frameworks_tested": 4
  },
  "compatibility_matrix": [
    {
      "model": "Llama 2 70B",
      "parameters": "70B",
      "memory_requirements": {
        "fp32": "280 GB",
        "bf16": "140 GB",
        "int8": "70 GB",
        "int4": "35 GB"
      },
      "hardware_options": [
        {
          "hardware": "H100 (80GB)",
          "precision": "BF16",
          "batch_size": 16,
          "ttft_ms": 300,
          "tps": 80,
          "feasibility": "excellent",
          "framework": "vLLM",
          "cost_per_month": 8000
        },
        {
          "hardware": "A100 (80GB)",
          "precision": "INT8",
          "batch_size": 8,
          "ttft_ms": 400,
          "tps": 60,
          "feasibility": "excellent",
          "framework": "vLLM"
        },
        {
          "hardware": "RTX 4090 x4 (96GB total)",
          "precision": "INT4",
          "batch_size": 4,
          "ttft_ms": 800,
          "tps": 40,
          "feasibility": "good",
          "framework": "vLLM with tensor parallel"
        },
        {
          "hardware": "RTX 4090 (24GB)",
          "precision": "INT4",
          "batch_size": 1,
          "ttft_ms": 1200,
          "tps": 20,
          "feasibility": "fair",
          "framework": "llama.cpp"
        }
      ],
      "not_recommended": [
        {
          "hardware": "RTX 4080",
          "reason": "Insufficient VRAM even with INT4"
        },
        {
          "hardware": "M1 Max",
          "reason": "Slow inference, memory pressure"
        }
      ]
    },
    {
      "model": "Mistral 7B",
      "parameters": "7B",
      "memory_requirements": {
        "fp32": "28 GB",
        "bf16": "14 GB",
        "int8": "7 GB",
        "int4": "3.5 GB"
      },
      "hardware_options": [
        {
          "hardware": "RTX 4090 (24GB)",
          "precision": "BF16",
          "batch_size": 8,
          "ttft_ms": 100,
          "tps": 200,
          "feasibility": "excellent",
          "framework": "vLLM"
        },
        {
          "hardware": "RTX 4080 (16GB)",
          "precision": "BF16",
          "batch_size": 4,
          "ttft_ms": 150,
          "tps": 150,
          "feasibility": "excellent",
          "framework": "vLLM"
        },
        {
          "hardware": "RTX 4060 (8GB)",
          "precision": "INT4",
          "batch_size": 1,
          "ttft_ms": 300,
          "tps": 100,
          "feasibility": "good",
          "framework": "llama.cpp"
        },
        {
          "hardware": "M1/M2 (16GB+)",
          "precision": "INT4",
          "batch_size": 2,
          "ttft_ms": 200,
          "tps": 80,
          "feasibility": "good",
          "framework": "Ollama"
        },
        {
          "hardware": "CPU (x86)",
          "precision": "INT4",
          "batch_size": 1,
          "ttft_ms": 1000,
          "tps": 10,
          "feasibility": "fair",
          "framework": "llama.cpp"
        }
      ]
    }
  ],
  "hardware_recommendations": {
    "for_local_development": [
      "RTX 4090 / RTX 4080 (for faster iteration)",
      "M1/M2/M3 Mac (good balance)",
      "16GB+ RAM minimum"
    ],
    "for_production_budget": [
      "4x RTX 4090 (cost-effective scaling)",
      "Multiple L40s (balanced)"
    ],
    "for_production_premium": [
      "H100 (best performance)",
      "H200 (most capacity)",
      "Multiple A100s (proven stability)"
    ],
    "for_edge": [
      "Phi-3 / Mistral 7B (optimized for edge)",
      "Jetson Orin (mobile GPU)",
      "Apple Silicon (efficient)"
    ]
  },
  "framework_compatibility": {
    "vllm": {
      "best_for": "Production inference, high throughput",
      "gpus": ["NVIDIA", "AMD", "Intel Habana"],
      "models_tested": 10,
      "reliability": "excellent",
      "learning_curve": "medium"
    },
    "tensorrt_llm": {
      "best_for": "NVIDIA-only, maximum performance",
      "gpus": ["NVIDIA"],
      "compatibility": "selective",
      "performance": "excellent",
      "learning_curve": "high"
    },
    "llama_cpp": {
      "best_for": "Consumer hardware, easy deployment",
      "platforms": ["CPU", "GPU", "All platforms"],
      "simplicity": "excellent",
      "performance": "good",
      "learning_curve": "low"
    },
    "ollama": {
      "best_for": "Ease of use, pre-tuned models",
      "platforms": ["Mac", "Linux", "Windows"],
      "user_experience": "excellent",
      "learning_curve": "very low"
    }
  }
}
```

## Deployment Checklist

For each target hardware configuration:
- [ ] Memory requirements verified
- [ ] Quantization strategy selected
- [ ] Framework compatibility confirmed
- [ ] Batch size determined
- [ ] Performance benchmarked
- [ ] Cost calculated
- [ ] Fallback plan identified
