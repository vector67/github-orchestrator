import type {
  Comment,
  Conversation,
  ConversationState,
  Diff,
  ManagerFlags,
  Operation,
  PrFacts,
  RecordState,
  WallGroup,
  WallGroupName,
} from 'frontend/data/api';
import { groupOf, type Role } from 'frontend/data/groups';
import type { Details, FileStat } from 'frontend/data/panel';
import { atWork } from 'frontend/data/thread';
import { levelOf, type Level } from 'frontend/data/wall';
import {
  operationKey,
  type StoredOperation,
  type Thread,
} from 'frontend/data/entities';
import type { PrEntity, ShownPr } from 'frontend/services/store';

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
  'on-hold': 'on-hold',
  'agent-running': 'agent-working',
  'agent-on-threads': 'agent-working',
  'agent-on-human-comments': 'agent-working',
  'agent-on-bot-comments': 'agent-working',
  closed: null,
  'not-reviewing': null,
  mentioned: 'mentioned',
};

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
    ['unresolved-threads', Boolean(facts.unresolved_threads)],
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
  if (facts.merge_state === 'clean') return { move: 'ready-to-merge' };
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
  return {
    move: 'await-reviewers',
    reviewers: unique([
      ...facts.pending_reviewers,
      ...facts.changes_requested_by,
    ]),
  };
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

function wallGroupOf(code: Move): WallGroup | null {
  if (code in GROUPS) return GROUPS[code] ?? null;
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
  const group = muted ? 'draft' : wallGroupOf(code);
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
  };
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

export interface Place {
  group: WallGroup | null;
  joined: number;
  moved: boolean;
}

export interface WallRow extends ShownPr {
  key: string;
  summaries: Summaries;
  moved: boolean;
}

export interface WallSection {
  group: WallGroup;
  name: string;
  level: Level;
  prs: WallRow[];
}

export function placeOf(
  was: Place | null,
  summaries: Summaries,
  joined: () => number,
): Place {
  const group = summaries.move.group;
  if (was && was.group === group) return was;
  return { group, joined: joined(), moved: was !== null };
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
