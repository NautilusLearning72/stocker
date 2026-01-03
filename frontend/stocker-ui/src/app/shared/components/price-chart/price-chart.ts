import {
  Component,
  Input,
  ElementRef,
  ViewChild,
  AfterViewInit,
  OnDestroy,
  OnChanges,
  SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  Time,
  CandlestickSeries,
  LineSeries,
} from 'lightweight-charts';
import { DailyPrice } from '../../../core/services/symbol-detail.service';

export type ChartType = 'candlestick' | 'line';

@Component({
  selector: 'app-price-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chart-wrapper">
      <div #chartContainer class="chart-container"></div>
      <div *ngIf="!prices || prices.length === 0" class="no-data">
        No price data available
      </div>
    </div>
  `,
  styles: [
    `
      .chart-wrapper {
        position: relative;
        width: 100%;
        height: 100%;
        min-height: 300px;
      }
      .chart-container {
        width: 100%;
        height: 100%;
      }
      .no-data {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: var(--color-muted);
        font-size: 14px;
      }
    `,
  ],
})
export class PriceChart implements AfterViewInit, OnDestroy, OnChanges {
  @ViewChild('chartContainer') chartContainer!: ElementRef<HTMLDivElement>;
  @Input() prices: DailyPrice[] = [];
  @Input() chartType: ChartType = 'candlestick';
  @Input() height: number = 300;

  private chart?: IChartApi;
  private series?: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'>;
  private resizeObserver?: ResizeObserver;

  ngAfterViewInit(): void {
    this.initChart();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['prices'] && this.chart) {
      this.updateData();
    }
    if (changes['chartType'] && this.chart) {
      this.rebuildChart();
    }
  }

  private initChart(): void {
    if (!this.chartContainer?.nativeElement) return;

    const container = this.chartContainer.nativeElement;
    const rootStyles = getComputedStyle(document.documentElement);
    const canvas = rootStyles.getPropertyValue('--color-canvas').trim() || '#ffffff';
    const accent = rootStyles.getPropertyValue('--color-accent').trim() || '#0969da';
    const border = rootStyles.getPropertyValue('--color-border').trim() || '#d0d7de';
    const muted = rootStyles.getPropertyValue('--color-muted').trim() || '#57606a';
    const success = rootStyles.getPropertyValue('--color-success').trim() || '#1a7f37';
    const danger = rootStyles.getPropertyValue('--color-danger').trim() || '#d1242f';

    this.chart = createChart(container, {
      width: container.clientWidth,
      height: this.height,
      layout: {
        background: { color: canvas },
        textColor: muted,
      },
      grid: {
        vertLines: { color: border },
        horzLines: { color: border },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: border,
      },
      timeScale: {
        borderColor: border,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    this.createSeries(accent, success, danger);
    this.updateData();

    // Handle resize
    this.resizeObserver = new ResizeObserver((entries) => {
      if (entries.length > 0 && this.chart) {
        const { width, height } = entries[0].contentRect;
        this.chart.applyOptions({ width, height: Math.max(height, this.height) });
      }
    });
    this.resizeObserver.observe(container);
  }

  private createSeries(accent: string, success: string, danger: string): void {
    if (!this.chart) return;

    if (this.chartType === 'candlestick') {
      this.series = this.chart.addSeries(CandlestickSeries, {
        upColor: success,
        downColor: danger,
        borderDownColor: danger,
        borderUpColor: success,
        wickDownColor: danger,
        wickUpColor: success,
      });
    } else {
      this.series = this.chart.addSeries(LineSeries, {
        color: accent,
        lineWidth: 2,
      });
    }
  }

  private rebuildChart(): void {
    if (this.series && this.chart) {
      this.chart.removeSeries(this.series);
    }
    const rootStyles = getComputedStyle(document.documentElement);
    const accent = rootStyles.getPropertyValue('--color-accent').trim() || '#0969da';
    const success = rootStyles.getPropertyValue('--color-success').trim() || '#1a7f37';
    const danger = rootStyles.getPropertyValue('--color-danger').trim() || '#d1242f';
    this.createSeries(accent, success, danger);
    this.updateData();
  }

  private updateData(): void {
    if (!this.series || !this.prices || this.prices.length === 0) return;

    if (this.chartType === 'candlestick') {
      const data: CandlestickData<Time>[] = this.prices.map((p) => ({
        time: p.date as Time,
        open: p.open,
        high: p.high,
        low: p.low,
        close: p.close,
      }));
      (this.series as ISeriesApi<'Candlestick'>).setData(data);
    } else {
      const data: LineData<Time>[] = this.prices.map((p) => ({
        time: p.date as Time,
        value: p.close,
      }));
      (this.series as ISeriesApi<'Line'>).setData(data);
    }

    this.chart?.timeScale().fitContent();
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }
}
