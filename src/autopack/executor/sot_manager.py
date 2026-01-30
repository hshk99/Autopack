"""
SOT (Source of Truth) Manager Module

Extracted from autonomous_executor.py to manage SOT document indexing and retrieval telemetry.

Key responsibilities:
- Index SOT documentation files to memory at startup
- Record SOT retrieval telemetry to database
- Resolve project-specific docs directories

Related modules:
- retrieval_injection.py: Gates SOT retrieval based on budget
- context_loading.py: Loads context including SOT retrieval
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SOTManager:
    """
    Manages SOT document indexing and retrieval telemetry.

    Handles:
    - Indexing SOT docs to memory at startup
    - Recording retrieval telemetry
    - Resolving project docs directories
    """

    def __init__(
        self,
        workspace: Path,
        run_id: str,
        memory_service: Optional[Any] = None,
        settings: Optional[Any] = None,
    ):
        """
        Initialize SOT manager.

        Args:
            workspace: Workspace root path
            run_id: Run identifier
            memory_service: Optional MemoryService for indexing
            settings: Optional settings object (autopack.config.settings)
        """
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.memory_service = memory_service
        self.settings = settings

    def resolve_project_docs_dir(self, project_id: str) -> Path:
        """Resolve the correct docs directory for a project.

        Args:
            project_id: Project identifier (e.g., 'autopack', 'telemetry-collection-v5')

        Returns:
            Path to the project's docs directory

        Notes:
            - For repo-root projects (project_id == 'autopack'), uses <workspace>/docs
            - For sub-projects, checks <workspace>/.autonomous_runs/<project_id>/docs
            - Falls back to <workspace>/docs with a warning if sub-project docs not found
        """
        # Check for sub-project docs directory
        candidate = self.workspace / ".autonomous_runs" / project_id / "docs"
        if candidate.exists():
            logger.debug(f"[Executor] Using sub-project docs dir: {candidate}")
            return candidate

        # Fallback to root docs directory
        root_docs = self.workspace / "docs"
        if not candidate.exists() and project_id != "autopack":
            logger.warning(
                f"[Executor] Sub-project docs dir not found: {candidate}, "
                f"falling back to {root_docs}"
            )
        return root_docs

    def maybe_index_sot_docs(self, project_id: str) -> None:
        """Index SOT documentation files at startup if enabled.

        Only indexes when:
        - Memory service is enabled
        - AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true

        Failures are logged as warnings and do not crash the run.

        Args:
            project_id: Project identifier for indexing
        """
        settings = self.settings
        if settings is None:
            try:
                from autopack.config import settings as config_settings

                settings = config_settings
            except ImportError:
                logger.warning("[SOT] Could not import settings, skipping SOT indexing")
                return

        # Log SOT configuration for operator visibility
        logger.info(
            f"[SOT] Configuration: "
            f"indexing_enabled={settings.autopack_enable_sot_memory_indexing}, "
            f"retrieval_enabled={settings.autopack_sot_retrieval_enabled}, "
            f"memory_enabled={self.memory_service.enabled if self.memory_service else False}"
        )

        if not self.memory_service or not self.memory_service.enabled:
            logger.debug("[SOT] Memory service disabled, skipping SOT indexing")
            return

        # Optional: if tidy marked SOT as dirty, we can opportunistically re-index at startup.
        # This keeps the "tidy -> SOT -> semantic indexing -> retrieval" pipeline fresh
        # without re-indexing on every run.
        if project_id == "autopack":
            dirty_marker = self.workspace / ".autonomous_runs" / "sot_index_dirty_autopack.json"
        else:
            dirty_marker = (
                self.workspace
                / ".autonomous_runs"
                / project_id
                / ".autonomous_runs"
                / "sot_index_dirty.json"
            )

        dirty_requested = dirty_marker.exists()

        if not settings.autopack_enable_sot_memory_indexing:
            if dirty_requested:
                logger.info(
                    f"[SOT] Dirty marker present but indexing disabled; "
                    f"leaving marker in place: {dirty_marker}"
                )
            else:
                logger.debug("[SOT] SOT indexing disabled by config")
            return

        try:
            docs_dir = self.resolve_project_docs_dir(project_id=project_id)
            if dirty_requested:
                logger.info(f"[SOT] Dirty marker detected; re-indexing SOT now: {dirty_marker}")
            logger.info(f"[SOT] Starting indexing for project={project_id}, docs_dir={docs_dir}")

            result = self.memory_service.index_sot_docs(
                project_id=project_id,
                workspace_root=self.workspace,
                docs_dir=docs_dir,
            )

            if result.get("skipped"):
                logger.info(f"[SOT] Indexing skipped: {result.get('reason', 'unknown')}")
            else:
                indexed_count = result.get("indexed", 0)
                logger.info(
                    f"[SOT] Indexing complete: {indexed_count} chunks indexed "
                    f"(project={project_id}, docs={docs_dir})"
                )

            # Clear dirty marker only after a successful indexing attempt (even if it indexed 0).
            if dirty_requested:
                try:
                    dirty_marker.unlink(missing_ok=True)
                    logger.info(f"[SOT] Cleared dirty marker: {dirty_marker}")
                except Exception as e:
                    logger.warning(f"[SOT] Failed to clear dirty marker {dirty_marker}: {e}")
        except Exception as e:
            logger.warning(f"[SOT] Indexing failed: {e}", exc_info=True)

    def record_sot_retrieval_telemetry(
        self,
        phase_id: str,
        include_sot: bool,
        max_context_chars: int,
        retrieved_context: dict,
        formatted_context: str,
    ) -> None:
        """Record SOT retrieval telemetry to database.

        Args:
            phase_id: Phase identifier
            include_sot: Whether SOT retrieval was attempted
            max_context_chars: Total context budget allocated
            retrieved_context: Raw context dict from retrieve_context()
            formatted_context: Final formatted string from format_retrieved_context()

        Notes:
            - Only records when TELEMETRY_DB_ENABLED=1
            - Failures are logged as warnings and do not crash execution
            - See docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md for metrics explanation
        """
        settings = self.settings
        if settings is None:
            try:
                from autopack.config import settings as config_settings

                settings = config_settings
            except ImportError:
                settings = None

        # Always emit an operator-visible log line so this can never be "silent bloat".
        # DB persistence remains opt-in (TELEMETRY_DB_ENABLED=1).
        try:
            sot_chunks = retrieved_context.get("sot", []) or []
            sot_chunks_retrieved = len(sot_chunks)
            sot_chars_raw = sum(len(chunk.get("content", "")) for chunk in sot_chunks)
            total_context_chars = len(formatted_context)
            budget_utilization_pct = (
                (total_context_chars / max_context_chars * 100) if max_context_chars > 0 else 0.0
            )

            sot_cap = getattr(settings, "autopack_sot_retrieval_max_chars", 0) if settings else 0
            top_k = getattr(settings, "autopack_sot_retrieval_top_k", 0) if settings else 0

            logger.info(
                f"[{phase_id}] [SOT] Context telemetry: include_sot={include_sot}, "
                f"sot_chunks={sot_chunks_retrieved}, sot_chars_raw={sot_chars_raw}, "
                f"total_chars={total_context_chars}/{max_context_chars} "
                f"({budget_utilization_pct:.1f}%), "
                f"sot_cap={sot_cap}, top_k={top_k}"
            )
        except Exception:
            # Never block execution if telemetry formatting fails.
            pass

        # Skip DB persistence if telemetry disabled
        if not os.getenv("TELEMETRY_DB_ENABLED") == "1":
            return

        try:
            from datetime import datetime, timezone

            from autopack.database import SessionLocal
            from autopack.models import SOTRetrievalEvent

            # Calculate metrics
            sot_chunks = retrieved_context.get("sot", [])
            sot_chunks_retrieved = len(sot_chunks)
            sot_chars_raw = sum(len(chunk.get("content", "")) for chunk in sot_chunks)

            total_context_chars = len(formatted_context)
            budget_utilization_pct = (
                (total_context_chars / max_context_chars * 100) if max_context_chars > 0 else 0.0
            )

            # Determine sections included
            sections_included = [k for k, v in retrieved_context.items() if v]

            # Estimate SOT contribution in formatted output (approximate)
            # Since format_retrieved_context() doesn't expose per-section breakdowns,
            # we can't measure exact SOT chars after formatting.
            # For now, set to None if SOT wasn't included, or sot_chars_raw if it was
            # (this is an upper bound - actual may be lower if truncated).
            sot_chars_formatted = sot_chars_raw if include_sot and sot_chunks else None

            # Detect if SOT was truncated (heuristic: raw > formatted and formatted < max)
            sot_truncated = False
            if include_sot and sot_chars_raw > 0:
                # If total context hit the cap, SOT might have been truncated
                sot_truncated = total_context_chars >= max_context_chars * 0.95  # Within 5% of cap

            # Create telemetry event
            session = SessionLocal()
            try:
                event = SOTRetrievalEvent(
                    run_id=self.run_id,
                    phase_id=phase_id,
                    timestamp=datetime.now(timezone.utc),
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    sot_budget_chars=(settings.autopack_sot_retrieval_max_chars if settings else 0),
                    sot_chunks_retrieved=sot_chunks_retrieved,
                    sot_chars_raw=sot_chars_raw,
                    total_context_chars=total_context_chars,
                    sot_chars_formatted=sot_chars_formatted,
                    budget_utilization_pct=budget_utilization_pct,
                    sot_truncated=sot_truncated,
                    sections_included=sections_included,
                    retrieval_enabled=(
                        settings.autopack_sot_retrieval_enabled if settings else False
                    ),
                    top_k=settings.autopack_sot_retrieval_top_k if settings else 0,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(event)
                session.commit()

                logger.debug(
                    f"[{phase_id}] SOT telemetry recorded: "
                    f"include_sot={include_sot}, "
                    f"chunks={sot_chunks_retrieved}, "
                    f"chars_raw={sot_chars_raw}, "
                    f"total={total_context_chars}/{max_context_chars} "
                    f"({budget_utilization_pct:.1f}%)"
                )
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to record SOT retrieval telemetry: {e}")
