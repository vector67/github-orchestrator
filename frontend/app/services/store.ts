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
  DiffAnchors,
  Emoji,
  EmojiList,
  FileLines,
  FrozenWorktree,
  GitRun,
  HarvestExtensionFolder,
  Health,
  HeldPullRequests,
  ManagerChanges,
  ManagerFlags,
  ManagerStanding,
  MentionableList,
  Mentions,
  Operation,
  OperationKind,
  Outcome,
  MovedAside,
  Person,
  PrFacts,
  PrSummary,
  Proposal,
  PullRequest,
  PullRequestCommits,
  ReadMark,
  ReadMarks,
  ResetRequest,
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
  opensTerminal,
  settledBy,
  slotOf,
  type PrVerb,
  type SetupWrite,
} from 'frontend/data/decisions';
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
import {
  notHeldBy,
  Refusal,
  unheldBy,
  type Unheld,
} from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { MOVED, tried, type Tried } from 'frontend/data/tried';
import { EventStream, type StreamState } from 'frontend/data/stream';
import {
  detailsOf,
  enteredAt,
  filesOf,
  heldOf,
  mentionableOf,
  outstandingOf,
  placeOf,
  prHeaderOf,
  readOf,
  resetStandingOf,
  shownOf,
  stepperOf,
  commitNoteOf,
  mergeNoteOf,
  pickedRangeOf,
  timelineOf,
  summaryOf,
  summaryTabOf,
  tickedOn,
  wallOf,
  type Entered,
  type Outstanding,
  type Place,
  type PrHeader,
  type ResetStanding,
  type Shown,
  type Stepper,
  type CommitNote,
  type DiffRange,
  type Looking,
  type MergeNote,
  type PickedRange,
  type Summaries,
  type SummaryTab,
  type WallSection,
} from 'frontend/data/summaries';
import type { Picked, Timeline } from 'frontend/data/timeline';
import type { Numbered } from 'frontend/data/wall';
import type HereService from 'frontend/services/here';
import { DOWN } from 'frontend/services/reachability';

export type {
  Flag,
  Move,
  NextMove,
  Outstanding,
  OutstandingGroup,
  OutstandingItem,
  PrHeader,
  ResetStanding,
  Summaries,
  Pip,
  PipState,
  Stepper,
  CommitNote,
  DiffRange,
  Looking,
  MergeNote,
  PickedRange,
  SummaryState,
  SummaryTab,
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
  standing: ManagerStanding;
  drawn_at: string | null;
}

export type DiffSource = 'origin' | 'local';

export interface PrEntity {
  repo: string;
  number: number;
  title: string | null;
  url: string | null;
  branch: string | null;
  base_branch: string | null;
  head_sha: string | null;
  created_at: string | null;
  commits: number | null;
  additions: number;
  deletions: number;
  ticket: string | null;
  author: string | null;
  board_url: string | null;
  facts: PrFacts | null;
  flags: ManagerFlags | null;
  drawn: Drawn | null;
  place: Place | null;
  unreadable: string[];
  in_flight: string[];
  sent: string[];
  diffs: Partial<Record<DiffSource, Commits>>;
  history: Partial<Record<DiffSource, PullRequestCommits>>;
  read: ReadMark[] | null;
  mismatches: number | null;
}

export type ShownPr = PrEntity & { drawn: Drawn };

export type PrSummaryEntity = Omit<PrSummary, 'mismatches'>;

export interface Manager {
  notes: string | null;
  output: HeardLine[];
  sessions: TerminalSession[];
}

export type Feed =
  | { kind: 'wall' }
  | { kind: 'runs' }
  | { kind: 'mentions' }
  | { kind: 'dashboard'; pr: Numbered }
  | { kind: 'pull-request'; pr: Numbered }
  | { kind: 'viewer'; pr: Numbered }
  | { kind: 'people'; pr: Numbered }
  | { kind: 'conversations'; pr: Numbered }
  | { kind: 'in-flight'; pr: Numbered }
  | { kind: 'summary'; pr: Numbered };

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

type ByKey<T> = Record<string, Record<string, T>>;

const SHELVED_WALL = 'hub-pull-requests';

const CHOSEN_REPOS = 'hub-repos';

const SECTIONS_ENTERED = 'hub-sections-entered';

const SUMMARY_MOVED =
  'The summary moved before your click reached the board. It has been read ' +
  'again; look at it before you press.';

const CONFIG_MOVED =
  'The config changed since this page read it. Check your choices and save again.';

const READ_MARKS = '/api/pull-request/read-marks';

const UNREAD_HEAD = 'the page has not read the worktree’s commits yet';

const NO_MANAGER: Manager = { notes: null, output: [], sessions: [] };

const FEED_PATHS: Record<Feed['kind'], string> = {
  wall: '/api/pull-requests',
  runs: '/api/runs',
  mentions: '/api/mentions',
  dashboard: '/api/dashboard',
  'pull-request': '/api/pull-request',
  viewer: '/api/viewer',
  people: '/api/people',
  conversations: '/api/conversations',
  'in-flight': '/api/operations',
  summary: '/api/summary',
};

const TOLD_PATHS: Record<Told, string> = {
  dashboard: '/api/dashboard/stream',
  notes: '/api/manager/changes/stream',
  output: '/api/manager/agent-output/stream?lines=200',
};

function keyOf(repo: string, number: number): string {
  return `${repo}#${number}`;
}

export function commitsOf(commits: DiffRange): string {
  const range = `${commits.base}..${commits.head}`;
  return commits.merged ? `${range}?merged=${commits.merged}` : range;
}

function anchorsOf(range: DiffRange, onto: Commits): string {
  const anchors = `${range.base}..${range.head}/anchors/${onto.base}..${onto.head}`;
  return range.merged ? `${anchors}?merged=${range.merged}` : anchors;
}

function markOf(operations: Operation[]): string {
  return operations.map((one) => `${one.id}:${one.state}`).join('|');
}

function listsOf(facts: PrFacts): PrFacts {
  const list = <T>(one: T[]): T[] => (Array.isArray(one) ? one : []);
  return {
    ...facts,
    changes_requested_by: list(facts.changes_requested_by),
    pending_reviewers: list(facts.pending_reviewers),
    mentions: list(facts.mentions),
  };
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
    const threaded = held.pull_requests.every((row) =>
      Array.isArray(row.dashboard.threads as unknown),
    );
    if (!threaded) return null;
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

function unshelve(): void {
  try {
    localStorage.removeItem(SHELVED_WALL);
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

function recalledEntries(): Record<string, Entered> {
  try {
    const raw = localStorage.getItem(SECTIONS_ENTERED);
    const entries: unknown = raw ? JSON.parse(raw) : {};
    return entries && typeof entries === 'object'
      ? (entries as Record<string, Entered>)
      : {};
  } catch {
    return {};
  }
}

function rememberEntries(entries: Record<string, Entered>): void {
  try {
    localStorage.setItem(SECTIONS_ENTERED, JSON.stringify(entries));
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
  @tracked private prSummaries: Record<string, PrSummaryEntity> = {};
  @tracked private lost: Record<string, boolean> = {};
  @tracked private diffs: Record<string, Diff> = {};
  @tracked private anchored: Record<string, DiffAnchors> = {};
  @tracked private lines: Record<string, FileLines> = {};
  @tracked private managers: Record<string, Manager> = {};
  @tracked private groups: WallGroupName[] | null = null;
  @tracked watching: string[] = [];
  @tracked ledger: Omit<RunLedger, 'watcher'> | null = null;
  @tracked mentions: Mentions | null = null;
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
  @tracked setupWrite: {
    write: StoredOperation | null;
    fields: Record<string, string>;
  } = { write: null, fields: {} };
  @tracked tour: Tour | null = null;
  @tracked harvestExtension: {
    write: StoredOperation | null;
    folder: string | null;
  } = { write: null, folder: null };
  @tracked emojis: Emoji[] = [];
  @tracked private assignable: Record<string, string[]> = {};
  private assignableAsked = new Set<string>();
  private restarting: Restarting | null = null;

  private joins = 0;
  private sends = 0;
  private entries: Record<string, Entered> = recalledEntries();
  private tags: Record<string, string | null> = {};
  private asking: Record<string, Promise<Read>> = {};

  constructor(owner: Owner) {
    super(owner);
    const held = unshelved();
    if (held) this.replayShelf(held);
    this.router.on('routeDidChange', () => {
      const asked = askedIn(this.router);
      if (asked && asked !== this.remembered) this.keepChosen(asked);
    });
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

  resetStanding(repo: string, number: number): ResetStanding | null {
    return resetStandingOf(
      this.prs[keyOf(repo, number)]?.drawn?.system.reset_to_origin,
    );
  }

  outstanding(repo: string, number: number): Outstanding | null {
    const key = keyOf(repo, number);
    const pr = this.prs[key];
    return pr ? outstandingOf(pr, this.threads[key]) : null;
  }

  prHeader(repo: string, number: number): PrHeader | null {
    const pr = this.prs[keyOf(repo, number)];
    return pr ? prHeaderOf(pr) : null;
  }

  notHeld(repo: string, number: number): boolean {
    return this.lost[keyOf(repo, number)] === true;
  }

  prSummary(repo: string, number: number): SummaryTab | null {
    const key = keyOf(repo, number);
    const held = this.prSummaries[key];
    const role = this.summary(repo, number)?.role ?? null;
    const head = this.prs[key]?.head_sha ?? null;
    return held ? summaryTabOf(held, head, role) : null;
  }

  async summarise(
    pr: Numbered,
    verb: 'summarise' | 'summarise-with-github-api',
  ): Promise<void> {
    const at = `${this.here.prefixOf(pr)}${FEED_PATHS.summary}`;
    const etag = this.prSummaries[keyOf(pr.repo, pr.number)]?.etag ?? null;
    const { taken, local } = await this.sendOn(
      pr,
      verb,
      () => posted<PrSummary>(`${at}/operations:${verb}`, etag, {}),
      `${verb} ${at}`,
    );
    if (taken.done) {
      this.takePrSummary(pr, taken.body.body);
      this.drop(pr, local);
      return;
    }
    if (taken.code === MOVED) {
      this.refuse(pr, local, await this.summaryReadAgain(pr, at), MOVED);
    }
  }

  private async summaryReadAgain(pr: Numbered, at: string): Promise<string> {
    try {
      this.takePrSummary(pr, await fetched<PrSummary>(at));
      return SUMMARY_MOVED;
    } catch (trouble) {
      void reportError(`read ${at} again`, trouble);
      return DOWN;
    }
  }

  get chosen(): string[] | null {
    const asked = askedIn(this.router) ?? this.remembered;
    const known = (asked ?? '')
      .split(',')
      .filter((repo) => this.watching.includes(repo));
    return known.length ? known : null;
  }

  get severalReposShown(): boolean {
    return (this.chosen ?? this.watching).length > 1;
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

  get heldCount(): number {
    return heldOf(this.prs);
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

  inFlight(repo: string, number: number): Operation[] {
    const key = keyOf(repo, number);
    const held = this.operations[key] ?? {};
    const pr = this.prs[key];
    const listed = new Set([
      ...(pr?.in_flight ?? []),
      ...(pr?.sent ?? []).map((id) => operationKey({ id, conversation: null })),
    ]);
    return [...listed].flatMap((id) => {
      const one = held[id];
      return one ? [one as unknown as Operation] : [];
    });
  }

  proposal(repo: string, number: number, thread: string): Proposal | undefined {
    return Object.values(this.proposals[keyOf(repo, number)] ?? {}).findLast(
      (one) => one.conversation === thread,
    );
  }

  diff(commits: DiffRange): Diff | undefined {
    return this.diffs[commitsOf(commits)];
  }

  anchors(range: DiffRange, onto: Commits): DiffAnchors | undefined {
    return this.anchored[anchorsOf(range, onto)];
  }

  stepper(
    pr: Numbered,
    source: DiffSource,
    chosen: string | null,
    picked: Picked | null,
    skipMerges: boolean,
    across: number,
  ): Stepper | null | undefined {
    const held = this.pr(pr.repo, pr.number);
    const stepper =
      held &&
      stepperOf(
        held.history[source],
        held.read,
        chosen,
        held.facts?.my_review_sha ?? null,
        picked,
        skipMerges,
        source === 'local' ? held.history.origin : undefined,
        across,
      );
    const mark = this.summary(pr.repo, pr.number)?.pressing.read;
    return stepper && mark ? tickedOn(stepper, mark) : stepper;
  }

  pickedRange(
    pr: Numbered,
    source: DiffSource,
    picked: Picked | null,
  ): PickedRange | null {
    const held = this.pr(pr.repo, pr.number);
    return held ? pickedRangeOf(held.history[source], picked) : null;
  }

  timeline(
    pr: Numbered,
    source: DiffSource,
    looking: Looking,
  ): Timeline | null | undefined {
    const held = this.pr(pr.repo, pr.number);
    if (!held) return undefined;
    const based = Object.values(this.prs).find(
      (one) =>
        one.repo === held.repo &&
        one.number !== held.number &&
        one.branch !== null &&
        one.branch === held.base_branch,
    );
    return timelineOf(
      held,
      held.history[source],
      looking,
      based?.number ?? null,
      source === 'local' ? held.history.origin : undefined,
    );
  }

  commitNote(pr: Numbered, source: DiffSource): CommitNote | null {
    const held = this.pr(pr.repo, pr.number);
    return held
      ? commitNoteOf(held.history[source], held.facts, held.read)
      : null;
  }

  mergeNote(merge: DiffRange): MergeNote | null {
    const { base, head } = merge;
    return mergeNoteOf(this.files(merge), this.files({ base, head }));
  }

  files(commits: DiffRange): FileStat[] | null {
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
      feed.kind === 'wall'
        ? await this.heldOrNot(asking)
        : 'pr' in feed
          ? await this.heldHere(feed.pr, this.heldOrNot(asking))
          : await asking;
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

  checkAccount(login: string): Promise<boolean> {
    const at = `/api/setup/accounts/${encodeURIComponent(login)}`;
    return this.sendSetup('check-account', async () => {
      const account = await fetched<SetupAccount>(at);
      this.accounts = { ...this.accounts, [login]: account };
      const { repos } = await fetched<SetupRepoChoices>(`${at}/repos`);
      this.repoChoices = { ...this.repoChoices, [login]: repos };
    });
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

  writeSetup(asked: SetupRequest): Promise<boolean> {
    const pid = this.health?.pid ?? null;
    return this.sendSetup('write-setup', async () => {
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
    });
  }

  moveAside(): Promise<boolean> {
    const pid = this.health?.pid ?? null;
    return this.sendSetup('move-aside', async () => {
      const { body } = await posted<MovedAside>(
        '/api/setup:move-aside',
        null,
        {},
      );
      this.movedTo = body.moved_to;
      this.restarting = { pid, operation: null };
    });
  }

  private async sendSetup(
    kind: SetupWrite,
    asking: () => Promise<void>,
  ): Promise<boolean> {
    const write = this.sending(null, kind, null);
    this.setupWrite = { write, fields: {} };
    try {
      await asking();
      this.setupWrite = { write: null, fields: {} };
      return true;
    } catch (trouble) {
      void reportError(kind, trouble);
      this.setupWrite = {
        write: {
          ...write,
          state: 'refused',
          reason: await this.setupRefusal(trouble),
        },
        fields: trouble instanceof Refusal ? trouble.fields : {},
      };
      return false;
    }
  }

  private async setupRefusal(trouble: unknown): Promise<string | null> {
    if (!(trouble instanceof Refusal)) return DOWN;
    if (trouble.code === MOVED) {
      return this.readSetup().then(
        () => CONFIG_MOVED,
        () => DOWN,
      );
    }
    if (Object.keys(trouble.fields).length) {
      return trouble.fields['config'] ?? null;
    }
    return trouble.detail;
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

  async readEmojis(): Promise<void> {
    try {
      this.emojis = (await fetched<EmojiList>('/api/emojis')).emojis;
    } catch (trouble) {
      void reportError('emojis', trouble);
    }
  }

  mentionable(pr: Numbered): Person[] {
    const key = keyOf(pr.repo, pr.number);
    return mentionableOf(
      this.prs[key],
      this.threads[key],
      this.assignable[pr.repo] ?? [],
      this.names,
    );
  }

  readMentionable(pr: Numbered): void {
    if (this.assignableAsked.has(pr.repo)) return;
    this.assignableAsked.add(pr.repo);
    const at = `${this.here.prefixOf(pr)}/api/mentionable`;
    void waitForPromise(
      fetched<MentionableList>(at).then(
        ({ logins }) => {
          this.assignable = { ...this.assignable, [pr.repo]: logins };
        },
        (trouble: unknown) => reportError('mentionable', trouble),
      ),
    );
  }

  async prepareHarvestExtension(): Promise<void> {
    const write = this.sending(null, 'prepare-harvest-extension', null);
    this.harvestExtension = { ...this.harvestExtension, write };
    const prepared = await tried(
      'prepare /api/harvest-extension:prepare',
      posted<HarvestExtensionFolder>(
        '/api/harvest-extension:prepare',
        null,
        {},
      ),
    );
    this.harvestExtension = prepared.done
      ? { write: null, folder: prepared.body.body.folder }
      : {
          ...this.harvestExtension,
          write: { ...write, state: 'refused', reason: prepared.why },
        };
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

  readDiff(commits: DiffRange): Promise<Drawing> {
    if (this.diff(commits)) return Promise.resolve('answered');
    const key = commitsOf(commits);
    return this.once(`diff ${key}`, async () => {
      const path = this.here.api(`/api/diffs/${key}`);
      try {
        this.takeDiff(await fetched<Diff>(path), key);
        return 'answered';
      } catch (trouble) {
        void reportError(`read ${path}`, trouble);
        return 'failed';
      }
    });
  }

  readAnchors(range: DiffRange, onto: Commits): Promise<Drawing> {
    if (this.anchors(range, onto)) return Promise.resolve('answered');
    const key = anchorsOf(range, onto);
    return this.once(`anchors ${key}`, async () => {
      const path = this.here.api(`/api/diffs/${key}`);
      try {
        const anchors = await fetched<DiffAnchors>(path);
        this.anchored = { ...this.anchored, [key]: anchors };
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

  readPrCommits(pr: Numbered, source: DiffSource): Promise<Read> {
    const path = `${this.here.prefixOf(pr)}/api/pull-request/commits?source=${source}`;
    return this.readTagged<PullRequestCommits>(path, (history) =>
      this.changePr(pr.repo, pr.number, (held) => ({
        ...held,
        history: { ...held.history, [source]: history },
      })),
    );
  }

  readReadMarks(pr: Numbered): Promise<Read> {
    const path = `${this.here.prefixOf(pr)}${READ_MARKS}`;
    return this.readTagged<ReadMarks>(path, ({ marks }) =>
      this.changePr(pr.repo, pr.number, (held) => ({ ...held, read: marks })),
    );
  }

  async resetToOrigin(
    pr: Numbered,
    verb:
      'reset-to-origin' | 'queue-reset-to-origin' | 'cancel-reset-to-origin',
  ): Promise<Tried<() => void>> {
    const head =
      this.pr(pr.repo, pr.number)?.history.local?.commits.at(-1)?.sha ?? null;
    const asked: ResetRequest | undefined =
      verb === 'reset-to-origin' && head ? { head } : undefined;
    const { taken, local } = await this.sendOn(
      pr,
      verb,
      () =>
        verb === 'reset-to-origin' && !head
          ? Promise.reject(
              new Refusal({
                status: 409,
                code: 'malformed-request',
                detail: UNREAD_HEAD,
              }),
            )
          : handed(
              `${this.here.prefixOf(pr)}/api/pull-request/operations:${verb}`,
              asked,
            ),
      `${verb} the worktree`,
    );
    if (!taken.done) return taken;
    const drawn = await this.ask({ kind: 'dashboard', pr }, null).catch(
      () => null,
    );
    if (drawn?.changed) drawn.take();
    return { done: true, body: () => this.drop(pr, local) };
  }

  async markRead(pr: Numbered, sha: string, marked: boolean): Promise<void> {
    const verb = marked ? 'mark-read' : 'mark-unread';
    const { taken, local } = await this.sendOn(
      pr,
      verb,
      () =>
        write<ReadMarks>(
          `${this.here.prefixOf(pr)}${READ_MARKS}/operations:${verb}`,
          null,
          { sha },
        ),
      'mark a commit read',
      sha,
    );
    if (!taken.done) return;
    this.changePr(pr.repo, pr.number, (held) => ({
      ...held,
      read: taken.body.marks,
    }));
    this.drop(pr, local);
  }

  private readTagged<T>(path: string, take: (body: T) => void): Promise<Read> {
    return this.once(path, async () => {
      try {
        const answer = await read<T>(path, this.tags[path]);
        if (!answer.changed) return 'unchanged';
        this.tags[path] = answer.tag;
        take(answer.body);
        return 'answered';
      } catch (trouble) {
        void reportError(`read ${path}`, trouble);
        return 'failed';
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

  async readOperation(pr: Numbered, id: string): Promise<Operation> {
    const going = await fetched<Operation>(
      `${this.here.prefixOf(pr)}/api/operations/${encodeURIComponent(id)}`,
    );
    this.takeAnswer(pr, going);
    if (going.state === 'applied') {
      this.markSent(
        pr,
        null,
        this.sentOn(pr, null).filter((one) => one !== going.id),
      );
    }
    return going;
  }

  async readSessions(pr: Numbered): Promise<void> {
    const listing = await fetched<TerminalSessionList>(
      this.here.api('/api/terminal/sessions'),
    );
    this.takeSessions(pr, listing);
  }

  async openSession(pr: Numbered, keys: string): Promise<Tried<void>> {
    const { taken, local } = await this.sendOn(
      pr,
      'open-session',
      () =>
        posted<TerminalSessionList>(
          this.here.api('/api/terminal/sessions'),
          null,
          {
            keys,
          },
        ),
      'terminal',
      keys,
    );
    return this.listed(pr, taken, local);
  }

  async askTheAgent(
    pr: Numbered,
    prompt: string,
    about: string | null,
  ): Promise<Tried<void>> {
    const asking = () =>
      posted<TerminalSessionList>(
        `${this.here.prefixOf(pr)}/api/terminal/questions`,
        null,
        { prompt },
      );
    const { taken, local } =
      about === null
        ? await this.sendOn(pr, 'ask-the-agent', asking, 'terminal')
        : await this.sendHeld(
            pr,
            this.hold(pr, this.sending(about, 'ask-the-agent', null)),
            asking,
            'terminal',
          );
    return this.listed(pr, taken, local);
  }

  private listed(
    pr: Numbered,
    taken: Tried<{ body: TerminalSessionList }>,
    local: StoredOperation,
  ): Tried<void> {
    if (!taken.done) return taken;
    this.drop(pr, local);
    this.takeSessions(pr, taken.body.body);
    return { done: true, body: undefined };
  }

  async decide(
    pr: Numbered,
    key: string,
    kind: string,
    verb: string,
    etag: string,
    body: Record<string, unknown>,
  ): Promise<Tried<() => void>> {
    const local = opensTerminal(kind)
      ? await this.listing(
          pr,
          this.hold(pr, this.sending(key, kind, body['body'])),
        )
      : this.hold(pr, this.sending(key, kind, body['body']));
    const written = await tried(
      'write',
      write<Outcome>(
        this.here.api(`${under(key)}/operations:${verb}`),
        etag,
        body,
      ),
    );
    if (!written.done) {
      this.refuse(pr, local, written.why, written.code);
      return written;
    }
    return {
      done: true,
      body: () => this.takeOutcome(pr, written.body, local),
    };
  }

  async createDraft(pr: Numbered, draft: unknown): Promise<string | null> {
    const local = this.hold(pr, this.sending(null, 'create-draft', null));
    const made = await tried(
      'write',
      write<Operation>(
        `${this.here.prefixOf(pr)}/api/operations:create-draft`,
        null,
        draft,
      ),
    );
    if (!made.done) {
      this.refuse(pr, local, made.why, made.code);
      return null;
    }
    this.drop(pr, local);
    this.takeAnswer(pr, made.body);
    return made.body.conversation;
  }

  async sendReview(pr: Numbered, review: unknown): Promise<void> {
    const local = this.hold(pr, this.sending(null, 'send-review', null));
    const answer = await tried(
      'review',
      posted<Operation>(
        `${this.here.prefixOf(pr)}/api/operations:send-review`,
        null,
        review,
      ),
    );
    if (!answer.done) {
      this.refuse(pr, local, answer.why, answer.code);
      return;
    }
    const going = answer.body.body;
    this.drop(pr, local);
    this.takeAnswer(pr, going);
    this.markSent(pr, null, [...this.sentOn(pr, null), going.id]);
  }

  async press(
    pr: Numbered,
    verb: PrVerb,
    where: string,
    path: string,
    body?: unknown,
  ): Promise<Tried<() => void>> {
    const { taken, local } = await this.sendOn(
      pr,
      verb,
      () => handed(path, body),
      where,
    );
    if (!taken.done) return taken;
    return { done: true, body: () => this.settle(pr, local, true) };
  }

  async runGit(
    pr: Numbered,
    path: string,
    keys: string,
  ): Promise<Tried<GitRun>> {
    const { taken, local } = await this.sendOn(
      pr,
      'git',
      () => posted<GitRun>(path, null, { keys }),
      'manager git',
      keys,
    );
    if (!taken.done) return taken;
    this.drop(pr, local);
    return { done: true, body: taken.body.body };
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

  private async heldHere<T>(pr: Numbered, asking: Promise<T>): Promise<T> {
    const key = keyOf(pr.repo, pr.number);
    try {
      const answer = await asking;
      if (this.lost[key]) this.lost = { ...this.lost, [key]: false };
      return answer;
    } catch (trouble) {
      if (notHeldBy(trouble) && !this.lost[key]) {
        this.lost = { ...this.lost, [key]: true };
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
      case 'mentions':
        this.mentions = body as Mentions;
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
      case 'summary':
        this.takePrSummary(feed.pr, body as PrSummary);
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

  private async listing(
    pr: Numbered,
    local: StoredOperation,
  ): Promise<StoredOperation> {
    try {
      await this.readSessions(pr);
    } catch {
      return local;
    }
    const listed = { ...local, listed: this.sessionIds(pr) };
    this.mergeOperations(keyOf(pr.repo, pr.number), [listed]);
    return listed;
  }

  private sessionIds(pr: Numbered): string[] {
    return this.manager(pr).sessions.map((one) => one.id);
  }

  private settleOpening(pr: Numbered, listing: TerminalSessionList): void {
    const key = keyOf(pr.repo, pr.number);
    const held = this.operations[key] ?? {};
    for (const conversation of Object.keys(this.threads[key] ?? {})) {
      for (const id of this.sentOn(pr, conversation)) {
        const one = held[operationKey({ id, conversation })];
        if (!one || one.state !== 'sent' || one.answer === undefined) continue;
        const answer = held[operationKey({ id: one.answer, conversation })];
        const fresh = listing.sessions.some(
          ({ id: session }) => one.listed && !one.listed.includes(session),
        );
        if (answer?.state === 'refused') {
          this.refuse(pr, one, answer.reason ?? '', answer.reason_code ?? null);
        } else if (fresh || answer?.state === 'applied') {
          this.drop(pr, one);
        }
      }
    }
  }

  private takeSessions(pr: Numbered, listing: TerminalSessionList): void {
    this.settleOpening(pr, listing);
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
      base_branch: pull.base_branch ?? held.base_branch,
      head_sha: pull.head_sha ?? held.head_sha,
      created_at: pull.created_at,
      commits: pull.commits,
      additions: pull.additions,
      deletions: pull.deletions,
    }));
  }

  private takePrSummary(
    { repo, number }: Numbered,
    { mismatches, ...summary }: PrSummary,
  ): void {
    const key = keyOf(repo, number);
    this.prSummaries = { ...this.prSummaries, [key]: summary };
    if (this.prs[key]?.mismatches === mismatches) return;
    this.changePr(repo, number, (pr) => ({ ...pr, mismatches }));
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
      taken.set(thread, threadMerged(held[thread], one));
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

  private sending(
    conversation: string | null,
    kind: string,
    typed: unknown,
  ): StoredOperation {
    this.sends += 1;
    return {
      id: `sent-${this.sends}`,
      conversation,
      kind: kind as OperationKind,
      state: 'sent',
      reason: null,
      reason_code: null,
      body: typeof typed === 'string' ? typed : null,
      local: true,
    };
  }

  private hold(pr: Numbered, one: StoredOperation): StoredOperation {
    const key = keyOf(pr.repo, pr.number);
    for (const id of this.sentOn(pr, one.conversation)) {
      const was = this.operations[key]?.[operationKey({ ...one, id })];
      if (one.conversation !== null || was?.kind === one.kind) {
        this.drop(pr, { ...one, id });
      }
    }
    this.mergeOperations(key, [one]);
    this.markSent(pr, one.conversation, [
      ...this.sentOn(pr, one.conversation),
      one.id,
    ]);
    return one;
  }

  private drop(pr: Numbered, one: StoredOperation): void {
    const key = keyOf(pr.repo, pr.number);
    const gone = operationKey(one);
    this.operations = {
      ...this.operations,
      [key]: Object.fromEntries(
        Object.entries(this.operations[key] ?? {}).filter(
          ([held]) => held !== gone,
        ),
      ),
    };
    this.markSent(
      pr,
      one.conversation,
      this.sentOn(pr, one.conversation).filter((id) => id !== one.id),
    );
  }

  private pressedOn(pr: Numbered): StoredOperation[] {
    const held = this.operations[keyOf(pr.repo, pr.number)] ?? {};
    return this.sentOn(pr, null).flatMap((id) => {
      const one = held[operationKey({ id, conversation: null })];
      return one && slotOf(one.kind ?? '') ? [one] : [];
    });
  }

  private async sendOn<T>(
    pr: Numbered,
    verb: PrVerb,
    asking: () => Promise<T>,
    where: string,
    on: string | null = null,
  ): Promise<{ taken: Tried<T>; local: StoredOperation }> {
    for (const one of this.pressedOn(pr)) {
      if (slotOf(one.kind ?? '') === slotOf(verb)) this.drop(pr, one);
    }
    return this.sendHeld(
      pr,
      this.hold(pr, this.sending(null, verb, on)),
      asking,
      where,
    );
  }

  private async sendHeld<T>(
    pr: Numbered,
    local: StoredOperation,
    asking: () => Promise<T>,
    where: string,
  ): Promise<{ taken: Tried<T>; local: StoredOperation }> {
    const taken = await tried(where, asking());
    if (!taken.done) this.refuse(pr, local, taken.why, taken.code);
    return { taken, local };
  }

  private settle(pr: Numbered, one: StoredOperation, answered: boolean): void {
    const facts = this.prs[keyOf(pr.repo, pr.number)]?.facts ?? null;
    if (settledBy(one.kind ?? '', facts, answered)) this.drop(pr, one);
  }

  private sentOn(pr: Numbered, conversation: string | null): string[] {
    const key = keyOf(pr.repo, pr.number);
    const on =
      conversation === null ? this.prs[key] : this.threads[key]?.[conversation];
    return on?.sent ?? [];
  }

  private refuse(
    pr: Numbered,
    one: StoredOperation,
    reason: string,
    code: string | null,
  ): void {
    this.mergeOperations(keyOf(pr.repo, pr.number), [
      {
        ...one,
        state: 'refused',
        reason,
        reason_code: code as StoredOperation['reason_code'],
      },
    ]);
  }

  private markSent(
    { repo, number }: Numbered,
    conversation: string | null,
    sent: string[],
  ): void {
    if (conversation === null) {
      this.changePr(repo, number, (held) => ({ ...held, sent }));
      return;
    }
    const key = keyOf(repo, number);
    const thread = this.threads[key]?.[conversation];
    if (!thread) return;
    this.threads = {
      ...this.threads,
      [key]: { ...this.threads[key], [conversation]: { ...thread, sent } },
    };
    this.place(repo, number);
  }

  private takeOutcome(
    pr: Numbered,
    { operation, conversation }: Outcome,
    local: StoredOperation,
  ): void {
    const { repo, number } = pr;
    if (opensTerminal(local.kind ?? '')) {
      this.mergeOperations(keyOf(repo, number), [
        { ...local, answer: operation.id },
      ]);
    } else {
      this.drop(pr, local);
    }
    this.takeAnswer(pr, operation);
    const key = keyOf(repo, number);
    const held = this.threads[key] ?? {};
    const taken = threadMerged(held[conversation.key], conversation);
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

  private takeDiff(diff: Diff, key = commitsOf(diff)): void {
    this.diffs = { ...this.diffs, [key]: diff };
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
      standing: dashboard.standing,
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
              base_branch: pr.base_branch ?? held.base_branch,
              ticket: pr.ticket,
              author: pr.author,
              drawn,
            }),
        facts: facts
          ? merged(held.facts, listsOf(facts), (polled) => polled.polled_at)
          : held.facts,
        flags:
          !stale && dashboard.standing === 'gone'
            ? manager
            : merged(held.flags, manager, (flags) => flags.changed_at),
      };
    });
    for (const one of this.pressedOn({ repo, number })) {
      if (one.state === 'sent') this.settle({ repo, number }, one, false);
    }
  }

  private replayShelf(held: HeldPullRequests): void {
    try {
      this.takeWall(held);
    } catch (trouble) {
      unshelve();
      this.watching = [];
      this.groups = null;
      this.prs = {};
      this.threads = {};
      this.operations = {};
      this.joins = 0;
      void reportError('shelf', trouble);
    }
  }

  private takeWall(held: HeldPullRequests): void {
    const { watching, groups, prs, threads, joins } = this;
    try {
      this.applyWall(held);
    } catch (trouble) {
      this.watching = watching;
      this.groups = groups;
      this.prs = prs;
      this.threads = threads;
      this.joins = joins;
      throw trouble;
    }
    shelve(held);
  }

  private applyWall(held: HeldPullRequests): void {
    if (!Array.isArray(held.groups)) {
      throw new Error('the wall came without its groups');
    }
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
        mismatches: row.mismatches,
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
      base_branch: null,
      head_sha: null,
      created_at: null,
      commits: null,
      additions: 0,
      deletions: 0,
      ticket: null,
      author: null,
      board_url: null,
      facts: null,
      flags: null,
      drawn: null,
      place: null,
      unreadable: [],
      in_flight: [],
      sent: [],
      diffs: {},
      history: {},
      read: null,
      mismatches: null,
    };
    this.prs = { ...this.prs, [key]: changed(held) };
    this.place(repo, number);
  }

  private place(repo: string, number: number, joining = false): void {
    const key = keyOf(repo, number);
    const pr = this.prs[key];
    const summary = summaryOf(pr, this.threads[key], this.operations[key]);
    if (!pr || !summary || (!pr.place && !joining)) return;
    const place = placeOf(
      pr.place,
      summary,
      () => this.joins++,
      (group, seenMoving) => this.enter(key, pr, group, seenMoving),
    );
    if (place === pr.place) return;
    this.prs = { ...this.prs, [key]: { ...pr, place } };
  }

  private enter(
    key: string,
    pr: PrEntity,
    group: Entered['group'],
    seenMoving: boolean,
  ): number {
    const at = enteredAt(
      this.entries[key],
      group,
      seenMoving,
      pr.drawn?.status.last_event_at ?? null,
      Date.now(),
    );
    this.entries = { ...this.entries, [key]: { group, at } };
    rememberEntries(this.entries);
    return at;
  }
}
