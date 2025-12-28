import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';

interface ServiceStatus {
  name: string;
  status: 'healthy' | 'warning' | 'error';
  lastHeartbeat: string;
  message?: string;
}

@Component({
  selector: 'app-system-health',
  imports: [CommonModule, MatCardModule, MatListModule, MatIconModule],
  templateUrl: './system-health.html',
  styleUrl: './system-health.scss',
})
export class SystemHealth {
  services: ServiceStatus[] = [
    { name: 'Redis Streams', status: 'healthy', lastHeartbeat: 'Just now' },
    { name: 'PostgreSQL', status: 'healthy', lastHeartbeat: 'Just now' },
    { name: 'Signal Consumer', status: 'healthy', lastHeartbeat: '5s ago' },
    { name: 'Portfolio Consumer', status: 'healthy', lastHeartbeat: '5s ago' },
    { name: 'Order Consumer', status: 'warning', lastHeartbeat: '2m ago', message: 'High latency detected' },
    { name: 'Broker Consumer', status: 'healthy', lastHeartbeat: '5s ago' },
  ];
}
