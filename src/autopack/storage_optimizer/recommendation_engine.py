"""
Recommendation Engine (BUILD-151 Phase 4)

Strategic cleanup recommendations based on scan history trends.

Analyzes historical scan data to provide proactive guidance:
- Growth rate alerts ("Dev caches growing 10GB/month")
- Recurring waste patterns ("You delete the same node_modules every 2 weeks")
- Optimization opportunities ("Consider increasing retention window for logs")
- Cost-benefit analysis ("Top 5 directories consuming 80% of disk space")

Requires scan history to function (at least 2-3 scans for trend analysis).
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from autopack.models import StorageScan, CleanupCandidateDB
from autopack.storage_optimizer.policy import StoragePolicy


@dataclass
class Recommendation:
    """Strategic recommendation for storage optimization."""
    type: str  # 'growth_alert', 'recurring_waste', 'policy_adjustment', 'top_consumers'
    priority: str  # 'high', 'medium', 'low'
    title: str
    description: str
    evidence: Dict  # Supporting data (growth rate, size trends, etc.)
    action: str  # Suggested action
    potential_savings_bytes: Optional[int] = None


class RecommendationEngine:
    """
    Generates strategic recommendations from scan history.

    Workflow:
        1. Analyze multiple scans over time
        2. Detect trends (growth, recurring patterns, etc.)
        3. Generate actionable recommendations
        4. Prioritize by impact (potential savings)
    """

    def __init__(
        self,
        db: Session,
        policy: StoragePolicy,
        min_scans_for_trends: int = 3
    ):
        """
        Initialize recommendation engine.

        Args:
            db: Database session
            policy: Current storage policy
            min_scans_for_trends: Minimum scans needed for trend analysis (default 3)
        """
        self.db = db
        self.policy = policy
        self.min_scans_for_trends = min_scans_for_trends

    def generate_recommendations(
        self,
        max_recommendations: int = 10,
        lookback_days: int = 90
    ) -> List[Recommendation]:
        """
        Generate all recommendations.

        Args:
            max_recommendations: Maximum recommendations to return
            lookback_days: Days of history to analyze (default 90)

        Returns:
            List of recommendations sorted by priority (high → low)
        """
        recommendations = []

        # Get scan history
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        scans = self.db.query(StorageScan).filter(
            StorageScan.timestamp >= cutoff_date
        ).order_by(StorageScan.timestamp.asc()).all()

        if len(scans) < 2:
            return [Recommendation(
                type='insufficient_data',
                priority='low',
                title='Insufficient Scan History',
                description=f'Need at least 2 scans to generate recommendations. Found {len(scans)}.',
                evidence={'scan_count': len(scans)},
                action='Run more scans over time to enable trend analysis.'
            )]

        # Generate different types of recommendations
        recommendations.extend(self._detect_growth_alerts(scans))
        recommendations.extend(self._detect_recurring_waste(scans))
        recommendations.extend(self._suggest_policy_adjustments(scans))
        recommendations.extend(self._identify_top_consumers(scans))

        # Sort by priority (high → medium → low) and potential savings
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recommendations.sort(key=lambda r: (
            priority_order[r.priority],
            -(r.potential_savings_bytes or 0)
        ))

        return recommendations[:max_recommendations]

    def _detect_growth_alerts(self, scans: List[StorageScan]) -> List[Recommendation]:
        """Detect categories growing rapidly over time."""
        recommendations = []

        if len(scans) < self.min_scans_for_trends:
            return recommendations

        # Analyze growth by category
        category_trends = self._analyze_category_growth(scans)

        for category, trend in category_trends.items():
            if trend['growth_rate_bytes_per_day'] > 100 * 1024**2:  # >100MB/day
                growth_rate_gb = trend['growth_rate_bytes_per_day'] / (1024**3)
                monthly_growth_gb = growth_rate_gb * 30

                priority = 'high' if monthly_growth_gb > 10 else 'medium'

                recommendations.append(Recommendation(
                    type='growth_alert',
                    priority=priority,
                    title=f"Rapid Growth in {category}",
                    description=f"{category} category growing at {monthly_growth_gb:.1f} GB/month",
                    evidence={
                        'category': category,
                        'growth_rate_gb_per_month': round(monthly_growth_gb, 2),
                        'current_size_gb': round(trend['latest_size_bytes'] / (1024**3), 2),
                        'size_30_days_ago_gb': round(trend['earliest_size_bytes'] / (1024**3), 2)
                    },
                    action=f"Review and clean up {category} more frequently, or tighten retention policy",
                    potential_savings_bytes=int(monthly_growth_gb * 0.7 * 1024**3)  # 70% of monthly growth
                ))

        return recommendations

    def _detect_recurring_waste(self, scans: List[StorageScan]) -> List[Recommendation]:
        """Detect items that are repeatedly deleted (waste of manual effort)."""
        recommendations = []

        # Find paths that appear in multiple scans as cleanup candidates
        path_frequency = defaultdict(list)

        for scan in scans:
            candidates = self.db.query(CleanupCandidateDB).filter(
                CleanupCandidateDB.scan_id == scan.id,
                CleanupCandidateDB.approval_status.in_(['approved', 'pending'])
            ).all()

            for candidate in candidates:
                # Normalize path (remove instance-specific parts)
                normalized_path = self._normalize_path_for_pattern(candidate.path)
                path_frequency[normalized_path].append({
                    'scan_id': scan.id,
                    'timestamp': scan.timestamp,
                    'size_bytes': candidate.size_bytes,
                    'category': candidate.category
                })

        # Find paths appearing in 3+ scans
        for path_pattern, occurrences in path_frequency.items():
            if len(occurrences) >= min(3, len(scans) // 2):
                # Calculate average size
                avg_size = sum(o['size_bytes'] for o in occurrences) / len(occurrences)
                category = occurrences[0]['category']

                # Calculate time between occurrences
                timestamps = sorted([o['timestamp'] for o in occurrences])
                intervals = [
                    (timestamps[i + 1] - timestamps[i]).days
                    for i in range(len(timestamps) - 1)
                ]
                avg_interval_days = sum(intervals) / len(intervals) if intervals else 0

                recommendations.append(Recommendation(
                    type='recurring_waste',
                    priority='medium',
                    title=f"Recurring Waste Pattern: {path_pattern}",
                    description=f"This path appears in {len(occurrences)} scans (avg every {avg_interval_days:.0f} days)",
                    evidence={
                        'path_pattern': path_pattern,
                        'occurrence_count': len(occurrences),
                        'avg_interval_days': round(avg_interval_days, 1),
                        'avg_size_gb': round(avg_size / (1024**3), 2),
                        'category': category
                    },
                    action=f"Consider automated cleanup or tighter retention policy for {category}",
                    potential_savings_bytes=int(avg_size * 12)  # Annual savings if cleaned monthly
                ))

        return recommendations

    def _suggest_policy_adjustments(self, scans: List[StorageScan]) -> List[Recommendation]:
        """Suggest policy adjustments based on approval patterns."""
        recommendations = []

        # Analyze rejection patterns (user consistently rejects certain categories)
        rejection_stats = self._analyze_rejection_patterns(scans)

        for category, stats in rejection_stats.items():
            if stats['rejection_rate'] > 0.8 and stats['total_count'] >= 5:
                # High rejection rate → suggest stricter policy
                recommendations.append(Recommendation(
                    type='policy_adjustment',
                    priority='low',
                    title=f"Consider Stricter Policy for {category}",
                    description=f"You reject {stats['rejection_rate'] * 100:.0f}% of {category} candidates",
                    evidence={
                        'category': category,
                        'rejection_rate': round(stats['rejection_rate'], 2),
                        'rejected_count': stats['rejected_count'],
                        'total_count': stats['total_count']
                    },
                    action=f"Increase retention window or size threshold for {category} to reduce false positives"
                ))

        return recommendations

    def _identify_top_consumers(self, scans: List[StorageScan]) -> List[Recommendation]:
        """Identify top storage consumers (Pareto principle: 80/20 rule)."""
        recommendations = []

        # Get latest scan
        latest_scan = scans[-1]

        # Get all candidates from latest scan grouped by category
        category_sizes = self.db.query(
            CleanupCandidateDB.category,
            func.sum(CleanupCandidateDB.size_bytes).label('total_size')
        ).filter(
            CleanupCandidateDB.scan_id == latest_scan.id
        ).group_by(
            CleanupCandidateDB.category
        ).order_by(
            func.sum(CleanupCandidateDB.size_bytes).desc()
        ).all()

        if not category_sizes:
            return recommendations

        total_size = sum(size for _, size in category_sizes)
        cumulative_size = 0
        top_categories = []

        # Find categories that make up 80% of storage
        for category, size in category_sizes:
            cumulative_size += size
            top_categories.append((category, size))

            if cumulative_size >= total_size * 0.8:
                break

        if len(top_categories) <= 3:
            categories_str = ', '.join([cat for cat, _ in top_categories])
            combined_size_gb = cumulative_size / (1024**3)

            recommendations.append(Recommendation(
                type='top_consumers',
                priority='high',
                title=f"Top {len(top_categories)} Categories Consume 80% of Storage",
                description=f"{categories_str} account for {combined_size_gb:.1f} GB ({cumulative_size / total_size * 100:.0f}%)",
                evidence={
                    'top_categories': [
                        {
                            'category': cat,
                            'size_gb': round(size / (1024**3), 2),
                            'percentage': round(size / total_size * 100, 1)
                        }
                        for cat, size in top_categories
                    ],
                    'total_size_gb': round(total_size / (1024**3), 2)
                },
                action=f"Focus cleanup efforts on {categories_str} for maximum impact",
                potential_savings_bytes=int(cumulative_size * 0.6)  # 60% of top consumers
            ))

        return recommendations

    def _analyze_category_growth(
        self,
        scans: List[StorageScan]
    ) -> Dict[str, Dict]:
        """Analyze growth rate by category."""
        category_trends = {}

        # Group candidates by category across scans
        for scan in scans:
            category_sizes = self.db.query(
                CleanupCandidateDB.category,
                func.sum(CleanupCandidateDB.size_bytes).label('total_size')
            ).filter(
                CleanupCandidateDB.scan_id == scan.id
            ).group_by(
                CleanupCandidateDB.category
            ).all()

            for category, size in category_sizes:
                if category not in category_trends:
                    category_trends[category] = {
                        'data_points': [],
                        'earliest_size_bytes': 0,
                        'latest_size_bytes': 0,
                        'growth_rate_bytes_per_day': 0
                    }

                category_trends[category]['data_points'].append({
                    'timestamp': scan.timestamp,
                    'size_bytes': size
                })

        # Calculate growth rates
        for category, trend in category_trends.items():
            if len(trend['data_points']) < 2:
                continue

            # Sort by timestamp
            trend['data_points'].sort(key=lambda dp: dp['timestamp'])

            earliest = trend['data_points'][0]
            latest = trend['data_points'][-1]

            trend['earliest_size_bytes'] = earliest['size_bytes']
            trend['latest_size_bytes'] = latest['size_bytes']

            # Calculate growth rate (bytes per day)
            time_delta = (latest['timestamp'] - earliest['timestamp']).total_seconds() / 86400  # days

            if time_delta > 0:
                growth = latest['size_bytes'] - earliest['size_bytes']
                trend['growth_rate_bytes_per_day'] = growth / time_delta

        return category_trends

    def _analyze_rejection_patterns(
        self,
        scans: List[StorageScan]
    ) -> Dict[str, Dict]:
        """Analyze user rejection patterns by category."""
        rejection_stats = defaultdict(lambda: {
            'rejected_count': 0,
            'approved_count': 0,
            'total_count': 0,
            'rejection_rate': 0.0
        })

        for scan in scans:
            candidates = self.db.query(CleanupCandidateDB).filter(
                CleanupCandidateDB.scan_id == scan.id,
                CleanupCandidateDB.approval_status.in_(['approved', 'rejected'])
            ).all()

            for candidate in candidates:
                stats = rejection_stats[candidate.category]
                stats['total_count'] += 1

                if candidate.approval_status == 'rejected':
                    stats['rejected_count'] += 1
                else:
                    stats['approved_count'] += 1

        # Calculate rejection rates
        for category, stats in rejection_stats.items():
            if stats['total_count'] > 0:
                stats['rejection_rate'] = stats['rejected_count'] / stats['total_count']

        return dict(rejection_stats)

    def _normalize_path_for_pattern(self, path: str) -> str:
        """
        Normalize path to detect recurring patterns.

        Examples:
            /temp/run-123/logs → /temp/run-*/logs
            c:/cache/2024-01-15/ → c:/cache/*/
        """
        import re

        # Replace timestamps (YYYY-MM-DD, YYYYMMDD)
        path = re.sub(r'\d{4}-\d{2}-\d{2}', '*', path)
        path = re.sub(r'\d{8}', '*', path)

        # Replace run IDs (run-123, run_abc)
        path = re.sub(r'run[-_]\w+', 'run-*', path)

        # Replace UUIDs
        path = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '*',
            path,
            flags=re.IGNORECASE
        )

        # Replace large numbers (file sizes, timestamps)
        path = re.sub(r'\d{6,}', '*', path)

        return path

    def get_scan_statistics(self, lookback_days: int = 90) -> Dict:
        """
        Get summary statistics for scan history.

        Args:
            lookback_days: Days of history to analyze

        Returns:
            Dict with scan statistics
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        scans = self.db.query(StorageScan).filter(
            StorageScan.timestamp >= cutoff_date
        ).order_by(StorageScan.timestamp.asc()).all()

        if not scans:
            return {
                'scan_count': 0,
                'date_range_days': 0,
                'total_candidates': 0,
                'total_potential_savings_gb': 0.0
            }

        total_candidates = sum(s.cleanup_candidates_count for s in scans)
        total_savings = sum(s.potential_savings_bytes for s in scans)

        date_range = (scans[-1].timestamp - scans[0].timestamp).days

        return {
            'scan_count': len(scans),
            'date_range_days': date_range,
            'earliest_scan': scans[0].timestamp.isoformat(),
            'latest_scan': scans[-1].timestamp.isoformat(),
            'total_candidates': total_candidates,
            'total_potential_savings_gb': round(total_savings / (1024**3), 2),
            'avg_candidates_per_scan': round(total_candidates / len(scans), 1),
            'avg_savings_per_scan_gb': round((total_savings / len(scans)) / (1024**3), 2)
        }
