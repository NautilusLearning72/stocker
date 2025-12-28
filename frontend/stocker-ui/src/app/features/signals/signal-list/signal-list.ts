import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';

export interface Signal {
  date: string;
  symbol: string;
  momentum: number;
  volatility: number;
  direction: number;
  weight: number;
}

const ELEMENT_DATA: Signal[] = [
  { date: '2025-12-28', symbol: 'AAPL', momentum: 0.15, volatility: 0.22, direction: 1, weight: 0.05 },
  { date: '2025-12-28', symbol: 'MSFT', momentum: -0.05, volatility: 0.18, direction: -1, weight: 0.00 },
  { date: '2025-12-28', symbol: 'SPY', momentum: 0.08, volatility: 0.12, direction: 1, weight: 0.15 },
  { date: '2025-12-28', symbol: 'GLD', momentum: 0.02, volatility: 0.10, direction: 1, weight: 0.12 },
];

@Component({
  selector: 'app-signal-list',
  imports: [CommonModule, MatTableModule],
  templateUrl: './signal-list.html',
  styleUrl: './signal-list.scss',
})
export class SignalList {
  displayedColumns: string[] = ['date', 'symbol', 'momentum', 'volatility', 'direction', 'weight'];
  dataSource = ELEMENT_DATA;
}
