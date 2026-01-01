import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { StreamService } from '../../../core/services/stream';
import { PortfolioService, Holding, PositionSnapshot } from '../../../core/services/portfolio';
import { OrdersService, Order } from '../../../core/services/orders';
import { PortfolioSummary } from '../portfolio-summary/portfolio-summary';
import { HoldingsTable } from '../holdings-table/holdings-table';
import { OrdersTable } from '../orders-table/orders-table';
import { InstrumentInfoService, InstrumentInfo } from '../../../core/services/instrument-info.service';
import { MatTabsModule } from '@angular/material/tabs';

@Component({
  selector: 'app-dashboard-home',
  imports: [CommonModule, PortfolioSummary, HoldingsTable, OrdersTable, MatTabsModule],
  templateUrl: './dashboard-home.html',
  styleUrl: './dashboard-home.scss',
})
export class DashboardHome implements OnInit, OnDestroy {
  metrics = [
    { label: 'Net Asset Value', value: 0, format: 'currency', digits: '1.0-0' },
    { label: 'Cash Balance', value: 0, format: 'currency', digits: '1.0-0' },
    { label: 'Gross Exposure', value: 0, format: 'percent', digits: '1.0-0' },
    { label: 'Drawdown', value: 0, format: 'percent', digits: '1.2-2' }
  ];

  holdings: PositionSnapshot[] = [];
  orders: Order[] = [];
  instrumentNames: Record<string, string> = {};

  private sub?: Subscription;

  constructor(
    private streamService: StreamService,
    private portfolioService: PortfolioService,
    private ordersService: OrdersService,
    private cdr: ChangeDetectorRef,
    private infoService: InstrumentInfoService,
  ) { }

  ngOnInit() {
    // Fetch initial data from API
    this.loadPortfolioData();

    // Subscribe to real-time updates
    this.sub = this.streamService.events$.subscribe(msg => {
      if (msg.event === 'update' && msg.data?.type === 'portfolio_update') {
        this.updateMetrics(msg.data.payload);
      }
    });
  }

  loadPortfolioData() {
    // Get portfolio state
    this.portfolioService.getState().subscribe({
      next: (state) => {
        if (state) {
          this.metrics = [
            { label: 'Net Asset Value', value: Number(state.nav), format: 'currency', digits: '1.0-0' },
            { label: 'Cash Balance', value: Number(state.cash), format: 'currency', digits: '1.0-0' },
            { label: 'Gross Exposure', value: Number(state.gross_exposure) * 100, format: 'percent', digits: '1.0-0' },
            { label: 'Drawdown', value: Number(state.drawdown) * 100, format: 'percent', digits: '1.2-2' }
          ];
          this.cdr.detectChanges();
        }
      },
      error: (err) => console.error('Failed to load portfolio state:', err)
    });

    // Get positions snapshot (fallback to holdings if empty)
    this.portfolioService.getPositions().subscribe({
      next: (positions) => {
        if (positions.length) {
          this.holdings = [...positions];
          this.loadInstrumentNames(this.holdings);
          this.cdr.detectChanges();
        } else {
          this.loadHoldingsFallback();
        }
      },
      error: (err) => {
        console.error('Failed to load positions:', err);
        this.loadHoldingsFallback();
      }
    });

    // Get orders
    this.ordersService.getOrders().subscribe({
      next: (orders) => {
        this.orders = [...orders];
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load orders:', err)
    });
  }

  ngOnDestroy() {
    this.sub?.unsubscribe();
  }

  private updateMetrics(data: any) {
    if (!data) return;
    this.metrics = [
      { label: 'Net Asset Value', value: data.nav, format: 'currency', digits: '1.0-0' },
      { label: 'Cash Balance', value: data.cash, format: 'currency', digits: '1.0-0' },
      { label: 'Gross Exposure', value: data.exposure_pct * 100, format: 'percent', digits: '1.0-0' },
      { label: 'Drawdown', value: data.drawdown * 100, format: 'percent', digits: '1.2-2' }
    ];
  }

  private loadHoldingsFallback() {
    this.portfolioService.getHoldings().subscribe({
      next: (holdings: Holding[]) => {
        this.holdings = holdings.map((holding) => ({
          ...holding,
          avg_entry_price: null,
          current_price: null,
          unrealized_pl: null,
          unrealized_plpc: null,
          unrealized_intraday_pl: null,
          unrealized_intraday_plpc: null,
          side: holding.qty < 0 ? 'SHORT' : 'LONG',
        }));
        this.loadInstrumentNames(this.holdings);
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load holdings:', err),
    });
  }

  private loadInstrumentNames(holdings: Array<{ symbol: string }>) {
    const orderSymbols = Array.from(new Set((this.orders || []).map(o => o.symbol))).filter(Boolean);
    const holdingSymbols = Array.from(new Set((holdings || []).map(h => h.symbol))).filter(Boolean);
    const symbols = Array.from(new Set([...holdingSymbols, ...orderSymbols]));
    if (!symbols.length) {
      this.instrumentNames = {};
      return;
    }
    this.infoService.getInfo(symbols).subscribe({
      next: (rows: InstrumentInfo[]) => {
        const map: Record<string, string> = {};
        rows.forEach(info => {
          map[info.symbol] = info.name || info.symbol;
        });
        this.instrumentNames = map;
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load instrument names', err),
    });
  }
}
