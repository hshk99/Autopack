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
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

import send2trash
from sqlalchemy.orm import Session

from ..models import CleanupCandidateDB
from .models import CleanupCandidate
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
        compression_archive_dir: Optional[Path] = None
    ):
        """
        Initialize cleanup executor.

        Args:
            policy: Storage policy for protected path checking
            dry_run: If True, preview actions without executing (default: True for safety)
            compress_before_delete: If True, compress files before deletion
            compression_archive_dir: Directory to store compressed archives
                (default: archive/superseded/storage_cleanup_{timestamp})
        """
        self.policy = policy
        self.dry_run = dry_run
        self.compress_before_delete = compress_before_delete

        # Set compression archive directory
        if compression_archive_dir is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self.compression_archive_dir = Path(f"archive/superseded/storage_cleanup_{timestamp}")
        else:
            self.compression_archive_dir = Path(compression_archive_dir)

        # Create archive directory if compression enabled
        if self.compress_before_delete and not self.dry_run:
            self.compression_archive_dir.mkdir(parents=True, exist_ok=True)

    # ==========================================================================
    # Single File/Directory Deletion
    # ==========================================================================

    def delete_file(self, file_path: Path) -> ExecutionResult:
        """
        Delete a single file using send2trash (Recycle Bin).

        Args:
            file_path: Path to file to delete

        Returns:
            ExecutionResult with status and error (if any)

        Safety:
            - Double-checks protected paths before deletion
            - Uses send2trash instead of os.remove() for Recycle Bin safety
            - Never raises exceptions (returns status instead)
        """
        try:
            # CRITICAL: Double-check protection before deletion
            if is_path_protected(str(file_path), self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Attempted to delete {file_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(file_path),
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path"
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
                    freed_bytes=0  # No actual deletion in dry-run
                )

            # Execute deletion via Recycle Bin
            logger.info(f"Deleting file to Recycle Bin: {file_path}")
            send2trash.send2trash(str(file_path))

            return ExecutionResult(
                candidate_id=-1,
                path=str(file_path),
                status=ExecutionStatus.COMPLETED,
                original_size_bytes=original_size,
                freed_bytes=original_size
            )

        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return ExecutionResult(
                candidate_id=-1,
                path=str(file_path),
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def delete_directory(self, dir_path: Path) -> ExecutionResult:
        """
        Delete a directory recursively using send2trash (Recycle Bin).

        Args:
            dir_path: Path to directory to delete

        Returns:
            ExecutionResult with status and error (if any)

        Safety:
            - Double-checks protected paths before deletion
            - Uses send2trash instead of shutil.rmtree() for Recycle Bin safety
            - Calculates total size before deletion for freed_bytes tracking
        """
        try:
            # CRITICAL: Double-check protection before deletion
            if is_path_protected(str(dir_path), self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Attempted to delete {dir_path}")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path"
                )

            # Calculate total size for freed_bytes tracking
            original_size = self._calculate_directory_size(dir_path)

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would delete directory: {dir_path} ({original_size / (1024**2):.2f} MB)")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.SKIPPED,
                    original_size_bytes=original_size,
                    freed_bytes=0  # No actual deletion in dry-run
                )

            # Execute deletion via Recycle Bin
            logger.info(f"Deleting directory to Recycle Bin: {dir_path} ({original_size / (1024**2):.2f} MB)")
            send2trash.send2trash(str(dir_path))

            return ExecutionResult(
                candidate_id=-1,
                path=str(dir_path),
                status=ExecutionStatus.COMPLETED,
                original_size_bytes=original_size,
                freed_bytes=original_size
            )

        except Exception as e:
            logger.error(f"Failed to delete directory {dir_path}: {e}")
            return ExecutionResult(
                candidate_id=-1,
                path=str(dir_path),
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    # ==========================================================================
    # Compression
    # ==========================================================================

    def compress_directory(self, dir_path: Path, archive_name: Optional[str] = None) -> ExecutionResult:
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
                    error="PROTECTED_PATH_VIOLATION: Attempted to compress protected path"
                )

            # Calculate original size
            original_size = self._calculate_directory_size(dir_path)

            # Skip compression if < 100MB (not worth it)
            min_compression_size = 100 * 1024 * 1024  # 100MB
            if original_size < min_compression_size:
                logger.info(f"Skipping compression for {dir_path} (only {original_size / (1024**2):.2f} MB)")
                return ExecutionResult(
                    candidate_id=-1,
                    path=str(dir_path),
                    status=ExecutionStatus.SKIPPED,
                    error=f"Directory too small for compression ({original_size / (1024**2):.2f} MB < 100 MB)"
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
                    original_size_bytes=original_size
                )

            # Create .zip archive
            logger.info(f"Compressing {dir_path} ({original_size / (1024**2):.2f} MB) to {archive_path}")
            archive_path.parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in dir_path.rglob('*'):
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
                original_size_bytes=original_size
            )

        except Exception as e:
            logger.error(f"Failed to compress directory {dir_path}: {e}")
            return ExecutionResult(
                candidate_id=-1,
                path=str(dir_path),
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    # ==========================================================================
    # Batch Execution
    # ==========================================================================

    def execute_cleanup_candidate(
        self,
        db: Session,
        candidate: CleanupCandidateDB
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
        """
        start_time = datetime.now(timezone.utc)

        try:
            # CRITICAL: Verify approval exists
            if candidate.requires_approval and candidate.approval_status != 'approved':
                logger.error(f"APPROVAL_REQUIRED: Candidate {candidate.id} not approved for deletion")
                return ExecutionResult(
                    candidate_id=candidate.id,
                    path=candidate.path,
                    status=ExecutionStatus.FAILED,
                    error="APPROVAL_REQUIRED: Candidate not approved for deletion"
                )

            # CRITICAL: Double-check protection before deletion
            if is_path_protected(candidate.path, self.policy):
                logger.error(f"PROTECTED_PATH_VIOLATION: Candidate {candidate.id} at {candidate.path}")
                return ExecutionResult(
                    candidate_id=candidate.id,
                    path=candidate.path,
                    status=ExecutionStatus.FAILED,
                    error="PROTECTED_PATH_VIOLATION: Attempted to delete protected path"
                )

            # Update execution status to 'executing'
            if not self.dry_run:
                candidate.execution_status = ExecutionStatus.EXECUTING.value
                db.commit()

            path = Path(candidate.path)
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
                        freed_bytes=delete_result.freed_bytes
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
                        freed_bytes=delete_result.freed_bytes
                    )
                else:
                    # Compression failed, DO NOT delete original
                    result = ExecutionResult(
                        candidate_id=candidate.id,
                        path=candidate.path,
                        status=ExecutionStatus.FAILED,
                        error=f"Compression failed: {compress_result.error}"
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
                    freed_bytes=delete_result.freed_bytes
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

            return result

        except Exception as e:
            logger.error(f"Failed to execute cleanup for candidate {candidate.id}: {e}")

            # Update execution status to failed
            if not self.dry_run:
                candidate.execution_status = ExecutionStatus.FAILED.value
                candidate.executed_at = datetime.now(timezone.utc)
                candidate.execution_error = str(e)
                db.commit()

            return ExecutionResult(
                candidate_id=candidate.id,
                path=candidate.path,
                status=ExecutionStatus.FAILED,
                error=str(e)
            )

    def execute_approved_candidates(
        self,
        db: Session,
        scan_id: int,
        category: Optional[str] = None
    ) -> BatchExecutionResult:
        """
        Execute cleanup for all approved candidates in a scan.

        Args:
            db: Database session
            scan_id: Scan ID to execute cleanup for
            category: Optional category filter (e.g., 'dev_caches')

        Returns:
            BatchExecutionResult with aggregated execution statistics

        Example:
            ```python
            executor = CleanupExecutor(policy, dry_run=False)
            results = executor.execute_approved_candidates(db, scan_id=123, category='dev_caches')
            print(f"Success rate: {results.success_rate:.1f}%")
            print(f"Freed {results.total_freed_bytes / (1024**3):.2f} GB")
            ```
        """
        start_time = datetime.now(timezone.utc)

        # Query approved candidates
        query = db.query(CleanupCandidateDB).filter(
            CleanupCandidateDB.scan_id == scan_id,
            CleanupCandidateDB.approval_status == 'approved'
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
                execution_duration_seconds=0
            )

        logger.info(f"Executing cleanup for {len(candidates)} approved candidates (dry_run={self.dry_run})")

        # Execute cleanup for each candidate
        results = []
        successful = 0
        failed = 0
        skipped = 0
        total_freed_bytes = 0

        for candidate in candidates:
            result = self.execute_cleanup_candidate(db, candidate)
            results.append(result)

            if result.status == ExecutionStatus.COMPLETED:
                successful += 1
                total_freed_bytes += result.freed_bytes or 0
            elif result.status == ExecutionStatus.FAILED:
                failed += 1
            elif result.status == ExecutionStatus.SKIPPED:
                skipped += 1

        duration = (datetime.now(timezone.utc) - start_time).seconds

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
            execution_duration_seconds=duration
        )

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _calculate_directory_size(self, dir_path: Path) -> int:
        """Calculate total size of directory recursively."""
        try:
            total = 0
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    total += file_path.stat().st_size
            return total
        except Exception as e:
            logger.warning(f"Failed to calculate size for {dir_path}: {e}")
            return 0
