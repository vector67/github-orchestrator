import type {
  Comment,
  Commits,
  Conversation,
  ConversationState,
  Diff,
  ManagerFlags,
  Operation,
  PrFacts,
  PullRequestCommit,
  PullRequestCommits,
  ReadMark,
  RecordState,
  ResetToOrigin,
  WitnessProgress,
  WallGroup,
  WallGroupName,
} from 'frontend/data/api';
import { edgeOf } from 'frontend/data/dashboard';
import { groupOf, type Role } from 'frontend/data/groups';
import type { Details, FileStat } from 'frontend/data/panel';
import { atWork } from 'frontend/data/thread';
import { levelOf, type Level } from 'frontend/data/wall';
import {
  dayOf,
  LONG,
  timelineBuilt,
  type Picked,
  type Standing,
  type Timeline,
} from 'frontend/data/timeline';
import {
  operationKey,
  type StoredOperation,
  type Thread,
} from 'frontend/data/entities';
import type {
  PrEntity,
  PrSummaryEntity,
  ShownPr,
} from 'frontend/services/store';

export type Move =
  | 'release-worktree'
  | 'on-hold'
  | 'first-poll'
  | 'closed'
  | 'send-review'
  | 'agent-running'
  | 'agent-on-threads'
  | 'address-feedback'
  | 'human-comments'
  | 'agent-on-human-comments'
  | 'bot-comments'
  | 'agent-on-bot-comments'
  | 'fix-ci'
  | 'rebase'
  | 'ready-to-merge'
  | 'await-ci'
  | 'await-rereview'
  | 'await-review'
  | 'not-reviewing'
  | 'review'
  | 'rereview'
  | 'await-reviewers'
  | 'await-author'
  | 'request-reviewers'
  | 'mark-ready-for-review'
  | 'await-rerequest'
  | 'mention'
  | 'mentioned';

export type Flag = 'draft' | 'fix-ci' | 'rebase' | 'unresolved-threads';

export interface Tally {
  done: number;
  total: number;
  toDecide: number;
  agentOn: number;
}

export interface Yours {
  answered: number;
  total: number;
}

export interface NextMove {
  code: Move;
  state: Move | null;
  group: WallGroup | null;
  muted: boolean;
  reviewers: string[];
  stillRequested: string[];
  mentionedBy: string[];
  flags: Flag[];
  unresolved: number;
}

export interface Summaries {
  role: Role | null;
  groups: Record<string, number>;
  drafts: number;
  ready: number;
  yours: Yours;
  human: Tally;
  bot: Tally;
  move: NextMove;
  mismatches: string | null;
}

type Threads = Record<string, Thread>;

type Operations = Record<string, StoredOperation>;

const LEFT_OUT: RecordState[] = ['draft', 'enrolled', 'discarded', 'not_mine'];
const NOT_YOURS: RecordState[] = [...LEFT_OUT, 'rejected', 'removed'];
const DONE: ConversationState[] = ['done', 'waiting', 'assumed-done'];
const PARKED: ConversationState[] = ['waiting', 'deferred'];

function read(one: Thread): boolean {
  return 'etag' in one;
}

const NO_OPERATIONS: Operations = {};

function operationsOf(thread: Thread, operations: Operations): Operation[] {
  return (thread.operations ?? []).flatMap((id) => {
    const one = operations[operationKey({ id, conversation: thread.key })];
    return one ? [one] : [];
  }) as unknown as Operation[];
}

const readSoFar = new WeakMap<Threads, WeakMap<Operations, Conversation[]>>();

export function readOf(
  threads: Threads | undefined,
  operations: Operations = NO_OPERATIONS,
): Conversation[] {
  if (!threads) return [];
  const byOperations = readSoFar.get(threads) ?? new WeakMap();
  readSoFar.set(threads, byOperations);
  const known = byOperations.get(operations);
  if (known) return known;
  const conversations = Object.values(threads)
    .filter(read)
    .map(
      (one) =>
        ({
          ...one,
          comments: one.comments ?? [],
          operations: operationsOf(one, operations),
        }) as unknown as Conversation,
    );
  byOperations.set(operations, conversations);
  return conversations;
}

const detailedSoFar = new WeakMap<Thread, WeakMap<Operations, Details>>();

export function detailsOf(
  thread: Thread | undefined,
  operations: Operations = NO_OPERATIONS,
): Details | null {
  if (!thread?.read) return null;
  const byOperations = detailedSoFar.get(thread) ?? new WeakMap();
  detailedSoFar.set(thread, byOperations);
  const known = byOperations.get(operations);
  if (known) return known;
  const details: Details = {
    version: thread.read,
    comments: (thread.comments ?? []).filter(
      (one): one is Comment => one.body !== undefined,
    ),
    operations: operationsOf(thread, operations),
  };
  byOperations.set(operations, details);
  return details;
}

function tallyOf(threads: Thread[]): Tally {
  return {
    done: threads.filter((one) => DONE.includes(one.state)).length,
    total: threads.length,
    toDecide: threads.filter((one) => one.state === 'ready').length,
    agentOn: threads.filter(atWork).length,
  };
}

function groupsOf(threads: Conversation[], role: Role): Record<string, number> {
  const counted: Record<string, number> = {};
  for (const one of threads) {
    const group = groupOf(one, role);
    counted[group] = (counted[group] ?? 0) + 1;
  }
  return counted;
}

const WAITING: Move[] = [
  'first-poll',
  'await-ci',
  'await-review',
  'await-reviewers',
  'await-author',
  'await-rerequest',
  'await-rereview',
];

const BEFORE_ANYTHING: Move[] = [
  'release-worktree',
  'on-hold',
  'first-poll',
  'closed',
];

const GROUPS: Partial<Record<Move, WallGroup | null>> = {
  'on-hold': 'parked',
  'agent-running': 'agent-working',
  'agent-on-threads': 'agent-working',
  'agent-on-human-comments': 'agent-working',
  'agent-on-bot-comments': 'agent-working',
  closed: null,
  'not-reviewing': null,
  mentioned: 'waiting-on-others',
};

const DRAFT_DECISIONS: Move[] = ['human-comments', 'bot-comments'];

const YOUR_TURN: Move[] = ['review', 'rereview'];

interface Pick {
  move: Move;
  reviewers?: string[];
  stillRequested?: string[];
  mentionedBy?: string[];
}

interface Board {
  flags: ManagerFlags | null;
  isAuthor: boolean;
  drafts: number;
  human: Tally;
  bot: Tally;
}

function unique(people: string[]): string[] {
  return [...new Set(people)];
}

function behindMain(facts: PrFacts): boolean {
  return facts.merge_state === 'conflicts' || facts.merge_state === 'behind';
}

function flagsOf(facts: PrFacts | null): Flag[] {
  if (!facts) return [];
  const holds: [Flag, boolean][] = [
    ['draft', facts.draft],
    ['fix-ci', facts.ci_status === 'failing'],
    ['rebase', behindMain(facts)],
    ['unresolved-threads', (facts.unresolved_threads ?? 0) > 0],
  ];
  return holds.filter(([, held]) => held).map(([flag]) => flag);
}

function ofAuthor(facts: PrFacts): Pick {
  const requesters = facts.changes_requested_by;
  const pending = facts.pending_reviewers;
  const owed = requesters.filter((login) => !pending.includes(login));
  const ci = facts.ci_status;
  if (owed.length) return { move: 'address-feedback', reviewers: owed };
  if (ci === 'failing') return { move: 'fix-ci' };
  if (behindMain(facts)) return { move: 'rebase' };
  if (facts.merge_state === 'clean') {
    return { move: facts.draft ? 'mark-ready-for-review' : 'ready-to-merge' };
  }
  if (ci === 'pending') return { move: 'await-ci' };
  if (requesters.length) {
    return { move: 'await-rereview', reviewers: requesters };
  }
  if (pending.length) return { move: 'await-review', reviewers: pending };
  return { move: facts.draft ? 'mark-ready-for-review' : 'request-reviewers' };
}

function afterApproving(facts: PrFacts): Pick {
  const decision = facts.review_decision;
  if (decision === 'approved') return { move: 'await-author' };
  if (decision === null) {
    return { move: 'await-author', stillRequested: facts.pending_reviewers };
  }
  if (!facts.pending_reviewers.length) return { move: 'await-author' };
  return { move: 'await-reviewers', reviewers: facts.pending_reviewers };
}

function reviewedBefore(facts: PrFacts): boolean {
  return facts.my_review !== null && facts.my_review !== 'pending';
}

function unanswered(facts: PrFacts, since: string | null): string[] {
  return unique(
    facts.mentions
      .filter(
        (mention) =>
          !mention.answered &&
          (since === null || (mention.at !== null && mention.at > since)),
      )
      .map((mention) => mention.author),
  );
}

function notReviewing(facts: PrFacts): Pick {
  if (!facts.mentioned) return { move: 'not-reviewing' };
  const who = unanswered(facts, null);
  return who.length
    ? { move: 'mention', mentionedBy: who }
    : { move: 'mentioned' };
}

function ofReviewer(facts: PrFacts): Pick {
  const reviewed = reviewedBefore(facts);
  if (facts.viewer_requested) {
    return { move: reviewed ? 'rereview' : 'review' };
  }
  if (!reviewed) return notReviewing(facts);
  const sinceReview = unanswered(facts, facts.my_review_at);
  if (sinceReview.length) return { move: 'mention', mentionedBy: sinceReview };
  if (facts.my_review === 'approved') return afterApproving(facts);
  return { move: 'await-rerequest' };
}

function ofPr(facts: PrFacts): Pick {
  if (facts.ended) return { move: 'closed' };
  return roleOf(facts) === 'author' ? ofAuthor(facts) : ofReviewer(facts);
}

function agentOf(flags: ManagerFlags | null): Move | null {
  if ((flags?.working_on ?? null) !== null) return 'agent-running';
  if (flags?.threads_live) return 'agent-on-threads';
  return null;
}

function onYourPr(state: Move, board: Board): Move {
  if (state === 'address-feedback') return state;
  if (board.human.toDecide) return 'human-comments';
  if (board.human.agentOn) return 'agent-on-human-comments';
  if (board.bot.toDecide) return 'bot-comments';
  if (board.bot.agentOn) return 'agent-on-bot-comments';
  if ((board.flags?.working_on ?? null) !== null) return 'agent-running';
  return state;
}

function yourTurn(state: Move, board: Board): Move {
  const agent = agentOf(board.flags);
  if (agent) return agent;
  return board.drafts ? 'send-review' : state;
}

function onTop(state: Move | null, board: Board): Move {
  if ((board.flags?.frozen_on ?? null) !== null) return 'release-worktree';
  if (board.flags?.on_hold) return 'on-hold';
  if (state === null) return 'first-poll';
  if (state === 'closed') return state;
  if (board.isAuthor) return onYourPr(state, board);
  return YOUR_TURN.includes(state) ? yourTurn(state, board) : state;
}

function wallGroupOf(code: Move, muted: boolean): WallGroup | null {
  if (code in GROUPS) return GROUPS[code] ?? null;
  if (muted && !DRAFT_DECISIONS.includes(code)) return 'parked';
  return WAITING.includes(code) ? 'waiting-on-others' : 'needs-you';
}

function nextMoveOf(facts: PrFacts | null, board: Board): NextMove {
  const pick = facts ? ofPr(facts) : null;
  const state = pick?.move ?? null;
  const code = onTop(state, board);
  const dismissed = Boolean(board.flags?.hidden) && code !== 'release-worktree';
  const muted =
    facts !== null &&
    facts.draft &&
    board.isAuthor &&
    !BEFORE_ANYTHING.includes(code);
  const group = wallGroupOf(code, muted);
  return {
    code,
    state,
    group: dismissed ? null : group,
    muted,
    reviewers: pick?.reviewers ?? [],
    stillRequested: pick?.stillRequested ?? [],
    mentionedBy: pick?.mentionedBy ?? [],
    flags: flagsOf(facts),
    unresolved: facts?.unresolved_threads ?? 0,
  };
}

function roleOf(facts: PrFacts | null): Role | null {
  if (!facts) return null;
  return facts.is_author === true ? 'author' : 'reviewer';
}

function summarised(
  pr: PrEntity | undefined,
  threads: Threads | undefined,
  operations: Operations,
): Summaries | null {
  if (!threads && !pr?.facts && !pr?.flags) return null;
  const all = Object.values(threads ?? {});
  const facts = pr?.facts ?? null;
  const role = roleOf(facts);
  const others = all.filter(
    (one) => one.author_kind !== 'mine' && !LEFT_OUT.includes(one.record_state),
  );
  const yours = all.filter(
    (one) =>
      one.author_kind === 'mine' && !NOT_YOURS.includes(one.record_state),
  );
  const human = tallyOf(others.filter((one) => one.author_kind === 'human'));
  const bot = tallyOf(others.filter((one) => one.author_kind === 'bot'));
  const drafts = all.filter((one) => one.state === 'draft').length;
  return {
    role,
    groups: role ? groupsOf(readOf(threads, operations), role) : {},
    drafts,
    ready: role === 'author' ? human.toDecide + bot.toDecide : 0,
    yours: {
      answered: yours.filter((one) => !PARKED.includes(one.state)).length,
      total: yours.length,
    },
    human,
    bot,
    move: nextMoveOf(facts, {
      flags: pr?.flags ?? null,
      isAuthor: role === 'author',
      drafts,
      human,
      bot,
    }),
    mismatches: mismatchesOf(pr?.mismatches ?? null),
  };
}

function mismatchesOf(count: number | null): string | null {
  if (!count) return null;
  return count === 1 ? '1 mismatch' : `${count} mismatches`;
}

const NONE = {};

type Memo = WeakMap<object, WeakMap<object, Summaries | null>>;

const memo = new WeakMap<object, Memo>();

export function summaryOf(
  pr: PrEntity | undefined,
  threads: Threads | undefined,
  operations: Operations = NO_OPERATIONS,
): Summaries | null {
  const byPr: Memo = memo.get(pr ?? NONE) ?? new WeakMap();
  memo.set(pr ?? NONE, byPr);
  const byThreads = byPr.get(threads ?? NONE) ?? new WeakMap();
  byPr.set(threads ?? NONE, byThreads);
  const known = byThreads.get(operations);
  if (known !== undefined) return known;
  const summary = summarised(pr, threads, operations);
  byThreads.set(operations, summary);
  return summary;
}

export type OutstandingKind =
  'drafts' | 'board' | 'unresolved' | 'ci' | 'rebase' | 'unpushed' | 'agent';

export interface OutstandingItem {
  key: string;
  where: string;
  what: string;
  thread?: string;
}

export interface OutstandingGroup {
  kind: OutstandingKind;
  label: string;
  count: number;
  items: OutstandingItem[];
}

export interface Outstanding {
  groups: OutstandingGroup[];
  total: number;
}

const OUTSTANDING_LABELS: Record<OutstandingKind, string> = {
  drafts: 'Unsent draft comments',
  board: 'Board threads waiting on you',
  unresolved: 'Unresolved on GitHub',
  ci: 'Failing CI',
  rebase: 'Needs a rebase',
  unpushed: 'Unpushed commits',
  agent: 'Agent still working',
};

function whereOf(one: Thread): string {
  const path = one.anchor?.path;
  if (!path) return 'conversation';
  return one.anchor?.line ? `${path}:${one.anchor.line}` : path;
}

function threadItem(one: Thread, what: string): OutstandingItem {
  return { key: one.key, where: whereOf(one), what, thread: one.key };
}

function unresolvedOf(
  all: Thread[],
  listed: OutstandingItem[],
  facts: PrFacts | null,
): { items: OutstandingItem[]; count: number } {
  const open = all.filter(
    (one) => one.kind === 'review' && one.github_resolved === false,
  );
  const shown = new Set(listed.map((one) => one.key));
  const items = open
    .filter((one) => one.state !== 'done' && !shown.has(one.key))
    .map((one) => threadItem(one, one.gist ?? 'unresolved on GitHub'));
  const untracked = (facts?.unresolved_threads ?? 0) - open.length;
  if (untracked <= 0) return { items, count: items.length };
  return {
    items: [
      ...items,
      {
        key: 'untracked',
        where: 'GitHub',
        what: `${untracked} more the board does not track`,
      },
    ],
    count: items.length + untracked,
  };
}

function rebaseOf(pr: PrEntity): OutstandingItem[] {
  const facts = pr.facts;
  if (!facts || !behindMain(facts)) return [];
  const base = pr.drawn?.system.base ?? null;
  const onto = pr.base_branch ?? 'the base';
  const standing = base
    ? `${base.behind_by} commits behind`
    : facts.merge_state === 'conflicts'
      ? 'conflicts'
      : 'behind';
  return [
    { key: 'base', where: onto, what: standing },
    ...(base?.conflicts ?? []).map((path) => ({
      key: `conflict:${path}`,
      where: path,
      what: 'conflicts',
    })),
  ];
}

function agentOutstandingOf(pr: PrEntity): OutstandingItem[] {
  const system = pr.drawn?.system;
  if (!system) return [];
  const working: OutstandingItem[] =
    system.agent.state === 'working'
      ? [
          {
            key: 'agent',
            where: system.agent.name,
            what: `working on ${system.agent.event ?? 'a run'}`,
          },
        ]
      : [];
  return [
    ...working,
    ...system.queue.map((queued, at) => ({
      key: `queued:${at}`,
      where: 'queued',
      what: queued.event ?? 'an event',
    })),
  ];
}

function outstandingFrom(
  pr: PrEntity,
  threads: Threads | undefined,
): Outstanding {
  const all = Object.values(threads ?? {});
  const facts = pr.facts;
  const board =
    roleOf(facts) === 'author'
      ? all
          .filter(
            (one) =>
              one.state === 'ready' &&
              one.author_kind !== 'mine' &&
              !LEFT_OUT.includes(one.record_state),
          )
          .map((one) => threadItem(one, one.gist ?? 'waiting on you'))
      : [];
  const unresolved = unresolvedOf(all, board, facts);
  const items: Record<OutstandingKind, OutstandingItem[]> = {
    drafts: all
      .filter((one) => one.state === 'draft')
      .map((one) => threadItem(one, one.gist ?? 'unsent comment')),
    board,
    unresolved: unresolved.items,
    ci: (facts?.checks ?? [])
      .filter((one) => one.failed)
      .map((one) => ({
        key: `check:${one.name}`,
        where: one.name,
        what: one.summary ?? 'failed',
      })),
    rebase: rebaseOf(pr),
    unpushed: (pr.drawn?.system.unpushed_commits ?? []).map((commit) => ({
      key: `commit:${commit.sha}`,
      where: commit.sha,
      what: commit.subject,
    })),
    agent: agentOutstandingOf(pr),
  };
  const groups = (Object.keys(OUTSTANDING_LABELS) as OutstandingKind[])
    .filter((kind) => items[kind].length)
    .map((kind) => ({
      kind,
      label: OUTSTANDING_LABELS[kind],
      count: kind === 'unresolved' ? unresolved.count : items[kind].length,
      items: items[kind],
    }));
  return {
    groups,
    total: groups.reduce((sum, group) => sum + group.count, 0),
  };
}

const outstandingMemo = new WeakMap<object, WeakMap<object, Outstanding>>();

export function outstandingOf(
  pr: PrEntity,
  threads: Threads | undefined,
): Outstanding {
  const byPr = outstandingMemo.get(pr) ?? new WeakMap<object, Outstanding>();
  outstandingMemo.set(pr, byPr);
  const known = byPr.get(threads ?? NONE);
  if (known) return known;
  const found = outstandingFrom(pr, threads);
  byPr.set(threads ?? NONE, found);
  return found;
}

const counted = new WeakMap<Diff, FileStat[]>();

export function filesOf(diff: Diff): FileStat[] {
  const known = counted.get(diff);
  if (known) return known;
  const files = diff.files.map(({ path, added, removed }) => ({
    path,
    added,
    removed,
  }));
  counted.set(diff, files);
  return files;
}

export type Square = 'added' | 'deleted' | 'neutral';

export interface PrHeader {
  title: string | null;
  createdAt: string | null;
  commits: string | null;
  additions: number;
  deletions: number;
  squares: Square[];
}

const SQUARES = 5;

function squaresOf(additions: number, deletions: number): Square[] {
  const changed = additions + deletions;
  const added = changed ? Math.floor((additions / changed) * SQUARES) : 0;
  const deleted = changed ? Math.floor((deletions / changed) * SQUARES) : 0;
  return [
    ...Array<Square>(added).fill('added'),
    ...Array<Square>(deleted).fill('deleted'),
    ...Array<Square>(SQUARES - added - deleted).fill('neutral'),
  ];
}

const headed = new WeakMap<PrEntity, PrHeader>();

export function prHeaderOf(pr: PrEntity): PrHeader {
  const known = headed.get(pr);
  if (known) return known;
  const { title, created_at, commits, additions, deletions } = pr;
  const header = {
    title,
    createdAt: created_at,
    commits:
      commits === null ? null : `${commits} commit${commits === 1 ? '' : 's'}`,
    additions,
    deletions,
    squares: squaresOf(additions, deletions),
  };
  headed.set(pr, header);
  return header;
}

export interface Place {
  group: WallGroup | null;
  joined: number;
  arrived: number;
  moved: boolean;
  entered: number;
}

export interface WallRow extends ShownPr {
  key: string;
  summaries: Summaries;
  arrived: number;
  moved: boolean;
  entered: number;
}

export interface WallSection {
  group: WallGroup;
  name: string;
  level: Level;
  edge: string;
  prs: WallRow[];
}

export function placeOf(
  was: Place | null,
  summaries: Summaries,
  joined: () => number,
  entered: (group: WallGroup | null, seenMoving: boolean) => number,
): Place {
  const group = summaries.move.group;
  if (was && was.group === group) return was;
  const at = joined();
  return {
    group,
    joined: at,
    arrived: was?.arrived ?? at,
    moved: was !== null,
    entered: entered(group, was !== null),
  };
}

export interface Entered {
  group: WallGroup | null;
  at: number;
}

export function enteredAt(
  remembered: Entered | undefined,
  group: WallGroup | null,
  seenMoving: boolean,
  lastEventAt: string | null,
  now: number,
): number {
  if (seenMoving) return now;
  if (remembered?.group === group) return remembered.at;
  const lastEvent = Date.parse(lastEventAt ?? '');
  return Number.isNaN(lastEvent) ? now : Math.min(lastEvent, now);
}

type Placed = WallRow & { joined: number; group: WallGroup | null };

function wallBuilt(
  groups: WallGroupName[],
  prs: Record<string, PrEntity>,
  threads: Record<string, Threads>,
  operations: Record<string, Operations>,
): WallSection[] {
  const placed = Object.entries(prs).flatMap(([key, pr]): Placed[] => {
    const summaries = summaryOf(pr, threads[key], operations[key]);
    const { drawn, place } = pr;
    return summaries && place && drawn
      ? [{ ...pr, key, drawn, summaries, ...place }]
      : [];
  });
  return groups
    .map(({ group, name }) => ({
      group,
      name,
      level: levelOf(group),
      edge: edgeOf(group),
      prs: placed
        .filter((one) => one.group === group)
        .sort((one, other) => one.joined - other.joined),
    }))
    .filter((section) => section.prs.length > 0);
}

let lastWall: {
  groups: WallGroupName[];
  prs: Record<string, PrEntity>;
  threads: Record<string, Threads>;
  operations: Record<string, Operations>;
  wall: WallSection[];
} | null = null;

export function wallOf(
  groups: WallGroupName[] | null,
  prs: Record<string, PrEntity>,
  threads: Record<string, Threads>,
  operations: Record<string, Operations>,
): WallSection[] {
  if (!groups) return [];
  if (
    lastWall?.groups === groups &&
    lastWall.prs === prs &&
    lastWall.threads === threads &&
    lastWall.operations === operations
  ) {
    return lastWall.wall;
  }
  const wall = wallBuilt(groups, prs, threads, operations);
  lastWall = { groups, prs, threads, operations, wall };
  return wall;
}

let lastHeld: { prs: Record<string, PrEntity>; held: number } | null = null;

export function heldOf(prs: Record<string, PrEntity>): number {
  if (lastHeld?.prs === prs) return lastHeld.held;
  const held = Object.values(prs).filter((pr) => pr.place !== null).length;
  lastHeld = { prs, held };
  return held;
}

export interface Shown {
  sections: WallSection[];
  needYou: number;
  hidden: number;
}

function shownBuilt(wall: WallSection[], chosen: string[] | null): Shown {
  const sections = chosen
    ? wall
        .map((section) => ({
          ...section,
          prs: section.prs.filter((pr) => chosen.includes(pr.repo)),
        }))
        .filter((section) => section.prs.length > 0)
    : wall;
  const held = (of: WallSection[]): number =>
    of.reduce((sum, section) => sum + section.prs.length, 0);
  const needing = sections.find((section) => section.group === 'needs-you');
  return {
    sections,
    needYou: needing?.prs.length ?? 0,
    hidden: held(wall) - held(sections),
  };
}

let lastShown: {
  wall: WallSection[];
  chosen: string;
  shown: Shown;
} | null = null;

export function shownOf(wall: WallSection[], chosen: string[] | null): Shown {
  const asked = chosen ? chosen.join(',') : '';
  if (lastShown?.wall === wall && lastShown.chosen === asked) {
    return lastShown.shown;
  }
  const shown = shownBuilt(wall, chosen);
  lastShown = { wall, chosen: asked, shown };
  return shown;
}

export type SummaryState =
  | 'none-yet-reviewer'
  | 'none-yet-author'
  | 'running'
  | 'ready'
  | 'stale'
  | 'needs-github-api'
  | 'failed';

export interface SummaryTab {
  state: SummaryState;
  sha: string | null;
  head: string | null;
  behind: string | null;
  finished: string | null;
  since: string | null;
  witnesses: WitnessProgress[];
  witnessesDone: number;
  witnessCount: number;
  exitStatus: number | null;
  reason: string | null;
  calls: number | null;
  markdown: string | null;
}

const SHORT_SHA = 7;

const NEEDS_GITHUB_API = 3;

const API_CALLS = /about (\d+) API calls/;

function shortOf(sha: string | null): string | null {
  return sha ? sha.slice(0, SHORT_SHA) : null;
}

function linesOf(text: string | null): string[] {
  return (text ?? '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function stateOf(
  summary: PrSummaryEntity,
  head: string | null,
  role: Role | null,
): SummaryState {
  const { running, exit_status, stderr } = summary;
  if (running) return 'running';
  if (exit_status === NEEDS_GITHUB_API) return 'needs-github-api';
  if (exit_status === null && stderr) return 'failed';
  if (exit_status === null) {
    return role !== 'author' && summary.wanted
      ? 'none-yet-reviewer'
      : 'none-yet-author';
  }
  if (exit_status !== 0) return 'failed';
  return head !== null && summary.head_sha !== head ? 'stale' : 'ready';
}

function reasonOf(state: SummaryState, stderr: string | null): string | null {
  const lines = linesOf(stderr);
  if (state === 'needs-github-api') return lines[0] ?? null;
  if (state === 'failed') return lines.at(-1) ?? null;
  return null;
}

function behindOf(count: number | null): string | null {
  if (!count) return null;
  return count === 1 ? '1 commit behind' : `${count} commits behind`;
}

function summaryTabBuilt(
  summary: PrSummaryEntity,
  head: string | null,
  role: Role | null,
): SummaryTab {
  const state = stateOf(summary, head, role);
  const calls = API_CALLS.exec(summary.stderr ?? '')?.[1];
  return {
    state,
    sha: shortOf(summary.head_sha),
    head: shortOf(head),
    behind: behindOf(summary.behind),
    finished: summary.finished,
    since: summary.since,
    witnesses: summary.witnesses,
    witnessesDone: summary.witnesses.filter((one) => one.done).length,
    witnessCount: summary.agents ?? 0,
    exitStatus: summary.exit_status,
    reason: reasonOf(state, summary.stderr),
    calls: calls === undefined ? null : Number(calls),
    markdown: summary.markdown,
  };
}

const lastTabs = new WeakMap<
  PrSummaryEntity,
  { head: string | null; role: Role | null; tab: SummaryTab }
>();

export function summaryTabOf(
  summary: PrSummaryEntity,
  head: string | null,
  role: Role | null,
): SummaryTab {
  const last = lastTabs.get(summary);
  if (last?.head === head && last.role === role) return last.tab;
  const tab = summaryTabBuilt(summary, head, role);
  lastTabs.set(summary, { head, role, tab });
  return tab;
}

export type PipState = 'read' | 'current' | 'unread' | 'range';

export interface Pip {
  sha: string;
  state: PipState;
  merge: boolean;
  label: string;
}

export interface DiffRange extends Commits {
  merged?: string;
}

export function isMerge(commit: PullRequestCommit): boolean {
  return commit.parents.length > 1;
}

function rangeOf(
  history: PullRequestCommits,
  from: number,
  to: number,
): DiffRange {
  const { commits } = history;
  const base = commits[from]!.parents[0] ?? history.fork;
  const head = commits[to]!.sha;
  const merge = commits.slice(from, to + 1).findLast(isMerge);
  return merge ? { base, head, merged: merge.parents.at(-1)! } : { base, head };
}

export interface MergeNote {
  came: number | null;
  own: string[];
}

export function mergeNoteOf(
  own: FileStat[] | null,
  merged: FileStat[] | null,
): MergeNote | null {
  if (!own) return null;
  const changed = new Set(own.map((one) => one.path));
  return {
    came: merged && merged.filter((one) => !changed.has(one.path)).length,
    own: [...changed],
  };
}

export interface ResetStanding {
  queued: boolean;
  outcome: string | null;
  ranAt: string | null;
}

export function resetStandingOf(
  kept: ResetToOrigin | null | undefined,
): ResetStanding | null {
  if (!kept) return null;
  return {
    queued: kept.queued_at !== null,
    outcome:
      kept.ran_at === null
        ? null
        : kept.refused === null
          ? 'Reset to origin when the agent finished.'
          : `The queued reset didn't run: ${kept.refused}`,
    ranAt: kept.ran_at,
  };
}

export interface Stepper {
  place: number;
  count: number;
  sha: string;
  short: string;
  subject: string;
  author: string;
  authoredAt: string;
  read: boolean;
  merge: boolean;
  offOrigin: string | null;
  range: DiffRange;
  previous: string | null;
  next: string | null;
  pips: Pip[];
  thin: boolean;
}

function pickedUpAt(
  history: PullRequestCommits,
  read: Set<string>,
  reviewed: string | null,
  skipMerges = false,
): number {
  const reviewedAt = history.commits.findIndex((one) => one.sha === reviewed);
  if (reviewedAt < 0) return -1;
  return history.commits.findIndex(
    (one, index) =>
      index > reviewedAt && !read.has(one.sha) && !(skipMerges && isMerge(one)),
  );
}

function offOriginOf(standing: Standing, sha: string): string | null {
  if (!standing.offOrigin.has(sha)) return null;
  return standing.diverged ? 'not on origin' : 'not pushed';
}

const lastStandings = new WeakMap<
  PullRequestCommits,
  { pushed: PullRequestCommits | undefined; standing: Standing }
>();

function standingBuilt(
  history: PullRequestCommits,
  pushed: PullRequestCommits | undefined,
): Standing {
  if (!pushed) return { offOrigin: new Set(), diverged: null };
  const local = history.commits.map((one) => one.sha);
  const originHead = pushed.commits.at(-1)?.sha ?? pushed.fork;
  const at = local.indexOf(originHead);
  if (at >= 0 || originHead === history.fork)
    return { offOrigin: new Set(local.slice(at + 1)), diverged: null };
  const onOrigin = new Set(pushed.commits.map((one) => one.sha));
  const here = local.filter((sha) => !onOrigin.has(sha));
  if (!here.length) return { offOrigin: new Set(), diverged: null };
  const kept = new Set(local);
  return {
    offOrigin: new Set(here),
    diverged: {
      here: here.length,
      there: pushed.commits.filter((one) => !kept.has(one.sha)),
    },
  };
}

export function standingOf(
  history: PullRequestCommits,
  pushed: PullRequestCommits | undefined,
): Standing {
  const last = lastStandings.get(history);
  if (last && last.pushed === pushed) return last.standing;
  const standing = standingBuilt(history, pushed);
  lastStandings.set(history, { pushed, standing });
  return standing;
}

interface Matching {
  read: Set<string>;
  matched: Set<string>;
  fresh: string[];
}

const lastMatching = new WeakMap<
  PullRequestCommits,
  { marks: ReadMark[]; matching: Matching }
>();

function matchingOf(history: PullRequestCommits, marks: ReadMark[]): Matching {
  const last = lastMatching.get(history);
  if (last?.marks === marks) return last.matching;
  const present = new Set(history.commits.map((one) => one.sha));
  const marked = new Set(marks.map((one) => one.sha));
  const goneSubjects = new Set(
    marks.filter((one) => !present.has(one.sha)).map((one) => one.subject),
  );
  const matched = new Set(
    history.commits
      .filter((one) => !marked.has(one.sha) && goneSubjects.has(one.subject))
      .map((one) => one.sha),
  );
  const read = new Set([...marked, ...matched]);
  const matching = {
    read,
    matched,
    fresh: history.commits
      .filter((one) => !read.has(one.sha))
      .map((one) => one.sha),
  };
  lastMatching.set(history, { marks, matching });
  return matching;
}

function stepperBuilt(
  history: PullRequestCommits,
  marks: ReadMark[],
  chosen: string | null,
  reviewed: string | null,
  picked: Picked | null,
  skipMerges: boolean,
  pushed: PullRequestCommits | undefined,
): Stepper | null {
  const { commits } = history;
  if (!commits.length) return null;
  const { read } = matchingOf(history, marks);
  const stops = (one: PullRequestCommit) => !(skipMerges && isMerge(one));
  const chosenAt = commits.findIndex((one) => one.sha === chosen);
  const pickedUp = pickedUpAt(history, read, reviewed, skipMerges);
  const unreadAt = commits.findIndex((one) => !read.has(one.sha) && stops(one));
  const lastAt = commits.findLastIndex(stops);
  const at =
    chosenAt >= 0
      ? chosenAt
      : pickedUp >= 0
        ? pickedUp
        : unreadAt >= 0
          ? unreadAt
          : lastAt >= 0
            ? lastAt
            : commits.length - 1;
  const commit = commits[at]!;
  const from = commits.findIndex((one) => one.sha === picked?.from);
  const to = commits.findIndex((one) => one.sha === picked?.to);
  const stateOf = (sha: string, index: number): PipState =>
    from >= 0 && index >= from && index <= to
      ? 'range'
      : index === at
        ? 'current'
        : read.has(sha)
          ? 'read'
          : 'unread';
  return {
    place: at + 1,
    count: commits.length,
    sha: commit.sha,
    short: commit.sha.slice(0, SHORT_SHA),
    subject: commit.subject,
    author: commit.author,
    authoredAt: commit.authored_at,
    read: read.has(commit.sha),
    merge: isMerge(commit),
    offOrigin: offOriginOf(standingOf(history, pushed), commit.sha),
    range: rangeOf(history, at, at),
    previous: commits.slice(0, at).findLast(stops)?.sha ?? null,
    next: commits.slice(at + 1).find(stops)?.sha ?? null,
    pips: commits.map((one, index) => ({
      sha: one.sha,
      state: stateOf(one.sha, index),
      merge: isMerge(one),
      label: `${index + 1} of ${commits.length} · ${one.sha.slice(0, SHORT_SHA)} ${one.subject}`,
    })),
    thin: commits.length > LONG,
  };
}

const lastSteppers = new WeakMap<
  PullRequestCommits,
  {
    marks: ReadMark[];
    chosen: string | null;
    reviewed: string | null;
    picked: Picked | null;
    skipMerges: boolean;
    pushed: PullRequestCommits | undefined;
    stepper: Stepper | null;
  }
>();

export function stepperOf(
  history: PullRequestCommits | undefined,
  marks: ReadMark[] | null,
  chosen: string | null,
  reviewed: string | null,
  picked: Picked | null,
  skipMerges: boolean,
  pushed: PullRequestCommits | undefined,
): Stepper | null | undefined {
  if (!history || !marks) return undefined;
  const last = lastSteppers.get(history);
  if (
    last?.marks === marks &&
    last.chosen === chosen &&
    last.reviewed === reviewed &&
    last.picked === picked &&
    last.skipMerges === skipMerges &&
    last.pushed === pushed
  )
    return last.stepper;
  const stepper = stepperBuilt(
    history,
    marks,
    chosen,
    reviewed,
    picked,
    skipMerges,
    pushed,
  );
  lastSteppers.set(history, {
    marks,
    chosen,
    reviewed,
    picked,
    skipMerges,
    pushed,
    stepper,
  });
  return stepper;
}

interface Rebased {
  pushedOn: string | null;
  matched: number;
  unchanged: number;
}

export interface CommitNote {
  count: number;
  reviewedOn: string;
  head: string;
  rebased: Rebased | null;
}

function commitNoteBuilt(
  history: PullRequestCommits,
  facts: PrFacts,
  marks: ReadMark[],
): CommitNote | null {
  const { commits, reviewed } = history;
  if (!facts.my_review_at) return null;
  const { read, matched, fresh } = matchingOf(history, marks);
  if (reviewed && commits.length)
    return {
      count: fresh.length,
      reviewedOn: dayOf(facts.my_review_at),
      head: commits[commits.length - 1]!.sha,
      rebased: {
        pushedOn: facts.force_pushed_at && dayOf(facts.force_pushed_at),
        matched: matched.size,
        unchanged: commits.length - matched.size - fresh.length,
      },
    };
  if (pickedUpAt(history, read, facts.my_review_sha) < 0) return null;
  const reviewedAt = commits.findIndex(
    (one) => one.sha === facts.my_review_sha,
  );
  const count = commits.length - reviewedAt - 1;
  return {
    count,
    reviewedOn: dayOf(facts.my_review_at),
    head: commits[commits.length - 1]!.sha,
    rebased: null,
  };
}

const lastNotes = new WeakMap<
  PullRequestCommits,
  { facts: PrFacts; marks: ReadMark[]; note: CommitNote | null }
>();

export function commitNoteOf(
  history: PullRequestCommits | undefined,
  facts: PrFacts | null,
  marks: ReadMark[] | null,
): CommitNote | null {
  if (!history || !facts || !marks) return null;
  const last = lastNotes.get(history);
  if (last?.facts === facts && last.marks === marks) return last.note;
  const note = commitNoteBuilt(history, facts, marks);
  lastNotes.set(history, { facts, marks, note });
  return note;
}

export interface PickedRange {
  fromShort: string;
  toShort: string;
  count: number;
  range: DiffRange;
  head: boolean;
}

function pickedRangeBuilt(
  history: PullRequestCommits,
  picked: Picked,
): PickedRange | null {
  const { commits } = history;
  const from = commits.findIndex((one) => one.sha === picked.from);
  const to = commits.findIndex((one) => one.sha === picked.to);
  if (from < 0 || to < from) return null;
  return {
    fromShort: picked.from.slice(0, SHORT_SHA),
    toShort: picked.to.slice(0, SHORT_SHA),
    count: to - from + 1,
    range: rangeOf(history, from, to),
    head: to === commits.length - 1,
  };
}

const lastPicked = new WeakMap<
  PullRequestCommits,
  { picked: Picked; range: PickedRange | null }
>();

export function pickedRangeOf(
  history: PullRequestCommits | undefined,
  picked: Picked | null,
): PickedRange | null {
  if (!history || !picked) return null;
  const last = lastPicked.get(history);
  if (last?.picked === picked) return last.range;
  const range = pickedRangeBuilt(history, picked);
  lastPicked.set(history, { picked, range });
  return range;
}

export interface Looking {
  current: string | null;
  picked: Picked | null;
  hidden: boolean;
  across: number;
}

const lastTimelines = new WeakMap<
  PullRequestCommits,
  {
    pr: PrEntity;
    current: string | null;
    picked: Picked | null;
    hidden: boolean;
    basePr: number | null;
    pushed: PullRequestCommits | undefined;
    across: number;
    timeline: Timeline | null;
  }
>();

export function timelineOf(
  pr: PrEntity,
  history: PullRequestCommits | undefined,
  { current, picked, hidden, across }: Looking,
  basePr: number | null,
  pushed: PullRequestCommits | undefined,
): Timeline | null | undefined {
  if (!history || !pr.read) return undefined;
  const last = lastTimelines.get(history);
  if (
    last?.pr === pr &&
    last.current === current &&
    last.picked === picked &&
    last.hidden === hidden &&
    last.basePr === basePr &&
    last.pushed === pushed &&
    last.across === across
  )
    return last.timeline;
  const { read, matched, fresh } = matchingOf(history, pr.read);
  const timeline = timelineBuilt({
    history,
    read,
    matched,
    fresh,
    branch: pr.branch,
    base: pr.base_branch,
    reviewedSha: pr.facts?.my_review_sha ?? null,
    reviewedAt: pr.facts?.my_review_at ?? null,
    current,
    picked,
    hidden,
    repo: pr.repo,
    basePr,
    standing: standingOf(history, pushed),
    across,
  });
  lastTimelines.set(history, {
    pr,
    current,
    picked,
    hidden,
    basePr,
    pushed,
    across,
    timeline,
  });
  return timeline;
}
