# autopack/validators/yaml_validator.py
"""
YAML and Docker Compose validation utilities for pre-apply gating.

Provides:
- validate_yaml_syntax: Basic YAML syntax validation
- validate_docker_compose: Docker Compose schema validation
- validate_yaml_completeness: Check for truncation markers

Used pre-apply to fail fast on malformed/truncated YAML.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    errors: List[str]
    warnings: List[str]

    def __bool__(self) -> bool:
        return self.valid


# Common truncation markers that indicate incomplete output
TRUNCATION_MARKERS = [
    "...",
    "# ...",
    "# truncated",
    "# (truncated)",
    "# remaining",
    "# rest of",
    "# etc",
    "# more",
    "[truncated]",
    "...(truncated)",
]

# Required keys for docker-compose files
COMPOSE_REQUIRED_KEYS = {"version", "services"}
COMPOSE_OPTIONAL_KEYS = {"networks", "volumes", "secrets", "configs", "x-"}

# Valid docker-compose versions
COMPOSE_VALID_VERSIONS = {"2", "2.0", "2.1", "2.2", "2.3", "2.4", "3", "3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9"}


def validate_yaml_syntax(content: str, filename: str = "unknown") -> ValidationResult:
    """
    Validate basic YAML syntax.

    Args:
        content: YAML content string
        filename: Filename for error messages

    Returns:
        ValidationResult with valid flag and any errors
    """
    errors = []
    warnings = []

    if not content or not content.strip():
        return ValidationResult(valid=False, errors=["Empty YAML content"], warnings=[])

    # Check for truncation markers
    content_lower = content.lower()
    for marker in TRUNCATION_MARKERS:
        if marker in content_lower:
            errors.append(f"Truncation marker detected: '{marker}'")

    # Try to parse YAML
    try:
        parsed = yaml.safe_load(content)
        if parsed is None:
            warnings.append("YAML parsed to None (empty document)")
        elif not isinstance(parsed, (dict, list)):
            warnings.append(f"YAML root is not dict or list: {type(parsed).__name__}")
    except yaml.YAMLError as e:
        errors.append(f"YAML syntax error: {e}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # Check for common YAML issues
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Check for tabs (YAML prefers spaces)
        if "\t" in line and not line.strip().startswith("#"):
            warnings.append(f"Line {i}: Tab character found (use spaces for YAML indentation)")

        # Check for trailing whitespace in values that might cause issues
        if line.rstrip() != line and line.strip() and not line.strip().startswith("#"):
            # Only warn if it's significant trailing whitespace
            pass

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def validate_docker_compose(content: str, filename: str = "docker-compose.yml") -> ValidationResult:
    """
    Validate Docker Compose file structure and common issues.

    Args:
        content: Docker Compose YAML content
        filename: Filename for error messages

    Returns:
        ValidationResult with valid flag and any errors
    """
    errors = []
    warnings = []

    # First validate basic YAML syntax
    syntax_result = validate_yaml_syntax(content, filename)
    errors.extend(syntax_result.errors)
    warnings.extend(syntax_result.warnings)

    if not syntax_result.valid:
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # Parse YAML
    try:
        compose = yaml.safe_load(content)
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error: {e}")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    if not isinstance(compose, dict):
        errors.append("Docker Compose root must be a dict")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    # Check for version (optional in newer Compose)
    version = compose.get("version")
    if version:
        version_str = str(version)
        if version_str not in COMPOSE_VALID_VERSIONS:
            warnings.append(f"Unusual Compose version: {version_str}")

    # Check for services (required)
    services = compose.get("services")
    if services is None:
        errors.append("Missing 'services' key (required for docker-compose)")
    elif not isinstance(services, dict):
        errors.append("'services' must be a dict")
    else:
        # Validate each service
        for service_name, service_config in services.items():
            service_errors = _validate_compose_service(service_name, service_config)
            errors.extend(service_errors)

    # Check for unknown top-level keys
    for key in compose.keys():
        if key not in COMPOSE_REQUIRED_KEYS and key not in COMPOSE_OPTIONAL_KEYS:
            if not key.startswith("x-"):  # x- prefix is for extensions
                warnings.append(f"Unknown top-level key: '{key}'")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _validate_compose_service(name: str, config: Any) -> List[str]:
    """Validate a single service definition."""
    errors = []

    if config is None:
        errors.append(f"Service '{name}': empty configuration")
        return errors

    if not isinstance(config, dict):
        errors.append(f"Service '{name}': configuration must be a dict")
        return errors

    # Check for image or build (at least one required)
    has_image = "image" in config
    has_build = "build" in config
    if not has_image and not has_build:
        errors.append(f"Service '{name}': must have 'image' or 'build'")

    # Validate ports format
    ports = config.get("ports", [])
    if ports:
        if not isinstance(ports, list):
            errors.append(f"Service '{name}': 'ports' must be a list")
        else:
            for port in ports:
                if not _is_valid_port_mapping(port):
                    errors.append(f"Service '{name}': invalid port mapping: {port}")

    # Validate volumes format
    volumes = config.get("volumes", [])
    if volumes:
        if not isinstance(volumes, list):
            errors.append(f"Service '{name}': 'volumes' must be a list")

    # Validate environment format
    env = config.get("environment")
    if env is not None:
        if not isinstance(env, (dict, list)):
            errors.append(f"Service '{name}': 'environment' must be dict or list")

    # Validate depends_on format
    depends = config.get("depends_on")
    if depends is not None:
        if not isinstance(depends, (dict, list)):
            errors.append(f"Service '{name}': 'depends_on' must be dict or list")

    return errors


def _is_valid_port_mapping(port: Any) -> bool:
    """Check if a port mapping is valid."""
    if isinstance(port, int):
        return 1 <= port <= 65535

    if isinstance(port, str):
        # Formats: "8080", "8080:80", "127.0.0.1:8080:80", "8080:80/tcp"
        port_pattern = r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:)?(\d+)(:(\d+))?(/(tcp|udp))?$'
        return bool(re.match(port_pattern, port))

    if isinstance(port, dict):
        # Long syntax
        return "target" in port

    return False


def validate_yaml_file(filepath: Path) -> ValidationResult:
    """
    Validate a YAML file from disk.

    Args:
        filepath: Path to YAML file

    Returns:
        ValidationResult
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[f"Failed to read file: {e}"],
            warnings=[],
        )

    filename = filepath.name
    if "compose" in filename.lower() or "docker" in filename.lower():
        return validate_docker_compose(content, filename)
    else:
        return validate_yaml_syntax(content, filename)


def validate_yaml_completeness(content: str, expected_keys: Optional[List[str]] = None) -> ValidationResult:
    """
    Check if YAML content appears complete (not truncated).

    Args:
        content: YAML content
        expected_keys: Optional list of expected top-level keys

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []

    # Check for truncation markers
    content_lower = content.lower()
    for marker in TRUNCATION_MARKERS:
        if marker in content_lower:
            errors.append(f"Truncation marker detected: '{marker}'")

    # Check for unclosed brackets/braces (common truncation symptom)
    open_braces = content.count("{") - content.count("}")
    open_brackets = content.count("[") - content.count("]")
    if open_braces != 0:
        errors.append(f"Unbalanced braces: {open_braces} unclosed")
    if open_brackets != 0:
        errors.append(f"Unbalanced brackets: {open_brackets} unclosed")

    # Check for expected keys
    if expected_keys:
        try:
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict):
                missing = [k for k in expected_keys if k not in parsed]
                if missing:
                    errors.append(f"Missing expected keys: {missing}")
        except yaml.YAMLError:
            pass  # Already caught by syntax validation

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
