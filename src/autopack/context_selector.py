"""Context Engineering - JIT (Just-In-Time) Loading

Following GPT's recommendation: Simple heuristics-based context selection
to reduce token usage by 40-60% while maintaining phase success rates.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
import re


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
    ) -> Dict[str, str]:
        """
        Get minimal context for a phase using simple heuristics.

        Args:
            phase_spec: Phase specification with task_category, complexity, description
            changed_files: Recently changed files (from git diff or previous phases)

        Returns:
            Dict mapping file paths to their contents
        """
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
                    content = path.read_text(encoding='utf-8')
                    files[str(path.relative_to(self.root))] = content
                except Exception:
                    # Skip files that can't be read
                    pass

        return files

    def _get_files_by_glob(self, pattern: str, max_files: int = 20) -> Dict[str, str]:
        """Load files matching glob pattern"""
        files = {}
        count = 0

        try:
            for path in self.root.glob(pattern):
                if path.is_file() and count < max_files:
                    try:
                        content = path.read_text(encoding='utf-8')
                        files[str(path.relative_to(self.root))] = content
                        count += 1
                    except Exception:
                        # Skip files that can't be read
                        pass
        except Exception:
            pass

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
