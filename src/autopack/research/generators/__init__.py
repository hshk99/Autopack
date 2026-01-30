"""Artifact generators for research projects.

Provides generators that produce deployment and configuration artifacts
based on research outputs like TechStackProposal.
"""

from autopack.research.generators.cicd_generator import CICDWorkflowGenerator

__all__ = [
    "CICDWorkflowGenerator",
]
