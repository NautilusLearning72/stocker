import { Component, Input } from '@angular/core';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-symbol-link',
  standalone: true,
  imports: [RouterModule],
  template: `
    <a [routerLink]="['/symbol', symbol]" class="symbol-link">
      {{ symbol }}
    </a>
  `,
  styles: [
    `
      .symbol-link {
        color: #1976d2;
        text-decoration: none;
        font-weight: 500;
        font-family: monospace;
      }
      .symbol-link:hover {
        text-decoration: underline;
      }
    `,
  ],
})
export class SymbolLink {
  @Input({ required: true }) symbol!: string;
}
