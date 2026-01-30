"""NDJSON format parser for Anthropic Builder responses.

Extracted from anthropic_clients.py lines 2762-3169 as part of PR-CLIENT-2.
Handles parsing of NDJSON (newline-delimited JSON) output format.

NDJSON is truncation-tolerant: each line is a complete JSON object,
so if truncation occurs, all complete lines are still usable.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ....llm_client import BuilderResult
from ....ndjson_format import NDJSONApplier, NDJSONParser

logger = logging.getLogger(__name__)


@dataclass
class NDJSONParseContext:
    """Context for NDJSON parsing."""

    content: str
    file_context: Optional[Dict]
    response: Any
    model: str
    phase_spec: Dict
    config: Optional[Any]
    stop_reason: Optional[str]
    was_truncated: bool


class NDJSONParserWrapper:
    """Parses NDJSON format Builder responses.

    NDJSON (Newline-Delimited JSON) format has one JSON object per line,
    making it more robust to truncation and streaming.

    This parser includes extensive fallback logic to handle cases where
    the model returns alternative formats (structured edit, JSON arrays).

    Responsibilities:
    1. Parse line-by-line JSON objects
    2. Handle format detection and fallback
    3. Apply operations to workspace
    4. Validate against deliverables manifest
    5. Generate synthetic diff markers
    """

    def parse(
        self,
        content: str,
        file_context: Optional[Dict],
        response: Any,
        model: str,
        phase_spec: Dict,
        config: Optional[Any] = None,
        stop_reason: Optional[str] = None,
        was_truncated: bool = False,
        # Callbacks for fallback to other parsers
        fallback_structured_edit=None,
    ) -> BuilderResult:
        """Parse NDJSON format response.

        Extracted from anthropic_clients.py lines 2762-3169.

        Args:
            content: Raw LLM output in NDJSON format
            file_context: Repository file context
            response: API response object
            model: Model name
            phase_spec: Phase specification
            config: Builder configuration
            stop_reason: Stop reason from API
            was_truncated: Whether output was truncated
            fallback_structured_edit: Callback for structured edit fallback

        Returns:
            BuilderResult with success/failure status
        """
        try:
            # Pre-sanitize: strip common markdown fences that break NDJSON line parsing
            raw = content or ""
            lines = []
            for ln in raw.splitlines():
                s = ln.strip()
                if s.startswith("```"):
                    continue
                lines.append(ln)
            sanitized = "\n".join(lines).strip()

            # Detect if model returned structured-edit JSON instead of NDJSON
            if self._is_structured_edit_format(sanitized):
                logger.warning(
                    "[BUILD-129:NDJSON] Detected structured-edit JSON; falling back to structured-edit parser"
                )
                if fallback_structured_edit:
                    return fallback_structured_edit(
                        sanitized,
                        file_context,
                        response,
                        model,
                        phase_spec,
                        config=config,
                        stop_reason=stop_reason,
                        was_truncated=bool(was_truncated),
                    )

            # Parse NDJSON
            parser = NDJSONParser()
            parse_result = parser.parse(sanitized)

            logger.info(
                f"[BUILD-129:NDJSON] Parsed {parse_result.lines_parsed} lines, "
                f"{len(parse_result.operations)} operations, "
                f"truncated={parse_result.was_truncated}"
            )

            # Calculate effective truncation
            effective_truncation = self._calculate_effective_truncation(
                was_truncated, parse_result, phase_spec
            )

            # Handle empty operations with fallbacks
            if not parse_result.operations:
                return self._handle_no_operations(
                    sanitized,
                    parse_result,
                    file_context,
                    response,
                    model,
                    phase_spec,
                    config,
                    stop_reason,
                    effective_truncation,
                    content,
                    fallback_structured_edit,
                )

            # Apply operations using NDJSONApplier
            workspace = Path(file_context.get("workspace", ".")) if file_context else Path(".")
            applier = NDJSONApplier(workspace=workspace)

            # Validate against deliverables manifest
            manifest_error = self._validate_manifest(phase_spec, parse_result.operations)
            if manifest_error:
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=manifest_error["messages"],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    model_used=model,
                    error=manifest_error["error_code"],
                    stop_reason=stop_reason,
                    was_truncated=effective_truncation,
                    raw_output=content,
                )

            # Apply operations
            apply_result = applier.apply(parse_result.operations)

            logger.info(
                f"[BUILD-129:NDJSON] Applied {len(apply_result['applied'])} operations, "
                f"{len(apply_result['failed'])} failed"
            )

            # Generate synthetic diff for deliverables validation
            patch_content = self._generate_synthetic_diff(apply_result)

            # Determine success
            success = len(apply_result["applied"]) > 0 and len(apply_result["failed"]) == 0

            # Build messages
            messages = self._build_messages(parse_result)

            return BuilderResult(
                success=success,
                patch_content=patch_content,
                builder_messages=messages,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                stop_reason=stop_reason,
                was_truncated=effective_truncation,
                raw_output=content,
            )

        except Exception as e:
            logger.error(f"[BUILD-129:NDJSON] Error parsing NDJSON output: {e}")
            error_msg = f"NDJSON parsing failed: {str(e)}"
            if was_truncated:
                error_msg += " (stop_reason=max_tokens)"

            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                error="ndjson_parse_error",
                stop_reason=stop_reason,
                was_truncated=was_truncated,
                raw_output=content,
            )

    def _is_structured_edit_format(self, sanitized: str) -> bool:
        """Check if content is structured-edit JSON instead of NDJSON."""
        try:
            if (
                sanitized.startswith("{")
                and '"operations"' in sanitized
                and "diff --git" not in sanitized
            ):
                obj = json.loads(sanitized)
                if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                    return True
        except Exception:
            pass
        return False

    def _calculate_effective_truncation(
        self, was_truncated: bool, parse_result, phase_spec: Dict
    ) -> bool:
        """Calculate effective truncation considering utilization."""
        output_utilization = 0.0
        try:
            tb = (phase_spec.get("metadata") or {}).get("token_budget") or {}
            output_utilization = float(tb.get("output_utilization") or 0.0)
        except Exception:
            output_utilization = 0.0

        return bool(was_truncated or (parse_result.was_truncated and output_utilization >= 95.0))

    def _handle_no_operations(
        self,
        sanitized: str,
        parse_result,
        file_context,
        response,
        model,
        phase_spec,
        config,
        stop_reason,
        effective_truncation,
        content,
        fallback_structured_edit,
    ) -> BuilderResult:
        """Handle case where no NDJSON operations were found."""
        # Check for unsupported diff format and return clear error
        if "diff --git" in sanitized or sanitized.startswith("*** Begin Patch"):
            logger.error(
                "[BUILD-129:NDJSON] Model returned diff format which is no longer supported. "
                "Use full-file or structured-edit format instead."
            )
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[
                    "Model returned unsupported diff format. Use full-file or structured-edit format."
                ],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                model_used=model,
                error="unsupported_diff_format",
                stop_reason=stop_reason,
                was_truncated=effective_truncation,
                raw_output=content,
            )

        # Fallback: Try to scan for structured-edit JSON
        structured_obj = self._scan_for_structured_edit(sanitized)
        if structured_obj and fallback_structured_edit:
            logger.warning(
                "[BUILD-129:NDJSON] Decoded structured-edit plan; routing to structured-edit parser"
            )
            plan_json = json.dumps(structured_obj, ensure_ascii=False)
            return fallback_structured_edit(
                plan_json,
                file_context,
                response,
                model,
                phase_spec,
                config=config,
                stop_reason=stop_reason,
                was_truncated=effective_truncation,
            )

        # Try to convert JSON array to NDJSON
        converted_result = self._try_convert_json_array(sanitized, parse_result)
        if converted_result and converted_result.operations:
            logger.info(
                f"[BUILD-129:NDJSON] Salvaged {len(converted_result.operations)} operations after fallback conversion"
            )
            # Re-process with converted operations (would need to apply them)
            # For now, treat as failure if we still have no ops after conversion attempt
            pass

        # No operations found after all fallbacks
        error_msg = "NDJSON parsing produced no valid operations"
        if effective_truncation:
            error_msg += " (truncated)"
        logger.error(error_msg)

        # Write debug sample
        self._write_debug_sample(sanitized, phase_spec, model, stop_reason, effective_truncation)

        return BuilderResult(
            success=False,
            patch_content="",
            builder_messages=[error_msg],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            model_used=model,
            error="ndjson_no_operations",
            stop_reason=stop_reason,
            was_truncated=effective_truncation,
            raw_output=content,
        )

    def _scan_for_structured_edit(self, sanitized: str) -> Optional[Dict]:
        """Scan for structured-edit JSON object in potentially malformed text."""
        try:
            import ast
            from json import JSONDecoder

            decoder = JSONDecoder()
            idx = 0

            while True:
                # Find next plausible JSON start
                m1 = sanitized.find("{", idx)
                m2 = sanitized.find("[", idx)
                starts = [p for p in (m1, m2) if p != -1]
                if not starts:
                    return None
                start = min(starts)
                try:
                    obj, end = decoder.raw_decode(sanitized[start:])
                    if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                        return obj
                except Exception:
                    # Try Python literal_eval as fallback
                    try:
                        obj = ast.literal_eval(sanitized[start:])
                        if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                            return obj
                    except Exception:
                        idx = start + 1
        except Exception:
            pass
        return None

    def _try_convert_json_array(self, sanitized: str, parse_result):
        """Try to convert JSON array format to NDJSON."""
        try:
            obj = json.loads(sanitized)
            parser = NDJSONParser()

            if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
                logger.warning(
                    "[BUILD-129:NDJSON] Detected JSON array; converting to NDJSON operations"
                )
                converted = "\n".join(json.dumps(x, ensure_ascii=False) for x in obj)
                return parser.parse(converted)
            elif isinstance(obj, dict) and obj.get("type") in (
                "create",
                "modify",
                "delete",
                "meta",
            ):
                logger.warning("[BUILD-129:NDJSON] Detected single JSON op; converting to NDJSON")
                converted = json.dumps(obj, ensure_ascii=False)
                return parser.parse(converted)
        except Exception:
            pass
        return None

    def _validate_manifest(self, phase_spec: Dict, operations: List) -> Optional[Dict]:
        """Validate operations against deliverables manifest."""
        manifest_paths_raw = None
        if isinstance(phase_spec, dict):
            scope_cfg = phase_spec.get("scope") or {}
            if isinstance(scope_cfg, dict):
                manifest_paths_raw = scope_cfg.get("deliverables_manifest")
            if manifest_paths_raw is None:
                manifest_paths_raw = phase_spec.get("deliverables_manifest")

        if not isinstance(manifest_paths_raw, list) or not manifest_paths_raw:
            return None

        # Build manifest set and prefixes
        manifest_set = set()
        manifest_prefixes = []
        for p in manifest_paths_raw:
            if isinstance(p, str) and p.strip():
                norm = p.strip().replace("\\", "/")
                while "//" in norm:
                    norm = norm.replace("//", "/")
                manifest_set.add(norm)
                if norm.endswith("/"):
                    manifest_prefixes.append(norm)

        def _in_manifest(path: str) -> bool:
            if path in manifest_set:
                return True
            return any(path.startswith(prefix) for prefix in manifest_prefixes)

        def _canonicalize_to_manifest(path: str) -> str:
            candidates = [path]
            if path.startswith("./"):
                candidates.append(path[2:])
            if path.startswith("code/"):
                candidates.append(path[len("code/") :])
            if path.startswith("code/src/"):
                candidates.append("src/" + path[len("code/src/") :])
            if path.startswith("code/docs/"):
                candidates.append("docs/" + path[len("code/docs/") :])
            if path.startswith("code/tests/"):
                candidates.append("tests/" + path[len("code/tests/") :])

            for c in candidates:
                c2 = c.replace("\\", "/")
                while "//" in c2:
                    c2 = c2.replace("//", "/")
                if _in_manifest(c2):
                    return c2
            return path

        # Check and canonicalize operations
        outside = []
        for op in operations:
            fp = (op.file_path or "").replace("\\", "/")
            while "//" in fp:
                fp = fp.replace("//", "/")
            if not fp:
                continue
            canon = _canonicalize_to_manifest(fp)
            if canon != fp:
                op.file_path = canon
                fp = canon
            if not _in_manifest(fp):
                outside.append(fp)

        if outside:
            outside = sorted(set(outside))
            msg = (
                "NDJSON operations contained file paths outside deliverables_manifest; "
                "skipping apply to prevent workspace drift."
            )
            logger.error(
                f"[BUILD-129:NDJSON] {msg} outside_count={len(outside)} sample={outside[:10]}"
            )
            return {
                "error_code": "ndjson_outside_manifest",
                "messages": [
                    msg,
                    f"outside_count={len(outside)}",
                    f"outside_sample={outside[:10]}",
                ],
            }

        return None

    def _generate_synthetic_diff(self, apply_result: Dict) -> str:
        """Generate synthetic diff markers for deliverables validation."""
        applied_paths = list(apply_result.get("applied") or [])
        patch_lines = [f"# NDJSON Operations Applied ({len(applied_paths)} files)"]
        for p in applied_paths:
            patch_lines.append(f"diff --git a/{p} b/{p}")
            patch_lines.append(f"+++ b/{p}")
        if apply_result.get("failed"):
            patch_lines.append(f"\n# Failed operations ({len(apply_result['failed'])}):")
            for failed in apply_result["failed"]:
                patch_lines.append(f"# - {failed['file_path']}: {failed['error']}")
        return "\n".join(patch_lines) + "\n"

    def _build_messages(self, parse_result) -> List[str]:
        """Build builder messages from parse result."""
        messages = []
        if parse_result.was_truncated and parse_result.total_expected:
            completed = len(parse_result.operations)
            expected = parse_result.total_expected
            messages.append(
                f"Output truncated: completed {completed}/{expected} operations. "
                f"Continuation recovery can complete remaining {expected - completed} operations."
            )
        return messages

    def _write_debug_sample(
        self,
        sanitized: str,
        phase_spec: Dict,
        model: str,
        stop_reason: str,
        effective_truncation: bool,
    ):
        """Write debug sample for failed NDJSON parsing."""
        try:
            phase_id = str(
                phase_spec.get("phase_id")
                or phase_spec.get("id")
                or phase_spec.get("name")
                or "unknown_phase"
            )
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            out_dir = Path(".autonomous_runs") / "autopack" / "ndjson_failures"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{stamp}_{phase_id}_ndjson_no_ops.txt"

            head = sanitized[:8000]
            tail = sanitized[-2000:] if len(sanitized) > 9000 else ""
            payload = (
                f"phase_id={phase_id}\n"
                f"model={model}\n"
                f"stop_reason={stop_reason}\n"
                f"effective_truncation={effective_truncation}\n"
                f"lines={len((sanitized or '').splitlines())}\n"
                f"--- BEGIN HEAD (<=8000 chars) ---\n{head}\n"
                f"--- END HEAD ---\n"
            )
            if tail:
                payload += f"--- BEGIN TAIL (<=2000 chars) ---\n{tail}\n--- END TAIL ---\n"
            out_path.write_text(payload, encoding="utf-8", errors="replace")
            logger.warning(
                f"[BUILD-129:NDJSON] Wrote debug sample for ndjson_no_operations to {out_path}"
            )
        except Exception as e:
            logger.warning(f"[BUILD-129:NDJSON] Failed to write debug sample: {e}")
