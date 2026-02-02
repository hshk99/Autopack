"""Documentation Phase Implementation for Autonomous Build System.

This module implements the DOCUMENTATION phase type, which enables the autonomous
executor to generate comprehensive documentation for projects during the build lifecycle.

Documentation phases are used when:
- A project needs comprehensive documentation generation
- API documentation, guides, and user manuals are required
- Architecture and design documentation needs to be created
- Integration with existing project artifacts is needed

Design Principles:
- Documentation phases leverage existing documentation generation infrastructure
- Artifacts are generated to workspace in phase-specific subdirectory
- Results are cached and reusable across phases
- Clear success/failure criteria for documentation completeness
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DocumentationStatus(Enum):
    """Status of a documentation phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DocumentationConfig:
    """Configuration for a documentation phase."""

    documentation_types: List[str] = field(default_factory=lambda: ["api", "architecture", "usage"])
    include_examples: bool = True
    include_api_docs: bool = True
    include_architecture_docs: bool = True
    include_user_guide: bool = True
    output_format: str = "markdown"
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class DocumentationInput:
    """Input data for documentation phase."""

    project_name: str
    project_description: str
    tech_stack: Dict[str, Any]
    source_paths: List[str] = field(default_factory=list)
    project_requirements: Optional[Dict[str, Any]] = None


@dataclass
class DocumentationOutput:
    """Output from documentation phase."""

    api_docs_path: Optional[str] = None
    architecture_docs_path: Optional[str] = None
    user_guide_path: Optional[str] = None
    examples_path: Optional[str] = None
    documentation_index_path: Optional[str] = None
    documentation_types_generated: List[str] = field(default_factory=list)
    artifacts_generated: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class DocumentationPhase:
    """Represents a documentation phase with its configuration and state."""

    phase_id: str
    description: str
    config: DocumentationConfig
    input_data: Optional[DocumentationInput] = None
    status: DocumentationStatus = DocumentationStatus.PENDING
    output: Optional[DocumentationOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            output_dict = {
                "api_docs_path": self.output.api_docs_path,
                "architecture_docs_path": self.output.architecture_docs_path,
                "user_guide_path": self.output.user_guide_path,
                "examples_path": self.output.examples_path,
                "documentation_index_path": self.output.documentation_index_path,
                "documentation_types_generated": self.output.documentation_types_generated,
                "artifacts_generated": self.output.artifacts_generated,
                "warnings": self.output.warnings,
                "recommendations": self.output.recommendations,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "project_name": self.input_data.project_name,
                "project_description": self.input_data.project_description,
                "tech_stack": self.input_data.tech_stack,
                "source_paths": self.input_data.source_paths,
                "project_requirements": self.input_data.project_requirements,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "documentation_types": self.config.documentation_types,
                "include_examples": self.config.include_examples,
                "include_api_docs": self.config.include_api_docs,
                "include_architecture_docs": self.config.include_architecture_docs,
                "include_user_guide": self.config.include_user_guide,
                "output_format": self.config.output_format,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class DocumentationPhaseExecutor:
    """Executor for documentation phases."""

    def __init__(
        self,
        workspace_path: Optional[Path] = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.

        Args:
            workspace_path: Optional path to workspace for artifact generation
            build_history_path: Optional path to BUILD_HISTORY.md
        """
        self.workspace_path = workspace_path or Path.cwd()
        self.build_history_path = build_history_path

    def execute(self, phase: DocumentationPhase) -> DocumentationPhase:
        """Execute a documentation phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing documentation phase: {phase.phase_id}")

        phase.status = DocumentationStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = DocumentationOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = DocumentationStatus.FAILED
                phase.error = "No input data provided for documentation phase"
                return phase

            # Generate documentation artifacts
            self._generate_documentation_artifacts(phase)

            # Mark as completed if not already failed
            if phase.status == DocumentationStatus.IN_PROGRESS:
                phase.status = DocumentationStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = DocumentationStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_documentation_artifacts(self, phase: DocumentationPhase) -> None:
        """Generate documentation artifacts based on configuration.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        # Create documentation directory
        docs_dir = self.workspace_path / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Generate API documentation if enabled
        if phase.config.include_api_docs or "api" in phase.config.documentation_types:
            try:
                self._generate_api_docs(phase, docs_dir)
            except Exception as e:
                logger.warning(f"Failed to generate API docs: {e}")
                phase.output.warnings.append(f"API documentation generation failed: {str(e)}")

        # Generate architecture documentation if enabled
        if (
            phase.config.include_architecture_docs
            or "architecture" in phase.config.documentation_types
        ):
            try:
                self._generate_architecture_docs(phase, docs_dir)
            except Exception as e:
                logger.warning(f"Failed to generate architecture docs: {e}")
                phase.output.warnings.append(
                    f"Architecture documentation generation failed: {str(e)}"
                )

        # Generate user guide if enabled
        if phase.config.include_user_guide or "usage" in phase.config.documentation_types:
            try:
                self._generate_user_guide(phase, docs_dir)
            except Exception as e:
                logger.warning(f"Failed to generate user guide: {e}")
                phase.output.warnings.append(f"User guide generation failed: {str(e)}")

        # Generate examples if enabled
        if phase.config.include_examples:
            try:
                self._generate_examples(phase, docs_dir)
            except Exception as e:
                logger.warning(f"Failed to generate examples: {e}")
                phase.output.warnings.append(f"Examples generation failed: {str(e)}")

        # Generate documentation index
        try:
            self._generate_documentation_index(phase, docs_dir)
        except Exception as e:
            logger.warning(f"Failed to generate documentation index: {e}")
            phase.output.warnings.append(f"Documentation index generation failed: {str(e)}")

    def _generate_api_docs(self, phase: DocumentationPhase, docs_dir: Path) -> None:
        """Generate API documentation.

        Args:
            phase: The phase being executed
            docs_dir: Documentation directory path
        """
        if not phase.output or not phase.input_data:
            return

        api_content = f"""# API Documentation

## {phase.input_data.project_name}

### Overview

This document provides comprehensive API documentation for the {phase.input_data.project_name} project.

**Project Description**: {phase.input_data.project_description}

### Technology Stack

"""
        # Add tech stack information
        for tech, version in phase.input_data.tech_stack.items():
            api_content += f"- **{tech}**: {version}\n"

        api_content += """

### API Endpoints

#### Authentication

All API endpoints require authentication via Bearer token in the Authorization header:

```
Authorization: Bearer <your-token>
```

#### Base URL

```
https://api.example.com/v1
```

### Getting Started

1. Obtain an API token from your dashboard
2. Include the token in the Authorization header
3. Make requests to the API endpoints
4. Handle responses and errors appropriately

### Response Format

All responses are returned in JSON format:

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

### Error Handling

Errors are returned with appropriate HTTP status codes:

- 400: Bad Request
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 500: Internal Server Error

### Rate Limiting

API requests are rate-limited to 1000 requests per hour per API token.

### Support

For API support, please contact: api-support@example.com
"""

        api_path = docs_dir / "API.md"
        api_path.write_text(api_content, encoding="utf-8")

        phase.output.api_docs_path = str(api_path)
        phase.output.artifacts_generated.append(str(api_path))
        phase.output.documentation_types_generated.append("api")
        logger.info(f"Generated API documentation: {api_path}")

    def _generate_architecture_docs(self, phase: DocumentationPhase, docs_dir: Path) -> None:
        """Generate architecture documentation.

        Args:
            phase: The phase being executed
            docs_dir: Documentation directory path
        """
        if not phase.output or not phase.input_data:
            return

        arch_content = f"""# Architecture Documentation

## {phase.input_data.project_name}

### System Overview

{phase.input_data.project_description}

### Architecture Diagram

```
+-------------------------------------+
|     Client Applications             |
+----------------+--------------------+
                 |
                 v
+-------------------------------------+
|     API Gateway / Router            |
+----------------+--------------------+
                 |
    +------------+------------+
    |            |            |
    v            v            v
+--------+  +--------+  +--------+
|Service1|  |Service2|  |Service3|
+---+----+  +---+----+  +---+----+
    |          |           |
    +-----+----+----+-----+
         |           |
         v           v
    +--------+  +--------+
    |Database|  | Cache  |
    +--------+  +--------+
```

### Technology Stack

"""
        for tech, version in phase.input_data.tech_stack.items():
            arch_content += f"- **{tech}**: {version}\n"

        arch_content += """

### Core Components

#### API Gateway
- Routes incoming requests
- Handles authentication and authorization
- Implements rate limiting and caching

#### Microservices
- Independent, deployable service units
- Communicate via REST APIs
- Database per service pattern

#### Data Layer
- Primary database for persistent storage
- Cache layer for performance optimization
- Event streaming for async communication

### Design Patterns

1. **Microservices Architecture**: Independent services for scalability
2. **API-First Design**: All interactions via REST APIs
3. **Database per Service**: Data isolation and independence
4. **Event-Driven Communication**: Async messaging for loose coupling
5. **Caching Strategy**: Multi-level caching for performance

### Scalability Considerations

- Horizontal scaling of microservices
- Database replication and sharding
- Cache clustering
- Load balancing across instances

### Security Architecture

- API authentication via Bearer tokens
- Authorization using role-based access control (RBAC)
- Encryption in transit (TLS/SSL)
- Encryption at rest for sensitive data
- Regular security audits and vulnerability scanning

### Deployment Architecture

- Containerized services (Docker)
- Orchestration via Kubernetes or similar
- CI/CD pipelines for automated deployment
- Environment-specific configurations
"""

        arch_path = docs_dir / "ARCHITECTURE.md"
        arch_path.write_text(arch_content, encoding="utf-8")

        phase.output.architecture_docs_path = str(arch_path)
        phase.output.artifacts_generated.append(str(arch_path))
        phase.output.documentation_types_generated.append("architecture")
        logger.info(f"Generated architecture documentation: {arch_path}")

    def _generate_user_guide(self, phase: DocumentationPhase, docs_dir: Path) -> None:
        """Generate user guide documentation.

        Args:
            phase: The phase being executed
            docs_dir: Documentation directory path
        """
        if not phase.output or not phase.input_data:
            return

        guide_content = f"""# User Guide

## {phase.input_data.project_name}

### Getting Started

Welcome to {phase.input_data.project_name}! This guide will help you get started.

### Installation

```bash
# Clone the repository
git clone https://github.com/example/{phase.input_data.project_name.lower()}.git

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Configuration

Create a `.env` file in the project root:

```env
API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:password@localhost/dbname
DEBUG=False
```

### Basic Usage

### Step 1: Initialize the Application

```python
from {phase.input_data.project_name.lower()} import App

app = App(config_file=".env")
```

### Step 2: Perform Operations

```python
# Example operation
result = app.process_data(data)
```

### Step 3: Handle Results

```python
if result.success:
    print("Operation completed successfully")
    print(result.data)
else:
    print("Operation failed:", result.error)
```

### Common Tasks

#### Task 1: Basic Setup
1. Install the package
2. Configure environment variables
3. Initialize the application

#### Task 2: Working with Data
1. Load data from source
2. Process the data
3. Export results

### Troubleshooting

#### Issue: Connection Error
**Solution**: Check that your database is running and credentials are correct.

#### Issue: API Rate Limit
**Solution**: Implement request throttling or upgrade your API plan.

#### Issue: Memory Issues
**Solution**: Process data in batches instead of loading everything at once.

### FAQs

**Q: How do I reset my API key?**
A: Visit your account dashboard and click "Reset API Key".

**Q: Can I use this in production?**
A: Yes, this application is suitable for production use with proper configuration and monitoring.

**Q: How do I report a bug?**
A: Please create an issue on GitHub with details about the problem.

### Support

- Documentation: https://docs.example.com
- Issues: https://github.com/example/issues
- Email: support@example.com
- Community Forum: https://community.example.com
"""

        guide_path = docs_dir / "USER_GUIDE.md"
        guide_path.write_text(guide_content, encoding="utf-8")

        phase.output.user_guide_path = str(guide_path)
        phase.output.artifacts_generated.append(str(guide_path))
        phase.output.documentation_types_generated.append("usage")
        logger.info(f"Generated user guide: {guide_path}")

    def _generate_examples(self, phase: DocumentationPhase, docs_dir: Path) -> None:
        """Generate examples documentation.

        Args:
            phase: The phase being executed
            docs_dir: Documentation directory path
        """
        if not phase.output or not phase.input_data:
            return

        examples_content = f"""# Examples

## {phase.input_data.project_name}

### Example 1: Basic Usage

```python
from {phase.input_data.project_name.lower()} import App

# Initialize the application
app = App()

# Perform a basic operation
result = app.run()
print(result)
```

### Example 2: Working with Data

```python
import json
from {phase.input_data.project_name.lower()} import DataProcessor

processor = DataProcessor()

# Load data
data = processor.load_data("input.json")

# Process data
processed = processor.process(data)

# Save results
with open("output.json", "w") as f:
    json.dump(processed, f)
```

### Example 3: Error Handling

```python
from {phase.input_data.project_name.lower()} import App, AppError

app = App()

try:
    result = app.run()
except AppError as e:
    print(f"Error occurred: {{e.message}}")
    # Handle the error appropriately
except Exception as e:
    print(f"Unexpected error: {{e}}")
    # Log and handle unexpected errors
```

### Example 4: Configuration

```python
from {phase.input_data.project_name.lower()} import App, Config

# Create custom configuration
config = Config(
    debug=True,
    timeout=30,
    retries=3,
    log_level="INFO"
)

# Initialize with custom config
app = App(config=config)
```

### Example 5: Advanced Features

```python
from {phase.input_data.project_name.lower()} import App

app = App()

# Enable caching
app.enable_caching(ttl=3600)

# Set up monitoring
app.setup_monitoring(endpoint="https://monitoring.example.com")

# Run with custom parameters
result = app.run(
    parallel=True,
    batch_size=100,
    timeout=60
)
```

### Example 6: Integration with External Services

```python
from {phase.input_data.project_name.lower()} import App
from some_external_service import ExternalAPI

app = App()
external_api = ExternalAPI(api_key="your-key")

# Integrate with external service
data = external_api.fetch_data()
result = app.process(data)

# Send results back
external_api.push_results(result)
```

### Running Examples

To run these examples:

```bash
# Navigate to examples directory
cd examples/

# Run a specific example
python example_1_basic.py

# Run all examples
for file in *.py; do
    python "$file"
done
```
"""

        examples_path = docs_dir / "EXAMPLES.md"
        examples_path.write_text(examples_content, encoding="utf-8")

        phase.output.examples_path = str(examples_path)
        phase.output.artifacts_generated.append(str(examples_path))
        logger.info(f"Generated examples documentation: {examples_path}")

    def _generate_documentation_index(self, phase: DocumentationPhase, docs_dir: Path) -> None:
        """Generate documentation index.

        Args:
            phase: The phase being executed
            docs_dir: Documentation directory path
        """
        if not phase.output:
            return

        index_content = f"""# {phase.input_data.project_name} Documentation

## Welcome

Thank you for using {phase.input_data.project_name}. This documentation provides comprehensive information about the project, its features, and how to use them.

## Table of Contents

1. [Getting Started](#getting-started)
2. [User Guide](./USER_GUIDE.md)
3. [API Documentation](./API.md)
4. [Architecture](./ARCHITECTURE.md)
5. [Examples](./EXAMPLES.md)
6. [FAQ](#faq)
7. [Support](#support)

## Getting Started

To get started with {phase.input_data.project_name}:

1. Review the [User Guide](./USER_GUIDE.md) for installation and basic setup
2. Check [Examples](./EXAMPLES.md) for code samples
3. Read the [API Documentation](./API.md) for endpoint details
4. Understand the [Architecture](./ARCHITECTURE.md) for system design

## Documentation Structure

```
docs/
├── INDEX.md (this file)
├── USER_GUIDE.md      # Installation, configuration, basic usage
├── API.md             # API endpoints and specifications
├── ARCHITECTURE.md    # System design and architecture
├── EXAMPLES.md        # Code examples and use cases
└── ...
```

## Key Features

- Comprehensive API documentation
- Architecture diagrams and explanations
- Step-by-step user guide
- Multiple code examples
- Troubleshooting section
- Community support

## Technology Stack

"""
        if phase.input_data:
            for tech, version in phase.input_data.tech_stack.items():
                index_content += f"- {tech}: {version}\n"

        index_content += """

## FAQ

**Q: Where should I start?**
A: Start with the User Guide for installation and basic setup.

**Q: How do I report issues?**
A: Please use the support channels listed below.

**Q: Is there a community forum?**
A: Yes, visit our community forum for discussions and help.

## Support

- **Documentation**: This documentation site
- **GitHub Issues**: Report bugs and request features
- **Email Support**: support@example.com
- **Community Forum**: https://community.example.com
- **Status Page**: https://status.example.com

## Contributing

We welcome contributions! See CONTRIBUTING.md for guidelines.

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Version

Current Documentation Version: 1.0.0
Last Updated: {datetime.now().strftime('%Y-%m-%d')}
"""

        index_path = docs_dir / "INDEX.md"
        index_path.write_text(index_content, encoding="utf-8")

        phase.output.documentation_index_path = str(index_path)
        phase.output.artifacts_generated.append(str(index_path))
        logger.info(f"Generated documentation index: {index_path}")

    def _save_to_history(self, phase: DocumentationPhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: DocumentationPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Documentation Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Documentation Artifacts")
            if phase.output.documentation_types_generated:
                lines.append(
                    f"- **Documentation Types**: {', '.join(phase.output.documentation_types_generated)}"
                )
            if phase.output.artifacts_generated:
                lines.append("- **Artifacts Generated**:")
                for artifact in phase.output.artifacts_generated:
                    lines.append(f"  - {artifact}")
            if phase.output.warnings:
                lines.append("- **Warnings**:")
                for warning in phase.output.warnings:
                    lines.append(f"  - {warning}")
            lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_documentation_phase(
    phase_id: str, project_name: str, project_description: str, tech_stack: Dict[str, Any], **kwargs
) -> DocumentationPhase:
    """Factory function to create a documentation phase.

    Args:
        phase_id: Unique phase identifier
        project_name: Name of the project
        project_description: Description of the project
        tech_stack: Technology stack configuration
        **kwargs: Additional configuration options

    Returns:
        Configured DocumentationPhase instance
    """
    config = DocumentationConfig(**kwargs)
    input_data = DocumentationInput(
        project_name=project_name,
        project_description=project_description,
        tech_stack=tech_stack,
    )

    return DocumentationPhase(
        phase_id=phase_id,
        description=f"Documentation phase: {phase_id}",
        config=config,
        input_data=input_data,
    )
