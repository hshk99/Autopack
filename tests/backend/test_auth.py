"""
Tests for authentication endpoints and security utilities.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend.main import app
from src.backend.models.user import Base, User
from src.backend.api.dependencies import get_db
from src.backend.core.security import get_password_hash, verify_password, create_access_token, decode_access_token


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create test database session."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create test client with database override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    """Create a test user in the database."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        is_active=True,
        is_superuser=False
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestPasswordHashing:
    """Tests for password hashing utilities."""
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False
    
    def test_different_hashes_for_same_password(self):
        """Test that same password produces different hashes (salt)."""
        password = "samepassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """Tests for JWT token creation and validation."""
    
    def test_create_and_decode_token(self):
        """Test JWT token creation and decoding."""
        data = {"user_id": 1, "username": "testuser"}
        token = create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        
        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["user_id"] == 1
        assert decoded["username"] == "testuser"
        assert "exp" in decoded
    
    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        invalid_token = "invalid.token.here"
        decoded = decode_access_token(invalid_token)
        assert decoded is None


class TestRegistrationEndpoint:
    """Tests for user registration endpoint."""
    
    def test_register_new_user(self, client):
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
        assert "hashed_password" not in data
        assert "password" not in data
        assert data["is_active"] is True
        assert data["is_superuser"] is False
    
    def test_register_duplicate_username(self, client, test_user):
        """Test registration with existing username."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "different@example.com",
                "password": "password123"
            }
        )
        
        assert response.status_code == 400
        assert "Username already registered" in response.json()["detail"]
    
    def test_register_duplicate_email(self, client, test_user):
        """Test registration with existing email."""
        response = client.post(
            "/api/auth/register",
            json={
                "username": "differentuser",
                "email": "test@example.com",
                "password": "password123"
            }
        )
        
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]


class TestLoginEndpoint:
    """Tests for user login endpoint."""
    
    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "testpassword123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_with_email(self, client, test_user):
        """Test login using email instead of username."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "test@example.com",
                "password": "testpassword123"
            }
        )
        
        assert response.status_code == 200
    
    def test_login_wrong_password(self, client, test_user):
        """Test login with incorrect password."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent user."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent",
                "password": "password123"
            }
        )
        
        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]
