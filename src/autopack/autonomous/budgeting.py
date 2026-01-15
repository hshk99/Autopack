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


class BudgetExhaustedError(Exception):
    """Raised when per-run token budget is exhausted."""

    pass


class PhaseTokenBudgetExceededError(Exception):
    """Raised when a phase exceeds its allocated token budget."""

    pass


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


def is_budget_exhausted(token_cap: int, tokens_used: int) -> bool:
    """Check if run has exceeded token budget.

    Args:
        token_cap: Maximum tokens allowed for the run
        tokens_used: Total tokens used so far

    Returns:
        True if budget is exhausted, False otherwise
    """
    if token_cap is None:
        return False
    return tokens_used >= token_cap


def get_budget_remaining_pct(token_cap: int, tokens_used: int) -> float:
    """Get percentage of budget remaining (0.0 = exhausted, 1.0 = full).

    Args:
        token_cap: Maximum tokens allowed for the run
        tokens_used: Total tokens used so far

    Returns:
        Percentage of budget remaining as float [0.0, 1.0]
    """
    if token_cap is None:
        return 1.0
    if token_cap <= 0:
        return 0.0
    remaining = max(0.0, (token_cap - tokens_used) / token_cap)
    return remaining


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
    context_fraction = fraction_remaining(inputs.context_chars_used, inputs.max_context_chars)
    sot_fraction = fraction_remaining(inputs.sot_chars_used, inputs.max_sot_chars)

    # Return minimum (most constraining dimension)
    return min(token_fraction, context_fraction, sot_fraction)


def is_phase_budget_exceeded(phase_tokens_used: int, phase_token_cap: int) -> bool:
    """Check if phase has exceeded its allocated token budget.

    Args:
        phase_tokens_used: Total tokens used by this phase so far
        phase_token_cap: Maximum tokens allocated for this phase

    Returns:
        True if phase budget exceeded, False otherwise
    """
    if phase_token_cap is None or phase_token_cap <= 0:
        return False
    return phase_tokens_used >= phase_token_cap


def get_phase_budget_remaining_pct(phase_tokens_used: int, phase_token_cap: int) -> float:
    """Get percentage of phase budget remaining (0.0 = exhausted, 1.0 = full).

    Args:
        phase_tokens_used: Total tokens used by this phase so far
        phase_token_cap: Maximum tokens allocated for this phase

    Returns:
        Percentage of phase budget remaining as float [0.0, 1.0]
    """
    if phase_token_cap is None:
        return 1.0
    if phase_token_cap <= 0:
        return 0.0
    remaining = max(0.0, (phase_token_cap - phase_tokens_used) / phase_token_cap)
    return remaining
