"""Tests for DocumentationGenerator artifact generator."""

from __future__ import annotations

from autopack.artifact_generators.documentation_generator import DocumentationGenerator


class TestDocumentationGeneratorInitialization:
    """Test DocumentationGenerator initialization."""

    def test_initialization(self) -> None:
        """Test DocumentationGenerator initialization."""
        generator = DocumentationGenerator()
        assert generator is not None

    def test_documentation_types_defined(self) -> None:
        """Test that documentation types are properly defined."""
        generator = DocumentationGenerator()
        assert "api" in generator.DOCUMENTATION_TYPES
        assert "architecture" in generator.DOCUMENTATION_TYPES
        assert "user" in generator.DOCUMENTATION_TYPES
        assert "developer" in generator.DOCUMENTATION_TYPES
        assert "operations" in generator.DOCUMENTATION_TYPES


class TestDocumentationGeneratorBasic:
    """Test basic documentation generation."""

    def test_generate_all_documentation_types(self) -> None:
        """Test generating all documentation types."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Python"],
            "frameworks": ["FastAPI"],
            "database": ["PostgreSQL"],
            "cache": ["Redis"],
            "package_manager": "pip",
        }

        docs = generator.generate(
            project_name="MyApp",
            project_description="A sample application",
            tech_stack=tech_stack,
        )

        # Verify all documentation types are generated
        assert len(docs) == 5
        assert "API_DOCUMENTATION.md" in docs
        assert "ARCHITECTURE.md" in docs
        assert "USER_GUIDE.md" in docs
        assert "DEVELOPER_GUIDE.md" in docs
        assert "OPERATIONS_GUIDE.md" in docs

    def test_generate_specific_documentation_types(self) -> None:
        """Test generating specific documentation types."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["JavaScript"],
            "frameworks": ["React", "Node.js"],
            "database": ["MongoDB"],
            "package_manager": "npm",
        }

        docs = generator.generate(
            project_name="WebApp",
            tech_stack=tech_stack,
            documentation_types=["api", "user"],
        )

        # Verify only specified types are generated
        assert len(docs) == 2
        assert "API_DOCUMENTATION.md" in docs
        assert "USER_GUIDE.md" in docs
        assert "ARCHITECTURE.md" not in docs
        assert "DEVELOPER_GUIDE.md" not in docs
        assert "OPERATIONS_GUIDE.md" not in docs

    def test_generate_with_empty_documentation_types(self) -> None:
        """Test that empty documentation types defaults to all."""
        generator = DocumentationGenerator()

        tech_stack = {"languages": ["Go"], "frameworks": ["Gin"]}

        docs = generator.generate(
            project_name="APIService",
            tech_stack=tech_stack,
            documentation_types=[],  # Empty list
        )

        # Should default to all types
        assert len(docs) == 5


class TestAPIDocumentation:
    """Test API documentation generation."""

    def test_api_documentation_structure(self) -> None:
        """Test that API documentation has correct structure."""
        generator = DocumentationGenerator()

        tech_stack = {"languages": ["Python"], "frameworks": ["FastAPI"]}

        docs = generator.generate(
            project_name="MyAPI",
            tech_stack=tech_stack,
            documentation_types=["api"],
        )

        api_doc = docs["API_DOCUMENTATION.md"]

        # Verify structure
        assert "# API Documentation - MyAPI" in api_doc
        assert "## Overview" in api_doc
        assert "## Table of Contents" in api_doc
        assert "## Authentication" in api_doc
        assert "## Endpoints" in api_doc
        assert "## Data Models" in api_doc
        assert "## Error Handling" in api_doc
        assert "## Rate Limiting" in api_doc

    def test_api_documentation_with_custom_endpoints(self) -> None:
        """Test API documentation with custom endpoints."""
        generator = DocumentationGenerator()

        api_endpoints = [
            {"method": "GET", "path": "/api/v1/users", "description": "List all users"},
            {
                "method": "POST",
                "path": "/api/v1/users",
                "description": "Create a new user",
            },
            {
                "method": "GET",
                "path": "/api/v1/users/{id}",
                "description": "Get user by ID",
            },
        ]

        docs = generator.generate(
            project_name="UserAPI",
            documentation_types=["api"],
            api_endpoints=api_endpoints,
        )

        api_doc = docs["API_DOCUMENTATION.md"]

        # Verify custom endpoints are included
        assert "/api/v1/users" in api_doc
        assert "/api/v1/users/{id}" in api_doc
        assert "List all users" in api_doc
        assert "Create a new user" in api_doc
        assert "Get user by ID" in api_doc


class TestArchitectureDocumentation:
    """Test architecture documentation generation."""

    def test_architecture_documentation_structure(self) -> None:
        """Test that architecture documentation has correct structure."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Python"],
            "frameworks": ["Django"],
            "database": ["PostgreSQL"],
        }

        docs = generator.generate(
            project_name="WebApp",
            project_description="A web application with microservices",
            tech_stack=tech_stack,
            documentation_types=["architecture"],
        )

        arch_doc = docs["ARCHITECTURE.md"]

        # Verify structure
        assert "# Architecture Documentation - WebApp" in arch_doc
        assert "## System Overview" in arch_doc
        assert "## Architecture Diagram" in arch_doc
        assert "## Components" in arch_doc
        assert "## Data Flow" in arch_doc
        assert "## Design Patterns" in arch_doc
        assert "## Scalability" in arch_doc

    def test_architecture_includes_tech_stack(self) -> None:
        """Test that architecture documentation includes tech stack."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Go"],
            "frameworks": ["Gin"],
            "database": ["MySQL"],
            "cache": ["Memcached"],
        }

        docs = generator.generate(
            project_name="HighPerformanceAPI",
            tech_stack=tech_stack,
            documentation_types=["architecture"],
        )

        arch_doc = docs["ARCHITECTURE.md"]

        # Verify tech stack is mentioned
        assert "MySQL" in arch_doc
        assert "Memcached" in arch_doc


class TestUserGuide:
    """Test user guide generation."""

    def test_user_guide_structure(self) -> None:
        """Test that user guide has correct structure."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="SampleApp",
            project_description="A sample application for users",
            documentation_types=["user"],
        )

        user_guide = docs["USER_GUIDE.md"]

        # Verify structure
        assert "# User Guide - SampleApp" in user_guide
        assert "## Welcome" in user_guide
        assert "## Table of Contents" in user_guide
        assert "## Getting Started" in user_guide
        assert "## Features" in user_guide
        assert "## Usage Examples" in user_guide
        assert "## Tips & Tricks" in user_guide
        assert "## FAQ" in user_guide
        assert "## Support" in user_guide

    def test_user_guide_with_custom_features(self) -> None:
        """Test user guide with custom features."""
        generator = DocumentationGenerator()

        features = [
            "User authentication and authorization",
            "Real-time data synchronization",
            "Advanced analytics dashboard",
            "Custom reporting tools",
        ]

        docs = generator.generate(
            project_name="EnterpriseApp",
            features=features,
            documentation_types=["user"],
        )

        user_guide = docs["USER_GUIDE.md"]

        # Verify features are included
        assert "User authentication and authorization" in user_guide
        assert "Real-time data synchronization" in user_guide
        assert "Advanced analytics dashboard" in user_guide
        assert "Custom reporting tools" in user_guide

    def test_user_guide_includes_faq(self) -> None:
        """Test that user guide includes FAQ section."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="FAQApp",
            documentation_types=["user"],
        )

        user_guide = docs["USER_GUIDE.md"]

        # Verify FAQ content
        assert "## FAQ" in user_guide
        assert "How do I reset my password?" in user_guide
        assert "two-factor authentication" in user_guide


class TestDeveloperGuide:
    """Test developer guide generation."""

    def test_developer_guide_structure(self) -> None:
        """Test that developer guide has correct structure."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["TypeScript"],
            "frameworks": ["Next.js"],
            "package_manager": "npm",
        }

        docs = generator.generate(
            project_name="DevProject",
            tech_stack=tech_stack,
            documentation_types=["developer"],
        )

        dev_guide = docs["DEVELOPER_GUIDE.md"]

        # Verify structure
        assert "# Developer Guide - DevProject" in dev_guide
        assert "## Project Setup" in dev_guide
        assert "## Project Structure" in dev_guide
        assert "## Development Workflow" in dev_guide
        assert "## Contributing" in dev_guide
        assert "## Testing" in dev_guide
        assert "## Deployment" in dev_guide

    def test_developer_guide_with_tech_stack(self) -> None:
        """Test that developer guide includes tech stack info."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Rust"],
            "frameworks": ["Actix"],
            "package_manager": "cargo",
        }

        docs = generator.generate(
            project_name="RustService",
            tech_stack=tech_stack,
            documentation_types=["developer"],
        )

        dev_guide = docs["DEVELOPER_GUIDE.md"]

        # Verify tech stack details
        assert "Rust" in dev_guide
        assert "cargo" in dev_guide

    def test_developer_guide_includes_testing(self) -> None:
        """Test that developer guide includes testing section."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="TestedApp",
            documentation_types=["developer"],
        )

        dev_guide = docs["DEVELOPER_GUIDE.md"]

        # Verify testing section
        assert "## Testing" in dev_guide
        assert "Running Tests" in dev_guide
        assert "Writing Tests" in dev_guide


class TestOperationsGuide:
    """Test operations guide generation."""

    def test_operations_guide_structure(self) -> None:
        """Test that operations guide has correct structure."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="ProductionApp",
            documentation_types=["operations"],
        )

        ops_guide = docs["OPERATIONS_GUIDE.md"]

        # Verify structure
        assert "# Operations Guide - ProductionApp" in ops_guide
        assert "## Deployment" in ops_guide
        assert "## Monitoring" in ops_guide
        assert "## Logging" in ops_guide
        assert "## Troubleshooting" in ops_guide
        assert "## Maintenance" in ops_guide
        assert "## Disaster Recovery" in ops_guide

    def test_operations_guide_includes_metrics(self) -> None:
        """Test that operations guide includes monitoring metrics."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="MonitoredApp",
            documentation_types=["operations"],
        )

        ops_guide = docs["OPERATIONS_GUIDE.md"]

        # Verify monitoring content
        assert "## Monitoring" in ops_guide
        assert "Key Metrics" in ops_guide
        assert "CPU Usage" in ops_guide
        assert "Memory Usage" in ops_guide
        assert "Response Time" in ops_guide

    def test_operations_guide_includes_troubleshooting(self) -> None:
        """Test that operations guide includes troubleshooting."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="TroubleshootApp",
            documentation_types=["operations"],
        )

        ops_guide = docs["OPERATIONS_GUIDE.md"]

        # Verify troubleshooting content
        assert "## Troubleshooting" in ops_guide
        assert "High CPU Usage" in ops_guide
        assert "Database Connection Issues" in ops_guide
        assert "Memory Leaks" in ops_guide


class TestDocumentationGeneratorNone:
    """Test behavior with None and default values."""

    def test_generate_with_all_none_optional_params(self) -> None:
        """Test generation with None optional parameters."""
        generator = DocumentationGenerator()

        docs = generator.generate(project_name="MinimalApp")

        # Should still generate all documentation types
        assert len(docs) == 5
        assert all(isinstance(content, str) for content in docs.values())

    def test_generate_with_empty_tech_stack(self) -> None:
        """Test generation with empty tech stack."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="BasicApp",
            tech_stack={},
            documentation_types=["api"],
        )

        api_doc = docs["API_DOCUMENTATION.md"]
        assert "# API Documentation - BasicApp" in api_doc

    def test_all_generated_docs_are_strings(self) -> None:
        """Test that all generated docs are strings."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Python"],
            "database": ["PostgreSQL"],
        }

        docs = generator.generate(
            project_name="StringCheckApp",
            tech_stack=tech_stack,
        )

        for filename, content in docs.items():
            assert isinstance(filename, str)
            assert isinstance(content, str)
            assert len(content) > 0
            assert filename.endswith(".md")


class TestDocumentationGeneratorIntegration:
    """Integration tests for complete documentation generation."""

    def test_full_documentation_generation(self) -> None:
        """Test full documentation generation with all features."""
        generator = DocumentationGenerator()

        tech_stack = {
            "languages": ["Python", "JavaScript"],
            "frameworks": ["FastAPI", "React"],
            "database": ["PostgreSQL"],
            "cache": ["Redis"],
            "package_manager": "npm",
        }

        features = [
            "User management",
            "Real-time notifications",
            "Data export",
            "Advanced search",
        ]

        api_endpoints = [
            {"method": "GET", "path": "/api/v1/users", "description": "List users"},
            {
                "method": "POST",
                "path": "/api/v1/products",
                "description": "Create product",
            },
        ]

        docs = generator.generate(
            project_name="FullFeaturedApp",
            project_description="A comprehensive application with all features",
            tech_stack=tech_stack,
            features=features,
            api_endpoints=api_endpoints,
        )

        # Verify all docs are generated
        assert len(docs) == 5

        # Verify API doc has endpoints
        api_doc = docs["API_DOCUMENTATION.md"]
        assert "/api/v1/users" in api_doc
        assert "/api/v1/products" in api_doc

        # Verify architecture includes tech stack
        arch_doc = docs["ARCHITECTURE.md"]
        assert "PostgreSQL" in arch_doc
        assert "Redis" in arch_doc

        # Verify user guide includes features
        user_guide = docs["USER_GUIDE.md"]
        assert "User management" in user_guide
        assert "Real-time notifications" in user_guide

        # Verify developer guide includes package manager
        dev_guide = docs["DEVELOPER_GUIDE.md"]
        assert "npm" in dev_guide

        # Verify operations guide has content
        ops_guide = docs["OPERATIONS_GUIDE.md"]
        assert "## Deployment" in ops_guide
        assert "## Monitoring" in ops_guide

    def test_documentation_consistency(self) -> None:
        """Test that generated documentation is consistent."""
        generator = DocumentationGenerator()

        # Generate twice with same input
        docs1 = generator.generate(
            project_name="ConsistencyApp",
            tech_stack={"languages": ["Python"]},
        )

        docs2 = generator.generate(
            project_name="ConsistencyApp",
            tech_stack={"languages": ["Python"]},
        )

        # Should generate identical documentation
        assert docs1.keys() == docs2.keys()
        for key in docs1.keys():
            assert docs1[key] == docs2[key]

    def test_invalid_documentation_types_handled_gracefully(self) -> None:
        """Test that invalid documentation types are handled gracefully."""
        generator = DocumentationGenerator()

        docs = generator.generate(
            project_name="InvalidTypeApp",
            documentation_types=["invalid", "also_invalid"],
        )

        # Should default to all valid types
        assert len(docs) == 5
