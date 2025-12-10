# Directory Routing Configuration in Qdrant

## Overview

This document describes how directory routing rules are stored in Qdrant for semantic similarity-based file classification. This complements the PostgreSQL schema (`directory_routing_rules` table) by enabling content-based routing using vector similarity.

## Collection: `file_routing_patterns`

### Purpose
Store embeddings of example file names and content patterns to enable semantic classification of new files created by Cursor or other tools.

### Schema

**Collection Configuration:**
```python
{
    "collection_name": "file_routing_patterns",
    "vectors_config": {
        "size": 384,  # For sentence-transformers/all-MiniLM-L6-v2
        "distance": "Cosine"
    }
}
```

**Point Structure:**
```python
{
    "id": "uuid-v4",  # Unique identifier
    "vector": [...],  # 384-dimensional embedding
    "payload": {
        "project_id": "file-organizer-app-v1",  # Project identifier
        "file_type": "plan",                     # Target file type
        "example_filename": "IMPLEMENTATION_PLAN_FEATURE_X.md",
        "example_content": "# Implementation Plan\n\n## Goal\n...",
        "keywords": ["plan", "implementation", "design"],
        "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/plans",
        "source_context": "cursor",             # cursor, autopack, manual
        "is_archived": false,
        "priority": 10,
        "created_at": "2025-12-11T00:00:00Z"
    }
}
```

### Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | string | Project identifier (e.g., "autopack", "file-organizer-app-v1") |
| `file_type` | string | Classification type (plan, analysis, log, run, diagnostic, etc.) |
| `example_filename` | string | Example filename for this pattern |
| `example_content` | string | Example file content (first ~500 chars) |
| `keywords` | array[string] | Keywords associated with this file type |
| `destination_path` | string | Target directory path |
| `source_context` | string | Source of file creation (cursor, autopack, manual) |
| `is_archived` | boolean | Whether this is for archived files |
| `priority` | integer | Priority for matching (higher = higher priority) |
| `created_at` | string | ISO 8601 timestamp |

## Usage Pattern

### 1. Classifying a New File

When a new file is created (e.g., by Cursor):

```python
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

# Initialize
client = QdrantClient(host="localhost", port=6333)
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Get file info
filename = "IMPLEMENTATION_PLAN_TIDY_STORAGE.md"
content = """
## Goal
Make run/output creation and tidy-up storage predictable...
"""

# Create embedding from filename + first 500 chars of content
text_to_embed = f"{filename}\n\n{content[:500]}"
query_vector = model.encode(text_to_embed).tolist()

# Search for similar patterns
results = client.search(
    collection_name="file_routing_patterns",
    query_vector=query_vector,
    limit=5,
    score_threshold=0.7,  # Only accept confident matches
    query_filter={
        "must": [
            {"key": "source_context", "match": {"value": "cursor"}},
            {"key": "project_id", "match": {"value": "file-organizer-app-v1"}}
        ]
    }
)

# Get best match
if results and results[0].score >= 0.7:
    best_match = results[0].payload
    file_type = best_match["file_type"]
    destination = best_match["destination_path"]
    print(f"Classified as {file_type}, route to: {destination}")
else:
    # Fallback to unsorted
    print("No confident match, route to: archive/unsorted")
```

### 2. Adding New Patterns

When adding routing rules via migration or manually:

```python
# Example: Add pattern for implementation plans
pattern_text = "IMPLEMENTATION_PLAN_FEATURE.md\n\n## Goal\nImplement new feature X with the following components..."
vector = model.encode(pattern_text).tolist()

client.upsert(
    collection_name="file_routing_patterns",
    points=[{
        "id": str(uuid.uuid4()),
        "vector": vector,
        "payload": {
            "project_id": "file-organizer-app-v1",
            "file_type": "plan",
            "example_filename": "IMPLEMENTATION_PLAN_*.md",
            "example_content": pattern_text,
            "keywords": ["plan", "implementation", "design", "goal"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/plans",
            "source_context": "cursor",
            "is_archived": False,
            "priority": 10,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    }]
)
```

## Seeding Initial Patterns

### Autopack Project Patterns

```python
autopack_patterns = [
    {
        "file_type": "plan",
        "example_filename": "IMPLEMENTATION_PLAN_MEMORY_SYSTEM.md",
        "example_content": "# Implementation Plan\n\n## Goal\nImplement memory and context system...",
        "keywords": ["plan", "implementation", "design", "roadmap", "strategy"],
        "destination_path": "C:\\dev\\Autopack\\archive\\plans"
    },
    {
        "file_type": "analysis",
        "example_filename": "ANALYSIS_PERFORMANCE_REVIEW.md",
        "example_content": "# Performance Analysis\n\n## Findings\nAfter reviewing the system...",
        "keywords": ["analysis", "review", "findings", "retrospective", "postmortem"],
        "destination_path": "C:\\dev\\Autopack\\archive\\analysis"
    },
    {
        "file_type": "prompt",
        "example_filename": "PROMPT_DELEGATION_TASK_X.md",
        "example_content": "# Delegation Prompt\n\nPlease implement the following...",
        "keywords": ["prompt", "delegation", "instruction", "task"],
        "destination_path": "C:\\dev\\Autopack\\archive\\prompts"
    }
]
```

### File Organizer Project Patterns

```python
fileorg_patterns = [
    {
        "file_type": "plan",
        "example_filename": "IMPLEMENTATION_PLAN_COUNTRY_PACKS.md",
        "example_content": "# Implementation Plan: Country Packs\n\n## Goal\nAdd UK/Canada/Australia...",
        "keywords": ["plan", "implementation", "design", "feature"],
        "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/plans"
    },
    {
        "file_type": "analysis",
        "example_filename": "ANALYSIS_DOCKER_BUILD_FAILURE.md",
        "example_content": "# Docker Build Analysis\n\n## Issue\nBuild failing with error...",
        "keywords": ["analysis", "review", "diagnostic", "investigation"],
        "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/analysis"
    },
    {
        "file_type": "report",
        "example_filename": "CONSOLIDATED_BUILD_PROGRESS.md",
        "example_content": "# Build Progress Report\n\n## Summary\nCompleted tasks...",
        "keywords": ["report", "summary", "consolidated", "progress"],
        "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/reports"
    }
]
```

## Integration with PostgreSQL

The Qdrant collection works alongside PostgreSQL:

1. **PostgreSQL** (`directory_routing_rules` table):
   - Stores definitive routing rules
   - Used for keyword-based matching
   - Source of truth for configuration

2. **Qdrant** (`file_routing_patterns` collection):
   - Stores semantic patterns for similarity matching
   - Used when keyword matching is ambiguous
   - Enables fuzzy matching of novel filenames

### Hybrid Classification Strategy

```python
def classify_file(filename: str, content: str, project_id: str) -> str:
    """Classify file using hybrid approach"""

    # Step 1: Try PostgreSQL keyword-based matching
    file_type = classify_file_type_by_keywords(content, db_session, project_id)

    if file_type != "unknown":
        return file_type

    # Step 2: Try Qdrant semantic matching
    text = f"{filename}\n\n{content[:500]}"
    vector = embedding_model.encode(text).tolist()

    results = qdrant_client.search(
        collection_name="file_routing_patterns",
        query_vector=vector,
        limit=1,
        score_threshold=0.7,
        query_filter={"must": [{"key": "project_id", "match": {"value": project_id}}]}
    )

    if results and results[0].score >= 0.7:
        return results[0].payload["file_type"]

    # Step 3: Fallback to "unknown"
    return "unknown"
```

## Maintenance

### Adding New Patterns

When users create new file types or patterns:

```bash
# CLI tool for adding patterns
python scripts/add_routing_pattern.py \
    --project file-organizer-app-v1 \
    --file-type analysis \
    --example-file path/to/example.md \
    --destination ".autonomous_runs/file-organizer-app-v1/archive/analysis"
```

### Updating Embeddings

When switching embedding models:

```bash
# Re-embed all patterns with new model
python scripts/reembed_routing_patterns.py --model BAAI/bge-m3
```

## Performance Considerations

- **Collection Size**: ~100-200 patterns per project (small)
- **Query Latency**: <10ms for similarity search
- **Embedding Time**: ~50ms per file (cached for repeated classifications)
- **Accuracy**: ~90% with good seed patterns

## Monitoring

Track classification accuracy:

```sql
-- In PostgreSQL tidy_activity table
SELECT
    project_id,
    action,
    COUNT(*) as files_classified,
    AVG(CASE WHEN reason LIKE '%semantic%' THEN 1 ELSE 0 END) as semantic_ratio
FROM tidy_activity
WHERE action = 'move'
GROUP BY project_id, action;
```

## Future Enhancements

1. **Active Learning**: Update patterns based on user corrections
2. **Confidence Scores**: Store classification confidence in tidy_activity
3. **Multi-Model Ensemble**: Combine multiple embedding models for robustness
4. **Auto-Seeding**: Generate patterns from existing well-organized directories

## See Also

- [PostgreSQL Schema](../src/autopack/migrations/add_directory_routing_config.sql)
- [Python Models](../src/autopack/directory_routing_models.py)
- [Tidy Workspace Script](../scripts/tidy_workspace.py)
