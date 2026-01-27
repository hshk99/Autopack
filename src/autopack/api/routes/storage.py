"""Storage optimization endpoints.

Extracted from main.py as part of PR-API-3c.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from autopack import schemas
from autopack.api.deps import verify_api_key, verify_read_access
from autopack.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post(
    "/scan",
    response_model=schemas.StorageScanResponse,
    dependencies=[Depends(verify_api_key)],
)
def trigger_storage_scan(request: schemas.StorageScanRequest, db: Session = Depends(get_db)):
    """
    Trigger a new storage scan and optionally save results to database.

    Args:
        request: Scan configuration (scan_type, scan_target, max_depth, etc.)
        db: Database session

    Returns:
        StorageScanResponse with scan metadata and summary statistics

    Example:
        ```bash
        curl -X POST http://localhost:8000/storage/scan \
          -H "Content-Type: application/json" \
          -d '{
            "scan_type": "directory",
            "scan_target": "c:/dev/Autopack",
            "max_depth": 3,
            "max_items": 1000,
            "save_to_db": true,
            "created_by": "user@example.com"
          }'
        ```
    """
    from datetime import datetime, timezone

    from autopack.storage_optimizer import FileClassifier, StorageScanner, load_policy

    start_time = datetime.now(timezone.utc)

    # Load policy
    policy = load_policy()

    # Execute scan
    scanner = StorageScanner(max_depth=request.max_depth)

    if request.scan_type == "drive":
        results = scanner.scan_high_value_directories(
            request.scan_target, max_items=request.max_items
        )
    elif request.scan_type == "directory":
        results = scanner.scan_directory(request.scan_target, max_items=request.max_items)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid scan_type: {request.scan_type}")

    # Classify candidates
    classifier = FileClassifier(policy)
    candidates = classifier.classify_batch(results)

    # Calculate statistics
    total_size_bytes = sum(r.size_bytes for r in results)
    potential_savings_bytes = sum(c.size_bytes for c in candidates)
    scan_duration_seconds = (datetime.now(timezone.utc) - start_time).seconds

    # Save to database if requested
    if request.save_to_db:
        from autopack.models import CleanupCandidateDB, StorageScan

        scan = StorageScan(
            timestamp=start_time,
            scan_type=request.scan_type,
            scan_target=request.scan_target,
            max_depth=request.max_depth,
            max_items=request.max_items,
            policy_version=policy.version,
            total_items_scanned=len(results),
            total_size_bytes=total_size_bytes,
            cleanup_candidates_count=len(candidates),
            potential_savings_bytes=potential_savings_bytes,
            scan_duration_seconds=scan_duration_seconds,
            created_by=request.created_by,
        )
        db.add(scan)
        db.flush()  # Get scan.id before adding candidates

        # Save candidates
        for candidate in candidates:
            candidate_db = CleanupCandidateDB(
                scan_id=scan.id,
                path=candidate.path,
                size_bytes=candidate.size_bytes,
                age_days=candidate.age_days,
                last_modified=candidate.last_modified,
                category=candidate.category,
                reason=candidate.reason,
                requires_approval=candidate.requires_approval,
                approval_status="pending",
            )
            db.add(candidate_db)

        db.commit()
        db.refresh(scan)

        return scan
    else:
        # Return in-memory scan result (not persisted)
        return schemas.StorageScanResponse(
            id=-1,
            timestamp=start_time,
            scan_type=request.scan_type,
            scan_target=request.scan_target,
            total_items_scanned=len(results),
            total_size_bytes=total_size_bytes,
            cleanup_candidates_count=len(candidates),
            potential_savings_bytes=potential_savings_bytes,
            scan_duration_seconds=scan_duration_seconds,
            created_by=request.created_by,
        )


@router.get("/scans", response_model=List[schemas.StorageScanResponse])
def list_storage_scans(
    limit: int = 50,
    offset: int = 0,
    since_days: Optional[int] = None,
    scan_type: Optional[str] = None,
    scan_target: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """
    List storage scan history with pagination and optional filters.

    Args:
        limit: Maximum number of scans to return (default: 50, max: 200)
        offset: Number of scans to skip for pagination (default: 0)
        since_days: Only include scans from the last N days (optional)
        scan_type: Filter by scan type ('drive' or 'directory', optional)
        scan_target: Filter by exact scan target path (optional)
        db: Database session

    Returns:
        List of StorageScanResponse objects ordered by timestamp descending

    Example:
        ```bash
        # Get last 50 scans
        curl http://localhost:8000/storage/scans

        # Get scans from last 30 days
        curl http://localhost:8000/storage/scans?since_days=30

        # Get directory scans only
        curl http://localhost:8000/storage/scans?scan_type=directory

        # Pagination
        curl http://localhost:8000/storage/scans?limit=25&offset=25
        ```
    """
    from autopack.storage_optimizer.db import get_scan_history

    # Enforce max limit
    if limit > 200:
        limit = 200

    scans = get_scan_history(
        db,
        limit=limit,
        offset=offset,
        since_days=since_days,
        scan_type=scan_type,
        scan_target=scan_target,
    )

    return scans


@router.get("/scans/{scan_id}", response_model=schemas.StorageScanDetailResponse)
def get_storage_scan_detail(
    scan_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """
    Get detailed scan results including all cleanup candidates.

    Args:
        scan_id: Primary key of the scan
        db: Database session

    Returns:
        StorageScanDetailResponse with scan metadata, candidates, and stats

    Example:
        ```bash
        curl http://localhost:8000/storage/scans/123
        ```
    """
    from autopack.storage_optimizer.db import (
        get_candidate_stats_by_category,
        get_cleanup_candidates_by_scan,
        get_scan_by_id,
    )

    scan = get_scan_by_id(db, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    candidates = get_cleanup_candidates_by_scan(db, scan_id)
    stats = get_candidate_stats_by_category(db, scan_id)

    return schemas.StorageScanDetailResponse(
        scan=scan, candidates=candidates, stats_by_category=stats
    )


@router.post("/scans/{scan_id}/approve", dependencies=[Depends(verify_api_key)])
def approve_cleanup_candidates(
    scan_id: int, request: schemas.ApprovalRequest, db: Session = Depends(get_db)
):
    """
    Approve or reject cleanup candidates for a specific scan.

    Args:
        scan_id: Scan ID containing the candidates
        request: Approval decision (candidate_ids, approved_by, decision, notes)
        db: Database session

    Returns:
        Approval decision record with metadata

    Example:
        ```bash
        curl -X POST http://localhost:8000/storage/scans/123/approve \
          -H "Content-Type: application/json" \
          -d '{
            "candidate_ids": [1, 2, 3, 4, 5],
            "approved_by": "user@example.com",
            "decision": "approve",
            "approval_method": "api",
            "notes": "Removing old dev_caches"
          }'
        ```
    """
    from autopack.storage_optimizer.db import create_approval_decision, get_scan_by_id

    # Verify scan exists
    scan = get_scan_by_id(db, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    # Validate decision
    if request.decision not in ["approve", "reject", "defer"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {request.decision}. Must be 'approve', 'reject', or 'defer'",
        )

    # Create approval decision
    try:
        approval = create_approval_decision(
            db,
            scan_id=scan_id,
            candidate_ids=request.candidate_ids,
            approved_by=request.approved_by,
            decision=request.decision,
            approval_method=request.approval_method,
            notes=request.notes,
        )
        db.commit()
        db.refresh(approval)

        return {
            "approval_id": approval.id,
            "scan_id": scan_id,
            "decision": request.decision,
            "total_candidates": approval.total_candidates,
            "total_size_bytes": approval.total_size_bytes,
            "approved_by": request.approved_by,
            "approved_at": approval.approved_at,
        }

    except ValueError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid request parameters")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create approval decision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create approval decision")


@router.post(
    "/scans/{scan_id}/execute",
    response_model=schemas.BatchExecutionResponse,
    dependencies=[Depends(verify_api_key)],
)
def execute_approved_cleanup(
    scan_id: int, request: schemas.ExecutionRequest, db: Session = Depends(get_db)
):
    """
    Execute approved cleanup candidates (deletion or dry-run preview).

    SAFETY:
    - Only deletes candidates with approval_status='approved'
    - Uses send2trash (Recycle Bin) instead of permanent deletion
    - Double-checks protected paths before deletion
    - Dry-run mode enabled by default for safety

    Args:
        scan_id: Scan ID to execute cleanup for
        request: Execution configuration (dry_run, compress_before_delete, category)
        db: Database session

    Returns:
        BatchExecutionResponse with execution statistics and results

    Example:
        ```bash
        # Dry-run preview (no actual deletion)
        curl -X POST http://localhost:8000/storage/scans/123/execute \
          -H "Content-Type: application/json" \
          -d '{
            "dry_run": true,
            "compress_before_delete": false
          }'

        # Execute approved deletions
        curl -X POST http://localhost:8000/storage/scans/123/execute \
          -H "Content-Type: application/json" \
          -d '{
            "dry_run": false,
            "compress_before_delete": true,
            "category": "dev_caches"
          }'
        ```
    """
    from autopack.storage_optimizer import load_policy
    from autopack.storage_optimizer.db import get_scan_by_id
    from autopack.storage_optimizer.executor import CleanupExecutor

    # Verify scan exists
    scan = get_scan_by_id(db, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    # Load policy
    policy = load_policy()

    # Create executor
    executor = CleanupExecutor(
        policy=policy,
        dry_run=request.dry_run,
        compress_before_delete=request.compress_before_delete,
    )

    # Execute cleanup
    try:
        batch_result = executor.execute_approved_candidates(
            db, scan_id=scan_id, category=request.category
        )

        # Convert to response format
        results = []
        for result in batch_result.results:
            results.append(
                schemas.ExecutionResultResponse(
                    candidate_id=result.candidate_id,
                    path=result.path,
                    status=result.status.value,
                    error=result.error,
                    freed_bytes=result.freed_bytes,
                    compressed_path=result.compressed_path,
                )
            )

        return schemas.BatchExecutionResponse(
            total_candidates=batch_result.total_candidates,
            successful=batch_result.successful,
            failed=batch_result.failed,
            skipped=batch_result.skipped,
            total_freed_bytes=batch_result.total_freed_bytes,
            success_rate=batch_result.success_rate,
            execution_duration_seconds=batch_result.execution_duration_seconds,
            results=results,
        )

    except Exception as e:
        logger.error(f"Failed to execute cleanup for scan {scan_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to execute cleanup")


@router.get("/steam/games", response_model=schemas.SteamGamesListResponse)
def get_steam_games(
    min_size_gb: float = 10.0,
    min_age_days: int = 180,
    include_all: bool = False,
    _auth: str = Depends(verify_read_access),
):
    """
    Detect Steam games and find large unplayed/unused games.

    Addresses user's original request for Steam game detection and storage optimization.

    Args:
        min_size_gb: Minimum game size in GB (default 10GB)
        min_age_days: Minimum days since last update (default 180 days = 6 months)
        include_all: Include all games regardless of size/age (default False)

    Returns:
        SteamGamesListResponse with list of games and totals

    Example:
        ```bash
        # Find large unplayed games (>10GB, not updated in 6 months)
        curl http://localhost:8000/storage/steam/games

        # Find any games >50GB not updated in a year
        curl "http://localhost:8000/storage/steam/games?min_size_gb=50&min_age_days=365"

        # List all installed games
        curl "http://localhost:8000/storage/steam/games?include_all=true"
        ```
    """
    from autopack.storage_optimizer.steam_detector import SteamGameDetector

    detector = SteamGameDetector()

    if not detector.is_available():
        return schemas.SteamGamesListResponse(
            total_games=0,
            total_size_bytes=0,
            total_size_gb=0.0,
            games=[],
            steam_available=False,
            steam_path=None,
        )

    # Get games
    if include_all:
        games = detector.detect_installed_games()
    else:
        games = detector.find_unplayed_games(min_size_gb=min_size_gb, min_age_days=min_age_days)

    # Convert to response format
    game_responses = []
    total_size = 0
    for game in games:
        total_size += game.size_bytes
        game_responses.append(
            schemas.SteamGameResponse(
                app_id=game.app_id,
                name=game.name,
                install_path=str(game.install_path),
                size_bytes=game.size_bytes,
                size_gb=round(game.size_bytes / (1024**3), 2),
                last_updated=game.last_updated.isoformat() if game.last_updated else None,
                age_days=game.age_days,
            )
        )

    return schemas.SteamGamesListResponse(
        total_games=len(game_responses),
        total_size_bytes=total_size,
        total_size_gb=round(total_size / (1024**3), 2),
        games=game_responses,
        steam_available=True,
        steam_path=str(detector.steam_path) if detector.steam_path else None,
    )


@router.post(
    "/patterns/analyze",
    response_model=List[schemas.PatternResponse],
    dependencies=[Depends(verify_api_key)],
)
def analyze_approval_patterns(
    category: Optional[str] = None, max_patterns: int = 10, db: Session = Depends(get_db)
):
    """
    Analyze approval history to detect patterns for learned rules.

    Args:
        category: Filter by category (optional)
        max_patterns: Maximum patterns to return (default 10)

    Returns:
        List of detected patterns sorted by confidence
    """
    from autopack.storage_optimizer import load_policy
    from autopack.storage_optimizer.approval_pattern_analyzer import (
        ApprovalPatternAnalyzer,
    )

    policy = load_policy()
    analyzer = ApprovalPatternAnalyzer(db, policy)

    patterns = analyzer.analyze_approval_patterns(category=category, max_patterns=max_patterns)

    return [
        schemas.PatternResponse(
            pattern_type=p.pattern_type,
            pattern_value=p.pattern_value,
            category=p.category,
            approvals=p.approvals,
            rejections=p.rejections,
            confidence=p.confidence,
            sample_paths=p.sample_paths,
            description=p.description,
        )
        for p in patterns
    ]


@router.get("/learned-rules", response_model=List[schemas.LearnedRuleResponse])
def get_learned_rules(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """
    Get learned policy rules.

    Args:
        status: Filter by status (pending, approved, rejected, applied)

    Returns:
        List of learned rules
    """
    from autopack.models import LearnedRule

    query = db.query(LearnedRule)

    if status:
        query = query.filter(LearnedRule.status == status)

    rules = query.order_by(LearnedRule.confidence_score.desc(), LearnedRule.created_at.desc()).all()

    return [
        schemas.LearnedRuleResponse(
            id=r.id,
            created_at=r.created_at.isoformat(),
            pattern_type=r.pattern_type,
            pattern_value=r.pattern_value,
            suggested_category=r.suggested_category,
            confidence_score=float(r.confidence_score),
            based_on_approvals=r.based_on_approvals,
            based_on_rejections=r.based_on_rejections,
            sample_paths=r.sample_paths,
            status=r.status,
            reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
            description=r.description,
            notes=r.notes,
        )
        for r in rules
    ]


@router.post(
    "/learned-rules/{rule_id}/approve",
    response_model=schemas.LearnedRuleResponse,
    dependencies=[Depends(verify_api_key)],
)
def approve_learned_rule(rule_id: int, approved_by: str, db: Session = Depends(get_db)):
    """Approve a learned rule for application to policy."""
    from autopack.storage_optimizer import load_policy
    from autopack.storage_optimizer.approval_pattern_analyzer import (
        ApprovalPatternAnalyzer,
    )

    policy = load_policy()
    analyzer = ApprovalPatternAnalyzer(db, policy)

    rule = analyzer.approve_rule(rule_id, approved_by)

    return schemas.LearnedRuleResponse(
        id=rule.id,
        created_at=rule.created_at.isoformat(),
        pattern_type=rule.pattern_type,
        pattern_value=rule.pattern_value,
        suggested_category=rule.suggested_category,
        confidence_score=float(rule.confidence_score),
        based_on_approvals=rule.based_on_approvals,
        based_on_rejections=rule.based_on_rejections,
        sample_paths=rule.sample_paths,
        status=rule.status,
        reviewed_by=rule.reviewed_by,
        reviewed_at=rule.reviewed_at.isoformat() if rule.reviewed_at else None,
        description=rule.description,
        notes=rule.notes,
    )


@router.get("/recommendations", response_model=schemas.RecommendationsListResponse)
def get_storage_recommendations(
    max_recommendations: int = 10,
    lookback_days: int = 90,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """
    Get strategic storage optimization recommendations based on scan history.

    Args:
        max_recommendations: Maximum recommendations to return (default 10)
        lookback_days: Days of history to analyze (default 90)

    Returns:
        List of recommendations with scan statistics
    """
    from autopack.storage_optimizer import load_policy
    from autopack.storage_optimizer.recommendation_engine import RecommendationEngine

    policy = load_policy()
    engine = RecommendationEngine(db, policy)

    recommendations = engine.generate_recommendations(
        max_recommendations=max_recommendations, lookback_days=lookback_days
    )

    scan_stats = engine.get_scan_statistics(lookback_days=lookback_days)

    return schemas.RecommendationsListResponse(
        recommendations=[
            schemas.RecommendationResponse(
                type=r.type,
                priority=r.priority,
                title=r.title,
                description=r.description,
                evidence=r.evidence,
                action=r.action,
                potential_savings_bytes=r.potential_savings_bytes,
                potential_savings_gb=(
                    round(r.potential_savings_bytes / (1024**3), 2)
                    if r.potential_savings_bytes
                    else None
                ),
            )
            for r in recommendations
        ],
        scan_statistics=scan_stats,
    )
