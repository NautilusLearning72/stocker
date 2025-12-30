import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { lastValueFrom } from 'rxjs';
import {
  MetricStatus,
  StrategyUniverse,
  Universe,
  UniverseDetail,
  UniverseService,
} from '../../../core/services/universe.service';
import { InstrumentInfo, InstrumentInfoService } from '../../../core/services/instrument-info.service';
import { UniverseNamePipe } from './universe-name.pipe';

@Component({
  selector: 'app-universe-manager',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    MatTableModule,
    MatTabsModule,
    UniverseNamePipe,
  ],
  templateUrl: './universe-manager.html',
  styleUrl: './universe-manager.scss',
})
export class UniverseManager implements OnInit {
  universes: Universe[] = [];
  selectedUniverseId?: number;
  selectedStrategyUniverseId?: number;
  strategyId = 'main_strategy';

  members: string[] = [];
  filteredMembers: string[] = [];
  selectedMembers = new Set<string>();
  memberFilter = '';
  addSymbolsInput = '';

  metrics: Record<string, MetricStatus> = {};
  instrumentNames: Record<string, string> = {};

  newUniverseName = '';
  newUniverseDescription = '';
  newUniverseSymbolsInput = '';

  loading = false;
  errorMsg = '';

  constructor(
    private universeService: UniverseService,
    private infoService: InstrumentInfoService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.loadUniverses();
    this.loadStrategyMapping();
  }

  loadUniverses(): void {
    this.loading = true;
    this.universeService.list().subscribe({
      next: (universes) => {
        this.universes = universes;
        if (this.selectedUniverseId === undefined && universes.length) {
          const preferred = universes.find((u) => u.is_global) ?? universes[0];
          this.selectedUniverseId = preferred.id;
        }
        Promise.resolve().then(() => {
          this.loading = false;
          this.cdr.detectChanges();
          this.loadUniverseDetail();
        });
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = 'Failed to load universes';
        console.error(err);
      },
    });
  }

  loadUniverseDetail(): void {
    if (this.selectedUniverseId === undefined || this.selectedUniverseId === null) return;
    this.loading = true;
    this.universeService.get(this.selectedUniverseId).subscribe({
      next: (detail: UniverseDetail) => {
        Promise.resolve().then(() => {
          this.members = detail.members || [];
          this.filteredMembers = [...this.members];
          this.selectedMembers.clear();
          this.memberFilter = '';
          this.loading = false;
          this.cdr.detectChanges();
          this.loadMetrics();
          this.loadNames(this.members);
        });
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = 'Failed to load universe details';
        console.error(err);
      },
    });
  }

  loadStrategyMapping(): void {
    this.universeService.getStrategyUniverse(this.strategyId).subscribe({
      next: (mapping: StrategyUniverse) => {
        Promise.resolve().then(() => {
          this.selectedStrategyUniverseId = mapping.universe_id ?? undefined;
          this.cdr.detectChanges();
        });
      },
      error: (err) => console.error('Failed to load strategy mapping', err),
    });
  }

  addMembers(): void {
    if (!this.selectedUniverseId) return;
    const symbols = this.parseSymbols(this.addSymbolsInput);
    if (!symbols.length) return;

    this.universeService.addMembers(this.selectedUniverseId, symbols).subscribe({
      next: () => {
        this.addSymbolsInput = '';
        this.loadUniverseDetail();
      },
      error: (err) => {
        this.errorMsg = 'Failed to add symbols';
        console.error(err);
      },
    });
  }

  removeMember(symbol: string): void {
    if (!this.selectedUniverseId) return;
    this.universeService.removeMember(this.selectedUniverseId, symbol).subscribe({
      next: () => {
        this.members = this.members.filter((s) => s !== symbol);
        this.onFilterChange();
        this.selectedMembers.delete(symbol);
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.errorMsg = `Failed to remove ${symbol}`;
        console.error(err);
      },
    });
  }

  async removeSelected(): Promise<void> {
    if (!this.selectedUniverseId || !this.selectedMembers.size) return;
    try {
      const removals = Array.from(this.selectedMembers).map((sym) =>
        lastValueFrom(this.universeService.removeMember(this.selectedUniverseId!, sym)),
      );
      await Promise.all(removals);
      this.selectedMembers.clear();
      this.loadUniverseDetail();
    } catch (err) {
      this.errorMsg = 'Failed to remove selected symbols';
      console.error(err);
    }
  }

  createUniverse(): void {
    const name = this.newUniverseName.trim();
    if (!name) return;
    const description = this.newUniverseDescription.trim();
    const symbols = this.parseSymbols(this.newUniverseSymbolsInput);

    this.universeService
      .create({ name, description: description || undefined })
      .subscribe({
        next: async (u: Universe) => {
          if (symbols.length) {
            try {
              await lastValueFrom(this.universeService.addMembers(u.id, symbols));
            } catch (err) {
              console.error('Failed to add initial symbols', err);
            }
          }
          this.newUniverseName = '';
          this.newUniverseDescription = '';
          this.newUniverseSymbolsInput = '';
          this.universes.push(u);
          this.selectedUniverseId = u.id;
          this.selectedStrategyUniverseId = this.selectedStrategyUniverseId ?? u.id;
          this.loadUniverseDetail();
          this.cdr.detectChanges();
        },
        error: (err) => {
          this.errorMsg = 'Failed to create universe';
          console.error(err);
        },
      });
  }

  assignStrategy(): void {
    if (!this.selectedStrategyUniverseId) return;
    this.universeService.setStrategyUniverse(this.strategyId, this.selectedStrategyUniverseId).subscribe({
      next: () => {},
      error: (err) => {
        this.errorMsg = 'Failed to assign strategy universe';
        console.error(err);
      },
    });
  }

  onFilterChange(): void {
    const term = this.memberFilter.trim().toLowerCase();
    if (!term) {
      this.filteredMembers = [...this.members];
    } else {
      this.filteredMembers = this.members.filter((sym) => {
        const name = this.instrumentNames[sym]?.toLowerCase() || '';
        return sym.toLowerCase().includes(term) || name.includes(term);
      });
    }
    this.cdr.detectChanges();
  }

  toggleSelection(symbol: string, checked: boolean): void {
    if (checked) {
      this.selectedMembers.add(symbol);
    } else {
      this.selectedMembers.delete(symbol);
    }
  }

  private parseSymbols(input: string): string[] {
    return input
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter((s) => !!s);
  }

  private loadMetrics(): void {
    if (!this.selectedUniverseId) return;
    this.universeService.getMetricsStatus(this.selectedUniverseId).subscribe({
      next: (rows: MetricStatus[]) => {
        const map: Record<string, MetricStatus> = {};
        rows.forEach((m) => (map[m.symbol] = m));
        Promise.resolve().then(() => {
          this.metrics = map;
          this.cdr.detectChanges();
        });
      },
      error: (err) => console.error('Failed to load metrics status', err),
    });
  }

  private loadNames(symbols: string[]): void {
    if (!symbols.length) return;
    this.infoService.getInfo(symbols).subscribe({
      next: (rows: InstrumentInfo[]) => {
        const map: Record<string, string> = {};
        rows.forEach((info) => (map[info.symbol] = info.name || info.symbol));
        Promise.resolve().then(() => {
          this.instrumentNames = map;
          this.onFilterChange();
          this.cdr.detectChanges();
        });
      },
      error: (err) => console.error('Failed to load instrument names', err),
    });
  }
}
