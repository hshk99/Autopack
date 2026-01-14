#!/usr/bin/env python3
"""
Project Configuration Loader for Centralized Multi-Project Tidy System

Loads project-specific configuration from database or provides defaults.
"""

import os
import re
import psycopg2
import json
from pathlib import Path
from typing import Optional, Dict, Any


def detect_project_id(project_flag: Optional[str] = None, cwd: Optional[Path] = None) -> str:
    """
    Auto-detect project ID from context

    Args:
        project_flag: Explicit --project flag value
        cwd: Current working directory

    Returns:
        Project ID (e.g., "autopack", "file-organizer-app-v1")
    """
    if project_flag:
        return project_flag

    cwd = cwd or Path.cwd()
    cwd_str = str(cwd)

    # Check if we're in a subproject
    if ".autonomous_runs" in cwd_str:
        # Extract project name from path
        # .autonomous_runs/file-organizer-app-v1 → "file-organizer-app-v1"
        match = re.search(r"\.autonomous_runs[/\\]([^/\\]+)", cwd_str)
        if match:
            return match.group(1)

    # Default to autopack
    return "autopack"


def load_project_config(project_id: str) -> Dict[str, Any]:
    """
    Load project configuration from database

    Args:
        project_id: Project identifier

    Returns:
        Configuration dictionary

    Raises:
        ValueError: If project not found and no default available
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print(f"⚠️  DATABASE_URL not set, using default config for {project_id}")
        return get_default_config(project_id)

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT project_root, docs_dir, archive_dir,
                   sot_build_history, sot_debug_log, sot_architecture, sot_unsorted,
                   project_context, enable_database_logging, enable_research_workflow
            FROM tidy_project_config
            WHERE project_id = %s
        """,
            (project_id,),
        )

        row = cur.fetchone()
        if not row:
            conn.close()
            print(f"⚠️  No config found in DB for {project_id}, using default")
            return get_default_config(project_id)

        config = {
            "project_id": project_id,
            "project_root": row[0],
            "docs_dir": row[1],
            "archive_dir": row[2],
            "sot_build_history": row[3],
            "sot_debug_log": row[4],
            "sot_architecture": row[5],
            "sot_unsorted": row[6],
            "project_context": row[7],  # Already parsed as dict by psycopg2
            "enable_database_logging": row[8],
            "enable_research_workflow": row[9],
        }

        conn.close()
        print(f"✅ Loaded config for {project_id} from database")
        return config

    except Exception as e:
        print(f"⚠️  Error loading config from DB: {e}")
        print(f"   Using default config for {project_id}")
        return get_default_config(project_id)


def get_default_config(project_id: str) -> Dict[str, Any]:
    """
    Get default configuration for a project

    Args:
        project_id: Project identifier

    Returns:
        Default configuration dictionary

    Raises:
        ValueError: If project_id is unknown
    """
    if project_id == "autopack":
        return {
            "project_id": "autopack",
            "project_root": ".",
            "docs_dir": "docs",
            "archive_dir": "archive",
            "sot_build_history": "BUILD_HISTORY.md",
            "sot_debug_log": "DEBUG_LOG.md",
            "sot_architecture": "ARCHITECTURE_DECISIONS.md",
            "sot_unsorted": "UNSORTED_REVIEW.md",
            "project_context": {
                "keywords": {
                    "build": ["implementation", "build", "complete", "feature"],
                    "debug": ["error", "bug", "fix", "troubleshoot"],
                    "architecture": ["decision", "design", "architecture", "analysis"],
                },
                "priorities": {},
                "exclude_patterns": [".autonomous_runs/*", "*.pyc", "__pycache__"],
            },
            "enable_database_logging": True,
            "enable_research_workflow": True,
        }

    elif project_id == "file-organizer-app-v1":
        return {
            "project_id": "file-organizer-app-v1",
            "project_root": ".autonomous_runs/file-organizer-app-v1",
            "docs_dir": "docs",
            "archive_dir": "archive",
            "sot_build_history": "BUILD_HISTORY.md",
            "sot_debug_log": "DEBUG_LOG.md",
            "sot_architecture": "ARCHITECTURE_DECISIONS.md",
            "sot_unsorted": "UNSORTED_REVIEW.md",
            "project_context": {
                "keywords": {
                    "build": [
                        "visa pack",
                        "document classification",
                        "batch upload",
                        "implementation",
                    ],
                    "debug": ["processing error", "classification failed", "error", "bug"],
                    "architecture": ["pack structure", "visa type", "decision", "design"],
                },
                "priorities": {},
                "exclude_patterns": ["packs/*", "*.db", "*.sqlite", "__pycache__"],
            },
            "enable_database_logging": True,
            "enable_research_workflow": True,
        }

    else:
        raise ValueError(
            f"Unknown project_id: {project_id}. Add to database or define default config."
        )


def get_project_keywords(config: Dict[str, Any], category: str) -> list:
    """
    Get keywords for a specific category from project context

    Args:
        config: Project configuration
        category: Category name ('build', 'debug', 'architecture')

    Returns:
        List of keywords for the category
    """
    return config.get("project_context", {}).get("keywords", {}).get(category, [])


if __name__ == "__main__":
    # Test configuration loading
    print("Testing project configuration loader...\n")

    # Test autopack
    print("=== Autopack ===")
    autopack_config = load_project_config("autopack")
    print(f"Project root: {autopack_config['project_root']}")
    print(f"Build keywords: {get_project_keywords(autopack_config, 'build')[:3]}...")

    # Test file-organizer
    print("\n=== File Organizer ===")
    fileorg_config = load_project_config("file-organizer-app-v1")
    print(f"Project root: {fileorg_config['project_root']}")
    print(f"Build keywords: {get_project_keywords(fileorg_config, 'build')[:3]}...")

    # Test auto-detection
    print("\n=== Auto-detection ===")
    print(f"Detected project: {detect_project_id()}")
