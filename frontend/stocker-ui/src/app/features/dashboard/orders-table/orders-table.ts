import { Component, Input } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { CommonModule } from '@angular/common';
import { Order } from '../../../core/services/orders';

@Component({
  selector: 'app-orders-table',
  imports: [MatTableModule, MatChipsModule, CommonModule],
  templateUrl: './orders-table.html',
  styleUrl: './orders-table.scss',
})
export class OrdersTable {
  displayedColumns: string[] = ['date', 'symbol', 'name', 'side', 'qty', 'status', 'fill_price'];

  @Input() set orders(value: Order[]) {
    this.dataSource = value || [];
  }

  @Input() instrumentNames: Record<string, string> = {};

  dataSource: Order[] = [];

  getStatusColor(status: string | null): string {
    switch (status?.toLowerCase()) {
      case 'filled': return 'primary';
      case 'pending': return 'accent';
      case 'cancelled': return 'warn';
      default: return '';
    }
  }

  getSideClass(side: string | null): string {
    return side?.toLowerCase() === 'buy' ? 'side-buy' : 'side-sell';
  }

  getFillPrice(order: Order): number | null {
    if (order.fills && order.fills.length > 0) {
      return Number(order.fills[0].price);
    }
    return null;
  }
}
