"""
Database session helpers and query utilities for Storage Optimizer.

Provides helper functions for interacting with storage optimizer tables
using Autopack's existing database session management.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..models import ApprovalDecision, CleanupCandidateDB, StorageScan


# ==============================================================================
# Query Helpers - Scan History
# ==============================================================================


def get_scan_history(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    since_days: Optional[int] = None,
    scan_type: Optional[str] = None,
    scan_target: Optional[str] = None,
) -> List[StorageScan]:
    """
    Get scan history with pagination and optional filters.

    Args:
        db: Database session (from get_db() dependency)
        limit: Maximum number of scans to return (default: 50)
        offset: Number of scans to skip (default: 0)
        since_days: Only include scans from the last N days (optional)
        scan_type: Filter by scan type ('drive' or 'directory', optional)
        scan_target: Filter by exact scan target path (optional)

    Returns:
        List of StorageScan objects ordered by timestamp descending

    Example:
        ```python
        # Get last 50 scans
        scans = get_scan_history(db)

        # Get scans from last 30 days
        recent_scans = get_scan_history(db, since_days=30)

        # Get directory scans only
        dir_scans = get_scan_history(db, scan_type='directory')
        ```
    """
    query = db.query(StorageScan)

    # Apply filters
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        query = query.filter(StorageScan.timestamp >= cutoff)

    if scan_type is not None:
        query = query.filter(StorageScan.scan_type == scan_type)

    if scan_target is not None:
        query = query.filter(StorageScan.scan_target == scan_target)

    # Order and paginate
    return query.order_by(desc(StorageScan.timestamp)).offset(offset).limit(limit).all()


def get_latest_scan_by_target(
    db: Session, scan_target: str, scan_type: Optional[str] = None
) -> Optional[StorageScan]:
    """
    Get the most recent scan for a specific target.

    Args:
        db: Database session
        scan_target: Exact scan target path (e.g., 'C:' or 'c:/dev/Autopack')
        scan_type: Optional scan type filter ('drive' or 'directory')

    Returns:
        Most recent StorageScan or None if no scans found

    Example:
        ```python
        # Get latest C: drive scan
        latest = get_latest_scan_by_target(db, 'C:', scan_type='drive')
        ```
    """
    query = db.query(StorageScan).filter(StorageScan.scan_target == scan_target)

    if scan_type is not None:
        query = query.filter(StorageScan.scan_type == scan_type)

    return query.order_by(desc(StorageScan.timestamp)).first()


def get_scan_by_id(db: Session, scan_id: int) -> Optional[StorageScan]:
    """
    Get a specific scan by ID.

    Args:
        db: Database session
        scan_id: Primary key of the scan

    Returns:
        StorageScan or None if not found

    Example:
        ```python
        scan = get_scan_by_id(db, 123)
        if scan:
            print(f"Scan found {scan.total_items_scanned} items")
        ```
    """
    return db.query(StorageScan).filter(StorageScan.id == scan_id).first()


def get_scan_count(db: Session, since_days: Optional[int] = None) -> int:
    """
    Get total number of scans in database.

    Args:
        db: Database session
        since_days: Only count scans from the last N days (optional)

    Returns:
        Count of scans matching criteria

    Example:
        ```python
        total = get_scan_count(db)
        recent = get_scan_count(db, since_days=30)
        print(f"{recent} scans in last 30 days out of {total} total")
        ```
    """
    query = db.query(func.count(StorageScan.id))

    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        query = query.filter(StorageScan.timestamp >= cutoff)

    return query.scalar()


# ==============================================================================
# Query Helpers - Cleanup Candidates
# ==============================================================================


def get_cleanup_candidates_by_scan(
    db: Session,
    scan_id: int,
    category: Optional[str] = None,
    approval_status: Optional[str] = None,
    requires_approval: Optional[bool] = None,
    min_size_bytes: Optional[int] = None,
) -> List[CleanupCandidateDB]:
    """
    Get cleanup candidates for a specific scan.

    Args:
        db: Database session
        scan_id: Scan ID to filter by
        category: Filter by category (e.g., 'dev_caches', 'diagnostics_logs')
        approval_status: Filter by approval status ('pending', 'approved', 'rejected')
        requires_approval: Filter by whether approval is required
        min_size_bytes: Filter by minimum file size

    Returns:
        List of CleanupCandidateDB objects ordered by size descending

    Example:
        ```python
        # Get all candidates for scan 123
        candidates = get_cleanup_candidates_by_scan(db, 123)

        # Get approved dev_caches only
        approved = get_cleanup_candidates_by_scan(
            db, 123, category='dev_caches', approval_status='approved'
        )

        # Get large files (>1GB) requiring approval
        large = get_cleanup_candidates_by_scan(
            db, 123, min_size_bytes=1024**3, requires_approval=True
        )
        ```
    """
    query = db.query(CleanupCandidateDB).filter(CleanupCandidateDB.scan_id == scan_id)

    # Apply filters
    if category is not None:
        query = query.filter(CleanupCandidateDB.category == category)

    if approval_status is not None:
        query = query.filter(CleanupCandidateDB.approval_status == approval_status)

    if requires_approval is not None:
        query = query.filter(CleanupCandidateDB.requires_approval == requires_approval)

    if min_size_bytes is not None:
        query = query.filter(CleanupCandidateDB.size_bytes >= min_size_bytes)

    # Order by size descending (largest files first)
    return query.order_by(desc(CleanupCandidateDB.size_bytes)).all()


def get_candidate_by_id(db: Session, candidate_id: int) -> Optional[CleanupCandidateDB]:
    """
    Get a specific cleanup candidate by ID.

    Args:
        db: Database session
        candidate_id: Primary key of the candidate

    Returns:
        CleanupCandidateDB or None if not found
    """
    return db.query(CleanupCandidateDB).filter(CleanupCandidateDB.id == candidate_id).first()


def get_candidates_by_ids(db: Session, candidate_ids: List[int]) -> List[CleanupCandidateDB]:
    """
    Get multiple cleanup candidates by their IDs.

    Args:
        db: Database session
        candidate_ids: List of candidate primary keys

    Returns:
        List of CleanupCandidateDB objects (may be fewer than requested if some IDs not found)

    Example:
        ```python
        candidates = get_candidates_by_ids(db, [1, 2, 3, 4, 5])
        ```
    """
    return db.query(CleanupCandidateDB).filter(CleanupCandidateDB.id.in_(candidate_ids)).all()


def get_candidate_stats_by_category(db: Session, scan_id: int) -> dict:
    """
    Get aggregate statistics for cleanup candidates grouped by category.

    Args:
        db: Database session
        scan_id: Scan ID to analyze

    Returns:
        Dictionary mapping category name to stats dict with keys:
        - count: Number of candidates
        - total_size_bytes: Total size of all candidates
        - approved_count: Number of approved candidates
        - approved_size_bytes: Total size of approved candidates

    Example:
        ```python
        stats = get_candidate_stats_by_category(db, 123)
        # {
        #   'dev_caches': {
        #     'count': 15,
        #     'total_size_bytes': 21474836480,  # 20GB
        #     'approved_count': 10,
        #     'approved_size_bytes': 15032385536  # 14GB
        #   },
        #   'diagnostics_logs': {...}
        # }
        ```
    """
    candidates = db.query(CleanupCandidateDB).filter(CleanupCandidateDB.scan_id == scan_id).all()

    stats = {}
    for candidate in candidates:
        if candidate.category not in stats:
            stats[candidate.category] = {
                "count": 0,
                "total_size_bytes": 0,
                "approved_count": 0,
                "approved_size_bytes": 0,
            }

        stats[candidate.category]["count"] += 1
        stats[candidate.category]["total_size_bytes"] += candidate.size_bytes

        if candidate.approval_status == "approved":
            stats[candidate.category]["approved_count"] += 1
            stats[candidate.category]["approved_size_bytes"] += candidate.size_bytes

    return stats


# ==============================================================================
# Query Helpers - Approval Decisions
# ==============================================================================


def get_approval_decisions_by_scan(db: Session, scan_id: int) -> List[ApprovalDecision]:
    """
    Get all approval decisions for a specific scan.

    Args:
        db: Database session
        scan_id: Scan ID to filter by

    Returns:
        List of ApprovalDecision objects ordered by approved_at descending

    Example:
        ```python
        decisions = get_approval_decisions_by_scan(db, 123)
        for decision in decisions:
            print(f"{decision.approved_by} {decision.decision} "
                  f"{decision.total_candidates} candidates "
                  f"via {decision.approval_method}")
        ```
    """
    return (
        db.query(ApprovalDecision)
        .filter(ApprovalDecision.scan_id == scan_id)
        .order_by(desc(ApprovalDecision.approved_at))
        .all()
    )


def create_approval_decision(
    db: Session,
    scan_id: int,
    candidate_ids: List[int],
    approved_by: str,
    decision: str,
    approval_method: str = "api",
    notes: Optional[str] = None,
) -> ApprovalDecision:
    """
    Create a new approval decision and update candidate approval status.

    Args:
        db: Database session
        scan_id: Scan ID this decision applies to
        candidate_ids: List of candidate IDs being approved/rejected
        approved_by: User identifier (email, username, etc.)
        decision: 'approve', 'reject', or 'defer'
        approval_method: How approval was given ('cli_interactive', 'api', 'telegram', 'automated')
        notes: Optional notes about the decision

    Returns:
        Created ApprovalDecision object

    Side Effects:
        Updates approval_status, approved_by, and approved_at fields on all
        specified CleanupCandidateDB records.

    Example:
        ```python
        # Approve 5 candidates via CLI
        decision = create_approval_decision(
            db,
            scan_id=123,
            candidate_ids=[1, 2, 3, 4, 5],
            approved_by='user@example.com',
            decision='approve',
            approval_method='cli_interactive',
            notes='Removing old dev_caches'
        )
        db.commit()
        ```
    """
    # Get candidates to calculate totals
    candidates = get_candidates_by_ids(db, candidate_ids)

    if not candidates:
        raise ValueError(f"No candidates found for IDs: {candidate_ids}")

    total_size_bytes = sum(c.size_bytes for c in candidates)

    # Create approval decision record
    approval = ApprovalDecision(
        scan_id=scan_id,
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc),
        approval_method=approval_method,
        total_candidates=len(candidates),
        total_size_bytes=total_size_bytes,
        decision=decision,
        notes=notes,
    )
    db.add(approval)

    # Update candidate approval status
    approval_status = "approved" if decision == "approve" else "rejected"
    for candidate in candidates:
        candidate.approval_status = approval_status
        candidate.approved_by = approved_by
        candidate.approved_at = datetime.now(timezone.utc)
        if decision == "reject" and notes:
            candidate.rejection_reason = notes

    return approval


# ==============================================================================
# Trend Analysis Helpers
# ==============================================================================


def compare_scans(db: Session, scan_id_current: int, scan_id_previous: int) -> dict:
    """
    Compare two scans to analyze storage trends.

    Args:
        db: Database session
        scan_id_current: ID of the more recent scan
        scan_id_previous: ID of the older scan to compare against

    Returns:
        Dictionary with comparison metrics:
        - total_size_change_bytes: Change in total size
        - cleanup_candidates_change: Change in candidate count
        - potential_savings_change_bytes: Change in potential savings
        - categories_added: List of new categories in current scan
        - categories_removed: List of categories no longer in current scan

    Example:
        ```python
        comparison = compare_scans(db, scan_id_current=124, scan_id_previous=123)
        if comparison['total_size_change_bytes'] > 0:
            print(f"Disk usage increased by {comparison['total_size_change_bytes']} bytes")
        ```
    """
    current = get_scan_by_id(db, scan_id_current)
    previous = get_scan_by_id(db, scan_id_previous)

    if not current or not previous:
        raise ValueError(f"Scan not found: current={scan_id_current}, previous={scan_id_previous}")

    # Basic numeric comparisons
    total_size_change = current.total_size_bytes - previous.total_size_bytes
    candidates_change = current.cleanup_candidates_count - previous.cleanup_candidates_count
    savings_change = current.potential_savings_bytes - previous.potential_savings_bytes

    # Category comparisons
    current_stats = get_candidate_stats_by_category(db, scan_id_current)
    previous_stats = get_candidate_stats_by_category(db, scan_id_previous)

    current_categories = set(current_stats.keys())
    previous_categories = set(previous_stats.keys())

    return {
        "total_size_change_bytes": total_size_change,
        "cleanup_candidates_change": candidates_change,
        "potential_savings_change_bytes": savings_change,
        "categories_added": list(current_categories - previous_categories),
        "categories_removed": list(previous_categories - current_categories),
        "category_stats_current": current_stats,
        "category_stats_previous": previous_stats,
        "scan_current": current,
        "scan_previous": previous,
    }
