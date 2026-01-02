# TIDY SOT Retrieval Integration Plan

**Status**: ✅ Completed and Superseded (BUILD-147 Phase A P11, 2026-01-01)

This integration plan has been fully implemented. All 8 planned components are operational with 26 passing tests.

## Quick Links
- **📁 Archived Plan**: [archive/superseded/plans/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md](../archive/superseded/plans/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md)
- **📖 Usage Guide**: [SOT_MEMORY_INTEGRATION_EXAMPLE.md](SOT_MEMORY_INTEGRATION_EXAMPLE.md)
- **✅ Completion Report**: [BUILD_HISTORY.md#build-147-phase-a-p11](BUILD_HISTORY.md#build-147-phase-a-p11)

## Why Archived?
The SOT runtime integration (indexing BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS into MemoryService) was completed in BUILD-147. The implementation plan served its purpose and has been archived as historical reference.

## Current Usage
For integration guidance and code examples, see [SOT_MEMORY_INTEGRATION_EXAMPLE.md](SOT_MEMORY_INTEGRATION_EXAMPLE.md).

## Implementation Status
- ✅ Stable entry ID generation (idempotent re-indexing)
- ✅ SOT chunking (1200 chars, 150 overlap)
- ✅ Opt-in indexing & retrieval flags
- ✅ Budget caps (4000 chars max, top-k=3)
- ✅ Multi-backend support (FAISS/Qdrant)
- ✅ 26/26 tests passing

## Architecture

The SOT retrieval system integrates with Autopack's memory layer:

```
┌─────────────────┐
│  SOT Ledgers    │
│  (docs/)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ SOT Chunking    │────▶│  MemoryService   │
│ (sot_indexing)  │     │  (index_sot_docs)│
└─────────────────┘     └────────┬─────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  Vector Store  │
                        │  (FAISS/Qdrant)│
                        └────────┬───────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │ retrieve_context│
                        │ (include_sot=T) │
                        └────────────────┘
```

### Key Design Principles

1. **Opt-In by Default**: SOT indexing and retrieval are disabled unless explicitly enabled
2. **Budget-Bounded**: Strict caps on chars retrieved (4000) and chunks (top-k=3)
3. **Idempotent**: Re-indexing same content produces identical chunk IDs (content-hash based)
4. **Multi-Project**: Supports multiple projects with isolated SOT namespaces

## Configuration

```bash
# Enable SOT indexing at startup
export AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true

# Enable SOT retrieval at runtime
export AUTOPACK_SOT_RETRIEVAL_ENABLED=true

# Optional: Adjust limits
export AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000
export AUTOPACK_SOT_RETRIEVAL_TOP_K=3
export AUTOPACK_SOT_CHUNK_MAX_CHARS=1200
export AUTOPACK_SOT_CHUNK_OVERLAP_CHARS=150
```

## Integration Points

1. **Startup**: `AutonomousExecutor._maybe_index_sot_docs()` (checks dirty marker, skips if docs unchanged)
2. **Runtime**: `memory.retrieve_context(..., include_sot=True)`
3. **Formatting**: `memory.format_retrieved_context(context, max_chars=...)`
4. **Re-indexing**: After tidy consolidation updates SOT files (automatic via dirty marker)

## See Also

- [SOT_MEMORY_INTEGRATION_EXAMPLE.md](SOT_MEMORY_INTEGRATION_EXAMPLE.md) - Code examples
- [scripts/tidy/README.md](../scripts/tidy/README.md) - Tidy system overview
- [src/autopack/memory/memory_service.py](../src/autopack/memory/memory_service.py) - Implementation
- [src/autopack/memory/sot_indexing.py](../src/autopack/memory/sot_indexing.py) - Chunking logic
- [tests/test_sot_memory_indexing.py](../tests/test_sot_memory_indexing.py) - Test suite
