"""
Performance API endpoints for trading performance analytics.

Provides:
- Equity curve data for charting
- Returns metrics (CAGR, period returns, win rates)
- Risk metrics (Sharpe, Sortino, drawdown, VaR)
- Execution quality metrics
- Signal performance analysis
- Exposure history and analysis
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict
from decimal import Decimal
from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from stocker.core.database import get_db
from stocker.models import (
    PortfolioState,
    Order,
    Fill,
    Signal,
    Holding,
    PerformanceMetricsDaily,
    ExecutionMetricsDaily,
    SignalPerformance,
)
from stocker.services.performance_calculator import performance_calculator


router = APIRouter()


# ============================================================================
# Pydantic Response Schemas
# ============================================================================

class EquityCurvePoint(BaseModel):
    """Single point on equity curve."""
    date: date
    nav: float
    drawdown: float
    high_water_mark: float
    daily_return: Optional[float] = None


class MonthlyReturn(BaseModel):
    """Monthly return data point."""
    year: int
    month: int
    return_pct: float


class ReturnsMetrics(BaseModel):
    """Comprehensive returns metrics."""
    # Overall
    total_return: float
    cagr: float
    ytd_return: Optional[float]
    mtd_return: Optional[float]

    # Period returns
    return_1d: Optional[float]
    return_1w: Optional[float]
    return_1m: Optional[float]
    return_3m: Optional[float]
    return_6m: Optional[float]
    return_1y: Optional[float]

    # Win/loss
    pct_winning_days: float
    pct_winning_months: float
    best_day: float
    worst_day: float
    best_month: float
    worst_month: float

    # Monthly returns for heatmap
    monthly_returns: List[MonthlyReturn]


class DrawdownPoint(BaseModel):
    """Drawdown series data point."""
    date: date
    drawdown: float


class RiskMetrics(BaseModel):
    """Risk-related metrics."""
    # Volatility
    annualized_volatility: float
    daily_volatility: float

    # Drawdown
    current_drawdown: float
    max_drawdown: float
    avg_drawdown: float
    max_drawdown_duration_days: int

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Tail risk
    var_95: float
    cvar_95: float
    worst_1m: float
    worst_3m: float
    worst_12m: float

    # Drawdown history for chart
    drawdown_series: List[DrawdownPoint]


class SymbolExecutionStats(BaseModel):
    """Execution stats for a single symbol."""
    symbol: str
    orders: int
    filled: int
    fill_rate: float
    avg_slippage_bps: float
    total_commission: float


class ExecutionMetrics(BaseModel):
    """Execution quality metrics."""
    # Order stats
    total_orders: int
    fill_rate: float
    partial_fills: int
    rejected_orders: int

    # Cost analysis
    total_commission: float
    total_slippage: float
    avg_slippage_bps: float
    commission_as_pct_nav: float

    # Timing
    avg_fill_time_ms: Optional[int]

    # By symbol breakdown
    by_symbol: List[SymbolExecutionStats]


class SymbolSignalStats(BaseModel):
    """Signal stats for a single symbol."""
    symbol: str
    signals: int
    winners: int
    hit_rate: float
    avg_return: float
    total_pnl: float


class SignalPerformanceMetrics(BaseModel):
    """Signal performance analysis."""
    # Overall hit rate
    total_signals: int
    winning_signals: int
    losing_signals: int
    hit_rate: float

    # By direction
    long_signals: int
    long_hit_rate: float
    short_signals: int
    short_hit_rate: float

    # Avg returns
    avg_winner_return: float
    avg_loser_return: float
    profit_factor: float

    # Holding periods
    avg_holding_days: float
    avg_winner_holding_days: float
    avg_loser_holding_days: float

    # Exit analysis
    exits_by_reason: Dict[str, int]

    # Symbol breakdown
    by_symbol: List[SymbolSignalStats]


class ExposurePoint(BaseModel):
    """Exposure at a point in time."""
    date: date
    gross_exposure: float
    net_exposure: float
    long_exposure: float
    short_exposure: float


class SectorExposure(BaseModel):
    """Exposure by sector."""
    sector: str
    exposure: float
    position_count: int


class ExposureAnalysis(BaseModel):
    """Exposure analysis metrics."""
    # Current
    current_gross_exposure: float
    current_net_exposure: float
    current_long_exposure: float
    current_short_exposure: float

    # Averages
    avg_gross_exposure: float
    avg_net_exposure: float
    max_gross_exposure: float

    # Turnover
    avg_daily_turnover: float
    avg_monthly_turnover: float
    annual_turnover: float

    # Time series for charts
    exposure_history: List[ExposurePoint]

    # Sector breakdown (current)
    by_sector: List[SectorExposure]


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/equity-curve", response_model=List[EquityCurvePoint])
async def get_equity_curve(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    granularity: str = Query(default="daily", regex="^(daily|monthly)$"),
    db: AsyncSession = Depends(get_db)
) -> List[EquityCurvePoint]:
    """
    Get historical NAV data for equity curve charting.
    """
    query = select(PortfolioState).where(
        PortfolioState.portfolio_id == portfolio_id
    ).order_by(PortfolioState.date)

    if start_date:
        query = query.where(PortfolioState.date >= start_date)
    if end_date:
        query = query.where(PortfolioState.date <= end_date)

    result = await db.execute(query)
    states = result.scalars().all()

    if not states:
        return []

    # Calculate daily returns
    points = []
    prev_nav = None

    for state in states:
        daily_return = None
        if prev_nav and prev_nav > 0:
            daily_return = (float(state.nav) / prev_nav) - 1

        points.append(EquityCurvePoint(
            date=state.date,
            nav=float(state.nav),
            drawdown=float(state.drawdown),
            high_water_mark=float(state.high_water_mark),
            daily_return=daily_return
        ))
        prev_nav = float(state.nav)

    # Aggregate to monthly if requested
    if granularity == "monthly" and points:
        df = pd.DataFrame([p.dict() for p in points])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')

        monthly = df.resample('ME').last().reset_index()
        points = [
            EquityCurvePoint(
                date=row['date'].date(),
                nav=row['nav'],
                drawdown=row['drawdown'],
                high_water_mark=row['high_water_mark'],
                daily_return=row.get('daily_return')
            )
            for _, row in monthly.iterrows()
        ]

    return points


@router.get("/returns", response_model=ReturnsMetrics)
async def get_returns(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db)
) -> ReturnsMetrics:
    """
    Get comprehensive return metrics.
    """
    query = select(PortfolioState).where(
        PortfolioState.portfolio_id == portfolio_id
    ).order_by(PortfolioState.date)

    if start_date:
        query = query.where(PortfolioState.date >= start_date)
    if end_date:
        query = query.where(PortfolioState.date <= end_date)

    result = await db.execute(query)
    states = result.scalars().all()

    if not states:
        return ReturnsMetrics(
            total_return=0, cagr=0, ytd_return=None, mtd_return=None,
            return_1d=None, return_1w=None, return_1m=None,
            return_3m=None, return_6m=None, return_1y=None,
            pct_winning_days=0, pct_winning_months=0,
            best_day=0, worst_day=0, best_month=0, worst_month=0,
            monthly_returns=[]
        )

    # Build NAV series
    nav_data = {state.date: float(state.nav) for state in states}
    nav_series = pd.Series(nav_data)
    nav_series.index = pd.to_datetime(nav_series.index)

    # Calculate metrics
    metrics = performance_calculator.calculate_all_metrics(nav_series)

    # Calculate monthly returns for heatmap
    monthly_returns_series = performance_calculator.calculate_monthly_returns(nav_series)
    monthly_returns = []
    for dt, ret in monthly_returns_series.items():
        monthly_returns.append(MonthlyReturn(
            year=dt.year,
            month=dt.month,
            return_pct=float(ret) * 100
        ))

    return ReturnsMetrics(
        total_return=metrics.total_return * 100,
        cagr=metrics.cagr * 100,
        ytd_return=metrics.ytd_return * 100 if metrics.ytd_return else None,
        mtd_return=metrics.mtd_return * 100 if metrics.mtd_return else None,
        return_1d=metrics.return_1d * 100 if metrics.return_1d else None,
        return_1w=metrics.return_1w * 100 if metrics.return_1w else None,
        return_1m=metrics.return_1m * 100 if metrics.return_1m else None,
        return_3m=metrics.return_3m * 100 if metrics.return_3m else None,
        return_6m=metrics.return_6m * 100 if metrics.return_6m else None,
        return_1y=metrics.return_1y * 100 if metrics.return_1y else None,
        pct_winning_days=metrics.pct_winning_days,
        pct_winning_months=metrics.pct_winning_months,
        best_day=metrics.best_day * 100,
        worst_day=metrics.worst_day * 100,
        best_month=metrics.best_month * 100,
        worst_month=metrics.worst_month * 100,
        monthly_returns=monthly_returns
    )


@router.get("/risk", response_model=RiskMetrics)
async def get_risk_metrics(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db)
) -> RiskMetrics:
    """
    Get risk-related metrics.
    """
    query = select(PortfolioState).where(
        PortfolioState.portfolio_id == portfolio_id
    ).order_by(PortfolioState.date)

    if start_date:
        query = query.where(PortfolioState.date >= start_date)
    if end_date:
        query = query.where(PortfolioState.date <= end_date)

    result = await db.execute(query)
    states = result.scalars().all()

    if not states:
        return RiskMetrics(
            annualized_volatility=0, daily_volatility=0,
            current_drawdown=0, max_drawdown=0, avg_drawdown=0,
            max_drawdown_duration_days=0,
            sharpe_ratio=0, sortino_ratio=0, calmar_ratio=0,
            var_95=0, cvar_95=0,
            worst_1m=0, worst_3m=0, worst_12m=0,
            drawdown_series=[]
        )

    # Build NAV series
    nav_data = {state.date: float(state.nav) for state in states}
    nav_series = pd.Series(nav_data)
    nav_series.index = pd.to_datetime(nav_series.index)

    # Calculate metrics
    metrics = performance_calculator.calculate_all_metrics(nav_series)

    # Build drawdown series
    drawdown_series = [
        DrawdownPoint(date=state.date, drawdown=float(state.drawdown) * 100)
        for state in states
    ]

    # Calculate average drawdown
    avg_dd = sum(float(s.drawdown) for s in states) / len(states) if states else 0

    # Daily volatility
    daily_returns = nav_series.pct_change().dropna()
    daily_vol = float(daily_returns.std()) if len(daily_returns) > 0 else 0

    # Helper to convert NaN to 0
    def nan_to_zero(val: float) -> float:
        import math
        return 0.0 if math.isnan(val) or math.isinf(val) else val

    return RiskMetrics(
        annualized_volatility=nan_to_zero(metrics.annualized_vol * 100),
        daily_volatility=nan_to_zero(daily_vol * 100),
        current_drawdown=nan_to_zero(metrics.current_drawdown * 100),
        max_drawdown=nan_to_zero(metrics.max_drawdown * 100),
        avg_drawdown=nan_to_zero(avg_dd * 100),
        max_drawdown_duration_days=metrics.max_drawdown_duration_days,
        sharpe_ratio=nan_to_zero(metrics.sharpe_ratio),
        sortino_ratio=nan_to_zero(metrics.sortino_ratio),
        calmar_ratio=nan_to_zero(metrics.calmar_ratio),
        var_95=nan_to_zero(metrics.var_95 * 100),
        cvar_95=nan_to_zero(metrics.cvar_95 * 100),
        worst_1m=nan_to_zero(metrics.worst_1m * 100),
        worst_3m=nan_to_zero(metrics.worst_3m * 100),
        worst_12m=nan_to_zero(metrics.worst_12m * 100),
        drawdown_series=drawdown_series
    )


@router.get("/execution", response_model=ExecutionMetrics)
async def get_execution_metrics(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db)
) -> ExecutionMetrics:
    """
    Get execution quality metrics.
    """
    # Build base query for orders
    query = select(Order).where(Order.portfolio_id == portfolio_id)

    if start_date:
        query = query.where(Order.date >= start_date)
    if end_date:
        query = query.where(Order.date <= end_date)

    result = await db.execute(query)
    orders = result.scalars().all()

    if not orders:
        return ExecutionMetrics(
            total_orders=0, fill_rate=0, partial_fills=0, rejected_orders=0,
            total_commission=0, total_slippage=0, avg_slippage_bps=0,
            commission_as_pct_nav=0, avg_fill_time_ms=None, by_symbol=[]
        )

    # Aggregate order stats
    total_orders = len(orders)
    filled_orders = sum(1 for o in orders if o.status == 'FILLED')
    partial_fills = sum(1 for o in orders if o.status == 'PARTIAL')
    rejected_orders = sum(1 for o in orders if o.status in ('REJECTED', 'FAILED', 'CANCELLED'))

    fill_rate = (filled_orders + partial_fills) / total_orders * 100 if total_orders > 0 else 0

    # Get fills for commission/slippage
    order_ids = [o.order_id for o in orders]
    fill_query = select(Fill).where(Fill.order_id.in_(order_ids))
    fill_result = await db.execute(fill_query)
    fills = fill_result.scalars().all()

    total_commission = sum(float(f.commission or 0) for f in fills)
    # Slippage would need expected price vs fill price - simplified for now
    total_slippage = 0.0
    avg_slippage_bps = 0.0

    # Get current NAV for commission as % of NAV
    nav_query = select(PortfolioState).where(
        PortfolioState.portfolio_id == portfolio_id
    ).order_by(PortfolioState.date.desc()).limit(1)
    nav_result = await db.execute(nav_query)
    current_state = nav_result.scalar_one_or_none()
    current_nav = float(current_state.nav) if current_state else 1

    commission_pct = (total_commission / current_nav * 100) if current_nav > 0 else 0

    # By symbol breakdown
    symbol_stats = {}
    for order in orders:
        if order.symbol not in symbol_stats:
            symbol_stats[order.symbol] = {
                'orders': 0, 'filled': 0, 'commission': 0
            }
        symbol_stats[order.symbol]['orders'] += 1
        if order.status == 'FILLED':
            symbol_stats[order.symbol]['filled'] += 1

    for fill in fills:
        # Find order to get symbol
        order = next((o for o in orders if o.order_id == fill.order_id), None)
        if order and order.symbol in symbol_stats:
            symbol_stats[order.symbol]['commission'] += float(fill.commission or 0)

    by_symbol = [
        SymbolExecutionStats(
            symbol=symbol,
            orders=stats['orders'],
            filled=stats['filled'],
            fill_rate=stats['filled'] / stats['orders'] * 100 if stats['orders'] > 0 else 0,
            avg_slippage_bps=0,  # Would need more data
            total_commission=stats['commission']
        )
        for symbol, stats in symbol_stats.items()
    ]

    return ExecutionMetrics(
        total_orders=total_orders,
        fill_rate=fill_rate,
        partial_fills=partial_fills,
        rejected_orders=rejected_orders,
        total_commission=total_commission,
        total_slippage=total_slippage,
        avg_slippage_bps=avg_slippage_bps,
        commission_as_pct_nav=commission_pct,
        avg_fill_time_ms=None,
        by_symbol=by_symbol
    )


@router.get("/signals", response_model=SignalPerformanceMetrics)
async def get_signal_performance(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db)
) -> SignalPerformanceMetrics:
    """
    Get signal performance analysis.
    """
    # Query closed signals from signal_performance table
    query = select(SignalPerformance).where(
        SignalPerformance.portfolio_id == portfolio_id,
        SignalPerformance.exit_date.isnot(None)  # Only closed signals
    )

    if start_date:
        query = query.where(SignalPerformance.signal_date >= start_date)
    if end_date:
        query = query.where(SignalPerformance.signal_date <= end_date)

    result = await db.execute(query)
    signals = result.scalars().all()

    if not signals:
        return SignalPerformanceMetrics(
            total_signals=0, winning_signals=0, losing_signals=0, hit_rate=0,
            long_signals=0, long_hit_rate=0, short_signals=0, short_hit_rate=0,
            avg_winner_return=0, avg_loser_return=0, profit_factor=0,
            avg_holding_days=0, avg_winner_holding_days=0, avg_loser_holding_days=0,
            exits_by_reason={}, by_symbol=[]
        )

    # Aggregate stats
    total = len(signals)
    winners = [s for s in signals if s.is_winner]
    losers = [s for s in signals if not s.is_winner]

    long_signals = [s for s in signals if s.direction == 1]
    short_signals = [s for s in signals if s.direction == -1]
    long_winners = [s for s in long_signals if s.is_winner]
    short_winners = [s for s in short_signals if s.is_winner]

    # Returns
    winner_returns = [float(s.realized_return or 0) for s in winners]
    loser_returns = [float(s.realized_return or 0) for s in losers]
    avg_winner = sum(winner_returns) / len(winner_returns) if winner_returns else 0
    avg_loser = sum(loser_returns) / len(loser_returns) if loser_returns else 0

    # Profit factor
    gross_profit = sum(r for r in winner_returns if r > 0)
    gross_loss = abs(sum(r for r in loser_returns if r < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

    # Holding days
    all_holding = [s.holding_days or 0 for s in signals]
    winner_holding = [s.holding_days or 0 for s in winners]
    loser_holding = [s.holding_days or 0 for s in losers]

    # Exit reasons
    exits_by_reason = {}
    for s in signals:
        reason = s.exit_reason or 'unknown'
        exits_by_reason[reason] = exits_by_reason.get(reason, 0) + 1

    # By symbol
    symbol_stats = {}
    for s in signals:
        if s.symbol not in symbol_stats:
            symbol_stats[s.symbol] = {'signals': 0, 'winners': 0, 'returns': []}
        symbol_stats[s.symbol]['signals'] += 1
        if s.is_winner:
            symbol_stats[s.symbol]['winners'] += 1
        symbol_stats[s.symbol]['returns'].append(float(s.realized_return or 0))

    by_symbol = [
        SymbolSignalStats(
            symbol=symbol,
            signals=stats['signals'],
            winners=stats['winners'],
            hit_rate=stats['winners'] / stats['signals'] * 100 if stats['signals'] > 0 else 0,
            avg_return=sum(stats['returns']) / len(stats['returns']) * 100 if stats['returns'] else 0,
            total_pnl=sum(stats['returns']) * 100
        )
        for symbol, stats in symbol_stats.items()
    ]

    return SignalPerformanceMetrics(
        total_signals=total,
        winning_signals=len(winners),
        losing_signals=len(losers),
        hit_rate=len(winners) / total * 100 if total > 0 else 0,
        long_signals=len(long_signals),
        long_hit_rate=len(long_winners) / len(long_signals) * 100 if long_signals else 0,
        short_signals=len(short_signals),
        short_hit_rate=len(short_winners) / len(short_signals) * 100 if short_signals else 0,
        avg_winner_return=avg_winner * 100,
        avg_loser_return=avg_loser * 100,
        profit_factor=profit_factor if profit_factor != float('inf') else 999.99,
        avg_holding_days=sum(all_holding) / len(all_holding) if all_holding else 0,
        avg_winner_holding_days=sum(winner_holding) / len(winner_holding) if winner_holding else 0,
        avg_loser_holding_days=sum(loser_holding) / len(loser_holding) if loser_holding else 0,
        exits_by_reason=exits_by_reason,
        by_symbol=by_symbol
    )


@router.get("/exposure", response_model=ExposureAnalysis)
async def get_exposure_analysis(
    portfolio_id: str = Query(default="main"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    granularity: str = Query(default="daily", regex="^(daily|monthly)$"),
    db: AsyncSession = Depends(get_db)
) -> ExposureAnalysis:
    """
    Get exposure analysis metrics.
    """
    query = select(PortfolioState).where(
        PortfolioState.portfolio_id == portfolio_id
    ).order_by(PortfolioState.date)

    if start_date:
        query = query.where(PortfolioState.date >= start_date)
    if end_date:
        query = query.where(PortfolioState.date <= end_date)

    result = await db.execute(query)
    states = result.scalars().all()

    if not states:
        return ExposureAnalysis(
            current_gross_exposure=0, current_net_exposure=0,
            current_long_exposure=0, current_short_exposure=0,
            avg_gross_exposure=0, avg_net_exposure=0, max_gross_exposure=0,
            avg_daily_turnover=0, avg_monthly_turnover=0, annual_turnover=0,
            exposure_history=[], by_sector=[]
        )

    # Current exposure (from latest state)
    latest = states[-1]
    current_gross = float(latest.gross_exposure)
    current_net = float(latest.net_exposure)

    # Estimate long/short from gross and net
    # long + short = gross, long - short = net
    # 2*long = gross + net, 2*short = gross - net
    current_long = (current_gross + current_net) / 2
    current_short = (current_gross - current_net) / 2

    # Aggregate stats
    gross_exposures = [float(s.gross_exposure) for s in states]
    net_exposures = [float(s.net_exposure) for s in states]

    avg_gross = sum(gross_exposures) / len(gross_exposures)
    avg_net = sum(net_exposures) / len(net_exposures)
    max_gross = max(gross_exposures)

    # Build exposure history
    exposure_history = []
    for state in states:
        gross = float(state.gross_exposure)
        net = float(state.net_exposure)
        long_exp = (gross + net) / 2
        short_exp = (gross - net) / 2

        exposure_history.append(ExposurePoint(
            date=state.date,
            gross_exposure=gross * 100,
            net_exposure=net * 100,
            long_exposure=long_exp * 100,
            short_exposure=short_exp * 100
        ))

    # Aggregate to monthly if requested
    if granularity == "monthly" and exposure_history:
        df = pd.DataFrame([e.dict() for e in exposure_history])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        monthly = df.resample('ME').mean().reset_index()

        exposure_history = [
            ExposurePoint(
                date=row['date'].date(),
                gross_exposure=row['gross_exposure'],
                net_exposure=row['net_exposure'],
                long_exposure=row['long_exposure'],
                short_exposure=row['short_exposure']
            )
            for _, row in monthly.iterrows()
        ]

    # Calculate turnover (simplified - based on exposure changes)
    if len(states) >= 2:
        daily_turnovers = []
        for i in range(1, len(states)):
            prev_net = float(states[i-1].net_exposure)
            curr_net = float(states[i].net_exposure)
            daily_turnovers.append(abs(curr_net - prev_net))

        avg_daily_turnover = sum(daily_turnovers) / len(daily_turnovers) if daily_turnovers else 0
        avg_monthly_turnover = avg_daily_turnover * 21  # ~21 trading days/month
        annual_turnover = avg_monthly_turnover * 12
    else:
        avg_daily_turnover = 0
        avg_monthly_turnover = 0
        annual_turnover = 0

    # Sector breakdown - get from current holdings
    holdings_query = select(Holding).where(
        Holding.portfolio_id == portfolio_id,
        Holding.date == latest.date
    )
    holdings_result = await db.execute(holdings_query)
    holdings = holdings_result.scalars().all()

    # For now, return empty sector breakdown (would need to join with instrument_info)
    by_sector: List[SectorExposure] = []

    return ExposureAnalysis(
        current_gross_exposure=current_gross * 100,
        current_net_exposure=current_net * 100,
        current_long_exposure=current_long * 100,
        current_short_exposure=current_short * 100,
        avg_gross_exposure=avg_gross * 100,
        avg_net_exposure=avg_net * 100,
        max_gross_exposure=max_gross * 100,
        avg_daily_turnover=avg_daily_turnover * 100,
        avg_monthly_turnover=avg_monthly_turnover * 100,
        annual_turnover=annual_turnover * 100,
        exposure_history=exposure_history,
        by_sector=by_sector
    )
