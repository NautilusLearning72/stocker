import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { DecisionEvent } from '../../../../../core/services/audit.service';

@Component({
  selector: 'app-audit-timeline',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule],
  template: `
    <div class="timeline">
      <div
        *ngFor="let event of events; let last = last"
        class="timeline-item"
        [class.last]="last">
        <div class="timeline-marker" [ngClass]="getStageClass(event.stage)">
          <mat-icon>{{ getStageIcon(event.stage) }}</mat-icon>
        </div>
        <div class="timeline-connector" *ngIf="!last"></div>
        <div class="timeline-content">
          <div class="timeline-header">
            <span class="time">{{ formatTime(event.timestamp) }}</span>
            <span class="stage-badge" [ngClass]="getStageClass(event.stage)">
              {{ event.stage }}
            </span>
          </div>
          <div class="timeline-body">
            <span class="event-type">{{ formatEventType(event.event_type) }}</span>
            <p class="description">{{ event.description }}</p>
            <div
              class="metadata"
              *ngIf="hasMetadata(event)"
              [matTooltip]="getMetadataTooltip(event.metadata)">
              <mat-icon class="meta-icon">info_outline</mat-icon>
              <span>{{ getMetadataPreview(event.metadata) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div *ngIf="!events || events.length === 0" class="empty-timeline">
        <mat-icon>timeline</mat-icon>
        <span>No timeline events</span>
      </div>
    </div>
  `,
  styles: [`
    .timeline {
      position: relative;
      padding: 16px 0;
    }

    .timeline-item {
      display: flex;
      position: relative;
      padding-bottom: 24px;

      &.last {
        padding-bottom: 0;
      }
    }

    .timeline-marker {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      z-index: 1;

      mat-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
        color: white;
      }

      &.signal {
        background: var(--color-accent);
      }
      &.target {
        background: var(--color-accent);
      }
      &.order, &.sizing {
        background: var(--color-warning);
      }
      &.execution {
        background: var(--color-success);
      }
      &.risk {
        background: var(--color-danger);
      }
      &.diversification {
        background: var(--color-muted);
      }
    }

    .timeline-connector {
      position: absolute;
      left: 17px;
      top: 36px;
      bottom: 0;
      width: 2px;
      background: var(--color-border);
    }

    .timeline-content {
      margin-left: 16px;
      flex: 1;
    }

    .timeline-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
    }

    .time {
      font-size: 12px;
      color: var(--color-muted);
      font-family: var(--font-mono);
    }

    .stage-badge {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 12px;
      text-transform: uppercase;
      font-weight: 600;
      color: white;

      &.signal { background: var(--color-accent); }
      &.target { background: var(--color-accent); }
      &.order, &.sizing { background: var(--color-warning); }
      &.execution { background: var(--color-success); }
      &.risk { background: var(--color-danger); }
      &.diversification { background: var(--color-muted); }
    }

    .timeline-body {
      background: var(--color-canvas-subtle);
      border: 1px solid var(--color-border);
      border-radius: 8px;
      padding: 12px;
    }

    .event-type {
      font-weight: 600;
      color: var(--color-text);
      display: block;
      margin-bottom: 4px;
    }

    .description {
      margin: 0;
      color: var(--color-muted);
      font-size: 14px;
      line-height: 1.4;
    }

    .metadata {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 8px;
      font-size: 12px;
      color: var(--color-muted);
      cursor: pointer;

      .meta-icon {
        font-size: 14px;
        width: 14px;
        height: 14px;
      }
    }

    .empty-timeline {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 32px;
      color: var(--color-muted);

      mat-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
        margin-bottom: 8px;
      }
    }
  `],
})
export class AuditTimeline {
  @Input() events: DecisionEvent[] = [];

  getStageIcon(stage: string): string {
    const icons: Record<string, string> = {
      signal: 'trending_up',
      target: 'track_changes',
      order: 'shopping_cart',
      sizing: 'straighten',
      execution: 'check_circle',
      risk: 'warning',
      diversification: 'pie_chart',
    };
    return icons[stage] || 'circle';
  }

  getStageClass(stage: string): string {
    return stage;
  }

  formatTime(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  formatEventType(eventType: string): string {
    return eventType
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  hasMetadata(event: DecisionEvent): boolean {
    return event.metadata && Object.keys(event.metadata).length > 0;
  }

  getMetadataPreview(metadata: Record<string, any>): string {
    const keys = Object.keys(metadata).slice(0, 2);
    return keys
      .map((k) => {
        const v = metadata[k];
        if (typeof v === 'number') {
          return `${k}: ${v.toFixed(4)}`;
        }
        return `${k}: ${v}`;
      })
      .join(', ');
  }

  getMetadataTooltip(metadata: Record<string, any>): string {
    return JSON.stringify(metadata, null, 2);
  }
}
