"""Import Graph Dependency Analyzer for scope expansion.

Traces cross-file dependencies to suggest related files for scope expansion.
Supports Python (AST-based) and JavaScript/TypeScript (regex-based) imports.

Architecture:
- Parses import statements (import, from...import, require, ES6 imports)
- Resolves relative imports to absolute workspace paths
- Builds bounded dependency graph (max depth=2, max files=50)
- Suggests related files for scope expansion (never auto-adds)

Integration:
- PatternMatcher: Suggests files based on import relationships
- ScopeExpander: Uses suggestions for controlled expansion
- ManifestGenerator: Enriches scope with dependency context

Usage:
    analyzer = ImportGraphAnalyzer(workspace_root=Path("/project"))
    graph = analyzer.build_graph(
        entry_files=["src/main.py"],
        max_depth=2,
        max_files=50
    )
    suggestions = analyzer.suggest_related_files(
        current_scope=["src/main.py"],
        graph=graph,
        max_suggestions=10
    )
"""

import ast
import re
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ImportNode:
    """Represents a file node in the import graph."""

    path: Path
    imports: List[str] = field(default_factory=list)  # Imported module names
    imported_by: List[str] = field(default_factory=list)  # Files that import this
    depth: int = 0  # Distance from entry files
    language: str = "unknown"  # python, javascript, typescript


@dataclass
class ImportGraph:
    """Dependency graph of file imports."""

    nodes: Dict[str, ImportNode] = field(default_factory=dict)  # path -> node
    edges: List[Tuple[str, str]] = field(default_factory=list)  # (from_path, to_path)
    entry_files: List[str] = field(default_factory=list)
    max_depth_reached: int = 0
    files_analyzed: int = 0


class ImportGraphAnalyzer:
    """Analyzes import dependencies across Python and JavaScript/TypeScript files."""

    def __init__(self, workspace_root: Path, gitignore_patterns: Optional[List[str]] = None):
        """Initialize analyzer.

        Args:
            workspace_root: Root directory of the workspace
            gitignore_patterns: Optional list of gitignore patterns to exclude
        """
        self.workspace_root = workspace_root.resolve()
        self.gitignore_patterns = gitignore_patterns or []

        # JavaScript/TypeScript import patterns (ES6 + CommonJS)
        self.js_import_patterns = [
            # ES6 imports: import X from 'module'
            re.compile(r"import\s+(?:[\w{},\s*]+)\s+from\s+['\"]([^'\"]+)['\"]"),
            # ES6 imports: import 'module'
            re.compile(r"import\s+['\"]([^'\"]+)['\"]"),
            # CommonJS: require('module')
            re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
            # Dynamic imports: import('module')
            re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        ]

    def build_graph(
        self,
        entry_files: List[str],
        max_depth: int = 2,
        max_files: int = 50,
    ) -> ImportGraph:
        """Build bounded import dependency graph.

        Args:
            entry_files: Starting files (relative to workspace_root)
            max_depth: Maximum traversal depth (default: 2)
            max_files: Maximum files to analyze (default: 50)

        Returns:
            ImportGraph with nodes and edges
        """
        graph = ImportGraph(entry_files=entry_files)
        queue: List[Tuple[str, int]] = [(f, 0) for f in entry_files]  # (path, depth)
        visited: Set[str] = set()

        while queue and graph.files_analyzed < max_files:
            current_path, depth = queue.pop(0)

            if current_path in visited or depth > max_depth:
                continue

            visited.add(current_path)
            graph.files_analyzed += 1
            graph.max_depth_reached = max(graph.max_depth_reached, depth)

            # Parse imports from current file
            abs_path = self.workspace_root / current_path
            if not abs_path.exists():
                logger.debug(f"[ImportGraph] File not found: {current_path}")
                continue

            imports = self._parse_imports(abs_path)
            language = self._detect_language(abs_path)

            # Create node
            node = ImportNode(
                path=abs_path,
                imports=imports,
                depth=depth,
                language=language,
            )
            graph.nodes[current_path] = node

            # Resolve imports to absolute paths and add to queue
            for imported_module in imports:
                resolved_path = self._resolve_import(
                    imported_module,
                    current_path,
                    language,
                )

                if resolved_path:
                    # Add edge
                    graph.edges.append((current_path, resolved_path))

                    # Update imported_by
                    if resolved_path not in graph.nodes:
                        graph.nodes[resolved_path] = ImportNode(
                            path=self.workspace_root / resolved_path,
                            depth=depth + 1,
                        )
                    graph.nodes[resolved_path].imported_by.append(current_path)

                    # Add to queue if not visited
                    if resolved_path not in visited and depth + 1 <= max_depth:
                        queue.append((resolved_path, depth + 1))

        logger.info(
            f"[ImportGraph] Built graph: {graph.files_analyzed} files, "
            f"max depth {graph.max_depth_reached}, {len(graph.edges)} edges"
        )
        return graph

    def suggest_related_files(
        self,
        current_scope: List[str],
        graph: ImportGraph,
        max_suggestions: int = 10,
    ) -> List[str]:
        """Suggest related files for scope expansion (never auto-adds).

        Args:
            current_scope: Files already in scope (relative paths)
            graph: Import graph from build_graph()
            max_suggestions: Maximum suggestions to return

        Returns:
            List of suggested file paths (relative to workspace_root)
        """
        suggestions: Set[str] = set()
        scope_set = set(current_scope)

        # Strategy 1: Direct imports/importers (depth 1)
        for file_path in current_scope:
            if file_path not in graph.nodes:
                continue

            node = graph.nodes[file_path]

            # Add files imported by current scope
            for edge in graph.edges:
                if edge[0] == file_path and edge[1] not in scope_set:
                    suggestions.add(edge[1])

            # Add files that import current scope
            for importer in node.imported_by:
                if importer not in scope_set:
                    suggestions.add(importer)

        # Strategy 2: Sibling files (same directory)
        for file_path in current_scope:
            abs_path = self.workspace_root / file_path
            parent_dir = abs_path.parent

            if parent_dir.exists():
                for sibling in parent_dir.iterdir():
                    if sibling.is_file() and self._is_code_file(sibling):
                        rel_path = str(sibling.relative_to(self.workspace_root))
                        if rel_path not in scope_set:
                            suggestions.add(rel_path)

        # Strategy 3: Test files (if main file in scope, suggest test)
        for file_path in current_scope:
            test_path = self._find_test_file(file_path)
            if test_path and test_path not in scope_set:
                suggestions.add(test_path)

        # Rank suggestions by relevance (imported/importers first)
        ranked = sorted(
            suggestions,
            key=lambda p: (
                -sum(
                    1 for edge in graph.edges if edge[0] in scope_set and edge[1] == p
                ),  # Imported by scope
                -sum(
                    1 for edge in graph.edges if edge[1] in scope_set and edge[0] == p
                ),  # Imports scope
                p,  # Alphabetical tie-breaker
            ),
        )

        return ranked[:max_suggestions]

    def _parse_imports(self, file_path: Path) -> List[str]:
        """Parse import statements from a file.

        Args:
            file_path: Absolute path to file

        Returns:
            List of imported module names (not resolved paths)
        """
        language = self._detect_language(file_path)

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"[ImportGraph] Failed to read {file_path}: {e}")
            return []

        if language == "python":
            return self._parse_python_imports(content)
        elif language in ("javascript", "typescript"):
            return self._parse_js_imports(content)
        else:
            return []

    def _parse_python_imports(self, content: str) -> List[str]:
        """Parse Python imports using AST.

        Args:
            content: File content

        Returns:
            List of imported module names
        """
        imports = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.debug(f"[ImportGraph] Python syntax error: {e}")
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return imports

    def _parse_js_imports(self, content: str) -> List[str]:
        """Parse JavaScript/TypeScript imports using regex.

        Args:
            content: File content

        Returns:
            List of imported module names
        """
        imports = []

        for pattern in self.js_import_patterns:
            for match in pattern.finditer(content):
                module_name = match.group(1)
                imports.append(module_name)

        return imports

    def _resolve_import(
        self,
        module_name: str,
        current_file: str,
        language: str,
    ) -> Optional[str]:
        """Resolve import to absolute workspace path.

        Args:
            module_name: Imported module name (e.g., './utils', 'autopack.models')
            current_file: Current file path (relative to workspace_root)
            language: File language (python, javascript, typescript)

        Returns:
            Resolved path (relative to workspace_root) or None if unresolvable
        """
        if language == "python":
            return self._resolve_python_import(module_name, current_file)
        elif language in ("javascript", "typescript"):
            return self._resolve_js_import(module_name, current_file)
        else:
            return None

    def _resolve_python_import(
        self,
        module_name: str,
        current_file: str,
    ) -> Optional[str]:
        """Resolve Python import to file path.

        Args:
            module_name: Module name (e.g., 'autopack.models', '.utils')
            current_file: Current file path (relative to workspace_root)

        Returns:
            Resolved path or None
        """
        # Handle relative imports (e.g., '.utils', '..models')
        if module_name.startswith("."):
            current_dir = (self.workspace_root / current_file).parent
            parts = module_name.split(".")
            level = len([p for p in parts if p == ""])  # Count leading dots
            module_parts = [p for p in parts if p]  # Non-empty parts

            # Navigate up directories
            target_dir = current_dir
            for _ in range(level - 1):
                target_dir = target_dir.parent

            # Append module parts
            for part in module_parts:
                target_dir = target_dir / part

            # Try .py file or __init__.py
            if (target_dir.with_suffix(".py")).exists():
                return str((target_dir.with_suffix(".py")).relative_to(self.workspace_root))
            elif (target_dir / "__init__.py").exists():
                return str((target_dir / "__init__.py").relative_to(self.workspace_root))

        # Handle absolute imports (e.g., 'autopack.models')
        else:
            parts = module_name.split(".")
            # Try src/<module>/... or <module>/...
            for base in [self.workspace_root / "src", self.workspace_root]:
                target = base
                for part in parts:
                    target = target / part

                # Try .py file or __init__.py
                if (target.with_suffix(".py")).exists():
                    return str((target.with_suffix(".py")).relative_to(self.workspace_root))
                elif (target / "__init__.py").exists():
                    return str((target / "__init__.py").relative_to(self.workspace_root))

        return None

    def _resolve_js_import(
        self,
        module_name: str,
        current_file: str,
    ) -> Optional[str]:
        """Resolve JavaScript/TypeScript import to file path.

        Args:
            module_name: Module name (e.g., './utils', '../components/Button')
            current_file: Current file path (relative to workspace_root)

        Returns:
            Resolved path or None
        """
        # Only handle relative imports (e.g., './utils', '../components')
        if not module_name.startswith("."):
            return None  # Skip node_modules and absolute imports

        current_dir = (self.workspace_root / current_file).parent
        target = (current_dir / module_name).resolve()

        # Try common extensions
        for ext in [".ts", ".tsx", ".js", ".jsx", ".mjs"]:
            if (target.with_suffix(ext)).exists():
                try:
                    return str((target.with_suffix(ext)).relative_to(self.workspace_root))
                except ValueError:
                    return None

        # Try index files
        for ext in [".ts", ".tsx", ".js", ".jsx"]:
            index_file = target / f"index{ext}"
            if index_file.exists():
                try:
                    return str(index_file.relative_to(self.workspace_root))
                except ValueError:
                    return None

        return None

    def _detect_language(self, file_path: Path) -> str:
        """Detect file language from extension.

        Args:
            file_path: File path

        Returns:
            'python', 'javascript', 'typescript', or 'unknown'
        """
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return "python"
        elif suffix in (".js", ".jsx", ".mjs"):
            return "javascript"
        elif suffix in (".ts", ".tsx"):
            return "typescript"
        else:
            return "unknown"

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if file is a code file (Python/JS/TS).

        Args:
            file_path: File path

        Returns:
            True if code file
        """
        return self._detect_language(file_path) != "unknown"

    def _find_test_file(self, file_path: str) -> Optional[str]:
        """Find corresponding test file for a given file.

        Args:
            file_path: File path (relative to workspace_root)

        Returns:
            Test file path or None
        """
        abs_path = self.workspace_root / file_path
        stem = abs_path.stem
        suffix = abs_path.suffix
        parent = abs_path.parent

        # Common test patterns
        test_patterns = [
            f"test_{stem}{suffix}",
            f"{stem}_test{suffix}",
            f"{stem}.test{suffix}",
            f"{stem}.spec{suffix}",
        ]

        # Check in same directory
        for pattern in test_patterns:
            test_file = parent / pattern
            if test_file.exists():
                return str(test_file.relative_to(self.workspace_root))

        # Check in tests/ directory
        tests_dir = self.workspace_root / "tests"
        if tests_dir.exists():
            for pattern in test_patterns:
                test_file = tests_dir / pattern
                if test_file.exists():
                    return str(test_file.relative_to(self.workspace_root))

        return None
