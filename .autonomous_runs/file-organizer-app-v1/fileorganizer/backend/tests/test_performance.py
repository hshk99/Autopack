"""
Performance benchmarking tests
"""
import pytest
import time


def test_document_list_performance(client, db):
    """Test document listing performance"""
    from app.models.document import Document, ProcessingStatus

    # Create 100 test documents
    documents = []
    for i in range(100):
        doc = Document(
            filename=f"test_{i}.pdf",
            original_path=f"/tmp/test_{i}.pdf",
            file_size=1000,
            file_type=".pdf",
            status=ProcessingStatus.COMPLETED
        )
        documents.append(doc)

    db.add_all(documents)
    db.commit()

    # Benchmark listing
    start_time = time.time()
    response = client.get("/api/v1/documents")
    end_time = time.time()

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 100

    elapsed = end_time - start_time
    print(f"\nDocument listing took {elapsed:.3f} seconds for 100 documents")
    assert elapsed < 1.0, "Document listing should complete in under 1 second"


def test_search_performance(client, db):
    """Test document search performance"""
    from app.models.document import Document, ProcessingStatus

    # Create 50 documents with searchable names
    documents = []
    for i in range(50):
        doc = Document(
            filename=f"invoice_{i:03d}.pdf",
            original_path=f"/tmp/invoice_{i:03d}.pdf",
            file_size=1000,
            file_type=".pdf",
            status=ProcessingStatus.COMPLETED
        )
        documents.append(doc)

    db.add_all(documents)
    db.commit()

    # Benchmark search
    start_time = time.time()
    response = client.get("/api/v1/documents/search?filename=invoice")
    end_time = time.time()

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 50

    elapsed = end_time - start_time
    print(f"\nDocument search took {elapsed:.3f} seconds for 50 matches")
    assert elapsed < 0.5, "Search should complete in under 0.5 seconds"


def test_cache_performance():
    """Test caching service performance"""
    from app.services.cache_service import CacheService

    cache = CacheService()

    # Benchmark cache writes
    start_time = time.time()
    for i in range(1000):
        cache.set(f"key_{i}", f"value_{i}")
    write_time = time.time() - start_time

    print(f"\nCache writes: 1000 entries in {write_time:.3f} seconds")
    assert write_time < 0.1, "Cache writes should be very fast"

    # Benchmark cache reads
    start_time = time.time()
    for i in range(1000):
        value = cache.get(f"key_{i}")
        assert value == f"value_{i}"
    read_time = time.time() - start_time

    print(f"Cache reads: 1000 entries in {read_time:.3f} seconds")
    assert read_time < 0.1, "Cache reads should be very fast"
