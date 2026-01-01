import { Component, Input, OnInit, OnChanges, SimpleChanges, ChangeDetectorRef } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import {
  SymbolDetailService,
  SymbolDetail,
  DailyPrice,
} from '../../../../../core/services/symbol-detail.service';
import { PriceChart, ChartType } from '../../../../../shared/components/price-chart/price-chart';
import { MetricTooltip } from '../../../../../shared/components/metric-tooltip/metric-tooltip';

@Component({
  selector: 'app-overview-tab',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonToggleModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatTooltipModule,
    DecimalPipe,
    PriceChart,
    MetricTooltip,
  ],
  templateUrl: './overview-tab.html',
  styleUrl: './overview-tab.scss',
})
export class OverviewTab implements OnInit, OnChanges {
  @Input() symbol!: string;
  @Input() detail!: SymbolDetail;

  prices: DailyPrice[] = [];
  loadingPrices = false;
  selectedDays = 30;
  chartType: ChartType = 'candlestick';

  // Quick stats computed from prices
  latestPrice: number | null = null;
  priceChange: number | null = null;
  priceChangePercent: number | null = null;
  latestVolume: number | null = null;

  dayOptions = [
    { value: 30, label: '1M' },
    { value: 90, label: '3M' },
    { value: 180, label: '6M' },
    { value: 365, label: '1Y' },
  ];

  constructor(
    private symbolService: SymbolDetailService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadPrices();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['symbol'] && !changes['symbol'].firstChange) {
      this.loadPrices();
    }
  }

  loadPrices(): void {
    // Defer to avoid ExpressionChangedAfterItHasBeenCheckedError
    Promise.resolve().then(() => {
      this.loadingPrices = true;
      this.cdr.detectChanges();
    });

    this.symbolService.getPrices(this.symbol, this.selectedDays).subscribe({
      next: (prices) => {
        this.prices = prices;
        this.computeQuickStats();
        this.loadingPrices = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load prices:', err);
        this.prices = [];
        this.loadingPrices = false;
        this.cdr.detectChanges();
      },
    });
  }

  onDaysChange(): void {
    this.loadPrices();
  }

  private computeQuickStats(): void {
    if (this.prices.length === 0) {
      this.latestPrice = null;
      this.priceChange = null;
      this.priceChangePercent = null;
      this.latestVolume = null;
      return;
    }

    const latest = this.prices[this.prices.length - 1];
    this.latestPrice = latest.close;
    this.latestVolume = latest.volume;

    if (this.prices.length > 1) {
      const previous = this.prices[this.prices.length - 2];
      this.priceChange = latest.close - previous.close;
      this.priceChangePercent = (this.priceChange / previous.close) * 100;
    }
  }

  formatLargeNumber(value: number | null | undefined): string {
    if (value == null) return '-';
    if (value >= 1e12) return (value / 1e12).toFixed(2) + 'T';
    if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return (value / 1e3).toFixed(2) + 'K';
    return value.toFixed(2);
  }

  formatPercent(value: number | null | undefined): string {
    if (value == null) return '-';
    return (value * 100).toFixed(2) + '%';
  }
}
