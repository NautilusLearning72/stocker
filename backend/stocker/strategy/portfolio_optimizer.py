from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import date
import pandas as pd

from stocker.strategy.signal_strategy import Signal
from stocker.strategy.diversification import (
    DiversificationEngine,
    DiversificationConfig,
    InstrumentMeta
)
from stocker.strategy.signal_enhancer import (
    SignalEnhancer,
    EnhancementConfig,
    SignalMetadata,
    enhance_signals
)
from stocker.core.metrics import metrics


@dataclass
class RiskConfig:
    portfolio_id: str = "main_strategy"
    single_instrument_cap: float = 0.35
    gross_exposure_cap: float = 1.50
    drawdown_threshold: float = 0.10
    drawdown_scale_factor: float = 0.50
    # Diversification settings
    diversification_enabled: bool = False
    sector_cap: float = 0.50
    asset_class_cap: float = 0.60
    correlation_throttle_enabled: bool = False
    correlation_threshold: float = 0.70
    correlation_lookback: int = 60
    correlation_scale_factor: float = 0.50
    # Signal enhancement settings
    enhancement_enabled: bool = False
    conviction_enabled: bool = True
    sentiment_enabled: bool = True
    regime_enabled: bool = True
    quality_enabled: bool = True
    # Enhancement tuning parameters
    min_lookback_return: float = 0.02  # Minimum for full conviction
    conviction_scale_min: float = 0.3  # Minimum scaling for weak signals
    sentiment_weight: float = 0.2  # How much sentiment affects signal
    sentiment_contrarian: bool = False  # Fade extreme sentiment
    regime_defensive_scale: float = 0.5  # Scale down in risk-off
    breadth_threshold: float = 0.4  # Below this = risk-off

@dataclass
class TargetExposure:
    symbol: str
    target_exposure: float
    reason: Optional[str] = None
    is_capped: bool = False

class PortfolioOptimizer:
    """
    Transforms raw signals into target portfolio exposures.
    Applies risk caps, leverage constraints, and diversification controls.
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        # Initialize diversification engine
        self.diversification = DiversificationEngine(DiversificationConfig(
            enabled=config.diversification_enabled,
            sector_cap=config.sector_cap,
            asset_class_cap=config.asset_class_cap,
            correlation_throttle_enabled=config.correlation_throttle_enabled,
            correlation_threshold=config.correlation_threshold,
            correlation_lookback=config.correlation_lookback,
            correlation_scale_factor=config.correlation_scale_factor
        ))
        # Initialize signal enhancer
        self.enhancer = SignalEnhancer(EnhancementConfig(
            enabled=config.enhancement_enabled,
            conviction_enabled=config.conviction_enabled,
            sentiment_enabled=config.sentiment_enabled,
            regime_enabled=config.regime_enabled,
            quality_enabled=config.quality_enabled,
            # Tuning parameters
            min_lookback_return=config.min_lookback_return,
            conviction_scale_min=config.conviction_scale_min,
            sentiment_weight=config.sentiment_weight,
            sentiment_contrarian=config.sentiment_contrarian,
            regime_defensive_scale=config.regime_defensive_scale,
            breadth_threshold=config.breadth_threshold
        ))

    def compute_targets(
        self,
        signals: List[Signal],
        current_drawdown: float = 0.0,
        instrument_metadata: Optional[Dict[str, InstrumentMeta]] = None,
        returns: Optional[pd.DataFrame] = None,
        current_positions: Optional[Dict[str, float]] = None,
        sentiment_data: Optional[Dict[str, float]] = None,
        instrument_metrics: Optional[Dict[str, dict]] = None,
        market_breadth: Optional[float] = None,
        vix_level: Optional[float] = None
    ) -> List[TargetExposure]:
        """
        Compute final target weights for a list of signals.

        Args:
            signals: List of Signal objects with raw weights
            current_drawdown: Current portfolio drawdown (0.0 to 1.0)
            instrument_metadata: Optional symbol -> InstrumentMeta mapping
            returns: Optional historical returns for correlation
            current_positions: Optional current position weights
            sentiment_data: Optional symbol -> sentiment score mapping
            instrument_metrics: Optional symbol -> metrics (market_cap, beta, etc.)
            market_breadth: Optional current market breadth (% advancing)
            vix_level: Optional current VIX level

        Returns:
            List of TargetExposure objects with final weights
        """
        targets = []
        
        # 0. Apply signal enhancement (conviction, sentiment, regime, quality)
        enhanced_weights = {}
        if self.config.enhancement_enabled:
            enhancements = enhance_signals(
                signals=signals,
                enhancer=self.enhancer,
                sentiment_data=sentiment_data,
                metrics_data=instrument_metrics,
                market_breadth=market_breadth,
                vix_level=vix_level
            )
            enhanced_weights = {
                sym: result.enhanced_weight
                for sym, result in enhancements.items()
            }
        
        # Use enhanced weights if available, otherwise raw
        raw_exposures = {
            s.symbol: enhanced_weights.get(s.symbol, s.raw_weight)
            for s in signals
        }

        # 1. Apply Drawdown Scaling
        scale_factor = 1.0
        drawdown_reason = None
        if current_drawdown > self.config.drawdown_threshold:
            scale_factor = self.config.drawdown_scale_factor
            drawdown_reason = f"Drawdown {current_drawdown:.1%} > {self.config.drawdown_threshold:.1%}"

            # Emit drawdown scaling metric
            metrics.drawdown_scaling(
                drawdown=current_drawdown,
                threshold=self.config.drawdown_threshold,
                scale_factor=scale_factor
            )

        # 2. Calculate gross exposure for scaling
        current_gross = sum(abs(w) for w in raw_exposures.values()) * scale_factor

        # If gross exposure > cap, scale down everything
        gross_scaler = 1.0
        if current_gross > self.config.gross_exposure_cap:
            gross_scaler = self.config.gross_exposure_cap / current_gross

            # Emit gross exposure scaling metric
            metrics.gross_exposure_scaled(
                gross_before=current_gross,
                gross_after=self.config.gross_exposure_cap,
                scale_factor=gross_scaler
            )

        # 3. Process each signal through individual caps
        for signal in signals:
            # Use enhanced weight if available, otherwise raw weight
            base_weight = raw_exposures.get(signal.symbol, signal.raw_weight)
            weight = base_weight * scale_factor

            reason = []
            is_capped = False

            # Single instrument cap
            if abs(weight) > self.config.single_instrument_cap:
                original_weight = weight
                weight = self.config.single_instrument_cap * (1 if weight > 0 else -1)
                is_capped = True
                reason.append(f"Capped at {self.config.single_instrument_cap:.0%}")

                # Emit single cap metric
                metrics.single_cap_applied(
                    symbol=signal.symbol,
                    weight_before=abs(original_weight),
                    cap=self.config.single_instrument_cap
                )

            # Apply gross exposure scaler
            if gross_scaler < 1.0:
                weight *= gross_scaler
                is_capped = True
                reason.append(f"Gross exposure scaled by {gross_scaler:.2f}")

            if drawdown_reason:
                reason.append(drawdown_reason)

            targets.append(TargetExposure(
                symbol=signal.symbol,
                target_exposure=round(weight, 4),
                is_capped=is_capped,
                reason="; ".join(reason) if reason else None
            ))

        # 4. Apply diversification controls
        if instrument_metadata:
            targets = self.diversification.apply_all(
                targets=targets,
                metadata=instrument_metadata,
                returns=returns,
                current_positions=current_positions
            )

        return targets
