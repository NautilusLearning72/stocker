import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatIconModule } from '@angular/material/icon';
import { METRIC_DEFINITIONS } from './metric-definitions';

@Component({
  selector: 'app-metric-tooltip',
  standalone: true,
  imports: [CommonModule, MatTooltipModule, MatIconModule],
  template: `
    <span class="metric-with-tooltip">
      <span class="metric-label">{{ getLabel() }}</span>
      <mat-icon
        class="info-icon"
        [matTooltip]="getTooltipText()"
        matTooltipClass="metric-tooltip"
        matTooltipPosition="above"
      >
        help_outline
      </mat-icon>
    </span>
  `,
  styles: [
    `
      .metric-with-tooltip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .metric-label {
        color: var(--color-muted);
        font-size: 0.8125rem;
      }
      .info-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
        color: var(--color-muted);
        cursor: help;
      }
      .info-icon:hover {
        color: var(--color-accent);
      }
    `,
  ],
})
export class MetricTooltip {
  @Input({ required: true }) metric!: string;

  getLabel(): string {
    return METRIC_DEFINITIONS[this.metric]?.label || this.formatKey(this.metric);
  }

  getTooltipText(): string {
    const def = METRIC_DEFINITIONS[this.metric];
    if (!def) return this.metric;
    let text = def.explanation;
    if (def.goodRange) {
      text += ` Typical range: ${def.goodRange}`;
    }
    return text;
  }

  private formatKey(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }
}
