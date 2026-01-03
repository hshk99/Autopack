#!/usr/bin/env python3
"""
Documentation link drift checker.

Validates that file references in core navigation documents actually exist.
Prevents "two truths" problem where docs reference non-existent files.

Scope:
- Default (BUILD-158): README.md, docs/INDEX.md, docs/BUILD_HISTORY.md
- Deep mode (BUILD-159): docs/**/*.md (excludes archive/** by default)

Features:
- Layered heuristic matching for broken links (same-dir → basename → fuzzy)
- Confidence scoring for suggested fixes (high/medium/low)
- Fix plan generation (JSON + Markdown)
- Fenced code block skipping to reduce false positives

Exit codes:
- 0: All links valid
- 1: Broken links found
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from urllib.parse import unquote

# File reference patterns
# Matches: [text](path/to/file.md) and `path/to/file.txt`
MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')  # [text](link)
BACKTICK_PATH_PATTERN = re.compile(r'`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`')  # `file.ext`
DIRECT_PATH_PATTERN = re.compile(r'(?:^|[ \t])([a-zA-Z0-9_\-./]+\.md)(?:[ \t:]|$)')  # file.md
FENCED_CODE_BLOCK_PATTERN = re.compile(r'^```.*?^```', re.MULTILINE | re.DOTALL)  # ```...```

# Confidence thresholds
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.85


def normalize_path(path: str) -> str:
    """
    Normalize a path for matching.

    - Convert backslashes to forward slashes
    - Remove leading './'
    - Decode URL encoding (%20 → space)
    - Strip trailing whitespace
    """
    normalized = path.replace('\\', '/')
    normalized = normalized.lstrip('./')
    normalized = unquote(normalized)
    return normalized.strip()


def strip_fenced_code_blocks(content: str) -> str:
    """
    Remove fenced code blocks from markdown content to reduce false positives.

    Replaces code blocks with empty lines to preserve line numbers.
    """
    def replace_with_newlines(match):
        # Count lines in matched block
        block = match.group(0)
        line_count = block.count('\n')
        return '\n' * line_count

    return FENCED_CODE_BLOCK_PATTERN.sub(replace_with_newlines, content)


def extract_file_references(content: str, file_path: Path, skip_code_blocks: bool = True) -> Dict[str, List[Dict]]:
    """
    Extract potential file references from markdown content.

    Args:
        content: Markdown file content
        file_path: Path to the markdown file (for relative resolution)
        skip_code_blocks: If True, skip fenced code blocks

    Returns:
        Dict mapping reference paths to list of occurrence details (link_text, line_number, source_link)
    """
    # Strip code blocks if requested
    if skip_code_blocks:
        content = strip_fenced_code_blocks(content)

    refs = {}
    lines = content.split('\n')

    # Extract markdown links: [text](path)
    for line_num, line in enumerate(lines, start=1):
        for match in MARKDOWN_LINK_PATTERN.finditer(line):
            link_text = match.group(1)
            link = match.group(2)

            # Skip URLs (http://, https://, mailto:)
            if link.startswith(('http://', 'https://', 'mailto:')):
                continue

            # Skip anchor-only links
            if link.startswith('#'):
                continue

            # Remove anchor fragments
            original_link = link
            if '#' in link:
                link = link.split('#')[0]

            if link:
                normalized = normalize_path(link)
                if normalized not in refs:
                    refs[normalized] = []
                refs[normalized].append({
                    'link_text': link_text,
                    'line_number': line_num,
                    'source_link': f'[{link_text}]({original_link})',
                    'original_target': link
                })

    # Extract backtick-wrapped paths: `path/to/file.ext`
    for line_num, line in enumerate(lines, start=1):
        for match in BACKTICK_PATH_PATTERN.finditer(line):
            path_ref = match.group(1)
            # Only include if it looks like a file path (has slash or dots)
            if '/' in path_ref or path_ref.count('.') >= 2:
                normalized = normalize_path(path_ref)
                if normalized not in refs:
                    refs[normalized] = []
                refs[normalized].append({
                    'link_text': path_ref,
                    'line_number': line_num,
                    'source_link': f'`{path_ref}`',
                    'original_target': path_ref
                })

    return refs


def find_closest_matches(
    broken_target: str,
    source_file: Path,
    repo_root: Path,
    search_paths: List[Path]
) -> List[Tuple[str, float]]:
    """
    Layered heuristic matching for broken links.

    Step 0: Exact match after normalization
    Step 1: Same-directory preference (basename in same dir or siblings)
    Step 2: Repo-wide basename match (unique = high confidence, multiple = medium)
    Step 3: Fuzzy matching using difflib (threshold ≥0.85)

    Args:
        broken_target: The broken link target
        source_file: Source markdown file doing the referencing
        repo_root: Repository root
        search_paths: List of all markdown files in scope

    Returns:
        List of (suggested_path, confidence_score) tuples, sorted by score descending
    """
    suggestions = []
    normalized_target = normalize_path(broken_target)
    target_basename = Path(normalized_target).name
    source_dir = source_file.parent

    # Step 0: Exact match after normalization (shouldn't happen, but defensive)
    abs_path = repo_root / normalized_target
    if abs_path.exists():
        return [(normalized_target, 1.0)]

    rel_path = source_dir / normalized_target
    if rel_path.exists():
        try:
            rel_to_repo = rel_path.relative_to(repo_root)
            return [(str(rel_to_repo), 1.0)]
        except ValueError:
            pass

    # Step 1: Same-directory preference
    same_dir_candidates = []
    for candidate in search_paths:
        if candidate.name == target_basename:
            # Check if in same directory or sibling directory
            if candidate.parent == source_dir or candidate.parent.parent == source_dir.parent:
                try:
                    rel_path = candidate.relative_to(repo_root)
                    same_dir_candidates.append(str(rel_path))
                except ValueError:
                    pass

    if same_dir_candidates:
        # High confidence for same-directory matches
        for candidate in same_dir_candidates:
            suggestions.append((candidate, 0.95))

    # Step 2: Repo-wide basename match
    basename_matches = []
    for candidate in search_paths:
        if candidate.name == target_basename:
            try:
                rel_path = candidate.relative_to(repo_root)
                rel_str = str(rel_path)
                # Skip if already added in Step 1
                if rel_str not in same_dir_candidates:
                    basename_matches.append(rel_str)
            except ValueError:
                pass

    if basename_matches:
        # High confidence if unique, medium if multiple
        confidence = 0.92 if len(basename_matches) == 1 else 0.87
        for match in basename_matches:
            suggestions.append((match, confidence))

    # Step 3: Fuzzy matching with difflib
    all_paths = []
    for candidate in search_paths:
        try:
            rel_path = candidate.relative_to(repo_root)
            all_paths.append(str(rel_path))
        except ValueError:
            pass

    # Use difflib to find close matches
    close_matches = difflib.get_close_matches(
        normalized_target,
        all_paths,
        n=5,
        cutoff=CONFIDENCE_MEDIUM
    )

    for match in close_matches:
        # Skip if already added in previous steps
        if not any(match == s[0] for s in suggestions):
            # Calculate actual similarity score
            similarity = difflib.SequenceMatcher(None, normalized_target, match).ratio()
            suggestions.append((match, similarity))

    # Sort by confidence descending, deduplicate
    seen = set()
    unique_suggestions = []
    for path, score in sorted(suggestions, key=lambda x: x[1], reverse=True):
        if path not in seen:
            seen.add(path)
            unique_suggestions.append((path, score))

    return unique_suggestions[:5]  # Return top 5


def validate_references(
    refs: Dict[str, List[Dict]],
    source_file: Path,
    repo_root: Path,
    search_paths: Optional[List[Path]] = None
) -> Tuple[List[Dict], List[Dict]]:
    """
    Validate that referenced paths exist and suggest fixes for broken ones.

    Args:
        refs: Dict mapping normalized paths to occurrence details
        source_file: Source markdown file doing the referencing
        repo_root: Repository root directory
        search_paths: List of all markdown files in scope (for suggestions)

    Returns:
        (valid_refs, broken_refs_with_suggestions) tuple
    """
    valid = []
    broken = []

    for ref, occurrences in refs.items():
        # Try as absolute path from repo root
        abs_path = repo_root / ref
        if abs_path.exists():
            try:
                resolved = abs_path.relative_to(repo_root)
                for occ in occurrences:
                    valid.append({
                        'target': ref,
                        'resolved_path': str(resolved),
                        **occ
                    })
                continue
            except ValueError:
                # Path exists but is outside repo - treat as broken
                pass

        # Try as relative path from source file's directory
        rel_path = source_file.parent / ref
        if rel_path.exists():
            try:
                resolved = rel_path.relative_to(repo_root)
                for occ in occurrences:
                    valid.append({
                        'target': ref,
                        'resolved_path': str(resolved),
                        **occ
                    })
                continue
            except ValueError:
                # Path exists but is outside repo - treat as broken
                pass

        # Path not found - find suggestions
        suggestions = []
        suggested_fix = None
        confidence = "low"
        fix_type = "manual_review"

        if search_paths:
            matches = find_closest_matches(ref, source_file, repo_root, search_paths)
            if matches:
                suggestions = [{"path": path, "score": round(score, 3)} for path, score in matches]
                suggested_fix = matches[0][0]
                top_score = matches[0][1]

                # Determine confidence level
                if top_score >= CONFIDENCE_HIGH:
                    confidence = "high"
                    fix_type = "update_reference"
                elif top_score >= CONFIDENCE_MEDIUM:
                    confidence = "medium"
                    fix_type = "update_reference"
                else:
                    confidence = "low"
                    fix_type = "manual_review"

        # Add broken reference with suggestions for each occurrence
        for occ in occurrences:
            broken.append({
                'source_file': str(source_file.relative_to(repo_root)),
                'line_number': occ['line_number'],
                'link_text': occ['link_text'],
                'source_link': occ['source_link'],
                'broken_target': occ['original_target'],
                'normalized_target': ref,
                'reason': 'missing_file',
                'suggested_fix': suggested_fix,
                'suggestions': suggestions,
                'confidence': confidence,
                'fix_type': fix_type
            })

    return valid, broken


def check_file(
    file_path: Path,
    repo_root: Path,
    search_paths: Optional[List[Path]] = None,
    skip_code_blocks: bool = True
) -> Dict:
    """
    Check a single file for broken links.

    Args:
        file_path: Path to markdown file
        repo_root: Repository root
        search_paths: List of all markdown files in scope (for suggestions)
        skip_code_blocks: If True, skip fenced code blocks

    Returns:
        Dict with check results
    """
    if not file_path.exists():
        return {
            "file": str(file_path.relative_to(repo_root)),
            "exists": False,
            "refs_total": 0,
            "refs_valid": [],
            "refs_broken": [],
        }

    content = file_path.read_text(encoding='utf-8')
    refs = extract_file_references(content, file_path, skip_code_blocks=skip_code_blocks)
    valid, broken = validate_references(refs, file_path, repo_root, search_paths=search_paths)

    return {
        "file": str(file_path.relative_to(repo_root)),
        "exists": True,
        "refs_total": len(refs),
        "refs_valid": valid,
        "refs_broken": broken,
    }


def discover_markdown_files(
    repo_root: Path,
    include_globs: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None
) -> List[Path]:
    """
    Discover markdown files based on glob patterns.

    Args:
        repo_root: Repository root
        include_globs: Glob patterns to include (e.g., ["docs/**/*.md"])
        exclude_globs: Glob patterns to exclude (e.g., ["archive/**"])

    Returns:
        List of markdown file paths
    """
    if not include_globs:
        include_globs = ["docs/**/*.md"]

    if not exclude_globs:
        exclude_globs = ["archive/**"]

    found_files = set()

    # Gather all files matching include patterns
    for pattern in include_globs:
        for file_path in repo_root.glob(pattern):
            if file_path.is_file():
                found_files.add(file_path)

    # Remove files matching exclude patterns
    for pattern in exclude_globs:
        for file_path in list(found_files):
            if file_path.match(pattern):
                found_files.discard(file_path)

    return sorted(found_files)


def export_fix_plan_json(broken_links: List[Dict], output_path: Path) -> None:
    """
    Export fix plan as JSON.

    Args:
        broken_links: List of broken link dictionaries
        output_path: Path to output JSON file
    """
    summary = {
        "total_broken": len(broken_links),
        "auto_fixable": sum(1 for b in broken_links if b['confidence'] in ['high', 'medium']),
        "manual_review": sum(1 for b in broken_links if b['confidence'] == 'low'),
        "by_confidence": {
            "high": sum(1 for b in broken_links if b['confidence'] == 'high'),
            "medium": sum(1 for b in broken_links if b['confidence'] == 'medium'),
            "low": sum(1 for b in broken_links if b['confidence'] == 'low'),
        }
    }

    fix_plan = {
        "generated_at": datetime.now().isoformat(),
        "broken_links": broken_links,
        "summary": summary
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fix_plan, indent=2), encoding='utf-8')


def export_fix_plan_markdown(broken_links: List[Dict], output_path: Path) -> None:
    """
    Export fix plan as human-readable Markdown.

    Args:
        broken_links: List of broken link dictionaries
        output_path: Path to output Markdown file
    """
    lines = [
        "# Documentation Link Fix Plan",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Broken Links**: {len(broken_links)}",
        "",
        "## Summary by Confidence",
        "",
        f"- **High** (≥{CONFIDENCE_HIGH:.0%}): {sum(1 for b in broken_links if b['confidence'] == 'high')} links (auto-fixable)",
        f"- **Medium** ({CONFIDENCE_MEDIUM:.0%}-{CONFIDENCE_HIGH:.0%}): {sum(1 for b in broken_links if b['confidence'] == 'medium')} links (auto-fixable with --apply-medium)",
        f"- **Low** (<{CONFIDENCE_MEDIUM:.0%}): {sum(1 for b in broken_links if b['confidence'] == 'low')} links (manual review required)",
        "",
        "## Broken Links",
        ""
    ]

    # Group by source file
    by_file = {}
    for broken in broken_links:
        source = broken['source_file']
        if source not in by_file:
            by_file[source] = []
        by_file[source].append(broken)

    for source_file in sorted(by_file.keys()):
        links = by_file[source_file]
        lines.append(f"### {source_file}")
        lines.append("")
        lines.append("| Line | Broken Target | Suggested Fix | Confidence | Score |")
        lines.append("|------|---------------|---------------|------------|-------|")

        for broken in sorted(links, key=lambda x: x['line_number']):
            line_num = broken['line_number']
            broken_target = broken['broken_target']
            suggested = broken['suggested_fix'] or '(none)'
            confidence = broken['confidence']
            score = broken['suggestions'][0]['score'] if broken['suggestions'] else 'N/A'

            lines.append(f"| {line_num} | `{broken_target}` | `{suggested}` | {confidence} | {score} |")

        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(
        description="Check documentation links for drift (broken file references)"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root directory (default: autodetect)"
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Deep mode: scan docs/**/*.md instead of just navigation files"
    )
    parser.add_argument(
        "--include-glob",
        action="append",
        dest="include_globs",
        help="Additional glob patterns to include (can be repeated)"
    )
    parser.add_argument(
        "--exclude-glob",
        action="append",
        dest="exclude_globs",
        help="Glob patterns to exclude (can be repeated)"
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        help="Export fix plan as JSON (default: archive/diagnostics/doc_link_fix_plan.json in deep mode)"
    )
    parser.add_argument(
        "--export-md",
        type=Path,
        help="Export fix plan as Markdown (default: archive/diagnostics/doc_link_fix_plan.md in deep mode)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show valid links in addition to broken ones"
    )
    parser.add_argument(
        "--no-skip-code-blocks",
        action="store_true",
        help="Don't skip fenced code blocks (may increase false positives)"
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    skip_code_blocks = not args.no_skip_code_blocks

    # Determine files to check
    if args.deep or args.include_globs:
        # Deep mode or custom globs
        include_globs = args.include_globs or ["docs/**/*.md"]
        exclude_globs = args.exclude_globs or ["archive/**"]

        # Always include core navigation files
        files_to_check = [
            repo_root / "README.md",
            repo_root / "docs" / "INDEX.md",
            repo_root / "docs" / "BUILD_HISTORY.md",
        ]

        # Add discovered files
        discovered = discover_markdown_files(repo_root, include_globs, exclude_globs)
        for file_path in discovered:
            if file_path not in files_to_check:
                files_to_check.append(file_path)

        mode = "deep" if args.deep else "custom"
    else:
        # Default mode: core navigation files only (BUILD-158 scope)
        files_to_check = [
            repo_root / "README.md",
            repo_root / "docs" / "INDEX.md",
            repo_root / "docs" / "BUILD_HISTORY.md",
        ]
        mode = "default"

    # Build search paths for suggestions (all markdown files in repo)
    all_markdown_files = list(repo_root.glob("**/*.md"))

    print("=" * 70)
    print("DOCUMENTATION LINK DRIFT CHECK")
    print("=" * 70)
    print(f"Repository root: {repo_root}")
    print(f"Mode: {mode}")
    print(f"Files to check: {len(files_to_check)}")
    print(f"Search space for suggestions: {len(all_markdown_files)} markdown files")
    print("=" * 70)
    print()

    total_refs = 0
    total_broken = 0
    all_broken_links = []
    results = []

    for file_path in files_to_check:
        result = check_file(file_path, repo_root, search_paths=all_markdown_files, skip_code_blocks=skip_code_blocks)
        results.append(result)

        if not result["exists"]:
            print(f"❌ {result['file']}: FILE NOT FOUND")
            continue

        total_refs += result["refs_total"]
        total_broken += len(result["refs_broken"])
        all_broken_links.extend(result["refs_broken"])

        if result["refs_broken"]:
            print(f"❌ {result['file']}: {len(result['refs_broken'])} broken link(s)")
            if args.verbose:
                for broken in result["refs_broken"]:
                    suggested = broken['suggested_fix'] or '(none)'
                    print(f"   Line {broken['line_number']}: {broken['broken_target']} → {suggested} ({broken['confidence']})")
        else:
            print(f"✅ {result['file']}: all {result['refs_total']} link(s) valid")

        if args.verbose and result["refs_valid"]:
            print(f"   Valid refs ({len(result['refs_valid'])}):")
            for valid_ref in sorted(result["refs_valid"], key=lambda x: x['target'])[:10]:  # Show first 10
                print(f"     • {valid_ref['target']}")
            if len(result["refs_valid"]) > 10:
                print(f"     ... and {len(result['refs_valid']) - 10} more")

        print()

    # Export fix plan if requested or in deep mode
    if all_broken_links and (args.export_json or args.export_md or mode == "deep"):
        json_path = args.export_json if args.export_json else (repo_root / "archive" / "diagnostics" / "doc_link_fix_plan.json")
        md_path = args.export_md if args.export_md else (repo_root / "archive" / "diagnostics" / "doc_link_fix_plan.md")

        # Ensure paths are absolute
        if not json_path.is_absolute():
            json_path = repo_root / json_path
        if not md_path.is_absolute():
            md_path = repo_root / md_path

        if args.export_json or mode == "deep":
            export_fix_plan_json(all_broken_links, json_path)
            try:
                rel_path = json_path.relative_to(repo_root)
                print(f"📄 Fix plan exported to: {rel_path}")
            except ValueError:
                print(f"📄 Fix plan exported to: {json_path}")

        if args.export_md or mode == "deep":
            export_fix_plan_markdown(all_broken_links, md_path)
            try:
                rel_path = md_path.relative_to(repo_root)
                print(f"📄 Fix plan exported to: {rel_path}")
            except ValueError:
                print(f"📄 Fix plan exported to: {md_path}")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files checked: {len(results)}")
    print(f"Total references found: {total_refs}")
    print(f"Broken references: {total_broken}")

    if total_broken > 0:
        high_conf = sum(1 for b in all_broken_links if b['confidence'] == 'high')
        med_conf = sum(1 for b in all_broken_links if b['confidence'] == 'medium')
        low_conf = sum(1 for b in all_broken_links if b['confidence'] == 'low')

        print()
        print(f"  Auto-fixable (high confidence): {high_conf}")
        print(f"  Auto-fixable (medium confidence): {med_conf}")
        print(f"  Manual review required: {low_conf}")
        print()
        print("❌ FAILED: Broken links detected")
        print("   Run with --deep to generate fix plan, or use scripts/fix_doc_links.py to apply fixes")
        return 1
    else:
        print()
        print("✅ PASSED: All documentation links are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
