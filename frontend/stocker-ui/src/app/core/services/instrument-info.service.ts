import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface InstrumentInfo {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  industry?: string | null;
  exchange?: string | null;
  currency?: string | null;
}

export interface SymbolValidationResult {
  valid: string[];
  invalid: string[];
}

export interface DataQualityAlert {
  symbol: string;
  date: string;
  issue_type: string;
  message: string;
  severity: string;
}

export interface BackfillResult {
  symbols_requested: number;
  records_processed: number;
  alerts: DataQualityAlert[];
}

@Injectable({ providedIn: 'root' })
export class InstrumentInfoService {
  private baseUrl = 'http://localhost:8000/api/v1/instruments';
  private adminUrl = 'http://localhost:8000/api/v1/admin';

  constructor(private http: HttpClient) {}

  getInfo(symbols: string[]): Observable<InstrumentInfo[]> {
    if (!symbols || symbols.length === 0) {
      return new Observable((observer) => {
        observer.next([]);
        observer.complete();
      });
    }
    const params = symbols.map((s) => `symbols=${encodeURIComponent(s)}`).join('&');
    return this.http.get<InstrumentInfo[]>(`${this.baseUrl}?${params}`);
  }

  validateSymbols(symbols: string[]): Observable<SymbolValidationResult> {
    return this.http.post<SymbolValidationResult>(`${this.baseUrl}/validate`, { symbols });
  }

  backfillPrices(symbols: string[], days = 200): Observable<BackfillResult> {
    return this.http.post<BackfillResult>(`${this.adminUrl}/backfill`, { symbols, days });
  }
}
