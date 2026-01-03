import { ChangeDetectorRef, Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { Subscription } from 'rxjs';
import { SystemHealthService, ServiceStatus } from '../../../core/services/system-health.service';
import { PortfolioSyncService, PortfolioSyncResult } from '../../../core/services/portfolio-sync.service';
import { MatButtonModule } from '@angular/material/button';
import { KillSwitchService, KillSwitchStatus } from '../../../core/services/kill-switch.service';
import { StreamService } from '../../../core/services/stream';

@Component({
  selector: 'app-system-health',
  imports: [CommonModule, MatCardModule, MatListModule, MatIconModule, MatButtonModule],
  templateUrl: './system-health.html',
  styleUrl: './system-health.scss',
})
export class SystemHealth implements OnInit, OnDestroy {
  services: ServiceStatus[] = [];
  loading = true;
  errorMsg = '';
  syncMessage = '';
  syncError = '';
  syncing = false;
  killSwitchActive = false;
  killSwitchReason = '';
  killSwitchSource: 'auto' | 'manual' | null = null;
  killSwitchTriggeredAt: string | null = null;
  killSwitchStatusText = 'Inactive';
  killSwitchMessage = '';
  killSwitchError = '';
  killSwitchBusy = false;
  private streamSub?: Subscription;

  constructor(
    private healthService: SystemHealthService,
    private portfolioSyncService: PortfolioSyncService,
    private killSwitchService: KillSwitchService,
    private streamService: StreamService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadHealth();
    this.loadKillSwitchStatus();
    this.subscribeToKillSwitchUpdates();
  }

  loadHealth(): void {
    this.loading = true;
    this.errorMsg = '';
    this.healthService.getHealth().subscribe({
      next: (services) => {
        Promise.resolve().then(() => {
          this.services = services.map((service) => ({
            ...service,
            message: service.message || undefined,
          }));
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.services = this.buildErrorServices();
          this.errorMsg = 'Backend unavailable. Start the API to see live system health.';
          this.loading = false;
          this.cdr.detectChanges();
        });
      },
    });
  }

  ngOnDestroy(): void {
    this.streamSub?.unsubscribe();
  }

  private buildErrorServices(): ServiceStatus[] {
    return [
      { name: 'API', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Redis Streams', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'PostgreSQL', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Signal Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Exit Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Portfolio Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Order Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Broker Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Ledger Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Performance Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Monitor Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
    ];
  }

  syncPortfolio(): void {
    this.syncing = true;
    this.syncError = '';
    this.syncMessage = 'Syncing portfolio...';
    this.portfolioSyncService.sync().subscribe({
      next: (result) => {
        Promise.resolve().then(() => {
          this.applySyncResult(result);
          this.syncing = false;
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.syncing = false;
          this.syncMessage = '';
          this.syncError = 'Portfolio sync failed. Check the backend logs.';
          this.cdr.detectChanges();
        });
      },
    });
  }

  private applySyncResult(result: PortfolioSyncResult): void {
    const parts = [
      `${result.holdings_refreshed} holdings`,
      `${result.orders_created} new orders`,
      `${result.orders_updated} updated`,
      `${result.fills_created} fills`,
    ];
    this.syncMessage = `Sync complete: ${parts.join(', ')}.`;
  }

  loadKillSwitchStatus(): void {
    this.killSwitchError = '';
    this.killSwitchService.status().subscribe({
      next: (status) => {
        Promise.resolve().then(() => {
          this.applyKillSwitchStatus(status);
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.killSwitchError = 'Kill switch status unavailable. Check the backend.';
          this.cdr.detectChanges();
        });
      },
    });
  }

  activateKillSwitch(): void {
    if (this.killSwitchBusy || this.killSwitchActive) {
      return;
    }
    this.killSwitchBusy = true;
    this.killSwitchError = '';
    this.killSwitchMessage = 'Activating kill switch...';
    this.killSwitchService.activate('main', 'Manual halt requested via UI').subscribe({
      next: (status) => {
        Promise.resolve().then(() => {
          this.applyKillSwitchStatus(status);
          this.killSwitchBusy = false;
          this.killSwitchMessage = 'Kill switch active. Trading halted.';
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.killSwitchBusy = false;
          this.killSwitchMessage = '';
          this.killSwitchError = 'Kill switch activation failed. Check backend logs.';
          this.cdr.detectChanges();
        });
      },
    });
  }

  resetKillSwitch(): void {
    if (this.killSwitchBusy || !this.killSwitchActive) {
      return;
    }
    this.killSwitchBusy = true;
    this.killSwitchError = '';
    this.killSwitchMessage = 'Resetting kill switch...';
    this.killSwitchService.reset().subscribe({
      next: (status) => {
        Promise.resolve().then(() => {
          this.applyKillSwitchStatus(status);
          this.killSwitchBusy = false;
          this.killSwitchMessage = 'Kill switch reset. Trading resumed.';
          this.cdr.detectChanges();
        });
      },
      error: () => {
        Promise.resolve().then(() => {
          this.killSwitchBusy = false;
          this.killSwitchMessage = '';
          this.killSwitchError = 'Kill switch reset failed. Check backend logs.';
          this.cdr.detectChanges();
        });
      },
    });
  }

  private subscribeToKillSwitchUpdates(): void {
    this.streamSub = this.streamService.events$.subscribe((msg) => {
      if (msg.event !== 'update') {
        return;
      }
      if (msg.data?.type === 'kill_switch_update') {
        this.applyKillSwitchStreamUpdate(msg.data.payload);
        return;
      }
      if (msg.data?.type === 'portfolio_update') {
        this.applyKillSwitchStreamUpdate(msg.data.payload);
      }
    });
  }

  private applyKillSwitchStatus(status: KillSwitchStatus): void {
    this.killSwitchActive = status.active;
    this.killSwitchReason = status.reason || '';
    this.killSwitchSource = status.source ?? null;
    this.killSwitchTriggeredAt = status.triggered_at ?? null;
    this.killSwitchStatusText = this.formatKillSwitchStatus();
  }

  private applyKillSwitchStreamUpdate(payload: any): void {
    if (!payload || typeof payload.kill_switch_active !== 'boolean') {
      return;
    }
    this.killSwitchActive = payload.kill_switch_active;
    this.killSwitchReason = payload.kill_switch_reason || '';
    this.killSwitchSource = payload.kill_switch_source ?? null;
    this.killSwitchTriggeredAt = payload.triggered_at ?? this.killSwitchTriggeredAt;
    this.killSwitchStatusText = this.formatKillSwitchStatus();
    this.cdr.detectChanges();
  }

  private formatKillSwitchStatus(): string {
    if (!this.killSwitchActive) {
      return 'Inactive';
    }
    const source =
      this.killSwitchSource === 'auto'
        ? 'Auto'
        : this.killSwitchSource === 'manual'
          ? 'Manual'
          : 'Unknown';
    return `Active (${source})`;
  }
}
