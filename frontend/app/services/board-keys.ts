import Service, { service } from '@ember/service';
import type RouterService from '@ember/routing/router-service';
import { stepped, type Keymap } from 'frontend/services/keys';
import type ReviewService from 'frontend/services/review';
import type StoreService from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export default class BoardKeysService extends Service implements Keymap {
  @service declare router: RouterService;
  @service declare review: ReviewService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;

  get openId(): string | null {
    const match = /\/conversations\/([^/?]+)/.exec(
      this.router.currentURL ?? '',
    );
    return match ? decodeURIComponent(match[1]!) : null;
  }

  open = (key: string): void => {
    this.store.markSeen(key);
    void this.router.transitionTo('conversations.detail', key);
  };

  nextReady = (): void => {
    this.walk(1, this.threads.readyKeys);
  };

  previousReady = (): void => {
    this.walk(-1, this.threads.readyKeys);
  };

  take = (key: string): boolean => {
    if (key === 'n') this.nextReady();
    else if (key === 'p') this.previousReady();
    else if (key === 'S') this.review.show();
    else if (key === 'j') this.walk(1, this.threads.railOrder);
    else if (key === 'k') this.walk(-1, this.threads.railOrder);
    else if (key === 'Escape') return this.close();
    else return false;
    return true;
  };

  private walk(by: number, order: string[]): void {
    const open = this.openId;
    const landed = stepped(order, open === null ? -1 : order.indexOf(open), by);
    if (landed) this.open(landed);
  }

  private close(): boolean {
    if (this.openId === null && this.router.currentRouteName !== 'board') {
      return false;
    }
    void this.router.transitionTo('conversations');
    return true;
  }
}
