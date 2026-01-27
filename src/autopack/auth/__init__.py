"""Authentication package for Autopack (JWT RS256).

BUILD-146 P12 Phase 5: Consolidates auth functionality from backend.api.auth
into autopack namespace.

BUILD-189 Gap 6.8: OAuth credential lifecycle management with refresh handling,
health monitoring, and external action ledger integration.

Exports:
- router: FastAPI router with prefix /api/auth
- oauth_router: FastAPI router with prefix /api/auth/oauth
- User: SQLAlchemy model using autopack.database.Base
- All Pydantic schemas (Token, UserCreate, UserResponse, etc.)
- Security utilities (hash_password, verify_password, etc.)
- OAuth lifecycle management (OAuthCredentialManager, etc.)
"""

from .api_key import generate_api_key, optional_api_key, require_api_key
from .api_key_router import router as api_key_router
from .models import APIKey, User
from .oauth_lifecycle import (
    GITHUB_REFRESH_HANDLER,
    GOOGLE_REFRESH_HANDLER,
    CredentialHealth,
    CredentialStatus,
    OAuthCredential,
    OAuthCredentialManager,
    RefreshAttemptResult,
    RefreshResult,
    create_generic_oauth2_handler,
)
from .oauth_router import router as oauth_router
from .router import router
from .schemas import (
    MessageResponse,
    Token,
    TokenData,
    UserCreate,
    UserInDB,
    UserLogin,
    UserResponse,
)
from .security import (
    create_access_token,
    decode_access_token,
    ensure_keys,
    generate_jwk_from_public_pem,
    hash_password,
    verify_password,
)

__all__ = [
    # Routers
    "router",
    "oauth_router",
    "api_key_router",
    # Models
    "User",
    "APIKey",
    # API Key Auth
    "require_api_key",
    "optional_api_key",
    "generate_api_key",
    # Schemas
    "Token",
    "UserCreate",
    "UserResponse",
    "UserLogin",
    "TokenData",
    "UserInDB",
    "MessageResponse",
    # Security
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "ensure_keys",
    "generate_jwk_from_public_pem",
    # OAuth Lifecycle
    "OAuthCredentialManager",
    "OAuthCredential",
    "CredentialHealth",
    "CredentialStatus",
    "RefreshResult",
    "RefreshAttemptResult",
    "create_generic_oauth2_handler",
    "GITHUB_REFRESH_HANDLER",
    "GOOGLE_REFRESH_HANDLER",
]
