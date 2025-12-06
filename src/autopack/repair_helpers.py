"""
Repair helpers for malformed Builder output (JSON) and YAML content.

Per ref2.md recommendations:
1. JSON repair helper - takes raw LLM text + decode error, attempts to fix syntax
2. YAML repair helper - takes old/new YAML + parse error, proposes minimal fix

These give Autopack a "second chance" to fix deterministic structural errors
without human intervention.
"""

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Expected schema for Builder full-file output
BUILDER_JSON_SCHEMA = {
    "summary": "string (optional)",
    "files": [
        {
            "path": "string (required)",
            "mode": "modify|create|delete (optional, defaults to modify)",
            "new_content": "string (required for modify/create)"
        }
    ]
}


class JsonRepairHelper:
    """
    Attempts to repair malformed JSON from Builder output.

    Strategies (ordered by aggressiveness):
    1. Rule-based fixes (strip common prefixes, fix escapes, balance brackets)
    2. LLM-assisted repair (call a cheap model to fix syntax only)

    The repair is considered successful only if:
    - The result is valid JSON
    - It has a "files" array
    - Each file entry has at least "path" and "new_content"
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Optional LLM client for repair calls. If None, only rule-based repair is attempted.
        """
        self.llm_client = llm_client
        self.repair_attempts = 0
        self.repair_successes = 0

    def attempt_repair(
        self,
        raw_output: str,
        error_message: str,
        max_llm_attempts: int = 1
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Attempt to repair malformed JSON Builder output.

        Args:
            raw_output: The raw LLM output that failed to parse
            error_message: The JSON decode error message
            max_llm_attempts: Max number of LLM repair calls to make

        Returns:
            Tuple of (repaired_json, repair_method) where:
            - repaired_json is the parsed dict if successful, None if failed
            - repair_method describes what worked (for telemetry)
        """
        self.repair_attempts += 1

        # Strategy 1: Rule-based repairs
        repaired, method = self._rule_based_repair(raw_output, error_message)
        if repaired is not None:
            self.repair_successes += 1
            logger.info(f"[JsonRepair] Rule-based repair succeeded: {method}")
            return repaired, f"rule_based:{method}"

        # Strategy 2: LLM-assisted repair (if client available)
        if self.llm_client and max_llm_attempts > 0:
            repaired, method = self._llm_repair(raw_output, error_message)
            if repaired is not None:
                self.repair_successes += 1
                logger.info(f"[JsonRepair] LLM repair succeeded: {method}")
                return repaired, f"llm_repair:{method}"

        logger.warning(f"[JsonRepair] All repair strategies failed for error: {error_message[:100]}")
        return None, "failed"

    def _rule_based_repair(
        self,
        raw_output: str,
        error_message: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Apply rule-based fixes for common JSON issues."""

        # Track what we tried
        repairs_applied = []

        # Clean the input
        text = raw_output.strip()

        # Rule 1: Strip markdown code fences that might have extra content
        if text.startswith("```"):
            # Find the actual JSON start
            json_start = text.find("{")
            if json_start > 0:
                text = text[json_start:]
                repairs_applied.append("strip_prefix")

        # Rule 2: Strip trailing markdown fence
        if "```" in text:
            fence_pos = text.rfind("```")
            # Only strip if the fence is after the JSON
            if fence_pos > text.rfind("}"):
                text = text[:fence_pos].strip()
                repairs_applied.append("strip_suffix")

        # Rule 3: Fix unescaped newlines in strings
        # This is tricky - we need to be careful not to break valid JSON
        if "\\n" not in text and "\n" in text:
            # Try to identify strings with newlines and escape them
            fixed = self._escape_newlines_in_strings(text)
            if fixed != text:
                text = fixed
                repairs_applied.append("escape_newlines")

        # Rule 4: Balance brackets
        text = self._balance_brackets(text)
        if "balance" not in repairs_applied:
            repairs_applied.append("balance_brackets")

        # Rule 5: Fix trailing commas
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        repairs_applied.append("fix_trailing_commas")

        # Rule 6: Add missing closing brackets based on error position
        if "Expecting ',' or '}'" in error_message or "Unterminated string" in error_message:
            # Try adding closing brackets at the end
            open_braces = text.count('{') - text.count('}')
            open_brackets = text.count('[') - text.count(']')
            if open_braces > 0 or open_brackets > 0:
                text = text + (']' * open_brackets) + ('}' * open_braces)
                repairs_applied.append("add_closing")

        # Try to parse the repaired text
        try:
            result = json.loads(text)
            if self._validate_builder_schema(result):
                return result, "+".join(repairs_applied)
        except json.JSONDecodeError:
            pass

        return None, "rule_based_failed"

    def _escape_newlines_in_strings(self, text: str) -> str:
        """Attempt to escape literal newlines inside JSON strings."""
        # This is a heuristic - we look for strings that span multiple lines
        # and try to escape the newlines
        result = []
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                result.append(char)
                escape_next = True
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                continue

            if char == '\n' and in_string:
                result.append('\\n')
            else:
                result.append(char)

        return ''.join(result)

    def _balance_brackets(self, text: str) -> str:
        """Balance JSON brackets by adding missing closing brackets."""
        # Count brackets
        stack = []
        for char in text:
            if char in '{[':
                stack.append(char)
            elif char == '}':
                if stack and stack[-1] == '{':
                    stack.pop()
            elif char == ']':
                if stack and stack[-1] == '[':
                    stack.pop()

        # Add missing closers
        closers = []
        for opener in reversed(stack):
            if opener == '{':
                closers.append('}')
            elif opener == '[':
                closers.append(']')

        return text + ''.join(closers)

    def _validate_builder_schema(self, data: Dict[str, Any]) -> bool:
        """Validate that the JSON matches the expected Builder schema."""
        if not isinstance(data, dict):
            return False

        files = data.get("files")
        if not isinstance(files, list):
            return False

        if len(files) == 0:
            # Empty files array is technically valid but not useful
            # We still accept it as "valid JSON" and let the caller handle it
            return True

        for file_entry in files:
            if not isinstance(file_entry, dict):
                return False
            if "path" not in file_entry:
                return False
            # new_content can be missing for delete operations
            mode = file_entry.get("mode", "modify")
            if mode in ("modify", "create") and "new_content" not in file_entry:
                return False

        return True

    def _llm_repair(
        self,
        raw_output: str,
        error_message: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Use an LLM to repair the JSON."""
        if not self.llm_client:
            return None, "no_llm_client"

        repair_prompt = f"""You are a JSON repair assistant. Your task is to fix malformed JSON.

## Input (malformed JSON)
```
{raw_output[:4000]}
```

## Error
{error_message}

## Expected Schema
The JSON must have this structure:
{{
  "summary": "optional string describing the changes",
  "files": [
    {{
      "path": "path/to/file",
      "mode": "modify|create|delete",
      "new_content": "the complete file content"
    }}
  ]
}}

## Instructions
1. Fix ONLY syntax errors (missing brackets, unescaped characters, trailing commas)
2. Do NOT modify the content of strings or add/remove files
3. Do NOT add explanations - output ONLY the repaired JSON
4. If the input cannot be repaired, output exactly: {{"error": "unrepairable"}}

Output the repaired JSON now:"""

        try:
            # Call LLM for repair (using a cheap/fast model)
            response = self.llm_client.repair_json(repair_prompt)
            if response:
                # Try to parse the repair response
                repaired_text = response.strip()
                # Strip any markdown fences the repair model might add
                if repaired_text.startswith("```"):
                    repaired_text = repaired_text.split("```")[1]
                    if repaired_text.startswith("json"):
                        repaired_text = repaired_text[4:]
                if repaired_text.endswith("```"):
                    repaired_text = repaired_text[:-3]

                result = json.loads(repaired_text.strip())

                # Check if repair model gave up
                if result.get("error") == "unrepairable":
                    return None, "llm_gave_up"

                if self._validate_builder_schema(result):
                    return result, "llm_fixed"

        except Exception as e:
            logger.warning(f"[JsonRepair] LLM repair failed: {e}")

        return None, "llm_failed"


class YamlRepairHelper:
    """
    Attempts to repair malformed YAML content.

    Strategies:
    1. Rule-based fixes (fix common YAML issues)
    2. LLM-assisted repair (call a model to fix the YAML)
    3. Fall back to structured edits (suggest smaller changes to original)
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.repair_attempts = 0
        self.repair_successes = 0

    def attempt_repair(
        self,
        old_yaml: str,
        new_yaml: str,
        error_message: str,
        file_path: str
    ) -> Tuple[Optional[str], str]:
        """
        Attempt to repair malformed YAML.

        Args:
            old_yaml: The original valid YAML content
            new_yaml: The new YAML that failed to parse
            error_message: The YAML parse error message
            file_path: Path to the file (for context)

        Returns:
            Tuple of (repaired_yaml, repair_method) where:
            - repaired_yaml is the fixed content if successful, None if failed
            - repair_method describes what worked (for telemetry)
        """
        self.repair_attempts += 1

        # Strategy 1: Rule-based repairs
        repaired, method = self._rule_based_repair(new_yaml, error_message)
        if repaired is not None:
            self.repair_successes += 1
            logger.info(f"[YamlRepair] Rule-based repair succeeded: {method}")
            return repaired, f"rule_based:{method}"

        # Strategy 2: LLM-assisted repair
        if self.llm_client:
            repaired, method = self._llm_repair(old_yaml, new_yaml, error_message, file_path)
            if repaired is not None:
                self.repair_successes += 1
                logger.info(f"[YamlRepair] LLM repair succeeded: {method}")
                return repaired, f"llm_repair:{method}"

        # Strategy 3: Suggest using the old YAML with minimal edits
        # This is a fallback that preserves safety
        logger.warning(f"[YamlRepair] All repair strategies failed, suggesting original")
        return None, "failed"

    def _rule_based_repair(
        self,
        yaml_content: str,
        error_message: str
    ) -> Tuple[Optional[str], str]:
        """Apply rule-based fixes for common YAML issues."""
        import yaml

        repairs_applied = []
        text = yaml_content

        # Rule 1: Fix truncated strings (unclosed quotes)
        if "while scanning a quoted scalar" in error_message or "found unexpected end of stream" in error_message:
            # Try to close unclosed strings
            lines = text.split('\n')
            fixed_lines = []
            for line in lines:
                # Count quotes in line
                quote_count = line.count('"') - line.count('\\"')
                if quote_count % 2 == 1:
                    # Odd number of quotes - try to close it
                    line = line + '"'
                    repairs_applied.append("close_string")
                fixed_lines.append(line)
            text = '\n'.join(fixed_lines)

        # Rule 2: Fix incomplete list items
        if text.strip().endswith('-'):
            text = text.rstrip() + ' ""'
            repairs_applied.append("complete_list_item")

        # Rule 3: Remove trailing incomplete lines
        lines = text.split('\n')
        while lines and lines[-1].strip().startswith('-') and ':' not in lines[-1]:
            # Incomplete list item at end - remove it
            lines.pop()
            repairs_applied.append("remove_incomplete_line")
        text = '\n'.join(lines)

        # Rule 4: Ensure proper ending
        if not text.endswith('\n'):
            text = text + '\n'

        # Try to parse
        try:
            yaml.safe_load(text)
            if repairs_applied:
                return text, "+".join(repairs_applied)
        except yaml.YAMLError:
            pass

        return None, "rule_based_failed"

    def _llm_repair(
        self,
        old_yaml: str,
        new_yaml: str,
        error_message: str,
        file_path: str
    ) -> Tuple[Optional[str], str]:
        """Use an LLM to repair the YAML."""
        import yaml

        if not self.llm_client:
            return None, "no_llm_client"

        # Truncate for prompt size
        old_yaml_truncated = old_yaml[:3000] if len(old_yaml) > 3000 else old_yaml
        new_yaml_truncated = new_yaml[:3000] if len(new_yaml) > 3000 else new_yaml

        repair_prompt = f"""You are a YAML repair assistant. Fix the malformed YAML below.

## File: {file_path}

## Original valid YAML (reference)
```yaml
{old_yaml_truncated}
```

## New YAML (malformed)
```yaml
{new_yaml_truncated}
```

## Parse Error
{error_message}

## Instructions
1. Fix ONLY the syntax errors in the new YAML
2. Preserve ALL content and structure from the new YAML
3. If the new YAML is truncated/incomplete, complete it based on the original structure
4. Do NOT change the semantic content - only fix syntax
5. Output ONLY the repaired YAML, no explanations
6. If unrepairable, output: # UNREPAIRABLE

Repaired YAML:"""

        try:
            response = self.llm_client.repair_yaml(repair_prompt)
            if response:
                repaired_text = response.strip()

                # Strip markdown fences if present
                if repaired_text.startswith("```yaml"):
                    repaired_text = repaired_text[7:]
                elif repaired_text.startswith("```"):
                    repaired_text = repaired_text[3:]
                if repaired_text.endswith("```"):
                    repaired_text = repaired_text[:-3]

                repaired_text = repaired_text.strip()

                # Check if repair model gave up
                if repaired_text.startswith("# UNREPAIRABLE"):
                    return None, "llm_gave_up"

                # Validate the repaired YAML
                yaml.safe_load(repaired_text)
                return repaired_text, "llm_fixed"

        except Exception as e:
            logger.warning(f"[YamlRepair] LLM repair failed: {e}")

        return None, "llm_failed"


def save_repair_debug(
    file_path: str,
    original: str,
    attempted: str,
    repaired: Optional[str],
    error: str,
    method: str,
    run_id: str = "unknown"
):
    """
    Save repair attempt to debug directory for postmortem analysis.

    Args:
        file_path: Original file being repaired
        original: Original content
        attempted: Content that failed
        repaired: Repaired content (if successful)
        error: Error message
        method: Repair method used
        run_id: Run ID for tracking
    """
    debug_dir = Path(".autonomous_runs/autopack/debug/repairs")
    debug_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = file_path.replace("/", "_").replace("\\", "_")

    debug_file = debug_dir / f"{timestamp}_{safe_name}_repair.json"

    debug_data = {
        "timestamp": timestamp,
        "run_id": run_id,
        "file_path": file_path,
        "error_message": error,
        "repair_method": method,
        "success": repaired is not None,
        "original_length": len(original) if original else 0,
        "attempted_length": len(attempted) if attempted else 0,
        "repaired_length": len(repaired) if repaired else 0,
    }

    # Also save the actual content for detailed analysis
    if len(attempted) < 10000:  # Only save if not too large
        debug_data["attempted_content"] = attempted
    if repaired and len(repaired) < 10000:
        debug_data["repaired_content"] = repaired

    try:
        debug_file.write_text(json.dumps(debug_data, indent=2), encoding="utf-8")
        logger.debug(f"[Repair] Saved debug info to {debug_file}")
    except Exception as e:
        logger.warning(f"[Repair] Failed to save debug info: {e}")
