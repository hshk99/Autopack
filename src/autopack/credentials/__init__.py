"""Provider credential health visibility and rotation tracking.

Implements gap analysis items:
- 6.8: non-secret credential status health endpoint
- 6.4: secrets rotation + scoped credentials + least privilege

Shows whether credentials are present/missing/validated/expired without leaking secret values.
Tracks credential lifecycle, rotation schedules, and scope-based access control.
"""

from .health import CredentialHealthService
from .models import CredentialStatus, ProviderCredential
from .rotation import (DEFAULT_ROTATION_POLICIES, CredentialEnvironment,
                       CredentialRecord, CredentialRotationTracker,
                       CredentialScope, RotationPolicy)

__all__ = [
    # Health visibility (6.8)
    "CredentialStatus",
    "ProviderCredential",
    "CredentialHealthService",
    # Rotation tracking (6.4)
    "CredentialScope",
    "CredentialEnvironment",
    "RotationPolicy",
    "CredentialRecord",
    "CredentialRotationTracker",
    "DEFAULT_ROTATION_POLICIES",
]
