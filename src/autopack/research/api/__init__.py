"""Research API module for FastAPI integration.

IMP-RES-006: Research API with gated bootstrap mode.

API Modes:
- DISABLED: All endpoints return 503 (production default)
- BOOTSTRAP_ONLY: Only bootstrap endpoints accessible
- FULL: All endpoints accessible (development only)
"""

from .router import (BootstrapRequest, BootstrapResponse,
                     BootstrapStatusResponse, DraftAnchorResponse,
                     ResearchAPIMode, router)
from .schemas import (CreateResearchSession, ResearchSession,
                      UpdateResearchSession)

__all__ = [
    "router",
    "ResearchAPIMode",
    "ResearchSession",
    "CreateResearchSession",
    "UpdateResearchSession",
    "BootstrapRequest",
    "BootstrapResponse",
    "BootstrapStatusResponse",
    "DraftAnchorResponse",
]
