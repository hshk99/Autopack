#!/usr/bin/env python3
"""
Initialize Qdrant collection for file routing patterns.

This script:
1. Creates the file_routing_patterns collection in Qdrant
2. Seeds it with example patterns for Autopack and File Organizer projects
3. Uses sentence-transformers for semantic embeddings
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams, PointStruct
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    print(f"Error: {e}")
    print("Please install required packages:")
    print("  pip install qdrant-client sentence-transformers")
    sys.exit(1)


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client from environment variables."""
    qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    print(f"Connecting to Qdrant at: {qdrant_host}")

    if qdrant_api_key:
        return QdrantClient(url=qdrant_host, api_key=qdrant_api_key)
    else:
        return QdrantClient(url=qdrant_host)


def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 384):
    """Create or recreate the file routing patterns collection."""
    try:
        # Check if collection exists
        try:
            client.get_collection(collection_name)
            print(f"Collection '{collection_name}' already exists. Recreating...")
            client.delete_collection(collection_name)
        except Exception:
            print(f"Creating new collection '{collection_name}'...")

        # Create collection with 384-dimensional vectors (sentence-transformers/all-MiniLM-L6-v2)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

        print(f"✓ Collection created successfully (vector_size={vector_size})")

    except Exception as e:
        print(f"Error creating collection: {e}")
        raise


def get_seed_patterns() -> List[Dict[str, Any]]:
    """Get seed patterns for both Autopack and File Organizer projects."""

    patterns = [
        # ==================== AUTOPACK PROJECT PATTERNS ====================
        {
            "project_id": "autopack",
            "file_type": "plan",
            "example_filename": "IMPLEMENTATION_PLAN_MEMORY_SYSTEM.md",
            "example_content": """# Implementation Plan: Memory & Context System

## Goal
Implement a comprehensive memory and context management system for Autopack that enables:
- Long-term memory storage across runs
- Context-aware decision making
- Learning from past successes and failures

## Approach
1. Design vector database schema for memory storage
2. Implement context retrieval using semantic similarity
3. Add memory persistence layer
""",
            "keywords": ["plan", "implementation", "design", "roadmap", "strategy", "architecture"],
            "destination_path": str(REPO_ROOT / "archive" / "plans"),
            "source_context": "cursor",
        },
        {
            "project_id": "autopack",
            "file_type": "analysis",
            "example_filename": "ANALYSIS_PERFORMANCE_REVIEW.md",
            "example_content": """# Performance Analysis

## Findings
After reviewing the system performance metrics, we found several bottlenecks:
1. Database query inefficiencies
2. Excessive API calls
3. Lack of caching

## Recommendations
- Implement query optimization
- Add request batching
- Deploy Redis caching layer
""",
            "keywords": [
                "analysis",
                "review",
                "findings",
                "retrospective",
                "postmortem",
                "assessment",
            ],
            "destination_path": str(REPO_ROOT / "archive" / "analysis"),
            "source_context": "cursor",
        },
        {
            "project_id": "autopack",
            "file_type": "prompt",
            "example_filename": "PROMPT_DELEGATION_TASK_X.md",
            "example_content": """# Delegation Prompt

## Task
Please implement the following feature:

## Requirements
- Must be compatible with existing API
- Should include comprehensive tests
- Document all public methods

## Context
This task relates to the memory system implementation.
""",
            "keywords": ["prompt", "delegation", "instruction", "task"],
            "destination_path": str(REPO_ROOT / "archive" / "prompts"),
            "source_context": "cursor",
        },
        {
            "project_id": "autopack",
            "file_type": "log",
            "example_filename": "api_server_test.log",
            "example_content": """[2025-12-11 10:30:00] INFO: Starting API server on port 8100
[2025-12-11 10:30:01] INFO: Connected to database
[2025-12-11 10:30:02] DEBUG: Loading configuration
[2025-12-11 10:30:03] INFO: Server ready
""",
            "keywords": ["log", "diagnostic", "trace", "debug", "error"],
            "destination_path": str(REPO_ROOT / "archive" / "logs"),
            "source_context": "cursor",
        },
        # ==================== FILE ORGANIZER PROJECT PATTERNS ====================
        {
            "project_id": "file-organizer-app-v1",
            "file_type": "plan",
            "example_filename": "IMPLEMENTATION_PLAN_COUNTRY_PACKS.md",
            "example_content": """# Implementation Plan: Country Packs

## Goal
Add UK, Canada, and Australia country packs to the file organizer application with:
- Country-specific folder structures
- Localized naming conventions
- Tax document categories

## Approach
1. Define country-specific schemas
2. Implement backend country detection
3. Create frontend country selector
4. Add tests for each country
""",
            "keywords": ["plan", "implementation", "design", "feature", "country pack"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/plans",
            "source_context": "cursor",
        },
        {
            "project_id": "file-organizer-app-v1",
            "file_type": "analysis",
            "example_filename": "ANALYSIS_DOCKER_BUILD_FAILURE.md",
            "example_content": """# Docker Build Failure Analysis

## Issue
Docker build failing with error: "unable to find image locally"

## Investigation
1. Checked Dockerfile syntax - OK
2. Verified base image exists - FAILED
3. Found issue: wrong registry

## Solution
Update Dockerfile to use correct base image from Docker Hub.
""",
            "keywords": ["analysis", "review", "diagnostic", "investigation", "failure"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/analysis",
            "source_context": "cursor",
        },
        {
            "project_id": "file-organizer-app-v1",
            "file_type": "report",
            "example_filename": "CONSOLIDATED_BUILD_PROGRESS.md",
            "example_content": """# Build Progress Report

## Summary
Completed Phase 2 build with following achievements:
- ✓ Backend API endpoints (8/8)
- ✓ Frontend components (12/15)
- ⚠ Integration tests (pending)

## Next Steps
1. Complete remaining frontend components
2. Write integration tests
3. Deploy to staging
""",
            "keywords": ["report", "summary", "consolidated", "progress", "status"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/reports",
            "source_context": "cursor",
        },
        {
            "project_id": "file-organizer-app-v1",
            "file_type": "diagnostic",
            "example_filename": "DIAGNOSTIC_FRONTEND_BUILD.md",
            "example_content": """# Frontend Build Diagnostic

## Error Trace
```
ERROR in ./src/components/CountrySelector.tsx
Module not found: Can't resolve 'react-select'
```

## Debug Steps
1. Check package.json - react-select not listed
2. Verify node_modules - package missing
3. Run npm install react-select --save

## Resolution
Package was missing from dependencies. Added to package.json.
""",
            "keywords": ["diagnostic", "trace", "debug", "troubleshoot"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/diagnostics",
            "source_context": "cursor",
        },
        {
            "project_id": "file-organizer-app-v1",
            "file_type": "script",
            "example_filename": "create_fileorg_country_runs.py",
            "example_content": """#!/usr/bin/env python3
# Script to create country-specific fileorg runs

import requests
from datetime import datetime

def create_run(country: str):
    run_id = f"fileorg-country-{country}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Call API to create run
    response = requests.post(
        "http://localhost:8100/api/runs",
        json={"run_id": run_id, "country": country}
    )

    return response.json()

if __name__ == "__main__":
    for country in ["uk", "canada", "australia"]:
        print(f"Creating run for {country}...")
        result = create_run(country)
        print(f"  Created: {result['run_id']}")
""",
            "keywords": ["script", "utility", "automation", "fileorg"],
            "destination_path": ".autonomous_runs/file-organizer-app-v1/archive/scripts/utility",
            "source_context": "cursor",
        },
    ]

    return patterns


def seed_patterns(client: QdrantClient, model: SentenceTransformer, collection_name: str):
    """Seed the collection with example patterns."""

    patterns = get_seed_patterns()
    points = []

    print(f"\nSeeding {len(patterns)} patterns...")

    for idx, pattern in enumerate(patterns):
        # Create text for embedding: filename + content
        text_to_embed = f"{pattern['example_filename']}\n\n{pattern['example_content']}"

        # Generate embedding
        vector = model.encode(text_to_embed, normalize_embeddings=True).tolist()

        # Create point
        point = PointStruct(
            id=idx + 1,
            vector=vector,
            payload={
                "project_id": pattern["project_id"],
                "file_type": pattern["file_type"],
                "example_filename": pattern["example_filename"],
                "example_content": pattern["example_content"][:500],  # Truncate for storage
                "keywords": pattern["keywords"],
                "destination_path": pattern["destination_path"],
                "source_context": pattern["source_context"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        points.append(point)

        print(
            f"  [{idx + 1}/{len(patterns)}] {pattern['project_id']:25s} | {pattern['file_type']:10s} | {pattern['example_filename']}"
        )

    # Upload points to Qdrant
    print(f"\nUploading {len(points)} points to Qdrant...")
    client.upsert(collection_name=collection_name, points=points)

    print(f"✓ Seeded {len(points)} patterns successfully")


def verify_collection(client: QdrantClient, collection_name: str):
    """Verify the collection was created and seeded correctly."""

    try:
        collection_info = client.get_collection(collection_name)
        print("\n=== Collection Info ===")
        print(f"  Name: {collection_info.config.params.vectors.size} dimensions")
        print(f"  Vectors: {collection_info.vectors_count} patterns")
        print(f"  Distance: {collection_info.config.params.vectors.distance}")

        # Test search
        print("\n=== Test Search ===")
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        test_queries = [
            "IMPLEMENTATION_PLAN_FEATURE.md with implementation strategy",
            "fileorg country pack analysis document",
            "autopack tidy workspace script",
        ]

        for query in test_queries:
            query_vector = model.encode(query, normalize_embeddings=True).tolist()
            results = client.query_points(
                collection_name=collection_name, query=query_vector, limit=2
            ).points

            print(f"\n  Query: '{query}'")
            for result in results:
                payload = result.payload
                print(
                    f"    [{result.score:.3f}] {payload['project_id']:25s} | {payload['file_type']:10s} | {payload['example_filename']}"
                )

        print("\n✓ Collection verification complete")

    except Exception as e:
        print(f"Error verifying collection: {e}")
        raise


def main():
    """Main initialization function."""

    print("=== Initializing File Routing Patterns Collection ===\n")

    # Check environment
    qdrant_host = os.getenv("QDRANT_HOST", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    collection_name = "file_routing_patterns"

    print("Configuration:")
    print(f"  Qdrant Host: {qdrant_host}")
    print(f"  Embedding Model: {embedding_model}")
    print(f"  Collection: {collection_name}")
    print()

    try:
        # Initialize clients
        print("Loading embedding model...")
        model = SentenceTransformer(embedding_model)
        print(f"✓ Model loaded (embedding dimension: {model.get_sentence_embedding_dimension()})")

        print("\nConnecting to Qdrant...")
        client = get_qdrant_client()
        print("✓ Connected to Qdrant")

        # Create collection
        print()
        create_collection(
            client, collection_name, vector_size=model.get_sentence_embedding_dimension()
        )

        # Seed patterns
        seed_patterns(client, model, collection_name)

        # Verify
        verify_collection(client, collection_name)

        print("\n" + "=" * 60)
        print("✓✓✓ INITIALIZATION COMPLETE ✓✓✓")
        print("=" * 60)
        print(f"\nThe '{collection_name}' collection is ready for use.")
        print("\nTo use in tidy_workspace.py:")
        print(f"  export QDRANT_HOST={qdrant_host}")
        print(f"  export EMBEDDING_MODEL={embedding_model}")
        print("  python scripts/tidy_workspace.py --root . --dry-run --verbose")

    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
