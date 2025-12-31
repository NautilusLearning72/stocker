"""
Metrics emission system for observability.

Provides structured metrics for:
- Signal confirmation checks
- Exit rule activations (trailing stops, ATR exits)
- Diversification caps (sector, correlation)
- Order sizing decisions
- Risk control triggers

Metrics are emitted to:
1. Python logging (immediate visibility)
2. Redis stream (real-time consumers, dashboard)
3. In-memory buffer (API aggregation)
"""
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class MetricEvent:
    """Structured metric event."""
    timestamp: datetime
    category: str          # "signal", "exit", "diversification", "order", "risk"
    event_type: str        # "confirmation_passed", "trailing_stop_triggered", etc.
    symbol: Optional[str]
    portfolio_id: str
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "category": self.category,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "portfolio_id": self.portfolio_id,
            "value": self.value,
            "metadata": self.metadata
        }


class MetricsEmitter:
    """
    Emit structured metrics to multiple destinations.

    Thread-safe for use across async consumers.
    """

    # Category constants
    CATEGORY_SIGNAL = "signal"
    CATEGORY_EXIT = "exit"
    CATEGORY_DIVERSIFICATION = "diversification"
    CATEGORY_ORDER = "order"
    CATEGORY_RISK = "risk"
    CATEGORY_PIPELINE = "pipeline"

    def __init__(self, redis_client=None, buffer_size: int = 1000):
        """
        Initialize metrics emitter.

        Args:
            redis_client: Optional async Redis client for stream publishing
            buffer_size: Max events to keep in memory buffer
        """
        self.redis = redis_client
        self.buffer_size = buffer_size
        self._buffer: List[MetricEvent] = []
        self._enabled = True

    def set_redis(self, redis_client) -> None:
        """Set Redis client (for lazy initialization)."""
        self.redis = redis_client

    def enable(self) -> None:
        """Enable metrics emission."""
        self._enabled = True

    def disable(self) -> None:
        """Disable metrics emission (for testing)."""
        self._enabled = False

    def emit(
        self,
        category: str,
        event_type: str,
        value: float,
        symbol: str = None,
        portfolio_id: str = "main",
        metadata: dict = None
    ) -> MetricEvent:
        """
        Emit a metric event.

        Args:
            category: Event category (signal, exit, diversification, order, risk)
            event_type: Specific event type within category
            value: Numeric value (1.0/0.0 for boolean, actual value for numeric)
            symbol: Optional instrument symbol
            portfolio_id: Portfolio identifier
            metadata: Additional context as key-value pairs

        Returns:
            The emitted MetricEvent
        """
        if not self._enabled:
            return None

        event = MetricEvent(
            timestamp=datetime.now(timezone.utc),
            category=category,
            event_type=event_type,
            symbol=symbol,
            portfolio_id=portfolio_id,
            value=value,
            metadata=metadata or {}
        )

        # Log for immediate visibility
        meta_str = f" {metadata}" if metadata else ""
        logger.info(
            f"METRIC [{category}/{event_type}] "
            f"symbol={symbol} value={value}{meta_str}"
        )

        # Add to buffer (with size limit)
        self._buffer.append(event)
        if len(self._buffer) > self.buffer_size:
            self._buffer = self._buffer[-self.buffer_size:]

        # Publish to Redis stream if available
        if self.redis:
            try:
                # Use sync xadd for simplicity; async version available if needed
                self.redis.xadd("metrics", {
                    "data": json.dumps(event.to_dict())
                })
            except Exception as e:
                logger.warning(f"Failed to publish metric to Redis: {e}")

        return event

    async def emit_async(
        self,
        category: str,
        event_type: str,
        value: float,
        symbol: str = None,
        portfolio_id: str = "main",
        metadata: dict = None
    ) -> MetricEvent:
        """Async version of emit for use in async consumers."""
        if not self._enabled:
            return None

        event = MetricEvent(
            timestamp=datetime.now(timezone.utc),
            category=category,
            event_type=event_type,
            symbol=symbol,
            portfolio_id=portfolio_id,
            value=value,
            metadata=metadata or {}
        )

        # Log
        meta_str = f" {metadata}" if metadata else ""
        logger.info(
            f"METRIC [{category}/{event_type}] "
            f"symbol={symbol} value={value}{meta_str}"
        )

        # Buffer
        self._buffer.append(event)
        if len(self._buffer) > self.buffer_size:
            self._buffer = self._buffer[-self.buffer_size:]

        # Async Redis publish
        if self.redis:
            try:
                await self.redis.xadd("metrics", {
                    "data": json.dumps(event.to_dict())
                })
            except Exception as e:
                logger.warning(f"Failed to publish metric to Redis: {e}")

        return event

    # =========================================================================
    # Convenience methods for common metrics
    # =========================================================================

    # Signal metrics
    def signal_generated(self, symbol: str, direction: int, raw_weight: float,
                        lookback_return: float, ewma_vol: float) -> MetricEvent:
        """Record signal generation."""
        return self.emit(
            self.CATEGORY_SIGNAL, "generated", raw_weight,
            symbol=symbol,
            metadata={
                "direction": direction,
                "lookback_return": round(lookback_return, 6),
                "ewma_vol": round(ewma_vol, 6)
            }
        )

    def signal_confirmation(self, symbol: str, passed: bool, conf_type: str,
                           direction: int) -> MetricEvent:
        """Record confirmation check result."""
        return self.emit(
            self.CATEGORY_SIGNAL, "confirmation_check", 1.0 if passed else 0.0,
            symbol=symbol,
            metadata={
                "type": conf_type,
                "passed": passed,
                "direction": direction
            }
        )

    # Exit rule metrics
    def trailing_stop_triggered(self, symbol: str, atr_multiple: float,
                               peak_price: float, current_price: float) -> MetricEvent:
        """Record trailing stop trigger."""
        return self.emit(
            self.CATEGORY_EXIT, "trailing_stop_triggered", atr_multiple,
            symbol=symbol,
            metadata={
                "peak_price": peak_price,
                "current_price": current_price,
                "drawdown_pct": (peak_price - current_price) / peak_price if peak_price else 0
            }
        )

    def atr_exit_triggered(self, symbol: str, atr_multiple: float,
                          entry_price: float, current_price: float) -> MetricEvent:
        """Record ATR-based exit trigger."""
        return self.emit(
            self.CATEGORY_EXIT, "atr_exit_triggered", atr_multiple,
            symbol=symbol,
            metadata={
                "entry_price": entry_price,
                "current_price": current_price
            }
        )

    def persistence_blocked(self, symbol: str, days: int, required: int,
                           direction: int) -> MetricEvent:
        """Record persistence filter blocking a signal flip."""
        return self.emit(
            self.CATEGORY_EXIT, "persistence_blocked", days,
            symbol=symbol,
            metadata={
                "required_days": required,
                "attempted_direction": direction
            }
        )

    # Diversification metrics
    def sector_cap_applied(self, symbol: str, sector: str,
                          exposure_before: float, cap: float) -> MetricEvent:
        """Record sector cap application."""
        return self.emit(
            self.CATEGORY_DIVERSIFICATION, "sector_cap_applied", cap,
            symbol=symbol,
            metadata={
                "sector": sector,
                "exposure_before": round(exposure_before, 4),
                "cap": cap
            }
        )

    def asset_class_cap_applied(self, symbol: str, asset_class: str,
                               exposure_before: float, cap: float) -> MetricEvent:
        """Record asset class cap application."""
        return self.emit(
            self.CATEGORY_DIVERSIFICATION, "asset_class_cap_applied", cap,
            symbol=symbol,
            metadata={
                "asset_class": asset_class,
                "exposure_before": round(exposure_before, 4),
                "cap": cap
            }
        )

    def correlation_throttle_applied(self, symbol: str, correlation: float,
                                    scale_factor: float, correlated_with: str) -> MetricEvent:
        """Record correlation throttle application."""
        return self.emit(
            self.CATEGORY_DIVERSIFICATION, "correlation_throttle", correlation,
            symbol=symbol,
            metadata={
                "scale_factor": scale_factor,
                "correlated_with": correlated_with,
                "correlation": round(correlation, 4)
            }
        )

    # Order metrics
    def order_sizing(self, symbol: str, target_qty: float, actual_qty: float,
                    fractional: bool, min_notional: float) -> MetricEvent:
        """Record order sizing decision."""
        return self.emit(
            self.CATEGORY_ORDER, "sizing", actual_qty,
            symbol=symbol,
            metadata={
                "target_qty": round(target_qty, 4),
                "actual_qty": round(actual_qty, 4),
                "fractional": fractional,
                "min_notional": min_notional,
                "tracking_error": round(abs(target_qty - actual_qty), 4)
            }
        )

    def order_skipped(self, symbol: str, reason: str, notional: float) -> MetricEvent:
        """Record skipped order."""
        return self.emit(
            self.CATEGORY_ORDER, "skipped", notional,
            symbol=symbol,
            metadata={"reason": reason}
        )

    def order_created(self, symbol: str, side: str, qty: float,
                     notional: float) -> MetricEvent:
        """Record order creation."""
        return self.emit(
            self.CATEGORY_ORDER, "created", notional,
            symbol=symbol,
            metadata={"side": side, "qty": qty}
        )

    # Risk metrics
    def single_cap_applied(self, symbol: str, weight_before: float,
                          cap: float) -> MetricEvent:
        """Record single instrument cap."""
        return self.emit(
            self.CATEGORY_RISK, "single_cap_applied", cap,
            symbol=symbol,
            metadata={
                "weight_before": round(weight_before, 4),
                "cap": cap
            }
        )

    def gross_exposure_scaled(self, gross_before: float, gross_after: float,
                             scale_factor: float) -> MetricEvent:
        """Record gross exposure scaling."""
        return self.emit(
            self.CATEGORY_RISK, "gross_exposure_scaled", scale_factor,
            metadata={
                "gross_before": round(gross_before, 4),
                "gross_after": round(gross_after, 4),
                "scale_factor": round(scale_factor, 4)
            }
        )

    def drawdown_scaling(self, drawdown: float, threshold: float,
                        scale_factor: float) -> MetricEvent:
        """Record drawdown-based scaling."""
        return self.emit(
            self.CATEGORY_RISK, "drawdown_scaling", drawdown,
            metadata={
                "drawdown": round(drawdown, 4),
                "threshold": threshold,
                "scale_factor": scale_factor
            }
        )

    def kill_switch_triggered(self, daily_pnl: float, threshold: float,
                             cancelled_orders: int) -> MetricEvent:
        """Record kill switch activation."""
        return self.emit(
            self.CATEGORY_RISK, "kill_switch_triggered", daily_pnl,
            metadata={
                "daily_pnl": round(daily_pnl, 4),
                "threshold": threshold,
                "cancelled_orders": cancelled_orders
            }
        )

    # Pipeline metrics
    def batch_processed(self, stage: str, count: int, success: int,
                       failed: int, duration_ms: float) -> MetricEvent:
        """Record batch processing completion."""
        return self.emit(
            self.CATEGORY_PIPELINE, "batch_processed", count,
            metadata={
                "stage": stage,
                "success": success,
                "failed": failed,
                "duration_ms": round(duration_ms, 2)
            }
        )

    # =========================================================================
    # Aggregation methods
    # =========================================================================

    def get_buffer(self) -> List[MetricEvent]:
        """Get buffered events (for API)."""
        return list(self._buffer)

    def get_summary(self, hours: int = 24) -> dict:
        """
        Get aggregated summary of recent metrics.

        Args:
            hours: How many hours of data to include

        Returns:
            Dictionary with aggregated metrics
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = [e for e in self._buffer if e.timestamp >= cutoff]

        # Count by category and event type
        by_category: Dict[str, int] = {}
        by_event: Dict[str, int] = {}

        confirmation_passed = 0
        confirmation_total = 0

        for event in recent:
            by_category[event.category] = by_category.get(event.category, 0) + 1
            key = f"{event.category}/{event.event_type}"
            by_event[key] = by_event.get(key, 0) + 1

            # Track confirmation rate
            if event.event_type == "confirmation_check":
                confirmation_total += 1
                if event.value == 1.0:
                    confirmation_passed += 1

        return {
            "period_hours": hours,
            "total_events": len(recent),
            "by_category": by_category,
            "by_event": by_event,
            "confirmation_rate": (
                confirmation_passed / confirmation_total
                if confirmation_total > 0 else None
            ),
            "trailing_stops_triggered": by_event.get("exit/trailing_stop_triggered", 0),
            "sector_caps_applied": by_event.get("diversification/sector_cap_applied", 0),
            "correlation_throttles": by_event.get("diversification/correlation_throttle", 0),
            "orders_created": by_event.get("order/created", 0),
            "orders_skipped": by_event.get("order/skipped", 0),
        }

    def clear_buffer(self) -> int:
        """Clear buffer and return count of cleared events."""
        count = len(self._buffer)
        self._buffer = []
        return count


# Global singleton instance
metrics = MetricsEmitter()
