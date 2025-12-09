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
from .qdrant_store import QdrantStore, QDRANT_AVAILABLE

logger = logging.getLogger(__name__)

# Collection names (per plan)
COLLECTION_CODE_DOCS = "code_docs"
COLLECTION_RUN_SUMMARIES = "run_summaries"
COLLECTION_ERRORS_CI = "errors_ci"
COLLECTION_DOCTOR_HINTS = "doctor_hints"
COLLECTION_PLANNING = "planning"

ALL_COLLECTIONS = [
    COLLECTION_CODE_DOCS,
    COLLECTION_RUN_SUMMARIES,
    COLLECTION_ERRORS_CI,
    COLLECTION_DOCTOR_HINTS,
    COLLECTION_PLANNING,
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
        use_qdrant: Optional[bool] = None,
    ):
        """
        Initialize memory service.

        Args:
            index_dir: Directory for FAISS indices (default from config or .faiss)
            enabled: Whether memory is enabled
            use_qdrant: Use Qdrant instead of FAISS (default from config)
        """
        config = _load_memory_config()
        self.enabled = config.get("enable_memory", enabled)
        self.top_k = config.get("top_k_retrieval", 5)
        self.max_embed_chars = config.get("max_embed_chars", MAX_EMBEDDING_CHARS)
        self.planning_collection = config.get("planning_collection", COLLECTION_PLANNING)

        # Determine which backend to use
        if use_qdrant is None:
            use_qdrant = config.get("use_qdrant", False)

        # Initialize appropriate store
        if use_qdrant and QDRANT_AVAILABLE:
            qdrant_config = config.get("qdrant", {})
            self.store = QdrantStore(
                host=qdrant_config.get("host", "localhost"),
                port=qdrant_config.get("port", 6333),
                api_key=qdrant_config.get("api_key") or None,
                prefer_grpc=qdrant_config.get("prefer_grpc", False),
                timeout=qdrant_config.get("timeout", 60),
            )
            self.backend = "qdrant"
            logger.info("[MemoryService] Using Qdrant backend")
        elif use_qdrant and not QDRANT_AVAILABLE:
            logger.warning(
                "[MemoryService] Qdrant requested but not available; falling back to FAISS"
            )
            if index_dir is None:
                index_dir = config.get(
                    "faiss_index_path",
                    ".autonomous_runs/file-organizer-app-v1/.faiss"
                )
            self.store = FaissStore(index_dir=index_dir)
            self.backend = "faiss"
        else:
            # Use FAISS
            if index_dir is None:
                index_dir = config.get(
                    "faiss_index_path",
                    ".autonomous_runs/file-organizer-app-v1/.faiss"
                )
            self.store = FaissStore(index_dir=index_dir)
            self.backend = "faiss"
            logger.info("[MemoryService] Using FAISS backend")

        # Ensure all collections exist
        collections = list(ALL_COLLECTIONS)
        if self.planning_collection not in collections:
            collections.append(self.planning_collection)

        for collection in collections:
            self.store.ensure_collection(collection, EMBEDDING_SIZE)

        logger.info(
            f"[MemoryService] Initialized (backend={self.backend}, enabled={self.enabled}, top_k={self.top_k})"
        )

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
    # Planning artifacts / plan changes / decision log
    # -------------------------------------------------------------------------

    def write_planning_artifact(
        self,
        path: str,
        content: str,
        project_id: str,
        version: int,
        author: Optional[str] = None,
        reason: Optional[str] = None,
        summary: Optional[str] = None,
        status: str = "active",
        replaced_by: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """Embed a planning artifact (templates/prompts/compiled plans)."""
        if not self.enabled:
            return ""

        content_truncated = content[:self.max_embed_chars]
        summary_text = (summary or content_truncated[:600]).strip()
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()

        vector = sync_embed_text(
            f"Planning artifact {path} v{version}\nSummary: {summary_text}\n\n{content_truncated[:1500]}"
        )
        point_id = f"planning_artifact:{project_id}:{path}:{version}"
        payload = {
            "type": "planning_artifact",
            "path": path,
            "version": version,
            "project_id": project_id,
            "timestamp": timestamp,
            "author": author,
            "reason": reason,
            "status": status,
            "replaced_by": replaced_by,
            "summary": summary_text,
            "content_preview": content_truncated[:800],
        }

        self.store.upsert(
            self.planning_collection,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info(f"[MemoryService] Stored planning artifact {path} v{version}")
        return point_id

    def write_plan_change(
        self,
        summary: str,
        rationale: str,
        project_id: str,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        replaces_version: Optional[int] = None,
        author: Optional[str] = None,
        status: str = "active",
        replaced_by: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """Embed a plan change (diff/summary) entry."""
        if not self.enabled:
            return ""

        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        text = f"Plan change summary: {summary}\nRationale: {rationale}"
        vector = sync_embed_text(text)
        point_id = f"plan_change:{project_id}:{run_id or 'na'}:{phase_id or 'na'}:{hashlib.sha256(text.encode()).hexdigest()[:8]}"
        payload = {
            "type": "plan_change",
            "summary": summary,
            "rationale": rationale,
            "project_id": project_id,
            "run_id": run_id,
            "phase_id": phase_id,
            "replaces_version": replaces_version,
            "status": status,
            "replaced_by": replaced_by,
            "timestamp": timestamp,
        }

        self.store.upsert(
            self.planning_collection,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info("[MemoryService] Stored plan change")
        return point_id

    def write_decision_log(
        self,
        trigger: str,
        choice: str,
        rationale: str,
        project_id: str,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        alternatives: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """Embed a decision log summary for recall."""
        if not self.enabled:
            return ""

        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        text = (
            f"Decision for {phase_id or 'phase'}: {choice}\n"
            f"Trigger: {trigger}\n"
            f"Alternatives: {alternatives or 'n/a'}\n"
            f"Rationale: {rationale}"
        )
        vector = sync_embed_text(text)
        point_id = f"decision:{project_id}:{run_id or 'na'}:{phase_id or 'na'}:{hashlib.sha256(text.encode()).hexdigest()[:8]}"
        payload = {
            "type": "decision_log",
            "trigger": trigger,
            "choice": choice,
            "alternatives": alternatives,
            "rationale": rationale,
            "project_id": project_id,
            "run_id": run_id,
            "phase_id": phase_id,
            "timestamp": timestamp,
        }

        self.store.upsert(
            self.planning_collection,
            [{"id": point_id, "vector": vector, "payload": payload}],
        )
        logger.info("[MemoryService] Stored decision log")
        return point_id

    def search_planning(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
        types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search planning collection (artifacts, plan changes, decisions)."""
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        results = self.store.search(
            self.planning_collection,
            query_vector,
            filter={"project_id": project_id},
            limit=limit,
        )
        if types:
            results = [r for r in results if r.get("payload", {}).get("type") in types]
        return results

    def latest_plan_change(self, project_id: str) -> List[Dict[str, Any]]:
        """Return latest plan changes (sorted newest first)."""
        docs = self.store.scroll(
            self.planning_collection,
            filter={"project_id": project_id},
            limit=500,
        )
        plan_changes = []
        for d in docs:
            payload = d.get("payload", {})
            if payload.get("type") != "plan_change":
                continue
            status = payload.get("status")
            if status in ("tombstoned", "superseded", "archived"):
                continue
            plan_changes.append(d)
        plan_changes.sort(
            key=lambda d: d.get("payload", {}).get("timestamp", ""),
            reverse=True,
        )
        return plan_changes

    def tombstone_entry(
        self,
        collection: str,
        point_id: str,
        reason: Optional[str] = None,
        replaced_by: Optional[str] = None,
    ) -> bool:
        """Mark an entry as tombstoned without deleting its vector."""
        try:
            payload = self.store.get_payload(collection, point_id)
            if payload is None:
                return False
            payload.update(
                {
                    "status": "tombstoned",
                    "tombstone_reason": reason,
                    "replaced_by": replaced_by or payload.get("replaced_by"),
                }
            )
            return self.store.update_payload(collection, point_id, payload)
        except Exception as exc:
            logger.warning(f"[MemoryService] Failed to tombstone {point_id}: {exc}")
            return False

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
        include_planning: bool = False,
        include_plan_changes: bool = False,
        include_decisions: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve combined context from all collections.

        Args:
            query: Search query
            project_id: Project to search within
            run_id: Optional run to scope summaries
            task_type: Optional task type filter
            include_*: Flags to include/exclude collections
            include_planning: Include planning artifacts
            include_plan_changes: Include most recent plan changes (recency-biased)
            include_decisions: Include decision logs

        Returns:
            Dict with keys: "code", "summaries", "errors", "hints", "planning", "plan_changes", "decisions"
        """
        if not self.enabled:
            return {
                "code": [],
                "summaries": [],
                "errors": [],
                "hints": [],
                "planning": [],
                "plan_changes": [],
                "decisions": [],
            }

        results = {}
        limit = self.top_k

        if include_code:
            results["code"] = self.search_code(query, project_id)

        if include_summaries:
            results["summaries"] = self.search_summaries(query, project_id, run_id)

        if include_errors:
            results["errors"] = self.search_errors(query, project_id)

        if include_hints:
            results["hints"] = self.search_doctor_hints(query, project_id)

        if include_planning:
            results["planning"] = self.search_planning(
                query,
                project_id,
                limit=limit,
                types=["planning_artifact"],
            )

        if include_plan_changes:
            # Bias to latest plan changes first
            results["plan_changes"] = self.latest_plan_change(project_id)[:limit]

        if include_decisions:
            results["decisions"] = self.search_planning(
                query,
                project_id,
                limit=limit,
                types=["decision_log"],
            )

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

        # Planning artifacts (summaries only)
        if retrieved.get("planning"):
            planning_section = ["## Planning Artifacts"]
            for item in retrieved["planning"][:2]:
                payload = item.get("payload", {})
                path = payload.get("path", "unknown")
                version = payload.get("version", "n/a")
                summary = payload.get("summary", "")[:300]
                entry = f"- {path} (v{version}): {summary}"
                if char_count + len(entry) > max_chars:
                    break
                planning_section.append(entry)
                char_count += len(entry)
            if len(planning_section) > 1:
                sections.append("\n".join(planning_section))

        # Plan changes (recency-biased)
        if retrieved.get("plan_changes"):
            plan_change_section = ["## Recent Plan Changes"]
            for item in retrieved["plan_changes"][:2]:
                payload = item.get("payload", {})
                summary = payload.get("summary", "")[:250]
                rationale = payload.get("rationale", "")[:200]
                entry = f"- {summary} (Why: {rationale})"
                if char_count + len(entry) > max_chars:
                    break
                plan_change_section.append(entry)
                char_count += len(entry)
            if len(plan_change_section) > 1:
                sections.append("\n".join(plan_change_section))

        # Decision log
        if retrieved.get("decisions"):
            decision_section = ["## Decisions"]
            for item in retrieved["decisions"][:2]:
                payload = item.get("payload", {})
                trigger = payload.get("trigger", "trigger unknown")
                choice = payload.get("choice", "")
                rationale = payload.get("rationale", "")[:200]
                entry = f"- Trigger: {trigger}; Choice: {choice}; Rationale: {rationale}"
                if char_count + len(entry) > max_chars:
                    break
                decision_section.append(entry)
                char_count += len(entry)
            if len(decision_section) > 1:
                sections.append("\n".join(decision_section))

        return "\n\n".join(sections) if sections else ""
