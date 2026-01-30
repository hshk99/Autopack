"""CI/CD Workflow Generator for research projects.

Generates GitHub Actions workflows based on TechStackProposal.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


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
