import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { forkJoin } from 'rxjs';

import { PortfolioService, Holding } from '../../../../../core/services/portfolio';
import { OrdersService, Order } from '../../../../../core/services/orders';
import { SignalService, Signal } from '../../../../../core/services/signal.service';

@Component({
  selector: 'app-activity-tab',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatTableModule,
    MatChipsModule,
  ],
  templateUrl: './activity-tab.html',
  styleUrl: './activity-tab.scss',
})
export class ActivityTab implements OnInit, OnChanges {
  @Input() symbol!: string;

  holding: Holding | null = null;
  orders: Order[] = [];
  signals: Signal[] = [];
  loading = false;

  orderColumns = ['date', 'side', 'qty', 'status', 'fill_price'];
  signalColumns = ['date', 'direction', 'target_weight', 'momentum', 'volatility'];

  constructor(
    private portfolioService: PortfolioService,
    private ordersService: OrdersService,
    private signalService: SignalService
  ) {}

  ngOnInit(): void {
    this.loadData();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['symbol'] && !changes['symbol'].firstChange) {
      this.loadData();
    }
  }

  loadData(): void {
    this.loading = true;

    forkJoin({
      holdings: this.portfolioService.getHoldings(),
      orders: this.ordersService.getOrders('main', 100),
      signals: this.signalService.getSignals(undefined, this.symbol),
    }).subscribe({
      next: ({ holdings, orders, signals }) => {
        // Find holding for this symbol
        this.holding = holdings.find((h) => h.symbol === this.symbol) || null;

        // Filter orders for this symbol
        this.orders = orders
          .filter((o) => o.symbol === this.symbol)
          .slice(0, 20);

        // Signals are already filtered by symbol from backend
        this.signals = signals.slice(0, 20);

        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load activity data:', err);
        this.loading = false;
      },
    });
  }

  getDirectionLabel(direction: number | null): string {
    if (direction === 1) return 'Long';
    if (direction === -1) return 'Short';
    return 'Flat';
  }

  getDirectionClass(direction: number | null): string {
    if (direction === 1) return 'long';
    if (direction === -1) return 'short';
    return 'flat';
  }

  getSideClass(side: string | null): string {
    if (side?.toUpperCase() === 'BUY') return 'buy';
    if (side?.toUpperCase() === 'SELL') return 'sell';
    return '';
  }

  getStatusClass(status: string | null): string {
    const s = status?.toLowerCase();
    if (s === 'filled' || s === 'complete') return 'filled';
    if (s === 'pending' || s === 'new') return 'pending';
    if (s === 'cancelled' || s === 'rejected') return 'cancelled';
    return '';
  }

  getFillPrice(order: Order): number | null {
    if (!order.fills || order.fills.length === 0) return null;
    const totalValue = order.fills.reduce((sum, f) => sum + f.qty * f.price, 0);
    const totalQty = order.fills.reduce((sum, f) => sum + f.qty, 0);
    return totalQty > 0 ? totalValue / totalQty : null;
  }

  getPnL(): number | null {
    if (!this.holding) return null;
    return this.holding.market_value - this.holding.cost_basis;
  }

  getPnLPercent(): number | null {
    if (!this.holding || this.holding.cost_basis === 0) return null;
    return ((this.holding.market_value - this.holding.cost_basis) / this.holding.cost_basis) * 100;
  }
}
