"""
Integration tests for SOT → DB/Qdrant Sync (BUILD-163).

THESE TESTS REQUIRE EXTERNAL DEPENDENCIES:
- PostgreSQL database (DATABASE_URL=postgresql://...)
- Qdrant vector store (QDRANT_HOST=http://localhost:6333)

Run manually or via scheduled CI workflow:
    # With PostgreSQL + Qdrant running:
    DATABASE_URL="postgresql://user:pass@localhost/autopack" \
    QDRANT_HOST="http://localhost:6333" \
    pytest tests/tidy/test_sot_db_sync_integration.py -v

Skip in default CI (external dependencies not available):
    pytest tests/tidy/ -k "not integration"
"""

from __future__ import annotations

import os
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tidy"))

from sot_db_sync import SOTDBSync, SyncMode

# Skip all tests in this file if external dependencies not configured
requires_postgres = pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith("postgresql://"),
    reason="PostgreSQL not configured (set DATABASE_URL=postgresql://...)",
)

requires_qdrant = pytest.mark.skipif(
    not os.getenv("QDRANT_HOST"),
    reason="Qdrant not configured (set QDRANT_HOST=http://localhost:6333)",
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_repo_structure(temp_dir):
    """Create mock repository structure with SOT files"""
    docs_dir = temp_dir / "docs"
    docs_dir.mkdir()

    # BUILD_HISTORY.md
    build_history = docs_dir / "BUILD_HISTORY.md"
    build_history.write_text(
        """# Build History

## BUILD-163: SOT DB Sync

This is a test build for integration testing.

**Features**:
- PostgreSQL sync
- Qdrant sync
- Full sync mode
"""
    )

    # ARCHITECTURE_DECISIONS.md
    arch_decisions = docs_dir / "ARCHITECTURE_DECISIONS.md"
    arch_decisions.write_text(
        """# Architecture Decisions

## DEC-100: Integration Test Decision

Test decision for integration testing.

**Status**: Active
**Impact**: Medium
"""
    )

    # DEBUG_LOG.md
    debug_log = docs_dir / "DEBUG_LOG.md"
    debug_log.write_text(
        """# Debug Log

## DBG-100: Integration Test Debug

Test debug entry for integration testing.

**Severity**: LOW
**Status**: Open
"""
    )

    return temp_dir


@requires_postgres
def test_postgres_sync(mock_repo_structure):
    """Test PostgreSQL database sync with real connection"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            max_seconds=60,
        )

        exit_code = syncer.run()

        assert exit_code == 0
        assert syncer.stats["parsed_entries"] > 0
        assert syncer.stats["db_inserts"] + syncer.stats["db_updates"] > 0

        # Verify connection was PostgreSQL
        assert syncer.database_url.startswith("postgresql://")

        # Cleanup: Remove test entries
        if syncer.db_conn:
            cursor = syncer.db_conn.cursor()
            cursor.execute(
                """
                DELETE FROM sot_entries
                WHERE entry_id IN ('BUILD-163', 'DEC-100', 'DBG-100')
            """
            )
            syncer.db_conn.commit()


@requires_qdrant
def test_qdrant_sync(mock_repo_structure):
    """Test Qdrant vector store sync with real connection"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.QDRANT_ONLY,
            execute=True,
            qdrant_host=os.getenv("QDRANT_HOST"),
            max_seconds=120,  # Embedding can be slow
        )

        exit_code = syncer.run()

        assert exit_code == 0
        assert syncer.stats["parsed_entries"] > 0
        assert syncer.stats["qdrant_upserts"] > 0

        # Verify Qdrant connection
        assert syncer.qdrant_store is not None
        assert syncer.qdrant_host == os.getenv("QDRANT_HOST")


@requires_postgres
@requires_qdrant
def test_full_sync_mode(mock_repo_structure):
    """Test full sync mode (PostgreSQL + Qdrant) with real connections"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.FULL,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            qdrant_host=os.getenv("QDRANT_HOST"),
            max_seconds=120,
        )

        exit_code = syncer.run()

        assert exit_code == 0
        assert syncer.stats["parsed_entries"] > 0
        assert syncer.stats["db_inserts"] + syncer.stats["db_updates"] > 0
        assert syncer.stats["qdrant_upserts"] > 0

        # Verify both connections
        assert syncer.db_conn is not None
        assert syncer.qdrant_store is not None

        # Cleanup PostgreSQL
        if syncer.db_conn:
            cursor = syncer.db_conn.cursor()
            cursor.execute(
                """
                DELETE FROM sot_entries
                WHERE entry_id IN ('BUILD-163', 'DEC-100', 'DBG-100')
            """
            )
            syncer.db_conn.commit()


@requires_postgres
def test_postgres_idempotent_upsert(mock_repo_structure):
    """Test PostgreSQL idempotent upserts with real database"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        # First sync
        syncer1 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            max_seconds=60,
        )
        syncer1.run()

        # Second sync (no changes)
        syncer2 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            max_seconds=60,
        )
        syncer2.run()

        # Should have 0 inserts/updates (content hash matches)
        assert syncer2.stats["db_inserts"] == 0
        assert syncer2.stats["db_updates"] == 0

        # Cleanup
        if syncer2.db_conn:
            cursor = syncer2.db_conn.cursor()
            cursor.execute(
                """
                DELETE FROM sot_entries
                WHERE entry_id IN ('BUILD-163', 'DEC-100', 'DBG-100')
            """
            )
            syncer2.db_conn.commit()


@requires_postgres
def test_postgres_content_update(mock_repo_structure):
    """Test PostgreSQL content update detection with real database"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        # First sync
        syncer1 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            max_seconds=60,
        )
        syncer1.run()

        # Modify content
        build_history = mock_repo_structure / "docs" / "BUILD_HISTORY.md"
        content = build_history.read_text()
        content = content.replace("integration testing", "MODIFIED integration testing")
        build_history.write_text(content)

        # Second sync
        syncer2 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            max_seconds=60,
        )
        syncer2.run()

        # Should have updates (content changed)
        assert syncer2.stats["db_updates"] > 0

        # Verify updated content
        cursor = syncer2.db_conn.cursor()
        cursor.execute("SELECT content FROM sot_entries WHERE entry_id = %s", ("BUILD-163",))
        row = cursor.fetchone()
        if row:
            assert "MODIFIED" in row[0]

        # Cleanup
        cursor.execute(
            """
            DELETE FROM sot_entries
            WHERE entry_id IN ('BUILD-163', 'DEC-100', 'DBG-100')
        """
        )
        syncer2.db_conn.commit()


@requires_postgres
def test_postgres_connection_error_handling():
    """Test handling of PostgreSQL connection errors"""
    with pytest.raises(SystemExit) as exc_info:
        syncer = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url="postgresql://invalid:invalid@nonexistent:5432/invalid",
            max_seconds=10,
        )

        syncer.run()

    # Should exit with error code
    assert exc_info.value.code != 0


@requires_qdrant
def test_qdrant_connection_error_handling():
    """Test handling of Qdrant connection errors"""
    with pytest.raises(SystemExit) as exc_info:
        syncer = SOTDBSync(
            mode=SyncMode.QDRANT_ONLY,
            execute=True,
            qdrant_host="http://nonexistent:9999",
            max_seconds=10,
        )

        syncer.run()

    # Should exit with error code
    assert exc_info.value.code != 0


@requires_postgres
@requires_qdrant
def test_performance_large_sync(mock_repo_structure):
    """Test performance of syncing with timing enabled"""
    with patch("sot_db_sync.REPO_ROOT", mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.FULL,
            execute=True,
            database_url=os.getenv("DATABASE_URL"),
            qdrant_host=os.getenv("QDRANT_HOST"),
            max_seconds=180,
            timing=True,
        )

        start = time.time()
        exit_code = syncer.run()
        elapsed = time.time() - start

        assert exit_code == 0
        # Should complete within timeout
        assert elapsed < 180

        # Should have timing data
        assert len(syncer.timings) > 0
        assert "parse_sot_files" in syncer.timings

        # Cleanup
        if syncer.db_conn:
            cursor = syncer.db_conn.cursor()
            cursor.execute(
                """
                DELETE FROM sot_entries
                WHERE entry_id IN ('BUILD-163', 'DEC-100', 'DBG-100')
            """
            )
            syncer.db_conn.commit()


if __name__ == "__main__":
    # Print environment check
    print("=" * 70)
    print("INTEGRATION TEST ENVIRONMENT CHECK")
    print("=" * 70)
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL', '(not set)')}")
    print(f"QDRANT_HOST: {os.getenv('QDRANT_HOST', '(not set)')}")
    print("=" * 70)
    print()

    if not os.getenv("DATABASE_URL", "").startswith("postgresql://"):
        print("⚠️  WARNING: PostgreSQL not configured")
        print("   Set DATABASE_URL=postgresql://user:pass@localhost/autopack")
        print()

    if not os.getenv("QDRANT_HOST"):
        print("⚠️  WARNING: Qdrant not configured")
        print("   Set QDRANT_HOST=http://localhost:6333")
        print()

    pytest.main([__file__, "-v", "-s"])
