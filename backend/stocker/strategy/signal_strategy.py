from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from datetime import date

@dataclass
class SignalConfig:
    strategy_name: str = "vol_target_trend_v1"
    lookback_days: int = 126
    ewma_lambda: float = 0.94
    target_vol: float = 0.10

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
    2. Volatility: EWMA annualized vol
    3. Sizing: Target Vol / Realized Vol
    """
    
    def __init__(self, config: SignalConfig):
        self.config = config

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
        
        direction = 1 if lookback_return > 0 else -1
        
        # Calculate Target Weight (Inverse Volatility)
        # We handle caps in the PortfolioOptimizer, here gives raw theoretical weight
        # If returns are flat/zero vol, avoid div by zero
        if annualized_vol < 1e-6:
             raw_weight = 0.0
        else:
             raw_weight = (self.config.target_vol / annualized_vol) * direction
             
        return Signal(
            symbol=symbol,
            date=prices.index[-1].date(),
            strategy_version=self.config.strategy_name,
            direction=direction,
            raw_weight=raw_weight,
            metrics={
                "lookback_return": round(lookback_return, 6),
                "ewma_vol": round(annualized_vol, 6),
                "daily_vol": round(vol, 6)
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
