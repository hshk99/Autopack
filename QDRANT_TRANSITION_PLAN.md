## Qdrant Transition Plan (Replace FAISS; Keep Postgres)

Goal
- Swap FAISS vector memory to Qdrant as the vector store.
- Standardize transactional DB on Postgres (no SQLite in defaults; SQLite only via explicit override).

Scope
- Vector: Qdrant only (replace FAISS usage in MemoryService / embeddings storage). FAISS remains behind a feature flag for offline/dev.
- Transactional: Postgres only as default `database_url`; SQLite allowed only via explicit override (documented).

Implementation Tasks
1) Dependencies
- Add `qdrant-client`.

2) Configuration
- `config/memory.yaml`: add `use_qdrant: true` and `qdrant:` block (host, port, api_key). Default to use_qdrant=true.
- Ensure `config.py`/defaults keep Postgres as the transactional DB; remove SQLite as a default (allow only via explicit env override).

3) Qdrant adapter
- Implement `QdrantStore` with:
  - `ensure_collection(name, dim)`
  - `upsert(collection, points with payload)`
  - `search(collection, vector, filter by payload.project_id and optional run_id/phase_id)`
  - optional delete/clear
- Use HNSW cosine or dot-product; payload filters on project_id (and run_id/phase_id as needed).
- Collections: code_docs, run_summaries, errors_ci, doctor_hints, planning.

4) MemoryService wiring
- Add `use_qdrant` flag; when true, use QdrantStore. Default to Qdrant. Keep FAISS path behind a flag for offline/dev.

5) Migration/backfill (optional)
- Provide a helper to backfill FAISS → Qdrant, or document that embeddings will regenerate on demand.

6) Tests
- QdrantStore tests: collection creation, upsert/search with payload filter, round-trip.
- MemoryService smoke test with use_qdrant=true (skip if Qdrant not available; guard with env).

7) Docs
- Update README/memory docs: Postgres = primary DB; Qdrant = default vector backend; SQLite only via explicit override. Add quick note for running Qdrant locally (e.g., docker -p 6333:6333).

8) Safety/ops
- Do not delete FAISS code; leave it gated.
- Avoid touching `.autonomous_runs` artifacts.
- If Qdrant isn’t running in CI, skip integration tests with clear reason.

Prompt
- See `QDRANT_CURSOR_PROMPT.md` for the Cursor implementation prompt; it should not restate this file, only reference it.

