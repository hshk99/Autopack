"""Deployment Analysis Module for generating deployment architecture guidance.

Analyzes tech stack and project requirements to generate deployment recommendations
including Docker, Kubernetes, serverless, and IaC templates.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeploymentTarget(str, Enum):
    """Deployment target environment types."""

    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    SERVERLESS = "serverless"
    PAAS = "paas"  # Platform as a Service (Heroku, Railway, etc.)
    STATIC = "static"  # Static hosting (Vercel, Netlify, S3)
    VM = "vm"  # Virtual machine (EC2, Droplet, etc.)


class ScalingStrategy(str, Enum):
    """Scaling strategy types."""

    NONE = "none"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    AUTO = "auto"


class InfrastructureProvider(str, Enum):
    """Cloud infrastructure providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    DIGITALOCEAN = "digitalocean"
    VERCEL = "vercel"
    NETLIFY = "netlify"
    HEROKU = "heroku"
    RAILWAY = "railway"
    FLY_IO = "fly_io"
    SELF_HOSTED = "self_hosted"


class ContainerConfig(BaseModel):
    """Container configuration for Docker/Kubernetes deployments."""

    base_image: str = Field(..., description="Base Docker image")
    port: int = Field(default=3000, description="Container port to expose")
    environment_variables: List[str] = Field(
        default_factory=list, description="Required environment variables"
    )
    volumes: List[str] = Field(default_factory=list, description="Volume mounts")
    health_check_path: str = Field(default="/health", description="Health check endpoint")
    resource_limits: Dict[str, str] = Field(
        default_factory=lambda: {"cpu": "500m", "memory": "512Mi"},
        description="Resource limits for container",
    )


class KubernetesConfig(BaseModel):
    """Kubernetes deployment configuration."""

    replicas: int = Field(default=2, description="Number of replicas")
    namespace: str = Field(default="default", description="Kubernetes namespace")
    service_type: str = Field(
        default="ClusterIP", description="Kubernetes service type"
    )
    ingress_enabled: bool = Field(default=True, description="Enable ingress")
    hpa_enabled: bool = Field(
        default=False, description="Enable Horizontal Pod Autoscaler"
    )
    min_replicas: int = Field(default=1, description="Minimum replicas for HPA")
    max_replicas: int = Field(default=5, description="Maximum replicas for HPA")
    target_cpu_utilization: int = Field(
        default=70, description="Target CPU utilization for HPA"
    )


class ServerlessConfig(BaseModel):
    """Serverless deployment configuration."""

    provider: str = Field(default="aws_lambda", description="Serverless provider")
    runtime: str = Field(default="nodejs20.x", description="Runtime version")
    memory_size: int = Field(default=256, description="Memory size in MB")
    timeout: int = Field(default=30, description="Timeout in seconds")
    functions: List[str] = Field(
        default_factory=list, description="Function entry points"
    )


class DeploymentRecommendation(BaseModel):
    """A single deployment recommendation with rationale."""

    target: DeploymentTarget = Field(..., description="Recommended deployment target")
    provider: InfrastructureProvider = Field(
        ..., description="Recommended infrastructure provider"
    )
    scaling_strategy: ScalingStrategy = Field(
        default=ScalingStrategy.NONE, description="Recommended scaling strategy"
    )
    score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Recommendation score"
    )
    rationale: str = Field(..., description="Reasoning for this recommendation")
    pros: List[str] = Field(default_factory=list, description="Advantages")
    cons: List[str] = Field(default_factory=list, description="Disadvantages")
    estimated_monthly_cost: str = Field(
        default="$0-50", description="Estimated monthly infrastructure cost"
    )
    setup_complexity: str = Field(
        default="medium", description="Setup complexity: low, medium, high"
    )


class DeploymentArchitecture(BaseModel):
    """Complete deployment architecture recommendation."""

    project_name: str = Field(..., description="Project name")
    project_type: str = Field(default="web_app", description="Type of project")
    primary_recommendation: DeploymentRecommendation = Field(
        ..., description="Primary deployment recommendation"
    )
    alternative_recommendations: List[DeploymentRecommendation] = Field(
        default_factory=list, description="Alternative recommendations"
    )
    container_config: Optional[ContainerConfig] = Field(
        default=None, description="Container configuration if applicable"
    )
    kubernetes_config: Optional[KubernetesConfig] = Field(
        default=None, description="Kubernetes configuration if applicable"
    )
    serverless_config: Optional[ServerlessConfig] = Field(
        default=None, description="Serverless configuration if applicable"
    )
    environment_requirements: List[str] = Field(
        default_factory=list, description="Required environment variables"
    )
    infrastructure_requirements: List[str] = Field(
        default_factory=list, description="Infrastructure requirements"
    )


class DeploymentAnalyzer:
    """Analyzer for deployment architecture recommendations.

    Analyzes tech stack characteristics and project requirements to generate
    deployment architecture recommendations including infrastructure choices,
    containerization strategies, and scaling approaches.
    """

    # Language to base image mapping
    _BASE_IMAGES: Dict[str, str] = {
        "node": "node:20-alpine",
        "python": "python:3.11-slim",
        "go": "golang:1.21-alpine",
        "rust": "rust:1.75-alpine",
        "ruby": "ruby:3.2-alpine",
        "php": "php:8.2-fpm-alpine",
        "java": "eclipse-temurin:21-jdk-alpine",
    }

    # Default ports by framework/language
    _DEFAULT_PORTS: Dict[str, int] = {
        "node": 3000,
        "python": 8000,
        "go": 8080,
        "rust": 8080,
        "ruby": 3000,
        "php": 9000,
        "java": 8080,
        "next.js": 3000,
        "react": 3000,
        "django": 8000,
        "fastapi": 8000,
        "flask": 5000,
        "express": 3000,
    }

    # Framework to serverless runtime mapping
    _SERVERLESS_RUNTIMES: Dict[str, str] = {
        "node": "nodejs20.x",
        "python": "python3.11",
        "go": "go1.x",
        "ruby": "ruby3.2",
        "java": "java21",
    }

    def __init__(self):
        """Initialize the deployment analyzer."""
        self._analysis_cache: Dict[str, DeploymentArchitecture] = {}

    def analyze(
        self,
        tech_stack: Dict[str, Any],
        project_requirements: Optional[Dict[str, Any]] = None,
    ) -> DeploymentArchitecture:
        """Analyze tech stack and generate deployment recommendations.

        Args:
            tech_stack: Technology stack configuration with keys like:
                - name: Stack name (e.g., "Next.js + Supabase")
                - category: Category (e.g., "Full Stack JavaScript")
                - language: Primary language (optional)
                - frameworks: List of frameworks (optional)
                - database: Database requirements (optional)
            project_requirements: Optional additional requirements:
                - scale: Expected scale (small, medium, large)
                - budget: Budget constraints (low, medium, high)
                - compliance: Compliance requirements (optional)
                - team_expertise: Team expertise level (optional)

        Returns:
            DeploymentArchitecture with recommendations and configurations
        """
        project_requirements = project_requirements or {}

        stack_name = tech_stack.get("name", "Unknown Stack")
        category = tech_stack.get("category", "")

        logger.info(f"[DeploymentAnalyzer] Analyzing deployment for: {stack_name}")

        # Detect primary language
        language = tech_stack.get("language") or self._detect_language(
            stack_name, category
        )

        # Determine project characteristics
        characteristics = self._analyze_characteristics(
            tech_stack, project_requirements, language
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            tech_stack, characteristics, language
        )

        # Select primary recommendation (highest score)
        primary = recommendations[0]
        alternatives = recommendations[1:3]  # Top 2 alternatives

        # Generate configurations based on primary recommendation
        container_config = None
        kubernetes_config = None
        serverless_config = None

        if primary.target in (DeploymentTarget.DOCKER, DeploymentTarget.KUBERNETES):
            container_config = self._generate_container_config(
                tech_stack, language, characteristics
            )

        if primary.target == DeploymentTarget.KUBERNETES:
            kubernetes_config = self._generate_kubernetes_config(
                tech_stack, characteristics
            )

        if primary.target == DeploymentTarget.SERVERLESS:
            serverless_config = self._generate_serverless_config(
                tech_stack, language, characteristics
            )

        # Determine environment and infrastructure requirements
        env_requirements = self._get_environment_requirements(tech_stack)
        infra_requirements = self._get_infrastructure_requirements(
            primary.target, tech_stack
        )

        architecture = DeploymentArchitecture(
            project_name=stack_name,
            project_type=self._determine_project_type(tech_stack, category),
            primary_recommendation=primary,
            alternative_recommendations=alternatives,
            container_config=container_config,
            kubernetes_config=kubernetes_config,
            serverless_config=serverless_config,
            environment_requirements=env_requirements,
            infrastructure_requirements=infra_requirements,
        )

        logger.info(
            f"[DeploymentAnalyzer] Recommended: {primary.target.value} on {primary.provider.value}"
        )

        return architecture

    def _detect_language(self, stack_name: str, category: str) -> str:
        """Detect primary language from stack name or category.

        Args:
            stack_name: Name of the technology stack
            category: Category of the stack

        Returns:
            Detected language string
        """
        combined = f"{stack_name} {category}".lower()

        language_mapping = {
            "next.js": "node",
            "react": "node",
            "vue": "node",
            "angular": "node",
            "express": "node",
            "node": "node",
            "django": "python",
            "fastapi": "python",
            "flask": "python",
            "python": "python",
            "go": "go",
            "golang": "go",
            "rust": "rust",
            "ruby": "ruby",
            "rails": "ruby",
            "php": "php",
            "laravel": "php",
            "java": "java",
            "spring": "java",
        }

        for tech, lang in language_mapping.items():
            if tech in combined:
                return lang

        return "node"  # Default

    def _analyze_characteristics(
        self,
        tech_stack: Dict[str, Any],
        requirements: Dict[str, Any],
        language: str,
    ) -> Dict[str, Any]:
        """Analyze project characteristics from tech stack and requirements.

        Args:
            tech_stack: Technology stack configuration
            requirements: Project requirements
            language: Detected primary language

        Returns:
            Dictionary of analyzed characteristics
        """
        characteristics = {
            "language": language,
            "is_frontend_only": self._is_frontend_only(tech_stack),
            "has_database": self._has_database(tech_stack),
            "has_api": self._has_api(tech_stack),
            "is_stateless": self._is_stateless(tech_stack),
            "scale": requirements.get("scale", "small"),
            "budget": requirements.get("budget", "low"),
            "team_expertise": requirements.get("team_expertise", "medium"),
            "needs_persistence": self._needs_persistence(tech_stack),
            "is_monolith": self._is_monolith(tech_stack),
            "is_microservices": self._is_microservices(tech_stack),
        }

        return characteristics

    def _is_frontend_only(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project is frontend-only (static site)."""
        stack_name = tech_stack.get("name", "").lower()
        category = tech_stack.get("category", "").lower()

        frontend_indicators = [
            "static",
            "spa",
            "frontend",
            "react app",
            "vue app",
            "angular app",
        ]
        backend_indicators = [
            "api",
            "backend",
            "server",
            "database",
            "postgres",
            "mysql",
            "mongo",
            "supabase",
            "firebase",
            "express",
            "django",
            "fastapi",
        ]

        combined = f"{stack_name} {category}"

        has_backend = any(ind in combined for ind in backend_indicators)
        is_frontend = any(ind in combined for ind in frontend_indicators)

        return is_frontend and not has_backend

    def _has_database(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project requires a database."""
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )
        db_indicators = [
            "postgres",
            "mysql",
            "mongo",
            "redis",
            "sqlite",
            "supabase",
            "firebase",
            "dynamodb",
            "database",
        ]
        return any(db in combined for db in db_indicators)

    def _has_api(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project has API components."""
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )
        api_indicators = [
            "api",
            "rest",
            "graphql",
            "backend",
            "server",
            "fastapi",
            "express",
            "django",
            "flask",
        ]
        return any(api in combined for api in api_indicators)

    def _is_stateless(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if application is stateless."""
        # If it has a database connection, it's still potentially stateless
        # (database state != application state)
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )
        stateful_indicators = ["session", "websocket", "socket.io", "real-time"]
        return not any(ind in combined for ind in stateful_indicators)

    def _needs_persistence(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project needs persistent storage beyond database."""
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )
        persistence_indicators = ["upload", "storage", "files", "media", "assets", "s3"]
        return any(ind in combined for ind in persistence_indicators)

    def _is_monolith(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project follows monolithic architecture."""
        category = tech_stack.get("category", "").lower()
        return "monolith" in category or "full stack" in category

    def _is_microservices(self, tech_stack: Dict[str, Any]) -> bool:
        """Check if project follows microservices architecture."""
        category = tech_stack.get("category", "").lower()
        return "microservice" in category or "distributed" in category

    def _determine_project_type(self, tech_stack: Dict[str, Any], category: str) -> str:
        """Determine the project type from stack and category."""
        combined = f"{tech_stack.get('name', '')} {category}".lower()

        if "api" in combined or "backend" in combined:
            return "api"
        elif "static" in combined or "spa" in combined:
            return "static_site"
        elif "full stack" in combined:
            return "full_stack"
        elif "microservice" in combined:
            return "microservices"
        else:
            return "web_app"

    def _generate_recommendations(
        self,
        tech_stack: Dict[str, Any],
        characteristics: Dict[str, Any],
        language: str,
    ) -> List[DeploymentRecommendation]:
        """Generate ranked deployment recommendations.

        Args:
            tech_stack: Technology stack configuration
            characteristics: Analyzed project characteristics
            language: Primary language

        Returns:
            List of DeploymentRecommendation sorted by score (highest first)
        """
        recommendations = []

        # Static/Frontend-only projects
        if characteristics["is_frontend_only"]:
            recommendations.extend(self._get_static_recommendations())
        # API/Backend projects
        elif characteristics["has_api"]:
            if characteristics["scale"] == "large" or characteristics["is_microservices"]:
                recommendations.extend(
                    self._get_kubernetes_recommendations(characteristics)
                )
            recommendations.extend(self._get_container_recommendations(characteristics))
            recommendations.extend(self._get_paas_recommendations(characteristics))
            if characteristics["is_stateless"]:
                recommendations.extend(
                    self._get_serverless_recommendations(characteristics, language)
                )
        # Default case (full stack)
        else:
            recommendations.extend(self._get_container_recommendations(characteristics))
            recommendations.extend(self._get_paas_recommendations(characteristics))

        # Score and sort recommendations
        for rec in recommendations:
            rec.score = self._calculate_recommendation_score(rec, characteristics)

        recommendations.sort(key=lambda r: r.score, reverse=True)

        return recommendations

    def _get_static_recommendations(self) -> List[DeploymentRecommendation]:
        """Get recommendations for static site deployment."""
        return [
            DeploymentRecommendation(
                target=DeploymentTarget.STATIC,
                provider=InfrastructureProvider.VERCEL,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="Vercel provides zero-config deployment with automatic CDN distribution for static sites and SSR.",
                pros=[
                    "Zero configuration required",
                    "Automatic HTTPS and CDN",
                    "Preview deployments for PRs",
                    "Generous free tier",
                ],
                cons=[
                    "Limited backend functionality",
                    "Vendor lock-in for serverless functions",
                ],
                estimated_monthly_cost="$0-20",
                setup_complexity="low",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.STATIC,
                provider=InfrastructureProvider.NETLIFY,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="Netlify offers excellent static hosting with built-in CI/CD and edge functions.",
                pros=[
                    "Easy GitHub integration",
                    "Instant rollbacks",
                    "Edge functions support",
                    "Form handling included",
                ],
                cons=[
                    "Build minutes limited on free tier",
                    "Function execution time limits",
                ],
                estimated_monthly_cost="$0-19",
                setup_complexity="low",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.STATIC,
                provider=InfrastructureProvider.AWS,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="AWS S3 + CloudFront provides cost-effective static hosting at scale.",
                pros=[
                    "Very low cost at scale",
                    "Full control over caching",
                    "Global CDN with CloudFront",
                ],
                cons=[
                    "More complex setup",
                    "Requires AWS knowledge",
                    "Manual CI/CD setup required",
                ],
                estimated_monthly_cost="$1-10",
                setup_complexity="medium",
            ),
        ]

    def _get_container_recommendations(
        self, characteristics: Dict[str, Any]
    ) -> List[DeploymentRecommendation]:
        """Get recommendations for container deployment."""
        recommendations = [
            DeploymentRecommendation(
                target=DeploymentTarget.DOCKER,
                provider=InfrastructureProvider.FLY_IO,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="Fly.io offers simple Docker deployment with global edge distribution and easy scaling.",
                pros=[
                    "Simple Docker deployment",
                    "Global edge distribution",
                    "Built-in PostgreSQL and Redis",
                    "Generous free tier",
                ],
                cons=[
                    "Newer platform, smaller ecosystem",
                    "Limited enterprise features",
                ],
                estimated_monthly_cost="$0-50",
                setup_complexity="low",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.DOCKER,
                provider=InfrastructureProvider.RAILWAY,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="Railway provides developer-friendly container deployment with automatic scaling.",
                pros=[
                    "Excellent developer experience",
                    "Easy database provisioning",
                    "GitHub integration",
                    "Usage-based pricing",
                ],
                cons=[
                    "Can get expensive at scale",
                    "Limited customization options",
                ],
                estimated_monthly_cost="$5-100",
                setup_complexity="low",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.DOCKER,
                provider=InfrastructureProvider.DIGITALOCEAN,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="DigitalOcean App Platform offers straightforward container hosting with predictable pricing.",
                pros=[
                    "Predictable pricing",
                    "Good documentation",
                    "Managed databases available",
                    "Simple scaling",
                ],
                cons=[
                    "Fewer regions than AWS/GCP",
                    "Limited advanced features",
                ],
                estimated_monthly_cost="$5-50",
                setup_complexity="low",
            ),
        ]

        # Add AWS ECS for larger scale
        if characteristics.get("scale") in ("medium", "large"):
            recommendations.append(
                DeploymentRecommendation(
                    target=DeploymentTarget.DOCKER,
                    provider=InfrastructureProvider.AWS,
                    scaling_strategy=ScalingStrategy.AUTO,
                    rationale="AWS ECS provides production-grade container orchestration with auto-scaling.",
                    pros=[
                        "Production-proven at scale",
                        "Deep AWS integration",
                        "Fargate for serverless containers",
                        "Extensive monitoring",
                    ],
                    cons=[
                        "Complex configuration",
                        "Requires AWS expertise",
                        "Can be expensive",
                    ],
                    estimated_monthly_cost="$50-500",
                    setup_complexity="high",
                )
            )

        return recommendations

    def _get_kubernetes_recommendations(
        self, characteristics: Dict[str, Any]
    ) -> List[DeploymentRecommendation]:
        """Get recommendations for Kubernetes deployment."""
        return [
            DeploymentRecommendation(
                target=DeploymentTarget.KUBERNETES,
                provider=InfrastructureProvider.GCP,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="GKE provides the most mature managed Kubernetes with excellent autopilot mode.",
                pros=[
                    "Autopilot mode reduces ops burden",
                    "Excellent observability tools",
                    "Cost optimization features",
                    "Strong security defaults",
                ],
                cons=[
                    "Can be expensive for small workloads",
                    "Requires Kubernetes knowledge",
                ],
                estimated_monthly_cost="$100-1000",
                setup_complexity="high",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.KUBERNETES,
                provider=InfrastructureProvider.AWS,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="EKS is ideal for teams already using AWS services extensively.",
                pros=[
                    "Deep AWS integration",
                    "Managed control plane",
                    "Extensive ecosystem",
                ],
                cons=[
                    "Complex pricing model",
                    "Control plane costs",
                    "Steeper learning curve",
                ],
                estimated_monthly_cost="$150-1500",
                setup_complexity="high",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.KUBERNETES,
                provider=InfrastructureProvider.DIGITALOCEAN,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="DOKS offers simpler Kubernetes for teams wanting K8s without cloud complexity.",
                pros=[
                    "Simple pricing",
                    "Free control plane",
                    "Good for learning K8s",
                ],
                cons=[
                    "Fewer advanced features",
                    "Limited integrations",
                ],
                estimated_monthly_cost="$50-300",
                setup_complexity="medium",
            ),
        ]

    def _get_serverless_recommendations(
        self, characteristics: Dict[str, Any], language: str
    ) -> List[DeploymentRecommendation]:
        """Get recommendations for serverless deployment."""
        recommendations = []

        if language in ("node", "python"):
            recommendations.append(
                DeploymentRecommendation(
                    target=DeploymentTarget.SERVERLESS,
                    provider=InfrastructureProvider.VERCEL,
                    scaling_strategy=ScalingStrategy.AUTO,
                    rationale="Vercel Serverless Functions provide zero-config serverless deployment.",
                    pros=[
                        "Zero configuration",
                        "Automatic scaling",
                        "Edge functions support",
                        "Great for Next.js/Node.js",
                    ],
                    cons=[
                        "Function timeout limits",
                        "Cold starts",
                        "Vendor lock-in",
                    ],
                    estimated_monthly_cost="$0-100",
                    setup_complexity="low",
                )
            )

        recommendations.append(
            DeploymentRecommendation(
                target=DeploymentTarget.SERVERLESS,
                provider=InfrastructureProvider.AWS,
                scaling_strategy=ScalingStrategy.AUTO,
                rationale="AWS Lambda offers mature serverless platform with extensive integrations.",
                pros=[
                    "Pay per invocation",
                    "Massive scale capability",
                    "Deep AWS integration",
                    "Provisioned concurrency option",
                ],
                cons=[
                    "Cold starts",
                    "Complex IAM configuration",
                    "15-minute execution limit",
                ],
                estimated_monthly_cost="$0-200",
                setup_complexity="medium",
            )
        )

        return recommendations

    def _get_paas_recommendations(
        self, characteristics: Dict[str, Any]
    ) -> List[DeploymentRecommendation]:
        """Get recommendations for PaaS deployment."""
        return [
            DeploymentRecommendation(
                target=DeploymentTarget.PAAS,
                provider=InfrastructureProvider.HEROKU,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="Heroku provides the simplest deployment experience for developers.",
                pros=[
                    "Extremely simple deployment",
                    "Add-ons marketplace",
                    "Good for prototypes",
                    "Automatic SSL",
                ],
                cons=[
                    "Expensive at scale",
                    "Limited customization",
                    "Dyno sleeping on free tier",
                ],
                estimated_monthly_cost="$7-250",
                setup_complexity="low",
            ),
            DeploymentRecommendation(
                target=DeploymentTarget.PAAS,
                provider=InfrastructureProvider.RAILWAY,
                scaling_strategy=ScalingStrategy.HORIZONTAL,
                rationale="Railway is a modern Heroku alternative with better pricing and DX.",
                pros=[
                    "Modern developer experience",
                    "Usage-based pricing",
                    "Easy database setup",
                    "Good free tier",
                ],
                cons=[
                    "Newer platform",
                    "Less mature ecosystem",
                ],
                estimated_monthly_cost="$5-100",
                setup_complexity="low",
            ),
        ]

    def _calculate_recommendation_score(
        self, recommendation: DeploymentRecommendation, characteristics: Dict[str, Any]
    ) -> float:
        """Calculate a score for a recommendation based on project characteristics.

        Args:
            recommendation: The deployment recommendation
            characteristics: Project characteristics

        Returns:
            Score between 0 and 1
        """
        score = 0.5  # Base score

        # Scale considerations
        scale = characteristics.get("scale", "small")
        if scale == "small":
            if recommendation.setup_complexity == "low":
                score += 0.2
            elif recommendation.setup_complexity == "high":
                score -= 0.1
        elif scale == "large":
            if recommendation.target == DeploymentTarget.KUBERNETES:
                score += 0.2
            elif recommendation.setup_complexity == "low":
                score -= 0.1

        # Budget considerations
        budget = characteristics.get("budget", "low")
        if budget == "low":
            if "0-" in recommendation.estimated_monthly_cost:
                score += 0.15
            elif "500" in recommendation.estimated_monthly_cost:
                score -= 0.2

        # Team expertise
        expertise = characteristics.get("team_expertise", "medium")
        if expertise == "low":
            if recommendation.setup_complexity == "low":
                score += 0.2
            elif recommendation.setup_complexity == "high":
                score -= 0.2
        elif expertise == "high":
            if recommendation.target == DeploymentTarget.KUBERNETES:
                score += 0.1

        # Stateless apps benefit from serverless/containers
        if characteristics.get("is_stateless", False):
            if recommendation.target in (
                DeploymentTarget.SERVERLESS,
                DeploymentTarget.DOCKER,
            ):
                score += 0.1

        # Frontend-only apps benefit from static hosting
        if characteristics.get("is_frontend_only", False):
            if recommendation.target == DeploymentTarget.STATIC:
                score += 0.3

        return min(1.0, max(0.0, score))

    def _generate_container_config(
        self,
        tech_stack: Dict[str, Any],
        language: str,
        characteristics: Dict[str, Any],
    ) -> ContainerConfig:
        """Generate container configuration.

        Args:
            tech_stack: Technology stack configuration
            language: Primary language
            characteristics: Project characteristics

        Returns:
            ContainerConfig for Docker deployment
        """
        base_image = self._BASE_IMAGES.get(language, "node:20-alpine")
        port = self._get_default_port(tech_stack, language)

        env_vars = self._get_environment_requirements(tech_stack)

        volumes = []
        if characteristics.get("needs_persistence", False):
            volumes.append("/app/uploads:/data/uploads")

        resource_limits = {"cpu": "500m", "memory": "512Mi"}
        scale = characteristics.get("scale", "small")
        if scale == "medium":
            resource_limits = {"cpu": "1000m", "memory": "1Gi"}
        elif scale == "large":
            resource_limits = {"cpu": "2000m", "memory": "2Gi"}

        return ContainerConfig(
            base_image=base_image,
            port=port,
            environment_variables=env_vars,
            volumes=volumes,
            health_check_path="/health",
            resource_limits=resource_limits,
        )

    def _generate_kubernetes_config(
        self,
        tech_stack: Dict[str, Any],
        characteristics: Dict[str, Any],
    ) -> KubernetesConfig:
        """Generate Kubernetes configuration.

        Args:
            tech_stack: Technology stack configuration
            characteristics: Project characteristics

        Returns:
            KubernetesConfig for Kubernetes deployment
        """
        scale = characteristics.get("scale", "small")

        replicas = 2
        hpa_enabled = False
        min_replicas = 1
        max_replicas = 5

        if scale == "medium":
            replicas = 3
            hpa_enabled = True
            max_replicas = 10
        elif scale == "large":
            replicas = 5
            hpa_enabled = True
            min_replicas = 3
            max_replicas = 20

        return KubernetesConfig(
            replicas=replicas,
            namespace="production",
            service_type="ClusterIP",
            ingress_enabled=True,
            hpa_enabled=hpa_enabled,
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            target_cpu_utilization=70,
        )

    def _generate_serverless_config(
        self,
        tech_stack: Dict[str, Any],
        language: str,
        characteristics: Dict[str, Any],
    ) -> ServerlessConfig:
        """Generate serverless configuration.

        Args:
            tech_stack: Technology stack configuration
            language: Primary language
            characteristics: Project characteristics

        Returns:
            ServerlessConfig for serverless deployment
        """
        runtime = self._SERVERLESS_RUNTIMES.get(language, "nodejs20.x")

        memory_size = 256
        scale = characteristics.get("scale", "small")
        if scale == "medium":
            memory_size = 512
        elif scale == "large":
            memory_size = 1024

        return ServerlessConfig(
            provider="aws_lambda",
            runtime=runtime,
            memory_size=memory_size,
            timeout=30,
            functions=["handler.main"],
        )

    def _get_default_port(self, tech_stack: Dict[str, Any], language: str) -> int:
        """Get default port for the tech stack.

        Args:
            tech_stack: Technology stack configuration
            language: Primary language

        Returns:
            Port number
        """
        stack_name = tech_stack.get("name", "").lower()

        for tech, port in self._DEFAULT_PORTS.items():
            if tech in stack_name:
                return port

        return self._DEFAULT_PORTS.get(language, 3000)

    def _get_environment_requirements(self, tech_stack: Dict[str, Any]) -> List[str]:
        """Get required environment variables.

        Args:
            tech_stack: Technology stack configuration

        Returns:
            List of required environment variable names
        """
        env_vars = ["NODE_ENV", "LOG_LEVEL"]
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )

        if any(db in combined for db in ["postgres", "mysql", "database"]):
            env_vars.append("DATABASE_URL")

        if "redis" in combined:
            env_vars.append("REDIS_URL")

        if any(auth in combined for auth in ["auth", "supabase", "firebase"]):
            env_vars.extend(["AUTH_SECRET", "AUTH_URL"])

        if "stripe" in combined:
            env_vars.extend(["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"])

        if any(api in combined for api in ["api", "openai", "anthropic"]):
            env_vars.append("API_KEY")

        return list(set(env_vars))

    def _get_infrastructure_requirements(
        self, target: DeploymentTarget, tech_stack: Dict[str, Any]
    ) -> List[str]:
        """Get infrastructure requirements based on deployment target.

        Args:
            target: Deployment target
            tech_stack: Technology stack configuration

        Returns:
            List of infrastructure requirements
        """
        requirements = []
        combined = (
            f"{tech_stack.get('name', '')} {tech_stack.get('category', '')}".lower()
        )

        # Base requirements by target
        if target == DeploymentTarget.DOCKER:
            requirements.append("Container registry for Docker images")
        elif target == DeploymentTarget.KUBERNETES:
            requirements.extend(
                [
                    "Kubernetes cluster",
                    "Container registry",
                    "Ingress controller",
                    "Load balancer",
                ]
            )
        elif target == DeploymentTarget.SERVERLESS:
            requirements.append("Serverless function runtime")
        elif target == DeploymentTarget.STATIC:
            requirements.append("CDN for static file distribution")

        # Database requirements
        if any(db in combined for db in ["postgres", "postgresql"]):
            requirements.append("PostgreSQL database (managed or self-hosted)")
        elif "mysql" in combined:
            requirements.append("MySQL database (managed or self-hosted)")
        elif "mongo" in combined:
            requirements.append("MongoDB database (managed or self-hosted)")

        # Cache requirements
        if "redis" in combined:
            requirements.append("Redis cache (managed or self-hosted)")

        # Storage requirements
        if any(storage in combined for storage in ["upload", "storage", "s3"]):
            requirements.append("Object storage for file uploads (S3, GCS, etc.)")

        return requirements
