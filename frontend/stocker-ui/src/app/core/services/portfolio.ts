import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface PortfolioState {
  portfolio_id: string;
  date: string;
  nav: number;
  cash: number;
  gross_exposure: number;
  net_exposure: number;
  realized_pnl: number;
  unrealized_pnl: number;
  drawdown: number;
  high_water_mark: number;
}

export interface Holding {
  portfolio_id: string;
  date: string;
  symbol: string;
  qty: number;
  cost_basis: number;
  market_value: number;
}

export interface PositionSnapshot {
  portfolio_id: string;
  date: string;
  symbol: string;
  side?: string | null;
  qty: number;
  avg_entry_price?: number | null;
  cost_basis?: number | null;
  market_value?: number | null;
  current_price?: number | null;
  lastday_price?: number | null;
  change_today?: number | null;
  unrealized_pl?: number | null;
  unrealized_plpc?: number | null;
  unrealized_intraday_pl?: number | null;
  unrealized_intraday_plpc?: number | null;
  asset_class?: string | null;
  exchange?: string | null;
  source?: string | null;
  as_of_ts?: string | null;
}

@Injectable({
  providedIn: 'root',
})
export class PortfolioService {
  private baseUrl = 'http://localhost:8000/api/v1/portfolio';

  constructor(private http: HttpClient) { }

  getState(portfolioId = 'main'): Observable<PortfolioState | null> {
    return this.http.get<PortfolioState | null>(`${this.baseUrl}/state`, {
      params: { portfolio_id: portfolioId }
    });
  }

  getHoldings(portfolioId = 'main'): Observable<Holding[]> {
    return this.http.get<Holding[]>(`${this.baseUrl}/holdings`, {
      params: { portfolio_id: portfolioId }
    });
  }

  getPositions(portfolioId = 'main'): Observable<PositionSnapshot[]> {
    return this.http.get<PositionSnapshot[]>(`${this.baseUrl}/positions`, {
      params: { portfolio_id: portfolioId }
    });
  }
}
