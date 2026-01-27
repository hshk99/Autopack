"""
Break-glass database repair tool using raw SQL to bypass ORM.

When database contains invalid enum values, the ORM cannot read those rows.
This tool uses raw SQL to diagnose and repair schema violations.

Per BUILD-130 Phase 1: Break-Glass Repair implementation.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import create_engine, text

from autopack.schema_validator import SchemaValidationResult, SchemaValidator

logger = logging.getLogger(__name__)


class BreakGlassRepair:
    """
    Database repair tool using raw SQL to bypass ORM.

    Use this when:
    - API returns 500 errors due to invalid enum values
    - ORM cannot deserialize database rows
    - Schema drift has occurred between code and database
    """

    def __init__(self, database_url: str):
        """
        Initialize break-glass repair tool.

        Args:
            database_url: SQLAlchemy database URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.validator = SchemaValidator(database_url)
        # P2.2: Use configured autonomous_runs_dir
        from .config import settings

        self.repair_log_path = f"{settings.autonomous_runs_dir}/break_glass_repairs.jsonl"

    def diagnose(self) -> SchemaValidationResult:
        """
        Run diagnostics without making changes.

        Returns:
            SchemaValidationResult with all detected issues
        """
        logger.info("[BreakGlass] Running diagnostic scan...")
        result = self.validator.validate_on_startup()

        if result.is_valid:
            logger.info("[BreakGlass] ✅ Database schema is valid - no repairs needed")
        else:
            logger.error(f"[BreakGlass] ❌ Found {len(result.errors)} schema violations")
            logger.info("[BreakGlass] Run with --repair to apply fixes")

            # Print summary
            self._print_diagnosis_summary(result)

        return result

    def repair(self, result: SchemaValidationResult, auto_approve: bool = False) -> bool:
        """
        Apply repairs from validation result.

        Args:
            result: Validation result with errors and repair SQL
            auto_approve: If True, apply all repairs without confirmation

        Returns:
            True if all repairs succeeded, False otherwise
        """
        if result.is_valid:
            logger.info("[BreakGlass] No repairs needed")
            return True

        logger.info(f"[BreakGlass] Applying {len(result.errors)} repairs...")

        success_count = 0
        failed_count = 0

        for i, error in enumerate(result.errors, 1):
            logger.info(
                f"[BreakGlass] Repair {i}/{len(result.errors)}: {error.table}.{error.column}"
            )
            logger.info(
                f"[BreakGlass]   Invalid value: '{error.invalid_value}' → '{error.suggested_fix}'"
            )
            logger.info(f"[BreakGlass]   Affected rows: {error.affected_rows}")
            logger.info(f"[BreakGlass]   SQL: {error.repair_sql}")

            # Ask for confirmation unless auto-approve
            if not auto_approve:
                confirm = input("\n  Apply this repair? [y/N]: ").strip().lower()
                if confirm != "y":
                    logger.info("[BreakGlass]   Skipped")
                    continue

            # Apply repair
            try:
                with self.engine.connect() as conn:
                    # Begin transaction
                    trans = conn.begin()
                    try:
                        # Execute repair SQL
                        conn.execute(text(error.repair_sql))

                        # Update timestamp
                        timestamp_sql = f"UPDATE {error.table} SET updated_at=:ts WHERE {error.column}=:new_value"
                        conn.execute(
                            text(timestamp_sql),
                            {"ts": datetime.now().isoformat(), "new_value": error.suggested_fix},
                        )

                        trans.commit()
                        logger.info("[BreakGlass]   ✅ Repair applied successfully")
                        success_count += 1

                        # Log repair
                        self._log_repair(error)

                    except Exception as e:
                        trans.rollback()
                        logger.error(f"[BreakGlass]   ❌ Repair failed: {e}")
                        failed_count += 1

            except Exception as e:
                logger.error(f"[BreakGlass]   ❌ Failed to connect: {e}")
                failed_count += 1

        logger.info(
            f"[BreakGlass] Repairs complete: {success_count} succeeded, {failed_count} failed"
        )
        return failed_count == 0

    def _print_diagnosis_summary(self, result: SchemaValidationResult):
        """Print human-readable summary of diagnosis"""
        print("\n" + "=" * 80)
        print("DATABASE SCHEMA DIAGNOSIS")
        print("=" * 80)

        for error in result.errors:
            print(f"\n❌ {error.table}.{error.column}")
            print(f"   Invalid value: '{error.invalid_value}'")
            print(f"   Suggested fix: '{error.suggested_fix}'")
            print(
                f"   Affected rows: {len(error.affected_rows)} ({', '.join(error.affected_rows[:5])}{'...' if len(error.affected_rows) > 5 else ''})"
            )
            print("   Repair SQL:")
            print(f"      {error.repair_sql}")

        for warning in result.warnings:
            print(f"\n⚠️  {warning}")

        print("\n" + "=" * 80)
        print(f"SUMMARY: {len(result.errors)} errors, {len(result.warnings)} warnings")
        print("=" * 80 + "\n")

    def _log_repair(self, error):
        """Log repair to JSONL file for audit trail"""
        import os

        os.makedirs(os.path.dirname(self.repair_log_path), exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "table": error.table,
            "column": error.column,
            "invalid_value": error.invalid_value,
            "new_value": error.suggested_fix,
            "affected_rows": error.affected_rows,
            "repair_sql": error.repair_sql,
        }

        with open(self.repair_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")

        logger.info(f"[BreakGlass] Repair logged to {self.repair_log_path}")
