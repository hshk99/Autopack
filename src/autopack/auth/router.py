"""Authentication API router (JWT RS256).

BUILD-146 P12 Phase 5: Migrated from backend.api.auth to consolidate
auth under autopack namespace.

SOT Contract Endpoints:
- POST /api/auth/register
- POST /api/auth/login
- GET /api/auth/me
- GET /api/auth/.well-known/jwks.json
- GET /api/auth/key-status
"""
import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .security import (
    create_access_token,
    decode_access_token,
    generate_jwk_from_public_pem,
    ensure_keys,
    hash_password,
    verify_password,
)
from .models import User
from .schemas import Token, UserCreate, UserResponse
from autopack.database import get_db
from autopack.config import settings  # BUILD-146 P12 Phase 5

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


def get_password_hash(password: str) -> str:
    """Expose hashing for tests and other modules."""
    return hash_password(password)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Return user if credentials are valid, otherwise None."""
    user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


@router.get("/.well-known/jwks.json")
async def jwks():
    """
    Expose the JWKS for token verification by external services.

    SOT endpoint: /api/auth/.well-known/jwks.json
    """
    ensure_keys()
    kid_source = settings.jwt_public_key.encode("utf-8")
    jwk = generate_jwk_from_public_pem(settings.jwt_public_key, kid_hex=hashlib.sha256(kid_source).hexdigest())
    return {"keys": [jwk]}


@router.get("/key-status")
async def key_status():
    """
    Return whether JWT keys are loaded and their source (env vs generated).

    SOT endpoint: /api/auth/key-status
    """
    try:
        ensure_keys()
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail="JWT keys not configured or invalid") from exc

    source = "env" if settings.jwt_private_key and settings.jwt_public_key else "generated"
    return {"keys_loaded": True, "source": source}


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
async def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Register a new user with unique username and email.

    SOT endpoint: /api/auth/register
    """
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=Token,
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """
    Validate credentials and issue an access token.

    SOT endpoint: /api/auth/login
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"user_id": user.id, "username": user.username})
    return Token(access_token=token, token_type="bearer")


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve user from Authorization header (Bearer token).

    Used by /api/auth/me and other protected endpoints.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    payload = decode_access_token(parts[1])
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    current_user: User = Depends(get_current_user),
):
    """
    Return the current authenticated user.

    SOT endpoint: /api/auth/me
    """
    return current_user
