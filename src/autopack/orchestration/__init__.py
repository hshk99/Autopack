"""Orchestration package for Autopack.

Provides orchestration capabilities for both single and multi-project execution.
"""

from .multi_project import (
    ExecutionStrategy,
    MultiProjectConfig,
    MultiProjectOrchestrator,
    ProjectObjective,
    ProjectResult,
    ResourceManager,
    ResourceSnapshot,
)

__all__ = [
    "ExecutionStrategy",
    "MultiProjectConfig",
    "MultiProjectOrchestrator",
    "ProjectObjective",
    "ProjectResult",
    "ResourceManager",
    "ResourceSnapshot",
]
