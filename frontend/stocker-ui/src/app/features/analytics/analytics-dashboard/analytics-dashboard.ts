import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatChipsModule } from '@angular/material/chips';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSortModule, Sort } from '@angular/material/sort';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatCardModule } from '@angular/material/card';
import { forkJoin, from, of } from 'rxjs';
import { catchError, finalize, mergeMap } from 'rxjs/operators';

import {
  DerivedMetricsService,
  DerivedMetricDefinition,
  DerivedMetricRuleSet,
  DerivedMetricRule,
  ScoreRow,
  MetricFilterClause,
  DerivedMetricsStatus,
} from '../../../core/services/derived-metrics.service';
import { InstrumentInfoService, InstrumentInfo } from '../../../core/services/instrument-info.service';
import { PortfolioService, Holding } from '../../../core/services/portfolio';
import { SymbolDetailService } from '../../../core/services/symbol-detail.service';
import { UniverseService, Universe } from '../../../core/services/universe.service';
import { QuickOrderDialog } from '../components/quick-order-dialog/quick-order-dialog';
import { SymbolLink } from '../../../shared/components/symbol-link/symbol-link';

interface MetricFilter {
  metric_key: string;
  op: string;
  value: number | null;
}

interface RuleEdit extends DerivedMetricRule {
  metric_key: string;
  normalize_display: string;
}

interface RuleSetDraft {
  id: number;
  name: string;
  description: string | null;
  universe_id: number | null;
  is_active: boolean;
}

interface NewRuleDraft {
  metric_key: string;
  operator: string;
  threshold_low: number | null;
  threshold_high: number | null;
  weight: number;
  is_required: boolean;
  normalize_display: string;
}

@Component({
  selector: 'app-analytics-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatTooltipModule,
    MatSidenavModule,
    MatChipsModule,
    MatCheckboxModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatProgressSpinnerModule,
    MatPaginatorModule,
    MatSortModule,
    MatDividerModule,
    MatDialogModule,
    MatCardModule,
    SymbolLink,
  ],
  templateUrl: './analytics-dashboard.html',
  styleUrl: './analytics-dashboard.scss',
})
export class AnalyticsDashboard implements OnInit {
  definitions: DerivedMetricDefinition[] = [];
  definitionByKey: Record<string, DerivedMetricDefinition> = {};
  definitionById: Record<number, DerivedMetricDefinition> = {};
  definitionsByCategory: Record<string, DerivedMetricDefinition[]> = {};
  categories: string[] = [];

  ruleSets: DerivedMetricRuleSet[] = [];
  selectedRuleSetId: number | null = null;
  ruleSetDraft: RuleSetDraft | null = null;
  rules: RuleEdit[] = [];
  universes: Universe[] = [];
  universeMap: Record<number, Universe> = {};
  loadingUniverses = false;
  metricsStatus: DerivedMetricsStatus | null = null;
  loadingStatus = false;
  newRuleSet: RuleSetDraft = {
    id: 0,
    name: '',
    description: null,
    universe_id: null,
    is_active: true,
  };
  newRule: NewRuleDraft = {
    metric_key: '',
    operator: '>',
    threshold_low: null,
    threshold_high: null,
    weight: 1,
    is_required: false,
    normalize_display: 'value',
  };

  scores: ScoreRow[] = [];
  total = 0;

  baseColumns = ['symbol', 'score', 'rank', 'percentile', 'sector', 'last_price', 'holding', 'actions'];
  selectedMetricKeys: string[] = [];
  displayedColumns: string[] = [];

  search = '';
  sector = '';
  industry = '';
  minScore: number | null = null;
  maxScore: number | null = null;
  universeId: number | null = null;
  asOfDate: Date | null = null;

  metricFilters: MetricFilter[] = [];
  filterMetricKey = '';
  filterOperator = '>';
  filterValue: number | null = null;

  sortField = 'score';
  sortOrder: 'asc' | 'desc' = 'desc';
  page = 1;
  pageSize = 100;
  pageSizeOptions = [25, 50, 100, 200];

  holdingsMap: Record<string, Holding> = {};
  instrumentInfoMap: Record<string, InstrumentInfo> = {};
  lastPriceMap: Record<string, number> = {};

  loadingScores = false;
  loadingRuleSets = false;
  loadingRules = false;
  loadingDefinitions = false;
  loadingHoldings = false;
  loadingPrices = false;
  errorMessage = '';
  drawerError = '';
  drawerOpen = false;
  lastScoresRequest: {
    mode: 'scores' | 'query';
    payload: Record<string, any>;
  } | null = null;

  operators = ['any', '>', '>=', '<', '<=', 'between'];
  normalizeOptions = ['value', 'zscore', 'percentile'];

  constructor(
    private derivedMetricsService: DerivedMetricsService,
    private instrumentInfoService: InstrumentInfoService,
    private portfolioService: PortfolioService,
    private symbolDetailService: SymbolDetailService,
    private universeService: UniverseService,
    private dialog: MatDialog,
    private router: Router,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadDefinitions();
    this.loadRuleSets();
    this.loadHoldings();
    this.loadUniverses();
    this.loadStatus();
  }

  toggleDrawer(): void {
    this.drawerOpen = !this.drawerOpen;
  }

  onRuleSetSelectionChange(): void {
    if (!this.selectedRuleSetId) {
      this.scores = [];
      this.total = 0;
      return;
    }
    this.errorMessage = '';
    const selected = this.ruleSets.find((rs) => rs.id === this.selectedRuleSetId);
    if (selected) {
      this.ruleSetDraft = {
        id: selected.id,
        name: selected.name,
        description: selected.description ?? null,
        universe_id: selected.universe_id ?? null,
        is_active: selected.is_active,
      };
    }
    this.loadRules();
    this.loadScores();
  }

  loadDefinitions(): void {
    this.loadingDefinitions = true;
    this.derivedMetricsService.getDefinitions({ active: true, version: 'v1' }).subscribe({
      next: (defs) => {
        this.definitions = defs;
        this.definitionByKey = {};
        this.definitionById = {};
        this.definitionsByCategory = {};
        defs.forEach((def) => {
          this.definitionByKey[def.metric_key] = def;
          this.definitionById[def.id] = def;
          if (!this.definitionsByCategory[def.category]) {
            this.definitionsByCategory[def.category] = [];
          }
          this.definitionsByCategory[def.category].push(def);
        });
        this.categories = Object.keys(this.definitionsByCategory).sort();
        this.categories.forEach((category) => {
          this.definitionsByCategory[category] = this.definitionsByCategory[category]
            .sort((a, b) => a.metric_key.localeCompare(b.metric_key));
        });
        this.setDefaultColumns();
        this.loadingDefinitions = false;
        this.cdr.detectChanges();
        if (this.selectedRuleSetId) {
          this.loadRules();
          this.loadScores();
        }
      },
      error: (err) => {
        console.error('Failed to load metric definitions', err);
        this.loadingDefinitions = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadRuleSets(): void {
    this.loadingRuleSets = true;
    this.derivedMetricsService.getRuleSets().subscribe({
      next: (ruleSets) => {
        this.ruleSets = ruleSets;
        console.debug('Analytics rule sets loaded', ruleSets.length);
        if (!this.selectedRuleSetId && ruleSets.length > 0) {
          this.selectedRuleSetId = ruleSets[0].id;
          this.ruleSetDraft = {
            id: ruleSets[0].id,
            name: ruleSets[0].name,
            description: ruleSets[0].description ?? null,
            universe_id: ruleSets[0].universe_id ?? null,
            is_active: ruleSets[0].is_active,
          };
          this.loadRules();
          this.loadScores();
        }
        this.loadingRuleSets = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load rule sets', err);
        this.loadingRuleSets = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadUniverses(): void {
    this.loadingUniverses = true;
    this.universeService.list(false).subscribe({
      next: (rows) => {
        this.universes = rows;
        this.universeMap = rows.reduce((acc, universe) => {
          acc[universe.id] = universe;
          return acc;
        }, {} as Record<number, Universe>);
        this.loadingUniverses = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load universes', err);
        this.loadingUniverses = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadRules(): void {
    if (!this.selectedRuleSetId) return;
    this.loadingRules = true;
    this.derivedMetricsService.getRules(this.selectedRuleSetId).subscribe({
      next: (rules) => {
        this.rules = rules.map((rule) => ({
          ...rule,
          metric_key: this.definitionById[rule.metric_id]?.metric_key ?? '',
          normalize_display: rule.normalize ?? 'value',
        }));
        this.loadingRules = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load rules', err);
        this.loadingRules = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadHoldings(): void {
    this.loadingHoldings = true;
    this.portfolioService.getHoldings('main').subscribe({
      next: (holdings) => {
        const map: Record<string, Holding> = {};
        holdings.forEach((holding) => {
          map[holding.symbol] = holding;
        });
        this.holdingsMap = map;
        this.loadingHoldings = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load holdings', err);
        this.loadingHoldings = false;
        this.cdr.detectChanges();
      },
    });
  }

  applyFilters(): void {
    this.page = 1;
    this.loadScores();
  }

  clearFilters(): void {
    this.search = '';
    this.sector = '';
    this.industry = '';
    this.minScore = null;
    this.maxScore = null;
    this.universeId = null;
    this.metricFilters = [];
    this.page = 1;
    this.loadScores();
  }

  addMetricFilter(): void {
    if (!this.filterMetricKey || this.filterValue === null) return;
    this.metricFilters = [
      ...this.metricFilters,
      {
        metric_key: this.filterMetricKey,
        op: this.filterOperator,
        value: this.filterValue,
      },
    ];
    this.filterMetricKey = '';
    this.filterOperator = '>';
    this.filterValue = null;
    this.applyFilters();
  }

  removeMetricFilter(index: number): void {
    this.metricFilters = this.metricFilters.filter((_, i) => i !== index);
    this.applyFilters();
  }

  onColumnsChange(): void {
    this.updateDisplayedColumns();
    this.loadScores();
  }

  onSortChange(event: Sort): void {
    if (!event.direction) return;
    if (this.selectedMetricKeys.includes(event.active)) {
      if (!this.asOfDate) {
        this.errorMessage = 'Select an as-of date to sort by metric columns';
        return;
      }
      this.sortField = `metric:${event.active}`;
    } else if (event.active === 'percentile') {
      this.sortField = 'score';
    } else {
      this.sortField = event.active;
    }
    this.sortOrder = event.direction as 'asc' | 'desc';
    this.loadScores();
  }

  onPageChange(event: PageEvent): void {
    this.page = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.loadScores();
  }

  refresh(): void {
    this.loadScores();
    this.loadHoldings();
    this.loadStatus();
  }

  loadStatus(): void {
    this.loadingStatus = true;
    this.derivedMetricsService.getStatus().subscribe({
      next: (status) => {
        this.metricsStatus = status;
        this.loadingStatus = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load derived metrics status', err);
        this.loadingStatus = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadScores(): void {
    if (!this.selectedRuleSetId) return;
    this.loadingScores = true;
    this.errorMessage = '';

    const asOfDate = this.toDateString(this.asOfDate);
    const filters: MetricFilterClause[] = [];
    if (this.sector) {
      filters.push({ field: 'sector', op: '=', value: this.sector });
    }
    if (this.industry) {
      filters.push({ field: 'industry', op: '=', value: this.industry });
    }
    this.metricFilters.forEach((filter) => {
      filters.push({
        field: 'metric',
        op: filter.op,
        value: filter.value ?? null,
        metric_key: filter.metric_key,
      });
    });

    const useQuery = filters.length > 0;
    const requestPayload = useQuery
      ? {
          rule_set_id: this.selectedRuleSetId,
          as_of_date: asOfDate ?? null,
          search: this.search || null,
          universe_id: this.universeId ?? null,
          filters,
          sort: { field: this.sortField, order: this.sortOrder },
          columns: this.selectedMetricKeys,
          page: this.page,
          page_size: this.pageSize,
        }
      : {
          rule_set_id: this.selectedRuleSetId,
          as_of_date: asOfDate,
          search: this.search,
          universe_id: this.universeId ?? undefined,
          sector: this.sector || undefined,
          industry: this.industry || undefined,
          min_score: this.minScore ?? undefined,
          max_score: this.maxScore ?? undefined,
          sort: this.sortField,
          order: this.sortOrder,
          page: this.page,
          page_size: this.pageSize,
          columns: this.selectedMetricKeys,
        };
    this.lastScoresRequest = {
      mode: useQuery ? 'query' : 'scores',
      payload: requestPayload,
    };
    console.debug('Analytics scores request', this.lastScoresRequest);

    const query$ = useQuery
      ? this.derivedMetricsService.queryScores({
          rule_set_id: this.selectedRuleSetId,
          as_of_date: asOfDate ?? null,
          search: this.search || null,
          universe_id: this.universeId ?? null,
          filters,
          sort: { field: this.sortField, order: this.sortOrder },
          columns: this.selectedMetricKeys,
          page: this.page,
          page_size: this.pageSize,
        })
      : this.derivedMetricsService.getScores({
          rule_set_id: this.selectedRuleSetId,
          as_of_date: asOfDate,
          search: this.search,
          universe_id: this.universeId ?? undefined,
          sector: this.sector || undefined,
          industry: this.industry || undefined,
          min_score: this.minScore ?? undefined,
          max_score: this.maxScore ?? undefined,
          sort: this.sortField,
          order: this.sortOrder,
          page: this.page,
          page_size: this.pageSize,
          columns: this.selectedMetricKeys,
        });

    query$
      .pipe(finalize(() => {
        this.loadingScores = false;
        this.cdr.detectChanges();
      }))
      .subscribe({
        next: (response) => {
          this.scores = response.items;
          this.total = response.total;
          console.debug('Analytics scores response', response.total, response.items.length);
          this.updateDisplayedColumns();
          this.loadInstrumentInfo(this.scores.map((row) => row.symbol));
          if (this.baseColumns.includes('last_price')) {
            this.loadLastPrices(this.scores.map((row) => row.symbol));
          }
        },
        error: (err) => {
          console.error('Failed to load scores', err);
          this.errorMessage = 'Failed to load analytics scores';
        },
      });
  }

  loadInstrumentInfo(symbols: string[]): void {
    const missing = symbols.filter((symbol) => !this.instrumentInfoMap[symbol]);
    if (missing.length === 0) return;
    this.instrumentInfoService.getInfo(missing).subscribe({
      next: (rows) => {
        const updated = { ...this.instrumentInfoMap };
        rows.forEach((row) => {
          updated[row.symbol] = row;
        });
        this.instrumentInfoMap = updated;
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load instrument info', err),
    });
  }

  loadLastPrices(symbols: string[]): void {
    const missing = symbols.filter((symbol) => this.lastPriceMap[symbol] === undefined);
    if (!missing.length) return;
    this.loadingPrices = true;
    from(missing)
      .pipe(
        mergeMap(
          (symbol) =>
            this.symbolDetailService.getPrices(symbol, 2).pipe(
              mergeMap((prices) => {
                const last = prices.length ? prices[prices.length - 1] : null;
                if (last && last.close != null) {
                  this.lastPriceMap[symbol] = last.close;
                }
                return of(symbol);
              }),
              catchError(() => of(symbol)),
            ),
          5,
        ),
        finalize(() => {
          this.loadingPrices = false;
          this.cdr.detectChanges();
        }),
      )
      .subscribe();
  }

  updateDisplayedColumns(): void {
    const metricColumns = this.selectedMetricKeys.filter((key) => !this.baseColumns.includes(key));
    this.displayedColumns = [...this.baseColumns, ...metricColumns];
  }

  setDefaultColumns(): void {
    const defaults = ['sentiment_score', 'mom_6m', 'pe_ttm'];
    this.selectedMetricKeys = defaults.filter((key) => !!this.definitionByKey[key]);
    if (this.selectedMetricKeys.length === 0 && this.definitions.length > 0) {
      this.selectedMetricKeys = this.definitions.slice(0, 3).map((def) => def.metric_key);
    }
    this.updateDisplayedColumns();
  }

  metricTooltip(metricKey: string): string {
    const def = this.definitionByKey[metricKey];
    if (!def) return metricKey;
    const pieces = [
      def.name,
      def.description ?? '',
      def.direction ? `Direction: ${def.direction}` : '',
      def.source_table ? `Source: ${def.source_table}${def.source_field ? `.${def.source_field}` : ''}` : '',
    ];
    return pieces.filter((piece) => piece).join('\n');
  }

  getSortActive(): string {
    if (this.sortField.startsWith('metric:')) {
      return this.sortField.split(':')[1];
    }
    return this.sortField;
  }

  getUniverseLabel(universeId: number | null | undefined): string {
    if (!universeId) return 'All';
    const universe = this.universeMap[universeId];
    if (!universe) return `Universe ${universeId}`;
    return universe.is_global ? `${universe.name} (Global)` : universe.name;
  }

  formatMetricValue(value: number | null, metricKey: string): string {
    if (value === null || value === undefined) return '—';
    const def = this.definitionByKey[metricKey];
    if (def?.unit === 'pct') return `${(value * 100).toFixed(2)}%`;
    if (def?.unit === 'price') return `$${value.toFixed(2)}`;
    if (def?.unit === 'ratio' || def?.unit === 'index') return value.toFixed(2);
    return value.toFixed(2);
  }

  formatScore(value: number | null): string {
    if (value === null || value === undefined) return '—';
    return value.toFixed(2);
  }

  formatPercent(value: number | null): string {
    if (value === null || value === undefined) return '—';
    return `${(value * 100).toFixed(1)}%`;
  }

  onRowClick(row: ScoreRow): void {
    this.router.navigate(['/symbol', row.symbol]);
  }

  openOrderDialog(row: ScoreRow, event: MouseEvent): void {
    event.stopPropagation();
    this.dialog.open(QuickOrderDialog, {
      data: { symbol: row.symbol },
    });
  }

  getHolding(symbol: string): Holding | null {
    return this.holdingsMap[symbol] ?? null;
  }

  getSector(symbol: string): string {
    return this.instrumentInfoMap[symbol]?.sector ?? '—';
  }

  getLastPrice(symbol: string): number | null {
    return this.lastPriceMap[symbol] ?? null;
  }

  createRuleSet(): void {
    if (!this.newRuleSet.name.trim()) {
      this.drawerError = 'Rule set name is required';
      return;
    }
    this.drawerError = '';
    this.derivedMetricsService.createRuleSet({
      name: this.newRuleSet.name.trim(),
      description: this.newRuleSet.description ?? undefined,
      universe_id: this.newRuleSet.universe_id ?? undefined,
      is_active: this.newRuleSet.is_active,
    }).subscribe({
      next: (ruleSet) => {
        this.ruleSets = [...this.ruleSets, ruleSet].sort((a, b) => a.name.localeCompare(b.name));
        this.selectedRuleSetId = ruleSet.id;
        this.ruleSetDraft = {
          id: ruleSet.id,
          name: ruleSet.name,
          description: ruleSet.description ?? null,
          universe_id: ruleSet.universe_id ?? null,
          is_active: ruleSet.is_active,
        };
        this.newRuleSet = {
          id: 0,
          name: '',
          description: null,
          universe_id: null,
          is_active: true,
        };
        this.loadRules();
        this.loadScores();
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to create rule set', err);
        this.drawerError = 'Failed to create rule set';
      },
    });
  }

  saveRuleSet(): void {
    if (!this.ruleSetDraft) return;
    if (!this.ruleSetDraft.name.trim()) {
      this.drawerError = 'Rule set name is required';
      return;
    }
    this.drawerError = '';
    this.derivedMetricsService.updateRuleSet(this.ruleSetDraft.id, {
      name: this.ruleSetDraft.name.trim(),
      description: this.ruleSetDraft.description ?? undefined,
      universe_id: this.ruleSetDraft.universe_id ?? undefined,
      is_active: this.ruleSetDraft.is_active,
    }).subscribe({
      next: (updated) => {
        this.ruleSets = this.ruleSets.map((rs) => (rs.id === updated.id ? updated : rs));
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to update rule set', err);
        this.drawerError = 'Failed to update rule set';
      },
    });
  }

  deleteRuleSet(): void {
    if (!this.ruleSetDraft) return;
    const confirmDelete = window.confirm(`Delete rule set "${this.ruleSetDraft.name}"?`);
    if (!confirmDelete) return;
    this.derivedMetricsService.deleteRuleSet(this.ruleSetDraft.id).subscribe({
      next: () => {
        this.ruleSets = this.ruleSets.filter((rs) => rs.id !== this.ruleSetDraft?.id);
        this.selectedRuleSetId = this.ruleSets.length ? this.ruleSets[0].id : null;
        this.ruleSetDraft = null;
        this.rules = [];
        this.loadScores();
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to delete rule set', err);
        this.drawerError = 'Failed to delete rule set';
      },
    });
  }

  duplicateRuleSet(): void {
    if (!this.ruleSetDraft) return;
    const name = `${this.ruleSetDraft.name} Copy`;
    this.derivedMetricsService.createRuleSet({
      name,
      description: this.ruleSetDraft.description ?? undefined,
      universe_id: this.ruleSetDraft.universe_id ?? undefined,
      is_active: this.ruleSetDraft.is_active,
    }).subscribe({
      next: (ruleSet) => {
        const createRules = this.rules.map((rule) =>
          this.derivedMetricsService.createRule(ruleSet.id, {
            metric_key: rule.metric_key,
            operator: rule.operator,
            threshold_low: rule.threshold_low ?? undefined,
            threshold_high: rule.threshold_high ?? undefined,
            weight: rule.weight,
            is_required: rule.is_required,
            normalize: this.toNormalizePayload(rule.normalize_display),
          })
        );
        if (!createRules.length) {
          this.ruleSets = [...this.ruleSets, ruleSet].sort((a, b) => a.name.localeCompare(b.name));
          this.selectedRuleSetId = ruleSet.id;
          this.ruleSetDraft = {
            id: ruleSet.id,
            name: ruleSet.name,
            description: ruleSet.description ?? null,
            universe_id: ruleSet.universe_id ?? null,
            is_active: ruleSet.is_active,
          };
          this.loadRules();
          this.loadScores();
          this.cdr.detectChanges();
          return;
        }
        forkJoin(createRules)
          .pipe(finalize(() => {
            this.ruleSets = [...this.ruleSets, ruleSet].sort((a, b) => a.name.localeCompare(b.name));
            this.selectedRuleSetId = ruleSet.id;
            this.ruleSetDraft = {
              id: ruleSet.id,
              name: ruleSet.name,
              description: ruleSet.description ?? null,
              universe_id: ruleSet.universe_id ?? null,
              is_active: ruleSet.is_active,
            };
            this.loadRules();
            this.loadScores();
            this.cdr.detectChanges();
          }))
          .subscribe();
      },
      error: (err) => {
        console.error('Failed to duplicate rule set', err);
        this.drawerError = 'Failed to duplicate rule set';
      },
    });
  }

  addRule(): void {
    if (!this.selectedRuleSetId) return;
    if (!this.newRule.metric_key) {
      this.drawerError = 'Select a metric for the rule';
      return;
    }
    this.drawerError = '';
    this.derivedMetricsService.createRule(this.selectedRuleSetId, {
      metric_key: this.newRule.metric_key,
      operator: this.newRule.operator,
      threshold_low: this.newRule.threshold_low ?? undefined,
      threshold_high: this.newRule.threshold_high ?? undefined,
      weight: this.newRule.weight,
      is_required: this.newRule.is_required,
      normalize: this.toNormalizePayload(this.newRule.normalize_display),
    }).subscribe({
      next: (rule) => {
        const newRule: RuleEdit = {
          ...rule,
          metric_key: this.definitionById[rule.metric_id]?.metric_key ?? this.newRule.metric_key,
          normalize_display: rule.normalize ?? 'value',
        };
        this.rules = [...this.rules, newRule];
        this.newRule = {
          metric_key: '',
          operator: '>',
          threshold_low: null,
          threshold_high: null,
          weight: 1,
          is_required: false,
          normalize_display: 'value',
        };
        this.loadScores();
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to create rule', err);
        this.drawerError = 'Failed to create rule';
      },
    });
  }

  saveRule(rule: RuleEdit): void {
    this.drawerError = '';
    this.derivedMetricsService.updateRule(rule.id, {
      metric_key: rule.metric_key,
      operator: rule.operator,
      threshold_low: rule.threshold_low ?? undefined,
      threshold_high: rule.threshold_high ?? undefined,
      weight: rule.weight,
      is_required: rule.is_required,
      normalize: this.toNormalizePayload(rule.normalize_display),
    }).subscribe({
      next: (updated) => {
        this.rules = this.rules.map((item) =>
          item.id === updated.id
            ? {
                ...updated,
                metric_key: this.definitionById[updated.metric_id]?.metric_key ?? rule.metric_key,
                normalize_display: updated.normalize ?? 'value',
              }
            : item
        );
        this.loadScores();
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to update rule', err);
        this.drawerError = 'Failed to update rule';
      },
    });
  }

  deleteRule(ruleId: number): void {
    const confirmDelete = window.confirm('Delete this rule?');
    if (!confirmDelete) return;
    this.derivedMetricsService.deleteRule(ruleId).subscribe({
      next: () => {
        this.rules = this.rules.filter((rule) => rule.id !== ruleId);
        this.loadScores();
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to delete rule', err);
        this.drawerError = 'Failed to delete rule';
      },
    });
  }

  private toNormalizePayload(value: string | null | undefined): string | null {
    if (!value || value === 'value') return null;
    return value;
  }

  private toDateString(date: Date | null): string | undefined {
    if (!date) return undefined;
    const year = date.getFullYear();
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const day = `${date.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  formatStatusDate(value: string | null | undefined): string {
    if (!value) return '—';
    return value;
  }
}
