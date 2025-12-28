import { Routes } from '@angular/router';
import { DashboardHome } from './features/dashboard/dashboard-home/dashboard-home';
import { SignalList } from './features/signals/signal-list/signal-list';
import { SystemHealth } from './features/admin/system-health/system-health';

export const routes: Routes = [
    { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    { path: 'dashboard', component: DashboardHome },
    { path: 'signals', component: SignalList },
    { path: 'admin', component: SystemHealth },
];
