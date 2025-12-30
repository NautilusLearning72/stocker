import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { InstrumentInfoService, InstrumentInfo } from '../../../core/services/instrument-info.service';
import { SignalService, Signal } from '../../../core/services/signal.service';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-signal-list',
  imports: [CommonModule, MatTableModule, MatChipsModule, MatIconModule],
  templateUrl: './signal-list.html',
  styleUrl: './signal-list.scss',
})
export class SignalList implements OnInit {
  displayedColumns: string[] = ['date', 'symbol', 'name', 'momentum', 'volatility', 'direction', 'weight'];
  dataSource: (Signal & { name?: string })[] = [];
  instrumentNames: Record<string, string> = {};
  loading = false;
  errorMsg = '';

  constructor(
    private infoService: InstrumentInfoService,
    private signalService: SignalService,
  ) {}

  ngOnInit(): void {
    this.fetchSignals();
  }

  fetchSignals(): void {
    this.loading = true;
    this.signalService.getLatestSignals().subscribe({
      next: (signals) => {
        this.dataSource = signals.map((s) => ({
          ...s,
          momentum: s.lookback_return ?? 0,
          volatility: s.ewma_vol ?? 0,
        }));
        const symbols = Array.from(new Set(signals.map((s) => s.symbol)));
        this.loadNames(symbols);
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = 'Failed to load signals';
        console.error(err);
      },
    });
  }

  loadNames(symbols: string[]): void {
    if (!symbols.length) return;
    this.infoService.getInfo(symbols).subscribe({
      next: (rows: InstrumentInfo[]) => {
        const map: Record<string, string> = {};
        rows.forEach((info) => (map[info.symbol] = info.name || info.symbol));
        this.instrumentNames = map;
        this.dataSource = this.dataSource.map((s) => ({
          ...s,
          name: this.instrumentNames[s.symbol] || s.symbol,
        }));
      },
      error: (err) => console.error('Failed to load instrument names', err),
    });
  }
}
