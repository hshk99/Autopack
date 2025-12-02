# Implementation Plan 3: Stage 2 - Structured Edits for Large Files

**Date**: December 2, 2025  
**Status**: Design phase  
**Priority**: HIGH - Enables modifying files >1000 lines  
**Dependencies**: IMPLEMENTATION_PLAN2.md must be completed first  
**Estimated Total Time**: 20-25 hours

---

## Executive Summary

This plan implements **Stage 2: Structured Edits**, which enables Autopack to safely modify files of any size (including files >1000 lines) by using targeted, region-based edits instead of full-file replacement.

**Problem**: After IMPLEMENTATION_PLAN2.md, Autopack cannot modify files >1000 lines (they fail safely but cannot be modified).

**Solution**: Implement a structured edit system where the LLM outputs specific operations (insert, replace, delete) at specific line ranges, rather than outputting complete file content.

---

## Why Stage 2 is Needed

### Current Limitations (After PLAN2)

| File Size | Can Read? | Can Modify? | Why? |
|-----------|-----------|-------------|------|
| ≤500 lines | ✅ | ✅ Full-file mode | Safe: LLM can output complete content |
| 501-1000 lines | ✅ | ✅ Diff mode | Workaround: LLM generates git diff |
| >1000 lines | ✅ | ❌ **Cannot modify** | Safety: Would truncate in full-file mode |

### What Stage 2 Enables

| File Size | Can Read? | Can Modify? | How? |
|-----------|-----------|-------------|------|
| Any size | ✅ | ✅ **Structured edits** | LLM outputs targeted operations |

**Example**: Modify `autonomous_executor.py` (2425 lines)
- Instead of: Output all 2425 lines (truncates)
- Stage 2: Output "Insert 5 lines at line 500" (safe)

---

## Architecture Overview

### Three Output Modes

After Stage 2, Autopack will support three modes:

```
┌─────────────────────────────────────────────────────────────┐
│                    File Size Decision Tree                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Is file ≤500 lines?
                              │
                    ┌─────────┴─────────┐
                   YES                  NO
                    │                    │
                    ▼                    ▼
            ┌──────────────┐    Is file ≤1000 lines?
            │  FULL-FILE   │             │
            │     MODE     │    ┌────────┴────────┐
            │  (Bucket A)  │   YES               NO
            └──────────────┘    │                 │
                                ▼                 ▼
                        ┌──────────────┐  ┌──────────────┐
                        │  DIFF MODE   │  │  STRUCTURED  │
                        │  (Bucket B)  │  │  EDIT MODE   │
                        │   Fallback   │  │  (Bucket C)  │
                        └──────────────┘  │   Stage 2    │
                                          └──────────────┘
```

---

## Implementation Phases

### 🔴 Phase 1: Core Data Structures (CRITICAL - Do First)

**Estimated Time**: 3-4 hours  
**Dependencies**: IMPLEMENTATION_PLAN2.md completed  
**Blocking**: All other phases

#### 1.1: Define Structured Edit Schema

**File**: `src/autopack/structured_edits.py` (NEW)

**Implementation**:

```python
"""Structured edit operations for large files

Stage 2: Enables modifying files of any size by using targeted operations
instead of full-file replacement.
"""

from dataclasses import dataclass
from typing import Literal, List, Optional
from enum import Enum


class EditOperationType(str, Enum):
    """Types of edit operations"""
    INSERT = "insert"           # Insert new lines at a position
    REPLACE = "replace"         # Replace a range of lines
    DELETE = "delete"           # Delete a range of lines
    APPEND = "append"           # Append lines to end of file
    PREPEND = "prepend"         # Prepend lines to start of file


@dataclass
class EditOperation:
    """A single edit operation on a file
    
    Examples:
        # Insert new lines
        EditOperation(
            type=EditOperationType.INSERT,
            file_path="src/example.py",
            line=100,
            content="new_function()\\n"
        )
        
        # Replace existing lines
        EditOperation(
            type=EditOperationType.REPLACE,
            file_path="src/example.py",
            start_line=50,
            end_line=55,
            content="updated code\\n"
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
    context_after: Optional[str] = None   # Lines after the edit
    
    def validate(self) -> tuple[bool, str]:
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
    failed_operations: List[tuple[EditOperation, str]] = None  # (operation, error)
    
    def __post_init__(self):
        if self.failed_operations is None:
            self.failed_operations = []


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
    
    def validate(self) -> tuple[bool, str]:
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
                        return False, f"Operation {i} overlaps with previous operation on {op.file_path}"
                
                file_ranges[op.file_path].append(new_range)
        
        return True, ""
    
    @staticmethod
    def _ranges_overlap(range1: tuple[int, int], range2: tuple[int, int]) -> bool:
        """Check if two line ranges overlap"""
        start1, end1 = range1
        start2, end2 = range2
        return not (end1 < start2 or end2 < start1)
```

**Testing**:
- [ ] Unit test: EditOperation validation
- [ ] Unit test: EditPlan validation
- [ ] Unit test: Overlapping edit detection
- [ ] Unit test: Invalid line ranges

---

#### 1.2: Create Edit Applicator

**File**: `src/autopack/structured_edits.py` (continued)

**Implementation**:

```python
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


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
        self,
        plan: EditPlan,
        file_contents: Dict[str, str],
        dry_run: bool = False
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
                error_message=f"Invalid edit plan: {error}"
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
            # Get current content
            if file_path not in file_contents:
                error = f"File not in context: {file_path}"
                logger.error(f"[StructuredEdit] {error}")
                failed += len(ops)
                failed_ops.extend([(op, error) for op in ops])
                continue
            
            current_content = file_contents[file_path]
            
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
                    full_path = self.workspace / file_path
                    full_path.write_text(content, encoding='utf-8')
                    logger.info(f"[StructuredEdit] Applied {len(operations_by_file[file_path])} operations to {file_path}")
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
            failed_operations=failed_ops
        )
    
    def _sort_operations(self, operations: List[EditOperation]) -> List[EditOperation]:
        """Sort operations to apply from bottom to top
        
        This preserves line numbers as we apply operations.
        """
        def get_sort_key(op: EditOperation) -> int:
            if op.type == EditOperationType.APPEND:
                return float('inf')  # Apply last
            elif op.type == EditOperationType.PREPEND:
                return 0  # Apply first
            elif op.type == EditOperationType.INSERT:
                return op.line
            else:  # REPLACE, DELETE
                return op.start_line
        
        # Sort in reverse order (bottom to top)
        return sorted(operations, key=get_sort_key, reverse=True)
    
    def _apply_operations_to_content(
        self,
        content: str,
        operations: List[EditOperation],
        file_path: str
    ) -> str:
        """Apply operations to content string
        
        Args:
            content: Original file content
            operations: Sorted list of operations (bottom to top)
            file_path: File path (for error messages)
            
        Returns:
            Modified content
        """
        lines = content.split('\n')
        
        for op in operations:
            if op.type == EditOperationType.INSERT:
                # Insert at line number (1-indexed)
                if op.line < 1 or op.line > len(lines) + 1:
                    raise ValueError(f"INSERT line {op.line} out of range (file has {len(lines)} lines)")
                
                new_lines = op.content.rstrip('\n').split('\n')
                lines.insert(op.line - 1, *new_lines)
            
            elif op.type == EditOperationType.REPLACE:
                # Replace lines (1-indexed, inclusive)
                if op.start_line < 1 or op.end_line > len(lines):
                    raise ValueError(f"REPLACE range {op.start_line}-{op.end_line} out of range (file has {len(lines)} lines)")
                
                # Validate context if provided
                if op.context_before:
                    actual_before = '\n'.join(lines[max(0, op.start_line - 4):op.start_line - 1])
                    if op.context_before.strip() not in actual_before:
                        raise ValueError(f"Context mismatch before line {op.start_line}")
                
                if op.context_after:
                    actual_after = '\n'.join(lines[op.end_line:min(len(lines), op.end_line + 3)])
                    if op.context_after.strip() not in actual_after:
                        raise ValueError(f"Context mismatch after line {op.end_line}")
                
                # Replace the range
                new_lines = op.content.rstrip('\n').split('\n')
                lines[op.start_line - 1:op.end_line] = new_lines
            
            elif op.type == EditOperationType.DELETE:
                # Delete lines (1-indexed, inclusive)
                if op.start_line < 1 or op.end_line > len(lines):
                    raise ValueError(f"DELETE range {op.start_line}-{op.end_line} out of range (file has {len(lines)} lines)")
                
                del lines[op.start_line - 1:op.end_line]
            
            elif op.type == EditOperationType.APPEND:
                # Append to end
                new_lines = op.content.rstrip('\n').split('\n')
                lines.extend(new_lines)
            
            elif op.type == EditOperationType.PREPEND:
                # Prepend to start
                new_lines = op.content.rstrip('\n').split('\n')
                lines = new_lines + lines
        
        return '\n'.join(lines)
```

**Testing**:
- [ ] Unit test: INSERT operation
- [ ] Unit test: REPLACE operation
- [ ] Unit test: DELETE operation
- [ ] Unit test: APPEND operation
- [ ] Unit test: PREPEND operation
- [ ] Unit test: Multiple operations on same file
- [ ] Unit test: Context validation
- [ ] Unit test: Out-of-range line numbers

---

### 🟡 Phase 2: LLM Integration (HIGH PRIORITY)

**Estimated Time**: 4-5 hours  
**Dependencies**: Phase 1  
**Blocking**: Phase 3, 4

#### 2.1: Create Structured Edit System Prompt

**File**: `src/autopack/anthropic_clients.py`

**Update**: `_build_system_prompt()` method

**Changes**:

```python
def _build_system_prompt(self, mode: str = "full_file") -> str:
    """Build system prompt based on output mode
    
    Args:
        mode: One of "full_file", "diff", "structured_edit"
        
    Returns:
        System prompt string
    """
    
    if mode == "full_file":
        # ... existing full-file prompt ...
    
    elif mode == "diff":
        # ... existing diff prompt ...
    
    elif mode == "structured_edit":
        # NEW: Structured edit mode for large files (Stage 2)
        return """You are a code modification assistant. Generate targeted edit operations for large files.

Your task is to output a structured JSON edit plan with specific operations.

Output format:
{
  "summary": "Brief description of changes",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/example.py",
      "line": 100,
      "content": "new code here\\n"
    },
    {
      "type": "replace",
      "file_path": "src/example.py",
      "start_line": 50,
      "end_line": 55,
      "content": "updated code here\\n"
    },
    {
      "type": "delete",
      "file_path": "src/example.py",
      "start_line": 200,
      "end_line": 210
    }
  ]
}

Operation Types:
1. "insert" - Insert new lines at a specific position
   Required: type, file_path, line, content
   
2. "replace" - Replace a range of lines
   Required: type, file_path, start_line, end_line, content
   Optional: context_before, context_after (for validation)
   
3. "delete" - Delete a range of lines
   Required: type, file_path, start_line, end_line
   
4. "append" - Append lines to end of file
   Required: type, file_path, content
   
5. "prepend" - Prepend lines to start of file
   Required: type, file_path, content

CRITICAL RULES:
- Line numbers are 1-indexed (first line is line 1)
- Ranges are inclusive (start_line to end_line, both included)
- Content should include newlines (\\n) where appropriate
- Do NOT output full file contents
- Do NOT use ellipses (...) or placeholders
- Make targeted, minimal changes
- Include context_before and context_after for validation when replacing critical sections

Example - Add a new function:
{
  "summary": "Add telemetry recording function",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 500,
      "content": "    def record_telemetry(self, event):\\n        self.telemetry.record_event(event)\\n"
    }
  ]
}

Example - Update existing function:
{
  "summary": "Update execute_phase to use new config",
  "operations": [
    {
      "type": "replace",
      "file_path": "src/autopack/autonomous_executor.py",
      "start_line": 1200,
      "end_line": 1205,
      "content": "    def execute_phase(self, phase_id, config):\\n        # Updated implementation\\n        pass\\n",
      "context_before": "    # Phase execution",
      "context_after": "    # Continue with"
    }
  ]
}

Do NOT:
- Output complete file contents
- Use placeholders or ellipses
- Make unnecessary changes
- Modify lines outside the specified ranges
"""
    
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

**Testing**:
- [ ] Unit test: Structured edit prompt is returned
- [ ] Verify prompt is clear and unambiguous

---

#### 2.2: Create Structured Edit Parser

**File**: `src/autopack/anthropic_clients.py`

**New Method**: `_parse_structured_edit_output()`

**Implementation**:

```python
def _parse_structured_edit_output(
    self,
    content: str,
    response,
    model: str,
    file_context: Optional[Dict],
    phase_spec: Dict,
    config: BuilderOutputConfig = None
) -> BuilderResult:
    """Parse LLM's structured edit JSON output
    
    Args:
        content: LLM response text (expected to be JSON)
        response: Full API response object
        model: Model identifier
        file_context: Dict of {file_path: file_content}
        phase_spec: Phase specification
        config: Builder configuration
        
    Returns:
        BuilderResult with edit plan
    """
    import json
    from src.autopack.structured_edits import EditPlan, EditOperation, EditOperationType
    
    if config is None:
        config = BuilderOutputConfig()
    
    try:
        # Parse JSON
        result_json = None
        try:
            result_json = json.loads(content.strip())
        except json.JSONDecodeError:
            # Try extracting from markdown code fence
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
                    result_json = json.loads(json_str)
        
        if not result_json:
            error_msg = "LLM output invalid format - expected JSON with 'operations' array"
            logger.error(f"{error_msg}\\nFirst 500 chars: {content[:500]}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                error=error_msg
            )
        
        # Extract summary and operations
        summary = result_json.get("summary", "Structured edits")
        operations_json = result_json.get("operations", [])
        
        if not operations_json:
            error_msg = "LLM returned empty operations array"
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                error=error_msg
            )
        
        # Parse operations
        operations = []
        for i, op_json in enumerate(operations_json):
            try:
                op = EditOperation(
                    type=EditOperationType(op_json.get("type")),
                    file_path=op_json.get("file_path"),
                    line=op_json.get("line"),
                    content=op_json.get("content"),
                    start_line=op_json.get("start_line"),
                    end_line=op_json.get("end_line"),
                    context_before=op_json.get("context_before"),
                    context_after=op_json.get("context_after")
                )
                
                # Validate operation
                is_valid, error = op.validate()
                if not is_valid:
                    error_msg = f"Operation {i} invalid: {error}"
                    logger.error(f"[Builder] {error_msg}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=error_msg
                    )
                
                operations.append(op)
            
            except Exception as e:
                error_msg = f"Failed to parse operation {i}: {str(e)}"
                logger.error(f"[Builder] {error_msg}")
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
                )
        
        # Create edit plan
        edit_plan = EditPlan(summary=summary, operations=operations)
        
        # Validate plan
        is_valid, error = edit_plan.validate()
        if not is_valid:
            error_msg = f"Invalid edit plan: {error}"
            logger.error(f"[Builder] {error_msg}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                error=error_msg
            )
        
        # Store edit plan in BuilderResult (we'll apply it in governed_apply.py)
        logger.info(f"[Builder] Generated structured edit plan with {len(operations)} operations")
        
        return BuilderResult(
            success=True,
            patch_content="",  # No patch content for structured edits
            builder_messages=[f"Generated {len(operations)} edit operations"],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            model_used=model,
            edit_plan=edit_plan  # NEW: Store edit plan
        )
    
    except Exception as e:
        logger.error(f"[Builder] Error parsing structured edit output: {e}")
        return BuilderResult(
            success=False,
            patch_content="",
            builder_messages=[str(e)],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            model_used=model,
            error=str(e)
        )
```

**Testing**:
- [ ] Unit test: Parse valid structured edit JSON
- [ ] Unit test: Handle invalid JSON
- [ ] Unit test: Validate operations
- [ ] Unit test: Detect overlapping edits

---

#### 2.3: Update BuilderResult to Support Edit Plans

**File**: `src/autopack/types.py` (or wherever BuilderResult is defined)

**Changes**:

```python
from dataclasses import dataclass
from typing import Optional, List
from src.autopack.structured_edits import EditPlan

@dataclass
class BuilderResult:
    """Result from Builder execution"""
    success: bool
    patch_content: str  # For full-file and diff modes
    builder_messages: List[str]
    tokens_used: int
    model_used: str
    error: Optional[str] = None
    
    # NEW: For structured edit mode (Stage 2)
    edit_plan: Optional[EditPlan] = None
    
    @property
    def is_structured_edit(self) -> bool:
        """Check if this is a structured edit result"""
        return self.edit_plan is not None
```

**Testing**:
- [ ] Unit test: BuilderResult with edit_plan
- [ ] Unit test: is_structured_edit property

---

### 🟡 Phase 3: Integration with Execution Flow (HIGH PRIORITY)

**Estimated Time**: 3-4 hours  
**Dependencies**: Phase 1, 2  
**Blocking**: Phase 4

#### 3.1: Update Pre-Flight Guard to Route to Structured Edit Mode

**File**: `src/autopack/autonomous_executor.py`

**Method**: `execute_phase()`

**Changes**:

```python
def execute_phase(self, phase_id: str, attempt: int = 1) -> bool:
    """Execute a single phase with Builder -> Patch -> CI -> Auditor flow"""
    
    # ... existing phase loading ...
    
    # Pre-flight file size validation
    if self.use_full_file_mode and file_context:
        config = self.builder_output_config
        files = file_context.get("existing_files", file_context)
        
        too_large = []      # Bucket C: >1000 lines
        needs_diff_mode = []  # Bucket B: 500-1000 lines
        
        for file_path, content in files.items():
            if not isinstance(content, str):
                continue
            line_count = content.count('\n') + 1
            
            if line_count > config.max_lines_hard_limit:
                too_large.append((file_path, line_count))
            elif line_count > config.max_lines_for_full_file:
                needs_diff_mode.append((file_path, line_count))
        
        # NEW: For files >1000 lines, use structured edit mode (Stage 2)
        if too_large:
            logger.info(
                f"[{phase_id}] Using structured edit mode for large files: "
                f"{', '.join(p for p, _ in too_large)}"
            )
            
            # Record telemetry
            for file_path, line_count in too_large:
                self.file_size_telemetry.record_event({
                    "run_id": self.run_id,
                    "phase_id": phase_id,
                    "event_type": "bucket_c_structured_edit_mode",
                    "file_path": file_path,
                    "line_count": line_count
                })
            
            # Use structured edit mode
            output_mode = "structured_edit"
        
        # For 500-1000 line files, use diff mode (Bucket B)
        elif needs_diff_mode:
            if config.legacy_diff_fallback_enabled:
                logger.warning(
                    f"[{phase_id}] Using diff mode for medium files: "
                    f"{', '.join(p for p, _ in needs_diff_mode)}"
                )
                output_mode = "diff"
                self.use_full_file_mode = False
            else:
                # Fail if diff mode disabled and no Stage 2
                msg = "; ".join(f"{p} has {n} lines" for p, n in needs_diff_mode)
                logger.error(f"[{phase_id}] Files too large: {msg}")
                return False
        
        # For small files, use full-file mode (Bucket A)
        else:
            output_mode = "full_file"
    else:
        output_mode = "full_file"
    
    # Call Builder with appropriate mode
    builder_result = self.llm_service.execute_builder(
        phase_spec=phase_spec,
        file_context=file_context,
        output_mode=output_mode,  # NEW: Pass mode explicitly
        config=self.builder_output_config,
        # ...
    )
    
    # ... rest of phase execution ...
```

**Testing**:
- [ ] Unit test: Route to structured_edit for >1000 line files
- [ ] Unit test: Route to diff for 500-1000 line files
- [ ] Unit test: Route to full_file for ≤500 line files

---

#### 3.2: Update LlmService to Support Structured Edit Mode

**File**: `src/autopack/llm_service.py`

**Method**: `execute_builder()`

**Changes**:

```python
def execute_builder(
    self,
    phase_spec: Dict,
    file_context: Optional[Dict] = None,
    project_rules: Optional[List] = None,
    run_hints: Optional[List] = None,
    max_tokens: Optional[int] = None,
    output_mode: str = "full_file",  # NEW: Explicit mode parameter
    config: BuilderOutputConfig = None
) -> BuilderResult:
    """Execute Builder to generate code changes
    
    Args:
        phase_spec: Phase specification
        file_context: Repository file context
        project_rules: Persistent learned rules
        run_hints: Within-run hints
        max_tokens: Maximum tokens for response
        output_mode: One of "full_file", "diff", "structured_edit"
        config: Builder configuration
        
    Returns:
        BuilderResult with generated changes
    """
    
    # Select model based on complexity
    model = self.model_router.select_builder_model(
        complexity=phase_spec.get("complexity", "medium"),
        category=phase_spec.get("task_category", "general")
    )
    
    # Call the appropriate client with mode
    if "claude" in model:
        client = self.anthropic_client
        return client.execute_phase(
            phase_spec=phase_spec,
            file_context=file_context,
            project_rules=project_rules,
            run_hints=run_hints,
            max_tokens=max_tokens,
            model=model,
            output_mode=output_mode,  # NEW: Pass mode
            config=config
        )
    # ... other clients ...
```

**Testing**:
- [ ] Unit test: Pass output_mode to client
- [ ] Integration test: Client receives correct mode

---

#### 3.3: Update AnthropicBuilderClient.execute_phase()

**File**: `src/autopack/anthropic_clients.py`

**Method**: `execute_phase()`

**Changes**:

```python
def execute_phase(
    self,
    phase_spec: Dict,
    file_context: Optional[Dict] = None,
    project_rules: Optional[List] = None,
    run_hints: Optional[List] = None,
    max_tokens: Optional[int] = None,
    model: str = "claude-sonnet-4-5",
    output_mode: str = "full_file",  # NEW: Explicit mode parameter
    config: BuilderOutputConfig = None
) -> BuilderResult:
    """Execute Builder to generate code changes"""
    
    if config is None:
        config = BuilderOutputConfig()
    
    # Build system prompt based on mode
    system_prompt = self._build_system_prompt(output_mode)
    
    # Build user prompt (same for all modes, but context differs)
    user_prompt = self._build_user_prompt(
        phase_spec, file_context, project_rules, run_hints, output_mode, config
    )
    
    # Call Anthropic API
    response = self.client.messages.create(
        model=model,
        max_tokens=max_tokens or 8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    # Parse response based on mode
    if output_mode == "full_file":
        return self._parse_full_file_output(...)
    elif output_mode == "diff":
        return self._parse_diff_output(...)
    elif output_mode == "structured_edit":
        return self._parse_structured_edit_output(...)  # NEW
    else:
        raise ValueError(f"Unknown output_mode: {output_mode}")
```

**Testing**:
- [ ] Unit test: Structured edit mode uses correct prompt
- [ ] Unit test: Structured edit mode uses correct parser
- [ ] Integration test: End-to-end structured edit flow

---

### 🟡 Phase 4: Apply Structured Edits (HIGH PRIORITY)

**Estimated Time**: 3-4 hours  
**Dependencies**: Phase 1, 2, 3  
**Blocking**: None

#### 4.1: Update Governed Apply to Handle Structured Edits

**File**: `src/autopack/governed_apply.py`

**New Method**: `apply_structured_edits()`

**Implementation**:

```python
from src.autopack.structured_edits import EditPlan, StructuredEditApplicator

def apply_structured_edits(
    edit_plan: EditPlan,
    file_context: Dict[str, str],
    workspace: Path,
    phase_id: str,
    run_id: str
) -> tuple[bool, str]:
    """Apply structured edit operations to files
    
    Args:
        edit_plan: EditPlan with operations to apply
        file_context: Dict of {file_path: current_content}
        workspace: Workspace root path
        phase_id: Phase identifier (for logging)
        run_id: Run identifier (for logging)
        
    Returns:
        (success, error_message)
    """
    logger.info(f"[{phase_id}] Applying structured edit plan with {len(edit_plan.operations)} operations")
    
    # Create applicator
    applicator = StructuredEditApplicator(workspace)
    
    # Apply edits (dry run first)
    dry_run_result = applicator.apply_edit_plan(edit_plan, file_context, dry_run=True)
    
    if not dry_run_result.success:
        logger.error(f"[{phase_id}] Dry run failed: {dry_run_result.error_message}")
        return False, dry_run_result.error_message
    
    logger.info(f"[{phase_id}] Dry run successful, applying edits...")
    
    # Apply edits for real
    result = applicator.apply_edit_plan(edit_plan, file_context, dry_run=False)
    
    if not result.success:
        logger.error(f"[{phase_id}] Failed to apply edits: {result.error_message}")
        return False, result.error_message
    
    logger.info(f"[{phase_id}] Successfully applied {result.operations_applied} operations")
    return True, ""
```

**Testing**:
- [ ] Unit test: Apply structured edits successfully
- [ ] Unit test: Dry run detects errors
- [ ] Unit test: Rollback on failure
- [ ] Integration test: Full apply flow

---

#### 4.2: Update autonomous_executor.py to Use Structured Edit Apply

**File**: `src/autopack/autonomous_executor.py`

**Method**: `execute_phase()`

**Changes**:

```python
def execute_phase(self, phase_id: str, attempt: int = 1) -> bool:
    """Execute a single phase with Builder -> Patch -> CI -> Auditor flow"""
    
    # ... Builder execution ...
    
    builder_result = self.llm_service.execute_builder(...)
    
    if not builder_result.success:
        # ... handle failure ...
        return False
    
    # Apply changes based on result type
    if builder_result.is_structured_edit:
        # NEW: Apply structured edits (Stage 2)
        logger.info(f"[{phase_id}] Applying structured edits...")
        
        from src.autopack.governed_apply import apply_structured_edits
        
        success, error = apply_structured_edits(
            edit_plan=builder_result.edit_plan,
            file_context=file_context,
            workspace=Path(self.workspace),
            phase_id=phase_id,
            run_id=self.run_id
        )
        
        if not success:
            logger.error(f"[{phase_id}] Failed to apply structured edits: {error}")
            self._record_phase_failure(phase_id, "structured_edit_apply_failed", error)
            return False
        
        logger.info(f"[{phase_id}] Structured edits applied successfully")
    
    else:
        # Existing: Apply patch using git apply
        logger.info(f"[{phase_id}] Applying patch...")
        # ... existing patch application logic ...
    
    # ... CI checks, auditor, etc. ...
```

**Testing**:
- [ ] Integration test: Full phase execution with structured edits
- [ ] Integration test: Verify files are modified correctly
- [ ] Integration test: CI runs after structured edits

---

### 🟢 Phase 5: User Prompt Updates (MEDIUM PRIORITY)

**Estimated Time**: 2-3 hours  
**Dependencies**: Phase 1, 2  
**Blocking**: None

#### 5.1: Update _build_user_prompt() for Structured Edit Mode

**File**: `src/autopack/anthropic_clients.py`

**Method**: `_build_user_prompt()`

**Changes**:

```python
def _build_user_prompt(
    self,
    phase_spec: Dict,
    file_context: Optional[Dict],
    project_rules: Optional[List],
    run_hints: Optional[List],
    output_mode: str = "full_file",  # NEW: Mode parameter
    config: BuilderOutputConfig = None
) -> str:
    """Build user prompt with phase details and file context"""
    
    if config is None:
        config = BuilderOutputConfig()
    
    prompt_parts = [
        "# Phase Specification",
        f"Description: {phase_spec.get('description', '')}",
        # ... phase details ...
    ]
    
    if file_context:
        files = file_context.get("existing_files", file_context)
        
        if output_mode == "structured_edit":
            # NEW: For structured edit mode, show file structure and line numbers
            prompt_parts.append("\n# Files in Context (for structured edits):")
            prompt_parts.append("Use line numbers to specify where to make changes.")
            prompt_parts.append("Line numbers are 1-indexed (first line is line 1).\n")
            
            for file_path, content in files.items():
                if not isinstance(content, str):
                    continue
                
                line_count = content.count('\n') + 1
                prompt_parts.append(f"\n## {file_path} ({line_count} lines)")
                
                # Show file with line numbers
                lines = content.split('\n')
                
                # For very large files, show first 100, middle section, last 100
                if line_count > 300:
                    # First 100 lines
                    for i, line in enumerate(lines[:100], 1):
                        prompt_parts.append(f"{i:4d} | {line}")
                    
                    prompt_parts.append(f"\n... [{line_count - 200} lines omitted] ...\n")
                    
                    # Last 100 lines
                    for i, line in enumerate(lines[-100:], line_count - 99):
                        prompt_parts.append(f"{i:4d} | {line}")
                else:
                    # Show all lines with numbers
                    for i, line in enumerate(lines, 1):
                        prompt_parts.append(f"{i:4d} | {line}")
        
        elif output_mode == "full_file":
            # Existing: Full-file mode prompt (from PLAN2)
            # ... existing logic ...
        
        elif output_mode == "diff":
            # Existing: Diff mode prompt
            # ... existing logic ...
    
    return "\n".join(prompt_parts)
```

**Testing**:
- [ ] Unit test: Structured edit prompt includes line numbers
- [ ] Unit test: Large files show first/last sections
- [ ] Unit test: Small files show all lines

---

### 🟢 Phase 6: Testing (MEDIUM PRIORITY)

**Estimated Time**: 4-5 hours  
**Dependencies**: Phases 1-5  
**Blocking**: None

#### 6.1: End-to-End Tests

**File**: `tests/test_structured_edits.py` (NEW)

**Tests to Implement**:

```python
import pytest
from pathlib import Path
from src.autopack.structured_edits import (
    EditPlan, EditOperation, EditOperationType, StructuredEditApplicator
)
from src.autopack.autonomous_executor import AutonomousExecutor

def test_insert_operation():
    """Test INSERT operation adds lines at correct position"""
    # ... implementation ...

def test_replace_operation():
    """Test REPLACE operation replaces correct line range"""
    # ... implementation ...

def test_delete_operation():
    """Test DELETE operation removes correct lines"""
    # ... implementation ...

def test_multiple_operations_same_file():
    """Test multiple operations applied in correct order"""
    # ... implementation ...

def test_overlapping_edits_rejected():
    """Test that overlapping edits are rejected during validation"""
    # ... implementation ...

def test_context_validation():
    """Test that context_before and context_after are validated"""
    # ... implementation ...

def test_large_file_modification():
    """Test modifying a 2000-line file with structured edits"""
    # Create 2000-line file
    # Apply structured edits
    # Verify changes are correct
    # ... implementation ...

def test_end_to_end_structured_edit_phase():
    """Test full phase execution with structured edit mode"""
    # Create executor
    # Create phase with >1000 line file
    # Execute phase
    # Verify structured edit mode was used
    # Verify file was modified correctly
    # ... implementation ...

def test_structured_edit_with_ci():
    """Test that CI runs after structured edits"""
    # ... implementation ...

def test_structured_edit_rollback_on_ci_failure():
    """Test that changes are rolled back if CI fails"""
    # ... implementation ...
```

**Testing Checklist**:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Test with actual 1500-line file
- [ ] Test with actual 2500-line file
- [ ] Verify no truncation occurs
- [ ] Verify CI runs successfully
- [ ] Verify rollback works

---

### 🟢 Phase 7: Documentation (LOW PRIORITY)

**Estimated Time**: 2-3 hours  
**Dependencies**: Phases 1-6  
**Blocking**: None

#### 7.1: Update Phase Spec Schema

**File**: `docs/phase_spec_schema.md`

**Add Section**:

```markdown
## Output Modes

Autopack supports three output modes for code generation:

### 1. Full-File Mode (≤500 lines)

**When**: Files are ≤500 lines  
**How**: LLM outputs complete file content in JSON  
**Pros**: Simple, reliable for small files  
**Cons**: Cannot handle large files

### 2. Diff Mode (501-1000 lines)

**When**: Files are 501-1000 lines  
**How**: LLM outputs git-compatible unified diff  
**Pros**: Can handle medium files  
**Cons**: LLMs sometimes generate incorrect diffs

### 3. Structured Edit Mode (>1000 lines) - Stage 2

**When**: Files are >1000 lines  
**How**: LLM outputs targeted edit operations (insert, replace, delete)  
**Pros**: Can handle files of any size, no truncation risk  
**Cons**: More complex, requires precise line numbers

**Example structured edit**:
```json
{
  "summary": "Add telemetry to autonomous_executor.py",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 500,
      "content": "    self.telemetry.record_event(event)\n"
    }
  ]
}
```
```

---

#### 7.2: Create Stage 2 User Guide

**File**: `docs/stage2_structured_edits.md` (NEW)

**Content**:

```markdown
# Stage 2: Structured Edits for Large Files

## Overview

Stage 2 enables Autopack to safely modify files of any size by using targeted edit operations instead of full-file replacement.

## When is Stage 2 Used?

Stage 2 (structured edit mode) is automatically used when:
- A file in the phase context is >1000 lines
- Full-file mode would risk truncation
- Diff mode is not appropriate

## How It Works

### 1. LLM Generates Edit Operations

Instead of outputting the complete file, the LLM outputs specific operations:

```json
{
  "summary": "Add error handling to execute_phase",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 650,
      "content": "        try:\n            # Error handling\n        except Exception as e:\n            logger.error(e)\n"
    }
  ]
}
```

### 2. System Applies Operations

The system applies each operation in order:
1. Validates operation (line numbers, file exists, etc.)
2. Applies operation to file content
3. Verifies result (syntax check, context validation)

### 3. CI Verification

After all operations are applied, CI runs to verify the changes work correctly.

## Operation Types

### INSERT
Insert new lines at a specific position.

**Example**: Add a new function at line 500
```json
{
  "type": "insert",
  "file_path": "src/example.py",
  "line": 500,
  "content": "def new_function():\n    pass\n"
}
```

### REPLACE
Replace a range of lines with new content.

**Example**: Update function implementation (lines 100-110)
```json
{
  "type": "replace",
  "file_path": "src/example.py",
  "start_line": 100,
  "end_line": 110,
  "content": "def updated_function():\n    # New implementation\n    pass\n"
}
```

### DELETE
Delete a range of lines.

**Example**: Remove deprecated function (lines 200-220)
```json
{
  "type": "delete",
  "file_path": "src/example.py",
  "start_line": 200,
  "end_line": 220
}
```

### APPEND
Append lines to the end of a file.

**Example**: Add new function at end of file
```json
{
  "type": "append",
  "file_path": "src/example.py",
  "content": "\ndef new_function():\n    pass\n"
}
```

### PREPEND
Prepend lines to the start of a file.

**Example**: Add import at top of file
```json
{
  "type": "prepend",
  "file_path": "src/example.py",
  "content": "import logging\n"
}
```

## Safety Features

### 1. Validation
- Line numbers must be valid (within file bounds)
- Operations cannot overlap
- Context validation (optional)

### 2. Dry Run
- All operations are validated before applying
- No changes made if validation fails

### 3. Context Matching
- Optional `context_before` and `context_after` fields
- Ensures edits are applied to correct location

**Example with context**:
```json
{
  "type": "replace",
  "file_path": "src/example.py",
  "start_line": 100,
  "end_line": 105,
  "content": "updated code",
  "context_before": "# This is the section",
  "context_after": "# End of section"
}
```

### 4. Rollback
- If any operation fails, all changes are rolled back
- File is restored to original state

## Limitations

### Current Limitations
- Line numbers must be precise
- Cannot handle moving code between files
- Cannot handle complex refactorings (e.g., rename class used in 50 files)

### Future Enhancements
- Semantic anchors (find by function name, not line number)
- Multi-file refactorings
- Automatic conflict resolution

## Examples

### Example 1: Add Telemetry to Large File

**Task**: Add telemetry recording to `autonomous_executor.py` (2425 lines)

**Structured Edit**:
```json
{
  "summary": "Add telemetry recording in execute_phase",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 650,
      "content": "        # Record phase start\n        self.telemetry.record_phase_start(phase_id)\n"
    },
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 750,
      "content": "        # Record phase end\n        self.telemetry.record_phase_end(phase_id)\n"
    }
  ]
}
```

### Example 2: Fix Bug in Large File

**Task**: Fix error handling in `autonomous_executor.py` line 1200

**Structured Edit**:
```json
{
  "summary": "Fix error handling in execute_phase",
  "operations": [
    {
      "type": "replace",
      "file_path": "src/autopack/autonomous_executor.py",
      "start_line": 1200,
      "end_line": 1205,
      "content": "        except Exception as e:\n            logger.error(f\"Phase failed: {e}\")\n            return False\n",
      "context_before": "        try:",
      "context_after": "        # Continue execution"
    }
  ]
}
```

## Troubleshooting

### Operation Failed: Line Out of Range
**Cause**: Line number exceeds file length  
**Solution**: Check file has expected number of lines, adjust line number

### Operation Failed: Context Mismatch
**Cause**: `context_before` or `context_after` doesn't match actual file content  
**Solution**: Update context strings to match actual file content

### Operation Failed: Overlapping Edits
**Cause**: Two operations try to modify the same lines  
**Solution**: Combine operations or adjust line ranges

## Performance

**Compared to Full-File Mode**:
- ✅ **Faster**: Only generates changed lines, not entire file
- ✅ **More reliable**: No truncation risk
- ✅ **More precise**: Only modifies intended sections

**Compared to Diff Mode**:
- ✅ **More reliable**: LLMs better at structured operations than git diffs
- ✅ **Easier to validate**: Clear operation types
- ⚠️ **Requires line numbers**: Must know where to edit

## Migration from Full-File Mode

If you have phases that currently fail with "file_too_large_for_full_file_mode", they will automatically use structured edit mode after Stage 2 is implemented.

**No changes needed** - the system automatically routes to the appropriate mode based on file size.
```

---

## Implementation Checklist

### Phase 1: Core Data Structures ✅
- [ ] Create `src/autopack/structured_edits.py`
- [ ] Define `EditOperation`, `EditPlan`, `StructuredEditResult`
- [ ] Implement `StructuredEditApplicator`
- [ ] Run unit tests for Phase 1

### Phase 2: LLM Integration ✅
- [ ] Add structured edit system prompt to `_build_system_prompt()`
- [ ] Create `_parse_structured_edit_output()` method
- [ ] Update `BuilderResult` to support `edit_plan`
- [ ] Run unit tests for Phase 2

### Phase 3: Integration with Execution Flow ✅
- [ ] Update pre-flight guard to route to structured edit mode
- [ ] Update `llm_service.execute_builder()` to support `output_mode`
- [ ] Update `AnthropicBuilderClient.execute_phase()` to support structured edit mode
- [ ] Run integration tests for Phase 3

### Phase 4: Apply Structured Edits ✅
- [ ] Create `apply_structured_edits()` in `governed_apply.py`
- [ ] Update `autonomous_executor.execute_phase()` to apply structured edits
- [ ] Add rollback support
- [ ] Run integration tests for Phase 4

### Phase 5: User Prompt Updates ✅
- [ ] Update `_build_user_prompt()` for structured edit mode
- [ ] Show files with line numbers
- [ ] Handle very large files (show first/last sections)
- [ ] Run unit tests for Phase 5

### Phase 6: Testing ✅
- [ ] Create `tests/test_structured_edits.py`
- [ ] Implement all test cases
- [ ] Test with 1500-line file
- [ ] Test with 2500-line file
- [ ] Run full test suite

### Phase 7: Documentation ✅
- [ ] Update `docs/phase_spec_schema.md`
- [ ] Create `docs/stage2_structured_edits.md`
- [ ] Add examples and troubleshooting guide
- [ ] Update README

---

## Success Criteria

1. ✅ Can modify files >1000 lines without truncation
2. ✅ Structured edit operations are validated before applying
3. ✅ Context validation prevents incorrect edits
4. ✅ Rollback works on failure
5. ✅ CI runs after structured edits
6. ✅ All tests pass
7. ✅ Documentation is complete
8. ✅ No regression in existing functionality (≤1000 line files)

---

## Dependencies

**Must be completed before Stage 2**:
- ✅ IMPLEMENTATION_PLAN2.md (pre-flight guard, 3-bucket policy)

**Stage 2 depends on**:
- ✅ BuilderOutputConfig (from PLAN2)
- ✅ FileSizeTelemetry (from PLAN2)
- ✅ Pre-flight guard (from PLAN2)
- ✅ 3-bucket policy (from PLAN2)

---

## Rollback Plan

If issues arise during implementation:

1. **Phase 1-2 issues**: Disable structured edit mode, fall back to failing for >1000 line files
2. **Phase 3-4 issues**: Keep LLM integration, disable apply logic
3. **Phase 5-7 issues**: Skip prompt updates/docs, use basic prompts

The system will gracefully degrade to PLAN2 behavior (fail for >1000 line files) if Stage 2 has issues.

---

## Estimated Timeline

| Phase | Time | Cumulative |
|-------|------|------------|
| Phase 1 | 3-4h | 3-4h |
| Phase 2 | 4-5h | 7-9h |
| Phase 3 | 3-4h | 10-13h |
| Phase 4 | 3-4h | 13-17h |
| Phase 5 | 2-3h | 15-20h |
| Phase 6 | 4-5h | 19-25h |
| Phase 7 | 2-3h | 21-28h |

**Total**: 20-25 hours (assuming PLAN2 is already complete)

---

## Notes

- Stage 2 is a significant enhancement but not critical for safety (PLAN2 provides safety)
- Can be implemented incrementally (phases are mostly independent)
- Phase 1-4 are the core functionality, Phase 5-7 are polish
- Estimated time assumes familiarity with codebase from PLAN2 implementation

---

*Plan created: December 2, 2025*  
*Last updated: December 2, 2025*  
*Status: Ready to implement (after PLAN2)*

