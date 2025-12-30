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

@Injectable({ providedIn: 'root' })
export class InstrumentInfoService {
  private baseUrl = 'http://localhost:8000/api/v1/instruments';

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
}
