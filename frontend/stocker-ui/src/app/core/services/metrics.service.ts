import { Injectable, NgZone } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, Subject, BehaviorSubject } from 'rxjs';

// Interfaces

export interface MetricsSummary {
  period_hours: number;
  total_events: number;
  by_category: Record<string, number>;
  by_event: Record<string, number>;
  confirmation_rate: number | null;
  trailing_stops_triggered: number;
  sector_caps_applied: number;
  correlation_throttles: number;
  orders_created: number;
  orders_skipped: number;
}

export interface MetricEvent {
  timestamp: string;
  category: string;
  event_type: string;
  symbol: string | null;
  portfolio_id: string;
  value: number | null;
  metadata: Record<string, any>;
}

export interface MetricsCategories {
  categories: Record<string, string[]>;
}

export interface MetricsHealth {
  buffer_size: number;
  redis_connected: boolean;
  enabled: boolean;
}

export interface EventFilters {
  category?: string;
  event_type?: string;
  symbol?: string;
  hours?: number;
  limit?: number;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

@Injectable({ providedIn: 'root' })
export class MetricsService {
  private baseUrl = 'http://localhost:8000/api/v1/metrics';

  // SSE state
  private eventSource?: EventSource;
  private streamSubject = new Subject<MetricEvent>();
  private connectionStatus = new BehaviorSubject<ConnectionStatus>('disconnected');

  public stream$ = this.streamSubject.asObservable();
  public connectionStatus$ = this.connectionStatus.asObservable();

  constructor(
    private http: HttpClient,
    private zone: NgZone
  ) {}

  // REST API Methods

  getSummary(hours: number = 24): Observable<MetricsSummary> {
    const params = new HttpParams().set('hours', hours.toString());
    return this.http.get<MetricsSummary>(`${this.baseUrl}/summary`, { params });
  }

  getEvents(filters: EventFilters = {}): Observable<MetricEvent[]> {
    let params = new HttpParams();
    if (filters.category) params = params.set('category', filters.category);
    if (filters.event_type) params = params.set('event_type', filters.event_type);
    if (filters.symbol) params = params.set('symbol', filters.symbol);
    if (filters.hours) params = params.set('hours', filters.hours.toString());
    if (filters.limit) params = params.set('limit', filters.limit.toString());
    return this.http.get<MetricEvent[]>(`${this.baseUrl}/events`, { params });
  }

  getCategories(): Observable<MetricsCategories> {
    return this.http.get<MetricsCategories>(`${this.baseUrl}/categories`);
  }

  getHealth(): Observable<MetricsHealth> {
    return this.http.get<MetricsHealth>(`${this.baseUrl}/health`);
  }

  // SSE Stream Methods

  connectStream(category?: string): void {
    if (this.eventSource && this.eventSource.readyState !== EventSource.CLOSED) {
      return;
    }

    this.connectionStatus.next('connecting');

    let url = `${this.baseUrl}/stream`;
    if (category) {
      url += `?category=${encodeURIComponent(category)}`;
    }

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        this.zone.run(() => {
          this.connectionStatus.next('connected');
        });
      };

      this.eventSource.onerror = () => {
        this.zone.run(() => {
          this.connectionStatus.next('disconnected');
          this.eventSource?.close();
        });
      };

      // Listen for metric events
      this.eventSource.addEventListener('metric', (event: MessageEvent) => {
        this.zone.run(() => {
          try {
            const data = JSON.parse(event.data) as MetricEvent;
            this.streamSubject.next(data);
          } catch (e) {
            console.error('Failed to parse metric event:', e);
          }
        });
      });

    } catch (e) {
      this.connectionStatus.next('disconnected');
    }
  }

  disconnectStream(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = undefined;
      this.connectionStatus.next('disconnected');
    }
  }
}
