import { AfterViewInit, Component, Input, ViewChild } from '@angular/core';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { CommonModule } from '@angular/common';
import { SymbolLink } from '../../../shared/components/symbol-link/symbol-link';
import { MatSort, MatSortModule } from '@angular/material/sort';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

export interface HoldingDisplay {
  symbol: string;
  name?: string;
  qty: number;
  side?: string | null;
  current_price?: number | null;
  avg_entry_price?: number | null;
  cost_basis?: number | null;
  market_value?: number | null;
  unrealized_intraday_pl?: number | null;
  unrealized_intraday_plpc?: number | null;
  unrealized_pl?: number | null;
  unrealized_plpc?: number | null;
}

@Component({
  selector: 'app-holdings-table',
  imports: [
    MatTableModule,
    CommonModule,
    SymbolLink,
    MatSortModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './holdings-table.html',
  styleUrl: './holdings-table.scss',
})
export class HoldingsTable implements AfterViewInit {
  displayedColumns: string[] = [
    'symbol',
    'name',
    'current_price',
    'qty',
    'side',
    'market_value',
    'avg_entry_price',
    'cost_basis',
    'today_pl_pct',
    'today_pl',
    'total_pl_pct',
    'total_pl',
  ];

  @Input() set holdings(value: HoldingDisplay[]) {
    this.dataSource.data = value || [];
    this.applyFilter();
  }

  @Input() set instrumentNames(value: Record<string, string>) {
    this._instrumentNames = value || {};
    this.applyFilter();
  }
  get instrumentNames(): Record<string, string> {
    return this._instrumentNames;
  }

  @ViewChild(MatSort) sort?: MatSort;

  filterText = '';
  sideFilter = 'ALL';

  dataSource = new MatTableDataSource<HoldingDisplay>([]);
  private _instrumentNames: Record<string, string> = {};

  ngAfterViewInit(): void {
    if (this.sort) {
      this.dataSource.sort = this.sort;
    }
    this.dataSource.filterPredicate = (data, rawFilter) => {
      let criteria: { text: string; side: string };
      try {
        criteria = JSON.parse(rawFilter) as { text: string; side: string };
      } catch {
        criteria = { text: rawFilter, side: 'ALL' };
      }
      const text = (criteria.text || '').trim().toLowerCase();
      const side = (criteria.side || 'ALL').toUpperCase();
      const symbol = (data.symbol || '').toLowerCase();
      const name = (this.instrumentNames[data.symbol] || '').toLowerCase();
      const matchesText = !text || symbol.includes(text) || name.includes(text);
      const sideValue = (data.side || '').toUpperCase();
      const matchesSide = side === 'ALL' || (!!sideValue && sideValue === side);
      return matchesText && matchesSide;
    };
    this.dataSource.sortingDataAccessor = (item, property) => {
      switch (property) {
        case 'name':
          return this.instrumentNames[item.symbol] || '';
        case 'symbol':
          return item.symbol || '';
        case 'side':
          return (item.side || '').toUpperCase();
        case 'qty':
          return this.toNumber(item.qty);
        case 'current_price':
          return this.toNumber(item.current_price);
        case 'avg_entry_price':
          return this.toNumber(item.avg_entry_price);
        case 'market_value':
          return this.toNumber(item.market_value);
        case 'cost_basis':
          return this.toNumber(item.cost_basis);
        case 'today_pl':
          return this.toNumber(item.unrealized_intraday_pl);
        case 'today_pl_pct':
          return this.toNumber(item.unrealized_intraday_plpc);
        case 'total_pl':
          return this.toNumber(item.unrealized_pl);
        case 'total_pl_pct':
          return this.toNumber(item.unrealized_plpc);
        default:
          return this.toNumber((item as any)[property]);
      }
    };
    this.applyFilter();
  }

  applyFilter(): void {
    const payload = JSON.stringify({
      text: this.filterText,
      side: this.sideFilter,
    });
    this.dataSource.filter = payload;
  }

  clearFilters(): void {
    this.filterText = '';
    this.sideFilter = 'ALL';
    this.applyFilter();
  }

  pnlClass(value?: number | null): string {
    if (!value) {
      return '';
    }
    return value > 0 ? 'positive' : 'negative';
  }

  formatPercent(value?: number | null): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return `${(value * 100).toFixed(2)}%`;
  }

  private toNumber(value: unknown): number {
    if (value === null || value === undefined) {
      return 0;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : 0;
  }
}
