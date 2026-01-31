"""Schema validation utilities for Autopack artifacts.

Provides minimal JSON schema validation without external dependencies.
Uses Python's built-in capabilities for required/type checks.
"""

from .json_schema import (SchemaValidationError, load_schema,
                          validate_autopilot_session_v1,
                          validate_gap_report_v1, validate_intention_anchor_v2,
                          validate_plan_proposal_v1)

__all__ = [
    "validate_intention_anchor_v2",
    "validate_gap_report_v1",
    "validate_plan_proposal_v1",
    "validate_autopilot_session_v1",
    "SchemaValidationError",
    "load_schema",
]
