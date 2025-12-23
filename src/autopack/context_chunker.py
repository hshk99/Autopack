"""
Context Chunker for Large Files (BUILD-125 Phase E)

Provides intelligent chunking of large files for grounded context without
blowing token budgets. Chunks CONTEXT, not SCOPE - scope.paths remain file paths.

Key Features:
- AST-based chunking for Python (class/function boundaries)
- Heuristic chunking for other languages
- Detects minified/generated files
- Stable chunk boundaries (deterministic)
- Hard caps on chunk counts
"""

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# Chunk limits
MAX_CHUNKS_PER_FILE = 50
MAX_CHUNK_LINES = 500
MIN_CHUNK_LINES = 10  # Don't create tiny chunks

# File size thresholds
LARGE_FILE_THRESHOLD_LINES = 1000  # Files > 1000 lines get chunked
MINIFIED_LINE_LENGTH = 500  # Lines > 500 chars suggest minification


@dataclass
class ChunkRef:
    """Reference to a code chunk within a file"""
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str
    kind: str  # "class", "function", "module", "heuristic"
    docstring: Optional[str] = None

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class FileProfile:
    """Metadata about a file for chunking decisions"""
    file_path: str
    size_bytes: int
    line_count: int
    language: str  # "python", "javascript", "typescript", "unknown"
    is_generated: bool
    is_minified: bool
    avg_line_length: float

    def should_chunk(self) -> bool:
        """Determine if file should be chunked"""
        # Don't chunk small files
        if self.line_count < LARGE_FILE_THRESHOLD_LINES:
            return False

        # Don't chunk minified files (useless)
        if self.is_minified:
            return False

        # Don't chunk generated files
        if self.is_generated:
            return False

        return True


class ContextChunker:
    """
    Chunk large files into logical sections for context building.

    Preserves scope.paths as file paths, but provides chunk-level
    summaries for grounded context to stay within token budgets.
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)

    def profile_file(self, file_path: str) -> FileProfile:
        """
        Build file profile for chunking decisions.

        Args:
            file_path: Relative path from workspace

        Returns:
            FileProfile with metadata
        """
        abs_path = self.workspace / file_path

        if not abs_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get basic stats
        size_bytes = abs_path.stat().st_size

        # Read file to analyze
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (UnicodeDecodeError, PermissionError) as e:
            logger.warning(f"Could not read {file_path}: {e}")
            # Return minimal profile for binary/unreadable files
            return FileProfile(
                file_path=file_path,
                size_bytes=size_bytes,
                line_count=0,
                language="unknown",
                is_generated=False,
                is_minified=True,  # Treat unreadable as minified
                avg_line_length=0
            )

        line_count = len(lines)
        avg_line_length = sum(len(line) for line in lines) / line_count if line_count > 0 else 0

        # Detect language
        language = self._detect_language(file_path)

        # Detect generated files
        is_generated = self._is_generated(lines, file_path)

        # Detect minification
        is_minified = self._is_minified(lines, avg_line_length)

        return FileProfile(
            file_path=file_path,
            size_bytes=size_bytes,
            line_count=line_count,
            language=language,
            is_generated=is_generated,
            is_minified=is_minified,
            avg_line_length=avg_line_length
        )

    def chunk_file(
        self,
        file_path: str,
        profile: Optional[FileProfile] = None
    ) -> List[ChunkRef]:
        """
        Chunk file into logical sections.

        Args:
            file_path: Relative path from workspace
            profile: Optional precomputed FileProfile

        Returns:
            List of ChunkRef objects
        """
        if profile is None:
            profile = self.profile_file(file_path)

        # Skip chunking if not needed
        if not profile.should_chunk():
            return []

        abs_path = self.workspace / file_path

        # Read file content
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read {file_path} for chunking: {e}")
            return []

        # Chunk based on language
        if profile.language == "python":
            return self._chunk_python(file_path, content)
        else:
            return self._chunk_heuristic(file_path, content, profile)

    def _chunk_python(self, file_path: str, content: str) -> List[ChunkRef]:
        """
        Chunk Python file using AST.

        Extracts top-level classes and functions with their docstrings.
        """
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"Python syntax error in {file_path}, falling back to heuristic: {e}")
            return self._chunk_heuristic(file_path, content, None)

        chunks = []
        lines = content.split('\n')

        for node in ast.walk(tree):
            # Only top-level classes and functions
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if it's top-level (col_offset == 0)
                if node.col_offset == 0:
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line

                    # Extract docstring
                    docstring = ast.get_docstring(node)

                    # Determine kind
                    if isinstance(node, ast.ClassDef):
                        kind = "class"
                    else:
                        kind = "function"

                    chunks.append(ChunkRef(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        symbol_name=node.name,
                        kind=kind,
                        docstring=docstring
                    ))

        # Sort by start line
        chunks.sort(key=lambda c: c.start_line)

        # Enforce chunk count limit
        if len(chunks) > MAX_CHUNKS_PER_FILE:
            logger.info(
                f"File {file_path} has {len(chunks)} chunks, "
                f"limiting to {MAX_CHUNKS_PER_FILE} largest"
            )
            # Keep largest chunks by line count
            chunks.sort(key=lambda c: c.line_count, reverse=True)
            chunks = chunks[:MAX_CHUNKS_PER_FILE]
            chunks.sort(key=lambda c: c.start_line)

        return chunks

    def _chunk_heuristic(
        self,
        file_path: str,
        content: str,
        profile: Optional[FileProfile]
    ) -> List[ChunkRef]:
        """
        Chunk non-Python files using heuristics.

        Looks for:
        - Class/function declarations (via regex)
        - Blank line boundaries
        - Comment blocks
        """
        lines = content.split('\n')
        chunks = []

        # Regex patterns for common declarations
        class_pattern = re.compile(r'^\s*(class|interface|struct|enum)\s+(\w+)')
        function_pattern = re.compile(r'^\s*(function|def|async\s+function|export\s+function|const\s+\w+\s*=\s*\(.*\)\s*=>)\s*(\w+)?')

        current_chunk_start = None
        current_symbol = None
        current_kind = "heuristic"

        for i, line in enumerate(lines, start=1):
            # Check for class declaration
            class_match = class_pattern.match(line)
            if class_match:
                # Save previous chunk if any
                if current_chunk_start is not None:
                    chunks.append(ChunkRef(
                        file_path=file_path,
                        start_line=current_chunk_start,
                        end_line=i - 1,
                        symbol_name=current_symbol or "unnamed",
                        kind=current_kind
                    ))

                # Start new chunk
                current_chunk_start = i
                current_symbol = class_match.group(2)
                current_kind = "class"
                continue

            # Check for function declaration
            func_match = function_pattern.match(line)
            if func_match:
                # Save previous chunk if any
                if current_chunk_start is not None:
                    chunks.append(ChunkRef(
                        file_path=file_path,
                        start_line=current_chunk_start,
                        end_line=i - 1,
                        symbol_name=current_symbol or "unnamed",
                        kind=current_kind
                    ))

                # Start new chunk
                current_chunk_start = i
                current_symbol = func_match.group(2) if func_match.lastindex >= 2 else "anonymous"
                current_kind = "function"
                continue

        # Save last chunk
        if current_chunk_start is not None:
            chunks.append(ChunkRef(
                file_path=file_path,
                start_line=current_chunk_start,
                end_line=len(lines),
                symbol_name=current_symbol or "unnamed",
                kind=current_kind
            ))

        # If no chunks found, mark as low confidence
        if not chunks:
            logger.debug(f"No heuristic chunks found in {file_path}")
            return []

        # Enforce limits
        if len(chunks) > MAX_CHUNKS_PER_FILE:
            chunks.sort(key=lambda c: c.line_count, reverse=True)
            chunks = chunks[:MAX_CHUNKS_PER_FILE]
            chunks.sort(key=lambda c: c.start_line)

        return chunks

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        suffix = Path(file_path).suffix.lower()

        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.cs': 'csharp',
        }

        return lang_map.get(suffix, 'unknown')

    def _is_generated(self, lines: List[str], file_path: str) -> bool:
        """
        Detect generated files.

        Checks for:
        - "auto-generated" comments in first 20 lines
        - Common generated file patterns
        """
        # Check file name patterns
        name_lower = file_path.lower()
        generated_patterns = [
            '_pb2.py',  # Protocol buffers
            '.generated.',
            'autogenerated',
            '-generated',
        ]

        for pattern in generated_patterns:
            if pattern in name_lower:
                return True

        # Check file content (first 20 lines)
        header = '\n'.join(lines[:20]).lower()

        generated_markers = [
            'auto-generated',
            'autogenerated',
            'do not edit',
            'generated by',
            'code generator',
            '@generated',
        ]

        for marker in generated_markers:
            if marker in header:
                return True

        return False

    def _is_minified(self, lines: List[str], avg_line_length: float) -> bool:
        """
        Detect minified files.

        Characteristics:
        - Very long lines (avg > 500 chars)
        - Few lines but large file size
        """
        if avg_line_length > MINIFIED_LINE_LENGTH:
            return True

        # Check if any single line is extremely long
        for line in lines[:10]:  # Check first 10 lines
            if len(line) > MINIFIED_LINE_LENGTH * 2:
                return True

        return False

    def build_chunk_summary(
        self,
        chunks: List[ChunkRef],
        max_chars: int = 1000
    ) -> str:
        """
        Build a summary of chunks for grounded context.

        Args:
            chunks: List of chunks
            max_chars: Maximum characters for summary

        Returns:
            Formatted summary string
        """
        if not chunks:
            return ""

        lines = []
        current_chars = 0

        for chunk in chunks:
            # Format chunk entry
            entry = f"- {chunk.kind} `{chunk.symbol_name}` (lines {chunk.start_line}-{chunk.end_line})"

            if chunk.docstring:
                # Truncate long docstrings
                doc_preview = chunk.docstring.split('\n')[0][:80]
                entry += f": {doc_preview}"

            entry_len = len(entry) + 1  # +1 for newline

            if current_chars + entry_len > max_chars:
                lines.append(f"... and {len(chunks) - len(lines)} more")
                break

            lines.append(entry)
            current_chars += entry_len

        return '\n'.join(lines)
