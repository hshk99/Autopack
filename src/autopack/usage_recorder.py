"""LLM usage tracking for token consumption monitoring"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from .database import Base


class LlmUsageEvent(Base):
    """Record of LLM token usage for a single API call"""

    __tablename__ = "llm_usage_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)  # openai, anthropic, google_gemini, glm
    model = Column(String, nullable=False, index=True)  # gpt-4o, claude-3-5-sonnet, etc.
    run_id = Column(String, nullable=True, index=True)  # null for global aux runs
    phase_id = Column(String, nullable=True)
    role = Column(String, nullable=False)  # builder, auditor, agent:planner, etc.
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


@dataclass
class UsageEventData:
    """Dataclass for passing usage event data"""

    provider: str
    model: str
    run_id: Optional[str]
    phase_id: Optional[str]
    role: str
    prompt_tokens: int
    completion_tokens: int


def record_usage(db: Session, event: UsageEventData) -> LlmUsageEvent:
    """
    Record a single LLM usage event.

    Args:
        db: Database session
        event: Usage event data

    Returns:
        Created LlmUsageEvent record
    """
    usage_record = LlmUsageEvent(
        provider=event.provider,
        model=event.model,
        run_id=event.run_id,
        phase_id=event.phase_id,
        role=event.role,
        prompt_tokens=event.prompt_tokens,
        completion_tokens=event.completion_tokens,
        created_at=datetime.utcnow(),
    )

    db.add(usage_record)
    db.commit()
    db.refresh(usage_record)

    return usage_record
