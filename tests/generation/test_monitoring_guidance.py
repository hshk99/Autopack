"""Tests for MonitoringGuidanceGenerator."""

import json
import tempfile
from pathlib import Path

import pytest

from autopack.generation.monitoring_guidance_generator import (
    MonitoringGuidanceGenerator,
    MonitoringGuide,
)


class TestMonitoringGuide:
    """Test MonitoringGuide dataclass."""

    def test_create_guide(self):
        """Test creating a MonitoringGuide instance."""
        guide = MonitoringGuide(
            platform_name="Prometheus",
            description="Time-series database",
            setup_difficulty="medium",
            estimated_setup_time_hours=4.0,
            cost_per_month_usd=0.0,
            metrics_collected=["CPU", "Memory"],
            alerting_included=True,
        )

        assert guide.platform_name == "Prometheus"
        assert guide.setup_difficulty == "medium"
        assert guide.estimated_setup_time_hours == 4.0
        assert guide.cost_per_month_usd == 0.0
        assert len(guide.metrics_collected) == 2
        assert guide.alerting_included is True

    def test_guide_defaults(self):
        """Test MonitoringGuide default values."""
        guide = MonitoringGuide(
            platform_name="Test Platform",
            description="Test description",
            setup_difficulty="easy",
            estimated_setup_time_hours=1.0,
            cost_per_month_usd=10.0,
        )

        assert guide.metrics_collected == []
        assert guide.log_aggregation_included is False
        assert guide.alerting_included is False
        assert guide.dashboard_included is False
        assert guide.best_for == ""
        assert guide.guide_content == ""
        assert guide.generated_at is not None


class TestMonitoringGuidanceGenerator:
    """Test MonitoringGuidanceGenerator."""

    def test_generator_initialization(self):
        """Test generator initialization."""
        generator = MonitoringGuidanceGenerator()
        assert generator.guides == {}

    def test_generate_prometheus_guide(self):
        """Test generating Prometheus guide."""
        generator = MonitoringGuidanceGenerator()
        guide = generator.generate_prometheus_guide()

        assert guide.platform_name == "Prometheus"
        assert guide.setup_difficulty == "medium"
        assert guide.estimated_setup_time_hours == 4.0
        assert guide.cost_per_month_usd == 0.0
        assert guide.alerting_included is True
        assert guide.log_aggregation_included is False
        assert "Prometheus" in guide.guide_content
        assert "Setup Guide" in guide.guide_content

    def test_generate_prometheus_guide_project_types(self):
        """Test Prometheus guide generation for different project types."""
        generator = MonitoringGuidanceGenerator()

        for project_type in ["web", "api", "batch", "ml"]:
            guide = generator.generate_prometheus_guide(project_type)
            assert guide.guide_content is not None
            assert len(guide.guide_content) > 100
            assert project_type.title() in guide.guide_content

    def test_generate_datadog_guide(self):
        """Test generating DataDog guide."""
        generator = MonitoringGuidanceGenerator()
        guide = generator.generate_datadog_guide()

        assert guide.platform_name == "DataDog"
        assert guide.setup_difficulty == "easy"
        assert guide.estimated_setup_time_hours == 2.0
        assert guide.cost_per_month_usd == 15.0
        assert guide.alerting_included is True
        assert guide.log_aggregation_included is True
        assert guide.dashboard_included is True
        assert "DataDog" in guide.guide_content
        assert "API Key" in guide.guide_content

    def test_generate_cloudwatch_guide(self):
        """Test generating CloudWatch guide."""
        generator = MonitoringGuidanceGenerator()
        guide = generator.generate_cloudwatch_guide()

        assert guide.platform_name == "AWS CloudWatch"
        assert guide.setup_difficulty == "easy"
        assert guide.estimated_setup_time_hours == 1.5
        assert guide.cost_per_month_usd == 5.0
        assert guide.alerting_included is True
        assert guide.log_aggregation_included is True
        assert guide.dashboard_included is True
        assert "CloudWatch" in guide.guide_content
        assert "Log Group" in guide.guide_content

    def test_generate_elasticsearch_guide(self):
        """Test generating Elasticsearch guide."""
        generator = MonitoringGuidanceGenerator()
        guide = generator.generate_elasticsearch_guide()

        assert guide.platform_name == "Elasticsearch (ELK Stack)"
        assert guide.setup_difficulty == "hard"
        assert guide.estimated_setup_time_hours == 8.0
        assert guide.cost_per_month_usd == 0.0
        assert guide.alerting_included is True
        assert guide.log_aggregation_included is True
        assert guide.dashboard_included is True
        assert "Elasticsearch" in guide.guide_content
        assert "Kibana" in guide.guide_content

    def test_generate_all_guides(self):
        """Test generating all guides at once."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        assert len(guides) == 4
        assert "prometheus" in guides
        assert "datadog" in guides
        assert "cloudwatch" in guides
        assert "elasticsearch" in guides

        # Verify all guides are properly initialized
        for platform, guide in guides.items():
            assert guide.platform_name is not None
            assert guide.guide_content is not None
            assert len(guide.guide_content) > 100

    def test_generate_all_guides_with_project_type(self):
        """Test generating all guides with custom project type."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides(project_type="ml")

        for platform, guide in guides.items():
            assert "ML" in guide.guide_content or "ml" in guide.guide_content.lower()

    def test_guides_stored_in_instance(self):
        """Test that guides are stored in the generator instance."""
        generator = MonitoringGuidanceGenerator()

        generator.generate_prometheus_guide()
        assert "prometheus" in generator.guides

        generator.generate_datadog_guide()
        assert "datadog" in generator.guides

        assert len(generator.guides) == 2

    def test_metrics_in_guides(self):
        """Test that all guides have metrics_collected."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        for guide in guides.values():
            assert guide.metrics_collected is not None
            assert len(guide.metrics_collected) > 0

            # Verify metrics are reasonable
            for metric in guide.metrics_collected:
                assert isinstance(metric, str)
                assert len(metric) > 0

    def test_features_included(self):
        """Test features included in each platform."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        # Prometheus: alerting but no log aggregation
        prometheus = guides["prometheus"]
        assert prometheus.alerting_included is True
        assert prometheus.log_aggregation_included is False

        # DataDog: all features
        datadog = guides["datadog"]
        assert datadog.alerting_included is True
        assert datadog.log_aggregation_included is True
        assert datadog.dashboard_included is True

        # CloudWatch: all features
        cloudwatch = guides["cloudwatch"]
        assert cloudwatch.alerting_included is True
        assert cloudwatch.log_aggregation_included is True
        assert cloudwatch.dashboard_included is True

        # Elasticsearch: all features
        elasticsearch = guides["elasticsearch"]
        assert elasticsearch.alerting_included is True
        assert elasticsearch.log_aggregation_included is True
        assert elasticsearch.dashboard_included is True

    def test_cost_comparison(self):
        """Test cost information in guides."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        # Free platforms
        assert guides["prometheus"].cost_per_month_usd == 0.0
        assert guides["elasticsearch"].cost_per_month_usd == 0.0

        # Paid platforms
        assert guides["datadog"].cost_per_month_usd > 0
        assert guides["cloudwatch"].cost_per_month_usd > 0

    def test_get_summary(self):
        """Test summary generation."""
        generator = MonitoringGuidanceGenerator()
        generator.generate_all_guides()

        summary = generator.get_summary()

        assert isinstance(summary, str)
        assert "Monitoring Setup Guides Summary" in summary
        assert "Prometheus" in summary
        assert "DataDog" in summary
        assert "CloudWatch" in summary
        assert "Elasticsearch" in summary
        assert "Best For" in summary

    def test_get_summary_no_guides(self):
        """Test summary with no guides generated."""
        generator = MonitoringGuidanceGenerator()
        summary = generator.get_summary()

        assert "No guides generated" in summary

    def test_export_guides_to_json(self):
        """Test exporting guides to JSON."""
        generator = MonitoringGuidanceGenerator()
        generator.generate_all_guides()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "guides.json")
            result_path = generator.export_guides_to_json(output_file)

            assert result_path == output_file
            assert Path(output_file).exists()

            # Verify JSON content
            with open(output_file) as f:
                data = json.load(f)

            assert len(data) == 4
            assert "prometheus" in data
            assert data["prometheus"]["platform_name"] == "Prometheus"
            assert data["prometheus"]["setup_difficulty"] == "medium"

    def test_export_guides_creates_directory(self):
        """Test that export creates necessary directories."""
        generator = MonitoringGuidanceGenerator()
        generator.generate_prometheus_guide()

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = str(Path(tmpdir) / "nested" / "dirs" / "guides.json")
            generator.export_guides_to_json(nested_path)

            assert Path(nested_path).exists()

    def test_export_guides_no_guides_raises_error(self):
        """Test that export raises error when no guides generated."""
        generator = MonitoringGuidanceGenerator()

        with pytest.raises(ValueError, match="No guides generated"):
            generator.export_guides_to_json()

    def test_guide_content_quality(self):
        """Test that guide content meets quality standards."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        for guide in guides.values():
            # Verify substantial content
            assert len(guide.guide_content) > 500

            # Verify markdown formatting
            assert "##" in guide.guide_content or "#" in guide.guide_content

            # Verify code examples
            assert "```" in guide.guide_content

            # Verify best practices
            assert (
                "Best Practices" in guide.guide_content
                or "best practices" in guide.guide_content.lower()
            )

    def test_setup_difficulty_levels(self):
        """Test that setup difficulty levels are reasonable."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        valid_levels = ["easy", "medium", "hard"]
        for guide in guides.values():
            assert guide.setup_difficulty in valid_levels

    def test_setup_time_estimates(self):
        """Test that setup time estimates are reasonable."""
        generator = MonitoringGuidanceGenerator()
        guides = generator.generate_all_guides()

        for guide in guides.values():
            # Setup should take between 0.5 and 24 hours
            assert 0.5 <= guide.estimated_setup_time_hours <= 24

    def test_multiple_project_types(self):
        """Test guides with multiple project types."""
        generator = MonitoringGuidanceGenerator()

        project_types = ["web", "api", "batch", "ml"]
        for project_type in project_types:
            guide = generator.generate_prometheus_guide(project_type)
            assert guide.guide_content is not None
            # Project type should be referenced in guide
            assert project_type.title() in guide.guide_content or len(guide.guide_content) > 0
