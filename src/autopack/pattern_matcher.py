"""
Pattern Matcher with Earned Confidence Scoring

Matches task goals to file scopes using deterministic patterns
with confidence scores earned from multiple signals.

Key Features:
- Keyword → category mapping
- Anchor file detection (earned confidence)
- Match density analysis (keyword frequency)
- Directory locality scoring (clustered vs scattered)
- Compile globs to explicit file lists
- 0 LLM calls (fully deterministic)

Usage:
    scanner = RepoScanner(workspace)
    matcher = PatternMatcher(scanner)

    result = matcher.match(
        goal="Add JWT authentication with login/logout endpoints",
        phase_id="auth-backend"
    )

    # result.category = "authentication"
    # result.confidence = 0.85
    # result.scope_paths = ["src/auth/jwt.py", "src/api/endpoints/auth.py", ...]
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass

from autopack.repo_scanner import RepoScanner


@dataclass
class MatchResult:
    """Result of pattern matching"""
    category: str
    confidence: float
    scope_paths: List[str]
    read_only_context: List[str]
    confidence_breakdown: Dict[str, float]
    anchor_files_found: List[str]
    match_density: float
    directory_locality: float


# Category patterns with keywords and anchor directories
CATEGORY_PATTERNS = {
    "authentication": {
        "keywords": [
            "auth", "login", "logout", "jwt", "token", "session",
            "password", "credential", "sign in", "sign out",
            "authentication", "authorize", "oauth"
        ],
        "anchor_dirs": [
            "src/auth", "src/authentication",
            "backend/auth", "api/auth",
            "src/middleware/auth"
        ],
        "scope_templates": [
            "{anchor}/**/*.py",
            "src/api/endpoints/auth*.py",
            "src/api/routers/auth*.py",
            "src/middleware/auth*.py",
        ],
        "readonly_templates": [
            "src/database/models.py",
            "src/config.py",
            "src/main.py"
        ],
        "test_templates": [
            "tests/auth/**/*.py",
            "tests/api/test_auth*.py"
        ]
    },

    "api_endpoint": {
        "keywords": [
            "api", "endpoint", "route", "router", "rest",
            "get", "post", "put", "delete", "patch",
            "fastapi", "flask", "django"
        ],
        "anchor_dirs": [
            "src/api/endpoints", "src/api/routes", "src/api/routers",
            "backend/api", "api/endpoints"
        ],
        "scope_templates": [
            "{anchor}/**/*.py",
            "src/api/**/*.py",
        ],
        "readonly_templates": [
            "src/database/models.py",
            "src/auth/**/*.py",
            "src/main.py"
        ],
        "test_templates": [
            "tests/api/**/*.py",
        ]
    },

    "database": {
        "keywords": [
            "database", "db", "model", "schema", "migration",
            "sql", "query", "table", "orm", "sqlalchemy",
            "postgres", "sqlite", "alembic"
        ],
        "anchor_dirs": [
            "src/database", "src/db", "src/models",
            "backend/database", "api/models"
        ],
        "scope_templates": [
            "{anchor}/**/*.py",
            "src/models/**/*.py",
            "alembic/versions/**/*.py"
        ],
        "readonly_templates": [
            "src/config.py",
            "src/main.py"
        ],
        "test_templates": [
            "tests/database/**/*.py",
            "tests/models/**/*.py"
        ]
    },

    "frontend": {
        "keywords": [
            "frontend", "ui", "component", "react", "vue", "angular",
            "jsx", "tsx", "css", "html", "form", "button",
            "modal", "page", "view"
        ],
        "anchor_dirs": [
            "src/frontend", "frontend", "src/ui", "ui",
            "src/components", "components", "src/pages", "pages"
        ],
        "scope_templates": [
            "{anchor}/**/*.tsx",
            "{anchor}/**/*.jsx",
            "{anchor}/**/*.ts",
            "{anchor}/**/*.js",
            "{anchor}/**/*.css"
        ],
        "readonly_templates": [
            "src/api/**/*.py",
        ],
        "test_templates": [
            "tests/frontend/**/*.test.tsx",
            "tests/frontend/**/*.test.ts"
        ]
    },

    "config": {
        "keywords": [
            "config", "configuration", "setting", "environment",
            "env", "dotenv", ".env"
        ],
        "anchor_dirs": [
            "src/config", "config"
        ],
        "scope_templates": [
            "src/config.py",
            "src/settings.py",
            "config/**/*.py",
            ".env.example"
        ],
        "readonly_templates": [],
        "test_templates": [
            "tests/test_config.py"
        ]
    },

    "tests": {
        "keywords": [
            "test", "testing", "pytest", "unittest",
            "coverage", "fixture", "mock"
        ],
        "anchor_dirs": [],  # Don't use broad anchor - use specific templates
        "scope_templates": [
            "tests/**/*.py",  # Root-level tests only (not src/autopack/tests)
            "test/**/*.py"
        ],
        "readonly_templates": [
            "src/**/*.py"
        ],
        "test_templates": []
    },

    "memory": {
        "keywords": [
            "memory", "embedding", "vector", "qdrant",
            "semantic", "retrieval", "search", "index"
        ],
        "anchor_dirs": [
            "src/autopack/memory", "src/memory"
        ],
        "scope_templates": [
            "{anchor}/**/*.py",
            "src/autopack/memory/**/*.py"
        ],
        "readonly_templates": [
            "src/database/models.py",
            "src/config.py"
        ],
        "test_templates": [
            "tests/autopack/memory/**/*.py"
        ]
    },

    "autonomous_executor": {
        "keywords": [
            "autonomous executor", "builder client", "autonomous loop",
            "phase execution", "orchestration loop"
        ],
        "anchor_dirs": [],  # Don't use broad directory anchor
        "scope_templates": [
            "src/autopack/autonomous_executor.py",
            "src/autopack/builder.py",
            "src/autopack/runner.py"
        ],
        "readonly_templates": [
            "src/autopack/memory/**/*.py",
            "src/database/models.py"
        ],
        "test_templates": [
            "tests/autopack/test_autonomous_executor.py",
            "tests/autopack/test_builder.py"
        ]
    },

    "governance": {
        "keywords": [
            "governed apply", "scope validation", "protection rules",
            "governance enforcement", "approval workflow"
        ],
        "anchor_dirs": [],  # Don't use broad directory anchor
        "scope_templates": [
            "src/autopack/governed_apply.py",
            "src/autopack/scope_validator.py",
            "src/autopack/preflight_validator.py"
        ],
        "readonly_templates": [
            "src/database/models.py"
        ],
        "test_templates": [
            "tests/autopack/test_governed_apply.py"
        ]
    }
}


class PatternMatcher:
    """
    Match task goals to file scopes using deterministic patterns.

    Confidence is EARNED from multiple signals:
    - Anchor files present: 40%
    - Match density: 30%
    - Directory locality: 20%
    - (Future: git history: 10%)
    """

    # Maximum files to include from a single category match
    MAX_SCOPE_FILES = 100

    def __init__(
        self,
        repo_scanner: RepoScanner,
        autopack_internal_mode: bool = False,
        run_type: str = "project_build",
    ):
        self.scanner = repo_scanner
        self.autopack_internal_mode = autopack_internal_mode
        self.run_type = run_type
        self.repo_structure = repo_scanner.scan()

    def match(
        self,
        goal: str,
        phase_id: str,
        description: Optional[str] = None
    ) -> MatchResult:
        """
        Match goal to category and generate scope.

        Returns MatchResult with:
        - category (best match)
        - confidence (earned from signals)
        - scope_paths (explicit file list, not globs)
        - read_only_context
        - confidence_breakdown
        """

        # Combine goal + description for matching
        text = goal.lower()
        if description:
            text += " " + description.lower()

        # Score all categories
        category_scores = {}
        for category, patterns in CATEGORY_PATTERNS.items():
            score = self._score_category(text, category, patterns)
            category_scores[category] = score

        # Get best match (by confidence score)
        best_category = max(category_scores, key=lambda k: category_scores[k]["confidence"])
        best_score = category_scores[best_category]
        best_patterns = CATEGORY_PATTERNS[best_category]

        # Require minimum keyword matches to prevent false positives.
        # Even if anchors exist, we need at least some keyword match.
        min_kw_matches = best_patterns.get("min_keyword_matches", 1)
        if best_score["match_count"] < min_kw_matches:
            # No keywords matched - return empty scope
            return self._generic_scope(goal, phase_id)

        # If confidence too low, return generic scope
        # Lowered to 0.15 to allow template-only matches (no anchors)
        if best_score["confidence"] < 0.15:
            return self._generic_scope(goal, phase_id)

        # Generate scope for best category
        patterns = CATEGORY_PATTERNS[best_category]
        scope_paths = self._generate_scope(best_category, patterns)
        readonly_context = self._generate_readonly_context(best_category, patterns)

        return MatchResult(
            category=best_category,
            confidence=best_score["confidence"],
            scope_paths=scope_paths,
            read_only_context=readonly_context,
            confidence_breakdown=best_score["breakdown"],
            anchor_files_found=best_score["anchors_found"],
            match_density=best_score["match_density"],
            directory_locality=best_score["locality"]
        )

    def _score_category(
        self,
        text: str,
        category: str,
        patterns: Dict
    ) -> Dict:
        """
        Score category match with EARNED confidence.

        Signals:
        1. Anchor files present (40%)
        2. Match density (30%)
        3. Directory locality (20%)
        4. (Future: git history 10%)
        """

        # Signal 1: Anchor files present
        anchors_found = []
        anchor_dirs = patterns.get("anchor_dirs", [])
        for anchor in anchor_dirs:
            if self._anchor_exists(anchor):
                anchors_found.append(anchor)

        anchor_signal = 0.40 if anchors_found else 0.0

        # Signal 2: Match density (keyword frequency)
        keywords = patterns.get("keywords", [])
        match_count = self._count_keyword_matches(text, keywords)
        match_density = min(match_count / max(len(keywords), 1), 1.0)
        density_signal = match_density * 0.30

        # Signal 3: Directory locality
        # (For now, if anchors exist, assume high locality)
        locality = 1.0 if anchors_found else 0.5
        locality_signal = locality * 0.20

        # Signal 4: Git history (future)
        # git_signal = 0.10 if self._check_git_history(category) else 0.0
        git_signal = 0.0  # Not implemented yet

        # Total confidence
        confidence = anchor_signal + density_signal + locality_signal + git_signal

        return {
            "confidence": confidence,
            "breakdown": {
                "anchor_files": anchor_signal,
                "match_density": density_signal,
                "directory_locality": locality_signal,
                "git_history": git_signal
            },
            "anchors_found": anchors_found,
            "match_count": match_count,
            "match_density": match_density,
            "locality": locality
        }

    def _count_keyword_matches(self, text: str, keywords: List[str]) -> int:
        """
        Count keyword matches with basic boundary-awareness.

        - Single-word keywords use word boundaries with a permissive plural 's' suffix.
        - Multi-word / punctuated keywords fall back to substring matching.
        """
        count = 0
        for kw in keywords:
            kw_norm = (kw or "").strip().lower()
            if not kw_norm:
                continue

            # Treat phrases or punctuated tokens as substring checks.
            if any(ch in kw_norm for ch in (" ", ".", "/", "-", "_")):
                if kw_norm in text:
                    count += 1
                continue

            # Word boundary match (allow simple pluralization: kw + optional 's')
            # Example: "test" should match "tests" in natural language.
            if re.search(rf"\b{re.escape(kw_norm)}s?\b", text):
                count += 1
        return count

    def _anchor_exists(self, anchor_dir: str) -> bool:
        """Check if anchor directory exists in repo"""
        tree = self.repo_structure["tree"]

        # Exact match
        if anchor_dir in tree:
            return True

        # Prefix match (e.g., "src/auth" matches "src/auth/jwt.py")
        for path in tree.keys():
            if path.startswith(anchor_dir):
                return True

        return False

    def _generate_scope(
        self,
        category: str,
        patterns: Dict
    ) -> List[str]:
        """
        Generate scope paths (EXPLICIT file list, not globs).

        Critical: Compile globs to explicit files.
        Enforces MAX_SCOPE_FILES limit to prevent overly broad scopes.
        """

        import logging
        logger = logging.getLogger(__name__)

        scope_paths = []
        anchor_files = self.repo_structure.get("anchor_files", {})
        all_files = self.repo_structure.get("all_files", [])

        # Use RepoScanner anchors ONLY if this category explicitly allows anchors.
        # (Fixes a bug where categories with anchor_dirs=[] still used scanner anchors.)
        allowed_anchor_roots = [a.rstrip("/") for a in patterns.get("anchor_dirs", [])]
        allow_anchor_strategy = bool(allowed_anchor_roots)

        # Get anchor directories for this category, filtered to allowed roots
        category_anchors_raw = anchor_files.get(category, [])
        category_anchors = self._filter_anchor_dirs(category_anchors_raw, allowed_anchor_roots)

        # Strategy 1: Use detected anchor directories
        if allow_anchor_strategy and category_anchors:
            for anchor in category_anchors:
                # Add all files under anchor (with limit)
                anchor_clean = anchor.rstrip("/")
                anchor_prefix = anchor_clean + "/"
                anchor_files_list = [f for f in all_files if f.startswith(anchor_prefix)]

                if len(anchor_files_list) > self.MAX_SCOPE_FILES:
                    logger.warning(
                        f"Category '{category}' anchor '{anchor}' has {len(anchor_files_list)} files, "
                        f"limiting to {self.MAX_SCOPE_FILES} most recently modified"
                    )
                    # Take first N files (repo_scanner sorts by mtime)
                    anchor_files_list = anchor_files_list[:self.MAX_SCOPE_FILES]

                scope_paths.extend(anchor_files_list)

        # Strategy 2: Use scope templates
        else:
            templates = patterns.get("scope_templates", [])
            for template in templates:
                if "{anchor}" in template:
                    # Expand {anchor} across allowed anchor roots that exist in repo
                    for anchor_root in allowed_anchor_roots:
                        if not self._anchor_exists(anchor_root):
                            continue
                        filled = template.format(anchor=anchor_root.rstrip("/"))
                        matched = self._match_template(filled, all_files)
                        if len(matched) > self.MAX_SCOPE_FILES:
                            logger.warning(
                                f"Template '{filled}' matched {len(matched)} files, "
                                f"limiting to {self.MAX_SCOPE_FILES}"
                            )
                            matched = matched[:self.MAX_SCOPE_FILES]
                        scope_paths.extend(matched)
                    continue

                # Match template pattern against all files
                matched = self._match_template(template, all_files)

                # Limit matched files per template
                if len(matched) > self.MAX_SCOPE_FILES:
                    logger.warning(
                        f"Template '{template}' matched {len(matched)} files, "
                        f"limiting to {self.MAX_SCOPE_FILES}"
                    )
                    matched = matched[:self.MAX_SCOPE_FILES]

                scope_paths.extend(matched)

        # Deduplicate and sort
        scope_paths = sorted(set(scope_paths))

        # Safety: never return directory entries in scope.paths (directories explode preflight counting
        # and widen scope enforcement unexpectedly).
        scope_paths = [p for p in scope_paths if not p.endswith("/")]

        # Final check: limit total scope size
        if len(scope_paths) > self.MAX_SCOPE_FILES:
            logger.warning(
                f"Category '{category}' generated {len(scope_paths)} total files, "
                f"limiting to {self.MAX_SCOPE_FILES}"
            )
            scope_paths = scope_paths[:self.MAX_SCOPE_FILES]

        # Filter out protected paths to avoid governance failures (project_build defaults).
        scope_paths = self._filter_scope_paths(scope_paths)

        return scope_paths

    def _filter_anchor_dirs(self, anchors: List[str], allowed_roots: List[str]) -> List[str]:
        """Keep only anchors that fall under allowed anchor roots."""
        if not anchors or not allowed_roots:
            return []
        allowed = []
        allowed_norm = [a.rstrip("/") for a in allowed_roots if a]
        for anchor in anchors:
            anchor_clean = (anchor or "").rstrip("/")
            if not anchor_clean:
                continue
            for root in allowed_norm:
                if anchor_clean == root or anchor_clean.startswith(root + "/"):
                    allowed.append(anchor_clean + "/")
                    break
        return sorted(set(allowed))

    def _filter_scope_paths(self, scope_paths: List[str]) -> List[str]:
        """Filter scope paths using GovernedApplyPath protection rules."""
        try:
            from autopack.governed_apply import GovernedApplyPath
        except Exception:
            # If governance cannot be imported for some reason, fail open (but keep deterministic output).
            return scope_paths

        gov = GovernedApplyPath(
            workspace=self.scanner.workspace,
            autopack_internal_mode=self.autopack_internal_mode,
            run_type=self.run_type,
            scope_paths=[],  # We're filtering candidates, not enforcing scope here
        )

        allowed = []
        for p in scope_paths:
            norm = p.replace("\\", "/")
            if norm.endswith("/"):
                continue
            if gov._is_path_protected(norm):
                continue
            allowed.append(p)
        return allowed

    def _generate_readonly_context(
        self,
        category: str,
        patterns: Dict
    ) -> List[str]:
        """
        Generate read-only context files.

        Enforces MAX_SCOPE_FILES limit to prevent validation failures.
        """

        import logging
        logger = logging.getLogger(__name__)

        readonly_paths = []
        all_files = self.repo_structure.get("all_files", [])

        templates = patterns.get("readonly_templates", [])
        for template in templates:
            matched = self._match_template(template, all_files)

            # Limit matched files per template
            if len(matched) > self.MAX_SCOPE_FILES:
                logger.warning(
                    f"Readonly template '{template}' matched {len(matched)} files, "
                    f"limiting to {self.MAX_SCOPE_FILES}"
                )
                matched = matched[:self.MAX_SCOPE_FILES]

            readonly_paths.extend(matched)

        # Deduplicate and sort
        readonly_paths = sorted(set(readonly_paths))

        # Final check: limit total readonly context size
        if len(readonly_paths) > self.MAX_SCOPE_FILES:
            logger.warning(
                f"Category '{category}' generated {len(readonly_paths)} readonly files, "
                f"limiting to {self.MAX_SCOPE_FILES}"
            )
            readonly_paths = readonly_paths[:self.MAX_SCOPE_FILES]

        return readonly_paths

    def _match_template(self, template: str, all_files: List[str]) -> List[str]:
        """
        Match template pattern against file list.

        Supports:
        - Exact match: "src/config.py"
        - Wildcard: "src/api/**/*.py"
        - Glob: "src/auth/*.py"
        """

        matched: List[str] = []
        pattern = (template or "").replace("\\", "/").lstrip("./")
        if not pattern:
            return matched

        # Convert glob-like patterns to regex with correct ** semantics:
        # - "**/" matches zero or more directories (including none)
        # - "**" matches any characters (including "/")
        # - "*" matches any characters except "/"
        # - "?" matches a single character except "/"
        regex_parts: List[str] = []
        i = 0
        while i < len(pattern):
            if pattern[i:i+3] == "**/":
                regex_parts.append(r"(?:.*/)?")
                i += 3
                continue
            if pattern[i:i+2] == "**":
                regex_parts.append(r".*")
                i += 2
                continue
            ch = pattern[i]
            if ch == "*":
                regex_parts.append(r"[^/]*")
            elif ch == "?":
                regex_parts.append(r"[^/]")
            else:
                regex_parts.append(re.escape(ch))
            i += 1

        regex = re.compile("^" + "".join(regex_parts) + "$")

        for file_path in all_files:
            normalized = (file_path or "").replace("\\", "/").lstrip("./")
            if not normalized:
                continue
            if regex.match(normalized):
                matched.append(normalized)

        return matched

    def _generic_scope(self, goal: str, phase_id: str) -> MatchResult:
        """
        Generate generic scope when confidence is too low.

        Falls back to minimal scope that requires LLM refinement.
        """

        return MatchResult(
            category="unknown",
            confidence=0.0,
            scope_paths=[],
            read_only_context=[],
            confidence_breakdown={
                "anchor_files": 0.0,
                "match_density": 0.0,
                "directory_locality": 0.0,
                "git_history": 0.0
            },
            anchor_files_found=[],
            match_density=0.0,
            directory_locality=0.0
        )

    def get_test_scope(self, category: str) -> List[str]:
        """Get test file scope for a category"""

        if category not in CATEGORY_PATTERNS:
            return []

        patterns = CATEGORY_PATTERNS[category]
        all_files = self.repo_structure.get("all_files", [])

        test_paths = []
        templates = patterns.get("test_templates", [])
        for template in templates:
            matched = self._match_template(template, all_files)
            test_paths.extend(matched)

        return sorted(set(test_paths))

    def expand_scope_with_siblings(
        self,
        file_path: str,
        current_scope: List[str]
    ) -> List[str]:
        """
        Expand scope to include sibling files.

        Used by adaptive scope expansion.
        """

        siblings = self.scanner.get_sibling_files(file_path)

        # Add siblings not already in scope
        expanded = current_scope.copy()
        for sibling in siblings:
            if sibling not in expanded:
                expanded.append(sibling)

        return sorted(expanded)

    def expand_scope_to_parent(
        self,
        file_path: str,
        current_scope: List[str]
    ) -> List[str]:
        """
        Expand scope from file to parent directory.

        Used by adaptive scope expansion.
        """

        # Directories in scope.paths are intentionally disallowed because they:
        # - explode preflight file counting via rglob()
        # - widen scope enforcement (prefix-based) unexpectedly
        #
        # If parent-level expansion is needed, prefer explicit sibling expansion.
        return sorted(current_scope)
