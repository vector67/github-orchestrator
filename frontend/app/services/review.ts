import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type RouterService from '@ember/routing/router-service';
import type { Operation, ReviewVerdict } from 'frontend/data/api';
import { reportError } from 'frontend/data/report';
import {
  reviewGoing,
  reviewOf,
  reviewSending,
  type Review,
} from 'frontend/data/review';
import { local, sent } from 'frontend/data/thread';
import type BoardService from 'frontend/services/board';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ToastsService from 'frontend/services/toasts';

class PerPr {
  @tracked open = false;
  @tracked verdict: ReviewVerdict = 'COMMENT';
  @tracked body = '';

  constructor(readonly scope: PrScope) {}
}

const fresh = (scope: PrScope): PerPr => new PerPr(scope);

export default class ReviewService extends Service {
  @service declare board: BoardService;
  @service('poll') declare loader: PollService;
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;
  @service declare toasts: ToastsService;
  @service declare here: HereService;

  private get pr(): PerPr {
    return this.here.scope.of(fresh);
  }

  get open(): boolean {
    return this.pr.open;
  }

  get verdict(): ReviewVerdict {
    return this.pr.verdict;
  }

  set verdict(verdict: ReviewVerdict) {
    this.pr.verdict = verdict;
  }

  get body(): string {
    return this.pr.body;
  }

  set body(body: string) {
    this.pr.body = body;
  }

  get trouble(): string | null {
    const going = this.going;
    if (going?.state !== 'refused') return null;
    if (local(going)) return going.reason;
    return (
      `GitHub refused the review: ${going.reason ?? going.reason_code ?? ''}. ` +
      'Every draft is still in it.'
    );
  }

  get review(): Review {
    return reviewOf(
      this.threads.conversations,
      this.threads.details,
      this.store.viewer ?? '',
      this.inFlight,
    );
  }

  get needsSummary(): boolean {
    return this.verdict !== 'APPROVE';
  }

  private get going(): Operation | undefined {
    return reviewGoing(this.threads.inFlight);
  }

  get inFlight(): boolean {
    return reviewSending(this.threads.inFlight);
  }

  get unsendable(): boolean {
    return this.inFlight || (this.needsSummary && !this.body.trim());
  }

  show = (): void => {
    this.pr.open = true;
    const { enrolled, pendingOnGitHub, unadded } = this.review;
    for (const one of [...enrolled, ...pendingOnGitHub, ...unadded]) {
      void waitForPromise(this.threads.loadDetails(one.key));
    }
  };

  close = (): void => {
    this.pr.open = false;
  };

  send(): Promise<void> {
    return waitForPromise(this.sent());
  }

  private async sent(): Promise<void> {
    const pr = this.pr;
    const at = this.here.pr;
    if (this.unsendable || at === null) return;
    await this.store.sendReview(at, {
      verdict: pr.verdict,
      body: pr.body.trim() || null,
    });
  }

  async follow(): Promise<void> {
    const pr = this.pr;
    const at = this.here.pr;
    const going = this.going;
    if (!this.inFlight || at === null || !going || sent(going)) return;
    let now: Operation;
    try {
      now = await this.store.readOperation(at, going.id);
    } catch (trouble) {
      void reportError('review', trouble);
      return;
    }
    if (pr.scope.left || now.state !== 'applied') return;
    pr.body = '';
    pr.open = false;
    this.toasts.say('Sent: your review is on GitHub.', 'done');
    await this.loader.refreshList();
  }

  add = (key: string): void => {
    void this.board.decide(key, 'enrol');
  };

  leaveOut = (key: string): void => {
    void this.board.decide(key, 'withdraw-from-review');
  };

  edit = async (key: string): Promise<void> => {
    this.pr.open = false;
    await this.router.transitionTo('conversations.detail', key);
  };
}
