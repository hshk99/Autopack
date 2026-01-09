"""Dry-run mode for side-effect integrations.

Implements gap analysis item 6.3: Dry-run first modes.

Every integration action supports dry_run=true that produces a fully-rendered
request payload + predicted side effects, without executing.
"""

from .models import DryRunResult, DryRunApproval, DryRunStatus
from .executor import DryRunExecutor

__all__ = ["DryRunResult", "DryRunApproval", "DryRunStatus", "DryRunExecutor"]
