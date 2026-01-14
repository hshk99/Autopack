"""BUILD-145: Smoke test for BUILD-144 migration runbook

Validates that the BUILD-144 migration runbook exists and contains key sections.
Lightweight string assertions to verify documentation completeness.
"""

import pytest
from pathlib import Path


class TestBuild144MigrationRunbookSmoke:
    """Smoke tests for BUILD-144 migration runbook documentation"""

    @pytest.fixture
    def runbook_path(self):
        """Path to BUILD-144 migration runbook"""
        return Path("docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md")

    def test_runbook_file_exists(self, runbook_path):
        """Runbook file exists at expected location"""
        assert runbook_path.exists(), f"Runbook not found at {runbook_path}"

    def test_runbook_has_content(self, runbook_path):
        """Runbook file is not empty"""
        content = runbook_path.read_text(encoding="utf-8")
        assert len(content) > 1000, "Runbook content suspiciously short"

    def test_runbook_has_required_sections(self, runbook_path):
        """Runbook contains all required sections"""
        content = runbook_path.read_text(encoding="utf-8")

        required_sections = [
            "# BUILD-144 Migration Runbook",
            "## What Changed in BUILD-144",
            "## Prerequisites",
            "## Migration Steps",
            "### Step 1: Set Environment Variables",
            "### Step 2: Run Migration Script",
            "### Step 3: Verify Migration Success",
            "## Post-Migration Verification",
            "## Troubleshooting",
            "## Rollback (If Needed)",
            "## Next Steps",
            "## Summary",
        ]

        for section in required_sections:
            assert section in content, f"Missing required section: {section}"

    def test_runbook_references_migration_script(self, runbook_path):
        """Runbook references the correct migration script"""
        content = runbook_path.read_text(encoding="utf-8")

        assert "scripts/migrations/add_total_tokens_build144.py" in content, (
            "Runbook must reference migration script path"
        )
        assert "upgrade" in content, "Runbook must mention 'upgrade' command"

    def test_runbook_has_environment_variables(self, runbook_path):
        """Runbook documents required environment variables"""
        content = runbook_path.read_text(encoding="utf-8")

        required_env_vars = ["DATABASE_URL", "PYTHONUTF8", "PYTHONPATH"]

        for env_var in required_env_vars:
            assert env_var in content, f"Missing environment variable: {env_var}"

    def test_runbook_has_verification_commands(self, runbook_path):
        """Runbook includes verification commands"""
        content = runbook_path.read_text(encoding="utf-8")

        # Should have Python verification snippet
        assert "from autopack.database import SessionLocal" in content, (
            "Runbook should include Python verification code"
        )

        # Should mention total_tokens column
        assert "total_tokens" in content.lower(), "Runbook must reference total_tokens column"

        # Should mention nullable columns
        assert "prompt_tokens" in content, "Runbook must reference prompt_tokens"
        assert "completion_tokens" in content, "Runbook must reference completion_tokens"
        assert "nullable" in content.lower(), "Runbook must explain nullable semantics"

    def test_runbook_has_sql_verification(self, runbook_path):
        """Runbook includes SQL verification queries"""
        content = runbook_path.read_text(encoding="utf-8")

        assert "sqlite3" in content, "Runbook should include sqlite3 commands"
        assert "SELECT" in content, "Runbook should include SQL SELECT queries"
        assert "llm_usage_events" in content, "Runbook must reference table name"

    def test_runbook_documents_null_safety(self, runbook_path):
        """Runbook explains NULL-safe dashboard aggregation"""
        content = runbook_path.read_text(encoding="utf-8")

        # Should explain total-only recording
        assert "total-only" in content.lower() or "total only" in content.lower(), (
            "Runbook must explain total-only recording"
        )

        # Should mention NULL handling
        assert "NULL" in content, "Runbook must explain NULL token splits"

        # Should reference dashboard
        assert "dashboard" in content.lower(), "Runbook must mention dashboard aggregation"

    def test_runbook_has_troubleshooting(self, runbook_path):
        """Runbook includes troubleshooting section with common issues"""
        content = runbook_path.read_text(encoding="utf-8")

        common_issues = ["database is locked", "already exists"]

        for issue in common_issues:
            assert issue.lower() in content.lower(), f"Runbook should address common issue: {issue}"

    def test_runbook_has_rollback_instructions(self, runbook_path):
        """Runbook includes rollback instructions"""
        content = runbook_path.read_text(encoding="utf-8")

        assert "backup" in content.lower(), "Runbook must emphasize backups"
        assert "rollback" in content.lower(), "Runbook must include rollback section"

    def test_runbook_references_related_files(self, runbook_path):
        """Runbook references related source and test files"""
        content = runbook_path.read_text(encoding="utf-8")

        related_files = [
            "usage_recorder.py",
            "llm_service.py",
            "main.py",
            "test_llm_usage_schema_drift.py",
            "test_dashboard_null_tokens.py",
        ]

        for file in related_files:
            assert file in content, f"Runbook should reference: {file}"

    def test_runbook_has_build_history_reference(self, runbook_path):
        """Runbook links to BUILD_HISTORY.md and README.md"""
        content = runbook_path.read_text(encoding="utf-8")

        assert "README.md" in content, "Runbook should link to README.md"
        assert "BUILD_HISTORY.md" in content, "Runbook should link to BUILD_HISTORY.md"
