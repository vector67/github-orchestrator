import Service, { service } from '@ember/service';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type {
  AgentOutput,
  Comment,
  Commits,
  Conversation,
  ConversationList,
  Dashboard,
  DashboardStatus,
  DashboardSystem,
  Diff,
  FileLines,
  FrozenWorktree,
  GitRun,
  Health,
  HeldPullRequests,
  ManagerChanges,
  ManagerFlags,
  Operation,
  Outcome,
  MovedAside,
  Person,
  PrFacts,
  Proposal,
  PullRequest,
  RunLedger,
  Setup,
  SetupAccount,
  SetupClone,
  SetupOperation,
  SetupRepoChoice,
  SetupRepoChoices,
  SetupRequest,
  TerminalSession,
  TerminalSessionList,
  Tour,
  WallGroupName,
  WatcherHealth,
} from 'frontend/data/api';
import {
  carried,
  commentsRead,
  merged,
  older,
  operationKey,
  operationsMerged,
  savedAfter,
  threadMerged,
  type Arriving,
  type HeardLine,
  type Merged,
  type StoredOperation,
  type Thread,
} from 'frontend/data/entities';
import {
  abandonUnder,
  fetched,
  handed,
  pending,
  posted,
  put,
  read,
  write,
} from 'frontend/data/http';
import type { Details, FileStat } from 'frontend/data/panel';
import { Refusal, unheldBy, type Unheld } from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { EventStream, type StreamState } from 'frontend/data/stream';
import {
  detailsOf,
  filesOf,
  placeOf,
  readOf,
  shownOf,
  summaryOf,
  wallOf,
  type Place,
  type Shown,
  type Summaries,
  type WallSection,
} from 'frontend/data/summaries';
import type { Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';

export type {
  Flag,
  Move,
  NextMove,
  Summaries,
  Tally,
  WallRow,
  WallSection,
  Yours,
} from 'frontend/data/summaries';
export type { HeardLine, Thread } from 'frontend/data/entities';

export interface Drawn {
  polled: boolean;
  status: DashboardStatus;
  system: DashboardSystem;
  frozen: FrozenWorktree | null;
  undismiss_command: string;
  notice: string | null;
  drawn_at: string | null;
}

export type DiffSource = 'origin' | 'local';

export interface PrEntity {
  repo: string;
  number: number;
  title: string | null;
  url: string | null;
  branch: string | null;
  head_sha: string | null;
  ticket: string | null;
  author: string | null;
  board_url: string | null;
  board_answered: boolean;
  facts: PrFacts | null;
  flags: ManagerFlags | null;
  drawn: Drawn | null;
  place: Place | null;
  unreadable: string[];
  in_flight: string[];
  diffs: Partial<Record<DiffSource, Commits>>;
}

export type ShownPr = PrEntity & { drawn: Drawn };

export interface Manager {
  notes: string | null;
  output: HeardLine[];
  sessions: TerminalSession[];
}

export type Feed =
  | { kind: 'wall' }
  | { kind: 'runs' }
  | { kind: 'dashboard'; pr: Numbered }
  | { kind: 'pull-request'; pr: Numbered }
  | { kind: 'viewer'; pr: Numbered }
  | { kind: 'people'; pr: Numbered }
  | { kind: 'conversations'; pr: Numbered }
  | { kind: 'in-flight'; pr: Numbered };

export type Asked =
  | { changed: false }
  | { changed: true; tag: string | null; mark: string; take: () => boolean };

export type Told = 'dashboard' | 'notes' | 'output';

export interface Following {
  readonly state: StreamState;
  readonly opened: Promise<void>;
  reopen(): void;
  close(): void;
}

export type Drawing = 'answered' | 'failed';

export type Read = 'answered' | 'updated' | 'unchanged' | 'failed';

export type Restart = 'going' | 'failed' | 'back';

interface Restarting {
  pid: number | null;
  operation: string | null;
}

export interface Sent {
  id: string;
  location: string;
}

type ByKey<T> = Record<string, Record<string, T>>;

const SHELVED_WALL = 'hub-pull-requests';

const CHOSEN_REPOS = 'hub-repos';

const NO_MANAGER: Manager = { notes: null, output: [], sessions: [] };

const FEED_PATHS: Record<Feed['kind'], string> = {
  wall: '/api/pull-requests',
  runs: '/api/runs',
  dashboard: '/api/dashboard',
  'pull-request': '/api/pull-request',
  viewer: '/api/viewer',
  people: '/api/people',
  conversations: '/api/conversations',
  'in-flight': '/api/operations',
};

const TOLD_PATHS: Record<Told, string> = {
  dashboard: '/api/dashboard/stream',
  notes: '/api/manager/changes/stream',
  output: '/api/manager/agent-output/stream?lines=200',
};

function keyOf(repo: string, number: number): string {
  return `${repo}#${number}`;
}

export function commitsOf(commits: Commits): string {
  return `${commits.base}..${commits.head}`;
}

function markOf(operations: Operation[]): string {
  return operations.map((one) => `${one.id}:${one.state}`).join('|');
}

function under(key: string): string {
  return `/api/conversations/${encodeURIComponent(key)}`;
}

type ShelvedBeforeManyRepos = Omit<HeldPullRequests, 'watching'> & {
  watching: string;
};

function unshelved(): HeldPullRequests | null {
  try {
    const raw = localStorage.getItem(SHELVED_WALL);
    if (!raw) return null;
    const held = JSON.parse(raw) as HeldPullRequests | ShelvedBeforeManyRepos;
    const { watching } = held;
    return {
      ...held,
      watching: typeof watching === 'string' ? [watching] : watching,
    };
  } catch {
    return null;
  }
}

function shelve(held: HeldPullRequests): void {
  try {
    localStorage.setItem(SHELVED_WALL, JSON.stringify(held));
  } catch {
    return;
  }
}

function recalled(): string | null {
  try {
    return localStorage.getItem(CHOSEN_REPOS);
  } catch {
    return null;
  }
}

function remember(asked: string | null): void {
  try {
    if (asked) localStorage.setItem(CHOSEN_REPOS, asked);
    else localStorage.removeItem(CHOSEN_REPOS);
  } catch {
    return;
  }
}

function askedIn(router: RouterService): string | null {
  const asked = router.currentRoute?.queryParams['repos'];
  return typeof asked === 'string' && asked ? asked : null;
}

export default class StoreService extends Service {
  @service declare here: HereService;
  @service declare router: RouterService;

  @tracked private prs: Record<string, PrEntity> = {};
  @tracked private threads: ByKey<Thread> = {};
  @tracked private operations: ByKey<StoredOperation> = {};
  @tracked private proposals: ByKey<Proposal> = {};
  @tracked private diffs: Record<string, Diff> = {};
  @tracked private lines: Record<string, FileLines> = {};
  @tracked private managers: Record<string, Manager> = {};
  @tracked private groups: WallGroupName[] | null = null;
  @tracked watching: string[] = [];
  @tracked ledger: Omit<RunLedger, 'watcher'> | null = null;
  @tracked health: Omit<Health, 'watcher'> | null = null;
  @tracked watcher: WatcherHealth | null = null;
  @tracked unheld: Unheld | null = null;
  @tracked configProblem: string | null = null;
  @tracked viewer: string | null = null;
  @tracked names: Record<string, string | null> = {};
  @tracked private remembered: string | null = recalled();
  @tracked setup: Setup | null = null;
  @tracked accounts: Record<string, SetupAccount> = {};
  @tracked repoChoices: Record<string, SetupRepoChoice[]> = {};
  @tracked named: Record<string, SetupRepoChoice> = {};
  @tracked clones: Record<string, SetupClone> = {};
  @tracked setupOperation: SetupOperation | null = null;
  @tracked movedTo: string | null = null;
  @tracked tour: Tour | null = null;
  private restarting: Restarting | null = null;

  private joins = 0;
  private tags: Record<string, string | null> = {};
  private asking: Record<string, Promise<Read>> = {};

  constructor(owner: Owner) {
    super(owner);
    const held = unshelved();
    if (held) this.takeWall(held);
    this.router.on('routeDidChange', () => {
      const asked = askedIn(this.router);
      if (asked && asked !== this.remembered) this.keepChosen(asked);
    });
  }

  get onHub(): boolean {
    return this.health?.serves === 'hub';
  }

  pr(repo: string, number: number): PrEntity | undefined {
    return this.prs[keyOf(repo, number)];
  }

  holding(number: number): PrEntity[] {
    return Object.values(this.prs)
      .filter((one) => one.number === number && one.place !== null)
      .sort((one, other) => one.repo.localeCompare(other.repo));
  }

  manager(pr: Numbered): Manager {
    return this.managers[keyOf(pr.repo, pr.number)] ?? NO_MANAGER;
  }

  summary(repo: string, number: number): Summaries | null {
    const key = keyOf(repo, number);
    return summaryOf(this.prs[key], this.threads[key], this.operations[key]);
  }

  get chosen(): string[] | null {
    const asked = askedIn(this.router) ?? this.remembered;
    const known = (asked ?? '')
      .split(',')
      .filter((repo) => this.watching.includes(repo));
    return known.length ? known : null;
  }

  choose(repos: string[] | null): void {
    const every = this.watching.every((repo) => repos?.includes(repo));
    const asked = repos?.length && !every ? repos.join(',') : null;
    this.keepChosen(asked);
    void this.router.transitionTo({ queryParams: { repos: asked } });
  }

  private keepChosen(asked: string | null): void {
    this.remembered = asked;
    remember(asked);
  }

  get wall(): WallSection[] {
    return this.shown.sections;
  }

  get needYou(): number {
    return this.shown.needYou;
  }

  get hidden(): number {
    return this.shown.hidden;
  }

  private get shown(): Shown {
    const wall = wallOf(this.groups, this.prs, this.threads, this.operations);
    return shownOf(wall, this.chosen);
  }

  conversations(repo: string, number: number): Conversation[] {
    const key = keyOf(repo, number);
    return readOf(this.threads[key], this.operations[key]);
  }

  details(repo: string, number: number, thread: string): Details | null {
    const key = keyOf(repo, number);
    return detailsOf(this.threads[key]?.[thread], this.operations[key]);
  }

  operation(repo: string, number: number, id: string): Operation | undefined {
    return Object.values(this.operations[keyOf(repo, number)] ?? {}).find(
      (one) => one.id === id,
    ) as unknown as Operation | undefined;
  }

  inFlight(repo: string, number: number): Operation[] {
    const key = keyOf(repo, number);
    const held = this.operations[key] ?? {};
    return (this.prs[key]?.in_flight ?? []).flatMap((id) => {
      const one = held[id];
      return one ? [one as unknown as Operation] : [];
    });
  }

  proposal(repo: string, number: number, thread: string): Proposal | undefined {
    return Object.values(this.proposals[keyOf(repo, number)] ?? {}).findLast(
      (one) => one.conversation === thread,
    );
  }

  diff(commits: Commits): Diff | undefined {
    return this.diffs[commitsOf(commits)];
  }

  files(commits: Commits): FileStat[] | null {
    const diff = this.diff(commits);
    return diff ? filesOf(diff) : null;
  }

  fileLines(query: string): FileLines | undefined {
    return this.lines[query];
  }

  pending(): string[] {
    return pending();
  }

  abandonUnder(prefix: string): void {
    abandonUnder(prefix);
  }

  async ask(feed: Feed, tag: string | null): Promise<Asked> {
    const path = this.pathOf(feed);
    const asking = read<unknown>(path, tag);
    const answer =
      feed.kind === 'wall' ? await this.heldOrNot(asking) : await asking;
    if (!answer.changed) return answer;
    return {
      changed: true,
      tag: answer.tag,
      mark: feed.kind === 'in-flight' ? markOf(answer.body as Operation[]) : '',
      take: () => this.take(feed, answer.body),
    };
  }

  follow(told: Told, pr: Numbered, heard = () => {}): Following {
    const path = `${this.here.prefixOf(pr)}${TOLD_PATHS[told]}`;
    return new EventStream(path, (data) => {
      this.told(told, pr, data);
      heard();
    });
  }

  async readHealth(path: string): Promise<boolean> {
    try {
      const { watcher, ...health } = await fetched<Health>(path);
      this.health = health;
      if (watcher) this.watcher = watcher;
      return true;
    } catch (trouble) {
      void reportError('health', trouble);
      return false;
    }
  }

  async answers(path: string): Promise<boolean> {
    try {
      await fetched<Health>(path);
      return true;
    } catch {
      return false;
    }
  }

  async readSetup(): Promise<void> {
    this.setup = await fetched<Setup>('/api/setup');
  }

  async readAccount(login: string): Promise<void> {
    const account = await fetched<SetupAccount>(
      `/api/setup/accounts/${encodeURIComponent(login)}`,
    );
    this.accounts = { ...this.accounts, [login]: account };
  }

  async readRepoChoices(login: string): Promise<void> {
    const { repos } = await fetched<SetupRepoChoices>(
      `/api/setup/accounts/${encodeURIComponent(login)}/repos`,
    );
    this.repoChoices = { ...this.repoChoices, [login]: repos };
  }

  async readRepoByName(login: string, repo: string): Promise<void> {
    const found = await fetched<SetupRepoChoice>(
      `/api/setup/repos/${repo}?login=${encodeURIComponent(login)}`,
    );
    this.named = { ...this.named, [found.repo]: found };
  }

  async readClone(repo: string): Promise<SetupClone> {
    const clone = await fetched<SetupClone>(`/api/setup/clones/${repo}`);
    this.clones = { ...this.clones, [repo]: clone };
    return clone;
  }

  async writeSetup(asked: SetupRequest): Promise<void> {
    const pid = this.health?.pid ?? null;
    const { body, location } = await put<SetupOperation>(
      '/api/setup',
      this.setup?.etag ?? '',
      asked,
    );
    this.setupOperation = body;
    this.restarting = {
      pid,
      operation: location ?? `/api/setup/operations/${body.id}`,
    };
  }

  async moveAside(): Promise<void> {
    const pid = this.health?.pid ?? null;
    const { body } = await posted<MovedAside>(
      '/api/setup:move-aside',
      null,
      {},
    );
    this.movedTo = body.moved_to;
    this.restarting = { pid, operation: null };
  }

  dropSetupOperation(): void {
    this.setupOperation = null;
  }

  async followRestart(): Promise<Restart> {
    const restarting = this.restarting;
    if (!restarting) return 'back';
    if (restarting.operation && this.setupOperation?.state === 'cloning') {
      try {
        this.setupOperation = await fetched<SetupOperation>(
          restarting.operation,
        );
      } catch {
        this.setupOperation = { ...this.setupOperation, state: 'restarting' };
      }
      if (this.setupOperation.state === 'failed') {
        this.restarting = null;
        return 'failed';
      }
      if (this.setupOperation.state === 'cloning') return 'going';
    }
    try {
      const { watcher, ...health } = await fetched<Health>('/api/health');
      if (health.pid === restarting.pid) return 'going';
      this.health = health;
      if (watcher) this.watcher = watcher;
    } catch {
      return 'going';
    }
    this.restarting = null;
    this.movedTo = null;
    this.setupOperation = null;
    return 'back';
  }

  async readTour(): Promise<void> {
    try {
      this.tour = await fetched<Tour>('/api/tour');
    } catch (trouble) {
      void reportError('tour', trouble);
    }
  }

  sawTour(): void {
    this.tour = { due: false };
    void waitForPromise(handed('/api/tour:seen').catch(() => undefined));
  }

  async readHome(): Promise<Numbered> {
    const pull = await fetched<PullRequest>('/api/pull-request');
    const pr = { repo: pull.repo, number: pull.number };
    this.takePullRequest(pr, pull);
    return pr;
  }

  async readThread(pr: Numbered, key: string): Promise<void> {
    const { repo, number } = pr;
    const thread = this.threads[keyOf(repo, number)]?.[key];
    if (!thread) return;
    const version = `${thread.etag} ${thread.updated_at ?? ''}`;
    const at = `${this.here.prefixOf(pr)}${under(key)}`;
    const [comments, operations, proposals] = await Promise.all([
      fetched<Comment[]>(`${at}/comments`),
      fetched<Operation[]>(`${at}/operations`),
      fetched<Proposal[]>(`${at}/proposals`),
    ]);
    this.takeProposals(repo, number, key, proposals);
    this.takeDetails(repo, number, key, version, comments, operations);
  }

  readDiff(commits: Commits): Promise<Drawing> {
    if (this.diff(commits)) return Promise.resolve('answered');
    const key = commitsOf(commits);
    return this.once(`diff ${key}`, async () => {
      const path = this.here.api(`/api/diffs/${key}`);
      try {
        this.takeDiff(await fetched<Diff>(path));
        return 'answered';
      } catch (trouble) {
        void reportError(`read ${path}`, trouble);
        return 'failed';
      }
    });
  }

  readPrDiff(
    pr: Numbered,
    source: DiffSource,
    path: string,
    revalidate = true,
  ): Promise<Read> {
    const known = this.pr(pr.repo, pr.number)?.diffs[source];
    if (known && !revalidate) return Promise.resolve('unchanged');
    return this.once(path, async () => {
      try {
        const answer = await read<Diff>(path, this.tags[path]);
        if (!answer.changed) return 'unchanged';
        this.tags[path] = answer.tag;
        this.takeDiff(answer.body);
        const { base, head } = answer.body;
        this.changePr(pr.repo, pr.number, (held) => ({
          ...held,
          diffs: { ...held.diffs, [source]: { base, head } },
        }));
        return known ? 'updated' : 'answered';
      } catch (trouble) {
        void reportError(`read ${path}`, trouble);
        return known ? 'unchanged' : 'failed';
      }
    });
  }

  readLines(query: string): Promise<Read> {
    if (this.lines[query]) return Promise.resolve('unchanged');
    const path = this.here.api(`/api/files?${query}`);
    return this.once(path, async () => {
      try {
        const lines = await fetched<FileLines>(path);
        this.lines = { ...this.lines, [query]: lines };
        return 'answered';
      } catch (trouble) {
        void reportError(`read ${path}`, trouble);
        return 'failed';
      }
    });
  }

  async readOperation(pr: Numbered, path: string): Promise<void> {
    const going = await fetched<Operation>(path);
    this.takeAnswer(pr, going);
  }

  async readSessions(pr: Numbered): Promise<void> {
    const listing = await fetched<TerminalSessionList>(
      this.here.api('/api/terminal/sessions'),
    );
    this.takeSessions(pr, listing);
  }

  async openSession(pr: Numbered, keys: string): Promise<void> {
    const { body } = await posted<TerminalSessionList>(
      this.here.api('/api/terminal/sessions'),
      null,
      { keys },
    );
    this.takeSessions(pr, body);
  }

  async decide(
    pr: Numbered,
    key: string,
    verb: string,
    etag: string,
    body: Record<string, unknown>,
  ): Promise<() => void> {
    const outcome = await write<Outcome>(
      this.here.api(`${under(key)}/operations:${verb}`),
      etag,
      body,
    );
    return () => this.takeOutcome(pr, outcome);
  }

  async createDraft(pr: Numbered, draft: unknown): Promise<string | null> {
    const made = await write<Operation>(
      this.here.api('/api/operations:create-draft'),
      null,
      draft,
    );
    this.takeAnswer(pr, made);
    return made.conversation;
  }

  async sendReview(pr: Numbered, review: unknown): Promise<Sent> {
    const prefix = this.here.prefix;
    const { body, location } = await posted<Operation>(
      `${prefix}/api/operations:send-review`,
      null,
      review,
    );
    this.takeAnswer(pr, body);
    return {
      id: body.id,
      location:
        location ?? `${prefix}/api/operations/${encodeURIComponent(body.id)}`,
    };
  }

  hand(path: string, body?: unknown): Promise<void> {
    return handed(path, body);
  }

  async runGit(path: string, keys: string): Promise<GitRun> {
    return (await posted<GitRun>(path, null, { keys })).body;
  }

  markSeen(key: string): void {
    void waitForPromise(
      handed(this.here.api(`${under(key)}/seen`), {}).catch(() => undefined),
    );
  }

  private once<T extends Read>(key: string, asking: () => Promise<T>) {
    this.asking[key] ??= asking().finally(() => {
      delete this.asking[key];
    });
    return this.asking[key] as Promise<T>;
  }

  private pathOf(feed: Feed): string {
    const path = FEED_PATHS[feed.kind];
    return 'pr' in feed ? `${this.here.prefixOf(feed.pr)}${path}` : path;
  }

  private async heldOrNot<T>(asking: Promise<T>): Promise<T> {
    try {
      const answer = await asking;
      this.unheld = null;
      this.configProblem = null;
      return answer;
    } catch (trouble) {
      const unheld = unheldBy(trouble);
      if (unheld) {
        this.unheld = unheld;
        this.configProblem =
          unheld === 'not-watching' ? (trouble as Refusal).detail : null;
      }
      throw trouble;
    }
  }

  private takeLedger({ watcher, ...ledger }: RunLedger): void {
    this.ledger = ledger;
    this.watcher = watcher;
  }

  private take(feed: Feed, body: unknown): boolean {
    switch (feed.kind) {
      case 'wall':
        this.takeWall(body as HeldPullRequests);
        return true;
      case 'runs':
        this.takeLedger(body as RunLedger);
        return true;
      case 'dashboard':
        this.drawnInto(feed.pr, body as Dashboard);
        return true;
      case 'pull-request':
        this.takePullRequest(feed.pr, body as PullRequest);
        return true;
      case 'viewer':
        this.viewer = (body as Person).login;
        return true;
      case 'people':
        this.takePeople(body as Person[]);
        return true;
      case 'conversations':
        this.takeConversations(feed.pr, body as ConversationList);
        return true;
      case 'in-flight':
        this.takeInFlight(feed.pr, body as Operation[]);
        return true;
    }
  }

  private told(told: Told, pr: Numbered, data: unknown): void {
    if (told === 'dashboard') {
      this.drawnInto(pr, data as Dashboard);
      return;
    }
    const held = this.manager(pr);
    const now =
      told === 'notes'
        ? { ...held, notes: (data as ManagerChanges).markdown }
        : {
            ...held,
            output: carried(held.output, (data as AgentOutput).lines),
          };
    this.managers = { ...this.managers, [keyOf(pr.repo, pr.number)]: now };
  }

  private takeSessions(pr: Numbered, listing: TerminalSessionList): void {
    this.managers = {
      ...this.managers,
      [keyOf(pr.repo, pr.number)]: {
        ...this.manager(pr),
        sessions: listing.sessions,
      },
    };
  }

  private takePullRequest(pr: Numbered, pull: PullRequest): void {
    this.changePr(pr.repo, pr.number, (held) => ({
      ...held,
      title: pull.title ?? held.title,
      url: pull.html_url,
      branch: pull.branch ?? held.branch,
      head_sha: pull.head_sha ?? held.head_sha,
    }));
  }

  private takePeople(people: Person[]): void {
    this.names = {
      ...this.names,
      ...Object.fromEntries(people.map((one) => [one.login, one.name])),
    };
  }

  private takeConversations(
    { repo, number }: Numbered,
    list: ConversationList,
  ): void {
    this.mergeThreads(
      keyOf(repo, number),
      list.conversations,
      list.listed_at,
      true,
    );
    this.changePr(repo, number, (held) => ({
      ...held,
      unreadable: list.unreadable,
    }));
  }

  private mergeThreads(
    key: string,
    arrived: Arriving[],
    listedAt: string | null,
    ordered: boolean,
  ): void {
    const held = this.threads[key] ?? {};
    const named = new Map(arrived.map((one) => [one.key, one]));
    const kept = Object.values(held).filter(
      (one) => named.has(one.key) || savedAfter(one.updated_at, listedAt),
    );
    const order = ordered
      ? [
          ...kept.filter((one) => !named.has(one.key)).map((one) => one.key),
          ...named.keys(),
        ]
      : [
          ...kept.map((one) => one.key),
          ...[...named.keys()].filter((one) => !(one in held)),
        ];
    const taken = new Map<string, Merged>();
    for (const [thread, one] of named) {
      taken.set(
        thread,
        threadMerged(held[thread], { ...one, provisional: false }),
      );
    }
    this.threads = {
      ...this.threads,
      [key]: Object.fromEntries(
        order.map((thread) => [
          thread,
          taken.get(thread)?.thread ?? held[thread]!,
        ]),
      ),
    };
    for (const under of [false, true]) {
      this.mergeOperations(
        key,
        [...taken.values()]
          .filter((one) => one.under === under)
          .flatMap((one) => one.operations),
        under,
      );
    }
  }

  private mergeOperations(
    key: string,
    arrived: StoredOperation[],
    under = false,
  ): void {
    if (!arrived.length) return;
    this.operations = {
      ...this.operations,
      [key]: operationsMerged(this.operations[key], arrived, under),
    };
  }

  private takeOutcome(
    pr: Numbered,
    { operation, conversation }: Outcome,
  ): void {
    const { repo, number } = pr;
    this.takeAnswer(pr, operation);
    const key = keyOf(repo, number);
    const held = this.threads[key] ?? {};
    const taken = threadMerged(held[conversation.key], {
      ...conversation,
      provisional: true,
    });
    this.threads = {
      ...this.threads,
      [key]: { ...held, [conversation.key]: taken.thread },
    };
    this.mergeOperations(key, taken.operations, taken.under);
    this.place(repo, number);
  }

  private takeAnswer({ repo, number }: Numbered, operation: Operation): void {
    this.mergeOperations(keyOf(repo, number), [operation]);
    this.place(repo, number);
  }

  private takeDetails(
    repo: string,
    number: number,
    thread: string,
    version: string,
    comments: Comment[],
    operations: Operation[],
  ): void {
    const key = keyOf(repo, number);
    const held = this.threads[key]?.[thread];
    if (!held) return;
    this.threads = {
      ...this.threads,
      [key]: {
        ...this.threads[key],
        [thread]: {
          ...held,
          comments: commentsRead(held.comments, comments),
          read: version,
        },
      },
    };
    this.mergeOperations(key, operations);
    this.place(repo, number);
  }

  private takeInFlight(
    { repo, number }: Numbered,
    operations: Operation[],
  ): void {
    this.mergeOperations(keyOf(repo, number), operations);
    this.changePr(repo, number, (held) => ({
      ...held,
      in_flight: operations.map(operationKey),
    }));
  }

  private takeProposals(
    repo: string,
    number: number,
    thread: string,
    proposals: Proposal[],
  ): void {
    const key = keyOf(repo, number);
    const held = this.proposals[key] ?? {};
    const others = Object.entries(held).filter(
      ([, one]) => one.conversation !== thread,
    );
    this.proposals = {
      ...this.proposals,
      [key]: Object.fromEntries([
        ...others,
        ...proposals.map((one) => [
          one.id,
          merged(held[one.id], one, (proposal) => proposal.updated_at),
        ]),
      ]) as Record<string, Proposal>,
    };
  }

  private takeDiff(diff: Diff): void {
    this.diffs = { ...this.diffs, [commitsOf(diff)]: diff };
  }

  private drawnInto({ repo, number }: Numbered, dashboard: Dashboard): void {
    const { facts, manager, threads, listed_at, pr } = dashboard;
    this.mergeThreads(keyOf(repo, number), threads, listed_at, false);
    const drawn: Drawn = {
      polled: dashboard.polled,
      status: dashboard.status,
      system: dashboard.system,
      frozen: dashboard.frozen,
      undismiss_command: dashboard.undismiss_command,
      notice: dashboard.notice,
      drawn_at: listed_at,
    };
    this.changePr(repo, number, (held) => {
      const stale =
        held.drawn !== null && older(listed_at, held.drawn.drawn_at);
      return {
        ...held,
        ...(stale
          ? {}
          : {
              title: pr.title ?? held.title,
              url: pr.url ?? held.url,
              branch: pr.branch ?? held.branch,
              ticket: pr.ticket,
              author: pr.author,
              drawn,
            }),
        facts: facts
          ? merged(held.facts, facts, (polled) => polled.polled_at)
          : held.facts,
        flags: merged(held.flags, manager, (flags) => flags.changed_at),
      };
    });
  }

  private takeWall(held: HeldPullRequests): void {
    shelve(held);
    this.watching = held.watching;
    this.groups = held.groups;
    const rows = [...held.pull_requests].sort(
      (one, other) =>
        one.repo.localeCompare(other.repo) || one.number - other.number,
    );
    for (const row of rows) {
      this.drawnInto(row, row.dashboard);
      this.changePr(row.repo, row.number, (pr) => ({
        ...pr,
        board_url: row.board_url,
        board_answered: row.board_answered,
      }));
      this.place(row.repo, row.number, true);
    }
    const onTheWall = new Set(rows.map((row) => keyOf(row.repo, row.number)));
    const left = Object.entries(this.prs).filter(
      ([key, pr]) => pr.place !== null && !onTheWall.has(key),
    );
    if (!left.length) return;
    this.prs = {
      ...this.prs,
      ...Object.fromEntries(
        left.map(([key, pr]) => [key, { ...pr, place: null }]),
      ),
    };
  }

  opened(repo: string, number: number): void {
    const place = this.pr(repo, number)?.place;
    if (!place?.moved) return;
    this.changePr(repo, number, (pr) => ({
      ...pr,
      place: { ...place, moved: false },
    }));
  }

  private changePr(
    repo: string,
    number: number,
    changed: (held: PrEntity) => PrEntity,
  ): void {
    const key = keyOf(repo, number);
    const held = this.prs[key] ?? {
      repo,
      number,
      title: null,
      url: null,
      branch: null,
      head_sha: null,
      ticket: null,
      author: null,
      board_url: null,
      board_answered: false,
      facts: null,
      flags: null,
      drawn: null,
      place: null,
      unreadable: [],
      in_flight: [],
      diffs: {},
    };
    this.prs = { ...this.prs, [key]: changed(held) };
    this.place(repo, number);
  }

  private place(repo: string, number: number, joining = false): void {
    const key = keyOf(repo, number);
    const pr = this.prs[key];
    const summary = summaryOf(pr, this.threads[key], this.operations[key]);
    if (!pr || !summary || (!pr.place && !joining)) return;
    const place = placeOf(pr.place, summary, () => this.joins++);
    if (place === pr.place) return;
    this.prs = { ...this.prs, [key]: { ...pr, place } };
  }
}
