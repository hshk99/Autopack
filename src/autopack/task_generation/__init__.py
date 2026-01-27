"""Task Generation Module.

Provides data-driven task prioritization and autonomous improvement suggestion
capabilities for the Autopack self-improvement loop.

Components:
- PriorityEngine: Prioritizes tasks based on historical success data
- InsightToTaskGenerator: Generates improvement suggestions from telemetry insights
"""

from __future__ import annotations

from .priority_engine import PriorityEngine

__all__ = ["PriorityEngine"]
