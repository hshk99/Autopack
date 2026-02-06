"""
AI Innovation Monitor - Automatic scanning and assessment of AI innovations.

Scans AI news sources, assesses relevance to Autopack, and notifies
when innovations have >10% improvement potential.

Token-efficient architecture:
- Stage 1: Rule-based filtering (0 tokens)
- Stage 2: LLM assessment only for top candidates
"""

from .models import (
    RawInnovation,
    ScoredInnovation,
    ImprovementAssessment,
    SourceType,
)
from .keyword_filter import KeywordFilter, KeywordFilterConfig
from .relevance_scorer import RelevanceScorer, ScoringWeights
from .deduplicator import Deduplicator
from .email_notifier import EmailNotifier
from .orchestrator import InnovationMonitorOrchestrator

__all__ = [
    "RawInnovation",
    "ScoredInnovation",
    "ImprovementAssessment",
    "SourceType",
    "KeywordFilter",
    "KeywordFilterConfig",
    "RelevanceScorer",
    "ScoringWeights",
    "Deduplicator",
    "EmailNotifier",
    "InnovationMonitorOrchestrator",
]
