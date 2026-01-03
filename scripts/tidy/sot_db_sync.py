#!/usr/bin/env python3
"""
SOT → DB/Qdrant Sync (BUILD-163)

Standalone, bounded synchronization from markdown SOT ledgers to derived indexes.

Canonical truth: Markdown SOT files in docs/ (BUILD_HISTORY.md, ARCHITECTURE_DECISIONS.md, DEBUG_LOG.md)
Derived indexes: PostgreSQL/SQLite and Qdrant (rebuildable, idempotent)

Features:
- Multiple execution modes: --docs-only (default), --db-only, --qdrant-only, --full
- Explicit write control: requires --execute flag for DB/Qdrant writes
- Bounded execution: --max-seconds timeout with timing output
- Clear target specification: --database-url and --qdrant-host
- Idempotent upserts: stable IDs + content hash
- SQLite fallback: defaults to sqlite:///autopack.db if DATABASE_URL unset

Usage:
    # Dry-run (docs parsing only, no writes):
    python scripts/tidy/sot_db_sync.py

    # Write to DB only:
    python scripts/tidy/sot_db_sync.py --db-only --execute

    # Write to Qdrant only:
    python scripts/tidy/sot_db_sync.py --qdrant-only --execute

    # Full sync (DB + Qdrant):
    python scripts/tidy/sot_db_sync.py --full --execute

    # With custom targets and timeout:
    python scripts/tidy/sot_db_sync.py --full --execute \
        --database-url postgresql://user:pass@host/db \
        --qdrant-host http://localhost:6333 \
        --max-seconds 60

Exit codes:
    0 - Success
    1 - Parsing/validation errors
    2 - Database connection errors
    3 - Timeout exceeded
    4 - Mode-specific requirements not met (e.g., --full but Qdrant unavailable)
"""

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


class TimeoutError(Exception):
    """Raised when execution exceeds max_seconds"""
    pass


class SyncMode:
    """Sync execution modes"""
    DOCS_ONLY = "docs-only"
    DB_ONLY = "db-only"
    QDRANT_ONLY = "qdrant-only"
    FULL = "full"


class SOTDBSync:
    """
    Synchronizes markdown SOT ledgers to DB/Qdrant indexes.

    Design principles:
    - Markdown SOT is canonical (never modified)
    - DB/Qdrant are derived (rebuildable)
    - Writes require explicit --execute flag
    - Operations are idempotent (stable IDs + content hash)
    """

    def __init__(
        self,
        mode: str,
        execute: bool,
        database_url: Optional[str] = None,
        qdrant_host: Optional[str] = None,
        max_seconds: int = 120,
        timing: bool = True,
        verbose: bool = False,
    ):
        self.mode = mode
        self.execute = execute
        self.max_seconds = max_seconds
        self.timing = timing
        self.verbose = verbose
        self.start_time = time.time()

        # Paths
        self.repo_root = REPO_ROOT
        self.docs_dir = self.repo_root / "docs"

        # Timing tracking
        self.timings: Dict[str, float] = {}

        # Database configuration
        self.database_url = self._resolve_database_url(database_url)
        self.qdrant_host = self._resolve_qdrant_host(qdrant_host)

        # Database connections (lazy init)
        self.db_conn = None
        self.qdrant_store = None

        # Statistics
        self.stats = {
            "parsed_entries": 0,
            "db_inserts": 0,
            "db_updates": 0,
            "qdrant_upserts": 0,
            "errors": [],
        }

    def _resolve_database_url(self, provided_url: Optional[str]) -> str:
        """
        Resolve database URL with explicit fallback chain.

        Priority:
        1. --database-url argument
        2. DATABASE_URL environment variable
        3. Default to sqlite:///autopack.db (explicit SQLite fallback)
        """
        if provided_url:
            url = provided_url
            source = "--database-url"
        elif os.getenv("DATABASE_URL"):
            url = os.getenv("DATABASE_URL")
            source = "DATABASE_URL env var"
        else:
            url = "sqlite:///autopack.db"
            source = "default (sqlite:///autopack.db)"

        # Normalize SQLite paths to absolute
        if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
            db_path_str = url[len("sqlite:///"):]
            db_path = Path(db_path_str)

            # Check for Windows absolute path
            is_windows_abs = (
                len(db_path_str) >= 3
                and db_path_str[1] == ":"
                and db_path_str[2] in ("/", "\\")
            )

            if not db_path.is_absolute() and not is_windows_abs:
                # Make relative to repo root
                abs_path = (self.repo_root / db_path).resolve()
                url = f"sqlite:///{abs_path}"

        print(f"[CONFIG] Database URL: {url} (from {source})")
        return url

    def _resolve_qdrant_host(self, provided_host: Optional[str]) -> Optional[str]:
        """
        Resolve Qdrant host.

        Priority:
        1. --qdrant-host argument
        2. QDRANT_HOST environment variable
        3. None (Qdrant disabled)
        """
        if provided_host:
            host = provided_host
            source = "--qdrant-host"
        elif os.getenv("QDRANT_HOST"):
            host = os.getenv("QDRANT_HOST")
            source = "QDRANT_HOST env var"
        else:
            host = None
            source = "not configured (Qdrant disabled)"

        if host:
            print(f"[CONFIG] Qdrant host: {host} (from {source})")
        else:
            print(f"[CONFIG] Qdrant: {source}")

        return host

    def _check_timeout(self):
        """Check if execution has exceeded max_seconds"""
        elapsed = time.time() - self.start_time
        if elapsed > self.max_seconds:
            raise TimeoutError(f"Execution exceeded {self.max_seconds}s limit")

    def _time_operation(self, name: str):
        """Context manager for timing operations"""
        class Timer:
            def __init__(self, parent, op_name):
                self.parent = parent
                self.op_name = op_name
                self.start = None

            def __enter__(self):
                self.start = time.time()
                return self

            def __exit__(self, *args):
                elapsed = time.time() - self.start
                self.parent.timings[self.op_name] = elapsed
                if self.parent.timing:
                    print(f"[TIMING] {self.op_name}: {elapsed:.2f}s")

        return Timer(self, name)

    def _init_db_connection(self):
        """Initialize database connection (PostgreSQL or SQLite)"""
        if self.db_conn:
            return  # Already initialized

        with self._time_operation("db_connection_init"):
            if self.database_url.startswith("postgresql://"):
                try:
                    import psycopg2
                    self.db_conn = psycopg2.connect(self.database_url)
                    print("[OK] Connected to PostgreSQL")
                except ImportError:
                    raise RuntimeError(
                        "psycopg2 not available. Install with: pip install psycopg2-binary"
                    )
                except Exception as e:
                    raise RuntimeError(f"PostgreSQL connection failed: {e}")

            elif self.database_url.startswith("sqlite:///"):
                try:
                    import sqlite3
                    db_path = self.database_url[len("sqlite:///"):]
                    self.db_conn = sqlite3.connect(db_path)
                    # Enable foreign keys for SQLite
                    self.db_conn.execute("PRAGMA foreign_keys = ON")
                    print(f"[OK] Connected to SQLite at {db_path}")
                except Exception as e:
                    raise RuntimeError(f"SQLite connection failed: {e}")

            else:
                raise RuntimeError(f"Unsupported database URL scheme: {self.database_url}")

            self._ensure_db_schema()

    def _ensure_db_schema(self):
        """
        Ensure SOT index table exists.

        Note: This ONLY creates the sot_entries table for SOT sync.
        It does NOT run migrations for the main Autopack schema (runs, phases, etc).
        Those require explicit migration scripts.
        """
        if not self.db_conn:
            return

        cursor = self.db_conn.cursor()

        # Detect database type
        is_postgres = self.database_url.startswith("postgresql://")

        if is_postgres:
            # PostgreSQL schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sot_entries (
                    id SERIAL PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    content_hash TEXT NOT NULL,
                    UNIQUE(project_id, file_type, entry_id)
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sot_entries_lookup
                ON sot_entries(project_id, file_type, entry_id);
            """)
        else:
            # SQLite schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sot_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    content_hash TEXT NOT NULL,
                    UNIQUE(project_id, file_type, entry_id)
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sot_entries_lookup
                ON sot_entries(project_id, file_type, entry_id);
            """)

        self.db_conn.commit()
        if self.verbose:
            print("[OK] Database schema verified")

    def _init_qdrant_connection(self):
        """Initialize Qdrant connection"""
        if self.qdrant_store:
            return  # Already initialized

        if not self.qdrant_host:
            raise RuntimeError(
                "Qdrant host not configured. Set QDRANT_HOST or use --qdrant-host"
            )

        with self._time_operation("qdrant_connection_init"):
            try:
                from autopack.memory.qdrant_store import QdrantStore

                # Parse host and port
                if self.qdrant_host.startswith("http://"):
                    host_part = self.qdrant_host.replace("http://", "")
                    if ":" in host_part:
                        host, port_str = host_part.rsplit(":", 1)
                        port = int(port_str)
                    else:
                        host = host_part
                        port = 6333
                else:
                    host = self.qdrant_host
                    port = 6333

                self.qdrant_store = QdrantStore(host=host, port=port)
                print(f"[OK] Connected to Qdrant at {self.qdrant_host}")

            except ImportError:
                raise RuntimeError(
                    "Qdrant dependencies not available. "
                    "Check autopack.memory.qdrant_store installation."
                )
            except Exception as e:
                raise RuntimeError(f"Qdrant connection failed: {e}")

    def parse_sot_files(self) -> Dict[str, List[Dict]]:
        """
        Parse SOT markdown ledgers.

        Returns:
            Dict mapping file_type to list of entries
        """
        with self._time_operation("parse_sot_files"):
            results = {}

            sot_files = {
                "build_history": self.docs_dir / "BUILD_HISTORY.md",
                "architecture": self.docs_dir / "ARCHITECTURE_DECISIONS.md",
                "debug_log": self.docs_dir / "DEBUG_LOG.md",
            }

            for file_type, file_path in sot_files.items():
                self._check_timeout()

                if not file_path.exists():
                    print(f"[SKIP] {file_type}: {file_path} not found")
                    continue

                try:
                    entries = self._parse_sot_file(file_path, file_type)
                    results[file_type] = entries
                    self.stats["parsed_entries"] += len(entries)
                    print(f"[OK] Parsed {len(entries)} entries from {file_type}")
                except Exception as e:
                    error_msg = f"Error parsing {file_type}: {e}"
                    self.stats["errors"].append(error_msg)
                    print(f"[ERROR] {error_msg}")

            return results

    def _parse_sot_file(self, file_path: Path, file_type: str) -> List[Dict]:
        """
        Parse a single SOT file and extract entries.

        Tries detailed section parsing first, falls back to INDEX table parsing.
        """
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        entries = []
        current_entry = None

        def commit_current():
            nonlocal current_entry
            if current_entry:
                entries.append(current_entry)
                current_entry = None

        def start_entry(entry_id: str, title: str):
            nonlocal current_entry
            commit_current()
            current_entry = {
                "id": entry_id,
                "title": title,
                "content": title + "\n",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {},
            }

        # Header patterns
        build_header = re.compile(r"^(#{2,3})\s+(BUILD-\d+)\b")
        dec_header = re.compile(r"^(#{2,3})\s+(DEC-\d+)\b")
        dbg_header = re.compile(r"^(#{2,3})\s+(DBG-\d+)\b")

        for line in lines:
            if file_type == "build_history":
                m = build_header.match(line)
                if m:
                    start_entry(entry_id=m.group(2), title=line)
                    continue
            elif file_type == "architecture":
                m = dec_header.match(line)
                if m:
                    start_entry(entry_id=m.group(2), title=line)
                    continue
            elif file_type == "debug_log":
                m = dbg_header.match(line)
                if m:
                    start_entry(entry_id=m.group(2), title=line)
                    continue

            if current_entry:
                current_entry["content"] += line + "\n"

        commit_current()

        # Fallback: parse INDEX table if no detailed entries
        if not entries:
            entries = self._parse_sot_index_table(file_path, file_type, lines)

        return entries

    def _parse_sot_index_table(self, file_path: Path, file_type: str, lines: List[str]) -> List[Dict]:
        """Parse INDEX table from SOT file"""
        entries = []

        # Find INDEX section
        try:
            idx_start = next(i for i, l in enumerate(lines) if l.strip().startswith("## INDEX"))
        except StopIteration:
            return entries

        # Collect table rows
        table_rows = []
        for line in lines[idx_start + 1:]:
            stripped = line.strip()
            if stripped.startswith("|"):
                table_rows.append(stripped)
            elif table_rows and not stripped:
                break

        # Filter out header/separator rows
        data_rows = []
        for row in table_rows:
            if re.match(r"^\|\s*[-\s:]+\|\s*$", row):
                continue
            if re.search(r"\|\s*(Timestamp|Date)\s*\|", row):
                continue
            data_rows.append(row)

        # Parse data rows
        for row in data_rows:
            if file_type == "build_history":
                # | 2026-01-02 | BUILD-153 | Title | Description |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(BUILD-\d+)\s*\|\s*([^|]+?)\s*\|\s*(.*)\|\s*$",
                    row
                )
                if m:
                    date_str, bid, title_text, desc = m.groups()
                    entries.append({
                        "id": bid,
                        "title": f"{bid} | {date_str} | {title_text.strip()}",
                        "content": f"{bid}\n{title_text.strip()}\n\n{desc.strip()}",
                        "created_at": f"{date_str}T00:00:00Z",
                        "metadata": {"source": "index_table"},
                    })

            elif file_type == "architecture":
                # | 2026-01-02 | DEC-016 | Decision | Status | Impact |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DEC-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
                    row
                )
                if m:
                    date_str, did, decision, status, impact = m.groups()
                    entries.append({
                        "id": did,
                        "title": f"{did} | {date_str} | {decision.strip()}",
                        "content": f"{did}\n{decision.strip()}\nStatus: {status.strip()}\nImpact: {impact.strip()}",
                        "created_at": f"{date_str}T00:00:00Z",
                        "metadata": {"source": "index_table", "status": status.strip()},
                    })

            elif file_type == "debug_log":
                # | 2026-01-01 | DBG-079 | LOW | Summary | Status |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DBG-\d+)\s*\|\s*([^|]+?)\s*\|\s*(.*)\|\s*([^|]+?)\s*\|\s*$",
                    row
                )
                if m:
                    date_str, gid, severity, summary, status = m.groups()
                    entries.append({
                        "id": gid,
                        "title": f"{gid} | {date_str} | {severity.strip()}",
                        "content": f"{gid}\nSeverity: {severity.strip()}\n{summary.strip()}\nStatus: {status.strip()}",
                        "created_at": f"{date_str}T00:00:00Z",
                        "metadata": {"source": "index_table", "severity": severity.strip(), "status": status.strip()},
                    })

        return entries

    def sync_to_db(self, parsed_entries: Dict[str, List[Dict]]):
        """Sync parsed entries to database"""
        if not self.execute:
            print("[DRY-RUN] Would sync to database (use --execute to write)")
            return

        with self._time_operation("sync_to_db"):
            self._init_db_connection()

            cursor = self.db_conn.cursor()
            is_postgres = self.database_url.startswith("postgresql://")

            for file_type, entries in parsed_entries.items():
                for entry in entries:
                    self._check_timeout()

                    # Compute content hash for idempotency
                    content_hash = hashlib.sha256(
                        entry["content"].encode("utf-8")
                    ).hexdigest()[:16]

                    # Stable entry ID
                    entry_id = entry["id"]
                    project_id = "autopack"

                    # Check if entry exists
                    if is_postgres:
                        cursor.execute(
                            "SELECT content_hash FROM sot_entries WHERE project_id = %s AND file_type = %s AND entry_id = %s",
                            (project_id, file_type, entry_id)
                        )
                    else:
                        cursor.execute(
                            "SELECT content_hash FROM sot_entries WHERE project_id = ? AND file_type = ? AND entry_id = ?",
                            (project_id, file_type, entry_id)
                        )

                    existing = cursor.fetchone()

                    if existing and existing[0] == content_hash:
                        # No change, skip
                        continue

                    # Upsert entry
                    metadata_json = json.dumps(entry.get("metadata", {}))

                    if is_postgres:
                        cursor.execute("""
                            INSERT INTO sot_entries
                            (project_id, file_type, entry_id, title, content, metadata, created_at, updated_at, content_hash)
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, NOW(), %s)
                            ON CONFLICT (project_id, file_type, entry_id)
                            DO UPDATE SET
                                title = EXCLUDED.title,
                                content = EXCLUDED.content,
                                metadata = EXCLUDED.metadata,
                                updated_at = NOW(),
                                content_hash = EXCLUDED.content_hash
                        """, (
                            project_id,
                            file_type,
                            entry_id,
                            entry.get("title", ""),
                            entry["content"],
                            metadata_json,
                            entry.get("created_at", datetime.now(timezone.utc).isoformat()),
                            content_hash,
                        ))
                    else:
                        # SQLite: manual UPSERT
                        cursor.execute(
                            "SELECT id FROM sot_entries WHERE project_id = ? AND file_type = ? AND entry_id = ?",
                            (project_id, file_type, entry_id)
                        )
                        existing_row = cursor.fetchone()

                        if existing_row:
                            cursor.execute("""
                                UPDATE sot_entries SET
                                    title = ?,
                                    content = ?,
                                    metadata = ?,
                                    updated_at = CURRENT_TIMESTAMP,
                                    content_hash = ?
                                WHERE project_id = ? AND file_type = ? AND entry_id = ?
                            """, (
                                entry.get("title", ""),
                                entry["content"],
                                metadata_json,
                                content_hash,
                                project_id,
                                file_type,
                                entry_id,
                            ))
                            self.stats["db_updates"] += 1
                        else:
                            cursor.execute("""
                                INSERT INTO sot_entries
                                (project_id, file_type, entry_id, title, content, metadata, created_at, updated_at, content_hash)
                                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                            """, (
                                project_id,
                                file_type,
                                entry_id,
                                entry.get("title", ""),
                                entry["content"],
                                metadata_json,
                                entry.get("created_at", datetime.now(timezone.utc).isoformat()),
                                content_hash,
                            ))
                            self.stats["db_inserts"] += 1

            self.db_conn.commit()
            print(f"[OK] Synced to database: {self.stats['db_inserts']} inserts, {self.stats['db_updates']} updates")

    def sync_to_qdrant(self, parsed_entries: Dict[str, List[Dict]]):
        """Sync parsed entries to Qdrant vector store"""
        if not self.execute:
            print("[DRY-RUN] Would sync to Qdrant (use --execute to write)")
            return

        with self._time_operation("sync_to_qdrant"):
            self._init_qdrant_connection()

            try:
                from autopack.memory.embeddings import sync_embed_text
            except ImportError:
                raise RuntimeError("Embedding function not available")

            collection_name = "autopack_sot_docs"

            # Ensure collection exists (1536 dimensions for OpenAI text-embedding-3-small)
            try:
                self.qdrant_store.ensure_collection(collection_name, size=1536)
            except Exception as e:
                raise RuntimeError(f"Failed to create Qdrant collection: {e}")

            points = []

            for file_type, entries in parsed_entries.items():
                for entry in entries:
                    self._check_timeout()

                    # Create embedding
                    try:
                        embedding = sync_embed_text(entry["content"])
                    except Exception as e:
                        error_msg = f"Failed to embed {entry['id']}: {e}"
                        self.stats["errors"].append(error_msg)
                        print(f"[WARN] {error_msg}")
                        continue

                    # Create point with stable ID
                    point_id = f"autopack_{file_type}_{entry['id']}"

                    point = {
                        "id": point_id,
                        "vector": embedding,
                        "payload": {
                            "project_id": "autopack",
                            "file_type": file_type,
                            "entry_id": entry["id"],
                            "title": entry.get("title", ""),
                            "content_preview": entry["content"][:500],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "metadata": entry.get("metadata", {}),
                        }
                    }

                    points.append(point)
                    self.stats["qdrant_upserts"] += 1

            # Batch upsert
            if points:
                try:
                    self.qdrant_store.upsert(collection_name, points)
                    print(f"[OK] Synced {len(points)} points to Qdrant")
                except Exception as e:
                    raise RuntimeError(f"Qdrant upsert failed: {e}")

    def run(self) -> int:
        """
        Execute sync based on mode.

        Returns:
            Exit code (0 = success)
        """
        try:
            print(f"\n{'='*80}")
            print(f"SOT → DB/Qdrant Sync (BUILD-163)")
            print(f"{'='*80}")
            print(f"Mode: {self.mode}")
            print(f"Execute: {self.execute}")
            print(f"Max seconds: {self.max_seconds}")
            print(f"{'='*80}\n")

            # Parse SOT files (always required)
            parsed_entries = self.parse_sot_files()

            if not parsed_entries:
                print("[WARN] No entries parsed from SOT files")
                return 1

            # Mode-specific sync
            if self.mode == SyncMode.DOCS_ONLY:
                print("\n[DOCS-ONLY] Parsing complete, no writes performed")

            elif self.mode == SyncMode.DB_ONLY:
                self.sync_to_db(parsed_entries)

            elif self.mode == SyncMode.QDRANT_ONLY:
                if not self.qdrant_host:
                    print("[ERROR] --qdrant-only mode requires Qdrant configuration")
                    print("Set QDRANT_HOST or use --qdrant-host")
                    return 4
                self.sync_to_qdrant(parsed_entries)

            elif self.mode == SyncMode.FULL:
                if not self.qdrant_host:
                    print("[ERROR] --full mode requires Qdrant configuration")
                    print("Set QDRANT_HOST or use --qdrant-host")
                    return 4
                self.sync_to_db(parsed_entries)
                self.sync_to_qdrant(parsed_entries)

            # Print summary
            self._print_summary()

            if self.stats["errors"]:
                return 1

            return 0

        except TimeoutError as e:
            print(f"\n[ERROR] {e}")
            return 3

        except RuntimeError as e:
            print(f"\n[ERROR] {e}")
            return 2

        except KeyboardInterrupt:
            print("\n[CANCELLED] Interrupted by user")
            return 130

        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return 1

        finally:
            # Cleanup
            if self.db_conn:
                self.db_conn.close()

    def _print_summary(self):
        """Print execution summary"""
        elapsed = time.time() - self.start_time

        print(f"\n{'='*80}")
        print("SYNC SUMMARY")
        print(f"{'='*80}")
        print(f"Mode: {self.mode}")
        print(f"Execute: {self.execute}")
        print(f"Total time: {elapsed:.2f}s")
        print(f"\nStatistics:")
        print(f"  Parsed entries: {self.stats['parsed_entries']}")
        print(f"  DB inserts: {self.stats['db_inserts']}")
        print(f"  DB updates: {self.stats['db_updates']}")
        print(f"  Qdrant upserts: {self.stats['qdrant_upserts']}")

        if self.stats["errors"]:
            print(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats["errors"][:10]:  # Limit to first 10
                print(f"  - {error}")
            if len(self.stats["errors"]) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")

        if self.timing and self.timings:
            print(f"\nTiming breakdown:")
            for op, duration in sorted(self.timings.items(), key=lambda x: -x[1]):
                print(f"  {op}: {duration:.2f}s")

        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Sync SOT markdown ledgers to DB/Qdrant indexes (BUILD-163)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run (docs parsing only):
  python scripts/tidy/sot_db_sync.py

  # Sync to database only:
  python scripts/tidy/sot_db_sync.py --db-only --execute

  # Sync to Qdrant only:
  python scripts/tidy/sot_db_sync.py --qdrant-only --execute

  # Full sync (DB + Qdrant):
  python scripts/tidy/sot_db_sync.py --full --execute

  # With custom targets:
  python scripts/tidy/sot_db_sync.py --full --execute \\
      --database-url postgresql://user:pass@host/db \\
      --qdrant-host http://localhost:6333
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--docs-only",
        action="store_const",
        const=SyncMode.DOCS_ONLY,
        dest="mode",
        help="Parse SOT files only, no DB/Qdrant writes (default)"
    )
    mode_group.add_argument(
        "--db-only",
        action="store_const",
        const=SyncMode.DB_ONLY,
        dest="mode",
        help="Sync to database only (no Qdrant)"
    )
    mode_group.add_argument(
        "--qdrant-only",
        action="store_const",
        const=SyncMode.QDRANT_ONLY,
        dest="mode",
        help="Sync to Qdrant only (no database)"
    )
    mode_group.add_argument(
        "--full",
        action="store_const",
        const=SyncMode.FULL,
        dest="mode",
        help="Sync to both database and Qdrant"
    )
    parser.set_defaults(mode=SyncMode.DOCS_ONLY)

    # Write control
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform writes (required for --db-only, --qdrant-only, --full)"
    )

    # Target configuration
    parser.add_argument(
        "--database-url",
        help="Database URL (default: DATABASE_URL env var or sqlite:///autopack.db)"
    )
    parser.add_argument(
        "--qdrant-host",
        help="Qdrant host URL (default: QDRANT_HOST env var or disabled)"
    )

    # Execution control
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=120,
        help="Maximum execution time in seconds (default: 120)"
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        default=True,
        help="Print timing information (default: enabled)"
    )
    parser.add_argument(
        "--no-timing",
        action="store_false",
        dest="timing",
        help="Disable timing information"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output with stack traces"
    )

    args = parser.parse_args()

    # Validation
    if args.mode != SyncMode.DOCS_ONLY and not args.execute:
        parser.error(f"--{args.mode} requires --execute flag")

    # Run sync
    syncer = SOTDBSync(
        mode=args.mode,
        execute=args.execute,
        database_url=args.database_url,
        qdrant_host=args.qdrant_host,
        max_seconds=args.max_seconds,
        timing=args.timing,
        verbose=args.verbose,
    )

    return syncer.run()


if __name__ == "__main__":
    sys.exit(main())
