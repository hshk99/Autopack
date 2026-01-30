"""
Research State Tracker for incremental research and gap detection.

Enables:
- Tracking research progress across sessions
- Identifying gaps in research coverage
- Avoiding re-researching discovered information
- Measuring research completeness
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GapType(Enum):
    """Types of research gaps."""

    COVERAGE = "coverage"
    ENTITY = "entity"
    DEPTH = "depth"
    RECENCY = "recency"
    VALIDATION = "validation"


class GapPriority(Enum):
    """Priority levels for gaps."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ResearchDepth(Enum):
    """Depth levels for research topics."""

    SHALLOW = "shallow"
    MEDIUM = "medium"
    DEEP = "deep"


@dataclass
class CompletedQuery:
    """Record of a completed research query."""

    query: str
    agent: str
    timestamp: datetime
    sources_found: int
    quality_score: float
    key_findings_hash: str
    gap_id: Optional[str] = None


@dataclass
class DiscoveredSource:
    """A discovered research source."""

    url: str
    source_type: str
    accessed_at: datetime
    content_hash: str
    relevance_score: float
    used_in: List[str] = field(default_factory=list)


@dataclass
class ResearchGap:
    """An identified gap in research."""

    gap_id: str
    gap_type: GapType
    category: str
    description: str
    priority: GapPriority
    suggested_queries: List[str] = field(default_factory=list)
    identified_at: datetime = field(default_factory=datetime.now)
    addressed_at: Optional[datetime] = None
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "gap_type": self.gap_type.value,
            "category": self.category,
            "description": self.description,
            "priority": self.priority.value,
            "suggested_queries": self.suggested_queries,
            "identified_at": self.identified_at.isoformat(),
            "addressed_at": self.addressed_at.isoformat() if self.addressed_at else None,
            "status": self.status,
        }


@dataclass
class CoverageMetrics:
    """Research coverage metrics."""

    overall_percentage: float = 0.0
    by_category: Dict[str, float] = field(default_factory=dict)

    DEFAULT_CATEGORIES = [
        "market_research",
        "competitive_analysis",
        "technical_feasibility",
        "legal_policy",
        "social_sentiment",
        "tool_availability",
    ]

    def __post_init__(self):
        # Initialize default categories if empty
        if not self.by_category:
            self.by_category = {cat: 0.0 for cat in self.DEFAULT_CATEGORIES}

    def recalculate_overall(self):
        """Recalculate overall coverage from category coverages."""
        if self.by_category:
            self.overall_percentage = sum(self.by_category.values()) / len(self.by_category)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_percentage": round(self.overall_percentage, 1),
            "by_category": {k: round(v, 1) for k, v in self.by_category.items()},
        }


@dataclass
class ResearchState:
    """Main research state container."""

    project_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    version: int = 1

    coverage: CoverageMetrics = field(default_factory=CoverageMetrics)
    completed_queries: List[CompletedQuery] = field(default_factory=list)
    discovered_sources: List[DiscoveredSource] = field(default_factory=list)
    identified_gaps: List[ResearchGap] = field(default_factory=list)

    entities_researched: Dict[str, List[str]] = field(default_factory=dict)
    research_depth: Dict[str, ResearchDepth] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_state": {
                "project_id": self.project_id,
                "created_at": self.created_at.isoformat(),
                "last_updated": self.last_updated.isoformat(),
                "version": self.version,
                "coverage": self.coverage.to_dict(),
                "completed_queries": [
                    {
                        "query": q.query,
                        "agent": q.agent,
                        "timestamp": q.timestamp.isoformat(),
                        "sources_found": q.sources_found,
                        "quality_score": q.quality_score,
                        "key_findings_hash": q.key_findings_hash,
                        "gap_id": q.gap_id,
                    }
                    for q in self.completed_queries
                ],
                "discovered_sources": [
                    {
                        "url": s.url,
                        "type": s.source_type,
                        "accessed_at": s.accessed_at.isoformat(),
                        "content_hash": s.content_hash,
                        "relevance_score": s.relevance_score,
                        "used_in": s.used_in,
                    }
                    for s in self.discovered_sources
                ],
                "identified_gaps": [g.to_dict() for g in self.identified_gaps],
                "entities_researched": self.entities_researched,
                "research_depth": {k: v.value for k, v in self.research_depth.items()},
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchState":
        """Load state from dictionary."""
        state_data = data.get("research_state", data)

        state = cls(
            project_id=state_data["project_id"],
            created_at=datetime.fromisoformat(state_data["created_at"]),
            last_updated=datetime.fromisoformat(state_data["last_updated"]),
            version=state_data.get("version", 1),
        )

        # Load coverage
        cov_data = state_data.get("coverage", {})
        state.coverage = CoverageMetrics(
            overall_percentage=cov_data.get("overall_percentage", 0),
            by_category=cov_data.get("by_category", {}),
        )

        # Load completed queries
        for q in state_data.get("completed_queries", []):
            state.completed_queries.append(
                CompletedQuery(
                    query=q["query"],
                    agent=q["agent"],
                    timestamp=datetime.fromisoformat(q["timestamp"]),
                    sources_found=q["sources_found"],
                    quality_score=q["quality_score"],
                    key_findings_hash=q["key_findings_hash"],
                    gap_id=q.get("gap_id"),
                )
            )

        # Load discovered sources
        for s in state_data.get("discovered_sources", []):
            state.discovered_sources.append(
                DiscoveredSource(
                    url=s["url"],
                    source_type=s["type"],
                    accessed_at=datetime.fromisoformat(s["accessed_at"]),
                    content_hash=s["content_hash"],
                    relevance_score=s["relevance_score"],
                    used_in=s.get("used_in", []),
                )
            )

        # Load identified gaps
        for g in state_data.get("identified_gaps", []):
            state.identified_gaps.append(
                ResearchGap(
                    gap_id=g["gap_id"],
                    gap_type=GapType(g["gap_type"]),
                    category=g["category"],
                    description=g["description"],
                    priority=GapPriority(g["priority"]),
                    suggested_queries=g.get("suggested_queries", []),
                    identified_at=datetime.fromisoformat(g["identified_at"]),
                    addressed_at=(
                        datetime.fromisoformat(g["addressed_at"]) if g.get("addressed_at") else None
                    ),
                    status=g.get("status", "pending"),
                )
            )

        # Load entities researched
        state.entities_researched = state_data.get("entities_researched", {})

        # Load research depth
        depth_data = state_data.get("research_depth", {})
        state.research_depth = {k: ResearchDepth(v) for k, v in depth_data.items()}

        return state


@dataclass
class ResearchRequirements:
    """Requirements for research completeness."""

    min_coverage: Dict[str, float] = field(default_factory=dict)
    min_sources: int = 2
    max_age_days: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        # Set defaults if not provided
        if not self.min_coverage:
            self.min_coverage = {
                "market_research": 70,
                "competitive_analysis": 70,
                "technical_feasibility": 60,
                "legal_policy": 80,
                "social_sentiment": 50,
                "tool_availability": 60,
            }
        if not self.max_age_days:
            self.max_age_days = {
                "market-research-agent": 30,
                "competitive-analysis-agent": 14,
                "technical-feasibility-agent": 60,
                "legal-policy-agent": 90,
                "social-sentiment-agent": 7,
                "tool-availability-agent": 30,
            }


@dataclass
class ResearchCheckpoint:
    """Checkpoint for resumable research sessions."""

    checkpoint_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    phase: str = ""  # current research phase
    completed_steps: List[str] = field(default_factory=list)
    partial_results: Dict[str, Any] = field(default_factory=dict)
    failed_tasks: Dict[str, str] = field(default_factory=dict)  # task_id: error
    state_snapshot: Optional[Dict[str, Any]] = None
    is_recoverable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "phase": self.phase,
            "completed_steps": self.completed_steps,
            "partial_results": self.partial_results,
            "failed_tasks": self.failed_tasks,
            "is_recoverable": self.is_recoverable,
            "state_snapshot": self.state_snapshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResearchCheckpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_updated=datetime.fromisoformat(data["last_updated"]),
            phase=data.get("phase", ""),
            completed_steps=data.get("completed_steps", []),
            partial_results=data.get("partial_results", {}),
            failed_tasks=data.get("failed_tasks", {}),
            is_recoverable=data.get("is_recoverable", True),
            state_snapshot=data.get("state_snapshot"),
        )


class ResearchStateTracker:
    """
    Tracks research state and identifies gaps for incremental research.

    Handles edge cases including:
    - Interrupted research with checkpoint recovery
    - Partial results processing
    - Async task failures with fallback strategies
    - State consistency validation
    """

    def __init__(
        self,
        project_root: Path,
        requirements: Optional[ResearchRequirements] = None,
    ):
        self.project_root = Path(project_root)
        self.requirements = requirements or ResearchRequirements()
        self.state_dir = self.project_root / ".autopack"
        self.state_file = self.state_dir / "research_state.json"
        self.history_dir = self.state_dir / "state_history"
        self.session_dir = self.state_dir / "session_logs"
        self.checkpoint_dir = self.state_dir / "checkpoints"
        self.recovery_log_file = self.state_dir / "recovery_log.json"

        self._state: Optional[ResearchState] = None
        self._current_checkpoint: Optional[ResearchCheckpoint] = None
        self._validation_errors: List[str] = []

    def load_or_create_state(self, project_id: str) -> ResearchState:
        """Load existing state or create new one with validation and recovery."""
        self._ensure_directories()

        # Try to load state, with validation and recovery
        state_loaded = False
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                self._state = ResearchState.from_dict(data)
                state_loaded = True
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning(f"Failed to load state file: {e}. Attempting recovery.")
                self._state = None

        # If state loading failed, try to recover from checkpoint
        if not state_loaded:
            recovered = self._recover_from_checkpoint(project_id)
            if recovered:
                logger.info("Successfully recovered state from checkpoint")
            else:
                self._state = ResearchState(project_id=project_id)
                logger.info("Created new research state")

        # Validate loaded state
        validation_errors = self.validate_state_consistency()
        if validation_errors:
            logger.warning(f"State validation found {len(validation_errors)} issues")
            for error in validation_errors[:3]:  # Log first 3 errors
                logger.warning(f"  - {error}")

        return self._state

    def _ensure_directories(self):
        """Create necessary directories."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(exist_ok=True)
        self.session_dir.mkdir(exist_ok=True)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def save_state(self):
        """Save current state with version history."""
        if not self._state:
            return

        self._ensure_directories()

        # Save version history before updating
        if self.state_file.exists():
            history_file = self.history_dir / f"state_v{self._state.version}.json"
            with open(self.state_file, "r") as f:
                old_data = f.read()
            with open(history_file, "w") as f:
                f.write(old_data)

            # Keep only last 5 versions
            history_files = sorted(self.history_dir.glob("state_v*.json"))
            for old_file in history_files[:-5]:
                old_file.unlink()

        # Update version and timestamp
        self._state.version += 1
        self._state.last_updated = datetime.now()

        # Save new state
        with open(self.state_file, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def detect_gaps(self) -> List[ResearchGap]:
        """Detect all gaps in current research state."""
        if not self._state:
            raise ValueError("State not loaded. Call load_or_create_state first.")

        gaps = []
        gap_counter = len(self._state.identified_gaps) + 1

        # 1. Coverage gaps
        for category, coverage in self._state.coverage.by_category.items():
            min_required = self.requirements.min_coverage.get(category, 70)
            if coverage < min_required:
                gaps.append(
                    ResearchGap(
                        gap_id=f"gap-{gap_counter:03d}",
                        gap_type=GapType.COVERAGE,
                        category=category,
                        description=f"{category} coverage at {coverage:.0f}%, need {min_required:.0f}%",
                        priority=self._calculate_coverage_priority(coverage, min_required),
                        suggested_queries=self._suggest_queries_for_category(category),
                    )
                )
                gap_counter += 1

        # 2. Recency gaps
        now = datetime.now()
        for query in self._state.completed_queries:
            max_age = self.requirements.max_age_days.get(query.agent, 30)
            age_days = (now - query.timestamp).days
            if age_days > max_age:
                gaps.append(
                    ResearchGap(
                        gap_id=f"gap-{gap_counter:03d}",
                        gap_type=GapType.RECENCY,
                        category="recency",
                        description=f"Query '{query.query[:50]}...' is {age_days} days old (max: {max_age})",
                        priority=GapPriority.LOW,
                        suggested_queries=[query.query],  # Re-run same query
                    )
                )
                gap_counter += 1

        # 3. Depth gaps - topics needing deeper research
        critical_topics = ["api_integration", "pricing", "compliance", "security"]
        for topic in critical_topics:
            depth = self._state.research_depth.get(topic, ResearchDepth.SHALLOW)
            if depth == ResearchDepth.SHALLOW:
                gaps.append(
                    ResearchGap(
                        gap_id=f"gap-{gap_counter:03d}",
                        gap_type=GapType.DEPTH,
                        category="depth",
                        description=f"Topic '{topic}' needs deeper research (currently: {depth.value})",
                        priority=GapPriority.HIGH,
                        suggested_queries=self._suggest_deep_queries(topic),
                    )
                )
                gap_counter += 1

        return sorted(gaps, key=lambda g: self._priority_order(g.priority))

    def _calculate_coverage_priority(self, current: float, required: float) -> GapPriority:
        """Calculate priority based on coverage gap size."""
        gap = required - current
        if gap > 50:
            return GapPriority.CRITICAL
        elif gap > 30:
            return GapPriority.HIGH
        elif gap > 15:
            return GapPriority.MEDIUM
        return GapPriority.LOW

    def _priority_order(self, priority: GapPriority) -> int:
        """Convert priority to sort order (lower = higher priority)."""
        return {
            GapPriority.CRITICAL: 0,
            GapPriority.HIGH: 1,
            GapPriority.MEDIUM: 2,
            GapPriority.LOW: 3,
        }.get(priority, 4)

    def _suggest_queries_for_category(self, category: str) -> List[str]:
        """Suggest queries to improve category coverage."""
        suggestions = {
            "market_research": [
                "market size and growth projections",
                "target customer demographics",
                "market trends and opportunities",
            ],
            "competitive_analysis": [
                "top competitors analysis",
                "competitor pricing strategies",
                "competitive advantages gaps",
            ],
            "technical_feasibility": [
                "technology stack requirements",
                "integration complexity assessment",
                "performance benchmarks",
            ],
            "legal_policy": [
                "platform terms of service",
                "regulatory compliance requirements",
                "intellectual property considerations",
            ],
            "social_sentiment": [
                "customer reviews and feedback",
                "social media sentiment analysis",
                "community discussions",
            ],
            "tool_availability": [
                "available APIs and SDKs",
                "open source alternatives",
                "pricing tiers and limits",
            ],
        }
        return suggestions.get(category, ["general research for " + category])

    def _suggest_deep_queries(self, topic: str) -> List[str]:
        """Suggest queries for deep research on a topic."""
        suggestions = {
            "api_integration": [
                "API rate limits and quotas",
                "API authentication methods",
                "API error handling best practices",
            ],
            "pricing": [
                "detailed pricing breakdown",
                "volume discount structures",
                "hidden fees and costs",
            ],
            "compliance": [
                "data privacy requirements",
                "regional compliance variations",
                "audit and certification needs",
            ],
            "security": [
                "security best practices",
                "vulnerability assessments",
                "authentication security",
            ],
        }
        return suggestions.get(topic, [f"deep research: {topic}"])

    def should_skip_query(self, query: str) -> bool:
        """Check if query should be skipped (already completed or similar)."""
        if not self._state:
            return False

        # Exact match
        completed_queries = [q.query.lower() for q in self._state.completed_queries]
        if query.lower() in completed_queries:
            return True

        # Check for very similar queries (simple word overlap)
        query_words = set(query.lower().split())
        for completed in self._state.completed_queries:
            completed_words = set(completed.query.lower().split())
            overlap = len(query_words & completed_words)
            total = len(query_words | completed_words)
            if total > 0 and overlap / total > 0.8:
                # Check recency - allow re-query if old
                age_days = (datetime.now() - completed.timestamp).days
                if age_days < 7:
                    return True

        return False

    def is_new_source(self, url: str, content_hash: Optional[str] = None) -> bool:
        """Check if a source is new (not already discovered)."""
        if not self._state:
            return True

        # URL match
        existing_urls = [s.url for s in self._state.discovered_sources]
        if url in existing_urls:
            return False

        # Content hash match
        if content_hash:
            existing_hashes = [s.content_hash for s in self._state.discovered_sources]
            if content_hash in existing_hashes:
                return False

        return True

    def record_completed_query(
        self,
        query: str,
        agent: str,
        sources_found: int,
        quality_score: float,
        findings: Any,
        gap_id: Optional[str] = None,
    ):
        """Record a completed research query."""
        if not self._state:
            raise ValueError("State not loaded")

        # Hash findings for deduplication
        findings_str = json.dumps(findings, sort_keys=True, default=str)
        findings_hash = hashlib.md5(findings_str.encode()).hexdigest()[:12]

        self._state.completed_queries.append(
            CompletedQuery(
                query=query,
                agent=agent,
                timestamp=datetime.now(),
                sources_found=sources_found,
                quality_score=quality_score,
                key_findings_hash=findings_hash,
                gap_id=gap_id,
            )
        )

        # Mark gap as addressed if applicable
        if gap_id:
            self.mark_gap_addressed(gap_id)

        self.save_state()

    def record_discovered_source(
        self,
        url: str,
        source_type: str,
        content_hash: str,
        relevance_score: float,
        agent: str,
    ):
        """Record a discovered source."""
        if not self._state:
            raise ValueError("State not loaded")

        if not self.is_new_source(url, content_hash):
            # Update existing source's used_in list
            for source in self._state.discovered_sources:
                if source.url == url:
                    if agent not in source.used_in:
                        source.used_in.append(agent)
                    break
            return

        self._state.discovered_sources.append(
            DiscoveredSource(
                url=url,
                source_type=source_type,
                accessed_at=datetime.now(),
                content_hash=content_hash,
                relevance_score=relevance_score,
                used_in=[agent],
            )
        )

    def update_coverage(self, category: str, new_coverage: float):
        """Update coverage for a category."""
        if not self._state:
            raise ValueError("State not loaded")

        self._state.coverage.by_category[category] = min(100.0, new_coverage)
        self._state.coverage.recalculate_overall()

    def update_research_depth(self, topic: str, depth: ResearchDepth):
        """Update research depth for a topic."""
        if not self._state:
            raise ValueError("State not loaded")

        self._state.research_depth[topic] = depth

    def add_researched_entity(self, entity_type: str, entity: str):
        """Add an entity that has been researched."""
        if not self._state:
            raise ValueError("State not loaded")

        if entity_type not in self._state.entities_researched:
            self._state.entities_researched[entity_type] = []

        if entity not in self._state.entities_researched[entity_type]:
            self._state.entities_researched[entity_type].append(entity)

    def mark_gap_addressed(self, gap_id: str):
        """Mark a gap as addressed."""
        if not self._state:
            return

        for gap in self._state.identified_gaps:
            if gap.gap_id == gap_id:
                gap.status = "addressed"
                gap.addressed_at = datetime.now()
                break

    def add_gap(self, gap: ResearchGap):
        """Add a new identified gap."""
        if not self._state:
            raise ValueError("State not loaded")

        # Check for duplicate gaps
        existing_ids = [g.gap_id for g in self._state.identified_gaps]
        if gap.gap_id not in existing_ids:
            self._state.identified_gaps.append(gap)

    def get_queries_to_skip(self) -> List[str]:
        """Get list of queries that should be skipped."""
        if not self._state:
            return []

        return [q.query for q in self._state.completed_queries]

    def get_session_summary(self) -> Dict[str, Any]:
        """Generate a summary of current research state."""
        if not self._state:
            return {"error": "State not loaded"}

        pending_gaps = [g for g in self._state.identified_gaps if g.status == "pending"]
        high_priority = [
            g for g in pending_gaps if g.priority in [GapPriority.CRITICAL, GapPriority.HIGH]
        ]

        return {
            "state_tracker_output": {
                "project_id": self._state.project_id,
                "coverage_summary": self._state.coverage.to_dict(),
                "total_queries_completed": len(self._state.completed_queries),
                "total_sources_discovered": len(self._state.discovered_sources),
                "gaps_found": len(pending_gaps),
                "high_priority_gaps": [
                    {
                        "gap_id": g.gap_id,
                        "description": g.description,
                        "suggested_action": g.suggested_queries[0] if g.suggested_queries else None,
                    }
                    for g in high_priority[:5]
                ],
                "queries_to_skip": self.get_queries_to_skip(),
                "recommended_next_queries": self._get_recommended_queries(pending_gaps),
                "entities_researched": self._state.entities_researched,
            }
        }

    def _get_recommended_queries(self, gaps: List[ResearchGap], limit: int = 5) -> List[str]:
        """Get recommended queries based on gaps."""
        queries = []
        for gap in gaps:
            queries.extend(gap.suggested_queries)
            if len(queries) >= limit:
                break
        return queries[:limit]

    # ============ Edge Case Handling Methods ============

    def create_checkpoint(
        self, phase: str, checkpoint_id: Optional[str] = None
    ) -> ResearchCheckpoint:
        """Create a checkpoint for resumable research."""
        if not self._state:
            raise ValueError("State not loaded")

        # Use filesystem-safe timestamp format (no colons)
        cp_id = checkpoint_id or f"checkpoint-{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        checkpoint = ResearchCheckpoint(
            checkpoint_id=cp_id,
            phase=phase,
            state_snapshot=self._state.to_dict(),
        )

        self._current_checkpoint = checkpoint
        self._save_checkpoint(checkpoint)
        logger.info(f"Created checkpoint {cp_id} for phase '{phase}'")
        return checkpoint

    def _save_checkpoint(self, checkpoint: ResearchCheckpoint):
        """Save checkpoint to disk."""
        self._ensure_directories()
        checkpoint_file = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

    def handle_interrupted_research(
        self, project_id: str
    ) -> Tuple[bool, Optional[ResearchCheckpoint]]:
        """Recover from interrupted research using checkpoints."""
        checkpoint = self._find_latest_checkpoint()
        if not checkpoint:
            logger.info("No checkpoint found, starting fresh")
            return False, None

        try:
            # Verify checkpoint is recoverable
            if not checkpoint.is_recoverable:
                logger.warning(
                    f"Checkpoint {checkpoint.checkpoint_id} is not marked as recoverable"
                )
                return False, None

            # Restore state from checkpoint snapshot
            if checkpoint.state_snapshot:
                self._state = ResearchState.from_dict(checkpoint.state_snapshot)
                self._current_checkpoint = checkpoint
                logger.info(f"Resumed research from checkpoint {checkpoint.checkpoint_id}")
                logger.info(f"Completed steps: {checkpoint.completed_steps}")
                return True, checkpoint
        except Exception as e:
            logger.error(f"Failed to recover from checkpoint: {e}")
            return False, None

        return False, None

    def handle_partial_results(self, phase: str, results: Dict[str, Any]) -> Dict[str, Any]:
        """Process partial results from interrupted research."""
        if not self._state:
            raise ValueError("State not loaded")

        if not self._current_checkpoint:
            self.create_checkpoint(phase)

        # Store partial results in checkpoint
        if self._current_checkpoint:
            self._current_checkpoint.partial_results.update(results)
            self._current_checkpoint.last_updated = datetime.now()
            self._save_checkpoint(self._current_checkpoint)

        processed = {
            "partial_results_stored": True,
            "phase": phase,
            "items_processed": len(results),
            "checkpoint_id": (
                self._current_checkpoint.checkpoint_id if self._current_checkpoint else None
            ),
        }

        logger.info(f"Stored {len(results)} partial results in phase '{phase}'")
        return processed

    def handle_async_failure(
        self, task_id: str, error: str, fallback_action: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle async task failure with recovery mechanisms."""
        if not self._state:
            raise ValueError("State not loaded")

        # Record failed task
        if not self._current_checkpoint:
            self.create_checkpoint("async_failure_recovery")

        if self._current_checkpoint:
            self._current_checkpoint.failed_tasks[task_id] = error
            self._current_checkpoint.last_updated = datetime.now()
            self._save_checkpoint(self._current_checkpoint)

        # Log recovery action
        recovery_record = {
            "task_id": task_id,
            "error": error,
            "timestamp": datetime.now().isoformat(),
            "fallback_action": fallback_action,
            "checkpoint_id": (
                self._current_checkpoint.checkpoint_id if self._current_checkpoint else None
            ),
        }

        self._log_recovery_event(recovery_record)
        logger.warning(f"Task {task_id} failed: {error}")
        if fallback_action:
            logger.info(f"Fallback action: {fallback_action}")

        return {
            "recovery_initiated": True,
            "task_id": task_id,
            "fallback_action": fallback_action,
        }

    def validate_state_consistency(self) -> List[str]:
        """Validate state consistency and detect corruptions."""
        if not self._state:
            return ["State not loaded"]

        errors = []

        # Check for orphaned state files
        if self.state_file.exists() and not self._state.project_id:
            errors.append("State file exists but project_id is missing")

        # Validate timestamps
        if self._state.created_at > self._state.last_updated:
            errors.append("last_updated is before created_at")

        # Validate coverage percentages
        for category, coverage in self._state.coverage.by_category.items():
            if not 0 <= coverage <= 100:
                errors.append(f"Coverage for {category} is {coverage}% (should be 0-100)")

        # Validate source counts
        if len(self._state.discovered_sources) < 0:
            errors.append("Negative number of discovered sources")

        # Check for duplicate gaps
        gap_ids = [g.gap_id for g in self._state.identified_gaps]
        if len(gap_ids) != len(set(gap_ids)):
            errors.append("Duplicate gap IDs detected")

        # Validate entity research records
        for entity_type, entities in self._state.entities_researched.items():
            if not isinstance(entities, list):
                errors.append(f"Entities for {entity_type} is not a list")

        # Check for invalid depth values
        for topic, depth in self._state.research_depth.items():
            if not isinstance(depth, ResearchDepth):
                errors.append(f"Invalid research depth for topic '{topic}'")

        self._validation_errors = errors
        return errors

    def repair_state(self) -> Dict[str, Any]:
        """Attempt to repair detected state issues."""
        if not self._state:
            return {"repair_failed": True, "reason": "State not loaded"}

        errors_before = len(self._validation_errors)
        repairs_made = []

        try:
            # Fix coverage percentages
            for category in self._state.coverage.by_category:
                value = self._state.coverage.by_category[category]
                if value > 100:
                    self._state.coverage.by_category[category] = 100.0
                    repairs_made.append(f"Capped coverage for {category} to 100%")
                elif value < 0:
                    self._state.coverage.by_category[category] = 0.0
                    repairs_made.append(f"Set coverage for {category} to 0%")

            # Remove duplicate gaps (keep first)
            gap_ids = {}
            deduplicated_gaps = []
            for gap in self._state.identified_gaps:
                if gap.gap_id not in gap_ids:
                    gap_ids[gap.gap_id] = True
                    deduplicated_gaps.append(gap)
                else:
                    repairs_made.append(f"Removed duplicate gap {gap.gap_id}")
            self._state.identified_gaps = deduplicated_gaps

            # Recalculate coverage metrics
            self._state.coverage.recalculate_overall()
            repairs_made.append("Recalculated overall coverage")

            # Save repaired state
            self.save_state()
            logger.info(f"Repaired {len(repairs_made)} state issues")

            return {
                "repair_successful": True,
                "errors_before": errors_before,
                "repairs_made": repairs_made,
                "errors_after": len(self.validate_state_consistency()),
            }
        except Exception as e:
            logger.error(f"Failed to repair state: {e}")
            return {"repair_failed": True, "reason": str(e)}

    def _find_latest_checkpoint(self) -> Optional[ResearchCheckpoint]:
        """Find the most recent checkpoint."""
        if not self.checkpoint_dir.exists():
            return None

        checkpoint_files = sorted(self.checkpoint_dir.glob("checkpoint-*.json"), reverse=True)
        if not checkpoint_files:
            return None

        try:
            with open(checkpoint_files[0], "r") as f:
                data = json.load(f)
            return ResearchCheckpoint.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None

    def _recover_from_checkpoint(self, project_id: str) -> bool:
        """Attempt to recover state from most recent checkpoint."""
        checkpoint = self._find_latest_checkpoint()
        if not checkpoint or not checkpoint.state_snapshot:
            return False

        try:
            self._state = ResearchState.from_dict(checkpoint.state_snapshot)
            self._current_checkpoint = checkpoint
            return True
        except Exception as e:
            logger.error(f"Failed to recover from checkpoint: {e}")
            return False

    def _log_recovery_event(self, record: Dict[str, Any]):
        """Log recovery event to recovery log."""
        self._ensure_directories()
        recovery_log = []

        # Load existing recovery log
        if self.recovery_log_file.exists():
            try:
                with open(self.recovery_log_file, "r") as f:
                    recovery_log = json.load(f)
            except json.JSONDecodeError:
                recovery_log = []

        # Add new record
        recovery_log.append(record)

        # Keep only last 100 recovery events
        recovery_log = recovery_log[-100:]

        # Save updated log
        with open(self.recovery_log_file, "w") as f:
            json.dump(recovery_log, f, indent=2)
