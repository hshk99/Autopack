"""Research Orchestrator for coordinating research sessions.

This module provides the ResearchOrchestrator class which coordinates research
workflows including traditional sessions and bootstrap sessions with parallel
execution and 24-hour caching.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

# Analysis modules for cost-effectiveness, state tracking, and follow-up triggers
from autopack.research.analysis import (
    BudgetEnforcer,
    BuildHistoryAnalyzer,
    CostEffectivenessAnalyzer,
    FollowupResearchTrigger,
    ResearchStateTracker,
)
from autopack.research.analysis.pattern_extractor import (
    PatternExtractionResult,
    PatternExtractor,
)
from autopack.research.discovery.project_history_analyzer import (
    ProjectHistoryAnalyzer,
)
from autopack.research.frameworks.competitive_intensity import CompetitiveIntensity
from autopack.research.frameworks.market_attractiveness import MarketAttractiveness
from autopack.research.frameworks.product_feasibility import ProductFeasibility
from autopack.research.idea_parser import ParsedIdea, ProjectType
from autopack.research.models.bootstrap_session import (
    BootstrapPhase,
    BootstrapSession,
    generate_idea_hash,
)
from autopack.research.phase_scheduler import (
    PhaseScheduler,
    PhaseTask,
    PhasePriority,
)
from autopack.research.models.enums import ValidationStatus
from autopack.research.models.research_intent import ResearchIntent
from autopack.research.models.research_session import ResearchSession
from autopack.research.validators.evidence_validator import EvidenceValidator
from autopack.research.validators.quality_validator import QualityValidator
from autopack.research.validators.recency_validator import RecencyValidator

logger = logging.getLogger(__name__)

# Default cache TTL: 24 hours
CACHE_TTL_HOURS = 24


class ResearchCache:
    """Cache for research results with 24-hour TTL.

    Stores bootstrap session results keyed by idea hash to avoid
    redundant research for identical or similar project ideas.
    """

    def __init__(self, ttl_hours: int = CACHE_TTL_HOURS):
        """Initialize the research cache.

        Args:
            ttl_hours: Time-to-live in hours for cached entries (default: 24)
        """
        self._cache: dict[str, BootstrapSession] = {}
        self.ttl_hours = ttl_hours

    def get(self, idea_hash: str) -> Optional[BootstrapSession]:
        """Get cached session if valid.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            Cached BootstrapSession if valid, None otherwise
        """
        session = self._cache.get(idea_hash)
        if session and session.is_cached_valid():
            logger.debug(f"Cache hit for idea hash: {idea_hash[:8]}...")
            return session
        elif session:
            # Cache entry exists but expired
            logger.debug(f"Cache expired for idea hash: {idea_hash[:8]}...")
            del self._cache[idea_hash]
        return None

    def set(self, idea_hash: str, session: BootstrapSession) -> None:
        """Store session in cache with TTL.

        Args:
            idea_hash: Hash of the parsed idea
            session: BootstrapSession to cache
        """
        session.expires_at = datetime.now() + timedelta(hours=self.ttl_hours)
        self._cache[idea_hash] = session
        logger.debug(
            f"Cached session for idea hash: {idea_hash[:8]}... (expires: {session.expires_at})"
        )

    def invalidate(self, idea_hash: str) -> bool:
        """Invalidate a cached entry.

        Args:
            idea_hash: Hash of the parsed idea

        Returns:
            True if entry was removed, False if not found
        """
        if idea_hash in self._cache:
            del self._cache[idea_hash]
            logger.debug(f"Invalidated cache for idea hash: {idea_hash[:8]}...")
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.debug("Research cache cleared")

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        expired = [
            key
            for key, session in self._cache.items()
            if session.expires_at and session.expires_at < now
        ]
        for key in expired:
            del self._cache[key]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired cache entries")
        return len(expired)


class ResearchOrchestrator:
    """Orchestrates research workflows including bootstrap sessions.

    Coordinates the entire research process from session initiation to
    validation and publication. Supports both traditional research sessions
    and bootstrap sessions with parallel execution and caching.

    Enhanced with:
    - Cost-effectiveness analysis for build/buy decisions
    - Incremental research via state tracking
    - Automated follow-up research triggers
    - Cross-project learning and pattern reuse
    """

    def __init__(
        self,
        cache_ttl_hours: int = CACHE_TTL_HOURS,
        project_root: Optional[Path] = None,
        budget_enforcer: Optional[BudgetEnforcer] = None,
        max_concurrent_phases: int = 3,
        max_phase_resources: float = 1.0,
    ):
        """Initialize the ResearchOrchestrator.

        Args:
            cache_ttl_hours: TTL for research cache in hours (default: 24)
            project_root: Root directory for project state files (optional)
            budget_enforcer: Optional budget enforcer for cost limits (default: $5000)
            max_concurrent_phases: Maximum concurrent research phases (default: 3)
            max_phase_resources: Maximum total resource usage for phases (default: 1.0)
        """
        self.sessions: dict[str, ResearchSession] = {}
        self.bootstrap_sessions: dict[str, BootstrapSession] = {}
        self._cache = ResearchCache(ttl_hours=cache_ttl_hours)

        # Initialize budget enforcer with default budget if not provided
        self._budget_enforcer = budget_enforcer or BudgetEnforcer(total_budget=5000.0)

        # Phase scheduler for dependency-aware scheduling
        self._scheduler = PhaseScheduler(
            max_concurrent_tasks=max_concurrent_phases,
            max_total_resources=max_phase_resources,
        )
        self._scheduler._check_budget_before_phase = self._check_budget_before_phase

        # Analysis components
        self._cost_analyzer = CostEffectivenessAnalyzer()
        self._followup_trigger = FollowupResearchTrigger()
        self._state_tracker: Optional[ResearchStateTracker] = None

        # Cross-project learning components
        self._pattern_extractor = PatternExtractor()
        self._history_analyzer: Optional[ProjectHistoryAnalyzer] = None
        self._pattern_cache: Optional[PatternExtractionResult] = None

        # Build history analyzer for feasibility and cost feedback
        self._build_history_analyzer: Optional[BuildHistoryAnalyzer] = None

        # Initialize state tracker if project root provided
        if project_root:
            self._state_tracker = ResearchStateTracker(project_root)
            history_path = project_root / ".autopack" / "project_history.json"
            self._history_analyzer = ProjectHistoryAnalyzer(
                project_history_path=history_path
            )
            # Initialize build history analyzer with BUILD_HISTORY.md path
            build_history_path = project_root / "BUILD_HISTORY.md"
            self._build_history_analyzer = BuildHistoryAnalyzer(
                build_history_path=build_history_path
            )

    def initialize_state_tracking(self, project_root: Path, project_id: str) -> None:
        """Initialize research state tracking for incremental research.

        Args:
            project_root: Root directory for project state files
            project_id: Unique project identifier
        """
        self._state_tracker = ResearchStateTracker(project_root)
        self._state_tracker.load_or_create_state(project_id)
        logger.info(f"Initialized state tracking for project: {project_id}")

    def initialize_budget_from_cost_analysis(self, cost_analysis: dict[str, Any]) -> None:
        """Initialize research budget from cost-effectiveness analysis.

        Extracts budget constraints from cost analysis and sets them
        as the research pipeline budget limits.

        Args:
            cost_analysis: Cost-effectiveness analysis results
        """
        tco = cost_analysis.get("total_cost_of_ownership", {})
        year_1_cost = tco.get("year_1", {}).get("total", 5000.0)

        # Use year 1 research estimate as budget ceiling
        # Research typically uses 10-15% of development budget
        research_budget = year_1_cost * 0.15

        self._budget_enforcer.set_budget(research_budget)
        logger.info(
            f"Initialized research budget from cost analysis: ${research_budget:.2f} "
            f"(based on Year 1 TCO of ${year_1_cost:.2f})"
        )

    def complete_research_phase(self, phase_name: str, actual_cost: Optional[float] = None) -> None:
        """Mark a research phase as complete.

        Args:
            phase_name: Name of the phase
            actual_cost: Actual cost incurred (optional)
        """
        self._budget_enforcer.complete_phase(phase_name, actual_cost)

    def get_budget_metrics(self) -> dict[str, Any]:
        """Get current budget metrics and status.

        Returns:
            Dictionary with budget information
        """
        return self._budget_enforcer.get_metrics().to_dict()

    def get_budget_status(self) -> dict[str, Any]:
        """Get human-readable budget status.

        Returns:
            Dictionary with status summary
        """
        return self._budget_enforcer.get_status_summary()

    def get_scheduler_metrics(self) -> dict[str, Any]:
        """Get metrics from the phase scheduler.

        Returns:
            Dictionary with scheduler metrics including execution time, speedup, and resource utilization
        """
        return self._scheduler.get_metrics().to_dict()

    def get_phase_execution_order(self) -> list[str]:
        """Get the optimal phase execution order based on dependencies and priorities.

        Returns:
            List of phase IDs in execution order
        """
        return self._scheduler.get_execution_order()

    def _check_budget_before_phase(self, phase_name: str) -> bool:
        """Check budget before starting a research phase.

        Args:
            phase_name: Name of the research phase about to start

        Returns:
            True if budget allows proceeding, False if exhausted
        """
        can_proceed = self._budget_enforcer.can_proceed(phase_name)
        if can_proceed:
            self._budget_enforcer.start_phase(phase_name)
        return can_proceed

    def start_session(
        self, intent_title: str, intent_description: str, intent_objectives: list
    ) -> str:
        """Start a new research session.

        Args:
            intent_title: Title of the research intent
            intent_description: Description of the research intent
            intent_objectives: List of research objectives

        Returns:
            Session ID for tracking
        """
        intent = ResearchIntent(intent_title, intent_description, intent_objectives)
        session = ResearchSession(intent)
        session_id = str(uuid4())
        self.sessions[session_id] = session
        return session_id

    def validate_session(self, session_id: str) -> str:
        """Validate the research session.

        Args:
            session_id: ID of the session to validate

        Returns:
            Validation status message
        """
        session = self.sessions.get(session_id)
        if not session:
            return "Session not found."

        evidence_validator = EvidenceValidator()
        recency_validator = RecencyValidator()
        quality_validator = QualityValidator()

        # Perform validation checks
        evidence_valid = evidence_validator.validate(session)
        recency_valid = recency_validator.validate(session)
        quality_valid = quality_validator.validate(session)

        if evidence_valid and recency_valid and quality_valid:
            session.validation_status = ValidationStatus.VALIDATED
            return "Session validated successfully."
        else:
            session.validation_status = ValidationStatus.FAILED
            return "Session validation failed."

    def publish_session(self, session_id: str) -> bool:
        """Publish the research findings.

        Args:
            session_id: ID of the session to publish

        Returns:
            True if published successfully, False otherwise
        """
        session = self.sessions.get(session_id)
        if not session or session.validation_status != ValidationStatus.VALIDATED:
            return False

        # Logic to publish the session's findings
        session.complete()
        return True

    async def start_bootstrap_session(
        self,
        parsed_idea: ParsedIdea,
        use_cache: bool = True,
        parallel: bool = True,
    ) -> BootstrapSession:
        """Start a bootstrap session for project initialization research.

        Coordinates market research, competitive analysis, and technical
        feasibility research. Supports parallel execution to reduce total
        time by approximately 50%.

        Args:
            parsed_idea: ParsedIdea from IdeaParser
            use_cache: Whether to use cached results if available (default: True)
            parallel: Whether to execute research phases in parallel (default: True)

        Returns:
            BootstrapSession with research results
        """
        # Generate hash for caching
        idea_hash = generate_idea_hash(
            parsed_idea.title,
            parsed_idea.description,
            parsed_idea.detected_project_type.value,
        )

        # Check cache first
        if use_cache:
            cached_session = self._cache.get(idea_hash)
            if cached_session and cached_session.is_complete():
                logger.info(f"Returning cached bootstrap session for: {parsed_idea.title}")
                return cached_session

        # Create new bootstrap session
        session_id = str(uuid4())
        session = BootstrapSession(
            session_id=session_id,
            idea_hash=idea_hash,
            parsed_idea_title=parsed_idea.title,
            parsed_idea_type=parsed_idea.detected_project_type.value,
        )

        self.bootstrap_sessions[session_id] = session
        logger.info(f"Started bootstrap session {session_id} for: {parsed_idea.title}")

        # Execute research phases
        if parallel:
            session.parallel_execution_used = True
            await self._execute_research_parallel(session, parsed_idea)
        else:
            await self._execute_research_sequential(session, parsed_idea)

        # Synthesize results if all phases completed
        if session.is_complete():
            session.synthesis = self._synthesize_research(session, parsed_idea)
            session.current_phase = BootstrapPhase.COMPLETED
            # Cache the completed session
            self._cache.set(idea_hash, session)
            logger.info(f"Bootstrap session {session_id} completed and cached")
        else:
            failed = session.get_failed_phases()
            if failed:
                session.current_phase = BootstrapPhase.FAILED
                logger.warning(
                    f"Bootstrap session {session_id} failed phases: {[p[0].value for p in failed]}"
                )

        return session

    async def _execute_research_parallel(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Execute research phases in parallel using dependency-aware scheduling.

        Uses PhaseScheduler to optimize concurrent execution with:
        - Dependency awareness (technical feasibility can inform cost analysis)
        - Resource-aware scheduling
        - Priority-based task ordering
        - Execution metrics

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        logger.debug(
            f"Executing research phases in parallel for session {session.session_id} "
            "using dependency-aware scheduler"
        )

        # Reset scheduler for this execution
        self._scheduler.reset()

        # Create phase tasks with priorities and dependencies
        # Market research and competitive analysis are independent
        market_task = PhaseTask(
            phase_id="market_research",
            phase_name="Market Attractiveness Research",
            task_func=lambda: self._run_market_research(session, parsed_idea),
            priority=PhasePriority.HIGH,
            dependencies=[],
            estimated_duration_seconds=10.0,
            resource_requirement=0.3,
        )

        competitive_task = PhaseTask(
            phase_id="competitive_analysis",
            phase_name="Competitive Intensity Analysis",
            task_func=lambda: self._run_competitive_analysis(session, parsed_idea),
            priority=PhasePriority.HIGH,
            dependencies=[],
            estimated_duration_seconds=10.0,
            resource_requirement=0.3,
        )

        # Technical feasibility can be independent but may benefit from market insights
        feasibility_task = PhaseTask(
            phase_id="technical_feasibility",
            phase_name="Product Feasibility Assessment",
            task_func=lambda: self._run_technical_feasibility(session, parsed_idea),
            priority=PhasePriority.NORMAL,
            dependencies=[],  # No dependencies - all phases can run in parallel
            estimated_duration_seconds=12.0,
            resource_requirement=0.4,
        )

        # Register phases with scheduler
        self._scheduler.register_phase(market_task)
        self._scheduler.register_phase(competitive_task)
        self._scheduler.register_phase(feasibility_task)

        # Execute with dependency-aware scheduling
        result = await self._scheduler.schedule_and_execute(sequential=False)

        # Log execution metrics
        metrics = result.get("metrics", {})
        logger.info(
            f"Research phase execution completed: "
            f"total_time={metrics.get('total_execution_time', 0):.2f}s, "
            f"speedup={metrics.get('parallel_speedup', 1.0):.2f}x, "
            f"resource_util={metrics.get('resource_utilization', 0):.2f}"
        )

        # Handle failed phases
        if not result.get("success", False):
            failed = result.get("failed_phases", [])
            logger.warning(f"Research phases failed: {failed}")

    async def _execute_research_sequential(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Execute research phases sequentially using the scheduler.

        Useful for debugging and ensuring deterministic phase ordering.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        logger.debug(f"Executing research phases sequentially for session {session.session_id}")

        # Reset scheduler for this execution
        self._scheduler.reset()

        # Create phase tasks (same as parallel, but will execute sequentially)
        market_task = PhaseTask(
            phase_id="market_research",
            phase_name="Market Attractiveness Research",
            task_func=lambda: self._run_market_research(session, parsed_idea),
            priority=PhasePriority.HIGH,
            dependencies=[],
            estimated_duration_seconds=10.0,
            resource_requirement=0.3,
        )

        competitive_task = PhaseTask(
            phase_id="competitive_analysis",
            phase_name="Competitive Intensity Analysis",
            task_func=lambda: self._run_competitive_analysis(session, parsed_idea),
            priority=PhasePriority.HIGH,
            dependencies=[],
            estimated_duration_seconds=10.0,
            resource_requirement=0.3,
        )

        feasibility_task = PhaseTask(
            phase_id="technical_feasibility",
            phase_name="Product Feasibility Assessment",
            task_func=lambda: self._run_technical_feasibility(session, parsed_idea),
            priority=PhasePriority.NORMAL,
            dependencies=[],
            estimated_duration_seconds=12.0,
            resource_requirement=0.4,
        )

        # Register phases
        self._scheduler.register_phase(market_task)
        self._scheduler.register_phase(competitive_task)
        self._scheduler.register_phase(feasibility_task)

        # Execute sequentially (for debugging/determinism)
        result = await self._scheduler.schedule_and_execute(sequential=True)

        if not result.get("success", False):
            failed = result.get("failed_phases", [])
            logger.warning(f"Research phases failed: {failed}")

    async def _run_market_research(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Run market research phase.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        phase = BootstrapPhase.MARKET_RESEARCH
        session.mark_phase_started(phase)

        try:
            # Define market indicators based on project type
            indicators = self._get_market_indicators(parsed_idea.detected_project_type)
            framework = MarketAttractiveness(indicators)

            # Build evaluation data from parsed idea
            eval_data = self._build_market_data(parsed_idea)

            # Run evaluation
            result = framework.evaluate(eval_data)

            # Store results
            data = {
                "framework": result.get("framework"),
                "attractiveness_score": result.get("attractiveness", 0),
                "details": result.get("details"),
                "indicators_evaluated": indicators,
                "project_type": parsed_idea.detected_project_type.value,
                "raw_requirements_analyzed": len(parsed_idea.raw_requirements),
            }

            session.mark_phase_completed(phase, data)
            self.complete_research_phase("market_research")
            logger.debug(f"Market research completed for session {session.session_id}")

        except Exception as e:
            session.mark_phase_failed(phase, [str(e)])
            logger.error(f"Market research failed for session {session.session_id}: {e}")

    async def _run_competitive_analysis(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Run competitive analysis phase.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        phase = BootstrapPhase.COMPETITIVE_ANALYSIS
        session.mark_phase_started(phase)

        try:
            # Define competitive factors based on project type
            factors = self._get_competitive_factors(parsed_idea.detected_project_type)
            framework = CompetitiveIntensity(factors)

            # Build evaluation data from parsed idea
            eval_data = self._build_competitive_data(parsed_idea)

            # Run evaluation
            result = framework.evaluate(eval_data)

            # Store results
            data = {
                "framework": result.get("framework"),
                "intensity_score": result.get("intensity", 0),
                "details": result.get("details"),
                "factors_evaluated": factors,
                "dependencies_identified": parsed_idea.dependencies,
            }

            session.mark_phase_completed(phase, data)
            self.complete_research_phase("competitive_analysis")
            logger.debug(f"Competitive analysis completed for session {session.session_id}")

        except Exception as e:
            session.mark_phase_failed(phase, [str(e)])
            logger.error(f"Competitive analysis failed for session {session.session_id}: {e}")

    async def _run_technical_feasibility(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Run technical feasibility phase.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        phase = BootstrapPhase.TECHNICAL_FEASIBILITY
        session.mark_phase_started(phase)

        try:
            # Define feasibility parameters based on project type
            parameters = self._get_feasibility_parameters(parsed_idea.detected_project_type)
            framework = ProductFeasibility(parameters)

            # Build evaluation data from parsed idea
            eval_data = self._build_feasibility_data(parsed_idea)

            # Run evaluation
            result = framework.evaluate(eval_data)

            # Store results
            data = {
                "framework": result.get("framework"),
                "feasibility_score": result.get("feasibility", 0),
                "details": result.get("details"),
                "parameters_evaluated": parameters,
                "risk_profile": parsed_idea.risk_profile.value,
                "dependencies": parsed_idea.dependencies,
            }

            session.mark_phase_completed(phase, data)
            self.complete_research_phase("technical_feasibility")
            logger.debug(f"Technical feasibility completed for session {session.session_id}")

        except Exception as e:
            session.mark_phase_failed(phase, [str(e)])
            logger.error(f"Technical feasibility failed for session {session.session_id}: {e}")

    def run_cost_effectiveness_analysis(
        self,
        session: BootstrapSession,
        build_vs_buy_results: list[dict[str, Any]],
        ai_features: Optional[list[dict[str, Any]]] = None,
        user_projections: Optional[dict[str, int]] = None,
    ) -> dict[str, Any]:
        """Run cost-effectiveness analysis on completed research.

        Args:
            session: BootstrapSession with completed phases
            build_vs_buy_results: List of component build/buy/integrate decisions
            ai_features: Optional list of AI feature specifications for token cost modeling
            user_projections: Optional user growth projections {year: user_count}

        Returns:
            Cost-effectiveness analysis results including TCO, projections, and recommendations
        """
        logger.info(f"Running cost-effectiveness analysis for session {session.session_id}")

        # Check budget before expensive analysis phase
        if not self._check_budget_before_phase("cost_effectiveness_analysis"):
            logger.warning("Budget exhausted, cannot run cost-effectiveness analysis")
            return {"error": "Budget exhausted"}

        # Extract technical feasibility data if available
        technical_feasibility = None
        if session.technical_feasibility and session.technical_feasibility.data:
            technical_feasibility = session.technical_feasibility.data

        # Run cost analysis
        cost_analysis = self._cost_analyzer.analyze(
            project_name=session.parsed_idea_title,
            build_vs_buy_results=build_vs_buy_results,
            technical_feasibility=technical_feasibility,
            tool_availability=None,  # Can be populated from tool-availability-agent
            ai_features=ai_features,
            user_projections=user_projections,
        )

        # Initialize research budget based on cost analysis results
        self.initialize_budget_from_cost_analysis(cost_analysis)

        # Mark analysis phase as complete
        self.complete_research_phase("cost_effectiveness_analysis")

        logger.info(
            f"Cost analysis completed: Year 1 TCO = ${cost_analysis.get('executive_summary', {}).get('total_year_1_cost', 'N/A')}"
        )

        return cost_analysis

    def analyze_followup_triggers(
        self,
        analysis_results: dict[str, Any],
        validation_results: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Analyze research results for follow-up research triggers.

        Identifies gaps, uncertainties, and areas needing deeper research.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results

        Returns:
            Trigger analysis with recommended follow-up research
        """
        logger.info("Analyzing for follow-up research triggers")

        trigger_result = self._followup_trigger.analyze(
            analysis_results=analysis_results,
            validation_results=validation_results,
        )

        if trigger_result.should_research:
            logger.info(
                f"Found {trigger_result.triggers_selected} triggers requiring follow-up research"
            )
        else:
            logger.info("No follow-up research needed")

        return trigger_result.to_dict()

    def get_research_gaps(self) -> list[dict[str, Any]]:
        """Get current research gaps from state tracker.

        Returns:
            List of identified research gaps with priorities
        """
        if not self._state_tracker:
            return []

        gaps = self._state_tracker.detect_gaps()
        return [g.to_dict() for g in gaps]

    def get_queries_to_skip(self) -> list[str]:
        """Get list of queries that should be skipped (already researched).

        Returns:
            List of query strings to skip
        """
        if not self._state_tracker:
            return []

        return self._state_tracker.get_queries_to_skip()

    def record_research_query(
        self,
        query: str,
        agent: str,
        sources_found: int,
        quality_score: float,
        findings: Any,
    ) -> None:
        """Record a completed research query for state tracking.

        Args:
            query: The research query executed
            agent: Agent that performed the research
            sources_found: Number of sources discovered
            quality_score: Quality score of findings (0-1)
            findings: The research findings
        """
        if not self._state_tracker:
            return

        self._state_tracker.record_completed_query(
            query=query,
            agent=agent,
            sources_found=sources_found,
            quality_score=quality_score,
            findings=findings,
        )
        self._state_tracker.save_state()

    def get_research_state_summary(self) -> dict[str, Any]:
        """Get summary of current research state.

        Returns:
            Research state summary including coverage and gaps
        """
        if not self._state_tracker:
            return {"error": "State tracking not initialized"}

        return self._state_tracker.get_session_summary()

    # ========================================================================
    # Cross-Project Learning and Pattern Methods
    # ========================================================================

    def initialize_pattern_learning(
        self,
        learning_db: Any,
        project_history_path: Optional[Path] = None,
    ) -> None:
        """Initialize cross-project learning with pattern extraction.

        Args:
            learning_db: LearningDatabase instance for pattern storage
            project_history_path: Optional path to project history file
        """
        if project_history_path:
            self._history_analyzer = ProjectHistoryAnalyzer(
                learning_db=learning_db,
                project_history_path=project_history_path,
            )
        elif self._history_analyzer:
            self._history_analyzer.set_learning_db(learning_db)
        else:
            self._history_analyzer = ProjectHistoryAnalyzer(learning_db=learning_db)

        logger.info("Initialized cross-project learning with pattern extraction")

    def extract_patterns_from_history(
        self,
        learning_db: Optional[Any] = None,
    ) -> PatternExtractionResult:
        """Extract patterns from historical project data.

        Analyzes past projects, improvements, and cycles to identify
        successful patterns that can inform new project recommendations.

        Args:
            learning_db: Optional LearningDatabase instance

        Returns:
            PatternExtractionResult with extracted patterns
        """
        logger.info("Extracting patterns from project history")

        # Get data from history analyzer
        if not self._history_analyzer:
            self._history_analyzer = ProjectHistoryAnalyzer(learning_db=learning_db)

        if learning_db:
            self._history_analyzer.set_learning_db(learning_db)

        # Analyze history
        history_result = self._history_analyzer.analyze_history(
            include_improvements=True,
            include_cycles=True,
        )

        # Convert project summaries to format expected by pattern extractor
        project_history = []
        for summary in history_result.project_summaries:
            project_history.append({
                "project_id": summary.project_id,
                "project_type": summary.project_type,
                "outcome": summary.overall_outcome,
                "tech_stack": summary.tech_stack,
                "architecture": summary.architecture,
                "monetization": summary.monetization,
                "deployment": summary.deployment,
                "timestamp": summary.start_date or "",
            })

        # Get improvement and cycle data from learning_db if available
        improvement_outcomes: dict[str, dict[str, Any]] = {}
        cycle_data: dict[str, dict[str, Any]] = {}

        if learning_db:
            for imp in learning_db.list_improvements():
                imp_id = imp.get("imp_id", "")
                if imp_id:
                    improvement_outcomes[imp_id] = imp

            for cycle in learning_db.list_cycles():
                cycle_id = cycle.get("cycle_id", "")
                if cycle_id:
                    cycle_data[cycle_id] = cycle

        # Extract patterns
        extraction_result = self._pattern_extractor.extract_patterns(
            project_history=project_history,
            improvement_outcomes=improvement_outcomes,
            cycle_data=cycle_data,
        )

        # Cache the result
        self._pattern_cache = extraction_result

        logger.info(
            "Extracted %d patterns from %d projects",
            len(extraction_result.patterns),
            extraction_result.total_projects_analyzed,
        )

        return extraction_result

    def get_pattern_recommendations(
        self,
        project_context: dict[str, Any],
        learning_db: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """Get pattern recommendations for a new project.

        Uses extracted patterns to recommend approaches based on
        historical success rates and project context.

        Args:
            project_context: Context of the new project including:
                - project_type: Type of project
                - keywords: Relevant keywords for matching
                - requirements: Project requirements
            learning_db: Optional LearningDatabase for fresh extraction

        Returns:
            List of recommended patterns with relevance scores
        """
        logger.info("Getting pattern recommendations for project context")

        # Extract patterns if not cached
        if not self._pattern_cache:
            self.extract_patterns_from_history(learning_db)

        if not self._pattern_cache:
            return []

        # Get recommendations from pattern extractor
        recommendations = self._pattern_extractor.get_recommended_patterns(
            self._pattern_cache,
            project_context,
        )

        # Convert to dictionary format
        return [p.to_dict() for p in recommendations]

    def get_patterns_for_project_type(
        self,
        project_type: str,
    ) -> list[dict[str, Any]]:
        """Get patterns relevant to a specific project type.

        Args:
            project_type: Type of project to get patterns for

        Returns:
            List of relevant patterns sorted by success rate
        """
        if not self._pattern_cache:
            return []

        patterns = self._pattern_extractor.get_patterns_for_project_type(
            self._pattern_cache,
            project_type,
        )

        return [p.to_dict() for p in patterns]

    def record_project_outcome(
        self,
        project_id: str,
        project_type: str,
        outcome: str,
        tech_stack: Optional[dict[str, Any]] = None,
        architecture: Optional[dict[str, Any]] = None,
        monetization: Optional[dict[str, Any]] = None,
        deployment: Optional[dict[str, Any]] = None,
        lessons_learned: Optional[list[str]] = None,
        learning_db: Optional[Any] = None,
    ) -> bool:
        """Record a project outcome for future pattern learning.

        Stores project data in the history for future pattern extraction.

        Args:
            project_id: Unique project identifier
            project_type: Type of project
            outcome: Project outcome (successful, partial, abandoned, blocked)
            tech_stack: Technology stack used
            architecture: Architecture decisions
            monetization: Monetization strategy
            deployment: Deployment configuration
            lessons_learned: Key lessons from the project
            learning_db: Optional LearningDatabase for storage

        Returns:
            True if recording was successful
        """
        logger.info("Recording project outcome: %s (%s)", project_id, outcome)

        # Store in history analyzer if available
        if self._history_analyzer:
            from autopack.research.discovery.project_history_analyzer import (
                ProjectSummary,
            )

            summary = ProjectSummary(
                project_id=project_id,
                project_type=project_type,
                overall_outcome=outcome,
                tech_stack=tech_stack or {},
                architecture=architecture or {},
                monetization=monetization or {},
                deployment=deployment or {},
                lessons_learned=lessons_learned or [],
            )

            self._history_analyzer.save_project_summary(summary)

        # Also store in learning_db if available
        if learning_db:
            learning_db.store_project_history(
                project_id=project_id,
                project_data={
                    "project_type": project_type,
                    "outcome": outcome,
                    "tech_stack": tech_stack or {},
                    "architecture": architecture or {},
                    "monetization": monetization or {},
                    "deployment": deployment or {},
                    "lessons_learned": lessons_learned or [],
                },
            )

        # Invalidate pattern cache since we have new data
        self._pattern_cache = None

        return True

    def get_cross_project_insights(
        self,
        learning_db: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Get cross-project learning insights.

        Provides a summary of patterns, success factors, and
        recommendations based on historical project data.

        Args:
            learning_db: Optional LearningDatabase for insights

        Returns:
            Dictionary with cross-project insights
        """
        insights: dict[str, Any] = {
            "pattern_extraction": None,
            "history_analysis": None,
            "recommendations": [],
        }

        # Get pattern extraction results
        if not self._pattern_cache:
            self.extract_patterns_from_history(learning_db)

        if self._pattern_cache:
            insights["pattern_extraction"] = {
                "total_patterns": len(self._pattern_cache.patterns),
                "top_patterns": [p.to_dict() for p in self._pattern_cache.top_patterns[:5]],
                "emerging_patterns": [
                    p.to_dict() for p in self._pattern_cache.emerging_patterns[:3]
                ],
                "coverage_by_type": self._pattern_cache.coverage_by_type,
            }

        # Get history analysis
        if self._history_analyzer:
            history_result = self._history_analyzer.analyze_history()
            insights["history_analysis"] = {
                "projects_analyzed": history_result.projects_analyzed,
                "success_correlations": history_result.success_correlations[:5],
                "failure_correlations": history_result.failure_correlations[:3],
                "recommendations": history_result.recommendations,
            }
            insights["recommendations"] = history_result.recommendations

        # Get insights from learning_db if available
        if learning_db and hasattr(learning_db, "get_cross_project_insights"):
            db_insights = learning_db.get_cross_project_insights()
            insights["learning_db_insights"] = db_insights

        return insights

    # ========================================================================
    # Build History Feedback Methods
    # ========================================================================

    def initialize_build_history_analysis(
        self,
        build_history_path: Optional[Path] = None,
        max_history_days: int = 365,
    ) -> None:
        """Initialize build history analyzer for feedback.

        Args:
            build_history_path: Path to BUILD_HISTORY.md
            max_history_days: Maximum age of builds to consider
        """
        self._build_history_analyzer = BuildHistoryAnalyzer(
            build_history_path=build_history_path,
            max_history_days=max_history_days,
        )
        logger.info("Initialized build history analyzer for feedback")

    def get_build_history_feedback(
        self,
        project_type: Optional[str] = None,
        tech_stack: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Get build history feedback for research decisions.

        Analyzes historical build outcomes to provide feasibility and
        cost-effectiveness feedback for new project assessments.

        Args:
            project_type: Filter by project type
            tech_stack: Filter by tech stack components

        Returns:
            Analysis result with feasibility signals and cost feedback
        """
        if not self._build_history_analyzer:
            logger.warning("Build history analyzer not initialized")
            return {"error": "Build history analyzer not initialized"}

        result = self._build_history_analyzer.analyze(
            project_type=project_type,
            tech_stack=tech_stack,
        )

        logger.info(
            "Build history analysis complete: %d builds, %.1f%% success rate",
            result.total_builds_analyzed,
            result.overall_success_rate * 100,
        )

        return result.to_dict()

    def get_feasibility_adjustment(
        self,
        base_feasibility_score: float,
        project_type: Optional[str] = None,
        tech_stack: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Get feasibility score adjustment based on build history.

        Uses historical build data to adjust feasibility assessments
        for more accurate predictions.

        Args:
            base_feasibility_score: Initial feasibility score (0-1)
            project_type: Project type for filtering
            tech_stack: Tech stack for filtering

        Returns:
            Adjusted feasibility with explanation
        """
        if not self._build_history_analyzer:
            return {
                "original_score": base_feasibility_score,
                "adjusted_score": base_feasibility_score,
                "adjustment": 0.0,
                "confidence": 0.0,
                "explanation": "Build history analyzer not initialized",
            }

        return self._build_history_analyzer.get_feasibility_adjustment(
            base_feasibility_score=base_feasibility_score,
            project_type=project_type,
            tech_stack=tech_stack,
        )

    def get_cost_effectiveness_from_history(
        self,
        project_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get cost-effectiveness insights from build history.

        Analyzes historical cost data to provide feedback on
        estimation accuracy and optimization opportunities.

        Args:
            project_type: Filter by project type

        Returns:
            Cost-effectiveness feedback from history
        """
        if not self._build_history_analyzer:
            return {"error": "Build history analyzer not initialized"}

        feedback = self._build_history_analyzer.analyze_cost_effectiveness(
            project_type=project_type,
        )

        return feedback.to_dict()

    def enhance_research_with_build_history(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> dict[str, Any]:
        """Enhance research synthesis with build history feedback.

        Integrates build history insights into the research synthesis
        to provide more accurate recommendations.

        Args:
            session: Completed BootstrapSession
            parsed_idea: ParsedIdea for context

        Returns:
            Enhanced synthesis with build history feedback
        """
        # Get base synthesis
        synthesis = self._synthesize_research(session, parsed_idea)

        # Add build history feedback if analyzer is available
        if self._build_history_analyzer:
            project_type = parsed_idea.detected_project_type.value
            tech_stack = parsed_idea.dependencies

            # Get history analysis
            history_analysis = self._build_history_analyzer.analyze(
                project_type=project_type,
                tech_stack=tech_stack,
            )

            # Adjust feasibility score based on history
            if "scores" in synthesis:
                original_feasibility = synthesis["scores"].get("technical_feasibility", 0)
                normalized_feasibility = original_feasibility / 10  # Normalize to 0-1

                adjustment = self._build_history_analyzer.get_feasibility_adjustment(
                    base_feasibility_score=normalized_feasibility,
                    project_type=project_type,
                    tech_stack=tech_stack,
                )

                synthesis["build_history_feedback"] = {
                    "analysis_summary": {
                        "builds_analyzed": history_analysis.total_builds_analyzed,
                        "overall_success_rate": history_analysis.overall_success_rate,
                        "time_estimate_accuracy": history_analysis.avg_time_estimate_accuracy,
                        "cost_estimate_accuracy": history_analysis.avg_cost_estimate_accuracy,
                    },
                    "feasibility_adjustment": adjustment,
                    "cost_effectiveness": history_analysis.cost_effectiveness.to_dict(),
                    "recommendations": history_analysis.recommendations,
                    "warnings": history_analysis.warnings,
                }

                # Update overall scores with adjusted feasibility
                if adjustment.get("confidence", 0) > 0.3:
                    adjusted_score = adjustment.get("adjusted_score", normalized_feasibility)
                    synthesis["scores"]["technical_feasibility_adjusted"] = adjusted_score * 10

                    # Update total and recommendation if significant change
                    old_total = synthesis["scores"]["total"]
                    adjustment_amount = (adjusted_score - normalized_feasibility) * 10
                    synthesis["scores"]["total_adjusted"] = old_total + adjustment_amount

            logger.info(
                "Enhanced research with build history: %d builds analyzed",
                history_analysis.total_builds_analyzed,
            )

        return synthesis

    def _get_market_indicators(self, project_type: ProjectType) -> list[str]:
        """Get market indicators for project type.

        Args:
            project_type: ProjectType enum

        Returns:
            List of indicator names
        """
        base_indicators = ["market_size", "growth_rate", "accessibility"]

        type_specific = {
            ProjectType.ECOMMERCE: ["online_retail_growth", "consumer_demand", "payment_adoption"],
            ProjectType.TRADING: ["trading_volume", "market_volatility", "regulatory_clarity"],
            ProjectType.CONTENT: ["content_consumption", "creator_economy", "platform_reach"],
            ProjectType.AUTOMATION: ["automation_adoption", "labor_costs", "tool_availability"],
            ProjectType.OTHER: ["general_demand", "digital_adoption"],
        }

        return base_indicators + type_specific.get(project_type, [])

    def _get_competitive_factors(self, project_type: ProjectType) -> list[str]:
        """Get competitive factors for project type.

        Args:
            project_type: ProjectType enum

        Returns:
            List of factor names
        """
        base_factors = ["competitor_count", "barrier_to_entry", "differentiation"]

        type_specific = {
            ProjectType.ECOMMERCE: ["fulfillment_competition", "pricing_pressure", "brand_loyalty"],
            ProjectType.TRADING: ["platform_competition", "api_availability", "cost_competition"],
            ProjectType.CONTENT: ["creator_competition", "platform_lock_in", "audience_attention"],
            ProjectType.AUTOMATION: ["tool_competition", "integration_barriers", "vendor_lock_in"],
            ProjectType.OTHER: ["general_competition"],
        }

        return base_factors + type_specific.get(project_type, [])

    def _get_feasibility_parameters(self, project_type: ProjectType) -> list[str]:
        """Get feasibility parameters for project type.

        Args:
            project_type: ProjectType enum

        Returns:
            List of parameter names
        """
        base_parameters = ["technical_complexity", "resource_availability", "time_to_market"]

        type_specific = {
            ProjectType.ECOMMERCE: [
                "payment_integration",
                "inventory_management",
                "shipping_logistics",
            ],
            ProjectType.TRADING: ["api_reliability", "data_quality", "latency_requirements"],
            ProjectType.CONTENT: ["content_delivery", "user_experience", "scalability"],
            ProjectType.AUTOMATION: ["integration_complexity", "error_handling", "monitoring"],
            ProjectType.OTHER: ["general_feasibility"],
        }

        return base_parameters + type_specific.get(project_type, [])

    def _build_market_data(self, parsed_idea: ParsedIdea) -> dict[str, Any]:
        """Build market evaluation data from parsed idea.

        Args:
            parsed_idea: ParsedIdea with project details

        Returns:
            Dictionary of evaluation data
        """
        # Base scores derived from idea analysis
        data = {
            "market_size": 1 if len(parsed_idea.raw_requirements) >= 3 else 0,
            "growth_rate": 1 if parsed_idea.confidence_score > 0.7 else 0,
            "accessibility": 1,
        }

        # Project type specific adjustments
        if parsed_idea.detected_project_type == ProjectType.ECOMMERCE:
            data.update(
                {
                    "online_retail_growth": 1,
                    "consumer_demand": 1 if "product" in parsed_idea.description.lower() else 0,
                    "payment_adoption": 1,
                }
            )
        elif parsed_idea.detected_project_type == ProjectType.TRADING:
            data.update(
                {
                    "trading_volume": 1,
                    "market_volatility": 1,
                    "regulatory_clarity": 0,  # Conservative default
                }
            )

        return data

    def _build_competitive_data(self, parsed_idea: ParsedIdea) -> dict[str, Any]:
        """Build competitive evaluation data from parsed idea.

        Args:
            parsed_idea: ParsedIdea with project details

        Returns:
            Dictionary of evaluation data
        """
        data = {
            "competitor_count": 1,
            "barrier_to_entry": 1 if len(parsed_idea.dependencies) > 2 else 0,
            "differentiation": 1 if parsed_idea.confidence_score > 0.8 else 0,
        }

        return data

    def _build_feasibility_data(self, parsed_idea: ParsedIdea) -> dict[str, Any]:
        """Build feasibility evaluation data from parsed idea.

        Args:
            parsed_idea: ParsedIdea with project details

        Returns:
            Dictionary of evaluation data
        """
        # Risk-based complexity assessment
        risk_complexity = {
            "high": 0,
            "medium": 1,
            "low": 1,
        }

        data = {
            "technical_complexity": risk_complexity.get(parsed_idea.risk_profile.value, 1),
            "resource_availability": 1,
            "time_to_market": 1 if len(parsed_idea.raw_requirements) <= 5 else 0,
        }

        return data

    def _synthesize_research(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> dict[str, Any]:
        """Synthesize research from all completed phases.

        Args:
            session: BootstrapSession with completed phases
            parsed_idea: ParsedIdea with project details

        Returns:
            Synthesized research findings
        """
        market_data = session.market_research.data
        competitive_data = session.competitive_analysis.data
        feasibility_data = session.technical_feasibility.data

        # Calculate overall scores
        market_score = market_data.get("attractiveness_score", 0)
        competitive_score = competitive_data.get("intensity_score", 0)
        feasibility_score = feasibility_data.get("feasibility_score", 0)

        # Determine overall recommendation
        total_score = market_score + competitive_score + feasibility_score
        max_possible = 10  # Approximate max from frameworks

        if total_score >= max_possible * 0.7:
            recommendation = "proceed"
            confidence = "high"
        elif total_score >= max_possible * 0.4:
            recommendation = "proceed_with_caution"
            confidence = "medium"
        else:
            recommendation = "reconsider"
            confidence = "low"

        synthesis = {
            "project_title": parsed_idea.title,
            "project_type": parsed_idea.detected_project_type.value,
            "overall_recommendation": recommendation,
            "confidence_level": confidence,
            "scores": {
                "market_attractiveness": market_score,
                "competitive_intensity": competitive_score,
                "technical_feasibility": feasibility_score,
                "total": total_score,
            },
            "risk_assessment": parsed_idea.risk_profile.value,
            "key_dependencies": parsed_idea.dependencies,
            "requirements_count": len(parsed_idea.raw_requirements),
            "research_phases_completed": len(session.get_completed_phases()),
            "parallel_execution": session.parallel_execution_used,
        }

        # Add research state summary if tracking is enabled
        if self._state_tracker:
            synthesis["research_state"] = self._state_tracker.get_session_summary()

        # Add pattern recommendations from cross-project learning
        if self._pattern_cache or self._history_analyzer:
            project_context = {
                "project_type": parsed_idea.detected_project_type.value,
                "keywords": parsed_idea.dependencies + [parsed_idea.title.lower()],
                "requirements": parsed_idea.raw_requirements,
            }
            pattern_recommendations = self.get_pattern_recommendations(project_context)
            if pattern_recommendations:
                synthesis["pattern_recommendations"] = pattern_recommendations[:5]

        # Add build history feedback if analyzer is available
        if self._build_history_analyzer:
            try:
                history_feedback = self._build_history_analyzer.analyze(
                    project_type=parsed_idea.detected_project_type.value,
                    tech_stack=parsed_idea.dependencies,
                )
                if history_feedback.total_builds_analyzed > 0:
                    synthesis["build_history_insights"] = {
                        "builds_analyzed": history_feedback.total_builds_analyzed,
                        "success_rate": history_feedback.overall_success_rate,
                        "time_accuracy": history_feedback.avg_time_estimate_accuracy,
                        "recommendations": history_feedback.recommendations[:3],
                        "warnings": history_feedback.warnings[:2],
                    }
            except Exception as e:
                logger.warning(f"Could not add build history feedback: {e}")

        return synthesis

    def get_bootstrap_session(self, session_id: str) -> Optional[BootstrapSession]:
        """Get a bootstrap session by ID.

        Args:
            session_id: Session ID

        Returns:
            BootstrapSession or None if not found
        """
        return self.bootstrap_sessions.get(session_id)

    def get_cached_session(self, parsed_idea: ParsedIdea) -> Optional[BootstrapSession]:
        """Get cached session for a parsed idea if available.

        Args:
            parsed_idea: ParsedIdea to look up

        Returns:
            Cached BootstrapSession or None
        """
        idea_hash = generate_idea_hash(
            parsed_idea.title,
            parsed_idea.description,
            parsed_idea.detected_project_type.value,
        )
        return self._cache.get(idea_hash)

    def invalidate_cache(self, parsed_idea: ParsedIdea) -> bool:
        """Invalidate cached session for a parsed idea.

        Args:
            parsed_idea: ParsedIdea to invalidate

        Returns:
            True if cache was invalidated
        """
        idea_hash = generate_idea_hash(
            parsed_idea.title,
            parsed_idea.description,
            parsed_idea.detected_project_type.value,
        )
        return self._cache.invalidate(idea_hash)
