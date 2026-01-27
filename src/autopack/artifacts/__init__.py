"""Artifact retention and PII/media governance.

Implements gap analysis item 6.6:
- Artifact retention windows by class
- PII/media redaction and scrubbing
- Browser artifact handling (screenshots, HAR logs)
"""

from .redaction import DEFAULT_REDACTION_PATTERNS, ArtifactRedactor, RedactionPattern
from .retention import (
    DEFAULT_RETENTION_POLICIES,
    ArtifactClass,
    ArtifactMetadata,
    ArtifactRetentionManager,
    RetentionPolicy,
)

__all__ = [
    "ArtifactClass",
    "RetentionPolicy",
    "ArtifactMetadata",
    "ArtifactRetentionManager",
    "DEFAULT_RETENTION_POLICIES",
    "RedactionPattern",
    "ArtifactRedactor",
    "DEFAULT_REDACTION_PATTERNS",
]
