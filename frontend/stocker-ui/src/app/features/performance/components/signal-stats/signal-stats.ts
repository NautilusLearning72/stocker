import { Component, Input } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { SignalPerformance } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-signal-stats',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatTableModule, MatIconModule, MatTooltipModule, MatChipsModule, DecimalPipe],
  template: `
    <div class="signal-grid">
      <!-- Summary Cards -->
      <div class="summary-cards">
        <mat-card class="stat-card highlight">
          <div class="stat-main">
            <span class="stat-value large" [class.good]="(data?.hit_rate ?? 0) >= 50">
              {{ data?.hit_rate | number:'1.1-1' }}%
            </span>
            <span class="stat-label">Hit Rate</span>
          </div>
          <div class="stat-sub">
            <span>{{ data?.winning_signals ?? 0 }} winners / {{ data?.total_signals ?? 0 }} total</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-row">
            <div class="stat-item">
              <span class="stat-label">Long Signals</span>
              <span class="stat-value">{{ data?.long_signals ?? 0 }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Long Hit Rate</span>
              <span class="stat-value" [class.good]="(data?.long_hit_rate ?? 0) >= 50">
                {{ data?.long_hit_rate | number:'1.1-1' }}%
              </span>
            </div>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-row">
            <div class="stat-item">
              <span class="stat-label">Short Signals</span>
              <span class="stat-value">{{ data?.short_signals ?? 0 }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Short Hit Rate</span>
              <span class="stat-value" [class.good]="(data?.short_hit_rate ?? 0) >= 50">
                {{ data?.short_hit_rate | number:'1.1-1' }}%
              </span>
            </div>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-main">
            <span class="stat-value large" [class.good]="(data?.profit_factor ?? 0) > 1">
              {{ data?.profit_factor | number:'1.2-2' }}
            </span>
            <span class="stat-label" matTooltip="Gross profit / Gross loss. Above 1.0 means profitable.">
              Profit Factor
            </span>
          </div>
        </mat-card>
      </div>

      <!-- Returns Analysis -->
      <mat-card class="section-card">
        <h3 class="section-title">Returns Analysis</h3>
        <div class="returns-grid">
          <div class="return-item positive">
            <mat-icon>trending_up</mat-icon>
            <div class="return-content">
              <span class="return-label">Avg Winner</span>
              <span class="return-value">+{{ data?.avg_winner_return | number:'1.2-2' }}%</span>
            </div>
          </div>
          <div class="return-item negative">
            <mat-icon>trending_down</mat-icon>
            <div class="return-content">
              <span class="return-label">Avg Loser</span>
              <span class="return-value">{{ data?.avg_loser_return | number:'1.2-2' }}%</span>
            </div>
          </div>
        </div>
      </mat-card>

      <!-- Holding Periods -->
      <mat-card class="section-card">
        <h3 class="section-title">Holding Periods</h3>
        <div class="holding-grid">
          <div class="holding-item">
            <span class="holding-value">{{ data?.avg_holding_days | number:'1.0-0' }}</span>
            <span class="holding-label">Avg Days</span>
          </div>
          <div class="holding-item">
            <span class="holding-value">{{ data?.avg_winner_holding_days | number:'1.0-0' }}</span>
            <span class="holding-label">Winners</span>
          </div>
          <div class="holding-item">
            <span class="holding-value">{{ data?.avg_loser_holding_days | number:'1.0-0' }}</span>
            <span class="holding-label">Losers</span>
          </div>
        </div>
      </mat-card>

      <!-- Exit Reasons -->
      <mat-card class="section-card" *ngIf="data?.exits_by_reason && getExitReasons().length > 0">
        <h3 class="section-title">Exit Reasons</h3>
        <div class="exit-chips">
          <mat-chip *ngFor="let reason of getExitReasons()" [class]="getExitClass(reason.key)">
            {{ formatExitReason(reason.key) }}: {{ reason.count }}
          </mat-chip>
        </div>
      </mat-card>

      <!-- By Symbol Table -->
      <mat-card class="section-card" *ngIf="data?.by_symbol?.length">
        <h3 class="section-title">By Symbol</h3>
        <table mat-table [dataSource]="data?.by_symbol ?? []" class="symbol-table">
          <ng-container matColumnDef="symbol">
            <th mat-header-cell *matHeaderCellDef>Symbol</th>
            <td mat-cell *matCellDef="let row">{{ row.symbol }}</td>
          </ng-container>

          <ng-container matColumnDef="signals">
            <th mat-header-cell *matHeaderCellDef>Signals</th>
            <td mat-cell *matCellDef="let row">{{ row.signals }}</td>
          </ng-container>

          <ng-container matColumnDef="winners">
            <th mat-header-cell *matHeaderCellDef>Winners</th>
            <td mat-cell *matCellDef="let row">{{ row.winners }}</td>
          </ng-container>

          <ng-container matColumnDef="hit_rate">
            <th mat-header-cell *matHeaderCellDef>Hit Rate</th>
            <td mat-cell *matCellDef="let row" [class.good]="row.hit_rate >= 50">
              {{ row.hit_rate | number:'1.1-1' }}%
            </td>
          </ng-container>

          <ng-container matColumnDef="avg_return">
            <th mat-header-cell *matHeaderCellDef>Avg Return</th>
            <td mat-cell *matCellDef="let row"
                [class.positive]="row.avg_return > 0"
                [class.negative]="row.avg_return < 0">
              {{ row.avg_return >= 0 ? '+' : '' }}{{ row.avg_return | number:'1.2-2' }}%
            </td>
          </ng-container>

          <ng-container matColumnDef="total_pnl">
            <th mat-header-cell *matHeaderCellDef>Total P&L</th>
            <td mat-cell *matCellDef="let row"
                [class.positive]="row.total_pnl > 0"
                [class.negative]="row.total_pnl < 0">
              {{ row.total_pnl >= 0 ? '+' : '' }}{{ row.total_pnl | number:'1.2-2' }}%
            </td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
        </table>
      </mat-card>

      <!-- Empty State -->
      <mat-card class="empty-card" *ngIf="!data || data.total_signals === 0">
        <mat-icon>insights</mat-icon>
        <p>No signal data available</p>
        <span class="empty-hint">Signal performance is tracked when positions are closed</span>
      </mat-card>
    </div>
  `,
  styles: [`
    .signal-grid {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .summary-cards {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }

    .stat-card {
      padding: 16px;
    }

    .stat-card.highlight {
      background: linear-gradient(135deg, var(--color-accent-soft) 0%, var(--color-accent-softer) 100%);
    }

    .stat-main {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
    }

    .stat-sub {
      margin-top: 8px;
      font-size: 12px;
      color: var(--color-muted);
      text-align: center;
    }

    .stat-row {
      display: flex;
      justify-content: space-around;
    }

    .stat-item {
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    .stat-value {
      font-size: 20px;
      font-weight: 600;
      color: var(--color-text);
    }

    .stat-value.large {
      font-size: 32px;
    }

    .stat-label {
      font-size: 12px;
      color: var(--color-muted);
    }

    .good {
      color: var(--color-success);
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

    .returns-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }

    .return-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px;
      border-radius: 8px;
    }

    .return-item.positive {
      background: var(--color-success-soft);
      color: var(--color-success);
    }

    .return-item.negative {
      background: var(--color-danger-soft);
      color: var(--color-danger);
    }

    .return-content {
      display: flex;
      flex-direction: column;
    }

    .return-label {
      font-size: 12px;
      opacity: 0.8;
    }

    .return-value {
      font-size: 20px;
      font-weight: 600;
    }

    .holding-grid {
      display: flex;
      justify-content: space-around;
    }

    .holding-item {
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    .holding-value {
      font-size: 28px;
      font-weight: 600;
      color: var(--color-accent);
    }

    .holding-label {
      font-size: 12px;
      color: var(--color-muted);
    }

    .exit-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .exit-chips mat-chip {
      font-size: 12px;
    }

    .symbol-table {
      width: 100%;
    }

    .positive {
      color: var(--color-success);
    }

    .negative {
      color: var(--color-danger);
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

    .empty-hint {
      font-size: 12px;
      color: var(--color-muted);
    }

    @media (max-width: 960px) {
      .summary-cards {
        grid-template-columns: repeat(2, 1fr);
      }
    }
  `]
})
export class SignalStatsComponent {
  @Input() data: SignalPerformance | null = null;

  displayedColumns = ['symbol', 'signals', 'winners', 'hit_rate', 'avg_return', 'total_pnl'];

  getExitReasons(): { key: string; count: number }[] {
    if (!this.data?.exits_by_reason) return [];
    return Object.entries(this.data.exits_by_reason).map(([key, count]) => ({ key, count }));
  }

  formatExitReason(reason: string): string {
    return reason.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }

  getExitClass(reason: string): string {
    if (reason.includes('stop')) return 'exit-stop';
    if (reason.includes('flip')) return 'exit-flip';
    return 'exit-other';
  }
}
