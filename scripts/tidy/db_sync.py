#!/usr/bin/env python3
"""
Database Synchronization for Tidy System

Keeps PostgreSQL and Qdrant in sync with SOT files after tidy runs.

Features:
1. Indexes SOT file content in Qdrant (vector search)
2. Stores structured data in PostgreSQL
3. Cross-validates data across all sources

Note: For README.md SOT summary updates, use scripts/tidy/sot_summary_refresh.py

Usage:
    python scripts/tidy/db_sync.py --project autopack
    python scripts/tidy/db_sync.py --project file-organizer-app-v1
"""

import os
import sys
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import psycopg2

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("[WARN] psycopg2 not available, PostgreSQL sync disabled")

try:
    from autopack.memory.qdrant_store import QdrantStore
    from autopack.memory.embeddings import sync_embed_text

    QDRANT_AVAILABLE = True
except ImportError as e:
    QDRANT_AVAILABLE = False
    print(f"[WARN] Qdrant not available, vector store sync disabled ({e})")


class DatabaseSync:
    """Synchronizes SOT files with PostgreSQL and Qdrant"""

    def __init__(self, project_id: str = "autopack", dry_run: bool = False):
        self.project_id = project_id
        self.dry_run = dry_run

        # Determine project paths
        if project_id == "autopack":
            self.project_dir = REPO_ROOT
        else:
            self.project_dir = REPO_ROOT / ".autonomous_runs" / project_id

        self.docs_dir = self.project_dir / "docs"

        # Database connections
        self.pg_conn = None
        self.qdrant = None

        self._init_databases()

    def _init_databases(self):
        """Initialize database connections"""
        # PostgreSQL
        db_url = os.getenv("DATABASE_URL")
        if db_url and POSTGRES_AVAILABLE:
            try:
                self.pg_conn = psycopg2.connect(db_url)
                self._ensure_tables()
                print("[OK] Connected to PostgreSQL")
            except Exception as e:
                print(f"[WARN] PostgreSQL connection failed: {e}")

        # Qdrant
        qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
        if QDRANT_AVAILABLE:
            try:
                # Parse host and port from URL
                if qdrant_host.startswith("http://"):
                    host = qdrant_host.replace("http://", "").split(":")[0]
                    port = (
                        int(qdrant_host.split(":")[-1])
                        if ":" in qdrant_host.replace("http://", "")
                        else 6333
                    )
                else:
                    host = qdrant_host
                    port = 6333

                self.qdrant = QdrantStore(host=host, port=port)
                print(f"[OK] Connected to Qdrant at {qdrant_host}")
            except Exception as e:
                print(f"[WARN] Qdrant connection failed: {e}")

    def _ensure_tables(self):
        """Ensure PostgreSQL tables exist"""
        if not self.pg_conn:
            return

        cur = self.pg_conn.cursor()

        # SOT entries table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sot_entries (
                id SERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                file_type TEXT NOT NULL,  -- 'build_history', 'architecture', 'debug_log'
                entry_id TEXT,  -- BUILD-001, DECISION-001, etc.
                title TEXT,
                content TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                content_hash TEXT,
                UNIQUE(project_id, file_type, entry_id)
            );
        """)

        # README sync status
        cur.execute("""
            CREATE TABLE IF NOT EXISTS readme_sync (
                id SERIAL PRIMARY KEY,
                project_id TEXT NOT NULL UNIQUE,
                last_synced_at TIMESTAMPTZ NOT NULL,
                last_update_summary TEXT,
                content_hash TEXT
            );
        """)

        # Sync activity log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sync_activity (
                id SERIAL PRIMARY KEY,
                project_id TEXT NOT NULL,
                sync_type TEXT NOT NULL,  -- 'postgres', 'qdrant', 'readme'
                action TEXT NOT NULL,  -- 'insert', 'update', 'delete'
                details JSONB,
                synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        self.pg_conn.commit()
        cur.close()

    def sync_all(self):
        """Run complete synchronization"""
        print(f"\n{'=' * 80}")
        print(f"DATABASE SYNC: {self.project_id}")
        print(f"{'=' * 80}\n")

        results = {"postgres": 0, "qdrant": 0, "readme": False, "validation_errors": []}

        # 1. Sync SOT files to PostgreSQL
        if self.pg_conn:
            results["postgres"] = self._sync_to_postgres()

        # 2. Sync SOT files to Qdrant
        if self.qdrant:
            results["qdrant"] = self._sync_to_qdrant()

        # 3. Cross-validate
        validation_errors = self._cross_validate()
        results["validation_errors"] = validation_errors

        # Summary
        self._print_summary(results)

        return results

    def _sync_to_postgres(self) -> int:
        """Sync SOT files to PostgreSQL"""
        print("Syncing to PostgreSQL...")

        synced_count = 0
        cur = self.pg_conn.cursor()

        # Process each SOT file
        sot_files = {
            "build_history": self.docs_dir / "BUILD_HISTORY.md",
            "architecture": self.docs_dir / "ARCHITECTURE_DECISIONS.md",
            "debug_log": self.docs_dir / "DEBUG_LOG.md",
        }

        for file_type, file_path in sot_files.items():
            if not file_path.exists():
                continue

            entries = self._parse_sot_file(file_path, file_type)

            for entry in entries:
                content_hash = hashlib.md5(entry["content"].encode()).hexdigest()

                # Upsert entry
                cur.execute(
                    """
                    INSERT INTO sot_entries
                    (project_id, file_type, entry_id, title, content, metadata, created_at, updated_at, content_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                    ON CONFLICT (project_id, file_type, entry_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW(),
                        content_hash = EXCLUDED.content_hash
                """,
                    (
                        self.project_id,
                        file_type,
                        entry.get("id"),
                        entry.get("title"),
                        entry["content"],
                        json.dumps(entry.get("metadata", {})),
                        entry.get("created_at", datetime.now()),
                        content_hash,
                    ),
                )

                synced_count += 1

            # Log sync activity
            cur.execute(
                """
                INSERT INTO sync_activity (project_id, sync_type, action, details)
                VALUES (%s, 'postgres', 'sync', %s)
            """,
                (self.project_id, json.dumps({"file_type": file_type, "entries": len(entries)})),
            )

        if not self.dry_run:
            self.pg_conn.commit()

        cur.close()
        print(f"   [OK] Synced {synced_count} entries to PostgreSQL")

        return synced_count

    def _sync_to_qdrant(self) -> int:
        """Sync SOT files to Qdrant vector store"""
        print("Syncing to Qdrant...")

        synced_count = 0
        collection_name = f"{self.project_id}_sot_docs"

        # Ensure collection exists
        try:
            # OpenAI text-embedding-3-small produces 1536-dimensional embeddings
            self.qdrant.ensure_collection(collection_name, size=1536)
        except Exception as e:
            print(f"   [WARN] Could not create collection: {e}")
            return 0

        # Process each SOT file
        sot_files = {
            "build_history": self.docs_dir / "BUILD_HISTORY.md",
            "architecture": self.docs_dir / "ARCHITECTURE_DECISIONS.md",
            "debug_log": self.docs_dir / "DEBUG_LOG.md",
        }

        points = []

        for file_type, file_path in sot_files.items():
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")

            # Create embedding
            try:
                embedding = sync_embed_text(content)
            except Exception as e:
                print(f"   [WARN] Could not create embedding for {file_type}: {e}")
                continue

            # Create point
            point = {
                "id": f"{self.project_id}_{file_type}",
                "vector": embedding,
                "payload": {
                    "project_id": self.project_id,
                    "file_type": file_type,
                    "file_path": str(file_path),
                    "updated_at": datetime.now().isoformat(),
                    "content_preview": content[:500],
                },
            }

            points.append(point)
            synced_count += 1

        # Upsert to Qdrant
        if points and not self.dry_run:
            try:
                self.qdrant.upsert(collection_name, points)
            except Exception as e:
                print(f"   [WARN] Could not upsert to Qdrant: {e}")

        print(f"   [OK] Synced {synced_count} documents to Qdrant")

        return synced_count

    def _parse_sot_file(self, file_path: Path, file_type: str) -> List[Dict]:
        """Parse SOT file and extract entries"""
        entries = []

        if not file_path.exists():
            return entries

        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        # Prefer detailed entry sections when present; fall back to INDEX table parsing.
        current_entry = None

        def _commit_current():
            nonlocal current_entry
            if current_entry:
                entries.append(current_entry)
                current_entry = None

        def _start_entry(entry_id: str, title: str, created_at: Optional[datetime] = None):
            nonlocal current_entry
            _commit_current()
            current_entry = {
                "id": entry_id,
                "title": title,
                "content": title + "\n",
                "created_at": created_at or datetime.now(),
                "metadata": {},
            }

        # Header patterns (current SOT formats)
        build_header = re.compile(r"^(#{2,3})\s+(BUILD-\d+)\b")
        dec_header = re.compile(r"^(#{2,3})\s+(DEC-\d+)\b")
        dbg_header = re.compile(r"^(#{2,3})\s+(DBG-\d+)\b")

        for line in lines:
            # Detect entry headers
            if file_type == "build_history":
                m = build_header.match(line)
                if m:
                    _start_entry(entry_id=m.group(2), title=line)
                    continue
            elif file_type == "architecture":
                m = dec_header.match(line)
                if m:
                    _start_entry(entry_id=m.group(2), title=line)
                    continue
            elif file_type == "debug_log":
                m = dbg_header.match(line)
                if m:
                    _start_entry(entry_id=m.group(2), title=line)
                    continue

            if current_entry:
                current_entry["content"] += line + "\n"

        # Add last entry
        _commit_current()

        # Fallback: parse INDEX table rows if no detailed entries were found.
        if entries:
            return entries

        index_entries = self._parse_sot_index_table(file_path, file_type, lines)
        return index_entries

    def _parse_sot_index_table(
        self, file_path: Path, file_type: str, lines: List[str]
    ) -> List[Dict]:
        """
        Parse INDEX tables for SOT files.

        This is a fallback used when detailed entry sections aren't present or
        are intentionally omitted (e.g., some DBG/BUILD entries may exist only in INDEX).
        """
        entries: List[Dict] = []

        # Find INDEX section
        try:
            idx_start = next(i for i, l in enumerate(lines) if l.strip().startswith("## INDEX"))
        except StopIteration:
            return entries

        # Collect contiguous markdown table rows after INDEX header
        table_rows: List[str] = []
        for l in lines[idx_start + 1 :]:
            s = l.strip()
            if s.startswith("|"):
                # skip separator/header rows but keep data rows
                table_rows.append(s)
                continue
            if table_rows and not s:
                break

        # Drop header + separator if present
        data_rows = []
        for r in table_rows:
            if re.match(r"^\|\s*[-\s:]+\|\s*$", r):
                continue
            if re.search(r"\|\s*Timestamp\s*\|", r) or re.search(r"\|\s*Date\s*\|", r):
                continue
            data_rows.append(r)

        def _parse_date(date_str: str) -> Optional[datetime]:
            try:
                return datetime.strptime(date_str.strip(), "%Y-%m-%d")
            except Exception:
                return None

        for row in data_rows:
            if file_type == "build_history":
                # | 2026-01-02 | BUILD-153 | Title | Description |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(BUILD-\d+)\s*\|\s*([^|]+?)\s*\|\s*(.*)\|\s*$",
                    row,
                )
                if not m:
                    continue
                date_s, bid, title_s, desc = m.groups()
                created_at = _parse_date(date_s)
                title = f"{bid} | {date_s} | {title_s.strip()}"
                content = f"{title}\n\n{desc.strip()}\n"
                entries.append(
                    {
                        "id": bid,
                        "title": title,
                        "content": content,
                        "created_at": created_at or datetime.now(),
                        "metadata": {"source": "index_table", "file": str(file_path)},
                    }
                )
            elif file_type == "architecture":
                # | 2026-01-02 | DEC-016 | Decision | Status | Impact |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DEC-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
                    row,
                )
                if not m:
                    continue
                date_s, did, decision, status, impact = m.groups()
                created_at = _parse_date(date_s)
                title = f"{did} | {date_s} | {decision.strip()} ({status.strip()})"
                content = f"{title}\n\nImpact: {impact.strip()}\n"
                entries.append(
                    {
                        "id": did,
                        "title": title,
                        "content": content,
                        "created_at": created_at or datetime.now(),
                        "metadata": {"source": "index_table", "file": str(file_path)},
                    }
                )
            elif file_type == "debug_log":
                # | 2026-01-01 | DBG-079 | LOW | Summary | Status |
                m = re.match(
                    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DBG-\d+)\s*\|\s*([^|]+?)\s*\|\s*(.*)\|\s*([^|]+?)\s*\|\s*$",
                    row,
                )
                if not m:
                    continue
                date_s, gid, severity, summary, status = m.groups()
                created_at = _parse_date(date_s)
                title = f"{gid} | {date_s} | {severity.strip()} | {status.strip()}"
                content = f"{title}\n\n{summary.strip()}\n"
                entries.append(
                    {
                        "id": gid,
                        "title": title,
                        "content": content,
                        "created_at": created_at or datetime.now(),
                        "metadata": {"source": "index_table", "file": str(file_path)},
                    }
                )

        return entries

    def _cross_validate(self) -> List[str]:
        """Cross-validate data across PostgreSQL, Qdrant, and files"""
        print("Cross-validating data...")

        errors = []

        # Validate PostgreSQL vs Files
        if self.pg_conn:
            cur = self.pg_conn.cursor()
            cur.execute(
                """
                SELECT file_type, COUNT(*)
                FROM sot_entries
                WHERE project_id = %s
                GROUP BY file_type
            """,
                (self.project_id,),
            )

            db_counts = {row[0]: row[1] for row in cur.fetchall()}

            # Compare with file counts
            for file_type, file_path in [
                ("build_history", self.docs_dir / "BUILD_HISTORY.md"),
                ("architecture", self.docs_dir / "ARCHITECTURE_DECISIONS.md"),
                ("debug_log", self.docs_dir / "DEBUG_LOG.md"),
            ]:
                if file_path.exists():
                    file_entries = self._parse_sot_file(file_path, file_type)
                    db_count = db_counts.get(file_type, 0)

                    if len(file_entries) != db_count:
                        error = (
                            f"{file_type}: File has {len(file_entries)} entries, DB has {db_count}"
                        )
                        errors.append(error)
                        print(f"   [WARN] {error}")

            cur.close()

        if not errors:
            print("   [OK] All data sources in sync")

        return errors

    def _print_summary(self, results: Dict):
        """Print sync summary"""
        print(f"\n{'=' * 80}")
        print("SYNC SUMMARY")
        print(f"{'=' * 80}")
        print(f"Project: {self.project_id}")
        print(f"PostgreSQL entries: {results['postgres']}")
        print(f"Qdrant documents: {results['qdrant']}")
        print(f"README updated: {'YES' if results['readme'] else 'NO'}")

        if results["validation_errors"]:
            print("\n[WARN] Validation Errors:")
            for error in results["validation_errors"]:
                print(f"   - {error}")
        else:
            print("\n[OK] All systems in sync!")

        print(f"{'=' * 80}\n")

    def close(self):
        """Close database connections"""
        if self.pg_conn:
            self.pg_conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Sync SOT files to databases")
    parser.add_argument("--project", default="autopack", help="Project ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")

    args = parser.parse_args()

    sync = DatabaseSync(project_id=args.project, dry_run=args.dry_run)

    try:
        results = sync.sync_all()
        return 0 if not results["validation_errors"] else 1
    finally:
        sync.close()


if __name__ == "__main__":
    sys.exit(main())
