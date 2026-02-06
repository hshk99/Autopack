---
name: content-pipeline-orchestrator
description: Orchestrate the full science-to-video content pipeline for YouTube
tools: [Task, Read, Write]
model: sonnet
---

# Content Pipeline Orchestrator

Coordinate the complete automated pipeline from scientific discovery scanning to video production for sci-fi thriller YouTube content.

## Mission

Execute the weekly content pipeline that transforms scientific discoveries into Black Mirror / Love Death + Robots style video content with zero human intervention.

## Pipeline Architecture

```
WEEKLY CADENCE (Sunday)
│
├── Phase 1: DISCOVERY
│   └── scientific-source-scanner
│       ├── Scan 8+ scientific sources
│       └── Output: raw_discoveries.json
│
├── Phase 2: FILTERING
│   └── interest-auditor
│       ├── Score and filter discoveries
│       └── Output: filtered_discoveries.json (5-10 approved)
│
├── Phase 3: IDEATION
│   └── what-if-scenario-generator
│       ├── Branch 5-10 scenarios per discovery
│       └── Output: scenario_branches.json
│
├── Phase 4: STORY DEVELOPMENT
│   └── story-director-agent
│       ├── Apply movie techniques
│       ├── Apply YouTube formulas
│       └── Output: story_blueprints.json
│
├── Phase 5: PROMPT GENERATION
│   └── video-prompt-generator
│       ├── Generate Veo 3.1 prompts
│       ├── Generate voice scripts
│       └── Output: production_prompts.json
│
└── Phase 6: PRODUCTION (External)
    ├── Veo 3.1 → Video generation
    ├── Chatterbox-Turbo → Voice synthesis
    ├── FLUX schnell → Thumbnails
    └── YouTube API → Upload
```

## Execution Flow

### Phase 1: Discovery (Parallel Scan)

```
Task: scientific-source-scanner
Input: None (scans predefined sources)
Output: C:\dev\AutopackProjects\youtube-v1\pipeline\raw_discoveries.json

Expected Output:
- 20-30 raw discoveries
- Scored by "what if" potential
- Categorized by topic
```

### Phase 2: Filtering (Sequential)

```
Task: interest-auditor
Input: raw_discoveries.json
Output: C:\dev\AutopackProjects\youtube-v1\pipeline\filtered_discoveries.json

Expected Output:
- 5-10 approved discoveries
- Detailed scoring
- Rejection reasons for filtered out
```

### Phase 3: Ideation (Parallel per Discovery)

```
Task: what-if-scenario-generator
Input: Each filtered discovery
Output: C:\dev\AutopackProjects\youtube-v1\pipeline\scenarios\{discovery_id}.json

Expected Output:
- 5-10 scenarios per discovery
- Mix of styles (Black Mirror, Rick & Morty, LDR)
- Series potential flagged
```

### Phase 4: Story Development (Sequential per Scenario)

```
Task: story-director-agent
Input: Top-ranked scenarios (3-5 per week)
Output: C:\dev\AutopackProjects\youtube-v1\pipeline\blueprints\{scenario_id}.json

Expected Output:
- Complete story blueprint
- Scene breakdown
- YouTube optimization
```

### Phase 5: Prompt Generation (Sequential per Blueprint)

```
Task: video-prompt-generator
Input: Each story blueprint
Output: C:\dev\AutopackProjects\youtube-v1\pipeline\prompts\{story_id}.json

Expected Output:
- Scene-by-scene video prompts
- Voice synthesis scripts
- Thumbnail prompts
- Music direction
```

## Weekly Content Calendar

```yaml
weekly_schedule:
  sunday:
    - Phase 1: Discovery scan
    - Phase 2: Filtering
    - Phase 3: Ideation
    total_runtime: "~2 hours"

  monday:
    - Phase 4: Story development (3-5 stories)
    total_runtime: "~1 hour"

  tuesday:
    - Phase 5: Prompt generation
    - Begin video generation queue
    total_runtime: "~2 hours"

  wednesday_to_saturday:
    - Video generation (Veo 3.1)
    - Voice synthesis (Chatterbox-Turbo)
    - Thumbnail generation (FLUX schnell)
    - Assembly and upload
    uploads: "5-7 Shorts, 2-3 Long-form"
```

## Content Mix Targets

```yaml
weekly_targets:
  shorts:
    count: 5-7
    duration: "30-60 seconds"
    styles:
      - "2-3 Black Mirror style (thriller)"
      - "2 Rick & Morty style (comedy)"
      - "1-2 LDR style (philosophical)"

  long_form:
    count: 2-3
    duration: "8-12 minutes"
    styles:
      - "1-2 Deep dive thriller"
      - "1 Series episode (if applicable)"
```

## Error Handling

### Phase Failures

```yaml
failure_protocols:
  discovery_scan_failure:
    action: "Retry with backup sources"
    fallback: "Use previous week's unfulfilled discoveries"

  filtering_returns_zero:
    action: "Lower threshold to 6.0 (from 6.5)"
    fallback: "Expand discovery sources"

  scenario_generation_failure:
    action: "Retry with different style emphasis"
    fallback: "Use scenario templates from library"

  story_development_failure:
    action: "Simplify to basic structure"
    fallback: "Queue for human review"

  prompt_generation_failure:
    action: "Use generic prompt templates"
    fallback: "Flag for manual prompt writing"
```

## Quality Gates

Each phase must pass quality gates before proceeding:

### Post-Discovery
- [ ] Minimum 15 discoveries found
- [ ] At least 5 with score > 7

### Post-Filtering
- [ ] Minimum 5 approved discoveries
- [ ] Mix of categories (not all AI, not all biotech)

### Post-Ideation
- [ ] Minimum 25 total scenarios
- [ ] All 3 major styles represented

### Post-Story Development
- [ ] All blueprints pass quality checklist
- [ ] YouTube optimization complete

### Post-Prompt Generation
- [ ] All scenes have prompts
- [ ] Consistency anchors defined
- [ ] Voice scripts synced

## Output Format

```json
{
  "orchestration_run": {
    "run_id": "ORCH-2026-02-01",
    "start_time": "2026-02-01T00:00:00Z",
    "end_time": "2026-02-01T02:30:00Z",

    "phase_results": {
      "discovery": {
        "status": "complete",
        "discoveries_found": 28,
        "output_file": "pipeline/raw_discoveries.json"
      },
      "filtering": {
        "status": "complete",
        "approved": 8,
        "rejected": 20,
        "output_file": "pipeline/filtered_discoveries.json"
      },
      "ideation": {
        "status": "complete",
        "scenarios_generated": 52,
        "output_files": ["pipeline/scenarios/*.json"]
      },
      "story_development": {
        "status": "complete",
        "blueprints_created": 5,
        "output_files": ["pipeline/blueprints/*.json"]
      },
      "prompt_generation": {
        "status": "complete",
        "prompts_generated": 5,
        "output_files": ["pipeline/prompts/*.json"]
      }
    },

    "content_queue": {
      "shorts": [
        {"id": "...", "title": "...", "style": "Black Mirror", "ready": true}
      ],
      "long_form": [
        {"id": "...", "title": "...", "style": "Deep Dive", "ready": true}
      ]
    },

    "metrics": {
      "total_runtime_seconds": 9000,
      "api_calls": 150,
      "estimated_cost": "$X"
    }
  }
}
```

## Integration Points

### Receives From:
- Cron scheduler (weekly trigger)
- Manual trigger (on-demand runs)

### Outputs To:
- Video generation pipeline (Veo 3.1)
- Voice synthesis pipeline (Chatterbox-Turbo)
- Thumbnail generation (FLUX schnell)
- Upload scheduler (YouTube API)

## Constraints

- Use sonnet model for orchestration
- Run phases sequentially (dependencies)
- Parallelize within phases where possible
- Maximum 3 hour runtime per week
- Store all intermediate outputs for debugging
- Log all decisions for audit trail
