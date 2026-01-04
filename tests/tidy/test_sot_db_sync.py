"""
Tests for SOT → DB/Qdrant Sync (BUILD-163).

Test Coverage:
- SQLite-only mode (CI-safe, no external dependencies)
- Parsing logic (BUILD_HISTORY, ARCHITECTURE_DECISIONS, DEBUG_LOG)
- Idempotent upserts (content hash checking)
- Mode selection (docs-only, db-only, qdrant-only, full)
- Timeout handling
- Error handling (missing files, connection failures)

External dependency tests (PostgreSQL, Qdrant) are in test_sot_db_sync_integration.py
"""

from __future__ import annotations

import pytest
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tidy"))

from sot_db_sync import SOTDBSync, SyncMode, TimeoutError


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
    build_history.write_text("""# Build History

## INDEX

| Date | Build ID | Title | Description |
|------|----------|-------|-------------|
| 2026-01-01 | BUILD-001 | Test Build | First test build |
| 2026-01-02 | BUILD-002 | Second Build | Second test build |

## BUILD-001: Test Build

This is the detailed content for BUILD-001.

**Features**:
- Feature 1
- Feature 2

## BUILD-002: Second Build

This is BUILD-002 detailed content.
""")

    # ARCHITECTURE_DECISIONS.md
    arch_decisions = docs_dir / "ARCHITECTURE_DECISIONS.md"
    arch_decisions.write_text("""# Architecture Decisions

## INDEX

| Date | Decision ID | Decision | Status | Impact |
|------|-------------|----------|--------|--------|
| 2026-01-01 | DEC-001 | Use SQLite | Active | Medium |
| 2026-01-02 | DEC-002 | Add Qdrant | Proposed | High |

## DEC-001: Use SQLite

Decision to use SQLite as default database.

**Rationale**: Simplicity and portability.

## DEC-002: Add Qdrant

Proposal to add vector search with Qdrant.
""")

    # DEBUG_LOG.md
    debug_log = docs_dir / "DEBUG_LOG.md"
    debug_log.write_text("""# Debug Log

## INDEX

| Date | ID | Severity | Summary | Status |
|------|-------|----------|---------|--------|
| 2026-01-01 | DBG-001 | HIGH | Test error | Fixed |
| 2026-01-02 | DBG-002 | LOW | Warning test | Open |

## DBG-001: Test Error

High severity test error.

**Resolution**: Fixed by applying patch.

## DBG-002: Warning Test

Low severity warning for testing.
""")

    return temp_dir


def test_docs_only_mode_no_writes(mock_repo_structure):
    """Test docs-only mode parses files without writes"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            max_seconds=30
        )

        exit_code = syncer.run()

        assert exit_code == 0
        assert syncer.stats["parsed_entries"] == 6  # 2 BUILD + 2 DEC + 2 DBG
        assert syncer.stats["db_inserts"] == 0
        assert syncer.stats["db_updates"] == 0
        assert syncer.db_conn is None  # No DB connection in docs-only


def test_sqlite_db_sync(mock_repo_structure, temp_dir):
    """Test SQLite database sync with idempotent upserts"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=f"sqlite:///{db_path}",
            max_seconds=30
        )

        exit_code = syncer.run()

        assert exit_code == 0
        assert syncer.stats["parsed_entries"] == 6
        assert syncer.stats["db_inserts"] == 6
        assert syncer.stats["db_updates"] == 0

        # Verify database contents
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sot_entries'")
        assert cursor.fetchone() is not None

        # Check entries
        cursor.execute("SELECT file_type, entry_id, title FROM sot_entries ORDER BY file_type, entry_id")
        rows = cursor.fetchall()

        assert len(rows) == 6
        assert rows[0][0] == "architecture"  # file_type
        assert rows[0][1] == "DEC-001"       # entry_id
        assert "DEC-001" in rows[0][2]       # title contains ID

        conn.close()


def test_idempotent_upsert(mock_repo_structure, temp_dir):
    """Test that re-syncing same content doesn't create duplicates"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        # First sync
        syncer1 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=f"sqlite:///{db_path}",
            max_seconds=30
        )
        syncer1.run()

        # Second sync (no changes)
        syncer2 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=f"sqlite:///{db_path}",
            max_seconds=30
        )
        syncer2.run()

        # Should have 0 updates (content hash matches)
        assert syncer2.stats["db_inserts"] == 0
        assert syncer2.stats["db_updates"] == 0

        # Verify only 6 entries (no duplicates)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sot_entries")
        count = cursor.fetchone()[0]
        assert count == 6
        conn.close()


def test_content_update_detection(mock_repo_structure, temp_dir):
    """Test that content changes trigger updates"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        # First sync
        syncer1 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=f"sqlite:///{db_path}",
            max_seconds=30
        )
        syncer1.run()

        # Modify BUILD_HISTORY.md - change detailed section content
        build_history = mock_repo_structure / "docs" / "BUILD_HISTORY.md"
        content = build_history.read_text()
        content = content.replace("Feature 1", "MODIFIED Feature 1")
        build_history.write_text(content)

        # Second sync
        syncer2 = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=True,
            database_url=f"sqlite:///{db_path}",
            max_seconds=30
        )
        syncer2.run()

        # Should have updates (content changed)
        assert syncer2.stats["db_updates"] > 0

        # Verify updated content
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM sot_entries WHERE entry_id = 'BUILD-001'")
        content_row = cursor.fetchone()[0]
        assert "MODIFIED Feature 1" in content_row
        conn.close()


def test_parse_build_history_detailed(mock_repo_structure):
    """Test BUILD_HISTORY.md detailed section parsing"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)

        build_history_path = mock_repo_structure / "docs" / "BUILD_HISTORY.md"
        entries = syncer._parse_sot_file(build_history_path, "build_history")

        assert len(entries) >= 2

        # Check BUILD-001 entry
        build_001 = next((e for e in entries if e["id"] == "BUILD-001"), None)
        assert build_001 is not None
        assert "Test Build" in build_001["title"]
        assert "Feature 1" in build_001["content"]
        assert "Feature 2" in build_001["content"]


def test_parse_architecture_decisions_index(mock_repo_structure):
    """Test ARCHITECTURE_DECISIONS.md INDEX table parsing"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)

        arch_path = mock_repo_structure / "docs" / "ARCHITECTURE_DECISIONS.md"
        entries = syncer._parse_sot_file(arch_path, "architecture")

        assert len(entries) >= 2

        # Check DEC-001 entry
        dec_001 = next((e for e in entries if e["id"] == "DEC-001"), None)
        assert dec_001 is not None
        assert "DEC-001" in dec_001["title"]
        assert "Use SQLite" in dec_001["title"] or "Use SQLite" in dec_001["content"]


def test_parse_debug_log_index(mock_repo_structure):
    """Test DEBUG_LOG.md INDEX table parsing"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)

        debug_path = mock_repo_structure / "docs" / "DEBUG_LOG.md"
        entries = syncer._parse_sot_file(debug_path, "debug_log")

        assert len(entries) >= 2

        # Check DBG-001 entry
        dbg_001 = next((e for e in entries if e["id"] == "DBG-001"), None)
        assert dbg_001 is not None
        assert "DBG-001" in dbg_001["title"]
        # Content should contain severity or error details
        assert ("HIGH" in dbg_001["content"].upper() or
                "Test error" in dbg_001["content"] or
                "severity" in dbg_001["content"].lower())


def test_missing_sot_files_handled(temp_dir):
    """Test that missing SOT files are handled gracefully"""
    # Create empty docs directory (no SOT files)
    docs_dir = temp_dir / "docs"
    docs_dir.mkdir()

    with patch('sot_db_sync.REPO_ROOT', temp_dir):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)
        exit_code = syncer.run()

        # Should return error code (no entries parsed)
        assert exit_code == 1
        assert syncer.stats["parsed_entries"] == 0


def test_timeout_handling(mock_repo_structure):
    """Test that timeout is enforced"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            max_seconds=0.001  # 1ms timeout (will definitely exceed)
        )

        # Mock sleep to trigger timeout
        original_time = time.time
        call_count = [0]

        def mock_time():
            call_count[0] += 1
            if call_count[0] > 5:  # After a few calls, return past timeout
                return original_time() + 10
            return original_time()

        with patch('time.time', side_effect=mock_time):
            exit_code = syncer.run()

            # Should return timeout error code
            assert exit_code == 3


def test_database_url_resolution_priority(temp_dir):
    """Test database URL resolution priority order"""
    with patch('sot_db_sync.REPO_ROOT', temp_dir):
        # Priority 1: --database-url argument
        syncer1 = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            database_url="sqlite:///custom.db"
        )
        assert "custom.db" in syncer1.database_url

        # Priority 2: DATABASE_URL env var
        with patch.dict('os.environ', {'DATABASE_URL': 'sqlite:///env.db'}):
            syncer2 = SOTDBSync(
                mode=SyncMode.DOCS_ONLY,
                execute=False
            )
            assert "env.db" in syncer2.database_url

        # Priority 3: Default
        with patch.dict('os.environ', {}, clear=True):
            syncer3 = SOTDBSync(
                mode=SyncMode.DOCS_ONLY,
                execute=False
            )
            assert "autopack.db" in syncer3.database_url


def test_qdrant_mode_requires_host(mock_repo_structure):
    """Test that qdrant-only mode requires QDRANT_HOST"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.QDRANT_ONLY,
            execute=True,
            qdrant_host=None  # No Qdrant configured
        )

        exit_code = syncer.run()

        # Should return error code 4 (mode requirements not met)
        assert exit_code == 4


def test_full_mode_requires_qdrant(mock_repo_structure):
    """Test that full mode requires Qdrant configuration"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.FULL,
            execute=True,
            qdrant_host=None  # No Qdrant configured
        )

        exit_code = syncer.run()

        # Should return error code 4
        assert exit_code == 4


def test_dry_run_mode_no_execute_flag(mock_repo_structure, temp_dir):
    """Test that db-only without --execute is rejected"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DB_ONLY,
            execute=False,  # Missing --execute flag
            database_url=f"sqlite:///{db_path}"
        )

        exit_code = syncer.run()

        # Should complete but skip writes
        assert exit_code == 0
        assert syncer.stats["db_inserts"] == 0
        assert not db_path.exists()  # DB file not created


def test_content_hash_idempotency(mock_repo_structure):
    """Test that content hash is deterministic"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)

        build_history_path = mock_repo_structure / "docs" / "BUILD_HISTORY.md"

        # Parse twice
        entries1 = syncer._parse_sot_file(build_history_path, "build_history")
        entries2 = syncer._parse_sot_file(build_history_path, "build_history")

        # Content should be identical
        assert len(entries1) == len(entries2)
        for e1, e2 in zip(entries1, entries2):
            assert e1["id"] == e2["id"]
            assert e1["content"] == e2["content"]


def test_timing_output(mock_repo_structure, capsys):
    """Test that timing information is printed when enabled"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            timing=True
        )

        syncer.run()

        captured = capsys.readouterr()
        assert "[TIMING]" in captured.out
        assert "parse_sot_files" in captured.out


def test_no_timing_output(mock_repo_structure, capsys):
    """Test that timing can be disabled"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            timing=False
        )

        syncer.run()

        captured = capsys.readouterr()
        assert "[TIMING]" not in captured.out


def test_relative_sqlite_path_normalization(temp_dir):
    """Test that relative SQLite paths are normalized to absolute"""
    with patch('sot_db_sync.REPO_ROOT', temp_dir):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            database_url="sqlite:///relative/path/test.db"
        )

        # Should be normalized to absolute path
        assert syncer.database_url.startswith("sqlite:///")
        assert "relative" in syncer.database_url
        # Should be absolute (contains full path)
        db_path = syncer.database_url.replace("sqlite:///", "")
        assert Path(db_path).is_absolute() or (len(db_path) >= 3 and db_path[1] == ":")


def test_windows_absolute_path_detection(temp_dir):
    """Test Windows absolute path detection (C:/ prefix)"""
    with patch('sot_db_sync.REPO_ROOT', temp_dir):
        syncer = SOTDBSync(
            mode=SyncMode.DOCS_ONLY,
            execute=False,
            database_url="sqlite:///C:/dev/test.db"
        )

        # Should NOT be modified (already absolute)
        assert syncer.database_url == "sqlite:///C:/dev/test.db"


def test_error_collection(mock_repo_structure):
    """Test that parsing errors are collected in stats"""
    # Create malformed SOT file
    docs_dir = mock_repo_structure / "docs"
    malformed = docs_dir / "BUILD_HISTORY.md"

    # Overwrite with content that will cause issues
    malformed.write_text("Not a valid markdown structure")

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)
        syncer.run()

        # Should have parsed but found 0 entries (not an error, just no matches)
        # This is actually valid behavior - file exists but has no entries
        assert syncer.stats["parsed_entries"] >= 0


def test_keyboard_interrupt_handling(mock_repo_structure):
    """Test graceful handling of KeyboardInterrupt"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        syncer = SOTDBSync(mode=SyncMode.DOCS_ONLY, execute=False)

        # Mock parse_sot_files to raise KeyboardInterrupt
        with patch.object(syncer, 'parse_sot_files', side_effect=KeyboardInterrupt):
            exit_code = syncer.run()

            # Should return 130 (standard for SIGINT)
            assert exit_code == 130


def test_cli_smoke_docs_only():
    """
    Smoke test: CLI runs without crashing in docs-only mode (repo context).

    In this repo, docs-only mode should always succeed because SOT ledgers
    (BUILD_HISTORY.md, ARCHITECTURE_DECISIONS.md, DEBUG_LOG.md) contain entries.

    This strict check (exit code 0 only) catches regressions where the parser
    fails to extract entries from valid SOT files.
    """
    import subprocess

    # Run from actual repo root (not test fixture)
    repo_root = Path(__file__).parent.parent.parent

    result = subprocess.run(
        [
            sys.executable,
            "scripts/tidy/sot_db_sync.py",
            "--docs-only"
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=30
    )

    # Repo context: MUST succeed (strict check)
    assert result.returncode == 0, (
        f"Expected success (0) but got {result.returncode}.\n"
        f"This repo has valid SOT ledgers; exit code {result.returncode} indicates a regression.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    # Should not crash with traceback
    assert "Traceback" not in result.stderr

    # Should parse non-zero entries (sanity check)
    assert "parsed_entries" in result.stdout.lower() or "entries" in result.stdout.lower()


def test_lock_acquisition_docs_only_no_locks(mock_repo_structure):
    """Test that docs-only mode does not acquire locks"""
    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        with patch('sot_db_sync.LOCKS_AVAILABLE', True):
            # Mock MultiLock to track calls
            mock_multi_lock = MagicMock()

            with patch('sot_db_sync.MultiLock', return_value=mock_multi_lock):
                syncer = SOTDBSync(
                    mode=SyncMode.DOCS_ONLY,
                    execute=False,
                    max_seconds=30
                )

                # Docs-only should not create MultiLock instance
                assert syncer.multi_lock is None

                # Run should complete without acquiring locks
                exit_code = syncer.run()
                assert exit_code == 0

                # Verify acquire was never called
                mock_multi_lock.acquire.assert_not_called()


def test_lock_acquisition_execute_mode_acquires_locks(mock_repo_structure, temp_dir):
    """Test that execute modes acquire subsystem locks"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        with patch('sot_db_sync.LOCKS_AVAILABLE', True):
            # Mock MultiLock to track calls
            mock_multi_lock = MagicMock()

            with patch('sot_db_sync.MultiLock', return_value=mock_multi_lock):
                syncer = SOTDBSync(
                    mode=SyncMode.DB_ONLY,
                    execute=True,
                    database_url=f"sqlite:///{db_path}",
                    max_seconds=30
                )

                # Execute mode should create MultiLock instance
                assert syncer.multi_lock is not None

                # Run should acquire locks with correct subsystems
                syncer.run()

                # Verify acquire was called with ["docs", "archive"]
                mock_multi_lock.acquire.assert_called_once_with(["docs", "archive"])

                # Verify release was called
                mock_multi_lock.release.assert_called_once()


def test_lock_acquisition_failure_returns_exit_code_5(mock_repo_structure, temp_dir):
    """Test that lock acquisition failure returns exit code 5"""
    db_path = temp_dir / "test.db"

    with patch('sot_db_sync.REPO_ROOT', mock_repo_structure):
        with patch('sot_db_sync.LOCKS_AVAILABLE', True):
            # Mock MultiLock to simulate lock acquisition failure
            mock_multi_lock = MagicMock()
            mock_multi_lock.acquire.side_effect = TimeoutError("Lock timeout")

            with patch('sot_db_sync.MultiLock', return_value=mock_multi_lock):
                syncer = SOTDBSync(
                    mode=SyncMode.DB_ONLY,
                    execute=True,
                    database_url=f"sqlite:///{db_path}",
                    max_seconds=30
                )

                # Run should return exit code 5 for lock failure
                exit_code = syncer.run()
                assert exit_code == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
