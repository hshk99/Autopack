"""Tests for gap plugin system."""

import tempfile
from pathlib import Path

from autopack.gaps.gap_plugin import (GapDetectorPlugin, GapResult,
                                      PluginRegistry)
from autopack.gaps.plugins.api_routes_plugin import ApiRoutesWithoutTestsPlugin


class TestGapResult:
    """Tests for GapResult dataclass."""

    def test_gap_result_creation(self):
        """Test creating a GapResult."""
        result = GapResult(
            gap_type="test_gap",
            description="Test gap description",
            file_path="src/test.py",
            severity="high",
            auto_fixable=False,
            suggested_fix="Fix this test",
        )

        assert result.gap_type == "test_gap"
        assert result.description == "Test gap description"
        assert result.file_path == "src/test.py"
        assert result.severity == "high"
        assert result.auto_fixable is False
        assert result.suggested_fix == "Fix this test"

    def test_gap_result_defaults(self):
        """Test GapResult with default values."""
        result = GapResult(
            gap_type="test_gap",
            description="Test gap",
        )

        assert result.severity == "medium"
        assert result.auto_fixable is False
        assert result.file_path is None
        assert result.suggested_fix is None


class TestGapDetectorPlugin:
    """Tests for GapDetectorPlugin base class."""

    class MockPlugin(GapDetectorPlugin):
        """Mock plugin for testing."""

        @property
        def name(self) -> str:
            return "mock_plugin"

        @property
        def gap_type(self) -> str:
            return "mock_gap"

        def detect(self, context: dict) -> list[GapResult]:
            return [
                GapResult(
                    gap_type=self.gap_type,
                    description="Mock gap detected",
                )
            ]

    def test_plugin_properties(self):
        """Test plugin name and gap_type properties."""
        plugin = self.MockPlugin()

        assert plugin.name == "mock_plugin"
        assert plugin.gap_type == "mock_gap"

    def test_plugin_detect(self):
        """Test plugin detect method."""
        plugin = self.MockPlugin()
        results = plugin.detect(context={"project_root": "."})

        assert len(results) == 1
        assert results[0].gap_type == "mock_gap"
        assert results[0].description == "Mock gap detected"


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_registry_creation(self):
        """Test creating an empty registry."""
        registry = PluginRegistry()
        assert registry.get_all() == []

    def test_register_plugin(self):
        """Test registering a plugin."""
        registry = PluginRegistry()
        plugin = TestGapDetectorPlugin.MockPlugin()

        registry.register(plugin)
        plugins = registry.get_all()

        assert len(plugins) == 1
        assert plugins[0].name == "mock_plugin"

    def test_register_multiple_plugins(self):
        """Test registering multiple plugins."""
        registry = PluginRegistry()

        plugin1 = TestGapDetectorPlugin.MockPlugin()
        plugin2 = ApiRoutesWithoutTestsPlugin()

        registry.register(plugin1)
        registry.register(plugin2)

        plugins = registry.get_all()
        assert len(plugins) == 2
        assert any(p.name == "mock_plugin" for p in plugins)
        assert any(p.name == "api_routes_without_tests" for p in plugins)

    def test_load_from_config_missing_file(self):
        """Test loading from non-existent config file."""
        registry = PluginRegistry()
        registry.load_from_config("/non/existent/path.yaml")
        # Should not raise exception
        assert registry.get_all() == []

    def test_load_from_config_empty_file(self):
        """Test loading from empty config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "gap_plugins.yaml"
            config_path.write_text("")

            registry = PluginRegistry()
            registry.load_from_config(config_path)

            # Empty config should result in no plugins
            assert registry.get_all() == []

    def test_load_from_config_valid_plugins(self):
        """Test loading plugins from valid config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "gap_plugins.yaml"
            config_content = """
plugins:
  - name: api_routes_without_tests
    module: autopack.gaps.plugins.api_routes_plugin
    class: ApiRoutesWithoutTestsPlugin
    enabled: true
"""
            config_path.write_text(config_content)

            registry = PluginRegistry()
            registry.load_from_config(config_path)

            plugins = registry.get_all()
            assert len(plugins) == 1
            assert plugins[0].name == "api_routes_without_tests"

    def test_load_from_config_disabled_plugin(self):
        """Test that disabled plugins are not loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "gap_plugins.yaml"
            config_content = """
plugins:
  - name: api_routes_without_tests
    module: autopack.gaps.plugins.api_routes_plugin
    class: ApiRoutesWithoutTestsPlugin
    enabled: false
"""
            config_path.write_text(config_content)

            registry = PluginRegistry()
            registry.load_from_config(config_path)

            # Disabled plugins should not be loaded
            assert registry.get_all() == []


class TestApiRoutesWithoutTestsPlugin:
    """Tests for ApiRoutesWithoutTestsPlugin."""

    def test_plugin_properties(self):
        """Test plugin name and gap_type."""
        plugin = ApiRoutesWithoutTestsPlugin()

        assert plugin.name == "api_routes_without_tests"
        assert plugin.gap_type == "untested_api_route"

    def test_detect_no_routes(self):
        """Test detection when no route files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = ApiRoutesWithoutTestsPlugin()
            results = plugin.detect(context={"project_root": tmpdir})

            assert results == []

    def test_detect_routes_with_tests(self):
        """Test detection when routes have corresponding tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create route file
            route_dir = tmpdir_path / "src" / "api"
            route_dir.mkdir(parents=True)
            (route_dir / "routes.py").write_text("# routes")

            # Create test file
            test_dir = tmpdir_path / "tests"
            test_dir.mkdir(parents=True)
            (test_dir / "test_api.py").write_text("# tests")

            plugin = ApiRoutesWithoutTestsPlugin()
            results = plugin.detect(context={"project_root": str(tmpdir_path)})

            # Since test_api.py exists for api/routes.py, no gap should be detected
            assert len(results) == 0

    def test_detect_routes_without_tests(self):
        """Test detection when routes lack corresponding tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create route file
            route_dir = tmpdir_path / "src" / "api"
            route_dir.mkdir(parents=True)
            (route_dir / "routes.py").write_text("# routes")

            # No test file created

            plugin = ApiRoutesWithoutTestsPlugin()
            results = plugin.detect(context={"project_root": str(tmpdir_path)})

            # Should detect untested route
            assert len(results) == 1
            assert results[0].gap_type == "untested_api_route"
            assert "routes.py" in results[0].description
            assert results[0].severity == "high"

    def test_detect_multiple_routes(self):
        """Test detection with multiple route files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create multiple route files
            for module in ["api", "admin", "user"]:
                route_dir = tmpdir_path / "src" / module
                route_dir.mkdir(parents=True)
                (route_dir / "routes.py").write_text("# routes")

            # Create tests for only two of them
            test_dir = tmpdir_path / "tests"
            test_dir.mkdir(parents=True)
            (test_dir / "test_api.py").write_text("# tests")
            (test_dir / "test_admin.py").write_text("# tests")

            plugin = ApiRoutesWithoutTestsPlugin()
            results = plugin.detect(context={"project_root": str(tmpdir_path)})

            # Should detect only the untested user route
            assert len(results) == 1
            assert "user" in results[0].description
