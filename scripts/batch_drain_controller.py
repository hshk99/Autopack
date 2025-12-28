"""
Batch Drain Controller - Efficiently process failed phases across multiple runs.

This controller orchestrates draining of failed phases with:
- Smart phase selection (prioritizes easier fixes, avoids known blockers)
- Progress tracking and reporting
- Resume capability (can stop/start without losing progress)
- Automatic retry with backoff for transient failures
- Summary reporting after each batch
- Adaptive timeout controls (starts low, increases for high-value phases)
- Failure fingerprinting (detects repeating errors, stops wasteful retries)
- Telemetry-aware tracking (measures yield-per-minute, optimizes for samples)

Usage:
  # Process 10 failed phases (default)
  python scripts/batch_drain_controller.py

  # Process 25 failed phases with 15-minute timeout
  python scripts/batch_drain_controller.py --batch-size 25 --phase-timeout-seconds 900

  # Process failed phases from specific run, with total time limit
  python scripts/batch_drain_controller.py --run-id build130-schema-validation-prevention --max-total-minutes 60

  # Dry run (show what would be processed)
  python scripts/batch_drain_controller.py --dry-run

  # Resume from previous session
  python scripts/batch_drain_controller.py --resume
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import os
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

# Default DATABASE_URL to the local SQLite DB when running from repo root.
# IMPORTANT: must run before importing autopack.database (SessionLocal binds at import time).
if not os.environ.get("DATABASE_URL"):
    _default_db_path = Path("autopack.db")
    if _default_db_path.exists():
        os.environ["DATABASE_URL"] = "sqlite:///autopack.db"
        print("[batch_drain] DATABASE_URL not set; defaulting to sqlite:///autopack.db")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from autopack.db_identity import print_db_identity, check_empty_db_warning, add_empty_db_arg


def normalize_error_text(text: str) -> str:
    """
    Normalize error text for fingerprinting.

    Removes:
    - Timestamps (2025-12-28, 16:22:03, etc.)
    - File paths (c:\\dev\\Autopack\\..., /tmp/..., etc.)
    - Memory addresses (0x7f8a1b2c3d4e)
    - Line numbers (line 123, :456, etc.)
    - Specific IDs (session-20251228-162203, etc.)

    Returns normalized text for similarity comparison.
    """
    if not text:
        return ""

    # Lowercase for case-insensitive matching
    normalized = text.lower()

    # Remove timestamps
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'date', normalized)
    normalized = re.sub(r'\d{2}:\d{2}:\d{2}', 'time', normalized)

    # Remove file paths (Windows and Unix)
    normalized = re.sub(r'[a-z]:\\[\w\\.\\-]+', 'path', normalized)
    normalized = re.sub(r'/[\w/\.\-]+', 'path', normalized)

    # Remove memory addresses
    normalized = re.sub(r'0x[0-9a-f]+', 'addr', normalized)

    # Remove line numbers
    normalized = re.sub(r'line \d+', 'line num', normalized)
    normalized = re.sub(r':\d+', ':num', normalized)

    # Remove session/run IDs
    normalized = re.sub(r'(session|run|batch|drain)-\d{8}-\d{6}', r'\1-id', normalized)

    # Remove numbers that aren't part of words
    normalized = re.sub(r'\b\d+\b', 'num', normalized)

    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip()


def compute_failure_fingerprint(result: 'DrainResult') -> str:
    """
    Compute a fingerprint for a DrainResult to detect repeating failures.

    Fingerprint includes:
    - Final state
    - Normalized error message (first 200 chars)
    - Return code bucket (0, timeout=-1, other errors)

    Returns: Short fingerprint string for grouping similar failures.
    """
    parts = [result.final_state]

    # Bucket return codes: 0 (success), -1 (timeout), 1 (error), other
    if result.subprocess_returncode is not None:
        if result.subprocess_returncode == -1:
            parts.append("timeout")
        elif result.subprocess_returncode == 0:
            parts.append("rc0")
        elif result.subprocess_returncode == 1:
            parts.append("rc1")
        elif result.subprocess_returncode == 143:
            parts.append("timeout143")  # SIGTERM timeout
        else:
            parts.append(f"rc{result.subprocess_returncode}")

    # Add normalized error message (first 200 chars for fingerprint)
    if result.error_message:
        normalized = normalize_error_text(result.error_message)[:200]
        parts.append(normalized)

    return "|".join(parts)


def detect_llm_boundary(stdout: str, stderr: str) -> bool:
    """
    T4: Detect if we hit an LLM boundary (message limit or context limit).

    Looks for patterns in stdout/stderr indicating:
    - Message limit reached (e.g., "max_turns", "message limit")
    - Context limit reached (e.g., "context_length_exceeded", "maximum context")
    - Token limit reached (e.g., "token limit", "max tokens")

    Args:
        stdout: Subprocess stdout content
        stderr: Subprocess stderr content

    Returns:
        True if LLM boundary detected, False otherwise
    """
    if not stdout and not stderr:
        return False

    combined = (stdout or "") + "\n" + (stderr or "")
    combined_lower = combined.lower()

    # Patterns indicating LLM boundary
    boundary_patterns = [
        "max_turns",
        "message limit",
        "context_length_exceeded",
        "maximum context",
        "token limit exceeded",
        "max tokens",
        "context window exceeded",
        "conversation too long",
        "exceeded maximum",
    ]

    return any(pattern in combined_lower for pattern in boundary_patterns)


def detect_zero_yield_reason(
    success: bool,
    telemetry_events: Optional[int],
    returncode: Optional[int],
    stdout: str,
    stderr: str,
    final_state: str
) -> Optional[str]:
    """
    T4: Determine why a phase produced zero telemetry events.

    Possible reasons:
    - "success_no_llm_calls": Phase completed but didn't call LLM (e.g., pure file operations)
    - "timeout": Phase timed out before collecting telemetry
    - "failed_before_llm": Phase failed during setup/validation before reaching LLM
    - "llm_boundary_hit": Hit message/context limit before completing
    - "execution_error": Runtime error during execution
    - "unknown": Other reason

    Args:
        success: Whether phase completed successfully
        telemetry_events: Number of telemetry events collected (None or 0)
        returncode: Subprocess return code
        stdout: Subprocess stdout content
        stderr: Subprocess stderr content
        final_state: Final phase state

    Returns:
        Reason string if yield was 0, None otherwise
    """
    # If we got telemetry, no zero-yield reason
    if telemetry_events and telemetry_events > 0:
        return None

    # Success but no LLM calls
    if success:
        return "success_no_llm_calls"

    # Timeout
    if returncode in (-1, 143):
        return "timeout"

    # LLM boundary hit
    if detect_llm_boundary(stdout, stderr):
        return "llm_boundary_hit"

    # Failed before reaching LLM - check if error is in setup/validation phase
    combined = (stdout or "") + "\n" + (stderr or "")
    combined_lower = combined.lower()

    early_failure_patterns = [
        "validation error",
        "schema error",
        "missing required field",
        "invalid phase",
        "phase not found",
        "run not found",
        "database error",
        "connection error",
        "permission denied",
    ]

    if any(pattern in combined_lower for pattern in early_failure_patterns):
        return "failed_before_llm"

    # Execution error (non-zero returncode, not timeout)
    if returncode and returncode not in (0, -1, 143):
        return "execution_error"

    # Unknown reason
    return "unknown"


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
    # Observability fields (A1)
    subprocess_returncode: Optional[int] = None
    subprocess_duration_seconds: Optional[float] = None
    subprocess_stdout_path: Optional[str] = None
    subprocess_stderr_path: Optional[str] = None
    subprocess_stdout_excerpt: Optional[str] = None
    subprocess_stderr_excerpt: Optional[str] = None
    # Failure fingerprinting
    failure_fingerprint: Optional[str] = None
    # Telemetry tracking
    telemetry_events_collected: Optional[int] = None
    telemetry_yield_per_minute: Optional[float] = None
    # T4: Telemetry clarity - LLM boundary + 0-yield reasons
    reached_llm_boundary: Optional[bool] = None  # True if we hit message limit or context limit
    zero_yield_reason: Optional[str] = None  # Reason why telemetry yield was 0

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.failure_fingerprint is None and not self.success:
            self.failure_fingerprint = compute_failure_fingerprint(self)


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
    total_timeouts: int = 0
    total_telemetry_events: int = 0
    results: List[DrainResult] = None
    # Failure fingerprint tracking: fingerprint -> count
    fingerprint_counts: Dict[str, int] = None
    # Stop conditions tracking
    stopped_fingerprints: Set[str] = None  # Fingerprints that hit repeat limit
    stopped_runs: Set[str] = None  # Run IDs deprioritized due to repeat failures
    # No-yield streak tracking
    consecutive_zero_yield: int = 0  # Count of consecutive phases with 0 telemetry events
    # Sample-first triage tracking (T3)
    sampled_runs: Set[str] = None  # Run IDs that have had at least 1 phase drained (sampled)
    promising_runs: Set[str] = None  # Run IDs that passed sample evaluation (continue draining)
    deprioritized_runs: Set[str] = None  # Run IDs that failed sample evaluation (cooldown)

    def __post_init__(self):
        if self.results is None:
            self.results = []
        if self.fingerprint_counts is None:
            self.fingerprint_counts = {}
        if self.stopped_fingerprints is None:
            self.stopped_fingerprints = set()
        if self.stopped_runs is None:
            self.stopped_runs = set()
        # T3: Sample-first triage sets
        if self.sampled_runs is None:
            self.sampled_runs = set()
        if self.promising_runs is None:
            self.promising_runs = set()
        if self.deprioritized_runs is None:
            self.deprioritized_runs = set()

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
        # Convert sets to lists for JSON serialization
        data = asdict(self)
        data['stopped_fingerprints'] = list(self.stopped_fingerprints) if self.stopped_fingerprints else []
        data['stopped_runs'] = list(self.stopped_runs) if self.stopped_runs else []
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, session_dir: Path, session_id: str) -> BatchDrainSession:
        """Load session state from disk."""
        session_file = session_dir / f"{session_id}.json"
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Convert results back to DrainResult objects
        results = [DrainResult(**r) for r in data.get('results', [])]
        data['results'] = results
        # Convert lists back to sets
        data['stopped_fingerprints'] = set(data.get('stopped_fingerprints', []))
        data['stopped_runs'] = set(data.get('stopped_runs', []))
        # Provide defaults for new fields if loading old session
        data.setdefault('fingerprint_counts', {})
        data.setdefault('total_timeouts', 0)
        data.setdefault('total_telemetry_events', 0)
        data.setdefault('consecutive_zero_yield', 0)
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
        dry_run: bool = False,
        skip_runs_with_queued: bool = True,
        api_url: Optional[str] = None,
        phase_timeout_seconds: int = 900,  # Default 15 minutes (was 30)
        max_total_minutes: Optional[int] = None,
        max_timeouts_per_run: int = 2,
        max_attempts_per_phase: int = 2,
        max_fingerprint_repeats: int = 3,
        skip_run_prefixes: Optional[List[str]] = None,
        max_consecutive_zero_yield: Optional[int] = None,
    ):
        self.workspace = workspace
        self.session_dir = session_dir or (workspace / ".autonomous_runs" / "batch_drain_sessions")
        self.dry_run = dry_run
        self.skip_runs_with_queued = skip_runs_with_queued
        # If provided, reuse a single API URL across drains (prevents spawning many uvicorn servers).
        # This should point at an API server using the same DATABASE_URL as this controller process.
        self.api_url = api_url
        self.session: Optional[BatchDrainSession] = None
        # Adaptive timeout controls
        self.phase_timeout_seconds = phase_timeout_seconds
        self.max_total_minutes = max_total_minutes
        self.max_timeouts_per_run = max_timeouts_per_run
        self.max_attempts_per_phase = max_attempts_per_phase
        self.max_fingerprint_repeats = max_fingerprint_repeats
        self.skip_run_prefixes = skip_run_prefixes or []
        self.max_consecutive_zero_yield = max_consecutive_zero_yield
        # Session start time for total time limit tracking
        self.session_start_time: Optional[float] = None

    def _queued_runs_set(self, db_session) -> set[str]:
        rows = db_session.query(Phase.run_id).filter(Phase.state == PhaseState.QUEUED).all()
        return {run_id for (run_id,) in rows if run_id}

    def _should_skip_phase(self, phase: Phase) -> tuple[bool, Optional[str]]:
        """
        Check if a phase should be skipped based on stop conditions.

        Returns: (should_skip, reason)
        """
        if not self.session:
            return False, None

        # T3: Check if run is deprioritized after sample-first triage
        if phase.run_id in self.session.deprioritized_runs:
            return True, f"run {phase.run_id} deprioritized (sample-first triage)"

        # Check if run is stopped due to repeated failures
        if phase.run_id in self.session.stopped_runs:
            return True, f"run {phase.run_id} deprioritized (too many repeat failures)"

        # Count timeouts for this run in current session
        run_timeouts = sum(
            1 for r in self.session.results
            if r.run_id == phase.run_id and r.subprocess_returncode in (-1, 143)
        )
        if run_timeouts >= self.max_timeouts_per_run:
            return True, f"run {phase.run_id} has {run_timeouts} timeouts (limit: {self.max_timeouts_per_run})"

        # Count attempts for this specific phase
        phase_key = f"{phase.run_id}:{phase.phase_id}"
        phase_attempts = sum(
            1 for r in self.session.results
            if f"{r.run_id}:{r.phase_id}" == phase_key
        )
        if phase_attempts >= self.max_attempts_per_phase:
            return True, f"phase already attempted {phase_attempts} times (limit: {self.max_attempts_per_phase})"

        return False, None

    def _evaluate_sample_result(self, result: DrainResult):
        """
        Evaluate a sample result (first phase from a run) to decide whether to continue or deprioritize the run.

        T3: Sample-first triage strategy.

        Criteria for "promising" run (continue draining):
        - Success = True (phase completed successfully)
        - OR has telemetry yield > 0 (we got data)
        - OR timeout but no repeating fingerprint (might succeed with more resources)

        Criteria for "deprioritize" run (cooldown):
        - Repeating failure fingerprint (indicates systematic issue)
        - AND zero telemetry yield (no data benefit)
        - AND not a timeout (timeouts might just need more time)
        """
        if not self.session:
            return

        run_id = result.run_id

        # Mark as sampled
        self.session.sampled_runs.add(run_id)

        # Evaluate promise criteria
        is_promising = False
        deprioritize_reason = None

        if result.success:
            is_promising = True
        elif (result.telemetry_events_collected or 0) > 0:
            is_promising = True
        elif result.subprocess_returncode in (-1, 143):
            # Timeout - might succeed with more time/resources
            is_promising = True
        else:
            # Failed with no telemetry - check if it's a repeating failure
            if result.failure_fingerprint:
                fingerprint_count = self.session.fingerprint_counts.get(result.failure_fingerprint, 0)
                if fingerprint_count >= 1:  # If we've seen this error before (even once)
                    deprioritize_reason = f"repeating fingerprint: {result.failure_fingerprint[:80]}..."
                    is_promising = False
                else:
                    # First time seeing this error - give it another chance
                    is_promising = True
            else:
                # No fingerprint - might be transient
                is_promising = True

        if is_promising:
            self.session.promising_runs.add(run_id)
            print(f"  [SAMPLE-OK] {run_id}: Promising (continue draining)")
        else:
            self.session.deprioritized_runs.add(run_id)
            reason = deprioritize_reason or "failed with no telemetry"
            print(f"  [SAMPLE-SKIP] {run_id}: Deprioritized ({reason})")

    def _get_telemetry_counts(self) -> Optional[int]:
        """
        Get current total telemetry event count.

        Returns: Total events across token_estimation_v2_events + token_budget_escalation_events, or None on error.
        """
        try:
            cmd = [
                sys.executable,
                "scripts/telemetry_row_counts.py",
            ]
            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None

            # Parse output: "- token_estimation_v2_events: 162"
            total = 0
            for line in result.stdout.splitlines():
                if "token_estimation_v2_events:" in line or "token_budget_escalation_events:" in line:
                    parts = line.split(":")
                    if len(parts) == 2:
                        try:
                            count = int(parts[1].strip())
                            total += count
                        except ValueError:
                            pass
            return total
        except Exception:
            return None

    def pick_next_failed_phase(
        self,
        db_session,
        run_id_filter: Optional[str] = None,
        exclude_keys: List[str] = None
    ) -> Optional[Phase]:
        """
        Pick the next failed phase to drain using smart prioritization.

        Priority order:
        1. Phases with no last_failure_reason (unknown failure, likely transient)
        2. Phases with collection errors (might be fixed by systemic improvements)
        3. Phases with deliverables missing (might be fixed by no-op guard)
        4. Phases with patch/no-op errors (quick to execute)
        5. Other failed phases (excluding timeouts - those go last)
        6. Timeout phases (expensive, low success rate)

        Within each category, prefer:
        - Lower phase_index (earlier in run)
        - Runs with fewer total failed phases (easier to complete runs)
        """
        exclude_keys = exclude_keys or []
        exclude_set = set(exclude_keys)

        # Build set of currently queued phase keys (run_id:phase_id)
        # We'll skip individual QUEUED phases, not entire runs
        queued_phase_keys: set[str] = set()
        if self.skip_runs_with_queued:
            queued_phases = db_session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()
            queued_phase_keys = {f"{p.run_id}:{p.phase_id}" for p in queued_phases}

            # Log for transparency
            if queued_phase_keys:
                print(f"  [INFO] Skipping {len(queued_phase_keys)} individual QUEUED phases (not entire runs)")

        query = db_session.query(Phase).filter(Phase.state == PhaseState.FAILED)

        if run_id_filter:
            query = query.filter(Phase.run_id == run_id_filter)

        failed_phases = query.all()

        # Skip individual QUEUED phases, not entire runs
        if self.skip_runs_with_queued and queued_phase_keys:
            failed_phases = [
                p for p in failed_phases
                if f"{p.run_id}:{p.phase_id}" not in queued_phase_keys
            ]

        # Filter out runs matching skip_run_prefixes
        if self.skip_run_prefixes:
            failed_phases = [
                p for p in failed_phases
                if not any(p.run_id.startswith(prefix) for prefix in self.skip_run_prefixes)
            ]

        # IMPORTANT: phase_id is not globally unique across runs. Exclude by composite key.
        failed_phases = [
            p for p in failed_phases
            if f"{p.run_id}:{p.phase_id}" not in exclude_set
        ]

        if not failed_phases:
            return None

        # Filter out phases that should be skipped
        candidate_phases = []
        for phase in failed_phases:
            should_skip, reason = self._should_skip_phase(phase)
            if not should_skip:
                candidate_phases.append(phase)
            elif reason:
                print(f"  [SKIP] {phase.run_id}/{phase.phase_id}: {reason}")

        if not candidate_phases:
            print("  No eligible phases remaining after applying stop conditions")
            return None

        # T3: Sample-first triage - split phases into unsampled vs sampled runs
        unsampled_phases = []
        promising_run_phases = []
        other_phases = []

        for phase in candidate_phases:
            if self.session and phase.run_id in self.session.sampled_runs:
                # Run has been sampled - check if it's promising
                if phase.run_id in self.session.promising_runs:
                    promising_run_phases.append(phase)
                # Deprioritized runs already filtered out in _should_skip_phase
            else:
                # Unsampled run - prioritize to get sample
                unsampled_phases.append(phase)

        # Prioritization: unsampled runs first, then promising runs, then others
        priority_groups = [unsampled_phases, promising_run_phases, other_phases]

        for group in priority_groups:
            if not group:
                continue

            # Within each group, categorize by failure type
            unknown_failures = []
            collection_errors = []
            deliverable_errors = []
            patch_errors = []
            timeout_errors = []
            other_failures = []

            for phase in group:
                failure_reason = (phase.last_failure_reason or "").lower()

                if not phase.last_failure_reason:
                    unknown_failures.append(phase)
                elif "collection" in failure_reason or "import" in failure_reason:
                    collection_errors.append(phase)
                elif "deliverable" in failure_reason or "missing" in failure_reason:
                    deliverable_errors.append(phase)
                elif "patch" in failure_reason or "no-op" in failure_reason or "manifest" in failure_reason:
                    patch_errors.append(phase)
                elif "timeout" in failure_reason or "timed out" in failure_reason:
                    timeout_errors.append(phase)
                else:
                    other_failures.append(phase)

            # Pick from highest priority category (timeouts last!)
            for category in [unknown_failures, collection_errors, deliverable_errors, patch_errors, other_failures, timeout_errors]:
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
                "--phase-id", phase_id,
                "--force"  # Allow non-exclusive execution (batch controller ensures sequential processing)
            ]

            print(f"  Draining: {run_id} / {phase_id} (index {phase_index})")

            # A2: Create persistent log directory for this session
            log_dir = self.workspace / ".autonomous_runs" / "batch_drain_sessions" / self.session.session_id / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            stdout_path = log_dir / f"{run_id}__{phase_id}.stdout.txt"
            stderr_path = log_dir / f"{run_id}__{phase_id}.stderr.txt"

            # B1: Force UTF-8 environment for subprocess
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            # CRITICAL: Enable telemetry collection for token estimation
            env["TELEMETRY_DB_ENABLED"] = "1"
            if self.api_url:
                env["AUTOPACK_API_URL"] = self.api_url
            # B2: Ensure DATABASE_URL is explicit
            if "DATABASE_URL" in os.environ:
                env["DATABASE_URL"] = os.environ["DATABASE_URL"]

            # A1: Capture subprocess metrics
            import time
            start_time = time.time()

            # Capture telemetry baseline before drain
            telemetry_before = self._get_telemetry_counts()

            result = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self.phase_timeout_seconds,
                env=env,
            )

            duration = time.time() - start_time

            # Capture telemetry after drain and compute delta
            telemetry_after = self._get_telemetry_counts()
            telemetry_delta = telemetry_after - telemetry_before if telemetry_before is not None and telemetry_after is not None else None

            # A2: Write full stdout/stderr to disk
            stdout_path.write_text(result.stdout or "", encoding="utf-8")
            stderr_path.write_text(result.stderr or "", encoding="utf-8")

            # Refresh phase state
            session.expire(phase)
            session.refresh(phase)
            final_state = phase.state.value if phase.state else "UNKNOWN"

            success = final_state == PhaseState.COMPLETE.value
            if success:
                error_msg = None
            else:
                # Prefer DB failure reason; fall back to subprocess stderr/stdout
                error_msg = phase.last_failure_reason
                if not error_msg:
                    stderr = (result.stderr or "").strip()
                    stdout = (result.stdout or "").strip()
                    # A3: Eliminate "Unknown error" - always include returncode and log paths
                    if result.returncode != 0:
                        error_msg = f"subprocess exit {result.returncode} (stderr: {stderr_path})"
                        if stderr:
                            error_msg = f"{error_msg[:200]} | {stderr[:300]}"
                    elif stderr:
                        error_msg = f"exit 0 but stderr present (see {stderr_path}): {stderr[:500]}"
                    elif stdout:
                        error_msg = f"exit 0 but not COMPLETE (see {stdout_path}): {stdout[:500]}"
                    else:
                        error_msg = f"exit 0 but not COMPLETE (empty output, see {stdout_path}, {stderr_path})"

            # Compute telemetry yield per minute
            telemetry_yield = None
            if telemetry_delta is not None and telemetry_delta > 0 and duration > 0:
                telemetry_yield = round((telemetry_delta / duration) * 60, 2)  # events per minute

            # T4: Detect LLM boundary and zero-yield reason
            stdout_str = result.stdout or ""
            stderr_str = result.stderr or ""
            reached_boundary = detect_llm_boundary(stdout_str, stderr_str)
            zero_yield_reason_val = detect_zero_yield_reason(
                success=success,
                telemetry_events=telemetry_delta,
                returncode=result.returncode,
                stdout=stdout_str,
                stderr=stderr_str,
                final_state=final_state
            )

            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state=final_state,
                success=success,
                error_message=error_msg,
                subprocess_returncode=result.returncode,
                subprocess_duration_seconds=round(duration, 2),
                subprocess_stdout_path=str(stdout_path),
                subprocess_stderr_path=str(stderr_path),
                subprocess_stdout_excerpt=(result.stdout or "")[:500] if result.stdout else None,
                subprocess_stderr_excerpt=(result.stderr or "")[:500] if result.stderr else None,
                telemetry_events_collected=telemetry_delta,
                telemetry_yield_per_minute=telemetry_yield,
                reached_llm_boundary=reached_boundary,
                zero_yield_reason=zero_yield_reason_val
            )

        except subprocess.TimeoutExpired as e:
            # Try to write whatever output we got before timeout
            duration = time.time() - start_time if 'start_time' in locals() else 1800
            if 'stdout_path' in locals() and 'stderr_path' in locals():
                stdout_path.write_text(e.stdout or "", encoding="utf-8")
                stderr_path.write_text(e.stderr or "", encoding="utf-8")

            # T4: Check for LLM boundary in timeout case
            timeout_stdout = e.stdout or ""
            timeout_stderr = e.stderr or ""
            timeout_boundary = detect_llm_boundary(timeout_stdout, timeout_stderr)

            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state="TIMEOUT",
                success=False,
                error_message=f"Phase drain timed out after 30 minutes (see logs)",
                subprocess_returncode=-1,  # Timeout
                subprocess_duration_seconds=round(duration, 2),
                subprocess_stdout_path=str(stdout_path) if 'stdout_path' in locals() else None,
                subprocess_stderr_path=str(stderr_path) if 'stderr_path' in locals() else None,
                reached_llm_boundary=timeout_boundary,
                zero_yield_reason="timeout"
            )
        except Exception as e:
            return DrainResult(
                run_id=run_id,
                phase_id=phase_id,
                phase_index=phase_index,
                initial_state=initial_state,
                final_state="ERROR",
                success=False,
                error_message=f"Exception during drain: {type(e).__name__}: {str(e)}"
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
        print(f"Adaptive Controls:")
        print(f"  - Phase timeout: {self.phase_timeout_seconds}s ({self.phase_timeout_seconds // 60}m)")
        print(f"  - Max total time: {self.max_total_minutes}m" if self.max_total_minutes else "  - Max total time: unlimited")
        print(f"  - Max timeouts per run: {self.max_timeouts_per_run}")
        print(f"  - Max attempts per phase: {self.max_attempts_per_phase}")
        print(f"  - Max fingerprint repeats: {self.max_fingerprint_repeats}")
        print()

        # Track which phases we've already processed
        processed_keys = [f"{r.run_id}:{r.phase_id}" for r in self.session.results]

        # Start session timer
        import time
        self.session_start_time = time.time()

        # Process phases
        db_session = SessionLocal()
        try:
            for i in range(self.session.total_processed, batch_size):
                # Check total time limit
                if self.max_total_minutes:
                    elapsed_minutes = (time.time() - self.session_start_time) / 60
                    if elapsed_minutes >= self.max_total_minutes:
                        print(f"  [TIME LIMIT] Reached max total time ({self.max_total_minutes}m)")
                        break

                print(f"[{i+1}/{batch_size}] Selecting next phase...")

                phase = self.pick_next_failed_phase(
                    db_session,
                    run_id_filter=run_id_filter,
                    exclude_keys=processed_keys
                )

                if not phase:
                    print("  No more failed phases to process")
                    break

                # Drain the phase
                result = self.drain_single_phase(phase.run_id, phase.phase_id)

                # Update session
                self.session.results.append(result)
                self.session.total_processed += 1
                processed_keys.append(f"{result.run_id}:{result.phase_id}")

                # T3: Evaluate sample result if this was first phase from this run
                if result.run_id not in self.session.sampled_runs:
                    self._evaluate_sample_result(result)

                if result.success:
                    self.session.total_success += 1
                    print(f"  [OK] Success: {result.final_state}")
                else:
                    self.session.total_failed += 1
                    print(f"  [FAIL] Failed: {result.final_state}")
                    if result.error_message:
                        print(f"    Error: {result.error_message[:100]}")

                # Track timeout count
                if result.subprocess_returncode in (-1, 143):
                    self.session.total_timeouts += 1

                # Track telemetry events and no-yield streak
                if result.telemetry_events_collected:
                    self.session.total_telemetry_events += result.telemetry_events_collected
                    self.session.consecutive_zero_yield = 0  # Reset streak on success
                    print(f"    [TELEMETRY] +{result.telemetry_events_collected} events ({result.telemetry_yield_per_minute:.2f}/min)")
                else:
                    self.session.consecutive_zero_yield += 1
                    # T4: Log zero-yield reason for transparency
                    if result.zero_yield_reason:
                        print(f"    [TELEMETRY] 0 events (reason: {result.zero_yield_reason})")
                    if self.max_consecutive_zero_yield and self.session.consecutive_zero_yield >= self.max_consecutive_zero_yield:
                        print(f"    [STOP] {self.session.consecutive_zero_yield} consecutive phases with 0 telemetry (limit: {self.max_consecutive_zero_yield})")
                        break

                # T4: Log LLM boundary detection
                if result.reached_llm_boundary:
                    print(f"    [LLM-BOUNDARY] Hit message/context limit during execution")

                # Track failure fingerprints and check for repeats
                if result.failure_fingerprint:
                    self.session.fingerprint_counts[result.failure_fingerprint] = \
                        self.session.fingerprint_counts.get(result.failure_fingerprint, 0) + 1

                    repeat_count = self.session.fingerprint_counts[result.failure_fingerprint]
                    if repeat_count >= self.max_fingerprint_repeats:
                        # Mark this fingerprint as stopped
                        self.session.stopped_fingerprints.add(result.failure_fingerprint)
                        # Mark the run as stopped (deprioritize it)
                        self.session.stopped_runs.add(result.run_id)
                        print(f"    [STOP] Fingerprint repeated {repeat_count}x - deprioritizing run {result.run_id}")

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
        print(f"  [OK] Succeeded: {session.total_success}")
        print(f"  [FAIL] Failed: {session.total_failed}")
        print(f"  [TIMEOUT] Timeouts: {session.total_timeouts}")

        if session.total_processed > 0:
            success_rate = (session.total_success / session.total_processed) * 100
            print(f"Success Rate: {success_rate:.1f}%")

        # Telemetry summary
        print()
        print("Telemetry Collection:")
        print(f"  Total Events: {session.total_telemetry_events}")
        if session.total_telemetry_events > 0:
            # Compute total duration (all non-timeout phases)
            total_duration_minutes = sum(
                (r.subprocess_duration_seconds or 0) / 60
                for r in session.results
                if r.subprocess_returncode not in (-1, 143)
            )
            if total_duration_minutes > 0:
                overall_yield = session.total_telemetry_events / total_duration_minutes
                print(f"  Overall Yield: {overall_yield:.2f} events/minute")

        # T4: Zero-yield reason breakdown
        zero_yield_phases = [r for r in session.results if not (r.telemetry_events_collected and r.telemetry_events_collected > 0)]
        if zero_yield_phases:
            print()
            print("Zero-Yield Breakdown:")
            reason_counts = {}
            for r in zero_yield_phases:
                reason = r.zero_yield_reason or "unknown"
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                print(f"  {reason}: {count}")

        # T4: LLM boundary detection summary
        llm_boundary_phases = [r for r in session.results if r.reached_llm_boundary]
        if llm_boundary_phases:
            print()
            print(f"LLM Boundary Hits: {len(llm_boundary_phases)} phases hit message/context limits")

        # Stop conditions summary
        print()
        print("Stop Conditions:")
        print(f"  Stopped Runs: {len(session.stopped_runs)}")
        if session.stopped_runs:
            for run_id in sorted(session.stopped_runs):
                print(f"    - {run_id}")
        print(f"  Unique Fingerprints: {len(session.fingerprint_counts)}")
        print(f"  Repeat Limit Hits: {len(session.stopped_fingerprints)}")

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
            timeouts = sum(1 for r in results if r.subprocess_returncode in (-1, 143))
            telemetry = sum(r.telemetry_events_collected or 0 for r in results)

            status = " [STOPPED]" if run_id in session.stopped_runs else ""
            print(f"  {run_id}{status}: {succeeded}/{total} succeeded, {timeouts} timeouts, {telemetry} events")

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
    ap.add_argument(
        "--skip-runs-with-queued",
        action="store_true",
        default=True,
        help=(
            "Safety default: skip individual QUEUED phases when selecting FAILED phases to drain. "
            "This prevents re-queueing a phase that is already queued, but still allows draining "
            "other FAILED phases from the same run."
        ),
    )
    ap.add_argument(
        "--no-skip-runs-with-queued",
        action="store_true",
        help="Disable --skip-runs-with-queued (not recommended unless you fully understand the risks).",
    )
    ap.add_argument(
        "--api-url",
        default=None,
        help=(
            "Optional: reuse a single API URL for all drains (prevents spawning many uvicorn servers). "
            "Example: http://127.0.0.1:8000"
        ),
    )
    # Adaptive draining controls
    ap.add_argument(
        "--phase-timeout-seconds",
        type=int,
        default=900,
        help="Timeout per phase in seconds (default: 900 = 15 minutes, was 30m)",
    )
    ap.add_argument(
        "--max-total-minutes",
        type=int,
        default=None,
        help="Optional: stop draining after this many minutes total (across all phases)",
    )
    ap.add_argument(
        "--max-timeouts-per-run",
        type=int,
        default=2,
        help="Skip run after this many timeout failures (default: 2)",
    )
    ap.add_argument(
        "--max-attempts-per-phase",
        type=int,
        default=2,
        help="Skip phase after this many retry attempts (default: 2)",
    )
    ap.add_argument(
        "--max-fingerprint-repeats",
        type=int,
        default=3,
        help="Deprioritize run after same error fingerprint repeats this many times (default: 3)",
    )
    ap.add_argument(
        "--skip-run-prefix",
        action="append",
        dest="skip_run_prefixes",
        help="Skip runs whose run_id starts with this prefix (can be specified multiple times). Example: --skip-run-prefix research-system",
    )
    ap.add_argument(
        "--max-consecutive-zero-yield",
        type=int,
        default=None,
        help="Stop draining after N consecutive phases with 0 telemetry events (default: unlimited). Useful for detecting systematic telemetry collection issues.",
    )
    add_empty_db_arg(ap)
    args = ap.parse_args()

    workspace = Path.cwd()
    skip_runs_with_queued = bool(args.skip_runs_with_queued and not args.no_skip_runs_with_queued)
    controller = BatchDrainController(
        workspace,
        dry_run=args.dry_run,
        skip_runs_with_queued=skip_runs_with_queued,
        api_url=args.api_url,
        phase_timeout_seconds=args.phase_timeout_seconds,
        max_total_minutes=args.max_total_minutes,
        max_timeouts_per_run=args.max_timeouts_per_run,
        max_attempts_per_phase=args.max_attempts_per_phase,
        max_fingerprint_repeats=args.max_fingerprint_repeats,
        skip_run_prefixes=args.skip_run_prefixes,
        max_consecutive_zero_yield=args.max_consecutive_zero_yield,
    )

    try:
        # Print DB identity and check for empty DB
        db_session = SessionLocal()
        try:
            print_db_identity(db_session)
            check_empty_db_warning(
                db_session,
                script_name="batch_drain_controller",
                allow_empty=args.allow_empty_db
            )
        finally:
            db_session.close()

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
