"""Tests to verify no unreachable code in ArtifactLoader (IMP-007)

This test file verifies that the ArtifactLoader methods, particularly
load_with_extended_contexts, have no unreachable code after definitive returns.
This ensures clean code that doesn't confuse static analysis tools.
"""

import ast
import pytest


class TestArtifactLoaderNoUnreachableCode:
    """Verify artifact_loader.py has no unreachable code patterns"""

    @pytest.fixture
    def artifact_loader_ast(self):
        """Parse artifact_loader.py into AST for analysis"""
        from pathlib import Path

        # Find artifact_loader.py
        autopack_dir = Path(__file__).parent.parent.parent / "src" / "autopack"
        artifact_loader_file = autopack_dir / "artifact_loader.py"

        with open(artifact_loader_file, "r") as f:
            content = f.read()

        return ast.parse(content)

    def test_load_with_extended_contexts_ends_with_return(self, artifact_loader_ast):
        """load_with_extended_contexts should end with a return statement"""
        for node in ast.walk(artifact_loader_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "load_with_extended_contexts":
                # The last statement should be a return
                assert len(node.body) > 0, "Function body is empty"
                last_stmt = node.body[-1]
                assert isinstance(
                    last_stmt, ast.Return
                ), f"Last statement is {type(last_stmt).__name__}, not Return"
                return

        pytest.fail("load_with_extended_contexts method not found")

    def test_no_consecutive_returns_in_load_with_extended_contexts(self, artifact_loader_ast):
        """Verify no unreachable return statements after definitive returns"""
        for node in ast.walk(artifact_loader_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "load_with_extended_contexts":
                # Check for any sequence of Return statements
                for i, stmt in enumerate(node.body):
                    if isinstance(stmt, ast.Return):
                        if i < len(node.body) - 1:
                            next_stmt = node.body[i + 1]
                            assert not isinstance(
                                next_stmt, ast.Return
                            ), f"Unreachable return found: return at line {stmt.lineno} followed by return at line {next_stmt.lineno}"
                return

        pytest.fail("load_with_extended_contexts method not found")

    def test_artifact_loader_file_parses_without_errors(self, artifact_loader_ast):
        """artifact_loader.py should parse as valid Python with no syntax errors"""
        # If we got here, the file parsed successfully
        assert artifact_loader_ast is not None
        assert isinstance(artifact_loader_ast, ast.Module)

    def test_all_functions_have_proper_returns(self, artifact_loader_ast):
        """All functions should have proper return statements"""
        for node in ast.walk(artifact_loader_ast):
            if isinstance(node, ast.FunctionDef):
                # Check return type annotations if present
                if node.returns is not None:
                    # This is just for verification - annotated functions are better
                    pass

                # Basic check: no completely unreachable code blocks after definitive returns
                for i, stmt in enumerate(node.body):
                    if isinstance(stmt, ast.Return) and i < len(node.body) - 1:
                        # There are statements after this return
                        next_stmt = node.body[i + 1]
                        # Multiple consecutive returns are definitely unreachable
                        assert not isinstance(
                            next_stmt, ast.Return
                        ), f"Function {node.name}: unreachable return at line {next_stmt.lineno}"
