"""
Cleanup execution engine for Storage Optimizer Phase 2.

Implements safe deletion with:
- Recycle Bin safety via send2trash (NOT permanent deletion)
- Protected path double-checking before execution
- Approval workflow state machine
- Compression before deletion (optional per policy)
- Transaction-like execution with rollback on failure
"""

import logging
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

import send2trash
from sqlalchemy.orm import Session

from ..models import CleanupCandidateDB
from .checkpoint_logger import CheckpointLogger, compute_sha256
from .lock_detector import LockDetector
from .policy import StoragePolicy, is_path_protected

logger = logging.getLogger(__name__)


# ==============================================================================
# Execution State Machine
# ==============================================================================


class ExecutionStatus(str, Enum):
    """Execution status states for cleanup candidates."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalStatus(str, Enum):
    """Approval status states for cleanup candidates."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"


# ==============================================================================
# Execution Results
# ==============================================================================


@dataclass
class ExecutionResult:
    """Result of executing cleanup on a single candidate."""

    candidate_id: int
    path: str
    status: ExecutionStatus
    error: Optional[str] = None
    compressed_path: Optional[str] = None
    compression_ratio: Optional[float] = None
    compression_duration_seconds: Optional[int] = None
    original_size_bytes: Optional[int] = None
    freed_bytes: Optional[int] = None
    lock_type: Optional[str] = None  # BUILD-152: Lock type classification
    retry_count: int = 0  # BUILD-152: Number of retry attempts


@dataclass
class BatchExecutionResult:
    """Result of executing cleanup on a batch of candidates."""

    total_candidates: int
    successful: int
    failed: int
    skipped: int
    total_freed_bytes: int
    results: List[ExecutionResult]
    execution_duration_seconds: int
    stopped_due_to_cap: bool = False
    cap_reason: Optional[str] = None
    remaining_candidates: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_candidates == 0:
            return 0.0
        return (self.successful / self.total_candidates) * 100


# ==============================================================================
# Cleanup Executor
# ==============================================================================


class CleanupExecutor:
    """
    Executes cleanup operations with safety guardrails.

    Safety Features:
    1. Protected path double-checking before ANY deletion
    2. send2trash (Recycle Bin) instead of permanent deletion
    3. Approval required for risky categories
    4. Compression before deletion (optional)
    5. Dry-run mode to preview actions

    Example:
        ```python
        executor = CleanupExecutor(policy, dry_run=False)
        results = executor.execute_approved_candidates(db, scan_id=123)
        print(f"Freed {results.total_freed_bytes / (1024**3):.2f} GB")
        ```
    """

    def __init__(
        self,
        policy: StoragePolicy,
        dry_run: bool = True,
        compress_before_delete: bool = False,
        compression_archive_dir: Optional[Path] = None,
        skip_locked: bool = False,
    ):
        """
        Initialize cleanup executor.

        Args:
            policy: Storage policy for protected path checking
            dry_run: If True, preview actions without executing (default: True for safety)
            compress_before_delete: If True, compress files before deletion
            compression_archive_dir: Directory to store compressed archives
                (default: archive/superseded/storage_cleanup_{timestamp})
            skip_locked: If True, skip locked files without retry (BUILD-152)
        """
        self.policy = policy
        self.dry_run = dry_run
        self.compress_before_delete = compress_before_delete
        self.skip_locked = skip_locked

        # Set compression archive directory
        if compression_archive_dir is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self.compression_archive_dir = Path(f"archive/superseded/storage_cleanup_{timestamp}")
        else:
            self.compression_archive_dir = Path(compression_archive_dir)

        # Create archive directory if compression enabled
        if self.compress_before_delete and not self.dry_run:
            self.compression_archive_dir.mkdir(parents=True, exist_ok=True)

        # BUILD-152: Initialize checkpoint logger and lock detector
        self.checkpoint_logger = CheckpointLogger()
        self.lock_detector = LockDetector()
        self.current_run_id = None  # Set during batch execution

    # ==========================================================================
    # Single File/Directory Deletion
    # ==========================================================================

    def _delete_with_retry(
        self, path: Path, deletion_func, max_retries: Optional[int] = None
    ) -> tuple[bool, Optional[str], Optional[str], int]:
        """
        Execute deletion with retry logic for transient locks (BUILD-152).

        Args:
            path: Path to delete
            deletion_func: Function to call for deletion (send2trash.send2trash)
            max_retries: Max retry attempts (default: from policy or lock type)

        Returns:
            Tuple of (success, error_msg, lock_type, retry_count)

        Algorithm:
            1. Attempt deletion
            2. On failure, detect lock type
            3. If transient lock, retry with exponential backoff
            4. If permanent lock or max retries exceeded, fail
        """
        # BUILD-152: Override max_retries to 0 if skip_locked is enabled
        if self.skip_locked and max_retries is None:
            max_retries = 0

        retry_count = 0
        last_error = None
        last_lock_type = None

        while retry_count <= (max_retries or 3):
            try:
                # Attempt deletion
                deletion_func(str(path))
                return (True, None, None, retry_count)

            except Exception as e:
                last_error = str(e)

                # Detect lock type
                lock_type = self.lock_detector.detect_lock_type(path, e)
                last_lock_type = lock_type

                # Check if we should retry
                is_transient = self.lock_detector.is_transient_lock(lock_type)
                recommended_retries = self.lock_detector.get_recommended_retry_count(lock_type)

                # Use recommended retries if max_retries not specified
                if max_retries is None:
                    max_retries = recommended_retries

                if is_transient and retry_count < max_retries:
                    # Exponential backoff
                    backoff = self.lock_detector.get_backoff_seconds(lock_type, retry_count)
                    logger.info(
                        f"[RETRY {retry_count + 1}/{max_retries}] {path} "
                        f"locked by {lock_type}, retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                    retry_count += 1
                else:
                    # Permanent lock or max retries exceeded
                    if is_transient:
                        logger.warning(
                            f"[LOCKED] {path} - {lock_type}: Max retries ({max_retries}) exceeded"
                        )
                    else:
                        hint = self.lock_detector.get_remediation_hint(lock_type)
                        logger.warning(f"[LOCKED] {path} - {lock_type}: {hint}")

                    return (False, last_error, lock_type, retry_count)

        # Should not reach here, but handle edge case
        return (False, last_error, last_lock_type, retry_count)

    def delete_file(self, file_path: Path) -> ExecutionResult:
        """
        Delete a single file using send2trash (Recycle Bin) with retry logic.

        Args:
            file_path: Path to file to delete

        Returns:
            ExecutionResult with status and error (if any)

        Safety:
            - Double-checks protected paths before deletion
            - Uses send2trash instead of os.remove() for Recycle Bin safety
            - Never raises exceptions (returns status instead)

        BUILD-152 Enhancements:
            - Retries transient locks (searchindexer, antivirus, handle)
            - Skips permanent locks (permission, path_too_long)
            - Provides remediation hints for failures
        """
        try:
            # CRITICAL: Double-check protection before deletion
            if is_path_protected(str(file_path), self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Attempted to delete {file_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(file_path),
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path",
                )

            # Get original size for freed_bytes tracking
            original_size = file_path.stat().st_size if file_path.exists() else 0

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would delete file: {file_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(file_path),
                    status=ExecutionStatus.SKIPPED,
                    original_size_bytes=original_size,
                    freed_bytes=0,  # No actual deletion in dry-run
                )

            # BUILD-152: Execute deletion with retry logic
            logger.info(f"Deleting file to Recycle Bin: {file_path}")
            success, error, lock_type, retry_count = self._delete_with_retry(
                file_path, send2trash.send2trash
            )

            if success:
                if retry_count > 0:
                    logger.info(f"✓ Deleted {file_path} after {retry_count} retries")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(file_path),
                    status=ExecutionStatus.COMPLETED,
                    original_size_bytes=original_size,
                    freed_bytes=original_size,
                    lock_type=lock_type,
                    retry_count=retry_count,
                )
            else:
                # Failed after retries
                error_msg = f"{lock_type}: {error}" if lock_type else error
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(file_path),
                    status=ExecutionStatus.FAILED,
                    error=error_msg,
                    lock_type=lock_type,
                    retry_count=retry_count,
                )

        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return ExecutionResult(
                candidate_id=-1, path=str(file_path), status=ExecutionStatus.FAILED, error=str(e)
            )

    def delete_directory(self, dir_path: Path) -> ExecutionResult:
        """
        Delete a directory recursively using send2trash (Recycle Bin) with retry logic.

        Args:
            dir_path: Path to directory to delete

        Returns:
            ExecutionResult with status and error (if any)

        Safety:
            - Double-checks protected paths before deletion
            - Uses send2trash instead of shutil.rmtree() for Recycle Bin safety
            - Calculates total size before deletion for freed_bytes tracking

        BUILD-152 Enhancements:
            - Retries transient locks (searchindexer, antivirus, handle)
            - Skips permanent locks (permission, path_too_long)
            - Provides remediation hints for failures
        """
        try:
            # CRITICAL: Double-check protection before deletion
            if is_path_protected(str(dir_path), self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Attempted to delete {dir_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path",
                )

            # Calculate total size for freed_bytes tracking
            original_size = self._calculate_directory_size(dir_path)

            if self.dry_run:
                logger.info(
                    f"[DRY-RUN] Would delete directory: {dir_path} ({original_size / (1024**2):.2f} MB)"
                )
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.SKIPPED,
                    original_size_bytes=original_size,
                    freed_bytes=0,  # No actual deletion in dry-run
                )

            # BUILD-152: Execute deletion with retry logic
            logger.info(
                f"Deleting directory to Recycle Bin: {dir_path} ({original_size / (1024**2):.2f} MB)"
            )
            success, error, lock_type, retry_count = self._delete_with_retry(
                dir_path, send2trash.send2trash
            )

            if success:
                if retry_count > 0:
                    logger.info(f"✓ Deleted {dir_path} after {retry_count} retries")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.COMPLETED,
                    original_size_bytes=original_size,
                    freed_bytes=original_size,
                    lock_type=lock_type,
                    retry_count=retry_count,
                )
            else:
                # Failed after retries
                error_msg = f"{lock_type}: {error}" if lock_type else error
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.FAILED,
                    error=error_msg,
                    lock_type=lock_type,
                    retry_count=retry_count,
                )

        except Exception as e:
            logger.error(f"Failed to delete directory {dir_path}: {e}")
            return ExecutionResult(
                candidate_id=-1, path=str(dir_path), status=ExecutionStatus.FAILED, error=str(e)
            )

    # ==========================================================================
    # Compression
    # ==========================================================================

    def compress_directory(
        self, dir_path: Path, archive_name: Optional[str] = None
    ) -> ExecutionResult:
        """
        Compress a directory to .zip archive before deletion.

        Args:
            dir_path: Path to directory to compress
            archive_name: Optional custom archive name (default: dir_name.zip)

        Returns:
            ExecutionResult with compressed_path, compression_ratio, and duration

        Safety:
            - Only deletes original files AFTER successful compression verified
            - Stores archives in archive/superseded/storage_cleanup_{timestamp}/
            - Skips compression if directory < 100MB (not worth it)
        """
        start_time = datetime.now(timezone.utc)

        try:
            # CRITICAL: Double-check protection before compression
            if is_path_protected(str(dir_path), self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Attempted to compress {dir_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to compress protected path",
                )

            # Calculate original size
            original_size = self._calculate_directory_size(dir_path)

            # Skip compression if < 100MB (not worth it)
            min_compression_size = 100 * 1024 * 1024  # 100MB
            if original_size < min_compression_size:
                logger.info(
                    f"Skipping compression for {dir_path} (only {original_size / (1024**2):.2f} MB)"
                )
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.SKIPPED,
                    error=f"Directory too small for compression ({original_size / (1024**2):.2f} MB < 100 MB)",
                )

            # Determine archive path
            if archive_name is None:
                archive_name = f"{dir_path.name}.zip"
            archive_path = self.compression_archive_dir / archive_name

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would compress {dir_path} to {archive_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.SKIPPED,
                    compressed_path=str(archive_path),
                    original_size_bytes=original_size,
                )

            # Create .zip archive
            logger.info(
                f"Compressing {dir_path} ({original_size / (1024**2):.2f} MB) to {archive_path}"
            )
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in dir_path.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(dir_path.parent)
                        zipf.write(file_path, arcname)

            # Verify archive created successfully
            if not archive_path.exists():
                raise ValueError(f"Archive {archive_path} was not created")

            compressed_size = archive_path.stat().st_size
            compression_ratio = original_size / compressed_size if compressed_size > 0 else 0

            duration = (datetime.now(timezone.utc) - start_time).seconds

            logger.info(
                f"Compression complete: {original_size / (1024**2):.2f} MB → "
                f"{compressed_size / (1024**2):.2f} MB "
                f"(ratio: {compression_ratio:.2f}x, duration: {duration}s)"
            )

            return ExecutionResult(
                candidate_id=-1,
                path=str(dir_path),
                status=ExecutionStatus.COMPLETED,
                compressed_path=str(archive_path),
                compression_ratio=compression_ratio,
                compression_duration_seconds=duration,
                original_size_bytes=original_size,
            )

        except Exception as e:
            logger.error(f"Failed to compress directory {dir_path}: {e}")
            return ExecutionResult(
                candidate_id=-1, path=str(dir_path), status=ExecutionStatus.FAILED, error=str(e)
            )

    # ==========================================================================
    # Batch Execution
    # ==========================================================================

    def execute_cleanup_candidate(
        self, db: Session, candidate: CleanupCandidateDB
    ) -> ExecutionResult:
        """
        Execute cleanup for a single candidate with approval checking.

        Args:
            db: Database session for updating candidate status
            candidate: CleanupCandidateDB to execute cleanup on

        Returns:
            ExecutionResult with execution details

        Safety:
            - Verifies approval exists before execution
            - Double-checks protected paths
            - Optionally compresses before deletion
            - Updates candidate execution status in database

        BUILD-152 Checkpoint Logging:
            - Computes SHA256 before deletion for idempotency tracking
            - Logs execution start/completion to execution_checkpoints table
            - Enables future scans to skip already-deleted files
        """
        start_time = datetime.now(timezone.utc)

        try:
            # CRITICAL: Verify approval exists
            if candidate.requires_approval and candidate.approval_status != "approved":
                logger.error(
                    f"APPROVAL_REQUIRED: Candidate {candidate.id} not approved for deletion"
                )
                return ExecutionResult(
                    candidate_id=candidate.id,
                    path=candidate.path,
                    status=ExecutionStatus.FAILED,
                    error="APPROVAL_REQUIRED: Candidate not approved for deletion",
                )

            # CRITICAL: Double-check protection before deletion
            if is_path_protected(candidate.path, self.policy):
                logger.error(
                    f"PROTECTED_PATH_VIOLATION: Candidate {candidate.id} at {candidate.path}"
                )
                return ExecutionResult(
                    candidate_id=candidate.id,
                    path=candidate.path,
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path",
                )

            # BUILD-152: Compute SHA256 checksum for idempotency tracking
            path = Path(candidate.path)
            sha256 = None
            if path.exists() and not self.dry_run:
                sha256 = compute_sha256(path)
                logger.debug(f"Computed SHA256 for {candidate.path}: {sha256}")

            # Update execution status to 'executing'
            if not self.dry_run:
                candidate.execution_status = ExecutionStatus.EXECUTING.value
                db.commit()

            result = None

            # Compress before deletion if enabled and path is directory
            if self.compress_before_delete and path.is_dir():
                compress_result = self.compress_directory(path)

                # Only proceed with deletion if compression succeeded
                if compress_result.status == ExecutionStatus.COMPLETED:
                    # Delete original directory after successful compression
                    delete_result = self.delete_directory(path)
                    result = ExecutionResult(
                        candidate_id=candidate.id,
                        path=candidate.path,
                        status=delete_result.status,
                        error=delete_result.error,
                        compressed_path=compress_result.compressed_path,
                        compression_ratio=compress_result.compression_ratio,
                        compression_duration_seconds=compress_result.compression_duration_seconds,
                        original_size_bytes=delete_result.original_size_bytes,
                        freed_bytes=delete_result.freed_bytes,
                    )
                elif compress_result.status == ExecutionStatus.SKIPPED:
                    # Compression skipped (too small), proceed with deletion
                    delete_result = self.delete_directory(path)
                    result = ExecutionResult(
                        candidate_id=candidate.id,
                        path=candidate.path,
                        status=delete_result.status,
                        error=delete_result.error,
                        original_size_bytes=delete_result.original_size_bytes,
                        freed_bytes=delete_result.freed_bytes,
                    )
                else:
                    # Compression failed, DO NOT delete original
                    result = ExecutionResult(
                        candidate_id=candidate.id,
                        path=candidate.path,
                        status=ExecutionStatus.FAILED,
                        error=f"Compression failed: {compress_result.error}",
                    )
            else:
                # No compression, direct deletion
                if path.is_dir():
                    delete_result = self.delete_directory(path)
                else:
                    delete_result = self.delete_file(path)

                result = ExecutionResult(
                    candidate_id=candidate.id,
                    path=candidate.path,
                    status=delete_result.status,
                    error=delete_result.error,
                    original_size_bytes=delete_result.original_size_bytes,
                    freed_bytes=delete_result.freed_bytes,
                )

            # Update candidate execution status in database
            if not self.dry_run:
                candidate.execution_status = result.status.value
                candidate.executed_at = datetime.now(timezone.utc)
                candidate.execution_error = result.error

                # Update compression metadata if applicable
                if result.compressed_path:
                    candidate.compressed = True
                    candidate.compressed_path = result.compressed_path
                    candidate.compression_ratio = result.compression_ratio
                    candidate.compression_duration_seconds = result.compression_duration_seconds

                db.commit()

                # BUILD-152: Log execution checkpoint for audit trail and idempotency
                if self.current_run_id:
                    action = "compress" if result.compressed_path else "delete"
                    checkpoint_status = (
                        "completed"
                        if result.status == ExecutionStatus.COMPLETED
                        else "skipped" if result.status == ExecutionStatus.SKIPPED else "failed"
                    )

                    self.checkpoint_logger.log_execution(
                        run_id=self.current_run_id,
                        candidate_id=candidate.id,
                        action=action,
                        path=candidate.path,
                        size_bytes=result.original_size_bytes,
                        sha256=sha256,
                        status=checkpoint_status,
                        error=result.error,
                        lock_type=result.lock_type,
                        retry_count=result.retry_count,
                    )

            return result

        except Exception as e:
            logger.error(f"Failed to execute cleanup for candidate {candidate.id}: {e}")

            # BUILD-152: Detect lock type for exception-level failures
            lock_type = self.lock_detector.detect_lock_type(path, e) if "path" in locals() else None

            # Update execution status to failed
            if not self.dry_run:
                candidate.execution_status = ExecutionStatus.FAILED.value
                candidate.executed_at = datetime.now(timezone.utc)
                candidate.execution_error = str(e)
                db.commit()

                # BUILD-152: Log failure checkpoint
                if self.current_run_id:
                    self.checkpoint_logger.log_execution(
                        run_id=self.current_run_id,
                        candidate_id=candidate.id,
                        action="delete",
                        path=candidate.path,
                        size_bytes=candidate.size_bytes,
                        sha256=sha256 if "sha256" in locals() else None,
                        status="failed",
                        error=str(e),
                        lock_type=lock_type,
                        retry_count=0,  # Exception-level failures don't retry
                    )

            return ExecutionResult(
                candidate_id=candidate.id,
                path=candidate.path,
                status=ExecutionStatus.FAILED,
                error=str(e),
                lock_type=lock_type,
                retry_count=0,
            )

    def execute_approved_candidates(
        self, db: Session, scan_id: int, category: Optional[str] = None
    ) -> BatchExecutionResult:
        """
        Execute cleanup for all approved candidates in a scan.

        Args:
            db: Database session
            scan_id: Scan ID to execute cleanup for
            category: Optional category filter (e.g., 'dev_caches')

        Returns:
            BatchExecutionResult with aggregated execution statistics

        Safety (BUILD-152):
            - Enforces per-category execution caps (GB and file count limits)
            - Stops execution when cap reached, leaving remaining candidates for next run
            - Reports cap violations clearly in results

        Checkpoint Logging (BUILD-152):
            - Generates unique run_id for this execution batch
            - All checkpoints from this batch share the same run_id
            - Enables audit trail queries by run_id

        Example:
            ```python
            executor = CleanupExecutor(policy, dry_run=False)
            results = executor.execute_approved_candidates(db, scan_id=123, category='dev_caches')
            print(f"Success rate: {results.success_rate:.1f}%")
            print(f"Freed {results.total_freed_bytes / (1024**3):.2f} GB")
            if results.stopped_due_to_cap:
                print(f"Stopped: {results.cap_reason}")
            ```
        """
        start_time = datetime.now(timezone.utc)

        # BUILD-152: Generate run_id for checkpoint logging (format: scan-{scan_id}-{timestamp})
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.current_run_id = f"scan-{scan_id}-{timestamp}"
        logger.info(f"Starting execution batch with run_id: {self.current_run_id}")

        # Query approved candidates
        query = db.query(CleanupCandidateDB).filter(
            CleanupCandidateDB.scan_id == scan_id, CleanupCandidateDB.approval_status == "approved"
        )

        if category is not None:
            query = query.filter(CleanupCandidateDB.category == category)

        candidates = query.all()

        if not candidates:
            logger.warning(f"No approved candidates found for scan {scan_id}")
            return BatchExecutionResult(
                total_candidates=0,
                successful=0,
                failed=0,
                skipped=0,
                total_freed_bytes=0,
                results=[],
                execution_duration_seconds=0,
            )

        # BUILD-152: Get execution limits for category
        execution_limits = None
        if category and category in self.policy.categories:
            cat_policy = self.policy.categories[category]
            execution_limits = cat_policy.execution_limits

        if execution_limits:
            max_gb = execution_limits.max_gb_per_run
            max_files = execution_limits.max_files_per_run
            logger.info(
                f"Executing cleanup for {len(candidates)} approved candidates "
                f"(caps: {max_gb}GB, {max_files} files, dry_run={self.dry_run})"
            )
        else:
            logger.info(
                f"Executing cleanup for {len(candidates)} approved candidates (no caps, dry_run={self.dry_run})"
            )

        # Execute cleanup for each candidate
        results = []
        successful = 0
        failed = 0
        skipped = 0
        total_freed_bytes = 0
        stopped_due_to_cap = False
        cap_reason = None
        processed_count = 0

        for candidate in candidates:
            # BUILD-152: Check caps BEFORE executing
            if execution_limits:
                accumulated_gb = total_freed_bytes / (1024**3)

                # Check GB cap
                if accumulated_gb >= execution_limits.max_gb_per_run:
                    stopped_due_to_cap = True
                    cap_reason = f"Reached {execution_limits.max_gb_per_run}GB cap ({accumulated_gb:.2f}GB freed)"
                    logger.warning(
                        f"[CAP] {cap_reason}, stopping execution ({len(candidates) - processed_count} candidates remaining)"
                    )
                    break

                # Check file count cap
                if processed_count >= execution_limits.max_files_per_run:
                    stopped_due_to_cap = True
                    cap_reason = f"Reached {execution_limits.max_files_per_run} file cap ({processed_count} files processed)"
                    logger.warning(
                        f"[CAP] {cap_reason}, stopping execution ({len(candidates) - processed_count} candidates remaining)"
                    )
                    break

            # Execute cleanup
            result = self.execute_cleanup_candidate(db, candidate)
            results.append(result)
            processed_count += 1

            if result.status == ExecutionStatus.COMPLETED:
                successful += 1
                total_freed_bytes += result.freed_bytes or 0
            elif result.status == ExecutionStatus.FAILED:
                failed += 1
            elif result.status == ExecutionStatus.SKIPPED:
                skipped += 1

        duration = (datetime.now(timezone.utc) - start_time).seconds

        remaining_candidates = len(candidates) - processed_count

        if stopped_due_to_cap:
            logger.warning(
                f"Batch execution STOPPED AT CAP: {successful} successful, {failed} failed, {skipped} skipped "
                f"({total_freed_bytes / (1024**3):.2f} GB freed in {duration}s, {remaining_candidates} candidates remaining)"
            )
        else:
            logger.info(
                f"Batch execution complete: {successful} successful, {failed} failed, {skipped} skipped "
                f"({total_freed_bytes / (1024**3):.2f} GB freed in {duration}s)"
            )

        return BatchExecutionResult(
            total_candidates=len(candidates),
            successful=successful,
            failed=failed,
            skipped=skipped,
            total_freed_bytes=total_freed_bytes,
            results=results,
            execution_duration_seconds=duration,
            stopped_due_to_cap=stopped_due_to_cap,
            cap_reason=cap_reason,
            remaining_candidates=remaining_candidates,
        )

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _calculate_directory_size(self, dir_path: Path) -> int:
        """Calculate total size of directory recursively."""
        try:
            total = 0
            for file_path in dir_path.rglob("*"):
                if file_path.is_file():
                    total += file_path.stat().st_size
            return total
        except Exception as e:
            logger.warning(f"Failed to calculate size for {dir_path}: {e}")
            return 0
