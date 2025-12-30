import { Component, Input } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { CommonModule } from '@angular/common';

export interface HoldingDisplay {
  symbol: string;
  name?: string;
  qty: number;
  cost_basis: number;
  market_value: number;
}

@Component({
  selector: 'app-holdings-table',
  imports: [MatTableModule, CommonModule],
  templateUrl: './holdings-table.html',
  styleUrl: './holdings-table.scss',
})
export class HoldingsTable {
  displayedColumns: string[] = ['symbol', 'name', 'qty', 'cost_basis', 'market_value'];

  @Input() set holdings(value: any[]) {
    this.dataSource = value || [];
  }

  @Input() instrumentNames: Record<string, string> = {};

  dataSource: HoldingDisplay[] = [];
}
