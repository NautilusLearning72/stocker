"""
Exit rule engine for position management.

Provides:
- Trailing stops based on ATR
- ATR-based exits from entry price
- Persistence filters for signal flips
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import date
import pandas as pd
import numpy as np

from stocker.core.metrics import metrics


@dataclass
class ExitConfig:
    """Configuration for exit rules."""
    enabled: bool = False
    trailing_stop_atr: float = 3.0  # Exit if retraces X ATRs from peak
    atr_exit_multiple: float = 2.0  # Exit if moves Y ATRs against entry
    atr_period: int = 14
    persistence_days: int = 3  # Days signal must persist before flip


@dataclass
class PositionStateData:
    """
    Position state data for exit evaluation.

    Mirror of the PositionState model for use in strategy code.
    """
    symbol: str
    direction: int  # -1, 0, 1
    entry_date: Optional[date]
    entry_price: Optional[float]
    peak_price: Optional[float]
    trough_price: Optional[float]
    pending_direction: Optional[int]
    signal_flip_date: Optional[date]
    consecutive_flip_days: int
    entry_atr: Optional[float]


class ExitRuleEngine:
    """
    Evaluate exit rules against current positions.

    Determines whether positions should be exited based on:
    - Trailing stop (price retraces X ATRs from peak)
    - ATR exit (price moves Y ATRs against entry)
    - Persistence filter (signal must persist Z days before flip)
    """

    def __init__(self, config: ExitConfig):
        self.config = config

    def compute_atr(self, prices: pd.DataFrame) -> float:
        """
        Calculate Average True Range.

        Args:
            prices: DataFrame with 'high', 'low', 'adj_close' columns

        Returns:
            ATR value
        """
        if 'high' not in prices.columns or 'low' not in prices.columns:
            # Fallback: estimate from adj_close volatility
            returns = prices['adj_close'].pct_change().dropna()
            if len(returns) < self.config.atr_period:
                return prices['adj_close'].iloc[-1] * 0.02  # 2% estimate
            return returns.std() * prices['adj_close'].iloc[-1] * np.sqrt(252 / self.config.atr_period)

        high = prices['high']
        low = prices['low']
        close = prices['adj_close'].shift(1)

        # True Range = max of (high-low, |high-prev_close|, |low-prev_close|)
        tr = pd.concat([
            high - low,
            (high - close).abs(),
            (low - close).abs()
        ], axis=1).max(axis=1)

        # ATR = rolling mean of TR
        atr = tr.rolling(self.config.atr_period).mean().iloc[-1]

        if pd.isna(atr):
            # Not enough data, use simple estimate
            return prices['adj_close'].iloc[-1] * 0.02

        return float(atr)

    def check_trailing_stop(
        self,
        position: PositionStateData,
        current_price: float,
        atr: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if trailing stop is triggered.

        For longs: Exit if price drops X ATRs below peak
        For shorts: Exit if price rises X ATRs above trough

        Returns:
            (triggered, reason)
        """
        if position.direction == 0:
            return False, None

        threshold = self.config.trailing_stop_atr * atr

        if position.direction == 1:  # Long
            if position.peak_price is None:
                return False, None
            drawdown = position.peak_price - current_price
            if drawdown > threshold:
                # Emit metric
                metrics.trailing_stop_triggered(
                    symbol=position.symbol,
                    atr_multiple=self.config.trailing_stop_atr,
                    peak_price=position.peak_price,
                    current_price=current_price
                )
                return True, f"Trailing stop: {drawdown/atr:.1f}x ATR from peak"

        elif position.direction == -1:  # Short
            if position.trough_price is None:
                return False, None
            runup = current_price - position.trough_price
            if runup > threshold:
                # Emit metric
                metrics.trailing_stop_triggered(
                    symbol=position.symbol,
                    atr_multiple=self.config.trailing_stop_atr,
                    peak_price=position.trough_price,  # Use trough as "peak" for shorts
                    current_price=current_price
                )
                return True, f"Trailing stop: {runup/atr:.1f}x ATR from trough"

        return False, None

    def check_atr_exit(
        self,
        position: PositionStateData,
        current_price: float,
        atr: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if ATR-based exit from entry is triggered.

        Exit if price moves Y ATRs against the entry price.

        Returns:
            (triggered, reason)
        """
        if position.direction == 0 or position.entry_price is None:
            return False, None

        threshold = self.config.atr_exit_multiple * atr

        if position.direction == 1:  # Long
            loss = position.entry_price - current_price
            if loss > threshold:
                metrics.atr_exit_triggered(
                    symbol=position.symbol,
                    atr_multiple=self.config.atr_exit_multiple,
                    entry_price=position.entry_price,
                    current_price=current_price
                )
                return True, f"ATR exit: {loss/atr:.1f}x ATR loss from entry"

        elif position.direction == -1:  # Short
            loss = current_price - position.entry_price
            if loss > threshold:
                metrics.atr_exit_triggered(
                    symbol=position.symbol,
                    atr_multiple=self.config.atr_exit_multiple,
                    entry_price=position.entry_price,
                    current_price=current_price
                )
                return True, f"ATR exit: {loss/atr:.1f}x ATR loss from entry"

        return False, None

    def check_persistence(
        self,
        position: PositionStateData,
        new_direction: int,
        current_date: date
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if signal flip passes persistence filter.

        Signal must persist for X days before position is flipped.

        Args:
            position: Current position state
            new_direction: Direction signal is trying to flip to
            current_date: Current date for tracking

        Returns:
            (allowed_to_flip, reason) - True means flip is allowed
        """
        # No flip happening
        if new_direction == position.direction:
            return True, None

        # Check if this is a new flip attempt or continuation
        if position.pending_direction == new_direction:
            # Same direction as pending - check days
            if position.consecutive_flip_days >= self.config.persistence_days:
                return True, f"Persistence passed: {position.consecutive_flip_days} days"
            else:
                # Emit metric for blocked flip
                metrics.persistence_blocked(
                    symbol=position.symbol,
                    days=position.consecutive_flip_days,
                    required=self.config.persistence_days,
                    direction=new_direction
                )
                return False, f"Persistence blocked: {position.consecutive_flip_days}/{self.config.persistence_days} days"
        else:
            # New flip direction - always block on first day
            metrics.persistence_blocked(
                symbol=position.symbol,
                days=0,
                required=self.config.persistence_days,
                direction=new_direction
            )
            return False, f"Persistence blocked: new flip started, 0/{self.config.persistence_days} days"

    def evaluate(
        self,
        position: PositionStateData,
        prices: pd.DataFrame,
        new_signal_direction: int,
        current_date: date
    ) -> Tuple[bool, int, Optional[str]]:
        """
        Evaluate all exit rules for a position.

        Args:
            position: Current position state
            prices: Price history DataFrame
            new_signal_direction: Direction from latest signal
            current_date: Current evaluation date

        Returns:
            (should_exit, final_direction, reason)
            - should_exit: True if position should be closed
            - final_direction: The direction to use (0 if exiting, otherwise new_signal)
            - reason: Explanation of decision
        """
        if not self.config.enabled:
            return False, new_signal_direction, None

        if position.direction == 0:
            # No position - no exit rules apply
            return False, new_signal_direction, None

        current_price = float(prices['adj_close'].iloc[-1])
        atr = self.compute_atr(prices)

        # Check trailing stop
        triggered, reason = self.check_trailing_stop(position, current_price, atr)
        if triggered:
            return True, 0, reason

        # Check ATR exit
        triggered, reason = self.check_atr_exit(position, current_price, atr)
        if triggered:
            return True, 0, reason

        # Check persistence for signal flips
        if new_signal_direction != position.direction:
            allowed, reason = self.check_persistence(position, new_signal_direction, current_date)
            if not allowed:
                # Don't flip yet - maintain current direction
                return False, position.direction, reason

        return False, new_signal_direction, None

    def update_position_state(
        self,
        position: PositionStateData,
        current_price: float,
        new_direction: int,
        current_date: date,
        atr: float
    ) -> PositionStateData:
        """
        Update position state after evaluation.

        Call this to update peak/trough prices and persistence tracking.

        Args:
            position: Current position state
            current_price: Latest price
            new_direction: Final direction after exit evaluation
            current_date: Current date
            atr: Current ATR value

        Returns:
            Updated PositionStateData
        """
        # Create a copy with updates
        updated = PositionStateData(
            symbol=position.symbol,
            direction=new_direction,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            peak_price=position.peak_price,
            trough_price=position.trough_price,
            pending_direction=position.pending_direction,
            signal_flip_date=position.signal_flip_date,
            consecutive_flip_days=position.consecutive_flip_days,
            entry_atr=position.entry_atr
        )

        # Handle direction change (new entry)
        if new_direction != 0 and position.direction != new_direction:
            # New position or flipped
            updated.entry_date = current_date
            updated.entry_price = current_price
            updated.entry_atr = atr
            updated.peak_price = current_price
            updated.trough_price = current_price
            updated.pending_direction = None
            updated.signal_flip_date = None
            updated.consecutive_flip_days = 0

        # Handle exit (going flat)
        elif new_direction == 0 and position.direction != 0:
            updated.entry_date = None
            updated.entry_price = None
            updated.peak_price = None
            updated.trough_price = None
            updated.pending_direction = None
            updated.signal_flip_date = None
            updated.consecutive_flip_days = 0

        # Update peak/trough for existing position
        elif new_direction == position.direction and new_direction != 0:
            if new_direction == 1:  # Long - track peak
                if position.peak_price is None or current_price > position.peak_price:
                    updated.peak_price = current_price
            else:  # Short - track trough
                if position.trough_price is None or current_price < position.trough_price:
                    updated.trough_price = current_price

        return updated
