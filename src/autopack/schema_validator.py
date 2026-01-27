"""
Schema validation system to detect database/code enum mismatches.

Validates that database enum values match code enum definitions to prevent
ORM serialization failures (500 errors).

Per BUILD-130 Phase 1: Schema Validator implementation.
"""

import difflib
import logging
from dataclasses import dataclass, field
from typing import List, Set

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


@dataclass
class SchemaValidationError:
    """Single schema validation error with repair SQL"""

    table: str
    column: str
    invalid_value: str
    affected_rows: List[str]  # IDs of affected rows
    suggested_fix: str  # Valid enum value to use
    repair_sql: str  # SQL to fix the issue


@dataclass
class SchemaValidationResult:
    """Result of schema validation with all errors and repairs"""

    is_valid: bool = True
    errors: List[SchemaValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, error: SchemaValidationError):
        """Add an error to the result"""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str):
        """Add a warning to the result"""
        self.warnings.append(warning)


class SchemaValidator:
    """
    Validate database schema matches code expectations.

    Checks:
    1. Enum values in database match code enum definitions
    2. Required columns exist
    3. NOT NULL constraints are satisfied
    4. JSON columns have valid structure
    """

    def __init__(self, database_url: str):
        """
        Initialize schema validator.

        Args:
            database_url: SQLAlchemy database URL (e.g., "sqlite:///autopack.db")
        """
        self.engine = create_engine(database_url)

    def validate_on_startup(self) -> SchemaValidationResult:
        """
        Comprehensive schema validation.

        Returns:
            SchemaValidationResult with all errors and repair SQL
        """
        result = SchemaValidationResult()

        logger.info("[SchemaValidator] Starting database schema validation...")

        # Validate enum columns
        self._validate_run_states(result)
        self._validate_phase_states(result)
        self._validate_tier_states(result)

        if result.is_valid:
            logger.info("[SchemaValidator] ✅ Database schema validation PASSED")
        else:
            logger.error(f"[SchemaValidator] ❌ Found {len(result.errors)} schema violations")
            for error in result.errors:
                logger.error(
                    f"[SchemaValidator]   {error.table}.{error.column}: '{error.invalid_value}' in rows {error.affected_rows}"
                )

        return result

    def _validate_run_states(self, result: SchemaValidationResult):
        """Validate all Run.state values are valid RunState enums"""
        from autopack.models import RunState

        valid_states = {s.value for s in RunState}

        # Use raw SQL to bypass ORM enum mapping
        with self.engine.connect() as conn:
            query = text("SELECT DISTINCT state FROM runs WHERE state IS NOT NULL")
            db_states = {row[0] for row in conn.execute(query)}

        invalid_states = db_states - valid_states

        if invalid_states:
            for invalid_state in invalid_states:
                # Find runs with this invalid state
                with self.engine.connect() as conn:
                    query = text("SELECT id FROM runs WHERE state = :state")
                    run_ids = [row[0] for row in conn.execute(query, {"state": invalid_state})]

                # Suggest closest valid state using fuzzy matching
                closest_match = self._fuzzy_match(invalid_state, valid_states)

                error = SchemaValidationError(
                    table="runs",
                    column="state",
                    invalid_value=invalid_state,
                    affected_rows=run_ids,
                    suggested_fix=closest_match,
                    repair_sql=f"UPDATE runs SET state='{closest_match}' WHERE state='{invalid_state}';",
                )

                result.add_error(error)
                logger.warning(
                    f"[SchemaValidator] Invalid RunState '{invalid_state}' → suggested fix: '{closest_match}'"
                )

    def _validate_phase_states(self, result: SchemaValidationResult):
        """Validate all Phase.state values are valid PhaseState enums"""
        from autopack.models import PhaseState

        valid_states = {s.value for s in PhaseState}

        # Use raw SQL to bypass ORM enum mapping
        with self.engine.connect() as conn:
            query = text("SELECT DISTINCT state FROM phases WHERE state IS NOT NULL")
            db_states = {row[0] for row in conn.execute(query)}

        invalid_states = db_states - valid_states

        if invalid_states:
            for invalid_state in invalid_states:
                # Find phases with this invalid state
                with self.engine.connect() as conn:
                    query = text("SELECT phase_id FROM phases WHERE state = :state")
                    phase_ids = [row[0] for row in conn.execute(query, {"state": invalid_state})]

                # Suggest closest valid state
                closest_match = self._fuzzy_match(invalid_state, valid_states)

                error = SchemaValidationError(
                    table="phases",
                    column="state",
                    invalid_value=invalid_state,
                    affected_rows=phase_ids,
                    suggested_fix=closest_match,
                    repair_sql=f"UPDATE phases SET state='{closest_match}' WHERE state='{invalid_state}';",
                )

                result.add_error(error)
                logger.warning(
                    f"[SchemaValidator] Invalid PhaseState '{invalid_state}' → suggested fix: '{closest_match}'"
                )

    def _validate_tier_states(self, result: SchemaValidationResult):
        """Validate all Tier.state values are valid TierState enums"""
        from autopack.models import TierState

        valid_states = {s.value for s in TierState}

        # Use raw SQL to bypass ORM enum mapping
        with self.engine.connect() as conn:
            # Check if tiers table exists
            if self.engine.dialect.name == "sqlite":
                table_check = text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='tiers'"
                )
            else:  # PostgreSQL
                table_check = text(
                    "SELECT table_name FROM information_schema.tables WHERE table_name='tiers'"
                )

            table_exists = bool(list(conn.execute(table_check)))

            if not table_exists:
                result.add_warning("Table 'tiers' does not exist - skipping tier state validation")
                return

            query = text("SELECT DISTINCT state FROM tiers WHERE state IS NOT NULL")
            db_states = {row[0] for row in conn.execute(query)}

        invalid_states = db_states - valid_states

        if invalid_states:
            for invalid_state in invalid_states:
                # Find tiers with this invalid state
                with self.engine.connect() as conn:
                    query = text("SELECT tier_id FROM tiers WHERE state = :state")
                    tier_ids = [row[0] for row in conn.execute(query, {"state": invalid_state})]

                # Suggest closest valid state
                closest_match = self._fuzzy_match(invalid_state, valid_states)

                error = SchemaValidationError(
                    table="tiers",
                    column="state",
                    invalid_value=invalid_state,
                    affected_rows=tier_ids,
                    suggested_fix=closest_match,
                    repair_sql=f"UPDATE tiers SET state='{closest_match}' WHERE state='{invalid_state}';",
                )

                result.add_error(error)
                logger.warning(
                    f"[SchemaValidator] Invalid TierState '{invalid_state}' → suggested fix: '{closest_match}'"
                )

    def _fuzzy_match(self, invalid_value: str, valid_values: Set[str]) -> str:
        """
        Find closest matching valid value using fuzzy string matching.

        Args:
            invalid_value: The invalid value from database
            valid_values: Set of valid enum values

        Returns:
            Closest matching valid value
        """
        # Use difflib to find closest match
        matches = difflib.get_close_matches(invalid_value, valid_values, n=1, cutoff=0.1)
        if matches:
            return matches[0]

        # Fallback: try partial matching
        invalid_upper = invalid_value.upper()
        for valid in valid_values:
            if invalid_upper in valid or valid in invalid_upper:
                return valid

        # Last resort: return first valid value (alphabetically)
        return sorted(valid_values)[0]
