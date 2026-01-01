import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { SystemHealthService, ServiceStatus } from '../../../core/services/system-health.service';
import { PortfolioSyncService, PortfolioSyncResult } from '../../../core/services/portfolio-sync.service';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-system-health',
  imports: [CommonModule, MatCardModule, MatListModule, MatIconModule, MatButtonModule],
  templateUrl: './system-health.html',
  styleUrl: './system-health.scss',
})
export class SystemHealth implements OnInit {
  services: ServiceStatus[] = [];
  loading = true;
  errorMsg = '';
  syncMessage = '';
  syncError = '';
  syncing = false;

  constructor(
    private healthService: SystemHealthService,
    private portfolioSyncService: PortfolioSyncService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadHealth();
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

  private buildErrorServices(): ServiceStatus[] {
    return [
      { name: 'API', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Redis Streams', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'PostgreSQL', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Signal Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Portfolio Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Order Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Broker Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
      { name: 'Ledger Consumer', status: 'error', last_heartbeat: 'Unavailable', message: 'Backend offline' },
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
}
