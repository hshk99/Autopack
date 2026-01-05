"""Tests for GroundedContextBuilder (BUILD-124 Phase C)"""

from pathlib import Path


from autopack.plan_analyzer_grounding import GroundedContextBuilder, MAX_CONTEXT_CHARS
from autopack.pattern_matcher import PatternMatcher
from autopack.repo_scanner import RepoScanner


def _touch(path: Path, content: str = "# test\n") -> None:
    """Helper to create test files"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_grounded_context_builder_basic(tmp_path: Path):
    """Test basic grounded context generation"""
    # Create test repo structure
    _touch(tmp_path / "src" / "auth" / "login.py", "def login(): pass")
    _touch(tmp_path / "src" / "auth" / "jwt.py", "def verify_token(): pass")
    _touch(tmp_path / "src" / "api" / "routes.py", "def get_routes(): pass")
    _touch(tmp_path / "tests" / "test_auth.py", "def test_login(): pass")

    # Initialize components
    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

    builder = GroundedContextBuilder(repo_scanner=scanner, pattern_matcher=matcher)

    # Build context for auth-related phase
    context = builder.build_context(
        goal="Add JWT authentication to login endpoint",
        phase_id="auth-backend",
        description="Implement JWT token generation and validation",
    )

    # Verify context structure
    assert context.repo_summary
    assert context.phase_context
    assert context.total_chars > 0
    assert context.total_chars <= MAX_CONTEXT_CHARS or context.truncated

    # Verify repo summary contains key info
    repo_text = context.repo_summary
    assert "Repository Structure" in repo_text
    assert "Top-level directories" in repo_text or "Total files scanned" in repo_text

    # Verify phase context contains phase info
    phase_text = context.phase_context
    assert "auth-backend" in phase_text
    assert "JWT authentication" in phase_text

    # Check formatted prompt
    prompt = context.to_prompt_section()
    assert "## Repository Context (Grounded)" in prompt
    assert "## Phase Analysis Context" in prompt


def test_grounded_context_with_match_result(tmp_path: Path):
    """Test context builder with pre-computed match result"""
    _touch(tmp_path / "src" / "auth" / "login.py")
    _touch(tmp_path / "tests" / "test_auth.py")

    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

    # Pre-compute match result
    match_result = matcher.match(goal="Add authentication", phase_id="auth-phase", description="")

    builder = GroundedContextBuilder(scanner, matcher)

    # Build context with pre-computed result
    context = builder.build_context(
        goal="Add authentication", phase_id="auth-phase", match_result=match_result
    )

    # Verify match result info is included
    phase_text = context.phase_context
    assert "Pattern Matching Results" in phase_text
    assert "Category:" in phase_text
    assert "Confidence:" in phase_text


def test_grounded_context_truncation(tmp_path: Path):
    """Test that context is truncated if it exceeds max_chars"""
    # Create many files to generate large context
    for i in range(50):
        _touch(tmp_path / f"src/module_{i}/file_{i}.py", "# " + "x" * 100)

    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

    # Use small max_chars to force truncation
    builder = GroundedContextBuilder(scanner, matcher, max_chars=500)

    # Build context with verbose goal/description to ensure we exceed limit
    context = builder.build_context(
        goal="Refactor all modules to improve code quality and maintainability across the entire codebase",
        phase_id="refactor-phase-with-very-long-identifier-name",
        description="This is a comprehensive refactoring effort that will touch multiple modules and requires careful analysis of the entire codebase structure",
    )

    # Verify truncation occurred
    assert context.truncated, f"Expected truncation but got {context.total_chars} chars"
    assert context.total_chars <= 600  # Allow small margin
    assert "(truncated)" in context.repo_summary or "(truncated)" in context.phase_context

    # Verify truncation marker in prompt
    prompt = context.to_prompt_section()
    assert "(Context truncated" in prompt


def test_grounded_context_empty_repo(tmp_path: Path):
    """Test context builder with empty repository"""
    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")
    builder = GroundedContextBuilder(scanner, matcher)

    context = builder.build_context(goal="Add feature", phase_id="test-phase")

    # Should still generate valid context
    assert context.repo_summary
    assert context.phase_context
    assert "Total files scanned:** 0" in context.repo_summary


def test_multi_phase_context(tmp_path: Path):
    """Test building context for multiple phases"""
    _touch(tmp_path / "src" / "auth.py")
    _touch(tmp_path / "src" / "api.py")
    _touch(tmp_path / "src" / "db.py")

    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")
    builder = GroundedContextBuilder(scanner, matcher)

    phases = [
        {"phase_id": "auth", "goal": "Add authentication"},
        {"phase_id": "api", "goal": "Create API endpoints"},
        {"phase_id": "db", "goal": "Set up database schema"},
    ]

    context_text = builder.build_multi_phase_context(phases, max_phases_shown=3)

    # Verify structure
    assert "Repository Structure" in context_text
    assert "Phases Overview" in context_text
    assert "Total Phases:** 3" in context_text
    assert "auth" in context_text
    assert "api" in context_text
    assert "db" in context_text

    # Verify length constraint
    assert len(context_text) <= MAX_CONTEXT_CHARS + 100  # Allow small margin


def test_multi_phase_context_truncation(tmp_path: Path):
    """Test multi-phase context with many phases triggers truncation message"""
    _touch(tmp_path / "src" / "main.py")

    scanner = RepoScanner(tmp_path)
    scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")
    builder = GroundedContextBuilder(scanner, matcher, max_chars=1000)

    # Create 20 phases
    phases = [{"phase_id": f"phase-{i}", "goal": f"Implement feature {i}"} for i in range(20)]

    context_text = builder.build_multi_phase_context(phases, max_phases_shown=10)

    # Should show truncation for remaining phases or character limit
    assert "... and 10 more phases" in context_text or "(truncated)" in context_text


def test_top_level_dirs_extraction(tmp_path: Path):
    """Test extraction of top-level directory names"""
    _touch(tmp_path / "src" / "module" / "file.py")
    _touch(tmp_path / "tests" / "test_file.py")
    _touch(tmp_path / "docs" / "README.md")
    _touch(tmp_path / "scripts" / "build.sh")

    scanner = RepoScanner(tmp_path)
    structure = scanner.scan(use_cache=False)

    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")
    builder = GroundedContextBuilder(scanner, matcher)

    top_level = builder._get_top_level_dirs(structure)

    # Should extract unique top-level dirs
    assert "src" in top_level
    assert "tests" in top_level
    assert "docs" in top_level
    assert "scripts" in top_level
    assert len(top_level) == 4
