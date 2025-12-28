from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import date
from stocker.strategy.signal_strategy import Signal

@dataclass
class RiskConfig:
    portfolio_id: str = "main_strategy"
    single_instrument_cap: float = 0.35
    gross_exposure_cap: float = 1.50
    drawdown_threshold: float = 0.10
    drawdown_scale_factor: float = 0.50

@dataclass
class TargetExposure:
    symbol: str
    target_exposure: float
    reason: Optional[str] = None
    is_capped: bool = False

class PortfolioOptimizer:
    """
    Transforms raw signals into target portfolio exposures.
    Applies risk caps and leverage constraints.
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config

    def compute_targets(self, signals: List[Signal], current_drawdown: float = 0.0) -> List[TargetExposure]:
        """
        Compute final target weights for a list of signals.
        """
        targets = []
        raw_exposures = {s.symbol: s.raw_weight for s in signals}
        
        # 1. Apply Drawdown Scaling
        scale_factor = 1.0
        drawdown_reason = None
        if current_drawdown > self.config.drawdown_threshold:
            scale_factor = self.config.drawdown_scale_factor
            drawdown_reason = f"Drawdown {current_drawdown:.1%} > {self.config.drawdown_threshold:.1%}"
        
        # 2. Process each signal through caps
        current_gross = sum(abs(w) for w in raw_exposures.values()) * scale_factor
        
        # If gross exposure > cap, we need to scalar down EVERYTHING
        gross_scaler = 1.0
        if current_gross > self.config.gross_exposure_cap:
             gross_scaler = self.config.gross_exposure_cap / current_gross
             
        for signal in signals:
            weight = signal.raw_weight * scale_factor
            
            # Check Single Asset Cap
            reason = []
            is_capped = False
            
            if abs(weight) > self.config.single_instrument_cap:
                weight = self.config.single_instrument_cap * (1 if weight > 0 else -1)
                is_capped = True
                reason.append(f"Capped at {self.config.single_instrument_cap:.0%}")
            
            # Apply Gross Scalar
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
            
        return targets
