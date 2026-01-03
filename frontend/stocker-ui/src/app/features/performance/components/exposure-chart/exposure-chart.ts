import { Component, Input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ExposureAnalysis, ExposurePoint } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-exposure-chart',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatIconModule, MatTooltipModule, DecimalPipe],
  template: `
    <div class="exposure-grid">
      <!-- Current Exposure -->
      <div class="current-exposure">
        <mat-card class="exposure-card gross">
          <div class="exposure-icon">
            <mat-icon>show_chart</mat-icon>
          </div>
          <div class="exposure-content">
            <span class="exposure-value">{{ data?.current_gross_exposure | number:'1.1-1' }}%</span>
            <span class="exposure-label" matTooltip="Sum of absolute position values / NAV">Gross Exposure</span>
          </div>
        </mat-card>

        <mat-card class="exposure-card net">
          <div class="exposure-icon">
            <mat-icon>swap_vert</mat-icon>
          </div>
          <div class="exposure-content">
            <span class="exposure-value">{{ data?.current_net_exposure | number:'1.1-1' }}%</span>
            <span class="exposure-label" matTooltip="Sum of position values / NAV (long - short)">Net Exposure</span>
          </div>
        </mat-card>

        <mat-card class="exposure-card long">
          <div class="exposure-icon">
            <mat-icon>arrow_upward</mat-icon>
          </div>
          <div class="exposure-content">
            <span class="exposure-value">{{ data?.current_long_exposure | number:'1.1-1' }}%</span>
            <span class="exposure-label">Long Exposure</span>
          </div>
        </mat-card>

        <mat-card class="exposure-card short">
          <div class="exposure-icon">
            <mat-icon>arrow_downward</mat-icon>
          </div>
          <div class="exposure-content">
            <span class="exposure-value">{{ data?.current_short_exposure | number:'1.1-1' }}%</span>
            <span class="exposure-label">Short Exposure</span>
          </div>
        </mat-card>
      </div>

      <!-- Historical Stats -->
      <mat-card class="section-card">
        <h3 class="section-title">Historical Exposure</h3>
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">Avg Gross</span>
            <span class="stat-value">{{ data?.avg_gross_exposure | number:'1.1-1' }}%</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Avg Net</span>
            <span class="stat-value">{{ data?.avg_net_exposure | number:'1.1-1' }}%</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Max Gross</span>
            <span class="stat-value">{{ data?.max_gross_exposure | number:'1.1-1' }}%</span>
          </div>
        </div>
      </mat-card>

      <!-- Turnover -->
      <mat-card class="section-card">
        <h3 class="section-title">Portfolio Turnover</h3>
        <div class="turnover-grid">
          <div class="turnover-item">
            <div class="turnover-value">{{ data?.avg_daily_turnover | number:'1.2-2' }}%</div>
            <div class="turnover-label">Daily Avg</div>
          </div>
          <div class="turnover-item">
            <div class="turnover-value">{{ data?.avg_monthly_turnover | number:'1.1-1' }}%</div>
            <div class="turnover-label">Monthly Avg</div>
          </div>
          <div class="turnover-item">
            <div class="turnover-value">{{ data?.annual_turnover | number:'1.0-0' }}%</div>
            <div class="turnover-label">Annual</div>
          </div>
        </div>
      </mat-card>

      <!-- Exposure History Chart (Simplified bar visualization) -->
      <mat-card class="section-card" *ngIf="data?.exposure_history?.length">
        <h3 class="section-title">Exposure Over Time</h3>
        <div class="exposure-bars">
          <div class="bar-row" *ngFor="let point of getRecentHistory()">
            <span class="bar-date">{{ formatDate(point.date) }}</span>
            <div class="bar-container">
              <div class="bar long-bar" [style.width.%]="point.long_exposure"></div>
              <div class="bar short-bar" [style.width.%]="point.short_exposure"></div>
            </div>
            <span class="bar-value">{{ point.gross_exposure | number:'1.0-0' }}%</span>
          </div>
        </div>
        <div class="bar-legend">
          <span class="legend-item"><span class="legend-color long"></span> Long</span>
          <span class="legend-item"><span class="legend-color short"></span> Short</span>
        </div>
      </mat-card>

      <!-- Sector Breakdown -->
      <mat-card class="section-card" *ngIf="data?.by_sector?.length">
        <h3 class="section-title">Sector Breakdown</h3>
        <div class="sector-list">
          <div class="sector-row" *ngFor="let sector of data?.by_sector ?? []">
            <span class="sector-name">{{ sector.sector }}</span>
            <div class="sector-bar-container">
              <div class="sector-bar" [style.width.%]="sector.exposure / maxSectorExposure * 100"></div>
            </div>
            <span class="sector-value">{{ sector.exposure | number:'1.1-1' }}%</span>
            <span class="sector-count">({{ sector.position_count }})</span>
          </div>
        </div>
      </mat-card>

      <!-- Empty State -->
      <mat-card class="empty-card" *ngIf="!data?.exposure_history?.length">
        <mat-icon>pie_chart</mat-icon>
        <p>No exposure data available</p>
      </mat-card>
    </div>
  `,
  styles: [`
    .exposure-grid {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .current-exposure {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }

    .exposure-card {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 20px;
    }

    .exposure-icon {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .exposure-card.gross .exposure-icon { background: var(--color-accent-soft); color: var(--color-accent); }
    .exposure-card.net .exposure-icon { background: var(--color-accent-softer); color: var(--color-accent); }
    .exposure-card.long .exposure-icon { background: var(--color-success-soft); color: var(--color-success); }
    .exposure-card.short .exposure-icon { background: var(--color-danger-soft); color: var(--color-danger); }

    .exposure-content {
      display: flex;
      flex-direction: column;
    }

    .exposure-value {
      font-size: 24px;
      font-weight: 600;
      color: var(--color-text);
    }

    .exposure-label {
      font-size: 12px;
      color: var(--color-muted);
    }

    .section-card {
      padding: 16px;
    }

    .section-title {
      margin: 0 0 16px 0;
      font-size: 14px;
      font-weight: 600;
      color: var(--color-text);
    }

    .stats-grid, .turnover-grid {
      display: flex;
      justify-content: space-around;
    }

    .stat-item, .turnover-item {
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    .stat-label, .turnover-label {
      font-size: 12px;
      color: var(--color-muted);
    }

    .stat-value {
      font-size: 20px;
      font-weight: 600;
      color: var(--color-text);
    }

    .turnover-value {
      font-size: 28px;
      font-weight: 600;
      color: var(--color-accent);
    }

    .exposure-bars {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .bar-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .bar-date {
      width: 80px;
      font-size: 12px;
      color: var(--color-muted);
    }

    .bar-container {
      flex: 1;
      height: 20px;
      background: var(--color-canvas-subtle);
      border-radius: 4px;
      display: flex;
      overflow: hidden;
    }

    .bar {
      height: 100%;
      transition: width 0.3s;
    }

    .long-bar {
      background: var(--color-success);
    }

    .short-bar {
      background: var(--color-danger);
    }

    .bar-value {
      width: 50px;
      text-align: right;
      font-size: 12px;
      font-weight: 500;
    }

    .bar-legend {
      display: flex;
      justify-content: center;
      gap: 24px;
      margin-top: 12px;
      font-size: 12px;
      color: var(--color-muted);
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .legend-color {
      width: 12px;
      height: 12px;
      border-radius: 2px;
    }

    .legend-color.long { background: var(--color-success); }
    .legend-color.short { background: var(--color-danger); }

    .sector-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .sector-row {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .sector-name {
      width: 120px;
      font-size: 13px;
    }

    .sector-bar-container {
      flex: 1;
      height: 16px;
      background: var(--color-canvas-subtle);
      border-radius: 4px;
      overflow: hidden;
    }

    .sector-bar {
      height: 100%;
      background: var(--color-accent);
      transition: width 0.3s;
    }

    .sector-value {
      width: 50px;
      text-align: right;
      font-size: 13px;
      font-weight: 600;
      color: var(--color-text);
    }

    .sector-count {
      width: 30px;
      font-size: 11px;
      color: var(--color-muted);
    }

    .empty-card {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 48px;
      color: var(--color-muted);
    }

    .empty-card mat-icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      margin-bottom: 16px;
    }

    @media (max-width: 960px) {
      .current-exposure {
        grid-template-columns: repeat(2, 1fr);
      }
    }
  `]
})
export class ExposureChartComponent {
  @Input() data: ExposureAnalysis | null = null;

  get maxSectorExposure(): number {
    if (!this.data?.by_sector) return 100;
    return Math.max(...this.data.by_sector.map(s => s.exposure), 1);
  }

  getRecentHistory(): ExposurePoint[] {
    if (!this.data?.exposure_history?.length) return [];
    // Return last 10 entries
    return this.data.exposure_history.slice(-10);
  }

  formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
}
