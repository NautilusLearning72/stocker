import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatTabsModule } from '@angular/material/tabs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ConfigService, ConfigEntry, ConfigMetadata } from '../../../core/services/config.service';

interface ConfigField {
  key: string;
  value: string;
  originalValue: string;
  value_type: 'int' | 'float' | 'bool' | 'str';
  description: string;
  tooltip?: string;
  min?: number;
  max?: number;
  options?: string[];
  isDirty: boolean;
}

interface CategoryConfig {
  name: string;
  displayName: string;
  fields: ConfigField[];
}

@Component({
  selector: 'app-config',
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatTabsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatButtonModule,
    MatIconModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
  ],
  templateUrl: './config.html',
  styleUrl: './config.scss',
})
export class Config implements OnInit {
  categories: CategoryConfig[] = [];
  loading = true;
  saving = false;
  error: string | null = null;

  private metadataMap = new Map<string, ConfigMetadata>();

  constructor(
    private configService: ConfigService,
    private snackBar: MatSnackBar
  ) {}

  ngOnInit(): void {
    this.loadConfig();
  }

  private loadConfig(): void {
    this.loading = true;
    this.error = null;

    // Load metadata and config in parallel
    Promise.all([
      this.configService.getMetadata().toPromise(),
      this.configService.getAll().toPromise()
    ]).then(([metadata, configs]) => {
      // Build metadata lookup
      this.metadataMap.clear();
      for (const meta of metadata || []) {
        this.metadataMap.set(meta.key, meta);
      }

      // Group configs by category
      const categoryMap = new Map<string, ConfigField[]>();
      for (const config of configs || []) {
        const meta = this.metadataMap.get(config.key);
        const field: ConfigField = {
          key: config.key,
          value: config.value,
          originalValue: config.value,
          value_type: config.value_type,
          description: config.description || meta?.description || '',
          tooltip: meta?.tooltip,
          min: meta?.min,
          max: meta?.max,
          options: meta?.options,
          isDirty: false,
        };

        if (!categoryMap.has(config.category)) {
          categoryMap.set(config.category, []);
        }
        categoryMap.get(config.category)!.push(field);
      }

      // Convert to array with display names
      const categoryOrder = ['strategy', 'risk', 'confirmation', 'exit', 'diversification', 'sizing'];
      const displayNames: Record<string, string> = {
        strategy: 'Strategy',
        risk: 'Risk Limits',
        confirmation: 'Confirmation',
        exit: 'Exit Rules',
        diversification: 'Diversification',
        sizing: 'Sizing',
      };

      this.categories = categoryOrder
        .filter(cat => categoryMap.has(cat))
        .map(cat => ({
          name: cat,
          displayName: displayNames[cat] || cat,
          fields: categoryMap.get(cat)!.sort((a, b) => a.key.localeCompare(b.key)),
        }));

      this.loading = false;
    }).catch(err => {
      this.error = 'Failed to load configuration';
      this.loading = false;
      console.error('Config load error:', err);
    });
  }

  onFieldChange(field: ConfigField): void {
    field.isDirty = field.value !== field.originalValue;
  }

  getCategoryDirtyCount(category: CategoryConfig): number {
    return category.fields.filter(f => f.isDirty).length;
  }

  getTotalDirtyCount(): number {
    return this.categories.reduce((sum, cat) => sum + this.getCategoryDirtyCount(cat), 0);
  }

  saveCategory(category: CategoryConfig): void {
    const dirtyFields = category.fields.filter(f => f.isDirty);
    if (dirtyFields.length === 0) return;

    this.saving = true;
    const updates: Record<string, string> = {};
    for (const field of dirtyFields) {
      updates[field.key] = String(field.value);
    }

    this.configService.bulkUpdate(updates).subscribe({
      next: (results) => {
        // Update original values
        for (const result of results) {
          const field = category.fields.find(f => f.key === result.key);
          if (field) {
            field.originalValue = result.value;
            field.isDirty = false;
          }
        }
        this.saving = false;
        this.snackBar.open('Configuration saved. Restart required to apply changes.', 'Dismiss', {
          duration: 5000,
        });
      },
      error: (err) => {
        this.saving = false;
        const message = err.error?.detail || 'Failed to save configuration';
        this.snackBar.open(message, 'Dismiss', { duration: 5000 });
      },
    });
  }

  saveAll(): void {
    const allDirty: Record<string, string> = {};
    for (const category of this.categories) {
      for (const field of category.fields.filter(f => f.isDirty)) {
        allDirty[field.key] = String(field.value);
      }
    }

    if (Object.keys(allDirty).length === 0) return;

    this.saving = true;
    this.configService.bulkUpdate(allDirty).subscribe({
      next: (results) => {
        // Update all original values
        for (const result of results) {
          for (const category of this.categories) {
            const field = category.fields.find(f => f.key === result.key);
            if (field) {
              field.originalValue = result.value;
              field.isDirty = false;
              break;
            }
          }
        }
        this.saving = false;
        this.snackBar.open('Configuration saved. Restart required to apply changes.', 'Dismiss', {
          duration: 5000,
        });
      },
      error: (err) => {
        this.saving = false;
        const message = err.error?.detail || 'Failed to save configuration';
        this.snackBar.open(message, 'Dismiss', { duration: 5000 });
      },
    });
  }

  resetCategory(category: CategoryConfig): void {
    for (const field of category.fields) {
      field.value = field.originalValue;
      field.isDirty = false;
    }
  }

  resetAll(): void {
    for (const category of this.categories) {
      this.resetCategory(category);
    }
  }

  getBoolValue(field: ConfigField): boolean {
    return field.value.toLowerCase() === 'true';
  }

  setBoolValue(field: ConfigField, checked: boolean): void {
    field.value = checked ? 'true' : 'false';
    this.onFieldChange(field);
  }

  formatKey(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  }
}
