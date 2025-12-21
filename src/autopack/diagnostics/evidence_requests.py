"""Evidence Requests Module for Cursor-like Steering.

This module provides functionality for Autopack to ask for missing evidence
explicitly without causing token blowups. It generates compact, structured
evidence requests that can be injected into prompts.

Design Goals:
- Compact representation to minimize token usage
- Clear, actionable requests for human operators
- Support for multiple evidence types (logs, files, configs, etc.)
- Priority-based ordering for most critical evidence first
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import json


class EvidenceType(Enum):
    """Types of evidence that can be requested."""
    LOG_FILE = "log_file"
    CONFIG_FILE = "config_file"
    ERROR_MESSAGE = "error_message"
    STACK_TRACE = "stack_trace"
    ENVIRONMENT_VAR = "environment_var"
    COMMAND_OUTPUT = "command_output"
    FILE_CONTENT = "file_content"
    DATABASE_STATE = "database_state"
    API_RESPONSE = "api_response"
    TEST_OUTPUT = "test_output"
    DEPENDENCY_VERSION = "dependency_version"
    SYSTEM_INFO = "system_info"
    CUSTOM = "custom"


class EvidencePriority(Enum):
    """Priority levels for evidence requests."""
    CRITICAL = 1  # Blocking - cannot proceed without this
    HIGH = 2      # Important - significantly impacts diagnosis
    MEDIUM = 3    # Helpful - improves diagnosis quality
    LOW = 4       # Optional - nice to have


@dataclass
class EvidenceRequest:
    """A single evidence request.
    
    Attributes:
        evidence_type: The type of evidence being requested
        description: Human-readable description of what's needed
        path_hint: Optional path or location hint (e.g., file path, env var name)
        priority: How critical this evidence is
        context: Why this evidence is needed
        format_hint: Expected format of the response
    """
    evidence_type: EvidenceType
    description: str
    path_hint: Optional[str] = None
    priority: EvidencePriority = EvidencePriority.MEDIUM
    context: Optional[str] = None
    format_hint: Optional[str] = None
    
    def to_compact_string(self) -> str:
        """Convert to a compact string representation for prompts.
        
        Returns:
            A compact string suitable for injection into prompts.
        """
        parts = [f"[{self.priority.name}] {self.evidence_type.value}: {self.description}"]
        if self.path_hint:
            parts.append(f"  Location: {self.path_hint}")
        if self.format_hint:
            parts.append(f"  Format: {self.format_hint}")
        return "\n".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.evidence_type.value,
            "description": self.description,
            "path_hint": self.path_hint,
            "priority": self.priority.name,
            "context": self.context,
            "format_hint": self.format_hint,
        }


@dataclass
class EvidenceRequestBatch:
    """A batch of evidence requests for a diagnostic session.
    
    Attributes:
        phase_id: The phase these requests relate to
        requests: List of individual evidence requests
        max_response_tokens: Suggested token limit for responses
        deadline_hint: Optional deadline for providing evidence
    """
    phase_id: str
    requests: List[EvidenceRequest] = field(default_factory=list)
    max_response_tokens: int = 2000  # Keep responses compact
    deadline_hint: Optional[str] = None
    
    def add_request(self, request: EvidenceRequest) -> None:
        """Add a request to the batch."""
        self.requests.append(request)
    
    def get_sorted_requests(self) -> List[EvidenceRequest]:
        """Get requests sorted by priority (critical first)."""
        return sorted(self.requests, key=lambda r: r.priority.value)
    
    def to_prompt_injection(self) -> str:
        """Generate a compact prompt injection for evidence requests.
        
        This is designed to be injected into LLM prompts without
        causing token blowups. Uses a structured but minimal format.
        
        Returns:
            A compact string suitable for prompt injection.
        """
        if not self.requests:
            return ""
        
        lines = [
            "--- EVIDENCE NEEDED ---",
            f"Phase: {self.phase_id}",
            f"Max response: ~{self.max_response_tokens} tokens",
            "",
        ]
        
        sorted_requests = self.get_sorted_requests()
        for i, req in enumerate(sorted_requests, 1):
            lines.append(f"{i}. {req.to_compact_string()}")
            lines.append("")
        
        lines.append("--- END EVIDENCE REQUEST ---")
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """Serialize to JSON for storage/transmission."""
        return json.dumps({
            "phase_id": self.phase_id,
            "requests": [r.to_dict() for r in self.requests],
            "max_response_tokens": self.max_response_tokens,
            "deadline_hint": self.deadline_hint,
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "EvidenceRequestBatch":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        batch = cls(
            phase_id=data["phase_id"],
            max_response_tokens=data.get("max_response_tokens", 2000),
            deadline_hint=data.get("deadline_hint"),
        )
        for req_data in data.get("requests", []):
            batch.add_request(EvidenceRequest(
                evidence_type=EvidenceType(req_data["type"]),
                description=req_data["description"],
                path_hint=req_data.get("path_hint"),
                priority=EvidencePriority[req_data.get("priority", "MEDIUM")],
                context=req_data.get("context"),
                format_hint=req_data.get("format_hint"),
            ))
        return batch


class EvidenceRequestBuilder:
    """Builder for creating evidence request batches.
    
    Provides a fluent interface for constructing evidence requests
    based on diagnostic context.
    """
    
    def __init__(self, phase_id: str):
        """Initialize builder for a specific phase.
        
        Args:
            phase_id: The phase ID these requests relate to
        """
        self.batch = EvidenceRequestBatch(phase_id=phase_id)
    
    def request_log(self, description: str, path: Optional[str] = None,
                    priority: EvidencePriority = EvidencePriority.MEDIUM) -> "EvidenceRequestBuilder":
        """Request a log file."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.LOG_FILE,
            description=description,
            path_hint=path,
            priority=priority,
            format_hint="Last 50 lines or relevant section",
        ))
        return self
    
    def request_error(self, description: str,
                      priority: EvidencePriority = EvidencePriority.HIGH) -> "EvidenceRequestBuilder":
        """Request an error message or stack trace."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.ERROR_MESSAGE,
            description=description,
            priority=priority,
            format_hint="Full error message with stack trace if available",
        ))
        return self
    
    def request_config(self, description: str, path: Optional[str] = None,
                       priority: EvidencePriority = EvidencePriority.MEDIUM) -> "EvidenceRequestBuilder":
        """Request a configuration file."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.CONFIG_FILE,
            description=description,
            path_hint=path,
            priority=priority,
            format_hint="Relevant sections only, redact secrets",
        ))
        return self
    
    def request_command_output(self, command: str, description: str,
                               priority: EvidencePriority = EvidencePriority.MEDIUM) -> "EvidenceRequestBuilder":
        """Request output from a command."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.COMMAND_OUTPUT,
            description=description,
            path_hint=f"Run: {command}",
            priority=priority,
            format_hint="Full output, truncate if > 100 lines",
        ))
        return self
    
    def request_file(self, description: str, path: str,
                     priority: EvidencePriority = EvidencePriority.MEDIUM) -> "EvidenceRequestBuilder":
        """Request content of a specific file."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.FILE_CONTENT,
            description=description,
            path_hint=path,
            priority=priority,
            format_hint="Full file or relevant section",
        ))
        return self
    
    def request_env_var(self, var_name: str, description: str,
                        priority: EvidencePriority = EvidencePriority.LOW) -> "EvidenceRequestBuilder":
        """Request an environment variable value."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.ENVIRONMENT_VAR,
            description=description,
            path_hint=var_name,
            priority=priority,
            format_hint="Value only, redact if sensitive",
        ))
        return self
    
    def request_test_output(self, description: str, test_command: Optional[str] = None,
                            priority: EvidencePriority = EvidencePriority.HIGH) -> "EvidenceRequestBuilder":
        """Request test output."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=EvidenceType.TEST_OUTPUT,
            description=description,
            path_hint=test_command,
            priority=priority,
            format_hint="Failed tests with assertions, skip passing tests",
        ))
        return self
    
    def request_custom(self, evidence_type: EvidenceType, description: str,
                       path_hint: Optional[str] = None, context: Optional[str] = None,
                       priority: EvidencePriority = EvidencePriority.MEDIUM,
                       format_hint: Optional[str] = None) -> "EvidenceRequestBuilder":
        """Request custom evidence."""
        self.batch.add_request(EvidenceRequest(
            evidence_type=evidence_type,
            description=description,
            path_hint=path_hint,
            priority=priority,
            context=context,
            format_hint=format_hint,
        ))
        return self
    
    def set_max_tokens(self, max_tokens: int) -> "EvidenceRequestBuilder":
        """Set the maximum response token limit."""
        self.batch.max_response_tokens = max_tokens
        return self
    
    def set_deadline(self, deadline: str) -> "EvidenceRequestBuilder":
        """Set a deadline hint for providing evidence."""
        self.batch.deadline_hint = deadline
        return self
    
    def build(self) -> EvidenceRequestBatch:
        """Build and return the evidence request batch."""
        return self.batch


def create_evidence_request_for_failure(
    phase_id: str,
    failure_type: str,
    failure_message: str,
    context: Optional[Dict[str, Any]] = None
) -> EvidenceRequestBatch:
    """Create evidence requests based on a failure type.
    
    This is a convenience function that generates appropriate evidence
    requests based on common failure patterns.
    
    Args:
        phase_id: The phase that failed
        failure_type: Type of failure (e.g., 'test_failure', 'build_error')
        failure_message: The failure message
        context: Optional additional context
    
    Returns:
        An EvidenceRequestBatch with appropriate requests
    """
    builder = EvidenceRequestBuilder(phase_id)
    
    # Common requests based on failure type
    if failure_type in ("test_failure", "test_error"):
        builder.request_test_output(
            "Full test output with failures",
            priority=EvidencePriority.CRITICAL
        )
        builder.request_log(
            "Test log file if available",
            path="pytest.log or test output",
            priority=EvidencePriority.HIGH
        )
    
    elif failure_type in ("build_error", "compilation_error"):
        builder.request_error(
            "Full build/compilation error output",
            priority=EvidencePriority.CRITICAL
        )
        builder.request_config(
            "Build configuration",
            path="pyproject.toml, setup.py, or Makefile",
            priority=EvidencePriority.MEDIUM
        )
    
    elif failure_type in ("import_error", "module_not_found"):
        builder.request_command_output(
            "pip list",
            "Installed packages list",
            priority=EvidencePriority.HIGH
        )
        builder.request_file(
            "Requirements file",
            "requirements.txt",
            priority=EvidencePriority.MEDIUM
        )
    
    elif failure_type in ("git_apply_failed", "patch_error"):
        builder.request_command_output(
            "git status",
            "Current git status",
            priority=EvidencePriority.HIGH
        )
        builder.request_command_output(
            "git diff",
            "Current uncommitted changes",
            priority=EvidencePriority.MEDIUM
        )
    
    elif failure_type in ("database_error", "connection_error"):
        builder.request_config(
            "Database configuration",
            priority=EvidencePriority.HIGH
        )
        builder.request_env_var(
            "DATABASE_URL",
            "Database connection string (redacted)",
            priority=EvidencePriority.MEDIUM
        )
    
    else:
        # Generic failure - request common evidence
        builder.request_error(
            f"Full error details for: {failure_message[:100]}",
            priority=EvidencePriority.CRITICAL
        )
        builder.request_log(
            "Relevant log output",
            priority=EvidencePriority.HIGH
        )
    
    # Always helpful to have
    builder.set_max_tokens(1500)  # Keep responses compact
    
    return builder.build()
