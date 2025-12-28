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
}
