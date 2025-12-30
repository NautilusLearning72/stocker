"""
Portfolio initialization and management tasks.

Provides bootstrap functionality to create initial PortfolioState
with starting NAV before trading can begin.
"""
import asyncio
import logging
from datetime import date
from decimal import Decimal

from stocker.scheduler.celery_app import app
from stocker.core.database import AsyncSessionLocal
from stocker.core.config import settings
from stocker.models.portfolio_state import PortfolioState
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _initialize_portfolio_async(
    portfolio_id: str,
    starting_nav: float,
    starting_cash: float
) -> dict:
    """Async implementation of portfolio initialization."""
    async with AsyncSessionLocal() as session:
        # Check if portfolio state already exists
        stmt = select(PortfolioState).where(
            PortfolioState.portfolio_id == portfolio_id
        ).order_by(PortfolioState.date.desc()).limit(1)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(
                f"Portfolio {portfolio_id} already initialized: "
                f"NAV={existing.nav}, Cash={existing.cash}"
            )
            return {
                "status": "exists",
                "portfolio_id": portfolio_id,
                "nav": float(existing.nav),
                "cash": float(existing.cash),
                "date": str(existing.date)
            }

        # Create initial portfolio state
        initial_state = PortfolioState(
            portfolio_id=portfolio_id,
            date=date.today(),
            nav=Decimal(str(starting_nav)),
            cash=Decimal(str(starting_cash)),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            drawdown=Decimal("0"),
            high_water_mark=Decimal(str(starting_nav))
        )
        session.add(initial_state)
        await session.commit()

        logger.info(
            f"Initialized portfolio {portfolio_id}: "
            f"NAV={starting_nav}, Cash={starting_cash}"
        )

        return {
            "status": "created",
            "portfolio_id": portfolio_id,
            "nav": starting_nav,
            "cash": starting_cash,
            "date": str(date.today())
        }


@app.task(name="stocker.tasks.portfolio.initialize_portfolio")
def initialize_portfolio(
    portfolio_id: str = "main",
    starting_nav: float = None,
    starting_cash: float = None
):
    """
    Initialize a portfolio with starting capital.

    This must be run before the pipeline can process fills,
    as LedgerConsumer requires an existing PortfolioState.

    Args:
        portfolio_id: Unique identifier for the portfolio (default: "main")
        starting_nav: Initial Net Asset Value (default: from settings)
        starting_cash: Initial cash balance (default: same as starting_nav)

    Returns:
        dict with status and portfolio details
    """
    # Use settings defaults if not provided
    if starting_nav is None:
        starting_nav = getattr(settings, 'STARTING_NAV', 100000.0)
    if starting_cash is None:
        starting_cash = starting_nav  # All cash initially

    return asyncio.run(_initialize_portfolio_async(
        portfolio_id, starting_nav, starting_cash
    ))


@app.task(name="stocker.tasks.portfolio.reset_portfolio")
def reset_portfolio(portfolio_id: str = "main"):
    """
    Reset a portfolio to initial state (for testing/paper trading reset).

    WARNING: This deletes all holdings, orders, fills and resets NAV to starting value.
    """
    async def _reset():
        from stocker.models.holding import Holding
        from stocker.models.order import Order
        from stocker.models.fill import Fill
        from sqlalchemy import delete

        async with AsyncSessionLocal() as session:
            # Get order IDs for this portfolio to delete related fills
            order_stmt = select(Order.order_id).where(Order.portfolio_id == portfolio_id)
            order_result = await session.execute(order_stmt)
            order_ids = [row[0] for row in order_result.fetchall()]

            # Delete fills first (foreign key constraint)
            if order_ids:
                await session.execute(
                    delete(Fill).where(Fill.order_id.in_(order_ids))
                )
                logger.info(f"Deleted fills for {len(order_ids)} orders")

            # Delete orders
            await session.execute(
                delete(Order).where(Order.portfolio_id == portfolio_id)
            )

            # Delete holdings
            await session.execute(
                delete(Holding).where(Holding.portfolio_id == portfolio_id)
            )

            # Delete portfolio states
            await session.execute(
                delete(PortfolioState).where(
                    PortfolioState.portfolio_id == portfolio_id
                )
            )

            await session.commit()
            logger.info(f"Reset portfolio {portfolio_id}: cleared all data")

        # Re-initialize with defaults
        return await _initialize_portfolio_async(
            portfolio_id,
            getattr(settings, 'STARTING_NAV', 100000.0),
            getattr(settings, 'STARTING_NAV', 100000.0)
        )

    return asyncio.run(_reset())
