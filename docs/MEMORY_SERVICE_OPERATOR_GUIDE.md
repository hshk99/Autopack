# Memory Service Production Operator Guide

**Version**: 1.0
**Last Updated**: 2026-01-13
**Audience**: Production operators, SREs, DevOps engineers

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Setup](#setup)
4. [Operations](#operations)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Performance Tuning](#performance-tuning)
8. [Maintenance](#maintenance)
9. [Security](#security)
10. [Reference](#reference)

---

## Overview

### What is the Memory Service?

The Autopack Memory Service provides **vector-based semantic memory** for autonomous execution. It enables the system to:

- **Learn from past phases**: Store and retrieve phase summaries, CI results, and execution outcomes
- **Maintain decision context**: Track planning artifacts, architectural decisions, and design rationale
- **Provide error insights**: Index CI failures, test errors, and doctor recommendations for future reference
- **Reuse domain knowledge**: Index Source of Truth (SOT) documentation for runtime retrieval
- **Support code awareness**: Embed workspace files for semantic code search

### Why It's Important

The memory service transforms Autopack from a stateless executor into a **learning system**:

- **Reduces repeated mistakes**: Retrieves past errors and their solutions
- **Improves decision quality**: Provides historical context for planning and execution
- **Accelerates debugging**: Finds similar past failures and their resolutions
- **Enables knowledge reuse**: Surfaces relevant SOT documentation during execution
- **Supports goal drift detection**: Compares current plans against historical decisions

**Without memory**: Each phase starts from scratch, repeating past failures
**With memory**: System learns continuously, improving over time

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Memory Service API                        │
│  (memory_service.py - High-level interface)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Embedding Layer                           │
│  (embeddings.py - OpenAI + Local fallback)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────┬──────────────────────────────────────┐
│   Qdrant Store       │       FAISS Store                    │
│   (Production)       │       (Dev/Fallback)                 │
│   qdrant_store.py    │       faiss_store.py                 │
└──────────────────────┴──────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Vector Storage                            │
│  Qdrant: Distributed vector DB (Docker/Cloud)               │
│  FAISS: In-memory/disk index (local)                        │
└─────────────────────────────────────────────────────────────┘
```

### Dual Backend Strategy

| Feature | Qdrant (Production) | FAISS (Fallback) |
|---------|---------------------|------------------|
| **Infrastructure** | Docker container or Cloud | In-process library |
| **Deployment** | Distributed, scalable | Single-process |
| **Persistence** | Disk-backed, durable | File-based snapshots |
| **Performance** | HNSW indexing, fast | Cosine similarity, moderate |
| **Use Case** | Production, multi-tenant | Development, offline |
| **Availability** | Requires Docker/Cloud | Always available |

**Automatic Fallback**: If Qdrant fails to start or becomes unavailable, the system **automatically falls back to FAISS** (if `fallback_to_faiss: true`).

### Data Collections

The memory service manages **7 core collections** per project:

| Collection | Purpose | TTL | Example Query |
|------------|---------|-----|---------------|
| `code_docs` | Workspace file embeddings | 90 days | "Find files handling authentication" |
| `run_summaries` | Per-phase execution summaries | 30 days | "What changed in phase 3?" |
| `errors_ci` | CI/test failure snippets | 14 days | "Similar test failures" |
| `doctor_hints` | Doctor recommendations | 30 days | "Past linting fixes" |
| `planning` | Planning artifacts & decisions | 30 days | "Why did we choose Postgres?" |
| `sot_docs` | Source of Truth documentation | 30 days | "Deployment procedures" |
| Custom planning | Per-plan artifacts (optional) | Variable | Project-specific context |

**Payload Examples**:

```python
# code_docs
{
    "type": "code",
    "path": "src/autopack/api/routes/dashboard.py",
    "content_hash": "a3f2e9...",
    "content_preview": "FastAPI dashboard endpoints...",
    "project_id": "my-project",
    "run_id": "run-123"
}

# run_summaries
{
    "type": "summary",
    "summary": "Added authentication middleware",
    "changes": "Modified 3 files, added JWT validation",
    "ci_result": "PASS",
    "phase_id": "phase-5",
    "task_type": "implementation"
}

# errors_ci
{
    "type": "error",
    "error_text": "AssertionError: Expected 200, got 401",
    "error_type": "test_failure",
    "test_name": "test_dashboard_auth",
    "phase_id": "phase-5"
}
```

### Vector Embeddings

**Embedding Pipeline**:

1. **Primary (OpenAI)**: `text-embedding-3-small` model (1536 dimensions)
   - Requires: `USE_OPENAI_EMBEDDINGS=true` + `OPENAI_API_KEY`
   - Cost: ~$0.02 per 1M tokens
   - Quality: High semantic accuracy

2. **Fallback (Deterministic)**: SHA256-based embedding
   - No API key required
   - Zero cost, fully offline
   - Quality: Moderate (content-hash based)

**Auto-selection Logic**:
- If OpenAI API key present → Use OpenAI
- If API key missing or rate-limited → Use fallback
- No configuration required (automatic)

**Input Limits**:
- Max chars per embedding: 30,000 (safe for 8191 token limit)
- Batch embedding supported via `sync_embed_texts()`

### Retrieval Methods

**Single-collection searches**:
```python
search_code(query, project_id, limit=5)
search_summaries(query, project_id, run_id, limit=5)
search_errors(query, project_id, limit=5)
search_doctor_hints(query, project_id, limit=5)
search_sot(query, project_id, limit=3)
search_planning(query, project_id, limit=5, types=["decision_log"])
```

**Multi-collection retrieval** (recommended):
```python
retrieve_context(
    query="How do we handle auth errors?",
    project_id="my-project",
    run_id="run-123",
    task_type="debugging",
    include_code=True,
    include_summaries=True,
    include_errors=True,
    include_hints=True,
    include_sot=True  # Budget-aware
)
```

**Result Format**:
```python
{
    "id": "uuid-or-deterministic-id",
    "score": 0.85,  # Cosine similarity [0,1], higher = better
    "payload": { ... }  # Type-specific fields
}
```

### SOT Memory Integration

**What is SOT?**

Source of Truth (SOT) documents are **append-only ledgers** that capture:
- `BUILD_HISTORY.md`: What changed and what was verified
- `DEBUG_LOG.md`: Failures → root cause → fix → verification
- `ARCHITECTURE_DECISIONS.md`: Durable rationale ("why")
- `LEARNED_RULES.json`: Project-specific rules and constraints
- `PROJECT_INDEX.json`: Project structure and metadata

**Indexing Strategy**:
- Markdown files chunked into 1200-char segments (150-char overlap)
- JSON files have field-selective extraction
- Stable chunk IDs (content-hash based, idempotent)
- Metadata: heading, timestamp, chunk_index

**Budget-Aware Retrieval**:
- SOT retrieval gated by `AUTOPACK_SOT_RETRIEVAL_ENABLED`
- Character limits enforced: default 4000 chars max
- Top-K limiting: default 3 chunks per query
- Prevents prompt bloat during autonomous execution

**Indexing Trigger**:
```python
# At startup (if enabled)
if AUTOPACK_ENABLE_SOT_MEMORY_INDEXING:
    memory.index_sot_docs(project_id, workspace_root, docs_dir)
```

---

## Setup

### Prerequisites

**Required**:
- Python 3.10+
- Docker (for Qdrant backend)
- 4GB RAM minimum (8GB recommended for Qdrant)

**Optional**:
- OpenAI API key (for high-quality embeddings)
- Qdrant Cloud account (for managed hosting)

### Installation

#### 1. Local Qdrant (Recommended for Production)

**Using Docker Compose** (preferred):

```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:v1.12.5
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    restart: unless-stopped
```

Start Qdrant:
```bash
docker compose up -d qdrant
```

**Using Docker Run** (alternative):
```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:v1.12.5
```

**Verify Qdrant is running**:
```bash
curl http://localhost:6333/health
# Expected: {"status": "ok"}
```

#### 2. Qdrant Cloud (Managed Option)

1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a cluster and obtain API key
3. Set environment variables:
```bash
export AUTOPACK_QDRANT_HOST="your-cluster.qdrant.io"
export AUTOPACK_QDRANT_PORT=6333
export AUTOPACK_QDRANT_API_KEY="your-api-key"
export AUTOPACK_USE_QDRANT=true
```

#### 3. FAISS Fallback (Development/Offline)

No installation required! FAISS is included with Autopack dependencies.

**Enable FAISS-only mode**:
```bash
export AUTOPACK_USE_QDRANT=false
export AUTOPACK_ENABLE_MEMORY=true
```

### Configuration

**Primary config file**: `config/memory.yaml`

```yaml
enable_memory: true
use_qdrant: true

qdrant:
  host: localhost
  port: 6333
  prefer_grpc: false
  timeout: 60
  autostart: true  # Auto-launch Docker on startup
  autostart_timeout_seconds: 15
  fallback_to_faiss: true  # Graceful degradation
  require: false  # Continue execution if unavailable

faiss_index_path: ".autonomous_runs/{project_id}/.faiss"
```

### Environment Variables

**Master Controls**:
```bash
# Enable/disable memory service entirely
export AUTOPACK_ENABLE_MEMORY=true

# Backend selection (true = Qdrant, false = FAISS)
export AUTOPACK_USE_QDRANT=true
```

**Qdrant Configuration**:
```bash
# Connection
export AUTOPACK_QDRANT_HOST=localhost
export AUTOPACK_QDRANT_PORT=6333
export AUTOPACK_QDRANT_API_KEY=""  # Optional, for Cloud
export AUTOPACK_QDRANT_PREFER_GRPC=false
export AUTOPACK_QDRANT_TIMEOUT=60

# Autostart behavior
export AUTOPACK_QDRANT_AUTOSTART=true
export AUTOPACK_QDRANT_AUTOSTART_TIMEOUT=15
export AUTOPACK_QDRANT_IMAGE=qdrant/qdrant:v1.12.5
```

**SOT Memory Features**:
```bash
# Index SOT docs at startup
export AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true

# Enable SOT retrieval during execution
export AUTOPACK_SOT_RETRIEVAL_ENABLED=true

# Budget controls
export AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000
export AUTOPACK_SOT_RETRIEVAL_TOP_K=3

# Chunking parameters
export AUTOPACK_SOT_CHUNK_MAX_CHARS=1200
export AUTOPACK_SOT_CHUNK_OVERLAP_CHARS=150
```

**Embedding Configuration**:
```bash
# Enable OpenAI embeddings (optional)
export USE_OPENAI_EMBEDDINGS=true
export OPENAI_API_KEY=sk-...
```

### First-Time Setup Checklist

- [ ] Docker installed and running
- [ ] Qdrant container started (`docker compose up -d qdrant`)
- [ ] Health check passes (`curl http://localhost:6333/health`)
- [ ] Environment variables set (at minimum `AUTOPACK_ENABLE_MEMORY=true`)
- [ ] Configuration file reviewed (`config/memory.yaml`)
- [ ] OpenAI API key set (if using embeddings)
- [ ] Test write operation (see [Operations](#operations))

---

## Operations

### Starting the Memory Service

**Automatic Startup** (recommended):

The memory service initializes automatically when Autopack starts, if:
1. `AUTOPACK_ENABLE_MEMORY=true`
2. `AUTOPACK_QDRANT_AUTOSTART=true` (default)

**What happens during autostart**:
1. Check if Qdrant is reachable at `host:port`
2. If not, attempt `docker compose up -d qdrant`
3. Wait up to 15 seconds for readiness
4. If fails and `fallback_to_faiss: true`, use FAISS
5. If fails and `require: false`, continue without memory

**Manual Startup**:

```bash
# Start Qdrant
docker compose up -d qdrant

# Verify health
curl http://localhost:6333/health

# Start Autopack (memory service auto-initializes)
PYTHONPATH=src python -m uvicorn autopack.main:app --host 0.0.0.0 --port 8000
```

### Stopping the Memory Service

**Graceful Shutdown**:

```bash
# Stop Autopack (memory service shuts down cleanly)
^C  # Ctrl+C on running process

# Stop Qdrant (optional)
docker compose stop qdrant
```

**Force Shutdown** (if needed):

```bash
# Kill Qdrant container
docker compose down qdrant

# Or directly
docker stop qdrant
docker rm qdrant
```

**Note**: Qdrant persists data to disk (`qdrant_storage/`), so stopping the container is safe.

### Health Checks

**Qdrant Health Check**:

```bash
# HTTP endpoint
curl http://localhost:6333/health
# Expected: {"status": "ok"}

# Check collections
curl http://localhost:6333/collections
# Expected: {"result": {"collections": [...]}}

# Docker container health
docker ps | grep qdrant
# Expected: "Up" status
```

**Memory Service Health Check**:

```python
from autopack.memory import MemoryService

memory = MemoryService(project_id="test-project")

# Test write
memory.write_phase_summary(
    run_id="test-run",
    phase_id="test-phase",
    project_id="test-project",
    summary="Health check test",
    changes="None",
    ci_result="N/A"
)

# Test read
results = memory.search_summaries(
    query="health check",
    project_id="test-project",
    limit=1
)

assert len(results) > 0, "Memory service not working!"
print("✓ Memory service healthy")
```

**Autostart Verification**:

Check Autopack startup logs for:
```
[INFO] Memory service enabled
[INFO] Attempting Qdrant autostart via docker compose...
[INFO] Qdrant started successfully in 3.2 seconds
[INFO] Memory service initialized with QdrantStore
```

Or (if fallback):
```
[WARNING] Qdrant unavailable, falling back to FAISS
[INFO] Memory service initialized with FAISSStore
```

### Monitoring

**Key Metrics**:

1. **Qdrant Container**:
   - CPU/Memory usage: `docker stats qdrant`
   - Disk usage: `du -sh ./qdrant_storage`
   - Collection count: `curl http://localhost:6333/collections`

2. **Memory Service**:
   - Embedding latency (logs)
   - Search latency (logs)
   - Fallback events (warnings in logs)

3. **Collection Stats**:

```python
from autopack.memory.qdrant_store import QdrantStore

store = QdrantStore()
collections = store.client.get_collections().collections

for coll in collections:
    info = store.client.get_collection(coll.name)
    print(f"{coll.name}: {info.points_count} points")
```

**Prometheus Metrics** (if enabled):

Qdrant exposes metrics at `http://localhost:6333/metrics`:
- `qdrant_search_requests_total`
- `qdrant_upsert_requests_total`
- `qdrant_search_duration_seconds`

**Log Locations**:

- Qdrant logs: `docker logs qdrant`
- Autopack logs: `stdout` or configured log file
- Memory service logs: Search for `[memory]` tag

### Backup and Restore

**Qdrant Snapshots**:

```bash
# Create snapshot (via API)
curl -X POST "http://localhost:6333/collections/run_summaries/snapshots"
# Returns: {"result": {"name": "run_summaries-2026-01-13.snapshot"}}

# Download snapshot
curl "http://localhost:6333/collections/run_summaries/snapshots/run_summaries-2026-01-13.snapshot" \
  -o backup.snapshot

# Restore snapshot (requires collection creation first)
curl -X PUT "http://localhost:6333/collections/run_summaries/snapshots/upload" \
  -F "snapshot=@backup.snapshot"
```

**Full Qdrant Backup** (filesystem):

```bash
# Stop Qdrant
docker compose stop qdrant

# Backup storage directory
tar -czf qdrant_backup_$(date +%Y%m%d).tar.gz ./qdrant_storage

# Restart Qdrant
docker compose start qdrant
```

**Restore from Backup**:

```bash
# Stop Qdrant
docker compose stop qdrant

# Restore storage directory
rm -rf ./qdrant_storage
tar -xzf qdrant_backup_YYYYMMDD.tar.gz

# Restart Qdrant
docker compose start qdrant
```

**FAISS Backup**:

```bash
# FAISS stores indices as files in .autonomous_runs/{project_id}/.faiss
cp -r .autonomous_runs/my-project/.faiss /backup/location/
```

---

## Troubleshooting

### Common Issues

#### 1. Qdrant Container Won't Start

**Symptoms**:
- `docker compose up -d qdrant` fails
- Logs show port conflict or permission errors

**Diagnosis**:
```bash
# Check if port 6333 is already in use
lsof -i :6333  # macOS/Linux
netstat -ano | findstr :6333  # Windows

# Check Docker logs
docker logs qdrant
```

**Solutions**:

**Port conflict**:
```bash
# Option A: Stop conflicting service
kill <PID>

# Option B: Change Qdrant port
# In docker-compose.yml:
ports:
  - "6334:6333"  # Map host 6334 -> container 6333

# Update config
export AUTOPACK_QDRANT_PORT=6334
```

**Permission errors**:
```bash
# Fix volume permissions
sudo chown -R $(whoami) ./qdrant_storage

# Or run with sudo (not recommended)
sudo docker compose up -d qdrant
```

**Docker not running**:
```bash
# Start Docker daemon
# macOS: Open Docker Desktop
# Linux: sudo systemctl start docker
```

#### 2. Memory Service Falls Back to FAISS Unexpectedly

**Symptoms**:
- Logs show: `Falling back to FAISS`
- Qdrant appears to be running

**Diagnosis**:
```bash
# Check Qdrant health
curl http://localhost:6333/health

# Check Qdrant logs
docker logs qdrant | tail -n 50

# Verify network connectivity
ping localhost
telnet localhost 6333
```

**Solutions**:

**Qdrant not fully initialized**:
- Wait 5-10 seconds after `docker compose up`
- Increase `autostart_timeout_seconds` in config

**Firewall blocking**:
```bash
# Linux: Allow port 6333
sudo ufw allow 6333

# macOS: Check Firewall settings
```

**Wrong host/port configuration**:
```bash
# Verify environment variables
echo $AUTOPACK_QDRANT_HOST  # Should be "localhost"
echo $AUTOPACK_QDRANT_PORT  # Should be "6333"
```

#### 3. Embeddings Failing (OpenAI)

**Symptoms**:
- Logs show: `OpenAI API error`
- Fallback to deterministic embeddings

**Diagnosis**:
```bash
# Check API key
echo $OPENAI_API_KEY
echo $USE_OPENAI_EMBEDDINGS

# Test API directly
curl https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "text-embedding-3-small"}'
```

**Solutions**:

**Invalid API key**:
```bash
export OPENAI_API_KEY=sk-...  # Correct format
```

**Rate limit exceeded**:
- Wait and retry (exponential backoff in code)
- Upgrade OpenAI plan

**Network issues**:
- Check proxy settings
- Verify outbound HTTPS allowed

**Want deterministic embeddings**:
```bash
# Disable OpenAI embeddings (use free fallback)
export USE_OPENAI_EMBEDDINGS=false
```

#### 4. Search Returns No Results

**Symptoms**:
- `search_*()` returns empty list
- Data was written successfully

**Diagnosis**:

```python
from autopack.memory import MemoryService

memory = MemoryService(project_id="my-project")

# Check collection stats
store = memory.store
info = store.client.get_collection("run_summaries")
print(f"Points in collection: {info.points_count}")

# Check payload filters
results = memory.search_summaries(
    query="test",
    project_id="my-project",  # Must match!
    limit=10
)
print(f"Results: {len(results)}")
```

**Solutions**:

**Wrong project_id filter**:
- Ensure `project_id` in search matches write
- Project IDs are case-sensitive

**Collection not created**:
- Collections created lazily on first write
- Verify data was written successfully

**Query too specific**:
- Try broader queries
- Check embedding quality (OpenAI vs fallback)

**Status filtering**:
- Entries with `status: tombstoned/superseded/archived` excluded
- Check payload `status` field

#### 5. SOT Indexing Fails

**Symptoms**:
- `index_sot_docs()` returns errors
- SOT retrieval returns no results

**Diagnosis**:

```python
from autopack.memory import MemoryService

memory = MemoryService(project_id="my-project")

result = memory.index_sot_docs(
    project_id="my-project",
    workspace_root="/path/to/workspace",
    docs_dir="docs"
)

print(result)
# Expected: {"indexed": 150, "errors": []}
```

**Solutions**:

**Missing SOT files**:
- Verify `docs/BUILD_HISTORY.md` exists
- Check `workspace_root` path is correct

**Chunking errors**:
- Large files may timeout
- Increase `AUTOPACK_SOT_CHUNK_MAX_CHARS`

**Embedding failures**:
- Check OpenAI API if enabled
- Fall back to deterministic embeddings

#### 6. High Memory Usage (Qdrant)

**Symptoms**:
- Qdrant container using excessive RAM
- System becomes unresponsive

**Diagnosis**:
```bash
# Check container memory
docker stats qdrant

# Check collection sizes
curl http://localhost:6333/collections | jq '.result.collections[] | {name, points_count}'
```

**Solutions**:

**Too many collections**:
- Run maintenance to prune old data (see [Maintenance](#maintenance))

**Large vectors**:
- OpenAI embeddings are 1536 dimensions
- Consider reducing `top_k` retrieval limits

**Insufficient host resources**:
- Increase Docker memory limit (Docker Desktop → Settings → Resources)
- Add RAM to host machine

**Memory leak**:
- Restart Qdrant: `docker compose restart qdrant`
- Update to latest Qdrant version

### Debugging Techniques

**Enable Debug Logging**:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("autopack.memory").setLevel(logging.DEBUG)
```

**Inspect Qdrant State**:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

# List all collections
collections = client.get_collections()
for coll in collections.collections:
    print(coll.name)

# Get collection info
info = client.get_collection("run_summaries")
print(f"Points: {info.points_count}")
print(f"Config: {info.config}")

# Scroll through points (first 10)
records = client.scroll("run_summaries", limit=10)
for record in records[0]:
    print(record.id, record.payload)
```

**Test Embedding Pipeline**:

```python
from autopack.memory.embeddings import sync_embed_text

text = "This is a test query"
vector = sync_embed_text(text)

print(f"Embedding dimension: {len(vector)}")
print(f"Sample values: {vector[:5]}")
```

**Simulate Search**:

```python
from autopack.memory import MemoryService

memory = MemoryService(project_id="test")

# Write test data
memory.write_phase_summary(
    run_id="test-run",
    phase_id="test-phase",
    project_id="test",
    summary="Authentication refactoring completed",
    changes="Updated JWT validation logic",
    ci_result="PASS"
)

# Search
results = memory.search_summaries(
    query="authentication changes",
    project_id="test",
    limit=5
)

for res in results:
    print(f"Score: {res['score']:.3f} | {res['payload']['summary']}")
```

---

## Performance Tuning

### Qdrant Optimization

**HNSW Index Tuning**:

HNSW (Hierarchical Navigable Small World) parameters control search speed vs accuracy:

```python
from qdrant_client.models import VectorParams, Distance, HnswConfigDiff

# Default (balanced)
VectorParams(
    size=1536,
    distance=Distance.COSINE,
    hnsw_config=HnswConfigDiff(
        m=16,  # Connections per node (higher = more accurate, slower)
        ef_construct=100,  # Construction time (higher = better index quality)
    )
)

# High accuracy (slower search)
hnsw_config = HnswConfigDiff(m=32, ef_construct=200)

# High speed (lower accuracy)
hnsw_config = HnswConfigDiff(m=8, ef_construct=50)
```

**Quantization** (reduce memory):

```python
from qdrant_client.models import QuantizationConfig, ScalarQuantization

# Enable scalar quantization (4x memory reduction)
QuantizationConfig(
    scalar=ScalarQuantization(
        type="int8",
        quantile=0.99,
        always_ram=True  # Keep quantized vectors in RAM
    )
)
```

**Note**: Autopack uses default HNSW settings. To customize, modify `qdrant_store.py::_create_collection()`.

### Search Performance

**Top-K Limiting**:

```python
# Faster: Retrieve fewer results
results = memory.search_summaries(query, project_id, limit=5)  # Good

# Slower: Retrieve many results
results = memory.search_summaries(query, project_id, limit=100)  # Avoid
```

**Recommendation**: Use `limit=5` for most queries, `limit=3` for SOT.

**Payload Filtering**:

```python
# Fast: Filter by indexed fields (project_id, run_id, phase_id)
results = memory.search_summaries(
    query="test failures",
    project_id="my-project",  # Indexed filter
    run_id="run-123",  # Indexed filter
    limit=5
)

# Slower: Post-filter in application code
all_results = memory.search_summaries(query, project_id, limit=100)
filtered = [r for r in all_results if r['payload']['ci_result'] == 'FAIL']
```

**Recommendation**: Use built-in filters (`project_id`, `run_id`) whenever possible.

### Embedding Optimization

**Batch Embedding**:

```python
from autopack.memory.embeddings import sync_embed_texts

# Faster: Batch multiple texts
texts = ["query 1", "query 2", "query 3"]
vectors = sync_embed_texts(texts)

# Slower: Embed one at a time
vectors = [sync_embed_text(t) for t in texts]
```

**OpenAI vs Fallback**:

| Feature | OpenAI | Fallback |
|---------|--------|----------|
| **Quality** | High (semantic) | Moderate (content-hash) |
| **Speed** | 100-200ms per request | <1ms |
| **Cost** | ~$0.02 per 1M tokens | Free |
| **Offline** | No | Yes |

**Recommendation**:
- **Production**: Use OpenAI for best results
- **Development**: Use fallback for speed and offline work
- **CI/Testing**: Use fallback to avoid API costs

### Scaling Strategies

**Horizontal Scaling** (Qdrant Cloud):

1. **Multi-node cluster**: Distribute collections across nodes
2. **Replication**: Set `replication_factor > 1` for high availability
3. **Sharding**: Partition large collections by project_id

**Vertical Scaling** (Single Instance):

1. **Increase RAM**: Allow more vectors in memory
2. **Add CPU cores**: Parallel search threads
3. **Use SSD storage**: Faster disk I/O for large collections

**Collection Partitioning**:

```python
# Instead of one massive collection:
# collection: "run_summaries" (10M points)

# Partition by project:
# collection: "run_summaries_project1" (500K points)
# collection: "run_summaries_project2" (500K points)
```

**TTL-Based Pruning**:

Run maintenance regularly to remove old data:

```python
from autopack.memory.maintenance import run_maintenance

# Weekly cron job
stats = run_maintenance(
    store=memory.store,
    project_id="my-project",
    ttl_days=30,  # Remove data older than 30 days
    planning_keep_versions=3  # Keep last 3 planning versions
)

print(f"Pruned {stats['pruned']} points")
```

### Resource Allocation

**Recommended Qdrant Resources**:

| Workload | RAM | CPU | Storage |
|----------|-----|-----|---------|
| **Dev (1 project)** | 2GB | 1 core | 5GB |
| **Small (5 projects)** | 4GB | 2 cores | 20GB |
| **Medium (20 projects)** | 8GB | 4 cores | 100GB |
| **Large (100+ projects)** | 16GB+ | 8+ cores | 500GB+ |

**Docker Resource Limits**:

```yaml
# docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant:v1.12.5
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

---

## Maintenance

### Routine Tasks

**Daily**:
- Monitor Qdrant container health (`docker ps`)
- Check disk usage (`du -sh ./qdrant_storage`)
- Review error logs for fallback warnings

**Weekly**:
- Run TTL-based pruning (see below)
- Backup Qdrant storage directory
- Review collection sizes and query performance

**Monthly**:
- Audit SOT indexing completeness
- Update Qdrant version (if new release)
- Review embedding costs (if using OpenAI)

### TTL Management

**Automated Pruning**:

```python
from autopack.memory.maintenance import run_maintenance
from autopack.memory import MemoryService

memory = MemoryService(project_id="my-project")

stats = run_maintenance(
    store=memory.store,
    project_id="my-project",
    ttl_days=30,  # Default TTLs from collection metadata
    planning_keep_versions=3,  # Keep last 3 planning artifacts
    dry_run=False  # Set True to preview changes
)

print(f"""
Maintenance Results:
  - Pruned: {stats['pruned']} points
  - Tombstoned: {stats['tombstoned']} points
  - Errors: {stats['errors']}
""")
```

**Collection-Specific TTLs**:

| Collection | Default TTL | Rationale |
|------------|-------------|-----------|
| `code_docs` | 90 days | Code changes slowly |
| `run_summaries` | 30 days | Recent context most relevant |
| `errors_ci` | 14 days | Errors get fixed quickly |
| `doctor_hints` | 30 days | Reusable recommendations |
| `planning` | 30 days | Decisions remain relevant |
| `sot_docs` | 30 days | Re-indexed frequently |

**Custom TTL**:

```python
# Override TTL for specific project
run_maintenance(
    store=memory.store,
    project_id="legacy-project",
    ttl_days=90,  # Keep data longer
    planning_keep_versions=10
)
```

### Collection Management

**List Collections**:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
collections = client.get_collections()

for coll in collections.collections:
    info = client.get_collection(coll.name)
    print(f"{coll.name}: {info.points_count} points")
```

**Delete Collection**:

```python
# Delete specific collection (use with caution!)
client.delete_collection("run_summaries_old_project")
```

**Recreate Collection** (reset):

```python
# Delete and recreate (DESTRUCTIVE!)
client.delete_collection("errors_ci")
# Collection will be auto-created on next write
```

### Re-indexing

**When to Re-index**:
- SOT documents updated significantly
- Changed embedding model (OpenAI ↔ fallback)
- Qdrant version upgrade with breaking changes

**SOT Re-indexing**:

```python
from autopack.memory import MemoryService

memory = MemoryService(project_id="my-project")

# Clear existing SOT data
memory.store.delete_by_filter(
    collection_name="sot_docs",
    filter_conditions={"project_id": "my-project"}
)

# Re-index SOT
result = memory.index_sot_docs(
    project_id="my-project",
    workspace_root="/path/to/workspace",
    docs_dir="docs"
)

print(f"Indexed {result['indexed']} chunks")
```

**Full Re-index** (all collections):

```bash
# Backup first!
tar -czf qdrant_backup_$(date +%Y%m%d).tar.gz ./qdrant_storage

# Stop Qdrant
docker compose stop qdrant

# Delete storage
rm -rf ./qdrant_storage

# Restart Qdrant (fresh state)
docker compose start qdrant

# Trigger re-indexing via application code or SOT indexing
```

### Version Upgrades

**Qdrant Version Upgrade**:

```bash
# 1. Backup current storage
docker compose stop qdrant
tar -czf qdrant_backup_pre_upgrade.tar.gz ./qdrant_storage

# 2. Update docker-compose.yml
# image: qdrant/qdrant:v1.12.5 → image: qdrant/qdrant:v1.13.0

# 3. Pull new image
docker compose pull qdrant

# 4. Restart
docker compose up -d qdrant

# 5. Verify health
curl http://localhost:6333/health

# 6. Test collections
curl http://localhost:6333/collections

# 7. If issues, rollback
docker compose stop qdrant
rm -rf ./qdrant_storage
tar -xzf qdrant_backup_pre_upgrade.tar.gz
docker compose up -d qdrant
```

**Breaking Changes**: Always review Qdrant release notes before upgrading.

---

## Security

### Access Control

**Qdrant API Key** (Qdrant Cloud):

```bash
# Set API key for Cloud deployments
export AUTOPACK_QDRANT_API_KEY=your-secure-api-key
```

**Network Security**:

- **Local Deployment**: Qdrant listens on `localhost` by default (safe)
- **Production**: Use firewall to restrict port 6333/6334 to trusted IPs
- **Cloud**: Qdrant Cloud provides TLS and API key auth

**Docker Network Isolation**:

```yaml
# docker-compose.yml
services:
  qdrant:
    networks:
      - backend

networks:
  backend:
    driver: bridge
    internal: true  # No external access
```

### Data Privacy

**Sensitive Data**:

- **Avoid indexing secrets**: Memory service stores plaintext payloads
- **PII considerations**: Code and summaries may contain personal data
- **Compliance**: Ensure TTLs meet data retention policies (GDPR, etc.)

**Payload Sanitization**:

```python
# Before writing to memory
summary = sanitize_pii(summary)  # Remove emails, names, etc.
memory.write_phase_summary(..., summary=summary)
```

**Encryption at Rest**:

- **Qdrant**: No built-in encryption (encrypt disk volume instead)
- **FAISS**: No built-in encryption (encrypt `.faiss` directory)

**Encryption in Transit**:

- **Qdrant Cloud**: TLS enabled by default
- **Local Qdrant**: HTTP only (use reverse proxy with TLS if exposing externally)

### OpenAI API Security

**API Key Management**:

```bash
# NEVER commit API keys to git
export OPENAI_API_KEY=sk-...

# Use secret management in production
# e.g., AWS Secrets Manager, HashiCorp Vault
```

**Data Sent to OpenAI**:

- Text content is sent for embedding generation
- OpenAI retains data for abuse monitoring (30 days)
- Review OpenAI's data usage policy: [openai.com/policies](https://openai.com/policies)

**Opt-Out Strategy**:

```bash
# Use deterministic embeddings (zero API calls)
export USE_OPENAI_EMBEDDINGS=false
```

### Audit Logging

**Track Memory Operations**:

```python
import logging

# Enable audit logging
logger = logging.getLogger("autopack.memory.audit")
logger.setLevel(logging.INFO)

# Logs include:
# - Collection writes (who, when, what)
# - Search queries (query text, filters)
# - Maintenance operations (pruned points)
```

**Qdrant Access Logs**:

```bash
# View Qdrant request logs
docker logs qdrant | grep -E "POST|GET|DELETE"
```

---

## Reference

### Configuration Files

- `config/memory.yaml` - Memory service configuration
- `docker-compose.yml` - Qdrant container definition
- `.env` - Environment variables (gitignored)

### Source Code

- `src/autopack/memory/memory_service.py` - High-level API
- `src/autopack/memory/qdrant_store.py` - Qdrant backend
- `src/autopack/memory/faiss_store.py` - FAISS backend
- `src/autopack/memory/embeddings.py` - Embedding utilities
- `src/autopack/memory/sot_indexing.py` - SOT chunking
- `src/autopack/memory/maintenance.py` - TTL and cleanup

### Documentation

- [docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md](docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md) - Integration guide
- [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) - Memory architecture decisions
- Qdrant docs: [qdrant.tech/documentation](https://qdrant.tech/documentation)
- OpenAI embeddings: [platform.openai.com/docs/guides/embeddings](https://platform.openai.com/docs/guides/embeddings)

### API Reference

**MemoryService Methods**:

```python
# Initialization
MemoryService(project_id: str, workspace_root: str = None)

# Writing
write_phase_summary(run_id, phase_id, project_id, summary, changes, ci_result)
write_error(run_id, phase_id, project_id, error_text, error_type, test_name)
write_doctor_hint(run_id, phase_id, project_id, hint, action, outcome)
write_planning_artifact(path, content, project_id, version, author, reason, status)
write_plan_change(summary, rationale, project_id, replaces_version, status)
write_decision_log(trigger, choice, rationale, project_id)
index_file(path, content, project_id, run_id)
index_sot_docs(project_id, workspace_root, docs_dir) -> dict

# Reading
search_code(query, project_id, limit=5) -> list[dict]
search_summaries(query, project_id, run_id=None, limit=5) -> list[dict]
search_errors(query, project_id, limit=5) -> list[dict]
search_doctor_hints(query, project_id, limit=5) -> list[dict]
search_sot(query, project_id, limit=3) -> list[dict]
search_planning(query, project_id, limit=5, types=None) -> list[dict]

retrieve_context(query, project_id, run_id, task_type, include_code=True,
                 include_summaries=True, include_errors=True, include_hints=True,
                 include_planning=False, include_sot=False) -> dict

format_retrieved_context(results: dict, max_chars=8000) -> str

# Maintenance
tombstone_entry(collection, point_id, reason, replaced_by=None)
latest_plan_change(project_id) -> dict | None
```

### Common Commands

```bash
# Start Qdrant
docker compose up -d qdrant

# Stop Qdrant
docker compose stop qdrant

# View Qdrant logs
docker logs -f qdrant

# Check Qdrant health
curl http://localhost:6333/health

# List collections
curl http://localhost:6333/collections

# Backup Qdrant storage
tar -czf qdrant_backup_$(date +%Y%m%d).tar.gz ./qdrant_storage

# Restore Qdrant storage
tar -xzf qdrant_backup_YYYYMMDD.tar.gz

# Monitor Qdrant resources
docker stats qdrant

# Update Qdrant image
docker compose pull qdrant && docker compose up -d qdrant
```

### Support

**Internal Resources**:
- Architecture decisions: `docs/ARCHITECTURE_DECISIONS.md`
- Debug log: `docs/DEBUG_LOG.md`
- Build history: `docs/BUILD_HISTORY.md`

**External Resources**:
- Qdrant community: [discord.gg/qdrant](https://discord.gg/qdrant)
- Qdrant GitHub: [github.com/qdrant/qdrant](https://github.com/qdrant/qdrant)
- OpenAI support: [help.openai.com](https://help.openai.com)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-13
**Maintained By**: Autopack Team
