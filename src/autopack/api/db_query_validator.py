"""Database query parameter validation for API routes (IMP-SEC-002).

This module provides validation helpers for API route parameters that are used
in database queries. It implements defense-in-depth by validating all user-controlled
inputs before they reach the database layer.

Note: SQLAlchemy ORM already provides parameterized query protection. This module
adds an explicit validation layer for:
1. Defense-in-depth security
2. Early validation before database queries
3. Consistent validation across all API endpoints
4. Better error messages for invalid inputs

IMP-SEC-002: Audit DB queries for sanitizer usage
This module ensures all user-controlled database query parameters are validated
using the SQLSanitizer before reaching the database layer.
"""

import logging
from typing import Any, List, Optional

from autopack.sql_sanitizer import SQLSanitizer

logger = logging.getLogger(__name__)


class DBQueryValidator:
    """Validates database query parameters from API inputs."""

    @staticmethod
    def validate_run_id(run_id: Optional[str]) -> Optional[str]:
        """Validate and sanitize run_id parameter.

        Args:
            run_id: Run ID from API path/query parameter

        Returns:
            Validated run_id

        Raises:
            ValueError: If run_id contains unsafe SQL patterns
        """
        if run_id is None:
            return None
        return SQLSanitizer.validate_parameter(run_id)

    @staticmethod
    def validate_phase_id(phase_id: Optional[str]) -> Optional[str]:
        """Validate and sanitize phase_id parameter.

        Args:
            phase_id: Phase ID from API path/query parameter

        Returns:
            Validated phase_id

        Raises:
            ValueError: If phase_id contains unsafe SQL patterns
        """
        if phase_id is None:
            return None
        return SQLSanitizer.validate_parameter(phase_id)

    @staticmethod
    def validate_session_id(session_id: Optional[str]) -> Optional[str]:
        """Validate and sanitize session_id parameter.

        Args:
            session_id: Session ID from API path/query parameter

        Returns:
            Validated session_id

        Raises:
            ValueError: If session_id contains unsafe SQL patterns
        """
        if session_id is None:
            return None
        return SQLSanitizer.validate_parameter(session_id)

    @staticmethod
    def validate_approval_id(approval_id: Optional[int]) -> Optional[int]:
        """Validate and sanitize approval_id parameter.

        Args:
            approval_id: Approval ID from API path/query parameter

        Returns:
            Validated approval_id

        Raises:
            ValueError: If approval_id is of invalid type
        """
        if approval_id is None:
            return None
        return SQLSanitizer.validate_parameter(approval_id)

    @staticmethod
    def validate_tier_id(tier_id: Optional[str]) -> Optional[str]:
        """Validate and sanitize tier_id parameter.

        Args:
            tier_id: Tier ID from API path/query parameter

        Returns:
            Validated tier_id

        Raises:
            ValueError: If tier_id contains unsafe SQL patterns
        """
        if tier_id is None:
            return None
        return SQLSanitizer.validate_parameter(tier_id)

    @staticmethod
    def validate_project_id(project_id: Optional[str]) -> Optional[str]:
        """Validate and sanitize project_id parameter.

        Args:
            project_id: Project ID from API path/query parameter

        Returns:
            Validated project_id

        Raises:
            ValueError: If project_id contains unsafe SQL patterns
        """
        if project_id is None:
            return None
        return SQLSanitizer.validate_parameter(project_id)

    @staticmethod
    def validate_string_parameter(param: Optional[str], param_name: str = "parameter") -> Optional[str]:
        """Generic validation for string parameters used in queries.

        Args:
            param: Parameter value from API input
            param_name: Name of parameter for logging (e.g., "user_id")

        Returns:
            Validated parameter

        Raises:
            ValueError: If parameter contains unsafe SQL patterns
        """
        if param is None:
            return None
        try:
            return SQLSanitizer.validate_parameter(param)
        except ValueError as e:
            logger.warning(f"Invalid {param_name}: {e}")
            raise

    @staticmethod
    def validate_integer_parameter(param: Optional[int], param_name: str = "parameter") -> Optional[int]:
        """Generic validation for integer parameters used in queries.

        Args:
            param: Parameter value from API input
            param_name: Name of parameter for logging (e.g., "count")

        Returns:
            Validated parameter

        Raises:
            ValueError: If parameter is invalid type
        """
        if param is None:
            return None
        try:
            return SQLSanitizer.validate_parameter(param)
        except ValueError as e:
            logger.warning(f"Invalid {param_name}: {e}")
            raise

    @staticmethod
    def validate_list_of_strings(
        items: Optional[List[str]], param_name: str = "items"
    ) -> Optional[List[str]]:
        """Validate a list of string parameters.

        Args:
            items: List of string parameters
            param_name: Name of parameter for logging

        Returns:
            List of validated parameters

        Raises:
            ValueError: If any item contains unsafe SQL patterns
        """
        if not items:
            return items
        validated = []
        for item in items:
            try:
                validated.append(SQLSanitizer.validate_parameter(item))
            except ValueError as e:
                logger.warning(f"Invalid item in {param_name}: {e}")
                raise
        return validated
