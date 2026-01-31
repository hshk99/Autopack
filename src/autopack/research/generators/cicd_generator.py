"""CI/CD Workflow Generator for research projects.

Generates CI/CD pipeline configurations for multiple platforms:
- GitHub Actions workflows
- GitLab CI/CD pipelines
- Jenkins Pipelines (Declarative)

Integrates with deployment guidance to generate appropriate deployment stages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class CICDPlatform(str, Enum):
    """Supported CI/CD platforms."""

    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"


class DeploymentTarget(str, Enum):
    """Supported deployment targets."""

    VERCEL = "vercel"
    NETLIFY = "netlify"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    AWS_ECS = "aws_ecs"
    AWS_LAMBDA = "aws_lambda"
    HEROKU = "heroku"
    RAILWAY = "railway"
    FLY_IO = "fly_io"
    GENERIC = "generic"


@dataclass
class DeploymentGuidance:
    """Deployment guidance configuration from IMP-RES-003."""

    target: DeploymentTarget = DeploymentTarget.GENERIC
    containerized: bool = False
    docker_registry: Optional[str] = None
    kubernetes_namespace: Optional[str] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    secrets_required: List[str] = field(default_factory=list)
    health_check_path: Optional[str] = None
    port: int = 3000
    replicas: int = 1
    auto_scaling: bool = False


@dataclass
class CICDAnalysisResult:
    """Result of CI/CD analysis for a project."""

    language: str
    version: str
    build_tool: str
    test_framework: Optional[str]
    lint_tool: Optional[str]
    package_manager: str
    has_docker: bool
    has_kubernetes: bool
    deployment_guidance: Optional[DeploymentGuidance]
    recommended_platform: CICDPlatform
    artifacts: List[str]
    cache_paths: List[str]


class CICDWorkflowGenerator:
    """Generates CI/CD workflows from tech stack proposals.

    Produces GitHub Actions workflow YAML files based on technology stack
    configuration including language, framework, and deployment settings.
    """

    # Mapping of technology categories to their typical language/runtime
    _LANGUAGE_MAPPING: Dict[str, str] = {
        "Next.js": "node",
        "React": "node",
        "Vue.js": "node",
        "Angular": "node",
        "Django": "python",
        "FastAPI": "python",
        "Flask": "python",
        "Python": "python",
        "Node.js": "node",
        "Express": "node",
        "Rust": "rust",
        "Go": "go",
        "Ruby on Rails": "ruby",
        "PHP": "php",
        "Laravel": "php",
    }

    # Default versions for languages
    _DEFAULT_VERSIONS: Dict[str, str] = {
        "node": "20",
        "python": "3.11",
        "rust": "stable",
        "go": "1.21",
        "ruby": "3.2",
        "php": "8.2",
    }

    # Test commands by language
    _TEST_COMMANDS: Dict[str, List[str]] = {
        "node": ["npm ci", "npm run lint", "npm test"],
        "python": ["pip install -e '.[dev]'", "pytest tests/ -v"],
        "rust": ["cargo test"],
        "go": ["go test ./..."],
        "ruby": ["bundle install", "bundle exec rspec"],
        "php": ["composer install", "vendor/bin/phpunit"],
    }

    # Build commands by language
    _BUILD_COMMANDS: Dict[str, List[str]] = {
        "node": ["npm run build"],
        "python": ["pip install build", "python -m build"],
        "rust": ["cargo build --release"],
        "go": ["go build ./..."],
        "ruby": ["bundle exec rake build"],
        "php": ["composer install --no-dev --optimize-autoloader"],
    }

    def __init__(
        self,
        default_branch: str = "main",
        include_deploy: bool = True,
        include_security_scan: bool = True,
    ):
        """Initialize the CI/CD workflow generator.

        Args:
            default_branch: Default branch to trigger workflows on
            include_deploy: Whether to include deployment job
            include_security_scan: Whether to include security scanning
        """
        self.default_branch = default_branch
        self.include_deploy = include_deploy
        self.include_security_scan = include_security_scan

    def generate(self, tech_stack: Dict[str, Any]) -> str:
        """Generate GitHub Actions workflow YAML.

        Args:
            tech_stack: Technology stack configuration dict with keys:
                - name: Stack name (e.g., "Next.js + Supabase")
                - category: Category (e.g., "Full Stack JavaScript")
                - language: Primary language (optional, auto-detected if missing)
                - test_command: Custom test command (optional)
                - build_command: Custom build command (optional)
                - deploy_provider: Deployment provider (optional)
                - env_vars: Environment variables (optional)

        Returns:
            Valid GitHub Actions workflow YAML string
        """
        stack_name = tech_stack.get("name", "Unknown Stack")
        category = tech_stack.get("category", "")

        # Detect language from stack name or category
        language = tech_stack.get("language") or self._detect_language(stack_name, category)
        version = tech_stack.get("version") or self._DEFAULT_VERSIONS.get(language, "latest")

        logger.info(
            f"[CICDWorkflowGenerator] Generating workflow for {stack_name} "
            f"(language={language}, version={version})"
        )

        workflow = self._build_workflow_structure(
            stack_name=stack_name,
            language=language,
            version=version,
            tech_stack=tech_stack,
        )

        # Use yaml.dump with proper formatting
        yaml_output = yaml.dump(
            workflow,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        return yaml_output

    def _detect_language(self, stack_name: str, category: str) -> str:
        """Detect the primary language from stack name or category.

        Args:
            stack_name: Name of the technology stack
            category: Category of the stack

        Returns:
            Detected language string (defaults to "node")
        """
        combined = f"{stack_name} {category}".lower()

        for tech, lang in self._LANGUAGE_MAPPING.items():
            if tech.lower() in combined:
                return lang

        # Default to node for unknown stacks
        return "node"

    def _build_workflow_structure(
        self,
        stack_name: str,
        language: str,
        version: str,
        tech_stack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the complete workflow structure.

        Args:
            stack_name: Name of the technology stack
            language: Primary programming language
            version: Language version
            tech_stack: Full tech stack configuration

        Returns:
            Workflow structure as dict
        """
        workflow: Dict[str, Any] = {
            "name": f"CI/CD - {stack_name}",
            "on": {
                "push": {"branches": [self.default_branch]},
                "pull_request": {"branches": [self.default_branch]},
            },
            "env": self._build_env_vars(tech_stack),
            "jobs": {},
        }

        # Add test job
        workflow["jobs"]["test"] = self._build_test_job(
            language=language,
            version=version,
            tech_stack=tech_stack,
        )

        # Add security scan job if enabled
        if self.include_security_scan:
            workflow["jobs"]["security"] = self._build_security_job(language)

        # Add build job
        workflow["jobs"]["build"] = self._build_build_job(
            language=language,
            version=version,
            tech_stack=tech_stack,
        )

        # Add deploy job if enabled
        if self.include_deploy:
            deploy_job = self._build_deploy_job(tech_stack)
            if deploy_job:
                workflow["jobs"]["deploy"] = deploy_job

        return workflow

    def _build_env_vars(self, tech_stack: Dict[str, Any]) -> Dict[str, str]:
        """Build environment variables section.

        Args:
            tech_stack: Tech stack configuration

        Returns:
            Dict of environment variables
        """
        env_vars: Dict[str, str] = {
            "CI": "true",
        }

        # Add custom env vars from tech stack
        custom_vars = tech_stack.get("env_vars", {})
        if isinstance(custom_vars, dict):
            env_vars.update(custom_vars)

        return env_vars

    def _build_test_job(
        self,
        language: str,
        version: str,
        tech_stack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the test job configuration.

        Args:
            language: Programming language
            version: Language version
            tech_stack: Tech stack configuration

        Returns:
            Test job configuration dict
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add language setup step
        setup_step = self._get_setup_step(language, version)
        if setup_step:
            job["steps"].append(setup_step)

        # Add cache step
        cache_step = self._get_cache_step(language)
        if cache_step:
            job["steps"].append(cache_step)

        # Add test commands
        custom_test_cmd = tech_stack.get("test_command")
        test_commands = (
            [custom_test_cmd]
            if custom_test_cmd
            else self._TEST_COMMANDS.get(language, ["echo 'No tests configured'"])
        )

        for cmd in test_commands:
            job["steps"].append({"name": f"Run: {cmd[:50]}", "run": cmd})

        return job

    def _build_security_job(self, language: str) -> Dict[str, Any]:
        """Build the security scanning job.

        Args:
            language: Programming language

        Returns:
            Security job configuration dict
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add CodeQL analysis for supported languages
        if language in ["node", "python", "go", "ruby"]:
            codeql_lang = "javascript" if language == "node" else language
            job["steps"].extend(
                [
                    {
                        "name": "Initialize CodeQL",
                        "uses": "github/codeql-action/init@v3",
                        "with": {"languages": codeql_lang},
                    },
                    {
                        "name": "Autobuild",
                        "uses": "github/codeql-action/autobuild@v3",
                    },
                    {
                        "name": "Perform CodeQL Analysis",
                        "uses": "github/codeql-action/analyze@v3",
                    },
                ]
            )
        else:
            # Generic dependency scan
            job["steps"].append(
                {
                    "name": "Dependency Review",
                    "uses": "actions/dependency-review-action@v4",
                    "if": "github.event_name == 'pull_request'",
                }
            )

        return job

    def _build_build_job(
        self,
        language: str,
        version: str,
        tech_stack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the build job configuration.

        Args:
            language: Programming language
            version: Language version
            tech_stack: Tech stack configuration

        Returns:
            Build job configuration dict
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "needs": ["test"],
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add language setup step
        setup_step = self._get_setup_step(language, version)
        if setup_step:
            job["steps"].append(setup_step)

        # Add cache step
        cache_step = self._get_cache_step(language)
        if cache_step:
            job["steps"].append(cache_step)

        # Add build commands
        custom_build_cmd = tech_stack.get("build_command")
        build_commands = (
            [custom_build_cmd]
            if custom_build_cmd
            else self._BUILD_COMMANDS.get(language, ["echo 'No build configured'"])
        )

        for cmd in build_commands:
            job["steps"].append({"name": f"Build: {cmd[:50]}", "run": cmd})

        # Upload artifacts
        job["steps"].append(
            {
                "name": "Upload build artifacts",
                "uses": "actions/upload-artifact@v4",
                "with": {
                    "name": "build-artifacts",
                    "path": self._get_artifact_path(language),
                    "retention-days": 7,
                },
            }
        )

        return job

    def _build_deploy_job(self, tech_stack: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build the deployment job configuration.

        Args:
            tech_stack: Tech stack configuration

        Returns:
            Deploy job configuration dict or None if no deployment configured
        """
        deploy_provider = tech_stack.get("deploy_provider", "").lower()

        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "needs": ["build"],
            "if": f"github.ref == 'refs/heads/{self.default_branch}'",
            "environment": "production",
            "steps": [
                {"uses": "actions/checkout@v4"},
                {
                    "name": "Download build artifacts",
                    "uses": "actions/download-artifact@v4",
                    "with": {"name": "build-artifacts"},
                },
            ],
        }

        # Add provider-specific deployment steps
        if deploy_provider == "vercel":
            job["steps"].append(
                {
                    "name": "Deploy to Vercel",
                    "uses": "amondnet/vercel-action@v25",
                    "with": {
                        "vercel-token": "${{ secrets.VERCEL_TOKEN }}",
                        "vercel-org-id": "${{ secrets.VERCEL_ORG_ID }}",
                        "vercel-project-id": "${{ secrets.VERCEL_PROJECT_ID }}",
                        "vercel-args": "--prod",
                    },
                }
            )
        elif deploy_provider == "netlify":
            job["steps"].append(
                {
                    "name": "Deploy to Netlify",
                    "uses": "nwtgck/actions-netlify@v2",
                    "with": {
                        "publish-dir": "./build",
                        "production-deploy": True,
                    },
                    "env": {
                        "NETLIFY_AUTH_TOKEN": "${{ secrets.NETLIFY_AUTH_TOKEN }}",
                        "NETLIFY_SITE_ID": "${{ secrets.NETLIFY_SITE_ID }}",
                    },
                }
            )
        elif deploy_provider == "docker":
            job["steps"].extend(
                [
                    {
                        "name": "Set up Docker Buildx",
                        "uses": "docker/setup-buildx-action@v3",
                    },
                    {
                        "name": "Login to Container Registry",
                        "uses": "docker/login-action@v3",
                        "with": {
                            "registry": "${{ secrets.REGISTRY_URL }}",
                            "username": "${{ secrets.REGISTRY_USERNAME }}",
                            "password": "${{ secrets.REGISTRY_PASSWORD }}",
                        },
                    },
                    {
                        "name": "Build and push Docker image",
                        "uses": "docker/build-push-action@v5",
                        "with": {
                            "context": ".",
                            "push": True,
                            "tags": "${{ secrets.REGISTRY_URL }}/${{ github.repository }}:${{ github.sha }}",
                        },
                    },
                ]
            )
        else:
            # Generic deployment placeholder
            job["steps"].append(
                {
                    "name": "Deploy",
                    "run": "echo 'Deployment step - configure for your provider'",
                }
            )

        return job

    def _get_setup_step(self, language: str, version: str) -> Optional[Dict[str, Any]]:
        """Get the setup step for a language.

        Args:
            language: Programming language
            version: Language version

        Returns:
            Setup step dict or None
        """
        if language == "node":
            return {
                "name": "Setup Node.js",
                "uses": "actions/setup-node@v4",
                "with": {"node-version": version, "cache": "npm"},
            }
        elif language == "python":
            return {
                "name": "Setup Python",
                "uses": "actions/setup-python@v5",
                "with": {"python-version": version, "cache": "pip"},
            }
        elif language == "go":
            return {
                "name": "Setup Go",
                "uses": "actions/setup-go@v5",
                "with": {"go-version": version},
            }
        elif language == "rust":
            return {
                "name": "Setup Rust",
                "uses": "dtolnay/rust-toolchain@stable",
            }
        elif language == "ruby":
            return {
                "name": "Setup Ruby",
                "uses": "ruby/setup-ruby@v1",
                "with": {"ruby-version": version, "bundler-cache": True},
            }
        return None

    def _get_cache_step(self, language: str) -> Optional[Dict[str, Any]]:
        """Get the cache step for a language.

        Args:
            language: Programming language

        Returns:
            Cache step dict or None (some setup actions include caching)
        """
        # Most modern setup actions include caching, so we skip for those
        if language in ["node", "python", "ruby"]:
            return None

        if language == "rust":
            return {
                "name": "Cache Rust dependencies",
                "uses": "Swatinem/rust-cache@v2",
            }
        elif language == "go":
            return {
                "name": "Cache Go modules",
                "uses": "actions/cache@v4",
                "with": {
                    "path": "~/go/pkg/mod",
                    "key": "${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}",
                },
            }
        return None

    def _get_artifact_path(self, language: str) -> str:
        """Get the typical artifact output path for a language.

        Args:
            language: Programming language

        Returns:
            Artifact path string
        """
        artifact_paths: Dict[str, str] = {
            "node": "dist/\n.next/\nbuild/",
            "python": "dist/",
            "rust": "target/release/",
            "go": "bin/",
            "ruby": "pkg/",
            "php": "vendor/",
        }
        return artifact_paths.get(language, "dist/")

    def generate_from_proposal(self, proposal: Any) -> str:
        """Generate workflow from a TechStackProposal object.

        Args:
            proposal: TechStackProposal instance with recommendation

        Returns:
            GitHub Actions workflow YAML string
        """
        # Extract tech stack from proposal
        if hasattr(proposal, "options") and proposal.options:
            # Use recommended option or first option
            option = None
            if hasattr(proposal, "recommendation") and proposal.recommendation:
                for opt in proposal.options:
                    if opt.name == proposal.recommendation:
                        option = opt
                        break
            if option is None:
                option = proposal.options[0]

            tech_stack = {
                "name": option.name,
                "category": option.category,
                "description": option.description,
            }

            return self.generate(tech_stack)

        # Fallback if proposal structure is different
        return self.generate({"name": "Generic Project", "category": "Unknown"})


class GitLabCIGenerator:
    """Generates GitLab CI/CD pipeline configurations.

    Produces .gitlab-ci.yml files based on technology stack configuration
    including language, framework, and deployment settings.
    """

    # Docker images by language
    _DOCKER_IMAGES: Dict[str, str] = {
        "node": "node:20-alpine",
        "python": "python:3.11-slim",
        "rust": "rust:1.75",
        "go": "golang:1.21",
        "ruby": "ruby:3.2",
        "php": "php:8.2-cli",
    }

    # Test scripts by language
    _TEST_SCRIPTS: Dict[str, List[str]] = {
        "node": ["npm ci", "npm run lint", "npm test"],
        "python": ["pip install -e '.[dev]'", "pytest tests/ -v --cov"],
        "rust": ["cargo test"],
        "go": ["go test ./... -v -cover"],
        "ruby": ["bundle install", "bundle exec rspec"],
        "php": ["composer install", "vendor/bin/phpunit"],
    }

    # Build scripts by language
    _BUILD_SCRIPTS: Dict[str, List[str]] = {
        "node": ["npm ci", "npm run build"],
        "python": ["pip install build", "python -m build"],
        "rust": ["cargo build --release"],
        "go": ["go build -o bin/ ./..."],
        "ruby": ["bundle exec rake build"],
        "php": ["composer install --no-dev --optimize-autoloader"],
    }

    def __init__(
        self,
        default_branch: str = "main",
        include_deploy: bool = True,
        include_security_scan: bool = True,
    ):
        """Initialize the GitLab CI generator.

        Args:
            default_branch: Default branch for deployment
            include_deploy: Whether to include deployment stage
            include_security_scan: Whether to include security scanning
        """
        self.default_branch = default_branch
        self.include_deploy = include_deploy
        self.include_security_scan = include_security_scan

    def generate(
        self,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance] = None,
    ) -> str:
        """Generate GitLab CI pipeline YAML.

        Args:
            tech_stack: Technology stack configuration dict
            deployment_guidance: Optional deployment configuration

        Returns:
            Valid GitLab CI YAML string
        """
        stack_name = tech_stack.get("name", "Unknown Stack")
        category = tech_stack.get("category", "")

        # Detect language
        language = tech_stack.get("language") or self._detect_language(stack_name, category)

        logger.info(f"[GitLabCIGenerator] Generating pipeline for {stack_name} (language={language})")

        pipeline = self._build_pipeline_structure(
            language=language,
            tech_stack=tech_stack,
            deployment_guidance=deployment_guidance,
        )

        # Use yaml.dump with proper formatting
        yaml_output = yaml.dump(
            pipeline,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        return yaml_output

    def _detect_language(self, stack_name: str, category: str) -> str:
        """Detect language from stack name or category."""
        combined = f"{stack_name} {category}".lower()

        language_mapping = {
            "next.js": "node",
            "react": "node",
            "vue": "node",
            "angular": "node",
            "express": "node",
            "django": "python",
            "fastapi": "python",
            "flask": "python",
            "python": "python",
            "rust": "rust",
            "go": "go",
            "golang": "go",
            "ruby": "ruby",
            "rails": "ruby",
            "php": "php",
            "laravel": "php",
        }

        for tech, lang in language_mapping.items():
            if tech in combined:
                return lang

        return "node"

    def _build_pipeline_structure(
        self,
        language: str,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance],
    ) -> Dict[str, Any]:
        """Build the complete GitLab CI pipeline structure."""
        pipeline: Dict[str, Any] = {
            "stages": ["test", "build"],
            "default": {
                "image": self._DOCKER_IMAGES.get(language, "alpine:latest"),
            },
            "variables": {
                "CI": "true",
            },
        }

        if self.include_security_scan:
            pipeline["stages"].insert(1, "security")

        if self.include_deploy:
            pipeline["stages"].append("deploy")

        # Add cache configuration
        pipeline["cache"] = self._get_cache_config(language)

        # Add test job
        pipeline["test"] = self._build_test_job(language, tech_stack)

        # Add security job
        if self.include_security_scan:
            pipeline["security_scan"] = self._build_security_job(language)

        # Add build job
        pipeline["build"] = self._build_build_job(language, tech_stack)

        # Add deploy job
        if self.include_deploy:
            deploy_job = self._build_deploy_job(tech_stack, deployment_guidance)
            if deploy_job:
                pipeline["deploy"] = deploy_job

        return pipeline

    def _get_cache_config(self, language: str) -> Dict[str, Any]:
        """Get cache configuration for language."""
        cache_paths: Dict[str, List[str]] = {
            "node": ["node_modules/", ".npm/"],
            "python": [".cache/pip/", ".venv/"],
            "rust": ["target/", ".cargo/"],
            "go": [".go/pkg/mod/"],
            "ruby": ["vendor/bundle/"],
            "php": ["vendor/"],
        }

        return {
            "key": "${CI_COMMIT_REF_SLUG}",
            "paths": cache_paths.get(language, []),
        }

    def _build_test_job(self, language: str, tech_stack: Dict[str, Any]) -> Dict[str, Any]:
        """Build the test job configuration."""
        custom_test = tech_stack.get("test_command")
        scripts = [custom_test] if custom_test else self._TEST_SCRIPTS.get(language, ["echo 'No tests'"])

        return {
            "stage": "test",
            "script": scripts,
            "artifacts": {
                "reports": {"junit": "test-results.xml"},
                "when": "always",
            },
            "coverage": r"/TOTAL.*\s+(\d+%)$/",
        }

    def _build_security_job(self, language: str) -> Dict[str, Any]:
        """Build the security scanning job."""
        if language == "node":
            return {
                "stage": "security",
                "script": ["npm audit --audit-level=moderate"],
                "allow_failure": True,
            }
        elif language == "python":
            return {
                "stage": "security",
                "script": [
                    "pip install safety bandit",
                    "safety check",
                    "bandit -r src/ -ll",
                ],
                "allow_failure": True,
            }
        else:
            return {
                "stage": "security",
                "script": ["echo 'Security scan placeholder'"],
                "allow_failure": True,
            }

    def _build_build_job(self, language: str, tech_stack: Dict[str, Any]) -> Dict[str, Any]:
        """Build the build job configuration."""
        custom_build = tech_stack.get("build_command")
        scripts = [custom_build] if custom_build else self._BUILD_SCRIPTS.get(language, ["echo 'No build'"])

        artifact_paths: Dict[str, List[str]] = {
            "node": ["dist/", ".next/", "build/"],
            "python": ["dist/"],
            "rust": ["target/release/"],
            "go": ["bin/"],
            "ruby": ["pkg/"],
            "php": ["vendor/"],
        }

        return {
            "stage": "build",
            "script": scripts,
            "artifacts": {
                "paths": artifact_paths.get(language, ["dist/"]),
                "expire_in": "1 week",
            },
            "needs": ["test"],
        }

    def _build_deploy_job(
        self,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance],
    ) -> Optional[Dict[str, Any]]:
        """Build the deployment job configuration."""
        deploy_provider = tech_stack.get("deploy_provider", "").lower()

        # Use deployment guidance if available
        if deployment_guidance:
            deploy_provider = deployment_guidance.target.value

        job: Dict[str, Any] = {
            "stage": "deploy",
            "needs": ["build"],
            "only": [self.default_branch],
            "environment": {
                "name": "production",
            },
        }

        if deploy_provider in ["docker", "kubernetes"]:
            job["image"] = "docker:24.0"
            job["services"] = ["docker:24.0-dind"]
            job["script"] = [
                "docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .",
                "docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA",
            ]
            if deploy_provider == "kubernetes":
                job["script"].extend([
                    "kubectl set image deployment/app app=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA",
                ])
        elif deploy_provider == "heroku":
            job["script"] = [
                "apt-get update && apt-get install -y curl",
                "curl https://cli-assets.heroku.com/install.sh | sh",
                "heroku container:push web -a $HEROKU_APP_NAME",
                "heroku container:release web -a $HEROKU_APP_NAME",
            ]
        else:
            job["script"] = ["echo 'Configure deployment for your provider'"]

        return job


class JenkinsPipelineGenerator:
    """Generates Jenkins Declarative Pipeline configurations.

    Produces Jenkinsfile with stages for testing, building, and deploying
    based on technology stack configuration.
    """

    # Tool configurations by language
    _TOOL_CONFIGS: Dict[str, Dict[str, str]] = {
        "node": {"nodejs": "nodejs-20"},
        "python": {},  # Python usually installed on agent
        "go": {"go": "go-1.21"},
        "rust": {},
        "ruby": {},
        "php": {},
    }

    def __init__(
        self,
        default_branch: str = "main",
        include_deploy: bool = True,
        include_security_scan: bool = True,
        agent_label: str = "any",
    ):
        """Initialize the Jenkins pipeline generator.

        Args:
            default_branch: Default branch for deployment
            include_deploy: Whether to include deployment stage
            include_security_scan: Whether to include security scanning
            agent_label: Jenkins agent label
        """
        self.default_branch = default_branch
        self.include_deploy = include_deploy
        self.include_security_scan = include_security_scan
        self.agent_label = agent_label

    def generate(
        self,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance] = None,
    ) -> str:
        """Generate Jenkins Declarative Pipeline.

        Args:
            tech_stack: Technology stack configuration dict
            deployment_guidance: Optional deployment configuration

        Returns:
            Valid Jenkinsfile content
        """
        stack_name = tech_stack.get("name", "Unknown Stack")
        category = tech_stack.get("category", "")

        # Detect language
        language = tech_stack.get("language") or self._detect_language(stack_name, category)

        logger.info(f"[JenkinsPipelineGenerator] Generating pipeline for {stack_name}")

        return self._build_jenkinsfile(
            language=language,
            tech_stack=tech_stack,
            deployment_guidance=deployment_guidance,
        )

    def _detect_language(self, stack_name: str, category: str) -> str:
        """Detect language from stack name or category."""
        combined = f"{stack_name} {category}".lower()

        language_mapping = {
            "next.js": "node",
            "react": "node",
            "vue": "node",
            "angular": "node",
            "django": "python",
            "fastapi": "python",
            "flask": "python",
            "python": "python",
            "rust": "rust",
            "go": "go",
            "ruby": "ruby",
            "php": "php",
        }

        for tech, lang in language_mapping.items():
            if tech in combined:
                return lang

        return "node"

    def _build_jenkinsfile(
        self,
        language: str,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance],
    ) -> str:
        """Build the complete Jenkinsfile content."""
        lines = [
            "pipeline {",
            f"    agent {{ label '{self.agent_label}' }}",
            "",
        ]

        # Add environment variables
        lines.extend(self._build_environment_section(tech_stack))

        # Add tools section if needed
        tools = self._TOOL_CONFIGS.get(language, {})
        if tools:
            lines.append("    tools {")
            for tool_type, tool_name in tools.items():
                lines.append(f"        {tool_type} '{tool_name}'")
            lines.append("    }")
            lines.append("")

        # Add options
        lines.extend([
            "    options {",
            "        buildDiscarder(logRotator(numToKeepStr: '10'))",
            "        timeout(time: 30, unit: 'MINUTES')",
            "        timestamps()",
            "    }",
            "",
        ])

        # Add stages
        lines.append("    stages {")

        # Test stage
        lines.extend(self._build_test_stage(language, tech_stack))

        # Security stage
        if self.include_security_scan:
            lines.extend(self._build_security_stage(language))

        # Build stage
        lines.extend(self._build_build_stage(language, tech_stack))

        # Deploy stage
        if self.include_deploy:
            lines.extend(self._build_deploy_stage(tech_stack, deployment_guidance))

        lines.append("    }")  # Close stages

        # Add post section
        lines.extend(self._build_post_section())

        lines.append("}")  # Close pipeline

        return "\n".join(lines)

    def _build_environment_section(self, tech_stack: Dict[str, Any]) -> List[str]:
        """Build the environment section."""
        lines = ["    environment {", "        CI = 'true'"]

        env_vars = tech_stack.get("env_vars", {})
        for key, value in env_vars.items():
            lines.append(f"        {key} = '{value}'")

        lines.extend(["    }", ""])
        return lines

    def _build_test_stage(self, language: str, tech_stack: Dict[str, Any]) -> List[str]:
        """Build the test stage."""
        custom_test = tech_stack.get("test_command")

        test_commands: Dict[str, List[str]] = {
            "node": ["npm ci", "npm run lint", "npm test"],
            "python": ["pip install -e '.[dev]'", "pytest tests/ -v --junitxml=test-results.xml"],
            "rust": ["cargo test"],
            "go": ["go test ./... -v"],
            "ruby": ["bundle install", "bundle exec rspec"],
            "php": ["composer install", "vendor/bin/phpunit"],
        }

        commands = [custom_test] if custom_test else test_commands.get(language, ["echo 'No tests'"])

        lines = [
            "        stage('Test') {",
            "            steps {",
        ]

        for cmd in commands:
            lines.append(f"                sh '{cmd}'")

        lines.extend([
            "            }",
            "            post {",
            "                always {",
            "                    junit allowEmptyResults: true, testResults: '**/test-results.xml'",
            "                }",
            "            }",
            "        }",
        ])

        return lines

    def _build_security_stage(self, language: str) -> List[str]:
        """Build the security scanning stage."""
        security_commands: Dict[str, List[str]] = {
            "node": ["npm audit --audit-level=moderate || true"],
            "python": ["pip install safety && safety check || true"],
            "rust": ["cargo audit || true"],
            "go": ["go install golang.org/x/vuln/cmd/govulncheck@latest && govulncheck ./... || true"],
        }

        commands = security_commands.get(language, ["echo 'Security scan placeholder'"])

        lines = [
            "        stage('Security Scan') {",
            "            steps {",
        ]

        for cmd in commands:
            lines.append(f"                sh '{cmd}'")

        lines.extend([
            "            }",
            "        }",
        ])

        return lines

    def _build_build_stage(self, language: str, tech_stack: Dict[str, Any]) -> List[str]:
        """Build the build stage."""
        custom_build = tech_stack.get("build_command")

        build_commands: Dict[str, List[str]] = {
            "node": ["npm run build"],
            "python": ["pip install build", "python -m build"],
            "rust": ["cargo build --release"],
            "go": ["go build -o bin/ ./..."],
            "ruby": ["bundle exec rake build"],
            "php": ["composer install --no-dev --optimize-autoloader"],
        }

        commands = [custom_build] if custom_build else build_commands.get(language, ["echo 'No build'"])

        lines = [
            "        stage('Build') {",
            "            steps {",
        ]

        for cmd in commands:
            lines.append(f"                sh '{cmd}'")

        artifact_paths: Dict[str, str] = {
            "node": "dist/, .next/, build/",
            "python": "dist/",
            "rust": "target/release/",
            "go": "bin/",
        }

        artifact = artifact_paths.get(language, "dist/")

        lines.extend([
            "            }",
            "            post {",
            "                success {",
            f"                    archiveArtifacts artifacts: '{artifact}', fingerprint: true",
            "                }",
            "            }",
            "        }",
        ])

        return lines

    def _build_deploy_stage(
        self,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance],
    ) -> List[str]:
        """Build the deploy stage."""
        deploy_provider = tech_stack.get("deploy_provider", "").lower()

        if deployment_guidance:
            deploy_provider = deployment_guidance.target.value

        lines = [
            "        stage('Deploy') {",
            "            when {",
            f"                branch '{self.default_branch}'",
            "            }",
            "            steps {",
        ]

        if deploy_provider in ["docker", "kubernetes"]:
            lines.extend([
                "                sh 'docker build -t ${DOCKER_IMAGE}:${BUILD_NUMBER} .'",
                "                sh 'docker push ${DOCKER_IMAGE}:${BUILD_NUMBER}'",
            ])
            if deploy_provider == "kubernetes":
                lines.append(
                    "                sh 'kubectl set image deployment/app "
                    "app=${DOCKER_IMAGE}:${BUILD_NUMBER}'"
                )
        else:
            lines.append("                echo 'Configure deployment for your provider'")

        lines.extend([
            "            }",
            "        }",
        ])

        return lines

    def _build_post_section(self) -> List[str]:
        """Build the post section."""
        return [
            "",
            "    post {",
            "        always {",
            "            cleanWs()",
            "        }",
            "        success {",
            "            echo 'Pipeline completed successfully!'",
            "        }",
            "        failure {",
            "            echo 'Pipeline failed!'",
            "        }",
            "    }",
        ]


class CICDAnalyzer:
    """Analyzes tech stack and generates appropriate CI/CD configurations.

    Coordinates between different CI/CD generators and integrates with
    deployment guidance from IMP-RES-003.
    """

    def __init__(self):
        """Initialize the CI/CD analyzer."""
        self._github_generator = CICDWorkflowGenerator()
        self._gitlab_generator = GitLabCIGenerator()
        self._jenkins_generator = JenkinsPipelineGenerator()

    def analyze_tech_stack(self, tech_stack: Dict[str, Any]) -> CICDAnalysisResult:
        """Analyze a tech stack and determine CI/CD requirements.

        Args:
            tech_stack: Technology stack configuration

        Returns:
            CICDAnalysisResult with analysis findings
        """
        stack_name = tech_stack.get("name", "").lower()
        category = tech_stack.get("category", "").lower()
        combined = f"{stack_name} {category}"

        # Detect language
        language = self._detect_language(combined)

        # Detect version
        version = tech_stack.get("version") or self._get_default_version(language)

        # Detect build tool
        build_tool = self._detect_build_tool(language, tech_stack)

        # Detect test framework
        test_framework = self._detect_test_framework(language, tech_stack)

        # Detect lint tool
        lint_tool = self._detect_lint_tool(language)

        # Detect package manager
        package_manager = self._detect_package_manager(language, tech_stack)

        # Check for Docker/Kubernetes
        has_docker = tech_stack.get("deploy_provider", "").lower() in ["docker", "kubernetes"]
        has_kubernetes = tech_stack.get("deploy_provider", "").lower() == "kubernetes"

        # Get deployment guidance if available
        deployment_guidance = self._extract_deployment_guidance(tech_stack)

        # Recommend CI/CD platform
        recommended_platform = self._recommend_platform(tech_stack)

        # Get artifact paths
        artifacts = self._get_artifact_paths(language)

        # Get cache paths
        cache_paths = self._get_cache_paths(language)

        logger.info(
            f"[CICDAnalyzer] Analyzed {stack_name}: language={language}, "
            f"build_tool={build_tool}, recommended_platform={recommended_platform.value}"
        )

        return CICDAnalysisResult(
            language=language,
            version=version,
            build_tool=build_tool,
            test_framework=test_framework,
            lint_tool=lint_tool,
            package_manager=package_manager,
            has_docker=has_docker,
            has_kubernetes=has_kubernetes,
            deployment_guidance=deployment_guidance,
            recommended_platform=recommended_platform,
            artifacts=artifacts,
            cache_paths=cache_paths,
        )

    def generate_all_configs(
        self,
        tech_stack: Dict[str, Any],
        deployment_guidance: Optional[DeploymentGuidance] = None,
    ) -> Dict[str, str]:
        """Generate CI/CD configs for all supported platforms.

        Args:
            tech_stack: Technology stack configuration
            deployment_guidance: Optional deployment guidance

        Returns:
            Dict mapping platform name to config content
        """
        return {
            "github_actions": self._github_generator.generate(tech_stack),
            "gitlab_ci": self._gitlab_generator.generate(tech_stack, deployment_guidance),
            "jenkins": self._jenkins_generator.generate(tech_stack, deployment_guidance),
        }

    def generate_for_platform(
        self,
        tech_stack: Dict[str, Any],
        platform: CICDPlatform,
        deployment_guidance: Optional[DeploymentGuidance] = None,
    ) -> str:
        """Generate CI/CD config for a specific platform.

        Args:
            tech_stack: Technology stack configuration
            platform: Target CI/CD platform
            deployment_guidance: Optional deployment guidance

        Returns:
            CI/CD configuration content
        """
        if platform == CICDPlatform.GITHUB_ACTIONS:
            return self._github_generator.generate(tech_stack)
        elif platform == CICDPlatform.GITLAB_CI:
            return self._gitlab_generator.generate(tech_stack, deployment_guidance)
        elif platform == CICDPlatform.JENKINS:
            return self._jenkins_generator.generate(tech_stack, deployment_guidance)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    def _detect_language(self, combined: str) -> str:
        """Detect programming language from stack info."""
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
            "rust": "rust",
            "go": "go",
            "golang": "go",
            "ruby": "ruby",
            "rails": "ruby",
            "php": "php",
            "laravel": "php",
        }

        for tech, lang in language_mapping.items():
            if tech in combined:
                return lang

        return "node"

    def _get_default_version(self, language: str) -> str:
        """Get default version for language."""
        versions = {
            "node": "20",
            "python": "3.11",
            "rust": "stable",
            "go": "1.21",
            "ruby": "3.2",
            "php": "8.2",
        }
        return versions.get(language, "latest")

    def _detect_build_tool(self, language: str, tech_stack: Dict[str, Any]) -> str:
        """Detect build tool for language."""
        build_tools = {
            "node": "npm",
            "python": "pip",
            "rust": "cargo",
            "go": "go",
            "ruby": "bundler",
            "php": "composer",
        }
        return tech_stack.get("build_tool") or build_tools.get(language, "make")

    def _detect_test_framework(self, language: str, tech_stack: Dict[str, Any]) -> Optional[str]:
        """Detect test framework for language."""
        frameworks = {
            "node": "jest",
            "python": "pytest",
            "rust": "cargo test",
            "go": "go test",
            "ruby": "rspec",
            "php": "phpunit",
        }
        return tech_stack.get("test_framework") or frameworks.get(language)

    def _detect_lint_tool(self, language: str) -> Optional[str]:
        """Detect lint tool for language."""
        lint_tools = {
            "node": "eslint",
            "python": "ruff",
            "rust": "clippy",
            "go": "golangci-lint",
            "ruby": "rubocop",
            "php": "phpcs",
        }
        return lint_tools.get(language)

    def _detect_package_manager(self, language: str, tech_stack: Dict[str, Any]) -> str:
        """Detect package manager for language."""
        package_managers = {
            "node": "npm",
            "python": "pip",
            "rust": "cargo",
            "go": "go mod",
            "ruby": "bundler",
            "php": "composer",
        }
        return tech_stack.get("package_manager") or package_managers.get(language, "unknown")

    def _extract_deployment_guidance(
        self, tech_stack: Dict[str, Any]
    ) -> Optional[DeploymentGuidance]:
        """Extract deployment guidance from tech stack."""
        deploy_provider = tech_stack.get("deploy_provider", "").lower()

        if not deploy_provider:
            return None

        target_mapping = {
            "vercel": DeploymentTarget.VERCEL,
            "netlify": DeploymentTarget.NETLIFY,
            "docker": DeploymentTarget.DOCKER,
            "kubernetes": DeploymentTarget.KUBERNETES,
            "k8s": DeploymentTarget.KUBERNETES,
            "aws_ecs": DeploymentTarget.AWS_ECS,
            "ecs": DeploymentTarget.AWS_ECS,
            "aws_lambda": DeploymentTarget.AWS_LAMBDA,
            "lambda": DeploymentTarget.AWS_LAMBDA,
            "heroku": DeploymentTarget.HEROKU,
            "railway": DeploymentTarget.RAILWAY,
            "fly": DeploymentTarget.FLY_IO,
            "fly.io": DeploymentTarget.FLY_IO,
        }

        target = target_mapping.get(deploy_provider, DeploymentTarget.GENERIC)

        return DeploymentGuidance(
            target=target,
            containerized=target in [DeploymentTarget.DOCKER, DeploymentTarget.KUBERNETES],
            environment_vars=tech_stack.get("env_vars", {}),
        )

    def _recommend_platform(self, tech_stack: Dict[str, Any]) -> CICDPlatform:
        """Recommend CI/CD platform based on tech stack."""
        # Default to GitHub Actions as most common
        return CICDPlatform.GITHUB_ACTIONS

    def _get_artifact_paths(self, language: str) -> List[str]:
        """Get artifact paths for language."""
        paths = {
            "node": ["dist/", ".next/", "build/"],
            "python": ["dist/"],
            "rust": ["target/release/"],
            "go": ["bin/"],
            "ruby": ["pkg/"],
            "php": ["vendor/"],
        }
        return paths.get(language, ["dist/"])

    def _get_cache_paths(self, language: str) -> List[str]:
        """Get cache paths for language."""
        paths = {
            "node": ["node_modules/", ".npm/"],
            "python": [".cache/pip/", ".venv/"],
            "rust": ["target/", ".cargo/"],
            "go": ["~/go/pkg/mod/"],
            "ruby": ["vendor/bundle/"],
            "php": ["vendor/"],
        }
        return paths.get(language, [])
