import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MonthlyReturn } from '../../../../core/services/performance.service';

interface HeatmapCell {
  month: number;
  return_pct: number | null;
}

interface HeatmapRow {
  year: number;
  months: HeatmapCell[];
  ytd: number;
}

@Component({
  selector: 'app-monthly-heatmap',
  standalone: true,
  imports: [CommonModule, MatTooltipModule],
  template: `
    <div class="heatmap-container">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th class="year-col">Year</th>
            <th *ngFor="let month of monthNames" class="month-col">{{ month }}</th>
            <th class="ytd-col">YTD</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let row of heatmapData">
            <td class="year-col">{{ row.year }}</td>
            <td *ngFor="let cell of row.months"
                class="month-cell"
                [style.background-color]="getCellColor(cell.return_pct)"
                [matTooltip]="getTooltip(row.year, cell.month, cell.return_pct)">
              <span *ngIf="cell.return_pct !== null" [class.positive]="cell.return_pct > 0" [class.negative]="cell.return_pct < 0">
                {{ formatValue(cell.return_pct) }}
              </span>
            </td>
            <td class="ytd-cell"
                [style.background-color]="getCellColor(row.ytd)"
                [class.positive]="row.ytd > 0"
                [class.negative]="row.ytd < 0">
              {{ formatValue(row.ytd) }}
            </td>
          </tr>
        </tbody>
      </table>

      <div class="legend">
        <span class="legend-label">-20%</span>
        <div class="legend-gradient"></div>
        <span class="legend-label">+20%</span>
      </div>
    </div>
  `,
  styles: [`
    .heatmap-container {
      overflow-x: auto;
    }

    .heatmap-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }

    th, td {
      padding: 8px 4px;
      text-align: center;
      border: 1px solid rgba(0, 0, 0, 0.08);
    }

    th {
      background: #f5f5f5;
      font-weight: 500;
      color: #666;
    }

    .year-col {
      width: 60px;
      font-weight: 500;
    }

    .month-col {
      width: 55px;
    }

    .ytd-col, .ytd-cell {
      width: 60px;
      font-weight: 500;
    }

    .month-cell {
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .month-cell:hover {
      opacity: 0.8;
    }

    .month-cell span {
      font-weight: 500;
    }

    .positive {
      color: #1B5E20;
    }

    .negative {
      color: #B71C1C;
    }

    .legend {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      margin-top: 16px;
      font-size: 11px;
      color: #666;
    }

    .legend-gradient {
      width: 200px;
      height: 12px;
      background: linear-gradient(to right, #F44336, #FFCDD2, #FFFFFF, #C8E6C9, #4CAF50);
      border-radius: 2px;
    }

    .legend-label {
      min-width: 40px;
    }
  `]
})
export class MonthlyHeatmap implements OnChanges {
  @Input() monthlyReturns: MonthlyReturn[] = [];

  monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  heatmapData: HeatmapRow[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['monthlyReturns']) {
      this.buildHeatmap();
    }
  }

  private buildHeatmap(): void {
    if (!this.monthlyReturns || this.monthlyReturns.length === 0) {
      this.heatmapData = [];
      return;
    }

    // Group by year
    const yearMap = new Map<number, Map<number, number>>();

    for (const mr of this.monthlyReturns) {
      if (!yearMap.has(mr.year)) {
        yearMap.set(mr.year, new Map());
      }
      yearMap.get(mr.year)!.set(mr.month, mr.return_pct);
    }

    // Build rows
    const years = Array.from(yearMap.keys()).sort((a, b) => b - a); // Descending

    this.heatmapData = years.map(year => {
      const monthData = yearMap.get(year)!;
      const months: HeatmapCell[] = [];
      let ytdReturn = 1;

      for (let m = 1; m <= 12; m++) {
        const ret = monthData.get(m) ?? null;
        months.push({ month: m, return_pct: ret });
        if (ret !== null) {
          ytdReturn *= (1 + ret / 100);
        }
      }

      return {
        year,
        months,
        ytd: (ytdReturn - 1) * 100
      };
    });
  }

  getCellColor(value: number | null): string {
    if (value === null) return 'transparent';

    // Clamp to -20% to +20% range
    const clamped = Math.max(-20, Math.min(20, value));
    const normalized = (clamped + 20) / 40; // 0 to 1

    if (value >= 0) {
      // Green gradient
      const intensity = Math.min(value / 20, 1);
      const r = Math.round(200 - intensity * 128);
      const g = Math.round(230 - intensity * 50);
      const b = Math.round(201 - intensity * 121);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      // Red gradient
      const intensity = Math.min(-value / 20, 1);
      const r = Math.round(255 - intensity * 11);
      const g = Math.round(205 - intensity * 127);
      const b = Math.round(210 - intensity * 156);
      return `rgb(${r}, ${g}, ${b})`;
    }
  }

  getTooltip(year: number, month: number, value: number | null): string {
    if (value === null) return `${this.monthNames[month - 1]} ${year}: No data`;
    const sign = value >= 0 ? '+' : '';
    return `${this.monthNames[month - 1]} ${year}: ${sign}${value.toFixed(2)}%`;
  }

  formatValue(value: number | null): string {
    if (value === null) return '';
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(1);
  }
}
