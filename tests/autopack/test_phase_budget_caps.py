"""Tests for IMP-COST-002: Per-phase token budget caps."""

import pytest

from autopack.autonomous.budgeting import (PhaseTokenBudgetExceededError,
                                           get_phase_budget_remaining_pct,
                                           is_phase_budget_exceeded)
from autopack.config import Settings


class TestPhaseBudgetExhaustion:
    """Tests for phase budget exhaustion detection."""

    def test_phase_budget_exceeded_when_tokens_exceed_cap(self):
        """Verify phase budget is detected as exceeded when tokens exceed cap."""
        assert is_phase_budget_exceeded(phase_tokens_used=501000, phase_token_cap=500000) is True
        assert is_phase_budget_exceeded(phase_tokens_used=500000, phase_token_cap=500000) is True

    def test_phase_budget_not_exceeded_when_tokens_under_cap(self):
        """Verify phase budget is not exceeded when under cap."""
        assert is_phase_budget_exceeded(phase_tokens_used=499999, phase_token_cap=500000) is False
        assert is_phase_budget_exceeded(phase_tokens_used=0, phase_token_cap=500000) is False

    def test_phase_budget_not_exceeded_when_cap_is_none_or_zero(self):
        """Verify None/zero cap means unlimited phase budget."""
        assert is_phase_budget_exceeded(phase_tokens_used=1000000, phase_token_cap=None) is False
        assert is_phase_budget_exceeded(phase_tokens_used=1000000, phase_token_cap=0) is False


class TestPhaseBudgetRemainingPercentage:
    """Tests for phase budget remaining percentage calculation."""

    def test_full_phase_budget_remaining(self):
        """Verify 100% remaining when no phase tokens used."""
        assert get_phase_budget_remaining_pct(phase_tokens_used=0, phase_token_cap=500000) == 1.0

    def test_half_phase_budget_remaining(self):
        """Verify 50% remaining when half phase tokens used."""
        assert (
            get_phase_budget_remaining_pct(phase_tokens_used=250000, phase_token_cap=500000) == 0.5
        )

    def test_phase_budget_exhausted_returns_zero(self):
        """Verify 0% remaining when phase budget exhausted."""
        assert (
            get_phase_budget_remaining_pct(phase_tokens_used=500000, phase_token_cap=500000) == 0.0
        )
        assert (
            get_phase_budget_remaining_pct(phase_tokens_used=600000, phase_token_cap=500000) == 0.0
        )

    def test_none_cap_returns_full_budget(self):
        """Verify None cap returns 100% (unlimited)."""
        assert (
            get_phase_budget_remaining_pct(phase_tokens_used=1000000, phase_token_cap=None) == 1.0
        )


class TestPhaseTokenBudgetExceededError:
    """Tests for PhaseTokenBudgetExceededError exception."""

    def test_exception_can_be_raised(self):
        """Verify PhaseTokenBudgetExceededError can be raised with message."""
        with pytest.raises(PhaseTokenBudgetExceededError) as exc_info:
            raise PhaseTokenBudgetExceededError("Phase exceeded token budget: 501000/500000 tokens")

        assert "exceeded token budget" in str(exc_info.value).lower()
        assert "501000/500000" in str(exc_info.value)

    def test_exception_is_subclass_of_exception(self):
        """Verify PhaseTokenBudgetExceededError is a proper Exception subclass."""
        assert issubclass(PhaseTokenBudgetExceededError, Exception)


class TestPhaseTokenCapMultipliers:
    """Tests for per-phase type budget multipliers in config."""

    def test_default_phase_token_cap(self):
        """Verify default phase token cap is 500k."""
        settings = Settings()
        assert settings.phase_token_cap_default == 500_000

    def test_phase_token_cap_multipliers_parsed(self):
        """Verify phase token cap multipliers are parsed correctly."""
        settings = Settings()
        multipliers = settings.phase_token_cap_multipliers
        assert "research" in multipliers
        assert "implementation" in multipliers
        assert "verification" in multipliers
        assert "audit" in multipliers
        assert multipliers["research"] == 1.5
        assert multipliers["implementation"] == 1.0

    def test_get_phase_token_cap_applies_multiplier(self):
        """Verify get_phase_token_cap applies multiplier correctly."""
        settings = Settings()
        # Research: 500k * 1.5 = 750k
        assert settings.get_phase_token_cap("research") == 750_000
        # Implementation: 500k * 1.0 = 500k
        assert settings.get_phase_token_cap("implementation") == 500_000
        # Verification: 500k * 0.5 = 250k
        assert settings.get_phase_token_cap("verification") == 250_000
        # Audit: 500k * 0.3 = 150k
        assert settings.get_phase_token_cap("audit") == 150_000

    def test_get_phase_token_cap_unknown_type_uses_default(self):
        """Verify unknown phase types use default multiplier (1.0)."""
        settings = Settings()
        # Unknown type should use 1.0 multiplier
        assert settings.get_phase_token_cap("unknown_type") == 500_000
