"""
Comprehensive tests for autopack.auth (BUILD-146 P12 Phase 5).

Migrated from tests/backend/api/test_auth.py to test the new autopack.auth package.
Tests registration, login, JWT tokens, and duplicate detection.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from autopack.auth import User, hash_password, router
from autopack.database import Base, get_db

# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def test_db():
    """Create a test database session."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables (including User table from autopack.auth)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def app(test_db):
    """Create a test FastAPI application."""
    app = FastAPI()
    app.include_router(router)

    # Override the get_db dependency
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def test_user(test_db):
    """Create a test user."""
    user = User(
        username="existinguser",
        email="existing@example.com",
        hashed_password=hash_password("password123"),
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestRegisterEndpoint:
    """Tests for the /api/auth/register endpoint."""

    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepassword123",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data
        assert "hashed_password" not in data  # Should not expose password

    def test_register_duplicate_username(self, client, test_user):
        """Test registration with duplicate username."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "existinguser",
                "email": "different@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 400
        assert "Username already registered" in response.json()["detail"]

    def test_register_duplicate_email(self, client, test_user):
        """Test registration with duplicate email."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "differentuser",
                "email": "existing@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    def test_register_invalid_email(self, client):
        """Test registration with invalid email format."""
        response = client.post(
            "/api/auth/register",
            json={"username": "newuser", "email": "invalid-email", "password": "password123"},
        )

        assert response.status_code == 422  # Validation error

    def test_register_short_password(self, client):
        """Test registration with password too short."""
        response = client.post(
            "/api/auth/register",
            json={"username": "newuser", "email": "newuser@example.com", "password": "short"},
        )

        assert response.status_code == 422  # Validation error


class TestLoginEndpoint:
    """Tests for the /api/auth/login endpoint."""

    def test_login_success(self, client, test_user):
        """Test successful login with valid credentials."""
        response = client.post(
            "/api/auth/login", data={"username": "existinguser", "password": "password123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, test_user):
        """Test login with incorrect password."""
        response = client.post(
            "/api/auth/login", data={"username": "existinguser", "password": "wrongpassword"}
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent username."""
        response = client.post(
            "/api/auth/login", data={"username": "nonexistent", "password": "password123"}
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_missing_credentials(self, client):
        """Test login with missing credentials."""
        response = client.post("/api/auth/login", data={})

        assert response.status_code == 422  # Validation error


class TestJWKSEndpoint:
    """Tests for the /api/auth/.well-known/jwks.json endpoint."""

    def test_jwks_returns_keys(self, client):
        """Test that JWKS endpoint returns public keys."""
        response = client.get("/api/auth/.well-known/jwks.json")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert isinstance(data["keys"], list)

        if len(data["keys"]) > 0:
            # Verify JWK structure
            jwk = data["keys"][0]
            assert "kty" in jwk  # Key type
            assert "use" in jwk  # Public key use
            assert "kid" in jwk  # Key ID


class TestKeyStatusEndpoint:
    """Tests for the /api/auth/key-status endpoint."""

    def test_key_status_returns_loaded(self, client):
        """Test that key status endpoint returns keys loaded."""
        response = client.get("/api/auth/key-status")

        assert response.status_code == 200
        data = response.json()
        assert "keys_loaded" in data
        assert data["keys_loaded"] is True
        assert "source" in data  # Should be 'env' or 'generated'


class TestMeEndpoint:
    """Tests for the /api/auth/me endpoint."""

    def test_me_with_valid_token(self, client, test_user):
        """Test /me endpoint with valid JWT token."""
        # First login to get token
        login_response = client.post(
            "/api/auth/login", data={"username": "existinguser", "password": "password123"}
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Then call /me with token
        me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert me_response.status_code == 200
        data = me_response.json()
        assert data["username"] == "existinguser"
        assert data["email"] == "existing@example.com"
        assert "hashed_password" not in data

    def test_me_without_token(self, client):
        """Test /me endpoint without authentication."""
        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_me_with_invalid_token(self, client):
        """Test /me endpoint with invalid token."""
        response = client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid_token_here"}
        )

        assert response.status_code == 401
