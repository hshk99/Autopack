"""
Generate archive index JSON + derived Markdown.

This script scans archive roots and produces:
- archive/ARCHIVE_INDEX.json (canonical, schema-validated)
- archive/ARCHIVE_INDEX.md (derived, human-readable)

Design constraints:
- Deterministic: same inputs produce same outputs (sorted, no timestamps in content)
- Portable: no absolute paths, all paths are repo-relative
- Bounded: recent_files limited per root, not full enumeration
- Read-only: only writes to archive/ARCHIVE_INDEX.{json,md}

CI contract:
- exits 0 on success
- exits 1 on validation failure
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

# Bounded rollup limits
TOP_RECENT_FILES_PER_ROOT = 25
MAX_FILES_PER_BUCKET_SAMPLE = 10

# Archive root configurations
ARCHIVE_ROOTS_CONFIG = [
    {
        "id": "repo",
        "root_rel": "archive",
        "kind": "repo_archive",
        "provenance": {
            "tidy_reports_rel_glob": "archive/reports/storage/*.json",
            "tidy_activity_logs_rel_glob": ".autonomous_runs/_ci_artifacts/tidy_*.log",
        },
    },
    {
        "id": "file-organizer-app-v1",
        "root_rel": ".autonomous_runs/file-organizer-app-v1/archive",
        "kind": "project_archive",
        "provenance": {
            "tidy_reports_rel_glob": ".autonomous_runs/file-organizer-app-v1/archive/reports/*.json",
        },
    },
]

# Bucket descriptions for known archive subdirectories
BUCKET_DESCRIPTIONS = {
    "data": "Raw data files and databases",
    "data/databases": "SQLite and other database files",
    "diagnostics": "Diagnostic logs and debug outputs",
    "diagnostics/logs": "Log files from various runs",
    "experiments": "Experimental code and research",
    "exports": "Exported data and reports",
    "misc": "Miscellaneous archived files",
    "patches": "Code patches and diffs",
    "plans": "Planning documents and specs",
    "prompts": "LLM prompts and templates",
    "reports": "Generated reports",
    "reports/storage": "Storage optimizer reports",
    "research": "Research notes and analysis",
    "runs": "Telemetry and execution runs",
    "schemas": "JSON schemas and data models",
    "scripts": "Archived scripts",
    "superseded": "Superseded/deprecated files",
    "tasks": "Task definitions and configs",
    "unsorted": "Files pending categorization",
}


class RecentFile(TypedDict):
    path_rel: str
    bytes: int
    mtime_utc: str
    kind: str | None
    summary_hint: str | None


class BucketStat(TypedDict):
    bucket_rel: str
    file_count: int
    total_bytes: int
    description: str | None


class Provenance(TypedDict, total=False):
    tidy_reports_rel_glob: str
    tidy_activity_logs_rel_glob: str


class ArchiveRoot(TypedDict):
    id: str
    root_rel: str
    kind: str
    bucket_stats: list[BucketStat]
    recent_files: list[RecentFile]
    provenance: Provenance | None


class ArchiveIndex(TypedDict):
    schema_version: int
    generated_at_utc: str
    generator_version: str
    archive_roots: list[ArchiveRoot]


def _infer_file_kind(path: Path, bucket_rel: str) -> str | None:
    """Infer file kind based on extension and bucket."""
    ext = path.suffix.lower()

    # Extension-based inference
    kind_map = {
        ".md": "markdown",
        ".json": "json",
        ".py": "python",
        ".sql": "sql",
        ".log": "log",
        ".txt": "text",
        ".db": "database",
        ".zip": "archive",
        ".csv": "csv",
        ".yaml": "yaml",
        ".yml": "yaml",
    }

    if ext in kind_map:
        return kind_map[ext]

    # Bucket-based inference
    if "runs" in bucket_rel or "telemetry" in bucket_rel:
        return "run_artifact"
    if "reports" in bucket_rel:
        return "report"
    if "prompts" in bucket_rel:
        return "prompt"

    return None


def _generate_summary_hint(path: Path, kind: str | None) -> str | None:
    """Generate a brief deterministic hint about file contents."""
    name = path.name

    # Pattern-based hints
    if name.startswith("CONSOLIDATED"):
        return "Consolidated documentation"
    if name.startswith("storage_scan_"):
        return "Storage optimizer scan results"
    if "telemetry" in name.lower():
        return "Telemetry collection data"
    if name.endswith(".schema.json"):
        return "JSON schema definition"
    if name.startswith("phase_"):
        return "Phase execution data"

    return None


def _get_bucket_description(bucket_rel: str, root_rel: str) -> str | None:
    """Get description for a bucket based on its relative path."""
    # Strip root prefix to get bucket-only path
    if bucket_rel.startswith(root_rel):
        bucket_only = bucket_rel[len(root_rel) :].lstrip("/\\")
    else:
        bucket_only = bucket_rel

    return BUCKET_DESCRIPTIONS.get(bucket_only)


def _scan_bucket(bucket_path: Path, repo_root: Path) -> tuple[int, int, list[tuple[Path, float]]]:
    """
    Scan a bucket directory and return (file_count, total_bytes, [(path, mtime), ...]).

    Returns files sorted by mtime descending (most recent first).
    """
    file_count = 0
    total_bytes = 0
    files_with_mtime: list[tuple[Path, float]] = []

    if not bucket_path.exists():
        return 0, 0, []

    try:
        for item in bucket_path.rglob("*"):
            if item.is_file():
                try:
                    stat = item.stat()
                    file_count += 1
                    total_bytes += stat.st_size
                    files_with_mtime.append((item, stat.st_mtime))
                except OSError:
                    # Skip files we can't stat (permissions, etc.)
                    pass
    except OSError:
        pass

    # Sort by mtime descending
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)

    return file_count, total_bytes, files_with_mtime


def _scan_archive_root(root_config: dict, repo_root: Path) -> ArchiveRoot | None:
    """Scan an archive root and return its statistics."""
    root_rel = root_config["root_rel"]
    root_path = repo_root / root_rel

    if not root_path.exists():
        return None

    # Find all bucket directories (immediate subdirectories)
    bucket_stats: list[BucketStat] = []
    all_recent_files: list[tuple[Path, float]] = []

    try:
        subdirs = sorted([d for d in root_path.iterdir() if d.is_dir()])
    except OSError:
        subdirs = []

    for subdir in subdirs:
        # Skip hidden directories
        if subdir.name.startswith("."):
            continue

        bucket_rel = str(subdir.relative_to(repo_root)).replace("\\", "/")
        file_count, total_bytes, files_with_mtime = _scan_bucket(subdir, repo_root)

        if file_count > 0:
            bucket_stats.append(
                {
                    "bucket_rel": bucket_rel,
                    "file_count": file_count,
                    "total_bytes": total_bytes,
                    "description": _get_bucket_description(bucket_rel, root_rel),
                }
            )
            all_recent_files.extend(files_with_mtime)

    # Also scan files directly in root (not in subdirs)
    try:
        root_files = [(f, f.stat().st_mtime) for f in root_path.iterdir() if f.is_file()]
        all_recent_files.extend(root_files)
    except OSError:
        pass

    # Sort all files by mtime and take top N
    all_recent_files.sort(key=lambda x: x[1], reverse=True)
    top_files = all_recent_files[:TOP_RECENT_FILES_PER_ROOT]

    recent_files: list[RecentFile] = []
    for file_path, mtime in top_files:
        try:
            stat = file_path.stat()
            path_rel = str(file_path.relative_to(repo_root)).replace("\\", "/")
            bucket_rel = str(file_path.parent.relative_to(repo_root)).replace("\\", "/")
            kind = _infer_file_kind(file_path, bucket_rel)

            recent_files.append(
                {
                    "path_rel": path_rel,
                    "bytes": stat.st_size,
                    "mtime_utc": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                    "kind": kind,
                    "summary_hint": _generate_summary_hint(file_path, kind),
                }
            )
        except OSError:
            pass

    # Sort bucket_stats by bucket_rel for determinism
    bucket_stats.sort(key=lambda x: x["bucket_rel"])

    return {
        "id": root_config["id"],
        "root_rel": root_rel,
        "kind": root_config["kind"],
        "bucket_stats": bucket_stats,
        "recent_files": recent_files,
        "provenance": root_config.get("provenance"),
    }


def _generate_markdown(index: ArchiveIndex, repo_root: Path) -> str:
    """Generate Markdown rendering from archive index."""
    lines = [
        "# Archive Index",
        "",
        f"**Generated**: {index['generated_at_utc']}",
        f"**Generator**: {index['generator_version']}",
        "",
        "> This file is auto-generated from `archive/ARCHIVE_INDEX.json`.",
        "> Do not edit manually - regenerate with `python scripts/archive/generate_archive_index.py`",
        "",
        "---",
        "",
    ]

    for root in index["archive_roots"]:
        lines.append(f"## {root['id']} (`{root['root_rel']}/`)")
        lines.append("")
        lines.append(f"**Kind**: {root['kind']}")
        lines.append("")

        # Bucket stats table
        if root["bucket_stats"]:
            lines.append("### Buckets")
            lines.append("")
            lines.append("| Bucket | Files | Size | Description |")
            lines.append("|--------|-------|------|-------------|")

            for bucket in root["bucket_stats"]:
                size_kb = bucket["total_bytes"] / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                desc = bucket["description"] or "-"
                bucket_name = bucket["bucket_rel"].split("/")[-1]
                lines.append(f"| `{bucket_name}/` | {bucket['file_count']} | {size_str} | {desc} |")

            lines.append("")

        # Recent files
        if root["recent_files"]:
            lines.append(f"### Recent Files (top {len(root['recent_files'])})")
            lines.append("")

            for f in root["recent_files"][:10]:  # Show first 10 in MD
                name = f["path_rel"].split("/")[-1]
                size_kb = f["bytes"] / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                hint = f" - {f['summary_hint']}" if f.get("summary_hint") else ""
                lines.append(f"- `{name}` ({size_str}){hint}")

            if len(root["recent_files"]) > 10:
                lines.append(f"- ... and {len(root['recent_files']) - 10} more in JSON")

            lines.append("")

        # Provenance
        if root.get("provenance"):
            lines.append("### Provenance")
            lines.append("")
            prov = root["provenance"]
            if prov.get("tidy_reports_rel_glob"):
                lines.append(f"- Tidy reports: `{prov['tidy_reports_rel_glob']}`")
            if prov.get("tidy_activity_logs_rel_glob"):
                lines.append(f"- Activity logs: `{prov['tidy_activity_logs_rel_glob']}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("*Auto-generated by Autopack Archive Index Generator*")
    lines.append("")

    return "\n".join(lines)


def _validate_no_absolute_paths(index: ArchiveIndex) -> list[str]:
    """Validate that no absolute paths snuck into the index."""
    errors = []

    def check_path(path: str, context: str) -> None:
        # Check for Windows absolute paths (C:\, D:\, etc.)
        if len(path) >= 2 and path[1] == ":":
            errors.append(f"{context}: absolute Windows path detected: {path}")
        # Check for Unix absolute paths
        if path.startswith("/"):
            errors.append(f"{context}: absolute Unix path detected: {path}")

    for root in index["archive_roots"]:
        check_path(root["root_rel"], f"root {root['id']}")
        for bucket in root["bucket_stats"]:
            check_path(bucket["bucket_rel"], f"bucket in {root['id']}")
        for f in root["recent_files"]:
            check_path(f["path_rel"], f"file in {root['id']}")

    return errors


def generate_archive_index(repo_root: Path) -> tuple[ArchiveIndex, list[str]]:
    """
    Generate archive index for the repository.

    Returns (index, validation_errors).
    """
    archive_roots: list[ArchiveRoot] = []

    for root_config in ARCHIVE_ROOTS_CONFIG:
        root = _scan_archive_root(root_config, repo_root)
        if root is not None:
            archive_roots.append(root)

    index: ArchiveIndex = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "generator_version": "1.0.0",
        "archive_roots": archive_roots,
    }

    validation_errors = _validate_no_absolute_paths(index)

    return index, validation_errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent

    print("[*] Generating archive index...")

    index, errors = generate_archive_index(repo_root)

    if errors:
        print("[X] Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    # Write JSON
    json_path = repo_root / "archive" / "ARCHIVE_INDEX.json"
    json_content = json.dumps(index, indent=2, ensure_ascii=False)
    json_path.write_text(json_content, encoding="utf-8")
    print(f"[OK] Wrote {json_path.relative_to(repo_root)}")

    # Write Markdown
    md_path = repo_root / "archive" / "ARCHIVE_INDEX.md"
    md_content = _generate_markdown(index, repo_root)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"[OK] Wrote {md_path.relative_to(repo_root)}")

    # Summary
    total_buckets = sum(len(r["bucket_stats"]) for r in index["archive_roots"])
    total_recent = sum(len(r["recent_files"]) for r in index["archive_roots"])
    print(
        f"[*] Summary: {len(index['archive_roots'])} roots, {total_buckets} buckets, {total_recent} recent files"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
