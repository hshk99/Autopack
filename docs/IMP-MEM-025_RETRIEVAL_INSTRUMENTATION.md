# IMP-MEM-025: Memory Retrieval Instrumentation

> **Status**: Proposed
> **Priority**: Medium
> **Category**: Memory / Observability
> **Prerequisites**: None
> **Estimated Effort**: Medium (3-5 phases)

## Problem Statement

Before implementing hybrid search (vector + keyword), we need **data-driven evidence** that pure vector search is missing relevant results. Currently, there's no instrumentation to detect:

1. Cases where relevant memories exist but weren't retrieved
2. Exact-match failures (query contains literal terms that exist in memory)
3. Query patterns that underperform

Without this data, implementing hybrid search is speculative and could introduce unnecessary complexity.

## Proposed Solution

Add retrieval instrumentation that logs potential missed retrievals and enables analysis of search effectiveness.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL INSTRUMENTATION FLOW                        │
└─────────────────────────────────────────────────────────────────────────┘

    Query Arrives
         │
         ▼
┌─────────────────────┐
│  Vector Search      │──────────────┐
│  (current behavior) │              │
└─────────────────────┘              │
         │                           │
         ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│  Results Returned   │    │  Keyword Scan       │
│  (top_k items)      │    │  (instrumentation)  │
└─────────────────────┘    └─────────────────────┘
         │                           │
         │                           ▼
         │              ┌─────────────────────────────┐
         │              │  Compare: Did keyword scan  │
         │              │  find items NOT in vector   │
         │              │  results?                   │
         │              └─────────────────────────────┘
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────┐
│  Log Retrieval Metrics                              │
│  - query_text, vector_results_count                 │
│  - keyword_only_count (items found by keyword but   │
│    not vector - potential misses)                   │
│  - overlap_count, timestamp                         │
└─────────────────────────────────────────────────────┘
         │
         ▼
    Return vector results (behavior unchanged)
```

### Key Components

#### 1. RetrievalInstrumentor Class

**Location**: `src/autopack/memory/retrieval_instrumentor.py`

```python
@dataclass
class RetrievalMetrics:
    """Metrics captured for each retrieval operation."""
    query_text: str
    query_embedding_hash: str  # For deduplication
    collection: str
    timestamp: datetime

    # Vector search results
    vector_results_count: int
    vector_result_ids: List[str]
    vector_top_score: float
    vector_min_score: float

    # Keyword scan results (instrumentation only)
    keyword_matches_count: int
    keyword_match_ids: List[str]

    # Analysis
    keyword_only_count: int  # Found by keyword but NOT by vector
    vector_only_count: int   # Found by vector but NOT by keyword
    overlap_count: int       # Found by both

    # Potential miss indicators
    exact_match_in_corpus: bool  # Query terms appear exactly in some memory
    exact_match_retrieved: bool  # That exact match was in vector results

class RetrievalInstrumentor:
    """Instruments memory retrieval to detect potential missed results."""

    def __init__(self, store: VectorStoreProtocol):
        self.store = store
        self.metrics_log: List[RetrievalMetrics] = []
        self.log_file = Path("data/retrieval_metrics.jsonl")

    def instrument_query(
        self,
        query: str,
        collection: str,
        vector_results: List[ScoredPoint],
        top_k: int = 10
    ) -> RetrievalMetrics:
        """
        Run keyword scan and compare with vector results.

        This does NOT change retrieval behavior - only logs metrics.
        """
        # 1. Extract significant terms from query
        terms = self._extract_query_terms(query)

        # 2. Run keyword scan against collection
        keyword_matches = self._keyword_scan(collection, terms)

        # 3. Compare with vector results
        vector_ids = {r.id for r in vector_results}
        keyword_ids = {m.id for m in keyword_matches}

        # 4. Calculate overlap/differences
        keyword_only = keyword_ids - vector_ids
        vector_only = vector_ids - keyword_ids
        overlap = vector_ids & keyword_ids

        # 5. Check for exact match scenarios
        exact_match_exists = self._check_exact_match_exists(collection, query)
        exact_match_retrieved = self._check_exact_match_retrieved(
            query, vector_results
        )

        # 6. Build and log metrics
        metrics = RetrievalMetrics(
            query_text=query,
            query_embedding_hash=hashlib.md5(query.encode()).hexdigest()[:8],
            collection=collection,
            timestamp=datetime.now(timezone.utc),
            vector_results_count=len(vector_results),
            vector_result_ids=[str(r.id) for r in vector_results],
            vector_top_score=vector_results[0].score if vector_results else 0.0,
            vector_min_score=vector_results[-1].score if vector_results else 0.0,
            keyword_matches_count=len(keyword_matches),
            keyword_match_ids=[str(m.id) for m in keyword_matches],
            keyword_only_count=len(keyword_only),
            vector_only_count=len(vector_only),
            overlap_count=len(overlap),
            exact_match_in_corpus=exact_match_exists,
            exact_match_retrieved=exact_match_retrieved,
        )

        self._log_metrics(metrics)
        return metrics

    def _extract_query_terms(self, query: str) -> List[str]:
        """Extract significant terms for keyword matching."""
        # Remove common stop words, keep technical terms
        # Focus on: error codes, function names, file paths, class names
        pass

    def _keyword_scan(
        self,
        collection: str,
        terms: List[str]
    ) -> List[ScoredPoint]:
        """
        Scan collection for keyword matches.

        Uses Qdrant's scroll + filter or FAISS metadata scan.
        """
        pass

    def _check_exact_match_exists(self, collection: str, query: str) -> bool:
        """Check if query text appears exactly in any memory entry."""
        pass

    def _check_exact_match_retrieved(
        self,
        query: str,
        results: List[ScoredPoint]
    ) -> bool:
        """Check if exact-match entry (if any) was in results."""
        pass

    def _log_metrics(self, metrics: RetrievalMetrics) -> None:
        """Append metrics to JSONL log file."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(asdict(metrics), default=str) + "\n")
```

#### 2. Integration Points

**File**: `src/autopack/memory/context_injector.py`

```python
# Add instrumentation to existing retrieval methods

class ContextInjector:
    def __init__(self, ...):
        # ... existing init ...
        self.instrumentor = RetrievalInstrumentor(self.store)
        self.enable_instrumentation = config.get(
            "memory.enable_retrieval_instrumentation", False
        )

    def retrieve_context_with_metadata(self, query: str, ...):
        # Existing vector retrieval
        results = self._vector_search(query, collection, top_k)

        # Instrumentation (does not change behavior)
        if self.enable_instrumentation:
            self.instrumentor.instrument_query(
                query=query,
                collection=collection,
                vector_results=results,
                top_k=top_k
            )

        return results  # Unchanged
```

#### 3. Analysis Report Generator

**File**: `src/autopack/memory/retrieval_analysis.py`

```python
class RetrievalAnalysisReport:
    """Generates analysis reports from retrieval metrics."""

    def generate_report(self, days: int = 7) -> Dict:
        """
        Analyze retrieval metrics and identify patterns.

        Returns:
            {
                "period": "2026-01-26 to 2026-02-02",
                "total_queries": 1523,
                "exact_match_miss_rate": 0.08,  # 8% of exact matches not retrieved
                "keyword_only_discoveries": [
                    {
                        "query": "NullPointerException AuthService",
                        "missed_entry": "error: NullPointerException in AuthService.validate()",
                        "vector_score": 0.72,  # Score of retrieved item
                        "keyword_match_score": 1.0,  # Exact match
                    },
                    ...
                ],
                "recommendation": "hybrid_search_warranted" | "vector_search_sufficient",
                "confidence": 0.85,
            }
        """
        pass

    def calculate_hybrid_search_benefit(self) -> Dict:
        """
        Estimate improvement if hybrid search were implemented.

        Returns:
            {
                "estimated_recall_improvement": 0.12,  # +12%
                "queries_affected_per_week": 45,
                "recommendation_threshold": 0.10,  # >10% = recommend hybrid
            }
        """
        pass
```

### Configuration

**File**: `config/memory.yaml`

```yaml
# Retrieval instrumentation settings (IMP-MEM-025)
retrieval_instrumentation:
  enabled: false  # Enable to start collecting metrics
  sample_rate: 1.0  # 1.0 = all queries, 0.1 = 10% sample
  log_path: "data/retrieval_metrics.jsonl"
  keyword_scan_limit: 100  # Max entries to scan per query

  # Analysis thresholds
  analysis:
    min_samples_for_report: 100  # Need N queries before generating report
    exact_match_miss_threshold: 0.05  # >5% = potential issue
    keyword_only_discovery_threshold: 0.10  # >10% = hybrid search warranted
```

### CLI Commands

```bash
# Enable instrumentation
autopack memory instrument --enable

# Check instrumentation status
autopack memory instrument --status

# Generate analysis report
autopack memory instrument --report --days 7

# Export raw metrics
autopack memory instrument --export retrieval_metrics.json
```

## Success Criteria

1. **Data Collection**: Capture metrics for 100+ queries across 7 days
2. **Analysis Report**: Generate actionable report with:
   - Exact-match miss rate
   - Keyword-only discovery rate
   - Specific examples of potential misses
3. **Decision Support**: Clear recommendation (hybrid vs. vector-only) with confidence score

## Decision Framework

After collecting data, use this framework:

| Metric | Threshold | Recommendation |
|--------|-----------|----------------|
| Exact-match miss rate | < 5% | Vector search sufficient |
| Exact-match miss rate | 5-15% | Consider hybrid for specific collections |
| Exact-match miss rate | > 15% | Hybrid search strongly recommended |
| Keyword-only discoveries | < 10% | No action needed |
| Keyword-only discoveries | > 10% | Hybrid search warranted |

## Implementation Phases

### Phase 1: Core Instrumentation
- [ ] Create `RetrievalInstrumentor` class
- [ ] Add JSONL logging for metrics
- [ ] Integrate into `ContextInjector`
- [ ] Add configuration options

### Phase 2: Keyword Scanning
- [ ] Implement `_extract_query_terms()` with technical term extraction
- [ ] Implement `_keyword_scan()` for Qdrant (scroll + filter)
- [ ] Implement `_keyword_scan()` for FAISS (metadata scan)
- [ ] Add exact-match detection

### Phase 3: Analysis & Reporting
- [ ] Create `RetrievalAnalysisReport` class
- [ ] Implement weekly report generation
- [ ] Add CLI commands for analysis
- [ ] Create decision recommendation logic

### Phase 4: Validation & Cleanup
- [ ] Run for 7+ days in production
- [ ] Generate analysis report
- [ ] Make hybrid search decision based on data
- [ ] Document findings
- [ ] Remove or retain instrumentation based on ongoing need

## Related IMPs

- **IMP-MEM-002**: Hint conflict detection (uses retrieval)
- **IMP-MEM-006**: Content-based deduplication (affects what's stored)
- **IMP-MEM-010**: Freshness filtering (affects what's retrieved)
- **IMP-LOOP-019**: Context quality metadata (consumes retrieval results)

## Notes

This IMP is **diagnostic only** - it does not change retrieval behavior. The purpose is to gather evidence before deciding whether hybrid search (or other retrieval improvements) are warranted.

If the data shows vector search is performing well (exact-match miss rate < 5%, keyword-only discoveries < 10%), we can confidently skip hybrid search implementation and avoid unnecessary complexity.
