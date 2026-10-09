import type {
  AuthorKind,
  Comment,
  Conversation,
  ConversationState,
  Diff,
  DiffLine,
  ErrorCode,
  ErrorDetail,
  FileChange,
  FileLines,
  FinishedRun,
  GitRun,
  HeldPullRequest,
  Dashboard,
  DashboardPr,
  DashboardStatus,
  DashboardSystem,
  ManagerFlags,
  Operation,
  OperationKind,
  OperationSummary,
  OutputLine,
  Person,
  PrFacts,
  Proposal,
  PullRequest,
  RecordState,
  RunLedger,
  RunsToday,
  TerminalSession,
  ThreadRow,
  WallGroupName,
  WatcherHealth,
  HubState,
  NewestRelease,
} from 'frontend/data/api';
import { driftOf } from 'frontend/tests/helpers/contract';
import { FakeSetup, type Answer } from 'frontend/tests/helpers/fake-setup';
import { RECORDED } from 'frontend/tests/helpers/thread-phases';

export type Phase =
  keyof (typeof RECORDED)['author'] | keyof (typeof RECORDED)['reviewer'];

export function thread(over: Partial<Conversation> = {}): Conversation {
  return {
    key: 'PRRT_a',
    github_node_id: 'PRRT_a',
    kind: 'review',
    state: 'ready',
    state_changed_at: null,
    reopened: false,
    etag: '"t1"',
    github_removed: false,
    github_resolved: false,
    github_resolved_at: null,
    created_at: null,
    anchor: {
      path: 'src/foo.py',
      line: 42,
      start_line: null,
      start_side: null,
      side: 'RIGHT',
      original_line: 42,
      original_start_line: null,
      original_commit: 'a1b2c3d',
      is_outdated: false,
    },
    gist: 'rename the helper',
    comments: [
      {
        id: 1,
        author: 'anna',
        created_at: '2026-09-12T10:00:00Z',
        review_state: 'CHANGES_REQUESTED',
      },
    ],
    operations: [],
    mention: false,
    updated_at: null,
    author_kind: 'human',
    unread: false,
    record_state: 'open',
    ...over,
  };
}

export function summary(
  over: Partial<OperationSummary> = {},
): OperationSummary {
  return {
    id: 'PRRT_a.1',
    kind: 'first',
    state: 'applied',
    reason: null,
    reason_code: null,
    requested_at: null,
    settled_at: null,
    steps_done: null,
    steps_total: null,
    attempts: null,
    attempts_allowed: null,
    lands: null,
    ticket_key: null,
    ...over,
  };
}

const RUN = {
  last_action: null,
  progress: null,
  plan: [],
  proposal: null,
};

const FIX = {
  ...RUN,
  attempts: 0,
  attempts_allowed: 3,
  onto: null,
  conflict: null,
  brief: null,
  classification: null,
};

const CLOSE = { delete_comment: false, posted_comment: null, reply: null };

const DRAFT = { anchor: null, body: null, posted_comment: null };

type Envelope =
  | 'id'
  | 'conversation'
  | 'kind'
  | 'state'
  | 'reason'
  | 'reason_code'
  | 'requested_at'
  | 'settled_at';

const DETAILS: {
  [K in OperationKind]: Omit<Operation & { kind: K }, Envelope>;
} = {
  first: FIX,
  rebase: FIX,
  rework: FIX,
  retry: FIX,
  'start-session': { ...RUN, steer: null },
  approve: {
    ...CLOSE,
    landed_base: null,
    landed_sha: null,
    proposal: null,
    reply_note: null,
    steps: { filed: false, picked: false, pushed: false, answered: false },
    ticket_key: null,
    ticket_url: null,
  },
  file: {},
  stop: { stopped: null },
  unpark: {},
  confirm: {},
  place: {},
  resolve: CLOSE,
  reject: CLOSE,
  defer: { note: null, until: 'manual' },
  reply: { body: '', posted_comment: null },
  'create-draft': DRAFT,
  'edit-draft': DRAFT,
  enrol: DRAFT,
  'withdraw-from-review': DRAFT,
  discard: DRAFT,
  'post-now': DRAFT,
  'send-review': {
    body: null,
    drafts: [],
    posted_review: null,
    verdict: 'COMMENT',
  },
  posted: { github_node_id: null, posted_comment: null, review: null },
};

export function operation(over: Partial<Operation> = {}): Operation {
  const kind = over.kind ?? 'first';
  return {
    id: 'PRRT_a.1',
    conversation: 'PRRT_a',
    state: 'applied',
    reason: null,
    reason_code: null,
    requested_at: null,
    settled_at: null,
    ...DETAILS[kind],
    ...over,
    kind,
  } as Operation;
}

export function comment(over: Partial<Comment> = {}): Comment {
  return {
    id: 1,
    author: 'anna',
    created_at: '2026-09-12T10:00:00Z',
    review_state: 'CHANGES_REQUESTED',
    body: 'please rename',
    updated_at: null,
    html_url: 'https://github.com/o/r/pull/7#discussion_r1',
    posted_by_board: false,
    deleted: false,
    deleted_by_board: false,
    ...over,
  };
}

export function proposal(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 'PRRT_a.1.proposal',
    conversation: 'PRRT_a',
    kind: 'commit',
    reply: null,
    ticket: null,
    operation: 'PRRT_a.1',
    created_at: null,
    updated_at: null,
    commits: { base: 'aaaaaaa', head: 'bbbbbbb' },
    directory: null,
    summary: 'renamed it',
    agent_note: null,
    confidence: null,
    confidence_note: null,
    tests: null,
    tests_note: null,
    commit_message: 'Rename the helper',
    ...over,
  };
}

export const PULL_REQUEST: PullRequest = {
  repo: 'o/r',
  number: 7,
  title: 'Fix the widget',
  html_url: 'https://github.com/o/r/pull/7',
  base_branch: 'main',
  branch: 'fix-the-widget',
  head_sha: 'c0ffee1',
};

export interface DashboardOver extends Partial<
  Omit<Dashboard, 'pr' | 'status' | 'system' | 'facts' | 'manager'>
> {
  pr?: Partial<DashboardPr>;
  status?: Partial<DashboardStatus>;
  system?: Partial<DashboardSystem>;
  facts?: Partial<PrFacts> | null;
  manager?: Partial<ManagerFlags>;
}

export function threadRow(
  key: string,
  state: ConversationState,
  record_state: RecordState,
  author_kind: AuthorKind,
  updated_at = '2026-10-08T08:00:00Z',
): ThreadRow {
  return { key, state, record_state, author_kind, updated_at };
}

export function prFacts(over: Partial<PrFacts> = {}): PrFacts {
  return {
    polled_at: '2026-09-12T08:30:00Z',
    ended: false,
    is_author: true,
    changes_requested_by: [],
    pending_reviewers: ['carol'],
    ci_status: 'passing',
    merge_state: 'blocked',
    draft: false,
    review_decision: null,
    my_review: null,
    my_review_at: null,
    viewer_requested: false,
    mentioned: false,
    mentions: [],
    unresolved_threads: 0,
    ...over,
  };
}

export const REVIEWED_AT = '2026-06-09T12:00:00Z';

const AS_REVIEWER: Partial<PrFacts> = {
  is_author: false,
  pending_reviewers: [],
  merge_state: 'clean',
  review_decision: 'review-required',
};

const FACTS_FOR: Record<string, Partial<PrFacts>> = {
  'fix-ci': {
    ci_status: 'failing',
    pending_reviewers: [],
    review_decision: 'review-required',
  },
  rebase: { merge_state: 'conflicts', pending_reviewers: [] },
  'ready-to-merge': {
    merge_state: 'clean',
    pending_reviewers: [],
    review_decision: 'approved',
  },
  'await-ci': { ci_status: 'pending' },
  'await-review': {},
  'await-rereview': {
    changes_requested_by: ['carol'],
    pending_reviewers: ['carol'],
  },
  'address-feedback': { changes_requested_by: ['bob'], pending_reviewers: [] },
  'request-reviewers': { pending_reviewers: [] },
  'mark-ready-for-review': { pending_reviewers: [], draft: true },
  review: { ...AS_REVIEWER, viewer_requested: true },
  rereview: {
    ...AS_REVIEWER,
    viewer_requested: true,
    my_review: 'commented',
    my_review_at: REVIEWED_AT,
  },
  'await-author': {
    ...AS_REVIEWER,
    review_decision: 'approved',
    my_review: 'approved',
    my_review_at: REVIEWED_AT,
  },
  'await-reviewers': {
    ...AS_REVIEWER,
    pending_reviewers: ['carol'],
    my_review: 'approved',
    my_review_at: REVIEWED_AT,
  },
  'await-rerequest': {
    ...AS_REVIEWER,
    my_review: 'commented',
    my_review_at: REVIEWED_AT,
  },
  'not-reviewing': AS_REVIEWER,
  mention: {
    ...AS_REVIEWER,
    mentioned: true,
    mentions: [{ author: 'anna', at: null, answered: false }],
  },
  mentioned: {
    ...AS_REVIEWER,
    mentioned: true,
    mentions: [{ author: 'anna', at: null, answered: true }],
  },
  closed: { ended: true },
};

export function factsFor(
  move: string,
  over: Partial<PrFacts> = {},
): Partial<PrFacts> {
  const facts = FACTS_FOR[move];
  if (!facts) throw new Error(`no facts make the move ${move}`);
  return { ...facts, ...over };
}

export function dashboard(over: DashboardOver = {}): Dashboard {
  const { pr, status, system, facts, manager, ...rest } = over;
  return {
    pr: {
      repo: 'o/r',
      number: 7,
      title: 'Fix the widget',
      url: 'https://github.com/o/r/pull/7',
      branch: 'PROJ-7-fix-the-widget',
      ticket: 'PROJ-7',
      author: 'dave',
      ...pr,
    },
    polled: true,
    status: {
      detailed_reviewer: 'carol',
      you_are_the_detailed_reviewer: false,
      mergeable: true,
      needs_rebase: false,
      last_event_at: '2026-09-12T08:30:00Z',
      review_ready_at: '2026-09-11T08:00:00Z',
      since_you_last_acted: null,
      failed_checks: [],
      checks_done: 4,
      checks_total: 4,
      changed_files: 3,
      approved_by: [],
      ...status,
    },
    system: {
      agent: {
        name: 'Claude',
        enabled: true,
        state: 'idle',
        event: null,
        elapsed_seconds: null,
        silent_seconds: null,
      },
      last_run: null,
      queued_events: 0,
      on_hold: false,
      unpushed_commits: 0,
      threads: { queued: 0, live: 0, proposed: 0, drafts: 0 },
      ...system,
    },
    frozen: null,
    undismiss_command: 'github-orchestrator undismiss 7',
    notice: null,
    standing: 'answering',
    facts: facts === null ? null : prFacts(facts),
    manager: {
      frozen_on: null,
      on_hold: false,
      working_on: null,
      hidden: false,
      threads_live: 0,
      changed_at: '2026-09-12T08:30:00Z',
      ...manager,
    },
    threads: [],
    unreadable: [],
    listed_at: null,
    ...rest,
  };
}

export interface HeldOver extends Partial<Omit<HeldPullRequest, 'dashboard'>> {
  dashboard?: DashboardOver;
}

export const WALL_GROUPS: WallGroupName[] = [
  { group: 'needs-you', name: 'Needs you' },
  { group: 'draft', name: 'Draft' },
  { group: 'agent-working', name: 'Agent working' },
  { group: 'waiting-on-others', name: 'Waiting on others' },
  { group: 'on-hold', name: 'On hold' },
  { group: 'mentioned', name: 'Mentioned' },
];

export function finishedRun(over: Partial<FinishedRun> = {}): FinishedRun {
  return {
    ended_at: '2026-09-28T09:00:00+00:00',
    repo: 'o/r',
    number: 7,
    event: 'ci-failed',
    elapsed_seconds: 95,
    exit_code: 0,
    cost_usd: 0.42,
    failed: false,
    board_url: '/pr/o/r/7',
    ...over,
  };
}

export function runLedger(
  over: {
    watcher?: Partial<WatcherHealth>;
    today?: Partial<RunsToday>;
    runs?: FinishedRun[];
  } = {},
): RunLedger {
  return {
    watcher: {
      polled_at: null,
      next_poll_at: null,
      overdue: false,
      last_error: null,
      fix: null,
      ...over.watcher,
    },
    today: { runs: 0, cost_usd: null, unpriced: 0, ...over.today },
    runs: over.runs ?? [],
  };
}

export function heldPr(over: HeldOver = {}): HeldPullRequest {
  const { dashboard: shown = {}, ...rest } = over;
  const number = rest.number ?? 7;
  const repo = rest.repo ?? 'o/r';
  return {
    repo,
    number,
    manager: 'running',
    board_url: `/pr/${repo}/${number}`,
    ...rest,
    dashboard: dashboard({
      ...shown,
      pr: {
        repo,
        number,
        url: `https://github.com/${repo}/pull/${number}`,
        ...shown.pr,
      },
    }),
  };
}

const MANAGER_VERB = /\/api\/manager:([a-z-]+)$/;
const HUB_VERB = /\/api\/pull-requests\/([^/]+\/[^/]+)\/(\d+):([a-z-]+)$/;
export const ONE_PR_READ =
  /^\/api\/(?!health$|pull-requests$|runs$|tour$|client-errors$)/;
const THROUGH_THE_HUB = /^\/pr\/([^/]+\/[^/]+)\/(\d+)(\/api\/.*)$/;

type Side = 'board' | 'hub';

export interface Posted {
  url: string;
  key: string;
  verb: string;
  ifMatch: string | null;
  body: unknown;
}

export interface Asked {
  url: string;
  ifNoneMatch: string | null;
}

export interface OpenStream {
  url: string;
  lastEventId: string | null;
  sent: string | null;
}

interface Streaming extends OpenStream {
  read: URL;
  controller: ReadableStreamDefaultController<Uint8Array>;
}

const STREAM = /^(\/api\/.+)\/stream$/;
const ENCODER = new TextEncoder();

const SOCKET =
  /(?:^\/pr\/[^/]+\/[^/]+\/\d+)?\/api\/terminal\/sessions\/([^/]+)$/;
const DECODER = new TextDecoder();

export class FakeSocket {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  readonly url: string;
  readonly session: string;
  binaryType: BinaryType = 'blob';
  readyState = 0;
  sent: (string | ArrayBuffer)[] = [];
  closedWith: number | null = null;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string, session: string) {
    this.url = url;
    this.session = session;
  }

  get typed(): string {
    return this.sent
      .filter((one): one is ArrayBuffer => typeof one !== 'string')
      .map((one) => DECODER.decode(one))
      .join('');
  }

  get sizes(): unknown[] {
    return this.sent
      .filter((one): one is string => typeof one === 'string')
      .map((one) => JSON.parse(one) as unknown);
  }

  send(data: string | ArrayBufferView | ArrayBuffer): void {
    if (typeof data === 'string') this.sent.push(data);
    else if (data instanceof ArrayBuffer) this.sent.push(data);
    else {
      this.sent.push(
        new Uint8Array(data.buffer, data.byteOffset, data.byteLength).slice()
          .buffer,
      );
    }
  }

  close(code = 1000): void {
    if (this.readyState === FakeSocket.CLOSED) return;
    this.readyState = FakeSocket.CLOSED;
    this.closedWith = code;
    this.onclose?.(new CloseEvent('close', { code }));
  }

  opened(): void {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  hear(data: string | ArrayBuffer): void {
    this.onmessage?.(new MessageEvent('message', { data }));
  }
}

export interface Reported {
  where: string;
  message: string;
  stack: string | null;
}

export class FakeBoard {
  pullRequest: PullRequest = { ...PULL_REQUEST };
  viewer: Person = { login: 'octocat', name: 'Octo Cat' };
  people: Person[] = [{ login: 'anna', name: 'Anna Example' }];
  conversations: Conversation[] = [];
  projections: Record<string, Conversation> = {};
  unreadable: string[] = [];
  listedAt = '2026-10-08T09:30:00Z';
  comments: Record<string, Comment[]> = {};
  operations: Record<string, Operation[]> = {};
  proposals: Record<string, Proposal[]> = {};
  diffs: Record<string, Diff> = {};
  pullRequestDiff: Diff = { base: 'ba5e000', head: 'c0ffee1', files: [] };
  localDiff: Diff | null = null;
  pushedSinceFetch: Diff | null = null;
  fetches = 0;
  files: FileLines | null = null;
  sources: Record<string, string[]> = {};
  inFlight: Operation[] = [];
  reviews: Record<string, Operation> = {};
  private managed: Dashboard = dashboard();
  private managerSet = false;

  get manager(): Dashboard {
    return this.managed;
  }

  set manager(shown: Dashboard) {
    this.managed = shown;
    this.managerSet = true;
  }
  changes: string | null = null;
  output: OutputLine[] = [];
  gitRuns: Record<string, GitRun> = {};
  created = 'draft_0000000000000001';
  refusal: ErrorDetail | null = null;
  down = false;
  unheld: { code: ErrorCode; detail: string } | null = null;
  broken: RegExp | null = null;
  posted: Posted[] = [];
  asked: Asked[] = [];
  reported: Reported[] = [];
  seen: string[] = [];
  serves: 'board' | 'hub' = 'board';
  hubUrl = 'http://127.0.0.1:8720';
  fontProblem: string | null = null;
  newestRelease: NewestRelease | null = null;
  state: HubState = 'watching';
  tourDue = false;
  toursSeen = 0;
  pid = 4242;
  setup = new FakeSetup();
  held: HeldPullRequest[] = [];
  ledger: RunLedger = runLedger();
  watching = ['o/r'];
  terminalSessions: TerminalSession[] = [];
  opensOutside = false;
  sockets: FakeSocket[] = [];

  private madeSessions = 0;

  get role(): 'author' | 'reviewer' {
    const shown =
      this.serves === 'hub'
        ? this.boardOf(
            `/pr/${this.pullRequest.repo}/${this.pullRequest.number}/api/dashboard`,
          )
        : this.manager;
    return shown?.facts?.is_author === false ? 'reviewer' : 'author';
  }

  actAs(role: 'author' | 'reviewer'): void {
    const acting = (shown: Dashboard): Dashboard => ({
      ...shown,
      facts: shown.facts && { ...shown.facts, is_author: role === 'author' },
    });
    if (this.managed) this.managed = acting(this.managed);
    this.held = this.held.map((one) =>
      one.repo === this.pullRequest.repo &&
      one.number === this.pullRequest.number
        ? { ...one, dashboard: acting(one.dashboard) }
        : one,
    );
  }

  private get recorded(): Record<string, Conversation> {
    return RECORDED[this.role];
  }

  phasesRecorded(): Phase[] {
    return Object.keys(this.recorded) as Phase[];
  }

  threadIn(phase: Phase, over: Partial<Conversation> = {}): Conversation {
    const reached = this.recorded[phase];
    if (!reached) {
      throw new Error(
        `the machine reached no ${phase} thread for the ${this.role}`,
      );
    }
    const copy = structuredClone(reached);
    const key = over.key ?? copy.key;
    return {
      ...copy,
      key,
      github_node_id: copy.github_node_id === null ? null : key,
      operations: copy.operations.map((one) => ({
        ...one,
        id: one.id.replace(copy.key, key),
      })),
      ...over,
    };
  }

  connect(url: string | URL): FakeSocket {
    const where = new URL(String(url));
    const session = decodeURIComponent(SOCKET.exec(where.pathname)?.[1] ?? '');
    const socket = new FakeSocket(String(url), session);
    this.sockets.push(socket);
    void Promise.resolve().then(() => {
      if (this.terminalSessions.some((one) => one.id === session)) {
        socket.opened();
      } else {
        socket.opened();
        socket.close(4404);
      }
    });
    return socket;
  }

  socketsOf(session: string): FakeSocket[] {
    return this.sockets.filter((one) => one.session === session);
  }

  print(session: string, text: string): void {
    const bytes = ENCODER.encode(text);
    this.socketsOf(session)
      .filter((one) => one.readyState === FakeSocket.OPEN)
      .forEach((one) => one.hear(bytes.slice().buffer));
  }

  exit(session: string, exitCode: number): void {
    this.terminalSessions = this.terminalSessions.filter(
      (one) => one.id !== session,
    );
    this.socketsOf(session)
      .filter((one) => one.readyState === FakeSocket.OPEN)
      .forEach((one) => {
        one.hear(JSON.stringify({ exit_code: exitCode }));
        one.close(1000);
      });
  }

  private startSession(argv: string[], worktree: string): void {
    this.madeSessions += 1;
    this.terminalSessions = [
      ...this.terminalSessions,
      { id: `made-${this.madeSessions}`, argv, worktree },
    ];
  }

  private gates: { pattern: RegExp; open: Promise<void> }[] = [];
  private streams: Streaming[] = [];

  get openStreams(): OpenStream[] {
    return this.streams.map(({ url, lastEventId, sent }) => ({
      url,
      lastEventId,
      sent,
    }));
  }

  streamed(): void {
    this.streams.forEach((one) => this.sendTo(one));
  }

  dropStreams(): void {
    const dropped = this.streams;
    this.streams = [];
    dropped.forEach((one) => one.controller.error(new TypeError('network')));
  }

  private stream(url: string, read: URL, headers: Headers): Response {
    const lastEventId = headers.get('Last-Event-ID');
    let opened: Streaming | null = null;
    const body = new ReadableStream<Uint8Array>({
      start: (controller) => {
        opened = { url, read, lastEventId, sent: lastEventId, controller };
        this.streams.push(opened);
        controller.enqueue(ENCODER.encode('retry: 1000\n\n'));
        this.sendTo(opened);
      },
      cancel: () => {
        this.streams = this.streams.filter((one) => one !== opened);
      },
    });
    return new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }

  private sendTo(stream: Streaming): void {
    const path = stream.read.pathname;
    const body = this.read(stream.read, 'board', stream.url);
    if (body === undefined) return;
    const data = JSON.stringify(body);
    const id = hash(data);
    if (id === stream.sent) return;
    stream.sent = id;
    this.drift.push(...driftOf('GET', `${path}/stream`, 200, body));
    const event = path.split('/').at(-1);
    stream.controller.enqueue(
      ENCODER.encode(`event: ${event}\nid: ${id}\ndata: ${data}\n\n`),
    );
  }

  askedFor(pattern: RegExp): Asked[] {
    return this.asked.filter((one) => pattern.test(one.url));
  }

  private releases: (() => void)[] = [];

  hold(pattern: RegExp): () => void {
    let release = () => {};
    const open = new Promise<void>((resolve) => {
      release = resolve;
    });
    this.gates.push({ pattern, open });
    const opened = () => {
      this.gates = this.gates.filter((one) => one.open !== open);
      release();
    };
    this.releases.push(opened);
    return opened;
  }

  releaseAll(): void {
    this.releases.forEach((release) => release());
  }

  private drift: string[] = [];

  fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = input instanceof Request ? input.url : String(input);
    const gate = this.gates.find((one) => one.pattern.test(url));
    const answering = gate
      ? gate.open.then(() => this.answer(input, init))
      : this.answer(input, init);
    const signal = init?.signal;
    const answered = signal
      ? Promise.race([answering, abortedBy(signal)])
      : answering;
    return answered.then((response) => {
      if (response.headers.get('Content-Type') === 'text/event-stream') {
        return response;
      }
      const text = BODIES.get(response);
      if (text === undefined) {
        throw new Error(
          'the fake board answered with a response respond() did not build',
        );
      }
      const body: unknown = text ? JSON.parse(text) : null;
      this.drift.push(
        ...driftOf(init?.method ?? 'GET', url, response.status, body),
      );
      return response;
    });
  };

  driftFromTheContract(): Promise<string[]> {
    return Promise.resolve(this.drift);
  }

  private answer = (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = input instanceof Request ? input.url : String(input);
    const headers = new Headers(init?.headers);
    if (this.down) return Promise.reject(new Error('connection refused'));
    if (this.broken?.test(url)) {
      return Promise.reject(new Error('connection refused'));
    }
    const where = new URL(url, 'http://127.0.0.1');
    const setup =
      this.serves === 'hub'
        ? this.setup.answer(init?.method ?? 'GET', where, init)
        : null;
    if (setup) return Promise.resolve(this.setupAnswered(setup));
    const through =
      this.serves === 'hub' ? THROUGH_THE_HUB.exec(where.pathname) : null;
    if (!through) {
      return Promise.resolve(
        this.served(url, where, init, headers, this.serves),
      );
    }
    return Promise.resolve(
      this.throughTheHub(
        through[1]!,
        Number(through[2]),
        new URL(`${through[3]}${where.search}`, 'http://127.0.0.1'),
        url,
        init,
        headers,
      ),
    );
  };

  private setupAnswered({ status, body, location }: Answer): Response {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (location) headers['Location'] = location;
    return respond(JSON.stringify(body), { status, headers });
  }

  private throughTheHub(
    repo: string,
    number: number,
    where: URL,
    url: string,
    init: RequestInit | undefined,
    headers: Headers,
  ): Response {
    const held = this.held.find(
      (one) => one.repo === repo && one.number === number,
    );
    if (!held) {
      return this.json(404, {
        errors: [{ status: 404, code: 'not-found', detail: 'not held' }],
      });
    }
    if (!held.board_url) {
      return this.json(503, {
        errors: [
          {
            status: 503,
            code: 'board-unreachable',
            detail: `${held.repo}#${number}'s board is not answering`,
          },
        ],
      });
    }
    const answered = this.served(url, where, init, headers, 'board');
    const location = answered.headers.get('Location');
    if (location)
      answered.headers.set('Location', `/pr/${repo}/${number}${location}`);
    return answered;
  }

  private served(
    url: string,
    where: URL,
    init: RequestInit | undefined,
    headers: Headers,
    side: Side,
  ): Response {
    if (init?.method === 'POST') return this.write(url, init, headers, side);
    this.asked.push({ url, ifNoneMatch: headers.get('If-None-Match') });
    const streaming = side === 'board' ? STREAM.exec(where.pathname) : null;
    if (streaming) {
      const read = new URL(`${streaming[1]}${where.search}`, where);
      return this.stream(url, read, headers);
    }
    if (
      side === 'hub' &&
      where.pathname === '/api/pull-requests' &&
      this.unheld
    ) {
      return this.starting(this.unheld.code, this.unheld.detail);
    }
    const body = this.read(where, side, url);
    if (body === undefined) {
      return this.json(404, {
        errors: [{ status: 404, code: 'not-found', detail: 'nothing here' }],
      });
    }
    const tag = `"${hash(JSON.stringify(body))}"`;
    if (headers.get('If-None-Match') === tag) {
      return respond(null, { status: 304, headers: { ETag: tag } });
    }
    return this.json(200, body, tag);
  }

  private json(status: number, body: unknown, tag?: string): Response {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (tag) headers['ETag'] = tag;
    return respond(JSON.stringify(body), { status, headers });
  }

  private starting(code: ErrorCode, said: string): Response {
    const detail = { status: 503, code, detail: said };
    return respond(JSON.stringify({ errors: [detail] }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'Retry-After': '1' },
    });
  }

  private pullRequestOf(asked: string): PullRequest {
    const shown = this.boardOf(asked)?.pr;
    if (!shown) return this.pullRequest;
    return {
      ...this.pullRequest,
      repo: shown.repo,
      number: shown.number,
      title: shown.title ?? this.pullRequest.title,
      html_url: shown.url ?? this.pullRequest.html_url,
      branch: shown.branch,
    };
  }

  private boardOf(url: string): Dashboard {
    const through = THROUGH_THE_HUB.exec(
      new URL(url, 'http://127.0.0.1').pathname,
    );
    const held = through
      ? this.held.find(
          (one) => one.repo === through[1] && one.number === Number(through[2]),
        )
      : undefined;
    if (!held) return this.manager;
    if (!this.managerSet) return held.dashboard;
    if (
      this.manager.pr.repo === held.repo &&
      this.manager.pr.number === held.number
    ) {
      return this.manager;
    }
    return held.dashboard;
  }

  private proposed(key: string, proposal: Proposal): Proposal {
    const diff = this.diffs[proposal.id];
    const commits =
      diff && proposal.commits
        ? { base: diff.base, head: diff.head }
        : proposal.commits;
    const conversation = this.conversations.find((one) => one.key === key);
    return {
      ...proposal,
      conversation: key,
      commits,
      updated_at: proposal.updated_at ?? conversation?.updated_at ?? null,
    };
  }

  private said(one: Conversation): Conversation {
    const comments = this.comments[one.key];
    if (!comments) return one;
    return {
      ...one,
      comments: comments.map(({ id, author, created_at, review_state }) => ({
        id,
        author,
        created_at,
        review_state,
      })),
    };
  }

  private conversationsOf(asked: string): Conversation[] {
    if (this.conversations.length) {
      return this.conversations.map((one) => this.said(one));
    }
    return (this.boardOf(asked)?.threads ?? []).map((row) =>
      thread({
        key: row.key,
        github_node_id: row.key,
        state: row.state,
        record_state: row.record_state,
        author_kind: row.author_kind,
        updated_at: row.updated_at,
      }),
    );
  }

  private listing(shown: Dashboard): Dashboard {
    if (shown.threads.length || shown.unreadable.length) return shown;
    return {
      ...shown,
      threads: this.conversations.map((one) =>
        threadRow(
          one.key,
          one.state,
          one.record_state,
          one.author_kind,
          one.updated_at ?? undefined,
        ),
      ),
      unreadable: this.unreadable,
    };
  }

  private read(url: URL, side: Side, asked: string): unknown {
    const path = url.pathname;
    if (path === '/api/health') {
      return {
        status: 'ok',
        pid: this.pid,
        serves: this.serves,
        hub_url: this.hubUrl,
        font_problem: this.fontProblem,
        ...(this.serves === 'hub'
          ? {
              state: this.state,
              version: '0.1.0',
              watcher: this.ledger.watcher,
            }
          : { state: null, version: null, watcher: null }),
        newest_release: this.serves === 'hub' ? this.newestRelease : null,
      };
    }
    if (side === 'hub') {
      if (path === '/api/runs') return this.ledger;
      if (path === '/api/tour') return { due: this.tourDue };
      return path === '/api/pull-requests'
        ? {
            watching: this.watching,
            groups: WALL_GROUPS,
            pull_requests: this.held.map((one) => ({
              ...one,
              dashboard: this.listing(one.dashboard),
            })),
          }
        : undefined;
    }
    if (path === '/api/dashboard') {
      const shown = this.boardOf(asked);
      return shown && this.listing(shown);
    }
    if (path === '/api/manager/changes') return { markdown: this.changes };
    if (path === '/api/manager/agent-output') {
      const lines = Number(url.searchParams.get('lines') ?? 200);
      return { lines: this.output.slice(-lines) };
    }
    if (path === '/api/terminal/sessions') {
      return { sessions: this.terminalSessions };
    }
    if (path === '/api/pull-request') return this.pullRequestOf(asked);
    if (path === '/api/pull-request/diff') {
      return url.searchParams.get('source') === 'local'
        ? (this.localDiff ?? this.pullRequestDiff)
        : this.pullRequestDiff;
    }
    if (path === '/api/viewer') return this.viewer;
    if (path === '/api/people') return this.people;
    if (path === '/api/operations') return this.inFlight;
    const review = /^\/api\/operations\/([^/]+)$/.exec(path);
    if (review) return this.reviews[decodeURIComponent(review[1]!)];
    if (path === '/api/files') {
      return this.linesOf(url.searchParams) ?? this.files ?? undefined;
    }
    const diff = /^\/api\/diffs\/([0-9a-f]+)\.\.([0-9a-f]+)$/.exec(path);
    if (diff) {
      return Object.values(this.diffs).find(
        (one) => one.base === diff[1] && one.head === diff[2],
      );
    }
    if (path === '/api/conversations') {
      return {
        conversations: this.conversationsOf(asked),
        unreadable: this.unreadable,
        listed_at: this.listedAt,
      };
    }
    const one = /^\/api\/conversations\/([^/]+)(\/.*)?$/.exec(path);
    if (!one) return undefined;
    const key = decodeURIComponent(one[1]!);
    const rest = one[2] ?? '';
    if (!this.conversations.some((found) => found.key === key)) {
      return undefined;
    }
    if (rest === '') {
      const found = this.conversations.find((c) => c.key === key);
      return found && this.said(found);
    }
    if (rest === '/comments') return this.comments[key] ?? [];
    if (rest === '/operations') return this.operations[key] ?? [];
    if (rest === '/proposals') {
      return (this.proposals[key] ?? []).map((one) => this.proposed(key, one));
    }
    return undefined;
  }

  private linesOf(query: URLSearchParams): FileLines | undefined {
    const sha = query.get('sha') ?? '';
    const path = query.get('path') ?? '';
    const source = this.sources[`${sha}:${path}`];
    if (!source) return undefined;
    const from = Number(query.get('from_line'));
    const to = Math.min(Number(query.get('to_line')), source.length);
    return {
      sha,
      path,
      from_line: from,
      to_line: to,
      truncated: false,
      lines: source
        .slice(from - 1, to)
        .map((text, at) => ({ number: from + at, text })),
    };
  }

  private write(
    url: string,
    init: RequestInit,
    headers: Headers,
    side: Side,
  ): Response {
    const seen = /\/api\/conversations\/([^/]+)\/seen$/.exec(url);
    if (seen) {
      this.seen.push(decodeURIComponent(seen[1]!));
      return respond(null, { status: 204 });
    }
    if (url.endsWith('/api/client-errors')) {
      this.reported.push(JSON.parse(init.body as string) as Reported);
      return respond(null, { status: 204 });
    }
    if (side === 'hub' && url.endsWith('/api/tour:seen')) {
      this.toursSeen += 1;
      this.tourDue = false;
      return respond(null, { status: 204 });
    }
    if (side === 'hub') return this.hubWrite(url, headers);
    if (url.endsWith('/api/manager/git')) return this.git(url, init, headers);
    if (url.endsWith('/api/terminal/sessions')) {
      return this.openTerminal(url, init, headers);
    }
    if (url.endsWith('/api/pull-request:fetch')) return this.fetchBranch();
    const told = MANAGER_VERB.exec(url);
    if (told) return this.tell(url, told[1]!, init, headers);
    const found =
      /\/api\/(?:conversations\/([^/]+)\/)?operations:([a-z-]+)$/.exec(url);
    const key = decodeURIComponent(found?.[1] ?? '');
    const verb = found?.[2] ?? '';
    const body: unknown =
      typeof init.body === 'string' ? JSON.parse(init.body) : null;
    this.posted.push({
      url,
      key,
      verb,
      ifMatch: headers.get('If-Match'),
      body,
    });
    if (this.refusal) {
      const refusal = this.refusal;
      this.refusal = null;
      return this.json(refusal.status, { errors: [refusal] });
    }
    const id = `op_${this.posted.length}`;
    if (verb === 'start-session') {
      this.startSession(['claude', '--resume', key], `/wt/thread-${key}`);
    }
    if (verb === 'send-review') {
      const review = operation({
        id,
        conversation: null,
        kind: verb,
        state: 'pending',
      });
      this.reviews[id] = review;
      return respond(JSON.stringify(review), {
        status: 202,
        headers: {
          'Content-Type': 'application/json',
          Location: `/api/operations/${id}`,
        },
      });
    }
    if (verb === 'create-draft') {
      return this.json(
        202,
        operation({
          id,
          conversation: this.created,
          kind: verb,
          state: 'applied',
        }),
      );
    }
    const asked =
      this.projections[key] ??
      this.conversations.find((one) => one.key === key);
    if (!asked) {
      return this.json(404, {
        errors: [
          { status: 404, code: 'not-found', detail: `no thread ${key}` },
        ],
      });
    }
    return this.json(202, {
      operation: operation({
        id,
        conversation: key,
        kind: verb === 'fix' ? 'first' : (verb as OperationKind),
        state: 'pending',
      }),
      conversation: asked,
    });
  }

  private fetchBranch(): Response {
    this.fetches += 1;
    if (this.refusal) {
      const refusal = this.refusal;
      this.refusal = null;
      return this.json(refusal.status, { errors: [refusal] });
    }
    if (this.pushedSinceFetch) this.pullRequestDiff = this.pushedSinceFetch;
    this.pushedSinceFetch = null;
    return respond(null, { status: 204 });
  }

  private hubWrite(url: string, headers: Headers): Response {
    const found = HUB_VERB.exec(url);
    const repo = found?.[1] ?? '';
    const number = Number(found?.[2]);
    const verb = found?.[3] ?? '';
    this.posted.push({
      url,
      key: `${repo}#${number}`,
      verb,
      ifMatch: headers.get('If-Match'),
      body: null,
    });
    const at = this.held.findIndex(
      (one) => one.repo === repo && one.number === number,
    );
    const pr = this.held[at];
    if (!pr) {
      return this.json(404, {
        errors: [{ status: 404, code: 'not-found', detail: 'not held' }],
      });
    }
    if (this.refusal) {
      const refusal = this.refusal;
      this.refusal = null;
      return this.json(refusal.status, { errors: [refusal] });
    }
    const shown = pr.dashboard;
    if (verb === 'release' && !shown.frozen) {
      return this.json(409, {
        errors: [{ status: 409, code: 'not-frozen', detail: 'not frozen' }],
      });
    }
    const changed: HeldPullRequest = {
      ...pr,
      dashboard:
        verb === 'release' && shown.frozen
          ? { ...shown, frozen: { ...shown.frozen, release_requested: true } }
          : {
              ...shown,
              system: { ...shown.system, on_hold: verb === 'hold' },
              manager: { ...shown.manager, on_hold: verb === 'hold' },
            },
    };
    this.held = this.held.map((one, index) => (index === at ? changed : one));
    return respond(null, {
      status: 202,
      headers: { Location: '/api/pull-requests' },
    });
  }

  private git(url: string, init: RequestInit, headers: Headers): Response {
    const body = JSON.parse(init.body as string) as { keys: string };
    this.posted.push({
      url,
      key: '',
      verb: 'git',
      ifMatch: headers.get('If-Match'),
      body,
    });
    if (this.refusal) {
      const refusal = this.refusal;
      this.refusal = null;
      return this.json(refusal.status, { errors: [refusal] });
    }
    return this.json(
      200,
      this.gitRuns[body.keys] ?? {
        exit_code: 0,
        lines: [],
        seconds: 0.1,
        truncated: false,
      },
    );
  }

  private openTerminal(
    url: string,
    init: RequestInit,
    headers: Headers,
  ): Response {
    const body = JSON.parse(init.body as string) as { keys: string };
    this.posted.push({
      url,
      key: '',
      verb: 'open-terminal',
      ifMatch: headers.get('If-Match'),
      body,
    });
    if (this.refusal) {
      const refusal = this.refusal;
      this.refusal = null;
      return this.json(refusal.status, { errors: [refusal] });
    }
    if (!this.opensOutside) {
      this.startSession(['fake', body.keys], '/Users/me/repositories/o/r');
    }
    return this.json(200, { sessions: this.terminalSessions });
  }

  private tell(
    url: string,
    verb: string,
    init: RequestInit,
    headers: Headers,
  ): Response {
    const body: unknown =
      typeof init.body === 'string' ? JSON.parse(init.body) : null;
    this.posted.push({
      url,
      key: '',
      verb,
      ifMatch: headers.get('If-Match'),
      body,
    });
    if (this.manager && (verb === 'hold' || verb === 'resume')) {
      this.manager = {
        ...this.manager,
        system: { ...this.manager.system, on_hold: verb === 'hold' },
        manager: { ...this.manager.manager, on_hold: verb === 'hold' },
      };
      this.streamed();
    }
    return respond(null, {
      status: 202,
      headers: { Location: '/api/dashboard' },
    });
  }
}

const BODIES = new WeakMap<Response, string | null>();

function respond(body: string | null, init: ResponseInit): Response {
  const response = new Response(body, init);
  BODIES.set(response, body);
  return response;
}

function abortedBy(signal: AbortSignal): Promise<never> {
  return new Promise((_, reject) => {
    const refuse = () =>
      reject(new DOMException('the request was aborted', 'AbortError'));
    if (signal.aborted) refuse();
    else signal.addEventListener('abort', refuse, { once: true });
  });
}

function hash(text: string): string {
  let value = 0;
  for (let at = 0; at < text.length; at += 1) {
    value = (value * 31 + text.charCodeAt(at)) | 0;
  }
  return (value >>> 0).toString(16);
}

export function setupFakeBoard(hooks: NestedHooks): () => FakeBoard {
  let board = new FakeBoard();
  let real: typeof globalThis.fetch;
  let realSocket: typeof globalThis.WebSocket;

  hooks.beforeEach(function () {
    board = new FakeBoard();
    real = globalThis.fetch;
    realSocket = globalThis.WebSocket;
    globalThis.fetch = board.fetch;
    globalThis.WebSocket = function (url: string | URL) {
      return board.connect(url);
    } as unknown as typeof WebSocket;
  });

  hooks.afterEach(async function (assert) {
    board.releaseAll();
    globalThis.fetch = real;
    globalThis.WebSocket = realSocket;
    assert.deepEqual(
      await board.driftFromTheContract(),
      [],
      'the fake board answered only as the Board API contract says',
    );
  });

  return () => board;
}

export function diffOf(path: string, ...lines: DiffLine[]): Diff {
  return {
    base: 'aaaaaaa',
    head: hash(JSON.stringify([path, lines])).padStart(8, '0'),
    files: [
      {
        path,
        old_path: null,
        status: 'modified',
        added: lines.filter((one) => one.kind === 'added').length,
        removed: lines.filter((one) => one.kind === 'removed').length,
        is_binary: false,
        line_count: null,
        hunks: [
          {
            old_start: 1,
            old_lines: 1,
            new_start: 1,
            new_lines: 1,
            section: null,
            lines,
          },
        ],
      },
    ],
  };
}

export function added(line: number, text: string): DiffLine {
  return { kind: 'added', old_line: null, new_line: line, text };
}

export function context(line: number, text: string): DiffLine {
  return { kind: 'context', old_line: line, new_line: line, text };
}

export function removed(line: number, text: string): DiffLine {
  return { kind: 'removed', old_line: line, new_line: null, text };
}

export function changed(
  path: string,
  lines: DiffLine[],
  over: Partial<FileChange> = {},
): FileChange {
  return {
    path,
    old_path: null,
    status: 'modified',
    added: lines.filter((one) => one.kind === 'added').length,
    removed: lines.filter((one) => one.kind === 'removed').length,
    is_binary: false,
    line_count: null,
    hunks: [
      {
        old_start: 18,
        old_lines: 3,
        new_start: 18,
        new_lines: 3,
        section: 'def widget():',
        lines,
      },
    ],
    ...over,
  };
}

export function prDiff(...files: FileChange[]): Diff {
  return { base: 'ba5e000', head: 'c0ffee1', files };
}
