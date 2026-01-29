"""Research Orchestrator for coordinating research sessions.

This module provides the ResearchOrchestrator class which coordinates research
workflows including traditional sessions and bootstrap sessions with parallel
execution and 24-hour caching.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from autopack.research.frameworks.competitive_intensity import CompetitiveIntensity
from autopack.research.frameworks.market_attractiveness import MarketAttractiveness
from autopack.research.frameworks.product_feasibility import ProductFeasibility
from autopack.research.idea_parser import ParsedIdea, ProjectType
from autopack.research.models.bootstrap_session import (
    BootstrapPhase,
    BootstrapSession,
    generate_idea_hash,
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
    """

    def __init__(self, cache_ttl_hours: int = CACHE_TTL_HOURS):
        """Initialize the ResearchOrchestrator.

        Args:
            cache_ttl_hours: TTL for research cache in hours (default: 24)
        """
        self.sessions: dict[str, ResearchSession] = {}
        self.bootstrap_sessions: dict[str, BootstrapSession] = {}
        self._cache = ResearchCache(ttl_hours=cache_ttl_hours)

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
        """Execute research phases in parallel.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        logger.debug(f"Executing research phases in parallel for session {session.session_id}")

        # Create tasks for parallel execution
        tasks = [
            self._run_market_research(session, parsed_idea),
            self._run_competitive_analysis(session, parsed_idea),
            self._run_technical_feasibility(session, parsed_idea),
        ]

        # Execute all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_research_sequential(
        self,
        session: BootstrapSession,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Execute research phases sequentially.

        Args:
            session: BootstrapSession to update
            parsed_idea: ParsedIdea with project details
        """
        logger.debug(f"Executing research phases sequentially for session {session.session_id}")

        await self._run_market_research(session, parsed_idea)
        await self._run_competitive_analysis(session, parsed_idea)
        await self._run_technical_feasibility(session, parsed_idea)

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
            logger.debug(f"Technical feasibility completed for session {session.session_id}")

        except Exception as e:
            session.mark_phase_failed(phase, [str(e)])
            logger.error(f"Technical feasibility failed for session {session.session_id}: {e}")

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

        return {
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
