"""
Phase Finalizer for BUILD-127 Phase 1.

Single completion authority - prevents bypassing quality/CI/deliverables gates.
Per BUILD-127 Final Plan: peer-reviewed comprehensive completion check.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

# Note: deliverables_validator is a module with standalone functions, not a class
import autopack.deliverables_validator as deliverables_validator_module
from autopack.test_baseline_tracker import (TestBaseline, TestBaselineTracker,
                                            TestDelta)

logger = logging.getLogger(__name__)


@dataclass
class PhaseFinalizationDecision:
    """Final decision on whether phase can complete."""

    can_complete: bool
    status: str  # "COMPLETE", "FAILED", "BLOCKED"
    reason: str
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PhaseFinalizer:
    """
    Authoritative completion check - single source of truth for phase completion.

    Per BUILD-127 design:
    - Replaces ad-hoc completion logic in autonomous_executor.py
    - Comprehensive gate checks (CI, quality, deliverables)
    - Enhanced blocking logic for phase validation_tests
    - Prevents false completions (BUILD-126 bug)

    Gates (in order):
    1. CI baseline regression check
    2. Quality gate decision
    3. Deliverables validation
    """

    def __init__(self, baseline_tracker: TestBaselineTracker):
        """
        Initialize finalizer.

        Args:
            baseline_tracker: Test baseline tracker
        """
        self.baseline_tracker = baseline_tracker

    def assess_completion(
        self,
        phase_id: str,
        phase_spec: Dict,
        ci_result: Optional[Dict],
        baseline: Optional[TestBaseline],
        quality_report: Optional[Dict],
        auditor_result: Optional[Dict],
        deliverables: List[str],
        applied_files: List[str],
        workspace: Path,
        builder_output: Optional[str] = None,
        apply_stats: Optional[Dict] = None,
    ) -> PhaseFinalizationDecision:
        """
        Comprehensive completion check.

        Args:
            phase_id: Phase ID
            phase_spec: Phase specification dict
            ci_result: CI test results (pytest-json-report output path)
            baseline: Test baseline (T0 capture)
            quality_report: Quality gate report
            auditor_result: Auditor verification result
            deliverables: Required deliverables list
            applied_files: Files actually applied in patch
            workspace: Workspace path
            builder_output: Builder's output text (for manifest extraction, BUILD-127 Phase 3)
            apply_stats: Apply statistics dict (from autonomous_executor) with mode, operations, patch size

        Returns:
            PhaseFinalizationDecision with blocking issues and warnings
        """
        blocking_issues = []
        warnings = []

        logger.info(f"[PhaseFinalizer] Assessing completion for phase {phase_id}")

        # Gate -1: No-op detection (prevent false "work completed" when apply did nothing)
        # Only block if required deliverables are missing in workspace
        noop_detected = False
        if apply_stats and deliverables:
            is_noop = self._detect_noop(apply_stats)
            allow_noop = phase_spec.get("allow_noop", False)

            if is_noop:
                noop_detected = True
                if allow_noop:
                    logger.info("[PhaseFinalizer] No-op detected but allowed by phase spec")
                    warnings.append("Phase completed with no changes (allow_noop=true)")
                else:
                    # Check if deliverables exist - if they do, this might be legitimately idempotent
                    missing = self._missing_deliverables_in_workspace(deliverables, workspace)
                    if missing:
                        blocking_issues.append(
                            f"No-op detected: no changes applied but required deliverables missing: {missing}"
                        )
                        logger.error(
                            f"[PhaseFinalizer] BLOCK: No-op with missing deliverables. "
                            f"Apply stats: {apply_stats}"
                        )
                    else:
                        # Deliverables exist, so phase is legitimately idempotent
                        logger.info(
                            "[PhaseFinalizer] No-op detected but all deliverables exist "
                            "(phase is idempotent)"
                        )
                        warnings.append(
                            "Phase completed with no changes (all deliverables already exist)"
                        )

        # Gate 0: Always block on CI collection/import errors (even when baseline missing).
        # pytest-json-report represents these as failed collectors and often produces:
        #   exitcode=2, summary.total=0, tests=[]
        if ci_result:
            collection_block = self._detect_collection_error(ci_result, workspace)
            if collection_block:
                blocking_issues.append(collection_block)
                logger.error(f"[PhaseFinalizer] BLOCK: {collection_block}")

        # Gate 1: CI baseline regression check
        if baseline and ci_result:
            delta = self._compute_ci_delta(baseline, ci_result, workspace)

            # ALWAYS BLOCK on new collection/import errors (after retry)
            if delta.new_collection_errors_persistent:
                blocking_issues.append(
                    f"New collection errors (persistent): {delta.new_collection_errors_persistent}"
                )
                logger.error(
                    f"[PhaseFinalizer] BLOCK: {len(delta.new_collection_errors_persistent)} "
                    "persistent collection errors"
                )

            # ALWAYS BLOCK if newly failing tests intersect phase's validation_tests
            phase_validation_tests = set(phase_spec.get("validation", {}).get("tests", []))
            if phase_validation_tests:
                newly_failing_set = set(delta.newly_failing_persistent)
                overlap = phase_validation_tests & newly_failing_set
                if overlap:
                    blocking_issues.append(
                        f"Phase validation tests failed (persistent): {list(overlap)}"
                    )
                    logger.error(
                        f"[PhaseFinalizer] BLOCK: Phase validation tests failed: {overlap}"
                    )

            # BLOCK on any persistent regression (low/medium/high/critical)
            #
            # Rationale: Autopack may run on a "red" baseline (known pre-existing failures).
            # The intended policy is delta-based: do not accept *new* persistent regressions.
            if delta.regression_severity != "none":
                blocking_issues.append(
                    f"{delta.regression_severity.upper()} regression: "
                    f"{len(delta.newly_failing_persistent)} persistent failures"
                )
                logger.error(
                    f"[PhaseFinalizer] BLOCK: {delta.regression_severity.upper()} regression"
                )

            # Log flaky suspects
            if delta.flaky_suspects:
                warnings.append(f"Flaky tests detected (passed on retry): {delta.flaky_suspects}")
                logger.warning(f"[PhaseFinalizer] Flaky suspects: {delta.flaky_suspects}")

            # Log newly passing tests (good sign)
            if delta.newly_passing:
                logger.info(
                    f"[PhaseFinalizer] {len(delta.newly_passing)} tests now passing "
                    "(were failing in baseline)"
                )

        # Gate 2: Quality gate decision
        if quality_report:
            quality_level = quality_report.get("quality_level", "unknown")
            is_blocked = quality_report.get("is_blocked", False)
            human_approved = bool(quality_report.get("human_approved", False))

            if is_blocked:
                if human_approved:
                    warnings.append(
                        f"Quality gate blocked but overridden by human approval: {quality_level}"
                    )
                    logger.warning(
                        f"[PhaseFinalizer] WARN: Quality gate blocked ({quality_level}) but human-approved override present"
                    )
                else:
                    blocking_issues.append(f"Quality gate blocked: {quality_level}")
                    logger.error(f"[PhaseFinalizer] BLOCK: Quality gate blocked ({quality_level})")

        # Gate 3: Deliverables existence validation (workspace-based)
        #
        # Important: do not rely on applied_files. A valid phase can be idempotent (no changes needed),
        # and some apply modes (structured edits, full-file conversions) may not yield a clean applied_files list.
        #
        # Skip deliverables check if allow_noop=True and no-op was detected (already checked in Gate -1)
        allow_noop = phase_spec.get("allow_noop", False)
        if deliverables and not (noop_detected and allow_noop):
            missing = self._missing_deliverables_in_workspace(deliverables, workspace)
            if missing:
                blocking_issues.append(f"Missing required deliverables: {missing}")
                logger.error(f"[PhaseFinalizer] BLOCK: Missing deliverables: {missing}")

        # Gate 3.5: Structured manifest validation (BUILD-127 Phase 3)
        if builder_output and deliverables:
            manifest = deliverables_validator_module.extract_manifest_from_output(builder_output)
            if manifest:
                logger.info("[PhaseFinalizer] Validating structured deliverables manifest")
                passed, issues = deliverables_validator_module.validate_structured_manifest(
                    manifest=manifest, workspace=workspace, expected_deliverables=deliverables
                )

                if not passed:
                    blocking_issues.append(f"Manifest validation failed: {'; '.join(issues)}")
                    logger.error(
                        f"[PhaseFinalizer] BLOCK: Manifest validation failed with {len(issues)} issues"
                    )
                    for issue in issues:
                        logger.error(f"[PhaseFinalizer]   - {issue}")
                else:
                    logger.info("[PhaseFinalizer] ✅ Structured manifest validated successfully")
            else:
                # Manifest not found - log as warning but don't block (optional feature)
                logger.info(
                    "[PhaseFinalizer] No structured manifest found in builder output (optional)"
                )

        # Decision
        if blocking_issues:
            decision = PhaseFinalizationDecision(
                can_complete=False,
                status="FAILED",
                reason="; ".join(blocking_issues),
                blocking_issues=blocking_issues,
                warnings=warnings,
            )
            logger.error(f"[PhaseFinalizer] ❌ Phase {phase_id} BLOCKED: {decision.reason}")
            return decision

        decision = PhaseFinalizationDecision(
            can_complete=True,
            status="COMPLETE",
            reason="All gates passed",
            blocking_issues=[],
            warnings=warnings,
        )

        logger.info(f"[PhaseFinalizer] ✅ Phase {phase_id} can complete")
        if warnings:
            for warning in warnings:
                logger.warning(f"[PhaseFinalizer]   ⚠️  {warning}")

        return decision

    def _missing_deliverables_in_workspace(
        self, deliverables: List[str], workspace: Path
    ) -> List[str]:
        """
        Workspace-based deliverables validation.

        Supports both:
        - exact file deliverables (e.g., "src/foo.py")
        - directory/prefix deliverables (e.g., "tests/research/unit/") satisfied by any file under that dir
        """
        missing: List[str] = []
        for d in deliverables:
            if not isinstance(d, str) or not d.strip():
                continue
            rel = d.replace("\\", "/").strip()

            # Prefix deliverables (directory)
            if rel.endswith("/"):
                try:
                    root = workspace / rel.rstrip("/")
                    if not root.exists() or not root.is_dir():
                        missing.append(rel)
                        continue
                    found_any = False
                    for dirpath, _dirnames, filenames in os.walk(root):
                        if filenames:
                            found_any = True
                            break
                    if not found_any:
                        missing.append(rel)
                except Exception:
                    missing.append(rel)
                continue

            # Exact file deliverable
            try:
                p = workspace / rel
                if not p.exists():
                    missing.append(rel)
            except Exception:
                missing.append(rel)

        return sorted(set(missing))

    def _extract_collection_error_digest(
        self, ci_result: Dict, workspace: Path, max_errors: int = 5
    ) -> Optional[List[str]]:
        """
        Extract a digest of collection/import errors from the pytest report.

        Returns a list of formatted error strings (up to max_errors) with nodeid + first line of longrepr.
        Returns None if no collection errors found.

        This digest can be written to phase summaries and persisted in ci_result.
        """
        try:
            report_path = ci_result.get("report_path")
            if not report_path:
                return None
            p = Path(report_path)
            if not p.exists() or p.suffix.lower() != ".json":
                return None

            report = json.loads(p.read_text(encoding="utf-8"))
            collectors = report.get("collectors", []) or []
            failed_collectors = [c for c in collectors if c.get("outcome") not in (None, "passed")]

            if not failed_collectors:
                return None

            digest = []
            for collector in failed_collectors[:max_errors]:
                nodeid = collector.get("nodeid", "<unknown>")
                longrepr = (collector.get("longrepr") or "").splitlines()
                detail = longrepr[0] if longrepr else "collector failed"
                digest.append(f"{nodeid}: {detail}")

            return digest if digest else None

        except Exception as e:
            logger.warning(f"[PhaseFinalizer] Failed to extract collection error digest: {e}")
            return None

    def _detect_collection_error(self, ci_result: Dict, workspace: Path) -> Optional[str]:
        """
        Detect CI collection/import errors from the structured pytest report.

        This is intentionally baseline-independent: collection errors are catastrophic and should
        block completion even when T0 baseline capture is unavailable.
        """
        try:
            report_path = ci_result.get("report_path")
            if not report_path:
                return None
            p = Path(report_path)
            if not p.exists():
                # If we don't have a structured report, fall back to the executor's signal.
                if bool(ci_result.get("suspicious_zero_tests")) and not bool(
                    ci_result.get("passed", False)
                ):
                    return "CI collection/import error suspected (0 tests detected)"
                return None

            # Only parse JSON reports; log files are handled by 'suspicious_zero_tests' above.
            if p.suffix.lower() != ".json":
                if bool(ci_result.get("suspicious_zero_tests")) and not bool(
                    ci_result.get("passed", False)
                ):
                    return "CI collection/import error suspected (0 tests detected)"
                return None

            report = json.loads(p.read_text(encoding="utf-8"))
            exitcode = report.get("exitcode")
            summary = report.get("summary", {}) or {}
            total = summary.get("total", 0)
            collectors = report.get("collectors", []) or []
            failed_collectors = [c for c in collectors if c.get("outcome") not in (None, "passed")]

            # Collection errors often have exitcode=2 and zero executed tests.
            if failed_collectors:
                first = failed_collectors[0]
                nodeid = first.get("nodeid", "<unknown>")
                longrepr = (first.get("longrepr") or "").splitlines()
                detail = longrepr[0] if longrepr else "collector failed"
                return f"CI collection/import error: {nodeid} ({detail})"

            if (
                exitcode
                and exitcode != 0
                and int(total) == 0
                and bool(ci_result.get("suspicious_zero_tests"))
            ):
                return f"CI failed before running tests (exitcode={exitcode}, total_tests=0)"

        except Exception as e:
            logger.warning(
                f"[PhaseFinalizer] Failed to detect collection errors from CI report: {e}"
            )
            return None

        return None

    def _compute_ci_delta(
        self, baseline: TestBaseline, ci_result: Dict, workspace: Path
    ) -> TestDelta:
        """
        Compute CI delta from baseline.

        Args:
            baseline: Test baseline
            ci_result: Dict with 'report_path' key pointing to pytest-json-report output
            workspace: Workspace path

        Returns:
            TestDelta with persistent failures and flaky suspects
        """
        report_path = ci_result.get("report_path")
        if not report_path:
            logger.warning("[PhaseFinalizer] CI result missing report_path")
            return TestDelta()

        report_path = Path(report_path)
        if not report_path.exists():
            logger.warning(f"[PhaseFinalizer] CI report not found: {report_path}")
            return TestDelta()

        # Compute full delta with retry. This must never hard-fail phase execution:
        # some CI adapters may only provide a text log, or JSON may be truncated/empty.
        try:
            delta = self.baseline_tracker.compute_full_delta(
                baseline=baseline, current_report_path=report_path, workspace=workspace
            )
        except Exception as e:
            logger.error(f"[PhaseFinalizer] Failed to compute CI delta from {report_path}: {e}")
            return TestDelta()

        logger.info(
            f"[PhaseFinalizer] CI Delta: "
            f"{len(delta.newly_failing_persistent)} persistent failures, "
            f"{len(delta.flaky_suspects)} flaky suspects, "
            f"{len(delta.newly_passing)} newly passing, "
            f"severity={delta.regression_severity}"
        )

        return delta

    def should_block_on_ci(self, delta: TestDelta, phase_validation_tests: Set[str]) -> bool:
        """
        Determine if CI results should block completion.

        Per BUILD-127: Block on:
        - Persistent collection errors
        - Phase validation_tests failures (even if medium severity)
        - High/critical overall regression

        Args:
            delta: Test delta
            phase_validation_tests: Set of test IDs from phase validation.tests

        Returns:
            True if should block
        """
        # Block on persistent collection errors
        if delta.new_collection_errors_persistent:
            return True

        # Block if phase validation tests failed
        if phase_validation_tests:
            newly_failing_set = set(delta.newly_failing_persistent)
            overlap = phase_validation_tests & newly_failing_set
            if overlap:
                return True

        # Block on any regression severity (low/medium/high/critical).
        if delta.regression_severity != "none":
            return True

        return False

    def _detect_noop(self, apply_stats: Dict) -> bool:
        """
        Detect if the apply operation was a no-op (no actual changes made).

        Args:
            apply_stats: Apply statistics dict from autonomous_executor

        Returns:
            True if no-op detected
        """
        mode = apply_stats.get("mode")

        if mode == "structured_edit":
            # For structured edits, check if any operations were actually applied
            operations_applied = apply_stats.get("operations_applied", 0)
            return operations_applied == 0

        elif mode == "patch":
            # For patch mode, check if patch was empty or whitespace-only
            patch_nonempty = apply_stats.get("patch_nonempty", False)
            return not patch_nonempty

        # Unknown mode or missing stats - be conservative, don't flag as no-op
        return False
