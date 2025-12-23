#!/usr/bin/env python3
"""
Execute Phase 0: Foundation & Governance

This script orchestrates the autonomous implementation of Phase 0 with
full validation checklist enforcement.

Usage:
    python scripts/execute_phase0_foundation.py [--dry-run] [--skip-approval]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.autonomous_executor import AutonomousExecutor
from autopack.memory.embeddings import embed_text, get_embedding_backend
import numpy as np


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def check_prerequisites() -> Tuple[bool, List[str]]:
    """
    Pre-Implementation Checklist (from AUTONOMOUS_IMPLEMENTATION_CHECKLIST.md)
    """
    issues = []

    print("\n" + "="*80)
    print("PHASE 0 PRE-IMPLEMENTATION CHECKLIST")
    print("="*80)

    # 1. Environment Setup
    print("\n[1/6] Checking environment setup...")

    # PostgreSQL check
    try:
        result = subprocess.run(
            ["psql", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("  ✓ PostgreSQL installed")
        else:
            issues.append("PostgreSQL not found (optional - SQLite fallback available)")
            print("  ⚠ PostgreSQL not found (will use SQLite)")
    except Exception:
        issues.append("PostgreSQL not found (optional - SQLite fallback available)")
        print("  ⚠ PostgreSQL not found (will use SQLite)")

    # Qdrant check
    try:
        import requests
        response = requests.get("http://localhost:6333/health", timeout=2)
        if response.status_code == 200:
            print("  ✓ Qdrant running")
        else:
            issues.append("Qdrant not running (optional - FAISS fallback available)")
            print("  ⚠ Qdrant not running (will use FAISS)")
    except Exception:
        issues.append("Qdrant not running (optional - FAISS fallback available)")
        print("  ⚠ Qdrant not running (will use FAISS)")

    # 2. Python Dependencies
    print("\n[2/6] Checking Python dependencies...")

    required_packages = [
        ("sentence_transformers", "sentence-transformers"),
        ("torch", "torch"),
        ("fastapi", "fastapi"),
        ("pydantic", "pydantic"),
    ]

    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
            print(f"  ✓ {package_name} installed")
        except ImportError:
            issues.append(f"Missing required package: {package_name}")
            print(f"  ✗ {package_name} NOT INSTALLED")

    # 3. Git Repository Status
    print("\n[3/6] Checking git repository...")

    try:
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=5
        )

        if result.stdout.strip():
            print(f"  ⚠ Uncommitted changes detected:\n{result.stdout}")
            print("  → Will create checkpoint before proceeding")
        else:
            print("  ✓ Working directory clean")

        # Check current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=5
        )
        branch = result.stdout.strip()
        print(f"  ✓ Current branch: {branch}")

    except Exception as e:
        issues.append(f"Git check failed: {e}")
        print(f"  ✗ Git check failed: {e}")

    # 4. Embedding Backend Validation
    print("\n[4/6] Validating embedding backend...")

    try:
        backend = get_embedding_backend()
        print(f"  → Current backend: {backend}")

        if backend == "hash":
            issues.append("BLOCKER: Hash embeddings not semantic - Phase 1 will fail")
            print("  ✗ Hash embeddings detected (NOT semantic)")
            print("  → Install sentence-transformers: pip install sentence-transformers torch")
        else:
            print(f"  ✓ Semantic backend detected: {backend}")

            # Test semantic similarity
            try:
                emb1 = embed_text("user authentication logic")
                emb2 = embed_text("login and auth system")
                emb3 = embed_text("database schema migration")

                sim_12 = cosine_sim(emb1, emb2)
                sim_13 = cosine_sim(emb1, emb3)

                print(f"  → Semantic similarity test:")
                print(f"    - Related concepts: {sim_12:.3f} (expected > 0.7)")
                print(f"    - Unrelated concepts: {sim_13:.3f} (expected < 0.5)")

                if sim_12 > 0.7 and sim_13 < 0.5:
                    print("  ✓ Semantic embeddings working correctly")
                else:
                    issues.append(f"Semantic similarity test failed: related={sim_12:.3f}, unrelated={sim_13:.3f}")
                    print("  ✗ Semantic similarity test failed")
            except Exception as e:
                issues.append(f"Embedding test failed: {e}")
                print(f"  ✗ Embedding test failed: {e}")

    except Exception as e:
        issues.append(f"Embedding backend check failed: {e}")
        print(f"  ✗ Embedding backend check failed: {e}")

    # 5. Protected Path Check
    print("\n[5/6] Checking existing protected paths...")

    try:
        from autopack.governed_apply import apply_governed_patch
        print("  ✓ governed_apply.py accessible")

        # Check if lovable/ directory already exists
        lovable_dir = Path(__file__).parent.parent / "src" / "autopack" / "lovable"
        if lovable_dir.exists():
            print(f"  ⚠ src/autopack/lovable/ already exists")
            print(f"  → Will preserve existing files during Phase 0.1")
        else:
            print("  ✓ src/autopack/lovable/ does not exist (will be created)")

    except Exception as e:
        issues.append(f"Protected path check failed: {e}")
        print(f"  ✗ Protected path check failed: {e}")

    # 6. Test Suite Baseline
    print("\n[6/6] Running baseline test suite...")

    try:
        result = subprocess.run(
            ["pytest", "tests/autopack/", "-v", "--tb=line", "-x"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=120
        )

        if result.returncode == 0:
            print("  ✓ All existing tests pass")
        else:
            issues.append("Existing tests failing - fix before proceeding")
            print("  ✗ Some tests failing")
            print(f"  → Output:\n{result.stdout[-500:]}")

    except subprocess.TimeoutExpired:
        issues.append("Test suite timeout - investigate slow tests")
        print("  ✗ Test suite timeout")
    except Exception as e:
        issues.append(f"Test suite check failed: {e}")
        print(f"  ✗ Test suite check failed: {e}")

    # Summary
    print("\n" + "="*80)
    if not issues:
        print("✓ ALL PRE-IMPLEMENTATION CHECKS PASSED")
        print("="*80)
        return True, []
    else:
        print("⚠ ISSUES DETECTED:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("="*80)

        # Check for blockers
        blockers = [issue for issue in issues if "BLOCKER" in issue or "NOT INSTALLED" in issue]
        if blockers:
            print("\n❌ BLOCKERS DETECTED - CANNOT PROCEED")
            return False, issues
        else:
            print("\n⚠ Non-blocking issues detected - proceeding with caution")
            return True, issues


def create_git_checkpoint() -> bool:
    """Create git checkpoint before Phase 0 implementation."""
    print("\n" + "="*80)
    print("CREATING GIT CHECKPOINT")
    print("="*80)

    repo_root = Path(__file__).parent.parent

    try:
        # Create checkpoint tag
        subprocess.run(
            ["git", "tag", "-f", "lovable-phase0-start", "-m", "Checkpoint before Phase 0 implementation"],
            cwd=repo_root,
            check=True,
            timeout=5
        )
        print("✓ Created git tag: lovable-phase0-start")

        # Show current commit
        result = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=5
        )
        print(f"✓ Current commit: {result.stdout.strip()}")

        return True

    except Exception as e:
        print(f"✗ Failed to create checkpoint: {e}")
        return False


def execute_phase0(dry_run: bool = False, skip_approval: bool = False) -> bool:
    """Execute Phase 0 autonomous implementation."""

    print("\n" + "="*80)
    print("EXECUTING PHASE 0: FOUNDATION & GOVERNANCE")
    print("="*80)

    config_path = Path(__file__).parent.parent / ".autonomous_runs" / "lovable-integration-v1" / "run_config_phase0.json"

    if not config_path.exists():
        print(f"✗ Config not found: {config_path}")
        return False

    print(f"\n✓ Loading config: {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    print(f"✓ Run ID: {config['run_id']}")
    print(f"✓ Phases: {len(config['phases'])}")

    for i, phase in enumerate(config['phases'], 1):
        print(f"  {i}. {phase['phase_name']} ({phase['decision_category']}, {phase['risk_level']} risk)")

    if dry_run:
        print("\n⚠ DRY RUN MODE - No actual execution")
        return True

    if not skip_approval:
        print("\n" + "="*80)
        response = input("Proceed with autonomous execution? [y/N]: ")
        if response.lower() != 'y':
            print("✗ Execution cancelled by user")
            return False

    print("\n🚀 Starting autonomous execution...")
    print("="*80)

    # Execute via autonomous_executor
    try:
        # Build command
        cmd = [
            sys.executable,
            "-m", "autopack.autonomous_executor",
            "--run-id", config['run_id'],
            "--config", str(config_path),
            "--max-iterations", "10"
        ]

        print(f"\nCommand: {' '.join(cmd)}\n")

        # Execute
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent.parent,
            env={
                **subprocess.os.environ,
                "PYTHONUTF8": "1",
                "PYTHONPATH": "src",
                "DATABASE_URL": "sqlite:///autopack.db"
            }
        )

        return result.returncode == 0

    except Exception as e:
        print(f"\n✗ Execution failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Execute Phase 0: Foundation & Governance")
    parser.add_argument("--dry-run", action="store_true", help="Check prerequisites only, don't execute")
    parser.add_argument("--skip-approval", action="store_true", help="Skip user approval prompt")
    parser.add_argument("--skip-prereq", action="store_true", help="Skip prerequisite checks (dangerous)")

    args = parser.parse_args()

    print("\n" + "="*80)
    print("LOVABLE INTEGRATION - PHASE 0 AUTONOMOUS EXECUTION")
    print("="*80)
    print("\nThis script will autonomously implement:")
    print("  - Phase 0.1: Protected-Path Strategy (2 days)")
    print("  - Phase 0.2: Semantic Embedding Backend (2 days)")
    print("  - Phase 0.3: Browser Telemetry Ingestion (3 days)")
    print("\nAll changes will be validated against:")
    print("  - AUTONOMOUS_IMPLEMENTATION_CHECKLIST.md")
    print("  - Symbol preservation checks")
    print("  - Structural similarity ≥70%")
    print("  - Test coverage ≥90%")

    # Check prerequisites
    if not args.skip_prereq:
        passed, issues = check_prerequisites()

        if not passed:
            print("\n❌ PREREQUISITE CHECKS FAILED")
            print("\nResolve blocking issues before proceeding:")
            for issue in issues:
                if "BLOCKER" in issue or "NOT INSTALLED" in issue:
                    print(f"  - {issue}")
            sys.exit(1)

    # Create git checkpoint
    if not args.dry_run:
        if not create_git_checkpoint():
            print("\n❌ Failed to create git checkpoint")
            sys.exit(1)

    # Execute Phase 0
    success = execute_phase0(dry_run=args.dry_run, skip_approval=args.skip_approval)

    if success:
        print("\n" + "="*80)
        print("✓ PHASE 0 EXECUTION COMPLETE")
        print("="*80)
        print("\nNext steps:")
        print("  1. Review implementation in src/autopack/lovable/")
        print("  2. Run full test suite: pytest tests/autopack/ -v")
        print("  3. Validate checklist: .autonomous_runs/lovable-integration-v1/AUTONOMOUS_IMPLEMENTATION_CHECKLIST.md")
        print("  4. Proceed to Phase 1 if all gates pass")
        sys.exit(0)
    else:
        print("\n" + "="*80)
        print("✗ PHASE 0 EXECUTION FAILED")
        print("="*80)
        print("\nRollback procedure:")
        print("  git reset --hard lovable-phase0-start")
        print("  git tag -d lovable-phase0-start")
        sys.exit(1)


if __name__ == "__main__":
    main()
