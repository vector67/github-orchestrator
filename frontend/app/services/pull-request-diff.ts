import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { Diff } from 'frontend/data/api';
import { inlineOf, type Inlined } from 'frontend/data/inline';
import { reportError } from 'frontend/data/report';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ReviewService from 'frontend/services/review';
import type StoreService from 'frontend/services/store';
import type { DiffSource } from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export type { DiffSource } from 'frontend/services/store';

class PerPr {
  @tracked failed = false;
  @tracked fetching = false;
  @tracked source: DiffSource = 'origin';
  asked: string | null = null;

  constructor(readonly scope: PrScope) {}
}

const fresh = (scope: PrScope): PerPr => new PerPr(scope);

export default class PullRequestDiffService extends Service {
  @service declare here: HereService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;
  @service declare review: ReviewService;

  private get pr(): PerPr {
    return this.here.scope.of(fresh);
  }

  get failed(): boolean {
    return this.pr.failed;
  }

  get fetching(): boolean {
    return this.pr.fetching;
  }

  get source(): DiffSource {
    return this.pr.source;
  }

  get asking(): string {
    return `pull-request-diff@${this.source}@${this.threads.pullRequest?.head_sha ?? ''}`;
  }

  get diff(): Diff | undefined {
    const commits = this.threads.pullRequest?.diffs[this.source];
    return commits && this.store.diff(commits);
  }

  load = () => {
    const pr = this.pr;
    const asking = this.asking;
    if (pr.asked === asking) return;
    pr.asked = asking;
    void waitForPromise(this.fetched(pr, pr.source));
  };

  show = (source: DiffSource) => {
    this.pr.source = source;
  };

  fetchBranch = () => {
    void waitForPromise(this.fetchingBranch(this.pr));
  };

  private async fetchingBranch(pr: PerPr): Promise<void> {
    pr.fetching = true;
    try {
      await this.read(pr.source, false);
      if (pr.scope.left) return;
      await this.store.hand(this.here.api('/api/pull-request:fetch'));
      if (pr.scope.left) return;
      if (pr.source === 'origin') await this.fetched(pr, 'origin');
    } catch (trouble) {
      void reportError('fetch the pull request', trouble);
    } finally {
      pr.fetching = false;
    }
  }

  private read(source: DiffSource, revalidate = true) {
    return this.store.readPrDiff(
      this.here.at,
      source,
      this.here.api(`/api/pull-request/diff?source=${source}`),
      revalidate,
    );
  }

  private async fetched(pr: PerPr, source: DiffSource): Promise<void> {
    const outcome = await this.read(source);
    if (pr.scope.left) return;
    pr.failed = outcome === 'failed' && !this.diff;
    if (outcome === 'failed') pr.asked = null;
  }
  get inline(): Inlined {
    const role = this.threads.role;
    if (!role) return { shown: [], outdated: {} };
    return inlineOf(this.threads.conversations, {
      details: (key) => this.threads.details(key) ?? undefined,
      context: (key) => this.threads.contextFor(key, role),
      reviewSending: this.review.inFlight,
      role,
    });
  }

  get anchored(): string[] {
    return this.threads.conversations
      .filter((one) => one.anchor.path !== null)
      .map((one) => `${one.key}@${one.etag}`);
  }

  readDetails = () => {
    for (const one of this.threads.conversations) {
      if (one.anchor.path !== null) {
        void waitForPromise(this.threads.loadDetails(one.key));
      }
    }
  };
}
