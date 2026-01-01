import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface PortfolioSyncResult {
  portfolio_id: string;
  orders_created: number;
  orders_updated: number;
  fills_created: number;
  holdings_refreshed: number;
  portfolio_state_updated: boolean;
  synced_at: string;
}

@Injectable({ providedIn: 'root' })
export class PortfolioSyncService {
  private baseUrl = 'http://localhost:8000/api/v1/admin/portfolio-sync';

  constructor(private http: HttpClient) {}

  sync(portfolioId = 'main'): Observable<PortfolioSyncResult> {
    return this.http.post<PortfolioSyncResult>(this.baseUrl, { portfolio_id: portfolioId });
  }
}
