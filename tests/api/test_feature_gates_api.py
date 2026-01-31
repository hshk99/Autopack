"""Tests for Feature Gate API endpoints (IMP-REL-001).

Tests cover all feature gate REST API endpoints:
- GET /features - List all features
- GET /features/enabled - List enabled features
- GET /features/disabled - List disabled features
- GET /features/{feature_id} - Get feature details
- POST /features/{feature_id}/enable - Enable feature
- POST /features/{feature_id}/disable - Disable feature
- GET /features/validate - Validate feature state
"""

import pytest
from fastapi.testclient import TestClient

from autopack.api.app import create_app
from autopack.feature_gates import reset_feature_overrides, set_feature_enabled


@pytest.fixture
def client():
    """Create test FastAPI client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def reset_features():
    """Reset feature overrides before and after each test."""
    reset_feature_overrides()
    yield
    reset_feature_overrides()


class TestFeatureGatesListEndpoint:
    """Test GET /features endpoint."""

    def test_list_all_features(self, client, reset_features):
        """Verify GET /features returns all features."""
        response = client.get("/features")
        assert response.status_code == 200

        data = response.json()
        assert "features" in data
        assert "summary" in data

        # Should have many features
        features = data["features"]
        assert len(features) > 10

        # Check structure
        for feature_id, feature_info in features.items():
            assert feature_info["feature_id"] == feature_id
            assert "name" in feature_info
            assert "enabled" in feature_info
            assert isinstance(feature_info["enabled"], bool)
            assert "wave" in feature_info
            assert "imp_id" in feature_info
            assert "risk_level" in feature_info

    def test_list_features_summary(self, client, reset_features):
        """Verify feature summary counts are accurate."""
        response = client.get("/features")
        assert response.status_code == 200

        data = response.json()
        summary = data["summary"]

        assert "total" in summary
        assert "enabled" in summary
        assert "disabled" in summary
        assert summary["enabled"] + summary["disabled"] == summary["total"]

    def test_list_features_with_enabled_feature(self, client, reset_features):
        """Verify list includes enabled features."""
        set_feature_enabled("phase6_metrics", True)

        response = client.get("/features")
        assert response.status_code == 200

        data = response.json()
        features = data["features"]
        assert features["phase6_metrics"]["enabled"] is True


class TestEnabledFeaturesEndpoint:
    """Test GET /features/enabled endpoint."""

    def test_list_enabled_features_empty(self, client, reset_features):
        """Verify GET /features/enabled when no features enabled."""
        response = client.get("/features/enabled")
        assert response.status_code == 200

        data = response.json()
        assert "features" in data
        assert "count" in data
        # Count should be 0 or low by default
        assert isinstance(data["count"], int)

    def test_list_enabled_features(self, client, reset_features):
        """Verify GET /features/enabled returns only enabled features."""
        # Enable some features
        set_feature_enabled("phase6_metrics", True)
        set_feature_enabled("consolidated_metrics", True)

        response = client.get("/features/enabled")
        assert response.status_code == 200

        data = response.json()
        features = data["features"]

        # Should include our enabled features
        assert "phase6_metrics" in features
        assert "consolidated_metrics" in features
        assert features["phase6_metrics"]["enabled"] is True
        assert features["consolidated_metrics"]["enabled"] is True

        # Count should match
        assert data["count"] >= 2


class TestDisabledFeaturesEndpoint:
    """Test GET /features/disabled endpoint."""

    def test_list_disabled_features(self, client, reset_features):
        """Verify GET /features/disabled returns only disabled features."""
        response = client.get("/features/disabled")
        assert response.status_code == 200

        data = response.json()
        features = data["features"]
        count = data["count"]

        # Should have disabled features (most are disabled by default)
        assert len(features) > 0
        assert count > 0

        # All should be disabled
        for feature_id, feature_info in features.items():
            assert feature_info["enabled"] is False


class TestGetFeatureEndpoint:
    """Test GET /features/{feature_id} endpoint."""

    def test_get_existing_feature(self, client, reset_features):
        """Verify GET /features/{feature_id} returns feature details."""
        response = client.get("/features/research_cycle_triggering")
        assert response.status_code == 200

        data = response.json()
        assert "feature" in data
        assert "dependencies" in data

        feature = data["feature"]
        assert feature["feature_id"] == "research_cycle_triggering"
        assert feature["name"] == "Research Cycle Triggering in Autopilot"
        assert feature["imp_id"] == "IMP-AUT-001"
        assert feature["wave"] == "wave3"
        assert feature["risk_level"] == "HIGH"

    def test_get_feature_with_dependencies(self, client, reset_features):
        """Verify GET /features/{feature_id} includes dependency info."""
        response = client.get("/features/monetization_guidance")
        assert response.status_code == 200

        data = response.json()
        deps = data["dependencies"]

        # Should have dependency info
        assert "status" in deps
        assert "missing_features" in deps

    def test_get_nonexistent_feature(self, client, reset_features):
        """Verify GET /features/{nonexistent} returns 404."""
        response = client.get("/features/nonexistent_feature")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data


class TestEnableFeatureEndpoint:
    """Test POST /features/{feature_id}/enable endpoint."""

    def test_enable_feature_success(self, client, reset_features):
        """Verify POST /features/{feature_id}/enable enables feature."""
        response = client.post("/features/phase6_metrics/enable")
        assert response.status_code == 200

        data = response.json()
        assert data["feature_id"] == "phase6_metrics"
        assert data["enabled"] is True
        assert "message" in data

    def test_enable_feature_persists(self, client, reset_features):
        """Verify enabled feature is returned by list endpoint."""
        # Enable feature
        response = client.post("/features/phase6_metrics/enable")
        assert response.status_code == 200

        # Verify it's enabled
        response = client.get("/features/phase6_metrics")
        assert response.status_code == 200
        assert response.json()["feature"]["enabled"] is True

    def test_enable_feature_with_unmet_deps(self, client, reset_features):
        """Verify POST /features/{feature_id}/enable fails with unmet deps."""
        # Try to enable feature with missing dependencies
        response = client.post("/features/post_build_artifacts/enable")
        # Should fail due to missing dependencies
        assert response.status_code == 400

        data = response.json()
        assert "missing_features" in str(data)

    def test_enable_nonexistent_feature(self, client, reset_features):
        """Verify POST /features/{nonexistent}/enable returns 404."""
        response = client.post("/features/nonexistent_feature/enable")
        assert response.status_code == 404


class TestDisableFeatureEndpoint:
    """Test POST /features/{feature_id}/disable endpoint."""

    def test_disable_feature_success(self, client, reset_features):
        """Verify POST /features/{feature_id}/disable disables feature."""
        # First enable it
        set_feature_enabled("phase6_metrics", True)

        # Then disable via API
        response = client.post("/features/phase6_metrics/disable")
        assert response.status_code == 200

        data = response.json()
        assert data["feature_id"] == "phase6_metrics"
        assert data["enabled"] is False
        assert "message" in data

    def test_disable_feature_emergency_kill_switch(self, client, reset_features):
        """Verify disable endpoint provides emergency kill switch."""
        # Enable feature first
        set_feature_enabled("research_cycle_triggering", True)

        # Disable as emergency kill switch
        response = client.post("/features/research_cycle_triggering/disable")
        assert response.status_code == 200

        # Verify it's disabled
        response = client.get("/features/research_cycle_triggering")
        assert response.status_code == 200
        assert response.json()["feature"]["enabled"] is False

    def test_disable_nonexistent_feature(self, client, reset_features):
        """Verify POST /features/{nonexistent}/disable returns 404."""
        response = client.post("/features/nonexistent_feature/disable")
        assert response.status_code == 404


class TestValidateGatesEndpoint:
    """Test GET /features/validate endpoint."""

    def test_validate_valid_state(self, client, reset_features):
        """Verify GET /features/validate returns valid state."""
        response = client.get("/features/validate")
        assert response.status_code == 200

        data = response.json()
        assert "valid" in data
        assert "issues" in data
        assert "total_features" in data
        assert "enabled_count" in data
        assert "disabled_count" in data

    def test_validate_detects_unmet_deps(self, client, reset_features):
        """Verify validate detects unmet dependencies."""
        # Enable feature with unmet dependencies
        set_feature_enabled("post_build_artifacts", True)

        response = client.get("/features/validate")
        assert response.status_code == 200

        data = response.json()
        # Should report as invalid
        assert data["valid"] is False
        # Should have issues
        assert len(data["issues"]) > 0


class TestFeatureGateIntegration:
    """Integration tests for feature gates."""

    def test_enable_disable_workflow(self, client, reset_features):
        """Verify complete enable/disable workflow."""
        feature_id = "phase6_metrics"

        # 1. Verify initially disabled
        response = client.get(f"/features/{feature_id}")
        assert response.json()["feature"]["enabled"] is False

        # 2. Enable via API
        response = client.post(f"/features/{feature_id}/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        # 3. Verify enabled in list
        response = client.get("/features/enabled")
        assert feature_id in response.json()["features"]

        # 4. Disable via API (kill switch)
        response = client.post(f"/features/{feature_id}/disable")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

        # 5. Verify disabled
        response = client.get(f"/features/{feature_id}")
        assert response.json()["feature"]["enabled"] is False

    def test_multiple_features_workflow(self, client, reset_features):
        """Verify managing multiple features simultaneously."""
        features = ["phase6_metrics", "consolidated_metrics", "intention_context"]

        # Enable all
        for feature_id in features:
            response = client.post(f"/features/{feature_id}/enable")
            assert response.status_code == 200

        # Verify all enabled
        response = client.get("/features/enabled")
        enabled_features = response.json()["features"]
        for feature_id in features:
            assert enabled_features[feature_id]["enabled"] is True

        # Disable half
        for feature_id in features[:2]:
            response = client.post(f"/features/{feature_id}/disable")
            assert response.status_code == 200

        # Verify mixed state
        response = client.get("/features")
        all_features = response.json()["features"]
        assert all_features[features[0]]["enabled"] is False
        assert all_features[features[1]]["enabled"] is False
        assert all_features[features[2]]["enabled"] is True
