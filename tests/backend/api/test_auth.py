"""
Tests for authentication API endpoints.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.api.auth import get_password_hash, router
from src.backend.models.user import Base, User, get_db
from fastapi import FastAPI


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
        hashed_password=get_password_hash("password123"),
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


class TestRegisterEndpoint:
    """Tests for the /register endpoint."""

    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepassword123"
            }
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
                "password": "password123"
            }
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
                "password": "password123"
            }
        )
        
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    def test_register_invalid_email(self, client):
        """Test registration with invalid email format."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "email": "invalid-email",
                "password": "password123"
            }
        )
        
        assert response.status_code == 422  # Validation error

    def test_register_short_password(self, client):
        """Test registration with password too short."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "short"
            }
        )
        
        assert response.status_code == 422  # Validation error

    def test_register_short_username(self, client):
        """Test registration with username too short."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "ab",
                "email": "newuser@example.com",
                "password": "password123"
            }
        )
        
        assert response.status_code == 422  # Validation error


class TestLoginEndpoint:
    """Tests for the /login endpoint."""

    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "existinguser",
                "password": "password123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "existinguser",
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent",
                "password": "password123"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]


class TestMeEndpoint:
    """Tests for the /me endpoint."""

    def test_get_current_user(self, client, test_user):
        """Test getting current user information."""
        # First login to get token
        login_response = client.post(
            "/api/auth/login",
            data={
                "username": "existinguser",
                "password": "password123"
            }
        )
        token = login_response.json()["access_token"]
        
        # Then get user info
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "existinguser"
        assert data["email"] == "existing@example.com"
        assert data["is_active"] is True

    def test_get_current_user_no_token(self, client):
        """Test getting current user without token."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401
