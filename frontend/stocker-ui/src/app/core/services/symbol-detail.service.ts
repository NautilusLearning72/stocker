import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, map } from 'rxjs';

export interface InstrumentMetrics {
  as_of_date: string;
  period_type: string;
  // Market & valuation
  market_cap?: number | null;
  enterprise_value?: number | null;
  shares_outstanding?: number | null;
  beta?: number | null;
  // Valuation ratios
  pe_ttm?: number | null;
  pe_forward?: number | null;
  price_to_book?: number | null;
  price_to_sales?: number | null;
  peg_ratio?: number | null;
  ev_to_ebitda?: number | null;
  fcf_yield?: number | null;
  dividend_yield?: number | null;
  // Profitability
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  roe?: number | null;
  roa?: number | null;
  roic?: number | null;
  // Growth
  revenue_growth_yoy?: number | null;
  earnings_growth_yoy?: number | null;
  eps_growth_yoy?: number | null;
  // Leverage
  debt_to_equity?: number | null;
  net_debt_to_ebitda?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;
}

export interface SymbolDetail {
  symbol: string;
  name?: string | null;
  asset_class?: string | null;
  sector?: string | null;
  industry?: string | null;
  exchange?: string | null;
  currency?: string | null;
  active: boolean;
  metrics?: InstrumentMetrics | null;
}

export interface DailyPrice {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
}

export interface SentimentData {
  date: string;
  sentiment_score: number;
  sentiment_magnitude?: number | null;
  article_count?: number | null;
  positive_count?: number | null;
  neutral_count?: number | null;
  negative_count?: number | null;
}

export interface SearchResult {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  exchange?: string | null;
}

@Injectable({ providedIn: 'root' })
export class SymbolDetailService {
  private baseUrl = 'http://localhost:8000/api/v1/instruments';

  constructor(private http: HttpClient) {}

  getDetail(symbol: string): Observable<SymbolDetail> {
    return this.http.get<any>(
      `${this.baseUrl}/${encodeURIComponent(symbol)}`
    ).pipe(
      map(data => ({
        ...data,
        metrics: data.metrics ? this.convertMetrics(data.metrics) : null,
      }))
    );
  }

  private convertMetrics(m: any): InstrumentMetrics {
    return {
      as_of_date: m.as_of_date,
      period_type: m.period_type,
      market_cap: m.market_cap != null ? Number(m.market_cap) : null,
      enterprise_value: m.enterprise_value != null ? Number(m.enterprise_value) : null,
      shares_outstanding: m.shares_outstanding != null ? Number(m.shares_outstanding) : null,
      beta: m.beta != null ? Number(m.beta) : null,
      pe_ttm: m.pe_ttm != null ? Number(m.pe_ttm) : null,
      pe_forward: m.pe_forward != null ? Number(m.pe_forward) : null,
      price_to_book: m.price_to_book != null ? Number(m.price_to_book) : null,
      price_to_sales: m.price_to_sales != null ? Number(m.price_to_sales) : null,
      peg_ratio: m.peg_ratio != null ? Number(m.peg_ratio) : null,
      ev_to_ebitda: m.ev_to_ebitda != null ? Number(m.ev_to_ebitda) : null,
      fcf_yield: m.fcf_yield != null ? Number(m.fcf_yield) : null,
      dividend_yield: m.dividend_yield != null ? Number(m.dividend_yield) : null,
      gross_margin: m.gross_margin != null ? Number(m.gross_margin) : null,
      operating_margin: m.operating_margin != null ? Number(m.operating_margin) : null,
      net_margin: m.net_margin != null ? Number(m.net_margin) : null,
      roe: m.roe != null ? Number(m.roe) : null,
      roa: m.roa != null ? Number(m.roa) : null,
      roic: m.roic != null ? Number(m.roic) : null,
      revenue_growth_yoy: m.revenue_growth_yoy != null ? Number(m.revenue_growth_yoy) : null,
      earnings_growth_yoy: m.earnings_growth_yoy != null ? Number(m.earnings_growth_yoy) : null,
      eps_growth_yoy: m.eps_growth_yoy != null ? Number(m.eps_growth_yoy) : null,
      debt_to_equity: m.debt_to_equity != null ? Number(m.debt_to_equity) : null,
      net_debt_to_ebitda: m.net_debt_to_ebitda != null ? Number(m.net_debt_to_ebitda) : null,
      current_ratio: m.current_ratio != null ? Number(m.current_ratio) : null,
      quick_ratio: m.quick_ratio != null ? Number(m.quick_ratio) : null,
    };
  }

  getPrices(symbol: string, days: number = 30): Observable<DailyPrice[]> {
    return this.http.get<any[]>(
      `${this.baseUrl}/${encodeURIComponent(symbol)}/prices`,
      { params: { days: days.toString() } }
    ).pipe(
      map(prices => prices.map(p => ({
        date: p.date,
        open: Number(p.open),
        high: Number(p.high),
        low: Number(p.low),
        close: Number(p.close),
        adj_close: Number(p.adj_close),
        volume: Number(p.volume),
      })))
    );
  }

  getSentiment(symbol: string, days: number = 30): Observable<SentimentData[]> {
    return this.http.get<any[]>(
      `${this.baseUrl}/${encodeURIComponent(symbol)}/sentiment`,
      { params: { days: days.toString() } }
    ).pipe(
      map(items => items.map(s => ({
        date: s.date,
        sentiment_score: Number(s.sentiment_score),
        sentiment_magnitude: s.sentiment_magnitude != null ? Number(s.sentiment_magnitude) : null,
        article_count: s.article_count != null ? Number(s.article_count) : null,
        positive_count: s.positive_count != null ? Number(s.positive_count) : null,
        neutral_count: s.neutral_count != null ? Number(s.neutral_count) : null,
        negative_count: s.negative_count != null ? Number(s.negative_count) : null,
      })))
    );
  }

  search(query: string, limit: number = 10): Observable<SearchResult[]> {
    if (!query || query.trim().length === 0) {
      return of([]);
    }
    return this.http.get<SearchResult[]>(`${this.baseUrl}/search`, {
      params: { q: query.trim(), limit: limit.toString() },
    });
  }
}
