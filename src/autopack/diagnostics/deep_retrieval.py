"""Stage 2A: Deep Retrieval - Bounded escalation with strict per-category caps.

When Stage 1 evidence (handoff bundle) lacks sufficient signal, this module retrieves
targeted snippets from:
- Run-local artifacts (.autonomous_runs/<run_id>/*)
- Source of Truth (SOT) files (docs/, src/)
- Optional memory (if available)

Strict caps prevent context noise:
- Run artifacts: 5 most recent files, max 10KB total
- SOT files: 3 most relevant files, max 15KB total
- Memory: 5 most relevant entries, max 5KB total

Recency awareness: Prioritize files modified in last 24 hours.

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.
"""

import logging
from typing import Dict, List, Any, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class DeepRetrieval:
    """Bounded deep retrieval with strict per-category caps and recency awareness."""

    # Per-category caps (strict limits to prevent context noise)
    MAX_RUN_ARTIFACTS = 5  # Most recent files
    MAX_RUN_ARTIFACTS_SIZE = 10 * 1024  # 10KB total

    MAX_SOT_FILES = 3  # Most relevant files
    MAX_SOT_FILES_SIZE = 15 * 1024  # 15KB total

    MAX_MEMORY_ENTRIES = 5  # Most relevant entries
    MAX_MEMORY_ENTRIES_SIZE = 5 * 1024  # 5KB total

    # Recency window (prioritize recent files)
    RECENCY_WINDOW_HOURS = 24

    def __init__(self, run_dir: Path, repo_root: Path):
        """Initialize deep retrieval module.

        Args:
            run_dir: Path to .autonomous_runs/<run_id> directory
            repo_root: Path to repository root
        """
        self.run_dir = run_dir
        self.repo_root = repo_root
        self.logger = logger

    def retrieve(
        self,
        phase_id: str,
        handoff_bundle: Dict[str, Any],
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """Retrieve targeted snippets with strict per-category caps.

        Args:
            phase_id: Current phase identifier
            handoff_bundle: Stage 1 evidence bundle
            priority: Retrieval priority ('high', 'medium', 'low')

        Returns:
            Deep retrieval bundle with categorized snippets
        """
        self.logger.info(
            f"[DeepRetrieval] Starting bounded retrieval for phase {phase_id} "
            f"(priority={priority})"
        )

        retrieval_bundle = {
            "phase_id": phase_id,
            "timestamp": datetime.utcnow().isoformat(),
            "priority": priority,
            "run_artifacts": [],
            "sot_files": [],
            "memory_entries": [],
            "stats": {
                "run_artifacts_count": 0,
                "run_artifacts_size": 0,
                "sot_files_count": 0,
                "sot_files_size": 0,
                "memory_entries_count": 0,
                "memory_entries_size": 0,
            }
        }

        # Category 1: Run-local artifacts
        run_artifacts = self._retrieve_run_artifacts(phase_id)
        retrieval_bundle["run_artifacts"] = run_artifacts
        retrieval_bundle["stats"]["run_artifacts_count"] = len(run_artifacts)
        retrieval_bundle["stats"]["run_artifacts_size"] = sum(
            len(a["content"]) for a in run_artifacts
        )

        # Category 2: SOT files
        sot_files = self._retrieve_sot_files(phase_id, handoff_bundle)
        retrieval_bundle["sot_files"] = sot_files
        retrieval_bundle["stats"]["sot_files_count"] = len(sot_files)
        retrieval_bundle["stats"]["sot_files_size"] = sum(
            len(f["content"]) for f in sot_files
        )

        # Category 3: Memory (optional)
        memory_entries = self._retrieve_memory_entries(phase_id, handoff_bundle)
        retrieval_bundle["memory_entries"] = memory_entries
        retrieval_bundle["stats"]["memory_entries_count"] = len(memory_entries)
        retrieval_bundle["stats"]["memory_entries_size"] = sum(
            len(m["content"]) for m in memory_entries
        )

        self.logger.info(
            f"[DeepRetrieval] Retrieved {retrieval_bundle['stats']['run_artifacts_count']} "
            f"run artifacts ({retrieval_bundle['stats']['run_artifacts_size']} bytes), "
            f"{retrieval_bundle['stats']['sot_files_count']} SOT files "
            f"({retrieval_bundle['stats']['sot_files_size']} bytes), "
            f"{retrieval_bundle['stats']['memory_entries_count']} memory entries "
            f"({retrieval_bundle['stats']['memory_entries_size']} bytes)"
        )

        return retrieval_bundle

    def _retrieve_run_artifacts(self, phase_id: str) -> List[Dict[str, Any]]:
        """Retrieve run-local artifacts with recency awareness.

        Args:
            phase_id: Current phase identifier

        Returns:
            List of artifact snippets (max 5, max 10KB total)
        """
        artifacts = []
        total_size = 0

        # Find all log/json files in run directory
        artifact_files = []
        for pattern in ["*.log", "*.json", "*.txt"]:
            artifact_files.extend(self.run_dir.glob(pattern))

        # Sort by modification time (most recent first)
        artifact_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Apply recency window
        cutoff_time = datetime.now().timestamp() - (self.RECENCY_WINDOW_HOURS * 3600)
        recent_files = [
            f for f in artifact_files
            if f.stat().st_mtime >= cutoff_time
        ]

        # If no recent files, fall back to most recent overall
        files_to_process = recent_files if recent_files else artifact_files[:self.MAX_RUN_ARTIFACTS]

        for artifact_file in files_to_process[:self.MAX_RUN_ARTIFACTS]:
            if total_size >= self.MAX_RUN_ARTIFACTS_SIZE:
                break

            try:
                content = artifact_file.read_text(encoding="utf-8")
                # Truncate if needed to stay within budget
                remaining_budget = self.MAX_RUN_ARTIFACTS_SIZE - total_size
                if len(content) > remaining_budget:
                    content = content[:remaining_budget]

                artifacts.append({
                    "path": str(artifact_file.relative_to(self.run_dir)),
                    "content": content,
                    "size": len(content),
                    "modified": datetime.fromtimestamp(artifact_file.stat().st_mtime).isoformat(),
                })
                total_size += len(content)

            except Exception as e:
                self.logger.debug(f"Could not read artifact {artifact_file}: {e}")
                continue

        return artifacts

    def _retrieve_sot_files(self, phase_id: str, handoff_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve SOT files with relevance ranking.

        Args:
            phase_id: Current phase identifier
            handoff_bundle: Stage 1 evidence bundle

        Returns:
            List of SOT file snippets (max 3, max 15KB total)
        """
        sot_files = []
        total_size = 0

        # Extract keywords from handoff bundle for relevance ranking
        keywords = self._extract_keywords(handoff_bundle)

        # Search SOT directories (docs/, src/)
        sot_dirs = [self.repo_root / "docs", self.repo_root / "src"]
        candidate_files = []

        for sot_dir in sot_dirs:
            if not sot_dir.exists():
                continue

            # Find markdown/python files
            for pattern in ["**/*.md", "**/*.py"]:
                candidate_files.extend(sot_dir.glob(pattern))

        # Rank by relevance (keyword matches)
        ranked_files = self._rank_by_relevance(candidate_files, keywords)

        for sot_file, score in ranked_files[:self.MAX_SOT_FILES]:
            if total_size >= self.MAX_SOT_FILES_SIZE:
                break

            try:
                content = sot_file.read_text(encoding="utf-8")
                # Truncate if needed
                remaining_budget = self.MAX_SOT_FILES_SIZE - total_size
                if len(content) > remaining_budget:
                    content = content[:remaining_budget]

                sot_files.append({
                    "path": str(sot_file.relative_to(self.repo_root)),
                    "content": content,
                    "size": len(content),
                    "relevance_score": score,
                })
                total_size += len(content)

            except Exception as e:
                self.logger.debug(f"Could not read SOT file {sot_file}: {e}")
                continue

        return sot_files

    def _retrieve_memory_entries(self, phase_id: str, handoff_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve memory entries (if available).

        Args:
            phase_id: Current phase identifier
            handoff_bundle: Stage 1 evidence bundle

        Returns:
            List of memory entry snippets (max 5, max 5KB total)
        """
        # Memory retrieval is optional - return empty if not available
        # Future enhancement: integrate with vector store/memory system
        self.logger.debug("[DeepRetrieval] Memory retrieval not yet implemented")
        return []

    def _extract_keywords(self, handoff_bundle: Dict[str, Any]) -> List[str]:
        """Extract keywords from handoff bundle for relevance ranking.

        Args:
            handoff_bundle: Stage 1 evidence bundle

        Returns:
            List of keywords
        """
        keywords = []

        # Extract from error message
        error_msg = handoff_bundle.get("error_message", "")
        if error_msg:
            # Simple keyword extraction (split on whitespace, filter short words)
            words = error_msg.lower().split()
            keywords.extend([w for w in words if len(w) > 4])

        # Extract from root cause
        root_cause = handoff_bundle.get("root_cause", "")
        if root_cause:
            words = root_cause.lower().split()
            keywords.extend([w for w in words if len(w) > 4])

        # Deduplicate
        return list(set(keywords))

    def _rank_by_relevance(self, files: List[Path], keywords: List[str]) -> List[Tuple[Path, float]]:
        """Rank files by keyword relevance.

        Args:
            files: List of candidate files
            keywords: List of keywords to match

        Returns:
            List of (file, score) tuples, sorted by score descending
        """
        if not keywords:
            # No keywords - return files sorted by recency
            return [(f, 0.0) for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)]

        scored_files = []
        for file in files:
            try:
                content = file.read_text(encoding="utf-8").lower()
                # Count keyword matches
                score = sum(content.count(kw) for kw in keywords)
                scored_files.append((file, float(score)))
            except Exception as e:
                self.logger.debug(f"Could not score file {file}: {e}")
                scored_files.append((file, 0.0))

        # Sort by score descending
        scored_files.sort(key=lambda x: x[1], reverse=True)
        return scored_files


# -------------------------------------------------------------------------------------------------
# Compatibility API used by BUILD-112 production validation tests
# -------------------------------------------------------------------------------------------------


class DeepRetrievalEngine:
    """Embedding-backed deep retrieval engine (test shim).

    This is separate from the bounded run-artifact retrieval above. The BUILD-112
    validation suite expects an engine that:
    - queries an embedding model,
    - caps snippets per category,
    - caps total snippets across categories,
    - enforces max line count per snippet,
    - preserves citation fields (path, start_line, end_line).
    """

    def __init__(self, embedding_model: Any):
        self.embedding_model = embedding_model

    def retrieve_deep_context(
        self,
        query: str,
        categories: List[str],
        max_snippets_per_category: int = 3,
        max_lines_per_snippet: int = 120,
        max_total_snippets: int = 12,
    ) -> Dict[str, List[Dict[str, Any]]]:
        results: Dict[str, List[Dict[str, Any]]] = {c: [] for c in categories}
        total = 0

        for category in categories:
            if total >= max_total_snippets:
                break

            # The embedding model interface is mocked in tests; call `search` at least once.
            try:
                candidates = self.embedding_model.search(query=query, category=category)
            except TypeError:
                candidates = self.embedding_model.search(query)

            snippets: List[Dict[str, Any]] = []
            for item in candidates or []:
                if len(snippets) >= max_snippets_per_category or total >= max_total_snippets:
                    break

                content = item.get("content", "") or ""
                content = self._truncate_to_lines(content, max_lines_per_snippet)

                snippet = {
                    "path": item.get("path", ""),
                    "content": content,
                    "score": item.get("score", 0.0),
                    "start_line": int(item.get("start_line", 1) or 1),
                    "end_line": int(item.get("end_line", 1) or 1),
                }
                snippets.append(snippet)
                total += 1

            results[category] = snippets

        return results

    def _truncate_to_lines(self, text: str, max_lines: int) -> str:
        if max_lines <= 0:
            return ""
        lines = text.splitlines(True)  # keep line endings
        if len(lines) <= max_lines:
            return text
        return "".join(lines[:max_lines])