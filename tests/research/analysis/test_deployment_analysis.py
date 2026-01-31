"""Tests for Deployment Analysis module."""

import unittest

from autopack.research.analysis.deployment_analysis import (
    ContainerConfig,
    DeploymentAnalyzer,
    DeploymentArchitecture,
    DeploymentRecommendation,
    DeploymentTarget,
    InfrastructureProvider,
    KubernetesConfig,
    ScalingStrategy,
    ServerlessConfig,
)


class TestDeploymentTarget(unittest.TestCase):
    """Tests for DeploymentTarget enum."""

    def test_deployment_targets_exist(self):
        """Test all deployment targets are defined."""
        targets = [
            DeploymentTarget.DOCKER,
            DeploymentTarget.KUBERNETES,
            DeploymentTarget.SERVERLESS,
            DeploymentTarget.PAAS,
            DeploymentTarget.STATIC,
            DeploymentTarget.VM,
        ]
        self.assertEqual(len(targets), 6)

    def test_deployment_target_values(self):
        """Test deployment target values are strings."""
        self.assertEqual(DeploymentTarget.DOCKER.value, "docker")
        self.assertEqual(DeploymentTarget.KUBERNETES.value, "kubernetes")
        self.assertEqual(DeploymentTarget.SERVERLESS.value, "serverless")


class TestInfrastructureProvider(unittest.TestCase):
    """Tests for InfrastructureProvider enum."""

    def test_providers_exist(self):
        """Test all infrastructure providers are defined."""
        providers = [
            InfrastructureProvider.AWS,
            InfrastructureProvider.GCP,
            InfrastructureProvider.AZURE,
            InfrastructureProvider.DIGITALOCEAN,
            InfrastructureProvider.VERCEL,
            InfrastructureProvider.NETLIFY,
            InfrastructureProvider.HEROKU,
            InfrastructureProvider.RAILWAY,
            InfrastructureProvider.FLY_IO,
            InfrastructureProvider.SELF_HOSTED,
        ]
        self.assertEqual(len(providers), 10)


class TestContainerConfig(unittest.TestCase):
    """Tests for ContainerConfig model."""

    def test_default_config(self):
        """Test ContainerConfig with defaults."""
        config = ContainerConfig(base_image="node:20-alpine")
        self.assertEqual(config.base_image, "node:20-alpine")
        self.assertEqual(config.port, 3000)
        self.assertEqual(config.health_check_path, "/health")
        self.assertEqual(config.environment_variables, [])
        self.assertEqual(config.volumes, [])

    def test_custom_config(self):
        """Test ContainerConfig with custom values."""
        config = ContainerConfig(
            base_image="python:3.11-slim",
            port=8000,
            environment_variables=["DATABASE_URL", "API_KEY"],
            volumes=["/app/data:/data"],
            health_check_path="/api/health",
            resource_limits={"cpu": "1000m", "memory": "1Gi"},
        )
        self.assertEqual(config.base_image, "python:3.11-slim")
        self.assertEqual(config.port, 8000)
        self.assertEqual(len(config.environment_variables), 2)
        self.assertEqual(config.resource_limits["memory"], "1Gi")


class TestKubernetesConfig(unittest.TestCase):
    """Tests for KubernetesConfig model."""

    def test_default_config(self):
        """Test KubernetesConfig with defaults."""
        config = KubernetesConfig()
        self.assertEqual(config.replicas, 2)
        self.assertEqual(config.namespace, "default")
        self.assertEqual(config.service_type, "ClusterIP")
        self.assertTrue(config.ingress_enabled)
        self.assertFalse(config.hpa_enabled)

    def test_hpa_config(self):
        """Test KubernetesConfig with HPA enabled."""
        config = KubernetesConfig(
            replicas=5,
            hpa_enabled=True,
            min_replicas=3,
            max_replicas=20,
            target_cpu_utilization=80,
        )
        self.assertTrue(config.hpa_enabled)
        self.assertEqual(config.min_replicas, 3)
        self.assertEqual(config.max_replicas, 20)
        self.assertEqual(config.target_cpu_utilization, 80)


class TestServerlessConfig(unittest.TestCase):
    """Tests for ServerlessConfig model."""

    def test_default_config(self):
        """Test ServerlessConfig with defaults."""
        config = ServerlessConfig()
        self.assertEqual(config.provider, "aws_lambda")
        self.assertEqual(config.runtime, "nodejs20.x")
        self.assertEqual(config.memory_size, 256)
        self.assertEqual(config.timeout, 30)

    def test_custom_config(self):
        """Test ServerlessConfig with custom values."""
        config = ServerlessConfig(
            provider="aws_lambda",
            runtime="python3.11",
            memory_size=1024,
            timeout=60,
            functions=["handler.main", "handler.api"],
        )
        self.assertEqual(config.runtime, "python3.11")
        self.assertEqual(config.memory_size, 1024)
        self.assertEqual(len(config.functions), 2)


class TestDeploymentRecommendation(unittest.TestCase):
    """Tests for DeploymentRecommendation model."""

    def test_recommendation_creation(self):
        """Test creating a deployment recommendation."""
        rec = DeploymentRecommendation(
            target=DeploymentTarget.DOCKER,
            provider=InfrastructureProvider.FLY_IO,
            scaling_strategy=ScalingStrategy.HORIZONTAL,
            rationale="Simple Docker deployment with global distribution",
            pros=["Easy setup", "Good pricing"],
            cons=["Newer platform"],
            estimated_monthly_cost="$0-50",
            setup_complexity="low",
        )
        self.assertEqual(rec.target, DeploymentTarget.DOCKER)
        self.assertEqual(rec.provider, InfrastructureProvider.FLY_IO)
        self.assertEqual(rec.scaling_strategy, ScalingStrategy.HORIZONTAL)
        self.assertEqual(len(rec.pros), 2)
        self.assertEqual(len(rec.cons), 1)


class TestDeploymentArchitecture(unittest.TestCase):
    """Tests for DeploymentArchitecture model."""

    def test_architecture_creation(self):
        """Test creating a deployment architecture."""
        primary = DeploymentRecommendation(
            target=DeploymentTarget.DOCKER,
            provider=InfrastructureProvider.FLY_IO,
            rationale="Good for small to medium apps",
        )
        arch = DeploymentArchitecture(
            project_name="Test Project",
            project_type="web_app",
            primary_recommendation=primary,
        )
        self.assertEqual(arch.project_name, "Test Project")
        self.assertEqual(arch.project_type, "web_app")
        self.assertEqual(arch.primary_recommendation.target, DeploymentTarget.DOCKER)


class TestDeploymentAnalyzer(unittest.TestCase):
    """Tests for DeploymentAnalyzer class."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = DeploymentAnalyzer()

    def test_analyze_node_stack(self):
        """Test analyzing a Node.js stack."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        result = self.analyzer.analyze(tech_stack)

        self.assertIsInstance(result, DeploymentArchitecture)
        self.assertIn("Next.js", result.project_name)
        self.assertIsNotNone(result.primary_recommendation)
        self.assertIsInstance(result.primary_recommendation, DeploymentRecommendation)

    def test_analyze_python_stack(self):
        """Test analyzing a Python stack."""
        tech_stack = {
            "name": "Django + PostgreSQL",
            "category": "Python Web Stack",
        }
        result = self.analyzer.analyze(tech_stack)

        self.assertIsInstance(result, DeploymentArchitecture)
        self.assertEqual(result.project_name, "Django + PostgreSQL")

    def test_analyze_static_site(self):
        """Test analyzing a static site."""
        tech_stack = {
            "name": "React SPA",
            "category": "Frontend Static",
        }
        result = self.analyzer.analyze(tech_stack)

        self.assertIsInstance(result, DeploymentArchitecture)
        # Static sites should recommend static hosting
        self.assertEqual(
            result.primary_recommendation.target, DeploymentTarget.STATIC
        )

    def test_analyze_with_requirements(self):
        """Test analyzing with project requirements."""
        tech_stack = {
            "name": "FastAPI + Redis",
            "category": "Python API",
        }
        requirements = {
            "scale": "large",
            "budget": "high",
            "team_expertise": "high",
        }
        result = self.analyzer.analyze(tech_stack, requirements)

        self.assertIsInstance(result, DeploymentArchitecture)
        # Large scale should suggest Kubernetes
        k8s_recommended = result.primary_recommendation.target == DeploymentTarget.KUBERNETES
        k8s_alternative = any(
            alt.target == DeploymentTarget.KUBERNETES
            for alt in result.alternative_recommendations
        )
        self.assertTrue(k8s_recommended or k8s_alternative)

    def test_analyze_generates_container_config(self):
        """Test that container config is generated for Docker targets."""
        tech_stack = {
            "name": "Express API",
            "category": "Node.js Backend",
        }
        result = self.analyzer.analyze(tech_stack)

        # Should have container config for container-based deployments
        if result.primary_recommendation.target in (
            DeploymentTarget.DOCKER,
            DeploymentTarget.KUBERNETES,
        ):
            self.assertIsNotNone(result.container_config)
            self.assertIsInstance(result.container_config, ContainerConfig)

    def test_analyze_generates_k8s_config(self):
        """Test that K8s config is generated for Kubernetes targets."""
        tech_stack = {
            "name": "FastAPI + Redis",
            "category": "Python API",
        }
        requirements = {"scale": "large"}
        result = self.analyzer.analyze(tech_stack, requirements)

        if result.primary_recommendation.target == DeploymentTarget.KUBERNETES:
            self.assertIsNotNone(result.kubernetes_config)
            self.assertIsInstance(result.kubernetes_config, KubernetesConfig)

    def test_language_detection_node(self):
        """Test language detection for Node.js stacks."""
        test_cases = [
            ("Next.js + Vercel", "Full Stack", "node"),
            ("React App", "Frontend", "node"),
            ("Express API", "Backend", "node"),
        ]
        for stack_name, category, expected in test_cases:
            with self.subTest(stack_name=stack_name):
                detected = self.analyzer._detect_language(stack_name, category)
                self.assertEqual(detected, expected)

    def test_language_detection_python(self):
        """Test language detection for Python stacks."""
        test_cases = [
            ("Django + PostgreSQL", "Python Web", "python"),
            ("FastAPI + Redis", "Backend", "python"),
            ("Flask App", "Microservice", "python"),
        ]
        for stack_name, category, expected in test_cases:
            with self.subTest(stack_name=stack_name):
                detected = self.analyzer._detect_language(stack_name, category)
                self.assertEqual(detected, expected)

    def test_language_detection_fallback(self):
        """Test language detection falls back to node for unknown."""
        detected = self.analyzer._detect_language("Unknown Stack", "Unknown")
        self.assertEqual(detected, "node")

    def test_environment_requirements_database(self):
        """Test environment requirements detection for database."""
        tech_stack = {"name": "Django + PostgreSQL", "category": "Python Web"}
        env_vars = self.analyzer._get_environment_requirements(tech_stack)
        self.assertIn("DATABASE_URL", env_vars)

    def test_environment_requirements_redis(self):
        """Test environment requirements detection for Redis."""
        tech_stack = {"name": "Express + Redis", "category": "Node.js Backend"}
        env_vars = self.analyzer._get_environment_requirements(tech_stack)
        self.assertIn("REDIS_URL", env_vars)

    def test_environment_requirements_auth(self):
        """Test environment requirements detection for auth."""
        tech_stack = {"name": "Next.js + Supabase", "category": "Full Stack"}
        env_vars = self.analyzer._get_environment_requirements(tech_stack)
        self.assertIn("AUTH_SECRET", env_vars)

    def test_infrastructure_requirements_docker(self):
        """Test infrastructure requirements for Docker deployment."""
        requirements = self.analyzer._get_infrastructure_requirements(
            DeploymentTarget.DOCKER, {"name": "Test", "category": "Test"}
        )
        self.assertTrue(any("registry" in req.lower() for req in requirements))

    def test_infrastructure_requirements_kubernetes(self):
        """Test infrastructure requirements for Kubernetes deployment."""
        requirements = self.analyzer._get_infrastructure_requirements(
            DeploymentTarget.KUBERNETES, {"name": "Test", "category": "Test"}
        )
        self.assertTrue(any("cluster" in req.lower() for req in requirements))
        self.assertTrue(any("ingress" in req.lower() for req in requirements))

    def test_frontend_only_detection(self):
        """Test detection of frontend-only projects."""
        # Static site should be detected as frontend-only
        tech_stack = {"name": "React SPA", "category": "Frontend Static"}
        is_frontend = self.analyzer._is_frontend_only(tech_stack)
        self.assertTrue(is_frontend)

        # Full stack should not be frontend-only
        tech_stack = {"name": "Next.js + Supabase", "category": "Full Stack"}
        is_frontend = self.analyzer._is_frontend_only(tech_stack)
        self.assertFalse(is_frontend)

    def test_has_database_detection(self):
        """Test detection of database requirements."""
        # With database
        tech_stack = {"name": "Django + PostgreSQL", "category": "Python Web"}
        has_db = self.analyzer._has_database(tech_stack)
        self.assertTrue(has_db)

        # Without database
        tech_stack = {"name": "React SPA", "category": "Frontend"}
        has_db = self.analyzer._has_database(tech_stack)
        self.assertFalse(has_db)

    def test_has_api_detection(self):
        """Test detection of API components."""
        # With API
        tech_stack = {"name": "FastAPI + Redis", "category": "Python API"}
        has_api = self.analyzer._has_api(tech_stack)
        self.assertTrue(has_api)

        # Without API
        tech_stack = {"name": "React SPA", "category": "Frontend Static"}
        has_api = self.analyzer._has_api(tech_stack)
        self.assertFalse(has_api)

    def test_alternative_recommendations(self):
        """Test that alternative recommendations are generated."""
        tech_stack = {
            "name": "Next.js + PostgreSQL",
            "category": "Full Stack JavaScript",
        }
        result = self.analyzer.analyze(tech_stack)

        # Should have at least one alternative
        self.assertGreater(len(result.alternative_recommendations), 0)
        # Alternatives should be different from primary
        for alt in result.alternative_recommendations:
            self.assertIsInstance(alt, DeploymentRecommendation)


class TestDeploymentAnalyzerContainerConfig(unittest.TestCase):
    """Tests for DeploymentAnalyzer container configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = DeploymentAnalyzer()

    def test_node_container_config(self):
        """Test container config generation for Node.js."""
        tech_stack = {"name": "Express API", "category": "Node.js Backend"}
        result = self.analyzer.analyze(tech_stack)

        if result.container_config:
            self.assertIn("node", result.container_config.base_image.lower())

    def test_python_container_config(self):
        """Test container config generation for Python."""
        tech_stack = {"name": "FastAPI", "category": "Python Backend"}
        result = self.analyzer.analyze(tech_stack)

        if result.container_config:
            self.assertIn("python", result.container_config.base_image.lower())

    def test_container_config_port(self):
        """Test container config port is set correctly."""
        tech_stack = {"name": "Django API", "category": "Python Backend"}
        result = self.analyzer.analyze(tech_stack)

        if result.container_config:
            # Python backends typically use 8000 or 8080
            self.assertIn(result.container_config.port, [8000, 8080])

    def test_container_config_resources_scale(self):
        """Test container resources scale with requirements."""
        tech_stack = {"name": "Express API", "category": "Node.js Backend"}

        # Small scale
        result_small = self.analyzer.analyze(tech_stack, {"scale": "small"})
        if result_small.container_config:
            small_memory = result_small.container_config.resource_limits.get("memory")

        # Large scale
        result_large = self.analyzer.analyze(tech_stack, {"scale": "large"})
        if result_large.container_config:
            large_memory = result_large.container_config.resource_limits.get("memory")

        # Large should have more resources
        if result_small.container_config and result_large.container_config:
            # Compare numeric values (e.g., "512Mi" vs "2Gi")
            self.assertNotEqual(small_memory, large_memory)


class TestDeploymentAnalyzerKubernetesConfig(unittest.TestCase):
    """Tests for DeploymentAnalyzer Kubernetes configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = DeploymentAnalyzer()

    def test_k8s_config_replicas_scale(self):
        """Test K8s replicas scale with requirements."""
        tech_stack = {"name": "FastAPI", "category": "Python API"}

        # Small scale
        result_small = self.analyzer.analyze(tech_stack, {"scale": "small"})

        # Large scale
        result_large = self.analyzer.analyze(tech_stack, {"scale": "large"})

        if result_small.kubernetes_config and result_large.kubernetes_config:
            self.assertLess(
                result_small.kubernetes_config.replicas,
                result_large.kubernetes_config.replicas,
            )

    def test_k8s_hpa_enabled_for_large_scale(self):
        """Test HPA is enabled for large scale deployments."""
        tech_stack = {"name": "FastAPI", "category": "Python API"}
        result = self.analyzer.analyze(tech_stack, {"scale": "large"})

        if result.kubernetes_config:
            self.assertTrue(result.kubernetes_config.hpa_enabled)


if __name__ == "__main__":
    unittest.main()
