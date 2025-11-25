"""Service for querying and aggregating LLM usage data"""

from datetime import datetime, timedelta
from typing import Dict, List, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .usage_recorder import LlmUsageEvent


class UsageService:
    """Service for querying LLM usage statistics"""

    def __init__(self, db: Session):
        self.db = db

    def _get_time_window_start(self, period: Literal["day", "week", "month"]) -> datetime:
        """Calculate start datetime for the given period"""
        now = datetime.utcnow()

        if period == "day":
            return now - timedelta(days=1)
        elif period == "week":
            return now - timedelta(weeks=1)
        elif period == "month":
            return now - timedelta(days=30)
        else:
            raise ValueError(f"Invalid period: {period}")

    def get_provider_usage_summary(
        self, period: Literal["day", "week", "month"] = "week"
    ) -> Dict[str, Dict[str, int]]:
        """
        Get token usage aggregated by provider for the given period.

        Returns:
            Dict mapping provider to usage stats:
            {
                "openai": {
                    "prompt_tokens": 1500000,
                    "completion_tokens": 500000,
                    "total_tokens": 2000000
                }
            }
        """
        start_time = self._get_time_window_start(period)

        # Query aggregated by provider
        results = (
            self.db.query(
                LlmUsageEvent.provider,
                func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
                func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
            )
            .filter(LlmUsageEvent.created_at >= start_time)
            .group_by(LlmUsageEvent.provider)
            .all()
        )

        summary = {}
        for provider, prompt_tokens, completion_tokens in results:
            summary[provider] = {
                "prompt_tokens": prompt_tokens or 0,
                "completion_tokens": completion_tokens or 0,
                "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
            }

        return summary

    def get_model_usage_summary(
        self, period: Literal["day", "week", "month"] = "week"
    ) -> List[Dict]:
        """
        Get token usage aggregated by model for the given period.

        Returns:
            List of dicts with model usage stats:
            [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "prompt_tokens": 800000,
                    "completion_tokens": 300000,
                    "total_tokens": 1100000
                }
            ]
        """
        start_time = self._get_time_window_start(period)

        # Query aggregated by provider and model
        results = (
            self.db.query(
                LlmUsageEvent.provider,
                LlmUsageEvent.model,
                func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
                func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
            )
            .filter(LlmUsageEvent.created_at >= start_time)
            .group_by(LlmUsageEvent.provider, LlmUsageEvent.model)
            .all()
        )

        summary = []
        for provider, model, prompt_tokens, completion_tokens in results:
            summary.append(
                {
                    "provider": provider,
                    "model": model,
                    "prompt_tokens": prompt_tokens or 0,
                    "completion_tokens": completion_tokens or 0,
                    "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0),
                }
            )

        return summary

    def get_run_usage(self, run_id: str) -> Dict[str, int]:
        """
        Get total token usage for a specific run.

        Returns:
            Dict with token counts:
            {
                "prompt_tokens": 150000,
                "completion_tokens": 50000,
                "total_tokens": 200000
            }
        """
        result = (
            self.db.query(
                func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
                func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
            )
            .filter(LlmUsageEvent.run_id == run_id)
            .first()
        )

        prompt_tokens = result[0] or 0
        completion_tokens = result[1] or 0

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def get_phase_usage(self, run_id: str, phase_id: str) -> Dict[str, int]:
        """
        Get total token usage for a specific phase.

        Returns:
            Dict with token counts:
            {
                "prompt_tokens": 10000,
                "completion_tokens": 3000,
                "total_tokens": 13000
            }
        """
        result = (
            self.db.query(
                func.sum(LlmUsageEvent.prompt_tokens).label("prompt_tokens"),
                func.sum(LlmUsageEvent.completion_tokens).label("completion_tokens"),
            )
            .filter(LlmUsageEvent.run_id == run_id, LlmUsageEvent.phase_id == phase_id)
            .first()
        )

        prompt_tokens = result[0] or 0
        completion_tokens = result[1] or 0

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
