"""
Tests for Milestone 2 Phase 2: Prompt Wiring

Verify that intention anchors are correctly injected into Builder/Auditor/Doctor prompts.

Intention behind these tests: Ensure prompts contain anchor content when run_id is present,
and gracefully degrade when anchor is missing.
"""

import tempfile
import pytest


from autopack.intention_anchor import IntentionConstraints, create_anchor, save_anchor
from autopack.error_recovery import DoctorRequest


@pytest.fixture(autouse=True)
def mock_llm_api_keys(monkeypatch):
    """Set dummy API keys for all LLM provider tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key-for-testing-only")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-dummy-google-key")
    monkeypatch.setenv("GLM_API_KEY", "test-dummy-glm-key")


# =============================================================================
# Builder Prompt Wiring Tests
# =============================================================================


def test_openai_builder_prompt_includes_anchor():
    """Test that OpenAI Builder prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-openai-builder",
            project_id="test-project",
            north_star="Build a file upload feature.",
            success_criteria=["Support PDF files", "Validate file size"],
            constraints=IntentionConstraints(must=["Use async processing"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.openai_clients import OpenAIBuilderClient

        client = OpenAIBuilderClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-openai-builder",
            "phase_id": "F1.1",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Implement file validation",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                phase_spec=phase_spec, file_context=None, project_rules=None
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Build a file upload feature" in prompt
        assert "Support PDF files" in prompt
        assert "Use async processing" in prompt


def test_gemini_builder_prompt_includes_anchor():
    """Test that Gemini Builder prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-gemini-builder",
            project_id="test-project",
            north_star="Optimize database queries.",
            success_criteria=["Reduce query time to <100ms"],
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.gemini_clients import GeminiBuilderClient

        client = GeminiBuilderClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-gemini-builder",
            "phase_id": "F1.1",
            "task_category": "optimization",
            "complexity": "high",
            "description": "Add query caching",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                phase_spec=phase_spec, file_context=None, project_rules=None
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Optimize database queries" in prompt
        assert "Reduce query time to <100ms" in prompt


def test_glm_builder_prompt_includes_anchor():
    """Test that GLM Builder prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-glm-builder",
            project_id="test-project",
            north_star="Add real-time notifications.",
            success_criteria=["Use WebSockets", "Handle reconnections"],
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.glm_clients import GLMBuilderClient

        client = GLMBuilderClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-glm-builder",
            "phase_id": "F1.1",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Implement WebSocket handler",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                phase_spec=phase_spec, file_context=None, project_rules=None
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Add real-time notifications" in prompt
        assert "Use WebSockets" in prompt


@pytest.mark.skip(
    reason="AnthropicBuilderClient has duplicate _build_user_prompt methods, pre-existing issue"
)
def test_anthropic_builder_prompt_includes_anchor():
    """Test that Anthropic Builder prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-anthropic-builder",
            project_id="test-project",
            north_star="Refactor authentication system.",
            success_criteria=["Use JWT tokens", "Add refresh mechanism"],
            constraints=IntentionConstraints(must_not=["Break existing integrations"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.anthropic_clients import AnthropicBuilderClient

        # Mock dependencies
        client = AnthropicBuilderClient(api_key="test-key")

        # Build prompt
        phase_spec = {
            "run_id": "test-anthropic-builder",
            "phase_id": "F1.1",
            "task_category": "refactor",
            "complexity": "high",
            "description": "Implement JWT authentication",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                phase_spec=phase_spec,
                file_context=None,
                project_rules=None,
                run_hints=None,
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Refactor authentication system" in prompt
        assert "Use JWT tokens" in prompt
        assert "Break existing integrations" in prompt


# =============================================================================
# Auditor Prompt Wiring Tests
# =============================================================================


def test_openai_auditor_prompt_includes_anchor():
    """Test that OpenAI Auditor prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-openai-auditor",
            project_id="test-project",
            north_star="Ensure code quality standards.",
            constraints=IntentionConstraints(must=["Follow PEP 8"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.openai_clients import OpenAIAuditorClient

        client = OpenAIAuditorClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-openai-auditor",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Add new API endpoint",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                patch_content="diff --git a/test.py b/test.py\n+print('hello')",
                phase_spec=phase_spec,
                project_rules=None,
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Ensure code quality standards" in prompt
        assert "Follow PEP 8" in prompt


def test_gemini_auditor_prompt_includes_anchor():
    """Test that Gemini Auditor prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-gemini-auditor",
            project_id="test-project",
            north_star="Maintain security standards.",
            constraints=IntentionConstraints(must_not=["Introduce SQL injection risks"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.gemini_clients import GeminiAuditorClient

        client = GeminiAuditorClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-gemini-auditor",
            "task_category": "feature",
            "complexity": "high",
            "description": "Add database query endpoint",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                patch_content="diff --git a/db.py b/db.py\n+query = f'SELECT * FROM users WHERE id={id}'",
                phase_spec=phase_spec,
                project_rules=None,
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Maintain security standards" in prompt
        assert "SQL injection" in prompt


def test_glm_auditor_prompt_includes_anchor():
    """Test that GLM Auditor prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-glm-auditor",
            project_id="test-project",
            north_star="Ensure test coverage.",
            success_criteria=["Maintain >80% code coverage"],
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.glm_clients import GLMAuditorClient

        client = GLMAuditorClient()

        # Build prompt
        phase_spec = {
            "run_id": "test-glm-auditor",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Add new utility function",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                patch_content="diff --git a/utils.py b/utils.py\n+def helper(): pass",
                phase_spec=phase_spec,
                project_rules=None,
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Ensure test coverage" in prompt
        assert "80% code coverage" in prompt


@pytest.mark.skip(reason="AnthropicAuditorClient was removed during refactoring")
def test_anthropic_auditor_prompt_includes_anchor():
    """Test that Anthropic Auditor prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-anthropic-auditor",
            project_id="test-project",
            north_star="Maintain API backwards compatibility.",
            constraints=IntentionConstraints(must_not=["Change existing API response formats"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import and create client
        from autopack.anthropic_clients import AnthropicAuditorClient

        client = AnthropicAuditorClient(api_key="test-key")

        # Build prompt
        phase_spec = {
            "run_id": "test-anthropic-auditor",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Add new API endpoint",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = client._build_user_prompt(
                patch_content="diff --git a/api.py b/api.py\n+@app.get('/new')",
                phase_spec=phase_spec,
                file_context=None,
                project_rules=None,
            )
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Maintain API backwards compatibility" in prompt
        assert "Change existing API response formats" in prompt


# =============================================================================
# Doctor Prompt Wiring Tests
# =============================================================================


def test_doctor_prompt_includes_anchor():
    """Test that Doctor prompts include intention anchor when available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create anchor
        anchor = create_anchor(
            run_id="test-doctor",
            project_id="test-project",
            north_star="Build reliable error recovery.",
            success_criteria=["Handle transient failures gracefully"],
            constraints=IntentionConstraints(must=["Preserve data integrity"]),
        )
        save_anchor(anchor, base_dir=tmpdir)

        # Import doctor module
        from autopack.llm import doctor

        # Build Doctor request
        request = DoctorRequest(
            run_id="test-doctor",
            phase_id="F1.1",
            error_category="patch_validation_error",
            builder_attempts=2,
            health_budget={
                "http_500": 0,
                "patch_failures": 2,
                "total_failures": 2,
                "total_cap": 25,
            },
            patch_errors=[{"error_type": "syntax_error", "message": "Invalid syntax at line 42"}],
            last_patch="diff --git a/test.py b/test.py\n+invalid syntax here",
        )

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            prompt = doctor._build_doctor_user_message(request)
        finally:
            os.chdir(original_cwd)

        # Verify anchor content is in prompt
        assert "Build reliable error recovery" in prompt
        assert "Handle transient failures gracefully" in prompt
        assert "Preserve data integrity" in prompt


# =============================================================================
# Graceful Degradation Tests
# =============================================================================


def test_builder_prompt_without_anchor_degrades_gracefully():
    """Test that Builder prompts work when anchor is missing (graceful degradation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Don't create anchor - test missing anchor scenario

        from autopack.openai_clients import OpenAIBuilderClient

        client = OpenAIBuilderClient()

        phase_spec = {
            "run_id": "nonexistent-run",
            "phase_id": "F1.1",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Implement feature",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Should not raise exception
            prompt = client._build_user_prompt(
                phase_spec=phase_spec, file_context=None, project_rules=None
            )
        finally:
            os.chdir(original_cwd)

        # Prompt should be generated without anchor content
        assert prompt is not None
        assert len(prompt) > 0


def test_auditor_prompt_without_anchor_degrades_gracefully():
    """Test that Auditor prompts work when anchor is missing (graceful degradation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Don't create anchor

        from autopack.openai_clients import OpenAIAuditorClient

        client = OpenAIAuditorClient()

        phase_spec = {
            "run_id": "nonexistent-run",
            "task_category": "feature",
            "description": "Add feature",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Should not raise exception
            prompt = client._build_user_prompt(
                patch_content="diff --git a/test.py b/test.py\n+print('test')",
                phase_spec=phase_spec,
                project_rules=None,
            )
        finally:
            os.chdir(original_cwd)

        # Prompt should be generated without anchor content
        assert prompt is not None
        assert len(prompt) > 0


def test_doctor_prompt_without_anchor_degrades_gracefully():
    """Test that Doctor prompts work when anchor is missing (graceful degradation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Don't create anchor

        from autopack.llm import doctor

        request = DoctorRequest(
            run_id="nonexistent-run",
            phase_id="F1.1",
            error_category="patch_validation_error",
            builder_attempts=1,
            health_budget={
                "http_500": 0,
                "patch_failures": 1,
                "total_failures": 1,
                "total_cap": 25,
            },
        )

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Should not raise exception
            prompt = doctor._build_doctor_user_message(request)
        finally:
            os.chdir(original_cwd)

        # Prompt should be generated without anchor content
        assert prompt is not None
        assert len(prompt) > 0


def test_prompt_without_run_id_degrades_gracefully():
    """Test that prompts work when run_id is not provided in phase_spec."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from autopack.openai_clients import OpenAIBuilderClient

        client = OpenAIBuilderClient()

        # Phase spec without run_id
        phase_spec = {
            "phase_id": "F1.1",
            "task_category": "feature",
            "complexity": "medium",
            "description": "Implement feature",
        }

        # Temporarily change working directory to tmpdir
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # Should not raise exception
            prompt = client._build_user_prompt(
                phase_spec=phase_spec, file_context=None, project_rules=None
            )
        finally:
            os.chdir(original_cwd)

        # Prompt should be generated without anchor content
        assert prompt is not None
        assert len(prompt) > 0
