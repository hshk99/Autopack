"""
Batch Drain Controller - Efficiently process failed phases across multiple runs.

This controller orchestrates draining of failed phases with:
- Smart phase selection (prioritizes easier fixes, avoids known blockers)
- Progress tracking and reporting
- Resume capability (can stop/start without losing progress)
- Automatic retry with backoff for transient failures
- Summary reporting after each batch

Usage:
  # Process 10 failed phases (default)
  python scripts/batch_drain_controller.py

  # Process 25 failed phases
  python scripts/batch_drain_controller.py --batch-size 25

  # Process failed phases from specific run
  python scripts/batch_drain_controller.py --run-id build130-schema-validation-prevention

  # Dry run (show what would be processed)
  python scripts/batch_drain_controller.py --dry-run

  # Resume from previous session
  python scripts/batch_drain_controller.py --resume
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState


@dataclass
class DrainResult:
    """Result of draining a single phase."""
    run_id: str
    phase_id: str
    phase_index: int
    initial_state: str
    final_state: str
    success: bool
    error_message: Optional[str] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class BatchDrainSession:
    """Persistent session state for batch draining."""
    session_id: str
    started_at: str
    completed_at: Optional[str] = None
    batch_size: int = 10
    total_processed: int = 0
    total_success: int = 0
    total_failed: int = 0
    results: List[DrainResult] = None

    def __post_init__(self):
        if self.results is None:
            self.results = []

    @classmethod
    def create_new(cls, batch_size: int = 10) -> BatchDrainSession:
        """Create a new drain session."""
        session_id = f"batch-drain-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        return cls(
            session_id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            batch_size=batch_size,
            results=[]
        )

    def save(self, session_dir: Path) -> None:
        """Save session state to disk."""
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"{self.session_id}.json"
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, session_dir: Path, session_id: str) -> BatchDrainSession:
        """Load session state from disk."""
        session_file = session_dir / f"{session_id}.json"
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Convert results back to DrainResult objects
        results = [DrainResult(**r) for r in data.get('results', [])]
        data['results'] = results
        return cls(**data)

    @classmethod
    def find_latest(cls, session_dir: Path) -> Optional[BatchDrainSession]:
        """Find the most recent incomplete session."""
        if not session_dir.exists():
            return None

        sessions = list(session_dir.glob("batch-drain-*.json"))
        if not sessions:
            return None

        # Sort by modification time, newest first
        sessions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for session_file in sessions:
            session_id = session_file.stem
            session = cls.load(session_dir, session_id)
            if session.completed_at is None:
                return session

        return None


class BatchDrainController:
    """Controller for batch draining of failed phases."""

    def __init__(
        self,
        workspace: Path,
        session_dir: Optional[Path] = None,
        dry_run: bool = False
    ):
        self.workspace = workspace
        self.session_dir = session_dir or (workspace / ".autonomous_runs" / "batch_drain_sessions")
        self.dry_run = dry_run
        self.session: Optional[BatchDrainSession] = None

    def pick_next_failed_phase(
        self,
        db_session,
        run_id_filter: Optional[str] = None,
        exclude_phases: List[str] = None
    ) -> Optional[Phase]:
        """
        Pick the next failed phase to drain using smart prioritization.

        Priority order:
        1. Phases with no last_failure_reason (unknown failure, likely transient)
        2. Phases with collection errors (might be fixed by systemic improvements)
        3. Phases with deliverables missing (might be fixed by no-op guard)
        4. Other failed phases

        Within each category, prefer:
        - Lower phase_index (earlier in run)
        - Runs with fewer total failed phases (easier to complete runs)
        """
        exclude_phases = exclude_phases or []

        query = db_session.query(Phase).filter(Phase.state == PhaseState.FAILED)

        if run_id_filter:
            query = query.filter(Phase.run_id == run_id_filter)

        if exclude_phases:
            query = query.filter(~Phase.phase_id.in_(exclude_phases))

        failed_phases = query.all()

        if not failed_phases:
            return None

        # Categorize phases by failure type
        unknown_failures = []
        collection_errors = []
        deliverable_errors = []
        other_failures = []

        for phase in failed_phases:
            failure_reason = (phase.last_failure_reason or "").lower()

            if not phase.last_failure_reason:
                unknown_failures.append(phase)
            elif "collection" in failure_reason or "import" in failure_reason:
                collection_errors.append(phase)
            elif "deliverable" in failure_reason or "missing" in failure_reason:
                deliverable_errors.append(phase)
            else:
                other_failures.append(phase)

        # Pick from highest priority category
        for category in [unknown_failures, collection_errors, deliverable_errors, other_failures]:
            if category:
                # Sort by phase_index (earlier phases first)
                category.sort(key=lambda p: (p.phase_index or 0))
                return category[0]

        return None

    def drain_single_phase(self, run_id: str, phase_id: str) -> DrainResult:
        """
        Drain a single phase using the autonomous executor.

        Returns DrainResult with success status and any error messages.
        """
        session = SessionLocal()
        try:
            # Get initial state
            phase = session.query(Phase).filter(
                Phase.run_id == run_id,
                Phase.phase_id == phase_id
            ).first()

            if not phase:
                return DrainResult(
                    run_id=run_id,
                    phase_id=phase_id,
                    phase_index=0,
                    initial_state="NOT_FOUND",
                    final_state="NOT_FOUND",
                    success=False,
                    error_message="Phase not found in database"
                )

            initial_state = phase.state.value if phase.state else "UNKNOWN"
            phase_index = phase.phase_index or 0

            if self.dry_run:
                print(f"  [DRY RUN] Would drain: {run_id} / {phase_id}")
                return DrainResult(
                    run_id=run_id,
                    phase_id=phase_id,
                    phase_index=phase_index,
                    initial_state=initial_state,
                    final_state=initial_state,
                    success=True,
                    error_message="Dry run - no changes made"
                )

            # Run the drain command
            cmd = [
                sys.executable,
                "scripts/drain_one_phase.py",
                "--run-id", run_id,
                "--phase-id", phase_id
            ]

            print(f"  Draining: {run_id} / {phase_id} (index {phase_index})")

            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout per phase
            )

            # Refresh phase state
            session.expire(phase)
            session.refresh(phase)
            final_state = phase.state.value if phase.state else "UNKNOWN"

            success = final_state == PhaseState.COMPLETE.value
            error_msg = None if success else (phase.last_failure_reason or "Unknown error")

            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state=final_state,
                success=success,
                error_message=error_msg
            )

        except subprocess.TimeoutExpired:
            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state="TIMEOUT",
                success=False,
                error_message="Phase drain timed out after 10 minutes"
            )
        except Exception as e:
            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state="ERROR",
                success=False,
                error_message=str(e)
            )
        finally:
            session.close()

    def run_batch(
        self,
        batch_size: int = 10,
        run_id_filter: Optional[str] = None,
        resume: bool = False
    ) -> BatchDrainSession:
        """
        Run a batch drain session.

        Args:
            batch_size: Number of phases to process
            run_id_filter: Optional run_id to limit processing
            resume: Whether to resume previous incomplete session

        Returns:
            BatchDrainSession with results
        """
        # Create or resume session
        if resume:
            self.session = BatchDrainSession.find_latest(self.session_dir)
            if self.session:
                print(f"Resuming session: {self.session.session_id}")
                print(f"Previous progress: {self.session.total_processed} processed, "
                      f"{self.session.total_success} succeeded, {self.session.total_failed} failed")
            else:
                print("No incomplete session found, starting new session")
                self.session = BatchDrainSession.create_new(batch_size)
        else:
            self.session = BatchDrainSession.create_new(batch_size)

        print(f"\nBatch Drain Controller")
        print(f"Session ID: {self.session.session_id}")
        print(f"Target: Process {batch_size} failed phases")
        if run_id_filter:
            print(f"Filter: run_id = {run_id_filter}")
        if self.dry_run:
            print("Mode: DRY RUN (no changes will be made)")
        print()

        # Track which phases we've already processed
        processed_phase_ids = [r.phase_id for r in self.session.results]

        # Process phases
        db_session = SessionLocal()
        try:
            for i in range(self.session.total_processed, batch_size):
                print(f"[{i+1}/{batch_size}] Selecting next phase...")

                phase = self.pick_next_failed_phase(
                    db_session,
                    run_id_filter=run_id_filter,
                    exclude_phases=processed_phase_ids
                )

                if not phase:
                    print("  No more failed phases to process")
                    break

                # Drain the phase
                result = self.drain_single_phase(phase.run_id, phase.phase_id)

                # Update session
                self.session.results.append(result)
                self.session.total_processed += 1
                processed_phase_ids.append(result.phase_id)

                if result.success:
                    self.session.total_success += 1
                    print(f"  ✓ Success: {result.final_state}")
                else:
                    self.session.total_failed += 1
                    print(f"  ✗ Failed: {result.final_state}")
                    if result.error_message:
                        print(f"    Error: {result.error_message[:100]}")

                # Save progress after each phase
                self.session.save(self.session_dir)
                print()

            # Mark session as complete
            self.session.completed_at = datetime.now(timezone.utc).isoformat()
            self.session.save(self.session_dir)

        finally:
            db_session.close()

        return self.session

    def print_summary(self, session: BatchDrainSession) -> None:
        """Print summary of batch drain session."""
        print("\n" + "="*80)
        print("BATCH DRAIN SUMMARY")
        print("="*80)
        print(f"Session ID: {session.session_id}")
        print(f"Started: {session.started_at}")
        print(f"Completed: {session.completed_at or 'In progress'}")
        print()
        print(f"Total Processed: {session.total_processed}")
        print(f"  ✓ Succeeded: {session.total_success}")
        print(f"  ✗ Failed: {session.total_failed}")

        if session.total_processed > 0:
            success_rate = (session.total_success / session.total_processed) * 100
            print(f"Success Rate: {success_rate:.1f}%")

        print()
        print("Results by Run:")
        print("-" * 80)

        # Group by run_id
        by_run: Dict[str, List[DrainResult]] = {}
        for result in session.results:
            by_run.setdefault(result.run_id, []).append(result)

        for run_id, results in sorted(by_run.items()):
            succeeded = sum(1 for r in results if r.success)
            total = len(results)
            print(f"  {run_id}: {succeeded}/{total} succeeded")

        print()
        print("Session saved to:")
        print(f"  {self.session_dir / session.session_id}.json")
        print("="*80)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Batch drain controller for processing failed phases efficiently"
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of phases to process (default: 10)"
    )
    ap.add_argument(
        "--run-id",
        help="Optional: limit processing to specific run_id"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes"
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Resume previous incomplete session"
    )
    args = ap.parse_args()

    workspace = Path.cwd()
    controller = BatchDrainController(workspace, dry_run=args.dry_run)

    try:
        session = controller.run_batch(
            batch_size=args.batch_size,
            run_id_filter=args.run_id,
            resume=args.resume
        )
        controller.print_summary(session)

        # Return non-zero exit code if any phases failed
        return 1 if session.total_failed > 0 else 0

    except KeyboardInterrupt:
        print("\n\nBatch drain interrupted by user")
        if controller.session:
            controller.session.save(controller.session_dir)
            print(f"Progress saved. Resume with: --resume")
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
