"""
Sub-agent orchestration module for Claude Code integration.

Provides:
- Context file management (handoff/context.md)
- Standard sub-agent output contract
- Task brief generation
- Guardrails enforcement (no secrets, no side effects, traceability)

BUILD-197: Claude Code sub-agent glue work
"""

from autopack.subagent.context import (ContextFile, ContextFileManager,
                                       SubagentFinding, SubagentProposal)
from autopack.subagent.guardrails import (GuardrailResult, GuardrailViolation,
                                          SubagentGuardrails)
from autopack.subagent.output_contract import (OutputContract, SubagentOutput,
                                               SubagentOutputValidator)
from autopack.subagent.task_brief import (TaskBrief, TaskBriefGenerator,
                                          TaskConstraint)

__all__ = [
    # Context management
    "ContextFile",
    "ContextFileManager",
    "SubagentFinding",
    "SubagentProposal",
    # Output contract
    "OutputContract",
    "SubagentOutput",
    "SubagentOutputValidator",
    # Task briefs
    "TaskBrief",
    "TaskBriefGenerator",
    "TaskConstraint",
    # Guardrails
    "GuardrailResult",
    "GuardrailViolation",
    "SubagentGuardrails",
]
