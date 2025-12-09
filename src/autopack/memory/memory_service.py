# autopack/memory/memory_service.py
"""
High-level memory service for Autopack vector memory.

Collections (per plan):
- code_docs: embeddings of workspace files (path, content hash)
- run_summaries: per-phase summaries (changes, CI result, errors)
- errors_ci: failing test/error snippets
- doctor_hints: doctor hints/actions/outcomes

Payload schema:
- run_id, phase_id, project_id, task_type, timestamp
- path (for code_docs)
- type: summary | error | hint | code
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import yaml

from .embeddings import sync_embed_text, async_embed_text, EMBEDDING_SIZE, MAX_EMBEDDING_CHARS
from .faiss_store import FaissStore

logger = logging.getLogger(__name__)

# Collection names (per plan)
COLLECTION_CODE_DOCS = "code_docs"
COLLECTION_RUN_SUMMARIES = "run_summaries"
COLLECTION_ERRORS_CI = "errors_ci"
COLLECTION_DOCTOR_HINTS = "doctor_hints"

ALL_COLLECTIONS = [
    COLLECTION_CODE_DOCS,
    COLLECTION_RUN_SUMMARIES,
    COLLECTION_ERRORS_CI,
    COLLECTION_DOCTOR_HINTS,
]


def _load_memory_config() -> Dict[str, Any]:
    """Load memory configuration from config/memory.yaml."""
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "memory.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load memory config: {e}")
    return {}


class MemoryService:
    """
    High-level interface for vector memory operations.

    Wraps FaissStore and provides semantic search + insert for Autopack use cases.
    """

    def __init__(
        self,
        index_dir: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize memory service.

        Args:
            index_dir: Directory for FAISS indices (default from config or .faiss)
            enabled: Whether memory is enabled
        """
        config = _load_memory_config()
        self.enabled = config.get("enable_memory", enabled)
        self.top_k = config.get("top_k_retrieval", 5)
        self.max_embed_chars = config.get("max_embed_chars", MAX_EMBEDDING_CHARS)

        if index_dir is None:
            index_dir = config.get(
                "faiss_index_path",
                ".autonomous_runs/file-organizer-app-v1/.faiss"
            )

        self.store = FaissStore(index_dir=index_dir)

        # Ensure all collections exist
        for collection in ALL_COLLECTIONS:
            self.store.ensure_collection(collection, EMBEDDING_SIZE)

        logger.info(f"[MemoryService] Initialized (enabled={self.enabled}, top_k={self.top_k})")

    # -------------------------------------------------------------------------
    # Code Docs (workspace files)
    # -------------------------------------------------------------------------

    def index_file(
        self,
        path: str,
        content: str,
        project_id: str,
        run_id: Optional[str] = None,
    ) -> str:
        """
        Index a workspace file for retrieval.

        Args:
            path: Relative file path
            content: File content
            project_id: Project identifier
            run_id: Optional run identifier

        Returns:
            Point ID
        """
        if not self.enabled:
            return ""

        # Truncate content for embedding
        content_truncated = content[:self.max_embed_chars]
        content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[:16]

        # Generate embedding
        vector = sync_embed_text(f"File: {path}\n\n{content_truncated}")

        point_id = f"code:{project_id}:{path}:{content_hash}"
        payload = {
            "type": "code",
            "path": path,
            "project_id": project_id,
            "run_id": run_id,
            "content_hash": content_hash,
            "content_preview": content_truncated[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.store.upsert(
            COLLECTION_CODE_DOCS,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.debug(f"[MemoryService] Indexed file: {path}")
        return point_id

    def search_code(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search code_docs collection.

        Args:
            query: Search query (natural language or code snippet)
            project_id: Project to search within
            limit: Max results (default: top_k from config)

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        return self.store.search(
            COLLECTION_CODE_DOCS,
            query_vector,
            filter={"project_id": project_id},
            limit=limit,
        )

    # -------------------------------------------------------------------------
    # Run Summaries
    # -------------------------------------------------------------------------

    def write_phase_summary(
        self,
        run_id: str,
        phase_id: str,
        project_id: str,
        summary: str,
        changes: List[str],
        ci_result: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> str:
        """
        Write a phase summary to run_summaries collection.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            project_id: Project identifier
            summary: Short summary text
            changes: List of changed files
            ci_result: CI/test result (pass/fail/skip)
            task_type: Task type (e.g., "feature", "bugfix")

        Returns:
            Point ID
        """
        if not self.enabled:
            return ""

        text = f"Phase {phase_id}: {summary}\nChanges: {', '.join(changes)}\nCI: {ci_result or 'N/A'}"
        vector = sync_embed_text(text)

        point_id = f"summary:{run_id}:{phase_id}"
        payload = {
            "type": "summary",
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "task_type": task_type,
            "summary": summary,
            "changes": changes,
            "ci_result": ci_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.store.upsert(
            COLLECTION_RUN_SUMMARIES,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info(f"[MemoryService] Wrote phase summary: {phase_id}")
        return point_id

    def search_summaries(
        self,
        query: str,
        project_id: str,
        run_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search run_summaries collection."""
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        filter_dict = {"project_id": project_id}
        if run_id:
            filter_dict["run_id"] = run_id
        return self.store.search(
            COLLECTION_RUN_SUMMARIES,
            query_vector,
            filter=filter_dict,
            limit=limit,
        )

    # -------------------------------------------------------------------------
    # Errors/CI
    # -------------------------------------------------------------------------

    def write_error(
        self,
        run_id: str,
        phase_id: str,
        project_id: str,
        error_text: str,
        error_type: Optional[str] = None,
        test_name: Optional[str] = None,
    ) -> str:
        """
        Write an error/CI failure to errors_ci collection.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            project_id: Project identifier
            error_text: Error message/traceback
            error_type: Error category (e.g., "test_failure", "syntax_error")
            test_name: Failing test name (if applicable)

        Returns:
            Point ID
        """
        if not self.enabled:
            return ""

        text = f"Error in {phase_id}: {error_text[:2000]}"
        if test_name:
            text = f"Test {test_name} failed: {error_text[:2000]}"
        vector = sync_embed_text(text)

        point_id = f"error:{run_id}:{phase_id}:{hashlib.sha256(error_text.encode()).hexdigest()[:8]}"
        payload = {
            "type": "error",
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "error_type": error_type,
            "test_name": test_name,
            "error_text": error_text[:5000],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.store.upsert(
            COLLECTION_ERRORS_CI,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info(f"[MemoryService] Wrote error: {error_type} in {phase_id}")
        return point_id

    def search_errors(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search errors_ci collection for similar errors."""
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        return self.store.search(
            COLLECTION_ERRORS_CI,
            query_vector,
            filter={"project_id": project_id},
            limit=limit,
        )

    # -------------------------------------------------------------------------
    # Doctor Hints
    # -------------------------------------------------------------------------

    def write_doctor_hint(
        self,
        run_id: str,
        phase_id: str,
        project_id: str,
        hint: str,
        action: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> str:
        """
        Write a doctor hint/action/outcome to doctor_hints collection.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            project_id: Project identifier
            hint: Doctor's hint/recommendation
            action: Action taken (e.g., "replan", "execute_fix")
            outcome: Outcome (e.g., "resolved", "failed")

        Returns:
            Point ID
        """
        if not self.enabled:
            return ""

        text = f"Doctor hint for {phase_id}: {hint}\nAction: {action or 'N/A'}\nOutcome: {outcome or 'pending'}"
        vector = sync_embed_text(text)

        point_id = f"hint:{run_id}:{phase_id}:{hashlib.sha256(hint.encode()).hexdigest()[:8]}"
        payload = {
            "type": "hint",
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "hint": hint,
            "action": action,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.store.upsert(
            COLLECTION_DOCTOR_HINTS,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info(f"[MemoryService] Wrote doctor hint: {action} in {phase_id}")
        return point_id

    def search_doctor_hints(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search doctor_hints collection for similar situations."""
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        return self.store.search(
            COLLECTION_DOCTOR_HINTS,
            query_vector,
            filter={"project_id": project_id},
            limit=limit,
        )

    # -------------------------------------------------------------------------
    # Combined Retrieval (for prompts)
    # -------------------------------------------------------------------------

    def retrieve_context(
        self,
        query: str,
        project_id: str,
        run_id: Optional[str] = None,
        task_type: Optional[str] = None,
        include_code: bool = True,
        include_summaries: bool = True,
        include_errors: bool = True,
        include_hints: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve combined context from all collections.

        Args:
            query: Search query
            project_id: Project to search within
            run_id: Optional run to scope summaries
            task_type: Optional task type filter
            include_*: Flags to include/exclude collections

        Returns:
            Dict with keys: "code", "summaries", "errors", "hints"
        """
        if not self.enabled:
            return {"code": [], "summaries": [], "errors": [], "hints": []}

        results = {}

        if include_code:
            results["code"] = self.search_code(query, project_id)

        if include_summaries:
            results["summaries"] = self.search_summaries(query, project_id, run_id)

        if include_errors:
            results["errors"] = self.search_errors(query, project_id)

        if include_hints:
            results["hints"] = self.search_doctor_hints(query, project_id)

        return results

    def format_retrieved_context(
        self,
        retrieved: Dict[str, List[Dict[str, Any]]],
        max_chars: int = 8000,
    ) -> str:
        """
        Format retrieved context for inclusion in prompts.

        Args:
            retrieved: Output from retrieve_context()
            max_chars: Maximum total characters

        Returns:
            Formatted string for prompt inclusion
        """
        sections = []
        char_count = 0

        # Code snippets
        if retrieved.get("code"):
            code_section = ["## Relevant Code"]
            for item in retrieved["code"][:3]:
                payload = item.get("payload", {})
                path = payload.get("path", "unknown")
                preview = payload.get("content_preview", "")[:500]
                entry = f"### {path}\n```\n{preview}\n```"
                if char_count + len(entry) > max_chars:
                    break
                code_section.append(entry)
                char_count += len(entry)
            if len(code_section) > 1:
                sections.append("\n".join(code_section))

        # Previous summaries
        if retrieved.get("summaries"):
            summary_section = ["## Previous Phase Summaries"]
            for item in retrieved["summaries"][:2]:
                payload = item.get("payload", {})
                phase = payload.get("phase_id", "unknown")
                summary = payload.get("summary", "")
                entry = f"- Phase {phase}: {summary}"
                if char_count + len(entry) > max_chars:
                    break
                summary_section.append(entry)
                char_count += len(entry)
            if len(summary_section) > 1:
                sections.append("\n".join(summary_section))

        # Similar errors
        if retrieved.get("errors"):
            error_section = ["## Similar Past Errors"]
            for item in retrieved["errors"][:2]:
                payload = item.get("payload", {})
                error_type = payload.get("error_type", "unknown")
                error_text = payload.get("error_text", "")[:300]
                entry = f"- {error_type}: {error_text}"
                if char_count + len(entry) > max_chars:
                    break
                error_section.append(entry)
                char_count += len(entry)
            if len(error_section) > 1:
                sections.append("\n".join(error_section))

        # Doctor hints
        if retrieved.get("hints"):
            hint_section = ["## Previous Doctor Hints"]
            for item in retrieved["hints"][:2]:
                payload = item.get("payload", {})
                hint = payload.get("hint", "")[:300]
                outcome = payload.get("outcome", "")
                entry = f"- Hint: {hint} (Outcome: {outcome})"
                if char_count + len(entry) > max_chars:
                    break
                hint_section.append(entry)
                char_count += len(entry)
            if len(hint_section) > 1:
                sections.append("\n".join(hint_section))

        return "\n\n".join(sections) if sections else ""
