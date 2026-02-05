"""DocumentationGenerator artifact generator for project documentation.

Generates comprehensive project documentation including API documentation,
architecture guides, user guides, developer guides, and operational documentation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DocumentationGenerator:
    """Generates comprehensive project documentation.

    Produces documentation including:
    - API documentation (endpoints, schemas, authentication)
    - Architecture documentation (system design, component interactions)
    - User guides (features, usage examples, FAQs)
    - Developer guides (setup, contribution guidelines, code structure)
    - Operations documentation (deployment, monitoring, troubleshooting)
    - Examples and tutorials (code samples, integration guides)
    """

    # Documentation types
    DOCUMENTATION_TYPES = {
        "api": {
            "name": "API Documentation",
            "description": "Complete API reference with endpoints, parameters, and examples",
            "sections": ["Authentication", "Endpoints", "Data Models", "Error Handling"],
        },
        "architecture": {
            "name": "Architecture Guide",
            "description": "System design, components, and interactions",
            "sections": ["System Overview", "Components", "Data Flow", "Design Patterns"],
        },
        "user": {
            "name": "User Guide",
            "description": "Feature documentation and usage examples",
            "sections": ["Getting Started", "Features", "Usage Examples", "FAQ"],
        },
        "developer": {
            "name": "Developer Guide",
            "description": "Setup, contribution guidelines, and code structure",
            "sections": ["Setup", "Project Structure", "Contributing", "Testing"],
        },
        "operations": {
            "name": "Operations Guide",
            "description": "Deployment, monitoring, and troubleshooting",
            "sections": ["Deployment", "Monitoring", "Troubleshooting", "Maintenance"],
        },
    }

    def __init__(self) -> None:
        """Initialize the DocumentationGenerator."""
        logger.info("[DocumentationGenerator] Initializing documentation generator")

    def generate(
        self,
        project_name: str,
        project_description: Optional[str] = None,
        tech_stack: Optional[Dict[str, Any]] = None,
        documentation_types: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        api_endpoints: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, str]:
        """Generate comprehensive project documentation.

        Args:
            project_name: Name of the project
            project_description: Brief description of the project
            tech_stack: Technology stack configuration
            documentation_types: Types of documentation to generate (defaults to all)
            features: List of main features
            api_endpoints: List of API endpoints with methods and descriptions

        Returns:
            Dictionary of documentation file names and content
        """
        logger.info(f"[DocumentationGenerator] Generating documentation for {project_name}")

        if tech_stack is None:
            tech_stack = {}

        if features is None:
            features = []

        if api_endpoints is None:
            api_endpoints = []

        if documentation_types is None:
            documentation_types = list(self.DOCUMENTATION_TYPES.keys())
        else:
            # Validate documentation types
            documentation_types = [d for d in documentation_types if d in self.DOCUMENTATION_TYPES]
            if not documentation_types:
                documentation_types = list(self.DOCUMENTATION_TYPES.keys())
                logger.warning("[DocumentationGenerator] No valid doc types specified, using all")

        docs = {}

        # Generate each type of documentation
        for doc_type in documentation_types:
            if doc_type == "api":
                docs["API_DOCUMENTATION.md"] = self._generate_api_documentation(
                    project_name, tech_stack, api_endpoints
                )
            elif doc_type == "architecture":
                docs["ARCHITECTURE.md"] = self._generate_architecture_documentation(
                    project_name, project_description, tech_stack
                )
            elif doc_type == "user":
                docs["USER_GUIDE.md"] = self._generate_user_guide(
                    project_name, project_description, features
                )
            elif doc_type == "developer":
                docs["DEVELOPER_GUIDE.md"] = self._generate_developer_guide(
                    project_name, tech_stack
                )
            elif doc_type == "operations":
                docs["OPERATIONS_GUIDE.md"] = self._generate_operations_guide(project_name)

        return docs

    def _generate_api_documentation(
        self,
        project_name: str,
        tech_stack: Dict[str, Any],
        api_endpoints: List[Dict[str, str]],
    ) -> str:
        """Generate API documentation."""
        doc = f"# API Documentation - {project_name}\n\n"

        doc += "## Overview\n\n"
        doc += f"This document describes the API for **{project_name}**. "
        doc += "The API provides programmatic access to all features.\n\n"

        doc += "## Table of Contents\n\n"
        doc += "- [Authentication](#authentication)\n"
        doc += "- [Endpoints](#endpoints)\n"
        doc += "- [Data Models](#data-models)\n"
        doc += "- [Error Handling](#error-handling)\n"
        doc += "- [Rate Limiting](#rate-limiting)\n\n"

        doc += self._generate_api_auth_section()
        doc += self._generate_endpoints_section(api_endpoints)
        doc += self._generate_data_models_section(tech_stack)
        doc += self._generate_error_handling_section()
        doc += self._generate_rate_limiting_section()

        return doc

    def _generate_api_auth_section(self) -> str:
        """Generate API authentication section."""
        section = "## Authentication\n\n"
        section += "### API Key Authentication\n\n"
        section += "Include your API key in the request header:\n\n"
        section += "```\nAuthorization: Bearer YOUR_API_KEY\n```\n\n"

        section += "### OAuth 2.0\n\n"
        section += "Use OAuth 2.0 for secure user authentication:\n\n"
        section += "```\nAuthorization: Bearer YOUR_ACCESS_TOKEN\n```\n\n"

        section += "### Getting Your API Key\n\n"
        section += "1. Log in to your account\n"
        section += "2. Navigate to API Settings\n"
        section += "3. Generate a new API key\n"
        section += "4. Store it securely (never commit to version control)\n\n"

        return section

    def _generate_endpoints_section(self, api_endpoints: List[Dict[str, str]]) -> str:
        """Generate endpoints section."""
        section = "## Endpoints\n\n"

        if not api_endpoints:
            section += "### Standard Endpoints\n\n"
            section += "| Method | Endpoint | Description |\n"
            section += "|--------|----------|-------------|\n"
            section += "| GET | `/api/v1/status` | Get API status |\n"
            section += "| GET | `/api/v1/users` | List users |\n"
            section += "| POST | `/api/v1/users` | Create user |\n"
            section += "| GET | `/api/v1/users/{id}` | Get user by ID |\n"
            section += "| PUT | `/api/v1/users/{id}` | Update user |\n"
            section += "| DELETE | `/api/v1/users/{id}` | Delete user |\n\n"
        else:
            section += "| Method | Endpoint | Description |\n"
            section += "|--------|----------|-------------|\n"
            for endpoint in api_endpoints:
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "/api/endpoint")
                description = endpoint.get("description", "API endpoint")
                section += f"| {method} | `{path}` | {description} |\n"
            section += "\n"

        section += "### Example Request\n\n"
        section += "```bash\ncurl -X GET https://api.example.com/api/v1/users \\\n"
        section += "  -H \"Authorization: Bearer YOUR_API_KEY\" \\\n"
        section += "  -H \"Content-Type: application/json\"\n```\n\n"

        section += "### Example Response\n\n"
        section += "```json\n{\n"
        section += '  "status": "success",\n'
        section += '  "data": [\n'
        section += "    {\n"
        section += '      "id": 1,\n'
        section += '      "name": "John Doe",\n'
        section += '      "email": "john@example.com"\n'
        section += "    }\n"
        section += "  ]\n"
        section += "}\n```\n\n"

        return section

    def _generate_data_models_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate data models section."""
        section = "## Data Models\n\n"

        section += "### User Model\n\n"
        section += "| Field | Type | Description |\n"
        section += "|-------|------|-------------|\n"
        section += "| `id` | Integer | Unique user identifier |\n"
        section += "| `name` | String | User's full name |\n"
        section += "| `email` | String | User's email address |\n"
        section += "| `created_at` | Timestamp | Account creation timestamp |\n"
        section += "| `updated_at` | Timestamp | Last update timestamp |\n\n"

        section += "### Response Model\n\n"
        section += "All responses follow this standard format:\n\n"
        section += "```json\n{\n"
        section += '  "status": "success|error",\n'
        section += '  "data": {},\n'
        section += '  "error": null,\n'
        section += '  "timestamp": "2024-01-01T00:00:00Z"\n'
        section += "}\n```\n\n"

        return section

    def _generate_error_handling_section(self) -> str:
        """Generate error handling section."""
        section = "## Error Handling\n\n"

        section += "### Error Response Format\n\n"
        section += "```json\n{\n"
        section += '  "status": "error",\n'
        section += '  "error": {\n'
        section += '    "code": "INVALID_REQUEST",\n'
        section += '    "message": "Invalid request parameters",\n'
        section += '    "details": {}\n'
        section += "  }\n"
        section += "}\n```\n\n"

        section += "### Error Codes\n\n"
        section += "| Code | Status | Description |\n"
        section += "|------|--------|-------------|\n"
        section += "| `INVALID_REQUEST` | 400 | Invalid request parameters |\n"
        section += "| `UNAUTHORIZED` | 401 | Missing or invalid authentication |\n"
        section += "| `FORBIDDEN` | 403 | Insufficient permissions |\n"
        section += "| `NOT_FOUND` | 404 | Resource not found |\n"
        section += "| `SERVER_ERROR` | 500 | Internal server error |\n\n"

        return section

    def _generate_rate_limiting_section(self) -> str:
        """Generate rate limiting section."""
        section = "## Rate Limiting\n\n"

        section += "API requests are rate-limited to prevent abuse:\n\n"
        section += "- **Default Limit**: 1000 requests per hour\n"
        section += "- **Per-IP Limit**: 100 requests per minute\n"
        section += "- **Header**: `X-RateLimit-Remaining` shows remaining requests\n"
        section += "- **Reset**: Rate limit resets every hour at :00 UTC\n\n"

        section += "### Rate Limit Response\n\n"
        section += "When rate limit is exceeded:\n\n"
        section += "```\nHTTP/1.1 429 Too Many Requests\n"
        section += "X-RateLimit-Limit: 1000\n"
        section += "X-RateLimit-Remaining: 0\n"
        section += "X-RateLimit-Reset: 1640000000\n"
        section += "Retry-After: 3600\n```\n\n"

        return section

    def _generate_architecture_documentation(
        self, project_name: str, project_description: Optional[str], tech_stack: Dict[str, Any]
    ) -> str:
        """Generate architecture documentation."""
        doc = f"# Architecture Documentation - {project_name}\n\n"

        doc += "## System Overview\n\n"
        if project_description:
            doc += f"{project_description}\n\n"
        else:
            doc += f"**{project_name}** is designed with a modular, scalable architecture.\n\n"

        doc += "## Table of Contents\n\n"
        doc += "- [System Overview](#system-overview)\n"
        doc += "- [Architecture Diagram](#architecture-diagram)\n"
        doc += "- [Components](#components)\n"
        doc += "- [Data Flow](#data-flow)\n"
        doc += "- [Design Patterns](#design-patterns)\n"
        doc += "- [Scalability](#scalability)\n\n"

        doc += self._generate_architecture_diagram()
        doc += self._generate_components_section(tech_stack)
        doc += self._generate_dataflow_section()
        doc += self._generate_design_patterns_section()
        doc += self._generate_scalability_section()

        return doc

    def _generate_architecture_diagram(self) -> str:
        """Generate architecture diagram section."""
        section = "## Architecture Diagram\n\n"
        section += "```\n"
        section += "┌─────────────────────────────────────────────────────────────┐\n"
        section += "│                        Client Layer                          │\n"
        section += "│                 (Web, Mobile, Desktop Apps)                  │\n"
        section += "└────────────────────────────┬────────────────────────────────┘\n"
        section += "                             │\n"
        section += "┌────────────────────────────▼────────────────────────────────┐\n"
        section += "│                      API Gateway Layer                       │\n"
        section += "│          (Authentication, Rate Limiting, Routing)           │\n"
        section += "└────────────────────────────┬────────────────────────────────┘\n"
        section += "                             │\n"
        section += "┌────────────────────────────▼────────────────────────────────┐\n"
        section += "│                   Application Services                       │\n"
        section += "│  (User Service, Product Service, Order Service, etc.)       │\n"
        section += "└────────────────────────────┬────────────────────────────────┘\n"
        section += "                    ┌────────┼────────┐\n"
        section += "                    │        │        │\n"
        section += "     ┌──────────────▼────┐  │   ┌────▼──────────────┐\n"
        section += "     │  Database Layer   │  │   │   Cache Layer     │\n"
        section += "     │  (PostgreSQL)     │  │   │   (Redis)         │\n"
        section += "     └───────────────────┘  │   └───────────────────┘\n"
        section += "                            │\n"
        section += "                    ┌───────▼────────┐\n"
        section += "                    │ Queue System   │\n"
        section += "                    │ (RabbitMQ)     │\n"
        section += "                    └────────────────┘\n"
        section += "```\n\n"
        return section

    def _generate_components_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate components section."""
        section = "## Components\n\n"

        section += "### API Gateway\n\n"
        section += "- Handles all incoming client requests\n"
        section += "- Performs authentication and authorization\n"
        section += "- Implements rate limiting and request validation\n"
        section += "- Routes requests to appropriate services\n\n"

        section += "### Application Services\n\n"
        section += "- **User Service**: Manages user authentication and profiles\n"
        section += "- **Product Service**: Handles product catalog and inventory\n"
        section += "- **Order Service**: Manages order processing and tracking\n"
        section += "- **Payment Service**: Processes payments securely\n"
        section += "- **Notification Service**: Sends emails, SMS, and push notifications\n\n"

        section += "### Data Layer\n\n"
        databases = tech_stack.get("database", ["PostgreSQL"])
        if isinstance(databases, list):
            database_list = ", ".join(databases)
        else:
            database_list = str(databases)
        section += f"- **Primary Database**: {database_list}\n"
        section += "- **Backup & Replication**: Automated backups and read replicas\n"
        section += "- **Data Consistency**: ACID transactions with proper isolation levels\n\n"

        section += "### Cache Layer\n\n"
        cache = tech_stack.get("cache", ["Redis"])
        if isinstance(cache, list):
            cache_list = ", ".join(cache)
        else:
            cache_list = str(cache)
        section += f"- **Cache Engine**: {cache_list}\n"
        section += "- **Session Storage**: In-memory session management\n"
        section += "- **Query Caching**: Reduces database load\n\n"

        return section

    def _generate_dataflow_section(self) -> str:
        """Generate data flow section."""
        section = "## Data Flow\n\n"

        section += "### Request Flow\n\n"
        section += "1. Client sends request to API Gateway\n"
        section += "2. API Gateway validates and authenticates the request\n"
        section += "3. Request is routed to appropriate service\n"
        section += "4. Service processes request and queries database/cache\n"
        section += "5. Response is sent back to client\n\n"

        section += "### Asynchronous Processing\n\n"
        section += "1. Service enqueues task to message queue\n"
        section += "2. Worker processes task from queue\n"
        section += "3. Results are stored and notifications sent\n"
        section += "4. Client polling or WebSocket receives update\n\n"

        return section

    def _generate_design_patterns_section(self) -> str:
        """Generate design patterns section."""
        section = "## Design Patterns\n\n"

        section += "### Microservices Architecture\n\n"
        section += "- Each service handles a specific business domain\n"
        section += "- Services are independently deployable and scalable\n"
        section += "- Communication via REST APIs and message queues\n\n"

        section += "### API Gateway Pattern\n\n"
        section += "- Single entry point for all client requests\n"
        section += "- Handles cross-cutting concerns (auth, logging, rate limiting)\n"
        section += "- Routes to appropriate backend services\n\n"

        section += "### Cache-Aside Pattern\n\n"
        section += "- Check cache first for requested data\n"
        section += "- If cache miss, fetch from database\n"
        section += "- Store result in cache for future requests\n\n"

        section += "### Circuit Breaker Pattern\n\n"
        section += "- Prevents cascading failures in distributed systems\n"
        section += "- Monitors service health\n"
        section += "- Stops sending requests to unhealthy services\n\n"

        return section

    def _generate_scalability_section(self) -> str:
        """Generate scalability section."""
        section = "## Scalability\n\n"

        section += "### Horizontal Scaling\n\n"
        section += "- Services can be deployed across multiple instances\n"
        section += "- Load balancer distributes traffic\n"
        section += "- Database read replicas for scaling read operations\n"
        section += "- Stateless services enable easy scaling\n\n"

        section += "### Vertical Scaling\n\n"
        section += "- Increase compute resources (CPU, memory)\n"
        section += "- Upgrade database instance types\n"
        section += "- Suitable for non-stateless components\n\n"

        section += "### Performance Optimization\n\n"
        section += "- Caching strategies to reduce database load\n"
        section += "- Database indexing and query optimization\n"
        section += "- Asynchronous processing for long-running tasks\n"
        section += "- CDN for static asset delivery\n\n"

        return section

    def _generate_user_guide(
        self, project_name: str, project_description: Optional[str], features: List[str]
    ) -> str:
        """Generate user guide."""
        guide = f"# User Guide - {project_name}\n\n"

        guide += "## Welcome\n\n"
        if project_description:
            guide += f"{project_description}\n\n"
        else:
            guide += f"Welcome to **{project_name}**! This guide will help you get started.\n\n"

        guide += "## Table of Contents\n\n"
        guide += "- [Getting Started](#getting-started)\n"
        guide += "- [Features](#features)\n"
        guide += "- [Usage Examples](#usage-examples)\n"
        guide += "- [Tips & Tricks](#tips--tricks)\n"
        guide += "- [FAQ](#faq)\n"
        guide += "- [Support](#support)\n\n"

        guide += self._generate_getting_started_section()
        guide += self._generate_features_section(features)
        guide += self._generate_usage_examples_section()
        guide += self._generate_tips_section()
        guide += self._generate_faq_section()
        guide += self._generate_support_section()

        return guide

    def _generate_getting_started_section(self) -> str:
        """Generate getting started section."""
        section = "## Getting Started\n\n"

        section += "### Sign Up\n\n"
        section += "1. Visit our website\n"
        section += "2. Click 'Sign Up'\n"
        section += "3. Enter your email address\n"
        section += "4. Create a secure password\n"
        section += "5. Verify your email\n\n"

        section += "### Initial Setup\n\n"
        section += "1. Log in to your account\n"
        section += "2. Complete your profile\n"
        section += "3. Configure preferences\n"
        section += "4. Generate API keys (if needed)\n\n"

        return section

    def _generate_features_section(self, features: List[str]) -> str:
        """Generate features section."""
        section = "## Features\n\n"

        if not features:
            section += "### Core Features\n\n"
            section += "- **User Management**: Create and manage user accounts\n"
            section += "- **Authentication**: Secure login and session management\n"
            section += "- **API Access**: Programmatic access to all features\n"
            section += "- **Real-time Updates**: Live notifications and updates\n"
            section += "- **Analytics**: Detailed usage and performance analytics\n"
            section += "- **Integrations**: Connect with third-party services\n\n"
        else:
            for i, feature in enumerate(features, 1):
                section += f"- **Feature {i}**: {feature}\n"
            section += "\n"

        return section

    def _generate_usage_examples_section(self) -> str:
        """Generate usage examples section."""
        section = "## Usage Examples\n\n"

        section += "### Example 1: Basic Workflow\n\n"
        section += "```\n1. Log in to your account\n"
        section += "2. Navigate to the dashboard\n"
        section += "3. Create a new project\n"
        section += "4. Configure settings\n"
        section += "5. Start using the feature\n```\n\n"

        section += "### Example 2: Using the API\n\n"
        section += "```python\nimport requests\n\nheaders = {'Authorization': 'Bearer YOUR_API_KEY'}\nresponse = requests.get(\n"
        section += "    'https://api.example.com/api/v1/users',\n"
        section += "    headers=headers\n"
        section += ")\n```\n\n"

        return section

    def _generate_tips_section(self) -> str:
        """Generate tips and tricks section."""
        section = "## Tips & Tricks\n\n"

        section += "### Productivity Tips\n\n"
        section += "- Use keyboard shortcuts for faster navigation\n"
        section += "- Bookmark frequently used pages\n"
        section += "- Enable notifications for important updates\n"
        section += "- Set up API integrations for automation\n\n"

        section += "### Best Practices\n\n"
        section += "- Regularly backup your data\n"
        section += "- Use strong passwords and enable 2FA\n"
        section += "- Review security settings periodically\n"
        section += "- Keep API keys secure and rotate them regularly\n\n"

        return section

    def _generate_faq_section(self) -> str:
        """Generate FAQ section."""
        section = "## FAQ\n\n"

        section += "### Q: How do I reset my password?\n"
        section += "A: Visit the login page and click 'Forgot Password'. Follow the instructions sent to your email.\n\n"

        section += "### Q: How do I enable two-factor authentication?\n"
        section += "A: Go to Account Settings > Security > Two-Factor Authentication and follow the setup wizard.\n\n"

        section += "### Q: Can I export my data?\n"
        section += "A: Yes, go to Settings > Data Export to download your data in CSV or JSON format.\n\n"

        section += "### Q: How do I delete my account?\n"
        section += "A: Contact our support team. Account deletion is permanent and cannot be undone.\n\n"

        section += "### Q: Is there a free trial?\n"
        section += "A: Yes, we offer a 14-day free trial with full feature access.\n\n"

        return section

    def _generate_support_section(self) -> str:
        """Generate support section."""
        section = "## Support\n\n"

        section += "### Getting Help\n\n"
        section += "- **Documentation**: Visit our [help center](https://help.example.com)\n"
        section += "- **Email Support**: [support@example.com](mailto:support@example.com)\n"
        section += "- **Chat Support**: Available during business hours\n"
        section += "- **Community Forum**: Connect with other users\n\n"

        section += "### Reporting Issues\n\n"
        section += "If you encounter a bug or issue:\n\n"
        section += "1. Check the FAQ and documentation\n"
        section += "2. Contact support with:\n"
        section += "   - Description of the issue\n"
        section += "   - Steps to reproduce\n"
        section += "   - Screenshots if applicable\n"
        section += "3. Our team will respond within 24 hours\n\n"

        return section

    def _generate_developer_guide(self, project_name: str, tech_stack: Dict[str, Any]) -> str:
        """Generate developer guide."""
        guide = f"# Developer Guide - {project_name}\n\n"

        guide += "## Introduction\n\n"
        guide += "This guide is for developers who want to contribute to or integrate with "
        guide += f"**{project_name}**.\n\n"

        guide += "## Table of Contents\n\n"
        guide += "- [Project Setup](#project-setup)\n"
        guide += "- [Project Structure](#project-structure)\n"
        guide += "- [Development Workflow](#development-workflow)\n"
        guide += "- [Contributing](#contributing)\n"
        guide += "- [Testing](#testing)\n"
        guide += "- [Deployment](#deployment)\n\n"

        guide += self._generate_project_setup_section(tech_stack)
        guide += self._generate_project_structure_section()
        guide += self._generate_development_workflow_section()
        guide += self._generate_contributing_section()
        guide += self._generate_testing_section()
        guide += self._generate_deployment_section()

        return guide

    def _generate_project_setup_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate project setup section."""
        section = "## Project Setup\n\n"

        section += "### Prerequisites\n\n"
        languages = tech_stack.get("languages", ["Python"])
        if isinstance(languages, list):
            lang_list = ", ".join(languages)
        else:
            lang_list = str(languages)
        section += f"- {lang_list}\n"
        section += "- Git\n"
        section += "- Docker (optional but recommended)\n\n"

        section += "### Clone Repository\n\n"
        section += "```bash\ngit clone https://github.com/your-org/project.git\n"
        section += "cd project\n```\n\n"

        section += "### Install Dependencies\n\n"
        package_manager = tech_stack.get("package_manager", "npm")
        if package_manager in ["npm", "yarn"]:
            section += f"```bash\n{package_manager} install\n```\n\n"
        elif package_manager == "pip":
            section += "```bash\npip install -r requirements.txt\n```\n\n"
        elif package_manager == "cargo":
            section += "```bash\ncargo build\n```\n\n"

        section += "### Environment Configuration\n\n"
        section += "```bash\ncp .env.example .env\n# Edit .env with your values\n```\n\n"

        section += "### Run Locally\n\n"
        section += "```bash\nnpm run dev\n# or\npython manage.py runserver\n```\n\n"

        return section

    def _generate_project_structure_section(self) -> str:
        """Generate project structure section."""
        section = "## Project Structure\n\n"

        section += "```\nproject/\n"
        section += "├── src/\n"
        section += "│   ├── api/              # API endpoints and routes\n"
        section += "│   ├── services/         # Business logic\n"
        section += "│   ├── models/           # Data models and schemas\n"
        section += "│   ├── middleware/       # Request middleware\n"
        section += "│   └── utils/            # Utility functions\n"
        section += "├── tests/\n"
        section += "│   ├── unit/             # Unit tests\n"
        section += "│   ├── integration/      # Integration tests\n"
        section += "│   └── e2e/              # End-to-end tests\n"
        section += "├── docs/                 # Documentation\n"
        section += "├── config/               # Configuration files\n"
        section += "├── .env.example          # Environment template\n"
        section += "├── Dockerfile            # Docker configuration\n"
        section += "└── README.md             # Project README\n"
        section += "```\n\n"

        return section

    def _generate_development_workflow_section(self) -> str:
        """Generate development workflow section."""
        section = "## Development Workflow\n\n"

        section += "### Creating a Feature Branch\n\n"
        section += "```bash\ngit checkout -b feature/your-feature-name\n```\n\n"

        section += "### Making Changes\n\n"
        section += "1. Create a feature branch\n"
        section += "2. Make your changes\n"
        section += "3. Write tests for new functionality\n"
        section += "4. Run tests locally\n"
        section += "5. Commit with clear messages\n\n"

        section += "### Commit Message Format\n\n"
        section += "```\ntype(scope): subject\n\nbody\n\nfooter\n```\n\n"

        section += "Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`\n\n"

        return section

    def _generate_contributing_section(self) -> str:
        """Generate contributing section."""
        section = "## Contributing\n\n"

        section += "### Pull Request Process\n\n"
        section += "1. Update documentation if needed\n"
        section += "2. Add tests for new features\n"
        section += "3. Ensure tests pass locally\n"
        section += "4. Push to your feature branch\n"
        section += "5. Create a Pull Request with clear description\n"
        section += "6. Address code review comments\n"
        section += "7. Merge when approved\n\n"

        section += "### Code Style\n\n"
        section += "- Follow PEP 8 (Python) or ESLint (JavaScript) guidelines\n"
        section += "- Use type hints where applicable\n"
        section += "- Write descriptive variable and function names\n"
        section += "- Add docstrings to functions and classes\n"
        section += "- Keep lines under 100 characters\n\n"

        return section

    def _generate_testing_section(self) -> str:
        """Generate testing section."""
        section = "## Testing\n\n"

        section += "### Running Tests\n\n"
        section += "```bash\n# Run all tests\nnpm test\n\n"
        section += "# Run specific test file\nnpm test -- tests/unit/example.test.js\n\n"
        section += "# Run with coverage\nnpm run test:coverage\n```\n\n"

        section += "### Writing Tests\n\n"
        section += "- Write unit tests for business logic\n"
        section += "- Write integration tests for API endpoints\n"
        section += "- Aim for >80% code coverage\n"
        section += "- Use descriptive test names\n"
        section += "- Follow AAA pattern (Arrange, Act, Assert)\n\n"

        section += "### Test Structure\n\n"
        section += "```javascript\ndescribe('UserService', () => {\n"
        section += "  it('should create a user', () => {\n"
        section += "    // Arrange\n"
        section += "    const userData = { name: 'John', email: 'john@example.com' };\n"
        section += "    // Act\n"
        section += "    const user = UserService.create(userData);\n"
        section += "    // Assert\n"
        section += "    expect(user.name).toBe('John');\n"
        section += "  });\n"
        section += "});\n```\n\n"

        return section

    def _generate_deployment_section(self) -> str:
        """Generate deployment section."""
        section = "## Deployment\n\n"

        section += "### Development Environment\n\n"
        section += "```bash\nnpm run dev\n```\n\n"

        section += "### Production Build\n\n"
        section += "```bash\nnpm run build\n```\n\n"

        section += "### Docker Deployment\n\n"
        section += "```bash\n# Build Docker image\ndocker build -t myapp:latest .\n\n"
        section += "# Run container\ndocker run -d -p 8080:8080 myapp:latest\n```\n\n"

        section += "### Deployment Checklist\n\n"
        section += "- [ ] All tests passing\n"
        section += "- [ ] Code review completed\n"
        section += "- [ ] Documentation updated\n"
        section += "- [ ] Environment variables configured\n"
        section += "- [ ] Database migrations run\n"
        section += "- [ ] Performance tested\n"
        section += "- [ ] Security audit completed\n\n"

        return section

    def _generate_operations_guide(self, project_name: str) -> str:
        """Generate operations guide."""
        guide = f"# Operations Guide - {project_name}\n\n"

        guide += "## Overview\n\n"
        guide += f"This guide covers operational aspects of running **{project_name}** in production.\n\n"

        guide += "## Table of Contents\n\n"
        guide += "- [Deployment](#deployment)\n"
        guide += "- [Monitoring](#monitoring)\n"
        guide += "- [Logging](#logging)\n"
        guide += "- [Troubleshooting](#troubleshooting)\n"
        guide += "- [Maintenance](#maintenance)\n"
        guide += "- [Disaster Recovery](#disaster-recovery)\n\n"

        guide += self._generate_ops_deployment_section()
        guide += self._generate_monitoring_section_ops()
        guide += self._generate_logging_section()
        guide += self._generate_troubleshooting_section()
        guide += self._generate_maintenance_section()
        guide += self._generate_disaster_recovery_section()

        return guide

    def _generate_ops_deployment_section(self) -> str:
        """Generate operations deployment section."""
        section = "## Deployment\n\n"

        section += "### Pre-Deployment Checklist\n\n"
        section += "- [ ] Code changes reviewed and tested\n"
        section += "- [ ] Database migrations prepared\n"
        section += "- [ ] Environment variables configured\n"
        section += "- [ ] Backups created\n"
        section += "- [ ] Rollback plan documented\n"
        section += "- [ ] Monitoring alerts configured\n\n"

        section += "### Deployment Steps\n\n"
        section += "1. Create deployment package\n"
        section += "2. Stop background jobs\n"
        section += "3. Run database migrations\n"
        section += "4. Deploy new version\n"
        section += "5. Health check\n"
        section += "6. Monitor metrics\n"
        section += "7. Resume background jobs\n\n"

        section += "### Rollback Procedure\n\n"
        section += "If deployment fails:\n\n"
        section += "1. Identify the issue\n"
        section += "2. Roll back to previous version\n"
        section += "3. Restore from backup if needed\n"
        section += "4. Verify system stability\n"
        section += "5. Investigate and fix issue\n\n"

        return section

    def _generate_monitoring_section_ops(self) -> str:
        """Generate operations monitoring section."""
        section = "## Monitoring\n\n"

        section += "### Key Metrics\n\n"
        section += "- **CPU Usage**: Keep below 80%\n"
        section += "- **Memory Usage**: Keep below 85%\n"
        section += "- **Disk Usage**: Keep below 90%\n"
        section += "- **Response Time**: Monitor p95 and p99 latencies\n"
        section += "- **Error Rate**: Track 4xx and 5xx errors\n"
        section += "- **Database Connections**: Monitor active connections\n\n"

        section += "### Alerting Rules\n\n"
        section += "- CPU > 90% for 5 minutes\n"
        section += "- Memory > 95% for 5 minutes\n"
        section += "- Response time p95 > 2 seconds\n"
        section += "- Error rate > 5%\n"
        section += "- Disk usage > 95%\n\n"

        return section

    def _generate_logging_section(self) -> str:
        """Generate logging section."""
        section = "## Logging\n\n"

        section += "### Log Levels\n\n"
        section += "- **DEBUG**: Detailed diagnostic information\n"
        section += "- **INFO**: General informational messages\n"
        section += "- **WARNING**: Warning messages for potentially harmful situations\n"
        section += "- **ERROR**: Error messages for serious problems\n"
        section += "- **CRITICAL**: Critical messages for very serious problems\n\n"

        section += "### Log Aggregation\n\n"
        section += "Logs are aggregated in centralized logging system:\n\n"
        section += "```\n# Query logs\nkibana: https://kibana.example.com\nlogstash: Processes and indexes logs\nelasticsearch: Stores log data\n```\n\n"

        section += "### Structured Logging\n\n"
        section += "```json\n{\n"
        section += '  "timestamp": "2024-01-01T00:00:00Z",\n'
        section += '  "level": "INFO",\n'
        section += '  "service": "api",\n'
        section += '  "message": "User login successful",\n'
        section += '  "user_id": 123,\n'
        section += '  "duration_ms": 150\n'
        section += "}\n```\n\n"

        return section

    def _generate_troubleshooting_section(self) -> str:
        """Generate troubleshooting section."""
        section = "## Troubleshooting\n\n"

        section += "### High CPU Usage\n\n"
        section += "**Symptoms**: Server CPU utilization high, slow response times\n\n"
        section += "**Diagnosis**:\n"
        section += "1. Check running processes: `top -o %CPU`\n"
        section += "2. Check application logs\n"
        section += "3. Profile application code\n\n"

        section += "**Resolution**:\n"
        section += "- Scale horizontally (add more instances)\n"
        section += "- Optimize slow queries\n"
        section += "- Implement caching\n\n"

        section += "### Database Connection Issues\n\n"
        section += "**Symptoms**: Connection refused, too many connections\n\n"
        section += "**Diagnosis**:\n"
        section += "1. Check database status\n"
        section += "2. Verify credentials\n"
        section += "3. Check connection pool settings\n\n"

        section += "**Resolution**:\n"
        section += "- Increase connection pool size\n"
        section += "- Kill idle connections\n"
        section += "- Upgrade database instance\n\n"

        section += "### Memory Leaks\n\n"
        section += "**Symptoms**: Memory gradually increases over time\n\n"
        section += "**Diagnosis**:\n"
        section += "1. Monitor memory usage over time\n"
        section += "2. Use memory profiler\n"
        section += "3. Check for circular references\n\n"

        section += "**Resolution**:\n"
        section += "- Fix memory leaks in code\n"
        section += "- Restart application regularly\n"
        section += "- Implement proper cleanup\n\n"

        return section

    def _generate_maintenance_section(self) -> str:
        """Generate maintenance section."""
        section = "## Maintenance\n\n"

        section += "### Regular Tasks\n\n"
        section += "**Daily**:\n"
        section += "- Monitor key metrics\n"
        section += "- Check error logs\n"
        section += "- Verify backups completed\n\n"

        section += "**Weekly**:\n"
        section += "- Review performance metrics\n"
        section += "- Run security scans\n"
        section += "- Update dependencies\n"
        section += "- Test disaster recovery procedures\n\n"

        section += "**Monthly**:\n"
        section += "- Full system audit\n"
        section += "- Capacity planning review\n"
        section += "- Security patches\n"
        section += "- Database optimization\n\n"

        section += "### Backup Procedure\n\n"
        section += "```bash\n# Daily backup\n0 2 * * * /scripts/backup-database.sh\n\n"
        section += "# Retention policy\n# Keep 7 daily backups\n# Keep 4 weekly backups\n# Keep 12 monthly backups\n```\n\n"

        return section

    def _generate_disaster_recovery_section(self) -> str:
        """Generate disaster recovery section."""
        section = "## Disaster Recovery\n\n"

        section += "### RTO and RPO\n\n"
        section += "- **RTO (Recovery Time Objective)**: 1 hour\n"
        section += "- **RPO (Recovery Point Objective)**: 1 hour (maximum data loss)\n\n"

        section += "### Backup Strategy\n\n"
        section += "- Full backups: Daily at 2 AM UTC\n"
        section += "- Incremental backups: Every 6 hours\n"
        section += "- Geo-redundant storage\n"
        section += "- Test restores monthly\n\n"

        section += "### Disaster Recovery Plan\n\n"
        section += "1. **Detection**: Automated monitoring detects failure\n"
        section += "2. **Assessment**: Determine scope and impact\n"
        section += "3. **Notification**: Alert on-call team\n"
        section += "4. **Recovery**: Execute recovery procedures\n"
        section += "5. **Verification**: Verify system integrity\n"
        section += "6. **Communication**: Update stakeholders\n\n"

        section += "### Failover Procedure\n\n"
        section += "```bash\n# Check replication status\nshow slave status;\n\n"
        section += "# Promote replica to primary\nSTOP SLAVE;\n"
        section += "SET GLOBAL READ_ONLY = OFF;\n\n"
        section += "# Update application configuration\n"
        section += "# Restart application services\n```\n\n"

        return section
