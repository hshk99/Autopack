#!/usr/bin/env python3
"""
Documentation link drift checker.

Validates that file references in core navigation documents actually exist.
Prevents "two truths" problem where docs reference non-existent files.

Scope:
- Default (BUILD-158): README.md, docs/INDEX.md, docs/BUILD_HISTORY.md
  * Nav mode (default): Only markdown links [text](path), backticks ignored
- Deep mode (BUILD-159): docs/**/*.md (excludes archive/** by default)
  * Can include backticks with --include-backticks flag

Features:
- Layered heuristic matching for broken links (same-dir → basename → fuzzy)
- Confidence scoring for suggested fixes (high/medium/low)
- Fix plan generation (JSON + Markdown)
- Fenced code block skipping to reduce false positives
- Backtick filtering (BUILD-166): Nav mode ignores code-formatted paths by default

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
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from urllib.parse import unquote

# File reference patterns
# Matches: [text](path/to/file.md) and `path/to/file.txt` or `Makefile`
MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')  # [text](link)
BACKTICK_PATH_PATTERN = re.compile(r'`([a-zA-Z0-9_\-./]+(?:\.[a-zA-Z0-9]+)?)`')  # `file.ext` or `Makefile` (BUILD-166: extension optional)
DIRECT_PATH_PATTERN = re.compile(r'(?:^|[ \t])([a-zA-Z0-9_\-./]+\.md)(?:[ \t:]|$)')  # file.md
FENCED_CODE_BLOCK_PATTERN = re.compile(r'^```.*?^```', re.MULTILINE | re.DOTALL)  # ```...```

# Confidence thresholds
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.85


def load_ignore_config(repo_root: Path) -> Dict:
    """
    Load ignore configuration from config/doc_link_check_ignore.yaml.

    Returns:
        Ignore config dictionary, or empty dict if file not found
    """
    config_path = repo_root / "config" / "doc_link_check_ignore.yaml"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"⚠️  Failed to load ignore config: {e}", file=sys.stderr)
        return {}


def classify_link_target(target: str, repo_root: Path, ignore_config: Dict) -> str:
    """
    Classify a link target into categories for policy-driven handling.

    Categories:
    - 'runtime_endpoint': API endpoints, localhost URLs (exist at runtime)
    - 'external_url': HTTP/HTTPS external URLs
    - 'historical_ref': archive/superseded/* (informational only)
    - 'anchor_only': Fragment-only link (#section)
    - 'ignored': Matches pattern_ignores
    - 'missing_file': File reference that doesn't exist (default)

    Args:
        target: Link target to classify
        repo_root: Repository root
        ignore_config: Loaded ignore configuration

    Returns:
        Category string
    """
    normalized = normalize_path(target)

    # Check pattern ignores first (complete skip)
    pattern_ignores = ignore_config.get('pattern_ignores', [])
    for ignore_entry in pattern_ignores:
        pattern = ignore_entry.get('pattern', '')
        if pattern and pattern in normalized:
            return 'ignored'

    # Check for anchor-only links
    if normalized.startswith('#'):
        return 'anchor_only'

    # Check runtime endpoints
    runtime_endpoints = ignore_config.get('runtime_endpoints', [])
    for endpoint_entry in runtime_endpoints:
        pattern = endpoint_entry.get('pattern', '')
        if pattern and pattern in normalized:
            return 'runtime_endpoint'

    # Check external URLs
    if normalized.startswith('http://') or normalized.startswith('https://'):
        return 'external_url'

    # Check historical references
    historical_refs = ignore_config.get('historical_refs', [])
    for hist_entry in historical_refs:
        pattern = hist_entry.get('pattern', '')
        if pattern and pattern in normalized:
            return 'historical_ref'

    # Default to missing_file
    return 'missing_file'


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


def extract_file_references(content: str, file_path: Path, skip_code_blocks: bool = True, include_backticks: bool = False) -> Dict[str, List[Dict]]:
    """
    Extract potential file references from markdown content.

    Args:
        content: Markdown file content
        file_path: Path to the markdown file (for relative resolution)
        skip_code_blocks: If True, skip fenced code blocks
        include_backticks: If True, extract backtick-wrapped paths (default: False for nav mode)

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

    # Extract backtick-wrapped paths: `path/to/file.ext` (BUILD-166: optional)
    if include_backticks:
        # Known file extensions and filenames that should be treated as paths
        KNOWN_EXTENSIONS = {
            '.md', '.py', '.js', '.ts', '.jsx', '.tsx', '.json', '.yaml', '.yml',
            '.toml', '.txt', '.sh', '.bash', '.sql', '.env', '.gitignore',
            '.dockerignore', '.csv', '.log', '.xml', '.html', '.css', '.scss'
        }
        KNOWN_FILENAMES = {
            'Makefile', 'Dockerfile', 'README', 'LICENSE', 'CHANGELOG',
            'TODO', 'AUTHORS', 'CONTRIBUTING', 'Pipfile', 'Procfile'
        }

        for line_num, line in enumerate(lines, start=1):
            for match in BACKTICK_PATH_PATTERN.finditer(line):
                path_ref = match.group(1)

                # Heuristics for identifying file paths (BUILD-166: improved for deep mode)
                # 1. Contains path separator (/)
                # 2. Has known file extension
                # 3. Is a known filename (e.g., Makefile, README)
                # 4. Has multiple dots (e.g., config.yaml.example)
                is_path = (
                    '/' in path_ref or
                    any(path_ref.endswith(ext) for ext in KNOWN_EXTENSIONS) or
                    any(path_ref.startswith(name) for name in KNOWN_FILENAMES) or
                    path_ref.count('.') >= 2
                )

                if is_path:
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
    search_paths: Optional[List[Path]] = None,
    ignore_config: Optional[Dict] = None
) -> Tuple[List[Dict], List[Dict]]:
    """
    Validate that referenced paths exist and suggest fixes for broken ones.

    Args:
        refs: Dict mapping normalized paths to occurrence details
        source_file: Source markdown file doing the referencing
        repo_root: Repository root directory
        search_paths: List of all markdown files in scope (for suggestions)
        ignore_config: Ignore configuration for classification

    Returns:
        (valid_refs, broken_refs_with_suggestions) tuple
    """
    valid = []
    broken = []
    ignore_config = ignore_config or {}

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

        # Path not found - classify the broken link
        category = classify_link_target(ref, repo_root, ignore_config)

        # Skip if ignored
        if category == 'ignored':
            continue

        # Find suggestions for missing_file category
        suggestions = []
        suggested_fix = None
        confidence = "low"
        fix_type = "manual_review"

        if category == 'missing_file' and search_paths:
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
                'reason': category,
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
    skip_code_blocks: bool = True,
    include_backticks: bool = False,
    ignore_config: Optional[Dict] = None
) -> Dict:
    """
    Check a single file for broken links.

    Args:
        file_path: Path to markdown file
        repo_root: Repository root
        search_paths: List of all markdown files in scope (for suggestions)
        skip_code_blocks: If True, skip fenced code blocks
        ignore_config: Ignore configuration for classification

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
    refs = extract_file_references(content, file_path, skip_code_blocks=skip_code_blocks, include_backticks=include_backticks)
    valid, broken = validate_references(refs, file_path, repo_root, search_paths=search_paths, ignore_config=ignore_config)

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
    parser.add_argument(
        "--include-backticks",
        action="store_true",
        help="Include backtick-wrapped paths (default: false for nav mode, true for deep mode if specified)"
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    skip_code_blocks = not args.no_skip_code_blocks

    # BUILD-166: Deep mode defaults to include backticks for comprehensive coverage
    # Nav mode defaults to exclude backticks to reduce false positives
    if args.deep and not args.include_backticks:
        include_backticks = True
    else:
        include_backticks = args.include_backticks

    # Load ignore configuration
    ignore_config = load_ignore_config(repo_root)

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
    print(f"Backtick extraction: {'enabled' if include_backticks else 'disabled (nav mode)'}")
    print("=" * 70)
    print()

    total_refs = 0
    total_broken = 0
    all_broken_links = []
    results = []

    for file_path in files_to_check:
        result = check_file(file_path, repo_root, search_paths=all_markdown_files, skip_code_blocks=skip_code_blocks, include_backticks=include_backticks, ignore_config=ignore_config)
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
        # Category breakdown
        categories = {}
        for b in all_broken_links:
            cat = b['reason']
            categories[cat] = categories.get(cat, 0) + 1

        # Separate enforced vs informational categories
        ci_fail_categories = ignore_config.get('ci_enforcement', {}).get('fail_on', ['missing_file'])
        enforced_links = [b for b in all_broken_links if b['reason'] in ci_fail_categories]
        informational_links = [b for b in all_broken_links if b['reason'] not in ci_fail_categories]

        print()
        if enforced_links:
            print(f"❌ Enforced broken links (CI-blocking): {len(enforced_links)}")
            enforced_cats = {}
            for b in enforced_links:
                cat = b['reason']
                enforced_cats[cat] = enforced_cats.get(cat, 0) + 1
            for cat, count in sorted(enforced_cats.items(), key=lambda x: -x[1]):
                print(f"  {cat}: {count}")

        if informational_links:
            print()
            print(f"ℹ️  Informational references (report-only): {len(informational_links)}")
            info_cats = {}
            for b in informational_links:
                cat = b['reason']
                info_cats[cat] = info_cats.get(cat, 0) + 1
            for cat, count in sorted(info_cats.items(), key=lambda x: -x[1]):
                print(f"  {cat}: {count}")

        # Confidence breakdown (for missing_file category)
        missing_file_links = [b for b in all_broken_links if b['reason'] == 'missing_file']
        if missing_file_links:
            high_conf = sum(1 for b in missing_file_links if b['confidence'] == 'high')
            med_conf = sum(1 for b in missing_file_links if b['confidence'] == 'medium')
            low_conf = sum(1 for b in missing_file_links if b['confidence'] == 'low')

            print()
            print(f"Missing files auto-fix confidence:")
            print(f"  Auto-fixable (high confidence): {high_conf}")
            print(f"  Auto-fixable (medium confidence): {med_conf}")
            print(f"  Manual review required: {low_conf}")

        # CI enforcement check (only fail on missing_file)
        ci_failures = len(enforced_links)

        print()
        if ci_failures > 0:
            print(f"❌ FAILED: {ci_failures} broken link(s) in fail_on categories: {ci_fail_categories}")
            print("   Run with --deep to generate fix plan, or use scripts/fix_doc_links.py to apply fixes")
            return 1
        else:
            print(f"⚠️  WARNING: {total_broken} broken link(s) found, but not in fail_on categories")
            print("   These are informational only and don't fail CI")
            return 0
    else:
        print()
        print("✅ PASSED: All documentation links are valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
