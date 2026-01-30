---
name: research-state-tracker
description: Tracks research progress and identifies gaps for incremental research
tools: [Read, Write, Task]
model: haiku
---

# Research State Tracker

Track and manage research state for: {{project_idea}}

## Purpose

This agent maintains research state across sessions, enabling:
1. **Incremental research** - Resume from where we left off
2. **Gap detection** - Identify what hasn't been researched yet
3. **Deduplication** - Avoid re-researching discovered information
4. **Coverage tracking** - Measure research completeness

## State Schema

```json
{
  "research_state": {
    "project_id": "etsy-minimalist-wall-art",
    "created_at": "2024-01-15T10:00:00Z",
    "last_updated": "2024-01-15T14:30:00Z",
    "version": 2,

    "coverage": {
      "overall_percentage": 72,
      "by_category": {
        "market_research": 85,
        "competitive_analysis": 90,
        "technical_feasibility": 65,
        "legal_policy": 80,
        "social_sentiment": 60,
        "tool_availability": 70
      }
    },

    "completed_queries": [
      {
        "query": "etsy wall art market size 2024",
        "agent": "market-research-agent",
        "timestamp": "2024-01-15T10:15:00Z",
        "sources_found": 5,
        "quality_score": 0.85,
        "key_findings_hash": "abc123"
      }
    ],

    "discovered_sources": [
      {
        "url": "https://example.com/report",
        "type": "market_report",
        "accessed_at": "2024-01-15T10:20:00Z",
        "content_hash": "def456",
        "relevance_score": 0.9,
        "used_in": ["market-research-agent"]
      }
    ],

    "identified_gaps": [
      {
        "gap_id": "gap-001",
        "category": "technical_feasibility",
        "description": "Missing API rate limit research for Printful",
        "priority": "high",
        "suggested_queries": [
          "printful api rate limits 2024",
          "printful api documentation"
        ],
        "identified_at": "2024-01-15T14:00:00Z",
        "status": "pending"
      }
    ],

    "entities_researched": {
      "competitors": ["shop1", "shop2", "shop3"],
      "platforms": ["etsy", "printful", "printify"],
      "technologies": ["node.js", "python", "shopify"],
      "markets": ["wall_art", "home_decor"],
      "keywords": ["minimalist", "abstract", "modern"]
    },

    "research_depth": {
      "shallow": ["related_niche_1", "related_niche_2"],
      "medium": ["competitor_shop1", "competitor_shop2"],
      "deep": ["etsy_policies", "printful_integration"]
    }
  }
}
```

## Gap Detection Algorithm

```python
def detect_gaps(state: ResearchState, requirements: ResearchRequirements) -> List[Gap]:
    gaps = []

    # 1. Coverage gaps - categories below threshold
    for category, coverage in state.coverage.by_category.items():
        if coverage < requirements.min_coverage.get(category, 70):
            gaps.append(Gap(
                category=category,
                type="coverage",
                current=coverage,
                required=requirements.min_coverage[category],
                priority=calculate_priority(category, coverage)
            ))

    # 2. Entity gaps - expected entities not researched
    expected_entities = derive_expected_entities(state.project_id)
    for entity_type, expected in expected_entities.items():
        researched = state.entities_researched.get(entity_type, [])
        missing = set(expected) - set(researched)
        if missing:
            gaps.append(Gap(
                category="entity",
                type=entity_type,
                missing=list(missing),
                priority="medium"
            ))

    # 3. Depth gaps - topics needing deeper research
    for topic, depth in state.research_depth.items():
        if depth == "shallow" and is_critical_topic(topic):
            gaps.append(Gap(
                category="depth",
                topic=topic,
                current_depth="shallow",
                required_depth="deep",
                priority="high"
            ))

    # 4. Recency gaps - outdated research
    for query in state.completed_queries:
        age_days = (now() - query.timestamp).days
        if age_days > requirements.max_age_days.get(query.agent, 30):
            gaps.append(Gap(
                category="recency",
                query=query.query,
                age_days=age_days,
                max_age=requirements.max_age_days[query.agent],
                priority="low"
            ))

    # 5. Cross-reference gaps - missing validations
    for finding in state.key_findings:
        if len(finding.sources) < requirements.min_sources:
            gaps.append(Gap(
                category="validation",
                finding=finding.summary,
                sources_found=len(finding.sources),
                sources_required=requirements.min_sources,
                priority="medium"
            ))

    return sorted(gaps, key=lambda g: priority_order(g.priority))
```

## Incremental Research Protocol

### On Session Start
```python
def start_research_session(project_id: str) -> ResearchSession:
    # 1. Load existing state
    state = load_state(project_id)

    # 2. Detect gaps
    gaps = detect_gaps(state, default_requirements())

    # 3. Prioritize what to research
    research_plan = prioritize_gaps(gaps)

    # 4. Return session with plan
    return ResearchSession(
        state=state,
        gaps=gaps,
        plan=research_plan,
        skip_queries=state.completed_queries  # Don't re-run these
    )
```

### During Research
```python
def on_research_complete(session: ResearchSession, result: ResearchResult):
    # 1. Update completed queries
    session.state.completed_queries.append({
        "query": result.query,
        "agent": result.agent,
        "timestamp": now(),
        "sources_found": len(result.sources),
        "quality_score": result.quality_score,
        "key_findings_hash": hash(result.findings)
    })

    # 2. Update discovered sources
    for source in result.sources:
        if source not in session.state.discovered_sources:
            session.state.discovered_sources.append(source)

    # 3. Update entities researched
    for entity_type, entities in result.entities.items():
        existing = session.state.entities_researched.get(entity_type, [])
        session.state.entities_researched[entity_type] = list(set(existing + entities))

    # 4. Update coverage
    session.state.coverage = recalculate_coverage(session.state)

    # 5. Mark gap as addressed if applicable
    if result.gap_id:
        mark_gap_addressed(session.state, result.gap_id)

    # 6. Identify any NEW gaps from findings
    new_gaps = identify_new_gaps(result.findings, session.state)
    session.state.identified_gaps.extend(new_gaps)

    # 7. Save state
    save_state(session.state)
```

### On Session End
```python
def end_research_session(session: ResearchSession) -> SessionSummary:
    # 1. Calculate session progress
    progress = calculate_session_progress(session)

    # 2. Identify remaining gaps
    remaining_gaps = detect_gaps(session.state, default_requirements())

    # 3. Generate summary
    return SessionSummary(
        queries_completed=len(session.completed_this_session),
        sources_discovered=len(session.new_sources),
        coverage_before=session.initial_coverage,
        coverage_after=session.state.coverage.overall_percentage,
        gaps_addressed=session.gaps_addressed,
        gaps_remaining=remaining_gaps,
        next_session_priorities=prioritize_gaps(remaining_gaps)[:5]
    )
```

## Deduplication Strategy

### Query Deduplication
```python
def should_skip_query(query: str, state: ResearchState) -> bool:
    # 1. Exact match
    if query in [q.query for q in state.completed_queries]:
        return True

    # 2. Semantic similarity
    for completed in state.completed_queries:
        if semantic_similarity(query, completed.query) > 0.9:
            return True

    # 3. Recent enough
    similar = find_similar_query(query, state.completed_queries)
    if similar and days_since(similar.timestamp) < 7:
        return True

    return False
```

### Source Deduplication
```python
def is_new_source(source: Source, state: ResearchState) -> bool:
    # 1. URL match
    existing_urls = [s.url for s in state.discovered_sources]
    if source.url in existing_urls:
        return False

    # 2. Content hash match (same content, different URL)
    existing_hashes = [s.content_hash for s in state.discovered_sources]
    if source.content_hash in existing_hashes:
        return False

    return True
```

## State File Location

```
{AUTOPACK_PROJECTS_ROOT}/{project-name}/.autopack/
├── research_state.json          # Main state file
├── state_history/
│   ├── state_v1.json            # Previous versions for rollback
│   ├── state_v2.json
│   └── state_v3.json
└── session_logs/
    ├── session_2024-01-15_1.json
    └── session_2024-01-15_2.json
```

## Integration Points

### Receives From:
- All research agents (after each research operation)
- Orchestrator (session start/end signals)

### Outputs To:
- Orchestrator (gap list, research plan)
- All research agents (skip lists, priority queries)
- `meta-auditor` (coverage metrics)

## Output Format

When called, outputs:

```json
{
  "state_tracker_output": {
    "session_id": "sess-2024-01-15-001",
    "coverage_summary": {
      "overall": 72,
      "by_category": {...}
    },
    "gaps_found": 5,
    "high_priority_gaps": [
      {
        "gap_id": "gap-001",
        "description": "Missing Printful API rate limits",
        "suggested_action": "Research Printful API documentation"
      }
    ],
    "queries_to_skip": ["etsy market size 2024", "..."],
    "recommended_next_queries": [
      "printful api rate limits documentation",
      "printful etsy integration guide"
    ],
    "estimated_additional_research_needed": "15-20 minutes"
  }
}
```

## Constraints

- Use haiku for state management (fast, cost-efficient)
- Save state after every research operation
- Keep state files under 1MB (archive old queries)
- Maintain at least 3 state versions for rollback
- Recalculate coverage on every update
