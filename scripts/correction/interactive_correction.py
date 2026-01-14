#!/usr/bin/env python3
"""
Interactive CLI for correcting file classifications.

This tool provides a user-friendly interface for reviewing and correcting
misclassified files, with real-time learning feedback to the classification system.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import psycopg2
from datetime import datetime, timezone

# Import Qdrant if available
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    from sentence_transformers import SentenceTransformer

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


class InteractiveCorrector:
    """Interactive file classification correction tool."""

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

    def get_recent_classifications(self, limit: int = 20) -> List[Tuple]:
        """Get recent tidy activity for review."""
        self.cursor.execute(
            """
            SELECT id, project_id, doc_type, src_path, dest_path, created_at
            FROM tidy_activity
            WHERE action = 'move'
            ORDER BY created_at DESC
            LIMIT %s
        """,
            (limit,),
        )

        return self.cursor.fetchall()

    def get_misclassifications(self, limit: int = 20) -> List[Tuple]:
        """Get files that might be misclassified (flagged by auditor or low confidence)."""
        # In a real implementation, this would query an auditor_flags table
        # For now, we'll just get recent moves
        return self.get_recent_classifications(limit)

    def show_classification(self, record: Tuple):
        """Display classification details."""
        record_id, project_id, doc_type, src_path, dest_path, created_at = record

        print("\n" + "=" * 70)
        print(f"Classification ID: {record_id}")
        print(f"Timestamp: {created_at}")
        print("=" * 70)
        print(f"File: {os.path.basename(src_path)}")
        print(f"Source: {src_path}")
        print("Classified as:")
        print(f"  Project: {project_id}")
        print(f"  Type: {doc_type}")
        print(f"Moved to: {dest_path}")
        print("=" * 70)

    def prompt_for_correction(self) -> Optional[Tuple[str, str]]:
        """Prompt user for correct classification."""
        print("\nIs this classification correct?")
        print("1. Yes, correct")
        print("2. No, wrong project")
        print("3. No, wrong type")
        print("4. No, both wrong")
        print("5. Skip this file")
        print("6. Quit")

        choice = input("\nEnter choice (1-6): ").strip()

        if choice == "1":
            return None  # Correct, no action needed

        elif choice == "2":
            project = input("Enter correct project ID: ").strip()
            return (project, None)

        elif choice == "3":
            doc_type = input(
                "Enter correct type (plan/analysis/report/prompt/log/script/unknown): "
            ).strip()
            return (None, doc_type)

        elif choice == "4":
            project = input("Enter correct project ID: ").strip()
            doc_type = input("Enter correct type: ").strip()
            return (project, doc_type)

        elif choice == "5":
            return "skip"

        elif choice == "6":
            return "quit"

        else:
            print("Invalid choice, skipping...")
            return "skip"

    def save_correction(
        self,
        file_path: str,
        content_sample: str,
        original_project: str,
        original_type: str,
        corrected_project: str,
        corrected_type: str,
    ):
        """Save correction to database and Qdrant."""
        # Use original values if not corrected
        final_project = corrected_project or original_project
        final_type = corrected_type or original_type

        # Save to PostgreSQL
        self.cursor.execute(
            """
            INSERT INTO classification_corrections
            (file_path, file_content_sample, original_project, original_type,
             corrected_project, corrected_type, corrected_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
            (
                file_path,
                content_sample,
                original_project,
                original_type,
                final_project,
                final_type,
                datetime.now(timezone.utc),
            ),
        )

        self.conn.commit()
        print("\n[OK] Correction saved to PostgreSQL")

        # Save to Qdrant as high-priority pattern
        if self.qdrant_client and self.embedding_model:
            try:
                text_to_embed = f"{os.path.basename(file_path)}\n\n{content_sample}"
                vector = self.embedding_model.encode(
                    text_to_embed, normalize_embeddings=True
                ).tolist()

                self.qdrant_client.upsert(
                    collection_name="file_routing_patterns",
                    points=[
                        PointStruct(
                            id=abs(hash(file_path + str(datetime.now(timezone.utc).timestamp()))),
                            vector=vector,
                            payload={
                                "project_id": final_project,
                                "file_type": final_type,
                                "example_filename": os.path.basename(file_path),
                                "source_context": "user_correction",
                                "confidence": 1.0,  # User corrections are 100% confident
                                "corrected_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    ],
                )
                print("[OK] Correction added to Qdrant as high-priority pattern")
            except Exception as e:
                print(f"[WARN] Could not add to Qdrant: {e}")

    def read_file_sample(self, file_path: str, max_chars: int = 500) -> str:
        """Read first N characters of file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_chars)
        except Exception:
            return ""

    def interactive_review_loop(self):
        """Main interactive review loop."""
        print("\n" + "=" * 70)
        print("INTERACTIVE CLASSIFICATION CORRECTION TOOL")
        print("=" * 70)
        print("\nFetching recent classifications...")

        records = self.get_recent_classifications(limit=20)

        if not records:
            print("\nNo recent classifications to review.")
            return

        print(f"\nFound {len(records)} recent classifications to review.")

        corrected_count = 0
        skipped_count = 0

        for record in records:
            record_id, project_id, doc_type, src_path, dest_path, created_at = record

            # Skip if file no longer exists
            if not os.path.exists(src_path) and not os.path.exists(dest_path):
                continue

            # Use dest_path if file was moved
            file_path = dest_path if os.path.exists(dest_path) else src_path

            self.show_classification(record)

            # Show file preview
            content_sample = self.read_file_sample(file_path)
            if content_sample:
                print("\nFile Preview (first 200 chars):")
                print("-" * 70)
                print(content_sample[:200])
                if len(content_sample) > 200:
                    print("...")
                print("-" * 70)

            result = self.prompt_for_correction()

            if result == "quit":
                break
            elif result == "skip":
                skipped_count += 1
                continue
            elif result is None:
                # Correct classification, no action needed
                print("[OK] Classification confirmed as correct")
                continue
            else:
                corrected_project, corrected_type = result
                self.save_correction(
                    file_path=file_path,
                    content_sample=content_sample,
                    original_project=project_id,
                    original_type=doc_type,
                    corrected_project=corrected_project,
                    corrected_type=corrected_type,
                )
                corrected_count += 1

        print("\n" + "=" * 70)
        print("REVIEW COMPLETE")
        print("=" * 70)
        print(f"Corrections made: {corrected_count}")
        print(f"Files skipped: {skipped_count}")
        print(f"Files confirmed correct: {len(records) - corrected_count - skipped_count}")

    def batch_review_flagged(self):
        """Review files specifically flagged by the auditor."""
        print("\n" + "=" * 70)
        print("REVIEWING AUDITOR-FLAGGED FILES")
        print("=" * 70)

        # This would query an auditor_flags table if it exists
        # For now, just note the feature
        print("\n[INFO] Auditor flag tracking not yet implemented")
        print("[INFO] Use --interactive to review recent classifications")

    def show_correction_stats(self):
        """Show statistics about corrections."""
        print("\n" + "=" * 70)
        print("CORRECTION STATISTICS")
        print("=" * 70)

        # Check if corrections table exists
        try:
            self.cursor.execute(
                """
                SELECT COUNT(*) FROM classification_corrections
            """
            )
            total = self.cursor.fetchone()[0]

            self.cursor.execute(
                """
                SELECT corrected_project, corrected_type, COUNT(*)
                FROM classification_corrections
                GROUP BY corrected_project, corrected_type
                ORDER BY COUNT(*) DESC
            """
            )

            corrections_by_type = self.cursor.fetchall()

            print(f"\nTotal corrections: {total}")
            print("\nCorrections by project/type:")
            for proj, typ, count in corrections_by_type:
                print(f"  {proj}/{typ}: {count}")

        except Exception as e:
            print(f"\n[WARN] Could not fetch stats: {e}")
            print("[INFO] Corrections table may not exist yet")

    def close(self):
        """Close database connections."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Interactive file classification correction tool")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Start interactive review of recent classifications",
    )
    parser.add_argument(
        "--flagged", "-f", action="store_true", help="Review files flagged by auditor"
    )
    parser.add_argument("--stats", "-s", action="store_true", help="Show correction statistics")

    args = parser.parse_args()

    corrector = InteractiveCorrector()

    try:
        if args.interactive:
            corrector.interactive_review_loop()
        elif args.flagged:
            corrector.batch_review_flagged()
        elif args.stats:
            corrector.show_correction_stats()
        else:
            print("Usage: python interactive_correction.py [--interactive|--flagged|--stats]")
            print("\nOptions:")
            print("  --interactive, -i   Review recent classifications interactively")
            print("  --flagged, -f       Review files flagged by auditor")
            print("  --stats, -s         Show correction statistics")
            sys.exit(1)

    finally:
        corrector.close()


if __name__ == "__main__":
    main()
