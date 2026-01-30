"""Tests for CI/CD Workflow Generator."""

import unittest

import yaml

from autopack.research.generators.cicd_generator import CICDWorkflowGenerator
from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry,
    get_cicd_generator,
    get_registry,
)


class TestCICDWorkflowGenerator(unittest.TestCase):
    """Tests for CICDWorkflowGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = CICDWorkflowGenerator()

    def test_generate_basic_workflow(self):
        """Test generating a basic workflow."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.generator.generate(tech_stack)

        # Verify it's valid YAML
        workflow = yaml.safe_load(result)
        self.assertIsInstance(workflow, dict)

        # Verify required keys
        self.assertIn("name", workflow)
        self.assertIn("on", workflow)
        self.assertIn("jobs", workflow)

        # Verify workflow name includes stack name
        self.assertIn("Next.js + Supabase", workflow["name"])

    def test_generate_python_workflow(self):
        """Test generating a workflow for Python stack."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify Python setup is included in test job
        test_job = workflow["jobs"]["test"]
        step_names = [step.get("name", step.get("uses", "")) for step in test_job["steps"]]

        # Should have Python setup step
        has_python_setup = any(
            "Setup Python" in name or "setup-python" in name for name in step_names
        )
        self.assertTrue(has_python_setup)

    def test_generate_with_custom_commands(self):
        """Test generating workflow with custom test/build commands."""
        tech_stack = {
            "name": "Custom Stack",
            "category": "Custom",
            "test_command": "make test",
            "build_command": "make build",
        }
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify custom test command is used
        test_job = workflow["jobs"]["test"]
        test_steps = [step.get("run", "") for step in test_job["steps"]]
        self.assertTrue(any("make test" in step for step in test_steps))

        # Verify custom build command is used
        build_job = workflow["jobs"]["build"]
        build_steps = [step.get("run", "") for step in build_job["steps"]]
        self.assertTrue(any("make build" in step for step in build_steps))

    def test_generate_with_env_vars(self):
        """Test generating workflow with environment variables."""
        tech_stack = {
            "name": "Test Stack",
            "category": "Test",
            "env_vars": {
                "DATABASE_URL": "postgres://localhost/test",
                "API_KEY": "test-key",
            },
        }
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify env vars are included
        self.assertIn("env", workflow)
        self.assertEqual(workflow["env"]["DATABASE_URL"], "postgres://localhost/test")
        self.assertEqual(workflow["env"]["API_KEY"], "test-key")
        self.assertEqual(workflow["env"]["CI"], "true")

    def test_generate_with_vercel_deploy(self):
        """Test generating workflow with Vercel deployment."""
        tech_stack = {
            "name": "Next.js App",
            "category": "Frontend",
            "deploy_provider": "vercel",
        }
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify deploy job exists
        self.assertIn("deploy", workflow["jobs"])
        deploy_job = workflow["jobs"]["deploy"]

        # Verify Vercel action is used
        step_uses = [step.get("uses", "") for step in deploy_job["steps"]]
        self.assertTrue(any("vercel-action" in use for use in step_uses))

    def test_generate_with_docker_deploy(self):
        """Test generating workflow with Docker deployment."""
        tech_stack = {
            "name": "Python API",
            "category": "Backend",
            "deploy_provider": "docker",
        }
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify deploy job has Docker steps
        deploy_job = workflow["jobs"]["deploy"]
        step_uses = [step.get("uses", "") for step in deploy_job["steps"]]

        # Should have buildx and build-push-action
        self.assertTrue(any("buildx" in use for use in step_uses))
        self.assertTrue(any("build-push-action" in use for use in step_uses))

    def test_generate_without_deploy(self):
        """Test generating workflow without deployment job."""
        generator = CICDWorkflowGenerator(include_deploy=False)
        tech_stack = {
            "name": "Test Stack",
            "category": "Test",
        }
        result = generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Deploy job should not exist
        self.assertNotIn("deploy", workflow["jobs"])

    def test_generate_without_security_scan(self):
        """Test generating workflow without security scanning."""
        generator = CICDWorkflowGenerator(include_security_scan=False)
        tech_stack = {
            "name": "Test Stack",
            "category": "Test",
        }
        result = generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Security job should not exist
        self.assertNotIn("security", workflow["jobs"])

    def test_generate_with_custom_branch(self):
        """Test generating workflow with custom default branch."""
        generator = CICDWorkflowGenerator(default_branch="develop")
        tech_stack = {
            "name": "Test Stack",
            "category": "Test",
        }
        result = generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Verify branch is set correctly
        self.assertEqual(workflow["on"]["push"]["branches"], ["develop"])
        self.assertEqual(workflow["on"]["pull_request"]["branches"], ["develop"])

    def test_language_detection_node(self):
        """Test language detection for Node.js stacks."""
        test_cases = [
            ("Next.js + Vercel", "Full Stack", "node"),
            ("React App", "Frontend", "node"),
            ("Vue.js SPA", "Frontend", "node"),
            ("Express API", "Backend", "node"),
        ]
        for stack_name, category, expected_lang in test_cases:
            with self.subTest(stack_name=stack_name):
                detected = self.generator._detect_language(stack_name, category)
                self.assertEqual(detected, expected_lang)

    def test_language_detection_python(self):
        """Test language detection for Python stacks."""
        test_cases = [
            ("Django + PostgreSQL", "Python Web", "python"),
            ("FastAPI + Redis", "Backend", "python"),
            ("Flask App", "Microservice", "python"),
        ]
        for stack_name, category, expected_lang in test_cases:
            with self.subTest(stack_name=stack_name):
                detected = self.generator._detect_language(stack_name, category)
                self.assertEqual(detected, expected_lang)

    def test_language_detection_fallback(self):
        """Test language detection falls back to node for unknown."""
        detected = self.generator._detect_language("Unknown Stack", "Unknown")
        self.assertEqual(detected, "node")

    def test_valid_yaml_output(self):
        """Test that output is always valid YAML."""
        tech_stacks = [
            {"name": "Stack 1", "category": "A"},
            {"name": "Stack 2", "category": "B", "env_vars": {"KEY": "value"}},
            {"name": "Stack 3", "category": "C", "deploy_provider": "docker"},
        ]
        for tech_stack in tech_stacks:
            with self.subTest(stack=tech_stack["name"]):
                result = self.generator.generate(tech_stack)
                # Should not raise an exception
                workflow = yaml.safe_load(result)
                self.assertIsInstance(workflow, dict)

    def test_job_dependencies(self):
        """Test that job dependencies are correctly set."""
        tech_stack = {"name": "Test", "category": "Test"}
        result = self.generator.generate(tech_stack)
        workflow = yaml.safe_load(result)

        # Build should depend on test
        self.assertEqual(workflow["jobs"]["build"]["needs"], ["test"])

        # Deploy should depend on build
        self.assertEqual(workflow["jobs"]["deploy"]["needs"], ["build"])


class TestArtifactGeneratorRegistry(unittest.TestCase):
    """Tests for ArtifactGeneratorRegistry class."""

    def test_registry_has_cicd_generator(self):
        """Test that registry has CI/CD generator registered."""
        registry = ArtifactGeneratorRegistry()
        self.assertTrue(registry.has_generator("cicd"))

    def test_registry_get_cicd_generator(self):
        """Test getting CI/CD generator from registry."""
        registry = ArtifactGeneratorRegistry()
        generator = registry.get("cicd")
        self.assertIsInstance(generator, CICDWorkflowGenerator)

    def test_registry_get_with_kwargs(self):
        """Test getting generator with custom kwargs."""
        registry = ArtifactGeneratorRegistry()
        generator = registry.get("cicd", default_branch="develop")
        self.assertEqual(generator.default_branch, "develop")

    def test_registry_get_unknown_generator(self):
        """Test getting unknown generator returns None."""
        registry = ArtifactGeneratorRegistry()
        result = registry.get("unknown")
        self.assertIsNone(result)

    def test_registry_list_generators(self):
        """Test listing all registered generators."""
        registry = ArtifactGeneratorRegistry()
        generators = registry.list_generators()
        self.assertIsInstance(generators, list)
        self.assertTrue(len(generators) > 0)

        # Should have cicd generator
        names = [g["name"] for g in generators]
        self.assertIn("cicd", names)

    def test_registry_register_custom_generator(self):
        """Test registering a custom generator."""
        registry = ArtifactGeneratorRegistry()

        class CustomGenerator:
            pass

        registry.register("custom", CustomGenerator, "Custom generator")
        self.assertTrue(registry.has_generator("custom"))

        generator = registry.get("custom")
        self.assertIsInstance(generator, CustomGenerator)


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for convenience functions."""

    def test_get_registry(self):
        """Test get_registry returns singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        self.assertIs(registry1, registry2)

    def test_get_cicd_generator(self):
        """Test get_cicd_generator convenience function."""
        generator = get_cicd_generator()
        self.assertIsInstance(generator, CICDWorkflowGenerator)

    def test_get_cicd_generator_with_kwargs(self):
        """Test get_cicd_generator with custom kwargs."""
        generator = get_cicd_generator(include_deploy=False)
        self.assertFalse(generator.include_deploy)


if __name__ == "__main__":
    unittest.main()
