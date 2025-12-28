import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';

interface ParameterRow {
  parameter: string;
  default: string;
  description: string;
}

@Component({
  selector: 'app-strategy-guide',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatExpansionModule,
    MatTableModule,
    MatIconModule,
    MatDividerModule
  ],
  templateUrl: './strategy-guide.html',
  styleUrl: './strategy-guide.scss'
})
export class StrategyGuide {
  displayedColumns: string[] = ['parameter', 'default', 'description'];

  parameters: ParameterRow[] = [
    { parameter: 'Lookback Period', default: '126 days', description: 'Trend signal calculation window (~6 months)' },
    { parameter: 'EWMA Lambda', default: '0.94', description: 'Volatility smoothing factor (RiskMetrics standard)' },
    { parameter: 'Target Volatility', default: '10%', description: 'Annualized portfolio volatility target' },
    { parameter: 'Single Instrument Cap', default: '35%', description: 'Maximum exposure per instrument' },
    { parameter: 'Gross Exposure Cap', default: '150%', description: 'Maximum total leverage (ETFs)' },
    { parameter: 'Drawdown Threshold', default: '10%', description: 'Circuit breaker trigger level' },
    { parameter: 'Drawdown Scale', default: '50%', description: 'Position reduction when circuit breaker active' },
    { parameter: 'Kill Switch', default: '-3% daily', description: 'Maximum acceptable daily loss' }
  ];
}
