import { Component, Input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-portfolio-summary',
  standalone: true,
  imports: [MatCardModule, CommonModule],
  templateUrl: './portfolio-summary.html',
  styleUrl: './portfolio-summary.scss',
})
export class PortfolioSummary {
  @Input() metrics: any[] = [];
}
