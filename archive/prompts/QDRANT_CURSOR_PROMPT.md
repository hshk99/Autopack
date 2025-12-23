You are Cursor implementing a transition from FAISS to Qdrant (vector store) and standardizing DB on Postgres for Autopack. Follow these steps safely:

Scope
- Replace FAISS usage in MemoryService with Qdrant.
- Keep Postgres as the transactional DB (no SQLite defaults; only via explicit override).
- Do not change business logic beyond the vector backend swap.

Steps
1) Dependencies/config
- Add Qdrant client dependency (qdrant-client).
- Update `config/memory.yaml` to include:
  - use_qdrant: true
  - qdrant:
      host: localhost
      port: 6333
      api_key: ""  # if applicable
- Ensure Postgres remains default in `config.py`; leave SQLite only as an explicit override.

2) Qdrant adapter
- Create a QdrantStore adapter (similar interface to FAISS store) that supports:
  - ensure_collection(name, dim)
  - upsert(collection, points with payload)
  - search(collection, vector, filter by payload.project_id/run_id/phase_id)
  - optional delete/clear if needed.
- Collections: code_docs, run_summaries, errors_ci, doctor_hints, planning.
- Use HNSW with cosine or dot-product, payload filter on project_id and optionally run_id/phase_id.

3) MemoryService wiring
- In `MemoryService`, add `use_qdrant` config; when true, use QdrantStore instead of FAISS.
- Keep the FAISS path available but default to Qdrant when configured.
- Ensure embeddings generation is unchanged; only the storage backend swaps.

4) Migration/backfill (optional)
- Add a script or note to backfill existing FAISS indices into Qdrant (best-effort), or document that embeddings will be regenerated when accessed.

5) Tests
- Add tests for QdrantStore: collection creation, upsert/search with payload filter, round-trip.
- Add a MemoryService smoke test with use_qdrant=true (can be skipped if Qdrant not available; guard with env flag).

6) Docs
- Update README/memory docs to state: Postgres is primary DB; Qdrant is default vector backend; SQLite only via explicit override.

Safety
- Do not drop existing FAISS code; keep it behind a flag.
- Avoid touching .autonomous_runs or user data.
- If Qdrant is unavailable in CI, mark Qdrant integration tests as skipped with a clear reason.

Runbook (if you need to execute)
- Ensure Qdrant running locally (`docker run -p 6333:6333 qdrant/qdrant`).
- Set config/memory.yaml use_qdrant: true, host/port.
- Run tests with Qdrant available; otherwise, skip guarded tests.

