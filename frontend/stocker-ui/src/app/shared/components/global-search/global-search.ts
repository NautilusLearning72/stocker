import {
  Component,
  OnInit,
  OnDestroy,
  ElementRef,
  HostListener,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { Subject, Subscription, debounceTime, distinctUntilChanged, switchMap, of } from 'rxjs';
import {
  SymbolDetailService,
  SearchResult,
} from '../../../core/services/symbol-detail.service';

@Component({
  selector: 'app-global-search',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
  ],
  templateUrl: './global-search.html',
  styleUrl: './global-search.scss',
})
export class GlobalSearch implements OnInit, OnDestroy {
  searchTerm = '';
  results: SearchResult[] = [];
  showDropdown = false;
  selectedIndex = -1;
  isLoading = false;

  private searchSubject = new Subject<string>();
  private subscription?: Subscription;

  constructor(
    private symbolService: SymbolDetailService,
    private router: Router,
    private elementRef: ElementRef
  ) {}

  ngOnInit(): void {
    this.subscription = this.searchSubject
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap((term) => {
          if (term.length < 1) {
            return of([]);
          }
          this.isLoading = true;
          return this.symbolService.search(term, 8);
        })
      )
      .subscribe({
        next: (results) => {
          this.results = results;
          this.showDropdown = results.length > 0;
          this.selectedIndex = -1;
          this.isLoading = false;
        },
        error: () => {
          this.results = [];
          this.showDropdown = false;
          this.isLoading = false;
        },
      });
  }

  onInput(): void {
    this.searchSubject.next(this.searchTerm);
    if (!this.searchTerm) {
      this.showDropdown = false;
      this.results = [];
    }
  }

  onFocus(): void {
    if (this.results.length > 0) {
      this.showDropdown = true;
    }
  }

  selectResult(result: SearchResult): void {
    this.router.navigate(['/symbol', result.symbol]);
    this.clearSearch();
  }

  onKeydown(event: KeyboardEvent): void {
    if (!this.showDropdown) return;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.selectedIndex = Math.min(
          this.selectedIndex + 1,
          this.results.length - 1
        );
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
        break;
      case 'Enter':
        event.preventDefault();
        if (this.selectedIndex >= 0) {
          this.selectResult(this.results[this.selectedIndex]);
        } else if (this.results.length > 0) {
          this.selectResult(this.results[0]);
        }
        break;
      case 'Escape':
        this.clearSearch();
        break;
    }
  }

  @HostListener('document:click', ['$event'])
  onClickOutside(event: Event): void {
    if (!this.elementRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }

  clearSearch(): void {
    this.searchTerm = '';
    this.results = [];
    this.showDropdown = false;
    this.selectedIndex = -1;
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
  }
}
