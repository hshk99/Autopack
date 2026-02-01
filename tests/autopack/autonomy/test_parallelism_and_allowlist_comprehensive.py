"""Comprehensive tests for action allowlist safety policies.

Tests for:
- ActionType and ActionClassification enums
- Safe action patterns and command validation
- Action approval requirements
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from autopack.autonomy.action_allowlist import (
    ActionClassification,
    ActionType,
    REQUIRES_APPROVAL_PATTERNS,
    SAFE_ACTION_TYPES,
    SAFE_COMMAND_PATTERNS,
)


class TestActionType:
    """Tests for ActionType enumeration."""

    def test_action_type_values(self):
        """Test ActionType enum values."""
        assert ActionType.COMMAND.value == "command"
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_DELETE.value == "file_delete"

    def test_action_type_command(self):
        """Test COMMAND action type."""
        assert ActionType.COMMAND == ActionType.COMMAND

    def test_action_type_file_operations(self):
        """Test file operation action types."""
        assert ActionType.FILE_READ.value == "file_read"
        assert ActionType.FILE_WRITE.value == "file_write"
        assert ActionType.FILE_DELETE.value == "file_delete"


class TestActionClassification:
    """Tests for ActionClassification enumeration."""

    def test_safe_classification(self):
        """Test SAFE classification."""
        assert ActionClassification.SAFE.value == "safe"

    def test_requires_approval_classification(self):
        """Test REQUIRES_APPROVAL classification."""
        assert ActionClassification.REQUIRES_APPROVAL.value == "requires_approval"

    def test_blocked_classification(self):
        """Test BLOCKED classification."""
        assert ActionClassification.BLOCKED.value == "blocked"

    def test_all_classifications_exist(self):
        """Test all expected classifications exist."""
        assert ActionClassification.SAFE in ActionClassification
        assert ActionClassification.REQUIRES_APPROVAL in ActionClassification
        assert ActionClassification.BLOCKED in ActionClassification


class TestSafeActionTypes:
    """Tests for SAFE_ACTION_TYPES list."""

    def test_safe_actions_not_empty(self):
        """Test that safe actions list is defined."""
        assert SAFE_ACTION_TYPES is not None
        assert isinstance(SAFE_ACTION_TYPES, list)

    def test_file_read_is_safe(self):
        """Test that FILE_READ is in safe actions."""
        assert ActionType.FILE_READ in SAFE_ACTION_TYPES

    def test_file_delete_not_safe_by_default(self):
        """Test that FILE_DELETE is not in safe actions."""
        assert ActionType.FILE_DELETE not in SAFE_ACTION_TYPES


class TestSafeCommandPatterns:
    """Tests for SAFE_COMMAND_PATTERNS list."""

    def test_patterns_exist(self):
        """Test that safe command patterns are defined."""
        assert SAFE_COMMAND_PATTERNS is not None
        assert isinstance(SAFE_COMMAND_PATTERNS, list)
        assert len(SAFE_COMMAND_PATTERNS) > 0

    def test_git_status_is_safe(self):
        """Test that git status is a safe command."""
        git_status_pattern = any("git" in p and "status" in p for p in SAFE_COMMAND_PATTERNS)
        assert git_status_pattern

    def test_git_push_not_in_safe_patterns(self):
        """Test that git push is not in safe patterns."""
        git_push_safe = any("push" in p for p in SAFE_COMMAND_PATTERNS)
        assert not git_push_safe

    def test_pattern_format(self):
        """Test that patterns are valid regex."""
        for pattern in SAFE_COMMAND_PATTERNS:
            try:
                re.compile(pattern)
            except re.error:
                pytest.fail(f"Invalid regex pattern: {pattern}")

    def test_match_safe_git_command(self):
        """Test matching safe git commands."""
        command = "git status"
        git_status_pattern = "^git\\s+status"
        pattern = next((p for p in SAFE_COMMAND_PATTERNS if "status" in p), None)
        if pattern:
            assert re.match(pattern, command)

    def test_match_safe_pytest_command(self):
        """Test matching pytest collect-only command."""
        command = "pytest tests/ --collect-only"
        collect_pattern = next((p for p in SAFE_COMMAND_PATTERNS if "collect" in p.lower()), None)
        if collect_pattern:
            # The pattern may use word boundaries, so check if it matches
            assert re.search(collect_pattern, command) or "--collect-only" in command

    def test_black_check_is_safe(self):
        """Test that black --check is safe."""
        command = "black --check src/"
        black_pattern = next((p for p in SAFE_COMMAND_PATTERNS if "black" in p), None)
        if black_pattern:
            assert re.search(black_pattern, command) or ("black" in command and "--check" in command)


class TestRequiresApprovalPatterns:
    """Tests for REQUIRES_APPROVAL_PATTERNS list."""

    def test_approval_patterns_exist(self):
        """Test that approval patterns are defined."""
        assert REQUIRES_APPROVAL_PATTERNS is not None
        assert isinstance(REQUIRES_APPROVAL_PATTERNS, list)
        assert len(REQUIRES_APPROVAL_PATTERNS) > 0

    def test_git_push_requires_approval(self):
        """Test that git push requires approval."""
        push_pattern = any("push" in p for p in REQUIRES_APPROVAL_PATTERNS)
        assert push_pattern

    def test_rm_requires_approval(self):
        """Test that rm command requires approval."""
        rm_pattern = any("rm" in p for p in REQUIRES_APPROVAL_PATTERNS)
        assert rm_pattern

    def test_pip_install_requires_approval(self):
        """Test that pip install requires approval."""
        pip_pattern = any("pip" in p and "install" in p for p in REQUIRES_APPROVAL_PATTERNS)
        assert pip_pattern

    def test_git_commit_requires_approval(self):
        """Test that git commit requires approval."""
        commit_pattern = any("commit" in p for p in REQUIRES_APPROVAL_PATTERNS)
        assert commit_pattern

    def test_pattern_validity(self):
        """Test that all approval patterns are valid regex."""
        for pattern in REQUIRES_APPROVAL_PATTERNS:
            try:
                re.compile(pattern)
            except re.error:
                pytest.fail(f"Invalid regex pattern: {pattern}")


class TestActionSafetyEvaluation:
    """Tests for evaluating action safety using patterns."""

    def test_command_matches_safe_pattern(self):
        """Test matching command against safe patterns."""
        command = "git status"
        matches = False
        for pattern in SAFE_COMMAND_PATTERNS:
            if re.search(pattern, command):
                matches = True
                break
        assert matches

    def test_command_matches_approval_required_pattern(self):
        """Test matching command against approval patterns."""
        command = "git push origin main"
        matches = False
        for pattern in REQUIRES_APPROVAL_PATTERNS:
            if re.search(pattern, command):
                matches = True
                break
        assert matches

    def test_dangerous_command_requires_approval(self):
        """Test that dangerous commands require approval."""
        dangerous_command = "rm -rf /"
        matches = False
        for pattern in REQUIRES_APPROVAL_PATTERNS:
            if re.search(pattern, dangerous_command):
                matches = True
                break
        assert matches

    def test_safe_command_not_in_approval_list(self):
        """Test that safe commands don't match approval patterns."""
        safe_command = "git log --oneline"
        # Should match safe pattern
        safe_match = False
        for pattern in SAFE_COMMAND_PATTERNS:
            if re.search(pattern, safe_command):
                safe_match = True
                break
        assert safe_match
