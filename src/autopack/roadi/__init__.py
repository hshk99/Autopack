"""ROAD-I: Regression Detection and Protection.

This module provides automatic regression protection for fixed issues,
preventing previously resolved problems from recurring.
"""

from .regression_protector import ProtectionResult, RegressionProtector, RegressionTest

__all__ = ["RegressionProtector", "RegressionTest", "ProtectionResult"]
