"""
Storage Optimizer Module

Policy-aware disk space analysis and cleanup recommendations.
Integrates with Autopack's tidy system and data retention policies.

MVP Features:
- Policy-aware scanning and classification
- Protected path enforcement
- Retention window compliance
- Dry-run reporting (no actual deletion)

Usage:
    from autopack.storage_optimizer import (
        load_policy,
        StorageScanner,
        FileClassifier,
        StorageReporter
    )

    # Load policy
    policy = load_policy()

    # Scan and classify
    scanner = StorageScanner()
    results = scanner.scan_high_value_directories("C")

    classifier = FileClassifier(policy)
    candidates = classifier.classify_batch(results)

    # Generate report
    reporter = StorageReporter()
    report = reporter.create_report(...)
    reporter.print_summary(report)
"""

from .policy import (
    CategoryPolicy,
    RetentionPolicy,
    StoragePolicy,
    load_policy,
    is_path_protected,
    get_category_for_path,
)

from .models import (
    ScanResult,
    CleanupCandidate,
    CleanupPlan,
    StorageReport,
)

from .scanner import StorageScanner
from .classifier import FileClassifier
from .reporter import StorageReporter

# Make submodules accessible for patching in tests
from . import steam_detector  # noqa: F401

__all__ = [
    # Policy
    "CategoryPolicy",
    "RetentionPolicy",
    "StoragePolicy",
    "load_policy",
    "is_path_protected",
    "get_category_for_path",
    # Models
    "ScanResult",
    "CleanupCandidate",
    "CleanupPlan",
    "StorageReport",
    # Core Components
    "StorageScanner",
    "FileClassifier",
    "StorageReporter",
]
