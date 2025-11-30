"""
Tests for advanced search API endpoint.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.database import Base, get_db
from src.backend.models.document import Document
from src.backend.main import app


# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """Create a test client with database dependency override."""
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
def sample_documents(db_session):
    """Create sample documents for testing."""
    now = datetime.utcnow()
    documents = [
        Document(
            filename="invoice_001.pdf",
            document_type="invoice",
            pack_name="pack_alpha",
            confidence_score=0.95,
            extracted_text="Invoice for services rendered in January 2024",
            metadata={"vendor": "Acme Corp"},
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=10)
        ),
        Document(
            filename="receipt_002.pdf",
            document_type="receipt",
            pack_name="pack_alpha",
            confidence_score=0.87,
            extracted_text="Receipt for office supplies purchase",
            metadata={"store": "Office Depot"},
            created_at=now - timedelta(days=5),
            updated_at=now - timedelta(days=5)
        ),
        Document(
            filename="contract_003.pdf",
            document_type="contract",
            pack_name="pack_beta",
            confidence_score=0.92,
            extracted_text="Service agreement for consulting services",
            metadata={"client": "Tech Startup Inc"},
            created_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=1)
        ),
        Document(
            filename="invoice_004.pdf",
            document_type="invoice",
            pack_name="pack_beta",
            confidence_score=0.78,
            extracted_text="Invoice for February 2024 services",
            metadata={"vendor": "Beta Services"},
            created_at=now,
            updated_at=now
        ),
    ]

    for doc in documents:
        db_session.add(doc)
    db_session.commit()

    return documents


class TestSearchEndpoint:
    """Test suite for search endpoint."""

    def test_search_no_filters(self, client, sample_documents):
        """Test search without any filters returns all documents."""
        response = client.get("/api/v1/search/documents")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 4
        assert len(data["results"]) == 4
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 1
        assert data["has_next"] is False
        assert data["has_prev"] is False

    def test_search_full_text(self, client, sample_documents):
        """Test full-text search on extracted text."""
        response = client.get("/api/v1/search/documents?query=services")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 3
        assert all("services" in result["extracted_text"].lower() for result in data["results"])

    def test_search_by_document_type(self, client, sample_documents):
        """Test filtering by document type."""
        response = client.get("/api/v1/search/documents?document_type=invoice")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert all(result["document_type"] == "invoice" for result in data["results"])

    def test_search_by_pack_name(self, client, sample_documents):
        """Test filtering by pack name."""
        response = client.get("/api/v1/search/documents?pack_name=pack_alpha")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert all(result["pack_name"] == "pack_alpha" for result in data["results"])

    def test_search_by_confidence_range(self, client, sample_documents):
        """Test filtering by confidence score range."""
        response = client.get("/api/v1/search/documents?min_confidence=0.85&max_confidence=0.95")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 3
        assert all(0.85 <= result["confidence_score"] <= 0.95 for result in data["results"])

    def test_search_by_date_range(self, client, sample_documents):
        """Test filtering by date range."""
        now = datetime.utcnow()
        date_from = (now - timedelta(days=6)).isoformat()
        date_to = now.isoformat()

        response = client.get(f"/api/v1/search/documents?date_from={date_from}&date_to={date_to}")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 3

    def test_search_combined_filters(self, client, sample_documents):
        """Test combining multiple filters."""
        response = client.get(
            "/api/v1/search/documents"
            "?document_type=invoice"
            "&pack_name=pack_alpha"
            "&min_confidence=0.9"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        result = data["results"][0]
        assert result["document_type"] == "invoice"
        assert result["pack_name"] == "pack_alpha"
        assert result["confidence_score"] >= 0.9

    def test_pagination_first_page(self, client, sample_documents):
        """Test pagination on first page."""
        response = client.get("/api/v1/search/documents?page=1&page_size=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 4
        assert len(data["results"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total_pages"] == 2
        assert data["has_next"] is True
        assert data["has_prev"] is False

    def test_pagination_second_page(self, client, sample_documents):
        """Test pagination on second page."""
        response = client.get("/api/v1/search/documents?page=2&page_size=2")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 4
        assert len(data["results"]) == 2
        assert data["page"] == 2
        assert data["page_size"] == 2
        assert data["total_pages"] == 2
        assert data["has_next"] is False
        assert data["has_prev"] is True

    def test_pagination_last_page_partial(self, client, sample_documents):
        """Test pagination on last page with partial results."""
        response = client.get("/api/v1/search/documents?page=2&page_size=3")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 4
        assert len(data["results"]) == 1
        assert data["page"] == 2
        assert data["page_size"] == 3
        assert data["total_pages"] == 2

    def test_empty_results(self, client, sample_documents):
        """Test search with no matching results."""
        response = client.get("/api/v1/search/documents?query=nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert len(data["results"]) == 0
        assert data["total_pages"] == 0

    def test_invalid_confidence_range(self, client, sample_documents):
        """Test validation error for invalid confidence range."""
        response = client.get("/api/v1/search/documents?min_confidence=0.9&max_confidence=0.5")
        assert response.status_code == 422

    def test_invalid_date_range(self, client, sample_documents):
        """Test validation error for invalid date range."""
        now = datetime.utcnow()
        date_from = now.isoformat()
        date_to = (now - timedelta(days=5)).isoformat()

        response = client.get(f"/api/v1/search/documents?date_from={date_from}&date_to={date_to}")
        assert response.status_code == 422

    def test_invalid_page_number(self, client, sample_documents):
        """Test validation error for invalid page number."""
        response = client.get("/api/v1/search/documents?page=0")
        assert response.status_code == 422

    def test_invalid_page_size(self, client, sample_documents):
        """Test validation error for invalid page size."""
        response = client.get("/api/v1/search/documents?page_size=0")
        assert response.status_code == 422

    def test_page_size_limit(self, client, sample_documents):
        """Test page size limit enforcement."""
        response = client.get("/api/v1/search/documents?page_size=101")
        assert response.status_code == 422

    def test_confidence_bounds(self, client, sample_documents):
        """Test confidence score bounds validation."""
        response = client.get("/api/v1/search/documents?min_confidence=-0.1")
        assert response.status_code == 422

        response = client.get("/api/v1/search/documents?max_confidence=1.1")
        assert response.status_code == 422

    def test_result_ordering(self, client, sample_documents):
        """Test results are ordered by created_at descending."""
        response = client.get("/api/v1/search/documents")
        assert response.status_code == 200

        data = response.json()
        results = data["results"]
        created_dates = [datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) for r in results]

        # Verify descending order
        for i in range(len(created_dates) - 1):
            assert created_dates[i] >= created_dates[i + 1]

    def test_result_structure(self, client, sample_documents):
        """Test result structure contains all required fields."""
        response = client.get("/api/v1/search/documents")
        assert response.status_code == 200

        data = response.json()
        result = data["results"][0]

        required_fields = [
            "id", "filename", "document_type", "pack_name",
            "confidence_score", "extracted_text", "created_at",
            "updated_at", "metadata"
        ]
        for field in required_fields:
            assert field in result

    def test_case_insensitive_search(self, client, sample_documents):
        """Test full-text search is case-insensitive."""
        response = client.get("/api/v1/search/documents?query=INVOICE")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert all("invoice" in result["extracted_text"].lower() for result in data["results"])
