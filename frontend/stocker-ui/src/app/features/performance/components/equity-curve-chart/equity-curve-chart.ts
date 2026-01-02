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
      color: #666;
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

    this.chart = createChart(container, {
      height: this.height,
      layout: {
        background: { color: 'transparent' },
        textColor: '#666',
      },
      grid: {
        vertLines: { color: 'rgba(197, 203, 206, 0.3)' },
        horzLines: { color: 'rgba(197, 203, 206, 0.3)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderColor: 'rgba(197, 203, 206, 0.8)',
        timeVisible: true,
      },
      crosshair: {
        mode: 1,
      },
    });

    // NAV line series
    this.navSeries = this.chart.addSeries(LineSeries, {
      color: '#2196F3',
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
        topColor: 'rgba(244, 67, 54, 0.3)',
        bottomColor: 'rgba(244, 67, 54, 0.0)',
        lineColor: 'rgba(244, 67, 54, 0.5)',
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
