import { Component, Input, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';

import {
  SymbolDetailService,
  SentimentData,
} from '../../../../../core/services/symbol-detail.service';
import { MetricTooltip } from '../../../../../shared/components/metric-tooltip/metric-tooltip';

@Component({
  selector: 'app-sentiment-tab',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatButtonToggleModule,
    MatIconModule,
    DecimalPipe,
    MetricTooltip,
  ],
  templateUrl: './sentiment-tab.html',
  styleUrl: './sentiment-tab.scss',
})
export class SentimentTab implements OnInit, OnChanges {
  @Input() symbol!: string;

  sentimentData: SentimentData[] = [];
  loading = false;
  selectedDays = 30;

  dayOptions = [
    { value: 7, label: '1W' },
    { value: 30, label: '1M' },
    { value: 90, label: '3M' },
  ];

  // Computed stats
  latestSentiment: SentimentData | null = null;
  averageSentiment: number | null = null;
  totalArticles: number | null = null;

  constructor(private symbolService: SymbolDetailService) {}

  ngOnInit(): void {
    this.loadSentiment();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['symbol'] && !changes['symbol'].firstChange) {
      this.loadSentiment();
    }
  }

  loadSentiment(): void {
    this.loading = true;
    this.symbolService.getSentiment(this.symbol, this.selectedDays).subscribe({
      next: (data) => {
        this.sentimentData = data;
        this.computeStats();
        this.loading = false;
      },
      error: (err) => {
        console.error('Failed to load sentiment:', err);
        this.sentimentData = [];
        this.loading = false;
      },
    });
  }

  onDaysChange(): void {
    this.loadSentiment();
  }

  private computeStats(): void {
    if (this.sentimentData.length === 0) {
      this.latestSentiment = null;
      this.averageSentiment = null;
      this.totalArticles = null;
      return;
    }

    this.latestSentiment = this.sentimentData[this.sentimentData.length - 1];

    const sum = this.sentimentData.reduce((acc, d) => acc + d.sentiment_score, 0);
    this.averageSentiment = sum / this.sentimentData.length;

    this.totalArticles = this.sentimentData.reduce(
      (acc, d) => acc + (d.article_count || 0),
      0
    );
  }

  getSentimentLabel(score: number): string {
    if (score >= 0.3) return 'Very Positive';
    if (score >= 0.1) return 'Positive';
    if (score >= -0.1) return 'Neutral';
    if (score >= -0.3) return 'Negative';
    return 'Very Negative';
  }

  getSentimentClass(score: number): string {
    if (score >= 0.3) return 'very-positive';
    if (score >= 0.1) return 'positive';
    if (score >= -0.1) return 'neutral';
    if (score >= -0.3) return 'negative';
    return 'very-negative';
  }

  getSentimentIcon(score: number): string {
    if (score >= 0.3) return 'sentiment_very_satisfied';
    if (score >= 0.1) return 'sentiment_satisfied';
    if (score >= -0.1) return 'sentiment_neutral';
    if (score >= -0.3) return 'sentiment_dissatisfied';
    return 'sentiment_very_dissatisfied';
  }
}
