"""Tests for CI/CD Workflow Generator.

Tests for all CI/CD generators:
- CICDWorkflowGenerator (GitHub Actions)
- GitLabCIGenerator
- JenkinsPipelineGenerator
- CICDAnalyzer
"""

import unittest

import yaml

from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry,
    MonetizationStrategyGenerator,
    get_cicd_analyzer,
    get_cicd_generator,
    get_gitlab_ci_generator,
    get_jenkins_generator,
    get_monetization_generator,
    get_registry,
)
from autopack.research.generators.cicd_generator import (
    CICDAnalyzer,
    CICDPlatform,
    CICDWorkflowGenerator,
    DeploymentGuidance,
    DeploymentTarget,
    GitLabCIGenerator,
    JenkinsPipelineGenerator,
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


class TestMonetizationStrategyGenerator(unittest.TestCase):
    """Tests for MonetizationStrategyGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = MonetizationStrategyGenerator()

    def test_generate_with_overview(self):
        """Test generating strategy with overview."""
        research_findings = {
            "overview": "Test monetization strategy overview",
        }
        result = self.generator.generate(research_findings)

        self.assertIn("# Monetization Strategy", result)
        self.assertIn("## Overview", result)
        self.assertIn("Test monetization strategy overview", result)

    def test_generate_with_pricing_models(self):
        """Test generating strategy with pricing models."""
        research_findings = {
            "models": [
                {
                    "model": "subscription",
                    "prevalence": "common",
                    "pros": ["Predictable revenue"],
                    "cons": ["Requires volume"],
                    "examples": [
                        {
                            "company": "Company A",
                            "url": "https://example.com/pricing",
                            "tiers": [
                                {
                                    "name": "Free",
                                    "price": "$0",
                                    "limits": "100 items/month",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        result = self.generator.generate(research_findings)

        self.assertIn("## Pricing Models", result)
        self.assertIn("Subscription", result)
        self.assertIn("Company A", result)
        self.assertIn("$0", result)

    def test_generate_with_benchmarks(self):
        """Test generating strategy with pricing benchmarks."""
        research_findings = {
            "pricing_benchmarks": {
                "entry_level": {
                    "range": "$10-30/month",
                    "median": "$19/month",
                    "source": "https://example.com",
                }
            }
        }
        result = self.generator.generate(research_findings)

        self.assertIn("## Pricing Benchmarks", result)
        self.assertIn("Entry Level", result)
        self.assertIn("$10-30/month", result)

    def test_generate_with_conversion_metrics(self):
        """Test generating strategy with conversion benchmarks."""
        research_findings = {
            "conversion_benchmarks": {
                "free_to_paid": {
                    "industry_average": "2-5%",
                    "top_performers": "7-10%",
                }
            }
        }
        result = self.generator.generate(research_findings)

        self.assertIn("## Conversion Metrics", result)
        self.assertIn("Free To Paid", result)
        self.assertIn("2-5%", result)

    def test_generate_with_revenue_potential(self):
        """Test generating strategy with revenue potential."""
        research_findings = {
            "revenue_potential": {
                "conservative": {
                    "monthly": "$10,000",
                    "assumptions": ["100 users", "2% conversion"],
                }
            }
        }
        result = self.generator.generate(research_findings)

        self.assertIn("## Revenue Potential", result)
        self.assertIn("Conservative Scenario", result)
        self.assertIn("$10,000", result)

    def test_generate_with_recommended_model(self):
        """Test generating strategy with recommended model."""
        research_findings = {
            "recommended_model": {
                "model": "freemium with pro tier",
                "rationale": "Market expects free tier",
                "suggested_pricing": {"free": "$0", "pro": "$29/month"},
                "differentiation": "Unique value proposition",
            }
        }
        result = self.generator.generate(research_findings)

        self.assertIn("## Recommended Model", result)
        self.assertIn("freemium with pro tier", result)
        self.assertIn("Market expects free tier", result)
        self.assertIn("$29/month", result)

    def test_generate_complete_strategy(self):
        """Test generating complete monetization strategy."""
        research_findings = {
            "overview": "Complete strategy",
            "models": [
                {
                    "model": "subscription",
                    "prevalence": "common",
                    "pros": ["Revenue"],
                    "cons": ["Churn"],
                }
            ],
            "pricing_benchmarks": {
                "entry_level": {
                    "range": "$10-30/month",
                    "median": "$19/month",
                }
            },
            "conversion_benchmarks": {"free_to_paid": {"industry_average": "2-5%"}},
            "revenue_potential": {"moderate": {"monthly": "$50,000", "assumptions": ["500 users"]}},
            "recommended_model": {
                "model": "freemium",
                "rationale": "Best fit",
            },
        }
        result = self.generator.generate(research_findings)

        # Verify all sections are present
        self.assertIn("# Monetization Strategy", result)
        self.assertIn("## Overview", result)
        self.assertIn("## Pricing Models", result)
        self.assertIn("## Pricing Benchmarks", result)
        self.assertIn("## Conversion Metrics", result)
        self.assertIn("## Revenue Potential", result)
        self.assertIn("## Recommended Model", result)

    def test_generate_empty_findings(self):
        """Test generating with empty findings."""
        research_findings = {}
        result = self.generator.generate(research_findings)

        # Should still have the header
        self.assertIn("# Monetization Strategy", result)

    def test_generate_returns_markdown_string(self):
        """Test that generate always returns a markdown string."""
        research_findings = {"overview": "Test"}
        result = self.generator.generate(research_findings)

        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("# Monetization Strategy"))


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

    def test_registry_has_monetization_generator(self):
        """Test that registry has monetization generator registered."""
        registry = ArtifactGeneratorRegistry()
        self.assertTrue(registry.has_generator("monetization"))

    def test_get_monetization_generator(self):
        """Test get_monetization_generator convenience function."""
        generator = get_monetization_generator()
        self.assertIsInstance(generator, MonetizationStrategyGenerator)

    def test_get_monetization_generator_from_registry(self):
        """Test getting monetization generator from registry."""
        registry = ArtifactGeneratorRegistry()
        generator = registry.get("monetization")
        self.assertIsInstance(generator, MonetizationStrategyGenerator)


class TestGitLabCIGenerator(unittest.TestCase):
    """Tests for GitLabCIGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = GitLabCIGenerator()

    def test_generate_basic_pipeline(self):
        """Test generating a basic GitLab CI pipeline."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.generator.generate(tech_stack)

        # Verify it's valid YAML
        pipeline = yaml.safe_load(result)
        self.assertIsInstance(pipeline, dict)

        # Verify required keys
        self.assertIn("stages", pipeline)
        self.assertIn("test", pipeline)
        self.assertIn("build", pipeline)

        # Verify stages order
        self.assertIn("test", pipeline["stages"])
        self.assertIn("build", pipeline["stages"])

    def test_generate_python_pipeline(self):
        """Test generating a pipeline for Python stack."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.generator.generate(tech_stack)
        pipeline = yaml.safe_load(result)

        # Verify Python image is used
        self.assertIn("python", pipeline["default"]["image"])

        # Verify pytest is in test scripts
        test_scripts = pipeline["test"]["script"]
        self.assertTrue(any("pytest" in script for script in test_scripts))

    def test_generate_with_security_scan(self):
        """Test generating pipeline with security scanning."""
        tech_stack = {
            "name": "Node.js App",
            "category": "Backend",
        }
        result = self.generator.generate(tech_stack)
        pipeline = yaml.safe_load(result)

        # Verify security stage exists
        self.assertIn("security", pipeline["stages"])
        self.assertIn("security_scan", pipeline)

    def test_generate_without_security_scan(self):
        """Test generating pipeline without security scanning."""
        generator = GitLabCIGenerator(include_security_scan=False)
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = generator.generate(tech_stack)
        pipeline = yaml.safe_load(result)

        # Security stage should not exist
        self.assertNotIn("security", pipeline["stages"])
        self.assertNotIn("security_scan", pipeline)

    def test_generate_with_docker_deploy(self):
        """Test generating pipeline with Docker deployment."""
        tech_stack = {
            "name": "Python API",
            "category": "Backend",
            "deploy_provider": "docker",
        }
        result = self.generator.generate(tech_stack)
        pipeline = yaml.safe_load(result)

        # Verify deploy job exists
        self.assertIn("deploy", pipeline)
        deploy_job = pipeline["deploy"]

        # Verify Docker image and services
        self.assertEqual(deploy_job["image"], "docker:24.0")
        self.assertIn("docker:24.0-dind", deploy_job["services"])

    def test_generate_with_deployment_guidance(self):
        """Test generating pipeline with deployment guidance."""
        tech_stack = {"name": "Python API", "category": "Backend"}
        guidance = DeploymentGuidance(
            target=DeploymentTarget.KUBERNETES,
            containerized=True,
        )
        result = self.generator.generate(tech_stack, guidance)
        pipeline = yaml.safe_load(result)

        # Verify kubernetes deploy commands
        deploy_scripts = pipeline["deploy"]["script"]
        self.assertTrue(any("kubectl" in script for script in deploy_scripts))

    def test_cache_configuration(self):
        """Test that cache is properly configured."""
        tech_stack = {"name": "Node.js App", "category": "Frontend"}
        result = self.generator.generate(tech_stack)
        pipeline = yaml.safe_load(result)

        # Verify cache exists
        self.assertIn("cache", pipeline)
        self.assertIn("paths", pipeline["cache"])
        self.assertIn("node_modules/", pipeline["cache"]["paths"])

    def test_valid_yaml_output(self):
        """Test that output is always valid YAML."""
        tech_stacks = [
            {"name": "Stack 1", "category": "A"},
            {"name": "Django App", "category": "Python"},
            {"name": "Go Service", "category": "Backend", "deploy_provider": "kubernetes"},
        ]
        for tech_stack in tech_stacks:
            with self.subTest(stack=tech_stack["name"]):
                result = self.generator.generate(tech_stack)
                pipeline = yaml.safe_load(result)
                self.assertIsInstance(pipeline, dict)


class TestJenkinsPipelineGenerator(unittest.TestCase):
    """Tests for JenkinsPipelineGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = JenkinsPipelineGenerator()

    def test_generate_basic_jenkinsfile(self):
        """Test generating a basic Jenkinsfile."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.generator.generate(tech_stack)

        # Verify it's a valid Jenkinsfile structure
        self.assertTrue(result.startswith("pipeline {"))
        self.assertTrue(result.strip().endswith("}"))
        self.assertIn("stages {", result)
        self.assertIn("stage('Test')", result)
        self.assertIn("stage('Build')", result)

    def test_generate_python_jenkinsfile(self):
        """Test generating a Jenkinsfile for Python stack."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.generator.generate(tech_stack)

        # Verify Python commands are used
        self.assertIn("pytest", result)
        self.assertIn("pip", result)

    def test_generate_with_security_scan(self):
        """Test generating Jenkinsfile with security scanning."""
        tech_stack = {"name": "Node.js App", "category": "Backend"}
        result = self.generator.generate(tech_stack)

        # Verify security stage exists
        self.assertIn("stage('Security Scan')", result)
        self.assertIn("npm audit", result)

    def test_generate_without_security_scan(self):
        """Test generating Jenkinsfile without security scanning."""
        generator = JenkinsPipelineGenerator(include_security_scan=False)
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = generator.generate(tech_stack)

        # Security stage should not exist
        self.assertNotIn("stage('Security Scan')", result)

    def test_generate_with_deploy_stage(self):
        """Test generating Jenkinsfile with deployment stage."""
        tech_stack = {
            "name": "Python API",
            "category": "Backend",
            "deploy_provider": "docker",
        }
        result = self.generator.generate(tech_stack)

        # Verify deploy stage exists
        self.assertIn("stage('Deploy')", result)
        self.assertIn("docker build", result)
        self.assertIn("docker push", result)

    def test_generate_with_custom_branch(self):
        """Test generating Jenkinsfile with custom default branch."""
        generator = JenkinsPipelineGenerator(default_branch="develop")
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = generator.generate(tech_stack)

        # Verify branch condition
        self.assertIn("branch 'develop'", result)

    def test_generate_with_custom_agent(self):
        """Test generating Jenkinsfile with custom agent label."""
        generator = JenkinsPipelineGenerator(agent_label="linux-docker")
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = generator.generate(tech_stack)

        # Verify agent label
        self.assertIn("label 'linux-docker'", result)

    def test_environment_section(self):
        """Test that environment section is generated."""
        tech_stack = {
            "name": "Test Stack",
            "category": "Test",
            "env_vars": {"MY_VAR": "my_value"},
        }
        result = self.generator.generate(tech_stack)

        # Verify environment section
        self.assertIn("environment {", result)
        self.assertIn("CI = 'true'", result)
        self.assertIn("MY_VAR = 'my_value'", result)

    def test_post_section(self):
        """Test that post section is generated."""
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = self.generator.generate(tech_stack)

        # Verify post section
        self.assertIn("post {", result)
        self.assertIn("always {", result)
        self.assertIn("cleanWs()", result)

    def test_options_section(self):
        """Test that options section is generated."""
        tech_stack = {"name": "Test Stack", "category": "Test"}
        result = self.generator.generate(tech_stack)

        # Verify options section
        self.assertIn("options {", result)
        self.assertIn("buildDiscarder", result)
        self.assertIn("timeout", result)
        self.assertIn("timestamps()", result)


class TestCICDAnalyzer(unittest.TestCase):
    """Tests for CICDAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = CICDAnalyzer()

    def test_analyze_node_stack(self):
        """Test analyzing a Node.js tech stack."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertEqual(result.language, "node")
        self.assertEqual(result.package_manager, "npm")
        self.assertEqual(result.test_framework, "jest")
        self.assertEqual(result.lint_tool, "eslint")
        self.assertIn("node_modules/", result.cache_paths)

    def test_analyze_python_stack(self):
        """Test analyzing a Python tech stack."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertEqual(result.language, "python")
        self.assertEqual(result.package_manager, "pip")
        self.assertEqual(result.test_framework, "pytest")
        self.assertEqual(result.lint_tool, "ruff")

    def test_analyze_rust_stack(self):
        """Test analyzing a Rust tech stack."""
        tech_stack = {
            "name": "Rust Web Service",
            "category": "Backend Rust",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertEqual(result.language, "rust")
        self.assertEqual(result.build_tool, "cargo")
        self.assertIn("target/", result.cache_paths)

    def test_analyze_go_stack(self):
        """Test analyzing a Go tech stack."""
        tech_stack = {
            "name": "Go Microservice",
            "category": "Backend Golang",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertEqual(result.language, "go")
        self.assertEqual(result.build_tool, "go")
        self.assertEqual(result.lint_tool, "golangci-lint")

    def test_analyze_with_docker(self):
        """Test analyzing stack with Docker deployment."""
        tech_stack = {
            "name": "Python API",
            "category": "Backend",
            "deploy_provider": "docker",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertTrue(result.has_docker)
        self.assertFalse(result.has_kubernetes)
        self.assertIsNotNone(result.deployment_guidance)
        self.assertEqual(result.deployment_guidance.target, DeploymentTarget.DOCKER)

    def test_analyze_with_kubernetes(self):
        """Test analyzing stack with Kubernetes deployment."""
        tech_stack = {
            "name": "Go Service",
            "category": "Backend",
            "deploy_provider": "kubernetes",
        }
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertTrue(result.has_docker)
        self.assertTrue(result.has_kubernetes)
        self.assertIsNotNone(result.deployment_guidance)
        self.assertEqual(result.deployment_guidance.target, DeploymentTarget.KUBERNETES)

    def test_generate_all_configs(self):
        """Test generating configs for all platforms."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        configs = self.analyzer.generate_all_configs(tech_stack)

        # Verify all platforms are generated
        self.assertIn("github_actions", configs)
        self.assertIn("gitlab_ci", configs)
        self.assertIn("jenkins", configs)

        # Verify each config is valid
        self.assertTrue(configs["github_actions"])  # Non-empty
        self.assertTrue(configs["gitlab_ci"])
        self.assertTrue(configs["jenkins"])

        # Verify GitHub Actions YAML is valid
        github_workflow = yaml.safe_load(configs["github_actions"])
        self.assertIn("jobs", github_workflow)

        # Verify GitLab CI YAML is valid
        gitlab_pipeline = yaml.safe_load(configs["gitlab_ci"])
        self.assertIn("stages", gitlab_pipeline)

        # Verify Jenkins has pipeline structure
        self.assertIn("pipeline {", configs["jenkins"])

    def test_generate_for_specific_platform(self):
        """Test generating config for a specific platform."""
        tech_stack = {
            "name": "Python API",
            "category": "Backend",
        }

        # Test each platform
        github_config = self.analyzer.generate_for_platform(tech_stack, CICDPlatform.GITHUB_ACTIONS)
        gitlab_config = self.analyzer.generate_for_platform(tech_stack, CICDPlatform.GITLAB_CI)
        jenkins_config = self.analyzer.generate_for_platform(tech_stack, CICDPlatform.JENKINS)

        # Verify each is non-empty and valid
        self.assertTrue(github_config)
        self.assertTrue(gitlab_config)
        self.assertTrue(jenkins_config)

        # Verify GitHub Actions
        github_workflow = yaml.safe_load(github_config)
        self.assertIn("jobs", github_workflow)

        # Verify GitLab CI
        gitlab_pipeline = yaml.safe_load(gitlab_config)
        self.assertIn("stages", gitlab_pipeline)

        # Verify Jenkins
        self.assertIn("pipeline {", jenkins_config)

    def test_generate_with_deployment_guidance(self):
        """Test generating configs with deployment guidance."""
        tech_stack = {"name": "Python API", "category": "Backend"}
        guidance = DeploymentGuidance(
            target=DeploymentTarget.KUBERNETES,
            containerized=True,
            kubernetes_namespace="production",
        )

        configs = self.analyzer.generate_all_configs(tech_stack, guidance)

        # Verify GitLab CI has kubernetes commands
        gitlab_pipeline = yaml.safe_load(configs["gitlab_ci"])
        deploy_scripts = gitlab_pipeline.get("deploy", {}).get("script", [])
        self.assertTrue(any("kubectl" in str(s) for s in deploy_scripts))

    def test_recommended_platform(self):
        """Test that recommended platform is GitHub Actions by default."""
        tech_stack = {"name": "Any Stack", "category": "Any"}
        result = self.analyzer.analyze_tech_stack(tech_stack)

        self.assertEqual(result.recommended_platform, CICDPlatform.GITHUB_ACTIONS)


class TestDeploymentGuidance(unittest.TestCase):
    """Tests for DeploymentGuidance dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        guidance = DeploymentGuidance()

        self.assertEqual(guidance.target, DeploymentTarget.GENERIC)
        self.assertFalse(guidance.containerized)
        self.assertIsNone(guidance.docker_registry)
        self.assertEqual(guidance.port, 3000)
        self.assertEqual(guidance.replicas, 1)
        self.assertFalse(guidance.auto_scaling)

    def test_custom_values(self):
        """Test custom values are set correctly."""
        guidance = DeploymentGuidance(
            target=DeploymentTarget.KUBERNETES,
            containerized=True,
            docker_registry="gcr.io/my-project",
            kubernetes_namespace="production",
            port=8080,
            replicas=3,
            auto_scaling=True,
        )

        self.assertEqual(guidance.target, DeploymentTarget.KUBERNETES)
        self.assertTrue(guidance.containerized)
        self.assertEqual(guidance.docker_registry, "gcr.io/my-project")
        self.assertEqual(guidance.kubernetes_namespace, "production")
        self.assertEqual(guidance.port, 8080)
        self.assertEqual(guidance.replicas, 3)
        self.assertTrue(guidance.auto_scaling)


class TestNewConvenienceFunctions(unittest.TestCase):
    """Tests for new convenience functions."""

    def test_get_gitlab_ci_generator(self):
        """Test get_gitlab_ci_generator convenience function."""
        generator = get_gitlab_ci_generator()
        self.assertIsInstance(generator, GitLabCIGenerator)

    def test_get_gitlab_ci_generator_with_kwargs(self):
        """Test get_gitlab_ci_generator with custom kwargs."""
        generator = get_gitlab_ci_generator(include_deploy=False)
        self.assertFalse(generator.include_deploy)

    def test_get_jenkins_generator(self):
        """Test get_jenkins_generator convenience function."""
        generator = get_jenkins_generator()
        self.assertIsInstance(generator, JenkinsPipelineGenerator)

    def test_get_jenkins_generator_with_kwargs(self):
        """Test get_jenkins_generator with custom kwargs."""
        generator = get_jenkins_generator(agent_label="docker-agent")
        self.assertEqual(generator.agent_label, "docker-agent")

    def test_get_cicd_analyzer(self):
        """Test get_cicd_analyzer convenience function."""
        analyzer = get_cicd_analyzer()
        self.assertIsInstance(analyzer, CICDAnalyzer)

    def test_registry_has_new_generators(self):
        """Test that registry has new generators registered."""
        registry = ArtifactGeneratorRegistry()

        self.assertTrue(registry.has_generator("gitlab_ci"))
        self.assertTrue(registry.has_generator("jenkins"))
        self.assertTrue(registry.has_generator("cicd_analyzer"))

    def test_registry_list_includes_new_generators(self):
        """Test that list_generators includes new generators."""
        registry = ArtifactGeneratorRegistry()
        generators = registry.list_generators()
        names = [g["name"] for g in generators]

        self.assertIn("gitlab_ci", names)
        self.assertIn("jenkins", names)
        self.assertIn("cicd_analyzer", names)


if __name__ == "__main__":
    unittest.main()
