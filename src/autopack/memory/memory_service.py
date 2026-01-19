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
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import hashlib
import yaml

from .embeddings import sync_embed_text, EMBEDDING_SIZE, MAX_EMBEDDING_CHARS
from .faiss_store import FaissStore
from .qdrant_store import QdrantStore, QDRANT_AVAILABLE

logger = logging.getLogger(__name__)

# Collection names (per plan)
COLLECTION_CODE_DOCS = "code_docs"
COLLECTION_RUN_SUMMARIES = "run_summaries"
COLLECTION_ERRORS_CI = "errors_ci"
COLLECTION_DOCTOR_HINTS = "doctor_hints"
COLLECTION_PLANNING = "planning"
COLLECTION_SOT_DOCS = "sot_docs"

ALL_COLLECTIONS = [
    COLLECTION_CODE_DOCS,
    COLLECTION_RUN_SUMMARIES,
    COLLECTION_ERRORS_CI,
    COLLECTION_DOCTOR_HINTS,
    COLLECTION_PLANNING,
    COLLECTION_SOT_DOCS,
]

_BOOL_TRUE = {"1", "true", "yes", "y", "on"}
_BOOL_FALSE = {"0", "false", "no", "n", "off"}


class NullStore:
    """No-op store used when memory is disabled."""

    def __init__(self) -> None:
        logger.warning(
            "[MemoryService] NullStore initialized: Memory is disabled. "
            "All memory operations will return empty results. "
            "Set enable_memory=true to enable persistence."
        )

    def ensure_collection(self, name: str, size: int = 1536) -> None:  # noqa: ARG002
        return None

    def upsert(self, collection: str, points: List[Dict[str, Any]]) -> int:  # noqa: ARG002
        return 0

    def search(  # noqa: ARG002
        self,
        collection: str,
        query_vector: List[float],
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        return []

    def scroll(  # noqa: ARG002
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return []

    def delete(self, collection: str, ids: List[str]) -> int:  # noqa: ARG002
        return 0

    def count(
        self, collection: str, filter: Optional[Dict[str, Any]] = None
    ) -> int:  # noqa: ARG002
        return 0

    def get_payload(
        self, collection: str, point_id: str
    ) -> Optional[Dict[str, Any]]:  # noqa: ARG002
        return None

    def update_payload(
        self, collection: str, point_id: str, payload: Dict[str, Any]
    ) -> bool:  # noqa: ARG002
        return False


def _parse_bool_env(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    v = value.strip().lower()
    if v in _BOOL_TRUE:
        return True
    if v in _BOOL_FALSE:
        return False
    return None


def _find_repo_root() -> Path:
    """Best-effort repo root discovery (for docker-compose.yml lookup)."""
    # memory_service.py -> autopack/memory/ -> src/ -> repo root
    return Path(__file__).resolve().parents[3]


def _is_localhost(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in {"localhost", "127.0.0.1", "::1"}


def _tcp_reachable(host: str, port: int, timeout_s: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except Exception:
        return False


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _docker_compose_cmd() -> Optional[List[str]]:
    """Return a usable docker compose command, if present."""
    # Prefer `docker compose`
    try:
        r = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return ["docker", "compose"]
    except Exception:
        pass
    # Fallback `docker-compose`
    try:
        r = subprocess.run(
            ["docker-compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return ["docker-compose"]
    except Exception:
        pass
    return None


# Default pinned Qdrant image (determinism; must match docker-compose.yml)
DEFAULT_QDRANT_IMAGE = "qdrant/qdrant:v1.12.5"


def _autostart_qdrant_if_needed(
    *,
    host: str,
    port: int,
    timeout_seconds: int,
    enabled: bool,
    qdrant_image: str = DEFAULT_QDRANT_IMAGE,
) -> bool:
    """
    Attempt to start Qdrant automatically (docker compose preferred) and wait for readiness.

    Returns True if Qdrant becomes reachable, False otherwise.
    """
    if not enabled:
        return False

    # Autostart is only safe for localhost usage. If host is a remote service or a docker
    # network hostname, we shouldn't try to start it locally.
    if not _is_localhost(host):
        return False

    # If already reachable, nothing to do.
    if _tcp_reachable(host, port, timeout_s=0.4):
        return True

    if not _docker_available():
        return False

    repo_root = _find_repo_root()
    compose_path = repo_root / "docker-compose.yml"

    started = False
    compose_cmd = _docker_compose_cmd()
    if compose_cmd and compose_path.exists():
        try:
            r = subprocess.run(
                [*compose_cmd, "up", "-d", "qdrant"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            started = r.returncode == 0
        except Exception:
            started = False

    if not started:
        # Fallback: docker run / docker start for a named container
        container_name = "autopack-qdrant"
        try:
            # If container exists, start it.
            inspect = subprocess.run(
                ["docker", "inspect", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if inspect.returncode == 0:
                r = subprocess.run(
                    ["docker", "start", container_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                started = r.returncode == 0
            else:
                r = subprocess.run(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--name",
                        container_name,
                        "-p",
                        f"{port}:6333",
                        qdrant_image,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                started = r.returncode == 0
        except Exception:
            started = False

    if not started:
        return False

    # Wait briefly for readiness.
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if _tcp_reachable(host, port, timeout_s=0.4):
            return True
        time.sleep(0.5)

    return False


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

    store: Union[NullStore, "FaissStore", "QdrantStore"]
    backend: str
    enabled: bool
    top_k: int
    max_embed_chars: int
    planning_collection: str

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
        env_enabled = _parse_bool_env(os.getenv("AUTOPACK_ENABLE_MEMORY"))
        self.enabled = config.get("enable_memory", enabled)
        if env_enabled is not None:
            self.enabled = env_enabled
        self.top_k = config.get("top_k_retrieval", 5)
        self.max_embed_chars = config.get("max_embed_chars", MAX_EMBEDDING_CHARS)
        self.planning_collection = config.get("planning_collection", COLLECTION_PLANNING)

        if not self.enabled:
            self.store = NullStore()
            self.backend = "disabled"
            logger.info("[MemoryService] Memory disabled (enable_memory=false)")
            return

        # Determine which backend to use
        if use_qdrant is None:
            use_qdrant = config.get("use_qdrant", False)

        env_use_qdrant = _parse_bool_env(os.getenv("AUTOPACK_USE_QDRANT"))
        if env_use_qdrant is not None:
            use_qdrant = env_use_qdrant

        # Initialize appropriate store
        qdrant_config = config.get("qdrant", {})
        fallback_to_faiss = bool(qdrant_config.get("fallback_to_faiss", True))
        require_qdrant = bool(qdrant_config.get("require", False))
        autostart_default = bool(qdrant_config.get("autostart", False))
        autostart_timeout_seconds = int(qdrant_config.get("autostart_timeout_seconds", 15))

        qdrant_host = os.getenv("AUTOPACK_QDRANT_HOST") or qdrant_config.get("host", "localhost")
        qdrant_port = int(os.getenv("AUTOPACK_QDRANT_PORT") or qdrant_config.get("port", 6333))
        qdrant_api_key = (
            os.getenv("AUTOPACK_QDRANT_API_KEY") or qdrant_config.get("api_key") or ""
        ).strip() or None
        env_qdrant_prefer_grpc = _parse_bool_env(os.getenv("AUTOPACK_QDRANT_PREFER_GRPC"))
        qdrant_prefer_grpc = (
            env_qdrant_prefer_grpc
            if env_qdrant_prefer_grpc is not None
            else bool(qdrant_config.get("prefer_grpc", False))
        )
        qdrant_timeout = int(
            os.getenv("AUTOPACK_QDRANT_TIMEOUT") or qdrant_config.get("timeout", 60)
        )

        env_autostart = _parse_bool_env(os.getenv("AUTOPACK_QDRANT_AUTOSTART"))
        autostart_enabled = env_autostart if env_autostart is not None else autostart_default
        try:
            autostart_timeout_seconds = int(
                os.getenv("AUTOPACK_QDRANT_AUTOSTART_TIMEOUT") or autostart_timeout_seconds
            )
        except Exception:
            autostart_timeout_seconds = autostart_timeout_seconds

        # Pinned image for autostart fallback (determinism). Env override supported.
        qdrant_image = os.getenv("AUTOPACK_QDRANT_IMAGE") or qdrant_config.get(
            "image", DEFAULT_QDRANT_IMAGE
        )

        if use_qdrant and QDRANT_AVAILABLE:
            try:
                self.store = QdrantStore(
                    host=qdrant_host,
                    port=qdrant_port,
                    api_key=qdrant_api_key,
                    prefer_grpc=qdrant_prefer_grpc,
                    timeout=qdrant_timeout,
                )
                self.backend = "qdrant"
                logger.info("[MemoryService] Using Qdrant backend")
            except Exception as exc:
                # If Qdrant is desired but not reachable, try to start it automatically (when local).
                if _autostart_qdrant_if_needed(
                    host=str(qdrant_host),
                    port=int(qdrant_port),
                    timeout_seconds=autostart_timeout_seconds,
                    enabled=autostart_enabled,
                    qdrant_image=qdrant_image,
                ):
                    try:
                        self.store = QdrantStore(
                            host=qdrant_host,
                            port=qdrant_port,
                            api_key=qdrant_api_key,
                            prefer_grpc=qdrant_prefer_grpc,
                            timeout=qdrant_timeout,
                        )
                        self.backend = "qdrant"
                        logger.info(
                            "[MemoryService] Qdrant autostart succeeded; using Qdrant backend"
                        )
                        return
                    except Exception:
                        # Fall through to existing policy (require vs fallback)
                        pass

                if require_qdrant or not fallback_to_faiss:
                    raise
                logger.warning(
                    f"[MemoryService] Qdrant unavailable at {qdrant_host}:{qdrant_port}; "
                    f"falling back to FAISS ({exc})"
                )
                if index_dir is None:
                    index_dir = config.get(
                        "faiss_index_path", ".autonomous_runs/file-organizer-app-v1/.faiss"
                    )
                self.store = FaissStore(index_dir=index_dir)
                self.backend = "faiss"
        elif use_qdrant and not QDRANT_AVAILABLE:
            logger.warning(
                "[MemoryService] Qdrant requested but not available; falling back to FAISS"
            )
            if index_dir is None:
                index_dir = config.get(
                    "faiss_index_path", ".autonomous_runs/file-organizer-app-v1/.faiss"
                )
            self.store = FaissStore(index_dir=index_dir)
            self.backend = "faiss"
        else:
            # Use FAISS
            if index_dir is None:
                index_dir = config.get(
                    "faiss_index_path", ".autonomous_runs/file-organizer-app-v1/.faiss"
                )
            self.store = FaissStore(index_dir=index_dir)
            self.backend = "faiss"
            logger.info("[MemoryService] Using FAISS backend")

        # Ensure all collections exist
        collections = list(ALL_COLLECTIONS)
        if self.planning_collection not in collections:
            collections.append(self.planning_collection)

        try:
            for collection in collections:
                self.store.ensure_collection(collection, EMBEDDING_SIZE)
        except Exception as exc:
            # If Qdrant became unavailable during init, prefer a clean FAISS fallback
            # rather than disabling memory entirely.
            if self.backend == "qdrant" and fallback_to_faiss and not require_qdrant:
                logger.warning(
                    f"[MemoryService] Qdrant init failed during collection setup; falling back to FAISS ({exc})"
                )
                if index_dir is None:
                    index_dir = config.get(
                        "faiss_index_path", ".autonomous_runs/file-organizer-app-v1/.faiss"
                    )
                self.store = FaissStore(index_dir=index_dir)
                self.backend = "faiss"
                for collection in collections:
                    self.store.ensure_collection(collection, EMBEDDING_SIZE)
            else:
                raise

        logger.info(
            f"[MemoryService] Initialized (backend={self.backend}, enabled={self.enabled}, top_k={self.top_k})"
        )

    def _safe_store_call(self, label: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            logger.warning(f"[MemoryService] {label} failed; continuing without memory op: {exc}")
            return default

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
        content_truncated = content[: self.max_embed_chars]
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

        self._safe_store_call(
            "index_file/upsert",
            lambda: self.store.upsert(
                COLLECTION_CODE_DOCS,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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
        return self._safe_store_call(
            "search_code/search",
            lambda: self.store.search(
                COLLECTION_CODE_DOCS,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
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

        text = (
            f"Phase {phase_id}: {summary}\nChanges: {', '.join(changes)}\nCI: {ci_result or 'N/A'}"
        )
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

        self._safe_store_call(
            "write_phase_summary/upsert",
            lambda: self.store.upsert(
                COLLECTION_RUN_SUMMARIES,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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
        return self._safe_store_call(
            "search_summaries/search",
            lambda: self.store.search(
                COLLECTION_RUN_SUMMARIES,
                query_vector,
                filter=filter_dict,
                limit=limit,
            ),
            [],
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

        point_id = (
            f"error:{run_id}:{phase_id}:{hashlib.sha256(error_text.encode()).hexdigest()[:8]}"
        )
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

        self._safe_store_call(
            "write_error/upsert",
            lambda: self.store.upsert(
                COLLECTION_ERRORS_CI,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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
        return self._safe_store_call(
            "search_errors/search",
            lambda: self.store.search(
                COLLECTION_ERRORS_CI,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
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

        self._safe_store_call(
            "write_doctor_hint/upsert",
            lambda: self.store.upsert(
                COLLECTION_DOCTOR_HINTS,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
        )
        logger.info(f"[MemoryService] Wrote doctor hint: {action} in {phase_id}")
        return point_id

    def write_telemetry_insight(
        self,
        insight: Dict[str, Any],
        project_id: Optional[str] = None,
    ) -> str:
        """Write a telemetry insight to appropriate memory collection.

        This is a convenience method that routes to write_phase_summary, write_error,
        or write_doctor_hint based on insight type.

        Args:
            insight: TelemetryInsight object to persist
            project_id: Optional project ID for namespacing

        Returns:
            Document ID of written insight
        """
        if not self.enabled:
            return ""

        insight_type = insight.get("insight_type", "unknown")
        description = insight.get("description", "")
        phase_id = insight.get("phase_id", "unknown")
        run_id = insight.get("run_id", "telemetry")
        suggested_action = insight.get("suggested_action")

        # Route to appropriate write method based on insight type
        if insight_type == "cost_sink":
            return self.write_phase_summary(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id or "default",
                summary=f"Cost sink detected: {description}",
                changes=[],
                ci_result=None,
                task_type="telemetry_insight",
            )
        elif insight_type == "failure_mode":
            return self.write_error(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id or "default",
                error_text=f"Recurring failure: {suggested_action or description}",
                error_type=description,
                test_name=None,
            )
        elif insight_type == "retry_cause":
            return self.write_doctor_hint(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id or "default",
                hint=suggested_action or description,
                action="telemetry_insight",
                outcome="pending",
            )
        else:
            # Generic write to phase summary
            return self.write_phase_summary(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id or "default",
                summary=f"Telemetry insight: {description}",
                changes=[],
                ci_result=None,
                task_type="telemetry_insight",
            )

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
        return self._safe_store_call(
            "search_doctor_hints/search",
            lambda: self.store.search(
                COLLECTION_DOCTOR_HINTS,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
        )

    # -------------------------------------------------------------------------
    # SOT (Source of Truth) Indexing
    # -------------------------------------------------------------------------

    def index_sot_docs(
        self,
        project_id: str,
        workspace_root: Path,
        docs_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Index SOT documentation files into vector memory.

        Indexes the canonical SOT files:
        - BUILD_HISTORY.md
        - DEBUG_LOG.md
        - ARCHITECTURE_DECISIONS.md
        - FUTURE_PLAN.md
        - PROJECT_INDEX.json (field-selective)
        - LEARNED_RULES.json (field-selective)

        Args:
            project_id: Project identifier
            workspace_root: Path to project workspace root
            docs_dir: Optional explicit docs directory path (defaults to workspace_root/docs)

        Returns:
            Dict with indexing statistics: {"indexed": N, "skipped": bool}
        """
        from .sot_indexing import chunk_sot_file, chunk_sot_json
        from ..config import settings

        if not self.enabled:
            return {"indexed": 0, "skipped": True, "reason": "memory_disabled"}

        if not settings.autopack_enable_sot_memory_indexing:
            return {"indexed": 0, "skipped": True, "reason": "sot_indexing_disabled"}

        docs_dir = docs_dir or (workspace_root / "docs")
        if not docs_dir.exists():
            return {"indexed": 0, "skipped": True, "reason": "docs_dir_not_found"}

        # Define SOT files to index (markdown files)
        sot_markdown_files = {
            "BUILD_HISTORY.md": docs_dir / "BUILD_HISTORY.md",
            "DEBUG_LOG.md": docs_dir / "DEBUG_LOG.md",
            "ARCHITECTURE_DECISIONS.md": docs_dir / "ARCHITECTURE_DECISIONS.md",
            "FUTURE_PLAN.md": docs_dir / "FUTURE_PLAN.md",
        }

        # Define SOT JSON files (use field-selective chunking)
        sot_json_files = {
            "PROJECT_INDEX.json": docs_dir / "PROJECT_INDEX.json",
            "LEARNED_RULES.json": docs_dir / "LEARNED_RULES.json",
        }

        indexed_count = 0
        max_chars = settings.autopack_sot_chunk_max_chars
        overlap_chars = settings.autopack_sot_chunk_overlap_chars

        # Index markdown files
        for sot_file, file_path in sot_markdown_files.items():
            if not file_path.exists():
                logger.debug(f"[MemoryService] SOT file not found: {sot_file}")
                continue

            # Chunk the file
            chunk_docs = chunk_sot_file(
                file_path,
                project_id,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )

            if not chunk_docs:
                continue

            # Create points with embeddings (skip existing chunks to avoid re-embedding)
            points = []
            skipped_existing = 0
            for doc in chunk_docs:
                try:
                    # Check if point already exists
                    existing = self._safe_store_call(
                        f"index_sot_docs/{sot_file}/get_payload",
                        lambda: self.store.get_payload(COLLECTION_SOT_DOCS, doc["id"]),
                        None,
                    )
                    if existing:
                        skipped_existing += 1
                        continue

                    # Embed and add to points
                    vector = sync_embed_text(doc["content"])
                    points.append(
                        {
                            "id": doc["id"],
                            "vector": vector,
                            "payload": doc["metadata"],
                        }
                    )
                except Exception as e:
                    logger.warning(f"[MemoryService] Failed to embed SOT chunk: {e}")
                    continue

            if skipped_existing > 0:
                logger.debug(
                    f"[MemoryService] Skipped {skipped_existing} existing chunks from {sot_file}"
                )

            # Upsert to store
            if points:
                self._safe_store_call(
                    f"index_sot_docs/{sot_file}/upsert",
                    lambda: self.store.upsert(COLLECTION_SOT_DOCS, points),
                    0,
                )
                indexed_count += len(points)
                logger.info(f"[MemoryService] Indexed {len(points)} chunks from {sot_file}")

        # Index JSON files with field-selective chunking
        for sot_file, file_path in sot_json_files.items():
            if not file_path.exists():
                logger.debug(f"[MemoryService] SOT file not found: {sot_file}")
                continue

            # Chunk the JSON file
            chunk_docs = chunk_sot_json(
                file_path,
                project_id,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )

            if not chunk_docs:
                continue

            # Create points with embeddings (skip existing chunks to avoid re-embedding)
            points = []
            skipped_existing = 0
            for doc in chunk_docs:
                try:
                    # Check if point already exists
                    existing = self._safe_store_call(
                        f"index_sot_docs/{sot_file}/get_payload",
                        lambda: self.store.get_payload(COLLECTION_SOT_DOCS, doc["id"]),
                        None,
                    )
                    if existing:
                        skipped_existing += 1
                        continue

                    # Embed and add to points
                    vector = sync_embed_text(doc["content"])
                    points.append(
                        {
                            "id": doc["id"],
                            "vector": vector,
                            "payload": doc["metadata"],
                        }
                    )
                except Exception as e:
                    logger.warning(f"[MemoryService] Failed to embed SOT JSON chunk: {e}")
                    continue

            if skipped_existing > 0:
                logger.debug(
                    f"[MemoryService] Skipped {skipped_existing} existing JSON chunks from {sot_file}"
                )

            # Upsert to store
            if points:
                self._safe_store_call(
                    f"index_sot_docs/{sot_file}/upsert",
                    lambda: self.store.upsert(COLLECTION_SOT_DOCS, points),
                    0,
                )
                indexed_count += len(points)
                logger.info(f"[MemoryService] Indexed {len(points)} JSON chunks from {sot_file}")

        return {
            "indexed": indexed_count,
            "skipped": False,
        }

    def search_sot(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search SOT docs collection.

        Args:
            query: Search query
            project_id: Project to search within
            limit: Max results (default: top_k from config)

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)
        return self._safe_store_call(
            "search_sot/search",
            lambda: self.store.search(
                COLLECTION_SOT_DOCS,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
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

        content_truncated = content[: self.max_embed_chars]
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

        self._safe_store_call(
            "write_planning_artifact/upsert",
            lambda: self.store.upsert(
                self.planning_collection,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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

        self._safe_store_call(
            "write_plan_change/upsert",
            lambda: self.store.upsert(
                self.planning_collection,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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

        self._safe_store_call(
            "write_decision_log/upsert",
            lambda: self.store.upsert(
                self.planning_collection,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
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
        results = self._safe_store_call(
            "search_planning/search",
            lambda: self.store.search(
                self.planning_collection,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
        )
        if types:
            results = [r for r in results if r.get("payload", {}).get("type") in types]
        return results

    def latest_plan_change(self, project_id: str) -> List[Dict[str, Any]]:
        """Return latest plan changes (sorted newest first)."""
        docs = self._safe_store_call(
            "latest_plan_change/scroll",
            lambda: self.store.scroll(
                self.planning_collection,
                filter={"project_id": project_id},
                limit=500,
            ),
            [],
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
            payload = self._safe_store_call(
                "tombstone_entry/get_payload",
                lambda: self.store.get_payload(collection, point_id),
                None,
            )
            if payload is None:
                return False
            payload.update(
                {
                    "status": "tombstoned",
                    "tombstone_reason": reason,
                    "replaced_by": replaced_by or payload.get("replaced_by"),
                }
            )
            return bool(
                self._safe_store_call(
                    "tombstone_entry/update_payload",
                    lambda: self.store.update_payload(collection, point_id, payload),
                    False,
                )
            )
        except Exception as exc:
            logger.warning(f"[MemoryService] Failed to tombstone {point_id}: {exc}")
            return False

    # -------------------------------------------------------------------------
    # Insights Retrieval (for ROAD-C task generation)
    # -------------------------------------------------------------------------

    def retrieve_insights(
        self,
        query: str,
        limit: int = 10,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve insights from memory for task generation (IMP-ARCH-010/016).

        This method is called by the ROAD-C AutonomousTaskGenerator to retrieve
        telemetry insights that can be converted into improvement tasks.

        IMP-ARCH-016: Fixed to query across collections where telemetry insights
        are actually written (run_summaries, errors_ci, doctor_hints) and filter
        for task_type="telemetry_insight".

        Args:
            query: Search query to find relevant insights
            limit: Maximum number of results to return
            project_id: Optional project ID to filter by

        Returns:
            List of insight dictionaries with content, metadata, and score
        """
        if not self.enabled:
            logger.debug("[MemoryService] Memory disabled, returning empty insights")
            return []

        try:
            # Embed the query text
            query_vector = sync_embed_text(query)

            # Collections where write_telemetry_insight routes data
            insight_collections = [
                COLLECTION_RUN_SUMMARIES,  # cost_sink and generic insights
                COLLECTION_ERRORS_CI,  # failure_mode insights
                COLLECTION_DOCTOR_HINTS,  # retry_cause insights
            ]

            all_insights = []
            per_collection_limit = max(limit // len(insight_collections), 3)

            for collection in insight_collections:
                # Build filter for telemetry insights
                search_filter = {"task_type": "telemetry_insight"}
                if project_id:
                    search_filter["project_id"] = project_id

                results = self._safe_store_call(
                    f"retrieve_insights/{collection}",
                    lambda col=collection, flt=search_filter: self.store.search(
                        collection=col,
                        query_vector=query_vector,
                        filter=flt,
                        limit=per_collection_limit,
                    ),
                    [],
                )

                for result in results:
                    payload = getattr(result, "payload", {}) or {}
                    # Only include telemetry insights
                    if payload.get("task_type") != "telemetry_insight":
                        continue

                    insight = {
                        "id": getattr(result, "id", None),
                        "content": payload.get("content", payload.get("summary", "")),
                        "metadata": payload,
                        "score": getattr(result, "score", 0.0),
                        "issue_type": payload.get("issue_type", "unknown"),
                        "severity": payload.get("severity", "medium"),
                        "file_path": payload.get("file_path"),
                        "collection": collection,
                    }
                    all_insights.append(insight)

            # Sort by score and limit
            all_insights.sort(key=lambda x: x.get("score", 0), reverse=True)
            insights = all_insights[:limit]

            logger.debug(
                f"[MemoryService] Retrieved {len(insights)} insights for query: {query[:50]}..."
            )
            return insights

        except Exception as e:
            logger.warning(f"[MemoryService] Failed to retrieve insights: {e}")
            return []

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
        include_sot: bool = False,
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
            include_sot: Include SOT (Source of Truth) documentation chunks

        Returns:
            Dict with keys: "code", "summaries", "errors", "hints", "planning", "plan_changes", "decisions", "sot"
        """
        from ..config import settings

        if not self.enabled:
            return {
                "code": [],
                "summaries": [],
                "errors": [],
                "hints": [],
                "planning": [],
                "plan_changes": [],
                "decisions": [],
                "sot": [],
            }

        # Initialize results with all possible keys (consistent structure)
        results: Dict[str, List[Dict[str, Any]]] = {
            "code": [],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }
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

        if include_sot and settings.autopack_sot_retrieval_enabled:
            sot_limit = settings.autopack_sot_retrieval_top_k
            results["sot"] = self.search_sot(query, project_id, limit=sot_limit)

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
        from ..config import settings

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

        # SOT documentation chunks (respects max_chars limit from settings)
        if retrieved.get("sot"):
            sot_section = ["## Relevant Documentation (SOT)"]
            sot_max_chars = settings.autopack_sot_retrieval_max_chars
            sot_char_count = 0

            for item in retrieved["sot"]:
                payload = item.get("payload", {})
                sot_file = payload.get("sot_file", "unknown")
                heading = payload.get("heading") or "No heading"
                content_preview = payload.get("content_preview", "")[:600]

                entry = f"### {sot_file} - {heading}\n```\n{content_preview}\n```"

                # Check both global max_chars and SOT-specific max_chars
                if (char_count + len(entry) > max_chars) or (
                    sot_char_count + len(entry) > sot_max_chars
                ):
                    break

                sot_section.append(entry)
                char_count += len(entry)
                sot_char_count += len(entry)

            if len(sot_section) > 1:
                sections.append("\n".join(sot_section))

        return "\n\n".join(sections) if sections else ""
