#!/usr/bin/env python3
"""Check seed data in PostgreSQL and Qdrant."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import psycopg2
from qdrant_client import QdrantClient


def check_postgresql():
    """Check PostgreSQL routing rules."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set")
        return

    conn = psycopg2.connect(dsn)
    cursor = conn.cursor()

    print("=" * 70)
    print("PostgreSQL Routing Rules")
    print("=" * 70)
    print()

    # Check routing rules
    cursor.execute("""
        SELECT project_id, file_type, content_keywords, destination_path, priority
        FROM directory_routing_rules
        WHERE source_context = 'cursor'
        ORDER BY project_id, priority DESC
    """)

    rows = cursor.fetchall()
    print(f"Total rules: {len(rows)}")
    print()

    current_project = None
    for proj, ftype, keywords, dest, priority in rows:
        if proj != current_project:
            print()
            print(f"--- {proj.upper()} ---")
            current_project = proj

        kw_display = keywords[:70] + "..." if keywords and len(keywords) > 70 else keywords
        print(f"  [{priority}] {ftype:12s} | {kw_display}")

    # Check project config
    print()
    print()
    print("=" * 70)
    print("Project Directory Config")
    print("=" * 70)
    print()

    cursor.execute("""
        SELECT project_id, base_path, runs_path, archive_path
        FROM project_directory_config
        ORDER BY project_id
    """)

    configs = cursor.fetchall()
    for proj, base, runs, archive in configs:
        print(f"{proj}:")
        print(f"  Base:    {base}")
        print(f"  Runs:    {runs}")
        print(f"  Archive: {archive}")
        print()

    cursor.close()
    conn.close()


def check_qdrant():
    """Check Qdrant patterns."""
    qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")

    try:
        client = QdrantClient(url=qdrant_host)

        print()
        print("=" * 70)
        print("Qdrant File Routing Patterns")
        print("=" * 70)
        print()

        # Get collection info
        collection_info = client.get_collection("file_routing_patterns")
        print("Collection: file_routing_patterns")
        print(f"Vectors count: {collection_info.points_count}")
        print(f"Vector dimension: {collection_info.config.params.vectors.size}")
        print()

        # Get all points (scroll through)
        offset = None
        all_points = []

        while True:
            result = client.scroll(
                collection_name="file_routing_patterns",
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            points, next_offset = result
            all_points.extend(points)

            if next_offset is None:
                break
            offset = next_offset

        print(f"Retrieved {len(all_points)} patterns")
        print()

        # Group by project
        by_project = {}
        for point in all_points:
            proj = point.payload.get("project_id")
            if proj not in by_project:
                by_project[proj] = []
            by_project[proj].append(point)

        for proj in sorted(by_project.keys()):
            print(f"--- {proj.upper()} ---")
            for point in by_project[proj]:
                ftype = point.payload.get("file_type")
                fname = point.payload.get("example_filename", "")
                source = point.payload.get("source_context", "")
                conf = point.payload.get("confidence", 0)

                print(f"  {ftype:12s} | {fname:45s} | source={source:15s} conf={conf:.2f}")
            print()

    except Exception as e:
        print(f"ERROR: Could not connect to Qdrant: {e}")


if __name__ == "__main__":
    check_postgresql()
    check_qdrant()
