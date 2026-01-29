# Implementation Plan: Claude Code Agents Research Bridge (Hybrid Mode)

**Audience**: Implementation cursor / Claude Code operators
**Status**: Plan only (create agents after approval)
**Purpose**: Bridge the 30% gap (research + anchor generation) while Autopack's native pipeline is being built

---

## Executive Summary

This plan establishes a Claude Code agent hierarchy that **mirrors Autopack's research infrastructure** in depth and comprehensiveness. The architecture uses **agents with sub-agents** to enable extensive research coverage while managing context limitations.

**Key Principle**: Sub-agents handle narrow, focused tasks → Agents aggregate → Main Claude synthesizes

---

## Design Philosophy

### From Autopack's Architecture

Autopack's research infrastructure follows this pattern:
```
Intent Clarification → Source Discovery → Data Gathering → Analysis →
Compilation → Framework Evaluation → Meta-Audit → Validation → Report
```

### Mapped to Claude Code

```
Main Claude (Orchestrator)
    │
    ├── DISCOVERY LAYER (Agents)
    │   └── Sub-agents per source type
    │
    ├── GATHERING LAYER (Agents)
    │   └── Sub-agents per extraction method
    │
    ├── ANALYSIS LAYER (Agents)
    │   └── Sub-agents per framework
    │
    ├── VALIDATION LAYER (Agents)
    │   └── Sub-agents per validation type
    │
    └── SYNTHESIS LAYER (Agent)
        └── Anchor generation
```

### Why Sub-Agents?

From the YouTube Script reference (Cursor Mafia approach):
- **Context preservation**: Main Claude maintains orchestration context
- **Parallel execution**: Independent sub-agents run simultaneously
- **Reduced pollution**: Heavy extraction happens outside main context
- **Quality control**: Each sub-agent has focused, verifiable output

---

## Complete Agent Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MAIN CLAUDE (ORCHESTRATOR)                          │
│                                                                              │
│  Responsibilities:                                                           │
│  - Parse project ideas document                                              │
│  - Coordinate all agents                                                     │
│  - Synthesize final outputs                                                  │
│  - Handle user Q&A                                                           │
│  - Write final artifacts                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 1: DISCOVERY AGENTS                        │    │
│  │                                                                     │    │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐           │    │
│  │  │ Web Discovery │  │ GitHub        │  │ Social        │           │    │
│  │  │ Agent         │  │ Discovery     │  │ Discovery     │           │    │
│  │  │               │  │ Agent         │  │ Agent         │           │    │
│  │  │ Sub-agents:   │  │               │  │               │           │    │
│  │  │ • Google      │  │ Sub-agents:   │  │ Sub-agents:   │           │    │
│  │  │   Search      │  │ • Repo Search │  │ • Reddit      │           │    │
│  │  │ • Site        │  │ • Issue       │  │   Discovery   │           │    │
│  │  │   Scraper     │  │   Search      │  │ • Twitter/X   │           │    │
│  │  │ • News        │  │ • Code Search │  │   Discovery   │           │    │
│  │  │   Aggregator  │  │ • Star/Fork   │  │ • HN/Forum    │           │    │
│  │  │               │  │   Analysis    │  │   Discovery   │           │    │
│  │  └───────────────┘  └───────────────┘  └───────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 2: RESEARCH AGENTS                         │    │
│  │                                                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │    │
│  │  │ Market       │ │ Competitive  │ │ Technical    │ │ Legal/     │ │    │
│  │  │ Research     │ │ Analysis     │ │ Feasibility  │ │ Policy     │ │    │
│  │  │ Agent        │ │ Agent        │ │ Agent        │ │ Agent      │ │    │
│  │  │              │ │              │ │              │ │            │ │    │
│  │  │ Sub-agents:  │ │ Sub-agents:  │ │ Sub-agents:  │ │ Sub-agents:│ │    │
│  │  │ • Market     │ │ • Competitor │ │ • API        │ │ • ToS      │ │    │
│  │  │   Size       │ │   Profiler   │ │   Research   │ │   Analyzer │ │    │
│  │  │ • Trend      │ │ • Feature    │ │ • Stack      │ │ • Regula-  │ │    │
│  │  │   Analyzer   │ │   Matrix     │ │   Evaluator  │ │   tory     │ │    │
│  │  │ • Demand     │ │ • Pricing    │ │ • Dependency │ │ • Privacy  │ │    │
│  │  │   Signals    │ │   Analyst    │ │   Checker    │ │   (GDPR)   │ │    │
│  │  │ • Monetiza-  │ │ • Differenti-│ │ • Complexity │ │ • Content  │ │    │
│  │  │   tion       │ │   ation      │ │   Estimator  │ │   Policy   │ │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │    │
│  │                                                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐                                 │    │
│  │  │ Social       │ │ Tool/MCP     │                                 │    │
│  │  │ Sentiment    │ │ Availability │                                 │    │
│  │  │ Agent        │ │ Agent        │                                 │    │
│  │  │              │ │              │                                 │    │
│  │  │ Sub-agents:  │ │ Sub-agents:  │                                 │    │
│  │  │ • Pain Point │ │ • MCP        │                                 │    │
│  │  │   Extractor  │ │   Registry   │                                 │    │
│  │  │ • Feature    │ │ • NPM/PyPI   │                                 │    │
│  │  │   Request    │ │   Scanner    │                                 │    │
│  │  │   Collector  │ │ • Build vs   │                                 │    │
│  │  │ • Influencer │ │   Buy        │                                 │    │
│  │  │   Mapper     │ │   Analyzer   │                                 │    │
│  │  └──────────────┘ └──────────────┘                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 3: FRAMEWORK AGENTS                        │    │
│  │   (Mirror Autopack's frameworks/)                                   │    │
│  │                                                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │    │
│  │  │ Market       │ │ Competitive  │ │ Product      │ │ Adoption   │ │    │
│  │  │ Attractive-  │ │ Intensity    │ │ Feasibility  │ │ Readiness  │ │    │
│  │  │ ness Agent   │ │ Agent        │ │ Agent        │ │ Agent      │ │    │
│  │  │              │ │              │ │              │ │            │ │    │
│  │  │ Evaluates:   │ │ Evaluates:   │ │ Evaluates:   │ │ Evaluates: │ │    │
│  │  │ • TAM/SAM    │ │ • # Rivals   │ │ • Tech Stack │ │ • Market   │ │    │
│  │  │ • Growth     │ │ • Barrier    │ │ • Resource   │ │   Timing   │ │    │
│  │  │ • Entry      │ │ • Switching  │ │ • Timeline   │ │ • User     │ │    │
│  │  │   Barrier    │ │   Cost       │ │ • Risk       │ │   Readines │ │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 4: ANALYSIS AGENTS                         │    │
│  │   (Mirror Autopack's agents/)                                       │    │
│  │                                                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │    │
│  │  │ Source       │ │ Analysis     │ │ Compilation  │                │    │
│  │  │ Evaluator    │ │ Agent        │ │ Agent        │                │    │
│  │  │ Agent        │ │              │ │              │                │    │
│  │  │              │ │ Tasks:       │ │ Tasks:       │                │    │
│  │  │ Tasks:       │ │ • Aggregate  │ │ • Deduplicate│                │    │
│  │  │ • Rank       │ │   findings   │ │   findings   │                │    │
│  │  │   sources    │ │ • Identify   │ │ • Categorize │                │    │
│  │  │ • Trust tier │ │   gaps       │ │   by type    │                │    │
│  │  │   assignment │ │ • Cross-ref  │ │ • Preserve   │                │    │
│  │  │ • Credibility│ │   conflicts  │ │   citations  │                │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 5: VALIDATION AGENTS                       │    │
│  │   (Mirror Autopack's validators/)                                   │    │
│  │                                                                     │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │    │
│  │  │ Citation     │ │ Evidence     │ │ Quality      │ │ Recency    │ │    │
│  │  │ Validator    │ │ Validator    │ │ Validator    │ │ Validator  │ │    │
│  │  │ Agent        │ │ Agent        │ │ Agent        │ │ Agent      │ │    │
│  │  │              │ │              │ │              │ │            │ │    │
│  │  │ Checks:      │ │ Checks:      │ │ Checks:      │ │ Checks:    │ │    │
│  │  │ • Exact      │ │ • Source     │ │ • Logical    │ │ • Within   │ │    │
│  │  │   quote      │ │   authentic  │ │   consistency│ │   2 years  │ │    │
│  │  │   matching   │ │ • Evidence   │ │ • Clear      │ │ • Not      │ │    │
│  │  │ • Source     │ │   type valid │ │   conclusions│ │   outdated │ │    │
│  │  │   hash       │ │ • Relevance  │ │ • Method     │ │ • Current  │ │    │
│  │  │   verify     │ │   > 0.5      │ │   adherence  │ │   state    │ │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    LAYER 6: SYNTHESIS AGENTS                        │    │
│  │                                                                     │    │
│  │  ┌──────────────────────┐  ┌──────────────────────┐                │    │
│  │  │ Meta Auditor Agent   │  │ Anchor Generator     │                │    │
│  │  │                      │  │ Agent                │                │    │
│  │  │ Tasks:               │  │                      │                │    │
│  │  │ • Synthesize all     │  │ Tasks:               │                │    │
│  │  │   framework scores   │  │ • Map findings to    │                │    │
│  │  │ • Strategic          │  │   8 pivot intentions │                │    │
│  │  │   recommendations    │  │ • Generate tech      │                │    │
│  │  │ • Risk aggregation   │  │   stack proposal     │                │    │
│  │  │ • Opportunity        │  │ • Create clarifying  │                │    │
│  │  │   prioritization     │  │   questions          │                │    │
│  │  └──────────────────────┘  └──────────────────────┘                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT FILES                                    │
│                                                                              │
│  projects/<project-name>/                                                    │
│  ├── research/                                                               │
│  │   ├── discovery/                                                          │
│  │   │   ├── web_sources.json                                                │
│  │   │   ├── github_sources.json                                             │
│  │   │   └── social_sources.json                                             │
│  │   ├── findings/                                                           │
│  │   │   ├── market_findings.json                                            │
│  │   │   ├── competitive_findings.json                                       │
│  │   │   ├── technical_findings.json                                         │
│  │   │   ├── legal_findings.json                                             │
│  │   │   ├── sentiment_findings.json                                         │
│  │   │   └── tool_findings.json                                              │
│  │   ├── frameworks/                                                         │
│  │   │   ├── market_attractiveness_score.json                                │
│  │   │   ├── competitive_intensity_score.json                                │
│  │   │   ├── product_feasibility_score.json                                  │
│  │   │   └── adoption_readiness_score.json                                   │
│  │   ├── validation/                                                         │
│  │   │   └── validation_report.json                                          │
│  │   └── reports/                                                            │
│  │       ├── market_analysis.md                                              │
│  │       ├── competitive_analysis.md                                         │
│  │       ├── technical_feasibility.md                                        │
│  │       ├── legal_compliance.md                                             │
│  │       ├── social_sentiment.md                                             │
│  │       └── mcp_availability.md                                             │
│  ├── research_synthesis.md                                                   │
│  ├── tech_stack_proposal.yaml                                                │
│  ├── intention_anchor.yaml                                                   │
│  ├── clarifying_questions.md (if needed)                                     │
│  └── READY_FOR_AUTOPACK                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (Script detects READY_FOR_AUTOPACK)
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AUTOPACK                                        │
│                                                                              │
│  1. Load intention_anchor.yaml                                               │
│  2. Run Gap Scanner                                                          │
│  3. Run Plan Proposer                                                        │
│  4. Execute with governance                                                  │
│  5. Tidy → SOT                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
.claude/
├── agents/
│   │
│   │  # LAYER 1: DISCOVERY AGENTS
│   ├── discovery/
│   │   ├── web-discovery-agent.md
│   │   ├── github-discovery-agent.md
│   │   └── social-discovery-agent.md
│   │
│   │  # LAYER 1: DISCOVERY SUB-AGENTS
│   ├── discovery-sub/
│   │   ├── google-search.md
│   │   ├── site-scraper.md
│   │   ├── news-aggregator.md
│   │   ├── github-repo-search.md
│   │   ├── github-issue-search.md
│   │   ├── github-code-search.md
│   │   ├── github-star-analyzer.md
│   │   ├── reddit-discovery.md
│   │   ├── twitter-discovery.md
│   │   └── forum-discovery.md
│   │
│   │  # LAYER 2: RESEARCH AGENTS
│   ├── research/
│   │   ├── market-research-agent.md
│   │   ├── competitive-analysis-agent.md
│   │   ├── technical-feasibility-agent.md
│   │   ├── legal-policy-agent.md
│   │   ├── social-sentiment-agent.md
│   │   └── tool-availability-agent.md
│   │
│   │  # LAYER 2: RESEARCH SUB-AGENTS
│   ├── research-sub/
│   │   │  # Market Research Sub-Agents
│   │   ├── market-size-estimator.md
│   │   ├── trend-analyzer.md
│   │   ├── demand-signals-detector.md
│   │   ├── monetization-analyzer.md
│   │   │  # Competitive Sub-Agents
│   │   ├── competitor-profiler.md
│   │   ├── feature-matrix-builder.md
│   │   ├── pricing-analyst.md
│   │   ├── differentiation-finder.md
│   │   │  # Technical Sub-Agents
│   │   ├── api-researcher.md
│   │   ├── stack-evaluator.md
│   │   ├── dependency-checker.md
│   │   ├── complexity-estimator.md
│   │   │  # Legal Sub-Agents
│   │   ├── tos-analyzer.md
│   │   ├── regulatory-checker.md
│   │   ├── privacy-compliance.md
│   │   ├── content-policy-checker.md
│   │   │  # Sentiment Sub-Agents
│   │   ├── pain-point-extractor.md
│   │   ├── feature-request-collector.md
│   │   ├── influencer-mapper.md
│   │   │  # Tool Sub-Agents
│   │   ├── mcp-registry-scanner.md
│   │   ├── npm-pypi-scanner.md
│   │   └── build-vs-buy-analyzer.md
│   │
│   │  # LAYER 3: FRAMEWORK AGENTS
│   ├── frameworks/
│   │   ├── market-attractiveness-agent.md
│   │   ├── competitive-intensity-agent.md
│   │   ├── product-feasibility-agent.md
│   │   └── adoption-readiness-agent.md
│   │
│   │  # LAYER 4: ANALYSIS AGENTS
│   ├── analysis/
│   │   ├── source-evaluator-agent.md
│   │   ├── analysis-agent.md
│   │   └── compilation-agent.md
│   │
│   │  # LAYER 5: VALIDATION AGENTS
│   ├── validation/
│   │   ├── citation-validator-agent.md
│   │   ├── evidence-validator-agent.md
│   │   ├── quality-validator-agent.md
│   │   └── recency-validator-agent.md
│   │
│   │  # LAYER 6: SYNTHESIS AGENTS
│   └── synthesis/
│       ├── meta-auditor-agent.md
│       └── anchor-generator-agent.md
│
├── skills/
│   └── project-bootstrap/
│       └── SKILL.md
│
└── scripts/
    ├── create-project-structure.ts
    ├── validate-research-output.ts
    └── trigger-autopack.ts
```

---

## Agent Specifications

### LAYER 1: DISCOVERY AGENTS

#### Web Discovery Agent

**File**: `.claude/agents/discovery/web-discovery-agent.md`

```markdown
---
name: web-discovery-agent
description: Orchestrate web source discovery across multiple channels
tools: [WebSearch, WebFetch, Read, Write, Task]
model: sonnet
---

# Web Discovery Agent

You orchestrate web source discovery for: {{project_idea}}

## Your Sub-Agents

You MUST delegate to these sub-agents IN PARALLEL:

1. **@google-search** - General web search
2. **@site-scraper** - Deep scraping of identified sites
3. **@news-aggregator** - News and press coverage

## Workflow

1. Define search queries based on project idea
2. Launch all 3 sub-agents in PARALLEL with specific queries
3. Wait for all results
4. Aggregate source lists
5. Remove duplicates
6. Write to: `{{output_path}}/discovery/web_sources.json`

## Output Schema

```json
{
  "sources": [
    {
      "url": "https://...",
      "title": "...",
      "source_type": "article|blog|news|documentation",
      "discovery_method": "google_search|site_scrape|news",
      "discovered_at": "ISO timestamp",
      "relevance_keywords": ["keyword1", "keyword2"]
    }
  ],
  "total_sources": 42,
  "discovery_stats": {
    "google_search": 20,
    "site_scrape": 15,
    "news": 7
  }
}
```

## Constraints

- Maximum 50 sources per discovery session
- Deduplicate by URL
- Exclude known low-quality domains
```

#### Google Search Sub-Agent

**File**: `.claude/agents/discovery-sub/google-search.md`

```markdown
---
name: google-search
description: Perform targeted Google searches and extract source URLs
tools: [WebSearch]
model: haiku
---

# Google Search Sub-Agent

Execute Google searches for: {{search_queries}}

## Search Strategy

For each query:
1. Execute search
2. Extract URLs from results
3. Note title and snippet
4. Classify source type

## Output Format

Return JSON array:
```json
[
  {
    "url": "https://...",
    "title": "...",
    "snippet": "...",
    "source_type": "article|blog|news|documentation|forum"
  }
]
```

## Constraints

- Use haiku (cost-efficient for simple extraction)
- Maximum 10 results per query
- Maximum 5 queries per session
```

#### Site Scraper Sub-Agent

**File**: `.claude/agents/discovery-sub/site-scraper.md`

```markdown
---
name: site-scraper
description: Deep scrape specific sites for relevant pages
tools: [WebFetch, Read, Write]
model: haiku
---

# Site Scraper Sub-Agent

Scrape target sites for pages related to: {{topic}}

## Target Sites

{{target_sites}}  # Provided by parent agent

## Scraping Process

1. Fetch sitemap.xml if available
2. Otherwise, crawl from homepage
3. Identify relevant pages by URL pattern and content
4. Extract page metadata

## Output Format

```json
[
  {
    "url": "https://...",
    "title": "...",
    "page_type": "pricing|features|docs|blog|about",
    "extracted_links": ["..."]
  }
]
```

## Constraints

- Respect robots.txt
- Maximum 20 pages per site
- 1 second delay between requests
```

---

### LAYER 2: RESEARCH AGENTS

#### Market Research Agent

**File**: `.claude/agents/research/market-research-agent.md`

```markdown
---
name: market-research-agent
description: Comprehensive market research with deep analysis
tools: [WebSearch, WebFetch, Read, Write, Task]
model: sonnet
---

# Market Research Agent

Conduct comprehensive market research for: {{project_idea}}

## Your Sub-Agents

Launch these sub-agents for deep research:

1. **@market-size-estimator** - TAM/SAM/SOM estimation
2. **@trend-analyzer** - Market trend analysis
3. **@demand-signals-detector** - User demand signals
4. **@monetization-analyzer** - Revenue model analysis

## Workflow

### Phase 1: Discovery Input
Read sources from: `{{project_path}}/research/discovery/web_sources.json`

### Phase 2: Parallel Deep Research
Launch all 4 sub-agents IN PARALLEL with:
- Relevant sources subset
- Specific research questions

### Phase 3: Aggregate Findings
Compile all sub-agent outputs into unified report

### Phase 4: Write Output
Write to: `{{project_path}}/research/findings/market_findings.json`
Write report: `{{project_path}}/research/reports/market_analysis.md`

## Finding Schema (per Autopack standard)

Each finding MUST include:
```json
{
  "content": "LLM interpretation of finding",
  "extraction_span": "EXACT quote from source (20+ chars)",
  "category": "market_intelligence",
  "source_url": "https://...",
  "source_hash": "SHA256 of source content",
  "confidence": 0.85
}
```

## Report Structure

```markdown
# Market Analysis: {{project_title}}

## Executive Summary
[2-3 sentences]

## Market Size
- TAM: [estimate with source]
- SAM: [estimate with source]
- SOM: [realistic target]

## Demand Signals
[From demand-signals-detector]

## Growth Trajectory
[From trend-analyzer]

## Monetization Models
[From monetization-analyzer]

## Sources
[All cited sources with URLs]
```
```

#### Market Size Estimator Sub-Agent

**File**: `.claude/agents/research-sub/market-size-estimator.md`

```markdown
---
name: market-size-estimator
description: Estimate TAM, SAM, SOM with cited sources
tools: [WebSearch, WebFetch, Read, Write]
model: sonnet
---

# Market Size Estimator Sub-Agent

Estimate market size for: {{market_segment}}

## Research Process

1. Search for industry reports mentioning market size
2. Look for publicly reported revenue of major players
3. Find analyst estimates and projections
4. Calculate bottom-up estimates where possible

## Output Format

```json
{
  "tam": {
    "value": "$X billion",
    "source": "...",
    "extraction_span": "exact quote from source",
    "year": "2024",
    "confidence": 0.8
  },
  "sam": {
    "value": "$X million",
    "source": "...",
    "extraction_span": "exact quote",
    "methodology": "geographic/segment filtering",
    "confidence": 0.7
  },
  "som": {
    "value": "$X million",
    "source": "internal estimate",
    "methodology": "X% of SAM based on...",
    "assumptions": ["assumption 1", "assumption 2"],
    "confidence": 0.5
  },
  "growth_rate": {
    "value": "X% CAGR",
    "source": "...",
    "extraction_span": "exact quote",
    "period": "2024-2029"
  }
}
```

## Critical Requirement

extraction_span MUST be CHARACTER-FOR-CHARACTER exact quote from source (minimum 20 characters).
This is verified by Citation Validator.

## Constraints

- Never fabricate statistics
- If data unavailable, state "Not found" with confidence 0
- Prefer official reports over blog estimates
```

#### Trend Analyzer Sub-Agent

**File**: `.claude/agents/research-sub/trend-analyzer.md`

```markdown
---
name: trend-analyzer
description: Analyze market trends and trajectory
tools: [WebSearch, WebFetch, Read, Write]
model: haiku
---

# Trend Analyzer Sub-Agent

Analyze trends for: {{market_segment}}

## Data Sources

1. Google Trends (via search for "Google Trends [keyword]")
2. Industry analyst reports
3. News articles about market direction
4. Social media sentiment trends

## Output Format

```json
{
  "trends": [
    {
      "trend": "Trend description",
      "direction": "growing|stable|declining",
      "evidence": "extraction_span quote",
      "source": "URL",
      "timeframe": "2024-present"
    }
  ],
  "overall_trajectory": "growing|stable|declining",
  "trajectory_confidence": 0.75
}
```

## Constraints

- Use haiku for cost efficiency
- Focus on last 2 years
- Minimum 3 trend signals before conclusion
```

#### Demand Signals Detector Sub-Agent

**File**: `.claude/agents/research-sub/demand-signals-detector.md`

```markdown
---
name: demand-signals-detector
description: Detect user demand signals from forums, reviews, and discussions
tools: [WebSearch, WebFetch, Read, Write]
model: haiku
---

# Demand Signals Detector Sub-Agent

Find demand signals for: {{product_type}}

## Search Targets

1. Reddit discussions ("looking for [product_type]", "need help with")
2. Forum posts requesting solutions
3. Product Hunt launch comments
4. Twitter/X complaints about existing solutions
5. App store reviews of competitors

## Output Format

```json
{
  "signals": [
    {
      "signal_type": "explicit_request|complaint|workaround|wishlist",
      "content": "Summary of signal",
      "extraction_span": "Exact user quote",
      "source": "URL",
      "upvotes_or_engagement": 42,
      "date": "2024-01-15"
    }
  ],
  "signal_strength": "strong|moderate|weak",
  "total_signals": 15
}
```

## Constraints

- Focus on signals with engagement (upvotes, replies)
- Prefer recent signals (last 12 months)
- Minimum 10 signals before assessment
```

#### Monetization Analyzer Sub-Agent

**File**: `.claude/agents/research-sub/monetization-analyzer.md`

```markdown
---
name: monetization-analyzer
description: Analyze monetization models in the market
tools: [WebSearch, WebFetch, Read, Write]
model: haiku
---

# Monetization Analyzer Sub-Agent

Analyze monetization for: {{product_category}}

## Research Targets

1. Competitor pricing pages
2. SaaS pricing benchmarks
3. Freemium conversion rates
4. Revenue reports (if public)

## Output Format

```json
{
  "models": [
    {
      "model": "subscription|freemium|one-time|usage-based",
      "examples": ["Company A", "Company B"],
      "price_range": "$X-Y/month",
      "typical_conversion": "X%",
      "evidence": "extraction_span",
      "source": "URL"
    }
  ],
  "recommended_model": "...",
  "recommendation_rationale": "...",
  "revenue_potential": {
    "conservative": "$X/month",
    "moderate": "$Y/month",
    "aggressive": "$Z/month",
    "assumptions": ["..."]
  }
}
```
```

---

### Competitive Analysis Agent

**File**: `.claude/agents/research/competitive-analysis-agent.md`

```markdown
---
name: competitive-analysis-agent
description: Comprehensive competitive landscape analysis
tools: [WebSearch, WebFetch, Read, Write, Task]
model: sonnet
---

# Competitive Analysis Agent

Analyze competitive landscape for: {{project_idea}}

## Your Sub-Agents

1. **@competitor-profiler** - Deep dive on each competitor
2. **@feature-matrix-builder** - Build feature comparison matrix
3. **@pricing-analyst** - Analyze pricing strategies
4. **@differentiation-finder** - Identify differentiation opportunities

## Workflow

### Phase 1: Identify Competitors
Use discovery sources + search to identify top 5-7 direct competitors

### Phase 2: Profile Each Competitor
Launch @competitor-profiler for EACH competitor IN PARALLEL

### Phase 3: Build Feature Matrix
Launch @feature-matrix-builder with all competitor profiles

### Phase 4: Analyze Pricing
Launch @pricing-analyst with competitor data

### Phase 5: Find Differentiation
Launch @differentiation-finder with full analysis

### Phase 6: Synthesize
Write to: `{{project_path}}/research/findings/competitive_findings.json`
Write report: `{{project_path}}/research/reports/competitive_analysis.md`

## Report Structure

```markdown
# Competitive Analysis: {{project_title}}

## Executive Summary

## Direct Competitors (Top 5)
### Competitor 1: [Name]
- URL: ...
- Pricing: ...
- Key Features: ...
- Strengths: ...
- Weaknesses: ...

## Feature Matrix
| Feature | Us | Comp1 | Comp2 | Comp3 |
|---------|-----|-------|-------|-------|

## Pricing Landscape

## Differentiation Opportunities
1. [Opportunity] - [Why underserved]

## Competitive Moats to Build
```
```

#### Competitor Profiler Sub-Agent

**File**: `.claude/agents/research-sub/competitor-profiler.md`

```markdown
---
name: competitor-profiler
description: Create detailed profile of a single competitor
tools: [WebFetch, Read, Write]
model: sonnet
---

# Competitor Profiler Sub-Agent

Profile competitor: {{competitor_url}}

## Data to Extract

1. **Basic Info**
   - Company name
   - Founded date
   - Team size (if findable)
   - Funding (if findable)

2. **Product**
   - Core features
   - Target audience
   - Unique selling proposition

3. **Pricing**
   - Pricing model
   - Price points
   - Free tier details

4. **Traction**
   - User count (if public)
   - Reviews/ratings
   - Social proof

5. **Weaknesses**
   - User complaints
   - Missing features
   - UX issues

## Output Format

```json
{
  "name": "Company Name",
  "url": "https://...",
  "basic_info": {
    "founded": "2020",
    "team_size": "11-50",
    "funding": "$5M Series A",
    "source": "URL"
  },
  "product": {
    "features": ["feature1", "feature2"],
    "target_audience": "...",
    "usp": "..."
  },
  "pricing": {
    "model": "subscription",
    "tiers": [
      {"name": "Free", "price": "$0", "limits": "..."},
      {"name": "Pro", "price": "$29/mo", "features": "..."}
    ]
  },
  "traction": {
    "users": "10,000+",
    "reviews": {"g2": 4.5, "capterra": 4.3},
    "source": "URL"
  },
  "weaknesses": [
    {
      "weakness": "Slow customer support",
      "evidence": "extraction_span quote from review",
      "source": "URL"
    }
  ]
}
```
```

---

### Technical Feasibility Agent

**File**: `.claude/agents/research/technical-feasibility-agent.md`

```markdown
---
name: technical-feasibility-agent
description: Assess technical feasibility with deep API and stack analysis
tools: [WebSearch, WebFetch, Read, Write, Bash, Task]
model: sonnet
---

# Technical Feasibility Agent

Assess technical feasibility for: {{project_idea}}

## Your Sub-Agents

1. **@api-researcher** - Research required APIs
2. **@stack-evaluator** - Evaluate technology stack options
3. **@dependency-checker** - Check library availability
4. **@complexity-estimator** - Estimate implementation complexity

## Workflow

### Phase 1: Identify Technical Requirements
Break down project into technical components

### Phase 2: API Research
Launch @api-researcher for each required API IN PARALLEL

### Phase 3: Stack Evaluation
Launch @stack-evaluator with API findings

### Phase 4: Dependency Check
Launch @dependency-checker with stack options

### Phase 5: Complexity Estimation
Launch @complexity-estimator with full technical picture

### Phase 6: Synthesize
Write to: `{{project_path}}/research/findings/technical_findings.json`
Write report: `{{project_path}}/research/reports/technical_feasibility.md`

## Report Structure

```markdown
# Technical Feasibility: {{project_title}}

## Feasibility Assessment: [Highly Feasible / Feasible / Challenging / Not Recommended]

## Core Technical Requirements
| Requirement | Complexity | Notes |

## API Dependencies
### API 1: [Name]
- Purpose: ...
- Rate Limits: ...
- Pricing: ...
- ToS Concerns: ...

## Technology Stack Options
### Option A: [Stack]
**Pros**: ...
**Cons**: ...
**Cost**: ...

## Implementation Complexity
| Component | Complexity | Effort |

## Technical Risks
| Risk | Likelihood | Impact | Mitigation |
```
```

#### API Researcher Sub-Agent

**File**: `.claude/agents/research-sub/api-researcher.md`

```markdown
---
name: api-researcher
description: Research a specific API's capabilities, limits, and pricing
tools: [WebSearch, WebFetch, Read, Write]
model: sonnet
---

# API Researcher Sub-Agent

Research API: {{api_name}}

## Research Targets

1. Official documentation
2. Rate limit documentation
3. Pricing page
4. Terms of Service
5. Developer forums for gotchas
6. GitHub issues for known problems

## Output Format

```json
{
  "api_name": "...",
  "provider": "...",
  "documentation_url": "...",
  "capabilities": ["cap1", "cap2"],
  "rate_limits": {
    "requests_per_minute": 60,
    "requests_per_day": 10000,
    "source": "URL",
    "extraction_span": "exact quote"
  },
  "pricing": {
    "free_tier": {
      "limits": "...",
      "duration": "..."
    },
    "paid_tiers": [
      {"name": "...", "price": "...", "limits": "..."}
    ],
    "source": "URL"
  },
  "tos_concerns": [
    {
      "concern": "...",
      "extraction_span": "exact quote from ToS",
      "source": "URL"
    }
  ],
  "known_issues": [
    {
      "issue": "...",
      "source": "URL"
    }
  ],
  "alternatives": ["API2", "API3"],
  "overall_viability": "high|medium|low",
  "viability_rationale": "..."
}
```

## Critical Requirements

- Always check official documentation first
- Rate limits must come from official source
- ToS extraction_span must be exact quotes
```

---

### Legal/Policy Agent

**File**: `.claude/agents/research/legal-policy-agent.md`

```markdown
---
name: legal-policy-agent
description: Comprehensive legal and policy compliance research
tools: [WebSearch, WebFetch, Read, Write, Task]
model: sonnet
---

# Legal/Policy Agent

Research legal/policy landscape for: {{project_idea}}

## Your Sub-Agents

1. **@tos-analyzer** - Analyze Terms of Service
2. **@regulatory-checker** - Check regulatory requirements
3. **@privacy-compliance** - GDPR/CCPA analysis
4. **@content-policy-checker** - AI/content policy analysis

## CRITICAL OUTPUT

Generate NEVER-ALLOW list for IntentionAnchorV2:
```yaml
safety_risk:
  never_allow:
    - operation: "Violate Etsy ToS section 4.3"
      rationale: "Account termination risk"
      source: "https://etsy.com/legal/terms"
```

## Report Structure

```markdown
# Legal/Policy Compliance: {{project_title}}

## Risk Level: [Low / Medium / High / Critical]

## Platform Terms of Service
### Platform 1
- Allowed: ...
- Prohibited: ...
- Gray Areas: ...

## NEVER-ALLOW List (Critical)
1. [Action] - [Why prohibited] - [Source]

## REQUIRES-APPROVAL List
1. [Action] - [Why approval needed]

## Regulatory Requirements

## Data Privacy Requirements
```
```

---

### LAYER 3: FRAMEWORK AGENTS

#### Market Attractiveness Agent

**File**: `.claude/agents/frameworks/market-attractiveness-agent.md`

```markdown
---
name: market-attractiveness-agent
description: Evaluate market opportunity attractiveness (mirrors Autopack's MarketAttractiveness framework)
tools: [Read, Write]
model: haiku
---

# Market Attractiveness Agent

Evaluate market attractiveness based on research findings.

## Input

Read: `{{project_path}}/research/findings/market_findings.json`

## Evaluation Factors (from Autopack)

Score each factor 0-10:

1. **Market Size** - TAM/SAM indicates large opportunity
2. **Growth Rate** - CAGR > 10% = high growth
3. **Demand Signals** - Strong user demand evidence
4. **Monetization Clarity** - Clear revenue path
5. **Entry Barriers** - Low barriers = easier entry (but less defensible)

## Output Format

```json
{
  "framework": "market_attractiveness",
  "scores": {
    "market_size": {"score": 8, "rationale": "..."},
    "growth_rate": {"score": 7, "rationale": "..."},
    "demand_signals": {"score": 9, "rationale": "..."},
    "monetization_clarity": {"score": 6, "rationale": "..."},
    "entry_barriers": {"score": 5, "rationale": "..."}
  },
  "total_score": 35,
  "max_score": 50,
  "attractiveness": 0.70,
  "assessment": "High attractiveness - strong demand and growth outweigh entry concerns"
}
```

Write to: `{{project_path}}/research/frameworks/market_attractiveness_score.json`
```

#### Competitive Intensity Agent

**File**: `.claude/agents/frameworks/competitive-intensity-agent.md`

```markdown
---
name: competitive-intensity-agent
description: Evaluate competitive intensity (mirrors Autopack's CompetitiveIntensity framework)
tools: [Read, Write]
model: haiku
---

# Competitive Intensity Agent

Evaluate competitive intensity based on research findings.

## Input

Read: `{{project_path}}/research/findings/competitive_findings.json`

## Evaluation Factors

Score each factor 0-10 (higher = MORE intense competition):

1. **Number of Competitors** - More = higher intensity
2. **Competitor Strength** - Well-funded competitors = higher intensity
3. **Switching Costs** - Low switching = higher intensity
4. **Product Differentiation** - Low differentiation = higher intensity
5. **Price Competition** - Race to bottom = higher intensity

## Output Format

```json
{
  "framework": "competitive_intensity",
  "scores": {
    "number_of_competitors": {"score": 6, "rationale": "..."},
    "competitor_strength": {"score": 7, "rationale": "..."},
    "switching_costs": {"score": 4, "rationale": "..."},
    "product_differentiation": {"score": 5, "rationale": "..."},
    "price_competition": {"score": 3, "rationale": "..."}
  },
  "total_score": 25,
  "max_score": 50,
  "intensity": 0.50,
  "assessment": "Moderate competition - differentiation opportunity exists"
}
```

Write to: `{{project_path}}/research/frameworks/competitive_intensity_score.json`
```

#### Product Feasibility Agent

**File**: `.claude/agents/frameworks/product-feasibility-agent.md`

```markdown
---
name: product-feasibility-agent
description: Evaluate product feasibility (mirrors Autopack's ProductFeasibility framework)
tools: [Read, Write]
model: haiku
---

# Product Feasibility Agent

Evaluate product feasibility based on technical findings.

## Input

Read: `{{project_path}}/research/findings/technical_findings.json`

## Evaluation Factors

Score each factor 0-10:

1. **Technical Complexity** - Lower = more feasible (inverted)
2. **API Availability** - Required APIs exist and accessible
3. **Library Ecosystem** - Good libraries available
4. **Resource Requirements** - Reasonable compute/storage needs
5. **Timeline Realism** - Can be built in reasonable time

## Output Format

```json
{
  "framework": "product_feasibility",
  "scores": {
    "technical_complexity": {"score": 6, "rationale": "..."},
    "api_availability": {"score": 8, "rationale": "..."},
    "library_ecosystem": {"score": 7, "rationale": "..."},
    "resource_requirements": {"score": 8, "rationale": "..."},
    "timeline_realism": {"score": 5, "rationale": "..."}
  },
  "total_score": 34,
  "max_score": 50,
  "feasibility": 0.68,
  "assessment": "Feasible with moderate effort - API availability is strength"
}
```

Write to: `{{project_path}}/research/frameworks/product_feasibility_score.json`
```

#### Adoption Readiness Agent

**File**: `.claude/agents/frameworks/adoption-readiness-agent.md`

```markdown
---
name: adoption-readiness-agent
description: Evaluate market adoption readiness (mirrors Autopack's AdoptionReadiness framework)
tools: [Read, Write]
model: haiku
---

# Adoption Readiness Agent

Evaluate adoption readiness based on all research findings.

## Input

Read all findings in: `{{project_path}}/research/findings/`

## Evaluation Factors

Score each factor 0-10:

1. **Market Timing** - Is market ready for this solution?
2. **User Sophistication** - Can target users use this product?
3. **Infrastructure Readiness** - Required infra exists?
4. **Regulatory Clarity** - Clear regulatory environment?
5. **Distribution Channels** - Clear path to users?

## Output Format

```json
{
  "framework": "adoption_readiness",
  "scores": {
    "market_timing": {"score": 8, "rationale": "..."},
    "user_sophistication": {"score": 7, "rationale": "..."},
    "infrastructure_readiness": {"score": 9, "rationale": "..."},
    "regulatory_clarity": {"score": 5, "rationale": "..."},
    "distribution_channels": {"score": 6, "rationale": "..."}
  },
  "total_score": 35,
  "max_score": 50,
  "readiness": 0.70,
  "assessment": "Good adoption readiness - regulatory clarity is main concern"
}
```

Write to: `{{project_path}}/research/frameworks/adoption_readiness_score.json`
```

---

### LAYER 4: ANALYSIS AGENTS

#### Source Evaluator Agent

**File**: `.claude/agents/analysis/source-evaluator-agent.md`

```markdown
---
name: source-evaluator-agent
description: Evaluate source credibility and assign trust tiers (mirrors Autopack's SourceEvaluator)
tools: [Read, Write]
model: haiku
---

# Source Evaluator Agent

Evaluate and rank all discovered sources.

## Input

Read all sources from: `{{project_path}}/research/discovery/`

## Trust Tiers (from Autopack)

- **Tier 3 (High)**: Official documentation, peer-reviewed, government sources
- **Tier 2 (Medium)**: Reputable news, established blogs, verified company pages
- **Tier 1 (Low)**: User forums, social media, unverified blogs

## Evaluation Criteria

1. **Domain Authority** - Known reputable domain?
2. **Content Type** - Documentation > News > Blog > Forum
3. **Recency** - Within 2 years?
4. **Verifiability** - Can claims be verified?

## Output Format

```json
{
  "evaluated_sources": [
    {
      "url": "https://...",
      "trust_tier": 3,
      "credibility_score": 0.9,
      "evaluation": {
        "domain_authority": "high",
        "content_type": "official_documentation",
        "recency": "2024",
        "verifiable": true
      }
    }
  ],
  "tier_distribution": {
    "tier_3": 10,
    "tier_2": 25,
    "tier_1": 15
  }
}
```

Write to: `{{project_path}}/research/validation/source_evaluation.json`
```

#### Analysis Agent

**File**: `.claude/agents/analysis/analysis-agent.md`

```markdown
---
name: analysis-agent
description: Aggregate findings, deduplicate, and identify gaps (mirrors Autopack's AnalysisAgent)
tools: [Read, Write]
model: sonnet
---

# Analysis Agent

Aggregate and analyze all research findings.

## Input

Read all findings from: `{{project_path}}/research/findings/`

## Tasks (from Autopack's AnalysisAgent)

1. **Aggregate Findings**
   - Group by type (market, competitive, technical, legal, sentiment, tool)
   - Count findings per category

2. **Deduplicate Content**
   - Remove findings with >80% content similarity
   - Preserve highest-confidence version

3. **Identify Gaps**
   - Check for missing categories
   - Check for thin coverage areas
   - Flag contradictions

4. **Cross-Reference**
   - Find conflicts between sources
   - Note where findings reinforce each other

## Output Format

```json
{
  "aggregated_findings": {
    "market_intelligence": [...],
    "competitive_analysis": [...],
    "technical_analysis": [...],
    "legal_compliance": [...],
    "social_sentiment": [...],
    "tool_availability": [...]
  },
  "deduplication": {
    "original_count": 150,
    "after_dedup": 120,
    "removed": 30
  },
  "gaps": [
    {
      "category": "technical",
      "gap": "No API rate limit data for Service X",
      "impact": "medium"
    }
  ],
  "conflicts": [
    {
      "finding_1": "...",
      "finding_2": "...",
      "conflict": "Contradictory market size estimates"
    }
  ],
  "coverage_score": 0.85
}
```

Write to: `{{project_path}}/research/analysis/aggregated_findings.json`
```

#### Compilation Agent

**File**: `.claude/agents/analysis/compilation-agent.md`

```markdown
---
name: compilation-agent
description: Compile, categorize, and preserve citations (mirrors Autopack's CompilationAgent)
tools: [Read, Write]
model: sonnet
---

# Compilation Agent

Compile final research output with full citation preservation.

## Input

Read: `{{project_path}}/research/analysis/aggregated_findings.json`

## Tasks (from Autopack's CompilationAgent)

1. **Categorize by Type**
   - Technical findings
   - UX/User findings
   - Market findings
   - Competitive findings

2. **Preserve Citations**
   - Every finding must have extraction_span
   - Every finding must have source_url
   - Every finding must have source_hash

3. **Compile Report**
   - Structure for human readability
   - Include all citations

## Output Format

```json
{
  "compiled_findings": {
    "technical": [...],
    "ux": [...],
    "market": [...],
    "competition": [...]
  },
  "citation_count": 120,
  "all_citations": [
    {
      "source": "URL",
      "title": "...",
      "extraction_spans": ["quote1", "quote2"],
      "accessed_at": "ISO timestamp"
    }
  ]
}
```

Write to: `{{project_path}}/research/compilation/compiled_findings.json`
```

---

### LAYER 5: VALIDATION AGENTS

#### Citation Validator Agent

**File**: `.claude/agents/validation/citation-validator-agent.md`

```markdown
---
name: citation-validator-agent
description: Verify extracted findings match source documents (mirrors Autopack's CitationValidator)
tools: [WebFetch, Read, Write]
model: sonnet
---

# Citation Validator Agent

Validate that extraction_spans match source documents.

## Input

Read: `{{project_path}}/research/compilation/compiled_findings.json`

## Validation Process (from Autopack)

For each finding with extraction_span:

1. **Fetch Source** - Get current source content
2. **Normalize Text** - Handle HTML entities, whitespace, Unicode
3. **Verify Match** - Check extraction_span exists in source
4. **Hash Verification** - Verify source hasn't changed

## Verification Result

```json
{
  "valid": true|false,
  "reason": "Text match found|Text not found in source|Source changed",
  "confidence": 0.95
}
```

## Output Format

```json
{
  "validation_results": [
    {
      "finding_id": "...",
      "source_url": "...",
      "extraction_span": "...",
      "verification": {
        "valid": true,
        "reason": "Text match found at position 1523",
        "confidence": 0.98
      }
    }
  ],
  "summary": {
    "total_findings": 120,
    "validated": 115,
    "failed": 5,
    "validation_rate": 0.958
  }
}
```

Write to: `{{project_path}}/research/validation/citation_validation.json`

## CRITICAL

Findings that fail validation MUST be flagged and excluded from final synthesis.
```

#### Evidence Validator Agent

**File**: `.claude/agents/validation/evidence-validator-agent.md`

```markdown
---
name: evidence-validator-agent
description: Validate evidence authenticity and type (mirrors Autopack's EvidenceValidator)
tools: [Read, Write]
model: haiku
---

# Evidence Validator Agent

Validate evidence meets quality standards.

## Input

Read: `{{project_path}}/research/compilation/compiled_findings.json`

## Validation Criteria (from Autopack)

1. **Evidence Type Valid** - EMPIRICAL|THEORETICAL|STATISTICAL|ANECDOTAL
2. **Relevance Score** - Must be > 0.5
3. **Citation Present** - Must have source attribution
4. **Type Appropriate** - Evidence type matches claim type

## Output Format

```json
{
  "validation_results": [
    {
      "finding_id": "...",
      "evidence_type": "STATISTICAL",
      "relevance": 0.85,
      "has_citation": true,
      "valid": true,
      "issues": []
    }
  ],
  "summary": {
    "total": 120,
    "valid": 118,
    "invalid": 2
  }
}
```

Write to: `{{project_path}}/research/validation/evidence_validation.json`
```

#### Quality Validator Agent

**File**: `.claude/agents/validation/quality-validator-agent.md`

```markdown
---
name: quality-validator-agent
description: Assess logical consistency and clarity (mirrors Autopack's QualityValidator)
tools: [Read, Write]
model: sonnet
---

# Quality Validator Agent

Validate research quality and logical consistency.

## Input

Read all findings and reports in: `{{project_path}}/research/`

## Validation Criteria (from Autopack)

1. **Logical Consistency** - Findings don't contradict each other
2. **Conclusion Clarity** - Clear, actionable conclusions
3. **Methodology Adherence** - Research followed stated methodology
4. **Bias Detection** - Check for systematic bias

## Output Format

```json
{
  "quality_assessment": {
    "logical_consistency": {
      "score": 0.85,
      "issues": ["Market size estimates vary significantly between sources"]
    },
    "conclusion_clarity": {
      "score": 0.90,
      "issues": []
    },
    "methodology_adherence": {
      "score": 0.95,
      "issues": []
    },
    "bias_detection": {
      "score": 0.80,
      "issues": ["Over-reliance on competitor marketing materials"]
    }
  },
  "overall_quality": 0.875,
  "pass": true
}
```

Write to: `{{project_path}}/research/validation/quality_validation.json`
```

#### Recency Validator Agent

**File**: `.claude/agents/validation/recency-validator-agent.md`

```markdown
---
name: recency-validator-agent
description: Ensure evidence is recent and relevant (mirrors Autopack's RecencyValidator)
tools: [Read, Write]
model: haiku
---

# Recency Validator Agent

Validate research recency.

## Input

Read: `{{project_path}}/research/compilation/compiled_findings.json`

## Validation Criteria (from Autopack)

1. **Publication Date** - Within 2 years (configurable)
2. **Market Relevance** - Still applicable to current market
3. **Technology Currency** - Tech references are current

## Output Format

```json
{
  "recency_results": [
    {
      "finding_id": "...",
      "source_date": "2024-03-15",
      "age_days": 120,
      "within_threshold": true,
      "concerns": []
    }
  ],
  "summary": {
    "total": 120,
    "recent": 110,
    "outdated": 10,
    "outdated_findings": ["finding_id_1", "finding_id_2"]
  }
}
```

Write to: `{{project_path}}/research/validation/recency_validation.json`
```

---

### LAYER 6: SYNTHESIS AGENTS

#### Meta Auditor Agent

**File**: `.claude/agents/synthesis/meta-auditor-agent.md`

```markdown
---
name: meta-auditor-agent
description: Synthesize all framework scores into strategic recommendations (mirrors Autopack's MetaAuditor)
tools: [Read, Write]
model: opus
---

# Meta Auditor Agent

Synthesize all research into strategic recommendations.

## Input

Read all framework scores from: `{{project_path}}/research/frameworks/`
Read validation results from: `{{project_path}}/research/validation/`
Read compiled findings from: `{{project_path}}/research/compilation/`

## Synthesis Tasks (from Autopack's MetaAuditor)

1. **Aggregate Framework Scores**
   - Market Attractiveness: X/50
   - Competitive Intensity: X/50
   - Product Feasibility: X/50
   - Adoption Readiness: X/50

2. **Calculate Overall Viability**
   - Weighted combination of scores
   - Adjust for validation failures

3. **Generate Strategic Recommendations**
   - Go/No-Go recommendation
   - Key success factors
   - Critical risks
   - Recommended approach

4. **Prioritize Opportunities**
   - Rank differentiation opportunities
   - Rank market entry strategies

## Output Format

```json
{
  "framework_synthesis": {
    "market_attractiveness": 0.70,
    "competitive_intensity": 0.50,
    "product_feasibility": 0.68,
    "adoption_readiness": 0.70
  },
  "overall_viability": {
    "score": 0.72,
    "rating": "High",
    "confidence": 0.85
  },
  "strategic_recommendations": {
    "go_no_go": "GO",
    "rationale": "...",
    "key_success_factors": ["...", "..."],
    "critical_risks": [
      {
        "risk": "...",
        "likelihood": "medium",
        "impact": "high",
        "mitigation": "..."
      }
    ],
    "recommended_approach": "..."
  },
  "prioritized_opportunities": [
    {
      "opportunity": "...",
      "priority": 1,
      "rationale": "..."
    }
  ]
}
```

Write to: `{{project_path}}/research_synthesis.json`
Write report: `{{project_path}}/research_synthesis.md`
```

#### Anchor Generator Agent

**File**: `.claude/agents/synthesis/anchor-generator-agent.md`

```markdown
---
name: anchor-generator-agent
description: Generate IntentionAnchorV2 from research synthesis
tools: [Read, Write]
model: opus
---

# Anchor Generator Agent

Generate IntentionAnchorV2 YAML from research synthesis.

## Input

Read: `{{project_path}}/research_synthesis.json`
Read: `{{project_path}}/research/findings/*.json`
Read: `{{project_path}}/research/validation/*.json`

## Mapping Rules (Research → Pivots)

| Research Output | Maps To Pivot |
|-----------------|---------------|
| Market size, trends | NorthStar.desired_outcomes |
| Competitor gaps | NorthStar.non_goals |
| ToS violations | SafetyRisk.never_allow |
| Approval requirements | SafetyRisk.requires_approval |
| API limits, blockers | EvidenceVerification.hard_blocks |
| Platform policies | ScopeBoundaries.network_allowlist |
| Cost estimates | BudgetCost.estimated_monthly_cost |
| Data requirements | MemoryContinuity.persist_to_sot |
| Risk level | GovernanceReview.default_policy |

## Output Files

1. `{{project_path}}/intention_anchor.yaml` - Full anchor
2. `{{project_path}}/tech_stack_proposal.yaml` - Stack options
3. `{{project_path}}/clarifying_questions.md` - If gaps exist

## Anchor Schema

```yaml
format_version: "2.0"
project_id: "{{project_id}}"
created_at: "{{timestamp}}"
research_session_id: "{{session_id}}"

pivot_intentions:
  north_star:
    desired_outcomes:
      - outcome: "[from market research]"
        success_signal: "[measurable metric]"
        priority: "P1|P2|P3"
    non_goals:
      - "[from competitive gaps - what NOT to build]"

  safety_risk:
    never_allow:
      - operation: "[from legal research NEVER-ALLOW]"
        rationale: "[why]"
        source: "[ToS URL]"
    requires_approval:
      - operation: "[from legal research REQUIRES-APPROVAL]"
        approval_channel: "cli|pr|telegram"
    risk_tolerance: "conservative|moderate|aggressive"

  evidence_verification:
    hard_blocks:
      - check: "[from technical research - API blockers]"
        rationale: "[why blocking]"
    required_proofs:
      - artifact: "[what must be produced]"
        format: "[format]"

  scope_boundaries:
    allowed_write_roots:
      - "{{project_path}}/src"
      - "{{project_path}}/tests"
    protected_paths:
      - path: "[sensitive path]"
        reason: "[why protected]"
    network_allowlist:
      - domain: "[from API research]"
        purpose: "[why needed]"

  budget_cost:
    token_cap_per_phase: 50000
    token_cap_global: 500000
    time_cap_per_phase_minutes: 30
    estimated_monthly_cost: "[from technical research]"
    cost_escalation_policy: "stop|warn|continue"

  memory_continuity:
    persist_to_sot:
      - "BUILD_HISTORY.md"
      - "DEBUG_LOG.md"
    retention_rules:
      research: "permanent"
      run_artifacts: "30_days"

  governance_review:
    default_policy: "deny"
    auto_approval_rules:
      - pattern: "[low-risk pattern]"
        conditions: ["[conditions]"]
    approval_channels:
      - channel: "cli"
        for: "low_risk"
      - channel: "pr"
        for: "high_risk"

  parallelism_isolation:
    allowed: false
    isolation_model: "worktree"
    max_parallel_runs: 1
```

## Tech Stack Proposal Schema

```yaml
project_type: "{{detected_type}}"

options:
  - name: "[Option A]"
    components: ["framework", "library"]
    pros: ["[from technical research]"]
    cons: ["[from technical research]"]
    risk_level: "low|medium|high"
    estimated_monthly_cost: "$X-Y"
    mcp_integrations:
      - name: "[mcp name]"
        status: "available|to_build"
        purpose: "[purpose]"

recommended: "[Option X]"
recommendation_rationale: "[from meta auditor]"
```

## Clarifying Questions

If any pivot has confidence < 0.7:

```markdown
# Clarifying Questions: {{project_title}}

## Critical (Must Answer)

### Q1: [Question from validate_pivot_completeness()]
**Context**: [why needed]
**Options**:
- A) [option]
- B) [option]
**Default**: [default]

## Important (Should Answer)
...

## Optional
...
```

## Final Step

After generating all files, create: `{{project_path}}/READY_FOR_AUTOPACK`
```

---

## Skill: Project Bootstrap

**File**: `.claude/skills/project-bootstrap/SKILL.md`

```markdown
---
name: project-bootstrap
description: Bootstrap a new project from idea through comprehensive research to Autopack-ready state
user_invocable: true
---

# Project Bootstrap Skill

## Usage

```
/project-bootstrap "Automated Etsy image upload with AI generation"
/project-bootstrap C:\path\to\ideas.md --project 1
```

## Complete Workflow

### Phase 1: Setup (Main Claude)
1. Parse input (idea string or file)
2. Create project directory structure
3. Initialize research session

### Phase 2: Discovery (Parallel Agents)
Launch IN PARALLEL:
- @web-discovery-agent
- @github-discovery-agent
- @social-discovery-agent

Wait for all to complete.

### Phase 3: Source Evaluation
Launch: @source-evaluator-agent

### Phase 4: Research (Parallel Agents)
Launch IN PARALLEL:
- @market-research-agent (with its 4 sub-agents)
- @competitive-analysis-agent (with its 4 sub-agents)
- @technical-feasibility-agent (with its 4 sub-agents)
- @legal-policy-agent (with its 4 sub-agents)
- @social-sentiment-agent (with its 3 sub-agents)
- @tool-availability-agent (with its 3 sub-agents)

Wait for all to complete.

### Phase 5: Framework Evaluation (Parallel)
Launch IN PARALLEL:
- @market-attractiveness-agent
- @competitive-intensity-agent
- @product-feasibility-agent
- @adoption-readiness-agent

Wait for all to complete.

### Phase 6: Analysis (Sequential)
1. Launch: @analysis-agent
2. Launch: @compilation-agent

### Phase 7: Validation (Parallel)
Launch IN PARALLEL:
- @citation-validator-agent
- @evidence-validator-agent
- @quality-validator-agent
- @recency-validator-agent

Wait for all to complete.

### Phase 8: Synthesis (Sequential)
1. Launch: @meta-auditor-agent
2. Launch: @anchor-generator-agent

### Phase 9: User Review
If clarifying_questions.md exists:
- Present questions
- Collect answers
- Re-run @anchor-generator-agent with answers

### Phase 10: Finalize
- Validate all outputs
- Create READY_FOR_AUTOPACK marker
- Print summary

## Execution Model

```
                    Main Claude
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   Discovery       Discovery       Discovery
   Agent (Web)     Agent (GitHub)  Agent (Social)
        │               │               │
   ┌────┴────┐     ┌────┴────┐     ┌────┴────┐
   │ │ │     │     │ │ │ │   │     │ │ │ │   │
   Sub-agents      Sub-agents      Sub-agents
   (parallel)      (parallel)      (parallel)
        │               │               │
        └───────────────┼───────────────┘
                        │
                        ▼
               Source Evaluator
                        │
        ┌───────────────┼───────────────┐
        │       │       │       │       │       │
        ▼       ▼       ▼       ▼       ▼       ▼
     Market  Compet  Tech    Legal  Sentim  Tools
     Agent   Agent   Agent   Agent  Agent   Agent
        │       │       │       │       │       │
     4 sub   4 sub  4 sub   4 sub  3 sub   3 sub
        │       │       │       │       │       │
        └───────┴───────┼───────┴───────┴───────┘
                        │
        ┌───────────────┼───────────────┐
        │       │       │       │       │
        ▼       ▼       ▼       ▼       │
     Market  Compet  Product  Adopt    │
     Attrac  Intens  Feasib   Ready    │
                        │               │
        └───────────────┼───────────────┘
                        │
                ┌───────┴───────┐
                ▼               ▼
           Analysis      Compilation
                │               │
                └───────┬───────┘
                        │
        ┌───────┬───────┼───────┬───────┐
        ▼       ▼       ▼       ▼       │
     Citation Evidence Quality Recency  │
     Valid    Valid    Valid   Valid    │
        └───────┴───────┼───────┴───────┘
                        │
                ┌───────┴───────┐
                ▼               ▼
           Meta Auditor   Anchor Generator
                        │
                        ▼
               READY_FOR_AUTOPACK
```
```

---

## Quality Standards (Matching Autopack)

| Autopack Component | Claude Agent | Quality Requirement |
|--------------------|--------------|---------------------|
| AnalysisAgent | analysis-agent | Aggregate, deduplicate (80% threshold), identify gaps |
| CompilationAgent | compilation-agent | Preserve all citations with extraction_span |
| IntentClarifier | (Main Claude) | Max 8 clarifying questions |
| WebDiscovery | web-discovery-agent | Cite all sources, verify recency |
| GitHubDiscovery | github-discovery-agent | Check repo activity, stars, recent commits |
| RedditDiscovery | social-discovery-agent | Sample 20+ discussions |
| MarketAttractiveness | market-attractiveness-agent | Score all 5 factors 0-10 |
| CompetitiveIntensity | competitive-intensity-agent | Score all 5 factors 0-10 |
| ProductFeasibility | product-feasibility-agent | Score all 5 factors 0-10 |
| AdoptionReadiness | adoption-readiness-agent | Score all 5 factors 0-10 |
| CitationValidator | citation-validator-agent | Verify exact extraction_span match |
| EvidenceValidator | evidence-validator-agent | Relevance > 0.5, type valid |
| QualityValidator | quality-validator-agent | Logical consistency, clarity |
| RecencyValidator | recency-validator-agent | Within 2 years |
| MetaAuditor | meta-auditor-agent | Synthesize all frameworks, strategic recommendations |

---

## Implementation Phases

### Phase 1: Directory Structure
Create all directories under `.claude/`

### Phase 2: Discovery Layer (5 agents + 10 sub-agents)
- web-discovery-agent.md
- github-discovery-agent.md
- social-discovery-agent.md
- 10 discovery sub-agents

### Phase 3: Research Layer (6 agents + 22 sub-agents)
- 6 research agents
- 22 research sub-agents

### Phase 4: Framework Layer (4 agents)
- 4 framework evaluation agents

### Phase 5: Analysis Layer (3 agents)
- source-evaluator-agent.md
- analysis-agent.md
- compilation-agent.md

### Phase 6: Validation Layer (4 agents)
- 4 validation agents

### Phase 7: Synthesis Layer (2 agents)
- meta-auditor-agent.md
- anchor-generator-agent.md

### Phase 8: Skill
- project-bootstrap/SKILL.md

### Phase 9: Scripts
- create-project-structure.ts
- validate-research-output.ts
- trigger-autopack.ps1

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Total agents | 20 |
| Total sub-agents | 32 |
| Research coverage | 100% of Autopack's research infrastructure |
| Findings per project | 100+ validated findings |
| Citation validation rate | >95% |
| Framework coverage | All 4 frameworks evaluated |
| Handoff success | 100% trigger Autopack correctly |
| Total time (parallel) | <45 minutes per project |
