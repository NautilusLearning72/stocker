"""
Signal Enhancement Module.

Adjusts signal weights based on:
1. Trend Conviction - strength of the directional signal
2. Market Sentiment - news/social sentiment alignment
3. Market Regime - broad market health (risk-on vs risk-off)
4. Instrument Quality - fundamentals and liquidity

This provides additional risk management and return optimization
beyond the base volatility-targeted trend strategy.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import date, timedelta
from decimal import Decimal
import logging

from stocker.core.metrics import metrics

logger = logging.getLogger(__name__)


@dataclass
class EnhancementConfig:
    """Configuration for signal enhancement."""
    enabled: bool = True
    
    # Trend conviction settings
    conviction_enabled: bool = True
    min_lookback_return: float = 0.02  # Require at least 2% move for full weight
    conviction_scale_min: float = 0.3  # Minimum scaling for weak signals
    
    # Market sentiment settings
    sentiment_enabled: bool = True
    sentiment_weight: float = 0.2  # How much sentiment affects signal (0-1)
    sentiment_contrarian: bool = False  # True = fade extreme sentiment
    sentiment_extreme_threshold: float = 0.7  # Above this is "extreme"
    
    # Market regime settings
    regime_enabled: bool = True
    regime_defensive_scale: float = 0.5  # Scale down in risk-off regime
    breadth_threshold: float = 0.4  # Below this = risk-off
    
    # Instrument quality settings
    quality_enabled: bool = True
    quality_weight: float = 0.15  # How much quality affects signal
    min_market_cap: float = 1e9  # $1B minimum for full weight
    preferred_beta_range: tuple = (0.8, 1.5)  # Ideal beta range


@dataclass
class SignalMetadata:
    """Additional context for signal enhancement."""
    symbol: str
    lookback_return: float
    ewma_vol: float
    direction: int
    
    # Optional enrichment data
    sentiment_score: Optional[float] = None  # -1 to 1
    sentiment_magnitude: Optional[float] = None
    market_cap: Optional[float] = None
    beta: Optional[float] = None
    avg_volume: Optional[float] = None  # Dollar volume
    
    # Market-wide context
    market_breadth: Optional[float] = None  # % advancing
    vix_level: Optional[float] = None


@dataclass
class EnhancementResult:
    """Result of signal enhancement."""
    original_weight: float
    enhanced_weight: float
    adjustments: Dict[str, float]  # Component adjustments
    reasons: List[str]


class SignalEnhancer:
    """
    Enhances raw signal weights using additional market context.
    
    Enhancement factors:
    1. Conviction: Scale by trend strength (weak trends get smaller positions)
    2. Sentiment: Align with or fade market sentiment
    3. Regime: Reduce risk in defensive market conditions
    4. Quality: Favor higher quality instruments
    """
    
    def __init__(self, config: EnhancementConfig):
        self.config = config
    
    def enhance(
        self,
        raw_weight: float,
        metadata: SignalMetadata
    ) -> EnhancementResult:
        """
        Apply all enhancement factors to a raw signal weight.
        
        Args:
            raw_weight: Original signal weight from SignalStrategy
            metadata: Additional context for enhancement
            
        Returns:
            EnhancementResult with adjusted weight and explanations
        """
        if not self.config.enabled:
            return EnhancementResult(
                original_weight=raw_weight,
                enhanced_weight=raw_weight,
                adjustments={},
                reasons=["Enhancement disabled"]
            )
        
        adjustments = {}
        reasons = []
        weight = raw_weight
        
        # 1. Conviction adjustment
        if self.config.conviction_enabled:
            conv_factor, conv_reason = self._apply_conviction(metadata)
            adjustments["conviction"] = conv_factor
            weight *= conv_factor
            if conv_reason:
                reasons.append(conv_reason)
        
        # 2. Sentiment adjustment
        if self.config.sentiment_enabled and metadata.sentiment_score is not None:
            sent_factor, sent_reason = self._apply_sentiment(metadata)
            adjustments["sentiment"] = sent_factor
            weight *= sent_factor
            if sent_reason:
                reasons.append(sent_reason)
        
        # 3. Market regime adjustment
        if self.config.regime_enabled and metadata.market_breadth is not None:
            regime_factor, regime_reason = self._apply_regime(metadata)
            adjustments["regime"] = regime_factor
            weight *= regime_factor
            if regime_reason:
                reasons.append(regime_reason)
        
        # 4. Quality adjustment
        if self.config.quality_enabled:
            qual_factor, qual_reason = self._apply_quality(metadata)
            adjustments["quality"] = qual_factor
            weight *= qual_factor
            if qual_reason:
                reasons.append(qual_reason)
        
        # Emit enhancement metric
        if abs(weight - raw_weight) > 0.001:
            metrics.emit(
                metrics.CATEGORY_SIGNAL,
                "enhanced",
                weight,
                symbol=metadata.symbol,
                metadata={
                    "original_weight": round(raw_weight, 4),
                    "enhanced_weight": round(weight, 4),
                    "adjustments": {k: round(v, 3) for k, v in adjustments.items()},
                    "direction": metadata.direction
                }
            )
        
        return EnhancementResult(
            original_weight=raw_weight,
            enhanced_weight=round(weight, 6),
            adjustments=adjustments,
            reasons=reasons
        )
    
    def _apply_conviction(self, metadata: SignalMetadata) -> tuple[float, str]:
        """
        Scale weight by trend conviction (strength of lookback return).
        
        Weak directional moves get smaller positions to reduce
        whipsaws from noise.
        """
        abs_return = abs(metadata.lookback_return)
        min_return = self.config.min_lookback_return
        scale_min = self.config.conviction_scale_min
        
        if abs_return >= min_return:
            # Strong signal - full weight
            return 1.0, None
        
        # Linear scale between min and full
        # At 0 return: scale_min, at min_return: 1.0
        factor = scale_min + (1 - scale_min) * (abs_return / min_return)
        factor = max(scale_min, min(1.0, factor))
        
        return factor, f"Weak conviction ({abs_return:.1%} < {min_return:.1%})"
    
    def _apply_sentiment(self, metadata: SignalMetadata) -> tuple[float, str]:
        """
        Adjust based on market sentiment alignment.
        
        Default: Boost when sentiment aligns with signal direction
        Contrarian mode: Fade extreme sentiment
        """
        sentiment = metadata.sentiment_score
        direction = metadata.direction
        weight = self.config.sentiment_weight
        threshold = self.config.sentiment_extreme_threshold
        
        # Sentiment score: -1 (bearish) to +1 (bullish)
        # Direction: -1 (short) or +1 (long)
        alignment = sentiment * direction  # Positive if aligned
        
        if self.config.sentiment_contrarian:
            # Contrarian: reduce position on extreme aligned sentiment
            if abs(sentiment) > threshold and alignment > 0:
                factor = 1 - (weight * 0.5)  # Reduce by half the weight
                return factor, f"Contrarian: extreme sentiment ({sentiment:.2f})"
            elif abs(sentiment) > threshold and alignment < 0:
                # Extreme opposite sentiment - could be reversal
                factor = 1 + (weight * 0.3)
                return min(1.3, factor), f"Contrarian opportunity (sentiment: {sentiment:.2f})"
        else:
            # Momentum: boost aligned sentiment
            if alignment > 0:
                # Sentiment agrees with direction
                boost = weight * abs(sentiment)
                factor = 1 + boost
                return min(1.3, factor), f"Sentiment aligned ({sentiment:.2f})"
            else:
                # Sentiment disagrees - reduce confidence
                reduction = weight * abs(sentiment) * 0.5
                factor = 1 - reduction
                return max(0.7, factor), f"Sentiment headwind ({sentiment:.2f})"
        
        return 1.0, None
    
    def _apply_regime(self, metadata: SignalMetadata) -> tuple[float, str]:
        """
        Adjust based on market regime (risk-on vs risk-off).
        
        Risk-off conditions (low breadth, high VIX) reduce position sizes.
        """
        breadth = metadata.market_breadth
        threshold = self.config.breadth_threshold
        scale = self.config.regime_defensive_scale
        
        # Check VIX if available (>25 = elevated fear)
        vix_penalty = 0
        if metadata.vix_level is not None and metadata.vix_level > 25:
            vix_penalty = min(0.3, (metadata.vix_level - 25) / 50)
        
        if breadth < threshold:
            # Risk-off regime
            factor = scale - vix_penalty
            factor = max(0.3, factor)
            return factor, f"Risk-off regime (breadth: {breadth:.1%})"
        elif breadth > 0.6 and metadata.direction == 1:
            # Strong breadth + long signal = favorable
            return 1.1, "Strong market breadth"
        
        # Neutral regime with VIX adjustment
        if vix_penalty > 0:
            return 1 - vix_penalty, f"Elevated VIX ({metadata.vix_level:.1f})"
        
        return 1.0, None
    
    def _apply_quality(self, metadata: SignalMetadata) -> tuple[float, str]:
        """
        Adjust based on instrument quality metrics.
        
        Factors: market cap, beta, liquidity
        """
        weight = self.config.quality_weight
        factors = []
        total_adjustment = 0
        
        # Market cap factor
        if metadata.market_cap is not None:
            min_cap = self.config.min_market_cap
            if metadata.market_cap < min_cap:
                # Small cap penalty
                cap_ratio = metadata.market_cap / min_cap
                penalty = weight * (1 - cap_ratio) * 0.5
                total_adjustment -= penalty
                factors.append(f"small cap (${metadata.market_cap/1e9:.1f}B)")
        
        # Beta factor - prefer moderate beta
        if metadata.beta is not None:
            low, high = self.config.preferred_beta_range
            if metadata.beta < low:
                # Low beta - might miss moves
                penalty = weight * 0.2
                total_adjustment -= penalty
                factors.append(f"low beta ({metadata.beta:.2f})")
            elif metadata.beta > high:
                # High beta - extra volatile
                penalty = weight * (metadata.beta - high) * 0.3
                total_adjustment -= min(0.2, penalty)
                factors.append(f"high beta ({metadata.beta:.2f})")
        
        # Liquidity factor (avg dollar volume)
        if metadata.avg_volume is not None:
            if metadata.avg_volume < 5e6:  # < $5M daily volume
                penalty = weight * 0.3
                total_adjustment -= penalty
                factors.append("low liquidity")
        
        if total_adjustment != 0:
            factor = 1 + total_adjustment
            factor = max(0.5, min(1.2, factor))
            return factor, f"Quality: {', '.join(factors)}"
        
        return 1.0, None


# Convenience function for batch enhancement
def enhance_signals(
    signals: list,  # List of Signal objects
    enhancer: SignalEnhancer,
    sentiment_data: Optional[Dict[str, float]] = None,
    metrics_data: Optional[Dict[str, dict]] = None,
    market_breadth: Optional[float] = None,
    vix_level: Optional[float] = None
) -> Dict[str, EnhancementResult]:
    """
    Enhance a batch of signals with available context.
    
    Args:
        signals: List of Signal objects
        enhancer: Configured SignalEnhancer
        sentiment_data: Symbol -> sentiment score mapping
        metrics_data: Symbol -> instrument metrics mapping
        market_breadth: Current market breadth (% advancing)
        vix_level: Current VIX level
        
    Returns:
        Symbol -> EnhancementResult mapping
    """
    results = {}
    
    for signal in signals:
        # Build metadata from available sources
        meta = SignalMetadata(
            symbol=signal.symbol,
            lookback_return=signal.metrics.get("lookback_return", 0),
            ewma_vol=signal.metrics.get("ewma_vol", 0.15),
            direction=signal.direction,
            market_breadth=market_breadth,
            vix_level=vix_level
        )
        
        # Add sentiment if available
        if sentiment_data and signal.symbol in sentiment_data:
            meta.sentiment_score = sentiment_data[signal.symbol]
        
        # Add instrument metrics if available
        if metrics_data and signal.symbol in metrics_data:
            m = metrics_data[signal.symbol]
            meta.market_cap = m.get("market_cap")
            meta.beta = m.get("beta")
            meta.avg_volume = m.get("avg_volume")
        
        results[signal.symbol] = enhancer.enhance(signal.raw_weight, meta)
    
    return results
