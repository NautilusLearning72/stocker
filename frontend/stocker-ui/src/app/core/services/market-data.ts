import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';

export interface DailyBar {
  symbol: string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

@Injectable({
  providedIn: 'root',
})
export class MarketDataService {
  private baseUrl = 'http://localhost:8000/api/v1/market-data';

  constructor(private http: HttpClient) { }

  // Placeholder - endpoint not yet created
  getDailyBars(symbol: string, days = 30): Observable<DailyBar[]> {
    // TODO: Implement once backend endpoint exists
    return of([]);
  }
}
