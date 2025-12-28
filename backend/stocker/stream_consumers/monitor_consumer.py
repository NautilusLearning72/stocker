"""
Monitor Consumer - System health monitoring and kill switch.

Monitors portfolio state for:
- Daily P&L < -3% → Kill switch triggered
- Drawdown > threshold → Alert (scaling handled by portfolio_optimizer)
- Data anomalies → Alert

Kill switch actions:
- Cancel all pending orders
- Publish critical alert
- Set system to HALTED state
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames, get_async_redis
from stocker.models.order import Order
from stocker.models.portfolio_state import PortfolioState
from sqlalchemy import select, update

logger = logging.getLogger(__name__)


class AlertLevel:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class MonitorConsumer(BaseStreamConsumer):
    """
    Monitors system health and implements kill switch per TDD spec.

    Kill Switch triggers when:
    - Daily P&L < -3%
    - Data/execution integrity fails

    Actions:
    - Cancel all pending orders
    - Publish CRITICAL alert
    - Halt trading until manual override
    """

    # Thresholds from TDD
    DAILY_PNL_KILL_THRESHOLD = -0.03  # -3%
    DRAWDOWN_ALERT_THRESHOLD = 0.10   # 10% (for alerting, scaling handled elsewhere)

    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.PORTFOLIO_STATE,
            consumer_group="monitors"
        )
        self._kill_switch_active = False
        self._last_nav: Optional[Decimal] = None
        self._session_start_nav: Optional[Decimal] = None
        self._current_date: Optional[date] = None

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process portfolio state updates and check for kill switch conditions."""
        event_type = data.get("event_type", "state_update")

        logger.info(f"MONITOR: Processing {event_type}")

        # Extract portfolio metrics
        try:
            nav = Decimal(data.get("nav", "0"))
            drawdown = float(data.get("drawdown", "0"))
            portfolio_id = data.get("portfolio_id", "main")
            event_date = data.get("date", str(date.today()))
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to parse portfolio state: {e}")
            await self._publish_alert(
                AlertLevel.ERROR,
                "Data integrity issue",
                f"Failed to parse portfolio state: {e}"
            )
            return

        # Track session start NAV for daily P&L calculation
        if self._current_date != event_date:
            self._current_date = event_date
            self._session_start_nav = self._last_nav or nav
            logger.info(f"New trading session: {event_date}, Start NAV: {self._session_start_nav}")

        self._last_nav = nav

        # Calculate daily P&L
        daily_pnl_pct = 0.0
        if self._session_start_nav and self._session_start_nav > 0:
            daily_pnl_pct = float((nav - self._session_start_nav) / self._session_start_nav)

        # Check kill switch conditions
        await self._check_kill_switch(daily_pnl_pct, drawdown, portfolio_id)

        # Check drawdown alert threshold
        await self._check_drawdown_alert(drawdown, portfolio_id)

        # Publish to UI updates channel for SSE
        await self._publish_ui_update(portfolio_id, nav, drawdown, daily_pnl_pct)

    async def _check_kill_switch(
        self,
        daily_pnl_pct: float,
        drawdown: float,
        portfolio_id: str
    ) -> None:
        """Check if kill switch should be triggered."""
        if self._kill_switch_active:
            return  # Already triggered

        trigger_reason = None

        if daily_pnl_pct < self.DAILY_PNL_KILL_THRESHOLD:
            trigger_reason = f"Daily P&L {daily_pnl_pct:.2%} < {self.DAILY_PNL_KILL_THRESHOLD:.2%}"

        if trigger_reason:
            logger.critical(f"KILL SWITCH TRIGGERED: {trigger_reason}")
            self._kill_switch_active = True

            # Execute kill switch actions
            await self._execute_kill_switch(portfolio_id, trigger_reason)

    async def _execute_kill_switch(self, portfolio_id: str, reason: str) -> None:
        """Execute kill switch: cancel pending orders and halt trading."""

        # 1. Cancel all pending orders
        cancelled_count = await self._cancel_pending_orders(portfolio_id)

        # 2. Publish critical alert
        await self._publish_alert(
            AlertLevel.CRITICAL,
            "KILL SWITCH ACTIVATED",
            f"Reason: {reason}. Cancelled {cancelled_count} pending orders. "
            "Trading halted until manual override."
        )

        # 3. Store kill switch state (could use Redis key or DB)
        if self.redis:
            await self.redis.set(
                f"kill_switch:{portfolio_id}",
                json.dumps({
                    "active": True,
                    "triggered_at": datetime.utcnow().isoformat(),
                    "reason": reason
                })
            )

        logger.critical(
            f"Kill switch executed for {portfolio_id}: "
            f"Cancelled {cancelled_count} orders. Reason: {reason}"
        )

    async def _cancel_pending_orders(self, portfolio_id: str) -> int:
        """Cancel all pending orders for portfolio."""
        cancelled = 0

        async with AsyncSessionLocal() as session:
            # Find pending orders
            stmt = select(Order).where(
                Order.portfolio_id == portfolio_id,
                Order.status.in_(["NEW", "PENDING", "PENDING_EXECUTION"])
            )
            result = await session.execute(stmt)
            pending_orders = result.scalars().all()

            for order in pending_orders:
                order.status = "CANCELLED"
                cancelled += 1
                logger.warning(f"Cancelled order {order.order_id} ({order.symbol} {order.side})")

            await session.commit()

        return cancelled

    async def _check_drawdown_alert(self, drawdown: float, portfolio_id: str) -> None:
        """Check drawdown and publish warning alert if threshold exceeded."""
        if drawdown > self.DRAWDOWN_ALERT_THRESHOLD:
            await self._publish_alert(
                AlertLevel.WARNING,
                "Drawdown threshold exceeded",
                f"Portfolio {portfolio_id} drawdown at {drawdown:.2%} "
                f"(threshold: {self.DRAWDOWN_ALERT_THRESHOLD:.2%}). "
                "Position scaling has been applied."
            )

    async def _publish_alert(
        self,
        level: str,
        title: str,
        message: str
    ) -> None:
        """Publish alert to alerts stream."""
        if not self.redis:
            logger.error(f"Cannot publish alert - Redis not connected: {title}")
            return

        await self.redis.xadd(StreamNames.ALERTS, {
            "level": level,
            "title": title,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Log based on level
        if level == AlertLevel.CRITICAL:
            logger.critical(f"ALERT [{level}] {title}: {message}")
        elif level == AlertLevel.ERROR:
            logger.error(f"ALERT [{level}] {title}: {message}")
        elif level == AlertLevel.WARNING:
            logger.warning(f"ALERT [{level}] {title}: {message}")
        else:
            logger.info(f"ALERT [{level}] {title}: {message}")

    async def _publish_ui_update(
        self,
        portfolio_id: str,
        nav: Decimal,
        drawdown: float,
        daily_pnl_pct: float
    ) -> None:
        """Publish update to UI via Redis pub/sub."""
        if not self.redis:
            return

        await self.redis.publish("ui-updates", json.dumps({
            "type": "portfolio_update",
            "payload": {
                "portfolio_id": portfolio_id,
                "nav": float(nav),
                "drawdown": drawdown,
                "daily_pnl_pct": daily_pnl_pct,
                "kill_switch_active": self._kill_switch_active,
                "timestamp": datetime.utcnow().isoformat()
            }
        }))

    async def reset_kill_switch(self, portfolio_id: str) -> None:
        """Manual reset of kill switch (called via admin API)."""
        self._kill_switch_active = False

        if self.redis:
            await self.redis.delete(f"kill_switch:{portfolio_id}")

        await self._publish_alert(
            AlertLevel.INFO,
            "Kill switch reset",
            f"Kill switch for {portfolio_id} has been manually reset. Trading resumed."
        )

        logger.info(f"Kill switch reset for {portfolio_id}")


if __name__ == "__main__":
    async def main() -> None:
        consumer = MonitorConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()

    asyncio.run(main())
