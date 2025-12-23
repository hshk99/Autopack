# Authentication System Documentation

## Overview

Autopack includes a comprehensive JWT-based authentication system using RS256 asymmetric signing, OAuth2 Password Bearer flow, and bcrypt password hashing. The authentication system provides secure user registration, login, and protected endpoint access.

## Architecture

### Components

1. **User Model** ([src/backend/models/user.py](src/backend/models/user.py))
   - SQLAlchemy model for user data
   - Fields: id, username, email, hashed_password, is_active, is_superuser, created_at, updated_at
   - Automatic timestamp management with timezone-aware UTC datetimes

2. **Security Module** ([src/backend/core/security.py](src/backend/core/security.py))
   - Password hashing/verification using bcrypt
   - JWT token creation/validation using RS256
   - RSA key management with auto-generation for dev/test environments
   - JWKS generation for external token verification

3. **Authentication API** ([src/backend/api/auth.py](src/backend/api/auth.py))
   - User registration endpoint
   - OAuth2 password flow login endpoint
   - Protected user profile endpoint
   - JWKS endpoint for token verification
   - Key status endpoint for configuration monitoring

4. **Pydantic Schemas** ([src/backend/schemas/user.py](src/backend/schemas/user.py))
   - Request/response validation models
   - UserCreate, UserResponse, Token, UserLogin, etc.

## API Endpoints

### Public Endpoints

#### POST /api/auth/register
Register a new user account.

**Request Body:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePassword123!"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-12-17T12:00:00Z",
  "updated_at": "2025-12-17T12:00:00Z"
}
```

**Validation Rules:**
- Username: 3-50 characters, unique
- Email: Valid email format, unique
- Password: 8-100 characters (truncated to 72 bytes for bcrypt)

**Error Responses:**
- 400: Username or email already registered
- 422: Validation error (invalid format, too short/long)

#### POST /api/auth/login
Authenticate and receive an access token.

**Request (Form Data):**
```
username=john_doe
password=SecurePassword123!
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "bearer"
}
```

**Error Responses:**
- 401: Incorrect username or password
- 422: Missing credentials

#### GET /api/auth/.well-known/jwks.json
Retrieve JSON Web Key Set for token verification.

**Response (200 OK):**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "n": "base64-encoded-modulus",
      "e": "base64-encoded-exponent",
      "kid": "sha256-hash-of-public-key"
    }
  ]
}
```

#### GET /api/auth/key-status
Check JWT key configuration status.

**Response (200 OK):**
```json
{
  "keys_loaded": true,
  "source": "env"  // or "generated"
}
```

### Protected Endpoints

#### GET /api/auth/me
Retrieve current authenticated user profile.

**Request Headers:**
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

**Response (200 OK):**
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-12-17T12:00:00Z",
  "updated_at": "2025-12-17T12:00:00Z"
}
```

**Error Responses:**
- 401: Not authenticated / Invalid token
- 400: Inactive user

## Security Features

### Password Security

- **Bcrypt Hashing**: Industry-standard password hashing with automatic salt generation
- **72-Byte Truncation**: Passwords truncated to 72 bytes (bcrypt limitation) during hashing and verification
- **Strong Password Requirements**: Minimum 8 characters enforced at validation layer

### JWT Token Security

- **RS256 Algorithm**: Asymmetric signing using RSA 2048-bit keys
- **Standard Claims**: Includes `iss` (issuer), `aud` (audience), `iat` (issued at), `exp` (expiration)
- **Token Expiration**: Configurable TTL (default: 30 minutes via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **No Token Refresh**: Stateless design - clients must re-authenticate after expiration

### Key Management

**Production (Recommended):**
```bash
# Generate RSA key pair
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem

# Set environment variables
export JWT_PRIVATE_KEY="$(cat private_key.pem)"
export JWT_PUBLIC_KEY="$(cat public_key.pem)"
```

**Development/Testing:**
- Keys auto-generated if not provided
- Ephemeral keys (not persisted to disk)
- Warning: Tokens invalid after server restart

## Environment Variables

### Required for Production

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string | `postgresql://user:pass@localhost:5432/autopack` |
| `JWT_PRIVATE_KEY` | RSA private key (PEM format) | `-----BEGIN PRIVATE KEY-----\n...` |
| `JWT_PUBLIC_KEY` | RSA public key (PEM format) | `-----BEGIN PUBLIC KEY-----\n...` |
| `SECRET_KEY` | FastAPI secret key | `your-secret-key-here` |

### Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL in minutes | `30` |
| `JWT_ALGORITHM` | JWT signing algorithm | `RS256` |
| `JWT_ISSUER` | Token issuer claim | `autopack` |
| `JWT_AUDIENCE` | Token audience claim | `autopack-api` |

### Development Example

```bash
# Minimal development setup (SQLite + auto-generated keys)
export DATABASE_URL="sqlite:///./autopack.db"
export SECRET_KEY="dev-secret-key"
python -m uvicorn autopack.main:app --reload
```

### Production Example

```bash
# Full production setup (PostgreSQL + explicit keys)
export DATABASE_URL="postgresql://autopack:password@localhost:5432/autopack"
export JWT_PRIVATE_KEY="$(cat /path/to/private_key.pem)"
export JWT_PUBLIC_KEY="$(cat /path/to/public_key.pem)"
export SECRET_KEY="$(openssl rand -hex 32)"
export ACCESS_TOKEN_EXPIRE_MINUTES="60"
python -m uvicorn autopack.main:app --host 0.0.0.0 --port 8000
```

## Database Setup

The authentication system requires the `users` table. Tables are created automatically on first startup via the `init_db()` function.

**Manual Initialization:**
```python
from backend.database import init_db
init_db()
```

**User Table Schema:**
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_superuser BOOLEAN DEFAULT FALSE NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
```

## Usage Examples

### Python Client Example

```python
import requests

# 1. Register a new user
response = requests.post(
    "http://localhost:8000/api/auth/register",
    json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "SecurePass123!"
    }
)
print(response.json())  # User profile

# 2. Login to get access token
response = requests.post(
    "http://localhost:8000/api/auth/login",
    data={
        "username": "alice",
        "password": "SecurePass123!"
    }
)
token = response.json()["access_token"]
print(f"Token: {token}")

# 3. Access protected endpoint
response = requests.get(
    "http://localhost:8000/api/auth/me",
    headers={"Authorization": f"Bearer {token}"}
)
print(response.json())  # User profile
```

### JavaScript/TypeScript Example

```typescript
// 1. Register
const registerResponse = await fetch('http://localhost:8000/api/auth/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'alice',
    email: 'alice@example.com',
    password: 'SecurePass123!'
  })
});
const user = await registerResponse.json();

// 2. Login
const loginResponse = await fetch('http://localhost:8000/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({
    username: 'alice',
    password: 'SecurePass123!'
  })
});
const { access_token } = await loginResponse.json();

// 3. Use token for authenticated requests
const meResponse = await fetch('http://localhost:8000/api/auth/me', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});
const profile = await meResponse.json();
```

### cURL Examples

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"SecurePass123!"}'

# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice&password=SecurePass123!"

# Get profile (replace TOKEN with actual token)
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer TOKEN"
```

## Testing

The authentication system includes comprehensive test coverage (29 tests) covering:

- Password hashing and verification
- JWT token creation and validation
- User registration (success, duplicates, validation)
- User login (success, wrong password, missing credentials)
- Protected endpoint access (valid token, no token, invalid token)
- JWKS endpoint functionality
- End-to-end authentication flows

**Run Authentication Tests:**
```bash
cd /path/to/Autopack
PYTHONPATH=src python -m pytest src/backend/tests/test_auth.py -v
```

**Expected Output:**
```
29 passed in 13.90s
```

## Integration with Existing Endpoints

To protect any endpoint with authentication, use the `get_current_user` dependency:

```python
from fastapi import APIRouter, Depends
from backend.api.auth import get_current_user
from backend.models.user import User

router = APIRouter()

@router.get("/protected-resource")
async def protected_endpoint(current_user: User = Depends(get_current_user)):
    # current_user is automatically populated from Bearer token
    return {
        "message": f"Hello, {current_user.username}!",
        "user_id": current_user.id
    }
```

## Security Best Practices

### Production Deployment

1. **Use Environment Variables**: Never hardcode secrets in source code
2. **Persistent Keys**: Use externally managed RSA keys (not auto-generated)
3. **HTTPS Only**: Always serve authentication endpoints over HTTPS
4. **Database Security**: Use strong database passwords and connection encryption
5. **Token Expiration**: Keep token TTL short (30-60 minutes recommended)
6. **Rate Limiting**: Implement rate limiting on login endpoint to prevent brute force
7. **Password Complexity**: Enforce strong password requirements in client validation

### Key Rotation

To rotate JWT signing keys:

1. Generate new RSA key pair
2. Add new public key to JWKS endpoint (support both keys temporarily)
3. Update `JWT_PRIVATE_KEY` to use new private key (new tokens signed with new key)
4. Wait for old tokens to expire (ACCESS_TOKEN_EXPIRE_MINUTES)
5. Remove old public key from JWKS endpoint

### Monitoring

Monitor these metrics in production:

- Failed login attempts (potential brute force attacks)
- Token validation failures (potential token tampering)
- Key status endpoint (`/api/auth/key-status`) should show `"source": "env"`
- Database connection health

## Troubleshooting

### Common Issues

**Problem**: "JWT keys not configured or invalid"
- **Solution**: Ensure `JWT_PRIVATE_KEY` and `JWT_PUBLIC_KEY` are valid PEM-formatted RSA keys

**Problem**: "Not authenticated"
- **Solution**: Check that `Authorization` header is present with format `Bearer <token>`

**Problem**: "Could not validate credentials"
- **Solution**: Token may be expired, invalid, or signed with different keys. Re-authenticate.

**Problem**: "Inactive user"
- **Solution**: User's `is_active` field is set to `False`. Update database or contact admin.

**Problem**: "Username already registered"
- **Solution**: Choose a different username or use login if account already exists

### Debug Mode

Enable debug logging to troubleshoot authentication issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Files Reference

| File | Purpose |
|------|---------|
| [src/backend/models/user.py](src/backend/models/user.py) | User SQLAlchemy model |
| [src/backend/schemas/user.py](src/backend/schemas/user.py) | Pydantic validation schemas |
| [src/backend/api/auth.py](src/backend/api/auth.py) | Authentication API endpoints |
| [src/backend/core/security.py](src/backend/core/security.py) | Security utilities (hashing, JWT) |
| [src/backend/core/config.py](src/backend/core/config.py) | Configuration settings |
| [src/backend/database.py](src/backend/database.py) | Database session management |
| [src/backend/tests/test_auth.py](src/backend/tests/test_auth.py) | Authentication test suite |

## Future Enhancements

Potential improvements for future releases:

1. **Token Refresh**: Add refresh token support for long-lived sessions
2. **OAuth2 Providers**: Support Google/GitHub OAuth authentication
3. **2FA/MFA**: Add two-factor authentication support
4. **Password Reset**: Email-based password reset flow
5. **Account Verification**: Email verification for new accounts
6. **Session Management**: Add ability to revoke tokens/sessions
7. **Audit Logging**: Log all authentication events for security monitoring
8. **Role-Based Access Control (RBAC)**: Expand beyond `is_superuser` flag

## Support

For questions or issues with the authentication system:

1. Review this documentation
2. Check the test suite for usage examples ([src/backend/tests/test_auth.py](src/backend/tests/test_auth.py))
3. Review API endpoint code ([src/backend/api/auth.py](src/backend/api/auth.py))
4. Open an issue in the project repository
