import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTabsModule } from '@angular/material/tabs';
import { MatIconModule } from '@angular/material/icon';

import { SystemHealth } from '../system-health/system-health';
import { Config } from '../config/config';
import { OrderAudit } from '../order-audit/order-audit';

@Component({
  selector: 'app-admin-page',
  imports: [
    CommonModule,
    MatTabsModule,
    MatIconModule,
    SystemHealth,
    Config,
    OrderAudit,
  ],
  templateUrl: './admin-page.html',
  styleUrl: './admin-page.scss',
})
export class AdminPage {}
