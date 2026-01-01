# SOT Memory Integration Example

This document shows how to integrate SOT (Source of Truth) memory indexing and retrieval into your Autopack workflow.

## Overview

The SOT memory integration allows Autopack to:
1. **Index** the three SOT ledgers (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS) into vector memory at startup
2. **Retrieve** relevant chunks from these ledgers during phase execution (opt-in)
3. Maintain **stable chunk IDs** for idempotent re-indexing

## Configuration

All features are **opt-in** via environment variables:

```bash
# Enable vector memory
export AUTOPACK_ENABLE_MEMORY=true

# Enable SOT indexing (required for retrieval)
export AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true

# Enable SOT retrieval at runtime
export AUTOPACK_SOT_RETRIEVAL_ENABLED=true

# Optional: Configure limits (defaults shown)
export AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000  # Max chars returned from SOT
export AUTOPACK_SOT_RETRIEVAL_TOP_K=3         # Top-k chunks to retrieve
export AUTOPACK_SOT_CHUNK_MAX_CHARS=1200      # Chunk size for indexing
export AUTOPACK_SOT_CHUNK_OVERLAP_CHARS=150   # Overlap between chunks
```

## Integration Example: Autonomous Executor

Here's how to integrate SOT indexing into the autonomous executor:

```python
# In autonomous_executor.py or your main entry point

from pathlib import Path
from autopack.memory.memory_service import MemoryService
from autopack.config import settings

class AutonomousExecutor:
    def __init__(self, workspace_root: Path, project_id: str):
        self.workspace_root = workspace_root
        self.project_id = project_id

        # Initialize memory service
        self.memory = MemoryService(
            enabled=True,
            use_qdrant=True,  # Or False for FAISS
        )

        # Index SOT docs at startup (if enabled)
        self._index_sot_at_startup()

    def _index_sot_at_startup(self):
        """Index SOT documentation at executor startup."""
        if not settings.autopack_enable_sot_memory_indexing:
            logger.info("[Executor] SOT indexing disabled")
            return

        logger.info("[Executor] Indexing SOT documents...")
        result = self.memory.index_sot_docs(
            project_id=self.project_id,
            workspace_root=self.workspace_root,
        )

        if result["skipped"]:
            logger.info(f"[Executor] SOT indexing skipped: {result.get('reason', 'unknown')}")
        else:
            logger.info(f"[Executor] Indexed {result['indexed']} SOT chunks")

    def execute_phase(self, phase_id: str, task_description: str):
        """Execute a phase with optional SOT context."""
        # Retrieve context (including SOT if enabled)
        context = self.memory.retrieve_context(
            query=task_description,
            project_id=self.project_id,
            include_code=True,
            include_summaries=True,
            include_errors=True,
            include_sot=True,  # Opt-in to SOT retrieval
        )

        # Format for prompt
        formatted_context = self.memory.format_retrieved_context(
            context,
            max_chars=8000,  # Global limit
        )

        # Use formatted_context in your prompt
        prompt = f"""
Task: {task_description}

{formatted_context}

Proceed with implementation...
        """

        # Continue with phase execution...
```

## Integration Example: Custom Script

For standalone scripts that want to use SOT retrieval:

```python
#!/usr/bin/env python3
"""
Example: Search SOT docs for specific content.
"""

import os
from pathlib import Path
from autopack.memory.memory_service import MemoryService

# Enable features
os.environ["AUTOPACK_ENABLE_MEMORY"] = "true"
os.environ["AUTOPACK_ENABLE_SOT_MEMORY_INDEXING"] = "true"
os.environ["AUTOPACK_SOT_RETRIEVAL_ENABLED"] = "true"

# Initialize
workspace_root = Path("/workspace")
memory = MemoryService(enabled=True, use_qdrant=False)

# Index SOT docs
print("Indexing SOT docs...")
result = memory.index_sot_docs("autopack", workspace_root)
print(f"Indexed {result['indexed']} chunks")

# Search
print("\nSearching for 'observability'...")
results = memory.search_sot("observability", "autopack", limit=5)

for i, result in enumerate(results, 1):
    payload = result["payload"]
    print(f"\n{i}. {payload['sot_file']} - {payload.get('heading', 'No heading')}")
    print(f"   Score: {result['score']:.3f}")
    print(f"   Preview: {payload['content_preview'][:200]}...")
```

## Integration Example: Re-indexing After Tidy

If you run tidy consolidation and want to re-index:

```python
from pathlib import Path
from autopack.memory.memory_service import MemoryService

workspace_root = Path("/workspace")
memory = MemoryService(enabled=True, use_qdrant=True)

# Re-index after tidy updates SOT files
print("Re-indexing SOT docs after tidy...")
result = memory.index_sot_docs("autopack", workspace_root)

if result["skipped"]:
    print(f"Skipped: {result['reason']}")
else:
    print(f"Re-indexed {result['indexed']} chunks")
    print("Note: Chunks with same content will have same IDs (idempotent)")
```

## Verifying Configuration

To verify your configuration is correct:

```python
from autopack.config import settings

print("SOT Memory Configuration:")
print(f"  Memory enabled: {settings.autopack_enable_sot_memory_indexing}")
print(f"  Retrieval enabled: {settings.autopack_sot_retrieval_enabled}")
print(f"  Max chars: {settings.autopack_sot_retrieval_max_chars}")
print(f"  Top-k: {settings.autopack_sot_retrieval_top_k}")
print(f"  Chunk size: {settings.autopack_sot_chunk_max_chars}")
```

## Testing

Run the test suite to verify everything works:

```bash
# Test stable entry_id generation
PYTHONUTF8=1 PYTHONPATH=src pytest tests/test_tidy_entry_id_stability.py -v

# Test SOT memory indexing
PYTHONUTF8=1 PYTHONPATH=src pytest tests/test_sot_memory_indexing.py -v
```

## Performance Considerations

### Indexing
- **When to index**: At executor startup, or after tidy consolidation updates SOT files
- **Cost**: One-time embedding cost per chunk (cached by content hash)
- **Idempotency**: Re-indexing same content produces same chunk IDs (no duplicates)

### Retrieval
- **Cost**: One embedding for query, plus vector search
- **Limits**: Strictly capped by `AUTOPACK_SOT_RETRIEVAL_MAX_CHARS` to prevent prompt bloat
- **Opt-in**: Only retrieved when `include_sot=True` in `retrieve_context()`

## Troubleshooting

### "SOT indexing skipped: sot_indexing_disabled"
**Solution**: Set `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`

### "SOT indexing skipped: docs_dir_not_found"
**Solution**: Ensure `docs/` directory exists in workspace with SOT files

### SOT results not appearing in retrieval
**Solution**: Check both flags:
- `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true` (for indexing)
- `AUTOPACK_SOT_RETRIEVAL_ENABLED=true` (for retrieval)
- Pass `include_sot=True` to `retrieve_context()`

### Re-indexing creates duplicates
**This shouldn't happen!** Chunk IDs are stable based on content hash. If you see duplicates:
1. Check that chunk content is truly identical
2. Verify `chunk_sot_file()` is using the same parameters
3. Report as a bug

## See Also

- [docs/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md](TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md) - Full implementation plan
- [scripts/tidy/README.md](../scripts/tidy/README.md) - Tidy system overview
- [src/autopack/memory/memory_service.py](../src/autopack/memory/memory_service.py) - MemoryService implementation
- [src/autopack/memory/sot_indexing.py](../src/autopack/memory/sot_indexing.py) - SOT chunking helpers
