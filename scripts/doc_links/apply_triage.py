#!/usr/bin/env python3
"""
Apply doc link triage decisions from config/doc_link_triage_overrides.yaml.

This script reads the triage overrides configuration and applies the specified
actions to broken links found in archive/diagnostics/doc_link_fix_plan.json.

Actions:
- ignore: Add to doc_link_check_ignore.yaml
- fix: Apply the specified fix by updating the source file
- create_stub: Create redirect stub file at broken_target pointing to stub_target
- manual: Report but take no action (requires human review)

Modes (BUILD-166):
- nav: Navigation docs only (README.md, INDEX.md, BUILD_HISTORY.md) - STRICT
  * NEVER ignores missing_file reason (nav docs must have valid links)
  * Blocks on any missing_file violations
  * Safe for CI enforcement
- deep: All docs/**/*.md - PERMISSIVE
  * Can ignore missing_file with explicit rules
  * Report-only mode for comprehensive cleanup
  * Used for weekly scans

Usage:
    # Nav mode (strict, safe for CI)
    python scripts/doc_links/apply_triage.py --mode nav [--dry-run] [--apply-fixes]

    # Deep mode (permissive, for cleanup)
    python scripts/doc_links/apply_triage.py --mode deep [--dry-run] [--apply-fixes]

Options:
    --mode: nav|deep - Nav (strict, nav docs only) or deep (permissive, all docs)
    --dry-run: Show what would be done without making changes
    --apply-fixes: Actually apply fixes (without this, only ignores are added)
    --report: Generate rule hit count report
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch
from pathlib import PurePosixPath

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not found. Install with: pip install pyyaml")
    sys.exit(1)

# Repository root
REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths
DOC_LINK_PLAN = REPO_ROOT / "archive" / "diagnostics" / "doc_link_fix_plan.json"
TRIAGE_OVERRIDES = REPO_ROOT / "config" / "doc_link_triage_overrides.yaml"
IGNORE_CONFIG = REPO_ROOT / "config" / "doc_link_check_ignore.yaml"

# Navigation docs (nav mode - strict)
NAV_DOCS = {
    "README.md",
    "docs/INDEX.md",
    "docs/BUILD_HISTORY.md",
}

def _norm_relpath(p: str) -> str:
    """Normalize repo-relative paths for consistent matching across OSes."""
    return str(p).replace("\\", "/").strip()

def _configure_utf8_stdio() -> None:
    """
    Make CLI output resilient on Windows terminals that default to legacy encodings (e.g. cp1252).

    This script prints Unicode glyphs (e.g. "→"). Prefer UTF-8 with replacement.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class TriageApplicator:
    """Apply triage decisions to broken doc links."""

    def __init__(
        self,
        mode: str = "deep",
        dry_run: bool = False,
        apply_fixes: bool = False,
        generate_report: bool = False
    ):
        self.mode = mode
        self.dry_run = dry_run
        self.apply_fixes = apply_fixes
        self.generate_report = generate_report
        self.stats = {
            "total_broken": 0,
            "matched_ignore": 0,
            "matched_fix": 0,
            "matched_manual": 0,
            "matched_stub": 0,
            "unmatched": 0,
            "fixes_applied": 0,
            "ignores_added": 0,
            "stubs_created": 0,
            "nav_strict_violations": 0,  # Nav mode: missing_file violations blocked
        }
        self.rule_hits = {}  # Track how many times each rule matched
        self.nav_strict_violations = []  # Track blocked violations

    def load_doc_link_plan(self) -> List[Dict[str, Any]]:
        """Load broken links from doc_link_fix_plan.json, filtered by mode."""
        if not DOC_LINK_PLAN.exists():
            print(f"ERROR: Doc link plan not found: {DOC_LINK_PLAN}")
            sys.exit(1)

        with open(DOC_LINK_PLAN, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_links = data.get("broken_links", [])

        # Filter by mode
        if self.mode == "nav":
            # Nav mode: only navigation docs, and only *real markdown links*.
            # Deep scans can include backticks; nav-mode hygiene (CI policy) intentionally does not.
            filtered = [
                link for link in all_links
                if (
                    _norm_relpath(link.get("source_file", "")) in NAV_DOCS
                    and str(link.get("source_link", "")).lstrip().startswith("[")
                )
            ]
            print(f"[MODE] Nav mode: filtered {len(all_links)} → {len(filtered)} links (nav docs only)")
            return filtered
        else:
            # Deep mode: all docs
            return all_links

    def load_triage_overrides(self) -> List[Dict[str, Any]]:
        """Load triage overrides from YAML config."""
        if not TRIAGE_OVERRIDES.exists():
            print(f"ERROR: Triage overrides not found: {TRIAGE_OVERRIDES}")
            sys.exit(1)

        with open(TRIAGE_OVERRIDES, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or []

    def load_ignore_config(self) -> Dict[str, Any]:
        """Load existing ignore configuration."""
        if not IGNORE_CONFIG.exists():
            return {"version": "1.0", "ignore_patterns": []}

        with open(IGNORE_CONFIG, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"version": "1.0", "ignore_patterns": []}

    def save_ignore_config(self, config: Dict[str, Any]) -> None:
        """Save updated ignore configuration."""
        if self.dry_run:
            print(f"[DRY-RUN] Would save ignore config: {IGNORE_CONFIG}")
            return

        with open(IGNORE_CONFIG, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"[SAVED] Updated ignore config: {IGNORE_CONFIG}")

    def match_override(
        self,
        broken_link: Dict[str, Any],
        override: Dict[str, Any]
    ) -> bool:
        """
        Check if a broken link matches a triage override.

        Args:
            broken_link: Broken link entry from doc_link_fix_plan.json
            override: Triage override rule

        Returns:
            True if the link matches the override rule
        """
        # Match source file pattern
        source_file = _norm_relpath(broken_link.get("source_file", ""))
        pattern = override.get("pattern", "**/*.md")

        # Use Path.match for glob pattern matching
        # Special case: **/*.md should match both root and nested .md files
        if pattern == "**/*.md":
            # Match any .md file at any depth including root
            if not source_file.endswith(".md"):
                return False
        elif not PurePosixPath(source_file).match(pattern):
            return False

        # Match broken target (exact or glob)
        broken_target = broken_link.get("broken_target", "")

        if "broken_target" in override:
            if override["broken_target"] != broken_target:
                return False

        if "broken_target_glob" in override:
            if not fnmatch.fnmatch(broken_target, override["broken_target_glob"]):
                return False

        # Match reason filter (if specified)
        if "reason_filter" in override:
            reason = broken_link.get("reason", "")
            if reason != override["reason_filter"]:
                return False

        return True

    def apply_ignore(
        self,
        broken_link: Dict[str, Any],
        override: Dict[str, Any],
        ignore_config: Dict[str, Any]
    ) -> None:
        """Add broken link to ignore configuration."""
        source_file = _norm_relpath(broken_link.get("source_file", ""))
        broken_target = broken_link.get("broken_target", "")
        reason = broken_link.get("reason", "")
        note = override.get("note", "Triaged as ignore")

        # Nav-strict check: NEVER ignore missing_file in nav docs
        if self.mode == "nav" and reason == "missing_file" and source_file in NAV_DOCS:
            self.nav_strict_violations.append({
                "source_file": source_file,
                "broken_target": broken_target,
                "line_number": broken_link.get("line_number"),
                "reason": reason,
                "attempted_action": "ignore"
            })
            self.stats["nav_strict_violations"] += 1
            print(f"[NAV-STRICT VIOLATION] Cannot ignore missing_file in {source_file}:{broken_link.get('line_number')}")
            print(f"                       Target: {broken_target}")
            print(f"                       Nav docs must have valid links (BUILD-166)")
            return

        # Check if already in ignore list
        ignore_patterns = ignore_config.setdefault("ignore_patterns", [])

        for pattern in ignore_patterns:
            if (_norm_relpath(pattern.get("file", "")) == source_file and
                pattern.get("target") == broken_target):
                print(f"[SKIP] Already ignored: {source_file} → {broken_target}")
                return

        # Add to ignore list
        ignore_patterns.append({
            "file": source_file,
            "target": broken_target,
            "reason": note
        })

        self.stats["ignores_added"] += 1
        print(f"[IGNORE] {source_file}:{broken_link.get('line_number')} → {broken_target}")
        print(f"         Note: {note}")

    def apply_fix(
        self,
        broken_link: Dict[str, Any],
        override: Dict[str, Any]
    ) -> None:
        """Apply a fix to a broken link in the source file."""
        source_file = REPO_ROOT / broken_link.get("source_file", "")
        broken_target = broken_link.get("broken_target", "")
        fix_target = override.get("fix_target")
        line_number = broken_link.get("line_number")

        if not fix_target:
            print(f"[ERROR] No fix_target specified for {broken_target}")
            return

        if not source_file.exists():
            print(f"[ERROR] Source file not found: {source_file}")
            return

        # Read source file
        with open(source_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if line_number < 1 or line_number > len(lines):
            print(f"[ERROR] Invalid line number {line_number} in {source_file}")
            return

        # Get the line (1-indexed to 0-indexed)
        line_idx = line_number - 1
        original_line = lines[line_idx]

        # Replace broken_target with fix_target in the line
        # Use word boundaries to avoid partial matches
        fixed_line = original_line.replace(broken_target, fix_target)

        if fixed_line == original_line:
            print(f"[WARN] Fix did not change line {line_number} in {source_file}")
            print(f"       Looking for: {broken_target}")
            print(f"       Line: {original_line.strip()}")
            return

        if self.dry_run or not self.apply_fixes:
            print(f"[DRY-RUN] Would fix: {source_file}:{line_number}")
            print(f"          - {original_line.rstrip()}")
            print(f"          + {fixed_line.rstrip()}")
            return

        # Apply the fix
        lines[line_idx] = fixed_line

        with open(source_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        self.stats["fixes_applied"] += 1
        print(f"[FIXED] {source_file}:{line_number}")
        print(f"        {broken_target} → {fix_target}")

    def create_stub(
        self,
        broken_link: Dict[str, Any],
        override: Dict[str, Any]
    ) -> None:
        """Create a redirect stub file for a moved document."""
        broken_target = broken_link.get("broken_target", "")
        stub_target = override.get("stub_target")
        stub_title = override.get("stub_title", broken_target.replace(".md", "").replace("_", " ").title())

        if not stub_target:
            print(f"[ERROR] No stub_target specified for {broken_target}")
            return

        # Construct stub file path (relative to repo root)
        stub_path = REPO_ROOT / broken_target

        if stub_path.exists():
            print(f"[SKIP] Stub already exists: {stub_path}")
            return

        # Create stub content
        stub_content = f"""# {stub_title}

**Status**: Moved

This document has been moved. See [{stub_title}]({stub_target}).

---

*This is a redirect stub created by doc link triage (BUILD-166).*
"""

        if self.dry_run or not self.apply_fixes:
            print(f"[DRY-RUN] Would create stub: {stub_path}")
            print(f"          Target: {stub_target}")
            print(f"          Content preview:")
            for line in stub_content.split("\n")[:5]:
                print(f"          | {line}")
            return

        # Create parent directory if needed
        stub_path.parent.mkdir(parents=True, exist_ok=True)

        # Write stub file
        with open(stub_path, "w", encoding="utf-8") as f:
            f.write(stub_content)

        self.stats.setdefault("stubs_created", 0)
        self.stats["stubs_created"] += 1
        print(f"[STUB CREATED] {stub_path}")
        print(f"               Points to: {stub_target}")

    def run(self) -> None:
        """Execute triage application."""
        print("=" * 70)
        print("DOC LINK TRIAGE APPLICATOR")
        print("=" * 70)
        print(f"Dry-run: {self.dry_run}")
        print(f"Apply fixes: {self.apply_fixes}")
        print()

        # Load data
        broken_links = self.load_doc_link_plan()
        triage_overrides = self.load_triage_overrides()
        ignore_config = self.load_ignore_config()

        self.stats["total_broken"] = len(broken_links)

        print(f"Loaded {len(broken_links)} broken links")
        print(f"Loaded {len(triage_overrides)} triage override rules")
        print()

        # Process each broken link
        for broken_link in broken_links:
            matched = False

            for override in triage_overrides:
                if self.match_override(broken_link, override):
                    action = override.get("action", "manual")

                    # Track rule hits
                    rule_id = override.get("id", override.get("pattern", "unknown"))
                    self.rule_hits[rule_id] = self.rule_hits.get(rule_id, 0) + 1

                    if action == "ignore":
                        self.apply_ignore(broken_link, override, ignore_config)
                        self.stats["matched_ignore"] += 1
                    elif action == "fix":
                        self.apply_fix(broken_link, override)
                        self.stats["matched_fix"] += 1
                    elif action == "create_stub":
                        self.create_stub(broken_link, override)
                        self.stats["matched_stub"] += 1
                    elif action == "manual":
                        print(f"[MANUAL] {broken_link.get('source_file')}:{broken_link.get('line_number')} → {broken_link.get('broken_target')}")
                        print(f"         Note: {override.get('note', 'Requires manual review')}")
                        self.stats["matched_manual"] += 1
                    else:
                        print(f"[WARN] Unknown action '{action}' for {broken_link.get('broken_target')}")

                    matched = True
                    break  # Only apply first matching override

            if not matched:
                self.stats["unmatched"] += 1

        # Save updated ignore config
        if self.stats["ignores_added"] > 0:
            self.save_ignore_config(ignore_config)

        # Print summary
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Mode:                   {self.mode}")
        print(f"Total broken links:     {self.stats['total_broken']}")
        print(f"Matched (ignore):       {self.stats['matched_ignore']}")
        print(f"Matched (fix):          {self.stats['matched_fix']}")
        print(f"Matched (stub):         {self.stats['matched_stub']}")
        print(f"Matched (manual):       {self.stats['matched_manual']}")
        print(f"Unmatched:              {self.stats['unmatched']}")
        print()
        print(f"Ignores added:          {self.stats['ignores_added']}")
        print(f"Fixes applied:          {self.stats['fixes_applied']}")
        print(f"Stubs created:          {self.stats['stubs_created']}")

        # Nav-strict violations
        if self.mode == "nav" and self.stats["nav_strict_violations"] > 0:
            print()
            print(f"Nav-strict violations:  {self.stats['nav_strict_violations']}")
            print()
            print("BLOCKED VIOLATIONS (nav-strict):")
            for violation in self.nav_strict_violations:
                print(f"  - {violation['source_file']}:{violation['line_number']} → {violation['broken_target']}")

        # Rule hit count report
        if self.generate_report and self.rule_hits:
            print()
            print("=" * 70)
            print("RULE HIT COUNTS")
            print("=" * 70)
            sorted_rules = sorted(self.rule_hits.items(), key=lambda x: x[1], reverse=True)
            for rule_id, count in sorted_rules:
                print(f"  {rule_id:50} {count:5} hits")

        print()

        if self.dry_run:
            print("DRY-RUN MODE - No changes were made")
        elif not self.apply_fixes and self.stats["matched_fix"] > 0:
            print(f"{self.stats['matched_fix']} fixes matched but not applied (use --apply-fixes)")

        # Nav-strict mode enforcement
        if self.mode == "nav" and self.stats["nav_strict_violations"] > 0:
            print()
            print("ERROR: Nav-strict violations detected.")
            print("Navigation docs must have valid links (BUILD-166).")
            print("Fix the violations above or change to deep mode.")


def main():
    _configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Apply doc link triage decisions"
    )
    parser.add_argument(
        "--mode",
        choices=["nav", "deep"],
        default="deep",
        help="Nav (strict, navigation docs only) or deep (permissive, all docs)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--apply-fixes",
        action="store_true",
        help="Actually apply fixes (default: only add ignores)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate rule hit count report"
    )

    args = parser.parse_args()

    applicator = TriageApplicator(
        mode=args.mode,
        dry_run=args.dry_run,
        apply_fixes=args.apply_fixes,
        generate_report=args.report
    )

    try:
        applicator.run()

        # Exit with non-zero if nav-strict violations found
        if args.mode == "nav" and applicator.stats["nav_strict_violations"] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Triage application cancelled")
        sys.exit(130)


if __name__ == "__main__":
    main()
