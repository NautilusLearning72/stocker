import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatCardModule } from '@angular/material/card';
import { Subscription } from 'rxjs';

import { MetricsService, MetricsSummary as MetricsSummaryData, MetricEvent, ConnectionStatus } from '../../../core/services/metrics.service';
import { MetricsSummary } from '../metrics-summary/metrics-summary';
import { EventFeed } from '../event-feed/event-feed';

@Component({
  selector: 'app-metrics-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatSlideToggleModule,
    MatSelectModule,
    MatFormFieldModule,
    MatCardModule,
    MetricsSummary,
    EventFeed,
  ],
  templateUrl: './metrics-dashboard.html',
  styleUrl: './metrics-dashboard.scss',
})
export class MetricsDashboard implements OnInit, OnDestroy {
  // Summary data
  summary: MetricsSummaryData | null = null;

  // Events data
  events: MetricEvent[] = [];

  // Real-time state
  isLive = false;
  connectionStatus: ConnectionStatus = 'disconnected';

  // Time range selection
  selectedHours = 24;
  hourOptions = [
    { value: 1, label: 'Last hour' },
    { value: 6, label: 'Last 6 hours' },
    { value: 12, label: 'Last 12 hours' },
    { value: 24, label: 'Last 24 hours' },
    { value: 48, label: 'Last 2 days' },
    { value: 72, label: 'Last 3 days' },
  ];

  // Loading states
  loadingSummary = false;
  loadingEvents = false;

  // Current filters
  private currentFilters: any = {};
  private subscriptions = new Subscription();

  constructor(
    private metricsService: MetricsService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    // Subscribe to connection status
    this.subscriptions.add(
      this.metricsService.connectionStatus$.subscribe(status => {
        this.connectionStatus = status;
        this.cdr.detectChanges();
      })
    );

    // Subscribe to real-time events
    this.subscriptions.add(
      this.metricsService.stream$.subscribe(event => {
        if (this.isLive) {
          // Prepend new event and cap at 200
          this.events = [event, ...this.events].slice(0, 200);
          this.cdr.detectChanges();
        }
      })
    );

    // Load initial data
    this.loadData();
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    this.metricsService.disconnectStream();
  }

  loadData(): void {
    this.loadSummary();
    this.loadEvents();
  }

  loadSummary(): void {
    this.loadingSummary = true;
    this.metricsService.getSummary(this.selectedHours).subscribe({
      next: (data) => {
        this.summary = data;
        this.loadingSummary = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load metrics summary:', err);
        this.loadingSummary = false;
        this.cdr.detectChanges();
      }
    });
  }

  loadEvents(filters?: any): void {
    this.loadingEvents = true;
    const queryFilters = {
      hours: this.selectedHours,
      limit: 100,
      ...this.currentFilters,
      ...filters
    };

    this.metricsService.getEvents(queryFilters).subscribe({
      next: (data) => {
        this.events = data;
        this.loadingEvents = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load events:', err);
        this.loadingEvents = false;
        this.cdr.detectChanges();
      }
    });
  }

  onTimeRangeChange(): void {
    this.loadData();
  }

  onLiveToggle(): void {
    if (this.isLive) {
      this.metricsService.connectStream();
    } else {
      this.metricsService.disconnectStream();
    }
  }

  onFiltersChange(filters: any): void {
    this.currentFilters = filters;
    this.loadEvents(filters);
  }

  refresh(): void {
    this.loadData();
  }
}
