# Improvements Plan: SOT Runtime Wiring + 6-File SOT Coverage + Model-Intel Ops

Audience: **implementation cursor (cheaper model)**  
Goal: close remaining gaps vs `README.md` “ideal state”, plus high-leverage robustness/ops improvements.

This plan is intentionally explicit to prevent drift. Follow it step-by-step, keep changes small, and add/adjust tests alongside code.

---

## North-star requirements (do not violate)

- **Opt-in only**: all new behavior must remain disabled by default.
- **Bounded outputs**: keep strict caps on prompt/context bloat.
- **Idempotent**: re-indexing should not create duplicates nor explode cost.
- **Multi-project correct**: must work for repo-root project *and* sub-projects under `.autonomous_runs/<project>/...`.
- **No info deletion**: indexing/retrieval is additive; don’t delete or rewrite SOT content.
- **Windows-safe**: normalize line endings where relevant, avoid path bugs.

---

## Current observed gaps (from code review)

### Gap A — SOT retrieval is not actually used by the executor
`MemoryService.retrieve_context()` supports `include_sot`, but `src/autopack/autonomous_executor.py` never passes it in the primary code paths, so SOT retrieval never appears in prompts even when env flags are set.

### Gap B — SOT indexing targets only 3 ledgers, while README defines 6-file SOT
Current indexing covers only:
- `BUILD_HISTORY.md`
- `DEBUG_LOG.md`
- `ARCHITECTURE_DECISIONS.md`

README standard SOT set is 6:
- `PROJECT_INDEX.json`
- `BUILD_HISTORY.md`
- `DEBUG_LOG.md`
- `ARCHITECTURE_DECISIONS.md`
- `FUTURE_PLAN.md`
- `LEARNED_RULES.json`

### Gap C — Multi-project docs directory ambiguity
`index_sot_docs(project_id, workspace_root)` assumes `workspace_root/docs`. Sub-project SOT lives under `.autonomous_runs/<project>/docs/`. We must ensure correct docs root resolution.

### Gap D — Re-index cost / robustness
Stable IDs help, but we should avoid re-embedding unchanged chunks if possible, and normalize line endings to avoid Windows `\r\n` churn affecting chunk hashes.

### Gap E — Operator visibility
There’s no single “is SOT indexing active, how many chunks indexed, when?” surface for operators (dashboard/smoke test).

### Gap F — Model Intelligence: “no stale model strings” enforcement & freshness loop
Plan requires an audit guardrail; also operational refresh for pricing/benchmarks/sentiment should be easy and safe.

---

## Part 1 — Wire SOT retrieval into the executor (lowest-risk, highest impact)

### 1.1 Requirements
- Executor should include SOT chunks in retrieval **only when**:
  - vector memory is enabled, and
  - SOT retrieval flag is enabled.
- Must remain safe/bounded: SOT section already has `AUTOPACK_SOT_RETRIEVAL_MAX_CHARS`.

### 1.2 Files
- `src/autopack/autonomous_executor.py`

### 1.3 Implementation steps
1) Locate every call to `self.memory_service.retrieve_context(...)` (there are several).
2) Add `include_sot=...` argument, driven by `settings.autopack_sot_retrieval_enabled` (or direct env parse, but prefer settings).

**Skeleton (apply to all relevant retrieve_context calls):**

```python
from autopack.config import settings

retrieved = self.memory_service.retrieve_context(
    query=query,
    project_id=project_id,
    run_id=self.run_id,
    include_code=True,
    include_summaries=True,
    include_errors=True,
    include_hints=True,
    include_planning=True,
    include_plan_changes=True,
    include_decisions=True,
    include_sot=bool(settings.autopack_sot_retrieval_enabled),
)
```

### 1.4 Acceptance criteria
- With defaults, behavior unchanged (no SOT retrieval).
- With `AUTOPACK_SOT_RETRIEVAL_ENABLED=true`, the formatted retrieved context includes a **“Relevant Documentation (SOT)”** section (when indexed).

### 1.5 Tests
If there are existing executor tests around context injection, extend them. If not, add a focused unit test that mocks `MemoryService.retrieve_context` and asserts `include_sot` is passed when enabled.

Prefer mocking to avoid embedding calls.

---

## Part 2 — Index SOT docs at startup (optional but recommended)

### 2.1 Requirements
- Indexing should happen once per run startup **only when**:
  - memory enabled, and
  - `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`.
- Indexing failures must not crash runs; log warnings.

### 2.2 Files
- `src/autopack/autonomous_executor.py`

### 2.3 Implementation steps
1) Find executor initialization where `self.memory_service` is created.
2) Add a private helper `self._maybe_index_sot_docs()` invoked once at startup.
3) Ensure it uses correct `docs_dir` resolution (see Part 3).

**Skeleton:**

```python
def _maybe_index_sot_docs(self) -> None:
    if not self.memory_service or not self.memory_service.enabled:
        return
    from autopack.config import settings
    if not settings.autopack_enable_sot_memory_indexing:
        return
    try:
        project_id = self._get_project_slug() or self.run_id
        docs_dir = self._resolve_project_docs_dir(project_id=project_id)
        result = self.memory_service.index_sot_docs(
            project_id=project_id,
            workspace_root=Path(self.workspace),
            docs_dir=docs_dir,  # new param added in Part 3
        )
        logger.info(f"[Executor] SOT indexing: {result}")
    except Exception as e:
        logger.warning(f"[Executor] SOT indexing failed: {e}")
```

### 2.4 Acceptance criteria
- Indexing occurs only when enabled.
- Logs show indexed chunk count and docs_dir used.

---

## Part 3 — Make SOT indexing multi-project correct (docs_dir resolution)

### 3.1 Requirements
- Support indexing for:
  - repo root docs (`<repo>/docs`)
  - sub-project docs (`<repo>/.autonomous_runs/<project>/docs`)
- Must not guess incorrectly; allow explicit override.

### 3.2 Proposed API change (low-risk)
Update `MemoryService.index_sot_docs` signature to accept optional `docs_dir`.

#### Files
- `src/autopack/memory/memory_service.py`
- possibly new helper `src/autopack/projects.py` (optional) or add a small resolver method in executor only.

#### Skeleton

```python
def index_sot_docs(self, project_id: str, workspace_root: Path, docs_dir: Optional[Path] = None) -> Dict[str, Any]:
    docs_dir = docs_dir or (workspace_root / "docs")
    ...
```

### 3.3 Docs dir resolution strategy (recommended)

Implement a resolver in the executor:

- If `project_id == "autopack"` (or matches current repo project), use `<workspace>/docs`.
- Else if `<workspace>/.autonomous_runs/<project_id>/docs` exists, use it.
- Else fallback to `<workspace>/docs` but log a warning.

**Skeleton:**

```python
def _resolve_project_docs_dir(self, project_id: str) -> Path:
    ws = Path(self.workspace)
    candidate = ws / ".autonomous_runs" / project_id / "docs"
    if candidate.exists():
        return candidate
    return ws / "docs"
```

If there is already a canonical project configuration resolver in tidy tooling, consider reusing it; but keep dependencies light.

### 3.4 Acceptance criteria
- Can index SOT for both root project and a sub-project when pointed at the correct `project_id`.

### 3.5 Tests
Add unit tests for docs_dir selection:
- When override passed, it is used.
- When override absent, correct default is used.

Use temp directories with small fake docs files to avoid huge I/O.

---

## Part 4 — Expand SOT indexing from 3 files → 6 files (with JSON-safe handling)

### 4.1 Requirements
- Index all 6 canonical SOT files.
- For JSON (`PROJECT_INDEX.json`, `LEARNED_RULES.json`):
  - do **field-selective embedding** to avoid indexing noisy/large blobs.
  - include metadata to identify source + key path.
- Keep stable IDs and idempotency.

### 4.2 Files
- `src/autopack/memory/memory_service.py`
- `src/autopack/memory/sot_indexing.py`

### 4.3 Implementation steps

#### 4.3.1 Update file list
In `MemoryService.index_sot_docs`, extend `sot_files` to include:
- `FUTURE_PLAN.md`
- `PROJECT_INDEX.json`
- `LEARNED_RULES.json`

#### 4.3.2 Extend `sot_indexing.py` for JSON
Add new helpers:
- `chunk_sot_json(file_path, project_id, max_chars, overlap_chars) -> List[Dict]`
- `json_to_embedding_text(obj) -> List[Tuple[str, str]]` returning `(key_path, text)` items

**Recommended JSON fields (keep small and high-signal):**
- `PROJECT_INDEX.json`: `project_name`, `setup`, `commands`, `structure`, `entrypoints`, `dependencies`, `api` summaries.
- `LEARNED_RULES.json`: each rule `id/title`, `rule`, `when`, `because`, `examples` (truncate).

**Stable IDs for JSON chunks**
Use a deterministic ID incorporating:
- file name
- key path
- content hash

Example:
`sot:autopack:PROJECT_INDEX.json:setup.commands:<hash>`

#### 4.3.3 Normalize line endings before hashing (Windows)
In `chunk_sot_file`:
- normalize `content = content.replace("\r\n", "\n")` before chunking/hashing.
This reduces churn in chunk IDs across OS.

### 4.4 Acceptance criteria
- Indexing logs indicate each of the 6 files is handled.
- Retrieval returns matches from `FUTURE_PLAN.md` and JSON SOT sources for relevant queries.

### 4.5 Tests
Extend `tests/test_sot_memory_indexing.py` (or create if missing) to cover:
- 6-file indexing list
- JSON handling: stable IDs, metadata includes `json_key_path`, retrieval returns expected payload fields.

Mock embeddings.

---

## Part 5 — Reduce re-index costs (skip unchanged chunks)

### 5.1 Requirements
- Re-indexing should avoid embedding calls for chunks already present in the vector store when feasible.
- Must work for both Qdrant and FAISS backends (or degrade gracefully).

### 5.2 Design options (pick one; keep it simple)

#### Option 1 (recommended): store-side “exists” check by point id
Add store capability `has_point(collection, point_id) -> bool` (or `get_payload` returning None).

Flow:
- For each chunk id:
  - if point exists: skip embedding + upsert
  - else: embed + upsert

If backend lacks efficient exists check, fallback to current behavior.

#### Option 2: local embedding cache keyed by chunk_id/content_hash
If an embedding cache exists already, ensure SOT chunk embedding uses it; if not, add a tiny on-disk cache.

### 5.3 Acceptance criteria
- Re-indexing an unchanged docs set does not perform N embedding calls (verify via logs/counters in tests).

### 5.4 Tests
Mock store `get_payload` / `has_point` and assert `sync_embed_text` is not called for existing points.

---

## Part 6 — Chunking quality improvements (avoid pathological splits)

### 6.1 Improvements
- Sentence boundary split currently only looks for `'. '`. Improve to also consider:
  - `\n\n` paragraph breaks
  - `? ` / `! `
  - markdown headings (`\n#`)
- Ensure overlap never causes infinite loops (already guarded, keep it).

### 6.2 Acceptance criteria
- Chunking test includes a markdown doc with headings and verifies chunks align near headings/paragraphs.

---

## Part 7 — Operator visibility

### 7.1 Requirements
Expose:
- whether SOT indexing is enabled
- whether retrieval is enabled
- last indexing attempt outcome
- count of indexed SOT chunks (best-effort)

### 7.2 Implementation options

#### Option A: add to dashboard status endpoint payload
If there is a `GET /dashboard/status`, add fields:
- `sot.indexing_enabled`
- `sot.retrieval_enabled`
- `sot.last_indexed_chunks`
- `sot.last_indexed_at`

This requires storing runtime state somewhere (in executor object / in a small JSON state file under `.autonomous_runs/<run>/`).

#### Option B (simpler): log + smoke test output
Update existing smoke test script to print SOT flags and indexing summary if available.

Pick the minimal option that fits current architecture.

### 7.3 Acceptance criteria
Operators can quickly confirm whether SOT is active and how many chunks were indexed without reading code.

---

## Part 8 — Model Intelligence System: enforcement + freshness workflows

### 8.1 Enforce “no stale model strings” (guardrail)

#### Requirements
- Add a CI-checkable command that fails if forbidden model IDs appear in `src/` (or specific globs).
- Must support allowlists for docs/comments if needed.

#### Implementation
If `scripts/model_audit.py` exists, use it; otherwise implement it.

Add a doc section and optionally a lightweight CI config or test that runs:

```bash
python scripts/model_audit.py --glob "src/**/*.py" --fail-on "glm-4.6"
```

Do **not** fail on markdown/docs by default.

#### Acceptance criteria
- When a deprecated model string is reintroduced in code, CI fails fast with a clear message.

### 8.2 Data freshness workflow (safe-by-default)

#### Requirements
- Easy to refresh:
  - catalog/pricing
  - benchmarks
  - runtime stats window
  - sentiment signals (optional)
- Provide “report deltas” since last run.

#### Implementation ideas
- Extend `scripts/model_intel.py` with:
  - `refresh-all --window-days 30` (runs ingest + stats + recommend for common use cases)
  - `report --since <timestamp|id>` or `report --diff-latest`
- Ensure all DB mutations still require explicit `DATABASE_URL`.

#### Acceptance criteria
- One command updates the system predictably; operators can see what changed and why.

---

## Final validation checklist (must do)

### SOT runtime
- Default env (all flags false): no behavior change.
- Enable indexing + retrieval:
  - SOT indexed once at startup (if you implemented startup indexing)
  - executor retrieval includes SOT section
- Multi-project:
  - index + retrieve for a sub-project docs dir (temp fixture ok)
- Re-index unchanged docs:
  - does not re-embed unchanged chunks (if Part 5 implemented)

### Model intelligence
- Audit command works and fails on forbidden models in `src/`.
- Refresh workflow is documented and bounded.

---

## Notes / places cheaper cursor is likely to stray (watch these)

- **Do not** enable SOT retrieval by default; keep opt-in.
- **Do not** index raw full JSON blobs; do field-selective embedding.
- **Do not** assume `workspace_root/docs` is always correct; sub-projects differ.
- **Do not** remove/rename SOT files; only index additional ones.
- **Do not** add heavy dependencies to solve simple problems; keep it minimal.


