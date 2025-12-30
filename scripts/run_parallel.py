#!/usr/bin/env python3
"""Production script for parallel run execution.

Usage:
    python scripts/run_parallel.py run1 run2 run3 --max-concurrent 3
    python scripts/run_parallel.py --run-ids-file runs.txt --max-concurrent 5
    AUTOPACK_API_URL=http://localhost:8000 python scripts/run_parallel.py run1 run2

Environment Variables:
    AUTOPACK_API_URL: API server URL (default: http://localhost:8000)
    AUTOPACK_API_KEY: API key (optional)
    SOURCE_REPO: Source repository path (default: current directory)
    WORKTREE_BASE: Base directory for worktrees (default: /tmp/autopack_worktrees)
"""

import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
from typing import List
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.parallel_orchestrator import execute_parallel_runs, RunResult

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def read_run_ids_from_file(file_path: str) -> List[str]:
    """Read run IDs from a file (one per line).

    Args:
        file_path: Path to file containing run IDs

    Returns:
        List of run IDs (empty lines and comments ignored)
    """
    run_ids = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                run_ids.append(line)
    return run_ids


async def mock_executor(run_id: str, workspace: Path) -> bool:
    """Mock executor for testing (replace with actual executor logic).

    Args:
        run_id: Run ID
        workspace: Workspace path

    Returns:
        True for success, False for failure
    """
    logger.info(f"[{run_id}] Executing in workspace: {workspace}")

    # Simulate work
    await asyncio.sleep(2)

    # Mock success (90% success rate for demo)
    import random
    success = random.random() > 0.1

    if success:
        logger.info(f"[{run_id}] Execution completed successfully")
    else:
        logger.error(f"[{run_id}] Execution failed")

    return success


def write_report(results: List[RunResult], output_path: str):
    """Write consolidated execution report.

    Args:
        results: List of RunResult objects
        output_path: Path to write report
    """
    report_lines = []
    report_lines.append("# Parallel Execution Report")
    report_lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    report_lines.append("")

    # Summary
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful

    report_lines.append("## Summary")
    report_lines.append(f"- Total runs: {total}")
    report_lines.append(f"- Successful: {successful} ({successful/total*100:.1f}%)")
    report_lines.append(f"- Failed: {failed} ({failed/total*100:.1f}%)")
    report_lines.append("")

    # Results
    report_lines.append("## Results")
    report_lines.append("")

    for result in results:
        status = "✅ SUCCESS" if result.success else "❌ FAILED"
        duration = (result.end_time - result.start_time).total_seconds() if result.end_time and result.start_time else 0

        report_lines.append(f"### {result.run_id}")
        report_lines.append(f"- Status: {status}")
        report_lines.append(f"- Duration: {duration:.2f}s")

        if result.workspace_path:
            report_lines.append(f"- Workspace: {result.workspace_path}")

        if result.error:
            report_lines.append(f"- Error: {result.error}")

        report_lines.append("")

    # Write report
    with open(output_path, 'w') as f:
        f.write('\n'.join(report_lines))

    logger.info(f"Report written to: {output_path}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Execute multiple Autopack runs in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "run_ids",
        nargs="*",
        help="Run IDs to execute (can also use --run-ids-file)",
    )

    parser.add_argument(
        "--run-ids-file",
        help="File containing run IDs (one per line)",
    )

    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=3,
        help="Maximum concurrent runs (default: 3)",
    )

    parser.add_argument(
        "--source-repo",
        help="Source repository path (default: $SOURCE_REPO or current directory)",
    )

    parser.add_argument(
        "--worktree-base",
        help="Base directory for worktrees (default: $WORKTREE_BASE or /tmp/autopack_worktrees)",
    )

    parser.add_argument(
        "--report",
        default="parallel_execution_report.md",
        help="Path to write execution report (default: parallel_execution_report.md)",
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not cleanup worktrees after execution (for debugging)",
    )

    args = parser.parse_args()

    # Collect run IDs
    run_ids = list(args.run_ids) if args.run_ids else []

    if args.run_ids_file:
        file_run_ids = read_run_ids_from_file(args.run_ids_file)
        run_ids.extend(file_run_ids)

    if not run_ids:
        logger.error("No run IDs provided. Use positional arguments or --run-ids-file")
        return 1

    # Remove duplicates while preserving order
    seen = set()
    run_ids = [x for x in run_ids if not (x in seen or seen.add(x))]

    logger.info(f"Executing {len(run_ids)} runs in parallel (max concurrent: {args.max_concurrent})")
    logger.info(f"Run IDs: {', '.join(run_ids)}")

    # Configuration
    source_repo = args.source_repo or os.getenv("SOURCE_REPO") or Path.cwd()
    worktree_base = args.worktree_base or os.getenv("WORKTREE_BASE") or Path("/tmp/autopack_worktrees")

    source_repo = Path(source_repo).resolve()
    worktree_base = Path(worktree_base).resolve()

    logger.info(f"Source repo: {source_repo}")
    logger.info(f"Worktree base: {worktree_base}")

    # Ensure worktree base exists
    worktree_base.mkdir(parents=True, exist_ok=True)

    # Execute runs in parallel
    try:
        results = await execute_parallel_runs(
            run_ids=run_ids,
            executor_func=mock_executor,  # TODO: Replace with actual executor
            max_concurrent=args.max_concurrent,
            source_repo=source_repo,
            worktree_base=worktree_base,
        )

        # Write report
        write_report(results, args.report)

        # Print summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        logger.info(f"Execution complete: {successful} successful, {failed} failed")

        return 0 if failed == 0 else 1

    except Exception as e:
        logger.error(f"Parallel execution failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
