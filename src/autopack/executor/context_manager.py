"""
Context Manager Module

Extracted from autonomous_executor.py to manage context building and loading.
This module addresses complexity by separating context management into
testable, modular components.

Key responsibilities:
- Load and validate file context
- Retrieve and deduplicate memory context
- Inject learning hints and project rules
- Build deliverables contracts
- Manage context budgets and SOT retrieval

Related modules:
- builder_orchestrator.py: Builder orchestration that uses context
- retrieval_injection.py: SOT retrieval and injection
- context_preflight.py: Context validation
"""

from dataclasses import dataclass
from typing import Dict, Optional, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ContextResult:
    """Result of context loading"""

    file_context: Dict[str, Any]
    learning_context: Dict[str, Any]
    retrieval_context: Optional[str] = None
    deliverables_contract: Optional[str] = None
    context_stats: Optional[Dict[str, Any]] = None


class ContextManager:
    """
    Manages context building for phase execution.

    Coordinates the loading of:
    - File context from scope
    - Memory context from vector search
    - Learning hints from project rules and run history
    - SOT (Source of Truth) retrieval
    """

    def __init__(
        self,
        memory_service: Optional[Any] = None,
        retrieval_injection: Optional[Any] = None,
        heuristic_loader: Optional[Any] = None,
        scoped_context_loader: Optional[Any] = None,
        scope_context_validator: Optional[Any] = None,
        context_preflight: Optional[Any] = None,
    ):
        """Initialize ContextManager with dependencies.

        Args:
            memory_service: Optional memory service for vector search
            retrieval_injection: Optional SOT retrieval module
            heuristic_loader: Optional heuristic context loader
            scoped_context_loader: Optional scoped context loader
            scope_context_validator: Optional context validator
            context_preflight: Optional context preflight validator
        """
        self.memory_service = memory_service
        self.retrieval_injection = retrieval_injection
        self.heuristic_loader = heuristic_loader
        self.scoped_context_loader = scoped_context_loader
        self.scope_context_validator = scope_context_validator
        self.context_preflight = context_preflight

    def build_context(
        self,
        phase: Dict,
        scope_config: Dict,
        workspace: Path,
        git_files: Optional[List[str]] = None,
        mentioned_files: Optional[List[str]] = None,
        priority_files: Optional[List[str]] = None,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> ContextResult:
        """Build complete context for phase execution.

        Args:
            phase: Phase specification dict
            scope_config: Scope configuration dict
            workspace: Workspace root path
            git_files: Optional list of git status files
            mentioned_files: Optional list of mentioned files
            priority_files: Optional list of priority files
            project_rules: Optional list of project learning rules
            run_hints: Optional list of run-local hints

        Returns:
            ContextResult with all context components
        """
        phase_id = phase.get("phase_id", "unknown")

        logger.info(f"[{phase_id}] Building context for phase...")

        # 1. Load file context
        file_context = self._load_file_context(
            phase_id, phase, scope_config, workspace, git_files, mentioned_files, priority_files
        )

        # 2. Load memory/SOT context
        retrieval_context = self._load_retrieval_context(phase, file_context, project_rules)

        # 3. Build learning context
        learning_context = self._build_learning_context(phase, project_rules, run_hints)

        # 4. Build deliverables contract
        deliverables_contract = self._build_deliverables_contract(phase, phase_id)

        # 5. Compute context stats
        context_stats = self._compute_context_stats(
            file_context, retrieval_context, learning_context
        )

        logger.info(
            f"[{phase_id}] Context built: "
            f"{len(file_context.get('files', []))} files, "
            f"learning_rules={len(project_rules) if project_rules else 0}, "
            f"run_hints={len(run_hints) if run_hints else 0}"
        )

        return ContextResult(
            file_context=file_context,
            learning_context=learning_context,
            retrieval_context=retrieval_context,
            deliverables_contract=deliverables_contract,
            context_stats=context_stats,
        )

    def _load_file_context(
        self,
        phase_id: str,
        phase: Dict,
        scope_config: Dict,
        workspace: Path,
        git_files: Optional[List[str]],
        mentioned_files: Optional[List[str]],
        priority_files: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Load file context from scope configuration.

        Uses heuristic_loader if available, otherwise simple scope loading.

        Args:
            phase_id: Phase identifier
            phase: Phase specification dict
            scope_config: Scope configuration dict
            workspace: Workspace root path
            git_files: Optional git status files
            mentioned_files: Optional mentioned files
            priority_files: Optional priority files

        Returns:
            File context dict
        """
        if self.heuristic_loader:
            return self.heuristic_loader.load_context_files(
                workspace=workspace,
                git_status_files=git_files or [],
                mentioned_files=mentioned_files or [],
                priority_files=priority_files or [],
            )

        # Fallback: simple scope-based context
        scope_paths = scope_config.get("paths", [])
        files = []
        for path_str in scope_paths:
            path = Path(workspace) / path_str
            if path.exists():
                files.append(str(path))

        return {"files": files, "scope": scope_config}

    def _load_retrieval_context(
        self,
        phase: Dict,
        file_context: Dict,
        project_rules: Optional[List],
    ) -> Optional[str]:
        """Load retrieval context from memory/SOT.

        Args:
            phase: Phase specification dict
            file_context: Loaded file context
            project_rules: Optional project rules

        Returns:
            Formatted retrieval context string or None
        """
        if not self.retrieval_injection or not self.memory_service:
            return None

        phase_id = phase.get("phase_id", "unknown")

        # Check if SOT retrieval should be included
        max_context_chars = phase.get("max_context_chars", 20000)
        if not self._should_include_sot_retrieval(max_context_chars, phase_id):
            logger.debug(f"[{phase_id}] SOT retrieval skipped by budget gate")
            return None

        # Retrieve context (delegates to retrieval_injection)
        retrieval_result = self.retrieval_injection.retrieve_context(
            phase=phase,
            file_context=file_context,
            project_rules=project_rules or [],
        )

        if not retrieval_result:
            return None

        # Format retrieved context
        formatted_context = self.retrieval_injection.format_retrieved_context(retrieval_result)

        # Record telemetry
        self._record_sot_telemetry(
            phase_id,
            True,  # include_sot
            max_context_chars,
            retrieval_result,
            formatted_context,
        )

        return formatted_context

    def _build_learning_context(
        self,
        phase: Dict,
        project_rules: Optional[List],
        run_hints: Optional[List],
    ) -> Dict[str, Any]:
        """Build learning context from rules and hints.

        Args:
            phase: Phase specification dict
            project_rules: Optional project learning rules
            run_hints: Optional run-local hints

        Returns:
            Learning context dict
        """
        return {
            "project_rules": project_rules or [],
            "run_hints": run_hints or [],
        }

    def _build_deliverables_contract(
        self,
        phase: Dict,
        phase_id: str,
    ) -> Optional[str]:
        """Build deliverables contract as hard constraint for Builder.

        Args:
            phase: Phase specification dict
            phase_id: Phase identifier

        Returns:
            Formatted deliverables contract string or None
        """
        scope = phase.get("scope")
        if not scope:
            return None

        # Extract expected deliverables from scope
        expected_paths = []
        if "paths" in scope:
            expected_paths = scope["paths"]
        elif "deliverables" in scope:
            expected_paths = scope["deliverables"]

        if not expected_paths:
            return None

        # Format contract
        contract_parts = ["## Deliverables (Required)", ""]
        for path in expected_paths[:10]:  # Limit to 10 for brevity
            contract_parts.append(f"- {path}")
        if len(expected_paths) > 10:
            contract_parts.append(f"... and {len(expected_paths) - 10} more")

        return "\n".join(contract_parts)

    def _compute_context_stats(
        self,
        file_context: Dict,
        retrieval_context: Optional[str],
        learning_context: Dict,
    ) -> Dict[str, Any]:
        """Compute statistics about loaded context.

        Args:
            file_context: File context dict
            retrieval_context: Optional retrieval context
            learning_context: Learning context dict

        Returns:
            Context statistics dict
        """
        return {
            "file_count": len(file_context.get("files", [])),
            "retrieval_chars": len(retrieval_context) if retrieval_context else 0,
            "project_rules_count": len(learning_context.get("project_rules", [])),
            "run_hints_count": len(learning_context.get("run_hints", [])),
        }

    def _should_include_sot_retrieval(
        self,
        max_context_chars: int,
        phase_id: Optional[str] = None,
    ) -> bool:
        """Determine if SOT retrieval should be included based on budget.

        Args:
            max_context_chars: Total context budget
            phase_id: Optional phase identifier for logging

        Returns:
            True if SOT retrieval should be included
        """
        if not self.retrieval_injection:
            return False

        # Delegate to retrieval_injection if available
        if hasattr(self.retrieval_injection, "gate_sot_retrieval"):
            gate = self.retrieval_injection.gate_sot_retrieval(max_context_chars, phase_id)
            return getattr(gate, "allowed", True)

        # Default: include SOT if budget allows (simple heuristic)
        return max_context_chars >= 4000  # 4k char minimum

    def _record_sot_telemetry(
        self,
        phase_id: str,
        include_sot: bool,
        max_context_chars: int,
        retrieved_context: Dict,
        formatted_context: str,
    ) -> None:
        """Record SOT retrieval telemetry.

        Args:
            phase_id: Phase identifier
            include_sot: Whether SOT retrieval was attempted
            max_context_chars: Total context budget
            retrieved_context: Raw retrieved context dict
            formatted_context: Final formatted context string
        """
        if not self.retrieval_injection:
            return

        # Compute statistics
        sot_chunks = retrieved_context.get("sot", []) or []
        sot_chars_raw = sum(len(chunk.get("content", "")) for chunk in sot_chunks)
        total_chars = len(formatted_context)
        budget_pct = (total_chars / max_context_chars * 100) if max_context_chars > 0 else 0

        logger.info(
            f"[{phase_id}] [SOT] Context telemetry: "
            f"include_sot={include_sot}, "
            f"sot_chunks={len(sot_chunks)}, sot_chars={sot_chars_raw}, "
            f"total_chars={total_chars}/{max_context_chars} ({budget_pct:.1f}%)"
        )

    def validate_context(
        self,
        phase: Dict,
        file_context: Dict,
        scope_config: Dict,
    ) -> bool:
        """Validate that loaded context matches scope configuration.

        Args:
            phase: Phase specification dict
            file_context: Loaded file context
            scope_config: Scope configuration

        Returns:
            True if context is valid
        """
        if self.scope_context_validator:
            return self.scope_context_validator.validate(phase, file_context, scope_config)

        # Default: basic validation
        return True

    def preflight_check(
        self,
        phase: Dict,
        file_context: Dict,
    ) -> bool:
        """Run preflight checks on context.

        Args:
            phase: Phase specification dict
            file_context: Loaded file context

        Returns:
            True if preflight checks pass
        """
        if self.context_preflight:
            phase_id = phase.get("phase_id", "unknown")
            return self.context_preflight.validate(phase_id, phase, file_context)

        # Default: pass
        return True
