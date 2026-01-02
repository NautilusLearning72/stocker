import { Component, Input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RiskMetrics } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-risk-metrics',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule, DecimalPipe],
  template: `
    <div class="risk-grid">
      <!-- Risk-Adjusted Returns -->
      <mat-card class="section-card">
        <h3 class="section-title">Risk-Adjusted Returns</h3>
        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-label" matTooltip="Excess return per unit of volatility. Above 1.0 is good, above 2.0 is excellent.">
              Sharpe Ratio
            </span>
            <span class="metric-value" [class.good]="(data?.sharpe_ratio ?? 0) > 1" [class.excellent]="(data?.sharpe_ratio ?? 0) > 2">
              {{ data?.sharpe_ratio | number:'1.2-2' }}
            </span>
          </div>
          <div class="metric-item">
            <span class="metric-label" matTooltip="Like Sharpe, but only penalizes downside volatility. Higher is better.">
              Sortino Ratio
            </span>
            <span class="metric-value" [class.good]="(data?.sortino_ratio ?? 0) > 1" [class.excellent]="(data?.sortino_ratio ?? 0) > 2">
              {{ data?.sortino_ratio | number:'1.2-2' }}
            </span>
          </div>
          <div class="metric-item">
            <span class="metric-label" matTooltip="CAGR divided by max drawdown. Higher means better return per unit of drawdown risk.">
              Calmar Ratio
            </span>
            <span class="metric-value" [class.good]="(data?.calmar_ratio ?? 0) > 1" [class.excellent]="(data?.calmar_ratio ?? 0) > 2">
              {{ data?.calmar_ratio | number:'1.2-2' }}
            </span>
          </div>
        </div>
      </mat-card>

      <!-- Volatility -->
      <mat-card class="section-card">
        <h3 class="section-title">Volatility</h3>
        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-label">Annualized Vol</span>
            <span class="metric-value">{{ data?.annualized_volatility | number:'1.1-1' }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Daily Vol</span>
            <span class="metric-value">{{ data?.daily_volatility | number:'1.2-2' }}%</span>
          </div>
        </div>
      </mat-card>

      <!-- Drawdown -->
      <mat-card class="section-card">
        <h3 class="section-title">Drawdown</h3>
        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-label">Current DD</span>
            <span class="metric-value negative">-{{ data?.current_drawdown | number:'1.1-1' }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Max DD</span>
            <span class="metric-value negative">-{{ data?.max_drawdown | number:'1.1-1' }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Avg DD</span>
            <span class="metric-value negative">-{{ data?.avg_drawdown | number:'1.1-1' }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label" matTooltip="Longest time spent in drawdown (days)">Max DD Duration</span>
            <span class="metric-value">{{ data?.max_drawdown_duration_days }} days</span>
          </div>
        </div>
      </mat-card>

      <!-- Tail Risk -->
      <mat-card class="section-card">
        <h3 class="section-title">Tail Risk</h3>
        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-label" matTooltip="95% Value at Risk - Expected daily loss that won't be exceeded 95% of the time">
              VaR (95%)
            </span>
            <span class="metric-value negative">-{{ data?.var_95 | number:'1.2-2' }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label" matTooltip="Conditional VaR - Expected loss when VaR is breached (tail losses)">
              CVaR (95%)
            </span>
            <span class="metric-value negative">-{{ data?.cvar_95 | number:'1.2-2' }}%</span>
          </div>
        </div>
      </mat-card>

      <!-- Worst Periods -->
      <mat-card class="section-card">
        <h3 class="section-title">Worst Periods</h3>
        <div class="metrics-row">
          <div class="metric-item">
            <span class="metric-label">Worst 1M</span>
            <span class="metric-value negative">{{ formatPercent(data?.worst_1m) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Worst 3M</span>
            <span class="metric-value negative">{{ formatPercent(data?.worst_3m) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Worst 12M</span>
            <span class="metric-value negative">{{ formatPercent(data?.worst_12m) }}</span>
          </div>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .risk-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .section-card {
      padding: 16px;
    }

    .section-title {
      margin: 0 0 16px 0;
      font-size: 14px;
      font-weight: 500;
      color: #333;
    }

    .metrics-row {
      display: flex;
      flex-wrap: wrap;
      gap: 24px;
    }

    .metric-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 100px;
    }

    .metric-label {
      font-size: 12px;
      color: #666;
      cursor: help;
    }

    .metric-value {
      font-size: 18px;
      font-weight: 500;
    }

    .metric-value.good {
      color: #2196F3;
    }

    .metric-value.excellent {
      color: #4CAF50;
    }

    .metric-value.negative {
      color: #F44336;
    }

    @media (max-width: 768px) {
      .risk-grid {
        grid-template-columns: 1fr;
      }
    }
  `]
})
export class RiskMetricsComponent {
  @Input() data: RiskMetrics | null = null;

  formatPercent(value: number | undefined | null): string {
    if (value == null) return '--';
    return value.toFixed(1) + '%';
  }
}
