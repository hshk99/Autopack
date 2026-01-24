"""Context Engineering - JIT (Just-In-Time) Loading

Following GPT's recommendation: Simple heuristics-based context selection
to reduce token usage by 40-60% while maintaining phase success rates.

Phase 1 Enhancement: Added ranking heuristics from chatbot_project
- Relevance scoring (keyword/path matching)
- Recency scoring (git history, mtime)
- Type priority scoring (tests > core > misc)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
import re
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextSelector:
    """
    Select minimal context for each phase using simple heuristics.

    Philosophy: Load only what's needed, when it's needed.
    Measure token counts and success rates to validate effectiveness.
    """

    def __init__(self, repo_root: Path):
        """
        Initialize context selector.

        Args:
            repo_root: Repository root directory
        """
        self.root = repo_root

        # File categories by task type
        self.category_patterns = {
            "backend": ["src/**/*.py", "config/**/*.yaml", "requirements.txt"],
            "frontend": ["src/**/frontend/**/*", "src/**/*.tsx", "src/**/*.jsx", "package.json"],
            "database": ["src/**/models.py", "src/**/database.py", "alembic/**/*", "*.sql"],
            "api": ["src/**/main.py", "src/**/routes/**/*", "src/**/*_schemas.py"],
            "tests": ["tests/**/*.py", "pytest.ini", "conftest.py"],
            "docs": ["docs/**/*.md", "README.md", "*.md"],
            "config": ["config/**/*", "*.yaml", "*.json", ".env.example"],
        }

    def get_context_for_phase(
        self,
        phase_spec: Dict,
        changed_files: Optional[List[str]] = None,
        token_budget: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Get minimal context for a phase using simple heuristics + ranking.

        Args:
            phase_spec: Phase specification with task_category, complexity, description
            changed_files: Recently changed files (from git diff or previous phases)
            token_budget: Optional token limit for context

        Returns:
            Dict mapping file paths to their contents (ranked and limited)
        """
        # NEW: Check for scope configuration (GPT recommendation)
        scope_config = phase_spec.get("scope") or {}
        scope_paths = scope_config.get("paths", [])
        readonly_context = scope_config.get("read_only_context", [])

        # If scope is defined, use scoped context loading
        if scope_paths:
            return self._build_scoped_context(
                scope_paths, readonly_context, token_budget, phase_spec
            )

        # Fallback: Original heuristic-based loading for backward compatibility
        context = {}
        task_category = phase_spec.get("task_category", "general")
        complexity = phase_spec.get("complexity", "medium")
        description = phase_spec.get("description", "")

        # 1. Always include: Global configs (small, high-value)
        context.update(self._get_global_configs())

        # 2. Category-specific files
        context.update(self._get_category_files(task_category))

        # 3. Recently changed files (high relevance)
        if changed_files:
            context.update(self._get_files_by_paths(changed_files))

        # 4. Description-based heuristics (keywords → relevant files)
        context.update(self._get_files_from_keywords(description))

        # 5. For high complexity, add architecture docs
        if complexity == "high":
            context.update(self._get_architecture_docs())

        # 6. Rank files and apply token budget (Phase 1 enhancement)
        if token_budget:
            context = self._rank_and_limit_context(context, phase_spec, token_budget)

        return context

    def _get_global_configs(self) -> Dict[str, str]:
        """Get always-included config files (small, high-value)"""
        config_files = [
            ".autopack/config.yaml",
            "config/models.yaml",
            "pyproject.toml",
            "requirements.txt",
        ]

        return self._get_files_by_paths(config_files)

    def _get_category_files(self, task_category: str) -> Dict[str, str]:
        """Get files relevant to task category"""
        # Map task categories to file categories
        category_map = {
            "general": ["backend"],
            "tests": ["tests"],
            "docs": ["docs"],
            "external_feature_reuse": ["backend", "config"],
            "security_auth_change": ["backend", "database"],
            "schema_contract_change": ["database", "api"],
        }

        file_categories = category_map.get(task_category, ["backend"])
        files = {}

        for cat in file_categories:
            patterns = self.category_patterns.get(cat, [])
            for pattern in patterns:
                files.update(self._get_files_by_glob(pattern))

        return files

    def _get_files_by_paths(self, paths: List[str]) -> Dict[str, str]:
        """Load specific files by path"""
        files = {}

        for path_str in paths:
            path = self.root / path_str
            if path.exists() and path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                    files[str(path.relative_to(self.root))] = content
                except PermissionError as e:
                    logger.warning("Permission denied reading %s: %s", path, e)
                except UnicodeDecodeError as e:
                    logger.debug("Unicode decode error reading %s: %s", path, e)
                except OSError as e:
                    logger.error("OS error reading %s: %s", path, e)

        return files

    def _get_files_by_glob(self, pattern: str, max_files: int = 20) -> Dict[str, str]:
        """Load files matching glob pattern"""
        files = {}
        count = 0

        try:
            for path in self.root.glob(pattern):
                if path.is_file() and count < max_files:
                    try:
                        content = path.read_text(encoding="utf-8")
                        files[str(path.relative_to(self.root))] = content
                        count += 1
                    except PermissionError as e:
                        logger.warning("Permission denied reading %s: %s", path, e)
                    except UnicodeDecodeError as e:
                        logger.debug("Unicode decode error reading %s: %s", path, e)
                    except OSError as e:
                        logger.error("OS error reading %s: %s", path, e)
        except OSError as e:
            logger.error("OS error during glob pattern '%s': %s", pattern, e)

        return files

    def _get_files_from_keywords(self, description: str) -> Dict[str, str]:
        """Get files based on keywords in description"""
        files = {}
        description_lower = description.lower()

        # Keyword → file patterns
        keyword_patterns = {
            "database": ["src/**/database.py", "src/**/models.py"],
            "api": ["src/**/main.py", "src/**/routes/**/*.py"],
            "dashboard": ["src/**/dashboard/**/*.py", "src/**/frontend/**/*"],
            "auth": ["src/**/*auth*.py", "src/**/*security*.py"],
            "test": ["tests/**/*.py", "conftest.py"],
            "config": ["config/**/*.yaml", "*.yaml"],
        }

        for keyword, patterns in keyword_patterns.items():
            if keyword in description_lower:
                for pattern in patterns:
                    files.update(self._get_files_by_glob(pattern, max_files=10))

        return files

    def _get_architecture_docs(self) -> Dict[str, str]:
        """Get architecture documentation for high-complexity phases"""
        doc_files = [
            "README.md",
            "docs/ARCHITECTURE.md",
            "docs/DESIGN.md",
            "CLAUDE.md",
        ]

        return self._get_files_by_paths(doc_files)

    def estimate_context_size(self, context: Dict[str, str]) -> int:
        """
        Estimate token count for context (rough approximation).

        Args:
            context: File path → content mapping

        Returns:
            Estimated token count
        """
        total_chars = sum(len(content) for content in context.values())
        # Rough approximation: 4 chars per token
        return total_chars // 4

    def log_context_stats(self, phase_id: str, context: Dict[str, str]):
        """
        Log context statistics for analysis.

        Args:
            phase_id: Phase identifier
            context: Selected context
        """
        token_estimate = self.estimate_context_size(context)
        file_count = len(context)

        print(f"[Context] Phase {phase_id}: {file_count} files, ~{token_estimate:,} tokens")

    # ===== Phase 1 Enhancement: Ranking Heuristics from chatbot_project =====

    def _rank_and_limit_context(
        self,
        context: Dict[str, str],
        phase_spec: Dict,
        token_budget: int,
    ) -> Dict[str, str]:
        """Rank files by relevance and limit by token budget.

        Args:
            context: File path → content mapping
            phase_spec: Phase specification for relevance scoring
            token_budget: Maximum tokens to include

        Returns:
            Ranked and limited context dict
        """
        # Score all files
        scored_files = []
        for file_path, content in context.items():
            score = self._score_file(file_path, content, phase_spec)
            scored_files.append((score, file_path, content))

        # Sort by score (descending)
        scored_files.sort(reverse=True, key=lambda x: x[0])

        # Build limited context respecting token budget
        limited_context = {}
        tokens_used = 0

        for score, file_path, content in scored_files:
            file_tokens = len(content) // 4  # Rough estimate
            if tokens_used + file_tokens <= token_budget:
                limited_context[file_path] = content
                tokens_used += file_tokens
            else:
                # Budget exhausted
                break

        return limited_context

    def _score_file(self, file_path: str, content: str, phase_spec: Dict) -> float:
        """Score file relevance using heuristics.

        Args:
            file_path: Relative file path
            content: File content
            phase_spec: Phase specification

        Returns:
            Relevance score (higher = more relevant)
        """
        score = 0.0

        # 1. Relevance score (keyword/path matching)
        score += self._relevance_score(file_path, phase_spec)

        # 2. Recency score (git history, mtime)
        score += self._recency_score(file_path)

        # 3. Type priority score (tests > core > misc)
        score += self._type_priority_score(file_path)

        return score

    def _relevance_score(self, file_path: str, phase_spec: Dict) -> float:
        """Score file relevance to phase description/category.

        Returns score in range [0, 40]
        """
        score = 0.0
        description = phase_spec.get("description", "").lower()
        task_category = phase_spec.get("task_category", "general")

        # Keyword matching in description
        keywords = re.findall(r"\b\w+\b", description)
        for keyword in keywords:
            if keyword in file_path.lower():
                score += 5.0
                break  # Cap per-keyword bonus

        # Category-specific path matching
        category_paths = {
            "database": ["database", "models", "migrations"],
            "api": ["routes", "main", "schemas"],
            "tests": ["tests", "test_"],
            "security_auth_change": ["auth", "security", "permissions"],
            "schema_contract_change": ["models", "schemas", "api"],
        }

        for path_fragment in category_paths.get(task_category, []):
            if path_fragment in file_path.lower():
                score += 10.0
                break

        return min(score, 40.0)

    def _recency_score(self, file_path: str) -> float:
        """Score file recency (recent changes = higher priority).

        Returns score in range [0, 30]
        """
        score = 0.0
        full_path = self.root / file_path

        try:
            # Try git log for recency (commits in last 30 days)
            result = subprocess.run(
                ["git", "log", "-1", "--since=30.days.ago", "--format=%ci", str(full_path)],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=2,
            )

            if result.stdout.strip():
                # File changed in last 30 days
                score += 30.0
            else:
                # Fallback: Check mtime
                mtime = full_path.stat().st_mtime
                age_days = (datetime.now().timestamp() - mtime) / 86400

                if age_days < 7:
                    score += 25.0
                elif age_days < 30:
                    score += 15.0
                elif age_days < 90:
                    score += 5.0

        except subprocess.TimeoutExpired:
            logger.debug("Git log timed out for %s, falling back to mtime", file_path)
            score = self._get_mtime_score(full_path)
        except subprocess.SubprocessError as e:
            logger.debug("Git subprocess error for %s: %s, falling back to mtime", file_path, e)
            score = self._get_mtime_score(full_path)
        except OSError as e:
            logger.debug("OS error checking recency for %s: %s", file_path, e)

        return min(score, 30.0)

    def _get_mtime_score(self, full_path: Path) -> float:
        """Get recency score based on file modification time.

        Args:
            full_path: Absolute path to file

        Returns:
            Recency score based on mtime (0-10)
        """
        try:
            mtime = full_path.stat().st_mtime
            age_days = (datetime.now().timestamp() - mtime) / 86400
            if age_days < 30:
                return 10.0
        except FileNotFoundError:
            logger.debug("File not found for mtime check: %s", full_path)
        except PermissionError as e:
            logger.warning("Permission denied checking mtime for %s: %s", full_path, e)
        except OSError as e:
            logger.debug("OS error checking mtime for %s: %s", full_path, e)
        return 0.0

    def _type_priority_score(self, file_path: str) -> float:
        """Score file type priority (tests > core > docs > misc).

        Returns score in range [0, 30]
        """
        path_lower = file_path.lower()

        # High priority: Core implementation files
        if any(x in path_lower for x in ["src/autopack", "main.py", "models.py", "database.py"]):
            return 30.0

        # Medium-high priority: Test files
        if "test" in path_lower or path_lower.startswith("tests/"):
            return 25.0

        # Medium priority: API/routes
        if any(x in path_lower for x in ["routes", "schemas", "api"]):
            return 20.0

        # Low-medium priority: Config files
        if any(x in path_lower for x in ["config", ".yaml", ".json"]):
            return 15.0

        # Low priority: Documentation
        if path_lower.endswith(".md") or "docs/" in path_lower:
            return 10.0

        # Very low priority: Misc files
        return 5.0

    # ===== Phase 2: Scope-Aware Context Loading (GPT recommendation) =====

    def _normalize_scope_paths(self, paths: List[str]) -> List[Path]:
        """Normalize scope paths to absolute Path objects.

        Args:
            paths: List of relative path strings

        Returns:
            List of absolute Path objects
        """
        normalized = []
        for path_str in paths:
            # Handle both Unix and Windows paths
            path_str = path_str.replace("\\", "/")
            path = self.root / path_str
            normalized.append(path)
        return normalized

    def _load_directory_files(self, directory: Path, context: Dict[str, str]) -> None:
        """Load all files from a directory recursively with proper logging.

        Args:
            directory: Directory path to load files from
            context: Dict to populate with file path -> content mappings
        """
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        relative_path = str(file_path.relative_to(self.root))
                        if relative_path not in context:
                            context[relative_path] = content
                    except PermissionError as e:
                        logger.warning("Permission denied reading %s: %s", file_path, e)
                    except UnicodeDecodeError as e:
                        logger.debug("Unicode decode error reading %s: %s", file_path, e)
                    except OSError as e:
                        logger.error("OS error reading %s: %s", file_path, e)
        except PermissionError as e:
            logger.warning("Permission denied accessing directory %s: %s", directory, e)
        except OSError as e:
            logger.error("OS error accessing directory %s: %s", directory, e)

    def _build_scoped_context(
        self,
        scope_paths: List[str],
        readonly_context: List[str],
        token_budget: Optional[int],
        phase_spec: Dict,
    ) -> Dict[str, str]:
        """Build context using explicit scope configuration.

        This enforces scope isolation by only loading files specified in scope.paths
        (modifiable) and scope.read_only_context (reference only).

        Args:
            scope_paths: List of file paths that can be modified
            readonly_context: List of directories/files for read-only reference
            token_budget: Optional token limit for context
            phase_spec: Phase specification for ranking

        Returns:
            Dict mapping file paths to contents
        """
        context = {}

        # 1. Load modifiable files from scope.paths
        normalized_scope = self._normalize_scope_paths(scope_paths)
        for path in normalized_scope:
            if path.exists() and path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                    relative_path = str(path.relative_to(self.root))
                    context[relative_path] = content
                except PermissionError as e:
                    logger.warning("Permission denied reading scope file %s: %s", path, e)
                except UnicodeDecodeError as e:
                    logger.debug("Unicode decode error reading scope file %s: %s", path, e)
                except OSError as e:
                    logger.error("OS error reading scope file %s: %s", path, e)
            elif path.exists() and path.is_dir():
                # If scope path is a directory, load all files recursively
                self._load_directory_files(path, context)

        # 2. Load read-only context (for reference, not modification)
        if readonly_context:
            normalized_readonly = self._normalize_scope_paths(readonly_context)
            for path in normalized_readonly:
                if path.exists() and path.is_file():
                    try:
                        content = path.read_text(encoding="utf-8")
                        relative_path = str(path.relative_to(self.root))
                        # Don't overwrite modifiable files
                        if relative_path not in context:
                            context[relative_path] = content
                    except PermissionError as e:
                        logger.warning("Permission denied reading readonly context %s: %s", path, e)
                    except UnicodeDecodeError as e:
                        logger.debug(
                            "Unicode decode error reading readonly context %s: %s", path, e
                        )
                    except OSError as e:
                        logger.error("OS error reading readonly context %s: %s", path, e)
                elif path.exists() and path.is_dir():
                    # Load directory contents as read-only context
                    self._load_directory_files(path, context)

        # 3. Apply token budget using ranking heuristics
        if token_budget and context:
            context = self._rank_and_limit_context(context, phase_spec, token_budget)

        return context
