import { Component, Input } from '@angular/core';
import { CommonModule, DecimalPipe, CurrencyPipe } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ExecutionMetrics } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-execution-quality',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatTableModule, MatIconModule, MatTooltipModule, DecimalPipe, CurrencyPipe],
  template: `
    <div class="execution-grid">
      <!-- Summary Cards -->
      <div class="summary-cards">
        <mat-card class="stat-card">
          <div class="stat-icon orders">
            <mat-icon>receipt_long</mat-icon>
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ data?.total_orders ?? 0 }}</span>
            <span class="stat-label">Total Orders</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-icon fill-rate" [class.good]="(data?.fill_rate ?? 0) >= 95">
            <mat-icon>check_circle</mat-icon>
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ data?.fill_rate | number:'1.1-1' }}%</span>
            <span class="stat-label">Fill Rate</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-icon partial">
            <mat-icon>pie_chart</mat-icon>
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ data?.partial_fills ?? 0 }}</span>
            <span class="stat-label">Partial Fills</span>
          </div>
        </mat-card>

        <mat-card class="stat-card">
          <div class="stat-icon rejected" [class.warning]="(data?.rejected_orders ?? 0) > 0">
            <mat-icon>cancel</mat-icon>
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ data?.rejected_orders ?? 0 }}</span>
            <span class="stat-label">Rejected</span>
          </div>
        </mat-card>
      </div>

      <!-- Cost Analysis -->
      <mat-card class="section-card">
        <h3 class="section-title">Cost Analysis</h3>
        <div class="cost-grid">
          <div class="cost-item">
            <span class="cost-label">Total Commission</span>
            <span class="cost-value">{{ data?.total_commission | currency:'USD' }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label">Total Slippage</span>
            <span class="cost-value">{{ data?.total_slippage | currency:'USD' }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label" matTooltip="Average slippage in basis points">Avg Slippage</span>
            <span class="cost-value">{{ data?.avg_slippage_bps | number:'1.1-1' }} bps</span>
          </div>
          <div class="cost-item">
            <span class="cost-label" matTooltip="Commission as percentage of NAV">Commission % NAV</span>
            <span class="cost-value">{{ data?.commission_as_pct_nav | number:'1.3-3' }}%</span>
          </div>
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

          <ng-container matColumnDef="orders">
            <th mat-header-cell *matHeaderCellDef>Orders</th>
            <td mat-cell *matCellDef="let row">{{ row.orders }}</td>
          </ng-container>

          <ng-container matColumnDef="filled">
            <th mat-header-cell *matHeaderCellDef>Filled</th>
            <td mat-cell *matCellDef="let row">{{ row.filled }}</td>
          </ng-container>

          <ng-container matColumnDef="fill_rate">
            <th mat-header-cell *matHeaderCellDef>Fill Rate</th>
            <td mat-cell *matCellDef="let row" [class.good]="row.fill_rate >= 95">
              {{ row.fill_rate | number:'1.1-1' }}%
            </td>
          </ng-container>

          <ng-container matColumnDef="slippage">
            <th mat-header-cell *matHeaderCellDef>Slippage</th>
            <td mat-cell *matCellDef="let row">{{ row.avg_slippage_bps | number:'1.1-1' }} bps</td>
          </ng-container>

          <ng-container matColumnDef="commission">
            <th mat-header-cell *matHeaderCellDef>Commission</th>
            <td mat-cell *matCellDef="let row">{{ row.total_commission | currency:'USD' }}</td>
          </ng-container>

          <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
          <tr mat-row *matRowDef="let row; columns: displayedColumns;"></tr>
        </table>
      </mat-card>

      <!-- Empty State -->
      <mat-card class="empty-card" *ngIf="!data || data.total_orders === 0">
        <mat-icon>inbox</mat-icon>
        <p>No execution data available</p>
      </mat-card>
    </div>
  `,
  styles: [`
    .execution-grid {
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
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px;
    }

    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--color-accent-soft);
      color: var(--color-accent);
    }

    .stat-icon.orders { background: var(--color-accent-soft); color: var(--color-accent); }
    .stat-icon.fill-rate { background: var(--color-success-soft); color: var(--color-success); }
    .stat-icon.fill-rate.good { background: var(--color-success-muted); }
    .stat-icon.partial { background: var(--color-warning-soft); color: var(--color-warning); }
    .stat-icon.rejected { background: var(--color-danger-soft); color: var(--color-danger); }
    .stat-icon.rejected.warning { background: var(--color-danger-muted); }

    .stat-content {
      display: flex;
      flex-direction: column;
    }

    .stat-value {
      font-size: 24px;
      font-weight: 600;
      color: var(--color-text);
    }

    .stat-label {
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

    .cost-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 24px;
    }

    .cost-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .cost-label {
      font-size: 12px;
      color: var(--color-muted);
    }

    .cost-value {
      font-size: 18px;
      font-weight: 600;
      color: var(--color-text);
    }

    .symbol-table {
      width: 100%;
    }

    .good {
      color: var(--color-success);
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
      .summary-cards {
        grid-template-columns: repeat(2, 1fr);
      }

      .cost-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }
  `]
})
export class ExecutionQualityComponent {
  @Input() data: ExecutionMetrics | null = null;

  displayedColumns = ['symbol', 'orders', 'filled', 'fill_rate', 'slippage', 'commission'];
}
