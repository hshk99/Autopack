# Stage 2A: Deep Retrieval - Bounded Escalation

## Overview

Stage 2A implements bounded deep retrieval escalation when Stage 1 evidence (handoff bundle) lacks sufficient signal. It retrieves targeted snippets from run-local artifacts, Source of Truth (SOT) documentation, and optional memory, with strict per-category caps and recency awareness to prevent context noise.

## Architecture

### Components

1. **RetrievalTrigger** (`src/autopack/diagnostics/retrieval_triggers.py`)
   - Detects insufficient Stage 1 evidence
   - Determines escalation priority
   - Analyzes handoff bundle quality

2. **DeepRetrieval** (`src/autopack/diagnostics/deep_retrieval.py`)
   - Executes bounded retrieval with strict caps
   - Ranks content by relevance and recency
   - Assembles retrieval bundle with metadata

### Data Flow

```
Handoff Bundle (Stage 1)
    ↓
RetrievalTrigger.should_escalate()
    ↓ (if triggered)
RetrievalTrigger.get_retrieval_priority()
    ↓
DeepRetrieval.retrieve()
    ↓
Retrieval Bundle (Stage 2A)
```

## Retrieval Triggers

### Trigger 1: Empty or Minimal Handoff Bundle

**Detection Logic:**
- Empty bundle (no keys)
- Error message < 20 characters
- Missing stack trace AND missing recent changes
- All critical fields empty

**Example:**
```python
# Triggers escalation
bundle = {
    "error_message": "Error",  # Too short
    "stack_trace": "",
    "recent_changes": []
}

# Does not trigger
bundle = {
    "error_message": "FileNotFoundError: Could not find config.yaml in /path/to/dir",
    "stack_trace": "Traceback (most recent call last):\n  File test.py line 10\n" * 3,
    "recent_changes": ["file1.py", "file2.py"]
}
```

### Trigger 2: Lack of Actionable Context

**Detection Logic:**
- Generic error phrases:
  - "unknown error"
  - "internal error"
  - "something went wrong"
- Error message < 30 characters
- No specific file paths, line numbers, or module names

**Example:**
```python
# Triggers escalation
bundle = {
    "error_message": "An unknown error occurred",
    "root_cause": "Unknown"
}

# Does not trigger
bundle = {
    "error_message": "FileNotFoundError: Could not find config.yaml in /path/to/dir",
    "root_cause": "Missing configuration file config.yaml"
}
```

### Trigger 3: Repeated Failures

**Detection Logic:**
- Attempt number ≥ 2
- Previous attempt logs contain failure markers:
  - "ERROR:"
  - "FAILED"
  - "Exception:"
  - "Traceback:"

**Example:**
```python
# Triggers escalation on attempt 2+
# phase_001_attempt_1.log contains: "ERROR: First failure\nFAILED to complete"
# phase_001_attempt_2.log contains: "ERROR: Second failure\nFAILED again"

result = trigger.should_escalate(bundle, "phase_001", attempt=2)
# Returns True
```

### Trigger 4: No Clear Root Cause

**Detection Logic:**
- Missing root_cause field
- Root cause contains unclear phrases:
  - "unknown"
  - "unclear"
  - "investigate"
  - "not sure"
- Root cause < 20 characters

**Example:**
```python
# Triggers escalation
bundle = {
    "error_message": "Detailed error message",
    "root_cause": "Unknown cause"  # Unclear
}

# Does not trigger
bundle = {
    "error_message": "FileNotFoundError: config.yaml not found",
    "root_cause": "Missing configuration file config.yaml in expected directory /etc/app"
}
```

## Priority Determination

**Priority Levels:**
- **High**: 2+ triggers fired
- **Medium**: 1 trigger fired
- **Low**: 0 triggers fired (no escalation needed)

**Example:**
```python
trigger = RetrievalTrigger(run_dir=run_dir)

# High priority (multiple triggers)
bundle = {
    "error_message": "Error",  # Too short (trigger 1)
    "root_cause": "Unknown"    # Unclear (trigger 4)
}
priority = trigger.get_retrieval_priority(bundle)
# Returns "high"

# Medium priority (single trigger)
bundle = {
    "error_message": "Detailed error message with sufficient context",
    "root_cause": "Unknown"  # Only this triggers
}
priority = trigger.get_retrieval_priority(bundle)
# Returns "medium"

# Low priority (no triggers)
bundle = {
    "error_message": "FileNotFoundError: config.yaml not found in /path",
    "root_cause": "Missing configuration file config.yaml in expected directory"
}
priority = trigger.get_retrieval_priority(bundle)
# Returns "low"
```

## Retrieval Caps

### Per-Category Limits

| Category | Max Files | Max Size | Notes |
|----------|-----------|----------|-------|
| Run Artifacts | 5 | 10 KB | Logs, outputs from current run |
| SOT Files | 3 | 15 KB | Documentation, guides, patterns |
| Memory Entries | 5 | 5 KB | Historical context (future) |

### Cap Enforcement

**Run Artifacts:**
```python
MAX_RUN_ARTIFACTS = 5
MAX_RUN_ARTIFACTS_SIZE = 10 * 1024  # 10KB

# Retrieval stops when either limit reached:
# - 5 files retrieved, OR
# - 10KB total size reached
```

**SOT Files:**
```python
MAX_SOT_FILES = 3
MAX_SOT_FILES_SIZE = 15 * 1024  # 15KB

# Retrieval stops when either limit reached:
# - 3 files retrieved, OR
# - 15KB total size reached
```

**Memory Entries:**
```python
MAX_MEMORY_ENTRIES = 5
MAX_MEMORY_ENTRIES_SIZE = 5 * 1024  # 5KB

# Currently returns empty (not yet implemented)
```

## Recency Awareness

### 24-Hour Window Prioritization

**Run Artifacts:**
1. Files modified within last 24 hours are prioritized
2. Within 24h window: sorted by modification time (newest first)
3. Outside 24h window: sorted by modification time (most recent first)
4. Falls back to most recent overall if no files in window

**Example:**
```python
# Files modified:
# - artifact_1.log: 1 hour ago (within window)
# - artifact_2.log: 2 hours ago (within window)
# - artifact_3.log: 48 hours ago (outside window)

# Retrieval order:
# 1. artifact_1.log (most recent in window)
# 2. artifact_2.log (second most recent in window)
# 3. artifact_3.log (most recent outside window)
```

**SOT Files:**
- Ranked by relevance score (keyword matches)
- Recency used as tiebreaker for equal relevance
- Modified time considered for documentation freshness

## Relevance Ranking

### Keyword Extraction

**From Handoff Bundle:**
```python
def _extract_keywords(handoff_bundle):
    """Extract meaningful keywords from handoff bundle."""
    keywords = set()
    
    # Extract from error_message
    if "error_message" in handoff_bundle:
        words = handoff_bundle["error_message"].lower().split()
        keywords.update(w for w in words if len(w) > 4)
    
    # Extract from root_cause
    if "root_cause" in handoff_bundle:
        words = handoff_bundle["root_cause"].lower().split()
        keywords.update(w for w in words if len(w) > 4)
    
    return keywords
```

**Example:**
```python
bundle = {
    "error_message": "Database connection failed unexpectedly",
    "root_cause": "Connection timeout occurred"
}

keywords = _extract_keywords(bundle)
# Returns: {"database", "connection", "failed", "unexpectedly", "timeout", "occurred"}
```

### Relevance Scoring

**SOT Files:**
```python
def _calculate_relevance(file_content, keywords):
    """Calculate relevance score based on keyword matches."""
    content_lower = file_content.lower()
    score = 0
    
    for keyword in keywords:
        # Count occurrences of each keyword
        count = content_lower.count(keyword)
        score += count
    
    return score
```

**Ranking:**
1. Files sorted by relevance score (descending)
2. Ties broken by modification time (newest first)
3. Top N files selected (up to MAX_SOT_FILES)

**Example:**
```python
# Files:
# - error_handling.md: 5 keyword matches
# - introduction.md: 0 keyword matches
# - database_guide.md: 3 keyword matches

# Ranking:
# 1. error_handling.md (score: 5)
# 2. database_guide.md (score: 3)
# 3. introduction.md (score: 0)
```

## Retrieval Bundle Structure

### Output Format

```json
{
  "phase_id": "phase_001",
  "timestamp": "2024-01-15T10:30:00Z",
  "priority": "high",
  "run_artifacts": [
    {
      "path": "phase_001_attempt_1.log",
      "content": "ERROR: Test failure\nFAILED to complete",
      "size": 42,
      "modified": "2024-01-15T10:25:00Z"
    }
  ],
  "sot_files": [
    {
      "path": "docs/error_handling.md",
      "content": "# Error Handling\n\nThis document covers...",
      "size": 1024,
      "relevance_score": 5
    }
  ],
  "memory_entries": [],
  "stats": {
    "run_artifacts_count": 1,
    "run_artifacts_size": 42,
    "sot_files_count": 1,
    "sot_files_size": 1024,
    "memory_entries_count": 0,
    "memory_entries_size": 0
  }
}
```

### Field Descriptions

**Top-Level Fields:**
- `phase_id`: Phase identifier (e.g., "phase_001")
- `timestamp`: ISO 8601 timestamp of retrieval
- `priority`: Escalation priority ("high", "medium", "low")
- `run_artifacts`: Array of run-local artifact entries
- `sot_files`: Array of SOT documentation entries
- `memory_entries`: Array of memory entries (future)
- `stats`: Aggregate statistics

**Artifact Entry:**
- `path`: Relative path from run directory
- `content`: File content (truncated if needed)
- `size`: Content size in bytes
- `modified`: ISO 8601 modification timestamp

**SOT Entry:**
- `path`: Relative path from repository root
- `content`: File content (truncated if needed)
- `size`: Content size in bytes
- `relevance_score`: Keyword match count

**Stats:**
- `*_count`: Number of entries retrieved
- `*_size`: Total size in bytes

## Truncation Behavior

### When Budget Exceeded

**Run Artifacts:**
```python
# If total size would exceed 10KB:
# 1. Stop adding new files
# 2. Truncate last file to fit within budget
# 3. Add truncation marker: "\n[... truncated ...]\n"

if current_size + file_size > MAX_RUN_ARTIFACTS_SIZE:
    remaining = MAX_RUN_ARTIFACTS_SIZE - current_size
    if remaining > 100:  # Minimum useful size
        truncated_content = content[:remaining - 25]
        truncated_content += "\n[... truncated ...]\n"
        # Add truncated file
    # Stop retrieval
```

**SOT Files:**
```python
# If total size would exceed 15KB:
# 1. Stop adding new files
# 2. Truncate last file to fit within budget
# 3. Add truncation marker: "\n[... truncated ...]\n"

if current_size + file_size > MAX_SOT_FILES_SIZE:
    remaining = MAX_SOT_FILES_SIZE - current_size
    if remaining > 100:  # Minimum useful size
        truncated_content = content[:remaining - 25]
        truncated_content += "\n[... truncated ...]\n"
        # Add truncated file
    # Stop retrieval
```

## Isolation Guarantees

### Protected Paths

**Never Modified:**
- `.autonomous_runs/`
- `.git/`
- `autopack.db`

**Read-Only Access:**
- Run directory (specified in constructor)
- Repository root (specified in constructor)
- SOT directories: `docs/`, `src/`, `tests/`

### Allowed Operations

**RetrievalTrigger:**
- ✓ Read log files from run directory
- ✓ Analyze handoff bundle (in-memory)
- ✗ Write to any filesystem location
- ✗ Modify protected paths

**DeepRetrieval:**
- ✓ Read artifacts from run directory
- ✓ Read SOT files from repository
- ✓ Compute relevance scores (in-memory)
- ✗ Write to any filesystem location
- ✗ Modify protected paths

## Usage Examples

### Basic Escalation Check

```python
from pathlib import Path
from src.autopack.diagnostics.retrieval_triggers import RetrievalTrigger
from src.autopack.diagnostics.deep_retrieval import DeepRetrieval

# Initialize
run_dir = Path(".autonomous_runs/run_20240115_103000")
repo_root = Path(".")

trigger = RetrievalTrigger(run_dir=run_dir)
retrieval = DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

# Check if escalation needed
handoff_bundle = {
    "error_message": "Error",
    "root_cause": "Unknown"
}

if trigger.should_escalate(handoff_bundle, "phase_001", attempt=1):
    # Get priority
    priority = trigger.get_retrieval_priority(handoff_bundle)
    
    # Retrieve additional context
    retrieval_bundle = retrieval.retrieve(
        phase_id="phase_001",
        handoff_bundle=handoff_bundle,
        priority=priority
    )
    
    print(f"Retrieved {retrieval_bundle['stats']['run_artifacts_count']} artifacts")
    print(f"Retrieved {retrieval_bundle['stats']['sot_files_count']} SOT files")
```

### High-Priority Retrieval

```python
# Multiple triggers fired
handoff_bundle = {
    "error_message": "",  # Empty (trigger 1)
    "stack_trace": "",
    "root_cause": ""  # Empty (trigger 4)
}

if trigger.should_escalate(handoff_bundle, "phase_001", attempt=2):
    priority = trigger.get_retrieval_priority(handoff_bundle)
    # Returns "high"
    
    retrieval_bundle = retrieval.retrieve(
        phase_id="phase_001",
        handoff_bundle=handoff_bundle,
        priority=priority
    )
    
    # High priority retrieval includes:
    # - Up to 5 most recent run artifacts
    # - Up to 3 most relevant SOT files
    # - Prioritizes files within 24h window
```

### Accessing Retrieved Content

```python
retrieval_bundle = retrieval.retrieve("phase_001", handoff_bundle)

# Access run artifacts
for artifact in retrieval_bundle["run_artifacts"]:
    print(f"Artifact: {artifact['path']}")
    print(f"Size: {artifact['size']} bytes")
    print(f"Modified: {artifact['modified']}")
    print(f"Content:\n{artifact['content']}\n")

# Access SOT files
for sot_file in retrieval_bundle["sot_files"]:
    print(f"SOT File: {sot_file['path']}")
    print(f"Relevance: {sot_file['relevance_score']}")
    print(f"Size: {sot_file['size']} bytes")
    print(f"Content:\n{sot_file['content']}\n")

# Check stats
stats = retrieval_bundle["stats"]
print(f"Total artifacts: {stats['run_artifacts_count']}")
print(f"Total artifacts size: {stats['run_artifacts_size']} bytes")
print(f"Total SOT files: {stats['sot_files_count']}")
print(f"Total SOT size: {stats['sot_files_size']} bytes")
```

## Testing

### Test Coverage

**RetrievalTrigger Tests:**
- `test_retrieval_triggers.py`: 441 lines
- Covers all 4 trigger conditions
- Tests priority determination
- Validates isolation guarantees
- Tests edge cases (None bundle, malformed data, unicode, etc.)

**DeepRetrieval Tests:**
- `test_deep_retrieval.py`: 447 lines
- Tests per-category caps (files and size)
- Validates recency awareness (24h window)
- Tests relevance ranking
- Validates truncation behavior
- Tests isolation guarantees

### Running Tests

```bash
# Run all diagnostics tests
pytest tests/autopack/diagnostics/ -v

# Run trigger tests only
pytest tests/autopack/diagnostics/test_retrieval_triggers.py -v

# Run retrieval tests only
pytest tests/autopack/diagnostics/test_deep_retrieval.py -v

# Run specific test class
pytest tests/autopack/diagnostics/test_retrieval_triggers.py::TestRetrievalTriggerInsufficientBundle -v

# Run with coverage
pytest tests/autopack/diagnostics/ --cov=src.autopack.diagnostics --cov-report=html
```

## Performance Considerations

### Time Complexity

**RetrievalTrigger:**
- `should_escalate()`: O(n) where n = number of log files
- `get_retrieval_priority()`: O(1) (counts triggers)

**DeepRetrieval:**
- `retrieve()`: O(m + k log k) where:
  - m = number of candidate files
  - k = number of files retrieved (limited by caps)
- Keyword extraction: O(w) where w = words in handoff bundle
- Relevance scoring: O(f × w) where f = SOT files, w = keywords

### Space Complexity

**Memory Usage:**
- Handoff bundle: ~1-5 KB
- Retrieval bundle: ~30 KB max (10KB + 15KB + 5KB)
- Temporary buffers: ~50 KB
- Total: ~85 KB per retrieval

**Disk I/O:**
- Run artifacts: Up to 5 file reads (10 KB total)
- SOT files: Up to 3 file reads (15 KB total)
- Log files: Up to 10 file reads (for trigger analysis)
- Total: ~18 file reads, ~25 KB read

## Future Enhancements

### Memory Integration

**Planned Features:**
- Query historical run data from `autopack.db`
- Retrieve similar past failures
- Include resolution patterns
- Respect 5 entry / 5KB cap

**Example:**
```python
# Future implementation
memory_entries = [
    {
        "phase_id": "phase_042",
        "error_pattern": "FileNotFoundError: config.yaml",
        "resolution": "Created missing config file",
        "similarity_score": 0.85
    }
]
```

### Semantic Search

**Planned Features:**
- Use embedding model for semantic similarity
- Rank SOT files by semantic relevance (not just keywords)
- Find conceptually related documentation

**Example:**
```python
# Future implementation
from src.autopack.embeddings import EmbeddingModel

embedding_model = EmbeddingModel()
query_embedding = embedding_model.embed(handoff_bundle["error_message"])
results = embedding_model.search(query_embedding, top_k=3)
```

### Adaptive Caps

**Planned Features:**
- Adjust caps based on priority level
- High priority: larger caps (e.g., 7 files, 15KB)
- Low priority: smaller caps (e.g., 3 files, 5KB)
- Dynamic cap adjustment based on retrieval effectiveness

## References

- **BUILD-043**: Diagnostics Parity - Stage 1 (Handoff Bundle)
- **BUILD-044**: Diagnostics Parity - Stage 2A (Deep Retrieval)
- **BUILD-045**: Diagnostics Parity - Stage 2B (Memory Integration)
- **Isolation Patterns**: Protected path enforcement
- **Test Patterns**: Comprehensive test coverage with fixtures
