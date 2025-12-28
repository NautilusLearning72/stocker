import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Signal {
    strategy_version: string;
    symbol: string;
    date: string;
    lookback_return: number | null;
    ewma_vol: number | null;
    direction: number | null;
    target_weight: number | null;
}

@Injectable({
    providedIn: 'root',
})
export class SignalService {
    private baseUrl = 'http://localhost:8000/api/v1/signals';

    constructor(private http: HttpClient) { }

    getLatestSignals(): Observable<Signal[]> {
        return this.http.get<Signal[]>(`${this.baseUrl}/latest`);
    }

    getSignals(asOf?: string, symbol?: string): Observable<Signal[]> {
        const params: any = {};
        if (asOf) params.as_of = asOf;
        if (symbol) params.symbol = symbol;
        return this.http.get<Signal[]>(this.baseUrl, { params });
    }
}
