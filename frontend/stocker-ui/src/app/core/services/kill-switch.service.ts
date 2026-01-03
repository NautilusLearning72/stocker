import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface KillSwitchStatus {
  portfolio_id: string;
  active: boolean;
  triggered_at?: string | null;
  reason?: string | null;
  source?: 'auto' | 'manual' | null;
}

export interface KillSwitchActionResult extends KillSwitchStatus {
  cancelled_orders?: number;
}

@Injectable({ providedIn: 'root' })
export class KillSwitchService {
  private baseUrl = 'http://localhost:8000/api/v1/admin/kill-switch';

  constructor(private http: HttpClient) {}

  status(portfolioId = 'main'): Observable<KillSwitchStatus> {
    const params = new HttpParams().set('portfolio_id', portfolioId);
    return this.http.get<KillSwitchStatus>(`${this.baseUrl}/status`, { params });
  }

  activate(portfolioId = 'main', reason?: string): Observable<KillSwitchActionResult> {
    return this.http.post<KillSwitchActionResult>(`${this.baseUrl}/activate`, {
      portfolio_id: portfolioId,
      reason,
    });
  }

  reset(portfolioId = 'main'): Observable<KillSwitchStatus> {
    return this.http.post<KillSwitchStatus>(`${this.baseUrl}/reset`, {
      portfolio_id: portfolioId,
    });
  }
}
