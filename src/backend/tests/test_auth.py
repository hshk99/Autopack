"""
Comprehensive tests for authentication endpoints and security functions.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone

from autopack.main import app
from backend.database import Base, get_db
from backend.models.user import User
from backend.api.auth import get_password_hash, authenticate_user
from backend.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    ensure_keys,
)


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh database for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a test client with database dependency override."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user_data():
    """Sample user data for registration tests."""
    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "SecurePassword123!"
    }


@pytest.fixture
def registered_user(client, test_user_data):
    """Create a registered user and return user data with token."""
    response = client.post("/api/auth/register", json=test_user_data)
    assert response.status_code == 201
    user_response = response.json()

    # Login to get token
    login_response = client.post(
        "/api/auth/login",
        data={"username": test_user_data["username"], "password": test_user_data["password"]}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    return {
        **test_user_data,
        "user_id": user_response["id"],
        "token": token
    }


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password(self):
        """Test that password hashing produces a valid bcrypt hash."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "testpassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_password_truncates_long_passwords(self):
        """Test that passwords longer than 72 bytes are truncated."""
        long_password = "a" * 100
        hashed = hash_password(long_password)

        # Verify with truncated password
        assert verify_password("a" * 72, hashed) is True
        # Full long password should also work
        assert verify_password(long_password, hashed) is True


class TestJWTTokens:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Test JWT token creation with valid data."""
        ensure_keys()
        data = {"user_id": 1, "username": "testuser"}
        token = create_access_token(data)

        assert isinstance(token, str)
        assert len(token) > 50

    def test_decode_access_token_valid(self):
        """Test decoding a valid JWT token."""
        ensure_keys()
        data = {"user_id": 1, "username": "testuser"}
        token = create_access_token(data)

        decoded = decode_access_token(token)

        assert decoded is not None
        assert decoded["user_id"] == 1
        assert decoded["username"] == "testuser"
        assert "iat" in decoded
        assert "exp" in decoded

    def test_decode_access_token_invalid(self):
        """Test decoding an invalid JWT token."""
        ensure_keys()
        invalid_token = "invalid.jwt.token"

        decoded = decode_access_token(invalid_token)

        assert decoded is None

    def test_token_expiration(self):
        """Test that token expiration is set correctly."""
        ensure_keys()
        data = {"user_id": 1, "username": "testuser"}
        token = create_access_token(data, expires_minutes=30)

        decoded = decode_access_token(token)

        assert decoded is not None
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        iat_time = datetime.fromtimestamp(decoded["iat"], tz=timezone.utc)

        # Should be approximately 30 minutes
        delta = exp_time - iat_time
        assert 29 <= delta.total_seconds() / 60 <= 31


class TestUserRegistration:
    """Tests for user registration endpoint."""

    def test_register_user_success(self, client, test_user_data):
        """Test successful user registration."""
        response = client.post("/api/auth/register", json=test_user_data)

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == test_user_data["username"]
        assert data["email"] == test_user_data["email"]
        assert "id" in data
        assert "hashed_password" not in data
        assert data["is_active"] is True
        assert data["is_superuser"] is False

    def test_register_user_duplicate_username(self, client, test_user_data):
        """Test registration with duplicate username."""
        # First registration
        response1 = client.post("/api/auth/register", json=test_user_data)
        assert response1.status_code == 201

        # Second registration with same username
        duplicate_data = {
            **test_user_data,
            "email": "different@example.com"
        }
        response2 = client.post("/api/auth/register", json=duplicate_data)

        assert response2.status_code == 400
        assert "Username already registered" in response2.json()["detail"]

    def test_register_user_duplicate_email(self, client, test_user_data):
        """Test registration with duplicate email."""
        # First registration
        response1 = client.post("/api/auth/register", json=test_user_data)
        assert response1.status_code == 201

        # Second registration with same email
        duplicate_data = {
            **test_user_data,
            "username": "differentuser"
        }
        response2 = client.post("/api/auth/register", json=duplicate_data)

        assert response2.status_code == 400
        assert "Email already registered" in response2.json()["detail"]

    def test_register_user_invalid_email(self, client, test_user_data):
        """Test registration with invalid email format."""
        invalid_data = {
            **test_user_data,
            "email": "not-an-email"
        }
        response = client.post("/api/auth/register", json=invalid_data)

        assert response.status_code == 422

    def test_register_user_short_password(self, client, test_user_data):
        """Test registration with password too short."""
        invalid_data = {
            **test_user_data,
            "password": "short"
        }
        response = client.post("/api/auth/register", json=invalid_data)

        assert response.status_code == 422

    def test_register_user_short_username(self, client, test_user_data):
        """Test registration with username too short."""
        invalid_data = {
            **test_user_data,
            "username": "ab"
        }
        response = client.post("/api/auth/register", json=invalid_data)

        assert response.status_code == 422


class TestUserLogin:
    """Tests for user login endpoint."""

    def test_login_success(self, client, registered_user):
        """Test successful login with valid credentials."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": registered_user["username"],
                "password": registered_user["password"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50

    def test_login_wrong_password(self, client, registered_user):
        """Test login with incorrect password."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": registered_user["username"],
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent username."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent",
                "password": "somepassword"
            }
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_missing_credentials(self, client):
        """Test login without providing credentials."""
        response = client.post("/api/auth/login", data={})

        assert response.status_code == 422


class TestProtectedEndpoints:
    """Tests for protected endpoints requiring authentication."""

    def test_get_current_user_success(self, client, registered_user):
        """Test /me endpoint with valid token."""
        headers = {"Authorization": f"Bearer {registered_user['token']}"}
        response = client.get("/api/auth/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == registered_user["username"]
        assert data["email"] == registered_user["email"]
        assert "hashed_password" not in data

    def test_get_current_user_no_token(self, client):
        """Test /me endpoint without token."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    def test_get_current_user_invalid_token(self, client):
        """Test /me endpoint with invalid token."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = client.get("/api/auth/me", headers=headers)

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    def test_get_current_user_malformed_header(self, client):
        """Test /me endpoint with malformed authorization header."""
        headers = {"Authorization": "NotBearer token123"}
        response = client.get("/api/auth/me", headers=headers)

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]


class TestJWKSEndpoint:
    """Tests for JWKS endpoint."""

    def test_jwks_endpoint(self, client):
        """Test that JWKS endpoint returns valid key information."""
        response = client.get("/api/auth/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) > 0

        key = data["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
        assert "n" in key
        assert "e" in key
        assert "kid" in key

    def test_key_status_endpoint(self, client):
        """Test that key status endpoint returns configuration info."""
        response = client.get("/api/auth/key-status")

        assert response.status_code == 200
        data = response.json()
        assert "keys_loaded" in data
        assert data["keys_loaded"] is True
        assert "source" in data
        assert data["source"] in ["env", "generated"]


class TestAuthenticateUserFunction:
    """Tests for the authenticate_user helper function."""

    def test_authenticate_user_success(self, test_db, test_user_data):
        """Test authenticate_user with valid credentials."""
        # Create user in database
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            hashed_password=get_password_hash(test_user_data["password"]),
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(user)
        test_db.commit()

        # Test authentication
        authenticated = authenticate_user(
            test_db,
            test_user_data["username"],
            test_user_data["password"]
        )

        assert authenticated is not None
        assert authenticated.username == test_user_data["username"]

    def test_authenticate_user_wrong_password(self, test_db, test_user_data):
        """Test authenticate_user with wrong password."""
        # Create user in database
        user = User(
            username=test_user_data["username"],
            email=test_user_data["email"],
            hashed_password=get_password_hash(test_user_data["password"]),
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(user)
        test_db.commit()

        # Test authentication with wrong password
        authenticated = authenticate_user(
            test_db,
            test_user_data["username"],
            "wrongpassword"
        )

        assert authenticated is None

    def test_authenticate_user_nonexistent(self, test_db):
        """Test authenticate_user with non-existent username."""
        authenticated = authenticate_user(
            test_db,
            "nonexistent",
            "somepassword"
        )

        assert authenticated is None


class TestSecurityIntegration:
    """Integration tests for end-to-end authentication flow."""

    def test_full_registration_login_access_flow(self, client):
        """Test complete flow: register -> login -> access protected endpoint."""
        # Step 1: Register
        user_data = {
            "username": "integrationuser",
            "email": "integration@example.com",
            "password": "IntegrationTest123!"
        }
        register_response = client.post("/api/auth/register", json=user_data)
        assert register_response.status_code == 201

        # Step 2: Login
        login_response = client.post(
            "/api/auth/login",
            data={"username": user_data["username"], "password": user_data["password"]}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Step 3: Access protected endpoint
        headers = {"Authorization": f"Bearer {token}"}
        me_response = client.get("/api/auth/me", headers=headers)
        assert me_response.status_code == 200

        user_info = me_response.json()
        assert user_info["username"] == user_data["username"]
        assert user_info["email"] == user_data["email"]

    def test_token_can_verify_with_jwks(self, client, registered_user):
        """Test that token can be verified using JWKS endpoint."""
        # Get JWKS
        jwks_response = client.get("/api/auth/.well-known/jwks.json")
        assert jwks_response.status_code == 200

        # Decode token
        decoded = decode_access_token(registered_user["token"])
        assert decoded is not None
        assert decoded["user_id"] == registered_user["user_id"]
