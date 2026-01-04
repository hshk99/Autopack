"""
Deterministic budget calculation for intention-first autonomy.

Implements:
- Budget remaining computation from Intention Anchor budgets + measured usage
- Deterministic fraction (0..1) clamped from token/context/SOT budgets
- No guessing; always explicit inputs

All budget calculations are reproducible and grounded in authoritative sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetInputs:
    """
    Authoritative inputs for budget calculation.

    All inputs must be explicit; no global state.
    """

    token_cap: int  # From settings.run_token_cap
    tokens_used: int  # From measured usage events
    max_context_chars: int  # From IntentionAnchor.budgets.max_context_chars
    context_chars_used: int  # From measured context construction
    max_sot_chars: int  # From IntentionAnchor.budgets.max_sot_chars
    sot_chars_used: int  # From measured SOT retrieval


def compute_budget_remaining(inputs: BudgetInputs) -> float:
    """
    Compute budget remaining as deterministic fraction [0.0, 1.0].

    Logic:
    - For each budget dimension (tokens, context, SOT):
      - fraction = 1.0 - (used / cap)
      - clamp to [0.0, 1.0]
    - Return minimum across all dimensions

    Args:
        inputs: Budget inputs with caps and measured usage

    Returns:
        Fraction of budget remaining, clamped to [0.0, 1.0]
    """

    def fraction_remaining(used: int, cap: int) -> float:
        """Calculate remaining fraction for one dimension."""
        if cap <= 0:
            # Zero or negative cap means no constraint -> full budget available
            return 1.0

        remaining = 1.0 - (used / cap)
        return max(0.0, min(1.0, remaining))

    # Compute fraction for each dimension
    token_fraction = fraction_remaining(inputs.tokens_used, inputs.token_cap)
    context_fraction = fraction_remaining(
        inputs.context_chars_used, inputs.max_context_chars
    )
    sot_fraction = fraction_remaining(inputs.sot_chars_used, inputs.max_sot_chars)

    # Return minimum (most constraining dimension)
    return min(token_fraction, context_fraction, sot_fraction)
