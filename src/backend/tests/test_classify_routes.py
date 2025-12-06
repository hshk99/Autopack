import pytest
from unittest.mock import Mock, patch, AsyncMock

# Skip until classifier service is implemented
pytest.importorskip("src.backend.services.classifier")
pytestmark = pytest.mark.skip(reason="Classifier service not implemented yet")

from src.backend.services.classifier import ClassificationService
