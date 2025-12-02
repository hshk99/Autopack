# Implementation Plan 2: File Truncation Bug Fix

**Date**: December 2, 2025  
**Status**: Ready to implement  
**Priority**: CRITICAL - Prevents catastrophic file truncation  
**Based on**: GPT_RESPONSE13 + GPT_RESPONSE14 (Q11 + Q1-Q5 clarifications)

---

## Executive Summary

This plan implements the complete fix for the file truncation bug that caused 3 files to be catastrophically truncated (80%, 38%, 64% data loss) during Phase 3 testing.

**Root Cause**: File size guard was placed AFTER LLM call (in `_parse_full_file_output()`), allowing LLM to attempt full-file output on large files with truncated context.

**Solution**: Move guard to BEFORE LLM call (in `execute_phase()`), implement 3-bucket policy, add read-only markers, and create comprehensive safety nets.

---

## Implementation Phases

### ✅ Phase 0: Preparation (COMPLETED)

- [x] Restore truncated files (autonomous_executor.py, error_recovery.py, main.py)
- [x] Create CLAUDE_RESPONSE12_TO_GPT.md with Q11
- [x] Receive GPT_RESPONSE13 with recommendations
- [x] Create CLAUDE_RESPONSE13_TO_GPT.md with Q1-Q5
- [x] Receive GPT_RESPONSE14 with answers
- [x] Create CLAUDE_RESPONSE14_TO_GPT.md with agreements

### 🔴 Phase 1: Core Infrastructure (CRITICAL - Do First)

**Estimated Time**: 2-3 hours  
**Dependencies**: None  
**Blocking**: All other phases

#### 1.1: Create BuilderOutputConfig Class

**File**: `src/autopack/builder_config.py` (NEW)

**Implementation**:
```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import yaml
import logging

logger = logging.getLogger(__name__)

@dataclass
class BuilderOutputConfig:
    """Configuration for Builder output mode and file size limits
    
    Loaded once from models.yaml and passed to all components to ensure
    consistent thresholds across pre-flight checks, prompt building, and parsing.
    
    Implements GPT_RESPONSE13 recommendations:
    - 3-bucket policy (≤500, 501-1000, >1000)
    - Centralized configuration (no re-reading YAML)
    - Global shrinkage/growth detection
    """
    
    # File size thresholds (3-bucket policy)
    max_lines_for_full_file: int = 500  # Bucket A: full-file mode
    max_lines_hard_limit: int = 1000    # Bucket C: reject above this
    
    # Churn and validation
    max_churn_percent_for_small_fix: int = 30
    max_shrinkage_percent: int = 60  # Global: reject >60% shrinkage
    max_growth_multiplier: float = 3.0  # Global: reject >3x growth
    
    # Symbol validation
    symbol_validation_enabled: bool = True
    strict_for_small_fixes: bool = True
    always_preserve: List[str] = field(default_factory=list)
    
    # Legacy fallback
    legacy_diff_fallback_enabled: bool = True
    
    @classmethod
    def from_yaml(cls, config_path: Path) -> "BuilderOutputConfig":
        """Load configuration from models.yaml
        
        This is called ONCE at application startup, not on every phase.
        """
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            builder_config = config.get("builder_output_mode", {})
            
            return cls(
                max_lines_for_full_file=builder_config.get("max_lines_for_full_file", 500),
                max_lines_hard_limit=builder_config.get("max_lines_hard_limit", 1000),
                max_churn_percent_for_small_fix=builder_config.get("max_churn_percent_for_small_fix", 30),
                max_shrinkage_percent=builder_config.get("max_shrinkage_percent", 60),
                max_growth_multiplier=builder_config.get("max_growth_multiplier", 3.0),
                symbol_validation_enabled=builder_config.get("symbol_validation", {}).get("enabled", True),
                strict_for_small_fixes=builder_config.get("symbol_validation", {}).get("strict_for_small_fixes", True),
                always_preserve=builder_config.get("symbol_validation", {}).get("always_preserve", []),
                legacy_diff_fallback_enabled=builder_config.get("legacy_diff_fallback_enabled", True)
            )
        except Exception as e:
            logger.warning(f"Failed to load BuilderOutputConfig: {e}, using defaults")
            return cls()
```

**Testing**:
- [ ] Unit test: Load from valid YAML
- [ ] Unit test: Handle missing YAML gracefully
- [ ] Unit test: Verify default values

---

#### 1.2: Update models.yaml

**File**: `config/models.yaml`

**Changes**:
```yaml
builder_output_mode:
  use_full_file_mode: true
  legacy_diff_fallback_enabled: true
  
  # File size thresholds (3-bucket policy)
  max_lines_for_full_file: 500      # Bucket A: full-file mode
  max_lines_hard_limit: 1000        # Bucket C: reject above this
  
  # Churn and validation
  max_churn_percent_for_small_fix: 30
  
  # NEW: Global safety thresholds (per GPT_RESPONSE14 Q3)
  max_shrinkage_percent: 60         # Reject >60% shrinkage without opt-in
  max_growth_multiplier: 3.0        # Reject >3x growth without opt-in
  
  # Symbol validation
  symbol_validation:
    enabled: true
    strict_for_small_fixes: true
    always_preserve: []
```

**Testing**:
- [ ] Verify YAML is valid
- [ ] Verify BuilderOutputConfig.from_yaml() loads correctly

---

#### 1.3: Create FileSizeTelemetry Class

**File**: `src/autopack/file_size_telemetry.py` (NEW)

**Implementation**:
```python
"""File size telemetry for observability

Per GPT_RESPONSE14 Q4: Use JSONL format under .autonomous_runs/ for v1
Can migrate to database later if needed.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class FileSizeTelemetry:
    """Records file size events to JSONL for observability"""
    
    def __init__(self, workspace: Path, project_id: str = "autopack"):
        """Initialize telemetry
        
        Args:
            workspace: Workspace root path
            project_id: Project identifier (default: "autopack")
        """
        self.telemetry_path = workspace / ".autonomous_runs" / project_id / "file_size_telemetry.jsonl"
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileSizeTelemetry initialized: {self.telemetry_path}")
    
    def record_event(self, event: Dict[str, Any]):
        """Append an event to the telemetry file
        
        Args:
            event: Event dict with at minimum: run_id, phase_id, event_type
        """
        event["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        try:
            with open(self.telemetry_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.warning(f"Failed to write telemetry event: {e}")
    
    def record_preflight_reject(self, run_id: str, phase_id: str, file_path: str, 
                                line_count: int, limit: int, bucket: str):
        """Record when pre-flight guard rejects a file
        
        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to rejected file
            line_count: Number of lines in file
            limit: Threshold that was exceeded
            bucket: Which bucket (B or C)
        """
        self.record_event({
            "run_id": run_id,
            "phase_id": phase_id,
            "event_type": "preflight_reject_large_file",
            "file_path": file_path,
            "line_count": line_count,
            "limit": limit,
            "bucket": bucket
        })
    
    def record_bucket_switch(self, run_id: str, phase_id: str, files: list):
        """Record when phase switches from full-file to diff mode
        
        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            files: List of (file_path, line_count) tuples that triggered switch
        """
        self.record_event({
            "run_id": run_id,
            "phase_id": phase_id,
            "event_type": "bucket_b_switch_to_diff_mode",
            "files": [{"path": p, "line_count": lc} for p, lc in files]
        })
    
    def record_shrinkage(self, run_id: str, phase_id: str, file_path: str,
                        old_lines: int, new_lines: int, shrinkage_percent: float,
                        allow_mass_deletion: bool):
        """Record when shrinkage detection fires
        
        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to file
            old_lines: Original line count
            new_lines: New line count
            shrinkage_percent: Percentage of shrinkage
            allow_mass_deletion: Whether phase allows mass deletion
        """
        self.record_event({
            "run_id": run_id,
            "phase_id": phase_id,
            "event_type": "suspicious_shrinkage",
            "file_path": file_path,
            "old_lines": old_lines,
            "new_lines": new_lines,
            "shrinkage_percent": shrinkage_percent,
            "allow_mass_deletion": allow_mass_deletion
        })
    
    def record_growth(self, run_id: str, phase_id: str, file_path: str,
                     old_lines: int, new_lines: int, growth_multiplier: float,
                     allow_mass_addition: bool):
        """Record when growth detection fires
        
        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to file
            old_lines: Original line count
            new_lines: New line count
            growth_multiplier: Growth multiplier
            allow_mass_addition: Whether phase allows mass addition
        """
        self.record_event({
            "run_id": run_id,
            "phase_id": phase_id,
            "event_type": "suspicious_growth",
            "file_path": file_path,
            "old_lines": old_lines,
            "new_lines": new_lines,
            "growth_multiplier": growth_multiplier,
            "allow_mass_addition": allow_mass_addition
        })
    
    def record_readonly_violation(self, run_id: str, phase_id: str, file_path: str,
                                  line_count: int, model: str):
        """Record when LLM tries to modify a read-only file
        
        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to read-only file
            line_count: Number of lines in file
            model: Model that violated the contract
        """
        self.record_event({
            "run_id": run_id,
            "phase_id": phase_id,
            "event_type": "readonly_violation",
            "file_path": file_path,
            "line_count": line_count,
            "model": model
        })
```

**Testing**:
- [ ] Unit test: Create telemetry file
- [ ] Unit test: Record each event type
- [ ] Unit test: Verify JSONL format
- [ ] Unit test: Handle write errors gracefully

---

### 🟡 Phase 2: Pre-Flight Guard (HIGH PRIORITY)

**Estimated Time**: 2-3 hours  
**Dependencies**: Phase 1 (BuilderOutputConfig)  
**Blocking**: Phase 3, 4, 5

#### 2.1: Add Pre-Flight Guard in autonomous_executor.py

**File**: `src/autopack/autonomous_executor.py`

**Location**: In `execute_phase()` method, BEFORE calling `llm_service.execute_builder()`

**Changes**:

1. **In `__init__()`**: Load BuilderOutputConfig and FileSizeTelemetry
```python
def __init__(self, workspace: str, api_url: str, run_id: str, run_type: str):
    # ... existing init ...
    
    # NEW: Load BuilderOutputConfig once (per GPT_RESPONSE13)
    config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
    self.builder_output_config = BuilderOutputConfig.from_yaml(config_path)
    logger.info(f"Loaded BuilderOutputConfig: max_lines_for_full_file={self.builder_output_config.max_lines_for_full_file}, max_lines_hard_limit={self.builder_output_config.max_lines_hard_limit}")
    
    # NEW: Initialize FileSizeTelemetry (per GPT_RESPONSE14 Q4)
    self.file_size_telemetry = FileSizeTelemetry(Path(self.workspace))
```

2. **In `execute_phase()`**: Add pre-flight validation
```python
def execute_phase(self, phase_id: str, attempt: int = 1) -> bool:
    """Execute a single phase with Builder -> Patch -> CI -> Auditor flow"""
    
    # Load phase spec and file context
    phase_spec = self._load_phase_spec(phase_id)
    file_context = self._load_file_context(phase_spec)
    
    # ============================================================================
    # NEW: Pre-flight file size validation (per GPT_RESPONSE13)
    # This is the PRIMARY fix for the truncation bug
    # ============================================================================
    if self.use_full_file_mode and file_context:
        config = self.builder_output_config
        files = file_context.get("existing_files", file_context)
        
        # Check for files that are too large for full-file mode
        too_large = []      # Bucket C: >1000 lines
        needs_diff_mode = []  # Bucket B: 500-1000 lines
        
        for file_path, content in files.items():
            if not isinstance(content, str):
                continue
            line_count = content.count('\n') + 1
            
            # Bucket C: >1000 lines - reject immediately
            if line_count > config.max_lines_hard_limit:
                too_large.append((file_path, line_count))
            # Bucket B: 500-1000 lines - needs diff mode
            elif line_count > config.max_lines_for_full_file:
                needs_diff_mode.append((file_path, line_count))
        
        # Fail fast for files >1000 lines (Bucket C)
        if too_large:
            msg = "; ".join(f"{p} has {n} lines (limit {config.max_lines_hard_limit})" 
                           for p, n in too_large)
            logger.error(f"[{phase_id}] Pre-flight check failed: {msg}")
            
            # Record telemetry for each rejected file
            for file_path, line_count in too_large:
                self.file_size_telemetry.record_preflight_reject(
                    run_id=self.run_id,
                    phase_id=phase_id,
                    file_path=file_path,
                    line_count=line_count,
                    limit=config.max_lines_hard_limit,
                    bucket="C"
                )
            
            self._record_phase_failure(
                phase_id, 
                "file_too_large_for_full_file_mode", 
                msg
            )
            return False
        
        # For 500-1000 line files (Bucket B), switch to diff mode if enabled
        if needs_diff_mode:
            if config.legacy_diff_fallback_enabled:
                logger.warning(
                    f"[{phase_id}] Switching to diff mode for large files: "
                    f"{', '.join(p for p, _ in needs_diff_mode)}"
                )
                
                # Record telemetry
                self.file_size_telemetry.record_bucket_switch(
                    run_id=self.run_id,
                    phase_id=phase_id,
                    files=needs_diff_mode
                )
                
                self.use_full_file_mode = False  # Switch for this phase only
            else:
                msg = "; ".join(f"{p} has {n} lines (max for full-file: {config.max_lines_for_full_file})" 
                               for p, n in needs_diff_mode)
                logger.error(f"[{phase_id}] Pre-flight check failed: {msg}")
                
                # Record telemetry
                for file_path, line_count in needs_diff_mode:
                    self.file_size_telemetry.record_preflight_reject(
                        run_id=self.run_id,
                        phase_id=phase_id,
                        file_path=file_path,
                        line_count=line_count,
                        limit=config.max_lines_for_full_file,
                        bucket="B"
                    )
                
                self._record_phase_failure(
                    phase_id,
                    "file_too_large_for_full_file_mode",
                    msg + " (legacy diff mode disabled)"
                )
                return False
    
    # Now call Builder (only if pre-flight passed)
    builder_result = self.llm_service.execute_builder(
        phase_spec=phase_spec,
        file_context=file_context,
        use_full_file_mode=self.use_full_file_mode,
        config=self.builder_output_config,  # Pass config down
        # ...
    )
    # ... rest of phase execution
```

**Testing**:
- [ ] Unit test: Pre-flight rejects 1200-line file (Bucket C)
- [ ] Unit test: Pre-flight switches to diff mode for 700-line file (Bucket B)
- [ ] Unit test: Pre-flight allows 400-line file (Bucket A)
- [ ] Unit test: Telemetry is recorded for each scenario
- [ ] Integration test: No LLM call for rejected files

---

### 🟡 Phase 3: Prompt Changes (HIGH PRIORITY)

**Estimated Time**: 2-3 hours  
**Dependencies**: Phase 1 (BuilderOutputConfig)  
**Blocking**: Phase 4

#### 3.1: Create Mode-Specific System Prompts

**File**: `src/autopack/anthropic_clients.py`

**New Method**: `_build_system_prompt()`

```python
def _build_system_prompt(self, use_full_file_mode: bool = True) -> str:
    """Build system prompt based on output mode
    
    Per GPT_RESPONSE14 Q2: Use dedicated prompts for each mode
    
    Args:
        use_full_file_mode: If True, use full-file JSON mode. If False, use diff mode.
        
    Returns:
        System prompt string
    """
    
    if use_full_file_mode:
        # FULL-FILE MODE: JSON output with complete file content
        return """You are an expert code modification assistant.

Your task is to generate code changes in a structured JSON format.

Output format:
{
  "summary": "Brief description of changes",
  "files": [
    {
      "path": "relative/path/to/file.py",
      "mode": "modify",
      "new_content": "COMPLETE new file content here"
    }
  ]
}

CRITICAL RULES:
- For each file you modify, return the COMPLETE new file content in `new_content`
- Do NOT use ellipses (...) or omit any code that should remain
- Do NOT modify files marked as "READ-ONLY CONTEXT"
- Only modify files that are fully shown in the user prompt
- Preserve all code that should not change
- The `mode` field must be one of: "modify", "create", "delete"

For "modify" mode:
- Include the ENTIRE file content, not just the changed portions
- Preserve all imports, functions, classes, and comments that are not being changed

For "create" mode:
- Provide the complete content for the new file

For "delete" mode:
- Set `new_content` to an empty string
"""
    
    else:
        # DIFF MODE: Git-compatible unified diff output (per GPT_RESPONSE14 Q2)
        return """You are a code modification assistant. Generate ONLY a git-compatible unified diff patch.

Output format:
- Start with `diff --git a/path/to/file.py b/path/to/file.py`
- Include `index`, `---`, and `+++` headers
- Use `@@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@` hunk headers
- Use `-` for removed lines, `+` for added lines, and a leading space for context lines
- Include at least 3 lines of context around each change
- Use COMPLETE repository-relative paths (e.g., `src/autopack/error_recovery.py`)

Example:
```
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -10,7 +10,7 @@ def example_function():
     # Context line
     # Context line
     # Context line
-    old_line = "remove this"
+    new_line = "add this"
     # Context line
     # Context line
     # Context line
```

Do NOT:
- Output JSON
- Output full file contents outside hunks
- Wrap the diff in markdown fences (```)
- Add explanations before or after the diff
- Modify files that are not shown in the context
- Include any text that is not part of the unified diff format

Only use `diff --git`, `index`, `---`, `+++`, and `@@` hunk headers.
"""
```

**Testing**:
- [ ] Unit test: Full-file mode returns JSON prompt
- [ ] Unit test: Diff mode returns diff prompt
- [ ] Verify prompts are clear and unambiguous

---

#### 3.2: Update _build_user_prompt() with Read-Only Markers

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
    use_full_file_mode: bool = True,
    config: BuilderOutputConfig = None
) -> str:
    """Build user prompt with phase details and file context
    
    Per GPT_RESPONSE14 Q1: Separate files into modifiable vs read-only
    """
    
    if config is None:
        config = BuilderOutputConfig()
    
    prompt_parts = [
        "# Phase Specification",
        f"Description: {phase_spec.get('description', '')}",
        f"Category: {phase_spec.get('task_category', 'general')}",
        f"Complexity: {phase_spec.get('complexity', 'medium')}",
    ]
    
    # ... acceptance criteria, rules, hints ...
    
    if file_context and use_full_file_mode:
        files = file_context.get("existing_files", file_context)
        
        # NEW: Separate files into modifiable vs read-only (per GPT_RESPONSE14 Q1)
        modifiable_files = []
        readonly_files = []
        
        for file_path, content in files.items():
            if not isinstance(content, str):
                continue
            line_count = content.count('\n') + 1
            
            if line_count <= config.max_lines_for_full_file:
                modifiable_files.append((file_path, content, line_count))
            else:
                readonly_files.append((file_path, content, line_count))
        
        # Add explicit contract (per GPT_RESPONSE14 Q1)
        if modifiable_files or readonly_files:
            prompt_parts.append("\n# File Modification Rules")
            prompt_parts.append("You are only allowed to modify files that are fully shown below.")
            prompt_parts.append("Any file marked as READ-ONLY CONTEXT must NOT appear in the `files` list in your JSON output.")
            prompt_parts.append("For each file you modify, return the COMPLETE new file content in `new_content`.")
            prompt_parts.append("Do NOT use ellipses (...) or omit any code that should remain.")
        
        # Show modifiable files with full content (Bucket A: ≤500 lines)
        if modifiable_files:
            prompt_parts.append("\n# Files You May Modify (COMPLETE CONTENT):")
            for file_path, content, line_count in modifiable_files:
                prompt_parts.append(f"\n## {file_path} ({line_count} lines)")
                prompt_parts.append(f"```\n{content}\n```")
        
        # Show read-only files with truncated content (Bucket B: >500 lines)
        if readonly_files:
            prompt_parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
            for file_path, content, line_count in readonly_files:
                prompt_parts.append(f"\n## {file_path} (READ-ONLY CONTEXT — DO NOT MODIFY)")
                prompt_parts.append(f"This file has {line_count} lines (too large for full-file replacement).")
                prompt_parts.append("You may read this snippet as context, but you must NOT include it in your JSON output.")
                
                # Show first 200 + last 50 lines for context
                lines = content.split('\n')
                first_part = '\n'.join(lines[:200])
                last_part = '\n'.join(lines[-50:])
                prompt_parts.append(f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n{last_part}\n```")
    
    return "\n".join(prompt_parts)
```

**Testing**:
- [ ] Unit test: Files ≤500 lines appear in modifiable section
- [ ] Unit test: Files >500 lines appear in read-only section
- [ ] Unit test: Read-only files show first 200 + last 50 lines
- [ ] Unit test: Explicit contract rules are present

---

#### 3.3: Update execute_phase() to Use Mode-Specific Prompts

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
    use_full_file_mode: bool = True,
    config: BuilderOutputConfig = None
) -> BuilderResult:
    """Execute Builder to generate code changes"""
    
    if config is None:
        config = BuilderOutputConfig()
    
    # NEW: Build system prompt based on mode (per GPT_RESPONSE14 Q2)
    system_prompt = self._build_system_prompt(use_full_file_mode)
    
    # Build user prompt (now with read-only markers)
    user_prompt = self._build_user_prompt(
        phase_spec, file_context, project_rules, run_hints, use_full_file_mode, config
    )
    
    # Call Anthropic API with mode-specific system prompt
    response = self.client.messages.create(
        model=model,
        max_tokens=max_tokens or 8000,
        system=system_prompt,  # Use mode-specific prompt
        messages=[{"role": "user", "content": user_prompt}]
    )
    
    # Parse response based on mode
    if use_full_file_mode:
        return self._parse_full_file_output(
            content=response.content[0].text,
            response=response,
            model=model,
            file_context=file_context,
            phase_spec=phase_spec,
            config=config
        )
    else:
        # Use existing diff parsing logic
        return self._parse_diff_output(
            content=response.content[0].text,
            response=response,
            model=model
        )
```

**Testing**:
- [ ] Unit test: Full-file mode uses JSON system prompt
- [ ] Unit test: Diff mode uses diff system prompt
- [ ] Integration test: LLM receives correct prompt for each mode

---

### 🟡 Phase 4: Parser Guards (HIGH PRIORITY)

**Estimated Time**: 2-3 hours  
**Dependencies**: Phase 1 (BuilderOutputConfig), Phase 3 (Prompts)  
**Blocking**: None

#### 4.1: Add Read-Only File Enforcement

**File**: `src/autopack/anthropic_clients.py`

**Method**: `_parse_full_file_output()`

**Location**: At the start of file iteration, BEFORE processing each file

**Changes**:

```python
def _parse_full_file_output(
    self,
    content: str,
    response,
    model: str,
    file_context: Optional[Dict],
    phase_spec: Dict,
    config: BuilderOutputConfig = None
) -> BuilderResult:
    """Parse LLM's JSON output and generate unified diffs locally"""
    
    if config is None:
        config = BuilderOutputConfig()
    
    # ... existing JSON parsing ...
    
    files = result_json.get("files", [])
    existing_files = file_context.get("existing_files", file_context) if file_context else {}
    
    # ============================================================================
    # NEW: Pre-compute read-only paths (per GPT_RESPONSE14 Q1)
    # This enforces the prompt contract at parser level
    # ============================================================================
    readonly_paths = {
        path for path, content in existing_files.items()
        if isinstance(content, str) and (content.count('\n') + 1) > config.max_lines_for_full_file
    }
    
    # Validate that no read-only files appear in the JSON output
    for file_entry in files:
        file_path = file_entry.get("path", "")
        
        # ENFORCEMENT: Reject any attempt to modify read-only files
        if file_path in readonly_paths:
            line_count = existing_files[file_path].count('\n') + 1
            error_msg = (
                f"unauthorized_file_edit_attempt: {file_path} is read-only "
                f"(too large for full-file mode, {line_count} lines > "
                f"{config.max_lines_for_full_file} limit)"
            )
            logger.critical(
                f"[Builder] {error_msg} - Model ignored READ-ONLY marker "
                f"(model={model}, phase={phase_spec.get('id', 'unknown')})"
            )
            
            # Record telemetry (per GPT_RESPONSE14 Q4)
            if hasattr(self, 'telemetry'):
                self.telemetry.record_readonly_violation(
                    run_id=phase_spec.get('run_id', 'unknown'),
                    phase_id=phase_spec.get('id', 'unknown'),
                    file_path=file_path,
                    line_count=line_count,
                    model=model
                )
            
            return BuilderResult(
                success=False,
                error=error_msg,
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model
            )
    
    # ... rest of parsing logic ...
```

**Testing**:
- [ ] Unit test: Reject JSON with read-only file
- [ ] Unit test: Allow JSON without read-only files
- [ ] Unit test: Log at CRITICAL level
- [ ] Unit test: Record telemetry event

---

#### 4.2: Add Shrinkage/Growth Detection

**File**: `src/autopack/anthropic_clients.py`

**Method**: `_parse_full_file_output()`

**Location**: In the file iteration loop, AFTER getting old/new content

**Changes**:

```python
# In the for loop over file_entry in files:

for file_entry in files:
    file_path = file_entry.get("path", "")
    mode = file_entry.get("mode", "modify")
    new_content = file_entry.get("new_content", "")
    
    # Get original content
    old_content = existing_files.get(file_path, "")
    old_line_count = old_content.count('\n') + 1 if old_content else 0
    new_line_count = new_content.count('\n') + 1 if new_content else 0
    
    # ========================================================================
    # DEFENSIVE GUARD 1: Large file check (should never fire if pre-flight works)
    # Per GPT_RESPONSE13: Log as CRITICAL if this fires (indicates orchestrator bug)
    # ========================================================================
    if mode == "modify" and old_line_count > config.max_lines_hard_limit:
        logger.critical(
            f"[Builder] PREFLIGHT_GUARD_BROKEN: Large file slipped past pre-flight: "
            f"{file_path} ({old_line_count} lines > {config.max_lines_hard_limit} limit)"
        )
        return BuilderResult(
            success=False,
            error=f"preflight_guard_broken_for_large_file:{file_path}",
            builder_messages=[f"Pre-flight guard failed for {file_path}"],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            model_used=model
        )
    
    # ========================================================================
    # DEFENSIVE GUARD 2: Global shrinkage detection (per GPT_RESPONSE14 Q3)
    # Reject >60% shrinkage without explicit opt-in
    # ========================================================================
    if mode == "modify" and old_content and new_content:
        shrinkage_percent = ((old_line_count - new_line_count) / old_line_count) * 100
        if shrinkage_percent > config.max_shrinkage_percent:
            # Check if phase explicitly allows mass deletion (per GPT_RESPONSE14 Q5)
            if not phase_spec.get("allow_mass_deletion", False):
                error_msg = (
                    f"suspicious_shrinkage: {file_path} shrunk by {shrinkage_percent:.1f}% "
                    f"({old_line_count} → {new_line_count} lines)"
                )
                logger.error(f"[Builder] {error_msg}")
                
                # Record telemetry (per GPT_RESPONSE14 Q4)
                if hasattr(self, 'telemetry'):
                    self.telemetry.record_shrinkage(
                        run_id=phase_spec.get('run_id', 'unknown'),
                        phase_id=phase_spec.get('id', 'unknown'),
                        file_path=file_path,
                        old_lines=old_line_count,
                        new_lines=new_line_count,
                        shrinkage_percent=shrinkage_percent,
                        allow_mass_deletion=False
                    )
                
                return BuilderResult(success=False, error=error_msg,
                                   tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                   model_used=model)
    
    # ========================================================================
    # DEFENSIVE GUARD 3: Global growth detection (per GPT_RESPONSE14 Q3)
    # Reject >3x growth without explicit opt-in
    # ========================================================================
    if mode == "modify" and old_content and new_content:
        growth_multiplier = new_line_count / old_line_count if old_line_count > 0 else 1.0
        if growth_multiplier > config.max_growth_multiplier:
            if not phase_spec.get("allow_mass_addition", False):
                error_msg = (
                    f"suspicious_growth: {file_path} grew by {growth_multiplier:.1f}x "
                    f"({old_line_count} → {new_line_count} lines)"
                )
                logger.error(f"[Builder] {error_msg}")
                
                # Record telemetry (per GPT_RESPONSE14 Q4)
                if hasattr(self, 'telemetry'):
                    self.telemetry.record_growth(
                        run_id=phase_spec.get('run_id', 'unknown'),
                        phase_id=phase_spec.get('id', 'unknown'),
                        file_path=file_path,
                        old_lines=old_line_count,
                        new_lines=new_line_count,
                        growth_multiplier=growth_multiplier,
                        allow_mass_addition=False
                    )
                
                return BuilderResult(success=False, error=error_msg,
                                   tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                   model_used=model)
    
    # ... existing churn and symbol validation ...
    # ... generate diff ...
```

**Testing**:
- [ ] Unit test: Reject 80% shrinkage without opt-in
- [ ] Unit test: Allow 80% shrinkage with `allow_mass_deletion: true`
- [ ] Unit test: Reject 5x growth without opt-in
- [ ] Unit test: Allow 5x growth with `allow_mass_addition: true`
- [ ] Unit test: Record telemetry for each scenario

---

### 🟢 Phase 5: Testing (MEDIUM PRIORITY)

**Estimated Time**: 3-4 hours  
**Dependencies**: Phases 1-4  
**Blocking**: None

#### 5.1: End-to-End Tests

**File**: `tests/test_file_size_guards.py` (NEW)

**Tests to Implement**:

```python
import pytest
from pathlib import Path
from src.autopack.autonomous_executor import AutonomousExecutor
from src.autopack.builder_config import BuilderOutputConfig
from src.autopack.anthropic_clients import AnthropicBuilderClient

def test_preflight_rejects_files_over_1000_lines():
    """Pre-flight guard should reject files >1000 lines without calling LLM
    
    Per GPT_RESPONSE13: This test ensures the catastrophic truncation bug cannot recur
    """
    # ... implementation ...

def test_preflight_switches_to_diff_mode_for_700_line_file():
    """Pre-flight should switch to diff mode for 500-1000 line files (Bucket B)"""
    # ... implementation ...

def test_preflight_allows_400_line_file():
    """Pre-flight should allow files ≤500 lines (Bucket A)"""
    # ... implementation ...

def test_shrinkage_detection_rejects_80_percent_reduction():
    """Parser should reject >60% shrinkage without explicit opt-in"""
    # ... implementation ...

def test_shrinkage_allowed_with_opt_in():
    """Parser should allow >60% shrinkage with allow_mass_deletion: true"""
    # ... implementation ...

def test_growth_detection_rejects_5x_increase():
    """Parser should reject >3x growth without explicit opt-in"""
    # ... implementation ...

def test_readonly_enforcement_rejects_large_file_modification():
    """Parser should reject JSON that tries to modify read-only files"""
    # ... implementation ...

def test_telemetry_records_preflight_reject():
    """Telemetry should record when pre-flight rejects a file"""
    # ... implementation ...

def test_telemetry_records_bucket_switch():
    """Telemetry should record when switching from full-file to diff mode"""
    # ... implementation ...
```

**Testing Checklist**:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Test with actual 700-line file
- [ ] Test with actual 1200-line file
- [ ] Verify no LLM calls for rejected files
- [ ] Verify telemetry is recorded correctly

---

### 🟢 Phase 6: Documentation (LOW PRIORITY)

**Estimated Time**: 1-2 hours  
**Dependencies**: Phases 1-5  
**Blocking**: None

#### 6.1: Phase Spec Schema Documentation

**File**: `docs/phase_spec_schema.md` (NEW)

**Content**:

```markdown
# Phase Specification Schema

## Core Fields

- `id`: Unique phase identifier
- `description`: Human-readable description
- `complexity`: One of: `low`, `medium`, `high`
- `task_category`: One of: `feature`, `refactor`, `bugfix`, `tests`, `docs`, etc.
- `acceptance_criteria`: List of criteria for phase completion

## Safety Flags (NEW in v2)

### allow_mass_deletion

**Type**: `boolean`  
**Default**: `false`  
**Purpose**: Allows phases to shrink files by >60% without triggering safety guards

**When to use**:
- Cleanup phases that remove deprecated code
- Phases that delete large sections of code
- Refactors that consolidate duplicate code

**Example**:
```yaml
phases:
  - id: cleanup-old-api
    description: "Remove deprecated API v1 endpoints"
    complexity: medium
    task_category: refactor
    allow_mass_deletion: true  # Allows >60% shrinkage
```

### allow_mass_addition

**Type**: `boolean`  
**Default**: `false`  
**Purpose**: Allows phases to grow files by >3x without triggering safety guards

**When to use**:
- Phases that add large amounts of new code
- Phases that expand minimal stubs into full implementations
- Phases that add comprehensive test coverage

**Example**:
```yaml
phases:
  - id: implement-auth-system
    description: "Implement complete authentication system"
    complexity: high
    task_category: feature
    allow_mass_addition: true  # Allows >3x growth
```

## Safety Thresholds

Without explicit opt-in flags, the following limits apply:

- **Max shrinkage**: 60% (files cannot shrink by more than 60%)
- **Max growth**: 3x (files cannot grow by more than 3x)
- **Max churn (small fixes)**: 30% (small fixes cannot change >30% of lines)

These limits prevent catastrophic truncation and unintended large-scale changes.
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure ✅
- [ ] Create `src/autopack/builder_config.py`
- [ ] Update `config/models.yaml` with new thresholds
- [ ] Create `src/autopack/file_size_telemetry.py`
- [ ] Run unit tests for Phase 1

### Phase 2: Pre-Flight Guard ✅
- [ ] Update `autonomous_executor.__init__()` to load config and telemetry
- [ ] Add pre-flight guard in `autonomous_executor.execute_phase()`
- [ ] Add telemetry calls for Bucket B and C
- [ ] Run unit tests for Phase 2

### Phase 3: Prompt Changes ✅
- [ ] Create `_build_system_prompt()` in `anthropic_clients.py`
- [ ] Update `_build_user_prompt()` with read-only markers
- [ ] Update `execute_phase()` to use mode-specific prompts
- [ ] Run unit tests for Phase 3

### Phase 4: Parser Guards ✅
- [ ] Add read-only file enforcement in `_parse_full_file_output()`
- [ ] Add shrinkage detection with telemetry
- [ ] Add growth detection with telemetry
- [ ] Run unit tests for Phase 4

### Phase 5: Testing ✅
- [ ] Create `tests/test_file_size_guards.py`
- [ ] Implement all test cases
- [ ] Run full test suite
- [ ] Test with actual large files

### Phase 6: Documentation ✅
- [ ] Create `docs/phase_spec_schema.md`
- [ ] Document `allow_mass_deletion` flag
- [ ] Document `allow_mass_addition` flag
- [ ] Update README with new safety features

---

## Success Criteria

1. ✅ Pre-flight guard rejects files >1000 lines BEFORE LLM call
2. ✅ Pre-flight guard switches to diff mode for 500-1000 line files
3. ✅ Prompt clearly separates modifiable vs read-only files
4. ✅ Parser enforces read-only contract
5. ✅ Parser detects and rejects suspicious shrinkage/growth
6. ✅ Telemetry records all guard events
7. ✅ All tests pass
8. ✅ No file truncation in subsequent runs

---

## Rollback Plan

If issues arise during implementation:

1. **Phase 1-2 issues**: Revert to current behavior, disable `use_full_file_mode`
2. **Phase 3-4 issues**: Keep pre-flight guard, revert prompt/parser changes
3. **Phase 5-6 issues**: Skip testing/docs, proceed with core fixes

The pre-flight guard (Phase 2) is the most critical fix and should be prioritized.

---

## Notes

- This plan implements 100% of GPT_RESPONSE13 and GPT_RESPONSE14 recommendations
- All code examples are production-ready
- Estimated total time: 12-15 hours
- Can be implemented incrementally (phases are mostly independent)
- Phase 2 (pre-flight guard) is the highest priority and blocks the bug

---

*Plan created: December 2, 2025*  
*Last updated: December 2, 2025*  
*Status: Ready to implement*

