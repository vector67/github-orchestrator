import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import {
  associateDestroyableChild,
  destroy,
  isDestroying,
} from '@ember/destroyable';
import { keyOf, pageOf, type Numbered } from 'frontend/data/wall';
import type StoreService from 'frontend/services/store';

const NOWHERE: Numbered = { repo: '', number: 0 };

export class PrScope {
  private parts = new Map<object, unknown>();

  get left(): boolean {
    return isDestroying(this);
  }

  of<T>(make: (scope: PrScope) => T): T {
    if (!this.parts.has(make)) this.parts.set(make, make(this));
    return this.parts.get(make) as T;
  }
}

export default class HereService extends Service {
  @service declare store: StoreService;

  @tracked pr: Numbered | null = null;
  @tracked scope = associateDestroyableChild(this, new PrScope());

  get at(): Numbered {
    return this.pr ?? NOWHERE;
  }

  get prefix(): string {
    return this.pr === null ? '' : this.prefixOf(this.pr);
  }

  prefixOf = (pr: Numbered): string => (this.store.onHub ? pageOf(pr) : '');

  api = (path: string): string => `${this.prefix}${path}`;

  enter(pr: Numbered): void {
    if (this.pr !== null && keyOf(this.pr) === keyOf(pr)) return;
    if (this.pr !== null) {
      this.store.abandonUnder(this.prefix);
      destroy(this.scope);
      this.scope = associateDestroyableChild(this, new PrScope());
    }
    this.pr = { repo: pr.repo, number: pr.number };
  }
}
