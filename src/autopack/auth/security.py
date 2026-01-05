"""JWT authentication security utilities (RS256).

BUILD-146 P12 Phase 5: Migrated from backend.core.security to consolidate
auth under autopack namespace.
"""

import os
import bcrypt
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt, JWTError

# Import settings from autopack config (BUILD-146 P12 Phase 5)
from autopack.config import settings


def _normalize_pem(pem: str) -> str:
    """
    Normalize PEM input:
    - Convert literal \n to newlines
    - Trim whitespace/blank lines
    - Reassemble header/body/footer with single newlines
    """
    if not pem:
        return pem
    text = pem.replace("\\n", "\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    if lines[0].startswith("-----BEGIN") and lines[-1].startswith("-----END"):
        header, footer = lines[0], lines[-1]
        body = lines[1:-1]
        return "\n".join([header, *body, footer])
    return "\n".join(lines)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt, ensuring it is not longer than 72 bytes.
    """
    return bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash, ensuring it is not longer than 72 bytes.
    """
    return bcrypt.checkpw(plain_password[:72].encode("utf-8"), hashed_password.encode("utf-8"))


def ensure_keys() -> None:
    """
    Ensure RSA keys are configured; generate ephemeral keys in dev/test if absent.
    """
    if settings.jwt_private_key and settings.jwt_public_key:
        try:
            priv_norm = _normalize_pem(settings.jwt_private_key)
            pub_norm = _normalize_pem(settings.jwt_public_key)
            serialization.load_pem_private_key(priv_norm.encode("utf-8"), password=None)
            serialization.load_pem_public_key(pub_norm.encode("utf-8"))
            settings.jwt_private_key = priv_norm
            settings.jwt_public_key = pub_norm
            return
        except Exception as exc:  # pragma: no cover - defensive
            # In tests, fall back to generated keys; otherwise fail fast.
            if os.getenv("PYTEST_CURRENT_TEST"):
                pass
            else:
                raise RuntimeError("Invalid JWT key configuration") from exc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    settings.jwt_private_key = priv_pem
    settings.jwt_public_key = pub_pem


def generate_jwk_from_public_pem(public_pem: str, kid_hex: str | None = None) -> Dict[str, str]:
    """
    Convert a PEM public key to a JWK dict.
    """
    public_key = serialization.load_pem_public_key(_normalize_pem(public_pem).encode("utf-8"))
    numbers = public_key.public_numbers()
    n = (
        base64.urlsafe_b64encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode("utf-8")
    )
    e = (
        base64.urlsafe_b64encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode("utf-8")
    )
    kid = kid_hex or ""
    return {
        "kty": "RSA",
        "alg": settings.jwt_algorithm,
        "use": "sig",
        "n": n,
        "e": e,
        "kid": kid,
    }


def create_access_token(
    data: Dict[str, Any],
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create an RS256-signed JWT with standard claims.
    """
    ensure_keys()
    ttl_minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    to_encode = {
        **data,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(
        to_encode,
        settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate and decode an RS256-signed JWT.
    """
    ensure_keys()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        return payload
    except JWTError:
        return None
