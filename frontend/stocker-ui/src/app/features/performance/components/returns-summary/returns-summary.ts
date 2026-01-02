import { Component, Input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ReturnsMetrics } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-returns-summary',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule, DecimalPipe],
  template: `
    <div class="metrics-grid">
      <!-- Total Return -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>trending_up</mat-icon>
          <span>Total Return</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.total_return ?? 0) > 0" [class.negative]="(data?.total_return ?? 0) < 0">
          {{ formatPercent(data?.total_return) }}
        </div>
      </mat-card>

      <!-- CAGR -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>show_chart</mat-icon>
          <span matTooltip="Compound Annual Growth Rate">CAGR</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.cagr ?? 0) > 0" [class.negative]="(data?.cagr ?? 0) < 0">
          {{ formatPercent(data?.cagr) }}
        </div>
      </mat-card>

      <!-- YTD -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>calendar_today</mat-icon>
          <span matTooltip="Year-to-Date Return">YTD</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.ytd_return ?? 0) > 0" [class.negative]="(data?.ytd_return ?? 0) < 0">
          {{ formatPercent(data?.ytd_return) }}
        </div>
      </mat-card>

      <!-- MTD -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>date_range</mat-icon>
          <span matTooltip="Month-to-Date Return">MTD</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.mtd_return ?? 0) > 0" [class.negative]="(data?.mtd_return ?? 0) < 0">
          {{ formatPercent(data?.mtd_return) }}
        </div>
      </mat-card>

      <!-- 1D Return -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>today</mat-icon>
          <span>1 Day</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.return_1d ?? 0) > 0" [class.negative]="(data?.return_1d ?? 0) < 0">
          {{ formatPercent(data?.return_1d) }}
        </div>
      </mat-card>

      <!-- 1W Return -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>view_week</mat-icon>
          <span>1 Week</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.return_1w ?? 0) > 0" [class.negative]="(data?.return_1w ?? 0) < 0">
          {{ formatPercent(data?.return_1w) }}
        </div>
      </mat-card>

      <!-- 1M Return -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>event</mat-icon>
          <span>1 Month</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.return_1m ?? 0) > 0" [class.negative]="(data?.return_1m ?? 0) < 0">
          {{ formatPercent(data?.return_1m) }}
        </div>
      </mat-card>

      <!-- 1Y Return -->
      <mat-card class="metric-card">
        <div class="metric-header">
          <mat-icon>event_available</mat-icon>
          <span>1 Year</span>
        </div>
        <div class="metric-value" [class.positive]="(data?.return_1y ?? 0) > 0" [class.negative]="(data?.return_1y ?? 0) < 0">
          {{ formatPercent(data?.return_1y) }}
        </div>
      </mat-card>
    </div>

    <!-- Win/Loss Stats -->
    <div class="win-loss-section">
      <mat-card class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Winning Days</span>
          <span class="stat-value">{{ data?.pct_winning_days | number:'1.1-1' }}%</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Winning Months</span>
          <span class="stat-value">{{ data?.pct_winning_months | number:'1.1-1' }}%</span>
        </div>
      </mat-card>

      <mat-card class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Best Day</span>
          <span class="stat-value positive">{{ formatPercent(data?.best_day) }}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Worst Day</span>
          <span class="stat-value negative">{{ formatPercent(data?.worst_day) }}</span>
        </div>
      </mat-card>

      <mat-card class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Best Month</span>
          <span class="stat-value positive">{{ formatPercent(data?.best_month) }}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Worst Month</span>
          <span class="stat-value negative">{{ formatPercent(data?.worst_month) }}</span>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }

    .metric-card {
      padding: 16px;
      text-align: center;
    }

    .metric-header {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      color: #666;
      font-size: 13px;
      margin-bottom: 8px;
    }

    .metric-header mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }

    .metric-value {
      font-size: 24px;
      font-weight: 500;
    }

    .metric-value.positive {
      color: #4CAF50;
    }

    .metric-value.negative {
      color: #F44336;
    }

    .win-loss-section {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }

    .stat-card {
      padding: 16px;
    }

    .stat-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
    }

    .stat-row:not(:last-child) {
      border-bottom: 1px solid rgba(0,0,0,0.08);
    }

    .stat-label {
      color: #666;
      font-size: 13px;
    }

    .stat-value {
      font-weight: 500;
    }

    .stat-value.positive {
      color: #4CAF50;
    }

    .stat-value.negative {
      color: #F44336;
    }

    @media (max-width: 960px) {
      .metrics-grid {
        grid-template-columns: repeat(2, 1fr);
      }

      .win-loss-section {
        grid-template-columns: 1fr;
      }
    }
  `]
})
export class ReturnsSummary {
  @Input() data: ReturnsMetrics | null = null;

  formatPercent(value: number | undefined | null): string {
    if (value == null) return '--';
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(2) + '%';
  }
}
