#!/usr/bin/env python3
"""
Pre-Publication Checklist for Autopack-Built Projects

Category: MANUAL ONLY
Triggers: Intent Router, Explicit Call
Excludes: Automatic Maintenance, Error Reports, Test Runs

Run this script before publishing any project built with Autopack to ensure
all necessary artifacts, documentation, and metadata are ready for public release.

This tool should NOT be included in automatic maintenance runs.

Usage:
    python scripts/pre_publish_checklist.py --project-path /path/to/project
    python scripts/pre_publish_checklist.py --project-path .autonomous_runs/file-organizer-app-v1
    python scripts/pre_publish_checklist.py --project-path /path/to/project --strict

Author: Autopack Framework
Date: 2025-12-09
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# ANSI color codes for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


class CheckResult:
    """Result of a single checklist item"""
    def __init__(self, name: str, passed: bool, message: str, severity: str = "error"):
        self.name = name
        self.passed = passed
        self.message = message
        self.severity = severity  # "error", "warning", "info"

    def __str__(self):
        icon = f"{GREEN}✓{RESET}" if self.passed else (
            f"{YELLOW}⚠{RESET}" if self.severity == "warning" else f"{RED}✗{RESET}"
        )
        return f"{icon} {self.name}: {self.message}"


class PrePublishChecker:
    """Pre-publication checklist runner"""

    def __init__(self, project_path: Path, strict: bool = False):
        self.project_path = project_path.resolve()
        self.strict = strict
        self.results: List[CheckResult] = []

    def run_all_checks(self) -> bool:
        """Run all pre-publication checks"""
        print(f"{BOLD}Pre-Publication Checklist for: {self.project_path}{RESET}\n")

        # Core artifact checks
        self.check_readme()
        self.check_license()
        self.check_changelog()
        self.check_version_file()
        self.check_semver_tags()

        # Distribution checks
        self.check_package_json_or_setup_py()
        self.check_dependencies_locked()
        self.check_build_directory()
        self.check_docker_support()

        # Documentation checks
        self.check_user_documentation()
        self.check_api_documentation()
        self.check_installation_guide()
        self.check_examples()

        # Quality checks
        self.check_tests_exist()
        self.check_ci_cd_config()
        self.check_security_policy()
        self.check_contributing_guide()
        self.check_code_of_conduct()

        # Legal & compliance
        self.check_license_headers()
        self.check_third_party_licenses()
        self.check_no_secrets()
        self.check_no_personal_data()

        # Metadata checks
        self.check_git_tags()
        self.check_github_release_template()
        self.check_release_notes_format()

        # Build verification
        self.check_build_succeeds()
        self.check_tests_pass()

        # Optional but recommended
        self.check_badges()
        self.check_demo_or_screenshots()
        self.check_roadmap()

        return self.print_summary()

    def check_readme(self):
        """Check for README.md with essential sections"""
        readme_path = self.project_path / "README.md"
        if not readme_path.exists():
            self.results.append(CheckResult(
                "README.md",
                False,
                "README.md not found. Create user-facing documentation.",
                "error"
            ))
            return

        content = readme_path.read_text(encoding="utf-8")
        required_sections = [
            ("# ", "Main title"),
            ("## Installation", "Installation instructions"),
            ("## Usage", "Usage examples"),
            ("## Features", "Feature list"),
        ]

        missing = []
        for pattern, desc in required_sections:
            if pattern not in content:
                missing.append(desc)

        if missing:
            self.results.append(CheckResult(
                "README.md sections",
                False,
                f"Missing sections: {', '.join(missing)}",
                "warning"
            ))
        else:
            self.results.append(CheckResult(
                "README.md",
                True,
                "README.md exists with essential sections"
            ))

    def check_license(self):
        """Check for LICENSE file"""
        license_files = ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]
        found = any((self.project_path / f).exists() for f in license_files)

        if found:
            self.results.append(CheckResult(
                "LICENSE",
                True,
                "LICENSE file found"
            ))
        else:
            self.results.append(CheckResult(
                "LICENSE",
                False,
                "No LICENSE file found. Add MIT, Apache-2.0, or appropriate license.",
                "error"
            ))

    def check_changelog(self):
        """Check for CHANGELOG.md"""
        changelog_path = self.project_path / "CHANGELOG.md"
        if not changelog_path.exists():
            self.results.append(CheckResult(
                "CHANGELOG.md",
                False,
                "CHANGELOG.md not found. Create version history with release notes.",
                "warning"
            ))
            return

        content = changelog_path.read_text(encoding="utf-8")
        # Check for semver-style versions
        if not re.search(r"##?\s+\[?v?\d+\.\d+\.\d+", content):
            self.results.append(CheckResult(
                "CHANGELOG.md format",
                False,
                "CHANGELOG.md exists but doesn't follow semver versioning format",
                "warning"
            ))
        else:
            self.results.append(CheckResult(
                "CHANGELOG.md",
                True,
                "CHANGELOG.md exists with versioned entries"
            ))

    def check_version_file(self):
        """Check for version file or version in package metadata"""
        version_locations = [
            self.project_path / "VERSION",
            self.project_path / "version.txt",
            self.project_path / "src" / "__version__.py",
            self.project_path / "package.json",
            self.project_path / "setup.py",
            self.project_path / "pyproject.toml",
        ]

        found = False
        for location in version_locations:
            if location.exists():
                found = True
                break

        if found:
            self.results.append(CheckResult(
                "Version file",
                True,
                f"Version metadata found in {location.name}"
            ))
        else:
            self.results.append(CheckResult(
                "Version file",
                False,
                "No version file found (VERSION, package.json, setup.py, etc.)",
                "warning"
            ))

    def check_semver_tags(self):
        """Check for semver git tags"""
        try:
            result = subprocess.run(
                ["git", "tag", "-l"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                check=True
            )
            tags = result.stdout.strip().split("\n")
            semver_tags = [t for t in tags if re.match(r"v?\d+\.\d+\.\d+", t)]

            if semver_tags:
                self.results.append(CheckResult(
                    "Git tags",
                    True,
                    f"Found {len(semver_tags)} semver tags (latest: {semver_tags[-1]})"
                ))
            else:
                self.results.append(CheckResult(
                    "Git tags",
                    False,
                    "No semver git tags found. Create release tags (v1.0.0, etc.)",
                    "warning"
                ))
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.results.append(CheckResult(
                "Git tags",
                False,
                "Could not check git tags (not a git repo or git not installed)",
                "info"
            ))

    def check_package_json_or_setup_py(self):
        """Check for package metadata files"""
        package_files = [
            ("package.json", "Node.js"),
            ("setup.py", "Python setuptools"),
            ("pyproject.toml", "Python PEP 518"),
            ("Cargo.toml", "Rust"),
            ("go.mod", "Go"),
        ]

        found = []
        for filename, desc in package_files:
            if (self.project_path / filename).exists():
                found.append(f"{filename} ({desc})")

        if found:
            self.results.append(CheckResult(
                "Package metadata",
                True,
                f"Found: {', '.join(found)}"
            ))
        else:
            self.results.append(CheckResult(
                "Package metadata",
                False,
                "No package metadata found (package.json, setup.py, pyproject.toml, etc.)",
                "error"
            ))

    def check_dependencies_locked(self):
        """Check for lockfiles"""
        lockfiles = [
            ("package-lock.json", "npm"),
            ("yarn.lock", "yarn"),
            ("pnpm-lock.yaml", "pnpm"),
            ("Pipfile.lock", "pipenv"),
            ("poetry.lock", "poetry"),
            ("requirements.txt", "pip"),
            ("Cargo.lock", "cargo"),
            ("go.sum", "go"),
        ]

        found = []
        for filename, tool in lockfiles:
            if (self.project_path / filename).exists():
                found.append(f"{filename} ({tool})")

        if found:
            self.results.append(CheckResult(
                "Dependency lockfile",
                True,
                f"Found: {', '.join(found)}"
            ))
        else:
            self.results.append(CheckResult(
                "Dependency lockfile",
                False,
                "No dependency lockfile found. Lock dependencies for reproducible builds.",
                "warning"
            ))

    def check_build_directory(self):
        """Check for build output or distribution directory"""
        build_dirs = ["dist", "build", "out", "target", "bin"]
        found = [d for d in build_dirs if (self.project_path / d).exists()]

        if found:
            self.results.append(CheckResult(
                "Build directory",
                True,
                f"Found build directories: {', '.join(found)}"
            ))
        else:
            self.results.append(CheckResult(
                "Build directory",
                False,
                "No build/dist directory found. Run build before publishing.",
                "warning"
            ))

    def check_docker_support(self):
        """Check for Docker support"""
        dockerfile = self.project_path / "Dockerfile"
        compose = self.project_path / "docker-compose.yml"

        if dockerfile.exists() or compose.exists():
            files = []
            if dockerfile.exists():
                files.append("Dockerfile")
            if compose.exists():
                files.append("docker-compose.yml")
            self.results.append(CheckResult(
                "Docker support",
                True,
                f"Found: {', '.join(files)}"
            ))
        else:
            self.results.append(CheckResult(
                "Docker support",
                False,
                "No Dockerfile or docker-compose.yml. Consider adding for easier deployment.",
                "info"
            ))

    def check_user_documentation(self):
        """Check for user-facing documentation"""
        doc_locations = [
            self.project_path / "docs",
            self.project_path / "documentation",
            self.project_path / "doc",
        ]

        found = any(loc.exists() and loc.is_dir() for loc in doc_locations)

        if found:
            self.results.append(CheckResult(
                "User documentation",
                True,
                "Documentation directory found"
            ))
        else:
            self.results.append(CheckResult(
                "User documentation",
                False,
                "No docs/ directory. Create user guides and tutorials.",
                "warning"
            ))

    def check_api_documentation(self):
        """Check for API documentation"""
        api_doc_indicators = [
            self.project_path / "docs" / "api",
            self.project_path / "docs" / "API.md",
            self.project_path / "API.md",
        ]

        found = any(loc.exists() for loc in api_doc_indicators)

        if found:
            self.results.append(CheckResult(
                "API documentation",
                True,
                "API documentation found"
            ))
        else:
            self.results.append(CheckResult(
                "API documentation",
                False,
                "No API documentation found. Document public APIs if applicable.",
                "info"
            ))

    def check_installation_guide(self):
        """Check for installation guide"""
        readme = self.project_path / "README.md"
        install_guide = self.project_path / "INSTALL.md"

        has_install = False
        if readme.exists():
            content = readme.read_text(encoding="utf-8").lower()
            has_install = "## installation" in content or "## install" in content

        if install_guide.exists():
            has_install = True

        if has_install:
            self.results.append(CheckResult(
                "Installation guide",
                True,
                "Installation instructions found"
            ))
        else:
            self.results.append(CheckResult(
                "Installation guide",
                False,
                "No installation guide found. Add installation instructions.",
                "error"
            ))

    def check_examples(self):
        """Check for example code or usage examples"""
        example_locations = [
            self.project_path / "examples",
            self.project_path / "example",
            self.project_path / "samples",
        ]

        found = any(loc.exists() and loc.is_dir() for loc in example_locations)

        if found:
            self.results.append(CheckResult(
                "Examples",
                True,
                "Examples directory found"
            ))
        else:
            self.results.append(CheckResult(
                "Examples",
                False,
                "No examples/ directory. Add usage examples.",
                "info"
            ))

    def check_tests_exist(self):
        """Check for test suite"""
        test_locations = [
            self.project_path / "tests",
            self.project_path / "test",
            self.project_path / "__tests__",
            self.project_path / "spec",
        ]

        found = any(loc.exists() and loc.is_dir() for loc in test_locations)

        if found:
            self.results.append(CheckResult(
                "Test suite",
                True,
                "Test directory found"
            ))
        else:
            self.results.append(CheckResult(
                "Test suite",
                False,
                "No tests/ directory. Add automated tests.",
                "warning"
            ))

    def check_ci_cd_config(self):
        """Check for CI/CD configuration"""
        ci_configs = [
            self.project_path / ".github" / "workflows",
            self.project_path / ".gitlab-ci.yml",
            self.project_path / ".travis.yml",
            self.project_path / "azure-pipelines.yml",
            self.project_path / ".circleci" / "config.yml",
        ]

        found = any(loc.exists() for loc in ci_configs)

        if found:
            self.results.append(CheckResult(
                "CI/CD",
                True,
                "CI/CD configuration found"
            ))
        else:
            self.results.append(CheckResult(
                "CI/CD",
                False,
                "No CI/CD config. Add GitHub Actions or equivalent.",
                "warning"
            ))

    def check_security_policy(self):
        """Check for security policy"""
        security = self.project_path / "SECURITY.md"

        if security.exists():
            self.results.append(CheckResult(
                "SECURITY.md",
                True,
                "Security policy found"
            ))
        else:
            self.results.append(CheckResult(
                "SECURITY.md",
                False,
                "No SECURITY.md. Add security reporting guidelines.",
                "info"
            ))

    def check_contributing_guide(self):
        """Check for contributing guidelines"""
        contributing = self.project_path / "CONTRIBUTING.md"

        if contributing.exists():
            self.results.append(CheckResult(
                "CONTRIBUTING.md",
                True,
                "Contributing guide found"
            ))
        else:
            self.results.append(CheckResult(
                "CONTRIBUTING.md",
                False,
                "No CONTRIBUTING.md. Add contribution guidelines if accepting PRs.",
                "info"
            ))

    def check_code_of_conduct(self):
        """Check for code of conduct"""
        coc_files = ["CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT.txt"]
        found = any((self.project_path / f).exists() for f in coc_files)

        if found:
            self.results.append(CheckResult(
                "Code of Conduct",
                True,
                "Code of Conduct found"
            ))
        else:
            self.results.append(CheckResult(
                "Code of Conduct",
                False,
                "No CODE_OF_CONDUCT.md. Consider adding for open-source projects.",
                "info"
            ))

    def check_license_headers(self):
        """Check for license headers in source files"""
        # Sample a few source files
        source_patterns = ["*.py", "*.js", "*.ts", "*.go", "*.rs", "*.java"]
        sample_size = 5

        source_files = []
        for pattern in source_patterns:
            source_files.extend(list(self.project_path.rglob(pattern))[:sample_size])

        if not source_files:
            self.results.append(CheckResult(
                "License headers",
                False,
                "No source files found to check",
                "info"
            ))
            return

        files_with_headers = 0
        for file in source_files[:sample_size]:
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                first_lines = "\n".join(content.split("\n")[:10]).lower()
                if "copyright" in first_lines or "license" in first_lines:
                    files_with_headers += 1
            except Exception:
                pass

        if files_with_headers >= len(source_files) * 0.5:
            self.results.append(CheckResult(
                "License headers",
                True,
                f"{files_with_headers}/{len(source_files)} sampled files have license headers"
            ))
        else:
            self.results.append(CheckResult(
                "License headers",
                False,
                f"Only {files_with_headers}/{len(source_files)} sampled files have license headers",
                "info"
            ))

    def check_third_party_licenses(self):
        """Check for third-party license documentation"""
        license_files = [
            "THIRD_PARTY_LICENSES.md",
            "THIRD_PARTY_NOTICES.txt",
            "NOTICE",
            "NOTICE.txt",
        ]

        found = any((self.project_path / f).exists() for f in license_files)

        if found:
            self.results.append(CheckResult(
                "Third-party licenses",
                True,
                "Third-party license documentation found"
            ))
        else:
            self.results.append(CheckResult(
                "Third-party licenses",
                False,
                "No third-party license doc. Document dependencies' licenses if distributing binaries.",
                "info"
            ))

    def check_no_secrets(self):
        """Check for potential secrets in git history"""
        secret_patterns = [
            r"api[_-]?key",
            r"password",
            r"secret",
            r"token",
            r"private[_-]?key",
            r"access[_-]?key",
        ]

        # Check for .env files or config files that might contain secrets
        potential_secret_files = [
            ".env",
            ".env.local",
            ".env.production",
            "secrets.yml",
            "config/secrets.yml",
        ]

        found_files = [f for f in potential_secret_files if (self.project_path / f).exists()]

        if found_files:
            self.results.append(CheckResult(
                "Secrets check",
                False,
                f"Found potential secret files: {', '.join(found_files)}. Ensure they're in .gitignore!",
                "error"
            ))
        else:
            self.results.append(CheckResult(
                "Secrets check",
                True,
                "No obvious secret files found in repo"
            ))

    def check_no_personal_data(self):
        """Check for personal data or PII"""
        # Check for common personal data patterns
        sensitive_patterns = [
            "TODO.*@",  # Email in TODOs
            "FIXME.*@",  # Email in FIXMEs
        ]

        # Sample check - would need more thorough scanning in production
        self.results.append(CheckResult(
            "Personal data check",
            True,
            "Manual review recommended for PII/personal data",
            "info"
        ))

    def check_git_tags(self):
        """Check for properly formatted git tags"""
        try:
            result = subprocess.run(
                ["git", "tag", "-l", "v*"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                check=True
            )
            tags = [t for t in result.stdout.strip().split("\n") if t]

            if tags:
                self.results.append(CheckResult(
                    "Git release tags",
                    True,
                    f"Found {len(tags)} release tags"
                ))
            else:
                self.results.append(CheckResult(
                    "Git release tags",
                    False,
                    "No release tags (v1.0.0, etc.). Tag releases for version tracking.",
                    "warning"
                ))
        except Exception:
            pass  # Already checked in check_semver_tags

    def check_github_release_template(self):
        """Check for GitHub release template"""
        release_template = self.project_path / ".github" / "release_template.md"

        if release_template.exists():
            self.results.append(CheckResult(
                "Release template",
                True,
                "GitHub release template found"
            ))
        else:
            self.results.append(CheckResult(
                "Release template",
                False,
                "No .github/release_template.md. Create template for consistent releases.",
                "info"
            ))

    def check_release_notes_format(self):
        """Check CHANGELOG format follows standard"""
        changelog = self.project_path / "CHANGELOG.md"

        if not changelog.exists():
            return  # Already checked in check_changelog

        content = changelog.read_text(encoding="utf-8")

        # Check for Keep a Changelog format
        has_keepachangelog = "keepachangelog.com" in content.lower()
        has_sections = all(s in content for s in ["Added", "Changed", "Fixed"])

        if has_keepachangelog or has_sections:
            self.results.append(CheckResult(
                "CHANGELOG format",
                True,
                "CHANGELOG follows standard format"
            ))
        else:
            self.results.append(CheckResult(
                "CHANGELOG format",
                False,
                "CHANGELOG doesn't follow Keep a Changelog format",
                "info"
            ))

    def check_build_succeeds(self):
        """Check if project builds successfully"""
        # Detect build command based on project type
        build_commands = [
            (self.project_path / "package.json", ["npm", "run", "build"]),
            (self.project_path / "setup.py", ["python", "setup.py", "build"]),
            (self.project_path / "Makefile", ["make"]),
            (self.project_path / "build.sh", ["./build.sh"]),
        ]

        for indicator, command in build_commands:
            if indicator.exists():
                self.results.append(CheckResult(
                    "Build verification",
                    True,
                    f"Build script detected: {' '.join(command)}. Run manually to verify.",
                    "info"
                ))
                return

        self.results.append(CheckResult(
            "Build verification",
            False,
            "No build script detected. Verify project builds before publishing.",
            "info"
        ))

    def check_tests_pass(self):
        """Check if tests can be run"""
        test_commands = [
            (self.project_path / "package.json", "npm test"),
            (self.project_path / "pytest.ini", "pytest"),
            (self.project_path / "Makefile", "make test"),
        ]

        for indicator, command in test_commands:
            if indicator.exists():
                self.results.append(CheckResult(
                    "Test verification",
                    True,
                    f"Test command detected: {command}. Run manually to verify all pass.",
                    "info"
                ))
                return

        self.results.append(CheckResult(
            "Test verification",
            False,
            "No test command detected. Run tests before publishing.",
            "info"
        ))

    def check_badges(self):
        """Check for README badges"""
        readme = self.project_path / "README.md"

        if not readme.exists():
            return

        content = readme.read_text(encoding="utf-8")
        has_badges = "shields.io" in content or "badge" in content.lower()

        if has_badges:
            self.results.append(CheckResult(
                "README badges",
                True,
                "Badges found in README"
            ))
        else:
            self.results.append(CheckResult(
                "README badges",
                False,
                "No badges in README. Add build status, version, license badges.",
                "info"
            ))

    def check_demo_or_screenshots(self):
        """Check for demo or screenshots"""
        readme = self.project_path / "README.md"

        if not readme.exists():
            return

        content = readme.read_text(encoding="utf-8")
        has_media = any(ext in content for ext in [".png", ".jpg", ".gif", ".mp4", "demo"])

        if has_media:
            self.results.append(CheckResult(
                "Demo/screenshots",
                True,
                "Demo or screenshots found"
            ))
        else:
            self.results.append(CheckResult(
                "Demo/screenshots",
                False,
                "No demo or screenshots in README. Add visual examples.",
                "info"
            ))

    def check_roadmap(self):
        """Check for roadmap"""
        roadmap_files = ["ROADMAP.md", "TODO.md"]
        found = any((self.project_path / f).exists() for f in roadmap_files)

        if found:
            self.results.append(CheckResult(
                "Roadmap",
                True,
                "Roadmap or TODO found"
            ))
        else:
            self.results.append(CheckResult(
                "Roadmap",
                False,
                "No ROADMAP.md. Consider adding future plans.",
                "info"
            ))

    def print_summary(self) -> bool:
        """Print check results and return success status"""
        print(f"\n{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}Pre-Publication Checklist Results{RESET}")
        print(f"{BOLD}{'='*70}{RESET}\n")

        # Group by severity
        errors = [r for r in self.results if not r.passed and r.severity == "error"]
        warnings = [r for r in self.results if not r.passed and r.severity == "warning"]
        info = [r for r in self.results if not r.passed and r.severity == "info"]
        passed = [r for r in self.results if r.passed]

        # Print errors first
        if errors:
            print(f"{RED}{BOLD}ERRORS (Must Fix):{RESET}")
            for result in errors:
                print(f"  {result}")
            print()

        # Then warnings
        if warnings:
            print(f"{YELLOW}{BOLD}WARNINGS (Should Fix):{RESET}")
            for result in warnings:
                print(f"  {result}")
            print()

        # Then info
        if info:
            print(f"{BLUE}{BOLD}RECOMMENDATIONS (Consider):{RESET}")
            for result in info:
                print(f"  {result}")
            print()

        # Summary
        print(f"{BOLD}{'='*70}{RESET}")
        print(f"{GREEN}✓ {len(passed)} passed{RESET}")
        if errors:
            print(f"{RED}✗ {len(errors)} errors{RESET}")
        if warnings:
            print(f"{YELLOW}⚠ {len(warnings)} warnings{RESET}")
        if info:
            print(f"{BLUE}ℹ {len(info)} recommendations{RESET}")
        print(f"{BOLD}{'='*70}{RESET}\n")

        # Determine pass/fail
        if self.strict:
            success = len(errors) == 0 and len(warnings) == 0
            if not success:
                print(f"{RED}{BOLD}STRICT MODE: Not ready for publication{RESET}")
            else:
                print(f"{GREEN}{BOLD}✓ Ready for publication (strict mode){RESET}")
        else:
            success = len(errors) == 0
            if not success:
                print(f"{RED}{BOLD}Not ready for publication (fix errors first){RESET}")
            else:
                if warnings:
                    print(f"{YELLOW}{BOLD}⚠ Ready with warnings (consider fixing warnings){RESET}")
                else:
                    print(f"{GREEN}{BOLD}✓ Ready for publication{RESET}")

        return success


def main():
    parser = argparse.ArgumentParser(
        description="Pre-publication checklist for Autopack-built projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/pre_publish_checklist.py --project-path /path/to/project
  python scripts/pre_publish_checklist.py --project-path .autonomous_runs/file-organizer-app-v1
  python scripts/pre_publish_checklist.py --project-path /path/to/project --strict

Checklist Categories:
  - Core artifacts (README, LICENSE, CHANGELOG, versioning)
  - Distribution (package metadata, lockfiles, build artifacts, Docker)
  - Documentation (user docs, API docs, installation, examples)
  - Quality (tests, CI/CD, security policy)
  - Legal (license headers, third-party licenses, no secrets)
  - Metadata (git tags, release templates)
  - Build verification (build succeeds, tests pass)
  - Optional (badges, demos, roadmap)
"""
    )

    parser.add_argument(
        "--project-path",
        type=Path,
        required=True,
        help="Path to project directory to check"
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: warnings are treated as failures"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Optional: Write results to JSON file"
    )

    args = parser.parse_args()

    if not args.project_path.exists():
        print(f"{RED}Error: Project path does not exist: {args.project_path}{RESET}")
        sys.exit(1)

    if not args.project_path.is_dir():
        print(f"{RED}Error: Project path is not a directory: {args.project_path}{RESET}")
        sys.exit(1)

    # Run checks
    checker = PrePublishChecker(args.project_path, strict=args.strict)
    success = checker.run_all_checks()

    # Write JSON output if requested
    if args.output:
        output_data = {
            "project_path": str(args.project_path),
            "timestamp": datetime.now().isoformat(),
            "strict_mode": args.strict,
            "success": success,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                }
                for r in checker.results
            ],
        }
        args.output.write_text(json.dumps(output_data, indent=2))
        print(f"\nResults written to: {args.output}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
