"""
SOT (Source of Truth) Indexing Helpers

Provides utilities for:
- Chunking SOT markdown files with overlap
- Generating stable chunk IDs
- Extracting metadata (headings, timestamps, etc.)
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def chunk_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk
        overlap_chars: Characters to overlap between chunks

    Returns:
        List of text chunks
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars

        # If this is not the last chunk, try to break at a sentence boundary
        if end < len(text):
            # Look for sentence endings in the last 20% of the chunk
            search_start = int(end * 0.8)
            sentence_end = text.rfind('. ', search_start, end)
            if sentence_end != -1:
                end = sentence_end + 1

        chunks.append(text[start:end])

        # Next chunk starts with overlap
        start = end - overlap_chars

        # Ensure we make progress even with very long sentences
        if start >= end:
            start = end

    return chunks


def extract_heading_from_chunk(chunk: str) -> Optional[str]:
    """
    Extract the first heading from a chunk of text.

    Args:
        chunk: Text chunk

    Returns:
        Heading text without markdown symbols, or None
    """
    lines = chunk.split('\n')
    for line in lines[:10]:  # Check first 10 lines
        # Match markdown headings (### Heading)
        match = re.match(r'^#{1,6}\s+(.+)$', line.strip())
        if match:
            return match.group(1).strip()
    return None


def extract_timestamp_from_chunk(chunk: str) -> Optional[datetime]:
    """
    Extract timestamp from chunk content.

    Looks for patterns like:
    - 2025-01-01
    - 2025-01-01T12:00
    - BUILD-001 | 2025-01-01 | ...

    Args:
        chunk: Text chunk

    Returns:
        Parsed datetime or None
    """
    patterns = [
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})',  # ISO datetime
        r'(\d{4}-\d{2}-\d{2})',               # Date only
    ]

    for pattern in patterns:
        match = re.search(pattern, chunk[:500])  # Check first 500 chars
        if match:
            try:
                date_str = match.group(1)
                if 'T' in date_str:
                    return datetime.fromisoformat(date_str)
                else:
                    return datetime.fromisoformat(f"{date_str}T00:00:00")
            except ValueError:
                continue

    return None


def stable_chunk_id(
    project_id: str,
    sot_file: str,
    chunk_content: str,
    chunk_index: int,
) -> str:
    """
    Generate stable chunk ID from content hash.

    Args:
        project_id: Project identifier
        sot_file: SOT file name (e.g., "BUILD_HISTORY.md")
        chunk_content: Chunk text content
        chunk_index: Chunk index within file

    Returns:
        Stable ID like "sot:autopack:BUILD_HISTORY.md:3f2a91c4:0"
    """
    # Hash chunk content for stability
    content_hash = hashlib.md5(chunk_content.encode()).hexdigest()[:8]

    return f"sot:{project_id}:{sot_file}:{content_hash}:{chunk_index}"


def chunk_sot_file(
    file_path: Path,
    project_id: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[Dict]:
    """
    Chunk an SOT file and generate metadata for each chunk.

    Args:
        file_path: Path to SOT file
        project_id: Project identifier
        max_chars: Maximum characters per chunk
        overlap_chars: Overlap between chunks

    Returns:
        List of dicts with keys: id, content, metadata
    """
    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    sot_file = file_path.name

    # Split into chunks
    text_chunks = chunk_text(content, max_chars, overlap_chars)

    # Build metadata for each chunk
    chunk_docs = []
    for idx, chunk in enumerate(text_chunks):
        chunk_id = stable_chunk_id(project_id, sot_file, chunk, idx)

        # Extract metadata
        heading = extract_heading_from_chunk(chunk)
        timestamp = extract_timestamp_from_chunk(chunk)

        # Calculate content hash (for duplicate detection)
        content_hash = hashlib.md5(chunk.encode()).hexdigest()[:12]

        doc = {
            "id": chunk_id,
            "content": chunk,
            "metadata": {
                "type": "sot",
                "sot_file": sot_file,
                "project_id": project_id,
                "source_path": str(file_path),
                "chunk_id": chunk_id,
                "chunk_index": idx,
                "content_hash": content_hash,
                "heading": heading,
                "created_at": timestamp.isoformat() if timestamp else None,
                "content_preview": chunk[:500],
            }
        }

        chunk_docs.append(doc)

    return chunk_docs
