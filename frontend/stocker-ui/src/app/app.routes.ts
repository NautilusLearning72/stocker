import { Routes } from '@angular/router';
import { DashboardHome } from './features/dashboard/dashboard-home/dashboard-home';
import { SignalList } from './features/signals/signal-list/signal-list';
import { MetricsDashboard } from './features/metrics/metrics-dashboard/metrics-dashboard';
import { AdminPage } from './features/admin/admin-page/admin-page';
import { StrategyGuide } from './features/guide/strategy-guide/strategy-guide';
import { UniverseManager } from './features/universe/universe-manager';
import { SymbolDetailPage } from './features/symbol/symbol-detail/symbol-detail';
import { PerformanceDashboard } from './features/performance/performance-dashboard/performance-dashboard';

export const routes: Routes = [
    { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    { path: 'dashboard', component: DashboardHome },
    { path: 'signals', component: SignalList },
    { path: 'metrics', component: MetricsDashboard },
    { path: 'performance', component: PerformanceDashboard },
    { path: 'admin', component: AdminPage },
    { path: 'guide', component: StrategyGuide },
    { path: 'universes', component: UniverseManager },
    { path: 'symbol/:symbol', component: SymbolDetailPage },
];
