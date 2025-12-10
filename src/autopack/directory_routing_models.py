"""Database models for directory routing configuration

These models store project-specific routing rules for files created by Cursor and Autopack.
Used by tidy_workspace.py to automatically route files to the correct locations.
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    ARRAY,
    UniqueConstraint,
)
from sqlalchemy.orm import Session

from .database import Base


class DirectoryRoutingRule(Base):
    """Routing rules for file organization by project, type, and source"""

    __tablename__ = "directory_routing_rules"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, nullable=False, index=True)
    file_type = Column(String, nullable=False, index=True)  # plan, analysis, log, run, diagnostic, etc.
    source_context = Column(String, nullable=False, index=True)  # cursor, autopack, manual
    destination_path = Column(Text, nullable=False)  # Supports {project}, {family}, {run_id} variables
    is_archived = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # Higher = higher priority
    pattern_match = Column(Text, nullable=True)  # Optional regex for filename matching
    content_keywords = Column(ARRAY(String), nullable=True)  # Keywords for content-based classification

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint('project_id', 'file_type', 'source_context', 'is_archived', name='uq_routing_rule'),
    )


class ProjectDirectoryConfig(Base):
    """Base directory configuration for each project"""

    __tablename__ = "project_directory_config"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, nullable=False, unique=True, index=True)
    base_path = Column(Text, nullable=False)
    runs_path = Column(Text, nullable=False)
    archive_path = Column(Text, nullable=False)
    docs_path = Column(Text, nullable=False)
    uses_family_grouping = Column(Boolean, default=True, nullable=False)
    auto_archive_days = Column(Integer, default=30, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# Helper functions for querying routing rules

def get_routing_rule(
    session: Session,
    project_id: str,
    file_type: str,
    source_context: str = "cursor",
    is_archived: bool = False,
) -> Optional[DirectoryRoutingRule]:
    """Get the routing rule for a specific file type and context"""
    return (
        session.query(DirectoryRoutingRule)
        .filter_by(
            project_id=project_id,
            file_type=file_type,
            source_context=source_context,
            is_archived=is_archived,
        )
        .order_by(DirectoryRoutingRule.priority.desc())
        .first()
    )


def get_project_config(session: Session, project_id: str) -> Optional[ProjectDirectoryConfig]:
    """Get the directory configuration for a project"""
    return session.query(ProjectDirectoryConfig).filter_by(project_id=project_id).first()


def classify_file_type_by_keywords(content: str, session: Session, project_id: str) -> str:
    """Classify file type based on content keywords

    Args:
        content: File content (first ~500 chars recommended)
        session: Database session
        project_id: Project identifier

    Returns:
        File type string (e.g., 'plan', 'analysis', 'log') or 'unknown'
    """
    content_lower = content.lower()

    # Get all rules for this project with keywords
    rules = (
        session.query(DirectoryRoutingRule)
        .filter_by(project_id=project_id, source_context="cursor")
        .filter(DirectoryRoutingRule.content_keywords.isnot(None))
        .order_by(DirectoryRoutingRule.priority.desc())
        .all()
    )

    best_match = None
    best_score = 0

    for rule in rules:
        if not rule.content_keywords:
            continue

        # Count keyword matches
        score = sum(1 for keyword in rule.content_keywords if keyword.lower() in content_lower)

        if score > best_score:
            best_score = score
            best_match = rule.file_type

    return best_match if best_match else "unknown"


def get_destination_path(
    session: Session,
    project_id: str,
    file_type: str,
    source_context: str = "cursor",
    is_archived: bool = False,
    family: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[str]:
    """Get the destination path for a file, with variable substitution

    Args:
        session: Database session
        project_id: Project identifier
        file_type: Type of file (plan, analysis, run, etc.)
        source_context: Source of file (cursor, autopack, manual)
        is_archived: Whether this is for archived files
        family: Run family name (for run files)
        run_id: Run identifier (for run files)

    Returns:
        Destination path with variables substituted, or None if no rule found
    """
    rule = get_routing_rule(session, project_id, file_type, source_context, is_archived)

    if not rule:
        return None

    path = rule.destination_path

    # Substitute variables
    if family:
        path = path.replace("{family}", family)
    if run_id:
        path = path.replace("{run_id}", run_id)
    if "{project}" in path:
        path = path.replace("{project}", project_id)
    if "{date}" in path:
        path = path.replace("{date}", datetime.now().strftime("%Y%m%d"))

    return path


def list_all_rules(session: Session, project_id: Optional[str] = None) -> List[DirectoryRoutingRule]:
    """List all routing rules, optionally filtered by project"""
    query = session.query(DirectoryRoutingRule).order_by(
        DirectoryRoutingRule.project_id,
        DirectoryRoutingRule.priority.desc(),
        DirectoryRoutingRule.file_type
    )

    if project_id:
        query = query.filter_by(project_id=project_id)

    return query.all()
