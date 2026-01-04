# autopack/memory/maintenance.py
# Adapted from chatbot_project/backend/memory_maintenance.py
"""
Memory maintenance utilities: TTL pruning and optional compression.

Provides:
- prune_old_entries: Remove entries older than TTL
- compress_entry: Optional LLM-based compression for long entries
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from .faiss_store import FaissStore
from .memory_service import (
    COLLECTION_RUN_SUMMARIES,
    COLLECTION_ERRORS_CI,
    COLLECTION_DOCTOR_HINTS,
    COLLECTION_PLANNING,
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
            collections=[COLLECTION_RUN_SUMMARIES, COLLECTION_ERRORS_CI, COLLECTION_DOCTOR_HINTS, COLLECTION_PLANNING],
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


def main():
    """CLI entry point: python -m autopack.memory.maintenance --project-id autopack"""
    import argparse
    from .memory_service import MemoryService

    cfg = _load_memory_config()
    default_ttl = cfg.get("ttl_days", DEFAULT_TTL_DAYS)
    keep_versions = cfg.get("planning_keep_versions", cfg.get("keep_versions", 3))

    parser = argparse.ArgumentParser(description="Run vector memory maintenance (TTL prune + tombstones)")
    parser.add_argument("--project-id", default="autopack", help="Project ID to prune")
    parser.add_argument("--ttl-days", type=int, default=default_ttl, help="TTL in days for pruning")
    parser.add_argument("--keep-versions", type=int, default=keep_versions, help="Planning artifact versions to retain")
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
