"""ROAD-I: Regression Detection and Protection.

This module provides automatic regression protection for fixed issues,
preventing previously resolved problems from recurring.

IMP-LOOP-018: Added RiskSeverity and RiskAssessment for task generation gating.
"""

from .regression_protector import (ProtectionResult, RegressionProtector,
                                   RegressionTest, RiskAssessment,
                                   RiskSeverity)

__all__ = [
    "RegressionProtector",
    "RegressionTest",
    "ProtectionResult",
    "RiskSeverity",
    "RiskAssessment",
]
