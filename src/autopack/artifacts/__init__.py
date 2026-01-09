"""Artifact retention and PII/media governance.

Implements gap analysis item 6.6:
- Artifact retention windows by class
- PII/media redaction and scrubbing
- Browser artifact handling (screenshots, HAR logs)
"""

from .retention import (
    ArtifactClass,
    RetentionPolicy,
    ArtifactMetadata,
    ArtifactRetentionManager,
    DEFAULT_RETENTION_POLICIES,
)
from .redaction import (
    RedactionPattern,
    ArtifactRedactor,
    DEFAULT_REDACTION_PATTERNS,
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
