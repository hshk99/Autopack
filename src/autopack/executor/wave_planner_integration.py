"""Wave planner integration for autonomous execution loop.

IMP-GOD-002: Extracted from autonomous_loop.py to reduce god file size.

Handles wave planning functionality for parallel IMP wave execution.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from generation.autonomous_wave_planner import AutonomousWavePlanner, WavePlan

logger = logging.getLogger(__name__)


class WavePlannerIntegration:
    """Manages wave planner integration for the autonomous loop.

    IMP-LOOP-027: The wave planner groups IMPs into waves that can be
    executed in parallel while respecting dependencies and file conflicts.
    """

    def __init__(
        self,
        wave_planner_enabled: bool = True,
    ):
        """Initialize wave planner integration.

        Args:
            wave_planner_enabled: Whether wave planning is enabled.
        """
        self._wave_planner: Optional["AutonomousWavePlanner"] = None
        self._current_wave_plan: Optional["WavePlan"] = None
        self._current_wave_number: int = 0
        self._wave_phases_loaded: Dict[int, List[Dict]] = {}  # wave_number -> loaded phases
        self._wave_phases_completed: Dict[int, List[str]] = {}  # wave_number -> completed phase_ids
        self._wave_planner_enabled = wave_planner_enabled
        self._wave_plan_path: Optional[Path] = None

    @property
    def wave_planner(self) -> Optional["AutonomousWavePlanner"]:
        """Get the wave planner instance."""
        return self._wave_planner

    @property
    def current_wave_plan(self) -> Optional["WavePlan"]:
        """Get the current wave plan."""
        return self._current_wave_plan

    @property
    def current_wave_number(self) -> int:
        """Get the current wave number."""
        return self._current_wave_number

    @property
    def wave_phases_loaded(self) -> Dict[int, List[Dict]]:
        """Get loaded phases by wave number."""
        return self._wave_phases_loaded

    @property
    def wave_phases_completed(self) -> Dict[int, List[str]]:
        """Get completed phase IDs by wave number."""
        return self._wave_phases_completed

    def get_stats(self) -> Dict[str, Any]:
        """Get wave planner statistics.

        Returns:
            Dictionary with wave planner stats.
        """
        return {
            "enabled": self._wave_planner_enabled,
            "current_wave_number": self._current_wave_number,
            "total_waves": (len(self._current_wave_plan.waves) if self._current_wave_plan else 0),
            "waves_loaded": len(self._wave_phases_loaded),
            "waves_completed": sum(
                1
                for wave_num, completed in self._wave_phases_completed.items()
                if wave_num in self._wave_phases_loaded
                and len(completed) >= len(self._wave_phases_loaded.get(wave_num, []))
            ),
        }

    def initialize(self, wave_plan_path: Optional[Path] = None) -> bool:
        """Initialize the wave planner with discovered IMPs or from a wave plan file.

        IMP-LOOP-027: Loads wave plan from file if provided, otherwise attempts
        to discover IMPs and generate a wave plan dynamically.

        Args:
            wave_plan_path: Optional path to an existing wave plan JSON file.

        Returns:
            True if wave planner was successfully initialized, False otherwise.
        """
        if not self._wave_planner_enabled:
            logger.info("[IMP-LOOP-027] Wave planner is disabled in settings")
            return False

        try:
            from generation.autonomous_wave_planner import AutonomousWavePlanner

            # Try to load from file first
            if wave_plan_path and wave_plan_path.exists():
                self._wave_plan_path = wave_plan_path
                import json

                plan_data = json.loads(wave_plan_path.read_text())

                # Reconstruct IMPs from wave plan file
                discovered_imps = []
                for wave_data in plan_data.get("waves", []):
                    for phase in wave_data.get("phases", []):
                        discovered_imps.append(
                            {
                                "imp_id": phase.get("imp_id"),
                                "title": phase.get("title", ""),
                                "files_affected": phase.get("files", []),
                                "dependencies": phase.get("dependencies", []),
                            }
                        )

                if discovered_imps:
                    self._wave_planner = AutonomousWavePlanner(discovered_imps)
                    self._current_wave_plan = self._wave_planner.plan_waves()
                    logger.info(
                        f"[IMP-LOOP-027] Wave planner loaded from {wave_plan_path}: "
                        f"{len(self._current_wave_plan.waves)} waves, "
                        f"{len(discovered_imps)} IMPs"
                    )
                    return True

            # Try default wave plan path
            default_path = Path(".autopack/AUTOPACK_WAVE_PLAN.json")
            if default_path.exists():
                return self.initialize(default_path)

            logger.debug("[IMP-LOOP-027] No wave plan file found, wave planner not initialized")
            return False

        except Exception as e:
            logger.warning(f"[IMP-LOOP-027] Failed to initialize wave planner: {e}")
            return False

    def is_current_wave_complete(self) -> bool:
        """Check if all phases in the current wave are complete.

        IMP-LOOP-027: Compares completed phase IDs against loaded phase IDs
        for the current wave number.

        Returns:
            True if current wave is complete (or no wave is active), False otherwise.
        """
        if self._current_wave_number == 0:
            # No wave currently active
            return True

        if self._current_wave_plan is None:
            return True

        # Get phases loaded for current wave
        loaded_phases = self._wave_phases_loaded.get(self._current_wave_number, [])
        if not loaded_phases:
            return True

        # Get completed phase IDs for current wave
        completed_ids = set(self._wave_phases_completed.get(self._current_wave_number, []))

        # Check if all loaded phases are completed
        loaded_ids = {p.get("phase_id") for p in loaded_phases if p.get("phase_id")}

        is_complete = loaded_ids.issubset(completed_ids)

        if is_complete:
            logger.info(
                f"[IMP-LOOP-027] Wave {self._current_wave_number} complete: "
                f"{len(completed_ids)}/{len(loaded_ids)} phases"
            )

        return is_complete

    def get_next_wave(self) -> Optional[Dict]:
        """Get the next wave from the wave plan.

        IMP-LOOP-027: Returns the next wave to execute after the current wave
        is complete.

        Returns:
            Wave data dictionary if next wave exists, None otherwise.
        """
        if self._current_wave_plan is None:
            return None

        next_wave_num = self._current_wave_number + 1

        if next_wave_num not in self._current_wave_plan.waves:
            logger.info(
                f"[IMP-LOOP-027] No more waves to execute (completed {self._current_wave_number} waves)"
            )
            return None

        imp_ids = self._current_wave_plan.waves[next_wave_num]

        wave_data = {
            "wave_number": next_wave_num,
            "imp_ids": imp_ids,
            "phases": [
                {
                    "imp_id": imp_id,
                    "title": self._wave_planner.imps.get(imp_id, {}).get("title", ""),
                    "files": self._wave_planner.imps.get(imp_id, {}).get("files_affected", []),
                    "dependencies": list(self._wave_planner.dependency_graph.get(imp_id, set())),
                }
                for imp_id in imp_ids
            ],
        }

        logger.info(
            f"[IMP-LOOP-027] Next wave: {next_wave_num} with {len(imp_ids)} IMPs: {imp_ids}"
        )

        return wave_data

    def load_wave_phases(
        self,
        wave: Dict,
        current_run_phases: Optional[List[Dict]] = None,
    ) -> int:
        """Load phases from a wave plan into the execution queue.

        IMP-LOOP-027: Converts wave IMP entries into executable phase specs
        and injects them into the current run's phase list.

        Args:
            wave: Wave data dictionary with wave_number, imp_ids, and phases.
            current_run_phases: Reference to current run's phase list for injection.

        Returns:
            Number of phases successfully loaded into the queue.
        """
        if wave is None:
            return 0

        wave_number = wave.get("wave_number", 0)
        phases = wave.get("phases", [])

        if not phases:
            logger.warning(f"[IMP-LOOP-027] Wave {wave_number} has no phases to load")
            return 0

        loaded_phases = []
        for phase_data in phases:
            imp_id = phase_data.get("imp_id")
            if not imp_id:
                continue

            # Create executable phase spec
            phase_spec = {
                "phase_id": f"wave{wave_number}-{imp_id.lower().replace('-', '')}",
                "phase_type": "wave-imp-execution",
                "status": "QUEUED",
                "imp_id": imp_id,
                "title": phase_data.get("title", f"Execute {imp_id}"),
                "description": f"Wave {wave_number} execution of {imp_id}",
                "files_affected": phase_data.get("files", []),
                "dependencies": phase_data.get("dependencies", []),
                "metadata": {
                    "wave_number": wave_number,
                    "wave_planner_generated": True,
                    "imp_id": imp_id,
                },
            }

            loaded_phases.append(phase_spec)

        # Store loaded phases for wave completion tracking
        self._wave_phases_loaded[wave_number] = loaded_phases
        self._wave_phases_completed[wave_number] = []

        # Update current wave number
        self._current_wave_number = wave_number

        # Inject phases into the current run's phase list
        if current_run_phases is not None:
            # Insert wave phases at the front of the queue (high priority)
            for phase_spec in reversed(loaded_phases):
                current_run_phases.insert(0, phase_spec)

            logger.info(
                f"[IMP-LOOP-027] Loaded {len(loaded_phases)} phases from wave {wave_number} "
                f"into execution queue"
            )
        else:
            logger.warning("[IMP-LOOP-027] Cannot inject wave phases - no current run phases list")

        return len(loaded_phases)

    def mark_phase_complete(self, phase_id: str) -> None:
        """Mark a wave phase as complete for tracking.

        IMP-LOOP-027: Updates wave completion tracking when a phase finishes.

        Args:
            phase_id: The phase ID that completed.
        """
        if self._current_wave_number == 0:
            return

        completed_list = self._wave_phases_completed.get(self._current_wave_number, [])
        if phase_id not in completed_list:
            completed_list.append(phase_id)
            self._wave_phases_completed[self._current_wave_number] = completed_list

            loaded = len(self._wave_phases_loaded.get(self._current_wave_number, []))
            completed = len(completed_list)
            logger.debug(
                f"[IMP-LOOP-027] Wave {self._current_wave_number} progress: "
                f"{completed}/{loaded} phases complete"
            )

    def check_and_load_next_wave(
        self,
        current_run_phases: Optional[List[Dict]] = None,
    ) -> int:
        """Check if current wave is complete and load next wave if available.

        IMP-LOOP-027: Orchestrates wave transitions during the execution loop.

        Args:
            current_run_phases: Reference to current run's phase list for injection.

        Returns:
            Number of phases loaded from the next wave, or 0 if no wave transition.
        """
        if not self._wave_planner_enabled or self._wave_planner is None:
            return 0

        if not self.is_current_wave_complete():
            return 0

        next_wave = self.get_next_wave()
        if next_wave is None:
            return 0

        return self.load_wave_phases(next_wave, current_run_phases)
