import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { OrdersService, CreateOrderRequest, Order } from '../../../../core/services/orders';

interface QuickOrderData {
  symbol: string;
}

@Component({
  selector: 'app-quick-order-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatButtonToggleModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './quick-order-dialog.html',
  styleUrl: './quick-order-dialog.scss',
})
export class QuickOrderDialog {
  symbol: string;
  side = 'BUY';
  orderType = 'market';
  timeInForce = 'day';
  quantityMode: 'qty' | 'notional' = 'qty';
  qty: number | null = null;
  notional: number | null = null;
  limitPrice: number | null = null;

  submitting = false;
  errorMessage = '';

  constructor(
    @Inject(MAT_DIALOG_DATA) data: QuickOrderData,
    private dialogRef: MatDialogRef<QuickOrderDialog, Order>,
    private ordersService: OrdersService,
  ) {
    this.symbol = data.symbol;
  }

  submit(): void {
    this.errorMessage = '';
    if (this.quantityMode === 'qty' && (!this.qty || this.qty <= 0)) {
      this.errorMessage = 'Enter a valid quantity';
      return;
    }
    if (this.quantityMode === 'notional' && (!this.notional || this.notional <= 0)) {
      this.errorMessage = 'Enter a valid notional value';
      return;
    }
    if (this.orderType === 'limit' && (!this.limitPrice || this.limitPrice <= 0)) {
      this.errorMessage = 'Enter a valid limit price';
      return;
    }

    const payload: CreateOrderRequest = {
      symbol: this.symbol,
      side: this.side,
      type: this.orderType,
      time_in_force: this.timeInForce,
    };

    if (this.quantityMode === 'qty') {
      payload.qty = this.qty ?? undefined;
    } else {
      payload.notional = this.notional ?? undefined;
    }
    if (this.orderType === 'limit') {
      payload.limit_price = this.limitPrice ?? undefined;
    }

    this.submitting = true;
    this.ordersService.createOrder(payload).subscribe({
      next: (order) => {
        this.submitting = false;
        this.dialogRef.close(order);
      },
      error: (err) => {
        console.error('Order submission failed', err);
        this.submitting = false;
        this.errorMessage = 'Order submission failed';
      },
    });
  }

  close(): void {
    this.dialogRef.close();
  }
}
