import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Universe {
  id: number;
  name: string;
  description?: string;
  is_global: boolean;
  is_deleted: boolean;
}

export interface UniverseDetail extends Universe {
  members: string[];
}

export interface StrategyUniverse {
  strategy_id: string;
  universe_id: number | null;
  symbols: string[];
}

export interface MetricStatus {
  symbol: string;
  as_of_date: string | null;
}

@Injectable({ providedIn: 'root' })
export class UniverseService {
  private baseUrl = 'http://localhost:8000/api/v1/universes';

  constructor(private http: HttpClient) {}

  list(includeDeleted = false): Observable<Universe[]> {
    return this.http.get<Universe[]>(`${this.baseUrl}?include_deleted=${includeDeleted}`);
  }

  get(universeId: number): Observable<UniverseDetail> {
    return this.http.get<UniverseDetail>(`${this.baseUrl}/${universeId}`);
  }

  create(payload: { name: string; description?: string; is_global?: boolean }): Observable<Universe> {
    return this.http.post<Universe>(this.baseUrl, payload);
  }

  update(universeId: number, payload: { name?: string; description?: string; is_global?: boolean }): Observable<Universe> {
    return this.http.patch<Universe>(`${this.baseUrl}/${universeId}`, payload);
  }

  delete(universeId: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${universeId}`);
  }

  addMembers(universeId: number, symbols: string[]): Observable<{ added: number }> {
    return this.http.post<{ added: number }>(`${this.baseUrl}/${universeId}/members`, { symbols });
  }

  removeMember(universeId: number, symbol: string): Observable<{ removed: number }> {
    return this.http.delete<{ removed: number }>(`${this.baseUrl}/${universeId}/members/${symbol}`);
  }

  setStrategyUniverse(strategyId: string, universeId: number): Observable<{ strategy_id: string; universe_id: number }> {
    return this.http.post<{ strategy_id: string; universe_id: number }>(
      `${this.baseUrl}/strategies/${strategyId}/universe`,
      { universe_id: universeId }
    );
  }

  getStrategyUniverse(strategyId: string): Observable<StrategyUniverse> {
    return this.http.get<StrategyUniverse>(`${this.baseUrl}/strategies/${strategyId}/universe`);
  }

  getMetricsStatus(universeId?: number, symbols?: string[]): Observable<MetricStatus[]> {
    const params = [];
    if (universeId !== undefined) {
      params.push(`universe_id=${universeId}`);
    } else if (symbols && symbols.length) {
      params.push(`symbols=${symbols.join('&symbols=')}`);
    }
    const query = params.length ? `?${params.join('&')}` : '';
    return this.http.get<MetricStatus[]>(`${this.baseUrl}/metrics${query}`);
  }
}
