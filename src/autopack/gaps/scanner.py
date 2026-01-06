"""Deterministic gap scanner for autonomy loop.

Scans workspace for known gap types without LLM calls.
Uses existing contract tests, file system checks, and git state.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import (
    Gap,
    GapEvidence,
    GapMetadata,
    GapReportV1,
    GapSummary,
    SafeRemediation,
)

logger = logging.getLogger(__name__)

SCANNER_VERSION = "1.0.0"


class GapScanner:
    """Deterministic gap scanner.

    Scans workspace for 10 known gap types:
    1. doc_drift: SOT docs out of sync with reality
    2. root_clutter: Files that should be in docs/ or archive/
    3. sot_duplicate: Same content in multiple SOT locations
    4. test_infra_drift: Flaky or broken tests
    5. memory_budget_cap_issue: Token budget exceeded
    6. windows_encoding_issue: UTF-8 encoding problems
    7. baseline_policy_drift: Baseline policy violations
    8. protected_path_violation: Writes to protected paths
    9. db_lock_contention: Database lock issues
    10. git_state_corruption: Git state inconsistencies
    """

    def __init__(self, workspace_root: Path):
        """Initialize gap scanner.

        Args:
            workspace_root: Root directory of workspace
        """
        self.workspace_root = workspace_root
        self.gaps: List[Gap] = []

    def scan(self) -> List[Gap]:
        """Run all gap detectors.

        Returns:
            List of detected gaps
        """
        start_time = datetime.now(timezone.utc)

        # Run all detectors
        self.gaps = []
        self.gaps.extend(self._detect_doc_drift())
        self.gaps.extend(self._detect_root_clutter())
        self.gaps.extend(self._detect_sot_duplicates())
        self.gaps.extend(self._detect_test_infra_drift())
        self.gaps.extend(self._detect_memory_budget_issues())
        self.gaps.extend(self._detect_windows_encoding_issues())
        self.gaps.extend(self._detect_baseline_policy_drift())
        self.gaps.extend(self._detect_protected_path_violations())
        self.gaps.extend(self._detect_db_lock_contention())
        self.gaps.extend(self._detect_git_state_corruption())

        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        logger.info(f"Gap scan completed in {elapsed_ms}ms: {len(self.gaps)} gaps found")

        return self.gaps

    def _detect_doc_drift(self) -> List[Gap]:
        """Detect documentation drift via contract tests.

        Uses existing doc contract tests when available (per implementation plan).
        """
        gaps = []

        # Check if README has outdated SOT summary markers
        readme_path = self.workspace_root / "README.md"
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8", errors="ignore")

            # Check for SOT summary markers (from tidy system)
            if "<!-- SOT_SUMMARY_START -->" in content:
                # This is a simplified check; real implementation would run tidy dry-run
                # and check for drift
                pass  # No drift detected in this simple check

        # Check for doc contract test failures (would run pytest in real implementation)
        # For now, return empty list (no drift detected)
        return gaps

    def _detect_root_clutter(self) -> List[Gap]:
        """Detect files in root that should be in docs/ or archive/."""
        gaps = []

        # Known patterns that should not be in root
        clutter_patterns = [
            "*.md",  # Most markdown files should be in docs/
            "BUILD_*.md",
            "COMPLETION_*.md",
            "IMPLEMENTATION_*.md",
            "PROMPT_*.md",
        ]

        clutter_files = []
        for pattern in clutter_patterns:
            for file in self.workspace_root.glob(pattern):
                # Exclude allowed root files
                if file.name not in [
                    "README.md",
                    "CONTRIBUTING.md",
                    "LICENSE.md",
                    "CHANGELOG.md",
                ]:
                    clutter_files.append(str(file.relative_to(self.workspace_root)))

        if clutter_files:
            gap_id = self._generate_gap_id("root_clutter", clutter_files)
            gaps.append(
                Gap(
                    gap_id=gap_id,
                    gap_type="root_clutter",
                    title=f"Root clutter: {len(clutter_files)} files should be in docs/",
                    description=f"Found {len(clutter_files)} markdown files in root that should be in docs/ or archive/",
                    detection_signals=[
                        f"Found {len(clutter_files)} markdown files in root",
                        "Files should follow workspace organization spec",
                    ],
                    evidence=GapEvidence(file_paths=clutter_files[:10]),  # Limit to 10
                    risk_classification="medium",
                    blocks_autopilot=False,
                    safe_remediation=SafeRemediation(
                        approach="Run tidy system to organize workspace",
                        requires_approval=True,
                        estimated_actions=len(clutter_files),
                    ),
                )
            )

        return gaps

    def _detect_sot_duplicates(self) -> List[Gap]:
        """Detect duplicate content in multiple SOT locations."""
        gaps = []

        # Check for known duplicate patterns
        # This would use content hashing in real implementation
        # For now, check for obvious file name duplicates

        docs_dir = self.workspace_root / "docs"
        if not docs_dir.exists():
            return gaps

        # Look for files with same name in docs/ and root
        for root_file in self.workspace_root.glob("*.md"):
            if root_file.name in ["README.md", "CONTRIBUTING.md", "LICENSE.md"]:
                continue

            docs_file = docs_dir / root_file.name
            if docs_file.exists():
                gap_id = self._generate_gap_id("sot_duplicate", [root_file.name, docs_file.name])
                gaps.append(
                    Gap(
                        gap_id=gap_id,
                        gap_type="sot_duplicate",
                        title=f"Duplicate file: {root_file.name}",
                        description=f"File exists in both root and docs/: {root_file.name}",
                        detection_signals=[
                            f"Found {root_file.name} in root",
                            f"Found {root_file.name} in docs/",
                        ],
                        evidence=GapEvidence(
                            file_paths=[
                                str(root_file.relative_to(self.workspace_root)),
                                str(docs_file.relative_to(self.workspace_root)),
                            ]
                        ),
                        risk_classification="medium",
                        blocks_autopilot=False,
                        safe_remediation=SafeRemediation(
                            approach="Remove duplicate and keep canonical version in docs/",
                            requires_approval=True,
                            estimated_actions=1,
                        ),
                    )
                )

        return gaps

    def _detect_test_infra_drift(self) -> List[Gap]:
        """Detect flaky or broken tests.

        In real implementation, would run pytest and check for failures.
        For deterministic-first approach, checks for known patterns.
        """
        gaps = []

        # Check for pytest cache indicating previous failures
        pytest_cache = self.workspace_root / ".pytest_cache"
        if pytest_cache.exists():
            lastfailed_path = pytest_cache / "v" / "cache" / "lastfailed"
            if lastfailed_path.exists():
                try:
                    import json

                    lastfailed = json.loads(lastfailed_path.read_text(encoding="utf-8"))
                    if lastfailed:
                        failed_tests = list(lastfailed.keys())
                        gap_id = self._generate_gap_id("test_infra_drift", failed_tests)
                        gaps.append(
                            Gap(
                                gap_id=gap_id,
                                gap_type="test_infra_drift",
                                title=f"Previously failed tests: {len(failed_tests)}",
                                description=f"Found {len(failed_tests)} previously failed tests in pytest cache",
                                detection_signals=[
                                    f"pytest lastfailed cache has {len(failed_tests)} entries",
                                ],
                                evidence=GapEvidence(test_names=failed_tests[:10]),
                                risk_classification="high",
                                blocks_autopilot=True,
                                safe_remediation=SafeRemediation(
                                    approach="Re-run tests to verify current status, fix failures",
                                    requires_approval=True,
                                    estimated_actions=len(failed_tests),
                                ),
                            )
                        )
                except Exception as e:
                    logger.debug(f"Failed to read pytest lastfailed cache: {e}")

        return gaps

    def _detect_memory_budget_issues(self) -> List[Gap]:
        """Detect token budget exceeded issues.

        Checks for large context files or excessive token usage.
        """
        gaps = []

        # Check for very large files that would exceed token budgets
        large_files = []
        for file in self.workspace_root.rglob("*.md"):
            try:
                size = file.stat().st_size
                # Flag files > 100KB (rough proxy for token budget issues)
                if size > 100_000:
                    large_files.append((str(file.relative_to(self.workspace_root)), size))
            except Exception:
                pass

        if large_files:
            gap_id = self._generate_gap_id("memory_budget_cap_issue", [f[0] for f in large_files])
            gaps.append(
                Gap(
                    gap_id=gap_id,
                    gap_type="memory_budget_cap_issue",
                    title=f"Large files detected: {len(large_files)}",
                    description=f"Found {len(large_files)} files > 100KB that may exceed token budgets",
                    detection_signals=[
                        f"{len(large_files)} files exceed 100KB",
                        "May cause token budget cap issues",
                    ],
                    evidence=GapEvidence(file_paths=[f[0] for f in large_files[:10]]),
                    risk_classification="medium",
                    blocks_autopilot=False,
                    safe_remediation=SafeRemediation(
                        approach="Split large files or consolidate content",
                        requires_approval=True,
                        estimated_actions=len(large_files),
                    ),
                )
            )

        return gaps

    def _detect_windows_encoding_issues(self) -> List[Gap]:
        """Detect Windows encoding issues.

        Checks for files with encoding problems.
        """
        gaps = []

        # Try to read all Python and markdown files and detect encoding issues
        encoding_errors = []
        for pattern in ["**/*.py", "**/*.md"]:
            for file in self.workspace_root.glob(pattern):
                try:
                    # Try to read with UTF-8 strict mode
                    file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    encoding_errors.append(str(file.relative_to(self.workspace_root)))
                except Exception:
                    pass

        if encoding_errors:
            gap_id = self._generate_gap_id("windows_encoding_issue", encoding_errors)
            gaps.append(
                Gap(
                    gap_id=gap_id,
                    gap_type="windows_encoding_issue",
                    title=f"Encoding issues: {len(encoding_errors)} files",
                    description=f"Found {len(encoding_errors)} files with UTF-8 encoding errors",
                    detection_signals=[
                        f"{len(encoding_errors)} files failed UTF-8 decoding",
                        "Windows encoding issues detected",
                    ],
                    evidence=GapEvidence(file_paths=encoding_errors[:10]),
                    risk_classification="high",
                    blocks_autopilot=True,
                    safe_remediation=SafeRemediation(
                        approach="Fix encoding to UTF-8 or use errors='ignore'",
                        requires_approval=True,
                        estimated_actions=len(encoding_errors),
                    ),
                )
            )

        return gaps

    def _detect_baseline_policy_drift(self) -> List[Gap]:
        """Detect baseline policy violations.

        Checks for deviations from baseline policy configuration.
        """
        gaps = []

        # Check for baseline policy config file
        baseline_config = self.workspace_root / "config" / "baseline_policy.yaml"
        if not baseline_config.exists():
            gap_id = self._generate_gap_id("baseline_policy_drift", ["missing_config"])
            gaps.append(
                Gap(
                    gap_id=gap_id,
                    gap_type="baseline_policy_drift",
                    title="Missing baseline policy configuration",
                    description="Baseline policy configuration file not found",
                    detection_signals=["config/baseline_policy.yaml does not exist"],
                    evidence=GapEvidence(file_paths=["config/baseline_policy.yaml"]),
                    risk_classification="medium",
                    blocks_autopilot=False,
                    safe_remediation=SafeRemediation(
                        approach="Create baseline policy configuration",
                        requires_approval=True,
                        estimated_actions=1,
                    ),
                )
            )

        return gaps

    def _detect_protected_path_violations(self) -> List[Gap]:
        """Detect writes to protected paths.

        Checks git status for modifications to protected paths.
        """
        gaps = []

        # Get modified files from git
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                protected_patterns = [
                    "docs/",
                    "config/",
                    ".github/",
                ]
                violations = []
                for line in result.stdout.splitlines():
                    if len(line) < 4:
                        continue
                    status = line[:2]
                    filepath = line[3:].strip()
                    # Check if modified and in protected path
                    if status.strip() and any(filepath.startswith(p) for p in protected_patterns):
                        violations.append(filepath)

                if violations:
                    gap_id = self._generate_gap_id("protected_path_violation", violations)
                    gaps.append(
                        Gap(
                            gap_id=gap_id,
                            gap_type="protected_path_violation",
                            title=f"Protected path modifications: {len(violations)}",
                            description=f"Found {len(violations)} modifications to protected paths",
                            detection_signals=[
                                f"{len(violations)} modified files in protected paths",
                                "Protected paths require explicit approval",
                            ],
                            evidence=GapEvidence(file_paths=violations[:10]),
                            risk_classification="high",
                            blocks_autopilot=True,
                            safe_remediation=SafeRemediation(
                                approach="Review and approve protected path changes",
                                requires_approval=True,
                                estimated_actions=len(violations),
                            ),
                        )
                    )
        except Exception as e:
            logger.debug(f"Failed to check git status: {e}")

        return gaps

    def _detect_db_lock_contention(self) -> List[Gap]:
        """Detect database lock contention issues.

        Checks for database lock files or errors.
        """
        gaps = []

        # Check for database lock files
        db_paths = [
            self.workspace_root / ".autopack" / "autopack.db",
            self.workspace_root / "autopack.db",
        ]

        for db_path in db_paths:
            lock_file = db_path.with_suffix(".db-lock")
            if lock_file.exists():
                gap_id = self._generate_gap_id("db_lock_contention", [str(lock_file)])
                gaps.append(
                    Gap(
                        gap_id=gap_id,
                        gap_type="db_lock_contention",
                        title="Database lock file detected",
                        description=f"Database lock file exists: {lock_file.name}",
                        detection_signals=[f"Found {lock_file.name}"],
                        evidence=GapEvidence(
                            file_paths=[str(lock_file.relative_to(self.workspace_root))]
                        ),
                        risk_classification="high",
                        blocks_autopilot=True,
                        safe_remediation=SafeRemediation(
                            approach="Clear stale lock file or wait for lock release",
                            requires_approval=True,
                            estimated_actions=1,
                        ),
                    )
                )

        return gaps

    def _detect_git_state_corruption(self) -> List[Gap]:
        """Detect git state inconsistencies.

        Checks for git corruption or inconsistent state.
        """
        gaps = []

        # Check git fsck
        try:
            result = subprocess.run(
                ["git", "fsck", "--no-progress"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0 or result.stderr.strip():
                gap_id = self._generate_gap_id("git_state_corruption", ["git_fsck_failed"])
                gaps.append(
                    Gap(
                        gap_id=gap_id,
                        gap_type="git_state_corruption",
                        title="Git state corruption detected",
                        description="git fsck reported errors",
                        detection_signals=[
                            "git fsck failed or reported warnings",
                            result.stderr[:200] if result.stderr else "Exit code non-zero",
                        ],
                        evidence=GapEvidence(file_paths=[".git/"]),
                        risk_classification="critical",
                        blocks_autopilot=True,
                        safe_remediation=SafeRemediation(
                            approach="Run git repair or restore from backup",
                            requires_approval=True,
                            estimated_actions=1,
                        ),
                    )
                )
        except Exception as e:
            logger.debug(f"Failed to check git fsck: {e}")

        return gaps

    def _generate_gap_id(self, gap_type: str, inputs: List[str]) -> str:
        """Generate stable gap ID from gap type and inputs.

        Args:
            gap_type: Type of gap
            inputs: List of inputs (file paths, test names, etc.)

        Returns:
            Stable gap ID (16 hex chars)
        """
        # Sort inputs for stability
        sorted_inputs = sorted(inputs)
        combined = f"{gap_type}:{'|'.join(sorted_inputs)}"
        digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return f"{gap_type}-{digest[:12]}"


def scan_workspace(
    workspace_root: Path,
    project_id: str,
    run_id: str,
) -> GapReportV1:
    """Scan workspace for gaps and return gap report.

    Args:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier

    Returns:
        GapReportV1 gap report
    """
    scanner = GapScanner(workspace_root)
    start_time = datetime.now(timezone.utc)

    gaps = scanner.scan()

    # Sort gaps by risk (critical > high > medium > low > info)
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    gaps.sort(key=lambda g: risk_order.get(g.risk_classification, 5))

    # Compute workspace state digest
    workspace_digest = _compute_workspace_digest(workspace_root)

    # Compute summary
    summary = GapSummary(
        total_gaps=len(gaps),
        critical_gaps=sum(1 for g in gaps if g.risk_classification == "critical"),
        high_gaps=sum(1 for g in gaps if g.risk_classification == "high"),
        medium_gaps=sum(1 for g in gaps if g.risk_classification == "medium"),
        low_gaps=sum(1 for g in gaps if g.risk_classification == "low"),
        autopilot_blockers=sum(1 for g in gaps if g.blocks_autopilot),
    )

    # Compute metadata
    elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    metadata = GapMetadata(
        scanner_version=SCANNER_VERSION,
        scan_duration_ms=elapsed_ms,
    )

    report = GapReportV1(
        project_id=project_id,
        run_id=run_id,
        generated_at=datetime.now(timezone.utc),
        workspace_state_digest=workspace_digest,
        gaps=gaps,
        summary=summary,
        metadata=metadata,
    )

    return report


def _compute_workspace_digest(workspace_root: Path) -> str:
    """Compute digest of workspace state (git HEAD + status).

    Args:
        workspace_root: Root directory of workspace

    Returns:
        16-char hex digest
    """
    try:
        # Get git HEAD
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_head = result.stdout.strip() if result.returncode == 0 else "unknown"

        # Get git status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_status = result.stdout.strip() if result.returncode == 0 else ""

        # Combine and hash
        combined = f"{git_head}|{git_status}"
        digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return digest[:16]
    except Exception as e:
        logger.debug(f"Failed to compute workspace digest: {e}")
        # Fallback to timestamp-based digest
        timestamp = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(timestamp.encode("utf-8")).hexdigest()
        return digest[:16]
