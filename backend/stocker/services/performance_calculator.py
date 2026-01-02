"""
Performance Calculator Service.

Provides TDD-compliant performance metrics calculations matching the BacktestEngine.
Used by the performance API to compute live trading metrics.
"""
import numpy as np
import pandas as pd
from typing import Optional, Tuple, List
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics matching TDD spec."""
    # Core performance
    total_return: float = 0.0
    cagr: float = 0.0
    annualized_vol: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Drawdown
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0

    # Period returns
    return_1d: Optional[float] = None
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    ytd_return: Optional[float] = None
    mtd_return: Optional[float] = None

    # Win/loss analysis
    pct_winning_days: float = 0.0
    pct_winning_months: float = 0.0
    best_day: float = 0.0
    worst_day: float = 0.0
    best_month: float = 0.0
    worst_month: float = 0.0

    # Worst periods
    worst_1m: float = 0.0
    worst_3m: float = 0.0
    worst_12m: float = 0.0

    # Tail risk
    var_95: float = 0.0
    cvar_95: float = 0.0


class PerformanceCalculator:
    """
    Calculates performance metrics from NAV time series.
    Matches formulas from BacktestEngine for consistency.
    """

    TRADING_DAYS_PER_YEAR = 252
    RISK_FREE_RATE = 0.0

    def calculate_all_metrics(
        self,
        nav_series: pd.Series,
        initial_nav: Optional[float] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics from NAV series.

        Args:
            nav_series: Time-indexed series of NAV values
            initial_nav: Starting NAV (defaults to first value in series)

        Returns:
            PerformanceMetrics with all calculated values
        """
        metrics = PerformanceMetrics()

        if nav_series.empty or len(nav_series) < 2:
            return metrics

        nav_series = nav_series.sort_index()
        initial_nav = initial_nav or float(nav_series.iloc[0])
        final_nav = float(nav_series.iloc[-1])

        # Calculate daily returns
        daily_returns = nav_series.pct_change().dropna()

        # Basic stats
        metrics.total_return = (final_nav / initial_nav) - 1

        # CAGR
        metrics.cagr = self.calculate_cagr(nav_series, initial_nav)

        # Volatility
        metrics.annualized_vol = self.calculate_annualized_vol(daily_returns)

        # Risk-adjusted returns
        metrics.sharpe_ratio = self.calculate_sharpe(metrics.cagr, metrics.annualized_vol)
        metrics.sortino_ratio = self.calculate_sortino(daily_returns, metrics.cagr)

        # Drawdown metrics
        dd_current, dd_max, dd_duration = self.calculate_drawdown_metrics(nav_series)
        metrics.current_drawdown = dd_current
        metrics.max_drawdown = dd_max
        metrics.max_drawdown_duration_days = dd_duration

        # Calmar ratio
        if metrics.max_drawdown > 0:
            metrics.calmar_ratio = metrics.cagr / metrics.max_drawdown

        # Period returns
        metrics.return_1d = self._period_return(nav_series, 1)
        metrics.return_1w = self._period_return(nav_series, 5)
        metrics.return_1m = self._period_return(nav_series, 21)
        metrics.return_3m = self._period_return(nav_series, 63)
        metrics.return_6m = self._period_return(nav_series, 126)
        metrics.return_1y = self._period_return(nav_series, 252)
        metrics.ytd_return = self._ytd_return(nav_series)
        metrics.mtd_return = self._mtd_return(nav_series)

        # Win/loss analysis
        metrics.pct_winning_days = float((daily_returns > 0).mean() * 100)
        metrics.best_day = float(daily_returns.max()) if len(daily_returns) > 0 else 0.0
        metrics.worst_day = float(daily_returns.min()) if len(daily_returns) > 0 else 0.0

        # Monthly analysis
        monthly_returns = self.calculate_monthly_returns(nav_series)
        if len(monthly_returns) > 0:
            metrics.pct_winning_months = float((monthly_returns > 0).mean() * 100)
            metrics.best_month = float(monthly_returns.max())
            metrics.worst_month = float(monthly_returns.min())
            metrics.worst_1m = float(monthly_returns.min())

            if len(monthly_returns) >= 3:
                rolling_3m = monthly_returns.rolling(3).sum()
                metrics.worst_3m = float(rolling_3m.min())

            if len(monthly_returns) >= 12:
                rolling_12m = monthly_returns.rolling(12).sum()
                metrics.worst_12m = float(rolling_12m.min())

        # Tail risk
        metrics.var_95 = self.calculate_var(daily_returns, 0.95)
        metrics.cvar_95 = self.calculate_cvar(daily_returns, 0.95)

        return metrics

    def calculate_cagr(
        self,
        nav_series: pd.Series,
        initial_nav: Optional[float] = None
    ) -> float:
        """Calculate Compound Annual Growth Rate."""
        if nav_series.empty or len(nav_series) < 2:
            return 0.0

        initial_nav = initial_nav or float(nav_series.iloc[0])
        final_nav = float(nav_series.iloc[-1])

        n_days = len(nav_series)
        n_years = n_days / self.TRADING_DAYS_PER_YEAR

        if n_years <= 0 or initial_nav <= 0:
            return 0.0

        return (final_nav / initial_nav) ** (1 / n_years) - 1

    def calculate_annualized_vol(self, daily_returns: pd.Series) -> float:
        """Calculate annualized volatility from daily returns."""
        if daily_returns.empty:
            return 0.0
        return float(daily_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR))

    def calculate_sharpe(self, cagr: float, annualized_vol: float) -> float:
        """Calculate Sharpe ratio."""
        if annualized_vol <= 0:
            return 0.0
        excess_return = cagr - self.RISK_FREE_RATE
        return excess_return / annualized_vol

    def calculate_sortino(self, daily_returns: pd.Series, cagr: float) -> float:
        """Calculate Sortino ratio (uses downside deviation only)."""
        if daily_returns.empty:
            return 0.0

        downside_returns = daily_returns[daily_returns < 0]
        if len(downside_returns) == 0:
            return float('inf') if cagr > 0 else 0.0

        downside_std = float(downside_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR))

        if downside_std <= 0:
            return 0.0

        excess_return = cagr - self.RISK_FREE_RATE
        return excess_return / downside_std

    def calculate_drawdown_metrics(
        self,
        nav_series: pd.Series
    ) -> Tuple[float, float, int]:
        """
        Calculate drawdown metrics.

        Returns:
            Tuple of (current_drawdown, max_drawdown, max_drawdown_duration_days)
        """
        if nav_series.empty:
            return 0.0, 0.0, 0

        rolling_max = nav_series.expanding().max()
        drawdowns = (nav_series - rolling_max) / rolling_max

        current_dd = abs(float(drawdowns.iloc[-1]))
        max_dd = abs(float(drawdowns.min()))

        # Calculate max drawdown duration
        max_duration = 0
        current_duration = 0

        for dd in drawdowns:
            if dd < 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return current_dd, max_dd, max_duration

    def calculate_var(self, daily_returns: pd.Series, confidence: float = 0.95) -> float:
        """Calculate Value at Risk at specified confidence level."""
        if daily_returns.empty:
            return 0.0
        percentile = (1 - confidence) * 100
        return abs(float(np.percentile(daily_returns, percentile)))

    def calculate_cvar(self, daily_returns: pd.Series, confidence: float = 0.95) -> float:
        """Calculate Conditional Value at Risk (Expected Shortfall)."""
        if daily_returns.empty:
            return 0.0
        var = -self.calculate_var(daily_returns, confidence)
        tail_returns = daily_returns[daily_returns <= var]
        if len(tail_returns) == 0:
            return abs(var)
        return abs(float(tail_returns.mean()))

    def calculate_monthly_returns(self, nav_series: pd.Series) -> pd.Series:
        """Calculate monthly returns from NAV series."""
        if nav_series.empty:
            return pd.Series()

        monthly_nav = nav_series.resample('ME').last()  # ME = Month End
        monthly_returns = monthly_nav.pct_change().dropna()
        return monthly_returns

    def calculate_rolling_metrics(
        self,
        daily_returns: pd.Series,
        window: int = 30
    ) -> pd.DataFrame:
        """
        Calculate rolling metrics for a given window.

        Returns:
            DataFrame with rolling_sharpe, rolling_vol, rolling_max_dd
        """
        if daily_returns.empty or len(daily_returns) < window:
            return pd.DataFrame()

        rolling_vol = daily_returns.rolling(window).std() * np.sqrt(self.TRADING_DAYS_PER_YEAR)
        rolling_return = daily_returns.rolling(window).mean() * self.TRADING_DAYS_PER_YEAR
        rolling_sharpe = rolling_return / rolling_vol

        # Rolling max drawdown requires cumulative returns
        cum_returns = (1 + daily_returns).cumprod()
        rolling_max_dd = pd.Series(index=daily_returns.index, dtype=float)

        for i in range(window, len(cum_returns) + 1):
            window_slice = cum_returns.iloc[i - window:i]
            rolling_max = window_slice.expanding().max()
            drawdowns = (window_slice - rolling_max) / rolling_max
            rolling_max_dd.iloc[i - 1] = abs(drawdowns.min())

        return pd.DataFrame({
            'rolling_sharpe': rolling_sharpe,
            'rolling_vol': rolling_vol,
            'rolling_max_dd': rolling_max_dd
        })

    def _period_return(self, nav_series: pd.Series, days: int) -> Optional[float]:
        """Calculate return over specified number of trading days."""
        if len(nav_series) < days + 1:
            return None
        current = float(nav_series.iloc[-1])
        past = float(nav_series.iloc[-days - 1])
        if past <= 0:
            return None
        return (current / past) - 1

    def _ytd_return(self, nav_series: pd.Series) -> Optional[float]:
        """Calculate year-to-date return."""
        if nav_series.empty:
            return None

        current_year = nav_series.index[-1].year
        year_start_data = nav_series[nav_series.index.year == current_year]

        if year_start_data.empty:
            return None

        start_nav = float(year_start_data.iloc[0])
        current_nav = float(nav_series.iloc[-1])

        if start_nav <= 0:
            return None

        return (current_nav / start_nav) - 1

    def _mtd_return(self, nav_series: pd.Series) -> Optional[float]:
        """Calculate month-to-date return."""
        if nav_series.empty:
            return None

        current_date = nav_series.index[-1]
        current_month = current_date.month
        current_year = current_date.year

        month_data = nav_series[
            (nav_series.index.month == current_month) &
            (nav_series.index.year == current_year)
        ]

        if month_data.empty:
            return None

        start_nav = float(month_data.iloc[0])
        current_nav = float(nav_series.iloc[-1])

        if start_nav <= 0:
            return None

        return (current_nav / start_nav) - 1


# Singleton instance for convenience
performance_calculator = PerformanceCalculator()
