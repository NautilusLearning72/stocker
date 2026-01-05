import { Component, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';

import { InstrumentMetrics } from '../../../../../core/services/symbol-detail.service';
import { MetricTooltip } from '../../../../../shared/components/metric-tooltip/metric-tooltip';
import { METRIC_THRESHOLDS, MetricThreshold } from './metric-thresholds';

interface MetricItem {
  key: string;
  value: number | null | undefined;
  format: 'number' | 'percent' | 'currency' | 'ratio';
}

interface MetricSection {
  title: string;
  metrics: MetricItem[];
}

@Component({
  selector: 'app-fundamentals-tab',
  standalone: true,
  imports: [CommonModule, MatCardModule, MetricTooltip],
  templateUrl: './fundamentals-tab.html',
  styleUrl: './fundamentals-tab.scss',
})
export class FundamentalsTab implements OnChanges {
  @Input() metrics: InstrumentMetrics | null | undefined;
  sections: MetricSection[] = [];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['metrics']) {
      this.updateSections();
    }
  }

  private updateSections(): void {
    if (!this.metrics) {
      this.sections = [];
      return;
    }

    this.sections = [
      {
        title: 'Valuation',
        metrics: [
          { key: 'pe_ttm', value: this.metrics.pe_ttm, format: 'ratio' },
          { key: 'pe_forward', value: this.metrics.pe_forward, format: 'ratio' },
          { key: 'price_to_book', value: this.metrics.price_to_book, format: 'ratio' },
          { key: 'price_to_sales', value: this.metrics.price_to_sales, format: 'ratio' },
          { key: 'peg_ratio', value: this.metrics.peg_ratio, format: 'ratio' },
          { key: 'ev_to_ebitda', value: this.metrics.ev_to_ebitda, format: 'ratio' },
        ],
      },
      {
        title: 'Profitability',
        metrics: [
          { key: 'gross_margin', value: this.metrics.gross_margin, format: 'percent' },
          { key: 'operating_margin', value: this.metrics.operating_margin, format: 'percent' },
          { key: 'net_margin', value: this.metrics.net_margin, format: 'percent' },
          { key: 'roe', value: this.metrics.roe, format: 'percent' },
          { key: 'roa', value: this.metrics.roa, format: 'percent' },
          { key: 'roic', value: this.metrics.roic, format: 'percent' },
        ],
      },
      {
        title: 'Growth',
        metrics: [
          { key: 'revenue_growth_yoy', value: this.metrics.revenue_growth_yoy, format: 'percent' },
          { key: 'earnings_growth_yoy', value: this.metrics.earnings_growth_yoy, format: 'percent' },
          { key: 'eps_growth_yoy', value: this.metrics.eps_growth_yoy, format: 'percent' },
        ],
      },
      {
        title: 'Leverage & Liquidity',
        metrics: [
          { key: 'debt_to_equity', value: this.metrics.debt_to_equity, format: 'ratio' },
          { key: 'net_debt_to_ebitda', value: this.metrics.net_debt_to_ebitda, format: 'ratio' },
          { key: 'current_ratio', value: this.metrics.current_ratio, format: 'ratio' },
          { key: 'quick_ratio', value: this.metrics.quick_ratio, format: 'ratio' },
        ],
      },
      {
        title: 'Dividends & Yield',
        metrics: [
          { key: 'dividend_yield', value: this.metrics.dividend_yield, format: 'percent' },
          { key: 'fcf_yield', value: this.metrics.fcf_yield, format: 'percent' },
        ],
      },
      {
        title: 'Market',
        metrics: [
          { key: 'market_cap', value: this.metrics.market_cap, format: 'currency' },
          { key: 'enterprise_value', value: this.metrics.enterprise_value, format: 'currency' },
          { key: 'beta', value: this.metrics.beta, format: 'number' },
          { key: 'shares_outstanding', value: this.metrics.shares_outstanding, format: 'number' },
        ],
      },
    ];
  }

  formatValue(item: MetricItem): string {
    if (item.value == null) return '-';

    switch (item.format) {
      case 'percent':
        return (item.value * 100).toFixed(2) + '%';
      case 'currency':
        return this.formatLargeNumber(item.value);
      case 'ratio':
        return item.value.toFixed(2);
      case 'number':
      default:
        if (item.value >= 1e6) {
          return this.formatLargeNumber(item.value);
        }
        return item.value.toFixed(2);
    }
  }

  private formatLargeNumber(value: number): string {
    if (value >= 1e12) return '$' + (value / 1e12).toFixed(2) + 'T';
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return (value / 1e3).toFixed(2) + 'K';
    return value.toFixed(2);
  }

  getColorClass(item: MetricItem): string {
    if (item.value == null) return '';

    const threshold = METRIC_THRESHOLDS[item.key];
    if (!threshold) return '';

    const val = item.value;
    const { type, good, bad } = threshold;

    if (type === 'higherIsBetter') {
      if (val >= good) return 'val-good';
      if (val <= bad) return 'val-bad';
    } else if (type === 'lowerIsBetter') {
      if (val <= good) return 'val-good';
      if (val >= bad) return 'val-bad';
    } else if (type === 'range') {
      // For Beta: Good is near 1 (0.8-1.2?), Bad is high (>1.5) or very low?
      // Simplified: Just use simple thresholds from config
      if (val <= good) return 'val-good'; // e.g. < 1.0 safe
      if (val >= bad) return 'val-bad';   // > 1.5 volatile
    }

    return '';
  }
}
