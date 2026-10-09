import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type RouterService from '@ember/routing/router-service';
import type { Operation, ReviewVerdict } from 'frontend/data/api';
import { reportError } from 'frontend/data/report';
import { reviewOf, type Review } from 'frontend/data/review';
import { tried } from 'frontend/data/tried';
import type BoardService from 'frontend/services/board';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ToastsService from 'frontend/services/toasts';

const SETTLED = ['applied', 'refused', 'requeued'];

class PerPr {
  @tracked open = false;
  @tracked verdict: ReviewVerdict = 'COMMENT';
  @tracked body = '';
  @tracked going: string | null = null;
  @tracked trouble: string | null = null;

  location: string | null = null;

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
    return this.pr.trouble;
  }

  get review(): Review {
    return reviewOf(
      this.threads.conversations,
      this.threads.details,
      this.store.viewer ?? '',
    );
  }

  get needsSummary(): boolean {
    return this.verdict !== 'APPROVE';
  }

  private get going(): Operation | undefined {
    const id = this.pr.going;
    const pr = this.here.pr;
    if (id === null || pr === null) return undefined;
    return this.store.operation(pr.repo, pr.number, id);
  }

  get inFlight(): boolean {
    const going = this.going;
    return going !== undefined && !SETTLED.includes(going.state);
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
    pr.trouble = null;
    const answer = await tried(
      'review',
      this.store.sendReview(at, {
        verdict: pr.verdict,
        body: pr.body.trim() || null,
      }),
    );
    if (!answer.done) {
      if (!pr.scope.left) pr.trouble = answer.why;
      return;
    }
    pr.going = answer.body.id;
    pr.location = answer.body.location;
  }

  async follow(): Promise<void> {
    const pr = this.pr;
    const at = this.here.pr;
    if (!this.inFlight || !pr.location || at === null) return;
    try {
      await this.store.readOperation(at, pr.location);
    } catch (trouble) {
      void reportError('review', trouble);
      return;
    }
    const going = this.going;
    if (pr.scope.left || !going) return;
    if (going.state === 'applied') {
      pr.body = '';
      pr.going = null;
      pr.open = false;
      this.toasts.say('Sent: your review is on GitHub.', 'done');
      await this.loader.refreshList();
    } else if (SETTLED.includes(going.state)) {
      pr.trouble =
        `GitHub refused the review: ${going.reason ?? going.reason_code ?? ''}. ` +
        'Every draft is still in it.';
    }
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
