"""Structured edit operations for large files

Stage 2: Enables modifying files of any size by using targeted operations
instead of full-file replacement.

Per IMPLEMENTATION_PLAN3.md Phase 1
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class EditOperationType(str, Enum):
    """Types of edit operations"""

    INSERT = "insert"  # Insert new lines at a position
    REPLACE = "replace"  # Replace a range of lines
    DELETE = "delete"  # Delete a range of lines
    APPEND = "append"  # Append lines to end of file
    PREPEND = "prepend"  # Prepend lines to start of file


@dataclass
class EditOperation:
    """A single edit operation on a file

    Examples:
        # Insert new lines
        EditOperation(
            type=EditOperationType.INSERT,
            file_path="src/example.py",
            line=100,
            content="new_function()\n"
        )

        # Replace existing lines
        EditOperation(
            type=EditOperationType.REPLACE,
            file_path="src/example.py",
            start_line=50,
            end_line=55,
            content="updated code\n"
        )

        # Delete lines
        EditOperation(
            type=EditOperationType.DELETE,
            file_path="src/example.py",
            start_line=200,
            end_line=210
        )
    """

    type: EditOperationType
    file_path: str

    # For INSERT, APPEND, PREPEND
    line: Optional[int] = None
    content: Optional[str] = None

    # For REPLACE, DELETE
    start_line: Optional[int] = None
    end_line: Optional[int] = None

    # Context for validation (optional)
    context_before: Optional[str] = None  # Lines before the edit
    context_after: Optional[str] = None  # Lines after the edit

    def validate(self) -> Tuple[bool, str]:
        """Validate operation has required fields

        Returns:
            (is_valid, error_message)
        """
        if self.type == EditOperationType.INSERT:
            if self.line is None or self.content is None:
                return False, "INSERT requires 'line' and 'content'"

        elif self.type == EditOperationType.REPLACE:
            if self.start_line is None or self.end_line is None or self.content is None:
                return False, "REPLACE requires 'start_line', 'end_line', and 'content'"
            if self.start_line > self.end_line:
                return False, f"start_line ({self.start_line}) > end_line ({self.end_line})"

        elif self.type == EditOperationType.DELETE:
            if self.start_line is None or self.end_line is None:
                return False, "DELETE requires 'start_line' and 'end_line'"
            if self.start_line > self.end_line:
                return False, f"start_line ({self.start_line}) > end_line ({self.end_line})"

        elif self.type in (EditOperationType.APPEND, EditOperationType.PREPEND):
            if self.content is None:
                return False, f"{self.type} requires 'content'"

        return True, ""


@dataclass
class StructuredEditResult:
    """Result of applying structured edits"""

    success: bool
    operations_applied: int
    operations_failed: int
    error_message: Optional[str] = None
    failed_operations: List[Tuple["EditOperation", str]] = field(default_factory=list)


@dataclass
class EditPlan:
    """A plan containing multiple edit operations

    Operations are applied in order. The system validates:
    1. No overlapping edits
    2. Line numbers are valid
    3. Context matches (if provided)
    """

    summary: str  # Human-readable description of changes
    operations: List[EditOperation]

    def validate(self) -> Tuple[bool, str]:
        """Validate the entire edit plan

        Returns:
            (is_valid, error_message)
        """
        if not self.operations:
            return False, "Edit plan has no operations"

        # Validate each operation
        for i, op in enumerate(self.operations):
            is_valid, error = op.validate()
            if not is_valid:
                return False, f"Operation {i}: {error}"

        # Check for overlapping edits on same file
        file_ranges = {}  # file_path -> [(start, end), ...]
        for i, op in enumerate(self.operations):
            if op.type in (EditOperationType.REPLACE, EditOperationType.DELETE):
                if op.file_path not in file_ranges:
                    file_ranges[op.file_path] = []

                new_range = (op.start_line, op.end_line)

                # Check for overlap with existing ranges
                for existing_range in file_ranges[op.file_path]:
                    if self._ranges_overlap(new_range, existing_range):
                        return (
                            False,
                            f"Operation {i} overlaps with previous operation on {op.file_path}",
                        )

                file_ranges[op.file_path].append(new_range)

        return True, ""

    @staticmethod
    def _ranges_overlap(range1: Tuple[int, int], range2: Tuple[int, int]) -> bool:
        """Check if two line ranges overlap"""
        start1, end1 = range1
        start2, end2 = range2
        return not (end1 < start2 or end2 < start1)


class StructuredEditApplicator:
    """Applies structured edit operations to files

    This is the core engine for Stage 2. It takes an EditPlan and applies
    each operation safely, with validation and rollback support.
    """

    def __init__(self, workspace: Path):
        """Initialize applicator

        Args:
            workspace: Workspace root path
        """
        self.workspace = workspace

    def apply_edit_plan(
        self, plan: EditPlan, file_contents: Dict[str, str], dry_run: bool = False
    ) -> StructuredEditResult:
        """Apply an edit plan to files

        Args:
            plan: EditPlan with operations to apply
            file_contents: Dict of {file_path: current_content}
            dry_run: If True, validate but don't actually modify files

        Returns:
            StructuredEditResult with success status and details
        """
        # Validate plan
        is_valid, error = plan.validate()
        if not is_valid:
            return StructuredEditResult(
                success=False,
                operations_applied=0,
                operations_failed=len(plan.operations),
                error_message=f"Invalid edit plan: {error}",
            )

        # Group operations by file
        operations_by_file = {}
        for op in plan.operations:
            if op.file_path not in operations_by_file:
                operations_by_file[op.file_path] = []
            operations_by_file[op.file_path].append(op)

        # Apply operations file by file
        applied = 0
        failed = 0
        failed_ops = []
        modified_contents = {}

        for file_path, ops in operations_by_file.items():
            # Get current content.
            #
            # NOTE: file_contents represents "context" loaded for the Builder; it may omit files due to
            # scope limits, and it will never include newly-created files. Structured edits must still be
            # applicable in these cases, so we fall back to reading from disk (or empty content if the file
            # does not yet exist).
            if file_path in file_contents:
                current_content = file_contents[file_path]
            else:
                # Basic path safety: only allow relative paths inside the workspace.
                rel = Path(file_path)
                if rel.is_absolute() or ".." in rel.parts:
                    error = f"Unsafe file path: {file_path}"
                    logger.error(f"[StructuredEdit] {error}")
                    failed += len(ops)
                    failed_ops.extend([(op, error) for op in ops])
                    continue

                full_path = self.workspace / rel
                if full_path.exists():
                    try:
                        current_content = full_path.read_text(encoding="utf-8")
                    except Exception as e:
                        error = f"Failed to read {file_path}: {e}"
                        logger.error(f"[StructuredEdit] {error}")
                        failed += len(ops)
                        failed_ops.extend([(op, error) for op in ops])
                        continue
                else:
                    # New file - start from empty content.
                    current_content = ""

            # Sort operations by line number (apply from bottom to top to preserve line numbers)
            sorted_ops = self._sort_operations(ops)

            # Apply operations
            try:
                new_content = self._apply_operations_to_content(
                    current_content, sorted_ops, file_path
                )
                modified_contents[file_path] = new_content
                applied += len(ops)
            except Exception as e:
                error = f"Failed to apply operations: {str(e)}"
                logger.error(f"[StructuredEdit] {error}")
                failed += len(ops)
                failed_ops.extend([(op, error) for op in ops])

        # If not dry run, write modified contents
        if not dry_run and modified_contents:
            for file_path, content in modified_contents.items():
                try:
                    # Safety check: ensure file_path is a string, not a list
                    if not isinstance(file_path, str):
                        logger.error(
                            f"[StructuredEdit] Invalid file_path type: {type(file_path)}, skipping"
                        )
                        continue
                    full_path = self.workspace / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    logger.info(
                        f"[StructuredEdit] Applied {len(operations_by_file[file_path])} operations to {file_path}"
                    )
                except Exception as e:
                    logger.error(f"[StructuredEdit] Failed to write {file_path}: {e}")
                    # Mark all operations for this file as failed
                    failed += len(operations_by_file[file_path])
                    applied -= len(operations_by_file[file_path])

        success = failed == 0
        return StructuredEditResult(
            success=success,
            operations_applied=applied,
            operations_failed=failed,
            error_message=None if success else f"{failed} operations failed",
            failed_operations=failed_ops,
        )

    def _sort_operations(self, operations: List[EditOperation]) -> List[EditOperation]:
        """Sort operations to apply from bottom to top

        This preserves line numbers as we apply operations.
        """

        def get_sort_key(op: EditOperation) -> float:
            if op.type == EditOperationType.APPEND:
                return float("inf")  # Apply last
            elif op.type == EditOperationType.PREPEND:
                return 0.0  # Apply first
            elif op.type == EditOperationType.INSERT:
                return float(op.line) if op.line else 0.0
            else:  # REPLACE, DELETE
                return float(op.start_line) if op.start_line else 0.0

        # Sort in reverse order (bottom to top)
        return sorted(operations, key=get_sort_key, reverse=True)

    def _apply_operations_to_content(
        self, content: str, operations: List[EditOperation], file_path: str
    ) -> str:
        """Apply operations to content string

        Args:
            content: Original file content
            operations: Sorted list of operations (bottom to top)
            file_path: File path (for error messages)

        Returns:
            Modified content
        """
        lines = content.split("\n")

        for op in operations:
            if op.type == EditOperationType.INSERT:
                # Insert at line number (1-indexed)
                if op.line is None:
                    raise ValueError("INSERT operation missing 'line'")
                if op.line < 1 or op.line > len(lines) + 1:
                    raise ValueError(
                        f"INSERT line {op.line} out of range (file has {len(lines)} lines)"
                    )

                new_lines = op.content.rstrip("\n").split("\n") if op.content else []
                lines[op.line - 1 : op.line - 1] = new_lines

            elif op.type == EditOperationType.REPLACE:
                # Replace lines (1-indexed, inclusive)
                if op.start_line is None or op.end_line is None:
                    raise ValueError("REPLACE operation missing 'start_line' or 'end_line'")
                if op.start_line < 1 or op.end_line > len(lines):
                    raise ValueError(
                        f"REPLACE range {op.start_line}-{op.end_line} out of range (file has {len(lines)} lines)"
                    )

                # Validate context if provided
                if op.context_before:
                    actual_before = "\n".join(lines[max(0, op.start_line - 4) : op.start_line - 1])
                    if op.context_before.strip() not in actual_before:
                        raise ValueError(f"Context mismatch before line {op.start_line}")

                if op.context_after:
                    actual_after = "\n".join(lines[op.end_line : min(len(lines), op.end_line + 3)])
                    if op.context_after.strip() not in actual_after:
                        raise ValueError(f"Context mismatch after line {op.end_line}")

                # Replace the range
                new_lines = op.content.rstrip("\n").split("\n") if op.content else []
                lines[op.start_line - 1 : op.end_line] = new_lines

            elif op.type == EditOperationType.DELETE:
                # Delete lines (1-indexed, inclusive)
                if op.start_line is None or op.end_line is None:
                    raise ValueError("DELETE operation missing 'start_line' or 'end_line'")
                if op.start_line < 1 or op.end_line > len(lines):
                    raise ValueError(
                        f"DELETE range {op.start_line}-{op.end_line} out of range (file has {len(lines)} lines)"
                    )

                del lines[op.start_line - 1 : op.end_line]

            elif op.type == EditOperationType.APPEND:
                # Append to end
                new_lines = op.content.rstrip("\n").split("\n") if op.content else []
                lines.extend(new_lines)

            elif op.type == EditOperationType.PREPEND:
                # Prepend to start
                new_lines = op.content.rstrip("\n").split("\n") if op.content else []
                lines = new_lines + lines

        return "\n".join(lines)
