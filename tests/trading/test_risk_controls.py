"""Tests for trading risk controls.

Tests the trading safety gates: kill switch, limits, mode controls,
and strategy change approval.
"""

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from autopack.trading import (
    RiskLimitType,
    RiskViolation,
    TradingMode,
    TradingRiskConfig,
    TradingRiskGate,
)


class TestTradingMode:
    """Tests for TradingMode enum."""

    def test_all_modes(self):
        """All expected modes exist."""
        assert TradingMode.DISABLED
        assert TradingMode.PAPER
        assert TradingMode.LIVE


class TestRiskLimitType:
    """Tests for RiskLimitType enum."""

    def test_all_limit_types(self):
        """All expected limit types exist."""
        assert RiskLimitType.MAX_LOSS_DAY
        assert RiskLimitType.MAX_ORDERS_DAY
        assert RiskLimitType.MAX_POSITION_SIZE
        assert RiskLimitType.MAX_TOTAL_EXPOSURE
        assert RiskLimitType.MAX_ORDER_VALUE
        assert RiskLimitType.MAX_DRAWDOWN


class TestTradingRiskConfig:
    """Tests for TradingRiskConfig."""

    def test_default_config_is_conservative(self):
        """Default config has conservative limits."""
        config = TradingRiskConfig()
        assert config.mode == TradingMode.DISABLED
        assert config.live_trading_approved is False
        assert config.max_loss_day == Decimal("100.00")
        assert config.max_orders_day == 10
        assert config.kill_switch_active is False

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = TradingRiskConfig(
            mode=TradingMode.PAPER,
            live_trading_approved=True,
            live_trading_approval_id="approval-123",
            max_loss_day=Decimal("500.00"),
            max_orders_day=20,
            kill_switch_active=True,
            kill_switch_reason="Test",
            strategy_version="2.0.0",
        )

        data = original.to_dict()
        restored = TradingRiskConfig.from_dict(data)

        assert restored.mode == original.mode
        assert restored.live_trading_approved == original.live_trading_approved
        assert restored.max_loss_day == original.max_loss_day
        assert restored.kill_switch_active == original.kill_switch_active
        assert restored.strategy_version == original.strategy_version


class TestRiskViolation:
    """Tests for RiskViolation."""

    def test_to_dict(self):
        """to_dict includes all fields."""
        violation = RiskViolation(
            violation_id="viol-001",
            limit_type=RiskLimitType.MAX_LOSS_DAY,
            limit_value=Decimal("100.00"),
            actual_value=Decimal("150.00"),
            timestamp=datetime.now(timezone.utc),
            message="Daily loss limit exceeded",
        )
        data = violation.to_dict()
        assert data["limit_type"] == "max_loss_day"
        assert data["limit_value"] == "100.00"
        assert data["actual_value"] == "150.00"


class TestTradingRiskGate:
    """Tests for TradingRiskGate."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "trading"

    @pytest.fixture
    def gate(self, temp_storage):
        """Create gate with temp storage."""
        return TradingRiskGate(storage_path=temp_storage)

    @pytest.fixture(autouse=True)
    def clear_env(self):
        """Clear LIVE_TRADING_ENABLED before each test."""
        old_value = os.environ.pop("LIVE_TRADING_ENABLED", None)
        yield
        if old_value is not None:
            os.environ["LIVE_TRADING_ENABLED"] = old_value
        else:
            os.environ.pop("LIVE_TRADING_ENABLED", None)

    def test_default_mode_disabled(self, gate):
        """Default mode is disabled."""
        assert gate.get_effective_mode() == TradingMode.DISABLED

    def test_paper_mode_allowed(self, gate):
        """Paper mode works without approvals."""
        gate.set_mode(TradingMode.PAPER)
        assert gate.get_effective_mode() == TradingMode.PAPER

    def test_live_mode_requires_approval(self, gate):
        """Live mode falls back to paper without approval."""
        gate.set_mode(TradingMode.LIVE)
        # No approval, falls back to paper
        assert gate.get_effective_mode() == TradingMode.PAPER

    def test_live_mode_requires_env_var(self, gate):
        """Live mode requires LIVE_TRADING_ENABLED env var."""
        gate.set_mode(TradingMode.LIVE)
        gate.approve_live_trading("approval-123", "admin")
        # Still paper because env var not set
        assert gate.get_effective_mode() == TradingMode.PAPER

    def test_live_mode_with_all_requirements(self, gate):
        """Live mode works with approval AND env var."""
        gate.set_mode(TradingMode.LIVE)
        gate.approve_live_trading("approval-123", "admin")
        os.environ["LIVE_TRADING_ENABLED"] = "1"
        assert gate.get_effective_mode() == TradingMode.LIVE

    def test_kill_switch_overrides_all(self, gate):
        """Kill switch disables trading regardless of mode."""
        gate.set_mode(TradingMode.PAPER)
        gate.activate_kill_switch("Emergency", "admin")
        assert gate.get_effective_mode() == TradingMode.DISABLED

    def test_kill_switch_deactivate(self, gate):
        """Kill switch can be deactivated."""
        gate.set_mode(TradingMode.PAPER)
        gate.activate_kill_switch("Emergency", "admin")
        gate.deactivate_kill_switch("admin")
        assert gate.get_effective_mode() == TradingMode.PAPER

    def test_can_execute_trade_disabled(self, gate):
        """Trading blocked when disabled."""
        can, reason = gate.can_execute_trade(Decimal("50.00"))
        assert can is False
        assert "disabled" in reason.lower()

    def test_can_execute_trade_paper(self, gate):
        """Trading allowed in paper mode."""
        gate.set_mode(TradingMode.PAPER)
        can, reason = gate.can_execute_trade(Decimal("50.00"))
        assert can is True
        assert reason is None

    def test_can_execute_trade_exceeds_order_value(self, gate):
        """Order blocked when exceeds max order value."""
        gate.set_mode(TradingMode.PAPER)
        # Default max is $100
        can, reason = gate.can_execute_trade(Decimal("150.00"))
        assert can is False
        assert "order value" in reason.lower()

    def test_can_execute_trade_exceeds_position_size(self, gate):
        """Order blocked when position size exceeds limit."""
        gate.set_mode(TradingMode.PAPER)
        can, reason = gate.can_execute_trade(
            order_value=Decimal("50.00"),
            position_size=Decimal("200.00"),
        )
        assert can is False
        assert "position size" in reason.lower()

    def test_can_execute_trade_daily_order_limit(self, gate):
        """Order blocked when daily order count exceeded."""
        gate.set_mode(TradingMode.PAPER)
        gate.update_limits(max_orders_day=3)

        # Record 3 orders
        for _ in range(3):
            can, _ = gate.can_execute_trade(Decimal("10.00"))
            assert can is True
            gate.record_order(Decimal("10.00"))

        # 4th order blocked
        can, reason = gate.can_execute_trade(Decimal("10.00"))
        assert can is False
        assert "order limit" in reason.lower()

    def test_can_execute_trade_exposure_limit(self, gate):
        """Order blocked when total exposure exceeded."""
        gate.set_mode(TradingMode.PAPER)
        gate.update_limits(max_total_exposure=Decimal("100.00"))

        # Record some exposure
        gate.record_order(Decimal("80.00"))

        # Order that would exceed exposure
        can, reason = gate.can_execute_trade(Decimal("30.00"))
        assert can is False
        assert "exposure" in reason.lower()

    def test_can_execute_trade_kill_switch(self, gate):
        """Order blocked with kill switch reason."""
        gate.set_mode(TradingMode.PAPER)
        gate.activate_kill_switch("Market crash", "admin")
        can, reason = gate.can_execute_trade(Decimal("10.00"))
        assert can is False
        assert "kill switch" in reason.lower()
        assert "Market crash" in reason

    def test_record_order_updates_state(self, gate):
        """record_order updates daily state."""
        gate.set_mode(TradingMode.PAPER)
        gate.record_order(Decimal("50.00"))
        gate.record_order(Decimal("30.00"))

        status = gate.get_status()
        assert status["daily_state"]["orders_count"] == 2
        assert Decimal(status["daily_state"]["total_exposure"]) == Decimal("80.00")

    def test_record_pnl(self, gate):
        """record_pnl updates tracking."""
        gate.set_mode(TradingMode.PAPER)
        gate.record_pnl(
            realized=Decimal("-10.00"),
            unrealized=Decimal("5.00"),
            current_equity=Decimal("990.00"),
        )

        status = gate.get_status()
        assert Decimal(status["daily_state"]["realized_pnl"]) == Decimal("-10.00")
        assert Decimal(status["daily_state"]["current_equity"]) == Decimal("990.00")

    def test_approve_live_trading(self, gate):
        """approve_live_trading sets approval."""
        gate.approve_live_trading("approval-456", "admin")
        assert gate.config.live_trading_approved is True
        assert gate.config.live_trading_approval_id == "approval-456"

    def test_revoke_live_trading(self, gate):
        """revoke_live_trading clears approval."""
        gate.approve_live_trading("approval-456", "admin")
        gate.revoke_live_trading("admin")
        assert gate.config.live_trading_approved is False
        assert gate.config.live_trading_approval_id is None

    def test_strategy_change_blocks_live(self, gate):
        """Pending strategy change blocks live trading."""
        gate.set_mode(TradingMode.LIVE)
        gate.approve_live_trading("approval-123", "admin")
        os.environ["LIVE_TRADING_ENABLED"] = "1"

        # Should be live
        assert gate.get_effective_mode() == TradingMode.LIVE

        # Request strategy change
        gate.request_strategy_change("2.0.0")

        # Now falls back to paper
        assert gate.get_effective_mode() == TradingMode.PAPER

    def test_strategy_change_approval(self, gate):
        """Strategy change approval unblocks live trading."""
        gate.set_mode(TradingMode.LIVE)
        gate.approve_live_trading("approval-123", "admin")
        os.environ["LIVE_TRADING_ENABLED"] = "1"
        gate.request_strategy_change("2.0.0")

        # Blocked
        assert gate.get_effective_mode() == TradingMode.PAPER

        # Approve strategy
        gate.approve_strategy_change("2.0.0", "admin")

        # Now live
        assert gate.get_effective_mode() == TradingMode.LIVE
        assert gate.config.strategy_version == "2.0.0"

    def test_update_limits(self, gate):
        """update_limits changes config."""
        gate.update_limits(
            max_loss_day=Decimal("200.00"),
            max_orders_day=50,
        )
        assert gate.config.max_loss_day == Decimal("200.00")
        assert gate.config.max_orders_day == 50

    def test_get_status(self, gate):
        """get_status returns comprehensive info."""
        gate.set_mode(TradingMode.PAPER)
        status = gate.get_status()

        assert "effective_mode" in status
        assert "configured_mode" in status
        assert "is_trading_enabled" in status
        assert "config" in status
        assert "env_live_enabled" in status

    def test_persistence(self, temp_storage):
        """State persists across gate instances."""
        # Create and configure first gate
        gate1 = TradingRiskGate(storage_path=temp_storage)
        gate1.set_mode(TradingMode.PAPER)
        gate1.update_limits(max_orders_day=100)
        gate1.record_order(Decimal("50.00"))

        # Load with new gate
        gate2 = TradingRiskGate(storage_path=temp_storage)

        assert gate2.config.mode == TradingMode.PAPER
        assert gate2.config.max_orders_day == 100

        status = gate2.get_status()
        assert status["daily_state"]["orders_count"] == 1

    def test_loss_limit_check(self, gate):
        """Trading blocked when daily loss exceeds limit."""
        gate.set_mode(TradingMode.PAPER)
        gate.update_limits(max_loss_day=Decimal("50.00"))

        # Record significant loss
        gate.record_pnl(
            realized=Decimal("-60.00"),
            unrealized=Decimal("0.00"),
            current_equity=Decimal("940.00"),
        )

        can, reason = gate.can_execute_trade(Decimal("10.00"))
        assert can is False
        assert "loss limit" in reason.lower()


class TestLiveRequirements:
    """Tests specifically for live trading requirements."""

    @pytest.fixture
    def temp_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "trading"

    @pytest.fixture(autouse=True)
    def clear_env(self):
        old_value = os.environ.pop("LIVE_TRADING_ENABLED", None)
        yield
        if old_value is not None:
            os.environ["LIVE_TRADING_ENABLED"] = old_value
        else:
            os.environ.pop("LIVE_TRADING_ENABLED", None)

    def test_live_requires_both_approval_and_env(self, temp_storage):
        """Live trading requires BOTH approval AND env var."""
        gate = TradingRiskGate(storage_path=temp_storage)
        gate.set_mode(TradingMode.LIVE)

        # Neither - paper fallback
        assert gate.get_effective_mode() == TradingMode.PAPER

        # Approval only - paper fallback
        gate.approve_live_trading("approval", "admin")
        assert gate.get_effective_mode() == TradingMode.PAPER

        # Revoke approval, env only - paper fallback
        gate.revoke_live_trading("admin")
        os.environ["LIVE_TRADING_ENABLED"] = "1"
        assert gate.get_effective_mode() == TradingMode.PAPER

        # Both - live
        gate.approve_live_trading("approval", "admin")
        assert gate.get_effective_mode() == TradingMode.LIVE
