"""User database model for authentication.

BUILD-146 P12 Phase 5: Migrated from backend.models.user to consolidate
auth under autopack namespace. Uses autopack.database.Base (not a second Base).
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime

from autopack.database import Base


class User(Base):
    """
    User model for authentication and authorization.

    Attributes:
        id: Primary key
        username: Unique username for login
        email: User's email address
        hashed_password: Bcrypt hashed password
        is_active: Whether the user account is active
        is_superuser: Whether the user has admin privileges
        created_at: Timestamp of account creation
        updated_at: Timestamp of last update
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

    def to_dict(self) -> dict:
        """Convert user to dictionary (excluding password)."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k != "hashed_password"
        }
