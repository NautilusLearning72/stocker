import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTableModule } from '@angular/material/table';
import { InstrumentInfoService, InstrumentInfo } from '../../../core/services/instrument-info.service';
import { SignalService, Signal } from '../../../core/services/signal.service';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { SymbolLink } from '../../../shared/components/symbol-link/symbol-link';

@Component({
  selector: 'app-signal-list',
  imports: [CommonModule, MatTableModule, MatChipsModule, MatIconModule, SymbolLink],
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
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.fetchSignals();
  }

  fetchSignals(): void {
    this.loading = true;
    this.signalService.getLatestSignals().subscribe({
      next: (signals) => {
        const mapped = signals.map((s) => ({
          ...s,
          momentum: Number(s.lookback_return ?? 0),
          volatility: Number(s.ewma_vol ?? 0),
        }));
        // Defer assignment to avoid ExpressionChanged errors
        Promise.resolve().then(() => {
          this.dataSource = mapped;
          const symbols = Array.from(new Set(signals.map((s) => s.symbol)));
          this.loadNames(symbols);
          this.loading = false;
          this.cdr.detectChanges();
        });
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
        Promise.resolve().then(() => {
          this.instrumentNames = map;
          this.dataSource = this.dataSource.map((s) => ({
            ...s,
            name: this.instrumentNames[s.symbol] || s.symbol,
          }));
          this.cdr.detectChanges();
        });
      },
      error: (err) => console.error('Failed to load instrument names', err),
    });
  }
}
