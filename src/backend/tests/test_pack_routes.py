import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session

# Skip until pack model/routes are implemented
pytest.importorskip("src.backend.models.pack")
pytestmark = pytest.mark.skip(reason="Pack routes not implemented yet")

from src.backend.models.pack import Pack, PackStatus
from src.backend.schemas.pack import PackCreate, PackResponse


@pytest.fixture
def mock_db():
    """Mock database session."""
    return Mock(spec=Session)
