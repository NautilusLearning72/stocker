from dataclasses import dataclass
from typing import Dict, List, Optional, Literal
import numpy as np
import pandas as pd
from datetime import date

from stocker.core.metrics import metrics


@dataclass
class SignalConfig:
    """Configuration for signal strategy."""
    strategy_name: str = "vol_target_trend_v1"
    lookback_days: int = 126
    ewma_lambda: float = 0.94
    target_vol: float = 0.10

    # Confirmation settings
    confirmation_enabled: bool = False
    confirmation_type: Literal["donchian", "dual_ma", "both"] = "donchian"
    donchian_period: int = 20      # 20-day high/low channel
    ma_fast_period: int = 50       # Fast moving average period
    ma_slow_period: int = 200      # Slow moving average period

@dataclass
class Signal:
    symbol: str
    date: date
    metrics: Dict[str, float]
    raw_weight: float
    direction: int
    strategy_version: str

class SignalStrategy:
    """
    Implements Volatility-Targeted Trend Following.

    1. Trend: 126-day return sign (+1/-1)
    2. Confirmation (optional): Donchian breakout or dual MA cross
    3. Volatility: EWMA annualized vol
    4. Sizing: Target Vol / Realized Vol
    """

    def __init__(self, config: SignalConfig):
        self.config = config

    def _check_donchian_confirmation(self, prices: pd.DataFrame, direction: int) -> bool:
        """
        Check if price confirms trend via Donchian channel breakout.

        For longs: Current price >= N-day high (breakout above)
        For shorts: Current price <= N-day low (breakout below)
        """
        period = self.config.donchian_period

        if len(prices) < period + 1:
            return True  # Not enough data, assume confirmed

        current = prices['adj_close'].iloc[-1]

        # Get the high/low of the lookback period (excluding current bar)
        lookback = prices['adj_close'].iloc[-period-1:-1]

        if direction == 1:  # Long - price at or above N-day high
            channel_high = lookback.max()
            return current >= channel_high
        else:  # Short - price at or below N-day low
            channel_low = lookback.min()
            return current <= channel_low

    def _check_ma_confirmation(self, prices: pd.DataFrame, direction: int) -> bool:
        """
        Check if moving averages confirm trend direction.

        For longs: Fast MA > Slow MA
        For shorts: Fast MA < Slow MA
        """
        fast_period = self.config.ma_fast_period
        slow_period = self.config.ma_slow_period

        if len(prices) < slow_period:
            return True  # Not enough data, assume confirmed

        fast_ma = prices['adj_close'].rolling(fast_period).mean().iloc[-1]
        slow_ma = prices['adj_close'].rolling(slow_period).mean().iloc[-1]

        if pd.isna(fast_ma) or pd.isna(slow_ma):
            return True  # Not enough data for MAs

        if direction == 1:  # Long - fast above slow
            return fast_ma > slow_ma
        else:  # Short - fast below slow
            return fast_ma < slow_ma

    def _is_trend_confirmed(self, prices: pd.DataFrame, direction: int, symbol: str) -> bool:
        """
        Master confirmation check.

        Returns True if trend is confirmed (or confirmation disabled).
        Emits metrics for confirmation checks.
        """
        if not self.config.confirmation_enabled:
            return True  # No confirmation required

        conf_type = self.config.confirmation_type
        confirmed = False

        if conf_type == "donchian":
            confirmed = self._check_donchian_confirmation(prices, direction)
        elif conf_type == "dual_ma":
            confirmed = self._check_ma_confirmation(prices, direction)
        elif conf_type == "both":
            donchian_ok = self._check_donchian_confirmation(prices, direction)
            ma_ok = self._check_ma_confirmation(prices, direction)
            confirmed = donchian_ok and ma_ok
        else:
            confirmed = True  # Unknown type, default to confirmed

        # Emit metric
        metrics.signal_confirmation(symbol, confirmed, conf_type, direction)

        return confirmed

    def compute_signal(self, symbol: str, prices: pd.DataFrame) -> Signal:
        """
        Compute signal for a single symbol given historical prices.
        Expects DataFrame with 'adj_close' column and DatetimeIndex.
        """
        if len(prices) < self.config.lookback_days + 1:
            raise ValueError(f"Insufficient data for {symbol}: {len(prices)} rows")
            
        # Ensure sorted by date
        prices = prices.sort_index()
        
        # Calculate daily returns
        returns = prices['adj_close'].pct_change().dropna()
        
        # Calculate EWMA Volatility
        vol = self._compute_ewma_volatility(returns.values, self.config.ewma_lambda)
        annualized_vol = vol * np.sqrt(252)
        
        # Calculate Trend (Lookback Return)
        # Using simple return: (Price_t / Price_t-N) - 1
        current_price = prices['adj_close'].iloc[-1]
        lookback_price = prices['adj_close'].iloc[-(self.config.lookback_days + 1)]
        lookback_return = (current_price / lookback_price) - 1
        
        # Direction: +1 long, -1 short, 0 flat (when return is exactly zero)
        if lookback_return > 0:
            direction = 1
        elif lookback_return < 0:
            direction = -1
        else:
            direction = 0  # Exactly flat - no trend signal

        # Check trend confirmation (if enabled and we have a direction)
        confirmed = (
            self._is_trend_confirmed(prices, direction, symbol)
            if direction != 0
            else False
        )

        # Calculate Target Weight (Inverse Volatility Sizing)
        # Direction is binary (+1/-1/0) but weight is continuous based on vol
        # We handle caps in the PortfolioOptimizer, here gives raw theoretical weight
        if direction == 0:
            # No trend - go flat
            raw_weight = 0.0
            final_direction = 0
        elif not confirmed:
            # Trend not confirmed - go flat
            raw_weight = 0.0
            final_direction = 0
        elif annualized_vol < 1e-6:
            # Avoid div by zero on near-zero volatility
            raw_weight = 0.0
            final_direction = 0
        else:
            # Inverse volatility sizing: lower vol = larger position
            raw_weight = (self.config.target_vol / annualized_vol) * direction
            final_direction = direction

        # Emit signal generation metric
        metrics.signal_generated(
            symbol=symbol,
            direction=final_direction,
            raw_weight=raw_weight,
            lookback_return=lookback_return,
            ewma_vol=annualized_vol
        )

        return Signal(
            symbol=symbol,
            date=prices.index[-1].date(),
            strategy_version=self.config.strategy_name,
            direction=final_direction,
            raw_weight=raw_weight,
            metrics={
                "lookback_return": round(lookback_return, 6),
                "ewma_vol": round(annualized_vol, 6),
                "daily_vol": round(vol, 6),
                "trend_direction": direction,  # Original trend before confirmation
                "confirmation_passed": confirmed
            }
        )

    def _compute_ewma_volatility(self, returns: np.ndarray, lambda_: float) -> float:
        """
        Compute EWMA volatility recursively.
        sigma_t^2 = lambda * sigma_t-1^2 + (1-lambda) * r_t^2
        """
        T = len(returns)
        variance = np.var(returns) # Initialize with simple variance
        
        for t in range(T):
            variance = lambda_ * variance + (1 - lambda_) * returns[t]**2
            
        return np.sqrt(variance)
