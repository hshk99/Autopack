"""Trading risk controls and safety gates.

Implements gap analysis item 6.5:
- Hard kill switch
- Max-loss/day, max-orders/day, max-position-size limits
- Paper trading only mode until explicit live promotion
- Strategy change approval requirements
- Deterministic audit logging

CRITICAL SAFETY DESIGN:
- Live trading requires EXPLICIT opt-in (LIVE_TRADING_ENABLED=1)
- All limits are enforced BEFORE order submission
- Kill switch halts ALL trading immediately
- Strategy changes require human approval
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TradingMode(str, Enum):
    """Trading execution mode."""

    DISABLED = "disabled"  # Trading completely disabled
    PAPER = "paper"  # Paper trading only (sandbox)
    LIVE = "live"  # Live trading with real money


class RiskLimitType(str, Enum):
    """Types of risk limits."""

    MAX_LOSS_DAY = "max_loss_day"  # Maximum loss per day
    MAX_ORDERS_DAY = "max_orders_day"  # Maximum orders per day
    MAX_POSITION_SIZE = "max_position_size"  # Maximum single position size
    MAX_TOTAL_EXPOSURE = "max_total_exposure"  # Maximum total exposure
    MAX_ORDER_VALUE = "max_order_value"  # Maximum single order value
    MAX_DRAWDOWN = "max_drawdown"  # Maximum drawdown from peak


@dataclass
class RiskViolation:
    """Record of a risk limit violation."""

    violation_id: str
    limit_type: RiskLimitType
    limit_value: Decimal
    actual_value: Decimal
    timestamp: datetime
    order_details: Optional[dict] = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "violation_id": self.violation_id,
            "limit_type": self.limit_type.value,
            "limit_value": str(self.limit_value),
            "actual_value": str(self.actual_value),
            "timestamp": self.timestamp.isoformat(),
            "order_details": self.order_details,
            "message": self.message,
        }


@dataclass
class TradingRiskConfig:
    """Configuration for trading risk controls.

    All limits are conservative defaults that must be explicitly relaxed.
    """

    # Mode controls
    mode: TradingMode = TradingMode.DISABLED
    live_trading_approved: bool = False  # Requires explicit approval
    live_trading_approval_id: Optional[str] = None

    # Daily limits
    max_loss_day: Decimal = Decimal("100.00")  # Max $100 loss per day
    max_orders_day: int = 10  # Max 10 orders per day
    max_total_exposure: Decimal = Decimal("1000.00")  # Max $1000 total exposure

    # Per-order limits
    max_position_size: Decimal = Decimal("100.00")  # Max $100 per position
    max_order_value: Decimal = Decimal("100.00")  # Max $100 per order

    # Drawdown limits
    max_drawdown_percent: Decimal = Decimal("10.0")  # Max 10% drawdown from peak

    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: Optional[str] = None
    kill_switch_activated_at: Optional[datetime] = None
    kill_switch_activated_by: Optional[str] = None

    # Strategy change tracking
    strategy_version: str = "1.0.0"
    strategy_approved_at: Optional[datetime] = None
    strategy_approved_by: Optional[str] = None
    pending_strategy_change: bool = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "live_trading_approved": self.live_trading_approved,
            "live_trading_approval_id": self.live_trading_approval_id,
            "max_loss_day": str(self.max_loss_day),
            "max_orders_day": self.max_orders_day,
            "max_total_exposure": str(self.max_total_exposure),
            "max_position_size": str(self.max_position_size),
            "max_order_value": str(self.max_order_value),
            "max_drawdown_percent": str(self.max_drawdown_percent),
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_reason": self.kill_switch_reason,
            "kill_switch_activated_at": (
                self.kill_switch_activated_at.isoformat() if self.kill_switch_activated_at else None
            ),
            "kill_switch_activated_by": self.kill_switch_activated_by,
            "strategy_version": self.strategy_version,
            "strategy_approved_at": (
                self.strategy_approved_at.isoformat() if self.strategy_approved_at else None
            ),
            "strategy_approved_by": self.strategy_approved_by,
            "pending_strategy_change": self.pending_strategy_change,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradingRiskConfig":
        return cls(
            mode=TradingMode(data.get("mode", "disabled")),
            live_trading_approved=data.get("live_trading_approved", False),
            live_trading_approval_id=data.get("live_trading_approval_id"),
            max_loss_day=Decimal(data.get("max_loss_day", "100.00")),
            max_orders_day=data.get("max_orders_day", 10),
            max_total_exposure=Decimal(data.get("max_total_exposure", "1000.00")),
            max_position_size=Decimal(data.get("max_position_size", "100.00")),
            max_order_value=Decimal(data.get("max_order_value", "100.00")),
            max_drawdown_percent=Decimal(data.get("max_drawdown_percent", "10.0")),
            kill_switch_active=data.get("kill_switch_active", False),
            kill_switch_reason=data.get("kill_switch_reason"),
            kill_switch_activated_at=(
                datetime.fromisoformat(data["kill_switch_activated_at"])
                if data.get("kill_switch_activated_at")
                else None
            ),
            kill_switch_activated_by=data.get("kill_switch_activated_by"),
            strategy_version=data.get("strategy_version", "1.0.0"),
            strategy_approved_at=(
                datetime.fromisoformat(data["strategy_approved_at"])
                if data.get("strategy_approved_at")
                else None
            ),
            strategy_approved_by=data.get("strategy_approved_by"),
            pending_strategy_change=data.get("pending_strategy_change", False),
        )


@dataclass
class DailyTradingState:
    """Tracks daily trading activity for limit enforcement."""

    date: str  # YYYY-MM-DD
    orders_count: int = 0
    realized_pnl: Decimal = Decimal("0.00")
    unrealized_pnl: Decimal = Decimal("0.00")
    total_exposure: Decimal = Decimal("0.00")
    peak_equity: Decimal = Decimal("0.00")
    current_equity: Decimal = Decimal("0.00")
    violations: list[RiskViolation] = field(default_factory=list)

    def total_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl

    def drawdown_percent(self) -> Decimal:
        if self.peak_equity <= 0:
            return Decimal("0.00")
        return ((self.peak_equity - self.current_equity) / self.peak_equity) * 100

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "orders_count": self.orders_count,
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "total_exposure": str(self.total_exposure),
            "peak_equity": str(self.peak_equity),
            "current_equity": str(self.current_equity),
            "violations": [v.to_dict() for v in self.violations],
        }


class TradingRiskGate:
    """Safety gate for trading operations.

    CRITICAL: This gate MUST be checked before any trading operation.
    All checks are fail-safe: if in doubt, block the trade.

    Usage:
        gate = TradingRiskGate(storage_path=Path(".trading"))

        # Check if trading is allowed
        can_trade, reason = gate.can_execute_trade(
            order_value=Decimal("50.00"),
            position_size=Decimal("50.00"),
        )

        if not can_trade:
            logger.error(f"Trade blocked: {reason}")
            return

        # Record the trade
        gate.record_order(order_value=Decimal("50.00"))
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize the trading risk gate.

        Args:
            storage_path: Path to store config and state
        """
        self.storage_path = storage_path or Path(".trading")
        self._config: TradingRiskConfig = TradingRiskConfig()
        self._daily_state: Optional[DailyTradingState] = None
        self._load()

    def _load(self) -> None:
        """Load config and state from storage."""
        config_file = self.storage_path / "risk_config.json"
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
                self._config = TradingRiskConfig.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load risk config: {e}")

        # Load today's state
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_file = self.storage_path / f"state_{today}.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                self._daily_state = DailyTradingState(
                    date=data["date"],
                    orders_count=data.get("orders_count", 0),
                    realized_pnl=Decimal(data.get("realized_pnl", "0.00")),
                    unrealized_pnl=Decimal(data.get("unrealized_pnl", "0.00")),
                    total_exposure=Decimal(data.get("total_exposure", "0.00")),
                    peak_equity=Decimal(data.get("peak_equity", "0.00")),
                    current_equity=Decimal(data.get("current_equity", "0.00")),
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load daily state: {e}")
                self._daily_state = DailyTradingState(date=today)
        else:
            self._daily_state = DailyTradingState(date=today)

    def _save(self) -> None:
        """Save config and state to storage."""
        self.storage_path.mkdir(parents=True, exist_ok=True)

        config_file = self.storage_path / "risk_config.json"
        config_file.write_text(
            json.dumps(self._config.to_dict(), indent=2),
            encoding="utf-8",
        )

        if self._daily_state:
            state_file = self.storage_path / f"state_{self._daily_state.date}.json"
            state_file.write_text(
                json.dumps(self._daily_state.to_dict(), indent=2),
                encoding="utf-8",
            )

    @property
    def config(self) -> TradingRiskConfig:
        """Get current risk configuration."""
        return self._config

    def get_effective_mode(self) -> TradingMode:
        """Get the effective trading mode considering all gates.

        Returns TradingMode.DISABLED if any safety check fails.
        """
        # Check environment variable override (ALWAYS checked)
        env_enabled = os.environ.get("LIVE_TRADING_ENABLED", "0") == "1"

        # Kill switch takes priority
        if self._config.kill_switch_active:
            return TradingMode.DISABLED

        # Must have explicit approval for live trading
        if self._config.mode == TradingMode.LIVE:
            if not self._config.live_trading_approved:
                return TradingMode.PAPER  # Fall back to paper
            if not env_enabled:
                return TradingMode.PAPER  # Fall back to paper

        # Strategy changes block live trading
        if self._config.pending_strategy_change:
            if self._config.mode == TradingMode.LIVE:
                return TradingMode.PAPER

        return self._config.mode

    def can_execute_trade(
        self,
        order_value: Decimal,
        position_size: Optional[Decimal] = None,
    ) -> tuple[bool, Optional[str]]:
        """Check if a trade can be executed given risk limits.

        Args:
            order_value: Value of the order
            position_size: Size of the position (defaults to order_value)

        Returns:
            Tuple of (can_execute: bool, rejection_reason: Optional[str])
        """
        position_size = position_size or order_value

        # Get effective mode
        mode = self.get_effective_mode()

        if mode == TradingMode.DISABLED:
            if self._config.kill_switch_active:
                return False, f"Kill switch active: {self._config.kill_switch_reason}"
            return False, "Trading is disabled"

        # Check per-order limits
        if order_value > self._config.max_order_value:
            return False, (
                f"Order value ${order_value} exceeds limit ${self._config.max_order_value}"
            )

        if position_size > self._config.max_position_size:
            return False, (
                f"Position size ${position_size} exceeds limit ${self._config.max_position_size}"
            )

        # Check daily limits
        if self._daily_state:
            # Order count limit
            if self._daily_state.orders_count >= self._config.max_orders_day:
                return False, (f"Daily order limit reached ({self._config.max_orders_day})")

            # Loss limit
            if self._daily_state.total_pnl() < -self._config.max_loss_day:
                return False, (
                    f"Daily loss limit exceeded (loss: ${-self._daily_state.total_pnl()})"
                )

            # Exposure limit
            new_exposure = self._daily_state.total_exposure + order_value
            if new_exposure > self._config.max_total_exposure:
                return False, (
                    f"Total exposure ${new_exposure} would exceed limit ${self._config.max_total_exposure}"
                )

            # Drawdown limit
            drawdown = self._daily_state.drawdown_percent()
            if drawdown > self._config.max_drawdown_percent:
                return False, (
                    f"Drawdown {drawdown}% exceeds limit {self._config.max_drawdown_percent}%"
                )

        # Mode-specific checks
        if mode == TradingMode.LIVE:
            # Extra confirmation for live trading
            if not self._config.live_trading_approved:
                return False, "Live trading not approved"
            if self._config.pending_strategy_change:
                return False, "Strategy change pending approval"

        return True, None

    def record_order(
        self,
        order_value: Decimal,
        order_id: Optional[str] = None,
    ) -> None:
        """Record an executed order for tracking.

        Args:
            order_value: Value of the order
            order_id: Optional order identifier
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self._daily_state is None or self._daily_state.date != today:
            self._daily_state = DailyTradingState(date=today)

        self._daily_state.orders_count += 1
        self._daily_state.total_exposure += order_value

        self._save()

        logger.info(
            f"Recorded order: ${order_value} "
            f"(day total: {self._daily_state.orders_count} orders, "
            f"exposure: ${self._daily_state.total_exposure})"
        )

    def record_pnl(
        self,
        realized: Decimal,
        unrealized: Decimal,
        current_equity: Decimal,
    ) -> None:
        """Update P&L tracking.

        Args:
            realized: Realized P&L
            unrealized: Unrealized P&L
            current_equity: Current account equity
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if self._daily_state is None or self._daily_state.date != today:
            self._daily_state = DailyTradingState(date=today)

        self._daily_state.realized_pnl = realized
        self._daily_state.unrealized_pnl = unrealized
        self._daily_state.current_equity = current_equity

        # Update peak equity
        if current_equity > self._daily_state.peak_equity:
            self._daily_state.peak_equity = current_equity

        self._save()

    def activate_kill_switch(self, reason: str, activated_by: str) -> None:
        """Activate the emergency kill switch.

        Args:
            reason: Reason for activation
            activated_by: Who activated it
        """
        self._config.kill_switch_active = True
        self._config.kill_switch_reason = reason
        self._config.kill_switch_activated_at = datetime.now(timezone.utc)
        self._config.kill_switch_activated_by = activated_by

        self._save()

        logger.critical(f"KILL SWITCH ACTIVATED by {activated_by}: {reason}")

    def deactivate_kill_switch(self, deactivated_by: str) -> None:
        """Deactivate the kill switch.

        Args:
            deactivated_by: Who deactivated it
        """
        self._config.kill_switch_active = False
        self._config.kill_switch_reason = None
        self._config.kill_switch_activated_at = None
        self._config.kill_switch_activated_by = None

        self._save()

        logger.warning(f"Kill switch deactivated by {deactivated_by}")

    def approve_live_trading(
        self,
        approval_id: str,
        approved_by: str,
    ) -> None:
        """Approve live trading.

        Args:
            approval_id: Approval record ID
            approved_by: Who approved
        """
        self._config.live_trading_approved = True
        self._config.live_trading_approval_id = approval_id

        self._save()

        logger.warning(f"Live trading approved by {approved_by} (approval: {approval_id})")

    def revoke_live_trading(self, revoked_by: str) -> None:
        """Revoke live trading approval.

        Args:
            revoked_by: Who revoked
        """
        self._config.live_trading_approved = False
        self._config.live_trading_approval_id = None

        self._save()

        logger.warning(f"Live trading approval revoked by {revoked_by}")

    def set_mode(self, mode: TradingMode) -> None:
        """Set the trading mode.

        Note: Setting to LIVE requires approval and env var.
        """
        self._config.mode = mode
        self._save()

        logger.info(f"Trading mode set to: {mode.value}")

    def approve_strategy_change(
        self,
        new_version: str,
        approved_by: str,
    ) -> None:
        """Approve a strategy change.

        Args:
            new_version: New strategy version
            approved_by: Who approved
        """
        self._config.strategy_version = new_version
        self._config.strategy_approved_at = datetime.now(timezone.utc)
        self._config.strategy_approved_by = approved_by
        self._config.pending_strategy_change = False

        self._save()

        logger.info(f"Strategy v{new_version} approved by {approved_by}")

    def request_strategy_change(self, new_version: str) -> None:
        """Request a strategy change (blocks live trading until approved).

        Args:
            new_version: New strategy version to approve
        """
        self._config.pending_strategy_change = True

        self._save()

        logger.warning(
            f"Strategy change to v{new_version} pending approval "
            "(live trading blocked until approved)"
        )

    def update_limits(
        self,
        max_loss_day: Optional[Decimal] = None,
        max_orders_day: Optional[int] = None,
        max_position_size: Optional[Decimal] = None,
        max_order_value: Optional[Decimal] = None,
        max_total_exposure: Optional[Decimal] = None,
        max_drawdown_percent: Optional[Decimal] = None,
    ) -> None:
        """Update risk limits.

        All parameters are optional; only provided values are updated.
        """
        if max_loss_day is not None:
            self._config.max_loss_day = max_loss_day
        if max_orders_day is not None:
            self._config.max_orders_day = max_orders_day
        if max_position_size is not None:
            self._config.max_position_size = max_position_size
        if max_order_value is not None:
            self._config.max_order_value = max_order_value
        if max_total_exposure is not None:
            self._config.max_total_exposure = max_total_exposure
        if max_drawdown_percent is not None:
            self._config.max_drawdown_percent = max_drawdown_percent

        self._save()

        logger.info("Risk limits updated")

    def get_status(self) -> dict:
        """Get comprehensive trading risk status.

        Returns:
            Status dictionary safe for API/dashboard display
        """
        mode = self.get_effective_mode()
        return {
            "effective_mode": mode.value,
            "configured_mode": self._config.mode.value,
            "is_trading_enabled": mode != TradingMode.DISABLED,
            "is_live": mode == TradingMode.LIVE,
            "is_paper": mode == TradingMode.PAPER,
            "config": self._config.to_dict(),
            "daily_state": self._daily_state.to_dict() if self._daily_state else None,
            "env_live_enabled": os.environ.get("LIVE_TRADING_ENABLED", "0") == "1",
        }
