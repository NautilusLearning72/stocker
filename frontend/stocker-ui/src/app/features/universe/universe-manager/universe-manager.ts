import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';

import { InstrumentInfoService, InstrumentInfo } from '../../../core/services/instrument-info.service';
import {
  MetricStatus,
  StrategyUniverse,
  Universe,
  UniverseDetail,
  UniverseService,
} from '../../../core/services/universe.service';

@Component({
  selector: 'app-universe-manager',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatChipsModule,
    MatIconModule,
    MatSelectModule,
    MatTableModule,
  ],
  templateUrl: './universe-manager.html',
  styleUrl: './universe-manager.scss',
})
export class UniverseManager implements OnInit {
  universes: Universe[] = [];
  selectedUniverseId?: number;
  selectedStrategyUniverseId?: number | null;
  strategyId = 'main_strategy';
  members: string[] = [];
  metrics: Record<string, MetricStatus> = {};
  instrumentNames: Record<string, string> = {};

  addSymbolsInput = '';
  newUniverseName = '';
  newUniverseDescription = '';
  newUniverseSymbolsInput = '';

  loading = false;
  errorMsg = '';

  constructor(
    private universeService: UniverseService,
    private infoService: InstrumentInfoService,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadUniverses();
    this.loadStrategyMapping();
  }

  loadUniverses(): void {
    this.universeService.list().subscribe({
      next: (data) => {
        this.universes = data;
        if (!this.selectedUniverseId && this.universes.length > 0) {
          const global = this.universes.find((u) => u.is_global);
          this.selectedUniverseId = global?.id ?? this.universes[0].id;
          this.selectedStrategyUniverseId = this.selectedUniverseId;
          this.loadUniverseDetail();
        }
      },
      error: (err) => {
        this.errorMsg = 'Failed to load universes';
        console.error(err);
      },
    });
  }

  loadUniverseDetail(): void {
    if (!this.selectedUniverseId) return;
    this.loading = true;
    this.universeService.get(this.selectedUniverseId).subscribe({
      next: (detail: UniverseDetail) => {
        // Defer to next tick to avoid ExpressionChanged errors
        Promise.resolve().then(() => {
          this.members = [...detail.members];
          this.loading = false;
          this.loadMetrics(this.members);
          this.loadNames(this.members);
          this.cdr.detectChanges();
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
        this.selectedStrategyUniverseId = mapping.universe_id;
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
        this.cdr.detectChanges();
        this.loadUniverseDetail();
      },
      error: (err) => {
        this.errorMsg = 'Failed to add members';
        console.error(err);
      },
    });
  }

  removeMember(symbol: string): void {
    if (!this.selectedUniverseId) return;
    this.universeService.removeMember(this.selectedUniverseId, symbol).subscribe({
      next: () => this.loadUniverseDetail(),
      error: (err) => {
        this.errorMsg = 'Failed to remove member';
        console.error(err);
      },
    });
  }

  createUniverse(): void {
    if (!this.newUniverseName.trim()) return;
    this.universeService
      .create({
        name: this.newUniverseName.trim(),
        description: this.newUniverseDescription || undefined,
        is_global: false,
      })
      .subscribe({
        next: (universe) => {
          const symbols = this.parseSymbols(this.newUniverseSymbolsInput);
          if (symbols.length) {
            this.universeService.addMembers(universe.id, symbols).subscribe({
              next: () => this.afterUniverseCreated(universe.id),
              error: (err) => {
                this.errorMsg = 'Failed to add members to new universe';
                console.error(err);
                this.afterUniverseCreated(universe.id);
              },
            });
          } else {
            this.afterUniverseCreated(universe.id);
          }
        },
        error: (err) => {
          this.errorMsg = 'Failed to create universe';
          console.error(err);
        },
      });
  }

  afterUniverseCreated(universeId: number): void {
    this.newUniverseName = '';
    this.newUniverseDescription = '';
    this.newUniverseSymbolsInput = '';
    this.selectedUniverseId = universeId;
    this.loadUniverses();
    this.loadUniverseDetail();
  }

  assignStrategy(): void {
    if (!this.selectedStrategyUniverseId) return;
    this.universeService
      .setStrategyUniverse(this.strategyId, this.selectedStrategyUniverseId)
      .subscribe({
        next: () => {
          // no-op; mapping stored
        },
        error: (err) => {
          this.errorMsg = 'Failed to assign strategy universe';
          console.error(err);
        },
      });
  }

  parseSymbols(value: string): string[] {
    if (!value) return [];
    return value
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter((s) => !!s);
  }

  loadMetrics(symbols: string[]): void {
    if (!symbols.length || !this.selectedUniverseId) {
      this.metrics = {};
      return;
    }
    this.universeService.getMetricsStatus(this.selectedUniverseId, symbols).subscribe({
      next: (rows) => {
        const map: Record<string, MetricStatus> = {};
        rows.forEach((m) => (map[m.symbol] = m));
        this.metrics = map;
      },
      error: (err) => {
        console.error('Failed to load metrics status', err);
      },
    });
  }

  loadNames(symbols: string[]): void {
    if (!symbols.length) {
      this.instrumentNames = {};
      return;
    }
    this.infoService.getInfo(symbols).subscribe({
      next: (rows) => {
        const map: Record<string, string> = {};
        rows.forEach((info) => {
          if (info.symbol) {
            map[info.symbol] = info.name || info.symbol;
          }
        });
        this.instrumentNames = map;
        this.cdr.detectChanges();
      },
      error: (err) => console.error('Failed to load instrument names', err),
    });
  }
}
