"""Authentication package for Autopack (JWT RS256).

BUILD-146 P12 Phase 5: Consolidates auth functionality from backend.api.auth
into autopack namespace.

Exports:
- router: FastAPI router with prefix /api/auth
- User: SQLAlchemy model using autopack.database.Base
- All Pydantic schemas (Token, UserCreate, UserResponse, etc.)
- Security utilities (hash_password, verify_password, etc.)
"""

from .router import router
from .models import User
from .schemas import (
    Token,
    UserCreate,
    UserResponse,
    UserLogin,
    TokenData,
    UserInDB,
    MessageResponse,
)
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    ensure_keys,
    generate_jwk_from_public_pem,
)

__all__ = [
    # Router
    "router",
    # Model
    "User",
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
]
