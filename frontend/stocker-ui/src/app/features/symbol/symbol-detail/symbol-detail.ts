import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { MatTabsModule } from '@angular/material/tabs';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { Subscription } from 'rxjs';

import {
  SymbolDetailService,
  SymbolDetail,
} from '../../../core/services/symbol-detail.service';
import { OverviewTab } from './tabs/overview-tab/overview-tab';
import { FundamentalsTab } from './tabs/fundamentals-tab/fundamentals-tab';
import { SentimentTab } from './tabs/sentiment-tab/sentiment-tab';
import { ActivityTab } from './tabs/activity-tab/activity-tab';

@Component({
  selector: 'app-symbol-detail',
  standalone: true,
  imports: [
    CommonModule,
    MatTabsModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatChipsModule,
    OverviewTab,
    FundamentalsTab,
    SentimentTab,
    ActivityTab,
  ],
  templateUrl: './symbol-detail.html',
  styleUrl: './symbol-detail.scss',
})
export class SymbolDetailPage implements OnInit, OnDestroy {
  symbol = '';
  detail: SymbolDetail | null = null;
  loading = false;
  error = '';

  private routeSub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private symbolService: SymbolDetailService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.routeSub = this.route.params.subscribe((params) => {
      this.symbol = params['symbol'];
      this.loadDetail();
    });
  }

  loadDetail(): void {
    this.loading = true;
    this.error = '';
    this.detail = null;

    this.symbolService.getDetail(this.symbol).subscribe({
      next: (detail) => {
        this.detail = detail;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to load symbol detail:', err);
        this.error = `Symbol "${this.symbol}" not found`;
        this.loading = false;
        this.cdr.detectChanges();
      },
    });
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();
  }
}
