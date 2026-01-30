"""CI/CD Pipeline Generation for Deployment Phase.

Generates CI/CD pipeline configurations for multiple platforms (GitHub Actions, GitLab CI, etc.)
as part of the deployment phase execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CICDConfig:
    """Configuration for CI/CD pipeline generation."""

    provider: str  # github_actions, gitlab_ci, generic
    default_branch: str = "main"
    include_build: bool = True
    include_test: bool = True
    include_security_scan: bool = True
    include_deploy: bool = True
    language: Optional[str] = None
    deployment_targets: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None


class CICDPipelineGenerator:
    """Generates CI/CD pipeline configurations for deployment phase.

    Supports multiple CI/CD platforms including GitHub Actions, GitLab CI, and
    generic pipeline configurations. Each generator produces configuration files
    suitable for the target platform.
    """

    # Language detection mappings
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

    # Default language versions
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

    # Language-specific Docker setup steps for GitHub Actions
    _SETUP_STEPS: Dict[str, Dict[str, Any]] = {
        "node": {
            "uses": "actions/setup-node@v4",
            "with": {"node-version": "${{ matrix.node-version }}"},
        },
        "python": {
            "uses": "actions/setup-python@v4",
            "with": {"python-version": "${{ matrix.python-version }}"},
        },
        "rust": {
            "uses": "actions-rs/toolchain@v1",
            "with": {"toolchain": "stable"},
        },
        "go": {
            "uses": "actions/setup-go@v4",
            "with": {"go-version": "${{ matrix.go-version }}"},
        },
    }

    # Cache steps for CI optimization
    _CACHE_STEPS: Dict[str, Dict[str, Any]] = {
        "node": {
            "uses": "actions/cache@v3",
            "with": {
                "path": "~/.npm",
                "key": "${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}",
                "restore-keys": "${{ runner.os }}-node-",
            },
        },
        "python": {
            "uses": "actions/cache@v3",
            "with": {
                "path": "~/.cache/pip",
                "key": "${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}",
                "restore-keys": "${{ runner.os }}-pip-",
            },
        },
        "go": {
            "uses": "actions/cache@v3",
            "with": {
                "path": "~/go/pkg/mod",
                "key": "${{ runner.os }}-go-${{ hashFiles('**/go.sum') }}",
                "restore-keys": "${{ runner.os }}-go-",
            },
        },
    }

    def __init__(
        self,
        provider: str = "github_actions",
        default_branch: str = "main",
        include_build: bool = True,
        include_test: bool = True,
        include_security_scan: bool = True,
        include_deploy: bool = True,
    ):
        """Initialize CI/CD pipeline generator.

        Args:
            provider: CI/CD platform (github_actions, gitlab_ci, generic)
            default_branch: Default branch to trigger workflows
            include_build: Include build job in pipeline
            include_test: Include test job in pipeline
            include_security_scan: Include security scanning
            include_deploy: Include deployment job
        """
        self.provider = provider
        self.default_branch = default_branch
        self.include_build = include_build
        self.include_test = include_test
        self.include_security_scan = include_security_scan
        self.include_deploy = include_deploy

    def generate_github_actions(self, tech_stack: Optional[Dict[str, Any]] = None) -> str:
        """Generate GitHub Actions workflow YAML.

        Args:
            tech_stack: Technology stack configuration with keys:
                - name: Stack name
                - language: Programming language (auto-detected if missing)
                - test_command: Custom test command
                - build_command: Custom build command
                - deploy_provider: Deployment target

        Returns:
            Valid GitHub Actions workflow.yaml content
        """
        logger.info("[CICDPipelineGenerator] Generating GitHub Actions workflow")

        tech_stack = tech_stack or {}
        stack_name = tech_stack.get("name", "Project")
        language = tech_stack.get("language") or self._detect_language(
            tech_stack.get("name", ""),
            tech_stack.get("category", ""),
        )
        version = tech_stack.get("version") or self._DEFAULT_VERSIONS.get(language, "latest")

        workflow = self._build_github_workflow(
            stack_name=stack_name,
            language=language,
            version=version,
            tech_stack=tech_stack,
        )

        # Generate YAML
        yaml_output = yaml.dump(
            workflow,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        return yaml_output

    def generate_gitlab_ci(self, tech_stack: Optional[Dict[str, Any]] = None) -> str:
        """Generate GitLab CI configuration YAML.

        Args:
            tech_stack: Technology stack configuration

        Returns:
            Valid .gitlab-ci.yml content
        """
        logger.info("[CICDPipelineGenerator] Generating GitLab CI configuration")

        tech_stack = tech_stack or {}
        language = tech_stack.get("language") or self._detect_language(
            tech_stack.get("name", ""),
            tech_stack.get("category", ""),
        )

        config = self._build_gitlab_ci_config(language, tech_stack)

        # Generate YAML
        yaml_output = yaml.dump(
            config,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        return yaml_output

    def generate_generic_ci(self, tech_stack: Optional[Dict[str, Any]] = None) -> str:
        """Generate generic CI/CD pipeline as YAML (provider-agnostic).

        Args:
            tech_stack: Technology stack configuration

        Returns:
            Generic pipeline configuration as YAML
        """
        logger.info("[CICDPipelineGenerator] Generating generic CI/CD pipeline")

        tech_stack = tech_stack or {}
        language = tech_stack.get("language") or self._detect_language(
            tech_stack.get("name", ""),
            tech_stack.get("category", ""),
        )

        pipeline = self._build_generic_pipeline(language, tech_stack)

        # Generate YAML
        yaml_output = yaml.dump(
            pipeline,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

        return yaml_output

    def _detect_language(self, stack_name: str, category: str) -> str:
        """Detect primary language from stack name or category.

        Args:
            stack_name: Name of technology stack
            category: Category of stack

        Returns:
            Detected language (defaults to "node")
        """
        combined = f"{stack_name} {category}".lower()

        for tech, lang in self._LANGUAGE_MAPPING.items():
            if tech.lower() in combined:
                return lang

        return "node"

    def _build_github_workflow(
        self,
        stack_name: str,
        language: str,
        version: str,
        tech_stack: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build GitHub Actions workflow structure.

        Args:
            stack_name: Name of technology stack
            language: Programming language
            version: Language version
            tech_stack: Technology stack configuration

        Returns:
            GitHub Actions workflow configuration
        """
        workflow: Dict[str, Any] = {
            "name": f"CI/CD - {stack_name}",
            "on": {
                "push": {"branches": [self.default_branch]},
                "pull_request": {"branches": [self.default_branch]},
            },
            "env": {
                "CI": "true",
                **(tech_stack.get("env_vars", {}) or {}),
            },
            "jobs": {},
        }

        # Add test job
        if self.include_test:
            workflow["jobs"]["test"] = self._build_test_job(
                language=language,
                version=version,
                tech_stack=tech_stack,
            )

        # Add security scan job
        if self.include_security_scan:
            workflow["jobs"]["security"] = self._build_security_job(language)

        # Add build job
        if self.include_build:
            workflow["jobs"]["build"] = self._build_build_job(
                language=language,
                version=version,
                tech_stack=tech_stack,
            )

        # Add deploy job
        if self.include_deploy:
            deploy_job = self._build_deploy_job(tech_stack)
            if deploy_job:
                workflow["jobs"]["deploy"] = deploy_job

        return workflow

    def _build_gitlab_ci_config(self, language: str, tech_stack: Dict[str, Any]) -> Dict[str, Any]:
        """Build GitLab CI configuration.

        Args:
            language: Programming language
            tech_stack: Technology stack configuration

        Returns:
            GitLab CI configuration
        """
        config: Dict[str, Any] = {
            "stages": ["lint", "test", "build", "deploy"],
            "variables": {
                "CI": "true",
                **(tech_stack.get("env_vars", {}) or {}),
            },
        }

        # Test stage
        if self.include_test:
            test_commands = self._TEST_COMMANDS.get(language, ["echo 'No tests configured'"])
            config["test:script"] = {
                "stage": "test",
                "image": f"{language}:{self._DEFAULT_VERSIONS.get(language, 'latest')}",
                "script": test_commands,
            }

        # Build stage
        if self.include_build:
            build_commands = self._BUILD_COMMANDS.get(language, ["echo 'No build configured'"])
            config["build:artifacts"] = {
                "stage": "build",
                "image": f"{language}:{self._DEFAULT_VERSIONS.get(language, 'latest')}",
                "script": build_commands,
                "artifacts": {
                    "paths": ["dist/", "build/"],
                    "expire_in": "30 days",
                },
            }

        # Deploy stage (basic)
        if self.include_deploy:
            config["deploy:production"] = {
                "stage": "deploy",
                "script": ["echo 'Deploy to production'"],
                "only": [self.default_branch],
                "when": "manual",
            }

        return config

    def _build_generic_pipeline(self, language: str, tech_stack: Dict[str, Any]) -> Dict[str, Any]:
        """Build generic CI/CD pipeline configuration.

        Args:
            language: Programming language
            tech_stack: Technology stack configuration

        Returns:
            Generic pipeline configuration
        """
        pipeline: Dict[str, Any] = {
            "name": "Generic CI/CD Pipeline",
            "description": "Provider-agnostic CI/CD pipeline configuration",
            "stages": ["lint", "test", "build", "deploy"],
            "version": "1.0",
            "language": language,
            "default_branch": self.default_branch,
            "jobs": {},
            "variables": tech_stack.get("env_vars", {}),
        }

        # Test job
        if self.include_test:
            pipeline["jobs"]["test"] = {
                "name": "Test Suite",
                "stage": "test",
                "commands": self._TEST_COMMANDS.get(language, ["echo 'No tests configured'"]),
            }

        # Build job
        if self.include_build:
            pipeline["jobs"]["build"] = {
                "name": "Build",
                "stage": "build",
                "commands": self._BUILD_COMMANDS.get(language, ["echo 'No build configured'"]),
                "artifacts": ["dist/", "build/"],
            }

        # Security scan job
        if self.include_security_scan:
            pipeline["jobs"]["security"] = {
                "name": "Security Scan",
                "stage": "test",
                "commands": self._get_security_commands(language),
            }

        # Deploy job
        if self.include_deploy:
            pipeline["jobs"]["deploy"] = {
                "name": "Deploy",
                "stage": "deploy",
                "commands": ["echo 'Deploy to production'"],
                "only_branches": [self.default_branch],
                "requires_approval": True,
            }

        return pipeline

    def _build_test_job(
        self, language: str, version: str, tech_stack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build GitHub Actions test job.

        Args:
            language: Programming language
            version: Language version
            tech_stack: Technology stack configuration

        Returns:
            Test job configuration
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add setup step
        setup_step = self._SETUP_STEPS.get(language)
        if setup_step:
            job["steps"].append(
                {
                    "name": f"Set up {language}",
                    **setup_step,
                }
            )

        # Add cache step
        cache_step = self._CACHE_STEPS.get(language)
        if cache_step:
            job["steps"].append(
                {
                    "name": f"Cache {language} dependencies",
                    **cache_step,
                }
            )

        # Add test commands
        test_commands = tech_stack.get("test_command")
        if test_commands:
            test_commands = [test_commands]
        else:
            test_commands = self._TEST_COMMANDS.get(language, ["echo 'No tests configured'"])

        for cmd in test_commands:
            job["steps"].append(
                {
                    "name": f"Run: {cmd[:50]}",
                    "run": cmd,
                }
            )

        return job

    def _build_security_job(self, language: str) -> Dict[str, Any]:
        """Build GitHub Actions security scanning job.

        Args:
            language: Programming language

        Returns:
            Security job configuration
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add CodeQL for supported languages
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
                        "name": "Perform CodeQL Analysis",
                        "uses": "github/codeql-action/analyze@v3",
                    },
                ]
            )

        # Add Dependabot if available
        job["steps"].append(
            {
                "name": "Check Dependencies",
                "run": "echo 'Run dependency checker for ' + '${{ matrix.language }}'",
            }
        )

        return job

    def _build_build_job(
        self, language: str, version: str, tech_stack: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build GitHub Actions build job.

        Args:
            language: Programming language
            version: Language version
            tech_stack: Technology stack configuration

        Returns:
            Build job configuration
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "needs": "test",
            "steps": [
                {"uses": "actions/checkout@v4"},
            ],
        }

        # Add setup step
        setup_step = self._SETUP_STEPS.get(language)
        if setup_step:
            job["steps"].append(
                {
                    "name": f"Set up {language}",
                    **setup_step,
                }
            )

        # Add build commands
        build_commands = tech_stack.get("build_command")
        if build_commands:
            build_commands = [build_commands]
        else:
            build_commands = self._BUILD_COMMANDS.get(language, ["echo 'No build configured'"])

        for cmd in build_commands:
            job["steps"].append(
                {
                    "name": f"Run: {cmd[:50]}",
                    "run": cmd,
                }
            )

        # Upload artifacts
        job["steps"].append(
            {
                "name": "Upload build artifacts",
                "uses": "actions/upload-artifact@v4",
                "with": {
                    "name": "build-artifacts",
                    "path": "dist/",
                    "retention-days": 5,
                },
            }
        )

        return job

    def _build_deploy_job(self, tech_stack: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build GitHub Actions deployment job.

        Args:
            tech_stack: Technology stack configuration

        Returns:
            Deployment job configuration or None
        """
        job: Dict[str, Any] = {
            "runs-on": "ubuntu-latest",
            "needs": "build",
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

        # Add provider-specific deployment
        deploy_provider = tech_stack.get("deploy_provider", "").lower()

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
                    "uses": "nwtgck/actions-netlify@v2.0",
                    "with": {
                        "publish-dir": "./dist",
                        "production-branch": self.default_branch,
                        "github-token": "${{ secrets.GITHUB_TOKEN }}",
                        "deploy-message": "Deployed from GitHub Actions",
                        "enable-pull-request-comment": True,
                        "enable-commit-comment": True,
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
                        "name": "Login to Docker Hub",
                        "uses": "docker/login-action@v3",
                        "with": {
                            "username": "${{ secrets.DOCKER_USERNAME }}",
                            "password": "${{ secrets.DOCKER_PASSWORD }}",
                        },
                    },
                    {
                        "name": "Build and push Docker image",
                        "uses": "docker/build-push-action@v5",
                        "with": {
                            "context": ".",
                            "push": True,
                            "tags": "${{ secrets.DOCKER_USERNAME }}/project:${{ github.sha }}",
                        },
                    },
                ]
            )
        else:
            job["steps"].append(
                {
                    "name": "Deploy",
                    "run": "echo 'Configure deployment for your platform'",
                }
            )

        return job

    def _get_security_commands(self, language: str) -> List[str]:
        """Get security scanning commands for language.

        Args:
            language: Programming language

        Returns:
            List of security scanning commands
        """
        commands: Dict[str, List[str]] = {
            "node": [
                "npm install -g snyk",
                "snyk test --severity-threshold=high || true",
            ],
            "python": [
                "pip install bandit safety",
                "bandit -r . -ll || true",
                "safety check || true",
            ],
            "rust": [
                "cargo install cargo-audit",
                "cargo audit --deny warnings || true",
            ],
            "go": [
                "go install github.com/securego/gosec/v2/cmd/gosec@latest",
                "gosec ./... || true",
            ],
        }

        return commands.get(language, ["echo 'No security scanning configured'"])
