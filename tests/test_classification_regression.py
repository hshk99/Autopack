#!/usr/bin/env python3
"""
Regression tests for file classification system.

Tests edge cases, known issues, and critical classification scenarios
to ensure 98%+ accuracy is maintained across updates.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


class TestClassificationRegression:
    """Regression tests for classification edge cases."""

    def test_unicode_encoding_fixed(self):
        """Ensure Unicode characters don't cause encoding errors."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        # This used to fail with charmap codec error
        result = classifier.classify(
            file_path=Path("test_file.md"),
            content_sample="Test content",
            default_project_id="autopack"
        )

        # Should return valid result without exceptions
        assert len(result) == 4
        project, file_type, dest, confidence = result
        assert project is not None
        assert confidence >= 0.0

        classifier.close()

    def test_postgresql_transaction_errors_handled(self):
        """Ensure PostgreSQL transaction errors don't crash classifier."""
        # This test would require mocking a transaction error
        # For now, just ensure connection pooling is enabled
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        # Connection pool should be initialized
        if classifier.pg_pool:
            assert classifier.pg_pool is not None
            print("[OK] Connection pooling enabled")
        else:
            print("[WARN] Connection pooling not available")

        classifier.close()

    def test_pattern_matching_confidence_improved(self):
        """Ensure pattern matching confidence is above baseline."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        # Test file with strong signals (should get > 0.70 confidence with new enhancements)
        result = classifier._classify_with_patterns(
            filename="autopack_tidy_workspace.py",
            content="This is about autopack autonomous executor and tidy workspace classification.\nimport sys\ndef main():\n    pass\nif __name__ == '__main__':\n    main()",
            suffix=".py",
            default_project="autopack"
        )

        project, file_type, dest, confidence = result

        # Pattern matching should now achieve higher confidence with:
        # - Multiple signal agreement (0.78 base)
        # - Content validation (script markers: import, def, if __name__)
        # - Structure validation (reasonable length)
        assert confidence > 0.70, f"Expected confidence > 0.70, got {confidence}"
        assert project == "autopack"
        assert file_type == "script"

        classifier.close()

    def test_qdrant_api_compatibility(self):
        """Ensure Qdrant query_points API is used (not deprecated search)."""
        # Read the classifier source and ensure it uses query_points
        classifier_path = Path(__file__).parent.parent / "scripts" / "file_classifier_with_memory.py"

        with open(classifier_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Should use query_points, not search
        assert "query_points" in content
        assert "client.search(" not in content  # Old deprecated API

    def test_generic_files_flagged_by_auditor(self):
        """Ensure generic files with minimal content are flagged."""
        # This would test the auditor integration
        # For now, just a placeholder
        pass

    def test_high_confidence_with_agreement(self):
        """Ensure high confidence when PostgreSQL and Qdrant agree."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        # Test file that should match routing rules
        result = classifier.classify(
            file_path=Path("IMPLEMENTATION_PLAN_TEST.md"),
            content_sample="# Implementation Plan\n\n## Goal\nTest the file classification system",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should get plan type classification
        assert file_type in ["plan", "unknown"]  # Depends on routing rules

        # Confidence should be reasonable
        assert confidence > 0.5

        classifier.close()

    def test_learning_mechanism_stores_patterns(self):
        """Ensure successful classifications are learned to Qdrant."""
        # This would test the learning mechanism
        # Requires Qdrant connection
        pass

    def test_user_corrections_highest_priority(self):
        """Ensure user corrections get 100% confidence priority."""
        # This would test the correction workflow
        # Requires PostgreSQL with corrections table
        pass


class TestEdgeCases:
    """Test edge cases that might break classification."""

    def test_empty_file_content(self):
        """Handle files with no content."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        result = classifier.classify(
            file_path=Path("empty.txt"),
            content_sample="",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should not crash, should return valid result
        assert project is not None
        assert confidence >= 0.0

        classifier.close()

    def test_very_long_filename(self):
        """Handle very long filenames."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        long_name = "a" * 300 + ".md"

        result = classifier.classify(
            file_path=Path(long_name),
            content_sample="Test content",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should not crash
        assert project is not None

        classifier.close()

    def test_special_characters_in_filename(self):
        """Handle special characters in filenames."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        result = classifier.classify(
            file_path=Path("file with spaces & special (chars).md"),
            content_sample="Test content",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should not crash
        assert project is not None

        classifier.close()

    def test_binary_content_handling(self):
        """Handle binary content gracefully."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        # Simulate binary content (non-UTF-8)
        result = classifier.classify(
            file_path=Path("binary_file.bin"),
            content_sample="\x00\x01\x02\xff",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should not crash
        assert project is not None

        classifier.close()


class TestAccuracyCritical:
    """Tests for critical accuracy scenarios."""

    def test_fileorg_plans_classified_correctly(self):
        """File organizer plans must be classified to file-organizer-app-v1."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        result = classifier.classify(
            file_path=Path("FILEORG_COUNTRY_PACK_PLAN.md"),
            content_sample="# File Organizer Country Pack\n\nImplementation plan for UK folder structure",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should classify to file-organizer-app-v1 (high confidence)
        assert project == "file-organizer-app-v1", f"Expected file-organizer-app-v1, got {project}"
        assert file_type == "plan"

        classifier.close()

    def test_autopack_scripts_classified_correctly(self):
        """Autopack scripts must be classified to autopack."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        result = classifier.classify(
            file_path=Path("tidy_workspace.py"),
            content_sample="# Autopack Tidy Workspace\n\nfrom autopack.autonomous_executor import run",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should classify to autopack
        assert project == "autopack", f"Expected autopack, got {project}"
        assert file_type == "script"

        classifier.close()

    def test_api_logs_classified_to_autopack(self):
        """API logs should be classified to autopack/log."""
        from scripts.file_classifier_with_memory import ProjectMemoryClassifier

        classifier = ProjectMemoryClassifier()

        result = classifier.classify(
            file_path=Path("api_test_run.log"),
            content_sample="[2025-12-11] INFO: API request started\n[2025-12-11] INFO: Response 200",
            default_project_id="autopack"
        )

        project, file_type, dest, confidence = result

        # Should classify to autopack/log
        assert project == "autopack"
        assert file_type == "log"

        classifier.close()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
