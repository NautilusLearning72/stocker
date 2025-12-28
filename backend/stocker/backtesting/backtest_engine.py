"""
Backtesting Engine implementing TDD metrics spec.

Required metrics (from TDD section 5.3):
- CAGR, annualised vol, Sharpe, max drawdown
- Turnover (monthly/annual)
- % winning months
- Worst 1m / 3m / 12m performance
- Exposure over time (gross/net)
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from stocker.strategy.signal_strategy import SignalStrategy, SignalConfig
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig, TargetExposure


@dataclass
class BacktestMetrics:
    """TDD-compliant backtest metrics."""
    # Core performance
    cagr: float = 0.0
    annualized_vol: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    # Additional stats
    total_return: float = 0.0
    final_equity: float = 0.0

    # Win/loss analysis
    pct_winning_months: float = 0.0
    pct_winning_days: float = 0.0

    # Worst periods
    worst_1m: float = 0.0
    worst_3m: float = 0.0
    worst_12m: float = 0.0

    # Turnover
    avg_monthly_turnover: float = 0.0
    annual_turnover: float = 0.0

    # Exposure
    avg_gross_exposure: float = 0.0
    avg_net_exposure: float = 0.0
    max_gross_exposure: float = 0.0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    metrics: BacktestMetrics
    daily_returns: pd.Series
    monthly_returns: pd.Series
    exposure_history: pd.DataFrame
    trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    signals: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def stats(self) -> Dict[str, float]:
        """Legacy compatibility - returns metrics as dict."""
        return {
            "cagr": self.metrics.cagr,
            "annualized_vol": self.metrics.annualized_vol,
            "sharpe_ratio": self.metrics.sharpe_ratio,
            "max_drawdown": self.metrics.max_drawdown,
            "total_return": self.metrics.total_return,
            "final_equity": self.metrics.final_equity,
            "pct_winning_months": self.metrics.pct_winning_months,
            "worst_1m": self.metrics.worst_1m,
            "worst_3m": self.metrics.worst_3m,
            "worst_12m": self.metrics.worst_12m,
            "avg_monthly_turnover": self.metrics.avg_monthly_turnover,
            "annual_turnover": self.metrics.annual_turnover,
            "avg_gross_exposure": self.metrics.avg_gross_exposure,
            "avg_net_exposure": self.metrics.avg_net_exposure,
        }

class BacktestEngine:
    """
    Simulates strategy performance on historical data.
    Implements TDD-compliant metrics calculation.
    """

    TRADING_DAYS_PER_YEAR = 252
    RISK_FREE_RATE = 0.0  # Assume 0 for simplicity

    def __init__(
        self,
        signal_config: SignalConfig,
        risk_config: RiskConfig,
        initial_capital: float = 100000.0,
        slippage_bps: float = 5.0,
        commission_per_trade: float = 1.0
    ):
        self.signal_strategy = SignalStrategy(signal_config)
        self.portfolio_optimizer = PortfolioOptimizer(risk_config)
        self.initial_capital = initial_capital
        self.slippage_bps = slippage_bps
        self.commission_per_trade = commission_per_trade

    def run(self, market_data: Dict[str, pd.DataFrame]) -> BacktestResult:
        """
        Run backtest on provided market data.
        market_data: Dict mapping symbol -> DataFrame(index=Date, columns=[adj_close])
        """
        # Align all dates
        all_dates = sorted(list(set().union(*[df.index for df in market_data.values()])))
        portfolio_value = [self.initial_capital]
        positions = {sym: 0.0 for sym in market_data.keys()}
        prev_positions = positions.copy()

        # Track history
        history = []
        exposure_history = []
        turnover_history = []

        # Simple daily loop
        for i, current_date in enumerate(all_dates):
            if i < self.signal_strategy.config.lookback_days:
                continue

            # 1. Generate Signals
            signals = []
            for symbol, df in market_data.items():
                if current_date in df.index:
                    hist_slice = df.loc[:current_date]
                    if len(hist_slice) > self.signal_strategy.config.lookback_days:
                        try:
                            sig = self.signal_strategy.compute_signal(symbol, hist_slice)
                            signals.append(sig)
                        except ValueError:
                            pass

            # 2. Optimize Portfolio
            current_equity = portfolio_value[-1]
            peak_equity = max(portfolio_value)
            drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0

            targets = self.portfolio_optimizer.compute_targets(signals, drawdown)

            # 3. Calculate exposure metrics
            new_positions = {t.symbol: t.target_exposure for t in targets}
            gross_exposure = sum(abs(v) for v in new_positions.values())
            net_exposure = sum(new_positions.values())

            # Calculate turnover
            turnover = sum(abs(new_positions.get(s, 0) - prev_positions.get(s, 0))
                          for s in set(new_positions.keys()) | set(prev_positions.keys()))

            exposure_history.append({
                "date": current_date,
                "gross_exposure": gross_exposure,
                "net_exposure": net_exposure
            })
            turnover_history.append(turnover)

            # 4. Simulate Next Day Return
            daily_pnl = 0.0
            if i < len(all_dates) - 1:
                next_date = all_dates[i + 1]

                for symbol, exposure in positions.items():
                    df = market_data[symbol]
                    if current_date in df.index and next_date in df.index:
                        ret = (df.loc[next_date, 'adj_close'] / df.loc[current_date, 'adj_close']) - 1
                        position_value = exposure * current_equity
                        daily_pnl += position_value * ret

                # Apply transaction costs
                trade_cost = self._calculate_trade_cost(turnover, current_equity)
                daily_pnl -= trade_cost

                new_equity = current_equity + daily_pnl
                portfolio_value.append(new_equity)

                # Update positions
                prev_positions = positions.copy()
                positions = new_positions

                history.append({
                    "date": next_date,
                    "equity": new_equity,
                    "drawdown": drawdown,
                    "daily_pnl": daily_pnl,
                    "daily_return": daily_pnl / current_equity if current_equity > 0 else 0
                })

        # Build result DataFrames
        results_df = pd.DataFrame(history)
        if not results_df.empty:
            results_df = results_df.set_index("date")

        exposure_df = pd.DataFrame(exposure_history)
        if not exposure_df.empty:
            exposure_df = exposure_df.set_index("date")

        # Calculate all TDD metrics
        metrics = self._calculate_metrics(
            results_df,
            exposure_df,
            turnover_history,
            portfolio_value
        )

        # Build return series
        daily_returns = results_df['daily_return'] if 'daily_return' in results_df.columns else pd.Series()
        monthly_returns = self._calculate_monthly_returns(results_df)

        return BacktestResult(
            equity_curve=results_df['equity'] if 'equity' in results_df.columns else pd.Series(),
            metrics=metrics,
            daily_returns=daily_returns,
            monthly_returns=monthly_returns,
            exposure_history=exposure_df,
            trades=pd.DataFrame(),
            signals=pd.DataFrame()
        )

    def _calculate_trade_cost(self, turnover: float, equity: float) -> float:
        """Calculate transaction costs based on turnover."""
        # Slippage as fraction of traded value
        slippage_cost = turnover * equity * (self.slippage_bps / 10000)
        # Flat commission per rebalance (simplified)
        commission_cost = self.commission_per_trade if turnover > 0 else 0
        return slippage_cost + commission_cost

    def _calculate_metrics(
        self,
        results_df: pd.DataFrame,
        exposure_df: pd.DataFrame,
        turnover_history: List[float],
        portfolio_value: List[float]
    ) -> BacktestMetrics:
        """Calculate TDD-compliant metrics."""
        metrics = BacktestMetrics()

        if results_df.empty or len(portfolio_value) < 2:
            return metrics

        # Basic stats
        metrics.final_equity = portfolio_value[-1]
        metrics.total_return = (portfolio_value[-1] / self.initial_capital) - 1

        # Daily returns
        daily_returns = results_df['daily_return'].dropna()
        if len(daily_returns) == 0:
            return metrics

        # CAGR
        n_years = len(daily_returns) / self.TRADING_DAYS_PER_YEAR
        if n_years > 0:
            metrics.cagr = (metrics.final_equity / self.initial_capital) ** (1 / n_years) - 1

        # Annualized volatility
        metrics.annualized_vol = daily_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR)

        # Sharpe ratio
        if metrics.annualized_vol > 0:
            excess_return = metrics.cagr - self.RISK_FREE_RATE
            metrics.sharpe_ratio = excess_return / metrics.annualized_vol

        # Max drawdown (proper calculation)
        equity_curve = results_df['equity']
        rolling_max = equity_curve.expanding().max()
        drawdowns = (equity_curve - rolling_max) / rolling_max
        metrics.max_drawdown = abs(drawdowns.min()) if len(drawdowns) > 0 else 0

        # Win rate
        metrics.pct_winning_days = (daily_returns > 0).mean() * 100

        # Monthly returns analysis
        monthly_returns = self._calculate_monthly_returns(results_df)
        if len(monthly_returns) > 0:
            metrics.pct_winning_months = (monthly_returns > 0).mean() * 100
            metrics.worst_1m = monthly_returns.min()

        # Rolling 3m and 12m worst
        if len(monthly_returns) >= 3:
            rolling_3m = monthly_returns.rolling(3).sum()
            metrics.worst_3m = rolling_3m.min()
        if len(monthly_returns) >= 12:
            rolling_12m = monthly_returns.rolling(12).sum()
            metrics.worst_12m = rolling_12m.min()

        # Turnover metrics
        if turnover_history:
            # Group by month for monthly turnover
            results_df_copy = results_df.copy()
            results_df_copy['turnover'] = turnover_history[:len(results_df)]
            monthly_turnover = results_df_copy.resample('M')['turnover'].sum()
            metrics.avg_monthly_turnover = monthly_turnover.mean()
            metrics.annual_turnover = metrics.avg_monthly_turnover * 12

        # Exposure metrics
        if not exposure_df.empty:
            metrics.avg_gross_exposure = exposure_df['gross_exposure'].mean()
            metrics.avg_net_exposure = exposure_df['net_exposure'].mean()
            metrics.max_gross_exposure = exposure_df['gross_exposure'].max()

        return metrics

    def _calculate_monthly_returns(self, results_df: pd.DataFrame) -> pd.Series:
        """Calculate monthly returns from daily data."""
        if results_df.empty or 'equity' not in results_df.columns:
            return pd.Series()

        monthly_equity = results_df['equity'].resample('M').last()
        monthly_returns = monthly_equity.pct_change().dropna()
        return monthly_returns
