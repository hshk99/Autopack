"""Contract tests for storage router.

These tests verify the storage router behavior contract is preserved
during the extraction from main.py to api/routes/storage.py (PR-API-3c).
"""

import pytest


class TestStorageRouterContract:
    """Contract tests for storage router configuration."""

    def test_router_has_storage_prefix(self):
        """Contract: Storage router uses /storage prefix."""
        from autopack.api.routes.storage import router

        assert router.prefix == "/storage"

    def test_router_has_storage_tag(self):
        """Contract: Storage router is tagged as 'storage'."""
        from autopack.api.routes.storage import router

        assert "storage" in router.tags


class TestTriggerStorageScanContract:
    """Contract tests for trigger_storage_scan endpoint."""

    def test_trigger_scan_rejects_invalid_scan_type(self):
        """Contract: /storage/scan rejects invalid scan_type with 400."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.storage import trigger_storage_scan

        mock_request = MagicMock()
        mock_request.scan_type = "invalid_type"
        mock_request.scan_target = "C:/test"
        mock_request.max_depth = 3
        mock_request.max_items = 100
        mock_request.save_to_db = False

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy"):
            with patch("autopack.storage_optimizer.StorageScanner"):
                with pytest.raises(HTTPException) as exc_info:
                    trigger_storage_scan(mock_request, mock_db)

        assert exc_info.value.status_code == 400
        assert "Invalid scan_type" in exc_info.value.detail

    def test_trigger_scan_accepts_directory_type(self):
        """Contract: /storage/scan accepts 'directory' scan_type."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import trigger_storage_scan

        mock_request = MagicMock()
        mock_request.scan_type = "directory"
        mock_request.scan_target = "C:/test"
        mock_request.max_depth = 3
        mock_request.max_items = 100
        mock_request.save_to_db = False
        mock_request.created_by = "test@example.com"

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy") as mock_load_policy:
            mock_policy = MagicMock()
            mock_load_policy.return_value = mock_policy

            with patch("autopack.storage_optimizer.StorageScanner") as mock_scanner_cls:
                mock_scanner = MagicMock()
                mock_scanner.scan_directory.return_value = []
                mock_scanner_cls.return_value = mock_scanner

                with patch("autopack.storage_optimizer.FileClassifier") as mock_classifier_cls:
                    mock_classifier = MagicMock()
                    mock_classifier.classify_batch.return_value = []
                    mock_classifier_cls.return_value = mock_classifier

                    result = trigger_storage_scan(mock_request, mock_db)

        assert result.scan_type == "directory"
        assert result.id == -1  # Non-persisted

    def test_trigger_scan_accepts_drive_type(self):
        """Contract: /storage/scan accepts 'drive' scan_type."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import trigger_storage_scan

        mock_request = MagicMock()
        mock_request.scan_type = "drive"
        mock_request.scan_target = "C:/"
        mock_request.max_depth = 3
        mock_request.max_items = 100
        mock_request.save_to_db = False
        mock_request.created_by = "test@example.com"

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy") as mock_load_policy:
            mock_policy = MagicMock()
            mock_load_policy.return_value = mock_policy

            with patch("autopack.storage_optimizer.StorageScanner") as mock_scanner_cls:
                mock_scanner = MagicMock()
                mock_scanner.scan_high_value_directories.return_value = []
                mock_scanner_cls.return_value = mock_scanner

                with patch("autopack.storage_optimizer.FileClassifier") as mock_classifier_cls:
                    mock_classifier = MagicMock()
                    mock_classifier.classify_batch.return_value = []
                    mock_classifier_cls.return_value = mock_classifier

                    result = trigger_storage_scan(mock_request, mock_db)

        assert result.scan_type == "drive"


class TestListStorageScansContract:
    """Contract tests for list_storage_scans endpoint."""

    def test_list_scans_enforces_max_limit(self):
        """Contract: /storage/scans enforces max limit of 200."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import list_storage_scans

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_history") as mock_get_history:
            mock_get_history.return_value = []

            # Call with limit > 200
            list_storage_scans(
                limit=500,
                offset=0,
                since_days=None,
                scan_type=None,
                scan_target=None,
                db=mock_db,
                _auth="test",
            )

            # Should have been capped to 200
            mock_get_history.assert_called_once_with(
                mock_db,
                limit=200,
                offset=0,
                since_days=None,
                scan_type=None,
                scan_target=None,
            )

    def test_list_scans_passes_filters(self):
        """Contract: /storage/scans passes filter parameters correctly."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import list_storage_scans

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_history") as mock_get_history:
            mock_get_history.return_value = []

            list_storage_scans(
                limit=25,
                offset=10,
                since_days=30,
                scan_type="directory",
                scan_target="C:/dev",
                db=mock_db,
                _auth="test",
            )

            mock_get_history.assert_called_once_with(
                mock_db,
                limit=25,
                offset=10,
                since_days=30,
                scan_type="directory",
                scan_target="C:/dev",
            )


class TestGetStorageScanDetailContract:
    """Contract tests for get_storage_scan_detail endpoint."""

    def test_scan_detail_returns_404_for_missing(self):
        """Contract: /storage/scans/{scan_id} returns 404 for missing scan."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.storage import get_storage_scan_detail

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_by_id") as mock_get_scan:
            mock_get_scan.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                get_storage_scan_detail(scan_id=999, db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "999 not found" in exc_info.value.detail


class TestApproveCleanupCandidatesContract:
    """Contract tests for approve_cleanup_candidates endpoint."""

    def test_approve_returns_404_for_missing_scan(self):
        """Contract: /storage/scans/{scan_id}/approve returns 404 for missing scan."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.storage import approve_cleanup_candidates

        mock_request = MagicMock()
        mock_request.decision = "approve"
        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_by_id") as mock_get_scan:
            mock_get_scan.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                approve_cleanup_candidates(scan_id=999, request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 404

    def test_approve_rejects_invalid_decision(self):
        """Contract: /storage/scans/{scan_id}/approve rejects invalid decision."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.storage import approve_cleanup_candidates

        mock_request = MagicMock()
        mock_request.decision = "invalid_decision"
        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_by_id") as mock_get_scan:
            mock_get_scan.return_value = MagicMock()  # Scan exists

            with pytest.raises(HTTPException) as exc_info:
                approve_cleanup_candidates(scan_id=1, request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "Invalid decision" in exc_info.value.detail

    def test_approve_accepts_valid_decisions(self):
        """Contract: /storage/scans/{scan_id}/approve accepts approve/reject/defer."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import approve_cleanup_candidates

        for decision in ["approve", "reject", "defer"]:
            mock_request = MagicMock()
            mock_request.decision = decision
            mock_request.candidate_ids = [1, 2, 3]
            mock_request.approved_by = "test@example.com"
            mock_request.approval_method = "api"
            mock_request.notes = "Test"

            mock_db = MagicMock()

            with patch("autopack.storage_optimizer.db.get_scan_by_id") as mock_get_scan:
                mock_get_scan.return_value = MagicMock()

                with patch("autopack.storage_optimizer.db.create_approval_decision") as mock_create:
                    mock_approval = MagicMock()
                    mock_approval.id = 1
                    mock_approval.total_candidates = 3
                    mock_approval.total_size_bytes = 1000
                    mock_approval.approved_at = "2024-01-01T00:00:00Z"
                    mock_create.return_value = mock_approval

                    result = approve_cleanup_candidates(scan_id=1, request=mock_request, db=mock_db)

            assert result["decision"] == decision


class TestExecuteApprovedCleanupContract:
    """Contract tests for execute_approved_cleanup endpoint."""

    def test_execute_returns_404_for_missing_scan(self):
        """Contract: /storage/scans/{scan_id}/execute returns 404 for missing scan."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.storage import execute_approved_cleanup

        mock_request = MagicMock()
        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.db.get_scan_by_id") as mock_get_scan:
            mock_get_scan.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                execute_approved_cleanup(scan_id=999, request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 404


class TestGetSteamGamesContract:
    """Contract tests for get_steam_games endpoint."""

    def test_steam_games_returns_unavailable_response(self):
        """Contract: /storage/steam/games returns proper response when Steam unavailable."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import get_steam_games

        with patch(
            "autopack.storage_optimizer.steam_detector.SteamGameDetector"
        ) as mock_detector_cls:
            mock_detector = MagicMock()
            mock_detector.is_available.return_value = False
            mock_detector_cls.return_value = mock_detector

            result = get_steam_games(
                min_size_gb=10.0, min_age_days=180, include_all=False, _auth="test"
            )

        assert result.steam_available is False
        assert result.total_games == 0
        assert result.games == []


class TestAnalyzeApprovalPatternsContract:
    """Contract tests for analyze_approval_patterns endpoint."""

    def test_patterns_returns_list(self):
        """Contract: /storage/patterns/analyze returns list of patterns."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import analyze_approval_patterns

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy") as mock_load_policy:
            mock_load_policy.return_value = MagicMock()

            with patch(
                "autopack.storage_optimizer.approval_pattern_analyzer.ApprovalPatternAnalyzer"
            ) as mock_analyzer_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze_approval_patterns.return_value = []
                mock_analyzer_cls.return_value = mock_analyzer

                result = analyze_approval_patterns(category=None, max_patterns=10, db=mock_db)

        assert isinstance(result, list)


class TestGetLearnedRulesContract:
    """Contract tests for get_learned_rules endpoint."""

    def test_learned_rules_filters_by_status(self):
        """Contract: /storage/learned-rules filters by status parameter."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import get_learned_rules

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        with patch("autopack.models.LearnedRule") as mock_learned_rule:
            mock_learned_rule.status = "status_field"
            mock_learned_rule.confidence_score = MagicMock()
            mock_learned_rule.confidence_score.desc.return_value = "desc_confidence"
            mock_learned_rule.created_at = MagicMock()
            mock_learned_rule.created_at.desc.return_value = "desc_created"

            result = get_learned_rules(status="pending", db=mock_db, _auth="test")

        mock_query.filter.assert_called_once()
        assert isinstance(result, list)


class TestApproveLearnedRuleContract:
    """Contract tests for approve_learned_rule endpoint."""

    def test_approve_rule_calls_analyzer(self):
        """Contract: /storage/learned-rules/{rule_id}/approve calls analyzer.approve_rule."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import approve_learned_rule

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy") as mock_load_policy:
            mock_load_policy.return_value = MagicMock()

            with patch(
                "autopack.storage_optimizer.approval_pattern_analyzer.ApprovalPatternAnalyzer"
            ) as mock_analyzer_cls:
                mock_analyzer = MagicMock()
                mock_rule = MagicMock()
                mock_rule.id = 1
                mock_rule.created_at.isoformat.return_value = "2024-01-01T00:00:00"
                mock_rule.pattern_type = "extension"
                mock_rule.pattern_value = "*.log"
                mock_rule.suggested_category = "logs"
                mock_rule.confidence_score = 0.95
                mock_rule.based_on_approvals = 10
                mock_rule.based_on_rejections = 0
                mock_rule.sample_paths = "[]"
                mock_rule.status = "approved"
                mock_rule.reviewed_by = "admin"
                mock_rule.reviewed_at = None
                mock_rule.description = "Test rule"
                mock_rule.notes = None
                mock_analyzer.approve_rule.return_value = mock_rule
                mock_analyzer_cls.return_value = mock_analyzer

                result = approve_learned_rule(rule_id=1, approved_by="admin", db=mock_db)

        mock_analyzer.approve_rule.assert_called_once_with(1, "admin")
        assert result.id == 1


class TestGetStorageRecommendationsContract:
    """Contract tests for get_storage_recommendations endpoint."""

    def test_recommendations_returns_structured_response(self):
        """Contract: /storage/recommendations returns RecommendationsListResponse."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.storage import get_storage_recommendations

        mock_db = MagicMock()

        with patch("autopack.storage_optimizer.load_policy") as mock_load_policy:
            mock_load_policy.return_value = MagicMock()

            with patch(
                "autopack.storage_optimizer.recommendation_engine.RecommendationEngine"
            ) as mock_engine_cls:
                mock_engine = MagicMock()
                mock_engine.generate_recommendations.return_value = []
                mock_engine.get_scan_statistics.return_value = {}
                mock_engine_cls.return_value = mock_engine

                result = get_storage_recommendations(
                    max_recommendations=10, lookback_days=90, db=mock_db, _auth="test"
                )

        assert hasattr(result, "recommendations")
        assert hasattr(result, "scan_statistics")
        assert isinstance(result.recommendations, list)
