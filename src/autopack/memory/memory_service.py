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

import hashlib
import logging
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

# IMP-MEM-005: Import retrieval quality tracker for metrics collection
from ..telemetry.meta_metrics import RetrievalQualityTracker
from .embeddings import EMBEDDING_SIZE, MAX_EMBEDDING_CHARS, sync_embed_text
from .faiss_store import FaissStore
from .qdrant_store import QDRANT_AVAILABLE, QdrantStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IMP-MEM-012: Content Compression for Write Path
# ---------------------------------------------------------------------------

# Max content length before compression/truncation is applied
MAX_CONTENT_LENGTH = 5000


def _compress_content(content: str, max_length: int = MAX_CONTENT_LENGTH) -> tuple[str, bool]:
    """Compress or truncate content that exceeds max length.

    IMP-MEM-012: Long entries >5000 chars are compressed before writing
    to prevent unbounded memory growth in vector DB.

    Args:
        content: Content string to potentially compress
        max_length: Maximum allowed length (default: 5000)

    Returns:
        Tuple of (processed_content, was_compressed) where was_compressed
        is True if content was modified
    """
    if len(content) <= max_length:
        return content, False

    # Truncate with preservation of key sections (start and end)
    # Keep first 80% of allowed length from start, last 20% from end
    # This preserves context at boundaries which often contain important info
    start_len = int(max_length * 0.8)
    end_len = max_length - start_len - 50  # Reserve 50 chars for marker

    truncated = (
        content[:start_len] + "\n\n[... truncated middle section ...]\n\n" + content[-end_len:]
    )

    logger.debug(f"[IMP-MEM-012] Compressed content from {len(content)} to {len(truncated)} chars")
    return truncated, True


# ---------------------------------------------------------------------------
# IMP-LOOP-003: Memory Retrieval Freshness Check
# ---------------------------------------------------------------------------

# Default maximum age for memory retrieval in task generation (hours)
# IMP-LOOP-023: Increased from 72h to 720h for better cross-cycle learning
DEFAULT_MEMORY_FRESHNESS_HOURS = 720  # 30 days


def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime object.

    Args:
        timestamp_str: ISO format timestamp string (e.g., "2024-01-15T10:30:00+00:00")

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None
    try:
        # Handle ISO format with timezone
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def _is_fresh(
    timestamp_str: Optional[str],
    max_age_hours: float,
    now: Optional[datetime] = None,
) -> bool:
    """Check if a timestamp is within the freshness threshold.

    Args:
        timestamp_str: ISO format timestamp string
        max_age_hours: Maximum age in hours for data to be considered fresh.
                      IMP-LOOP-014: Must be positive; non-positive values
                      are treated as using the default freshness threshold.
        now: Current time (defaults to UTC now)

    Returns:
        True if timestamp is within max_age_hours, False otherwise
    """
    # IMP-LOOP-014: Freshness filtering is mandatory - non-positive values
    # should not bypass the check. Log warning and use default.
    if max_age_hours <= 0:
        logger.warning(
            "[IMP-LOOP-014] _is_fresh called with max_age_hours=%s (must be positive). "
            "Using DEFAULT_MEMORY_FRESHNESS_HOURS=%s instead.",
            max_age_hours,
            DEFAULT_MEMORY_FRESHNESS_HOURS,
        )
        max_age_hours = DEFAULT_MEMORY_FRESHNESS_HOURS

    parsed_ts = _parse_timestamp(timestamp_str)
    if parsed_ts is None:
        return False  # Can't determine freshness without valid timestamp

    now = now or datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware for comparison
    if parsed_ts.tzinfo is None:
        parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_hours = (now - parsed_ts).total_seconds() / 3600
    return age_hours <= max_age_hours


# ---------------------------------------------------------------------------
# IMP-LOOP-019: Context Relevance/Confidence Metadata
# ---------------------------------------------------------------------------

# Confidence thresholds for context quality assessment
LOW_CONFIDENCE_THRESHOLD = 0.3
MEDIUM_CONFIDENCE_THRESHOLD = 0.6

# Age thresholds for confidence decay (hours)
FRESH_AGE_HOURS = 24  # Context younger than this gets full score
STALE_AGE_HOURS = 168  # Context older than this (1 week) gets penalized


@dataclass
class ContextMetadata:
    """Metadata about context relevance and quality.

    IMP-LOOP-019: Provides relevance scoring and confidence signals
    so callers know how fresh and relevant the retrieved context is.

    Attributes:
        content: The actual context content string
        relevance_score: Similarity/relevance score from vector search (0.0-1.0)
        age_hours: Age of the context in hours since creation
        confidence: Computed confidence score combining relevance and freshness (0.0-1.0)
        is_low_confidence: True if confidence is below the threshold for reliable use
        source_type: Type of context source (e.g., 'error', 'summary', 'hint', 'code')
        source_id: Original ID of the memory record
    """

    content: str
    relevance_score: float
    age_hours: float
    confidence: float
    is_low_confidence: bool
    source_type: str = ""
    source_id: str = ""

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
            return "high"
        elif self.confidence >= LOW_CONFIDENCE_THRESHOLD:
            return "medium"
        return "low"


def _calculate_age_hours(
    timestamp_str: Optional[str],
    now: Optional[datetime] = None,
) -> float:
    """Calculate age in hours from timestamp.

    Args:
        timestamp_str: ISO format timestamp string
        now: Current time (defaults to UTC now)

    Returns:
        Age in hours, or -1.0 if timestamp is invalid/missing
    """
    parsed_ts = _parse_timestamp(timestamp_str)
    if parsed_ts is None:
        return -1.0  # Unknown age

    now = now or datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware
    if parsed_ts.tzinfo is None:
        parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - parsed_ts).total_seconds()
    return max(0.0, age_seconds / 3600)


def _calculate_confidence(
    relevance_score: float,
    age_hours: float,
) -> float:
    """Calculate confidence score combining relevance and freshness.

    IMP-LOOP-019: Confidence is based on:
    - Relevance score from vector search (primary factor)
    - Age decay: fresh context is more reliable than stale context

    Args:
        relevance_score: Similarity score from vector search (0.0-1.0)
        age_hours: Age of context in hours (-1 for unknown)

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Normalize relevance to 0-1 range (scores can sometimes exceed 1.0)
    relevance = max(0.0, min(1.0, relevance_score))

    # Unknown age gets a penalty but not complete rejection
    if age_hours < 0:
        age_factor = 0.5  # Unknown age = 50% confidence in freshness
    elif age_hours <= FRESH_AGE_HOURS:
        age_factor = 1.0  # Fresh content gets full score
    elif age_hours >= STALE_AGE_HOURS:
        age_factor = 0.5  # Stale content gets 50% score
    else:
        # Linear decay between fresh and stale thresholds
        decay_range = STALE_AGE_HOURS - FRESH_AGE_HOURS
        age_beyond_fresh = age_hours - FRESH_AGE_HOURS
        age_factor = 1.0 - (0.5 * age_beyond_fresh / decay_range)

    # Combine: relevance is weighted more heavily (70%) than freshness (30%)
    confidence = 0.7 * relevance + 0.3 * age_factor

    return max(0.0, min(1.0, confidence))


def _enrich_with_metadata(
    result: Dict[str, Any],
    source_type: str = "",
    content_key: str = "content",
    now: Optional[datetime] = None,
) -> ContextMetadata:
    """Enrich a search result with context metadata.

    IMP-LOOP-019: Converts a raw search result dict to ContextMetadata
    with relevance scoring and confidence signals.

    Args:
        result: Search result dict with 'id', 'score', and 'payload' keys
        source_type: Type of context source for identification
        content_key: Key in payload to use for content extraction
        now: Current time for age calculation

    Returns:
        ContextMetadata with all quality signals
    """
    # Extract fields from result
    score = result.get("score", 0.0)
    payload = result.get("payload", {})
    source_id = result.get("id", "")

    # Try to extract content from various common keys
    content = ""
    for key in [content_key, "content", "summary", "error_text", "hint", "description"]:
        if key in payload and payload[key]:
            content = str(payload[key])
            break

    # Get timestamp and calculate age
    timestamp = payload.get("timestamp")
    age_hours = _calculate_age_hours(timestamp, now)

    # Calculate confidence
    confidence = _calculate_confidence(score, age_hours)
    is_low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

    return ContextMetadata(
        content=content,
        relevance_score=score,
        age_hours=age_hours,
        confidence=confidence,
        is_low_confidence=is_low_confidence,
        source_type=source_type or payload.get("type", ""),
        source_id=source_id,
    )


# ---------------------------------------------------------------------------
# IMP-LOOP-002: Telemetry Feedback Validation
# ---------------------------------------------------------------------------


class TelemetryFeedbackValidationError(Exception):
    """Raised when telemetry feedback data fails validation."""

    pass


class TelemetryFeedbackValidator:
    """Validator for telemetry feedback data before memory storage.

    IMP-LOOP-002: Ensures data integrity and proper feedback propagation
    between telemetry collection and memory service.
    """

    # Required fields for telemetry insights
    REQUIRED_FIELDS = {"insight_type", "description"}

    # Valid insight types that can be stored
    VALID_INSIGHT_TYPES = {"cost_sink", "failure_mode", "retry_cause", "unknown"}

    # Maximum lengths for string fields
    MAX_DESCRIPTION_LENGTH = 10000
    MAX_SUGGESTED_ACTION_LENGTH = 5000

    @classmethod
    def validate_insight(
        cls,
        insight: Dict[str, Any],
        strict: bool = False,
    ) -> tuple[bool, List[str]]:
        """Validate a telemetry insight before memory storage.

        Args:
            insight: The telemetry insight dictionary to validate.
            strict: If True, raise exception on validation failure.
                   If False, return validation result with error messages.

        Returns:
            Tuple of (is_valid, error_messages).

        Raises:
            TelemetryFeedbackValidationError: If strict=True and validation fails.
        """
        errors: List[str] = []

        # Check if insight is a dict
        if not isinstance(insight, dict):
            errors.append(f"Insight must be a dict, got {type(insight).__name__}")
            if strict:
                raise TelemetryFeedbackValidationError("; ".join(errors))
            return False, errors

        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in insight:
                errors.append(f"Missing required field: {field}")
            elif insight[field] is None:
                errors.append(f"Required field '{field}' cannot be None")

        # Validate insight_type
        insight_type = insight.get("insight_type")
        if insight_type is not None:
            if not isinstance(insight_type, str):
                errors.append(f"insight_type must be a string, got {type(insight_type).__name__}")
            elif insight_type not in cls.VALID_INSIGHT_TYPES:
                # Log warning but don't fail - allow extension
                logger.warning(
                    f"[IMP-LOOP-002] Unknown insight_type '{insight_type}', "
                    f"valid types: {cls.VALID_INSIGHT_TYPES}"
                )

        # Validate description length
        description = insight.get("description")
        if description is not None:
            if not isinstance(description, str):
                errors.append(f"description must be a string, got {type(description).__name__}")
            elif len(description) > cls.MAX_DESCRIPTION_LENGTH:
                errors.append(
                    f"description exceeds max length ({len(description)} > {cls.MAX_DESCRIPTION_LENGTH})"
                )

        # Validate suggested_action if present
        suggested_action = insight.get("suggested_action")
        if suggested_action is not None:
            if not isinstance(suggested_action, str):
                errors.append(
                    f"suggested_action must be a string, got {type(suggested_action).__name__}"
                )
            elif len(suggested_action) > cls.MAX_SUGGESTED_ACTION_LENGTH:
                errors.append(
                    f"suggested_action exceeds max length "
                    f"({len(suggested_action)} > {cls.MAX_SUGGESTED_ACTION_LENGTH})"
                )

        # Validate optional string fields
        optional_string_fields = ["phase_id", "run_id", "project_id"]
        for field in optional_string_fields:
            value = insight.get(field)
            if value is not None and not isinstance(value, str):
                errors.append(f"{field} must be a string, got {type(value).__name__}")

        is_valid = len(errors) == 0

        if strict and not is_valid:
            raise TelemetryFeedbackValidationError("; ".join(errors))

        return is_valid, errors

    @classmethod
    def sanitize_insight(cls, insight: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize a telemetry insight before storage.

        Truncates oversized fields and sets defaults for missing optional fields.

        Args:
            insight: The telemetry insight to sanitize.

        Returns:
            Sanitized copy of the insight.
        """
        if not isinstance(insight, dict):
            return {"insight_type": "unknown", "description": str(insight)}

        sanitized = dict(insight)

        # Ensure required fields have defaults
        if "insight_type" not in sanitized or sanitized["insight_type"] is None:
            sanitized["insight_type"] = "unknown"

        if "description" not in sanitized or sanitized["description"] is None:
            sanitized["description"] = ""

        # Truncate oversized fields
        if isinstance(sanitized.get("description"), str):
            if len(sanitized["description"]) > cls.MAX_DESCRIPTION_LENGTH:
                sanitized["description"] = (
                    sanitized["description"][: cls.MAX_DESCRIPTION_LENGTH - 3] + "..."
                )

        if isinstance(sanitized.get("suggested_action"), str):
            if len(sanitized["suggested_action"]) > cls.MAX_SUGGESTED_ACTION_LENGTH:
                sanitized["suggested_action"] = (
                    sanitized["suggested_action"][: cls.MAX_SUGGESTED_ACTION_LENGTH - 3] + "..."
                )

        return sanitized


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

# ---------------------------------------------------------------------------
# IMP-MEM-004: Per-Collection Staleness Policies
# ---------------------------------------------------------------------------
# Different memory collections have different freshness requirements:
# - Error patterns need quick attention (24h)
# - Test/CI results need frequent refresh (48h)
# - Learning hints have moderate freshness (72h - default)
# - Code docs change less frequently (168h = 1 week)
# - Planning artifacts are more stable (168h)
# - SOT docs are reference material (336h = 2 weeks)

COLLECTION_FRESHNESS_HOURS: Dict[str, int] = {
    COLLECTION_ERRORS_CI: 24,  # Errors should be addressed quickly
    COLLECTION_RUN_SUMMARIES: 48,  # Test/CI results need frequent refresh
    COLLECTION_DOCTOR_HINTS: 72,  # Hints have moderate freshness
    COLLECTION_CODE_DOCS: 168,  # Code docs change less frequently (1 week)
    COLLECTION_PLANNING: 168,  # Planning artifacts are more stable
    COLLECTION_SOT_DOCS: 336,  # SOT docs are reference material (2 weeks)
    "default": 720,  # Fallback to DEFAULT_MEMORY_FRESHNESS_HOURS (IMP-LOOP-023: 30 days)
}


def get_freshness_threshold(collection_name: str) -> int:
    """Get the freshness threshold in hours for a specific collection.

    IMP-MEM-004: Different collections have different staleness policies.
    Error patterns age differently than code docs, so each collection type
    has its own configurable freshness threshold.

    Args:
        collection_name: The name of the memory collection.

    Returns:
        Freshness threshold in hours for the collection.
    """
    return COLLECTION_FRESHNESS_HOURS.get(collection_name, COLLECTION_FRESHNESS_HOURS["default"])


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
    except Exception as e:
        logger.debug(f"[IMP-TELE-003] TCP connection to {host}:{port} failed: {e}")
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
    except Exception as e:
        logger.debug(f"[IMP-TELE-003] Docker availability check failed: {e}")
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
    except Exception as e:
        logger.debug(f"[IMP-TELE-003] 'docker compose' command check failed: {e}")
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
    except Exception as e:
        logger.debug(f"[IMP-TELE-003] 'docker-compose' command check failed: {e}")
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
        except Exception as e:
            logger.warning(f"[IMP-TELE-003] Docker compose up failed: {e}")
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
        except Exception as e:
            logger.warning(f"[IMP-TELE-003] Docker container start/run failed: {e}")
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


# ---------------------------------------------------------------------------
# IMP-REL-002: Memory Service Retry with Backoff
# ---------------------------------------------------------------------------


def _create_qdrant_store_with_retry(
    host: str,
    port: int,
    api_key: Optional[str],
    prefer_grpc: bool,
    timeout: int,
    max_attempts: int = 3,
) -> "QdrantStore":
    """Create QdrantStore with retry and exponential backoff.

    IMP-REL-002: Memory service failures previously fell back immediately to NullStore,
    losing accumulated knowledge. This wrapper adds retry with exponential backoff
    before falling back, allowing transient connection issues to resolve.

    Args:
        host: Qdrant server host
        port: Qdrant server port
        api_key: Optional API key for Qdrant Cloud
        prefer_grpc: Use gRPC instead of HTTP
        timeout: Request timeout in seconds
        max_attempts: Maximum number of connection attempts (default: 3)

    Returns:
        QdrantStore instance

    Raises:
        Exception: If connection fails after all retry attempts
    """

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _connect() -> "QdrantStore":
        logger.debug(f"[IMP-REL-002] Attempting to connect to Qdrant at {host}:{port}")
        return QdrantStore(
            host=host,
            port=port,
            api_key=api_key,
            prefer_grpc=prefer_grpc,
            timeout=timeout,
        )

    try:
        store = _connect()
        logger.info(f"[IMP-REL-002] Successfully connected to Qdrant at {host}:{port}")
        return store
    except RetryError as e:
        logger.warning(
            f"[IMP-REL-002] Failed to connect to Qdrant after {max_attempts} attempts: {e}"
        )
        raise e.last_attempt.exception() from e
    except Exception as e:
        logger.warning(f"[IMP-REL-002] Failed to connect to Qdrant: {e}")
        raise


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

        # IMP-MEM-005: Initialize retrieval quality tracker (must happen before early return)
        self._retrieval_quality_tracker: Optional[RetrievalQualityTracker] = None

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
        except (ValueError, TypeError) as e:
            logger.debug(
                f"[IMP-TELE-003] Invalid AUTOPACK_QDRANT_AUTOSTART_TIMEOUT, using default: {e}"
            )
            autostart_timeout_seconds = autostart_timeout_seconds

        # Pinned image for autostart fallback (determinism). Env override supported.
        qdrant_image = os.getenv("AUTOPACK_QDRANT_IMAGE") or qdrant_config.get(
            "image", DEFAULT_QDRANT_IMAGE
        )

        if use_qdrant and QDRANT_AVAILABLE:
            try:
                # IMP-REL-002: Use retry with exponential backoff for Qdrant connection
                self.store = _create_qdrant_store_with_retry(
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
                        # IMP-REL-002: Use retry with exponential backoff after autostart
                        self.store = _create_qdrant_store_with_retry(
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
                    except Exception as e:
                        # Fall through to existing policy (require vs fallback)
                        logger.warning(
                            f"[IMP-TELE-003] Qdrant connection failed after autostart: {e}"
                        )

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

        # IMP-AUTO-003: Concurrent write safety for parallel phase execution
        # Lock protects against concurrent write_telemetry_insight calls
        self._write_lock = threading.Lock()
        # Track content hashes to deduplicate insights with identical content
        self._content_hashes: set = set()

    def _safe_store_call(self, label: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            logger.warning(f"[MemoryService] {label} failed; continuing without memory op: {exc}")
            return default

    # -------------------------------------------------------------------------
    # IMP-MEM-005: Retrieval Quality Metrics
    # -------------------------------------------------------------------------

    @property
    def retrieval_quality_tracker(self) -> Optional[RetrievalQualityTracker]:
        """Get the retrieval quality tracker if set."""
        return self._retrieval_quality_tracker

    def set_retrieval_quality_tracker(self, tracker: Optional[RetrievalQualityTracker]) -> None:
        """Set the retrieval quality tracker for metrics collection.

        IMP-MEM-005: Enables recording of retrieval quality metrics including
        hit rate, relevance scores, and freshness.

        Args:
            tracker: RetrievalQualityTracker instance or None to disable tracking
        """
        self._retrieval_quality_tracker = tracker
        if tracker:
            logger.debug("[IMP-MEM-005] Retrieval quality tracker enabled")
        else:
            logger.debug("[IMP-MEM-005] Retrieval quality tracker disabled")

    def _record_retrieval_metrics(
        self,
        query: str,
        results: List[Dict[str, Any]],
        collection: str,
    ) -> None:
        """Record metrics for a retrieval operation.

        IMP-MEM-005: Records hit count, relevance scores, and freshness metrics.

        Args:
            query: The search query string
            results: List of result dicts from the search
            collection: Name of the collection searched
        """
        if self._retrieval_quality_tracker is None:
            return

        try:
            self._retrieval_quality_tracker.record_retrieval(
                query=query,
                results=results,
                collection=collection,
            )
        except Exception as e:
            # Don't let metrics recording break the main functionality
            logger.warning(f"[IMP-MEM-005] Failed to record retrieval metrics: {e}")

    def get_retrieval_quality_summary(self) -> Optional[Dict[str, Any]]:
        """Get a summary of retrieval quality metrics.

        IMP-MEM-005: Returns aggregated quality metrics for memory retrieval
        operations, or None if tracking is not enabled.

        Returns:
            Dict with quality metrics, or None if tracker not set
        """
        if self._retrieval_quality_tracker is None:
            return None
        return self._retrieval_quality_tracker.to_dict()

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
        max_age_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search code_docs collection.

        Args:
            query: Search query (natural language or code snippet)
            project_id: Project to search within
            limit: Max results (default: top_k from config)
            max_age_hours: Optional maximum age in hours for freshness filtering.
                          IMP-MEM-010: When provided, filters out stale results.

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        # IMP-MEM-010: Over-fetch when filtering to ensure enough fresh results
        fetch_limit = limit * 2 if max_age_hours is not None else limit
        query_vector = sync_embed_text(query)
        results = self._safe_store_call(
            "search_code/search",
            lambda: self.store.search(
                COLLECTION_CODE_DOCS,
                query_vector,
                filter={"project_id": project_id},
                limit=fetch_limit,
            ),
            [],
        )

        # IMP-MEM-010: Apply freshness filtering if max_age_hours specified
        if max_age_hours is not None and results:
            results = [
                r
                for r in results
                if _is_fresh(r.get("payload", {}).get("timestamp"), max_age_hours)
            ]
            results = results[:limit]

        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "code")
        return results

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

        # IMP-MEM-012: Compress summary if too long
        compressed_summary, was_compressed = _compress_content(summary)

        text = f"Phase {phase_id}: {compressed_summary}\nChanges: {', '.join(changes)}\nCI: {ci_result or 'N/A'}"
        vector = sync_embed_text(text)

        point_id = f"summary:{run_id}:{phase_id}"
        payload = {
            "type": "summary",
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "task_type": task_type,
            "summary": compressed_summary,
            "changes": changes,
            "ci_result": ci_result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compressed": was_compressed,  # IMP-MEM-012: Track compression status
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
        max_age_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search run_summaries collection.

        Args:
            query: Search query string
            project_id: Project to search within
            run_id: Optional run ID to filter by
            limit: Max results (default: top_k from config)
            max_age_hours: Optional maximum age in hours for freshness filtering.
                          IMP-MEM-010: When provided, filters out stale results.

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        # IMP-MEM-010: Over-fetch when filtering to ensure enough fresh results
        fetch_limit = limit * 2 if max_age_hours is not None else limit
        query_vector = sync_embed_text(query)
        filter_dict = {"project_id": project_id}
        if run_id:
            filter_dict["run_id"] = run_id
        results = self._safe_store_call(
            "search_summaries/search",
            lambda: self.store.search(
                COLLECTION_RUN_SUMMARIES,
                query_vector,
                filter=filter_dict,
                limit=fetch_limit,
            ),
            [],
        )

        # IMP-MEM-010: Apply freshness filtering if max_age_hours specified
        if max_age_hours is not None and results:
            results = [
                r
                for r in results
                if _is_fresh(r.get("payload", {}).get("timestamp"), max_age_hours)
            ]
            results = results[:limit]

        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "summaries")
        return results

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

        # IMP-MEM-012: Compress error text if too long
        compressed_error, was_compressed = _compress_content(error_text)

        text = f"Error in {phase_id}: {compressed_error[:2000]}"
        if test_name:
            text = f"Test {test_name} failed: {compressed_error[:2000]}"
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
            "error_text": compressed_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "compressed": was_compressed,  # IMP-MEM-012: Track compression status
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
        max_age_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search errors_ci collection for similar errors.

        Args:
            query: Search query string
            project_id: Project to search within
            limit: Max results (default: top_k from config)
            max_age_hours: Optional maximum age in hours for freshness filtering.
                          IMP-MEM-010: When provided, filters out stale results.

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        # IMP-MEM-010: Over-fetch when filtering to ensure enough fresh results
        fetch_limit = limit * 2 if max_age_hours is not None else limit
        query_vector = sync_embed_text(query)
        results = self._safe_store_call(
            "search_errors/search",
            lambda: self.store.search(
                COLLECTION_ERRORS_CI,
                query_vector,
                filter={"project_id": project_id},
                limit=fetch_limit,
            ),
            [],
        )

        # IMP-MEM-010: Apply freshness filtering if max_age_hours specified
        if max_age_hours is not None and results:
            results = [
                r
                for r in results
                if _is_fresh(r.get("payload", {}).get("timestamp"), max_age_hours)
            ]
            results = results[:limit]

        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "errors")
        return results

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
        validate: bool = True,
        strict: bool = False,
    ) -> str:
        """Write a telemetry insight to appropriate memory collection.

        This is a convenience method that routes to write_phase_summary, write_error,
        or write_doctor_hint based on insight type.

        IMP-LOOP-002: Added validation support to ensure data integrity before storage.
        IMP-AUTO-003: Added concurrent write safety with content-hash deduplication.
        IMP-MEM-006: Added content-based semantic deduplication using embedding
                     similarity to prevent memory bloat from duplicate failure patterns.
                     Similar insights (>90% similarity) are merged instead of stored
                     as separate entries, updating occurrence count and timestamps.

        Args:
            insight: TelemetryInsight object to persist
            project_id: Optional project ID for namespacing
            validate: If True, validate insight before storage (default: True)
            strict: If True with validate=True, raise exception on validation failure

        Returns:
            Document ID of written insight, or empty string if validation fails,
            duplicate content detected, or merged into existing similar insight

        Raises:
            TelemetryFeedbackValidationError: If strict=True and validation fails
        """
        if not self.enabled:
            return ""

        # IMP-LOOP-002: Validate telemetry insight before storage
        if validate:
            is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight, strict=strict)
            if not is_valid:
                logger.warning(
                    f"[IMP-LOOP-002] Telemetry insight validation failed: {errors}. "
                    f"Sanitizing and proceeding."
                )
                # Sanitize the insight to make it storable
                insight = TelemetryFeedbackValidator.sanitize_insight(insight)

        insight_type = insight.get("insight_type", "unknown")
        description = insight.get("description", "")
        content = insight.get("content", description)
        phase_id = insight.get("phase_id", "unknown")
        run_id = insight.get("run_id", "telemetry")
        suggested_action = insight.get("suggested_action")

        # IMP-REL-002: Add lifecycle tracking fields for rules
        is_rule = insight.get("is_rule", False)
        if is_rule:
            # Ensure lifecycle metadata exists for rule tracking
            if "metadata" not in insight:
                insight["metadata"] = {}
            if "created_at" not in insight["metadata"]:
                insight["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
            if "last_applied" not in insight["metadata"]:
                insight["metadata"]["last_applied"] = None
            if "application_count" not in insight["metadata"]:
                insight["metadata"]["application_count"] = 0

        # IMP-AUTO-003: Compute content hash for deduplication
        content_hash = hashlib.sha256(f"{insight_type}:{content}".encode()).hexdigest()[:16]

        # IMP-AUTO-003: Thread-safe duplicate check and write
        with self._write_lock:
            if content_hash in self._content_hashes:
                logger.debug(f"[IMP-AUTO-003] Duplicate insight skipped: {content_hash}")
                return ""

            # Track the hash before writing to prevent race conditions
            self._content_hashes.add(content_hash)

        # IMP-MEM-006: Check for semantically similar insights before storing
        # Skip semantic check for rules (they use different lifecycle tracking)
        if not is_rule and insight_type not in ("promoted_rule", "effectiveness_rule"):
            similar_insights = self._find_similar_insights(insight, threshold=0.9)
            if similar_insights:
                # Merge with the most similar existing insight
                merged_id = self._merge_insights(similar_insights[0], insight)
                if merged_id:
                    # Successfully merged - don't store as new
                    return merged_id
                # If merge failed, fall through to normal storage

        # Route to appropriate write method based on insight type
        # IMP-REL-002: Handle rules with lifecycle tracking first
        if is_rule or insight_type in ("promoted_rule", "effectiveness_rule"):
            return self._write_rule_with_lifecycle(
                insight=insight,
                project_id=project_id or "default",
                run_id=run_id,
                phase_id=phase_id,
            )
        elif insight_type == "cost_sink":
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

    # -------------------------------------------------------------------------
    # IMP-MEM-006: Content-based deduplication for insights
    # -------------------------------------------------------------------------

    def _find_similar_insights(
        self,
        insight: Dict[str, Any],
        threshold: float = 0.9,
    ) -> List[Dict[str, Any]]:
        """Find semantically similar insights using embedding similarity.

        IMP-MEM-006: Prevents memory bloat by detecting near-duplicate insights
        before storage. Uses vector similarity to find insights with similar
        content, even if not exact matches.

        Args:
            insight: The insight dict containing content/description to match.
            threshold: Minimum similarity score (0-1) to consider as duplicate.
                       Default 0.9 requires very high similarity.

        Returns:
            List of similar insights with their payloads and scores, sorted
            by similarity score descending. Empty list if no matches found.
        """
        if not self.enabled:
            return []

        insight_type = insight.get("insight_type", "unknown")
        description = insight.get("description", "")
        content = insight.get("content", description)

        # Build search text same as used for storage
        search_text = f"{insight_type}:{content}"
        if not search_text.strip(":"):
            return []

        try:
            # Create embedding for similarity search
            query_vector = sync_embed_text(search_text)

            # Determine which collection to search based on insight type
            if insight_type == "failure_mode":
                collection = COLLECTION_ERRORS_CI
            elif insight_type == "retry_cause":
                collection = COLLECTION_DOCTOR_HINTS
            else:
                # cost_sink and generic insights go to run_summaries
                collection = COLLECTION_RUN_SUMMARIES

            # Search for similar insights with telemetry_insight task_type
            results = self._safe_store_call(
                f"_find_similar_insights/{collection}",
                lambda: self.store.search(
                    collection,
                    query_vector,
                    filter={"task_type": "telemetry_insight"},
                    limit=5,
                ),
                [],
            )

            # Filter by similarity threshold and return with metadata
            similar = []
            for result in results:
                score = result.get("score", 0)
                if score >= threshold:
                    similar.append(
                        {
                            "id": result.get("id"),
                            "payload": result.get("payload", {}),
                            "score": score,
                            "collection": collection,
                        }
                    )

            # Sort by score descending (highest similarity first)
            similar.sort(key=lambda x: x.get("score", 0), reverse=True)

            if similar:
                logger.debug(
                    f"[IMP-MEM-006] Found {len(similar)} similar insights "
                    f"(threshold={threshold}): top score={similar[0]['score']:.3f}"
                )

            return similar

        except Exception as e:
            logger.warning(f"[IMP-MEM-006] Error finding similar insights: {e}")
            return []

    def _merge_insights(
        self,
        existing: Dict[str, Any],
        new_insight: Dict[str, Any],
    ) -> str:
        """Merge a new insight into an existing similar insight.

        IMP-MEM-006: Instead of storing duplicate content, this method updates
        the existing insight with merged metadata: increments occurrence count,
        updates timestamp, and preserves the highest confidence value.

        Args:
            existing: Dict containing 'id', 'payload', and 'collection' of
                      the existing similar insight.
            new_insight: The new insight dict that would have been stored.

        Returns:
            The existing insight's ID (now updated with merged data).
        """
        if not self.enabled:
            return ""

        existing_id = existing.get("id", "")
        collection = existing.get("collection", COLLECTION_RUN_SUMMARIES)
        payload = existing.get("payload", {})

        if not existing_id:
            logger.warning("[IMP-MEM-006] Cannot merge: missing existing insight ID")
            return ""

        try:
            # Update occurrence count
            current_occurrences = payload.get("occurrence_count", 1)
            new_occurrences = current_occurrences + 1

            # Update timestamp to latest
            new_timestamp = datetime.now(timezone.utc).isoformat()

            # Merge metadata - keep highest confidence
            existing_confidence = payload.get("confidence", 0.5)
            new_confidence = new_insight.get("confidence", 0.5)
            merged_confidence = max(existing_confidence, new_confidence)

            # Prepare updated payload
            updated_payload = {
                "occurrence_count": new_occurrences,
                "last_occurrence": new_timestamp,
                "confidence": merged_confidence,
                # Track merge history
                "merge_count": payload.get("merge_count", 0) + 1,
                "last_merged_at": new_timestamp,
            }

            # Preserve suggested_action if new one is provided
            new_action = new_insight.get("suggested_action")
            if new_action and new_action != payload.get("suggested_action"):
                # Append to existing actions or set new one
                existing_actions = payload.get("suggested_actions", [])
                if payload.get("suggested_action"):
                    existing_actions = [payload["suggested_action"]] + existing_actions
                if new_action not in existing_actions:
                    existing_actions.append(new_action)
                updated_payload["suggested_actions"] = existing_actions[:5]  # Keep max 5

            # Update the existing record
            success = self._safe_store_call(
                f"_merge_insights/{collection}",
                lambda: self.store.update_payload(collection, existing_id, updated_payload),
                False,
            )

            if success:
                logger.info(
                    f"[IMP-MEM-006] Merged insight into existing (id={existing_id}, "
                    f"occurrences={new_occurrences}, confidence={merged_confidence:.2f})"
                )
                return existing_id
            else:
                logger.warning(
                    f"[IMP-MEM-006] Failed to update existing insight {existing_id}, "
                    "will store as new"
                )
                return ""

        except Exception as e:
            logger.warning(f"[IMP-MEM-006] Error merging insights: {e}")
            return ""

    def _write_rule_with_lifecycle(
        self,
        insight: Dict[str, Any],
        project_id: str,
        run_id: str,
        phase_id: str,
    ) -> str:
        """Write a rule with lifecycle tracking metadata.

        IMP-REL-002: Stores rules (promoted hints or effectiveness-generated rules)
        with lifecycle tracking fields for decay and pruning support.

        Args:
            insight: The rule insight dict containing metadata
            project_id: Project identifier
            run_id: Run identifier
            phase_id: Phase identifier

        Returns:
            Point ID of the stored rule
        """
        if not self.enabled:
            return ""

        description = insight.get("description", "")
        content = insight.get("content", description)
        insight_type = insight.get("insight_type", "rule")
        suggested_action = insight.get("suggested_action", "")
        metadata = insight.get("metadata", {})

        # Build text for embedding
        text = f"Rule: {description}\nContent: {content}\nAction: {suggested_action}"
        vector = sync_embed_text(text)

        # Create unique point ID for rule
        rule_hash = hashlib.sha256(f"{insight_type}:{content}".encode()).hexdigest()[:12]
        point_id = f"rule:{project_id}:{rule_hash}"

        # Build payload with lifecycle tracking fields
        payload = {
            "type": "rule",
            "is_rule": True,
            "insight_type": insight_type,
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "description": description[:1000] if description else "",
            "content": content[:2000] if content else "",
            "suggested_action": suggested_action[:1000] if suggested_action else "",
            "severity": insight.get("severity", "medium"),
            "confidence": insight.get("confidence", 0.5),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # IMP-REL-002: Lifecycle tracking fields
            "created_at": metadata.get("created_at", datetime.now(timezone.utc).isoformat()),
            "last_applied": metadata.get("last_applied"),
            "application_count": metadata.get("application_count", 0),
            # Additional rule metadata
            "rule_type": metadata.get("rule_type"),
            "pattern": metadata.get("pattern"),
            "sample_size": metadata.get("sample_size"),
            "success_rate": metadata.get("success_rate"),
            "occurrences": insight.get("occurrences"),
            "hint_type": insight.get("hint_type"),
            "phase_type": insight.get("phase_type"),
        }

        self._safe_store_call(
            "_write_rule_with_lifecycle/upsert",
            lambda: self.store.upsert(
                COLLECTION_DOCTOR_HINTS,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
        )
        logger.info(
            f"[IMP-REL-002] Wrote rule with lifecycle tracking: {insight_type} "
            f"(id={point_id}, application_count={payload['application_count']})"
        )
        return point_id

    def record_rule_application(self, rule_id: str) -> bool:
        """Record that a rule was successfully applied.

        IMP-REL-002: Updates the lifecycle tracking fields for a rule when it
        is successfully applied. This increments application_count and updates
        last_applied timestamp for decay calculation.

        Args:
            rule_id: Point ID of the rule to update

        Returns:
            True if the rule was updated, False if not found or update failed
        """
        if not self.enabled:
            return False

        try:
            # Get current payload
            payload = self._safe_store_call(
                "record_rule_application/get_payload",
                lambda: self.store.get_payload(COLLECTION_DOCTOR_HINTS, rule_id),
                None,
            )

            if payload is None:
                logger.warning(f"[IMP-REL-002] Rule not found for application: {rule_id}")
                return False

            # Update lifecycle fields
            payload["last_applied"] = datetime.now(timezone.utc).isoformat()
            payload["application_count"] = payload.get("application_count", 0) + 1

            # Persist updated payload
            success = self._safe_store_call(
                "record_rule_application/update_payload",
                lambda: self.store.update_payload(COLLECTION_DOCTOR_HINTS, rule_id, payload),
                False,
            )

            if success:
                logger.info(
                    f"[IMP-REL-002] Recorded rule application: {rule_id} "
                    f"(count={payload['application_count']})"
                )
            return success

        except Exception as e:
            logger.warning(f"[IMP-REL-002] Failed to record rule application: {e}")
            return False

    def get_rules_for_pruning(
        self,
        project_id: str,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        """Get all rules for pruning evaluation.

        IMP-REL-002: Retrieves all rules with is_rule=True from doctor_hints
        collection for lifecycle pruning evaluation.

        Args:
            project_id: Project identifier
            limit: Maximum number of rules to retrieve

        Returns:
            List of rule documents with their payloads and IDs
        """
        if not self.enabled:
            return []

        try:
            docs = self._safe_store_call(
                "get_rules_for_pruning/scroll",
                lambda: self.store.scroll(
                    COLLECTION_DOCTOR_HINTS,
                    filter={"project_id": project_id},
                    limit=limit,
                ),
                [],
            )

            # Filter for rules only
            rules = []
            for doc in docs:
                payload = doc.get("payload", {})
                if payload.get("is_rule", False) or payload.get("type") == "rule":
                    rules.append(doc)

            logger.debug(f"[IMP-REL-002] Found {len(rules)} rules for pruning evaluation")
            return rules

        except Exception as e:
            logger.warning(f"[IMP-REL-002] Failed to get rules for pruning: {e}")
            return []

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID.

        IMP-REL-002: Removes a rule from the doctor_hints collection.
        Used by maintenance pruning to remove stale rules.

        Args:
            rule_id: Point ID of the rule to delete

        Returns:
            True if deleted, False otherwise
        """
        if not self.enabled:
            return False

        try:
            deleted = self._safe_store_call(
                "delete_rule/delete",
                lambda: self.store.delete(COLLECTION_DOCTOR_HINTS, [rule_id]),
                0,
            )
            if deleted > 0:
                logger.info(f"[IMP-REL-002] Deleted rule: {rule_id}")
                return True
            return False
        except Exception as e:
            logger.warning(f"[IMP-REL-002] Failed to delete rule {rule_id}: {e}")
            return False

    def search_doctor_hints(
        self,
        query: str,
        project_id: str,
        limit: Optional[int] = None,
        max_age_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search doctor_hints collection for similar situations.

        Args:
            query: Search query string
            project_id: Project to search within
            limit: Max results (default: top_k from config)
            max_age_hours: Optional maximum age in hours for freshness filtering.
                          IMP-MEM-010: When provided, filters out stale results.

        Returns:
            List of {"id", "score", "payload"} dicts
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        # IMP-MEM-010: Over-fetch when filtering to ensure enough fresh results
        fetch_limit = limit * 2 if max_age_hours is not None else limit
        query_vector = sync_embed_text(query)
        results = self._safe_store_call(
            "search_doctor_hints/search",
            lambda: self.store.search(
                COLLECTION_DOCTOR_HINTS,
                query_vector,
                filter={"project_id": project_id},
                limit=fetch_limit,
            ),
            [],
        )

        # IMP-MEM-010: Apply freshness filtering if max_age_hours specified
        if max_age_hours is not None and results:
            results = [
                r
                for r in results
                if _is_fresh(r.get("payload", {}).get("timestamp"), max_age_hours)
            ]
            results = results[:limit]

        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "hints")
        return results

    # -------------------------------------------------------------------------
    # Task Execution Feedback (IMP-LOOP-005)
    # -------------------------------------------------------------------------

    def write_task_execution_feedback(
        self,
        run_id: str,
        phase_id: str,
        project_id: str,
        success: bool,
        phase_type: Optional[str] = None,
        execution_time_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
        tokens_used: Optional[int] = None,
        context_summary: Optional[str] = None,
        learnings: Optional[List[str]] = None,
    ) -> str:
        """Write task execution feedback to memory for learning.

        IMP-LOOP-005: Captures task execution results (success/failure) and stores
        them in memory for future context enrichment. This enables the system to
        learn from past executions and improve future task planning.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            project_id: Project identifier
            success: Whether the phase executed successfully
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            execution_time_seconds: How long the execution took
            error_message: Error message if execution failed
            tokens_used: Number of tokens consumed during execution
            context_summary: Summary of the execution context
            learnings: List of key learnings or observations from execution

        Returns:
            Point ID of the stored feedback
        """
        if not self.enabled:
            return ""

        # Build a rich text representation for embedding
        status_str = "succeeded" if success else "failed"
        text_parts = [
            f"Task execution feedback for phase {phase_id}:",
            f"Status: {status_str}",
        ]

        if phase_type:
            text_parts.append(f"Phase type: {phase_type}")

        if execution_time_seconds is not None:
            text_parts.append(f"Execution time: {execution_time_seconds:.1f}s")

        if error_message:
            text_parts.append(f"Error: {error_message[:500]}")

        if context_summary:
            text_parts.append(f"Context: {context_summary[:500]}")

        if learnings:
            learnings_str = "; ".join(learnings[:5])
            text_parts.append(f"Learnings: {learnings_str}")

        text = "\n".join(text_parts)
        vector = sync_embed_text(text)

        # Create unique point ID
        timestamp = datetime.now(timezone.utc)
        point_id = f"exec_feedback:{run_id}:{phase_id}:{timestamp.strftime('%Y%m%d%H%M%S')}"

        payload = {
            "type": "execution_feedback",
            "run_id": run_id,
            "phase_id": phase_id,
            "project_id": project_id,
            "success": success,
            "phase_type": phase_type,
            "execution_time_seconds": execution_time_seconds,
            "error_message": error_message[:2000] if error_message else None,
            "tokens_used": tokens_used,
            "context_summary": context_summary[:1000] if context_summary else None,
            "learnings": learnings[:10] if learnings else None,
            "timestamp": timestamp.isoformat(),
            "task_type": "execution_feedback",  # For retrieval filtering
        }

        self._safe_store_call(
            "write_task_execution_feedback/upsert",
            lambda: self.store.upsert(
                COLLECTION_RUN_SUMMARIES,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
        )

        logger.info(
            f"[IMP-LOOP-005] Stored execution feedback for {phase_id} "
            f"(success={success}, phase_type={phase_type})"
        )
        return point_id

    def search_execution_feedback(
        self,
        query: str,
        project_id: str,
        success_only: Optional[bool] = None,
        phase_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar past execution feedback.

        IMP-LOOP-005: Enables retrieval of past execution outcomes for similar tasks,
        helping inform future execution strategies.

        Args:
            query: Search query describing the current task/context
            project_id: Project to search within
            success_only: If True, only return successful executions;
                         If False, only return failures; If None, return both
            phase_type: Optional phase type filter
            limit: Max results (default: top_k from config)

        Returns:
            List of {"id", "score", "payload"} dicts with execution feedback
        """
        if not self.enabled:
            return []

        limit = limit or self.top_k
        query_vector = sync_embed_text(query)

        # Build filter
        filter_dict: Dict[str, Any] = {
            "project_id": project_id,
            "type": "execution_feedback",
        }

        if success_only is not None:
            filter_dict["success"] = success_only

        if phase_type:
            filter_dict["phase_type"] = phase_type

        results = self._safe_store_call(
            "search_execution_feedback/search",
            lambda: self.store.search(
                COLLECTION_RUN_SUMMARIES,
                query_vector,
                filter=filter_dict,
                limit=limit,
            ),
            [],
        )
        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "execution_feedback")
        return results

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
        from ..config import settings
        from .sot_indexing import chunk_sot_file, chunk_sot_json

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
        results = self._safe_store_call(
            "search_sot/search",
            lambda: self.store.search(
                COLLECTION_SOT_DOCS,
                query_vector,
                filter={"project_id": project_id},
                limit=limit,
            ),
            [],
        )
        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "sot")
        return results

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
        # IMP-MEM-005: Record retrieval quality metrics
        self._record_retrieval_metrics(query, results, "planning")
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
        max_age_hours: Optional[float] = None,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve insights from memory for task generation (IMP-ARCH-010/016).

        This method is called by the ROAD-C AutonomousTaskGenerator to retrieve
        telemetry insights that can be converted into improvement tasks.

        IMP-ARCH-016: Fixed to query across collections where telemetry insights
        are actually written (run_summaries, errors_ci, doctor_hints) and filter
        for task_type="telemetry_insight".

        IMP-LOOP-003: Added freshness check to filter out stale insights based on
        timestamp. Stale data can lead to outdated context being used for task creation.

        IMP-LOOP-014: Freshness filtering is MANDATORY. Attempts to disable via
        0/negative values are ignored with a warning. Audit logging added.

        IMP-LOOP-016: Added confidence filtering to exclude low-confidence insights
        from task generation, improving decision quality.

        Args:
            query: Search query to find relevant insights
            limit: Maximum number of results to return
            project_id: Optional project ID to filter by
            max_age_hours: Maximum age in hours for insights to be considered fresh.
                          Defaults to DEFAULT_MEMORY_FRESHNESS_HOURS (720 hours / 30 days).
                          Must be positive; attempts to disable are ignored.
            min_confidence: Optional minimum confidence threshold (0.0-1.0).
                           If provided, insights with confidence below this are filtered.

        Returns:
            List of insight dictionaries with content, metadata, and score
        """
        if not self.enabled:
            logger.debug("[MemoryService] Memory disabled, returning empty insights")
            return []

        # IMP-LOOP-014: Enforce mandatory freshness filtering with validation
        # IMP-MEM-004: When max_age_hours is None, use per-collection thresholds
        use_per_collection_freshness = max_age_hours is None
        if max_age_hours is not None and max_age_hours <= 0:
            logger.warning(
                "[IMP-LOOP-014] max_age_hours=%s is invalid (must be positive). "
                "Freshness filtering is mandatory for the self-improvement loop. "
                "Override ignored - using per-collection thresholds.",
                max_age_hours,
            )
            use_per_collection_freshness = True

        # IMP-LOOP-014/IMP-MEM-004: Audit log for freshness filter applied
        if use_per_collection_freshness:
            logger.info(
                "[IMP-MEM-004] Retrieving insights with per-collection freshness thresholds, "
                "project_id=%s, limit=%s",
                project_id or "all",
                limit,
            )
        else:
            logger.info(
                "[IMP-LOOP-014] Retrieving insights with freshness_filter=%sh, project_id=%s, limit=%s",
                max_age_hours,
                project_id or "all",
                limit,
            )

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
            stale_count = 0
            # Fetch more results to account for freshness filtering
            per_collection_limit = max((limit * 2) // len(insight_collections), 5)

            for collection in insight_collections:
                # IMP-MEM-004: Get collection-specific freshness threshold
                if use_per_collection_freshness:
                    collection_max_age = get_freshness_threshold(collection)
                else:
                    collection_max_age = max_age_hours

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

                    # IMP-LOOP-003/IMP-LOOP-014/IMP-MEM-004: Apply freshness check
                    # Uses per-collection threshold when max_age_hours is not specified
                    timestamp = payload.get("timestamp")
                    if not _is_fresh(timestamp, collection_max_age):
                        stale_count += 1
                        logger.debug(
                            "[IMP-MEM-004] Skipping stale insight (age > %sh for %s): "
                            "id=%s, timestamp=%s",
                            collection_max_age,
                            collection,
                            getattr(result, "id", "unknown"),
                            timestamp,
                        )
                        continue

                    # IMP-LOOP-016: Extract confidence from payload, default to 1.0
                    confidence = payload.get("confidence", 1.0)
                    insight = {
                        "id": getattr(result, "id", None),
                        "content": payload.get("content", payload.get("summary", "")),
                        "metadata": payload,
                        "score": getattr(result, "score", 0.0),
                        "issue_type": payload.get("issue_type", "unknown"),
                        "severity": payload.get("severity", "medium"),
                        "file_path": payload.get("file_path"),
                        "collection": collection,
                        "timestamp": timestamp,  # IMP-LOOP-003: Include timestamp in result
                        "freshness_threshold": collection_max_age,  # IMP-MEM-004: Include threshold
                        "confidence": confidence,  # IMP-LOOP-016: Include confidence for filtering
                    }
                    all_insights.append(insight)

            # Sort by score and limit
            all_insights.sort(key=lambda x: x.get("score", 0), reverse=True)
            insights = all_insights[:limit]

            # IMP-LOOP-003/IMP-MEM-004: Log freshness filtering stats
            if stale_count > 0:
                logger.info(
                    "[IMP-MEM-004] Filtered %d stale insights using per-collection thresholds",
                    stale_count,
                )

            # IMP-LOOP-016: Apply confidence filtering if threshold is specified
            if min_confidence is not None:
                pre_filter_count = len(insights)
                insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]
                filtered_count = pre_filter_count - len(insights)
                if filtered_count > 0:
                    logger.info(
                        "[IMP-LOOP-016] Filtered %d low-confidence insights " "(threshold: %.2f)",
                        filtered_count,
                        min_confidence,
                    )

            logger.debug(
                f"[MemoryService] Retrieved {len(insights)} fresh insights for query: {query[:50]}..."
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

    def retrieve_context_with_metadata(
        self,
        query: str,
        project_id: str,
        run_id: Optional[str] = None,
        include_code: bool = True,
        include_summaries: bool = True,
        include_errors: bool = True,
        include_hints: bool = True,
        min_confidence: Optional[float] = None,
    ) -> Dict[str, List["ContextMetadata"]]:
        """
        Retrieve context with relevance and confidence metadata.

        IMP-LOOP-019: Returns ContextMetadata objects instead of raw dicts,
        providing relevance_score, age_hours, and confidence signals.

        IMP-MEM-013: Filters out low-confidence entries below threshold.

        Args:
            query: Search query
            project_id: Project to search within
            run_id: Optional run to scope summaries
            include_*: Flags to include/exclude collections
            min_confidence: Minimum confidence threshold (defaults to LOW_CONFIDENCE_THRESHOLD).
                           Set to 0.0 to disable filtering.

        Returns:
            Dict with keys mapping to lists of ContextMetadata objects.
            Each ContextMetadata includes confidence signals to help
            callers determine if the context is reliable.
        """
        results: Dict[str, List[ContextMetadata]] = {
            "code": [],
            "summaries": [],
            "errors": [],
            "hints": [],
        }

        if not self.enabled:
            return results

        now = datetime.now(timezone.utc)

        # Content key mappings for each source type
        content_keys = {
            "code": "content_preview",
            "summaries": "summary",
            "errors": "error_text",
            "hints": "hint",
        }

        if include_code:
            raw_results = self.search_code(query, project_id)
            results["code"] = [
                _enrich_with_metadata(r, "code", content_keys["code"], now) for r in raw_results
            ]

        if include_summaries:
            raw_results = self.search_summaries(query, project_id, run_id)
            results["summaries"] = [
                _enrich_with_metadata(r, "summary", content_keys["summaries"], now)
                for r in raw_results
            ]

        if include_errors:
            raw_results = self.search_errors(query, project_id)
            results["errors"] = [
                _enrich_with_metadata(r, "error", content_keys["errors"], now) for r in raw_results
            ]

        if include_hints:
            raw_results = self.search_doctor_hints(query, project_id)
            results["hints"] = [
                _enrich_with_metadata(r, "hint", content_keys["hints"], now) for r in raw_results
            ]

        # IMP-MEM-001: Sort all results by confidence (highest first)
        # This ensures hints with higher confidence * similarity ranking
        # are prioritized over less reliable results
        for key in results:
            results[key].sort(key=lambda x: x.confidence, reverse=True)

        # IMP-MEM-013: Filter out low-confidence entries
        # Use provided threshold or default to LOW_CONFIDENCE_THRESHOLD
        confidence_threshold = (
            min_confidence if min_confidence is not None else LOW_CONFIDENCE_THRESHOLD
        )

        total_before_filter = sum(len(v) for v in results.values())
        filtered_count = 0

        if confidence_threshold > 0:
            for key in results:
                original_len = len(results[key])
                results[key] = [
                    item for item in results[key] if item.confidence >= confidence_threshold
                ]
                filtered_count += original_len - len(results[key])

        # Log summary with confidence information
        total_items = sum(len(v) for v in results.values())
        low_confidence_items = sum(
            1 for items in results.values() for item in items if item.is_low_confidence
        )
        if total_before_filter > 0:
            log_msg = f"[MemoryService] Retrieved {total_items} context items with metadata"
            if filtered_count > 0:
                log_msg += (
                    f" (filtered {filtered_count} below {confidence_threshold:.1%} confidence)"
                )
            if low_confidence_items > 0:
                log_msg += f" ({low_confidence_items} low confidence)"
            logger.info(log_msg)

        return results

    def get_context_quality_summary(
        self,
        context_items: Dict[str, List["ContextMetadata"]],
    ) -> Dict[str, Any]:
        """
        Get a summary of context quality metrics.

        IMP-LOOP-019: Provides aggregated quality metrics for retrieved context.

        Args:
            context_items: Output from retrieve_context_with_metadata()

        Returns:
            Dict with quality metrics:
            - total_items: Total number of context items
            - low_confidence_count: Items with low confidence
            - avg_confidence: Average confidence score
            - avg_age_hours: Average age of context
            - has_low_confidence_warning: True if significant portion is low confidence
        """
        all_items = [item for items in context_items.values() for item in items]

        if not all_items:
            return {
                "total_items": 0,
                "low_confidence_count": 0,
                "avg_confidence": 0.0,
                "avg_age_hours": 0.0,
                "has_low_confidence_warning": False,
            }

        total = len(all_items)
        low_confidence = sum(1 for item in all_items if item.is_low_confidence)
        avg_confidence = sum(item.confidence for item in all_items) / total

        # Calculate average age, excluding unknown ages (-1)
        valid_ages = [item.age_hours for item in all_items if item.age_hours >= 0]
        avg_age = sum(valid_ages) / len(valid_ages) if valid_ages else -1.0

        # Warning if more than 50% of items are low confidence
        has_warning = (low_confidence / total) > 0.5

        return {
            "total_items": total,
            "low_confidence_count": low_confidence,
            "avg_confidence": round(avg_confidence, 3),
            "avg_age_hours": round(avg_age, 1),
            "has_low_confidence_warning": has_warning,
        }

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


# ---------------------------------------------------------------------------
# IMP-LOOP-012: Memory Lifecycle Management
# ---------------------------------------------------------------------------


@dataclass
class MemoryMaintenancePolicy:
    """Policy for memory lifecycle management.

    IMP-LOOP-012: Provides automatic eviction of stale insights (>90 days),
    compaction of duplicate insights, and memory usage limits with alerts.
    Prevents unbounded memory growth in the memory service.

    Attributes:
        max_age_days: Maximum age in days before an insight is eligible for eviction.
        max_memory_mb: Maximum memory usage in MB before alerts are triggered.
        dedup_enabled: Whether to enable duplicate compaction.
        alert_callback: Optional callback function for memory alerts.
    """

    max_age_days: int = 90
    max_memory_mb: float = 100.0
    dedup_enabled: bool = True
    alert_callback: Optional[Any] = dataclass_field(default=None, repr=False)

    def should_evict(self, insight: Dict[str, Any], age_days: int) -> bool:
        """Check if insight should be evicted based on age.

        Args:
            insight: The insight dictionary (payload from memory store).
            age_days: The age of the insight in days.

        Returns:
            True if the insight should be evicted, False otherwise.
        """
        return age_days > self.max_age_days

    def calculate_age_days(self, timestamp_str: Optional[str]) -> int:
        """Calculate the age in days from an ISO timestamp string.

        Args:
            timestamp_str: ISO format timestamp string (e.g., "2024-01-15T10:30:00+00:00")

        Returns:
            Age in days, or 0 if timestamp cannot be parsed.
        """
        if not timestamp_str:
            return 0
        try:
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            parsed_ts = datetime.fromisoformat(timestamp_str)
            if parsed_ts.tzinfo is None:
                parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_seconds = (now - parsed_ts).total_seconds()
            return int(age_seconds / 86400)  # Convert to days
        except (ValueError, TypeError):
            return 0

    def compact_duplicates(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate insights, keeping newest versions.

        Identifies duplicates based on content_hash field in payload.
        When duplicates are found, keeps only the most recent one
        (determined by timestamp).

        Args:
            insights: List of insight dictionaries with 'payload' containing
                     'content_hash' and 'timestamp' fields.

        Returns:
            List of deduplicated insights, keeping the newest of each duplicate set.
        """
        if not self.dedup_enabled:
            return insights

        # Sort by timestamp descending (newest first)
        def get_timestamp(insight: Dict[str, Any]) -> str:
            payload = insight.get("payload", {})
            return payload.get("timestamp", "")

        sorted_insights = sorted(insights, key=get_timestamp, reverse=True)

        # Keep only the first occurrence of each content_hash
        seen_hashes: Dict[str, Dict[str, Any]] = {}
        for insight in sorted_insights:
            payload = insight.get("payload", {})
            content_hash = payload.get("content_hash")
            if content_hash is None:
                # No content_hash, use a unique key based on id or content
                content_hash = insight.get("id", str(hash(str(payload))))

            if content_hash not in seen_hashes:
                seen_hashes[content_hash] = insight

        return list(seen_hashes.values())

    def check_memory_usage(self, current_usage_mb: float) -> bool:
        """Check if memory usage exceeds the limit and trigger alert if needed.

        Args:
            current_usage_mb: Current memory usage in megabytes.

        Returns:
            True if usage is within limits, False if over limit.
        """
        is_within_limit = current_usage_mb <= self.max_memory_mb
        if not is_within_limit:
            logger.warning(
                f"[IMP-LOOP-012] Memory usage alert: {current_usage_mb:.2f}MB "
                f"exceeds limit of {self.max_memory_mb:.2f}MB"
            )
            if self.alert_callback:
                try:
                    self.alert_callback(current_usage_mb, self.max_memory_mb)
                except Exception as e:
                    logger.error(f"[IMP-LOOP-012] Alert callback failed: {e}")
        return is_within_limit

    def get_eviction_candidates(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get list of insights that are candidates for eviction based on age.

        Args:
            insights: List of insight dictionaries with 'payload' containing 'timestamp'.

        Returns:
            List of insights that should be evicted (age > max_age_days).
        """
        eviction_candidates = []
        for insight in insights:
            payload = insight.get("payload", {})
            timestamp = payload.get("timestamp")
            age_days = self.calculate_age_days(timestamp)
            if self.should_evict(payload, age_days):
                eviction_candidates.append(insight)
        return eviction_candidates

    def run_maintenance(
        self,
        memory_service: "MemoryService",
        collection: str,
        project_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Run full maintenance cycle on a memory collection.

        Performs:
        1. Eviction of stale insights (age > max_age_days)
        2. Compaction of duplicates
        3. Memory usage check with alerts

        Args:
            memory_service: The MemoryService instance to maintain.
            collection: The collection name to maintain.
            project_id: Optional project ID to filter by.
            dry_run: If True, report what would be done without making changes.

        Returns:
            Dict with maintenance results:
            - evicted_count: Number of insights evicted
            - deduplicated_count: Number of duplicates removed
            - memory_usage_mb: Current memory usage (estimated)
            - memory_ok: Whether memory usage is within limits
        """
        results = {
            "evicted_count": 0,
            "deduplicated_count": 0,
            "memory_usage_mb": 0.0,
            "memory_ok": True,
            "dry_run": dry_run,
        }

        if not memory_service.enabled:
            logger.info("[IMP-LOOP-012] Memory disabled, skipping maintenance")
            return results

        try:
            # Get all insights from collection
            filter_dict: Optional[Dict[str, Any]] = None
            if project_id:
                filter_dict = {"project_id": project_id}

            all_insights = memory_service._safe_store_call(
                f"run_maintenance/{collection}/scroll",
                lambda: memory_service.store.scroll(collection, filter=filter_dict, limit=10000),
                [],
            )

            if not all_insights:
                logger.info(f"[IMP-LOOP-012] No insights found in {collection}")
                return results

            # Step 1: Find eviction candidates
            eviction_candidates = self.get_eviction_candidates(all_insights)
            results["evicted_count"] = len(eviction_candidates)

            if eviction_candidates and not dry_run:
                eviction_ids = [i.get("id") for i in eviction_candidates if i.get("id")]
                if eviction_ids:
                    memory_service._safe_store_call(
                        f"run_maintenance/{collection}/delete",
                        lambda: memory_service.store.delete(collection, eviction_ids),
                        0,
                    )
                    logger.info(
                        f"[IMP-LOOP-012] Evicted {len(eviction_ids)} stale insights from {collection}"
                    )

            # Step 2: Compact duplicates (on remaining insights)
            remaining_insights = [i for i in all_insights if i not in eviction_candidates]
            compacted = self.compact_duplicates(remaining_insights)
            duplicates_removed = len(remaining_insights) - len(compacted)
            results["deduplicated_count"] = duplicates_removed

            if duplicates_removed > 0 and not dry_run:
                # Find the duplicate IDs to remove
                compacted_ids = {i.get("id") for i in compacted}
                duplicate_ids = [
                    i.get("id")
                    for i in remaining_insights
                    if i.get("id") and i.get("id") not in compacted_ids
                ]
                if duplicate_ids:
                    memory_service._safe_store_call(
                        f"run_maintenance/{collection}/delete_duplicates",
                        lambda: memory_service.store.delete(collection, duplicate_ids),
                        0,
                    )
                    logger.info(
                        f"[IMP-LOOP-012] Removed {len(duplicate_ids)} duplicate insights from {collection}"
                    )

            # Step 3: Check memory usage (estimate based on count)
            # Rough estimate: ~2KB per insight average
            remaining_count = memory_service._safe_store_call(
                f"run_maintenance/{collection}/count",
                lambda: memory_service.store.count(collection, filter=filter_dict),
                0,
            )
            estimated_mb = (remaining_count * 2) / 1024  # 2KB per insight
            results["memory_usage_mb"] = estimated_mb
            results["memory_ok"] = self.check_memory_usage(estimated_mb)

            logger.info(
                f"[IMP-LOOP-012] Maintenance complete for {collection}: "
                f"evicted={results['evicted_count']}, "
                f"deduplicated={results['deduplicated_count']}, "
                f"memory_mb={results['memory_usage_mb']:.2f}"
            )

        except Exception as e:
            logger.error(f"[IMP-LOOP-012] Maintenance failed for {collection}: {e}")
            results["error"] = str(e)

        return results
