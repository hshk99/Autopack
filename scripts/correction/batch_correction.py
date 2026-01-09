#!/usr/bin/env python3
"""
Batch correction tool for multiple file classifications.

This tool allows correcting multiple files at once using pattern matching,
CSV import, or directory-based corrections.
"""

import os
import sys
import csv
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import psycopg2

# Import Qdrant if available
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    from sentence_transformers import SentenceTransformer
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


class BatchCorrector:
    """Batch file classification correction tool."""

    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
        self.embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"

        if not self.db_url:
            print("ERROR: DATABASE_URL environment variable not set")
            sys.exit(1)

        self.conn = psycopg2.connect(self.db_url)
        self.cursor = self.conn.cursor()

        # Initialize Qdrant if available
        self.qdrant_client = None
        self.embedding_model = None
        if QDRANT_AVAILABLE:
            try:
                self.qdrant_client = QdrantClient(url=self.qdrant_host)
                self.embedding_model = SentenceTransformer(self.embedding_model_name)
                print(f"[OK] Connected to Qdrant at {self.qdrant_host}")
            except Exception as e:
                print(f"[WARN] Qdrant unavailable: {e}")

    def correct_by_pattern(self, file_pattern: str, project: str, file_type: str, dry_run: bool = True):
        """Correct all files matching a pattern."""
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Correcting files matching: {file_pattern}")
        print(f"Target: {project}/{file_type}")

        # Find matching files in tidy activity
        self.cursor.execute("""
            SELECT id, project_id, doc_type, src_path, dest_path
            FROM tidy_activity
            WHERE (src_path LIKE %s OR dest_path LIKE %s)
            AND action = 'move'
            ORDER BY created_at DESC
        """, (f"%{file_pattern}%", f"%{file_pattern}%"))

        matches = self.cursor.fetchall()

        if not matches:
            print(f"[INFO] No files found matching pattern: {file_pattern}")
            return 0

        print(f"[INFO] Found {len(matches)} matching files")

        corrected = 0
        for record_id, orig_project, orig_type, src_path, dest_path in matches:
            file_path = dest_path if os.path.exists(dest_path) else src_path
            file_name = os.path.basename(file_path)

            print(f"\n  {file_name}")
            print(f"    Was: {orig_project}/{orig_type}")
            print(f"    Now: {project}/{file_type}")

            if not dry_run:
                self._save_correction(
                    file_path=file_path,
                    original_project=orig_project,
                    original_type=orig_type,
                    corrected_project=project,
                    corrected_type=file_type
                )
                corrected += 1

        if dry_run:
            print(f"\n[DRY-RUN] Would correct {len(matches)} files")
            print("[INFO] Run with --execute to apply corrections")
        else:
            print(f"\n[OK] Corrected {corrected} files")

        return corrected

    def correct_from_csv(self, csv_path: str, dry_run: bool = True):
        """Correct files from CSV file.

        CSV format: file_path,project,type
        """
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Correcting from CSV: {csv_path}")

        if not os.path.exists(csv_path):
            print(f"[ERROR] CSV file not found: {csv_path}")
            return 0

        corrections = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                corrections.append({
                    'file_path': row['file_path'],
                    'project': row['project'],
                    'type': row['type']
                })

        print(f"[INFO] Found {len(corrections)} corrections in CSV")

        corrected = 0
        for corr in corrections:
            file_path = corr['file_path']
            project = corr['project']
            file_type = corr['type']

            # Find original classification
            self.cursor.execute("""
                SELECT project_id, doc_type
                FROM tidy_activity
                WHERE (src_path = %s OR dest_path = %s)
                ORDER BY created_at DESC
                LIMIT 1
            """, (file_path, file_path))

            result = self.cursor.fetchone()
            if not result:
                print(f"  [WARN] File not found in tidy_activity: {os.path.basename(file_path)}")
                continue

            orig_project, orig_type = result

            print(f"\n  {os.path.basename(file_path)}")
            print(f"    Was: {orig_project}/{orig_type}")
            print(f"    Now: {project}/{file_type}")

            if not dry_run:
                self._save_correction(
                    file_path=file_path,
                    original_project=orig_project,
                    original_type=orig_type,
                    corrected_project=project,
                    corrected_type=file_type
                )
                corrected += 1

        if dry_run:
            print(f"\n[DRY-RUN] Would correct {len(corrections)} files")
            print("[INFO] Run with --execute to apply corrections")
        else:
            print(f"\n[OK] Corrected {corrected} files")

        return corrected

    def correct_directory(self, directory: str, project: str, file_type: str, dry_run: bool = True):
        """Correct all files in a directory."""
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Correcting all files in: {directory}")
        print(f"Target: {project}/{file_type}")

        if not os.path.exists(directory):
            print(f"[ERROR] Directory not found: {directory}")
            return 0

        files = list(Path(directory).rglob("*"))
        files = [f for f in files if f.is_file()]

        print(f"[INFO] Found {len(files)} files in directory")

        corrected = 0
        for file_path in files:
            file_path_str = str(file_path)

            # Find original classification
            self.cursor.execute("""
                SELECT project_id, doc_type
                FROM tidy_activity
                WHERE (src_path = %s OR dest_path = %s)
                ORDER BY created_at DESC
                LIMIT 1
            """, (file_path_str, file_path_str))

            result = self.cursor.fetchone()
            if not result:
                continue

            orig_project, orig_type = result

            print(f"\n  {file_path.name}")
            print(f"    Was: {orig_project}/{orig_type}")
            print(f"    Now: {project}/{file_type}")

            if not dry_run:
                self._save_correction(
                    file_path=file_path_str,
                    original_project=orig_project,
                    original_type=orig_type,
                    corrected_project=project,
                    corrected_type=file_type
                )
                corrected += 1

        if dry_run:
            print(f"\n[DRY-RUN] Would correct {len(files)} files")
            print("[INFO] Run with --execute to apply corrections")
        else:
            print(f"\n[OK] Corrected {corrected} files")

        return corrected

    def _save_correction(self, file_path: str, original_project: str, original_type: str,
                        corrected_project: str, corrected_type: str):
        """Save single correction to database and Qdrant."""
        # Read file sample
        content_sample = self._read_file_sample(file_path)

        # Save to PostgreSQL
        self.cursor.execute("""
            INSERT INTO classification_corrections
            (file_path, file_content_sample, original_project, original_type,
             corrected_project, corrected_type, corrected_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (file_path, content_sample, original_project, original_type,
              corrected_project, corrected_type, datetime.now(timezone.utc)))

        self.conn.commit()

        # Save to Qdrant as high-priority pattern
        if self.qdrant_client and self.embedding_model:
            try:
                text_to_embed = f"{os.path.basename(file_path)}\n\n{content_sample}"
                vector = self.embedding_model.encode(text_to_embed, normalize_embeddings=True).tolist()

                self.qdrant_client.upsert(
                    collection_name="file_routing_patterns",
                    points=[
                        PointStruct(
                            id=abs(hash(file_path + str(datetime.now(timezone.utc).timestamp()))),
                            vector=vector,
                            payload={
                                "project_id": corrected_project,
                                "file_type": corrected_type,
                                "example_filename": os.path.basename(file_path),
                                "source_context": "batch_correction",
                                "confidence": 1.0,
                                "corrected_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    ]
                )
            except Exception as e:
                print(f"    [WARN] Could not add to Qdrant: {e}")

    def _read_file_sample(self, file_path: str, max_chars: int = 500) -> str:
        """Read first N characters of file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(max_chars)
        except Exception:
            return ""

    def export_misclassifications(self, output_csv: str, confidence_threshold: float = 0.7):
        """Export potential misclassifications to CSV for batch review."""
        print(f"\nExporting potential misclassifications to: {output_csv}")
        print(f"Confidence threshold: {confidence_threshold}")

        # This would ideally join with classifier confidence scores
        # For now, export recent classifications
        self.cursor.execute("""
            SELECT src_path, project_id, doc_type, dest_path
            FROM tidy_activity
            WHERE action = 'move'
            ORDER BY created_at DESC
            LIMIT 100
        """)

        rows = self.cursor.fetchall()

        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['file_path', 'project', 'type', 'notes'])

            for src_path, project, doc_type, dest_path in rows:
                file_path = dest_path if os.path.exists(dest_path) else src_path
                writer.writerow([file_path, project, doc_type, ''])

        print(f"[OK] Exported {len(rows)} classifications to {output_csv}")
        print("[INFO] Review CSV, update project/type as needed, then import with --csv")

    def close(self):
        """Close database connections."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch file classification correction tool")
    parser.add_argument("--pattern", "-p", help="Correct files matching pattern (e.g., 'fileorg_*.md')")
    parser.add_argument("--project", help="Target project ID")
    parser.add_argument("--type", help="Target file type")
    parser.add_argument("--csv", help="Import corrections from CSV file")
    parser.add_argument("--directory", "-d", help="Correct all files in directory")
    parser.add_argument("--export", "-e", help="Export potential misclassifications to CSV")
    parser.add_argument("--execute", action="store_true", help="Execute corrections (default is dry-run)")

    args = parser.parse_args()

    corrector = BatchCorrector()

    try:
        if args.export:
            corrector.export_misclassifications(args.export)

        elif args.csv:
            corrector.correct_from_csv(args.csv, dry_run=not args.execute)

        elif args.pattern:
            if not args.project or not args.type:
                print("ERROR: --pattern requires --project and --type")
                sys.exit(1)
            corrector.correct_by_pattern(args.pattern, args.project, args.type, dry_run=not args.execute)

        elif args.directory:
            if not args.project or not args.type:
                print("ERROR: --directory requires --project and --type")
                sys.exit(1)
            corrector.correct_directory(args.directory, args.project, args.type, dry_run=not args.execute)

        else:
            print("Usage: python batch_correction.py [options]")
            print("\nOptions:")
            print("  --pattern PATTERN   Correct files matching pattern")
            print("  --project PROJECT   Target project ID")
            print("  --type TYPE         Target file type")
            print("  --csv FILE          Import corrections from CSV")
            print("  --directory DIR     Correct all files in directory")
            print("  --export FILE       Export potential misclassifications to CSV")
            print("  --execute           Execute corrections (default is dry-run)")
            print("\nExamples:")
            print("  # Dry-run: correct all fileorg_*.md files")
            print("  python batch_correction.py --pattern 'fileorg_*.md' --project file-organizer-app-v1 --type plan")
            print("\n  # Execute: correct all files in a directory")
            print("  python batch_correction.py --directory .autonomous_runs/temp --project autopack --type log --execute")
            print("\n  # Export misclassifications for review")
            print("  python batch_correction.py --export misclassified.csv")
            print("\n  # Import corrections from CSV")
            print("  python batch_correction.py --csv corrections.csv --execute")
            sys.exit(1)

    finally:
        corrector.close()


if __name__ == "__main__":
    main()
