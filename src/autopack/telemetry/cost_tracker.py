"""Context preparation cost tracking for IMP-COST-004.

Tracks previously invisible context preparation overhead:
- File reads (count and bytes)
- Embedding API calls and token usage
- Artifact loads (bytes)
- Scope analysis duration
- Estimated token equivalent of prep work

This enables visibility into 20-40% hidden overhead in context assembly phase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ContextPrepCost:
    """Tracks context preparation costs."""

    phase_id: str
    file_reads_count: int
    file_reads_bytes: int
    embedding_calls: int
    embedding_tokens: int
    artifact_loads: int
    artifact_bytes: int
    scope_analysis_ms: float
    total_prep_ms: float

    @property
    def estimated_token_equivalent(self) -> int:
        """Estimate token equivalent of context prep work.

        Rough estimate: 1 token ≈ 4 bytes, plus embedding tokens directly.
        """
        # Bytes to token conversion
        bytes_total = self.file_reads_bytes + self.artifact_bytes
        bytes_as_tokens = bytes_total // 4
        return bytes_as_tokens + self.embedding_tokens


class ContextPrepTracker:
    """Tracks context preparation costs.

    Records file reads, embedding API calls, artifact loads, and scope analysis
    duration to measure previously invisible context preparation overhead.
    """

    def __init__(self, phase_id: str):
        """Initialize context preparation tracker.

        Args:
            phase_id: Identifier for the phase being tracked
        """
        self.phase_id = phase_id
        self._start_time: float | None = None
        self._file_reads: List[Dict[str, int]] = []
        self._embedding_calls: List[Dict[str, int]] = []
        self._artifact_loads: List[Dict[str, int]] = []
        self._scope_analysis_ms: float = 0.0

    def start(self) -> None:
        """Start tracking."""
        self._start_time = time.time()

    def record_file_read(self, path: str, bytes_read: int) -> None:
        """Record a file read operation.

        Args:
            path: File path that was read
            bytes_read: Number of bytes read
        """
        self._file_reads.append({"path": path, "bytes": bytes_read})

    def record_embedding_call(self, tokens: int) -> None:
        """Record an embedding API call.

        Args:
            tokens: Number of tokens used in the embedding call
        """
        self._embedding_calls.append({"tokens": tokens})

    def record_artifact_load(self, artifact_id: str, bytes_loaded: int) -> None:
        """Record an artifact load.

        Args:
            artifact_id: Identifier for the artifact
            bytes_loaded: Number of bytes loaded
        """
        self._artifact_loads.append({"id": artifact_id, "bytes": bytes_loaded})

    def record_scope_analysis(self, duration_ms: float) -> None:
        """Record scope analysis duration.

        Args:
            duration_ms: Duration of scope analysis in milliseconds
        """
        self._scope_analysis_ms = duration_ms

    def finalize(self) -> ContextPrepCost:
        """Finalize and return cost summary.

        Returns:
            ContextPrepCost object with aggregated metrics
        """
        total_ms = (time.time() - self._start_time) * 1000 if self._start_time else 0

        return ContextPrepCost(
            phase_id=self.phase_id,
            file_reads_count=len(self._file_reads),
            file_reads_bytes=sum(r["bytes"] for r in self._file_reads),
            embedding_calls=len(self._embedding_calls),
            embedding_tokens=sum(e["tokens"] for e in self._embedding_calls),
            artifact_loads=len(self._artifact_loads),
            artifact_bytes=sum(a["bytes"] for a in self._artifact_loads),
            scope_analysis_ms=self._scope_analysis_ms,
            total_prep_ms=total_ms,
        )
