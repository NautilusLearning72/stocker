import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

// ============================================================================
// Types
// ============================================================================

export interface EquityCurvePoint {
  date: string;
  nav: number;
  drawdown: number;
  high_water_mark: number;
  daily_return?: number;
}

export interface MonthlyReturn {
  year: number;
  month: number;
  return_pct: number;
}

export interface ReturnsMetrics {
  total_return: number;
  cagr: number;
  ytd_return?: number;
  mtd_return?: number;
  return_1d?: number;
  return_1w?: number;
  return_1m?: number;
  return_3m?: number;
  return_6m?: number;
  return_1y?: number;
  pct_winning_days: number;
  pct_winning_months: number;
  best_day: number;
  worst_day: number;
  best_month: number;
  worst_month: number;
  monthly_returns: MonthlyReturn[];
}

export interface DrawdownPoint {
  date: string;
  drawdown: number;
}

export interface RiskMetrics {
  annualized_volatility: number;
  daily_volatility: number;
  current_drawdown: number;
  max_drawdown: number;
  avg_drawdown: number;
  max_drawdown_duration_days: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  var_95: number;
  cvar_95: number;
  worst_1m: number;
  worst_3m: number;
  worst_12m: number;
  drawdown_series: DrawdownPoint[];
}

export interface SymbolExecutionStats {
  symbol: string;
  orders: number;
  filled: number;
  fill_rate: number;
  avg_slippage_bps: number;
  total_commission: number;
}

export interface ExecutionMetrics {
  total_orders: number;
  fill_rate: number;
  partial_fills: number;
  rejected_orders: number;
  total_commission: number;
  total_slippage: number;
  avg_slippage_bps: number;
  commission_as_pct_nav: number;
  avg_fill_time_ms?: number;
  by_symbol: SymbolExecutionStats[];
}

export interface SymbolSignalStats {
  symbol: string;
  signals: number;
  winners: number;
  hit_rate: number;
  avg_return: number;
  total_pnl: number;
}

export interface SignalPerformance {
  total_signals: number;
  winning_signals: number;
  losing_signals: number;
  hit_rate: number;
  long_signals: number;
  long_hit_rate: number;
  short_signals: number;
  short_hit_rate: number;
  avg_winner_return: number;
  avg_loser_return: number;
  profit_factor: number;
  avg_holding_days: number;
  avg_winner_holding_days: number;
  avg_loser_holding_days: number;
  exits_by_reason: { [key: string]: number };
  by_symbol: SymbolSignalStats[];
}

export interface ExposurePoint {
  date: string;
  gross_exposure: number;
  net_exposure: number;
  long_exposure: number;
  short_exposure: number;
}

export interface SectorExposure {
  sector: string;
  exposure: number;
  position_count: number;
}

export interface ExposureAnalysis {
  current_gross_exposure: number;
  current_net_exposure: number;
  current_long_exposure: number;
  current_short_exposure: number;
  avg_gross_exposure: number;
  avg_net_exposure: number;
  max_gross_exposure: number;
  avg_daily_turnover: number;
  avg_monthly_turnover: number;
  annual_turnover: number;
  exposure_history: ExposurePoint[];
  by_sector: SectorExposure[];
}

export type Granularity = 'daily' | 'monthly';

export interface PerformanceFilters {
  portfolioId?: string;
  startDate?: string;
  endDate?: string;
  granularity?: Granularity;
}

// ============================================================================
// Service
// ============================================================================

@Injectable({
  providedIn: 'root',
})
export class PerformanceService {
  private baseUrl = 'http://localhost:8000/api/v1/performance';

  constructor(private http: HttpClient) {}

  private buildParams(filters: PerformanceFilters): HttpParams {
    let params = new HttpParams();

    if (filters.portfolioId) {
      params = params.set('portfolio_id', filters.portfolioId);
    }
    if (filters.startDate) {
      params = params.set('start_date', filters.startDate);
    }
    if (filters.endDate) {
      params = params.set('end_date', filters.endDate);
    }
    if (filters.granularity) {
      params = params.set('granularity', filters.granularity);
    }

    return params;
  }

  /**
   * Get equity curve data for charting.
   */
  getEquityCurve(filters: PerformanceFilters = {}): Observable<EquityCurvePoint[]> {
    const params = this.buildParams(filters);
    return this.http.get<EquityCurvePoint[]>(`${this.baseUrl}/equity-curve`, { params }).pipe(
      map(points => points.map(p => ({
        ...p,
        nav: Number(p.nav),
        drawdown: Number(p.drawdown),
        high_water_mark: Number(p.high_water_mark),
        daily_return: p.daily_return != null ? Number(p.daily_return) : undefined
      })))
    );
  }

  /**
   * Get comprehensive return metrics.
   */
  getReturns(filters: PerformanceFilters = {}): Observable<ReturnsMetrics> {
    const params = this.buildParams(filters);
    return this.http.get<ReturnsMetrics>(`${this.baseUrl}/returns`, { params }).pipe(
      map(m => ({
        ...m,
        total_return: Number(m.total_return),
        cagr: Number(m.cagr),
        ytd_return: m.ytd_return != null ? Number(m.ytd_return) : undefined,
        mtd_return: m.mtd_return != null ? Number(m.mtd_return) : undefined,
        return_1d: m.return_1d != null ? Number(m.return_1d) : undefined,
        return_1w: m.return_1w != null ? Number(m.return_1w) : undefined,
        return_1m: m.return_1m != null ? Number(m.return_1m) : undefined,
        return_3m: m.return_3m != null ? Number(m.return_3m) : undefined,
        return_6m: m.return_6m != null ? Number(m.return_6m) : undefined,
        return_1y: m.return_1y != null ? Number(m.return_1y) : undefined,
        pct_winning_days: Number(m.pct_winning_days),
        pct_winning_months: Number(m.pct_winning_months),
        best_day: Number(m.best_day),
        worst_day: Number(m.worst_day),
        best_month: Number(m.best_month),
        worst_month: Number(m.worst_month),
        monthly_returns: m.monthly_returns.map(mr => ({
          ...mr,
          return_pct: Number(mr.return_pct)
        }))
      }))
    );
  }

  /**
   * Get risk metrics.
   */
  getRiskMetrics(filters: PerformanceFilters = {}): Observable<RiskMetrics> {
    const params = this.buildParams(filters);
    return this.http.get<RiskMetrics>(`${this.baseUrl}/risk`, { params }).pipe(
      map(m => ({
        ...m,
        annualized_volatility: Number(m.annualized_volatility),
        daily_volatility: Number(m.daily_volatility),
        current_drawdown: Number(m.current_drawdown),
        max_drawdown: Number(m.max_drawdown),
        avg_drawdown: Number(m.avg_drawdown),
        max_drawdown_duration_days: Number(m.max_drawdown_duration_days),
        sharpe_ratio: Number(m.sharpe_ratio),
        sortino_ratio: Number(m.sortino_ratio),
        calmar_ratio: Number(m.calmar_ratio),
        var_95: Number(m.var_95),
        cvar_95: Number(m.cvar_95),
        worst_1m: Number(m.worst_1m),
        worst_3m: Number(m.worst_3m),
        worst_12m: Number(m.worst_12m),
        drawdown_series: m.drawdown_series.map(d => ({
          ...d,
          drawdown: Number(d.drawdown)
        }))
      }))
    );
  }

  /**
   * Get execution quality metrics.
   */
  getExecutionMetrics(filters: PerformanceFilters = {}): Observable<ExecutionMetrics> {
    const params = this.buildParams(filters);
    return this.http.get<ExecutionMetrics>(`${this.baseUrl}/execution`, { params }).pipe(
      map(m => ({
        ...m,
        total_orders: Number(m.total_orders),
        fill_rate: Number(m.fill_rate),
        partial_fills: Number(m.partial_fills),
        rejected_orders: Number(m.rejected_orders),
        total_commission: Number(m.total_commission),
        total_slippage: Number(m.total_slippage),
        avg_slippage_bps: Number(m.avg_slippage_bps),
        commission_as_pct_nav: Number(m.commission_as_pct_nav),
        avg_fill_time_ms: m.avg_fill_time_ms != null ? Number(m.avg_fill_time_ms) : undefined,
        by_symbol: m.by_symbol.map(s => ({
          ...s,
          orders: Number(s.orders),
          filled: Number(s.filled),
          fill_rate: Number(s.fill_rate),
          avg_slippage_bps: Number(s.avg_slippage_bps),
          total_commission: Number(s.total_commission)
        }))
      }))
    );
  }

  /**
   * Get signal performance analysis.
   */
  getSignalPerformance(filters: PerformanceFilters = {}): Observable<SignalPerformance> {
    const params = this.buildParams(filters);
    return this.http.get<SignalPerformance>(`${this.baseUrl}/signals`, { params }).pipe(
      map(m => ({
        ...m,
        total_signals: Number(m.total_signals),
        winning_signals: Number(m.winning_signals),
        losing_signals: Number(m.losing_signals),
        hit_rate: Number(m.hit_rate),
        long_signals: Number(m.long_signals),
        long_hit_rate: Number(m.long_hit_rate),
        short_signals: Number(m.short_signals),
        short_hit_rate: Number(m.short_hit_rate),
        avg_winner_return: Number(m.avg_winner_return),
        avg_loser_return: Number(m.avg_loser_return),
        profit_factor: Number(m.profit_factor),
        avg_holding_days: Number(m.avg_holding_days),
        avg_winner_holding_days: Number(m.avg_winner_holding_days),
        avg_loser_holding_days: Number(m.avg_loser_holding_days),
        by_symbol: m.by_symbol.map(s => ({
          ...s,
          signals: Number(s.signals),
          winners: Number(s.winners),
          hit_rate: Number(s.hit_rate),
          avg_return: Number(s.avg_return),
          total_pnl: Number(s.total_pnl)
        }))
      }))
    );
  }

  /**
   * Get exposure analysis.
   */
  getExposureAnalysis(filters: PerformanceFilters = {}): Observable<ExposureAnalysis> {
    const params = this.buildParams(filters);
    return this.http.get<ExposureAnalysis>(`${this.baseUrl}/exposure`, { params }).pipe(
      map(m => ({
        ...m,
        current_gross_exposure: Number(m.current_gross_exposure),
        current_net_exposure: Number(m.current_net_exposure),
        current_long_exposure: Number(m.current_long_exposure),
        current_short_exposure: Number(m.current_short_exposure),
        avg_gross_exposure: Number(m.avg_gross_exposure),
        avg_net_exposure: Number(m.avg_net_exposure),
        max_gross_exposure: Number(m.max_gross_exposure),
        avg_daily_turnover: Number(m.avg_daily_turnover),
        avg_monthly_turnover: Number(m.avg_monthly_turnover),
        annual_turnover: Number(m.annual_turnover),
        exposure_history: m.exposure_history.map(e => ({
          ...e,
          gross_exposure: Number(e.gross_exposure),
          net_exposure: Number(e.net_exposure),
          long_exposure: Number(e.long_exposure),
          short_exposure: Number(e.short_exposure)
        })),
        by_sector: m.by_sector.map(s => ({
          ...s,
          exposure: Number(s.exposure),
          position_count: Number(s.position_count)
        }))
      }))
    );
  }
}
