# autopack/memory/maintenance.py
# Adapted from chatbot_project/backend/memory_maintenance.py
"""
Memory maintenance utilities: TTL pruning and optional compression.

Provides:
- prune_old_entries: Remove entries older than TTL
- compress_entry: Optional LLM-based compression for long entries
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .faiss_store import FaissStore
from .memory_service import (
    COLLECTION_DOCTOR_HINTS,
    COLLECTION_ERRORS_CI,
    COLLECTION_PLANNING,
    COLLECTION_RUN_SUMMARIES,
    _load_memory_config,
)

logger = logging.getLogger(__name__)

# Default TTL in days (from plan: 30 days)
DEFAULT_TTL_DAYS = 30

# Max content length before compression is considered
MAX_CONTENT_LENGTH = 5000


def prune_old_entries(
    store: FaissStore,
    project_id: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
    collections: Optional[List[str]] = None,
) -> int:
    """
    Prune entries older than TTL from memory collections.

    Args:
        store: FaissStore instance
        project_id: Project to prune within
        ttl_days: Days before entries expire (default: 30)
        collections: Collections to prune (default: all except code_docs)

    Returns:
        Number of entries pruned
    """
    if collections is None:
        # Don't prune code_docs by default (may want to keep indexed files)
        collections = [COLLECTION_RUN_SUMMARIES, COLLECTION_ERRORS_CI, COLLECTION_DOCTOR_HINTS]

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    cutoff_iso = cutoff.isoformat()

    total_pruned = 0

    for collection in collections:
        try:
            # Scroll all documents for this project
            docs = store.scroll(
                collection,
                filter={"project_id": project_id},
                limit=10000,
            )

            ids_to_delete = []
            for doc in docs:
                payload = doc.get("payload", {})
                timestamp = payload.get("timestamp", "")

                # Parse timestamp and compare
                try:
                    if timestamp and timestamp < cutoff_iso:
                        ids_to_delete.append(doc["id"])
                except Exception:
                    # If timestamp parsing fails, skip
                    continue

            if ids_to_delete:
                deleted = store.delete(collection, ids_to_delete)
                total_pruned += deleted
                logger.info(
                    f"[Maintenance] Pruned {deleted} entries from '{collection}' "
                    f"(project={project_id}, older than {ttl_days} days)"
                )

        except Exception as e:
            logger.error(f"[Maintenance] Failed to prune '{collection}': {e}")

    return total_pruned


def tombstone_superseded_planning(
    store: FaissStore,
    project_id: str,
    keep_versions: int = 3,
    collection: str = COLLECTION_PLANNING,
) -> int:
    """
    Mark older planning artifacts as tombstoned while keeping latest N versions.
    """
    docs = store.scroll(
        collection,
        filter={"project_id": project_id},
        limit=5000,
    )

    by_path = {}
    for doc in docs:
        payload = doc.get("payload", {})
        if payload.get("type") != "planning_artifact":
            continue
        path = payload.get("path")
        if not path:
            continue
        by_path.setdefault(path, []).append(doc)

    tombstoned = 0
    for path, entries in by_path.items():
        entries.sort(key=lambda d: d.get("payload", {}).get("timestamp", ""), reverse=True)
        for idx, doc in enumerate(entries):
            if idx < keep_versions:
                continue
            point_id = doc["id"]
            payload = doc.get("payload", {})
            payload["status"] = "tombstoned"
            payload["tombstone_reason"] = f"Replaced by newer version for {path}"
            store.update_payload(collection, point_id, payload)
            tombstoned += 1

    if tombstoned:
        logger.info(
            f"[Maintenance] Tombstoned {tombstoned} planning artifacts for project={project_id} (keep_versions={keep_versions})"
        )
    return tombstoned


async def compress_entry_content(
    content: str,
    llm_service: Optional[any] = None,
) -> Optional[str]:
    """
    Compress long content using LLM summarization.

    This is optional and requires an LLM service. If not provided,
    returns None and the caller should keep original content.

    Args:
        content: Content to compress
        llm_service: Optional LLM service with async completion

    Returns:
        Compressed content or None if compression not performed
    """
    if len(content) < MAX_CONTENT_LENGTH:
        return None

    if llm_service is None:
        logger.debug("[Maintenance] No LLM service provided, skipping compression")
        return None

    try:
        # Use a simple summarization prompt
        prompt = (
            "Compress this entry to preserve its core meaning in under 500 characters. "
            "Keep key technical details, error messages, and file paths:\n\n"
            f"{content[:4000]}"
        )

        # This assumes llm_service has an async method for completion
        # Adjust based on actual LlmService interface
        if hasattr(llm_service, "complete_async"):
            compressed = await llm_service.complete_async(prompt, max_tokens=200)
            if compressed and len(compressed) < len(content):
                logger.info(
                    f"[Maintenance] Compressed content from {len(content)} to {len(compressed)} chars"
                )
                return compressed

    except Exception as e:
        logger.warning(f"[Maintenance] Compression failed: {e}")

    return None


def run_maintenance(
    store: FaissStore,
    project_id: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
    planning_keep_versions: int = 3,
) -> dict:
    """
    Run full maintenance cycle: prune old entries.

    Args:
        store: FaissStore instance
        project_id: Project to maintain
        ttl_days: TTL for pruning

    Returns:
        Dict with maintenance stats
    """
    logger.info(f"[Maintenance] Starting maintenance for project '{project_id}'")

    stats = {
        "pruned": 0,
        "planning_tombstoned": 0,
        "compressed": 0,
        "errors": [],
    }

    try:
        stats["pruned"] = prune_old_entries(
            store,
            project_id,
            ttl_days,
            collections=[
                COLLECTION_RUN_SUMMARIES,
                COLLECTION_ERRORS_CI,
                COLLECTION_DOCTOR_HINTS,
                COLLECTION_PLANNING,
            ],
        )
    except Exception as e:
        stats["errors"].append(f"Prune failed: {e}")
        logger.error(f"[Maintenance] Prune failed: {e}")

    try:
        stats["planning_tombstoned"] = tombstone_superseded_planning(
            store, project_id, keep_versions=planning_keep_versions
        )
    except Exception as e:
        stats["errors"].append(f"Tombstone failed: {e}")
        logger.error(f"[Maintenance] Tombstone failed: {e}")

    logger.info(f"[Maintenance] Completed: {stats}")
    return stats


# IMP-LOOP-017: Maintenance scheduling constants and state
MAINTENANCE_TIMESTAMP_FILE = Path(".autonomous_runs/.last_maintenance")
DEFAULT_MAINTENANCE_INTERVAL_HOURS = 24


def _load_maintenance_config() -> Dict[str, Any]:
    """Load maintenance configuration from config/memory.yaml."""
    config = _load_memory_config()
    maintenance_config = config.get("maintenance", {})
    return {
        "auto_maintenance_enabled": maintenance_config.get("auto_maintenance_enabled", True),
        "maintenance_interval_hours": maintenance_config.get(
            "maintenance_interval_hours", DEFAULT_MAINTENANCE_INTERVAL_HOURS
        ),
        "max_age_days": maintenance_config.get("max_age_days", DEFAULT_TTL_DAYS),
        "prune_threshold": maintenance_config.get("prune_threshold", 1000),
        "planning_keep_versions": maintenance_config.get("planning_keep_versions", 3),
    }


def _get_last_maintenance_time() -> Optional[datetime]:
    """Get the timestamp of the last maintenance run.

    Returns:
        datetime of last maintenance, or None if never run
    """
    if not MAINTENANCE_TIMESTAMP_FILE.exists():
        return None

    try:
        content = MAINTENANCE_TIMESTAMP_FILE.read_text().strip()
        return datetime.fromisoformat(content)
    except (ValueError, OSError) as e:
        logger.warning(f"[Maintenance] Failed to read last maintenance time: {e}")
        return None


def _update_last_maintenance_time() -> None:
    """Update the timestamp file with current time."""
    try:
        MAINTENANCE_TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        MAINTENANCE_TIMESTAMP_FILE.write_text(datetime.now(timezone.utc).isoformat())
    except OSError as e:
        logger.warning(f"[Maintenance] Failed to update maintenance timestamp: {e}")


def is_maintenance_due(interval_hours: Optional[int] = None) -> bool:
    """Check if maintenance is due based on the configured interval.

    Args:
        interval_hours: Hours between maintenance runs. If None, uses config value.

    Returns:
        True if maintenance should run, False otherwise
    """
    config = _load_maintenance_config()

    if not config["auto_maintenance_enabled"]:
        return False

    if interval_hours is None:
        interval_hours = config["maintenance_interval_hours"]

    last_run = _get_last_maintenance_time()

    if last_run is None:
        # Never run before, maintenance is due
        logger.debug("[Maintenance] No previous maintenance found, due for first run")
        return True

    elapsed = datetime.now(timezone.utc) - last_run
    hours_since_last = elapsed.total_seconds() / 3600

    if hours_since_last >= interval_hours:
        logger.debug(
            f"[Maintenance] {hours_since_last:.1f}h since last run, "
            f"threshold is {interval_hours}h - maintenance due"
        )
        return True

    logger.debug(
        f"[Maintenance] {hours_since_last:.1f}h since last run, "
        f"threshold is {interval_hours}h - not due yet"
    )
    return False


def run_maintenance_if_due(
    project_id: str = "autopack",
    store: Optional[FaissStore] = None,
) -> Optional[Dict[str, Any]]:
    """Run maintenance if enough time has passed since last run.

    This is the main entry point for automated maintenance scheduling.
    It checks if maintenance is due based on the configured interval,
    runs maintenance if needed, and updates the timestamp.

    Args:
        project_id: Project to maintain (default: "autopack")
        store: Optional FaissStore instance. If None, creates via MemoryService.

    Returns:
        Maintenance stats dict if maintenance was run, None otherwise
    """
    if not is_maintenance_due():
        return None

    config = _load_maintenance_config()

    logger.info(
        f"[IMP-LOOP-017] Auto-maintenance triggered for project '{project_id}' "
        f"(interval: {config['maintenance_interval_hours']}h)"
    )

    try:
        # Import here to avoid circular imports
        from .memory_service import MemoryService

        if store is None:
            service = MemoryService()
            store = service.store

        stats = run_maintenance(
            store=store,
            project_id=project_id,
            ttl_days=config["max_age_days"],
            planning_keep_versions=config["planning_keep_versions"],
        )

        _update_last_maintenance_time()

        logger.info(
            f"[IMP-LOOP-017] Auto-maintenance completed: "
            f"pruned={stats['pruned']}, tombstoned={stats['planning_tombstoned']}"
        )

        return stats

    except Exception as e:
        logger.error(f"[IMP-LOOP-017] Auto-maintenance failed: {e}")
        # Still update timestamp to prevent retry storm
        _update_last_maintenance_time()
        return {"pruned": 0, "planning_tombstoned": 0, "compressed": 0, "errors": [str(e)]}


def main():
    """CLI entry point: python -m autopack.memory.maintenance --project-id autopack"""
    import argparse

    from .memory_service import MemoryService

    cfg = _load_memory_config()
    default_ttl = cfg.get("ttl_days", DEFAULT_TTL_DAYS)
    keep_versions = cfg.get("planning_keep_versions", cfg.get("keep_versions", 3))

    parser = argparse.ArgumentParser(
        description="Run vector memory maintenance (TTL prune + tombstones)"
    )
    parser.add_argument("--project-id", default="autopack", help="Project ID to prune")
    parser.add_argument("--ttl-days", type=int, default=default_ttl, help="TTL in days for pruning")
    parser.add_argument(
        "--keep-versions",
        type=int,
        default=keep_versions,
        help="Planning artifact versions to retain",
    )
    args = parser.parse_args()

    try:
        service = MemoryService()
        stats = run_maintenance(
            service.store,
            args.project_id,
            ttl_days=args.ttl_days,
            planning_keep_versions=args.keep_versions,
        )
        print(stats)
    except Exception as exc:
        logger.error(f"[Maintenance] Failed: {exc}")


if __name__ == "__main__":
    main()
