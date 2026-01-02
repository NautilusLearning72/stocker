import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTabsModule } from '@angular/material/tabs';
import { MatCardModule } from '@angular/material/card';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import {
  PerformanceService,
  EquityCurvePoint,
  ReturnsMetrics,
  RiskMetrics,
  ExecutionMetrics,
  SignalPerformance,
  ExposureAnalysis,
  Granularity,
  PerformanceFilters
} from '../../../core/services/performance.service';

import { EquityCurveChart } from '../components/equity-curve-chart/equity-curve-chart';
import { ReturnsSummary } from '../components/returns-summary/returns-summary';
import { MonthlyHeatmap } from '../components/monthly-heatmap/monthly-heatmap';
import { RiskMetricsComponent } from '../components/risk-metrics/risk-metrics';
import { ExecutionQualityComponent } from '../components/execution-quality/execution-quality';
import { SignalStatsComponent } from '../components/signal-stats/signal-stats';
import { ExposureChartComponent } from '../components/exposure-chart/exposure-chart';

@Component({
  selector: 'app-performance-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTabsModule,
    MatCardModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatInputModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    EquityCurveChart,
    ReturnsSummary,
    MonthlyHeatmap,
    RiskMetricsComponent,
    ExecutionQualityComponent,
    SignalStatsComponent,
    ExposureChartComponent,
  ],
  templateUrl: './performance-dashboard.html',
  styleUrl: './performance-dashboard.scss',
})
export class PerformanceDashboard implements OnInit {
  // Filters
  granularity: Granularity = 'daily';
  startDate: Date | null = null;
  endDate: Date | null = null;

  // Data
  equityCurve: EquityCurvePoint[] = [];
  returnsMetrics: ReturnsMetrics | null = null;
  riskMetrics: RiskMetrics | null = null;
  executionMetrics: ExecutionMetrics | null = null;
  signalPerformance: SignalPerformance | null = null;
  exposureAnalysis: ExposureAnalysis | null = null;

  // Loading states (initialize to true to avoid ExpressionChangedAfterItHasBeenCheckedError)
  loading = {
    equity: true,
    returns: true,
    risk: true,
    execution: true,
    signals: true,
    exposure: true
  };

  constructor(
    private performanceService: PerformanceService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadAllData();
  }

  onGranularityChange(): void {
    this.loadEquityCurve();
    this.loadExposure();
  }

  onDateChange(): void {
    this.loadAllData();
  }

  refresh(): void {
    this.loadAllData();
  }

  clearDates(): void {
    this.startDate = null;
    this.endDate = null;
    this.loadAllData();
  }

  private getFilters(): PerformanceFilters {
    const filters: PerformanceFilters = {
      granularity: this.granularity
    };

    if (this.startDate) {
      filters.startDate = this.formatDate(this.startDate);
    }
    if (this.endDate) {
      filters.endDate = this.formatDate(this.endDate);
    }

    return filters;
  }

  private formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }

  loadAllData(): void {
    this.loadEquityCurve();
    this.loadReturns();
    this.loadRisk();
    this.loadExecution();
    this.loadSignals();
    this.loadExposure();
  }

  private loadEquityCurve(): void {
    this.loading.equity = true;
    this.performanceService.getEquityCurve(this.getFilters()).subscribe({
      next: (data) => {
        this.equityCurve = data;
        Promise.resolve().then(() => {
          this.loading.equity = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.equity = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  private loadReturns(): void {
    this.loading.returns = true;
    this.performanceService.getReturns(this.getFilters()).subscribe({
      next: (data) => {
        this.returnsMetrics = data;
        Promise.resolve().then(() => {
          this.loading.returns = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.returns = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  private loadRisk(): void {
    this.loading.risk = true;
    this.performanceService.getRiskMetrics(this.getFilters()).subscribe({
      next: (data) => {
        this.riskMetrics = data;
        Promise.resolve().then(() => {
          this.loading.risk = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.risk = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  private loadExecution(): void {
    this.loading.execution = true;
    this.performanceService.getExecutionMetrics(this.getFilters()).subscribe({
      next: (data) => {
        this.executionMetrics = data;
        Promise.resolve().then(() => {
          this.loading.execution = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.execution = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  private loadSignals(): void {
    this.loading.signals = true;
    this.performanceService.getSignalPerformance(this.getFilters()).subscribe({
      next: (data) => {
        this.signalPerformance = data;
        Promise.resolve().then(() => {
          this.loading.signals = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.signals = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  private loadExposure(): void {
    this.loading.exposure = true;
    this.performanceService.getExposureAnalysis(this.getFilters()).subscribe({
      next: (data) => {
        this.exposureAnalysis = data;
        Promise.resolve().then(() => {
          this.loading.exposure = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.loading.exposure = false;
          this.cdr.detectChanges();
        });
      }
    });
  }

  get isLoading(): boolean {
    return Object.values(this.loading).some(v => v);
  }
}
