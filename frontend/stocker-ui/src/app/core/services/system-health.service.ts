import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ServiceStatus {
  name: string;
  status: 'healthy' | 'warning' | 'error';
  last_heartbeat: string;
  message?: string | null;
}

@Injectable({ providedIn: 'root' })
export class SystemHealthService {
  private baseUrl = 'http://localhost:8000/api/v1/admin/health';

  constructor(private http: HttpClient) {}

  getHealth(): Observable<ServiceStatus[]> {
    return this.http.get<ServiceStatus[]>(this.baseUrl);
  }
}
