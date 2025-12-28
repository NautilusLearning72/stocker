import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Fill {
  fill_id: string;
  date: string | null;
  qty: number;
  price: number;
}

export interface Order {
  order_id: string;
  portfolio_id: string;
  date: string;
  symbol: string;
  side: string | null;
  qty: number;
  type: string | null;
  status: string | null;
  broker_order_id: string | null;
  fills: Fill[];
}

@Injectable({
  providedIn: 'root',
})
export class OrdersService {
  private baseUrl = 'http://localhost:8000/api/v1/orders';

  constructor(private http: HttpClient) {}

  getOrders(portfolioId = 'main', limit = 50): Observable<Order[]> {
    return this.http.get<Order[]>(this.baseUrl, {
      params: { portfolio_id: portfolioId, limit: limit.toString() }
    });
  }

  getOrder(orderId: string): Observable<Order | null> {
    return this.http.get<Order | null>(`${this.baseUrl}/${orderId}`);
  }
}
