import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';

// ---------- Interfaces ----------

export interface SignalSnapshot {
  strategy_version: string;
  symbol: string;
  date: string;
  direction: number;
  target_weight: number;
  lookback_return?: number | null;
  ewma_vol?: number | null;
  created_at?: string | null;
}

export interface TargetSnapshot {
  symbol: string;
  date: string;
  target_exposure: number;
  scaling_factor: number;
  is_capped: boolean;
  reason?: string | null;
  created_at?: string | null;
}

export interface FillSnapshot {
  fill_id: string;
  date: string;
  qty: number;
  price: number;
  commission: number;
  exchange?: string | null;
}

export interface OrderSnapshot {
  order_id: string;
  portfolio_id: string;
  date: string;
  symbol: string;
  side?: string | null;
  qty: number;
  type?: string | null;
  status?: string | null;
  broker_order_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DecisionEvent {
  timestamp: string;
  stage: string; // signal, target, sizing, execution
  event_type: string;
  description: string;
  metadata: Record<string, any>;
}

export interface DiscrepancyInfo {
  type: string; // qty_mismatch, partial_fill, rejected, slippage
  expected?: number | null;
  actual?: number | null;
  difference?: number | null;
  severity: string; // info, warning, error
  description: string;
}

export interface OrderAuditRecord {
  order: OrderSnapshot;
  signal?: SignalSnapshot | null;
  target?: TargetSnapshot | null;
  fills: FillSnapshot[];
  timeline: DecisionEvent[];
  discrepancies: DiscrepancyInfo[];
  expected_qty?: number | null;
  filled_qty: number;
  fill_rate: number;
  avg_fill_price?: number | null;
  slippage_bps?: number | null;
  total_commission: number;
}

export interface AuditSummary {
  total_orders: number;
  filled_count: number;
  failed_count: number;
  pending_count: number;
  discrepancy_count: number;
  avg_fill_rate?: number | null;
  total_commission: number;
  date_from?: string | null;
  date_to?: string | null;
}

export interface AuditListResponse {
  items: OrderAuditRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilters {
  portfolio_id?: string;
  date_from?: string | null;
  date_to?: string | null;
  symbol?: string | null;
  status?: string | null;
  side?: string | null;
  strategy_version?: string | null;
  min_qty?: number | null;
  max_qty?: number | null;
  has_discrepancy?: boolean | null;
  limit?: number;
  offset?: number;
}

// ---------- Service ----------

@Injectable({ providedIn: 'root' })
export class AuditService {
  private baseUrl = 'http://localhost:8000/api/v1/audit';

  constructor(private http: HttpClient) {}

  /**
   * Convert numeric strings to numbers in API response
   */
  private convertNumbers(record: any): OrderAuditRecord {
    return {
      ...record,
      filled_qty: Number(record.filled_qty),
      fill_rate: Number(record.fill_rate),
      avg_fill_price: record.avg_fill_price != null ? Number(record.avg_fill_price) : null,
      slippage_bps: record.slippage_bps != null ? Number(record.slippage_bps) : null,
      total_commission: Number(record.total_commission),
      order: {
        ...record.order,
        qty: Number(record.order.qty),
      },
      signal: record.signal ? {
        ...record.signal,
        target_weight: Number(record.signal.target_weight),
        lookback_return: record.signal.lookback_return != null ? Number(record.signal.lookback_return) : null,
        ewma_vol: record.signal.ewma_vol != null ? Number(record.signal.ewma_vol) : null,
      } : null,
      target: record.target ? {
        ...record.target,
        target_exposure: Number(record.target.target_exposure),
        scaling_factor: Number(record.target.scaling_factor),
      } : null,
      fills: record.fills.map((f: any) => ({
        ...f,
        qty: Number(f.qty),
        price: Number(f.price),
        commission: Number(f.commission),
      })),
      discrepancies: record.discrepancies.map((d: any) => ({
        ...d,
        expected: d.expected != null ? Number(d.expected) : null,
        actual: d.actual != null ? Number(d.actual) : null,
        difference: d.difference != null ? Number(d.difference) : null,
      })),
    };
  }

  /**
   * Get paginated list of order audit records with filters
   */
  getAuditOrders(filters: AuditFilters = {}): Observable<AuditListResponse> {
    let params = new HttpParams();

    if (filters.portfolio_id) params = params.set('portfolio_id', filters.portfolio_id);
    if (filters.date_from) params = params.set('date_from', filters.date_from);
    if (filters.date_to) params = params.set('date_to', filters.date_to);
    if (filters.symbol) params = params.set('symbol', filters.symbol);
    if (filters.status) params = params.set('status', filters.status);
    if (filters.side) params = params.set('side', filters.side);
    if (filters.strategy_version) params = params.set('strategy_version', filters.strategy_version);
    if (filters.min_qty != null) params = params.set('min_qty', filters.min_qty.toString());
    if (filters.max_qty != null) params = params.set('max_qty', filters.max_qty.toString());
    if (filters.has_discrepancy != null) params = params.set('has_discrepancy', filters.has_discrepancy.toString());
    if (filters.limit != null) params = params.set('limit', filters.limit.toString());
    if (filters.offset != null) params = params.set('offset', filters.offset.toString());

    return this.http.get<any>(`${this.baseUrl}/orders`, { params }).pipe(
      map(response => ({
        ...response,
        items: response.items.map((item: any) => this.convertNumbers(item)),
      }))
    );
  }

  /**
   * Get full audit record for a specific order
   */
  getAuditOrder(orderId: string): Observable<OrderAuditRecord> {
    return this.http.get<any>(`${this.baseUrl}/orders/${orderId}`).pipe(
      map(record => this.convertNumbers(record))
    );
  }

  /**
   * Get summary statistics for order audit
   */
  getSummary(
    portfolioId: string = 'main',
    dateFrom?: string,
    dateTo?: string
  ): Observable<AuditSummary> {
    let params = new HttpParams().set('portfolio_id', portfolioId);
    if (dateFrom) params = params.set('date_from', dateFrom);
    if (dateTo) params = params.set('date_to', dateTo);

    return this.http.get<any>(`${this.baseUrl}/summary`, { params }).pipe(
      map(summary => ({
        ...summary,
        total_commission: Number(summary.total_commission),
      }))
    );
  }

  /**
   * Get orders with detected discrepancies
   */
  getDiscrepancies(
    portfolioId: string = 'main',
    dateFrom?: string,
    dateTo?: string,
    severity?: string,
    limit: number = 50
  ): Observable<OrderAuditRecord[]> {
    let params = new HttpParams()
      .set('portfolio_id', portfolioId)
      .set('limit', limit.toString());

    if (dateFrom) params = params.set('date_from', dateFrom);
    if (dateTo) params = params.set('date_to', dateTo);
    if (severity) params = params.set('severity', severity);

    return this.http.get<any[]>(`${this.baseUrl}/discrepancies`, { params }).pipe(
      map(records => records.map(record => this.convertNumbers(record)))
    );
  }
}
