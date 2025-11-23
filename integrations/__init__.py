"""
Autopack Integrations Package

This package provides integration modules for connecting external AI agents
(Cursor and Codex) with the Autopack orchestrator.

Modules:
- cursor_integration: Builder (Cursor) integration
- codex_integration: Auditor (Codex) integration
- supervisor: Orchestration loop coordinating Builder and Auditor
"""

from .cursor_integration import CursorBuilder
from .codex_integration import CodexAuditor
from .supervisor import Supervisor

__all__ = ["CursorBuilder", "CodexAuditor", "Supervisor"]
