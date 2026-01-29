"""Anthropic Claude-based Builder and Auditor implementations

Per models.yaml configuration:
- Claude Opus 4.5 for high-risk auditing
- Claude Sonnet 4.5 for progressive strategy auditing
- Complementary to OpenAI models for dual auditing

This module provides Anthropic API integration for when
ModelRouter selects Claude models based on category/quota.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from anthropic import Anthropic
except ImportError:
    # Graceful degradation if anthropic package not installed
    Anthropic = None

from .journal_reader import get_prevention_prompt_injection
# PR-CLIENT-2: Import parser modules for output format handling
from .llm.anthropic.parsers import FullFileParser, NDJSONParserWrapper
# PR-CLIENT-1: Import phase execution orchestrator
from .llm.anthropic.phase_executor import AnthropicPhaseExecutor
# PR-LLM-1: Import transport wrapper for clean separation of transport layer
from .llm.providers.anthropic_transport import (AnthropicTransport,
                                                AnthropicTransportError)
from .llm_client import AuditorResult, BuilderResult

# BUILD-129 Phase 1: Deliverable-based token estimation

# BUILD-129 Phase 2: Continuation-based recovery

# BUILD-129 Phase 3: NDJSON truncation-tolerant format


logger = logging.getLogger(__name__)

# IMP-COST-006: Size limits for project rules in auditor prompts
# These prevent large rulesets from adding excessive tokens
MAX_RULE_CHARS = 500  # Max characters per individual rule
MAX_TOTAL_RULES_TOKENS = 2000  # Max total tokens for all rules (~4 chars per token)


def _write_token_estimation_v2_telemetry(
    run_id: str,
    phase_id: str,
    category: str,
    complexity: str,
    deliverables: List[str],
    predicted_output_tokens: int,
    actual_output_tokens: int,
    selected_budget: int,
    success: bool,
    truncated: bool,
    stop_reason: Optional[str],
    model: str,
    # BUILD-129 Phase 3: Feature tracking for DOC_SYNTHESIS analysis
    is_truncated_output: bool = False,
    api_reference_required: Optional[bool] = None,
    examples_required: Optional[bool] = None,
    research_required: Optional[bool] = None,
    usage_guide_required: Optional[bool] = None,
    context_quality: Optional[str] = None,
    # BUILD-129 Phase 3 P3: SOT file tracking
    is_sot_file: Optional[bool] = None,
    sot_file_name: Optional[str] = None,
    sot_entry_count_hint: Optional[int] = None,
    # BUILD-142 PARITY: Separate estimator intent from final ceiling
    actual_max_tokens: Optional[int] = None,
) -> None:
    """Write TokenEstimationV2 event to database for validation.

    Feature flag: TELEMETRY_DB_ENABLED (default: false for backwards compat)

    BUILD-129 Phase 3: Now captures feature flags for DOC_SYNTHESIS tasks to enable
    phase-based estimation analysis and truncation-aware calibration.

    BUILD-129 Phase 3 P3: Now captures SOT (Source of Truth) file metadata for
    specialized estimation of BUILD_LOG.md, BUILD_HISTORY.md, etc.

    BUILD-142 PARITY: Now captures actual_max_tokens (final ceiling after P4 enforcement)
    separately from selected_budget (estimator intent) for accurate waste calculation.
    """
    # Feature flag check
    if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() not in ["1", "true", "yes"]:
        return

    # BUILD-129 Phase 3: Telemetry validity guard
    # Reject anomalous events with suspiciously low actual_output_tokens (<50)
    # These are likely parser errors, API failures, or other edge cases that corrupt metrics
    if actual_output_tokens < 50:
        logger.warning(
            f"[TELEMETRY] Skipping invalid event for {phase_id}: actual_output_tokens={actual_output_tokens} < 50 (likely error)"
        )
        return

    try:
        from .database import SessionLocal
        from .models import Phase as PhaseModel
        from .models import TokenEstimationV2Event

        # Calculate metrics
        if actual_output_tokens > 0 and predicted_output_tokens > 0:
            denom = (abs(actual_output_tokens) + abs(predicted_output_tokens)) / 2
            smape = abs(actual_output_tokens - predicted_output_tokens) / max(1, denom) * 100.0
            waste_ratio = predicted_output_tokens / actual_output_tokens
            underestimated = actual_output_tokens > predicted_output_tokens
        else:
            smape = None
            waste_ratio = None
            underestimated = None

        # Sanitize deliverables (max 20, truncate long paths)
        deliverables_clean = []
        for d in deliverables[:20]:  # Cap at 20
            if len(str(d)) > 200:
                deliverables_clean.append(str(d)[:197] + "...")
            else:
                deliverables_clean.append(str(d))

        deliverables_json = json.dumps(deliverables_clean)

        # Try to resolve run_id if caller passed "unknown"/empty.
        # In most flows, the executor has the true run_id; but some legacy call paths
        # may not populate phase_spec["run_id"]. Use the phases table as a best-effort lookup.
        if not run_id or run_id == "unknown":
            session_lookup = SessionLocal()
            try:
                phase_row = (
                    session_lookup.query(PhaseModel)
                    .filter(PhaseModel.phase_id == phase_id)
                    .order_by(PhaseModel.run_id.desc())
                    .first()
                )
                if phase_row and getattr(phase_row, "run_id", None):
                    run_id = phase_row.run_id
            finally:
                try:
                    session_lookup.close()
                except Exception as e:
                    logger.debug(f"Non-critical: session_lookup close failed: {e}")

        # Write to DB
        session = SessionLocal()
        try:
            event = TokenEstimationV2Event(
                run_id=run_id,
                phase_id=phase_id,
                category=category,
                complexity=complexity,
                deliverable_count=len(deliverables),
                deliverables_json=deliverables_json,
                predicted_output_tokens=predicted_output_tokens,
                actual_output_tokens=actual_output_tokens,
                selected_budget=selected_budget,
                success=success,
                truncated=truncated,
                stop_reason=stop_reason,
                model=model,
                # Keep DB semantics aligned with migrations/views:
                # - smape_percent is a percent (float)
                # - waste_ratio is predicted/actual (float ratio, not percent)
                smape_percent=float(smape) if smape is not None else None,
                waste_ratio=float(waste_ratio) if waste_ratio is not None else None,
                underestimated=underestimated,
                # BUILD-129 Phase 3: Feature tracking for DOC_SYNTHESIS
                is_truncated_output=is_truncated_output,
                api_reference_required=api_reference_required,
                examples_required=examples_required,
                research_required=research_required,
                usage_guide_required=usage_guide_required,
                context_quality=context_quality,
                # BUILD-129 Phase 3 P3: SOT file tracking
                is_sot_file=is_sot_file,
                sot_file_name=sot_file_name,
                sot_entry_count_hint=sot_entry_count_hint,
                # BUILD-142 PARITY: Final ceiling after P4 enforcement
                actual_max_tokens=actual_max_tokens,
            )
            session.add(event)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        # Don't fail the build on telemetry errors
        logger.warning(f"[TokenEstimationV2] Failed to write DB telemetry: {e}")


# Per GPT_RESPONSE24 C1: Normalize complexity to handle variations
ALLOWED_COMPLEXITIES = {"low", "medium", "high", "maintenance"}


def normalize_complexity(value: str | None) -> str:
    """
    Normalize complexity value to canonical form.

    Per GPT_RESPONSE24 C1: Handle case variations, common suffixes, and aliases.
    Per GPT_RESPONSE25 C1: Log DATA_INTEGRITY for unknown values and fallback to "medium".

    Args:
        value: Raw complexity value from phase_spec

    Returns:
        Normalized complexity value (always one of ALLOWED_COMPLEXITIES)
    """
    if value is None:
        return "medium"  # Default

    v = value.strip().lower()

    # Strip common suffixes (per GPT1 and GPT2)
    for suffix in (
        "_complexity",
        "-complexity",
        "_level",
        "-level",
        "_mode",
        "-mode",
        "_task",
        "_tier",
    ):
        if v.endswith(suffix):
            v = v[: -len(suffix)]

    # Map common aliases (per GPT1 and GPT2)
    alias_map = {
        "low": "low",
        "medium": "medium",
        "med": "medium",
        "high": "high",
        "maint": "maintenance",
        "maintain": "maintenance",
        "maintenance": "maintenance",
        "maintenance_mode": "maintenance",
    }

    normalized = alias_map.get(v, v)

    # Per GPT_RESPONSE25 C1: Guard for unknown values - log and fallback to "medium"
    if normalized not in ALLOWED_COMPLEXITIES:
        logger.warning(
            "[DATA_INTEGRITY] Unknown complexity value %r (normalized to %r); "
            "falling back to 'medium'. Consider adding to alias_map if valid.",
            value,
            normalized,
        )
        return "medium"

    return normalized


class AnthropicBuilderClient:
    """Builder implementation using Anthropic Claude API

    Currently used for:
    - Test generation (claude-sonnet-4-5 per models.yaml)
    - Escalation scenarios when OpenAI quota exhausted
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic client

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        # PR-LLM-1: Use transport wrapper for clean separation
        try:
            self.transport = AnthropicTransport(api_key=api_key, timeout=120.0)
        except AnthropicTransportError as e:
            # Maintain backwards compatibility with ImportError for missing package
            if "not installed" in str(e):
                raise ImportError(str(e))
            raise

        # PR-CLIENT-1: Initialize phase execution orchestrator
        self.phase_executor = AnthropicPhaseExecutor(self.transport, self)

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        use_full_file_mode: bool = True,
        config=None,
        retrieved_context: Optional[str] = None,
    ) -> BuilderResult:
        """Execute a phase using Claude.

        PR-CLIENT-1: This method now delegates to AnthropicPhaseExecutor for
        orchestration. The 1,014-line implementation has been extracted to
        phase_executor.py for better modularity.

        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            max_tokens: Token budget
            model: Claude model (claude-opus-4-5, claude-sonnet-4-5, etc.)
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            use_full_file_mode: If True, use new full-file replacement format
            config: BuilderOutputConfig instance
            retrieved_context: Retrieved context from vector memory

        Returns:
            BuilderResult with patch and metadata
        """
        # PR-CLIENT-1: Delegate to phase execution orchestrator
        return self.phase_executor.execute_phase(
            phase_spec=phase_spec,
            file_context=file_context,
            max_tokens=max_tokens,
            model=model,
            project_rules=project_rules,
            run_hints=run_hints,
            use_full_file_mode=use_full_file_mode,
            config=config,
            retrieved_context=retrieved_context,
        )

    def _parse_full_file_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Optional[Dict] = None,
        config=None,  # NEW: BuilderOutputConfig for thresholds
        stop_reason: Optional[str] = None,  # NEW: Anthropic stop_reason
        was_truncated: bool = False,  # NEW: Truncation flag
    ) -> "BuilderResult":
        """Parse full-file replacement output and generate git diff locally.

        Per GPT_RESPONSE10: LLM outputs complete file content, we generate diff.
        Per GPT_RESPONSE11: Added guards for large files, churn, and symbol validation.
        Per IMPLEMENTATION_PLAN2.md Phase 4: Added read-only enforcement and shrinkage/growth detection.

        Args:
            content: Raw LLM output (should be JSON)
            file_context: Original file contents for diff generation
            response: API response object for token usage
            model: Model identifier
            phase_spec: Phase specification for churn classification
            config: BuilderOutputConfig for thresholds (per IMPLEMENTATION_PLAN2.md)

        Returns:
            BuilderResult with generated patch
        """
        # PR-CLIENT-2: Delegate to FullFileParser
        parser = FullFileParser()
        result = parser.parse(
            content=content,
            file_context=file_context,
            response=response,
            model=model,
            phase_spec=phase_spec,
            config=config,
            stop_reason=stop_reason,
            was_truncated=was_truncated,
        )

        # Convert FullFileParseResult to BuilderResult
        return BuilderResult(
            success=result.success,
            patch_content=result.patch_content,
            builder_messages=(
                [result.summary] if result.success else ([result.error] if result.error else [])
            ),
            tokens_used=result.tokens_used,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            model_used=model,
            error=result.error,
            stop_reason=result.stop_reason,
            was_truncated=result.was_truncated,
        )

    def _parse_legacy_diff_output(
        self,
        content: str,
        response,
        model: str,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> "BuilderResult":
        """Parse legacy git diff output from LLM.

        This is the deprecated mode where LLM generates raw git diffs.
        Kept for backward compatibility.

        Args:
            content: Raw LLM output
            response: API response object for token usage
            model: Model identifier

        Returns:
            BuilderResult with extracted patch
        """
        patch_content = ""
        summary = "Generated by Claude"

        try:
            # Try to parse as direct JSON first
            result_json = json.loads(content)
            patch_content = result_json.get("patch_content", "")
            summary = result_json.get("summary", "Generated by Claude")
        except json.JSONDecodeError:
            # Check if wrapped in markdown code fence
            if "```json" in content:
                # Extract JSON from markdown code block
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
                    try:
                        result_json = json.loads(json_str)
                        patch_content = result_json.get("patch_content", "")
                        summary = result_json.get("summary", "Generated by Claude")
                    except json.JSONDecodeError:
                        pass

            # If still no patch, try to extract raw diff content
            if not patch_content:
                patch_content = self._extract_diff_from_text(content)
                if not patch_content:
                    # Format validation failed - return error
                    error_msg = "LLM output invalid format - no git diff markers found. Output must start with 'diff --git'"
                    # Include truncation info so autonomous_executor can trigger structured_edit fallback
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

        return BuilderResult(
            success=True,
            patch_content=patch_content,
            builder_messages=[summary],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            model_used=model,
            stop_reason=stop_reason,
            was_truncated=was_truncated,
        )

    def _parse_structured_edit_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Dict,
        config=None,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> "BuilderResult":
        """Parse LLM's structured edit JSON output (Stage 2)

        Per IMPLEMENTATION_PLAN3.md Phase 2.2
        """
        import json

        from autopack.builder_config import BuilderOutputConfig
        from autopack.structured_edits import (EditOperation,
                                               EditOperationType, EditPlan)

        if config is None:
            config = BuilderOutputConfig()

        # Extract existing files from context for format conversion
        files = {}
        if file_context:
            files = file_context.get("existing_files", {})
            if not isinstance(files, dict):
                logger.warning(
                    f"[Builder] file_context.get('existing_files') returned non-dict: {type(files)}, using empty dict"
                )
                files = {}

        try:
            # Parse JSON
            result_json = None
            initial_parse_error = None
            try:
                result_json = json.loads(content.strip())
            except json.JSONDecodeError as e:
                initial_parse_error = str(e)
                # Try extracting from markdown code fence
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        json_str = content[json_start:json_end].strip()
                        try:
                            result_json = json.loads(json_str)
                            initial_parse_error = None  # Fence extraction succeeded
                        except json.JSONDecodeError as e2:
                            initial_parse_error = str(e2)

            if not result_json:
                # BUILD-039: Apply JSON repair to structured_edit mode (same as full-file mode)
                logger.info(
                    "[Builder] Attempting JSON repair on malformed structured_edit output..."
                )
                from autopack.repair_helpers import (JsonRepairHelper,
                                                     save_repair_debug)

                json_repair = JsonRepairHelper()
                error_msg = initial_parse_error or "Failed to parse JSON with 'operations' array"
                repaired_json, repair_method = json_repair.attempt_repair(content, error_msg)

                if repaired_json is not None:
                    logger.info(
                        f"[Builder] Structured edit JSON repair succeeded via {repair_method}"
                    )
                    save_repair_debug(
                        file_path="builder_structured_edit.json",
                        original="",
                        attempted=content,
                        repaired=json.dumps(repaired_json),
                        error=error_msg,
                        method=repair_method,
                    )
                    result_json = repaired_json
                else:
                    # JSON repair failed - return error
                    error_msg = "LLM output invalid format - expected JSON with 'operations' array"
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            # Extract summary and operations
            summary = result_json.get("summary", "Structured edits")
            operations_json = result_json.get("operations", [])

            # BUILD-040: Auto-convert full-file format to structured_edit format
            # If LLM produced {"files": [...]} instead of {"operations": [...]}, convert it
            if not operations_json and "files" in result_json:
                logger.info(
                    "[Builder] Detected full-file format in structured_edit mode - auto-converting to operations"
                )
                files_json = result_json.get("files", [])
                operations_json = []

                for file_entry in files_json:
                    file_path = file_entry.get("path")
                    mode = file_entry.get("mode", "modify")
                    new_content = file_entry.get("new_content")

                    if not file_path:
                        continue

                    if mode == "create" and new_content:
                        # Convert "create" to prepend operation (which creates file if missing)
                        # Using prepend instead of insert to handle non-existent files
                        operations_json.append(
                            {"type": "prepend", "file_path": file_path, "content": new_content}
                        )
                        logger.info(
                            f"[Builder] Converted create file '{file_path}' to prepend operation"
                        )
                    elif mode == "delete":
                        # For delete, we need to know file line count
                        # Since we don't have it here, skip delete conversions
                        # DELETE mode is rare for restoration tasks anyway
                        logger.warning(
                            f"[Builder] Skipping delete mode conversion for '{file_path}' (not supported)"
                        )
                        continue
                    elif mode == "modify" and new_content:
                        # Convert "modify" to replace operation (whole file)
                        # Check if file exists in context to get line count
                        file_exists = file_path in files
                        if file_exists:
                            # Get actual line count from existing file
                            existing_content = files.get(file_path, "")
                            if isinstance(existing_content, str):
                                line_count = existing_content.count("\n") + 1
                                operations_json.append(
                                    {
                                        "type": "replace",
                                        "file_path": file_path,
                                        "start_line": 1,
                                        "end_line": line_count,
                                        "content": new_content,
                                    }
                                )
                                logger.info(
                                    f"[Builder] Converted modify file '{file_path}' to replace operation (lines 1-{line_count})"
                                )
                            else:
                                logger.warning(
                                    f"[Builder] Skipping modify for '{file_path}' (existing content not string)"
                                )
                        else:
                            # File doesn't exist, treat as create (use prepend)
                            operations_json.append(
                                {"type": "prepend", "file_path": file_path, "content": new_content}
                            )
                            logger.info(
                                f"[Builder] Converted modify non-existent file '{file_path}' to prepend operation (create)"
                            )

                if operations_json:
                    logger.info(
                        f"[Builder] Format conversion successful: {len(operations_json)} operations generated"
                    )
                else:
                    logger.warning("[Builder] Format conversion produced no operations")

            if not operations_json:
                # Treat empty structured edits as a safe no-op rather than a hard failure.
                info_msg = "Structured edit produced no operations; treating as no-op"
                logger.warning(f"[Builder] {info_msg}")
                return BuilderResult(
                    success=True,
                    patch_content="",
                    builder_messages=[info_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=None,
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
                        context_after=op_json.get("context_after"),
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
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                            model_used=model,
                            error=error_msg,
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
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        model_used=model,
                        error=error_msg,
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
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=error_msg,
                )

            # Store edit plan in BuilderResult
            logger.info(
                f"[Builder] Generated structured edit plan with {len(operations)} operations"
            )

            return BuilderResult(
                success=True,
                patch_content="",  # No patch content for structured edits
                builder_messages=[f"Generated {len(operations)} edit operations"],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                edit_plan=edit_plan,  # NEW: Store edit plan
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        except Exception as e:
            logger.error(f"[Builder] Error parsing structured edit output: {e}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[str(e)],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                error=str(e),
            )

    def _parse_ndjson_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response: Any,
        model: str,
        phase_spec: Dict,
        config: Optional[Any] = None,
        stop_reason: Optional[str] = None,
        was_truncated: bool = False,
    ) -> BuilderResult:
        """
        Parse NDJSON format output (BUILD-129 Phase 3).

        NDJSON is truncation-tolerant: each line is a complete JSON object,
        so if truncation occurs, all complete lines are still usable.

        Args:
            content: Raw LLM output in NDJSON format
            file_context: Repository file context
            response: API response object
            model: Model name
            phase_spec: Phase specification
            config: Builder configuration
            stop_reason: Stop reason from API
            was_truncated: Whether output was truncated

        Returns:
            BuilderResult with success/failure status
        """
        # PR-CLIENT-2: Delegate to NDJSONParserWrapper
        parser = NDJSONParserWrapper()

        # Define fallback handlers for format detection
        def fallback_structured_edit():
            return self._parse_structured_edit_output(
                content=content,
                file_context=file_context,
                response=response,
                model=model,
                phase_spec=phase_spec,
                config=config,
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        def fallback_legacy_diff():
            return self._parse_legacy_diff_output(
                content=content,
                response=response,
                model=model,
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        # Call parser with fallbacks
        return parser.parse(
            content=content,
            file_context=file_context,
            response=response,
            model=model,
            phase_spec=phase_spec,
            config=config,
            stop_reason=stop_reason,
            was_truncated=was_truncated,
            fallback_structured_edit=fallback_structured_edit,
            fallback_legacy_diff=fallback_legacy_diff,
        )

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> AuditorResult:
        """Review patch using Claude

        Args:
            patch_content: Git diff format patch
            phase_spec: Phase specification
            file_context: Repository context
            max_tokens: Token budget
            model: Claude model
            project_rules: Learned rules
            run_hints: Within-run hints from earlier phases

        Returns:
            AuditorResult with issues found
        """
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Build user prompt
            user_prompt = self._build_user_prompt(
                patch_content, phase_spec, file_context, project_rules, run_hints
            )

            # PR-LLM-1: Call Anthropic API via transport wrapper
            # Use higher token limit to avoid truncation on complex reviews
            # Actual usage is typically ~500 tokens for JSON response
            response = self.transport.send_request(
                messages=[{"role": "user", "content": user_prompt}],
                model=model,
                max_tokens=min(max_tokens or 8192, 8192),
                system=system_prompt,
                temperature=0.1,  # Low temperature for consistent auditing
                stream=False,
            )

            # Extract content
            content = response.content

            # Parse JSON response
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: treat as text review
                result_json = {
                    "approved": False,
                    "issues": [{"severity": "major", "description": content}],
                    "summary": "Review completed",
                }

            return AuditorResult(
                approved=result_json.get("approved", False),
                issues_found=result_json.get("issues", []),
                auditor_messages=[result_json.get("summary", "")],
                tokens_used=response.usage.total_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=response.model,
            )

        except Exception as e:
            # Log error before returning error result
            logger.error(f"Auditor review failed: {e}", exc_info=True)
            return AuditorResult(
                approved=False,
                issues_found=[
                    {
                        "severity": "critical",
                        "category": "auditor_error",
                        "description": f"Auditor error: {str(e)}",
                    }
                ],
                auditor_messages=[f"Auditor failed: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e),
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for Claude Auditor"""
        base_prompt = """You are an expert code reviewer for an autonomous build system.

Your task is to review code patches for:
- Security vulnerabilities (OWASP Top 10)
- Type safety issues
- Edge cases and error handling
- Performance problems
- Best practice violations

Output Format (JSON):
{
  "approved": true/false,
  "issues": [
    {
      "severity": "minor|major|critical",
      "category": "security|types|logic|performance|style",
      "description": "Detailed issue description",
      "file_path": "path/to/file.py",
      "line_number": 42
    }
  ],
  "summary": "Brief review summary"
}

Approval Criteria:
- REJECT if any critical or major issues
- APPROVE if only minor issues or no issues"""

        # Inject prevention rules from debug journal
        try:
            prevention_rules = get_prevention_prompt_injection()
            if prevention_rules:
                base_prompt += "\n\n" + prevention_rules
        except (FileNotFoundError, IOError) as e:
            # File not available - this is expected in some environments
            logger.debug(f"Prevention rules file not available: {e}")
        except (ValueError, KeyError) as e:
            # Malformed prevention rules - log and continue
            logger.warning(f"Could not parse prevention rules: {e}")
        except Exception as e:
            # Unexpected error - log for debugging but don't fail the build
            logger.warning(f"Unexpected error loading prevention rules: {e}")

        return base_prompt

    def _build_user_prompt(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List],
        run_hints: Optional[List] = None,
    ) -> str:
        """Build user prompt with patch to review"""
        prompt_parts = [
            "# Patch to Review",
            f"```diff\n{patch_content}\n```",
            "\n# Phase Context",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Description: {phase_spec.get('description', '')}",
        ]

        if project_rules:
            prompt_parts.append("\n# Project Rules (check compliance):")
            # IMP-COST-006: Apply size limits to prevent excessive token usage
            total_chars = 0
            max_total_chars = MAX_TOTAL_RULES_TOKENS * 4  # ~4 chars per token
            rules_truncated = 0
            rules_added = 0

            for rule in project_rules:
                rule_text = rule.get("rule_text", "")
                if not rule_text:
                    continue

                # Truncate individual rules exceeding max chars
                if len(rule_text) > MAX_RULE_CHARS:
                    rule_text = rule_text[:MAX_RULE_CHARS] + "..."
                    rules_truncated += 1

                # Stop adding rules if total char budget exceeded
                if total_chars + len(rule_text) > max_total_chars:
                    rules_skipped = len(project_rules) - rules_added
                    logger.info(
                        f"Project rules truncated: {rules_skipped} rules skipped "
                        f"(total chars {total_chars} approaching limit {max_total_chars})"
                    )
                    break

                prompt_parts.append(f"- {rule_text}")
                total_chars += len(rule_text)
                rules_added += 1

            if rules_truncated > 0:
                logger.info(
                    f"Project rules: {rules_truncated} individual rules truncated "
                    f"to {MAX_RULE_CHARS} chars"
                )

        if run_hints:
            prompt_parts.append("\n# Recent Run Hints:")
            for hint in run_hints[:5]:
                prompt_parts.append(f"- {hint}")

        # Milestone 2: Inject intention anchor (for validation context)
        if run_id := phase_spec.get("run_id"):
            from .intention_anchor import load_and_render_for_auditor

            anchor_section = load_and_render_for_auditor(
                run_id=run_id,
                base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
            )
            if anchor_section:
                prompt_parts.append("\n")
                prompt_parts.append(anchor_section)

        prompt_parts.append("\nProvide your review as a JSON response.")

        return "\n".join(prompt_parts)
