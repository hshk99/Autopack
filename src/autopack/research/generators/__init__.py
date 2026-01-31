"""Artifact generators for research projects.

Provides generators that produce deployment and configuration artifacts
based on research outputs like TechStackProposal.

Supports multiple CI/CD platforms:
- GitHub Actions
- GitLab CI/CD
- Jenkins Declarative Pipelines
"""

from autopack.research.generators.cicd_generator import (
    CICDAnalysisResult, CICDAnalyzer, CICDPlatform, CICDWorkflowGenerator,
    DeploymentGuidance, DeploymentTarget, GitLabCIGenerator,
    JenkinsPipelineGenerator)

__all__ = [
    "CICDAnalysisResult",
    "CICDAnalyzer",
    "CICDPlatform",
    "CICDWorkflowGenerator",
    "DeploymentGuidance",
    "DeploymentTarget",
    "GitLabCIGenerator",
    "JenkinsPipelineGenerator",
]
