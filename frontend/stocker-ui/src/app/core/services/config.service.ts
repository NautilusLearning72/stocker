import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ConfigEntry {
  key: string;
  value: string;
  value_type: 'int' | 'float' | 'bool' | 'str';
  category: string;
  description: string | null;
}

export interface ConfigMetadata {
  key: string;
  value_type: 'int' | 'float' | 'bool' | 'str';
  category: string;
  description: string;
  tooltip?: string;
  min?: number;
  max?: number;
  options?: string[];
}

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private baseUrl = 'http://localhost:8000/api/v1/admin/config';

  constructor(private http: HttpClient) {}

  getAll(): Observable<ConfigEntry[]> {
    return this.http.get<ConfigEntry[]>(this.baseUrl);
  }

  getCategories(): Observable<string[]> {
    return this.http.get<string[]>(`${this.baseUrl}/categories`);
  }

  getMetadata(): Observable<ConfigMetadata[]> {
    return this.http.get<ConfigMetadata[]>(`${this.baseUrl}/metadata`);
  }

  getByCategory(category: string): Observable<ConfigEntry[]> {
    return this.http.get<ConfigEntry[]>(`${this.baseUrl}/category/${category}`);
  }

  get(key: string): Observable<ConfigEntry> {
    return this.http.get<ConfigEntry>(`${this.baseUrl}/${key}`);
  }

  update(key: string, value: string): Observable<ConfigEntry> {
    return this.http.put<ConfigEntry>(`${this.baseUrl}/${key}`, { value });
  }

  bulkUpdate(updates: Record<string, string>): Observable<ConfigEntry[]> {
    return this.http.patch<ConfigEntry[]>(this.baseUrl, { updates });
  }
}
