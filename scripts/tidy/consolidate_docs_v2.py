#!/usr/bin/env python3
"""
Documentation Consolidation System V2
Consolidates scattered archive files into AI-optimized documentation files.

Target Files:
- BUILD_HISTORY.md - Past implementations (what was built)
- DEBUG_LOG.md - Problem solving (errors and fixes)
- ARCHITECTURE_DECISIONS.md - Design rationale (why decisions were made)

Usage:
  python scripts/tidy/consolidate_docs_v2.py              # Full consolidation
  python scripts/tidy/consolidate_docs_v2.py --dry-run    # Preview only
  python scripts/tidy/consolidate_docs_v2.py --project file-organizer-app-v1
"""

import argparse
import json
import re
import subprocess
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "tidy"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from classification_auditor import ClassificationAuditor


# ============================================================================
# STATUS AUDITOR - Determines if content is implemented/rejected/pending
# ============================================================================

class StatusAuditor:
    """Infers status of archive content by cross-referencing with project state."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.docs_dir = project_dir / "docs"
        self.src_dir = project_dir / "src"

        # State tracking
        self.implemented_features: Set[str] = set()
        self.active_tasks: Set[str] = set()
        self.completed_tasks: Set[str] = set()
        self.codebase_keywords: Set[str] = set()

    def load_project_state(self):
        """Load current project state from FUTURE_PLAN and codebase."""
        print("  [Auditor] Loading project state...")

        # Load FUTURE_PLAN.md
        whats_left = self.docs_dir / "FUTURE_PLAN.md"
        if whats_left.exists():
            self._parse_whats_left_to_build(whats_left)

        # Scan codebase for implemented features
        if self.src_dir.exists():
            self._scan_codebase()

        print(f"    Implemented features: {len(self.implemented_features)}")
        print(f"    Active tasks: {len(self.active_tasks)}")
        print(f"    Completed tasks: {len(self.completed_tasks)}")

    def _parse_whats_left_to_build(self, file_path: Path):
        """Parse FUTURE_PLAN.md for task status (Autopack format)."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # Try Autopack format first (### Task N with **Phase ID** and **Status**)
            lines = content.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i]

                # Detect Autopack task headers: "### Task N:"
                if re.match(r'^###\s+Task\s+\d+:', line, re.IGNORECASE):
                    task_name = line.replace('###', '').strip()
                    phase_id = None
                    status = None

                    # Scan next lines for Phase ID and Status
                    j = i + 1
                    while j < len(lines) and not lines[j].startswith('###') and not lines[j].startswith('---'):
                        curr_line = lines[j]

                        # Extract Phase ID
                        phase_match = re.match(r'\*\*Phase ID\*\*:\s*`(.+?)`', curr_line)
                        if phase_match:
                            phase_id = phase_match.group(1)

                        # Extract Status
                        status_match = re.match(r'\*\*Status\*\*:\s*(.+)', curr_line)
                        if status_match:
                            status = status_match.group(1).strip()

                        j += 1

                    # Classify based on status
                    if status:
                        status_lower = status.lower()
                        # Check for completion indicators
                        if any(keyword in status_lower for keyword in ['complete', 'done', 'finished', 'implemented']):
                            if task_name:
                                self.completed_tasks.add(task_name.lower())
                            if phase_id:
                                self.completed_tasks.add(phase_id.lower())
                        # Check for active/in-progress indicators
                        elif any(keyword in status_lower for keyword in ['in progress', 'started', 'ongoing', 'dependency', 'current']):
                            if task_name:
                                self.active_tasks.add(task_name.lower())
                            if phase_id:
                                self.active_tasks.add(phase_id.lower())

                    i = j
                    continue

                # Fallback: Try classic section-based format
                # Detect section headers
                if re.match(r'^##\s+(Completed|Done|Implemented)', line, re.IGNORECASE):
                    current_section = "completed"
                elif re.match(r'^##\s+(In Progress|Active|Current)', line, re.IGNORECASE):
                    current_section = "active"
                elif re.match(r'^##\s+(Todo|Planned|Future)', line, re.IGNORECASE):
                    current_section = "todo"
                elif line.startswith('##'):
                    current_section = None

                # Extract tasks from bullet lists
                if 'current_section' in locals() and current_section and line.strip().startswith(('-', '*', '+')):
                    task = line.strip()[1:].strip()
                    # Remove checkboxes
                    task = re.sub(r'^\[[ xX]\]\s*', '', task)

                    if current_section == "completed":
                        self.completed_tasks.add(task.lower())
                    elif current_section == "active":
                        self.active_tasks.add(task.lower())

                i += 1

        except Exception as e:
            print(f"    [WARNING] Failed to parse FUTURE_PLAN: {e}")

    def _scan_codebase(self):
        """Quick scan of src/ for major features/technologies."""
        try:
            # Scan Python files for import statements and class names
            for py_file in self.src_dir.rglob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8")

                    # Extract imports
                    imports = re.findall(r'^(?:from|import)\s+(\w+)', content, re.MULTILINE)
                    self.codebase_keywords.update(imports)

                    # Extract class names
                    classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
                    self.codebase_keywords.update(classes)

                    # Extract function names (major ones only)
                    functions = re.findall(r'^def\s+(\w+)', content, re.MULTILINE)
                    self.codebase_keywords.update(f[:20] for f in functions)  # Limit to first 20 chars

                except Exception:
                    continue

            # Add file/directory names as features
            for item in self.src_dir.rglob("*"):
                if item.is_file():
                    self.codebase_keywords.add(item.stem.lower())
        except Exception as e:
            print(f"    [WARNING] Codebase scan failed: {e}")

    def infer_status(self, file_path: Path, content: str, timestamp: datetime) -> str:
        """
        Infer status: IMPLEMENTED, REJECTED, PENDING, STALE, REFERENCE, or UNKNOWN.

        Returns status code that influences classification routing.
        """
        # Check age first (handle both naive and aware datetimes)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        age_days = (datetime.now() - timestamp).days

        # Extract mentioned features/technologies
        mentioned_features = self._extract_mentioned_features(content)

        # 1. Check for explicit rejection markers
        if self._has_rejection_markers(content):
            if age_days > 180:
                return "REJECTED_OBSOLETE"  # Old rejection, can compress
            return "REJECTED"  # Recent rejection, keep full context

        # 2. Check for implementation markers
        if self._has_implementation_markers(content):
            # Cross-reference with codebase
            if self._is_in_codebase(mentioned_features):
                return "IMPLEMENTED"
            else:
                # Claims implementation but not in codebase
                if age_days > 90:
                    return "STALE_IMPLEMENTATION"  # Might be outdated
                return "IMPLEMENTED"  # Trust recent claims

        # 3. Check if in completed tasks
        if self._is_in_completed_tasks(content):
            return "IMPLEMENTED"

        # 4. Check if in active tasks
        if self._is_in_active_tasks(content):
            return "PENDING_ACTIVE"

        # 5. Check for research/reference value
        if self._is_research_content(content):
            return "REFERENCE"  # Permanent keep

        # 6. Age-based staleness
        if age_days > 180:
            return "STALE"  # Old plan never implemented

        return "UNKNOWN"

    def _extract_mentioned_features(self, content: str) -> Set[str]:
        """Extract feature/technology names from content."""
        features = set()

        # Common technology patterns
        tech_patterns = [
            r'\b(qdrant|redis|postgresql|sqlite|docker|kubernetes)\b',
            r'\b(jwt|oauth|authentication|authorization)\b',
            r'\b(fastapi|django|flask|express)\b',
            r'\b(react|vue|angular|svelte)\b',
        ]

        for pattern in tech_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            features.update(m.lower() for m in matches)

        return features

    def _has_rejection_markers(self, content: str) -> bool:
        """Detect explicit rejection language."""
        rejection_patterns = [
            r'decided not to',
            r'abandoned',
            r'superseded by',
            r'too complex',
            r'won\'t implement',
            r'rejected because',
            r'not feasible',
            r'decided against',
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in rejection_patterns)

    def _has_implementation_markers(self, content: str) -> bool:
        """Detect implementation completion language."""
        implementation_patterns = [
            r'implemented',
            r'completed',
            r'deployed',
            r'merged',
            r'live in production',
            r'successfully integrated',
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in implementation_patterns)

    def _is_in_codebase(self, features: Set[str]) -> bool:
        """Check if mentioned features exist in codebase."""
        if not features:
            return False
        return any(feat in self.codebase_keywords for feat in features)

    def _is_in_completed_tasks(self, content: str) -> bool:
        """Check if content matches completed tasks."""
        content_lower = content.lower()
        return any(task in content_lower for task in self.completed_tasks)

    def _is_in_active_tasks(self, content: str) -> bool:
        """Check if content matches active tasks."""
        content_lower = content.lower()
        return any(task in content_lower for task in self.active_tasks)

    def _is_research_content(self, content: str) -> bool:
        """Detect research/reference value."""
        research_indicators = [
            r'comparison of',
            r'evaluation of',
            r'benchmark',
            r'literature review',
            r'market research',
            r'pros and cons',
            r'trade-?offs?',
        ]
        return any(re.search(p, content, re.IGNORECASE) for p in research_indicators)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class DocumentEntry:
    """Represents a single entry to be consolidated."""
    entry_id: str  # BUILD-089, DBG-042, DEC-015
    timestamp: datetime
    title: str
    content: str
    category: str  # "build", "debug", "decision"
    confidence: float
    source_file: str
    metadata: Dict[str, any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Convert entry to markdown format."""
        ts = self.timestamp.strftime("%Y-%m-%dT%H:%M")

        if self.category == "build":
            return self._build_entry_markdown(ts)
        elif self.category == "debug":
            return self._debug_entry_markdown(ts)
        elif self.category == "decision":
            return self._decision_entry_markdown(ts)
        else:
            return f"### {self.entry_id} | {ts} | {self.title}\n\n{self.content}\n"

    def _build_entry_markdown(self, ts: str) -> str:
        """Format BUILD_HISTORY entry."""
        phase_id = self.metadata.get("phase_id", "N/A")
        status = self.metadata.get("status", "✅ Implemented")
        category = self.metadata.get("implementation_category", "Feature")
        files_changed = self.metadata.get("files_changed", [])
        decision_ref = self.metadata.get("decision_ref", "")

        md = f"### {self.entry_id} | {ts} | {self.title}\n"
        md += f"**Phase ID**: {phase_id}\n"
        md += f"**Status**: {status}\n"
        md += f"**Category**: {category}\n"
        md += f"**Implementation Summary**: {self.content}\n"

        if files_changed:
            md += "**Files Changed**:\n"
            for file_info in files_changed:
                md += f"- {file_info}\n"

        if decision_ref:
            md += f"**Decision Reference**: {decision_ref}\n"

        completed = self.metadata.get("completed_at", "")
        if completed:
            md += f"**Completed**: {completed}\n"

        md += f"**Source**: `{self.source_file}`\n\n"
        return md

    def _debug_entry_markdown(self, ts: str) -> str:
        """Format DEBUG_LOG entry."""
        severity = self.metadata.get("severity", "MEDIUM")
        symptom = self.metadata.get("symptom", "")
        root_cause = self.metadata.get("root_cause", "")
        solution = self.metadata.get("solution", "")
        status = self.metadata.get("status", "✅ Resolved")

        md = f"### {self.entry_id} | {ts} | {self.title}\n"
        md += f"**Severity**: {severity}\n"
        md += f"**Status**: {status}\n"

        if symptom:
            md += f"**Symptom**: {symptom}\n"

        md += f"**Root Cause**: {root_cause or self.content}\n"

        if solution:
            md += f"**Solution**: {solution}\n"

        md += f"**Source**: `{self.source_file}`\n\n"
        return md

    def _decision_entry_markdown(self, ts: str) -> str:
        """Format ARCHITECTURE_DECISIONS entry."""
        context = self.metadata.get("context", "")
        options = self.metadata.get("options_considered", [])
        chosen = self.metadata.get("chosen_approach", "")
        rationale = self.metadata.get("rationale", "")
        status = self.metadata.get("status", "✅ Implemented")
        impact = self.metadata.get("impact", "")

        md = f"### {self.entry_id} | {ts} | {self.title}\n"
        md += f"**Status**: {status}\n"

        if context:
            md += f"**Context**: {context}\n"

        if options:
            md += "**Options Considered**:\n"
            for i, option in enumerate(options, 1):
                md += f"{i}. {option}\n"

        md += f"**Chosen Approach**: {chosen or self.content}\n"

        if rationale:
            md += f"**Rationale**: {rationale}\n"

        if impact:
            md += f"**Impact**: {impact}\n"

        md += f"**Source**: `{self.source_file}`\n\n"
        return md


# ============================================================================
# CLASSIFICATION PATTERNS
# ============================================================================

CLASSIFICATION_PATTERNS = {
    "build": {
        "filename_patterns": [
            r".*README\.md$",
            r".*COMPLETE.*\.md$",
            r".*IMPLEMENTATION.*\.md$",
            r".*BUILD.*\.md$",
            r".*PHASE.*\.md$",
            r".*SUMMARY.*\.md$",
            r".*TRANSITION.*\.md$",
            r".*INTEGRATION.*\.md$",
            r".*SETUP.*\.md$",
            r".*GUIDE.*\.md$",
            r".*WIRING.*\.md$",
        ],
        "content_patterns": [
            r"^##\s+What Was Built",
            r"^##\s+Implementation",
            r"^##\s+Complete",
            r"^##\s+Setup",
            r"Phase ID:",
            r"Tests Added:",
            r"Files Changed:",
            r"Implemented:",
            r"Integration:",
            r"Deployed:",
        ],
        "keywords": [
            "implemented", "added", "created", "integrated", "built",
            "deployment", "release", "feature", "enhancement", "refactor",
            "complete", "setup", "install", "configure", "transition"
        ],
    },
    "debug": {
        "filename_patterns": [
            r".*ERROR.*\.md$",
            r".*FIX.*\.md$",
            r".*BUG.*\.md$",
            r".*TEST.*\.md$",
            r".*DEBUG.*\.md$",
            r".*ISSUE.*\.md$",
            r".*TROUBLESHOOT.*\.md$",
            r".*VERIFICATION.*\.md$",
            r"CONSOLIDATED_DEBUG\.md$",
        ],
        "content_patterns": [
            r"^##\s+Error",
            r"^##\s+Bug",
            r"^##\s+Issue",
            r"^##\s+Fix",
            r"Root Cause:",
            r"Symptom:",
            r"Solution:",
            r"Failed:",
            r"Traceback:",
            r"Test Results:",
            r"Verification:",
        ],
        "keywords": [
            "error", "failed", "bug", "fix", "issue", "problem",
            "exception", "traceback", "stack trace", "crash", "failure",
            "test", "verify", "troubleshoot", "debug", "resolve"
        ],
    },
    "decision": {
        "filename_patterns": [
            r".*ANALYSIS.*\.md$",
            r".*STRATEGY.*\.md$",
            r".*RESEARCH.*\.md$",
            r".*DECISION.*\.md$",
            r".*COMPARISON.*\.md$",
            r".*PLAN.*\.md$",
            r".*ASSESSMENT.*\.md$",
            r".*EVALUATION.*\.md$",
            r"CONSOLIDATED_STRATEGY\.md$",
            r"CONSOLIDATED_REFERENCE\.md$",
        ],
        "content_patterns": [
            r"^##\s+Decision",
            r"^##\s+Rationale",
            r"^##\s+Analysis",
            r"^##\s+Strategy",
            r"^##\s+Research",
            r"^##\s+Plan",
            r"Comparison:",
            r"Options Considered:",
            r"Why\s+we",
            r"Approach:",
        ],
        "keywords": [
            "decision", "architecture", "strategy", "research", "analysis",
            "comparison", "evaluation", "rationale", "approach", "design",
            "plan", "assessment", "consideration", "option", "trade-off"
        ],
    },
}


# ============================================================================
# DOCUMENT CONSOLIDATOR
# ============================================================================

class DocumentConsolidator:
    """Main consolidation engine."""

    def __init__(self, project_dir: Path, dry_run: bool = False, run_id: Optional[str] = None, project_id: Optional[str] = None):
        self.project_dir = project_dir
        self.dry_run = dry_run
        self.docs_dir = project_dir / "docs"
        self.archive_dir = project_dir / "archive"

        # Output files
        self.build_history_file = self.docs_dir / "BUILD_HISTORY.md"
        self.debug_log_file = self.docs_dir / "DEBUG_LOG.md"
        self.architecture_decisions_file = self.docs_dir / "ARCHITECTURE_DECISIONS.md"
        self.unsorted_file = self.docs_dir / "UNSORTED_REVIEW.md"

        # Entry collections
        self.build_entries: List[DocumentEntry] = []
        self.debug_entries: List[DocumentEntry] = []
        self.decision_entries: List[DocumentEntry] = []
        self.unsorted_entries: List[Tuple[Path, float, Dict[str, float]]] = []

        # ID counters
        self.build_counter = 1
        self.debug_counter = 1
        self.decision_counter = 1

        # Status auditor (initialized in consolidate())
        self.auditor: Optional[StatusAuditor] = None

        # Classification auditor (LLM-powered review for low-confidence classifications)
        self.classification_auditor: Optional[ClassificationAuditor] = None

        # Override flags for automated workflows (e.g., research consolidation)
        self.force_status: Optional[str] = None  # Force all entries to this status
        self.force_category: Optional[str] = None  # Force all entries to this category (build/debug/decision)

        # Database logging (replaces audit reports)
        from tidy_logger import TidyLogger
        self.run_id = run_id or str(uuid.uuid4())
        self.project_id = project_id or "autopack"
        self.logger = TidyLogger(project_dir, project_id=self.project_id)

    def consolidate(self):
        """Main consolidation workflow with status auditing."""
        print(f"\n{'='*80}")
        print(f"DOCUMENTATION CONSOLIDATION - {self.project_dir.name}")
        print(f"{'='*80}\n")

        # Step 0: Initialize auditors
        print("[0] Initializing auditors...")
        self.auditor = StatusAuditor(self.project_dir)
        self.auditor.load_project_state()

        # Initialize classification auditor with low threshold (0.60)
        # Files below 0.60 confidence will be reviewed by LLM
        self.classification_auditor = ClassificationAuditor(
            audit_threshold=0.60,  # Review everything below 0.60
            enable_auto_override=True
        )
        print("  [ClassificationAuditor] Initialized (threshold=0.60)")

        # Step 1: Process existing CONSOLIDATED files
        self._process_consolidated_files()

        # Step 2: Process archive files
        self._process_archive_files()

        # Step 3: Generate new documentation files
        self._generate_documentation_files()

        # Step 4: Generate unsorted review file
        self._generate_unsorted_review()

        # Step 5: Delete old CONSOLIDATED files
        self._cleanup_old_files()

        print(f"\n{'='*80}")
        print("CONSOLIDATION COMPLETE")
        print(f"{'='*80}\n")

    def _process_consolidated_files(self):
        """Process existing CONSOLIDATED_*.md files."""
        print("[1] Processing existing CONSOLIDATED files...")

        consolidated_files = list(self.docs_dir.glob("CONSOLIDATED_*.md"))

        for file_path in consolidated_files:
            print(f"  Processing {file_path.name}...")
            self._classify_and_extract(file_path)

    def _process_archive_files(self):
        """Process archive markdown files."""
        print("\n[2] Processing archive files...")

        if not self.archive_dir.exists():
            print("  [SKIP] Archive directory not found")
            return

        # Always use recursive glob to process all .md files in subdirectories
        # This ensures comprehensive consolidation of nested archive structures
        md_files = list(self.archive_dir.rglob("*.md"))

        # Exclusion paths (never tidy these)
        exclusion_paths = [
            self.archive_dir / "prompts",  # Prompt templates (not documentation)
            self.archive_dir / "research" / "active",  # Active research awaiting Auditor review
        ]

        for file_path in md_files:
            # Skip excluded directories
            if any(file_path.is_relative_to(excluded) for excluded in exclusion_paths if excluded.exists()):
                print(f"  [SKIP] Excluded: {file_path.relative_to(self.project_dir)}")
                continue

            # Skip certain files
            if file_path.name in ["ARCHIVE_INDEX.md", "README.md"]:
                continue

            print(f"  Processing {file_path.relative_to(self.project_dir)}...")
            self._classify_and_extract(file_path)

    def _classify_and_extract(self, file_path: Path):
        """Classify file and extract entries with status auditing."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  [ERROR] Failed to read {file_path.name}: {e}")
            return

        # CHECK FOR FORCE OVERRIDES (for automated workflows)
        if self.force_status and self.force_category:
            # Automated workflow: bypass classification, use forced values
            print(f"    [FORCED] status={self.force_status}, category={self.force_category}")
            self._extract_entries(file_path, content, self.force_category, status=self.force_status)
            return

        # STEP 1: Infer status (NEW - Status Auditor)
        timestamp = self._extract_timestamp(file_path, content) or datetime.now()
        status = self.force_status or (self.auditor.infer_status(file_path, content, timestamp) if self.auditor else "UNKNOWN")

        # STEP 2: Calculate confidence scores for each category (Existing)
        scores = {
            "build": self._calculate_confidence(file_path, content, "build"),
            "debug": self._calculate_confidence(file_path, content, "debug"),
            "decision": self._calculate_confidence(file_path, content, "decision"),
        }

        best_category = self.force_category or max(scores, key=scores.get)
        best_confidence = scores[best_category] if not self.force_category else 1.0

        # STEP 3: Status-aware routing (NEW - combines status + category)
        routed = self._route_by_status(file_path, content, status, best_category, best_confidence, scores)

        if not routed:
            # Fallback to confidence-based classification with tiered thresholds
            # High confidence (>= 0.75): Check for strategic/schema content before auto-route
            # Medium confidence (0.60-0.74): Route with warning for review
            # Low confidence (< 0.60): Manual review required

            if best_confidence >= 0.75:
                # High confidence - but still check for schema/strategic/reference content

                # First: Check if this is a schema/spec file (always goes to ARCHITECTURE_DECISIONS)
                if self._is_schema_or_spec_file(file_path, content):
                    print(f"    [SCHEMA/SPEC] High confidence ({best_confidence:.2f}) schema/spec file → ARCHITECTURE_DECISIONS")
                    self._extract_entries(file_path, content, "decision", status="REFERENCE",
                                        metadata={"reference": True, "permanent": True,
                                                "original_category": best_category,
                                                "confidence": best_confidence,
                                                "file_type": "schema"})

                # Second: Check if this is reference documentation (tutorials, guides, quickstarts)
                elif self._is_reference_documentation(file_path, content):
                    print(f"    [REFERENCE_DOC] High confidence ({best_confidence:.2f}) reference docs → ARCHITECTURE_DECISIONS")
                    self._extract_entries(file_path, content, "decision", status="REFERENCE",
                                        metadata={"reference": True, "permanent": True,
                                                "original_category": best_category,
                                                "confidence": best_confidence,
                                                "file_type": "reference_doc"})

                # Third: Check if BUILD_HISTORY-bound content has strategic indicators
                elif best_category == "build" and self._is_strategic_content(content):
                    # High-confidence implementation plan with strategic content
                    # Route to BUILD_HISTORY but flag for review
                    print(f"    [HIGH_CONFIDENCE_STRATEGIC] {best_category} ({best_confidence:.2f}) but has strategic content - flagged for review")
                    self._extract_entries(file_path, content, best_category, status=status,
                                        metadata={"has_strategic_content": True,
                                                "needs_review": True,
                                                "confidence": best_confidence})
                else:
                    # Pure high-confidence content - safe to auto-route
                    self._extract_entries(file_path, content, best_category, status=status)
            elif best_confidence >= 0.60:
                # Medium confidence - route but flag for review
                # Check if this is strategic content that shouldn't be in BUILD_HISTORY
                if best_category == "build" and self._is_strategic_content(content):
                    # Strategic content with medium confidence → send to ARCHITECTURE_DECISIONS
                    print(f"    [STRATEGIC] Medium confidence ({best_confidence:.2f}) strategic content → ARCHITECTURE_DECISIONS")
                    self._extract_entries(file_path, content, "decision", status="REFERENCE",
                                        metadata={"reference": True, "needs_review": True,
                                                "original_category": best_category,
                                                "confidence": best_confidence})
                else:
                    # Non-strategic content with medium confidence → route to best category
                    self._extract_entries(file_path, content, best_category, status=status,
                                        metadata={"needs_review": True, "confidence": best_confidence})
                    print(f"    [MEDIUM_CONFIDENCE] Routed to {best_category} (confidence: {best_confidence:.2f})")
            else:
                # Low confidence (< 0.60) - use LLM auditor for deep analysis
                print(f"    [LOW_CONFIDENCE] Confidence too low ({best_confidence:.2f}), invoking ClassificationAuditor...")

                # Prepare classifier result in auditor's expected format
                # Map our categories to file types: build -> plan, debug -> log, decision -> decision
                type_mapping = {"build": "plan", "debug": "log", "decision": "decision"}
                file_type = type_mapping.get(best_category, "report")

                classifier_result = (self.project_id, file_type, str(file_path), best_confidence)

                # Ask auditor to review
                if self.classification_auditor:
                    approved, final_project, final_type, final_dest, final_confidence, audit_reason = \
                        self.classification_auditor.audit_classification(file_path, content, classifier_result)

                    if approved:
                        # Auditor approved or overrode - map back to our categories
                        type_to_category = {"plan": "build", "log": "debug", "decision": "decision",
                                          "analysis": "build", "report": "build", "script": "build"}
                        final_category = type_to_category.get(final_type, best_category)

                        print(f"    [AUDITOR_APPROVED] {final_category} (confidence: {final_confidence:.2f}) - {audit_reason}")
                        self._extract_entries(file_path, content, final_category, status=status,
                                            metadata={"auditor_approved": True,
                                                    "original_confidence": best_confidence,
                                                    "final_confidence": final_confidence,
                                                    "audit_reason": audit_reason})
                    else:
                        # Auditor flagged for manual review
                        self.unsorted_entries.append((file_path, best_confidence, scores, status))
                        print(f"    [AUDITOR_FLAGGED] Manual review required - {audit_reason}")
                else:
                    # No auditor available - fall back to manual review
                    self.unsorted_entries.append((file_path, best_confidence, scores, status))
                    print(f"    [UNSORTED] No auditor available, manual review required")

    def _is_schema_or_spec_file(self, file_path: Path, content: str) -> bool:
        """
        Detect schema, specification, or reference documentation files.

        These are permanent reference materials that should go to ARCHITECTURE_DECISIONS,
        not BUILD_HISTORY.
        """
        # Check filename
        filename_lower = file_path.name.lower()
        if any(keyword in filename_lower for keyword in ['schema', 'spec', 'specification', 'reference']):
            return True

        # Check content structure (schema files have specific patterns)
        schema_indicators = [
            r'##\s+(Core\s+)?Fields',
            r'\*\*Type\*\*:',
            r'\*\*Purpose\*\*:',
            r'\*\*Default\*\*:',
            r'##\s+Schema',
            r'##\s+Structure',
            r'##\s+API\s+Reference',
            r'##\s+Configuration\s+Reference',
        ]

        indicator_count = sum(1 for pattern in schema_indicators
                            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE))

        # File is a schema/spec if it has filename match OR >=2 content indicators
        return indicator_count >= 2

    def _is_reference_documentation(self, file_path: Path, content: str) -> bool:
        """
        Detect permanent reference documentation (tutorials, guides, quickstarts).

        These are permanent reference materials that should go to ARCHITECTURE_DECISIONS,
        not BUILD_HISTORY.
        """
        # Check filename
        filename_lower = file_path.name.lower()
        if any(keyword in filename_lower for keyword in [
            'quickstart', 'quick_start', 'guide', 'tutorial',
            'readme', 'getting_started', 'how_to', 'user_guide'
        ]):
            return True

        # Check content header (first 500 chars)
        header = content[:500].lower() if len(content) >= 500 else content.lower()
        header_indicators = [
            '# quickstart',
            '# getting started',
            '# tutorial',
            '# user guide',
            'step-by-step',
            'before you begin',
            '## pre-flight checklist',
        ]

        if any(pattern in header for pattern in header_indicators):
            return True

        return False

    def _is_strategic_content(self, content: str) -> bool:
        """
        Detect if content contains strategic/architectural discussions that shouldn't
        be silently dumped into BUILD_HISTORY.

        Returns True for:
        - Market research / business analysis
        - Architectural decisions / trade-offs
        - Strategic planning / roadmap discussions
        - Technology evaluation / comparisons
        - Design patterns / system architecture
        """
        strategic_indicators = [
            # Market/Business Strategy
            r'\b(market\s+research|TAM|total\s+addressable\s+market|business\s+model|revenue\s+model)\b',
            r'\b(competitive\s+analysis|competitor|market\s+opportunity|market\s+size)\b',
            r'\b(go-to-market|GTM|pricing\s+strategy|monetization)\b',

            # Architectural/Design
            r'\b(architecture\s+decision|design\s+pattern|system\s+design|architectural\s+trade-?off)\b',
            r'\b(scalability|performance\s+analysis|load\s+testing\s+strategy)\b',
            r'\b(microservices|monolith|service-oriented|event-driven)\b',

            # Technology Evaluation
            r'\b(technology\s+evaluation|framework\s+comparison|library\s+comparison)\b',
            r'\b(pros\s+and\s+cons|trade-?offs|alternatives\s+considered)\b',
            r'\b(evaluation\s+criteria|selection\s+criteria|decision\s+matrix)\b',

            # Strategic Planning
            r'\b(roadmap|strategic\s+plan|long-?term\s+plan|vision)\b',
            r'\b(risk\s+analysis|risk\s+assessment|mitigation\s+strategy)\b',
            r'\b(technical\s+debt|refactoring\s+strategy|migration\s+plan)\b',

            # Templates / Frameworks (reusable strategic tools)
            r'##\s+(template|framework|checklist|guidelines)',
            r'\{[a-z_]+\}',  # Template placeholders like {product_name}
        ]

        # Count how many strategic indicators are present
        indicator_count = sum(1 for pattern in strategic_indicators
                            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE))

        # Content is strategic if it has >= 3 indicators
        # OR if it's explicitly a template/framework (placeholder pattern)
        has_template_placeholders = bool(re.search(r'\{[a-z_]+\}', content))

        return indicator_count >= 3 or has_template_placeholders

    def _route_by_status(self, file_path: Path, content: str, status: str,
                         category: str, confidence: float, scores: Dict[str, float]) -> bool:
        """Route content based on inferred status. Returns True if routed, False if fallback needed."""

        if status == "IMPLEMENTED":
            # Implemented features → BUILD_HISTORY
            self._extract_entries(file_path, content, "build", status=status,
                                metadata={"implementation_status": "✅ Implemented"})
            return True

        elif status == "REJECTED" or status == "REJECTED_OBSOLETE":
            # Rejected plans → ARCHITECTURE_DECISIONS with rejection context
            self._extract_entries(file_path, content, "decision", status=status,
                                metadata={"decision_status": "❌ Rejected", "permanent": False})
            return True

        elif status == "PENDING_ACTIVE":
            # Check if already in FUTURE_PLAN
            print(f"    [SKIP] Active task already in FUTURE_PLAN")
            return True  # Skip consolidation

        elif status == "REFERENCE":
            # Research/reference → ARCHITECTURE_DECISIONS (permanent)
            self._extract_entries(file_path, content, "decision", status=status,
                                metadata={"reference": True, "permanent": True})
            return True

        elif status == "STALE" or status == "STALE_IMPLEMENTATION":
            # Stale content → Manual review with warning
            self.unsorted_entries.append((file_path, confidence, scores, status))
            print(f"    [UNSORTED] STALE content (age >180 days), manual review required")
            return True

        # UNKNOWN status → use confidence-based fallback
        return False

    def _calculate_confidence(self, file_path: Path, content: str, category: str) -> float:
        """Calculate confidence score for a category."""
        score = 0.0
        patterns = CLASSIFICATION_PATTERNS[category]

        # Filename pattern match (35%)
        for pattern in patterns["filename_patterns"]:
            if re.search(pattern, str(file_path.name), re.IGNORECASE):
                score += 0.35
                break

        # Content pattern matches (50% max, 0.125 per match up to 4 matches)
        pattern_matches = 0
        for pattern in patterns["content_patterns"]:
            if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                pattern_matches += 1
        score += min(0.50, pattern_matches * 0.125)

        # Keyword density (30% max - increased weight)
        keyword_count = 0
        words = content.lower().split()
        total_words = max(len(words), 1)

        for keyword in patterns["keywords"]:
            keyword_count += words.count(keyword.lower())

        # More generous keyword scoring
        keyword_density = keyword_count / total_words
        score += min(0.30, keyword_density * 30)

        # Timestamp extraction bonus (10%)
        if self._extract_timestamp(file_path, content):
            score += 0.10

        return min(1.0, score)

    def _extract_timestamp(self, file_path: Path, content: str) -> Optional[datetime]:
        """
        Extract timestamp with 4-tier fallback and validation against file mtime.

        Handles cases where content dates are typos (e.g., 2024 instead of 2025).
        If extracted timestamp is >180 days older than file mtime, uses mtime instead.
        """

        # Get file mtime first for validation
        file_mtime = None
        try:
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        except Exception:
            pass

        # Priority 1: Git commit date (MOST RELIABLE - actual file creation/modification date)
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", str(file_path)],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                dt = datetime.fromisoformat(result.stdout.strip().replace('+00:00', ''))
                # Normalize to naive datetime
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt
        except Exception:
            pass

        # Priority 2: Content patterns (fallback if not in git)
        content_timestamp = None
        content_patterns = [
            r"\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})",
            r"Date:\s*(\d{4}-\d{2}-\d{2})",
            r"Created:\s*(\d{4}-\d{2}-\d{2})",
            r"Timestamp:\s*(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2})",
        ]

        for pattern in content_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1)
                    if 'T' in date_str or ' ' in date_str:
                        dt = datetime.fromisoformat(date_str.replace(' ', 'T'))
                    else:
                        dt = datetime.fromisoformat(f"{date_str}T00:00:00")
                    # Normalize to naive datetime
                    if dt.tzinfo is not None:
                        dt = dt.replace(tzinfo=None)
                    content_timestamp = dt
                    break
                except ValueError:
                    continue

        # Validate content timestamp against file mtime
        # If content date is >180 days older than file mtime, it's likely a typo
        if content_timestamp and file_mtime:
            age_difference = (file_mtime - content_timestamp).days
            if age_difference > 180:
                # Content date is suspiciously old compared to file - use file mtime instead
                return file_mtime
            else:
                return content_timestamp
        elif content_timestamp:
            return content_timestamp

        # Priority 3: Filename patterns
        filename_patterns = [
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{8})",  # YYYYMMDD
        ]

        for pattern in filename_patterns:
            match = re.search(pattern, file_path.name)
            if match:
                try:
                    date_str = match.group(1)
                    if len(date_str) == 8:
                        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    filename_timestamp = datetime.fromisoformat(f"{date_str}T00:00:00")

                    # Validate against file mtime
                    if file_mtime:
                        age_difference = (file_mtime - filename_timestamp).days
                        if age_difference > 180:
                            return file_mtime
                    return filename_timestamp
                except ValueError:
                    continue

        # Priority 4: File mtime
        if file_mtime:
            return file_mtime

        return datetime.now()

    def _extract_entries(self, file_path: Path, content: str, category: str,
                         status: str = "UNKNOWN", metadata: Optional[Dict[str, any]] = None):
        """Extract entries from file based on category with status-aware metadata."""
        timestamp = self._extract_timestamp(file_path, content)

        # Merge provided metadata with extracted metadata
        base_metadata = metadata or {}

        # Simple extraction: treat whole file as one entry for now
        # In a more sophisticated version, we'd parse sections

        if category == "build":
            entry_id = f"BUILD-{self.build_counter:03d}"
            self.build_counter += 1

            # Extract build-specific metadata
            build_metadata = self._extract_build_metadata(content)
            build_metadata.update(base_metadata)  # Merge with status metadata

            entry = DocumentEntry(
                entry_id=entry_id,
                timestamp=timestamp,
                title=self._extract_title(file_path, content),
                content=self._extract_summary(content),
                category="build",
                confidence=self._calculate_confidence(file_path, content, "build"),
                source_file=str(file_path.relative_to(self.project_dir)),
                metadata=build_metadata  # Use merged metadata
            )
            self.build_entries.append(entry)

            # Log to database
            if not self.dry_run:
                self.logger.log(
                    run_id=self.run_id,
                    action="consolidate",
                    src=str(file_path.relative_to(self.project_dir)),
                    dest="docs/BUILD_HISTORY.md",
                    reason=f"BUILD entry: {entry_id} - {status}"
                )

        elif category == "debug":
            entry_id = f"DBG-{self.debug_counter:03d}"
            self.debug_counter += 1

            # Extract debug-specific metadata
            debug_metadata = self._extract_debug_metadata(content)
            debug_metadata.update(base_metadata)  # Merge with status metadata

            entry = DocumentEntry(
                entry_id=entry_id,
                timestamp=timestamp,
                title=self._extract_title(file_path, content),
                content=self._extract_summary(content),
                category="debug",
                confidence=self._calculate_confidence(file_path, content, "debug"),
                source_file=str(file_path.relative_to(self.project_dir)),
                metadata=debug_metadata  # Use merged metadata
            )
            self.debug_entries.append(entry)

            # Log to database
            if not self.dry_run:
                self.logger.log(
                    run_id=self.run_id,
                    action="consolidate",
                    src=str(file_path.relative_to(self.project_dir)),
                    dest="docs/DEBUG_LOG.md",
                    reason=f"DEBUG entry: {entry_id} - {status}"
                )

        elif category == "decision":
            entry_id = f"DEC-{self.decision_counter:03d}"
            self.decision_counter += 1

            # Extract decision-specific metadata
            decision_metadata = self._extract_decision_metadata(content)
            decision_metadata.update(base_metadata)  # Merge with status metadata

            entry = DocumentEntry(
                entry_id=entry_id,
                timestamp=timestamp,
                title=self._extract_title(file_path, content),
                content=self._extract_summary(content),
                category="decision",
                confidence=self._calculate_confidence(file_path, content, "decision"),
                source_file=str(file_path.relative_to(self.project_dir)),
                metadata=decision_metadata  # Use merged metadata
            )
            self.decision_entries.append(entry)

            # Log to database
            if not self.dry_run:
                self.logger.log(
                    run_id=self.run_id,
                    action="consolidate",
                    src=str(file_path.relative_to(self.project_dir)),
                    dest="docs/ARCHITECTURE_DECISIONS.md",
                    reason=f"DECISION entry: {entry_id} - {status}"
                )

    def _extract_title(self, file_path: Path, content: str) -> str:
        """Extract title from file."""
        # Try to find first heading
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Fallback to filename
        return file_path.stem.replace("_", " ").replace("-", " ").title()

    def _extract_summary(self, content: str, max_length: int = 500) -> str:
        """Extract summary from content."""
        # Remove markdown headers
        lines = content.split('\n')
        clean_lines = []

        for line in lines:
            # Skip headers
            if line.startswith('#'):
                continue
            # Skip empty lines
            if not line.strip():
                continue
            clean_lines.append(line.strip())

        summary = ' '.join(clean_lines)

        if len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary

    def _extract_build_metadata(self, content: str) -> Dict[str, any]:
        """Extract metadata for BUILD_HISTORY entries."""
        metadata = {}

        # Extract phase ID
        match = re.search(r"Phase ID:\s*([^\n]+)", content, re.IGNORECASE)
        if match:
            metadata["phase_id"] = match.group(1).strip()

        # Extract files changed
        files_pattern = r"Files? Changed:?\s*\n((?:[-*]\s+`.+`.*\n?)+)"
        match = re.search(files_pattern, content, re.MULTILINE | re.IGNORECASE)
        if match:
            files_text = match.group(1)
            files = re.findall(r"[-*]\s+`([^`]+)`", files_text)
            metadata["files_changed"] = files

        return metadata

    def _extract_debug_metadata(self, content: str) -> Dict[str, any]:
        """Extract metadata for DEBUG_LOG entries."""
        metadata = {}

        # Extract root cause
        match = re.search(r"Root Cause:?\s*\n(.+?)(?:\n\n|\n#|$)", content, re.DOTALL | re.IGNORECASE)
        if match:
            metadata["root_cause"] = match.group(1).strip()

        # Extract solution
        match = re.search(r"Solution:?\s*\n(.+?)(?:\n\n|\n#|$)", content, re.DOTALL | re.IGNORECASE)
        if match:
            metadata["solution"] = match.group(1).strip()

        # Detect severity
        if re.search(r"\bCRITICAL\b|\bSEVERE\b", content, re.IGNORECASE):
            metadata["severity"] = "CRITICAL"
        elif re.search(r"\bHIGH\b|\bMAJOR\b", content, re.IGNORECASE):
            metadata["severity"] = "HIGH"
        else:
            metadata["severity"] = "MEDIUM"

        return metadata

    def _extract_decision_metadata(self, content: str) -> Dict[str, any]:
        """Extract metadata for ARCHITECTURE_DECISIONS entries."""
        metadata = {}

        # Extract rationale
        match = re.search(r"Rationale:?\s*\n(.+?)(?:\n\n|\n#|$)", content, re.DOTALL | re.IGNORECASE)
        if match:
            metadata["rationale"] = match.group(1).strip()

        # Extract options
        match = re.search(r"Options Considered:?\s*\n((?:[-*\d.]\s+.+\n?)+)", content, re.MULTILINE | re.IGNORECASE)
        if match:
            options_text = match.group(1)
            options = re.findall(r"[-*\d.]\s+(.+)", options_text)
            metadata["options_considered"] = options

        return metadata

    def _normalize_timestamp_for_sort(self, timestamp: datetime) -> datetime:
        """Normalize timestamp to naive datetime for safe comparison."""
        if timestamp is None:
            return datetime.min
        if timestamp.tzinfo is not None:
            return timestamp.replace(tzinfo=None)
        return timestamp

    def _generate_documentation_files(self):
        """Generate final documentation files."""
        print("\n[3] Generating documentation files...")

        # Sort entries by timestamp (most recent first)
        # Normalize timestamps to prevent offset-naive/offset-aware comparison errors
        self.build_entries.sort(key=lambda e: self._normalize_timestamp_for_sort(e.timestamp), reverse=True)
        self.debug_entries.sort(key=lambda e: self._normalize_timestamp_for_sort(e.timestamp), reverse=True)
        self.decision_entries.sort(key=lambda e: self._normalize_timestamp_for_sort(e.timestamp), reverse=True)

        # Generate BUILD_HISTORY.md
        self._generate_build_history()

        # Generate DEBUG_LOG.md
        self._generate_debug_log()

        # Generate ARCHITECTURE_DECISIONS.md
        self._generate_architecture_decisions()

    def _generate_build_history(self):
        """Generate BUILD_HISTORY.md file."""
        print(f"  Generating {self.build_history_file.name}...")

        content = "# Build History - Implementation Log\n\n"
        content += "<!-- META\n"
        content += f"Last_Updated: {datetime.now().isoformat()}Z\n"
        content += f"Total_Builds: {len(self.build_entries)}\n"
        content += "Format_Version: 2.0\n"
        content += "Auto_Generated: True\n"
        content += "Sources: CONSOLIDATED files, archive/\n"
        content += "-->\n\n"

        # INDEX
        content += "## INDEX (Chronological - Most Recent First)\n\n"
        content += "| Timestamp | BUILD-ID | Phase | Summary | Files Changed |\n"
        content += "|-----------|----------|-------|---------|---------------|\n"

        for entry in self.build_entries[:50]:  # Limit index to 50 most recent
            ts = entry.timestamp.strftime("%Y-%m-%d")
            phase = entry.metadata.get("phase_id", "N/A")
            summary = entry.title[:50]
            files_count = len(entry.metadata.get("files_changed", []))
            files_info = f"{files_count} files" if files_count > 0 else ""

            content += f"| {ts} | {entry.entry_id} | {phase} | {summary} | {files_info} |\n"

        content += "\n## BUILDS (Reverse Chronological)\n\n"

        # Entries
        for entry in self.build_entries:
            content += entry.to_markdown()

        if not self.dry_run:
            self.build_history_file.write_text(content, encoding="utf-8")
            print(f"    [OK] {len(self.build_entries)} entries written")
        else:
            print(f"    [DRY-RUN] Would write {len(self.build_entries)} entries")

    def _generate_debug_log(self):
        """Generate DEBUG_LOG.md file."""
        print(f"  Generating {self.debug_log_file.name}...")

        content = "# Debug Log - Problem Solving History\n\n"
        content += "<!-- META\n"
        content += f"Last_Updated: {datetime.now().isoformat()}Z\n"
        content += f"Total_Issues: {len(self.debug_entries)}\n"
        content += "Format_Version: 2.0\n"
        content += "Auto_Generated: True\n"
        content += "Sources: CONSOLIDATED_DEBUG, archive/\n"
        content += "-->\n\n"

        # INDEX
        content += "## INDEX (Chronological - Most Recent First)\n\n"
        content += "| Timestamp | DBG-ID | Severity | Summary | Status |\n"
        content += "|-----------|--------|----------|---------|--------|\n"

        for entry in self.debug_entries[:50]:
            ts = entry.timestamp.strftime("%Y-%m-%d")
            severity = entry.metadata.get("severity", "MEDIUM")
            summary = entry.title[:50]
            status = entry.metadata.get("status", "✅ Resolved")

            content += f"| {ts} | {entry.entry_id} | {severity} | {summary} | {status} |\n"

        content += "\n## DEBUG ENTRIES (Reverse Chronological)\n\n"

        # Entries
        for entry in self.debug_entries:
            content += entry.to_markdown()

        if not self.dry_run:
            self.debug_log_file.write_text(content, encoding="utf-8")
            print(f"    [OK] {len(self.debug_entries)} entries written")
        else:
            print(f"    [DRY-RUN] Would write {len(self.debug_entries)} entries")

    def _generate_architecture_decisions(self):
        """Generate ARCHITECTURE_DECISIONS.md file."""
        print(f"  Generating {self.architecture_decisions_file.name}...")

        content = "# Architecture Decisions - Design Rationale\n\n"
        content += "<!-- META\n"
        content += f"Last_Updated: {datetime.now().isoformat()}Z\n"
        content += f"Total_Decisions: {len(self.decision_entries)}\n"
        content += "Format_Version: 2.0\n"
        content += "Auto_Generated: True\n"
        content += "Sources: CONSOLIDATED_STRATEGY, CONSOLIDATED_REFERENCE, archive/\n"
        content += "-->\n\n"

        # INDEX
        content += "## INDEX (Chronological - Most Recent First)\n\n"
        content += "| Timestamp | DEC-ID | Decision | Status | Impact |\n"
        content += "|-----------|--------|----------|--------|--------|\n"

        for entry in self.decision_entries[:50]:
            ts = entry.timestamp.strftime("%Y-%m-%d")
            decision = entry.title[:50]
            status = entry.metadata.get("status", "✅ Implemented")
            impact = entry.metadata.get("impact", "")[:30]

            content += f"| {ts} | {entry.entry_id} | {decision} | {status} | {impact} |\n"

        content += "\n## DECISIONS (Reverse Chronological)\n\n"

        # Entries
        for entry in self.decision_entries:
            content += entry.to_markdown()

        if not self.dry_run:
            self.architecture_decisions_file.write_text(content, encoding="utf-8")
            print(f"    [OK] {len(self.decision_entries)} entries written")
        else:
            print(f"    [DRY-RUN] Would write {len(self.decision_entries)} entries")

    def _generate_unsorted_review(self):
        """Generate UNSORTED_REVIEW.md for manual review."""
        if not self.unsorted_entries:
            print("\n[4] No unsorted entries")
            return

        print(f"\n[4] Generating {self.unsorted_file.name}...")

        content = "# Unsorted Content - Manual Review Required\n\n"
        content += "Files below confidence threshold (0.6) need manual classification.\n\n"
        content += f"**Total Items**: {len(self.unsorted_entries)}\n"
        content += f"**Generated**: {datetime.now().isoformat()}\n\n"
        content += "**Status Codes**:\n"
        content += "- IMPLEMENTED: Appears to be completed (check if in BUILD_HISTORY)\n"
        content += "- REJECTED: Explicitly rejected decision\n"
        content += "- REFERENCE: Research/reference material (permanent value)\n"
        content += "- STALE: Old content (>180 days, not implemented)\n"
        content += "- UNKNOWN: Could not determine status\n\n"

        for entry in self.unsorted_entries:
            # Handle both old (3-tuple) and new (4-tuple with status) formats
            if len(entry) == 4:
                file_path, confidence, scores, status = entry
            else:
                file_path, confidence, scores = entry
                status = "UNKNOWN"

            rel_path = file_path.relative_to(self.project_dir)

            content += f"## `{rel_path}`\n\n"
            content += f"**Status**: {status}\n"
            content += f"**Best Match**: {max(scores, key=scores.get)} ({confidence:.2f})\n"
            content += f"**Confidence Scores**:\n"
            content += f"- BUILD_HISTORY: {scores['build']:.2f}\n"
            content += f"- DEBUG_LOG: {scores['debug']:.2f}\n"
            content += f"- ARCHITECTURE_DECISIONS: {scores['decision']:.2f}\n\n"

            # Status-based recommendation
            if status == "IMPLEMENTED":
                content += f"**Recommendation**: Move to BUILD_HISTORY (implementation confirmed)\n"
            elif status == "REJECTED":
                content += f"**Recommendation**: Move to ARCHITECTURE_DECISIONS (rejected plan)\n"
            elif status == "REFERENCE":
                content += f"**Recommendation**: Move to ARCHITECTURE_DECISIONS (permanent reference)\n"
            elif status == "STALE":
                content += f"**Recommendation**: Review for relevance - may be obsolete (age >180 days)\n"
            else:
                content += f"**Recommendation**: Manual review required\n"
            content += "\n"

            # Preview content
            try:
                file_content = file_path.read_text(encoding="utf-8")
                preview = file_content[:500]
                content += f"**Preview**:\n```\n{preview}...\n```\n\n"
            except Exception:
                content += "**Preview**: _Could not read file_\n\n"

            content += "**Action Required**: [ ] Move to appropriate category\n\n"
            content += "---\n\n"

        if not self.dry_run:
            self.unsorted_file.write_text(content, encoding="utf-8")
            print(f"    [OK] {len(self.unsorted_entries)} items need review")
        else:
            print(f"    [DRY-RUN] Would write {len(self.unsorted_entries)} items for review")

    def _cleanup_old_files(self):
        """Delete old CONSOLIDATED files."""
        print("\n[5] Cleaning up old CONSOLIDATED files...")

        old_files = [
            "CONSOLIDATED_DEBUG.md",
            "CONSOLIDATED_BUILD.md",
            "CONSOLIDATED_STRATEGY.md",
            "CONSOLIDATED_REFERENCE.md",
            "CONSOLIDATED_MISC.md",
            "CONSOLIDATED_CORRESPONDENCE.md",
        ]

        for filename in old_files:
            file_path = self.docs_dir / filename
            if file_path.exists():
                if not self.dry_run:
                    file_path.unlink()
                    print(f"  Deleted {filename}")
                else:
                    print(f"  [DRY-RUN] Would delete {filename}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Consolidate documentation into AI-optimized format"
    )
    parser.add_argument(
        "--project",
        default="autopack-framework",
        help="Project to consolidate (default: autopack-framework)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files"
    )

    args = parser.parse_args()

    # Determine project directory
    if args.project == "autopack-framework":
        project_dir = REPO_ROOT
    else:
        project_dir = REPO_ROOT / ".autonomous_runs" / args.project

    if not project_dir.exists():
        print(f"[ERROR] Project directory not found: {project_dir}")
        return 1

    # Run consolidation
    consolidator = DocumentConsolidator(project_dir, dry_run=args.dry_run)
    consolidator.consolidate()

    # Cleanup
    if consolidator.classification_auditor:
        consolidator.classification_auditor.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
