import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { StreamService } from '../../../core/services/stream';
import { PortfolioService, Holding } from '../../../core/services/portfolio';
import { OrdersService, Order } from '../../../core/services/orders';
import { PortfolioSummary } from '../portfolio-summary/portfolio-summary';
import { HoldingsTable } from '../holdings-table/holdings-table';
import { OrdersTable } from '../orders-table/orders-table';

@Component({
  selector: 'app-dashboard-home',
  imports: [CommonModule, PortfolioSummary, HoldingsTable, OrdersTable],
  templateUrl: './dashboard-home.html',
  styleUrl: './dashboard-home.scss',
})
export class DashboardHome implements OnInit, OnDestroy {
  metrics = [
    { label: 'Net Asset Value', value: 0, format: 'currency' },
    { label: 'Cash Balance', value: 0, format: 'currency' },
    { label: 'Gross Exposure', value: 0, format: 'percent' },
    { label: 'Drawdown', value: 0, format: 'percent' }
  ];

  holdings: Holding[] = [];
  orders: Order[] = [];

  private sub?: Subscription;

  constructor(
    private streamService: StreamService,
    private portfolioService: PortfolioService,
    private ordersService: OrdersService,
    private cdr: ChangeDetectorRef
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
            { label: 'Net Asset Value', value: Number(state.nav), format: 'currency' },
            { label: 'Cash Balance', value: Number(state.cash), format: 'currency' },
            { label: 'Gross Exposure', value: Number(state.gross_exposure) * 100, format: 'percent' },
            { label: 'Drawdown', value: Number(state.drawdown) * 100, format: 'percent' }
          ];
          this.cdr.detectChanges();
        }
      },
      error: (err) => console.error('Failed to load portfolio state:', err)
    });

    // Get holdings
    this.portfolioService.getHoldings().subscribe({
      next: (holdings) => {
        this.holdings = [...holdings];
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load holdings:', err)
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
      { label: 'Net Asset Value', value: data.nav, format: 'currency' },
      { label: 'Cash Balance', value: data.cash, format: 'currency' },
      { label: 'Gross Exposure', value: data.exposure_pct * 100, format: 'percent' },
      { label: 'Drawdown', value: data.drawdown * 100, format: 'percent' }
    ];
  }
}
