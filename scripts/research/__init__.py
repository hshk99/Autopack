"""
Universal Research Analysis System

A project-agnostic research analysis pipeline that works for any project.

Components:
- ContextAssembler: Builds comprehensive project context from SOT + research
- ResearchAnalyzer: Finds gaps between current state and research
- DecisionEngine: Makes strategic implementation decisions
- DecisionRouter: Routes decisions to appropriate locations

Usage:
    from scripts.research.run_universal_analysis import UniversalResearchAnalysisPipeline

    pipeline = UniversalResearchAnalysisPipeline('file-organizer-app-v1')
    results = pipeline.run()
"""

from scripts.research.data_structures import (
    ProjectContext,
    ResearchGap,
    OpportunityAnalysis,
    ImplementationDecision,
    DecisionReport,
    ResearchType,
    GapType,
    Priority,
    Effort,
    DecisionType
)

from scripts.research.context_assembler import ContextAssembler
from scripts.research.research_analyzer import ResearchAnalyzer
from scripts.research.decision_engine import DecisionEngine, DecisionRouter
from scripts.research.run_universal_analysis import UniversalResearchAnalysisPipeline

__all__ = [
    # Data structures
    'ProjectContext',
    'ResearchGap',
    'OpportunityAnalysis',
    'ImplementationDecision',
    'DecisionReport',
    'ResearchType',
    'GapType',
    'Priority',
    'Effort',
    'DecisionType',
    # Components
    'ContextAssembler',
    'ResearchAnalyzer',
    'DecisionEngine',
    'DecisionRouter',
    'UniversalResearchAnalysisPipeline'
]
