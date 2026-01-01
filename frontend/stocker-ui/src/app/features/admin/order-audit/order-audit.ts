import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSortModule } from '@angular/material/sort';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatBadgeModule } from '@angular/material/badge';

import {
  AuditService,
  OrderAuditRecord,
  AuditSummary,
  AuditFilters,
} from '../../../core/services/audit.service';
import { AuditTimeline } from './components/timeline/timeline';
import { SymbolLink } from '../../../shared/components/symbol-link/symbol-link';

@Component({
  selector: 'app-order-audit',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSidenavModule,
    MatCardModule,
    MatDividerModule,
    MatTooltipModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatButtonToggleModule,
    MatBadgeModule,
    AuditTimeline,
    SymbolLink,
  ],
  templateUrl: './order-audit.html',
  styleUrl: './order-audit.scss',
})
export class OrderAudit implements OnInit {
  // Data
  records: OrderAuditRecord[] = [];
  selectedRecord: OrderAuditRecord | null = null;
  summary: AuditSummary | null = null;
  loading = false;
  drawerOpen = false;

  // Pagination
  totalRecords = 0;
  pageSize = 25;
  pageIndex = 0;

  // Filters
  filters: AuditFilters = {
    portfolio_id: 'main',
    limit: 25,
    offset: 0,
  };
  dateFrom: Date | null = null;
  dateTo: Date | null = null;
  symbolFilter = '';
  statusFilter = '';
  sideFilter = '';
  hasDiscrepancyFilter: boolean | null = null;

  // Filter options
  statusOptions = ['', 'NEW', 'PENDING_EXECUTION', 'FILLED', 'FAILED'];
  sideOptions = ['', 'BUY', 'SELL'];

  // Table columns
  displayedColumns = ['date', 'symbol', 'side', 'qty', 'status', 'fillRate', 'discrepancies', 'actions'];

  constructor(
    private auditService: AuditService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    // Default to last 30 days
    const today = new Date();
    const oneMonthAgo = new Date();
    oneMonthAgo.setDate(today.getDate() - 30);

    this.dateTo = today;
    this.dateFrom = oneMonthAgo;

    this.loadData();
    this.loadSummary();
  }

  loadData(): void {
    this.loading = true;
    this.buildFilters();

    this.auditService.getAuditOrders(this.filters).subscribe({
      next: (response) => {
        this.records = response.items;
        this.totalRecords = response.total;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load audit records:', err);
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  loadSummary(): void {
    const dateFrom = this.dateFrom ? this.formatDate(this.dateFrom) : undefined;
    const dateTo = this.dateTo ? this.formatDate(this.dateTo) : undefined;

    this.auditService.getSummary('main', dateFrom, dateTo).subscribe({
      next: (summary) => {
        this.summary = summary;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load summary:', err);
      },
    });
  }

  buildFilters(): void {
    this.filters = {
      portfolio_id: 'main',
      date_from: this.dateFrom ? this.formatDate(this.dateFrom) : undefined,
      date_to: this.dateTo ? this.formatDate(this.dateTo) : undefined,
      symbol: this.symbolFilter || undefined,
      status: this.statusFilter || undefined,
      side: this.sideFilter || undefined,
      has_discrepancy: this.hasDiscrepancyFilter,
      limit: this.pageSize,
      offset: this.pageIndex * this.pageSize,
    };
  }

  applyFilters(): void {
    this.pageIndex = 0;
    this.loadData();
    this.loadSummary();
  }

  clearFilters(): void {
    this.dateFrom = null;
    this.dateTo = null;
    this.symbolFilter = '';
    this.statusFilter = '';
    this.sideFilter = '';
    this.hasDiscrepancyFilter = null;
    this.pageIndex = 0;
    this.applyFilters();
  }

  onPageChange(event: PageEvent): void {
    this.pageSize = event.pageSize;
    this.pageIndex = event.pageIndex;
    this.loadData();
  }

  viewDetails(record: OrderAuditRecord): void {
    this.selectedRecord = record;
    this.drawerOpen = true;
  }

  closeDrawer(): void {
    this.drawerOpen = false;
    this.selectedRecord = null;
  }

  // Formatting helpers
  formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }

  formatDateTime(dateStr: string | null | undefined): string {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  formatShortDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  formatPercent(value: number): string {
    return (value * 100).toFixed(1) + '%';
  }

  formatPrice(value: number | null | undefined): string {
    if (value == null) return '-';
    return '$' + value.toFixed(2);
  }

  formatQty(value: number): string {
    if (value >= 1) {
      return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    return value.toFixed(4);
  }

  // Status helpers
  getStatusClass(status: string | null | undefined): string {
    if (!status) return '';
    const s = status.toLowerCase();
    if (s === 'filled') return 'status-filled';
    if (s === 'failed') return 'status-failed';
    if (s.includes('pending') || s === 'new') return 'status-pending';
    return '';
  }

  getSideClass(side: string | null | undefined): string {
    if (!side) return '';
    return side.toUpperCase() === 'BUY' ? 'side-buy' : 'side-sell';
  }

  getDiscrepancyCount(record: OrderAuditRecord): number {
    return record.discrepancies.length;
  }

  getDiscrepancySeverity(record: OrderAuditRecord): string {
    if (record.discrepancies.some((d) => d.severity === 'error')) return 'error';
    if (record.discrepancies.some((d) => d.severity === 'warning')) return 'warning';
    return 'info';
  }

  hasFilters(): boolean {
    return !!(
      this.dateFrom ||
      this.dateTo ||
      this.symbolFilter ||
      this.statusFilter ||
      this.sideFilter ||
      this.hasDiscrepancyFilter !== null
    );
  }
}
