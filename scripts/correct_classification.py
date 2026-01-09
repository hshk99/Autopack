#!/usr/bin/env python3
"""
User feedback tool for correcting misclassifications.

This script allows users to:
1. Review files that were classified
2. Correct misclassifications
3. Store corrections to improve future accuracy
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Repo root detection for dynamic paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import psycopg2
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    print(f"Error: {e}")
    print("Please install: pip install psycopg2 qdrant-client sentence-transformers")
    sys.exit(1)


def create_correction_table(dsn: str):
    """Create table to store user corrections if it doesn't exist."""
    conn = psycopg2.connect(dsn)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classification_corrections (
            id SERIAL PRIMARY KEY,
            file_path TEXT NOT NULL,
            file_content_sample TEXT,

            -- Original classification
            original_project TEXT,
            original_type TEXT,
            original_confidence FLOAT,

            -- Corrected classification
            corrected_project TEXT NOT NULL,
            corrected_type TEXT NOT NULL,

            -- Metadata
            correction_reason TEXT,
            corrected_by TEXT DEFAULT 'user',
            corrected_at TIMESTAMPTZ DEFAULT NOW(),

            -- For deduplication
            UNIQUE(file_path, corrected_project, corrected_type)
        );

        CREATE INDEX IF NOT EXISTS idx_corrections_original
            ON classification_corrections(original_project, original_type);

        CREATE INDEX IF NOT EXISTS idx_corrections_corrected
            ON classification_corrections(corrected_project, corrected_type);
    """)

    conn.commit()
    cursor.close()
    conn.close()


def add_correction(
    dsn: str,
    file_path: str,
    content_sample: str,
    original_project: str,
    original_type: str,
    original_confidence: float,
    corrected_project: str,
    corrected_type: str,
    reason: str = None
):
    """Store a user correction in PostgreSQL."""

    conn = psycopg2.connect(dsn)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO classification_corrections (
            file_path, file_content_sample,
            original_project, original_type, original_confidence,
            corrected_project, corrected_type,
            correction_reason
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (file_path, corrected_project, corrected_type)
        DO UPDATE SET
            original_confidence = EXCLUDED.original_confidence,
            correction_reason = EXCLUDED.correction_reason,
            corrected_at = NOW()
    """, (
        file_path, content_sample,
        original_project, original_type, original_confidence,
        corrected_project, corrected_type,
        reason
    ))

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[OK] Correction stored: {file_path}")
    print(f"     {original_project}/{original_type} -> {corrected_project}/{corrected_type}")


def update_qdrant_with_correction(
    qdrant_host: str,
    embedding_model_name: str,
    file_path: str,
    content_sample: str,
    corrected_project: str,
    corrected_type: str,
    destination_path: str
):
    """Update Qdrant with the corrected classification as a high-priority pattern."""

    client = QdrantClient(url=qdrant_host)
    model = SentenceTransformer(embedding_model_name)

    # Create embedding
    text = f"{Path(file_path).name}\n\n{content_sample}"
    vector = model.encode(text, normalize_embeddings=True).tolist()

    # Create point ID from hash
    import hashlib
    file_hash = hashlib.sha256(f"{file_path}_{corrected_project}_{corrected_type}".encode()).hexdigest()[:16]
    point_id = int(file_hash, 16) % (2**63)

    from qdrant_client.http.models import PointStruct

    # Store with high priority (marked as "user_corrected")
    client.upsert(
        collection_name="file_routing_patterns",
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "project_id": corrected_project,
                    "file_type": corrected_type,
                    "example_filename": Path(file_path).name,
                    "example_content": content_sample[:500],
                    "destination_path": destination_path,
                    "source_context": "user_corrected",  # High priority
                    "confidence": 1.0,  # User corrections are 100% confident
                    "corrected_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        ]
    )

    print("[OK] Qdrant pattern updated with user correction")


def interactive_correction():
    """Interactive mode for correcting classifications."""

    print("=== Classification Correction Tool ===\n")

    # Get file info
    file_path = input("File path that was misclassified: ").strip()
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        return

    # Read content sample
    try:
        content_sample = Path(file_path).read_text(encoding="utf-8", errors="ignore")[:500]
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print(f"\nFile: {file_path}")
    print(f"Content preview: {content_sample[:200]}...")

    # Get original classification
    print("\n--- Original Classification ---")
    original_project = input("Original project (e.g., autopack, file-organizer-app-v1): ").strip()
    original_type = input("Original type (e.g., plan, analysis, log): ").strip()
    original_confidence = float(input("Original confidence (0.0-1.0): ").strip() or "0.5")

    # Get corrected classification
    print("\n--- Correct Classification ---")
    corrected_project = input("Correct project: ").strip()
    corrected_type = input("Correct type: ").strip()
    reason = input("Reason for correction (optional): ").strip() or None

    # Determine destination
    if corrected_project == "autopack":
        destination_path = str(REPO_ROOT / "archive" / f"{corrected_type}s" / Path(file_path).name)
    else:
        destination_path = str(REPO_ROOT / ".autonomous_runs" / corrected_project / "archive" / f"{corrected_type}s" / Path(file_path).name)

    # Confirm
    print("\n--- Confirmation ---")
    print(f"File: {file_path}")
    print(f"Original: {original_project}/{original_type} (confidence={original_confidence})")
    print(f"Correct:  {corrected_project}/{corrected_type}")
    print(f"Destination: {destination_path}")
    confirm = input("\nStore this correction? (y/n): ").strip().lower()

    if confirm != 'y':
        print("Cancelled.")
        return

    # Store correction
    dsn = os.getenv("DATABASE_URL")
    qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    if dsn:
        create_correction_table(dsn)
        add_correction(
            dsn, file_path, content_sample,
            original_project, original_type, original_confidence,
            corrected_project, corrected_type,
            reason
        )

        # Update Qdrant
        try:
            update_qdrant_with_correction(
                qdrant_host, embedding_model,
                file_path, content_sample,
                corrected_project, corrected_type,
                destination_path
            )
        except Exception as e:
            print(f"Warning: Could not update Qdrant: {e}")

        print("\n[SUCCESS] Correction stored and will improve future classifications!")
    else:
        print("Error: DATABASE_URL not set")


def show_corrections(dsn: str, limit: int = 20):
    """Show recent corrections."""

    conn = psycopg2.connect(dsn)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            file_path,
            original_project, original_type, original_confidence,
            corrected_project, corrected_type,
            correction_reason,
            corrected_at
        FROM classification_corrections
        ORDER BY corrected_at DESC
        LIMIT %s
    """, (limit,))

    rows = cursor.fetchall()

    print(f"=== Recent Corrections ({len(rows)}) ===\n")

    for row in rows:
        file_path, orig_proj, orig_type, orig_conf, corr_proj, corr_type, reason, corr_at = row
        print(f"File: {Path(file_path).name}")
        print(f"  Original: {orig_proj}/{orig_type} (confidence={orig_conf:.2f})")
        print(f"  Correct:  {corr_proj}/{corr_type}")
        if reason:
            print(f"  Reason: {reason}")
        print(f"  When: {corr_at}")
        print()

    cursor.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Correct misclassifications and improve accuracy")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive correction mode")
    parser.add_argument("--show", "-s", action="store_true", help="Show recent corrections")
    parser.add_argument("--limit", type=int, default=20, help="Number of corrections to show")

    args = parser.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Error: DATABASE_URL environment variable not set")
        sys.exit(1)

    if args.show:
        show_corrections(dsn, args.limit)
    elif args.interactive:
        interactive_correction()
    else:
        print("Usage:")
        print("  Interactive mode: python correct_classification.py --interactive")
        print("  Show corrections: python correct_classification.py --show")


if __name__ == "__main__":
    main()
