import pandas as pd
from typing import Dict, List
from dataclasses import dataclass
from stocker.strategy.signal_strategy import SignalStrategy, SignalConfig
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig, TargetExposure

@dataclass
class BacktestResult:
    equity_curve: pd.Series
    stats: Dict[str, float]
    trades: pd.DataFrame
    signals: pd.DataFrame

class BacktestEngine:
    """
    Simulates strategy performance on historical data.
    """
    
    def __init__(self, 
                 signal_config: SignalConfig, 
                 risk_config: RiskConfig, 
                 initial_capital: float = 100000.0):
        self.signal_strategy = SignalStrategy(signal_config)
        self.portfolio_optimizer = PortfolioOptimizer(risk_config)
        self.initial_capital = initial_capital
        
    def run(self, market_data: Dict[str, pd.DataFrame]) -> BacktestResult:
        """
        Run backtest on provided market data.
        market_data: Dict mapping symbol -> DataFrame(index=Date, columns=[adj_close])
        """
        # Align all dates
        all_dates = sorted(list(set().union(*[df.index for df in market_data.values()])))
        portfolio_value = [self.initial_capital]
        positions = {sym: 0.0 for sym in market_data.keys()}
        
        # Track history
        history = []
        
        # Simple daily loop
        for i, date in enumerate(all_dates):
            if i < self.signal_strategy.config.lookback_days:
                continue
                
            current_date = date
            
            # 1. Generate Signals
            signals = []
            for symbol, df in market_data.items():
                if current_date in df.index:
                    # Slice history up to today
                    # We need enough history for lookback
                    hist_slice = df.loc[:current_date]
                    if len(hist_slice) > self.signal_strategy.config.lookback_days:
                        try:
                            sig = self.signal_strategy.compute_signal(symbol, hist_slice)
                            signals.append(sig)
                        except ValueError:
                            pass # Not enough data
            
            # 2. Optimize Portfolio
            # Calculate current drawdown for scaling
            current_equity = portfolio_value[-1]
            peak_equity = max(portfolio_value)
            drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
            
            targets = self.portfolio_optimizer.compute_targets(signals, drawdown)
            
            # 3. Simulate Next Day Return
            # This is a simplified "vectorized-like" step for the loop
            # Real simulation would apply fills, etc.
            # Here we just assume we get the target exposure at Close
            
            # Calculate daily P&L based on PREVIOUS positions and TODAY's return
            daily_pnl = 0.0
            if i < len(all_dates) - 1:
                next_date = all_dates[i+1]
                
                for symbol, exposure in positions.items():
                    df = market_data[symbol]
                    if current_date in df.index and next_date in df.index:
                        ret = (df.loc[next_date, 'adj_close'] / df.loc[current_date, 'adj_close']) - 1
                        # PnL = Exposure ($) * Return
                        # Exposure ($) = Exposure (%) * Portfolio Value
                        position_value = exposure * current_equity
                        daily_pnl += position_value * ret
                
                new_equity = current_equity + daily_pnl
                portfolio_value.append(new_equity)
                
                # Update positions for NEXT day based on TODAY's targets
                # (Assuming we rebalance at Close)
                positions = {t.symbol: t.target_exposure for t in targets}
                
                history.append({
                    "date": next_date,
                    "equity": new_equity,
                    "drawdown": drawdown,
                    "daily_pnl": daily_pnl
                })

        results_df = pd.DataFrame(history).set_index("date")
        
        stats = {
            "total_return": (portfolio_value[-1] / self.initial_capital) - 1,
            "final_equity": portfolio_value[-1],
            "max_drawdown": results_df['drawdown'].max() if not results_df.empty else 0
        }
        
        return BacktestResult(
            equity_curve=results_df['equity'],
            stats=stats,
            trades=pd.DataFrame(), # TODO: Detailed trade logs
            signals=pd.DataFrame()
        )
