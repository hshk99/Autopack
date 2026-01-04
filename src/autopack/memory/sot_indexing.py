"""
SOT (Source of Truth) Indexing Helpers

Provides utilities for:
- Chunking SOT markdown files with overlap
- Generating stable chunk IDs
- Extracting metadata (headings, timestamps, etc.)
- Field-selective JSON embedding
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


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

        # If this is not the last chunk, try to break at a natural boundary
        if end < len(text):
            # Look for boundaries in the last 20% of the chunk (prefer earlier boundaries)
            search_start = int(end * 0.8)

            # Try boundaries in order of preference:
            # 1. Double newline (paragraph break)
            para_break = text.rfind('\n\n', search_start, end)
            if para_break != -1:
                end = para_break + 2

            # 2. Markdown heading
            elif '\n#' in text[search_start:end]:
                heading_pos = text.rfind('\n#', search_start, end)
                if heading_pos != -1:
                    end = heading_pos + 1

            # 3. Sentence endings (. ? !)
            else:
                for boundary in ['. ', '? ', '! ']:
                    boundary_pos = text.rfind(boundary, search_start, end)
                    if boundary_pos != -1:
                        end = boundary_pos + len(boundary)
                        break

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
    # Normalize line endings for Windows-safe hashing
    content = content.replace("\r\n", "\n")
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


def json_to_embedding_text(obj: Any, file_name: str) -> List[Tuple[str, str]]:
    """
    Convert JSON object to embeddable text chunks with field-selective extraction.

    Args:
        obj: Parsed JSON object
        file_name: Name of source file (e.g., "PROJECT_INDEX.json")

    Returns:
        List of (key_path, text) tuples for embedding
    """
    items = []

    if file_name == "PROJECT_INDEX.json":
        # Extract high-signal fields
        if isinstance(obj, dict):
            # Project metadata
            if "project_name" in obj:
                items.append(("project_name", f"Project: {obj['project_name']}"))
            if "description" in obj:
                items.append(("description", f"Description: {obj['description']}"))

            # Setup information
            if "setup" in obj and isinstance(obj["setup"], dict):
                setup = obj["setup"]
                if "commands" in setup and isinstance(setup["commands"], list):
                    items.append(("setup.commands", f"Setup commands: {', '.join(setup['commands'][:10])}"))
                if "dependencies" in setup and isinstance(setup["dependencies"], list):
                    items.append(("setup.dependencies", f"Dependencies: {', '.join(setup['dependencies'][:20])}"))

            # Structure/entrypoints
            if "structure" in obj and isinstance(obj["structure"], dict):
                structure = obj["structure"]
                if "entrypoints" in structure and isinstance(structure["entrypoints"], list):
                    entrypoints_text = ", ".join(structure["entrypoints"][:10])
                    items.append(("structure.entrypoints", f"Entrypoints: {entrypoints_text}"))

            # API summaries
            if "api" in obj and isinstance(obj["api"], dict):
                api = obj["api"]
                if "summary" in api:
                    items.append(("api.summary", f"API: {api['summary']}"))

    elif file_name == "LEARNED_RULES.json":
        # Extract rules (array of rule objects)
        if isinstance(obj, dict) and "rules" in obj and isinstance(obj["rules"], list):
            for idx, rule in enumerate(obj["rules"][:50]):  # Limit to first 50 rules
                if isinstance(rule, dict):
                    rule_id = rule.get("id", f"rule_{idx}")
                    title = rule.get("title", "")
                    rule_text = rule.get("rule", "")
                    when_text = rule.get("when", "")
                    because_text = rule.get("because", "")
                    examples = rule.get("examples", [])

                    # Build compact rule text
                    parts = [f"Rule {rule_id}: {title}"]
                    if rule_text:
                        parts.append(f"Rule: {rule_text[:300]}")
                    if when_text:
                        parts.append(f"When: {when_text[:200]}")
                    if because_text:
                        parts.append(f"Because: {because_text[:200]}")
                    if examples and isinstance(examples, list):
                        examples_text = "; ".join(str(ex)[:100] for ex in examples[:3])
                        parts.append(f"Examples: {examples_text}")

                    items.append((f"rules.{rule_id}", " | ".join(parts)))

        # Fallback for older format (array at root)
        elif isinstance(obj, list):
            for idx, rule in enumerate(obj[:50]):
                if isinstance(rule, dict):
                    rule_id = rule.get("id", f"rule_{idx}")
                    title = rule.get("title", "")
                    rule_text = rule.get("rule", "")
                    parts = [f"Rule {rule_id}: {title}"]
                    if rule_text:
                        parts.append(rule_text[:300])
                    items.append((f"rules.{rule_id}", " | ".join(parts)))

    return items


def chunk_sot_json(
    file_path: Path,
    project_id: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[Dict]:
    """
    Chunk a JSON SOT file with field-selective embedding.

    Args:
        file_path: Path to JSON SOT file
        project_id: Project identifier
        max_chars: Maximum characters per chunk (applies to extracted text)
        overlap_chars: Not used for JSON (each field is independent)

    Returns:
        List of dicts with keys: id, content, metadata
    """
    if not file_path.exists():
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        # Normalize line endings for Windows-safe hashing
        content = content.replace("\r\n", "\n")
        obj = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Log error but don't crash indexing
        return []

    sot_file = file_path.name
    items = json_to_embedding_text(obj, sot_file)

    chunk_docs = []
    for idx, (key_path, text) in enumerate(items):
        # Truncate if needed
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        # Generate stable ID with key path
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        chunk_id = f"sot:{project_id}:{sot_file}:{key_path}:{content_hash}"

        doc = {
            "id": chunk_id,
            "content": text,
            "metadata": {
                "type": "sot",
                "sot_file": sot_file,
                "project_id": project_id,
                "source_path": str(file_path),
                "chunk_id": chunk_id,
                "json_key_path": key_path,
                "chunk_index": idx,
                "content_hash": content_hash,
                "content_preview": text[:500],
            }
        }

        chunk_docs.append(doc)

    return chunk_docs
