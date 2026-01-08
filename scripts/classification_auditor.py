#!/usr/bin/env python3
"""
Classification Auditor - LLM-based verification layer

This auditor provides human-in-the-loop verification using an LLM to:
1. Review classifier's decision with full file context
2. Cross-reference with project knowledge
3. Override low-confidence classifications
4. Flag ambiguous cases for manual review

WHY NOT REDUNDANT:
- Vector DB: Pattern matching ("looks like a plan file")
- Auditor: Deep understanding ("THIS plan is for file-organizer's country packs feature")
"""

import os
import sys
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

# Repo root detection for dynamic paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from glm_native_client import NativeGLMClient
except ImportError:
    NativeGLMClient = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None


class ClassificationAuditor:
    """
    LLM-powered auditor for classification decisions.

    Provides contextual review of classifier decisions before execution.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        postgres_dsn: Optional[str] = None,
        audit_threshold: float = 0.80,  # Only audit if confidence < 80%
        enable_auto_override: bool = True,
    ):
        """
        Initialize auditor.

        Args:
            llm_client: LLM client for deep analysis
            postgres_dsn: PostgreSQL connection for project knowledge
            audit_threshold: Only audit classifications below this confidence
            enable_auto_override: Allow auditor to override classifier decisions
        """
        self.llm_client = llm_client or self._init_llm()
        self.postgres_dsn = postgres_dsn or os.getenv("DATABASE_URL")
        self.audit_threshold = audit_threshold
        self.enable_auto_override = enable_auto_override

        self.pg_conn = None
        if self.postgres_dsn and psycopg2:
            try:
                self.pg_conn = psycopg2.connect(self.postgres_dsn)
            except Exception:
                pass

    def _init_llm(self):
        """Initialize LLM client."""
        if NativeGLMClient:
            # Default comes from config/models.yaml tool_models.tidy_semantic.
            return NativeGLMClient()
        return None

    def audit_classification(
        self,
        file_path: Path,
        file_content: str,
        classifier_result: Tuple[str, str, str, float],  # (project, type, dest, confidence)
    ) -> Tuple[bool, str, str, str, float, str]:
        """
        Audit a classification decision.

        Args:
            file_path: Path to the file
            file_content: Full file content (not just sample)
            classifier_result: Tuple of (project_id, file_type, dest_path, confidence)

        Returns:
            Tuple of (approved, final_project, final_type, final_dest, final_confidence, audit_reason)
            - approved: Whether to proceed with this classification
            - final_*: Auditor's decision (may override classifier)
            - audit_reason: Explanation of audit decision
        """

        project_id, file_type, dest_path, confidence = classifier_result

        # Skip audit if confidence is high
        if confidence >= self.audit_threshold:
            return (True, project_id, file_type, dest_path, confidence, "High confidence, no audit needed")

        # Perform LLM-based audit
        if not self.llm_client:
            # No LLM available, trust classifier
            return (True, project_id, file_type, dest_path, confidence, "No LLM available")

        print(f"[Auditor] Reviewing low-confidence classification ({confidence:.2f}) for: {file_path.name}")

        # Build context-rich prompt
        prompt = self._build_audit_prompt(file_path, file_content, project_id, file_type, confidence)

        # Get LLM audit
        try:
            response = self.llm_client.chat([{"role": "user", "content": prompt}])
            audit_result = self._parse_audit_response(response)

            # Check if LLM agrees or overrides
            if audit_result["action"] == "approve":
                return (
                    True,
                    project_id,
                    file_type,
                    dest_path,
                    min(confidence * 1.1, 1.0),  # Boost confidence slightly
                    f"Auditor approved: {audit_result['reason']}"
                )

            elif audit_result["action"] == "override" and self.enable_auto_override:
                # LLM suggests different classification
                new_project = audit_result.get("suggested_project", project_id)
                new_type = audit_result.get("suggested_type", file_type)

                # Build new destination path
                if new_project == "autopack":
                    new_dest = str(REPO_ROOT / "archive" / f"{new_type}s" / file_path.name)
                else:
                    new_dest = str(REPO_ROOT / ".autonomous_runs" / new_project / "archive" / f"{new_type}s" / file_path.name)

                print(f"[Auditor] OVERRIDE: {project_id}/{file_type} -> {new_project}/{new_type}")

                return (
                    True,
                    new_project,
                    new_type,
                    new_dest,
                    0.95,  # Auditor override has high confidence
                    f"Auditor override: {audit_result['reason']}"
                )

            elif audit_result["action"] == "flag":
                # LLM uncertain, flag for manual review
                print(f"[Auditor] FLAGGED for manual review: {audit_result['reason']}")
                return (
                    False,  # Don't auto-move
                    project_id,
                    file_type,
                    dest_path,
                    confidence,
                    f"Flagged for manual review: {audit_result['reason']}"
                )

        except Exception as e:
            print(f"[Auditor] Error during audit: {e}")
            # On error, trust classifier
            return (True, project_id, file_type, dest_path, confidence, f"Audit error: {e}")

        # Default: trust classifier
        return (True, project_id, file_type, dest_path, confidence, "Auditor review complete")

    def _build_audit_prompt(
        self,
        file_path: Path,
        file_content: str,
        classified_project: str,
        classified_type: str,
        confidence: float
    ) -> str:
        """Build context-rich audit prompt for LLM."""

        # Get project context from database
        project_context = self._get_project_context(classified_project)

        prompt = f"""You are a Classification Auditor reviewing file organization decisions.

**FILE DETAILS**:
- Filename: {file_path.name}
- Extension: {file_path.suffix}
- Size: {len(file_content)} chars

**CLASSIFIER DECISION** (needs review):
- Project: {classified_project}
- Type: {classified_type}
- Confidence: {confidence:.2f} (LOW - below 0.80 threshold)

**FILE CONTENT** (first 1000 chars):
```
{file_content[:1000]}
```

**PROJECT CONTEXT**:
{project_context}

**YOUR TASK**:
1. Read the file content carefully
2. Determine which project this file ACTUALLY relates to (not just pattern matching)
3. Determine what type of file it ACTUALLY is
4. Consider: Does the content discuss specific features, runs, or components of a project?

**RESPOND IN THIS FORMAT**:
ACTION: [approve | override | flag]
REASON: [Your detailed reasoning]
SUGGESTED_PROJECT: [only if override: autopack | file-organizer-app-v1]
SUGGESTED_TYPE: [only if override: plan | analysis | report | log | script | etc]

**DECISION GUIDELINES**:
- APPROVE: Classifier is correct despite low confidence
- OVERRIDE: Classifier is wrong, here's the correct classification
- FLAG: Too ambiguous, needs manual human review

RESPOND:"""

        return prompt

    def _get_project_context(self, project_id: str) -> str:
        """Get project-specific context from database."""

        if not self.pg_conn:
            return self._get_hardcoded_project_context(project_id)

        try:
            cursor = self.pg_conn.cursor()

            # Get project configuration
            cursor.execute("""
                SELECT base_path, runs_path, archive_path, docs_path
                FROM project_directory_config
                WHERE project_id = %s
            """, (project_id,))

            config = cursor.fetchone()
            if not config:
                return self._get_hardcoded_project_context(project_id)

            context = f"""
PROJECT: {project_id}
- Base path: {config[0]}
- Runs path: {config[1]}
- Archive path: {config[2]}
- Docs path: {config[3]}

KNOWN FILE TYPES FOR THIS PROJECT:
"""

            # Get routing rules for this project
            cursor.execute("""
                SELECT file_type, content_keywords, destination_path
                FROM directory_routing_rules
                WHERE project_id = %s
                ORDER BY priority DESC
                LIMIT 10
            """, (project_id,))

            rules = cursor.fetchall()
            for rule in rules:
                file_type, keywords, dest = rule
                context += f"- {file_type}: keywords={keywords}, dest={dest}\n"

            cursor.close()
            return context

        except Exception:
            return self._get_hardcoded_project_context(project_id)

    def _get_hardcoded_project_context(self, project_id: str) -> str:
        """Fallback project context if database unavailable."""

        if project_id == "autopack":
            return f"""
PROJECT: Autopack (Autonomous Build Orchestration System)
- Core features: Phase execution, LLM usage, autonomous executor, tidy workspace
- Key components: RunFileLayout, autonomous_executor, tidy_workspace, phase management
- Typical files: Implementation plans, analysis docs, diagnostic logs, API logs, scripts
- Location: {REPO_ROOT}
"""
        elif project_id == "file-organizer-app-v1":
            return """
PROJECT: File Organizer App
- Core features: Country-specific folder structures (UK, Canada, Australia), tax documents
- Key components: Folder templates, country packs, document categorization
- Typical files: Country pack plans, build analysis, frontend/backend code, Docker configs
- Location: .autonomous_runs/file-organizer-app-v1/
"""
        else:
            return f"PROJECT: {project_id}\n(No context available)"

    def _parse_audit_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM audit response."""

        result = {
            "action": "approve",  # Default
            "reason": "No clear decision in response",
        }

        lines = response.strip().split('\n')

        for line in lines:
            line = line.strip()

            if line.startswith("ACTION:"):
                action = line.split(":", 1)[1].strip().lower()
                if action in ["approve", "override", "flag"]:
                    result["action"] = action

            elif line.startswith("REASON:"):
                result["reason"] = line.split(":", 1)[1].strip()

            elif line.startswith("SUGGESTED_PROJECT:"):
                result["suggested_project"] = line.split(":", 1)[1].strip()

            elif line.startswith("SUGGESTED_TYPE:"):
                result["suggested_type"] = line.split(":", 1)[1].strip()

        return result

    def close(self):
        """Close database connection."""
        if self.pg_conn:
            self.pg_conn.close()


def batch_audit_classifications(
    classifications: list,
    auditor: ClassificationAuditor,
    show_approved: bool = False
) -> Tuple[list, list, list]:
    """
    Batch audit multiple classifications.

    Args:
        classifications: List of (file_path, content, classifier_result) tuples
        auditor: ClassificationAuditor instance
        show_approved: Show approved classifications (not just overrides/flags)

    Returns:
        Tuple of (approved, overridden, flagged) lists
    """

    approved = []
    overridden = []
    flagged = []

    print(f"\n=== Auditing {len(classifications)} Classifications ===\n")

    for file_path, content, classifier_result in classifications:
        result = auditor.audit_classification(file_path, content, classifier_result)
        is_approved, final_proj, final_type, final_dest, final_conf, reason = result

        if not is_approved:
            flagged.append((file_path, classifier_result, reason))
            print(f"[FLAGGED] {file_path.name}: {reason}")

        elif final_proj != classifier_result[0] or final_type != classifier_result[1]:
            overridden.append((file_path, classifier_result, (final_proj, final_type, final_dest, final_conf), reason))
            print(f"[OVERRIDE] {file_path.name}: {classifier_result[0]}/{classifier_result[1]} -> {final_proj}/{final_type}")

        else:
            approved.append((file_path, classifier_result, reason))
            if show_approved:
                print(f"[APPROVED] {file_path.name}: {reason}")

    print(f"\n=== Audit Summary ===")
    print(f"Approved: {len(approved)}")
    print(f"Overridden: {len(overridden)}")
    print(f"Flagged for manual review: {len(flagged)}")

    return approved, overridden, flagged


def main():
    """Demo/test auditor."""
    import argparse

    parser = argparse.ArgumentParser(description="Classification Auditor Demo")
    parser.add_argument("--file", type=Path, help="File to audit")
    parser.add_argument("--project", default="autopack", help="Classified project")
    parser.add_argument("--type", default="plan", help="Classified type")
    parser.add_argument("--confidence", type=float, default=0.65, help="Classifier confidence")

    args = parser.parse_args()

    if not args.file or not args.file.exists():
        print("Usage: python classification_auditor.py --file FILE_PATH")
        sys.exit(1)

    # Read file
    content = args.file.read_text(encoding="utf-8", errors="ignore")

    # Simulate classifier result
    classifier_result = (args.project, args.type, f"dest/{args.file.name}", args.confidence)

    # Create auditor
    auditor = ClassificationAuditor(
        audit_threshold=0.80,
        enable_auto_override=True
    )

    # Audit
    result = auditor.audit_classification(args.file, content, classifier_result)
    approved, final_proj, final_type, final_dest, final_conf, reason = result

    # Display result
    print("\n=== Audit Result ===")
    print(f"File: {args.file}")
    print(f"Classifier: {args.project}/{args.type} (confidence={args.confidence})")
    print(f"Auditor: {final_proj}/{final_type} (confidence={final_conf})")
    print(f"Approved: {approved}")
    print(f"Reason: {reason}")

    auditor.close()


if __name__ == "__main__":
    main()
