"""Adaptive Context Budget with Extractive Summarization.

Provides deterministic extractive summarization to fit more context within token budgets.
Uses per-file hash caching to avoid redundant summarization.

Architecture:
- Extractive summarization (deterministic, no LLM):
  - Extract imports section
  - Extract class/function signatures (no bodies)
  - Extract docstrings
  - Extract type annotations
- Per-file hash caching: Cache summaries by file hash + mtime
- Budget allocation strategy:
  - Small files (<500 lines): Full content
  - Medium files (500-2000 lines): Extractive summary
  - Large files (>2000 lines): Signature-only summary
- Token estimation: ~4 chars per token (conservative)

Usage:
    summarizer = ContextSummarizer(cache_dir=Path(".cache/summaries"))
    
    # Summarize single file
    summary = summarizer.summarize_file(
        file_path=Path("src/main.py"),
        max_tokens=1000
    )
    
    # Allocate budget across multiple files
    summaries = summarizer.allocate_budget(
        file_paths=[Path("src/a.py"), Path("src/b.py")],
        total_budget=5000
    )
"""

import ast
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileSummary:
    """Summary of a file's content."""
    file_path: Path
    content: str
    token_count: int
    summary_type: str  # "full", "extractive", "signature_only"
    cache_hit: bool = False


@dataclass
class CacheEntry:
    """Cache entry for file summary."""
    file_hash: str
    mtime: float
    summary: str
    token_count: int
    summary_type: str


class ContextSummarizer:
    """Adaptive context summarizer with extractive summarization."""

    # Size thresholds (lines)
    SMALL_FILE_THRESHOLD = 500
    LARGE_FILE_THRESHOLD = 2000

    # Token estimation (conservative: 4 chars per token)
    CHARS_PER_TOKEN = 4

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize context summarizer.

        Args:
            cache_dir: Directory for summary cache (default: .cache/summaries)
        """
        self.cache_dir = cache_dir or Path(".cache/summaries")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, CacheEntry] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self.cache_dir / "summary_cache.json"
        if not cache_file.exists():
            return

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, entry_data in data.items():
                    self._cache[key] = CacheEntry(**entry_data)
            logger.info(f"[ContextSummarizer] Loaded {len(self._cache)} cache entries")
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Save cache to disk."""
        cache_file = self.cache_dir / "summary_cache.json"
        try:
            data = {
                key: {
                    "file_hash": entry.file_hash,
                    "mtime": entry.mtime,
                    "summary": entry.summary,
                    "token_count": entry.token_count,
                    "summary_type": entry.summary_type,
                }
                for key, entry in self._cache.items()
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to save cache: {e}")

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash of file content.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hash of file content
        """
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to hash {file_path}: {e}")
            return ""

    def _get_cache_key(self, file_path: Path) -> str:
        """Get cache key for file.

        Args:
            file_path: Path to file

        Returns:
            Cache key (file path string)
        """
        return str(file_path.resolve())

    def _check_cache(self, file_path: Path) -> Optional[CacheEntry]:
        """Check if file summary is cached and valid.

        Args:
            file_path: Path to file

        Returns:
            CacheEntry if valid, None otherwise
        """
        cache_key = self._get_cache_key(file_path)
        if cache_key not in self._cache:
            return None

        entry = self._cache[cache_key]

        # Check mtime
        try:
            current_mtime = file_path.stat().st_mtime
            if abs(current_mtime - entry.mtime) > 0.001:  # Allow small float differences
                return None
        except Exception:
            return None

        # Check hash
        current_hash = self._compute_file_hash(file_path)
        if current_hash != entry.file_hash:
            return None

        return entry

    def _update_cache(self, file_path: Path, summary: str, summary_type: str) -> None:
        """Update cache with new summary.

        Args:
            file_path: Path to file
            summary: Summary content
            summary_type: Type of summary
        """
        cache_key = self._get_cache_key(file_path)
        try:
            file_hash = self._compute_file_hash(file_path)
            mtime = file_path.stat().st_mtime
            token_count = self._estimate_tokens(summary)

            self._cache[cache_key] = CacheEntry(
                file_hash=file_hash,
                mtime=mtime,
                summary=summary,
                token_count=token_count,
                summary_type=summary_type,
            )
            self._save_cache()
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to update cache for {file_path}: {e}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text content

        Returns:
            Estimated token count
        """
        return len(text) // self.CHARS_PER_TOKEN

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in file.

        Args:
            file_path: Path to file

        Returns:
            Number of lines
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to count lines in {file_path}: {e}")
            return 0

    def _extract_imports(self, content: str) -> str:
        """Extract import statements from Python code.

        Args:
            content: Python source code

        Returns:
            Import statements
        """
        lines = content.split("\n")
        imports = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                imports.append(line)
            elif imports and not stripped.startswith("#") and stripped:
                # Stop at first non-import, non-comment line
                break
        return "\n".join(imports)

    def _extract_signatures(self, content: str) -> str:
        """Extract class/function signatures from Python code.

        Args:
            content: Python source code

        Returns:
            Signatures with docstrings
        """
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fallback to regex-based extraction
            return self._extract_signatures_regex(content)

        signatures = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Extract class signature
                sig = f"class {node.name}"
                if node.bases:
                    bases = ", ".join(ast.unparse(base) for base in node.bases)
                    sig += f"({bases})"
                sig += ":"
                signatures.append(sig)

                # Extract docstring
                docstring = ast.get_docstring(node)
                if docstring:
                    signatures.append(f'    """\n    {docstring}\n    """')

            elif isinstance(node, ast.FunctionDef):
                # Extract function signature
                args = []
                for arg in node.args.args:
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    args.append(arg_str)

                sig = f"def {node.name}({', '.join(args)})"
                if node.returns:
                    sig += f" -> {ast.unparse(node.returns)}"
                sig += ":"
                signatures.append(sig)

                # Extract docstring
                docstring = ast.get_docstring(node)
                if docstring:
                    signatures.append(f'    """\n    {docstring}\n    """')

        return "\n\n".join(signatures)

    def _extract_signatures_regex(self, content: str) -> str:
        """Extract signatures using regex (fallback for syntax errors).

        Args:
            content: Python source code

        Returns:
            Signatures
        """
        signatures = []
        lines = content.split("\n")

        # Match class/function definitions
        class_pattern = re.compile(r"^(class\s+\w+.*?):")
        func_pattern = re.compile(r"^(def\s+\w+.*?):")
        docstring_pattern = re.compile(r'^\s*"""')

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for class/function definition
            if class_pattern.match(line) or func_pattern.match(line):
                signatures.append(line)

                # Check for docstring on next lines
                j = i + 1
                if j < len(lines) and docstring_pattern.match(lines[j]):
                    # Extract docstring
                    docstring_lines = [lines[j]]
                    j += 1
                    while j < len(lines):
                        docstring_lines.append(lines[j])
                        if '"""' in lines[j] and j > i + 1:
                            break
                        j += 1
                    signatures.append("\n".join(docstring_lines))
                    i = j

            i += 1

        return "\n\n".join(signatures)

    def summarize_file(
        self,
        file_path: Path,
        max_tokens: Optional[int] = None,
    ) -> FileSummary:
        """Summarize a single file.

        Args:
            file_path: Path to file
            max_tokens: Maximum tokens for summary (None = auto-detect)

        Returns:
            FileSummary with content and metadata
        """
        # Check cache
        cache_entry = self._check_cache(file_path)
        if cache_entry:
            logger.debug(f"[ContextSummarizer] Cache hit: {file_path}")
            return FileSummary(
                file_path=file_path,
                content=cache_entry.summary,
                token_count=cache_entry.token_count,
                summary_type=cache_entry.summary_type,
                cache_hit=True,
            )

        # Read file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"[ContextSummarizer] Failed to read {file_path}: {e}")
            return FileSummary(
                file_path=file_path,
                content="",
                token_count=0,
                summary_type="error",
            )

        # Count lines
        line_count = self._count_lines(file_path)

        # Determine summary type
        if line_count < self.SMALL_FILE_THRESHOLD:
            # Small file: use full content
            summary = content
            summary_type = "full"
        elif line_count < self.LARGE_FILE_THRESHOLD:
            # Medium file: extractive summary
            imports = self._extract_imports(content)
            signatures = self._extract_signatures(content)
            summary = f"{imports}\n\n{signatures}"
            summary_type = "extractive"
        else:
            # Large file: signature-only summary
            signatures = self._extract_signatures(content)
            summary = signatures
            summary_type = "signature_only"

        # Apply max_tokens if specified
        token_count = self._estimate_tokens(summary)
        if max_tokens and token_count > max_tokens:
            # Truncate to fit budget
            char_limit = max_tokens * self.CHARS_PER_TOKEN
            summary = summary[:char_limit] + "\n\n# ... (truncated)"
            token_count = max_tokens

        # Update cache
        self._update_cache(file_path, summary, summary_type)

        return FileSummary(
            file_path=file_path,
            content=summary,
            token_count=token_count,
            summary_type=summary_type,
        )

    def allocate_budget(
        self,
        file_paths: List[Path],
        total_budget: int,
    ) -> List[FileSummary]:
        """Allocate token budget across multiple files.

        Args:
            file_paths: List of file paths
            total_budget: Total token budget

        Returns:
            List of FileSummary objects
        """
        if not file_paths:
            return []

        # First pass: summarize all files without budget constraint
        summaries = [self.summarize_file(fp) for fp in file_paths]

        # Calculate total tokens
        total_tokens = sum(s.token_count for s in summaries)

        # If within budget, return as-is
        if total_tokens <= total_budget:
            logger.info(
                f"[ContextSummarizer] Budget allocation: {total_tokens}/{total_budget} tokens "
                f"({len(file_paths)} files)"
            )
            return summaries

        # Budget exceeded: allocate proportionally
        logger.warning(
            f"[ContextSummarizer] Budget exceeded: {total_tokens}/{total_budget} tokens. "
            f"Allocating proportionally."
        )

        # Calculate per-file budget (proportional to original size)
        budget_per_file = [
            int(total_budget * (s.token_count / total_tokens))
            for s in summaries
        ]

        # Re-summarize with budget constraints
        adjusted_summaries = []
        for file_path, budget in zip(file_paths, budget_per_file):
            summary = self.summarize_file(file_path, max_tokens=budget)
            adjusted_summaries.append(summary)

        final_total = sum(s.token_count for s in adjusted_summaries)
        logger.info(
            f"[ContextSummarizer] Budget allocation complete: {final_total}/{total_budget} tokens "
            f"({len(file_paths)} files)"
        )

        return adjusted_summaries

    def clear_cache(self) -> None:
        """Clear summary cache."""
        self._cache.clear()
        cache_file = self.cache_dir / "summary_cache.json"
        if cache_file.exists():
            cache_file.unlink()
        logger.info("[ContextSummarizer] Cache cleared")
