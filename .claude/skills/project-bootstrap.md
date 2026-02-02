---
name: project-bootstrap
description: Bootstrap a new project from rough idea to Autopack-ready state
invocable: true
tools: [Task, WebSearch, WebFetch, Read, Write, Bash]
model: sonnet
---

# Project Bootstrap Skill

Usage: `/project-bootstrap <project_idea_or_file> [--output <path>] [--name <project-name>]`

## Overview

This skill orchestrates the complete research pipeline to transform a rough project idea into a fully validated, Autopack-ready project with intention anchors.

## Project Isolation

**Important:** Projects are created in a SEPARATE location from Autopack to avoid:
- Lint failures from mixed codebases
- CI conflicts during parallel development
- Git history pollution

### Default Output Location
```
AUTOPACK_PROJECTS_ROOT (default: C:\dev\AutopackProjects)
└── {project-name}\
    ├── .autopack\research\     # Research outputs
    ├── .autopack\synthesis\    # Synthesis outputs
    ├── intention_anchor.yaml
    └── READY_FOR_AUTOPACK
```

### Custom Output
```
/project-bootstrap "My idea" --output C:\dev\my-projects\custom-project
```

## Pipeline Stages

```
Stage 1: Idea Parsing
    ↓
Stage 2: Discovery (Parallel)
    ├── Web Discovery Agent
    ├── GitHub Discovery Agent
    └── Social Discovery Agent
    ↓
Stage 3: Research (Parallel)
    ├── Market Research Agent
    ├── Competitive Analysis Agent
    ├── Technical Feasibility Agent
    ├── Legal/Policy Agent
    ├── Social Sentiment Agent
    └── Tool Availability Agent
    ↓
Stage 4: Framework Scoring
    ├── Market Attractiveness
    ├── Competitive Intensity
    ├── Product Feasibility
    └── Adoption Readiness
    ↓
Stage 5: Analysis
    ├── Source Evaluation
    ├── Cross-Reference Analysis
    └── Compilation
    ↓
Stage 6: Validation (Parallel)
    ├── Citation Validation
    ├── Evidence Validation
    ├── Quality Validation
    └── Recency Validation
    ↓
Stage 7: Synthesis
    ├── Meta Audit
    └── Anchor Generation
    ↓
Stage 8: Autopack Handoff
```

## Execution Steps

### Step 1: Parse Input
```
Read project idea from file or description
Extract:
- Core concept
- Target market hints
- Technical requirements hints
- Constraints/preferences
```

### Step 2: Run Discovery Layer
```
Parallel execution:
- Task: web-discovery-agent
- Task: github-discovery-agent
- Task: social-discovery-agent

Aggregate results → discovery_outputs/
```

### Step 3: Run Research Layer
```
Parallel execution using discovery outputs:
- Task: market-research-agent
- Task: competitive-analysis-agent
- Task: technical-feasibility-agent
- Task: legal-policy-agent
- Task: social-sentiment-agent
- Task: tool-availability-agent

Aggregate results → research_outputs/
```

### Step 4: Apply Frameworks
```
Sequential (depends on research):
- Task: market-attractiveness-agent
- Task: competitive-intensity-agent
- Task: product-feasibility-agent
- Task: adoption-readiness-agent

Results → framework_scores/
```

### Step 5: Run Analysis
```
Sequential:
1. Task: source-evaluator → source_evaluation.json
2. Task: cross-reference-agent → cross_reference.json
3. Task: compilation-agent → compiled_outputs/
```

### Step 6: Run Validation
```
Parallel:
- Task: citation-validator
- Task: evidence-validator
- Task: quality-validator
- Task: recency-validator

Results → validation_results/
```

### Step 7: Synthesize
```
Sequential:
1. Task: meta-auditor → audit_result.json
2. If GO: Task: anchor-generator → intention_anchors.json
```

### Step 8: Handoff
```
Generate handoff files:
- intention_anchors.json
- PROJECT_BRIEF.md
- READY_FOR_AUTOPACK

Notify user of completion
```

## Output Structure

Projects are created in an ISOLATED directory (not inside Autopack):

```
{AUTOPACK_PROJECTS_ROOT}/{project-name}/
├── .autopack/                          # All Autopack-managed data
│   ├── research/
│   │   ├── discovery/
│   │   │   ├── web_discovery.json
│   │   │   ├── github_discovery.json
│   │   │   └── social_discovery.json
│   │   ├── findings/
│   │   │   ├── market_research.json
│   │   │   ├── competitive_analysis.json
│   │   │   ├── technical_feasibility.json
│   │   │   ├── legal_policy.json
│   │   │   ├── social_sentiment.json
│   │   │   └── tool_availability.json
│   │   ├── frameworks/
│   │   │   ├── market_attractiveness.json
│   │   │   ├── competitive_intensity.json
│   │   │   ├── product_feasibility.json
│   │   │   └── adoption_readiness.json
│   │   └── validation/
│   │       ├── citation_validation.json
│   │       ├── evidence_validation.json
│   │       ├── quality_validation.json
│   │       └── recency_validation.json
│   ├── synthesis/
│   │   ├── audit_result.json
│   │   └── research_synthesis.md
│   ├── builds/                         # Future build history
│   └── runs/                           # Future run artifacts
├── src/                                # Project source (created during build)
├── tests/                              # Project tests (created during build)
├── intention_anchor.yaml               # Project intention anchor
├── tech_stack_proposal.yaml            # Recommended tech stack
├── PROJECT_BRIEF.md                    # Human-readable summary
├── READY_FOR_AUTOPACK                  # Handoff marker
└── .gitignore                          # Project-specific ignores
```

### Why Isolated?

1. **No lint conflicts** - Autopack linters don't scan project files
2. **No CI conflicts** - Projects have independent CI pipelines
3. **Parallel safe** - Multiple projects can build simultaneously
4. **Clean git history** - Tool changes separate from project changes

## Progress Reporting

Throughout execution, report progress:

```
[1/8] Parsing project idea...
[2/8] Running Discovery agents (3 parallel)...
      ✓ Web Discovery complete
      ✓ GitHub Discovery complete
      ✓ Social Discovery complete
[3/8] Running Research agents (6 parallel)...
      ✓ Market Research complete
      ✓ Competitive Analysis complete
      ...
[4/8] Applying Framework scoring...
      Market Attractiveness: 7.5/10
      Competitive Intensity: 6.5/10
      Product Feasibility: 7.2/10
      Adoption Readiness: 7.0/10
      Composite Score: 7.1/10
[5/8] Running Analysis...
[6/8] Running Validation...
[7/8] Synthesizing results...
      Audit Score: 7.8/10
      Recommendation: GO
[8/8] Generating handoff files...
      ✓ intention_anchors.json
      ✓ PROJECT_BRIEF.md
      ✓ READY_FOR_AUTOPACK

✅ Project bootstrap complete!
   Recommendation: GO (High Confidence)
   Next: Review PROJECT_BRIEF.md and run 'autopack init'
```

## Error Handling

### Stage Failures
- If discovery fails: Retry with alternative sources
- If research fails: Continue with available data, flag gaps
- If validation fails: Return to research for fixes
- If audit fails (NO-GO): Report findings, do not generate anchors

### Partial Results
- Save intermediate results after each stage
- Allow resume from last completed stage
- Flag incomplete sections clearly

## Human Checkpoints

### Required Approvals
1. After audit (GO/NO-GO decision)
2. Before Autopack initialization

### Optional Reviews
1. After discovery (validate search scope)
2. After research (validate findings)
3. After framework scoring (validate scores)

## Configuration

### Execution Mode
- `full`: Run complete pipeline (default)
- `discovery-only`: Stop after discovery
- `research-only`: Stop after research
- `no-autopack`: Skip handoff generation

### Parallelism
- `max-parallel`: Maximum concurrent agents (default: 6)
- `sequential`: Run all stages sequentially

### Model Override
- `--haiku`: Use haiku for all agents (faster, cheaper)
- `--opus`: Use opus for all agents (higher quality)

## Supported Project Types

The bootstrap pipeline automatically detects and handles these project categories:

| Project Type | Description | Risk Level | Example Ideas |
|-------------|-------------|------------|---------------|
| **CONTENT** | Video, audio, publishing, social media | LOW | YouTube automation, podcast tools, blog platforms |
| **ECOMMERCE** | Online stores, marketplaces, selling | MEDIUM | Etsy shops, dropshipping, marketplaces |
| **TRADING** | Financial, crypto, investments | HIGH | Trading bots, crypto signals, portfolio tools |
| **AUTOMATION** | Workflows, bots, integrations | MEDIUM | CI/CD tools, task automation, ETL pipelines |
| **OTHER** | Mobile apps, general software | MEDIUM | Fitness apps, utilities, general tools |

### Project Type Detection Examples

```
# YouTube/Video Projects → CONTENT type
/project-bootstrap "YouTube Shorts automation tool with AI video generation"

# Etsy/E-commerce Projects → ECOMMERCE type
/project-bootstrap "Etsy listing automation with AI product descriptions"

# Trading Projects → TRADING type (HIGH risk)
/project-bootstrap "Crypto trading signal bot with technical analysis"

# Dropshipping Projects → ECOMMERCE type
/project-bootstrap "Automated dropshipping store with supplier integration"

# Creative Commerce Projects → CONTENT or ECOMMERCE type
/project-bootstrap "AI art print store with print-on-demand fulfillment"

# Mobile App Projects → OTHER type
/project-bootstrap "Mobile fitness tracking app with wearable integration"
```

## Example Usage

```
# From description (creates project in default location)
/project-bootstrap "AI-powered tool that helps e-commerce sellers automate their Etsy listings"
# → Creates: C:\dev\AutopackProjects\etsy-listing-automation\

# With custom name
/project-bootstrap "Etsy automation" --name etsy-pro
# → Creates: C:\dev\AutopackProjects\etsy-pro\

# With custom output location
/project-bootstrap "My idea" --output D:\projects\my-custom-project
# → Creates: D:\projects\my-custom-project\

# From file
/project-bootstrap C:\ideas\my_idea.md

# With options
/project-bootstrap --discovery-only "My idea"
/project-bootstrap --sequential --opus "My idea"
```

## Integration with Autopack

After successful bootstrap:

```bash
# Navigate to project directory
cd C:\dev\AutopackProjects\{project-name}

# Review generated files
cat PROJECT_BRIEF.md
cat intention_anchor.yaml
cat tech_stack_proposal.yaml

# Initialize Autopack build
autopack init --project .

# Or from Autopack directory, specify project path
cd C:\dev\Autopack
autopack init --project C:\dev\AutopackProjects\{project-name}

# Autopack auto-detects READY_FOR_AUTOPACK marker
autopack scan --projects-root C:\dev\AutopackProjects
# → Lists all projects ready for build
```

### Environment Setup

```bash
# Set projects root (add to system environment)
set AUTOPACK_PROJECTS_ROOT=C:\dev\AutopackProjects

# Or in .env file
echo AUTOPACK_PROJECTS_ROOT=C:\dev\AutopackProjects >> .env
```

## Constraints

- Use sonnet as default orchestration model
- Respect rate limits across all agents
- Save progress after each stage
- Total execution: 15-30 minutes typical
- Require human approval for NO-GO decisions
