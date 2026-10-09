import Service, { service } from '@ember/service';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import { tracked } from '@glimmer/tracking';
import { registerDestructor } from '@ember/destroyable';
import { waitForPromise } from '@ember/test-waiters';
import { Refusal, unheldBy, unreachable } from 'frontend/data/refusal';
import type { Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';
import type { PrScope } from 'frontend/services/here';
import type ReachabilityService from 'frontend/services/reachability';
import type { Polled } from 'frontend/services/reachability';
import type ReviewService from 'frontend/services/review';
import type StoreService from 'frontend/services/store';
import type { Feed, Following } from 'frontend/services/store';
import type ThreadsService from 'frontend/services/threads';

export const LIST_MS = 5000;
export const OPERATIONS_MS = 1000;
export const RESTART_MS = 500;

class Rail {
  @tracked loaded = false;
  starting: Promise<void> | null = null;

  readonly pull: Polled;
  readonly viewer: Polled;
  readonly people: Polled;
  readonly list: Polled;
  readonly inFlight: Polled;

  constructor(
    reachability: ReachabilityService,
    store: StoreService,
    readonly scope: PrScope,
    pr: Numbered,
  ) {
    const counts = (trouble: unknown): boolean =>
      this.loaded || !unreachable(trouble);
    const polled = (where: string, feed: Feed, flipped = false) =>
      reachability.polled(where, (tag) => store.ask(feed, tag), {
        counts,
        flipped,
        scope,
      });
    this.pull = polled('rail', { kind: 'pull-request', pr });
    this.viewer = polled('rail', { kind: 'viewer', pr });
    this.people = polled('rail', { kind: 'people', pr });
    this.list = polled('rail', { kind: 'conversations', pr }, true);
    this.inFlight = polled('refresh', { kind: 'in-flight', pr });
  }
}

interface Streams {
  dashboard: Following;
  notes: Following;
  output: Following;
}

class Board {
  @tracked readAt: number | null = null;
  @tracked heard = false;
  @tracked streamed = false;
  @tracked streams: Streams | null = null;
  reading: Promise<void> | null = null;

  readonly bar: Polled;

  constructor(
    reachability: ReachabilityService,
    store: StoreService,
    scope: PrScope,
    pr: Numbered,
  ) {
    this.bar = reachability.polled(
      'dashboard',
      (tag) => store.ask({ kind: 'dashboard', pr }, tag),
      { counts: (trouble) => !(trouble instanceof Refusal), scope },
    );
    registerDestructor(scope, () => this.unfollow());
  }

  unfollow(): void {
    const streams = this.streams;
    if (!streams) return;
    streams.dashboard.close();
    streams.notes.close();
    streams.output.close();
    this.streams = null;
    this.streamed = false;
  }

  forget(): void {
    this.bar.forget();
    this.heard = false;
  }
}

export default class PollService extends Service {
  @service declare here: HereService;
  @service declare reachability: ReachabilityService;
  @service declare review: ReviewService;
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare threads: ThreadsService;

  @tracked now = Date.now();
  @tracked hubAt = Date.now();

  readonly wall: Polled;
  readonly runs: Polled;

  private located: Promise<void> | null = null;
  private walling: Promise<void> | null = null;
  private timers: ReturnType<typeof setInterval>[] = [];
  private listTimer: ReturnType<typeof setInterval> | null = null;
  private dashboardTimer: ReturnType<typeof setInterval> | null = null;
  private hubTimer: ReturnType<typeof setInterval> | null = null;
  private barTimer: ReturnType<typeof setInterval> | null = null;
  private restartTimer: ReturnType<typeof setInterval> | null = null;

  constructor(owner: Owner) {
    super(owner);
    this.wall = this.reachability.polled(
      'pull requests',
      (tag) => this.store.ask({ kind: 'wall' }, tag),
      {
        flipped: true,
        overdue: true,
        counts: (trouble) => unheldBy(trouble) === null,
      },
    );
    this.runs = this.reachability.polled(
      'runs',
      (tag) => this.store.ask({ kind: 'runs' }, tag),
      { overdue: true },
    );
  }

  private freshRail = (scope: PrScope): Rail =>
    new Rail(this.reachability, this.store, scope, this.here.at);

  private freshBoard = (scope: PrScope): Board =>
    new Board(this.reachability, this.store, scope, this.here.at);

  get rail(): Rail {
    return this.here.scope.of(this.freshRail);
  }

  get board(): Board {
    return this.here.scope.of(this.freshBoard);
  }

  locate(): Promise<void> {
    this.located ??= this.store.readHealth('/api/health').then(() => undefined);
    return this.located;
  }

  start(): void {
    if (this.timers.length > 0) return;
    this.timers = [
      setInterval(() => void waitForPromise(this.tick()), OPERATIONS_MS),
    ];
  }

  stop(): void {
    this.timers.forEach(clearInterval);
    this.timers = [];
  }

  startList(): void {
    this.listTimer ??= setInterval(
      () => void waitForPromise(this.refreshList()),
      LIST_MS,
    );
  }

  stopList(): void {
    if (this.listTimer) clearInterval(this.listTimer);
    this.listTimer = null;
  }

  startDashboard(): void {
    this.dashboardTimer ??= setInterval(
      () => this.tickDashboard(),
      OPERATIONS_MS,
    );
  }

  stopDashboard(): void {
    if (this.dashboardTimer) clearInterval(this.dashboardTimer);
    this.dashboardTimer = null;
  }

  startHub(): void {
    this.hubTimer ??= setInterval(
      () => void waitForPromise(this.refreshHub()),
      LIST_MS,
    );
  }

  stopHub(): void {
    if (this.hubTimer) clearInterval(this.hubTimer);
    this.hubTimer = null;
  }

  startBar(): void {
    this.barTimer ??= setInterval(
      () => void waitForPromise(this.refreshLive()),
      LIST_MS,
    );
  }

  stopBar(): void {
    if (this.barTimer) clearInterval(this.barTimer);
    this.barTimer = null;
  }

  followRestart(): void {
    this.restartTimer ??= setInterval(
      () => void waitForPromise(this.tickRestart()),
      RESTART_MS,
    );
  }

  private stopRestart(): void {
    if (this.restartTimer) clearInterval(this.restartTimer);
    this.restartTimer = null;
  }

  private async tickRestart(): Promise<void> {
    const now = await this.store.followRestart();
    if (now === 'going') return;
    this.stopRestart();
    if (now === 'failed') return;
    if (this.store.health?.state === 'watching') {
      await this.router.transitionTo('index');
    } else {
      await this.router.refresh('setup');
    }
  }

  willDestroy(): void {
    super.willDestroy();
    this.stopRestart();
    this.stop();
    this.stopList();
    this.stopDashboard();
    this.stopHub();
    this.stopBar();
  }

  private async tick(): Promise<void> {
    await this.refreshOperations();
    await this.review.follow();
  }

  startRail(): Promise<void> {
    const rail = this.rail;
    rail.starting ??= this.starting(rail).finally(() => {
      rail.starting = null;
    });
    return rail.starting;
  }

  private async starting(rail: Rail): Promise<void> {
    if (rail.loaded) return;
    await Promise.all([
      rail.pull.poll(),
      rail.viewer.poll(),
      rail.people.poll(),
      rail.list.poll(),
      rail.inFlight.poll(),
    ]);
    rail.loaded = true;
  }

  async refreshList(): Promise<void> {
    const rail = this.rail;
    await this.readRail(rail).catch(() => undefined);
    if (rail.scope.left) return;
    await this.threads.reread();
  }

  private async readRail(rail: Rail): Promise<void> {
    if (!rail.loaded) return this.starting(rail);
    const [, listed] = await Promise.all([rail.pull.poll(), rail.list.poll()]);
    if (listed) await rail.people.poll();
  }

  async refreshOperations(): Promise<void> {
    const rail = this.rail;
    const { inFlight, scope } = rail;
    const before = inFlight.mark;
    try {
      await inFlight.poll();
    } catch {
      return;
    }
    if (scope.left) return;
    if (inFlight.mark !== before) await this.refreshList();
  }

  async refreshHub(): Promise<void> {
    await Promise.allSettled([this.wall.poll(), this.runs.poll()]);
    this.hubAt = Date.now();
  }

  held(): Promise<void> {
    if (this.store.wall.length) return Promise.resolve();
    this.walling ??= this.refreshHub().finally(() => {
      this.walling = null;
    });
    return this.walling;
  }

  follow(): Promise<void> {
    const board = this.board;
    const pr = this.here.at;
    board.streams ??= {
      dashboard: this.store.follow('dashboard', pr, () => {
        board.streamed = true;
      }),
      notes: this.store.follow('notes', pr),
      output: this.store.follow('output', pr),
    };
    const { streams } = board;
    return Promise.all([
      streams.dashboard.opened,
      streams.notes.opened,
      streams.output.opened,
    ]).then(() => undefined);
  }

  leave(): void {
    const board = this.board;
    board.unfollow();
    if (this.store.onHub) board.forget();
  }

  private tickDashboard(): void {
    this.now = Date.now();
    const streams = this.board.streams;
    if (!streams) return;
    streams.dashboard.reopen();
    streams.notes.reopen();
    streams.output.reopen();
  }

  read(): Promise<void> {
    const board = this.board;
    board.reading ??= this.refreshLive().finally(() => {
      board.reading = null;
    });
    return board.reading;
  }

  async refreshLive(): Promise<void> {
    const board = this.board;
    try {
      await board.bar.poll();
      board.heard = true;
      board.readAt = Date.now();
    } catch {
      board.forget();
    }
    this.now = Date.now();
  }
}
