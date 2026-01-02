import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';

interface ParameterRow {
  parameter: string;
  default: string;
  description: string;
  category?: string;
}

@Component({
  selector: 'app-strategy-guide',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatExpansionModule,
    MatTableModule,
    MatIconModule,
    MatDividerModule
  ],
  templateUrl: './strategy-guide.html',
  styleUrl: './strategy-guide.scss'
})
export class StrategyGuide {
  displayedColumns: string[] = ['parameter', 'default', 'description'];

  parameters: ParameterRow[] = [
    // Strategy Parameters
    { parameter: 'LOOKBACK_DAYS', default: '126', description: 'Trend signal lookback period (~6 months)', category: 'Strategy' },
    { parameter: 'EWMA_LAMBDA', default: '0.94', description: 'Volatility smoothing factor (RiskMetrics standard)', category: 'Strategy' },
    { parameter: 'TARGET_VOL', default: '0.10', description: 'Annualized portfolio volatility target (10%)', category: 'Strategy' },

    // Risk Limits
    { parameter: 'SINGLE_INSTRUMENT_CAP', default: '0.35', description: 'Maximum exposure per instrument (35%)', category: 'Risk' },
    { parameter: 'GROSS_EXPOSURE_CAP', default: '1.50', description: 'Maximum total leverage (150%)', category: 'Risk' },
    { parameter: 'DRAWDOWN_THRESHOLD', default: '0.10', description: 'Circuit breaker trigger level (10%)', category: 'Risk' },
    { parameter: 'DRAWDOWN_SCALE_FACTOR', default: '0.50', description: 'Position reduction when triggered', category: 'Risk' },

    // Trend Confirmation
    { parameter: 'CONFIRMATION_ENABLED', default: 'false', description: 'Enable trend confirmation filters', category: 'Confirmation' },
    { parameter: 'CONFIRMATION_TYPE', default: 'donchian', description: 'Type: donchian | dual_ma | both', category: 'Confirmation' },
    { parameter: 'DONCHIAN_PERIOD', default: '20', description: 'Donchian channel lookback days', category: 'Confirmation' },
    { parameter: 'MA_FAST_PERIOD', default: '50', description: 'Fast moving average period', category: 'Confirmation' },
    { parameter: 'MA_SLOW_PERIOD', default: '200', description: 'Slow moving average period', category: 'Confirmation' },

    // Exit Rules
    { parameter: 'EXIT_RULES_ENABLED', default: 'false', description: 'Enable position-level exit rules', category: 'Exit Rules' },
    { parameter: 'TRAILING_STOP_ATR_MULTIPLE', default: '3.0', description: 'ATRs from peak to trigger stop', category: 'Exit Rules' },
    { parameter: 'ATR_EXIT_MULTIPLE', default: '2.0', description: 'ATRs against entry to exit', category: 'Exit Rules' },
    { parameter: 'ATR_PERIOD', default: '14', description: 'ATR calculation period', category: 'Exit Rules' },
    { parameter: 'PERSISTENCE_DAYS', default: '3', description: 'Days signal must persist before flip', category: 'Exit Rules' },

    // Diversification
    { parameter: 'DIVERSIFICATION_ENABLED', default: 'false', description: 'Enable sector/correlation controls', category: 'Diversification' },
    { parameter: 'SECTOR_CAP', default: '0.50', description: 'Max exposure per sector (50%)', category: 'Diversification' },
    { parameter: 'ASSET_CLASS_CAP', default: '0.60', description: 'Max exposure per asset class (60%)', category: 'Diversification' },
    { parameter: 'CORRELATION_THROTTLE_ENABLED', default: 'false', description: 'Throttle correlated position adds', category: 'Diversification' },
    { parameter: 'CORRELATION_THRESHOLD', default: '0.70', description: 'Correlation level to trigger throttle', category: 'Diversification' },
    { parameter: 'CORRELATION_SCALE_FACTOR', default: '0.50', description: 'Scale factor when throttled', category: 'Diversification' },
    { parameter: 'CORRELATION_LOOKBACK', default: '60', description: 'Days to measure correlation', category: 'Diversification' },

    // Enhancement
    { parameter: 'ENHANCEMENT_ENABLED', default: 'false', description: 'Master toggle for signal enhancement', category: 'Enhancement' },
    { parameter: 'CONVICTION_ENABLED', default: 'true', description: 'Scale by trend strength', category: 'Enhancement' },
    { parameter: 'MIN_LOOKBACK_RETURN', default: '0.02', description: 'Return threshold for full conviction', category: 'Enhancement' },
    { parameter: 'CONVICTION_SCALE_MIN', default: '0.50', description: 'Minimum conviction multiplier', category: 'Enhancement' },
    { parameter: 'SENTIMENT_ENABLED', default: 'true', description: 'Adjust by market sentiment', category: 'Enhancement' },
    { parameter: 'SENTIMENT_WEIGHT', default: '0.30', description: 'Sentiment influence (0-1)', category: 'Enhancement' },
    { parameter: 'SENTIMENT_CONTRARIAN', default: 'true', description: 'Fade extreme sentiment', category: 'Enhancement' },
    { parameter: 'REGIME_ENABLED', default: 'true', description: 'Reduce in stressed regimes', category: 'Enhancement' },
    { parameter: 'REGIME_DEFENSIVE_SCALE', default: '0.60', description: 'Multiplier in defensive mode', category: 'Enhancement' },
    { parameter: 'BREADTH_THRESHOLD', default: '0.40', description: 'Breadth level triggering defense', category: 'Enhancement' },
    { parameter: 'QUALITY_ENABLED', default: 'true', description: 'Tilt toward quality instruments', category: 'Enhancement' },

    // Order Sizing
    { parameter: 'FRACTIONAL_SIZING_ENABLED', default: 'true', description: 'Allow fractional share orders', category: 'Sizing' },
    { parameter: 'FRACTIONAL_DECIMALS', default: '4', description: 'Decimal places for fractional qty', category: 'Sizing' },
    { parameter: 'MIN_NOTIONAL_USD', default: '50.0', description: 'Minimum order size in dollars', category: 'Sizing' },
    { parameter: 'MIN_NOTIONAL_MODE', default: 'fixed', description: 'Mode: fixed | nav_scaled | liquidity_scaled', category: 'Sizing' },
    { parameter: 'ALLOW_SHORT_SELLING', default: 'true', description: 'Enable short positions', category: 'Sizing' },

    // Broker
    { parameter: 'BROKER_MODE', default: 'paper', description: 'Trading mode: paper | live', category: 'Broker' },
    { parameter: 'ALPACA_BASE_URL', default: 'paper-api.alpaca.markets', description: 'Alpaca API endpoint', category: 'Broker' },
  ];
}
