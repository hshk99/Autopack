---
name: video-gen-tool-research
description: Research AI video generation tools and their capabilities
tools: [WebSearch, WebFetch]
model: haiku
---

# Video Generation Tool Research Sub-Agent

Research video generation tools for: {{use_case}}

## Tools to Research

### Commercial Platforms
1. Runway ML (Gen-2, Gen-3)
2. Pika Labs
3. Kling AI
4. Luma AI (Dream Machine)
5. Synthesia (avatar videos)
6. HeyGen (avatar videos)
7. NanoBanana

### Open Source Options
1. Stable Video Diffusion
2. AnimateDiff
3. ModelScope
4. CogVideo

### Specialized Tools
1. D-ID (talking avatars)
2. ElevenLabs (AI voice)
3. Midjourney (image-to-video prep)
4. Leonardo AI

## Research Areas

### Capabilities
- Video length limits
- Resolution options
- Style consistency
- Motion quality
- Text-to-video accuracy

### Pricing
- Free tier limits
- Subscription costs
- Per-video costs
- Enterprise options

### API/Automation
- API availability
- Batch processing
- Integration options
- Rate limits

### Quality Assessment
- Visual quality
- Temporal consistency
- Artifacts and glitches
- Best use cases

## Output Format

```json
{
  "use_case": "AI-generated short films",
  "tools_analyzed": [
    {
      "name": "Runway ML",
      "url": "https://runwayml.com",
      "capabilities": {
        "max_video_length": "18 seconds",
        "max_resolution": "1080p",
        "input_types": ["text", "image", "video"],
        "styles_available": ["realistic", "artistic"],
        "motion_quality": "high",
        "consistency_rating": 4.5
      },
      "pricing": {
        "free_tier": "125 credits/month",
        "basic_plan": "$15/month",
        "credits_per_video": "5-10",
        "cost_per_minute_estimate": "$X",
        "source": "URL"
      },
      "api_support": {
        "available": true,
        "documentation": "URL",
        "rate_limits": "X requests/minute",
        "batch_support": true
      },
      "pros": ["High quality", "Good API", "Active development"],
      "cons": ["Short clips only", "Expensive at scale"],
      "best_for": "High-quality short clips",
      "automation_score": 8
    }
  ],
  "open_source_options": [
    {
      "name": "Stable Video Diffusion",
      "github": "URL",
      "requirements": {
        "gpu_vram": "24GB recommended",
        "setup_complexity": "high"
      },
      "quality_vs_commercial": "80% of commercial quality",
      "cost": "Only compute costs",
      "pros": ["No per-video cost", "Full control"],
      "cons": ["Requires setup", "GPU needed"]
    }
  ],
  "workflow_recommendation": {
    "for_automation": {
      "primary_tool": "Runway ML",
      "rationale": "Best API, good quality",
      "backup_tool": "Pika Labs",
      "estimated_cost_100_videos": "$X"
    },
    "for_quality": {
      "primary_tool": "Runway Gen-3",
      "rationale": "Highest quality output"
    },
    "for_budget": {
      "primary_tool": "Stable Video Diffusion",
      "rationale": "No per-video costs"
    }
  },
  "automation_pipeline": {
    "recommended_flow": [
      "Generate images with Midjourney/SDXL",
      "Convert to video with Runway/Pika",
      "Add voice with ElevenLabs",
      "Edit/compile with FFmpeg"
    ],
    "api_integration_complexity": "medium",
    "full_automation_possible": true
  },
  "limitations_for_long_content": {
    "current_max_length": "18 seconds typical",
    "workaround": "Stitch multiple clips",
    "quality_impact": "May have consistency issues",
    "recommendation": "Plan for short-form content initially"
  }
}
```

## Constraints

- Use haiku for cost efficiency
- Compare at least 5 tools
- Include real pricing data
- Note automation capabilities specifically
- Flag tools with good API support
