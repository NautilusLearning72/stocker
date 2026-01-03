import {
  Component,
  Input,
  ElementRef,
  ViewChild,
  AfterViewInit,
  OnChanges,
  OnDestroy,
  SimpleChanges,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineSeries,
  AreaSeries,
  LineData,
  AreaData,
  Time,
} from 'lightweight-charts';
import { EquityCurvePoint } from '../../../../core/services/performance.service';

@Component({
  selector: 'app-equity-curve-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chart-wrapper">
      <div #chartContainer class="chart-container"></div>
      <div *ngIf="!data || data.length === 0" class="no-data">
        No NAV history available
      </div>
    </div>
  `,
  styles: [`
    .chart-wrapper {
      position: relative;
      width: 100%;
    }
    .chart-container {
      width: 100%;
    }
    .no-data {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      color: var(--color-muted);
      font-size: 14px;
    }
  `]
})
export class EquityCurveChart implements AfterViewInit, OnChanges, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef<HTMLDivElement>;

  @Input() data: EquityCurvePoint[] = [];
  @Input() height = 350;
  @Input() showDrawdown = true;

  private chart?: IChartApi;
  private navSeries?: ISeriesApi<'Line'>;
  private drawdownSeries?: ISeriesApi<'Area'>;
  private resizeObserver?: ResizeObserver;

  ngAfterViewInit(): void {
    this.initChart();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && this.chart) {
      this.updateData();
    }
    if (changes['height'] && this.chart) {
      this.chart.applyOptions({ height: this.height });
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.chart?.remove();
  }

  private initChart(): void {
    if (!this.chartContainer?.nativeElement) return;

    const container = this.chartContainer.nativeElement;
    const rootStyles = getComputedStyle(document.documentElement);
    const accent = rootStyles.getPropertyValue('--color-accent').trim() || '#0969da';
    const border = rootStyles.getPropertyValue('--color-border').trim() || '#d0d7de';
    const muted = rootStyles.getPropertyValue('--color-muted').trim() || '#57606a';
    const danger = rootStyles.getPropertyValue('--color-danger').trim() || '#d1242f';
    const toRgba = (hex: string, alpha: number): string => {
      const value = hex.replace('#', '').trim();
      if (value.length !== 6) {
        return `rgba(209, 36, 47, ${alpha})`;
      }
      const r = parseInt(value.slice(0, 2), 16);
      const g = parseInt(value.slice(2, 4), 16);
      const b = parseInt(value.slice(4, 6), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    };

    this.chart = createChart(container, {
      height: this.height,
      layout: {
        background: { color: 'transparent' },
        textColor: muted,
      },
      grid: {
        vertLines: { color: border },
        horzLines: { color: border },
      },
      rightPriceScale: {
        borderColor: border,
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderColor: border,
        timeVisible: true,
      },
      crosshair: {
        mode: 1,
      },
    });

    // NAV line series
    this.navSeries = this.chart.addSeries(LineSeries, {
      color: accent,
      lineWidth: 2,
      priceFormat: {
        type: 'custom',
        formatter: (price: number) => '$' + price.toLocaleString(undefined, {
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }),
      },
    });

    // Drawdown area series (on separate price scale)
    if (this.showDrawdown) {
      this.drawdownSeries = this.chart.addSeries(AreaSeries, {
        topColor: toRgba(danger, 0.25),
        bottomColor: toRgba(danger, 0),
        lineColor: toRgba(danger, 0.55),
        lineWidth: 1,
        priceScaleId: 'drawdown',
        priceFormat: {
          type: 'custom',
          formatter: (price: number) => price.toFixed(1) + '%',
        },
      });

      this.chart.priceScale('drawdown').applyOptions({
        scaleMargins: { top: 0.7, bottom: 0 },
        borderVisible: false,
      });
    }

    this.updateData();

    // Handle resize
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart) {
        this.chart.applyOptions({ width: container.clientWidth });
      }
    });
    this.resizeObserver.observe(container);
  }

  private updateData(): void {
    if (!this.data || this.data.length === 0) return;

    // NAV data
    const navData: LineData<Time>[] = this.data.map(point => ({
      time: point.date as Time,
      value: point.nav,
    }));
    this.navSeries?.setData(navData);

    // Drawdown data (inverted so negative shows above)
    if (this.showDrawdown && this.drawdownSeries) {
      const drawdownData: AreaData<Time>[] = this.data.map(point => ({
        time: point.date as Time,
        value: -point.drawdown, // Invert for visual
      }));
      this.drawdownSeries.setData(drawdownData);
    }

    this.chart?.timeScale().fitContent();
  }
}
