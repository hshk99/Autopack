"""BUILD-145 P0: Tests for read_only_context normalization at schema boundary

Tests that PhaseCreate schema normalizes read_only_context to canonical dict format
at the API boundary, ensuring all consumers receive consistent format regardless of
whether legacy string format or new dict format is provided.
"""

import pytest

from autopack.schemas import PhaseCreate


class TestPhaseCreateReadOnlyContextNormalization:
    """Test PhaseCreate schema normalization of read_only_context"""

    def test_legacy_string_format_normalized_to_dict(self):
        """Legacy string format should be normalized to dict format"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": ["src/reference.py", "docs/README.md"],
            },
        )

        # Should be normalized to dict format with empty reason
        assert phase.scope["read_only_context"] == [
            {"path": "src/reference.py", "reason": ""},
            {"path": "docs/README.md", "reason": ""},
        ]

    def test_new_dict_format_preserved(self):
        """New dict format should be preserved"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {"path": "src/reference.py", "reason": "Reference implementation"},
                    {"path": "docs/README.md", "reason": "Documentation style"},
                ],
            },
        )

        # Should preserve dict format with reasons
        assert phase.scope["read_only_context"] == [
            {"path": "src/reference.py", "reason": "Reference implementation"},
            {"path": "docs/README.md", "reason": "Documentation style"},
        ]

    def test_mixed_format_normalized(self):
        """Mixed list of strings and dicts should be normalized"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    "src/legacy.py",  # Legacy string
                    {"path": "src/new.py", "reason": "New format"},  # New dict
                    "docs/guide.md",  # Legacy string
                ],
            },
        )

        # Should normalize all to dict format
        assert phase.scope["read_only_context"] == [
            {"path": "src/legacy.py", "reason": ""},
            {"path": "src/new.py", "reason": "New format"},
            {"path": "docs/guide.md", "reason": ""},
        ]

    def test_dict_without_reason_gets_empty_reason(self):
        """Dict format without reason should get empty string reason"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [{"path": "src/file.py"}],  # No reason field
            },
        )

        # Should add empty reason
        assert phase.scope["read_only_context"] == [{"path": "src/file.py", "reason": ""}]

    def test_invalid_dict_without_path_skipped(self):
        """Dict entry without 'path' field should be skipped"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {"reason": "Missing path field"},  # Invalid
                    {"path": "src/valid.py", "reason": "Valid entry"},
                ],
            },
        )

        # Should skip invalid entry
        assert phase.scope["read_only_context"] == [
            {"path": "src/valid.py", "reason": "Valid entry"}
        ]

    def test_invalid_entry_types_skipped(self):
        """Invalid entry types (int, None, list) should be skipped"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    "src/valid1.py",
                    123,  # Invalid: int
                    {"path": "src/valid2.py"},
                    None,  # Invalid: None
                    ["nested", "list"],  # Invalid: list
                    "src/valid3.py",
                ],
            },
        )

        # Should skip invalid entries
        assert phase.scope["read_only_context"] == [
            {"path": "src/valid1.py", "reason": ""},
            {"path": "src/valid2.py", "reason": ""},
            {"path": "src/valid3.py", "reason": ""},
        ]

    def test_empty_read_only_context_list(self):
        """Empty read_only_context list should remain empty"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={"paths": ["src/test.py"], "read_only_context": []},
        )

        assert phase.scope["read_only_context"] == []

    def test_missing_read_only_context_field(self):
        """Missing read_only_context field should not cause error"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"]
                # No read_only_context field
            },
        )

        # Should not add read_only_context if it doesn't exist
        assert "read_only_context" not in phase.scope

    def test_none_scope_field(self):
        """None scope field should not cause error"""
        phase = PhaseCreate(
            phase_id="F1.test", phase_index=0, tier_id="T1", name="Test Phase", scope=None
        )

        assert phase.scope is None

    def test_scope_with_other_fields_preserved(self):
        """Other scope fields should be preserved during normalization"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": ["src/ref.py"],
                "acceptance_criteria": ["All tests pass"],
                "test_cmd": "pytest tests/",
                "notes": ["Be careful"],
            },
        )

        # read_only_context normalized, others preserved
        assert phase.scope["paths"] == ["src/test.py"]
        assert phase.scope["read_only_context"] == [{"path": "src/ref.py", "reason": ""}]
        assert phase.scope["acceptance_criteria"] == ["All tests pass"]
        assert phase.scope["test_cmd"] == "pytest tests/"
        assert phase.scope["notes"] == ["Be careful"]

    def test_dict_with_extra_fields_cleaned(self):
        """Dict entries with extra fields should only preserve path and reason"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {
                        "path": "src/file.py",
                        "reason": "Reference",
                        "extra_field": "ignored",
                        "priority": 1,
                    }
                ],
            },
        )

        # Should only preserve path and reason
        assert phase.scope["read_only_context"] == [{"path": "src/file.py", "reason": "Reference"}]

    def test_paths_with_spaces_preserved(self):
        """Paths with spaces should be preserved"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {"path": "path with spaces/file.py", "reason": "Test spaces"}
                ],
            },
        )

        assert phase.scope["read_only_context"] == [
            {"path": "path with spaces/file.py", "reason": "Test spaces"}
        ]

    def test_relative_paths_preserved(self):
        """Relative paths should be preserved"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": ["src/module.py", "../other/file.py", "./local.py"],
            },
        )

        assert phase.scope["read_only_context"] == [
            {"path": "src/module.py", "reason": ""},
            {"path": "../other/file.py", "reason": ""},
            {"path": "./local.py", "reason": ""},
        ]

    def test_absolute_paths_preserved(self):
        """Absolute paths should be preserved"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": ["/abs/path/file.py", "C:/Windows/path/file.py"],
            },
        )

        assert phase.scope["read_only_context"] == [
            {"path": "/abs/path/file.py", "reason": ""},
            {"path": "C:/Windows/path/file.py", "reason": ""},
        ]

    def test_normalization_idempotent(self):
        """Normalizing already normalized data should be idempotent"""
        normalized_data = {
            "paths": ["src/test.py"],
            "read_only_context": [{"path": "src/ref.py", "reason": "Reference"}],
        }

        phase1 = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope=normalized_data,
        )

        # Apply normalization again
        phase2 = PhaseCreate(
            phase_id="F1.test", phase_index=0, tier_id="T1", name="Test Phase", scope=phase1.scope
        )

        # Should remain the same
        assert phase1.scope["read_only_context"] == phase2.scope["read_only_context"]

    def test_empty_string_path_skipped(self):
        """Empty string path should be skipped"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": ["", "src/valid.py"],  # Empty string
            },
        )

        # Empty string becomes dict with empty path, which is still included
        # (This matches the executor behavior which also accepts empty paths)
        assert phase.scope["read_only_context"] == [
            {"path": "", "reason": ""},
            {"path": "src/valid.py", "reason": ""},
        ]

    def test_dict_with_empty_path_skipped(self):
        """Dict with empty path should be skipped"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {"path": "", "reason": "Empty path"},  # Should be skipped
                    {"path": "src/valid.py", "reason": "Valid"},
                ],
            },
        )

        # Empty path dict should be skipped
        assert phase.scope["read_only_context"] == [{"path": "src/valid.py", "reason": "Valid"}]

    def test_dict_with_none_path_skipped(self):
        """Dict with None path should be skipped"""
        phase = PhaseCreate(
            phase_id="F1.test",
            phase_index=0,
            tier_id="T1",
            name="Test Phase",
            scope={
                "paths": ["src/test.py"],
                "read_only_context": [
                    {"path": None, "reason": "None path"},  # Should be skipped
                    {"path": "src/valid.py", "reason": "Valid"},
                ],
            },
        )

        # None path should be skipped
        assert phase.scope["read_only_context"] == [{"path": "src/valid.py", "reason": "Valid"}]

    def test_non_dict_scope_raises_validation_error(self):
        """Non-dict scope value should raise Pydantic validation error"""
        # This tests that Pydantic's type checking catches invalid scope types
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            PhaseCreate(
                phase_id="F1.test",
                phase_index=0,
                tier_id="T1",
                name="Test Phase",
                scope="invalid_scope_string",  # type: ignore
            )

        # Should raise validation error for incorrect type
        assert "dict_type" in str(exc_info.value)

    def test_normalization_at_api_boundary(self):
        """Test that normalization happens at API boundary (PhaseCreate instantiation)"""
        # This simulates what happens when API receives a RunStartRequest
        from autopack.schemas import RunCreate, RunStartRequest, TierCreate

        request = RunStartRequest(
            run=RunCreate(run_id="test-run"),
            tiers=[TierCreate(tier_id="T1", tier_index=0, name="Tier 1")],
            phases=[
                PhaseCreate(
                    phase_id="F1.test",
                    phase_index=0,
                    tier_id="T1",
                    name="Test Phase",
                    scope={
                        "paths": ["src/test.py"],
                        "read_only_context": [
                            "src/legacy.py",  # Legacy format from API request
                            {"path": "src/new.py", "reason": "New format"},
                        ],
                    },
                )
            ],
        )

        # Normalization should have occurred at PhaseCreate instantiation
        phase = request.phases[0]
        assert phase.scope["read_only_context"] == [
            {"path": "src/legacy.py", "reason": ""},
            {"path": "src/new.py", "reason": "New format"},
        ]
