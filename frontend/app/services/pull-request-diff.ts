import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { Commits, Diff } from 'frontend/data/api';
import { inlineOf, type Inlined } from 'frontend/data/inline';
import { reportError } from 'frontend/data/report';
import { keyOf } from 'frontend/data/wall';
import type CommitBoxService from 'frontend/services/commit-box';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ReviewService from 'frontend/services/review';
import type StoreService from 'frontend/services/store';
import { commitsOf } from 'frontend/services/store';
import type { CommitNote, DiffSource, Stepper } from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export type { DiffSource } from 'frontend/services/store';

class PerPr {
  @tracked failed = false;
  @tracked fetching = false;
  @tracked source: DiffSource = 'origin';
  @tracked chosen: string | null = null;
  @tracked stepless = false;
  @tracked unreadable: string | null = null;
  asked: string | null = null;

  constructor(readonly scope: PrScope) {}
}

const fresh = (scope: PrScope): PerPr => new PerPr(scope);

export default class PullRequestDiffService extends Service {
  @service declare here: HereService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;
  @service declare review: ReviewService;
  @service declare commitBox: CommitBoxService;

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

  get stepper(): Stepper | null | undefined {
    if (this.commitBox.sizing === 'hidden') return null;
    return this.store.stepper(this.here.at, this.source, this.pr.chosen);
  }

  get note(): CommitNote | null {
    if (this.commitBox.sizing !== 'full') return null;
    const note = this.store.commitNote(this.here.at, this.source);
    if (!note || this.commitBox.noteDismissed(keyOf(this.here.at), note.head))
      return null;
    return note;
  }

  dismissNote = () => {
    const note = this.note;
    if (note) this.commitBox.dismissNote(keyOf(this.here.at), note.head);
  };

  get shown(): Diff | undefined {
    const stepper = this.stepper;
    if (stepper) return this.store.diff(stepper.range);
    if (stepper === undefined && !this.pr.stepless) return undefined;
    return this.diff;
  }

  get shownFailed(): boolean {
    const stepper = this.stepper;
    if (stepper) return this.pr.unreadable === commitsOf(stepper.range);
    return this.failed;
  }

  get commenting(): boolean {
    return !this.stepper?.next;
  }

  get drawing(): string {
    const stepper = this.stepper;
    return stepper ? commitsOf(stepper.range) : '';
  }

  load = () => {
    const pr = this.pr;
    const asking = this.asking;
    if (pr.asked === asking) return;
    pr.asked = asking;
    void waitForPromise(this.fetched(pr, pr.source));
    void waitForPromise(this.readHistory(pr, pr.source));
  };

  draw = () => {
    const stepper = this.stepper;
    if (stepper) void waitForPromise(this.drawn(this.pr, stepper.range));
  };

  step = (by: number) => {
    const stepper = this.stepper;
    const sha = by < 0 ? stepper?.previous : stepper?.next;
    if (sha) this.pr.chosen = sha;
  };

  go = (sha: string) => {
    this.pr.chosen = sha;
  };

  tick = (marked: boolean) => {
    const stepper = this.stepper;
    if (!stepper) return;
    this.pr.chosen = stepper.sha;
    void waitForPromise(
      this.store
        .markRead(this.here.at, stepper.sha, marked)
        .catch((trouble) => reportError('mark a commit read', trouble)),
    );
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
      if (pr.source !== 'origin') return;
      await Promise.all([
        this.fetched(pr, 'origin'),
        this.readHistory(pr, 'origin'),
      ]);
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

  private async readHistory(pr: PerPr, source: DiffSource): Promise<void> {
    const outcomes = await Promise.all([
      this.store.readPrCommits(this.here.at, source),
      this.store.readReadMarks(this.here.at),
    ]);
    if (pr.scope.left) return;
    pr.stepless = outcomes.includes('failed') && this.stepper === undefined;
  }

  private async drawn(pr: PerPr, range: Commits): Promise<void> {
    const outcome = await this.store.readDiff(range);
    if (pr.scope.left) return;
    pr.unreadable = outcome === 'failed' ? commitsOf(range) : null;
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
