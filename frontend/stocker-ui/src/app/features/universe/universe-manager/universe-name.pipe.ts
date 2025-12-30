import { Pipe, PipeTransform } from '@angular/core';
import { Universe } from '../../../core/services/universe.service';

@Pipe({
  name: 'universeName',
  standalone: true,
})
export class UniverseNamePipe implements PipeTransform {
  transform(universes: Universe[] | null | undefined, id: number | undefined): string | undefined {
    if (!universes || id === undefined || id === null) return undefined;
    const found = universes.find((u) => u.id === id);
    return found?.name;
  }
}
