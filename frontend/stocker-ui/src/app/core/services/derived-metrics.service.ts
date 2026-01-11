import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';

export interface DerivedMetricDefinition {
  id: number;
  metric_key: string;
  name: string;
  category: string;
  unit?: string | null;
  direction: string;
  lookback_days?: number | null;
  description?: string | null;
  tags?: string | null;
  source_table?: string | null;
  source_field?: string | null;
  version: string;
  is_active: boolean;
}

export interface DerivedMetricValue {
  symbol: string;
  as_of_date: string;
  metric_id: number;
  metric_key: string;
  value: number | null;
  zscore: number | null;
  percentile: number | null;
  rank: number | null;
  source: string;
  calc_version: string;
}

export interface DerivedMetricRuleSet {
  id: number;
  name: string;
  description?: string | null;
  universe_id?: number | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface DerivedMetricRule {
  id: number;
  rule_set_id: number;
  metric_id: number;
  operator: string;
  threshold_low?: number | null;
  threshold_high?: number | null;
  weight: number;
  is_required: boolean;
  normalize?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface RuleSetCreate {
  name: string;
  description?: string | null;
  universe_id?: number | null;
  is_active?: boolean;
}

export interface RuleSetUpdate {
  name?: string | null;
  description?: string | null;
  universe_id?: number | null;
  is_active?: boolean | null;
}

export interface RuleCreate {
  metric_id?: number | null;
  metric_key?: string | null;
  operator: string;
  threshold_low?: number | null;
  threshold_high?: number | null;
  weight?: number | null;
  is_required?: boolean | null;
  normalize?: string | null;
}

export interface RuleUpdate {
  metric_id?: number | null;
  metric_key?: string | null;
  operator?: string | null;
  threshold_low?: number | null;
  threshold_high?: number | null;
  weight?: number | null;
  is_required?: boolean | null;
  normalize?: string | null;
}

export interface ScoreRow {
  symbol: string;
  score: number | null;
  rank: number | null;
  percentile: number | null;
  passes_required: boolean;
  metrics: Record<string, number | null>;
  holdings?: Record<string, any> | null;
}

export interface ScoresResponse {
  items: ScoreRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface DerivedMetricsStatus {
  latest_values_date: string | null;
  latest_scores_date: string | null;
  latest_values_updated_at: string | null;
  latest_scores_updated_at: string | null;
}

export interface ScoresQueryParams {
  rule_set_id: number;
  as_of_date?: string;
  search?: string;
  universe_id?: number;
  sector?: string;
  industry?: string;
  min_score?: number;
  max_score?: number;
  sort?: string;
  order?: string;
  page?: number;
  page_size?: number;
  columns?: string[];
}

export interface MetricFilterClause {
  field: string;
  op: string;
  value?: string | number | null;
  metric_key?: string | null;
}

export interface ScoresQueryBody {
  rule_set_id: number;
  as_of_date?: string | null;
  search?: string | null;
  universe_id?: number | null;
  filters?: MetricFilterClause[];
  sort?: {
    field: string;
    order?: string;
  } | null;
  columns?: string[];
  page?: number;
  page_size?: number;
}

@Injectable({ providedIn: 'root' })
export class DerivedMetricsService {
  private baseUrl = 'http://localhost:8000/api/v1/metrics/derived';

  constructor(private http: HttpClient) {}

  getDefinitions(params: { category?: string; active?: boolean; version?: string } = {}):
    Observable<DerivedMetricDefinition[]> {
    let httpParams = new HttpParams();
    if (params.category) httpParams = httpParams.set('category', params.category);
    if (params.active !== undefined) httpParams = httpParams.set('active', String(params.active));
    if (params.version) httpParams = httpParams.set('version', params.version);
    return this.http.get<DerivedMetricDefinition[]>(`${this.baseUrl}/definitions`, { params: httpParams });
  }

  getValues(params: { as_of_date?: string; symbol?: string; metric_keys?: string[] } = {}):
    Observable<DerivedMetricValue[]> {
    let httpParams = new HttpParams();
    if (params.as_of_date) httpParams = httpParams.set('as_of_date', params.as_of_date);
    if (params.symbol) httpParams = httpParams.set('symbol', params.symbol);
    if (params.metric_keys) {
      params.metric_keys.forEach((key) => {
        httpParams = httpParams.append('metric_keys', key);
      });
    }
    return this.http.get<DerivedMetricValue[]>(`${this.baseUrl}/values`, { params: httpParams }).pipe(
      map((rows) => rows.map((row) => ({
        ...row,
        value: this.toNumber(row.value),
        zscore: this.toNumber(row.zscore),
        percentile: this.toNumber(row.percentile),
        rank: row.rank != null ? Number(row.rank) : null,
      })))
    );
  }

  getRuleSets(active?: boolean): Observable<DerivedMetricRuleSet[]> {
    let httpParams = new HttpParams();
    if (active !== undefined) httpParams = httpParams.set('active', String(active));
    return this.http.get<DerivedMetricRuleSet[]>(`${this.baseUrl}/rule-sets`, { params: httpParams });
  }

  createRuleSet(payload: RuleSetCreate): Observable<DerivedMetricRuleSet> {
    return this.http.post<DerivedMetricRuleSet>(`${this.baseUrl}/rule-sets`, payload);
  }

  updateRuleSet(ruleSetId: number, payload: RuleSetUpdate): Observable<DerivedMetricRuleSet> {
    return this.http.patch<DerivedMetricRuleSet>(`${this.baseUrl}/rule-sets/${ruleSetId}`, payload);
  }

  deleteRuleSet(ruleSetId: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/rule-sets/${ruleSetId}`);
  }

  getRules(ruleSetId: number): Observable<DerivedMetricRule[]> {
    return this.http.get<DerivedMetricRule[]>(`${this.baseUrl}/rule-sets/${ruleSetId}/rules`).pipe(
      map((rows) => rows.map((row) => ({
        ...row,
        threshold_low: this.toNumber(row.threshold_low),
        threshold_high: this.toNumber(row.threshold_high),
        weight: this.toNumber(row.weight) ?? 0,
      })))
    );
  }

  createRule(ruleSetId: number, payload: RuleCreate): Observable<DerivedMetricRule> {
    return this.http.post<DerivedMetricRule>(`${this.baseUrl}/rule-sets/${ruleSetId}/rules`, payload).pipe(
      map((row) => ({
        ...row,
        threshold_low: this.toNumber(row.threshold_low),
        threshold_high: this.toNumber(row.threshold_high),
        weight: this.toNumber(row.weight) ?? 0,
      }))
    );
  }

  updateRule(ruleId: number, payload: RuleUpdate): Observable<DerivedMetricRule> {
    return this.http.patch<DerivedMetricRule>(`${this.baseUrl}/rules/${ruleId}`, payload).pipe(
      map((row) => ({
        ...row,
        threshold_low: this.toNumber(row.threshold_low),
        threshold_high: this.toNumber(row.threshold_high),
        weight: this.toNumber(row.weight) ?? 0,
      }))
    );
  }

  deleteRule(ruleId: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/rules/${ruleId}`);
  }

  getScores(params: ScoresQueryParams): Observable<ScoresResponse> {
    let httpParams = new HttpParams()
      .set('rule_set_id', String(params.rule_set_id));

    if (params.as_of_date) httpParams = httpParams.set('as_of_date', params.as_of_date);
    if (params.search) httpParams = httpParams.set('search', params.search);
    if (params.universe_id !== undefined) httpParams = httpParams.set('universe_id', String(params.universe_id));
    if (params.sector) httpParams = httpParams.set('sector', params.sector);
    if (params.industry) httpParams = httpParams.set('industry', params.industry);
    if (params.min_score !== undefined && params.min_score !== null) {
      httpParams = httpParams.set('min_score', String(params.min_score));
    }
    if (params.max_score !== undefined && params.max_score !== null) {
      httpParams = httpParams.set('max_score', String(params.max_score));
    }
    if (params.sort) httpParams = httpParams.set('sort', params.sort);
    if (params.order) httpParams = httpParams.set('order', params.order);
    if (params.page) httpParams = httpParams.set('page', String(params.page));
    if (params.page_size) httpParams = httpParams.set('page_size', String(params.page_size));
    if (params.columns) {
      params.columns.forEach((col) => {
        httpParams = httpParams.append('columns', col);
      });
    }

    return this.http.get<ScoresResponse>(`${this.baseUrl}/scores`, { params: httpParams }).pipe(
      map((response) => this.normalizeScores(response))
    );
  }

  queryScores(body: ScoresQueryBody): Observable<ScoresResponse> {
    return this.http.post<ScoresResponse>(`${this.baseUrl}/scores/query`, body).pipe(
      map((response) => this.normalizeScores(response))
    );
  }

  getStatus(): Observable<DerivedMetricsStatus> {
    return this.http.get<DerivedMetricsStatus>(`${this.baseUrl}/status`);
  }

  private normalizeScores(response: ScoresResponse): ScoresResponse {
    return {
      ...response,
      items: response.items.map((item) => ({
        ...item,
        score: this.toNumber(item.score),
        rank: item.rank != null ? Number(item.rank) : null,
        percentile: this.toNumber(item.percentile),
        metrics: this.normalizeMetrics(item.metrics),
      })),
    };
  }

  private normalizeMetrics(metrics: Record<string, any> | null | undefined): Record<string, number | null> {
    if (!metrics) return {};
    const normalized: Record<string, number | null> = {};
    Object.entries(metrics).forEach(([key, value]) => {
      normalized[key] = this.toNumber(value);
    });
    return normalized;
  }

  private toNumber(value: any): number | null {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
}
