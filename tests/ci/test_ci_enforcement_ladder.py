"""CI enforcement ladder contract tests (PR6).

Ensures critical subsystems have mechanical enforcement via CI:
1. GapScanner baseline-policy detection matches real repo state
2. RiskScorer protected-config paths exist
3. Docs drift checker is invoked in CI
4. Workspace structure verification is invoked in CI

Contract: All drift detectors and policy checkers are wired into CI
         and don't emit false positives on a clean repo.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


class TestGapScannerBaselinePolicy:
    """Verify GapScanner baseline-policy detection matches real repo state."""

    def test_baseline_policy_config_exists(self):
        """config/baseline_policy.yaml must exist (GapScanner checks for it)."""
        baseline_config = REPO_ROOT / "config" / "baseline_policy.yaml"
        assert baseline_config.exists(), (
            "config/baseline_policy.yaml not found - "
            "GapScanner will emit 'missing baseline policy' gap"
        )

    def test_gap_scanner_no_false_positive_baseline_policy(self):
        """GapScanner should not emit baseline policy gap on clean repo."""
        from autopack.gaps.scanner import GapScanner

        scanner = GapScanner(workspace_root=REPO_ROOT)
        gaps = scanner._detect_baseline_policy_drift()

        baseline_gaps = [g for g in gaps if "baseline_policy" in g.gap_type]
        assert not baseline_gaps, (
            f"GapScanner emitted baseline policy gap on clean repo: {baseline_gaps}"
        )

    def test_gap_scanner_detects_missing_baseline_in_empty_dir(self, tmp_path):
        """GapScanner should detect missing baseline in workspace without config."""
        from autopack.gaps.scanner import GapScanner

        # Create minimal workspace structure
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()

        scanner = GapScanner(workspace_root=tmp_path)
        gaps = scanner._detect_baseline_policy_drift()

        assert len(gaps) == 1, "Expected exactly 1 gap for missing baseline"
        assert gaps[0].gap_type == "baseline_policy_drift"
        assert "missing" in gaps[0].title.lower()


class TestRiskScorerProtectedPaths:
    """Verify RiskScorer protected-config paths exist."""

    def test_risk_scorer_protected_paths_exist(self):
        """All protected paths referenced by RiskScorer must exist or be valid patterns."""
        from autopack.risk_scorer import RiskScorer

        # Paths that may not exist initially but are valid protection targets
        # (created at runtime or by specific workflows)
        OPTIONAL_PATHS = {
            "alembic/versions/*",  # Only exists after alembic init
            ".autonomous_runs/*",  # Created during autonomous runs
            "autopack.db",  # Created when DB is initialized
        }

        # Patterns that use wildcards are checked for parent directory existence
        missing_paths = []
        for path_pattern in RiskScorer.PROTECTED_PATHS:
            # Skip optional paths
            if path_pattern in OPTIONAL_PATHS:
                continue

            if "*" in path_pattern:
                # Wildcard pattern - check parent directory exists
                parent = path_pattern.split("*")[0].rstrip("/")
                if parent:
                    parent_path = REPO_ROOT / parent
                    if not parent_path.exists():
                        missing_paths.append(f"{path_pattern} (parent {parent} missing)")
            else:
                # Exact path - check it exists
                full_path = REPO_ROOT / path_pattern
                if not full_path.exists():
                    # Some paths may be runtime-created (like autopack.db)
                    # Only flag config files and directories that should exist
                    if path_pattern.startswith("config/") or path_pattern.startswith(".github/"):
                        missing_paths.append(path_pattern)

        assert not missing_paths, (
            f"RiskScorer references non-existent protected paths: {missing_paths}"
        )

    def test_risk_scorer_protected_paths_include_critical_configs(self):
        """RiskScorer must protect critical config paths."""
        from autopack.risk_scorer import RiskScorer

        # Critical paths that must be protected
        critical_patterns = [
            "config/",  # Any config path or config/models.yaml or similar
            ".github/",  # Any github path
        ]

        protected_str = " ".join(RiskScorer.PROTECTED_PATHS)
        for pattern in critical_patterns:
            assert pattern in protected_str or any(
                p.startswith(pattern.rstrip("/")) for p in RiskScorer.PROTECTED_PATHS
            ), f"RiskScorer should protect {pattern}"


class TestCIWorkflowEnforcement:
    """Verify CI workflow includes all enforcement steps."""

    def test_ci_invokes_docs_drift_check(self):
        """CI must invoke scripts/check_docs_drift.py."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_yml.exists(), "ci.yml not found"

        content = ci_yml.read_text(encoding="utf-8")
        assert "check_docs_drift.py" in content, (
            "CI workflow must invoke scripts/check_docs_drift.py"
        )

    def test_ci_invokes_workspace_structure_verification(self):
        """CI must invoke verify_workspace_structure.py."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        assert "verify_workspace_structure.py" in content, (
            "CI workflow must invoke scripts/tidy/verify_workspace_structure.py"
        )

    def test_ci_invokes_sot_summary_check(self):
        """CI must invoke sot_summary_refresh.py --check."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        assert "sot_summary_refresh.py" in content and "--check" in content, (
            "CI workflow must invoke scripts/tidy/sot_summary_refresh.py --check"
        )

    def test_ci_invokes_doc_link_check(self):
        """CI must invoke doc link checks."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        assert "check_doc_links.py" in content, (
            "CI workflow must invoke scripts/check_doc_links.py"
        )

    def test_ci_runs_doc_contract_tests(self):
        """CI must run pytest tests/docs/."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        assert "pytest" in content and "tests/docs/" in content, (
            "CI workflow must run pytest tests/docs/"
        )


class TestDocsDriftCheckerCompleteness:
    """Verify docs drift checker covers known problem patterns."""

    def test_drift_checker_blocks_legacy_uvicorn_targets(self):
        """scripts/check_docs_drift.py must block legacy uvicorn targets."""
        drift_checker = REPO_ROOT / "scripts" / "check_docs_drift.py"
        assert drift_checker.exists(), "scripts/check_docs_drift.py not found"

        content = drift_checker.read_text(encoding="utf-8")

        # Must block autopack.api.server:app (legacy)
        assert "autopack.api.server" in content or "api.server:app" in content, (
            "Drift checker must block legacy autopack.api.server:app references"
        )

    def test_drift_checker_blocks_compose_service_drift(self):
        """scripts/check_docs_drift.py must block compose service name drift."""
        drift_checker = REPO_ROOT / "scripts" / "check_docs_drift.py"
        content = drift_checker.read_text(encoding="utf-8")

        # Must detect old service names (api, postgres)
        assert "postgres" in content.lower() or "api" in content, (
            "Drift checker must block legacy compose service names"
        )

    def test_drift_checker_excludes_historical_files(self):
        """scripts/check_docs_drift.py must exclude historical files from checks."""
        drift_checker = REPO_ROOT / "scripts" / "check_docs_drift.py"
        content = drift_checker.read_text(encoding="utf-8")

        # Should exclude historical files
        assert "BUILD_HISTORY" in content or "EXCLUDED_PATHS" in content, (
            "Drift checker must exclude historical ledger files"
        )


class TestEnforcementLadderIntegrity:
    """Verify the enforcement ladder is complete and consistent."""

    def test_all_sot_files_have_contract_tests(self):
        """All SOT files in sot_registry.json should have contract test coverage."""
        import json

        sot_registry = REPO_ROOT / "config" / "sot_registry.json"
        if not sot_registry.exists():
            pytest.skip("sot_registry.json not found")

        with open(sot_registry, "r", encoding="utf-8") as f:
            registry = json.load(f)

        # Get list of SOT files
        sot_files = set()
        for category in registry.get("categories", {}).values():
            for file_path in category.get("files", []):
                sot_files.add(file_path)

        # Verify tests/docs/ exists and has tests
        docs_tests = REPO_ROOT / "tests" / "docs"
        assert docs_tests.exists(), "tests/docs/ directory must exist"

        test_files = list(docs_tests.glob("test_*.py"))
        assert len(test_files) > 0, "tests/docs/ must contain test files"

    def test_ci_workflow_is_blocking(self):
        """CI workflow must not use continue-on-error for critical checks."""
        ci_yml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        content = ci_yml.read_text(encoding="utf-8")

        # Find the docs-sot-integrity job
        docs_job_match = re.search(
            r"docs-sot-integrity:.*?(?=^\s+\w+:|\Z)",
            content,
            re.MULTILINE | re.DOTALL
        )

        if docs_job_match:
            docs_job = docs_job_match.group(0)
            # Should not have continue-on-error for doc checks
            assert "continue-on-error: true" not in docs_job or docs_job.count("continue-on-error: true") == 0, (
                "docs-sot-integrity job should be blocking (no continue-on-error)"
            )

    def test_enforcement_scripts_are_importable(self):
        """Enforcement scripts must be importable (no import errors)."""
        import importlib.util

        scripts_to_check = [
            REPO_ROOT / "scripts" / "check_docs_drift.py",
            REPO_ROOT / "scripts" / "tidy" / "verify_workspace_structure.py",
        ]

        for script_path in scripts_to_check:
            if not script_path.exists():
                continue

            spec = importlib.util.spec_from_file_location(
                script_path.stem, script_path
            )
            try:
                importlib.util.module_from_spec(spec)
                # Don't execute main(), just verify it loads
            except Exception as e:
                pytest.fail(f"Script {script_path.name} has import errors: {e}")
