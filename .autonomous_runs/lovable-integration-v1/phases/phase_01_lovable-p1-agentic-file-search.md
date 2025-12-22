# Phase 1.1: Agentic File Search Implementation

## Priority: P1 (Highest)
## Tier: Phase 1 - Core Precision
## Estimated Effort: 3-4 days
## ROI Rating: ⭐⭐⭐⭐⭐

---

## Objective

Implement Lovable's "Agentic File Search" pattern to achieve **95% reduction in hallucinations** by using semantic search and confidence scoring to find the exact files that need to be modified, rather than guessing or modifying wrong files.

**Key Impact:**
- 95% reduction in hallucinations (modifying wrong files)
- Surgical precision in file selection
- Foundation for all other Lovable patterns

---

## Background

**Current Problem:**
Autopack's builder sometimes modifies the wrong files due to:
- Ambiguous file names (e.g., `utils.py` exists in 5 different directories)
- Incomplete context (doesn't know which `config.py` to modify)
- Token limits preventing full codebase analysis
- LLM hallucinations when guessing file locations

**Lovable Solution:**
- Use semantic search (embeddings) to find files based on intent
- Assign confidence scores (0.0-1.0) to each candidate file
- Only proceed if confidence > threshold (default: 0.7)
- Fallback to manual selection or full codebase mode if confidence too low

**Example:**
```
User Intent: "Fix the authentication bug in the login handler"

Without Agentic Search:
- Builder guesses: "Maybe src/auth/login.py?"
- Actually in: "src/api/handlers/auth_handler.py"
- Result: Wrong file modified, bug persists

With Agentic Search:
- Semantic search: "authentication login handler"
- Candidates:
  - src/api/handlers/auth_handler.py (confidence: 0.92) ✅
  - src/auth/login.py (confidence: 0.45)
  - src/utils/auth_utils.py (confidence: 0.31)
- Selects: src/api/handlers/auth_handler.py
- Result: Correct file modified, bug fixed
```

---

## Implementation Plan

### Files to Create

**1. `src/autopack/file_manifest/agentic_search.py` (NEW)**

Core module implementing agentic file search:

```python
"""Agentic File Search - Semantic file discovery with confidence scoring."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileCandidate:
    """A candidate file from agentic search."""
    file_path: str
    confidence: float  # 0.0 to 1.0
    relevance_score: float  # Raw semantic similarity
    reasons: List[str]  # Why this file was selected
    metadata: dict  # File size, last modified, etc.


class AgenticFileSearch:
    """Semantic file search using embeddings and confidence scoring."""

    def __init__(
        self,
        repo_root: Path,
        confidence_threshold: float = 0.7,
        max_candidates: int = 5
    ):
        """
        Initialize agentic file search.

        Args:
            repo_root: Repository root directory
            confidence_threshold: Minimum confidence to accept a file (0.0-1.0)
            max_candidates: Maximum number of candidates to return
        """
        self.repo_root = Path(repo_root)
        self.confidence_threshold = confidence_threshold
        self.max_candidates = max_candidates
        self._embedding_cache = {}  # Cache file embeddings

    def search(
        self,
        intent: str,
        file_type: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[FileCandidate]:
        """
        Search for files matching the given intent.

        Args:
            intent: Natural language description of what to find
                   (e.g., "authentication login handler")
            file_type: Optional file type filter (e.g., "py", "ts", "md")
            exclude_patterns: Optional patterns to exclude (e.g., ["*test*", "*.pyc"])

        Returns:
            List of FileCandidate objects, sorted by confidence (highest first)
        """
        logger.info(f"[AgenticSearch] Searching for: {intent}")

        # Step 1: Get all candidate files (respecting filters)
        all_files = self._get_all_files(file_type, exclude_patterns)
        logger.debug(f"[AgenticSearch] Found {len(all_files)} candidate files")

        # Step 2: Generate embedding for search intent
        intent_embedding = self._get_embedding(intent)

        # Step 3: Score each file against intent
        scored_files = []
        for file_path in all_files:
            score = self._score_file(file_path, intent, intent_embedding)
            if score['confidence'] >= self.confidence_threshold:
                candidate = FileCandidate(
                    file_path=str(file_path),
                    confidence=score['confidence'],
                    relevance_score=score['relevance'],
                    reasons=score['reasons'],
                    metadata=self._get_file_metadata(file_path)
                )
                scored_files.append(candidate)

        # Step 4: Sort by confidence and limit results
        scored_files.sort(key=lambda x: x.confidence, reverse=True)
        top_candidates = scored_files[:self.max_candidates]

        logger.info(
            f"[AgenticSearch] Found {len(top_candidates)} files "
            f"with confidence >= {self.confidence_threshold}"
        )
        for candidate in top_candidates:
            logger.debug(
                f"  - {candidate.file_path} "
                f"(confidence: {candidate.confidence:.2f})"
            )

        return top_candidates

    def _get_all_files(
        self,
        file_type: Optional[str],
        exclude_patterns: Optional[List[str]]
    ) -> List[Path]:
        """Get all files in repo matching filters."""
        # TODO: Implement file discovery with gitignore respect
        # Use existing file manifest logic from Autopack
        raise NotImplementedError("File discovery logic")

    def _get_embedding(self, text: str):
        """Generate embedding for text using sentence-transformers or similar."""
        # TODO: Integrate with embedding model
        # Options:
        #   1. sentence-transformers/all-MiniLM-L6-v2 (local, fast)
        #   2. OpenAI text-embedding-ada-002 (API, high quality)
        #   3. Anthropic embeddings (if available)
        raise NotImplementedError("Embedding generation")

    def _score_file(
        self,
        file_path: Path,
        intent: str,
        intent_embedding
    ) -> dict:
        """
        Score a file against the search intent.

        Returns:
            {
                'confidence': float,  # 0.0-1.0
                'relevance': float,   # Raw similarity score
                'reasons': List[str]  # Why this file scored well
            }
        """
        reasons = []

        # 1. Semantic similarity (file path + contents)
        file_embedding = self._get_file_embedding(file_path)
        semantic_score = self._cosine_similarity(intent_embedding, file_embedding)

        # 2. Boost for file name matches
        file_name_score = self._file_name_match_score(file_path, intent)
        if file_name_score > 0.5:
            reasons.append(f"File name matches intent (score: {file_name_score:.2f})")

        # 3. Boost for recent modifications (recency bias)
        recency_score = self._recency_score(file_path)
        if recency_score > 0.7:
            reasons.append(f"Recently modified (score: {recency_score:.2f})")

        # 4. Combine scores with weights
        combined_score = (
            0.6 * semantic_score +
            0.25 * file_name_score +
            0.15 * recency_score
        )

        # 5. Convert to confidence (apply sigmoid for sharper thresholding)
        confidence = self._score_to_confidence(combined_score)

        if confidence >= self.confidence_threshold:
            reasons.append(
                f"High semantic similarity to intent (score: {semantic_score:.2f})"
            )

        return {
            'confidence': confidence,
            'relevance': semantic_score,
            'reasons': reasons
        }

    def _get_file_embedding(self, file_path: Path):
        """Get cached or generate embedding for file."""
        # Cache embeddings to avoid recomputation
        cache_key = str(file_path)
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # Generate embedding from file path + first N lines of code
        file_text = self._extract_file_text(file_path)
        embedding = self._get_embedding(file_text)

        self._embedding_cache[cache_key] = embedding
        return embedding

    def _extract_file_text(self, file_path: Path, max_lines: int = 50) -> str:
        """Extract text representation of file for embedding."""
        # Combine file path + docstring + first N lines
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()[:max_lines]
            content = ''.join(lines)

            # Format: "path/to/file.py: <content>"
            return f"{file_path}: {content}"
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return str(file_path)

    def _cosine_similarity(self, embedding1, embedding2) -> float:
        """Calculate cosine similarity between two embeddings."""
        # TODO: Implement cosine similarity
        # Use numpy or scipy for efficient computation
        raise NotImplementedError("Cosine similarity")

    def _file_name_match_score(self, file_path: Path, intent: str) -> float:
        """Score based on file name matching intent keywords."""
        # Extract keywords from intent
        # Check if file name contains keywords
        # Return score 0.0-1.0
        raise NotImplementedError("File name matching")

    def _recency_score(self, file_path: Path) -> float:
        """Score based on how recently file was modified."""
        # Files modified recently are more likely to be relevant
        # Return score 0.0-1.0
        raise NotImplementedError("Recency scoring")

    def _score_to_confidence(self, score: float) -> float:
        """Convert raw score to confidence using sigmoid."""
        import math
        # Sigmoid: 1 / (1 + e^(-k*(x - threshold)))
        # k controls steepness, threshold is midpoint
        k = 10
        threshold = 0.5
        confidence = 1 / (1 + math.exp(-k * (score - threshold)))
        return confidence

    def _get_file_metadata(self, file_path: Path) -> dict:
        """Get file metadata (size, modified time, etc.)."""
        try:
            stat = file_path.stat()
            return {
                'size_bytes': stat.st_size,
                'modified_timestamp': stat.st_mtime,
                'is_symlink': file_path.is_symlink()
            }
        except Exception as e:
            logger.warning(f"Failed to get metadata for {file_path}: {e}")
            return {}


# Utility functions

def search_files(
    intent: str,
    repo_root: Path,
    confidence_threshold: float = 0.7,
    file_type: Optional[str] = None
) -> List[FileCandidate]:
    """
    Convenience function for one-off file searches.

    Args:
        intent: What to search for (natural language)
        repo_root: Repository root directory
        confidence_threshold: Minimum confidence (0.0-1.0)
        file_type: Optional file type filter

    Returns:
        List of FileCandidate objects
    """
    searcher = AgenticFileSearch(
        repo_root=repo_root,
        confidence_threshold=confidence_threshold
    )
    return searcher.search(intent=intent, file_type=file_type)
```

---

### Integration Points

**1. File Manifest Generator** (`src/autopack/file_manifest/manifest_generator.py`)

Add agentic search mode:

```python
from autopack.file_manifest.agentic_search import AgenticFileSearch

class FileManifestGenerator:
    def __init__(self, ...):
        self.agentic_search = AgenticFileSearch(repo_root=self.repo_root)

    def generate_manifest(
        self,
        phase_goal: str,
        mode: str = "auto"  # "auto", "full", "agentic"
    ):
        if mode == "agentic":
            # Use agentic search to find relevant files
            candidates = self.agentic_search.search(
                intent=phase_goal,
                confidence_threshold=0.7
            )

            if not candidates:
                logger.warning("No high-confidence files found, falling back to full mode")
                return self._generate_full_manifest()

            # Build manifest from high-confidence candidates
            manifest = self._build_manifest_from_candidates(candidates)
            return manifest
```

**2. Builder Integration** (`src/autopack/llm_service.py`)

Use agentic search in builder phase:

```python
def execute_builder_phase(self, phase_goal: str, ...):
    # Check feature flag
    if os.getenv("LOVABLE_AGENTIC_SEARCH", "false").lower() == "true":
        # Use agentic search mode
        manifest = self.manifest_generator.generate_manifest(
            phase_goal=phase_goal,
            mode="agentic"
        )
    else:
        # Use existing full manifest mode
        manifest = self.manifest_generator.generate_manifest(
            phase_goal=phase_goal,
            mode="full"
        )
```

---

### Testing Strategy

**Unit Tests** (`tests/autopack/file_manifest/test_agentic_search.py`):

```python
import pytest
from pathlib import Path
from autopack.file_manifest.agentic_search import (
    AgenticFileSearch,
    FileCandidate,
    search_files
)

def test_agentic_search_finds_correct_file():
    """Test that agentic search finds the correct file with high confidence."""
    searcher = AgenticFileSearch(
        repo_root=Path("test_fixtures/sample_repo"),
        confidence_threshold=0.7
    )

    candidates = searcher.search(intent="authentication login handler")

    assert len(candidates) > 0
    assert candidates[0].file_path == "src/api/handlers/auth_handler.py"
    assert candidates[0].confidence >= 0.7


def test_agentic_search_respects_confidence_threshold():
    """Test that low-confidence files are filtered out."""
    searcher = AgenticFileSearch(
        repo_root=Path("test_fixtures/sample_repo"),
        confidence_threshold=0.9  # Very high threshold
    )

    candidates = searcher.search(intent="vague intent")

    # Should return no candidates if none meet threshold
    assert all(c.confidence >= 0.9 for c in candidates)


def test_file_name_boost():
    """Test that file names matching intent get boosted confidence."""
    searcher = AgenticFileSearch(repo_root=Path("test_fixtures/sample_repo"))

    candidates = searcher.search(intent="database connection")

    # File named "database.py" should rank higher than "utils.py"
    db_files = [c for c in candidates if "database" in c.file_path.lower()]
    assert len(db_files) > 0
    assert db_files[0].confidence > 0.7
```

---

### Feature Flag

**Environment Variable:** `LOVABLE_AGENTIC_SEARCH`

```bash
# Enable agentic search
export LOVABLE_AGENTIC_SEARCH=true

# Disable (use existing full manifest mode)
export LOVABLE_AGENTIC_SEARCH=false
```

**Configuration File:** `models.yaml`

```yaml
lovable_patterns:
  agentic_search:
    enabled: true
    confidence_threshold: 0.7
    max_candidates: 5
    embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
```

---

### Success Metrics

**Measure After Deployment:**

1. **Hallucination Rate** (manual sampling)
   - Baseline: 20% (1 in 5 phases modifies wrong files)
   - Target: 5% (1 in 20 phases)
   - Method: Manual review of 50 random phases

2. **File Selection Accuracy**
   - Baseline: 75% (3 in 4 phases select correct files)
   - Target: 95% (19 in 20 phases)
   - Method: Automated test suite + manual review

3. **Token Usage Reduction** (indirect benefit)
   - By selecting only relevant files, reduce tokens sent to LLM
   - Baseline: 50k tokens per phase
   - Target: 35k tokens per phase (30% reduction from file selection alone)

---

### Dependencies

**Python Packages:**
- `sentence-transformers` - For local embeddings (recommended)
  - OR `openai` - For OpenAI embeddings (higher quality, costs API calls)
- `numpy` - For cosine similarity calculations
- `scikit-learn` - For additional ML utilities (optional)

**Install:**
```bash
pip install sentence-transformers numpy scikit-learn
```

---

### Rollout Plan

**Week 1: Implementation**
- Day 1-2: Implement `AgenticFileSearch` class
- Day 3: Integrate with `FileManifestGenerator`
- Day 4: Write unit tests

**Week 2: Testing & Deployment**
- Day 1: Manual testing with 10 sample runs
- Day 2: Fix bugs, tune confidence threshold
- Day 3: Deploy with feature flag (10% of runs)
- Day 4: Monitor metrics, increase to 50%
- Day 5: Full rollout (100%)

---

### Risks & Mitigation

**Risk 1: Embedding Model Performance**
- **Issue:** Embeddings may not accurately capture file semantics
- **Mitigation:** Start with sentence-transformers (fast, local), upgrade to OpenAI embeddings if needed
- **Fallback:** If confidence too low, fall back to full manifest mode

**Risk 2: False Negatives**
- **Issue:** Correct file has low confidence, gets excluded
- **Mitigation:** Set conservative threshold (0.7), provide manual override option
- **Fallback:** User can force full manifest mode via environment variable

**Risk 3: Performance (Embedding Generation)**
- **Issue:** Generating embeddings for all files may be slow
- **Mitigation:** Cache embeddings, only regenerate when files change
- **Optimization:** Precompute embeddings in background task

---

## Deliverables

- [ ] `src/autopack/file_manifest/agentic_search.py` implemented
- [ ] Integration with `FileManifestGenerator` complete
- [ ] Unit tests passing (>=90% coverage)
- [ ] Feature flag (`LOVABLE_AGENTIC_SEARCH`) working
- [ ] Configuration in `models.yaml` added
- [ ] Documentation updated (README.md, LOVABLE_INTEGRATION_GUIDE.md)
- [ ] Metrics dashboard configured (Grafana)
- [ ] Gradual rollout complete (10% → 50% → 100%)

---

## Next Phase

After Phase 1.1 completes → Proceed to **Phase 1.2: Intelligent File Selection**

The two patterns work together:
- **Agentic Search** finds candidate files
- **Intelligent Selection** chooses which files to include in context (token optimization)
