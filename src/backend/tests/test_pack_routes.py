from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session
from src.backend.models.pack import Pack, PackStatus
from src.backend.schemas.pack import PackCreate, PackResponse
@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock(spec=Session)
