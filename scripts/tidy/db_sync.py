#!/usr/bin/env python3
"""
Database Synchronization for Tidy System

Keeps PostgreSQL and Qdrant in sync with SOT files after tidy runs.

Features:
1. Indexes SOT file content in Qdrant (vector search)
2. Stores structured data in PostgreSQL
3. Updates README.md with latest changes
4. Cross-validates data across all sources

Usage:
    python scripts/tidy/db_sync.py --project autopack
    python scripts/tidy/db_sync.py --project file-organizer-app-v1
"""

import os
import sys
import json
import hashlib
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
                    port = int(qdrant_host.split(":")[-1]) if ":" in qdrant_host.replace("http://", "") else 6333
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
        print(f"\n{'='*80}")
        print(f"DATABASE SYNC: {self.project_id}")
        print(f"{'='*80}\n")

        results = {
            "postgres": 0,
            "qdrant": 0,
            "readme": False,
            "validation_errors": []
        }

        # 1. Sync SOT files to PostgreSQL
        if self.pg_conn:
            results["postgres"] = self._sync_to_postgres()

        # 2. Sync SOT files to Qdrant
        if self.qdrant:
            results["qdrant"] = self._sync_to_qdrant()

        # 3. Update README.md
        results["readme"] = self._update_readme()

        # 4. Cross-validate
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
                cur.execute("""
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
                """, (
                    self.project_id,
                    file_type,
                    entry.get("id"),
                    entry.get("title"),
                    entry["content"],
                    json.dumps(entry.get("metadata", {})),
                    entry.get("created_at", datetime.now()),
                    content_hash
                ))

                synced_count += 1

            # Log sync activity
            cur.execute("""
                INSERT INTO sync_activity (project_id, sync_type, action, details)
                VALUES (%s, 'postgres', 'sync', %s)
            """, (self.project_id, json.dumps({"file_type": file_type, "entries": len(entries)})))

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
                    "content_preview": content[:500]
                }
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

    def _update_readme(self) -> bool:
        """Update README.md with latest SOT summary"""
        print("Updating README.md...")

        readme_path = self.project_dir / "README.md"

        if not readme_path.exists():
            print(f"   [WARN] README.md not found at {readme_path}")
            return False

        # Read current README
        content = readme_path.read_text(encoding="utf-8")

        # Generate summary from SOT files
        summary = self._generate_sot_summary()

        # Find or create "Project Status" section
        marker_start = "<!-- SOT_SUMMARY_START -->"
        marker_end = "<!-- SOT_SUMMARY_END -->"

        if marker_start in content and marker_end in content:
            # Replace existing section
            before = content.split(marker_start)[0]
            after = content.split(marker_end)[1]
            new_content = f"{before}{marker_start}\n{summary}\n{marker_end}{after}"
        else:
            # Append new section
            new_content = f"{content}\n\n## Project Status\n\n{marker_start}\n{summary}\n{marker_end}\n"

        # Write updated README
        if not self.dry_run:
            readme_path.write_text(new_content, encoding="utf-8")

            # Log to PostgreSQL
            if self.pg_conn:
                cur = self.pg_conn.cursor()
                content_hash = hashlib.md5(new_content.encode()).hexdigest()
                cur.execute("""
                    INSERT INTO readme_sync (project_id, last_synced_at, last_update_summary, content_hash)
                    VALUES (%s, NOW(), %s, %s)
                    ON CONFLICT (project_id)
                    DO UPDATE SET
                        last_synced_at = NOW(),
                        last_update_summary = EXCLUDED.last_update_summary,
                        content_hash = EXCLUDED.content_hash
                """, (self.project_id, summary[:200], content_hash))
                self.pg_conn.commit()
                cur.close()

        print("   [OK] Updated README.md")

        return True

    def _generate_sot_summary(self) -> str:
        """Generate summary from SOT files"""
        summary_lines = [
            f"**Last Updated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ""
        ]

        # BUILD_HISTORY summary
        build_history = self.docs_dir / "BUILD_HISTORY.md"
        if build_history.exists():
            entries = self._parse_sot_file(build_history, "build_history")
            summary_lines.append(f"- **Builds Completed**: {len(entries)}")
            if entries:
                latest = entries[0]
                summary_lines.append(f"- **Latest Build**: {latest.get('title', 'N/A')}")

        # ARCHITECTURE_DECISIONS summary
        arch_decisions = self.docs_dir / "ARCHITECTURE_DECISIONS.md"
        if arch_decisions.exists():
            entries = self._parse_sot_file(arch_decisions, "architecture")
            summary_lines.append(f"- **Architecture Decisions**: {len(entries)}")

        # DEBUG_LOG summary
        debug_log = self.docs_dir / "DEBUG_LOG.md"
        if debug_log.exists():
            entries = self._parse_sot_file(debug_log, "debug_log")
            summary_lines.append(f"- **Debugging Sessions**: {len(entries)}")

        summary_lines.append(f"\n*Auto-generated by Autopack Tidy System*")

        return "\n".join(summary_lines)

    def _parse_sot_file(self, file_path: Path, file_type: str) -> List[Dict]:
        """Parse SOT file and extract entries"""
        entries = []

        if not file_path.exists():
            return entries

        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        current_entry = None

        for line in lines:
            # Detect entry headers
            if file_type == "build_history" and line.startswith("### BUILD-"):
                if current_entry:
                    entries.append(current_entry)

                # Extract BUILD-ID
                build_id = line.split("|")[0].replace("###", "").strip()
                current_entry = {
                    "id": build_id,
                    "title": line,
                    "content": line + "\n",
                    "created_at": datetime.now(),
                    "metadata": {}
                }
            elif file_type == "architecture" and line.startswith("## DECISION-"):
                if current_entry:
                    entries.append(current_entry)

                decision_id = line.split(":")[0].replace("##", "").strip()
                current_entry = {
                    "id": decision_id,
                    "title": line,
                    "content": line + "\n",
                    "created_at": datetime.now(),
                    "metadata": {}
                }
            elif file_type == "debug_log" and line.startswith("## DEBUG-"):
                if current_entry:
                    entries.append(current_entry)

                debug_id = line.split("|")[0].replace("##", "").strip()
                current_entry = {
                    "id": debug_id,
                    "title": line,
                    "content": line + "\n",
                    "created_at": datetime.now(),
                    "metadata": {}
                }
            elif current_entry:
                current_entry["content"] += line + "\n"

        # Add last entry
        if current_entry:
            entries.append(current_entry)

        return entries

    def _cross_validate(self) -> List[str]:
        """Cross-validate data across PostgreSQL, Qdrant, and files"""
        print("Cross-validating data...")

        errors = []

        # Validate PostgreSQL vs Files
        if self.pg_conn:
            cur = self.pg_conn.cursor()
            cur.execute("""
                SELECT file_type, COUNT(*)
                FROM sot_entries
                WHERE project_id = %s
                GROUP BY file_type
            """, (self.project_id,))

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
                        error = f"{file_type}: File has {len(file_entries)} entries, DB has {db_count}"
                        errors.append(error)
                        print(f"   [WARN] {error}")

            cur.close()

        if not errors:
            print("   [OK] All data sources in sync")

        return errors

    def _print_summary(self, results: Dict):
        """Print sync summary"""
        print(f"\n{'='*80}")
        print("SYNC SUMMARY")
        print(f"{'='*80}")
        print(f"Project: {self.project_id}")
        print(f"PostgreSQL entries: {results['postgres']}")
        print(f"Qdrant documents: {results['qdrant']}")
        print(f"README updated: {'YES' if results['readme'] else 'NO'}")

        if results['validation_errors']:
            print("\n[WARN] Validation Errors:")
            for error in results['validation_errors']:
                print(f"   - {error}")
        else:
            print("\n[OK] All systems in sync!")

        print(f"{'='*80}\n")

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
        return 0 if not results['validation_errors'] else 1
    finally:
        sync.close()


if __name__ == "__main__":
    sys.exit(main())
