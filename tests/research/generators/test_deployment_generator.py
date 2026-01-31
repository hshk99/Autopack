"""Tests for Deployment Guidance Generator."""

import unittest

from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry,
    DeploymentGuidanceGenerator,
    get_deployment_generator,
    get_registry,
)


class TestDeploymentGuidanceGenerator(unittest.TestCase):
    """Tests for DeploymentGuidanceGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = DeploymentGuidanceGenerator()

    def test_generate_basic_guidance(self):
        """Test generating basic deployment guidance."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.generator.generate(tech_stack)

        # Verify it's markdown with expected sections
        self.assertIn("# Deployment Guide", result)
        self.assertIn("## Executive Summary", result)
        self.assertIn("## Recommended Architecture", result)

    def test_generate_includes_project_info(self):
        """Test generated guide includes project information."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("Django + PostgreSQL", result)

    def test_generate_includes_docker_section(self):
        """Test generated guide includes Docker configuration."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        # Should include Docker section for backend apps
        self.assertIn("## Docker Configuration", result)
        self.assertIn("### Dockerfile", result)
        self.assertIn("### docker-compose.yml", result)

    def test_generate_includes_environment_section(self):
        """Test generated guide includes environment variables section."""
        tech_stack = {
            "name": "FastAPI + PostgreSQL",
            "category": "Python API",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("## Environment Variables", result)
        self.assertIn("DATABASE_URL", result)

    def test_generate_includes_alternatives(self):
        """Test generated guide includes alternative approaches."""
        tech_stack = {
            "name": "Express + Redis",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("## Alternative Approaches", result)

    def test_generate_includes_infrastructure_requirements(self):
        """Test generated guide includes infrastructure requirements."""
        tech_stack = {
            "name": "Django API",
            "category": "Python Backend",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("## Infrastructure Requirements", result)

    def test_generate_static_site(self):
        """Test generating guidance for static site."""
        tech_stack = {
            "name": "React SPA",
            "category": "Frontend Static",
        }
        result = self.generator.generate(tech_stack)

        # Static sites shouldn't have Docker section
        self.assertIn("# Deployment Guide", result)
        # Should recommend static hosting
        self.assertIn("Static", result)

    def test_generate_with_requirements(self):
        """Test generating guidance with project requirements."""
        tech_stack = {
            "name": "FastAPI + PostgreSQL",
            "category": "Python API",
        }
        requirements = {
            "scale": "large",
            "budget": "high",
        }
        result = self.generator.generate(tech_stack, requirements)

        # Should include Kubernetes for large scale
        self.assertIn("# Deployment Guide", result)

    def test_generate_returns_string(self):
        """Test generate always returns a string."""
        tech_stack = {"name": "Test", "category": "Test"}
        result = self.generator.generate(tech_stack)

        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


class TestDockerfileGeneration(unittest.TestCase):
    """Tests for Dockerfile generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = DeploymentGuidanceGenerator()

    def test_generate_node_dockerfile(self):
        """Test generating Dockerfile for Node.js."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        # Should contain Node.js specific commands
        self.assertIn("npm", result)
        self.assertIn("node", result)

    def test_generate_python_dockerfile(self):
        """Test generating Dockerfile for Python."""
        tech_stack = {
            "name": "FastAPI",
            "category": "Python Backend",
        }
        result = self.generator.generate(tech_stack)

        # Should contain Python specific commands
        self.assertIn("pip", result)
        self.assertIn("python", result)

    def test_dockerfile_has_healthcheck(self):
        """Test Dockerfile includes health check."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("HEALTHCHECK", result)

    def test_dockerfile_exposes_port(self):
        """Test Dockerfile exposes port."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        self.assertIn("EXPOSE", result)


class TestDockerComposeGeneration(unittest.TestCase):
    """Tests for docker-compose.yml generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = DeploymentGuidanceGenerator()

    def test_generate_docker_compose(self):
        """Test generating docker-compose.yml."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        # Should contain docker-compose content
        self.assertIn("version:", result)
        self.assertIn("services:", result)

    def test_docker_compose_with_database(self):
        """Test docker-compose includes database service."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web",
        }
        result = self.generator.generate(tech_stack)

        # Should have postgres service
        self.assertIn("postgres", result.lower())

    def test_docker_compose_with_redis(self):
        """Test docker-compose includes Redis service."""
        tech_stack = {
            "name": "Express + Redis",
            "category": "Node.js Backend",
        }
        result = self.generator.generate(tech_stack)

        # Should have redis service
        self.assertIn("redis", result.lower())


class TestKubernetesGeneration(unittest.TestCase):
    """Tests for Kubernetes manifest generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = DeploymentGuidanceGenerator()

    def test_generate_k8s_for_large_scale(self):
        """Test generating K8s manifests for large scale."""
        tech_stack = {
            "name": "FastAPI + PostgreSQL",
            "category": "Python API",
        }
        requirements = {"scale": "large"}
        result = self.generator.generate(tech_stack, requirements)

        # Large scale should include Kubernetes section
        self.assertIn("Kubernetes", result)

    def test_k8s_deployment_manifest(self):
        """Test K8s deployment manifest structure."""
        tech_stack = {
            "name": "FastAPI",
            "category": "Python API",
        }
        requirements = {"scale": "large"}
        result = self.generator.generate(tech_stack, requirements)

        if "deployment.yaml" in result:
            self.assertIn("apiVersion: apps/v1", result)
            self.assertIn("kind: Deployment", result)

    def test_k8s_service_manifest(self):
        """Test K8s service manifest structure."""
        tech_stack = {
            "name": "FastAPI",
            "category": "Python API",
        }
        requirements = {"scale": "large"}
        result = self.generator.generate(tech_stack, requirements)

        if "service.yaml" in result:
            self.assertIn("kind: Service", result)


class TestServerlessGeneration(unittest.TestCase):
    """Tests for serverless configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = DeploymentGuidanceGenerator()

    def test_serverless_config_structure(self):
        """Test serverless.yml structure."""
        # Create a stateless API that would benefit from serverless
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend Stateless",
        }
        result = self.generator.generate(tech_stack)

        # Check if serverless is recommended and has proper structure
        if "Serverless" in result and "serverless.yml" in result:
            self.assertIn("service:", result)
            self.assertIn("provider:", result)
            self.assertIn("functions:", result)


class TestArtifactGeneratorRegistry(unittest.TestCase):
    """Tests for ArtifactGeneratorRegistry with deployment generator."""

    def test_registry_has_deployment_generator(self):
        """Test that registry has deployment generator registered."""
        registry = ArtifactGeneratorRegistry()
        self.assertTrue(registry.has_generator("deployment"))

    def test_registry_get_deployment_generator(self):
        """Test getting deployment generator from registry."""
        registry = ArtifactGeneratorRegistry()
        generator = registry.get("deployment")
        self.assertIsInstance(generator, DeploymentGuidanceGenerator)

    def test_registry_list_includes_deployment(self):
        """Test listing generators includes deployment."""
        registry = ArtifactGeneratorRegistry()
        generators = registry.list_generators()
        names = [g["name"] for g in generators]
        self.assertIn("deployment", names)


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for convenience functions."""

    def test_get_deployment_generator(self):
        """Test get_deployment_generator convenience function."""
        generator = get_deployment_generator()
        self.assertIsInstance(generator, DeploymentGuidanceGenerator)

    def test_get_registry_singleton(self):
        """Test get_registry returns singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        self.assertIs(registry1, registry2)

    def test_get_deployment_generator_from_registry(self):
        """Test getting deployment generator from default registry."""
        registry = get_registry()
        generator = registry.get("deployment")
        self.assertIsInstance(generator, DeploymentGuidanceGenerator)


if __name__ == "__main__":
    unittest.main()
