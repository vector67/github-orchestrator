import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type { Commits, Diff } from 'frontend/data/api';
import { inlineOf, type Inlined } from 'frontend/data/inline';
import { ordered, type Picked, type Timeline } from 'frontend/data/timeline';
import { reportError } from 'frontend/data/report';
import { keyOf } from 'frontend/data/wall';
import type CommitBoxService from 'frontend/services/commit-box';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ReviewService from 'frontend/services/review';
import type StoreService from 'frontend/services/store';
import { commitsOf } from 'frontend/services/store';
import type {
  CommitNote,
  DiffRange,
  DiffSource,
  MergeNote,
  PickedRange,
  Stepper,
} from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export type { DiffSource } from 'frontend/services/store';

class PerPr {
  @tracked failed = false;
  @tracked fetching = false;
  @tracked source: DiffSource = 'origin';
  @tracked chosen: string | null = null;
  @tracked picked: Picked | null = null;
  @tracked timelineOpen = false;
  @tracked across = 0;
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

  private get hidden(): boolean {
    return this.commitBox.sizing === 'hidden';
  }

  private get stepping(): Stepper | null | undefined {
    return this.store.stepper(
      this.here.at,
      this.source,
      this.pr.chosen,
      this.pr.picked,
      this.commitBox.skipMerges,
    );
  }

  get stepper(): Stepper | null | undefined {
    return this.hidden ? null : this.stepping;
  }

  get picked(): PickedRange | null {
    return this.store.pickedRange(this.here.at, this.source, this.pr.picked);
  }

  get pickedFiles(): number | null {
    const picked = this.picked;
    return picked && (this.store.files(picked.range)?.length ?? null);
  }

  get timeline(): Timeline | null | undefined {
    return this.store.timeline(this.here.at, this.source, {
      current: this.stepping?.sha ?? null,
      picked: this.pr.picked,
      hidden: this.hidden,
      across: this.pr.across,
    });
  }

  fit = (across: number) => {
    this.pr.across = across;
  };

  get timelineOpen(): boolean {
    return this.pr.timelineOpen && Boolean(this.timeline);
  }

  toggleTimeline = () => {
    this.pr.timelineOpen = !this.pr.timelineOpen;
  };

  pick = (sha: string, extend: boolean) => {
    const order = this.timeline?.order ?? [];
    const anchor = this.stepper?.sha ?? this.pr.picked?.from ?? sha;
    this.choose(extend ? ordered(order, anchor, sha) : { from: sha, to: sha });
  };

  stretch = (end: 'from' | 'to', sha: string) => {
    const showing = this.timeline?.showing;
    if (!showing) return;
    const kept = end === 'from' ? showing.to : showing.from;
    this.choose(ordered(this.timeline?.order ?? [], kept, sha));
  };

  choose = (picked: Picked | null) => {
    if (picked && picked.from === picked.to && !this.hidden) {
      this.pr.chosen = picked.from;
      this.pr.picked = null;
      return;
    }
    this.pr.picked = picked;
  };

  get whole(): Picked | null {
    const { repo, number } = this.here.at;
    const commits = this.store.pr(repo, number)?.history[this.source]?.commits;
    return commits?.length
      ? { from: commits[0]!.sha, to: commits.at(-1)!.sha }
      : null;
  }

  showWhole = () => {
    const whole = this.whole;
    if (whole) this.choose(whole);
  };

  unpick = (): boolean => {
    if (!this.pr.picked) return false;
    this.pr.picked = null;
    return true;
  };

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

  private get range(): DiffRange | null {
    return this.picked?.range ?? this.stepper?.range ?? null;
  }

  private get merging(): Commits | null {
    const stepper = this.stepper;
    if (this.picked || !stepper?.merge) return null;
    return { base: stepper.range.base, head: stepper.range.head };
  }

  get mergeNote(): MergeNote | null {
    const stepper = this.stepper;
    if (this.picked || !stepper?.merge) return null;
    return this.store.mergeNote(stepper.range);
  }

  get baseName(): string {
    return this.threads.pullRequest?.base_branch ?? 'main';
  }

  skipMerges = (skip: boolean) => {
    this.commitBox.chooseSkipMerges(skip);
  };

  get shown(): Diff | undefined {
    const range = this.range;
    if (range) return this.store.diff(range);
    if (this.stepper === undefined && !this.pr.stepless) return undefined;
    return this.diff;
  }

  get shownFailed(): boolean {
    const range = this.range;
    if (range) return this.pr.unreadable === commitsOf(range);
    return this.failed;
  }

  get commenting(): boolean {
    const picked = this.picked;
    return picked ? picked.head : !this.stepper?.next;
  }

  get drawing(): string {
    const range = this.range;
    return range ? commitsOf(range) : '';
  }

  load = () => {
    const pr = this.pr;
    const asking = this.asking;
    if (pr.asked === asking) return;
    pr.asked = asking;
    void waitForPromise(this.fetched(pr, pr.source));
    void waitForPromise(this.readHistory(pr, pr.source));
    if (pr.source === 'local') void waitForPromise(this.readPushed());
  };

  draw = () => {
    const range = this.range;
    if (range) void waitForPromise(this.drawn(this.pr, range));
    const merging = this.merging;
    if (merging) void waitForPromise(this.readMerged(merging));
  };

  step = (by: number) => {
    const stepper = this.stepper;
    const sha = by < 0 ? stepper?.previous : stepper?.next;
    if (!sha) return;
    this.pr.chosen = sha;
    this.pr.picked = null;
  };

  go = (sha: string) => {
    this.pr.chosen = sha;
    this.pr.picked = null;
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

  private async readMerged(range: Commits): Promise<void> {
    await this.store.readDiff(range);
  }

  private async readPushed(): Promise<void> {
    await this.store.readPrCommits(this.here.at, 'origin');
  }

  private async drawn(pr: PerPr, range: DiffRange): Promise<void> {
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
