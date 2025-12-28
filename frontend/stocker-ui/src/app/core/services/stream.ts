import { Injectable, NgZone } from '@angular/core';
import { Subject } from 'rxjs';

export interface StreamEvent {
  event: string;
  data: any;
}

@Injectable({
  providedIn: 'root'
})
export class StreamService {
  private eventSource?: EventSource;
  private eventSubject = new Subject<StreamEvent>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private isConnecting = false;

  public events$ = this.eventSubject.asObservable();

  constructor(private zone: NgZone) {
    // Delay initial connection to avoid blocking app startup
    setTimeout(() => this.connect(), 1000);
  }

  connect(): void {
    if (this.isConnecting || (this.eventSource && this.eventSource.readyState === EventSource.OPEN)) {
      return;
    }

    this.isConnecting = true;
    const url = 'http://localhost:8000/api/v1/stream';

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        this.reconnectAttempts = 0;
        this.isConnecting = false;
      };

      this.eventSource.onerror = () => {
        this.isConnecting = false;
        this.eventSource?.close();

        // Limit reconnection attempts
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = Math.min(5000 * this.reconnectAttempts, 30000);
          setTimeout(() => this.connect(), delay);
        }
      };

      this.eventSource.addEventListener('update', (event: MessageEvent) => {
        this.zone.run(() => {
          try {
            const payload = JSON.parse(event.data);
            this.eventSubject.next({ event: 'update', data: payload });
          } catch (e) {
            // Silently ignore parse errors
          }
        });
      });

      this.eventSource.addEventListener('connected', () => {
        // Connected successfully
      });
    } catch {
      this.isConnecting = false;
    }
  }
}
