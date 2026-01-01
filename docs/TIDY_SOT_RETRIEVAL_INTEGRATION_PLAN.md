# Tidy → SOT → Retrieval Integration Plan (No Info Loss)

This plan implements the user’s core intention:

> **Tidy backlog → SOT ledgers → semantic indexing → Autopack/Cursor retrieves what it needs when needed**  
> (without dumping everything into `README.md`, and without deleting information—only moving/organizing).

It includes two improvements:

1) **Option A (runtime retrieval)**: Chunk + index the 3 SOT ledgers into Autopack `MemoryService` (Qdrant/FAISS), add `include_sot` retrieval with strict caps, opt-in via env flag.
2) **Tidy dedupe correctness**: Make `consolidate_docs_v2.py` generate **stable `entry_id`** (prefer explicit IDs like BUILD-146/DBG-078; else deterministic hash). This makes `db_sync.py` upserts truly idempotent across repeated tidy runs.

---

## Part 1 — Option A: Index SOT ledgers into MemoryService (Qdrant/FAISS)

### Goals
- Make SOT ledgers usable by Autopack at runtime via `MemoryService.retrieve_context()`.
- Keep retrieval **bounded** (no prompt bloat).
- Keep feature **opt-in** and safe by default.

### Non-goals
- Do not change the three canonical SOT ledgers’ filenames or locations.
- Do not require Qdrant; FAISS fallback must work.

---

### Proposed API / Behavior

#### New env flags
- `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true|false` (default: false)
- `AUTOPACK_SOT_RETRIEVAL_ENABLED=true|false` (default: false)  
  (separate from indexing so you can index offline but not use at runtime)
- `AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000` (default: 4000)
- `AUTOPACK_SOT_RETRIEVAL_TOP_K=3` (default: 3)
- `AUTOPACK_SOT_CHUNK_MAX_CHARS=1200` (default: 1200)
- `AUTOPACK_SOT_CHUNK_OVERLAP_CHARS=150` (default: 150)

#### New MemoryService collection
- `COLLECTION_SOT_DOCS = "sot_docs"`

#### Payload schema (suggested)
Each chunk point should include:
- `type`: `"sot"`
- `sot_file`: `"BUILD_HISTORY.md" | "DEBUG_LOG.md" | "ARCHITECTURE_DECISIONS.md"`
- `project_id`
- `source_path` (e.g., `docs/BUILD_HISTORY.md`)
- `chunk_id` (stable)
- `content_hash` (short hash)
- `heading` (best-effort)
- `created_at` or `timestamp` (best-effort parsed, else file mtime)
- `content_preview` (first ~500 chars)

#### Chunk id strategy (stable)
Use deterministic IDs so re-indexing upserts instead of duplicating:
- `sot:{project_id}:{sot_file}:{content_hash}:{chunk_index}`

---

### Files to change / add (skeleton)

#### 1) `src/autopack/memory/memory_service.py`
Add:
- `COLLECTION_SOT_DOCS`
- `index_sot_docs(project_id: str, workspace_root: Path) -> Dict[str, Any]`
- `search_sot(query: str, project_id: str, limit: Optional[int] = None) -> List[Dict]`
- Update `retrieve_context(...)` to accept `include_sot: bool = False`
  - If enabled, include top-k SOT chunk matches, then let `format_retrieved_context` cap output.

Skeleton:

```python
COLLECTION_SOT_DOCS = "sot_docs"

def index_sot_docs(self, project_id: str, workspace_root: Path) -> Dict[str, Any]:
    # if not enabled or env flag off → return {"indexed": 0, "skipped": True}
    # read the three files under workspace_root/docs/
    # chunk each file, embed each chunk, upsert with stable id

def search_sot(self, query: str, project_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    # embed query, store.search with filter {"project_id": project_id, "type": "sot"}

def retrieve_context(..., include_sot: bool = False, ...):
    # existing retrievals + optionally self.search_sot(...)
```

#### 2) `src/autopack/autonomous_executor.py`
Where `retrieve_context(...)` is called, add:
- `include_sot=os.getenv("AUTOPACK_SOT_RETRIEVAL_ENABLED", "0") in ("1","true","True")`

Optional enhancement:
- Index SOT docs once per run startup when enabled.

#### 3) New helper module (recommended)
Add:
- `src/autopack/memory/sot_indexing.py`

Responsibilities:
- chunking logic (with overlap)
- best-effort heading extraction
- stable chunk IDs

#### 4) Tests
Add tests with **no real embedding calls**:
- Patch `sync_embed_text` to return fixed vectors.
- Use FAISS backend in temp dir.

Suggested new test file:
- `tests/autopack/memory/test_sot_memory_indexing.py`

Test cases:
- Indexing is opt-in (no indexing when flag off).
- Indexing produces stable IDs (run twice → same point IDs).
- Retrieval respects caps (formatted output ≤ max chars).

---

## Part 2 — Stable entry_id + dedupe in tidy consolidation

### Current problem
`scripts/tidy/consolidate_docs_v2.py` generates synthetic IDs (`BUILD-###`, `DBG-###`, `DEC-###`) based on counters. Re-running tidy can produce new IDs for the same source material, defeating idempotence and causing duplicates in DB sync.

### Target behavior
For each extracted entry:
1) Prefer explicit IDs embedded in content (e.g., `BUILD-146`, `DBG-078`, `DECISION-012`).
2) Else derive a deterministic ID from:
   - normalized source path
   - normalized first heading (or filename stem)
   - extracted timestamp (or file mtime)
   - then hash to a compact suffix

Example:
- `BUILD-HASH-3f2a91c4`
- `DBG-HASH-a20f0d11`
- `DEC-HASH-9c01d2aa`

### Files to change / add (skeleton)

#### 1) `scripts/tidy/consolidate_docs_v2.py`
Add helper functions:
- `_extract_explicit_entry_id(content: str) -> Optional[str]`
- `_stable_entry_id(prefix: str, source_path: str, heading: str, timestamp: datetime) -> str`

Modify `_extract_entries(...)` to set `entry_id`:
- If explicit id found → use it (normalized).
- Else use stable hash id.

Pseudo:

```python
explicit = self._extract_explicit_entry_id(content)
if explicit:
    entry_id = explicit
else:
    heading = self._extract_title(file_path, content)
    entry_id = self._stable_entry_id("BUILD", str(file_path.relative_to(self.project_dir)), heading, timestamp)
```

#### 2) `scripts/tidy/db_sync.py`
Already uses:
- `UNIQUE(project_id, file_type, entry_id)` and `ON CONFLICT (...) DO UPDATE`

After stable IDs land, repeated sync runs become idempotent.

#### 3) Tests
Add unit tests for:
- explicit ID extraction
- stable hash determinism
- “same file, same heading, same timestamp” → same entry_id

Suggested test file:
- `tests/test_tidy_entry_id_stability.py`

---

## Rollout / Safety

### Step 1 (safe, no runtime behavior change)
Implement stable entry IDs in tidy + tests.

### Step 2 (opt-in runtime enhancement)
Implement SOT indexing into MemoryService behind env flags.

### Step 3 (operator workflow)
Update smoke test to report:
- whether SOT indexing is enabled
- whether SOT docs are indexed (count)

---

## Acceptance Criteria

- Re-running tidy does not create duplicate logical entries in SOT DB sync (stable IDs).
- SOT docs can be indexed into MemoryService (Qdrant/FAISS).
- Autopack can retrieve SOT context via `include_sot` when enabled.
- Retrieval is bounded (max chars) and safe by default (opt-in).


