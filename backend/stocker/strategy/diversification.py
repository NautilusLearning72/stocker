"""
Diversification controls for portfolio construction.

Provides:
- Sector exposure caps
- Asset class exposure caps
- Correlation-based throttling for new positions
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from stocker.core.metrics import metrics


@dataclass
class InstrumentMeta:
    """Metadata for an instrument used in diversification."""
    symbol: str
    sector: str
    asset_class: str


@dataclass
class DiversificationConfig:
    """Configuration for diversification controls."""
    enabled: bool = False
    sector_cap: float = 0.50
    asset_class_cap: float = 0.60
    correlation_throttle_enabled: bool = False
    correlation_threshold: float = 0.70
    correlation_lookback: int = 60
    correlation_scale_factor: float = 0.50


class DiversificationEngine:
    """
    Apply diversification constraints to target exposures.

    Provides bucket caps (sector, asset class) and correlation throttling.
    """

    def __init__(self, config: DiversificationConfig):
        self.config = config

    def apply_bucket_caps(
        self,
        targets: List,  # List[TargetExposure]
        metadata: Dict[str, InstrumentMeta]
    ) -> List:
        """
        Apply sector and asset class exposure caps.

        Uses proportional scaling when bucket exceeds cap.

        Args:
            targets: List of TargetExposure objects
            metadata: Symbol -> InstrumentMeta mapping

        Returns:
            Modified list of TargetExposure objects
        """
        if not self.config.enabled:
            return targets

        # Calculate current bucket exposures
        sector_exposure: Dict[str, float] = {}
        asset_class_exposure: Dict[str, float] = {}

        for t in targets:
            meta = metadata.get(t.symbol)
            if meta:
                sector = meta.sector or "Unknown"
                asset_class = meta.asset_class or "Unknown"
                sector_exposure[sector] = sector_exposure.get(sector, 0) + abs(t.target_exposure)
                asset_class_exposure[asset_class] = asset_class_exposure.get(asset_class, 0) + abs(t.target_exposure)

        # Apply caps with proportional scaling
        for t in targets:
            meta = metadata.get(t.symbol)
            if not meta:
                continue

            sector = meta.sector or "Unknown"
            asset_class = meta.asset_class or "Unknown"
            original_exposure = t.target_exposure

            # Sector cap
            sector_total = sector_exposure.get(sector, 0)
            if sector_total > self.config.sector_cap:
                scale = self.config.sector_cap / sector_total
                t.target_exposure = round(t.target_exposure * scale, 4)
                t.is_capped = True
                reason = f"Sector '{sector}' capped at {self.config.sector_cap:.0%}"
                t.reason = f"{t.reason}; {reason}" if t.reason else reason

                # Emit metric
                metrics.sector_cap_applied(
                    symbol=t.symbol,
                    sector=sector,
                    exposure_before=abs(original_exposure),
                    cap=self.config.sector_cap
                )

            # Asset class cap
            asset_class_total = asset_class_exposure.get(asset_class, 0)
            if asset_class_total > self.config.asset_class_cap:
                scale = self.config.asset_class_cap / asset_class_total
                t.target_exposure = round(t.target_exposure * scale, 4)
                t.is_capped = True
                reason = f"Asset class '{asset_class}' capped at {self.config.asset_class_cap:.0%}"
                t.reason = f"{t.reason}; {reason}" if t.reason else reason

                # Emit metric
                metrics.asset_class_cap_applied(
                    symbol=t.symbol,
                    asset_class=asset_class,
                    exposure_before=abs(original_exposure),
                    cap=self.config.asset_class_cap
                )

        return targets

    def compute_correlation_matrix(self, returns: pd.DataFrame) -> pd.DataFrame:
        """
        Compute correlation matrix from returns.

        Args:
            returns: DataFrame with symbol columns and date index

        Returns:
            Correlation matrix
        """
        if len(returns) < self.config.correlation_lookback:
            # Not enough data, return identity-like matrix
            return pd.DataFrame(
                np.eye(len(returns.columns)),
                index=returns.columns,
                columns=returns.columns
            )

        # Use rolling correlation for the lookback period
        recent_returns = returns.tail(self.config.correlation_lookback)
        return recent_returns.corr()

    def apply_correlation_throttle(
        self,
        targets: List,  # List[TargetExposure]
        returns: pd.DataFrame,
        current_positions: Dict[str, float]
    ) -> List:
        """
        Throttle new/increasing positions when highly correlated with existing.

        Only affects positions that are being added or increased.

        Args:
            targets: List of TargetExposure objects
            returns: Historical returns DataFrame
            current_positions: Current position weights by symbol

        Returns:
            Modified list of TargetExposure objects
        """
        if not self.config.correlation_throttle_enabled:
            return targets

        if returns.empty or len(returns.columns) < 2:
            return targets

        corr_matrix = self.compute_correlation_matrix(returns)

        for t in targets:
            # Only throttle NEW or INCREASING positions
            current = current_positions.get(t.symbol, 0.0)
            if abs(t.target_exposure) <= abs(current):
                continue  # Not increasing, no throttle

            # Check correlation with existing positions
            max_corr = 0.0
            most_correlated_with = None

            for existing_symbol, existing_exposure in current_positions.items():
                if existing_symbol == t.symbol:
                    continue
                if abs(existing_exposure) < 0.01:
                    continue  # Skip negligible positions

                # Check if both symbols are in correlation matrix
                if existing_symbol not in corr_matrix.columns:
                    continue
                if t.symbol not in corr_matrix.index:
                    continue

                corr = abs(corr_matrix.loc[t.symbol, existing_symbol])
                if pd.notna(corr) and corr > max_corr:
                    max_corr = corr
                    most_correlated_with = existing_symbol

            # Apply throttle if correlation exceeds threshold
            if max_corr > self.config.correlation_threshold:
                original_exposure = t.target_exposure
                t.target_exposure = round(
                    t.target_exposure * self.config.correlation_scale_factor,
                    4
                )
                t.is_capped = True
                reason = f"Corr throttle ({max_corr:.2f} with {most_correlated_with})"
                t.reason = f"{t.reason}; {reason}" if t.reason else reason

                # Emit metric
                metrics.correlation_throttle_applied(
                    symbol=t.symbol,
                    correlation=max_corr,
                    scale_factor=self.config.correlation_scale_factor,
                    correlated_with=most_correlated_with or "unknown"
                )

        return targets

    def apply_all(
        self,
        targets: List,
        metadata: Dict[str, InstrumentMeta],
        returns: Optional[pd.DataFrame] = None,
        current_positions: Optional[Dict[str, float]] = None
    ) -> List:
        """
        Apply all diversification controls in sequence.

        Args:
            targets: List of TargetExposure objects
            metadata: Symbol -> InstrumentMeta mapping
            returns: Historical returns for correlation (optional)
            current_positions: Current position weights (optional)

        Returns:
            Modified list of TargetExposure objects
        """
        if not self.config.enabled:
            return targets

        # Apply bucket caps first
        targets = self.apply_bucket_caps(targets, metadata)

        # Apply correlation throttle if data provided
        if returns is not None and current_positions is not None:
            targets = self.apply_correlation_throttle(
                targets, returns, current_positions
            )

        return targets
