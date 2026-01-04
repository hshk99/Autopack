"""
Approval Pattern Analyzer (BUILD-151 Phase 4)

Learns policy rules from user approval/rejection patterns to reduce manual approval burden.

The analyzer identifies patterns in approval history and suggests new policy rules:
- Path patterns (e.g., "always approve node_modules in temp directories")
- File type patterns (e.g., "always approve .log files older than 90 days")
- Size thresholds (e.g., "approve .cache files > 1GB")
- Age thresholds (e.g., "approve diagnostics older than 6 months")

Requires approval history data to function effectively (chicken-egg problem solved
by collecting initial approvals, then learning from them).
"""

import re
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func

from autopack.models import CleanupCandidateDB, LearnedRule
from autopack.storage_optimizer.policy import StoragePolicy


@dataclass
class Pattern:
    """Detected pattern from approval history."""
    pattern_type: str  # 'path_pattern', 'file_type', 'age_threshold', 'size_threshold'
    pattern_value: str
    category: str
    approvals: int
    rejections: int
    confidence: float
    sample_paths: List[str]
    description: str


class ApprovalPatternAnalyzer:
    """
    Analyzes approval history to learn policy rules.

    Workflow:
        1. User approves/rejects cleanup candidates over time
        2. Analyzer detects patterns in approved vs rejected items
        3. High-confidence patterns suggested as learned rules
        4. User reviews and approves learned rules
        5. Approved rules applied to policy (reducing future manual approvals)
    """

    def __init__(
        self,
        db: Session,
        policy: StoragePolicy,
        min_samples: int = 5,
        min_confidence: float = 0.75
    ):
        """
        Initialize analyzer.

        Args:
            db: Database session
            policy: Current storage policy
            min_samples: Minimum approval samples to consider pattern (default 5)
            min_confidence: Minimum confidence to suggest rule (default 0.75)
        """
        self.db = db
        self.policy = policy
        self.min_samples = min_samples
        self.min_confidence = min_confidence

    def analyze_approval_patterns(
        self,
        category: Optional[str] = None,
        max_patterns: int = 10
    ) -> List[Pattern]:
        """
        Analyze approval history and detect patterns.

        Args:
            category: Filter by category (e.g., 'dev_caches'), None for all
            max_patterns: Maximum patterns to return

        Returns:
            List of detected patterns sorted by confidence descending
        """
        patterns = []

        # Detect path patterns
        patterns.extend(self._detect_path_patterns(category))

        # Detect file type patterns
        patterns.extend(self._detect_file_type_patterns(category))

        # Detect age threshold patterns
        patterns.extend(self._detect_age_threshold_patterns(category))

        # Detect size threshold patterns
        patterns.extend(self._detect_size_threshold_patterns(category))

        # Sort by confidence descending
        patterns.sort(key=lambda p: p.confidence, reverse=True)

        return patterns[:max_patterns]

    def _detect_path_patterns(self, category: Optional[str]) -> List[Pattern]:
        """Detect common path patterns in approved items."""
        patterns = []

        # Get approved candidates
        query = self.db.query(CleanupCandidateDB).filter(
            CleanupCandidateDB.approval_status == 'approved'
        )
        if category:
            query = query.filter(CleanupCandidateDB.category == category)

        approved = query.all()

        if len(approved) < self.min_samples:
            return patterns

        # Group by common path prefixes
        path_groups = defaultdict(list)
        for candidate in approved:
            path = Path(candidate.path)

            # Extract common patterns
            # Pattern 1: parent directory name
            if len(path.parts) >= 2:
                parent_pattern = path.parts[-2]
                path_groups[f"parent:{parent_pattern}"].append(candidate)

            # Pattern 2: grandparent directory
            if len(path.parts) >= 3:
                grandparent_pattern = f"{path.parts[-3]}/{path.parts[-2]}"
                path_groups[f"grandparent:{grandparent_pattern}"].append(candidate)

            # Pattern 3: directory name contains keyword
            for part in path.parts:
                for keyword in ['node_modules', 'cache', 'temp', 'tmp', 'build', 'dist']:
                    if keyword in part.lower():
                        path_groups[f"contains:{keyword}"].append(candidate)

        # Analyze each group
        for pattern_key, candidates in path_groups.items():
            if len(candidates) < self.min_samples:
                continue

            # Check rejection rate for same pattern
            pattern_type, pattern_value = pattern_key.split(':', 1)
            rejections = self._count_rejections_matching_path_pattern(
                pattern_type, pattern_value, category
            )

            approvals = len(candidates)
            total = approvals + rejections

            if total == 0:
                continue

            confidence = approvals / total

            if confidence >= self.min_confidence:
                # Extract category from candidates (should be same)
                candidate_category = candidates[0].category

                patterns.append(Pattern(
                    pattern_type='path_pattern',
                    pattern_value=f"{pattern_type}:{pattern_value}",
                    category=candidate_category,
                    approvals=approvals,
                    rejections=rejections,
                    confidence=confidence,
                    sample_paths=[c.path for c in candidates[:5]],
                    description=f"Approve items in directories matching '{pattern_value}'"
                ))

        return patterns

    def _detect_file_type_patterns(self, category: Optional[str]) -> List[Pattern]:
        """Detect file extension patterns in approved items."""
        patterns = []

        # Get approved candidates grouped by extension
        query = self.db.query(
            func.lower(func.substr(CleanupCandidateDB.path, func.length(CleanupCandidateDB.path) - 4)),
            CleanupCandidateDB.category,
            func.count().label('count')
        ).filter(
            CleanupCandidateDB.approval_status == 'approved'
        ).group_by(
            func.lower(func.substr(CleanupCandidateDB.path, func.length(CleanupCandidateDB.path) - 4)),
            CleanupCandidateDB.category
        )

        if category:
            query = query.filter(CleanupCandidateDB.category == category)

        results = query.all()

        for ext_suffix, cat, count in results:
            if count < self.min_samples:
                continue

            # Extract extension
            ext_match = re.search(r'\.(\w+)$', ext_suffix)
            if not ext_match:
                continue

            extension = ext_match.group(1)

            # Count rejections for same extension
            rejections = self.db.query(func.count()).filter(
                CleanupCandidateDB.approval_status == 'rejected',
                CleanupCandidateDB.path.like(f'%.{extension}'),
                CleanupCandidateDB.category == cat
            ).scalar() or 0

            total = count + rejections

            if total == 0:
                continue

            confidence = count / total

            if confidence >= self.min_confidence:
                # Get sample paths
                samples = self.db.query(CleanupCandidateDB.path).filter(
                    CleanupCandidateDB.approval_status == 'approved',
                    CleanupCandidateDB.path.like(f'%.{extension}'),
                    CleanupCandidateDB.category == cat
                ).limit(5).all()

                patterns.append(Pattern(
                    pattern_type='file_type',
                    pattern_value=f'.{extension}',
                    category=cat,
                    approvals=count,
                    rejections=rejections,
                    confidence=confidence,
                    sample_paths=[s[0] for s in samples],
                    description=f"Approve .{extension} files in {cat} category"
                ))

        return patterns

    def _detect_age_threshold_patterns(self, category: Optional[str]) -> List[Pattern]:
        """Detect age threshold patterns (e.g., 'approve items older than X days')."""
        patterns = []

        # Get approved candidates with age data
        query = self.db.query(CleanupCandidateDB).filter(
            CleanupCandidateDB.approval_status == 'approved',
            CleanupCandidateDB.age_days.isnot(None)
        )
        if category:
            query = query.filter(CleanupCandidateDB.category == category)

        approved = query.all()

        if len(approved) < self.min_samples:
            return patterns

        # Group by category and analyze age distribution
        by_category = defaultdict(list)
        for candidate in approved:
            by_category[candidate.category].append(candidate.age_days)

        for cat, ages in by_category.items():
            if len(ages) < self.min_samples:
                continue

            # Find minimum age threshold where most approvals occur
            ages_sorted = sorted(ages)
            min_age = ages_sorted[int(len(ages_sorted) * 0.2)]  # 20th percentile

            # Round to nearest month (30 days)
            min_age_rounded = round(min_age / 30) * 30

            if min_age_rounded < 30:
                continue

            # Count rejections below this threshold
            rejections = self.db.query(func.count()).filter(
                CleanupCandidateDB.approval_status == 'rejected',
                CleanupCandidateDB.category == cat,
                CleanupCandidateDB.age_days < min_age_rounded
            ).scalar() or 0

            approvals = len([a for a in ages if a >= min_age_rounded])
            total = approvals + rejections

            if total == 0:
                continue

            confidence = approvals / total

            if confidence >= self.min_confidence:
                # Get sample paths
                samples = self.db.query(CleanupCandidateDB.path).filter(
                    CleanupCandidateDB.approval_status == 'approved',
                    CleanupCandidateDB.category == cat,
                    CleanupCandidateDB.age_days >= min_age_rounded
                ).limit(5).all()

                patterns.append(Pattern(
                    pattern_type='age_threshold',
                    pattern_value=str(min_age_rounded),
                    category=cat,
                    approvals=approvals,
                    rejections=rejections,
                    confidence=confidence,
                    sample_paths=[s[0] for s in samples],
                    description=f"Approve {cat} items older than {min_age_rounded} days ({min_age_rounded // 30} months)"
                ))

        return patterns

    def _detect_size_threshold_patterns(self, category: Optional[str]) -> List[Pattern]:
        """Detect size threshold patterns (e.g., 'approve items larger than X GB')."""
        patterns = []

        # Get approved candidates with size data
        query = self.db.query(CleanupCandidateDB).filter(
            CleanupCandidateDB.approval_status == 'approved',
            CleanupCandidateDB.size_bytes > 0
        )
        if category:
            query = query.filter(CleanupCandidateDB.category == category)

        approved = query.all()

        if len(approved) < self.min_samples:
            return patterns

        # Group by category and analyze size distribution
        by_category = defaultdict(list)
        for candidate in approved:
            by_category[candidate.category].append(candidate.size_bytes)

        for cat, sizes in by_category.items():
            if len(sizes) < self.min_samples:
                continue

            # Find minimum size threshold where most approvals occur
            sizes_sorted = sorted(sizes)
            min_size = sizes_sorted[int(len(sizes_sorted) * 0.2)]  # 20th percentile

            # Round to nearest 100MB
            min_size_mb = round(min_size / (1024**2) / 100) * 100

            if min_size_mb < 100:
                continue

            min_size_bytes = min_size_mb * 1024**2

            # Count rejections below this threshold
            rejections = self.db.query(func.count()).filter(
                CleanupCandidateDB.approval_status == 'rejected',
                CleanupCandidateDB.category == cat,
                CleanupCandidateDB.size_bytes < min_size_bytes
            ).scalar() or 0

            approvals = len([s for s in sizes if s >= min_size_bytes])
            total = approvals + rejections

            if total == 0:
                continue

            confidence = approvals / total

            if confidence >= self.min_confidence:
                # Get sample paths
                samples = self.db.query(CleanupCandidateDB.path).filter(
                    CleanupCandidateDB.approval_status == 'approved',
                    CleanupCandidateDB.category == cat,
                    CleanupCandidateDB.size_bytes >= min_size_bytes
                ).limit(5).all()

                size_display = f"{min_size_mb}MB" if min_size_mb < 1024 else f"{min_size_mb / 1024:.1f}GB"

                patterns.append(Pattern(
                    pattern_type='size_threshold',
                    pattern_value=str(min_size_bytes),
                    category=cat,
                    approvals=approvals,
                    rejections=rejections,
                    confidence=confidence,
                    sample_paths=[s[0] for s in samples],
                    description=f"Approve {cat} items larger than {size_display}"
                ))

        return patterns

    def _count_rejections_matching_path_pattern(
        self,
        pattern_type: str,
        pattern_value: str,
        category: Optional[str]
    ) -> int:
        """Count rejections matching a path pattern."""
        query = self.db.query(func.count()).filter(
            CleanupCandidateDB.approval_status == 'rejected'
        )

        if category:
            query = query.filter(CleanupCandidateDB.category == category)

        # Apply pattern matching
        if pattern_type == 'parent':
            # Path ends with /pattern_value/filename
            query = query.filter(CleanupCandidateDB.path.like(f'%/{pattern_value}/%'))
        elif pattern_type == 'grandparent':
            # Path contains grandparent/parent pattern
            query = query.filter(CleanupCandidateDB.path.like(f'%{pattern_value}%'))
        elif pattern_type == 'contains':
            # Path contains keyword
            query = query.filter(CleanupCandidateDB.path.like(f'%{pattern_value}%'))

        return query.scalar() or 0

    def create_learned_rule(
        self,
        pattern: Pattern,
        reviewed_by: str,
        notes: Optional[str] = None
    ) -> LearnedRule:
        """
        Create a learned rule from a detected pattern.

        Args:
            pattern: Detected pattern
            reviewed_by: User who reviewed the pattern
            notes: Optional notes about the rule

        Returns:
            Created LearnedRule database record
        """
        # Convert sample paths to JSON string for SQLite compatibility
        import json
        sample_paths_json = json.dumps(pattern.sample_paths)

        rule = LearnedRule(
            created_at=datetime.now(timezone.utc),
            pattern_type=pattern.pattern_type,
            pattern_value=pattern.pattern_value,
            suggested_category=pattern.category,
            confidence_score=round(pattern.confidence, 2),
            based_on_approvals=pattern.approvals,
            based_on_rejections=pattern.rejections,
            sample_paths=sample_paths_json,
            status='pending',
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(timezone.utc),
            description=pattern.description,
            notes=notes
        )

        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)

        return rule

    def get_pending_rules(self) -> List[LearnedRule]:
        """Get all pending learned rules awaiting review."""
        return self.db.query(LearnedRule).filter(
            LearnedRule.status == 'pending'
        ).order_by(
            LearnedRule.confidence_score.desc(),
            LearnedRule.created_at.desc()
        ).all()

    def approve_rule(self, rule_id: int, approved_by: str) -> LearnedRule:
        """Approve a learned rule for application to policy."""
        rule = self.db.query(LearnedRule).filter(LearnedRule.id == rule_id).first()

        if not rule:
            raise ValueError(f"Learned rule {rule_id} not found")

        rule.status = 'approved'
        rule.reviewed_by = approved_by
        rule.reviewed_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(rule)

        return rule

    def reject_rule(self, rule_id: int, rejected_by: str, reason: str) -> LearnedRule:
        """Reject a learned rule."""
        rule = self.db.query(LearnedRule).filter(LearnedRule.id == rule_id).first()

        if not rule:
            raise ValueError(f"Learned rule {rule_id} not found")

        rule.status = 'rejected'
        rule.reviewed_by = rejected_by
        rule.reviewed_at = datetime.now(timezone.utc)
        rule.notes = reason

        self.db.commit()
        self.db.refresh(rule)

        return rule
