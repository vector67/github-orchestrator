import type {
  DashboardStatus,
  DashboardSystem,
  FinishedRun,
  FrozenWorktree,
  PrFacts,
  WallGroup,
} from 'frontend/data/api';
import { tildeOf } from 'frontend/data/address';
import { countsOf as groupCountsOf, READY_GROUP } from 'frontend/data/groups';
import type {
  Flag as FlagCode,
  Move,
  NextMove,
  Summaries,
  ShownPr,
  Tally,
} from 'frontend/services/store';

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function lengthOf(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const days = Math.floor(whole / DAY);
  const hours = Math.floor((whole % DAY) / HOUR);
  const minutes = Math.floor((whole % HOUR) / MINUTE);
  const rest = whole % MINUTE;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${rest}s`;
  return `${rest}s`;
}

const RUN_NAMES: Record<string, string> = {
  'ci-failed': 'CI fix',
  'became-unmergeable': 'rebase on main',
  'review-requested': 'review',
  'pushed-since-review': 're-review',
  'manual-continue': 'carry on',
  'pr-closed': 'clean-up',
};

const THREAD_RUNS = ['thread-fix-', 'candidate-'];

export function runNameOf(event: string): string {
  if (THREAD_RUNS.some((prefix) => event.startsWith(prefix))) {
    return 'thread fix';
  }
  return RUN_NAMES[event] ?? event;
}

const SIGNALS: Record<number, string> = {
  1: 'SIGHUP',
  2: 'SIGINT',
  3: 'SIGQUIT',
  6: 'SIGABRT',
  9: 'SIGKILL',
  11: 'SIGSEGV',
  13: 'SIGPIPE',
  14: 'SIGALRM',
  15: 'SIGTERM',
};

export function exitWordOf(code: number | null): string {
  if (code === null) return 'exit unknown';
  if (code === 0) return 'ok';
  if (code > 0) return `exit ${code}`;
  const name = SIGNALS[-code];
  return name ? `killed (${name})` : `killed (signal ${-code})`;
}

export function clockOf(ms: number): string {
  return new Date(ms).toLocaleTimeString('en-GB', { hour12: false });
}

export function relativeOf(iso: string | null, now: number): string {
  if (!iso) return '—';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '—';
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < MINUTE) return `${seconds}s ago`;
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m ago`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h ago`;
  return `${Math.floor(seconds / DAY)}d ago`;
}

function graceOf(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return whole >= MINUTE ? `${Math.floor(whole / MINUTE)}m` : `${whole}s`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function listed(people: string[]): string {
  return people.join(', ');
}

const WAITING_FOR_AUTHOR = 'Waiting for author';

const STATE_LABELS: Partial<Record<Move, string>> = {
  closed: 'Merged or closed',
  'fix-ci': 'Fix CI',
  rebase: 'Rebase on main',
  'address-feedback': 'Address review feedback',
  'ready-to-merge': 'Ready to merge',
  'await-review': 'Waiting for review',
  'request-reviewers': 'Request reviewers',
  'mark-ready-for-review': 'Mark ready for review',
  'await-rereview': 'Waiting for re-review',
  'await-ci': 'CI running',
  'not-reviewing': 'Not reviewing',
  review: 'Review this PR',
  rereview: 'Review this PR',
  'await-reviewers': 'Waiting on reviewers',
  'await-author': WAITING_FOR_AUTHOR,
  'await-rerequest': WAITING_FOR_AUTHOR,
  mention: 'Answer the mention',
  mentioned: 'Mentioned',
};

function labelOf(state: Move): string {
  return STATE_LABELS[state] ?? state;
}

const CI_WORDS: Record<string, string> = {
  passing: 'CI passing',
  failing: 'CI failing',
  pending: 'CI pending',
};

type Polled = Pick<
  PrFacts,
  | 'ci_status'
  | 'review_decision'
  | 'my_review'
  | 'changes_requested_by'
  | 'pending_reviewers'
  | 'unresolved_threads'
>;

const UNPOLLED: Polled = {
  ci_status: 'pending',
  review_decision: null,
  my_review: null,
  changes_requested_by: [],
  pending_reviewers: [],
  unresolved_threads: null,
};

function polledOf(shown: ShownPr): Polled {
  return shown.facts ?? UNPOLLED;
}

function unresolvedOf(facts: Polled): string {
  const unresolved = facts.unresolved_threads;
  return unresolved !== null
    ? `${unresolved} unresolved comments`
    : 'unresolved comments';
}

function afterApprovingOf(move: NextMove): string {
  const still = move.stillRequested;
  return still.length
    ? `You approved | ${listed(still)} still requested`
    : 'You approved';
}

function awaitingReviewOf(status: DashboardStatus, facts: Polled): string {
  const approved = status.approved_by;
  const parts = approved.map((login) => `${login} approved`);
  if (facts.pending_reviewers.length) {
    parts.push(`Waiting on: ${listed(facts.pending_reviewers)}`);
  } else if (!approved.length) {
    parts.push('No reviewers assigned');
  }
  return parts.join(' | ');
}

const EVERY_MENTION_ANSWERED = 'Every mention answered';

function mentionedOf(move: NextMove): string {
  return `${listed(move.mentionedBy)} mentioned you`;
}

function detailOf(state: Move, shown: ShownPr, move: NextMove): string {
  const status = shown.drawn.status;
  const facts = polledOf(shown);
  const ci = CI_WORDS[facts.ci_status] ?? `CI ${facts.ci_status}`;
  switch (state) {
    case 'fix-ci':
      return status.failed_checks.length
        ? `Failed: ${listed(status.failed_checks)}`
        : 'Fix CI failures';
    case 'rebase':
      return 'Merge conflicts detected';
    case 'address-feedback':
      return `${listed(facts.changes_requested_by) || 'Reviewer'} requested changes | ${unresolvedOf(facts)}`;
    case 'ready-to-merge':
      return `Approved by ${listed(status.approved_by) || 'Reviewer'} | CI passing`;
    case 'await-review':
    case 'request-reviewers':
    case 'mark-ready-for-review':
      return awaitingReviewOf(status, facts);
    case 'await-rereview':
      return `Waiting on ${listed(move.reviewers)} to re-review`;
    case 'await-ci':
      return `${status.checks_done}/${status.checks_total} checks complete`;
    case 'review':
      return `${ci} | ${status.changed_files ?? '?'} files changed | no reviews yet`;
    case 'rereview':
      return `Re-review requested | ${ci}`;
    case 'await-reviewers':
      return move.reviewers.length
        ? `You approved | Waiting on review from: ${listed(move.reviewers)}`
        : 'You approved';
    case 'await-author':
      return afterApprovingOf(move);
    case 'await-rerequest':
      return 'Waiting for the author to ask you to review again';
    case 'not-reviewing':
      return 'You are not a reviewer on this PR';
    case 'mention':
      return mentionedOf(move);
    case 'mentioned':
      return EVERY_MENTION_ANSWERED;
    default:
      return '';
  }
}

interface Action {
  label: string;
  detail: string;
}

function actionOf(shown: ShownPr, move: NextMove): Action | null {
  const state = move.state;
  if (!state) return null;
  return {
    label: labelOf(state),
    detail: detailOf(state, shown, move),
  };
}

const FIRST_POLL = 'Waiting for the first poll';

function commentsOf(who: string, counts: Tally, rest: string): string {
  return `${who} comments · ${counts.done}/${counts.total} done · ${rest}`;
}

const AGENT_DOING: Record<string, string> = {
  'ci-failed': 'fixing CI',
  'became-unmergeable': 'rebasing on main',
  'review-requested': 'reviewing',
  'manual-continue': 'carrying on',
};

function moveOf(shown: ShownPr, summaries: Summaries): string {
  const { threads, queued_events: queued, agent } = shown.drawn.system;
  const { move, human, bot } = summaries;
  const code = move.code;
  switch (code) {
    case 'release-worktree':
      return 'Release the worktree';
    case 'on-hold':
      return queued ? `On hold, ${plural(queued, 'event')} held` : 'On hold';
    case 'address-feedback':
      return `Address changes requested from ${listed(move.reviewers)}`;
    case 'human-comments':
      return commentsOf('Human', human, `${human.toDecide} to decide`);
    case 'agent-on-human-comments':
      return commentsOf('Human', human, `agent on ${human.agentOn}`);
    case 'bot-comments':
      return commentsOf('Bot', bot, `${bot.toDecide} to decide`);
    case 'agent-on-bot-comments':
      return commentsOf('Bot', bot, `agent on ${bot.agentOn}`);
    case 'send-review':
      return `Send your review · ${plural(summaries.drafts, 'draft')}`;
    case 'agent-running': {
      const event = agent.event ?? '';
      return `Agent is ${AGENT_DOING[event] ?? `working on ${event}`}`;
    }
    case 'agent-on-threads':
      return `Agent is working on ${plural(threads.live, 'thread')}`;
    case 'first-poll':
      return FIRST_POLL;
    case 'await-ci':
      return 'Waiting on CI';
    case 'await-rereview':
      return `Waiting on ${listed(move.reviewers)} to re-review`;
    case 'await-review':
    case 'await-reviewers':
      return move.reviewers.length
        ? `Waiting on reviewers ${listed(move.reviewers)}`
        : 'Waiting on reviewers';
    case 'await-author':
      return move.stillRequested.length
        ? `Waiting on the author · ${listed(move.stillRequested)} still requested`
        : 'Waiting on the author';
    case 'await-rerequest':
      return 'Waiting on the author to ask you again';
    case 'rereview':
      return `Re-review · ${summaries.yours.answered}/${summaries.yours.total} of your threads answered`;
    case 'mention':
      return mentionedOf(move);
    case 'mentioned':
      return EVERY_MENTION_ANSWERED;
    default:
      return labelOf(code);
  }
}

function sinceOf(shown: ShownPr): string[] | null {
  const since = shown.drawn.status.since_you_last_acted;
  if (!since) return null;
  const said: string[] = [];
  if (since.force_pushed) said.push('force-pushed');
  else if (since.commits) said.push(plural(since.commits, 'commit'));
  if (since.reviews) said.push(plural(since.reviews, 'review'));
  if (since.comments) said.push(plural(since.comments, 'comment'));
  if (since.threads_resolved) {
    said.push(`${plural(since.threads_resolved, 'thread')} resolved`);
  }
  return said.length ? said : ['nothing new'];
}

function whoseOf(shown: ShownPr, summaries: Summaries): string | null {
  if (!shown.drawn.polled) return null;
  if (summaries.role === 'author') return 'your PR';
  return shown.author ? `${shown.author}'s PR` : 'reviewing';
}

export interface DismissWording {
  untilNextEvent: string;
  forever: string;
  foreverDetail: string;
}

function dismissOf(shown: ShownPr): DismissWording {
  return {
    untilNextEvent: 'until next event',
    forever: 'forever — removes the worktree',
    foreverDetail: `Stops the watcher tracking this PR. Reverse it with: ${shown.drawn.undismiss_command}`,
  };
}

const DETAILED_REVIEWER_HINT =
  'Named on the PR description’s "Detailed reviewer: @login" line: the reviewer the PR asks to read the whole change in detail';

const ROW_HINTS: Record<string, string> = {
  reviewer: DETAILED_REVIEWER_HINT,
  queue: 'Events the watcher queued for this PR’s agent to pick up',
  unpushed: 'Commits in this PR’s worktree not yet pushed to origin',
};

export interface Row {
  key: string;
  label: string;
  hint: string;
  value: string;
  alarm: boolean;
  quiet: boolean;
  rebase: boolean;
}

function row(key: string, label: string, value: string, tone = ''): Row {
  return {
    key,
    label,
    hint: ROW_HINTS[key] ?? '',
    value,
    alarm: tone === 'alarm',
    quiet: tone === 'quiet',
    rebase: false,
  };
}

function agentRebasing(shown: ShownPr): boolean {
  return shown.drawn.system.agent.event === 'became-unmergeable';
}

function rebaseIsNext(shown: ShownPr, move: NextMove): boolean {
  return move.state === 'rebase' && !agentRebasing(shown);
}

const REVIEW_WORDS: Record<string, string> = {
  approved: 'approved',
  'changes-requested': 'changes requested',
  'review-required': 'pending',
  commented: 'commented',
  dismissed: 'dismissed',
};

function reviewWordOf(decision: string | null): string {
  return decision ? (REVIEW_WORDS[decision] ?? decision) : 'pending';
}

function statusRows(shown: ShownPr, summaries: Summaries, now: number): Row[] {
  const status = shown.drawn.status;
  const rows: Row[] = [];
  if (!status.you_are_the_detailed_reviewer) {
    rows.push(
      status.detailed_reviewer
        ? row('reviewer', 'Detailed reviewer', `@${status.detailed_reviewer}`)
        : row('reviewer', 'Detailed reviewer', 'not assigned', 'quiet'),
    );
  }
  const facts = polledOf(shown);
  const ci = facts.ci_status;
  rows.push(
    row(
      'ci',
      'CI',
      ci,
      ci === 'failing' ? 'alarm' : ci === 'passing' ? 'quiet' : '',
    ),
  );
  if (status.mergeable)
    rows.push(row('mergeable', 'Mergeable', 'yes', 'quiet'));
  else if (agentRebasing(shown))
    rows.push(row('mergeable', 'Mergeable', 'no, agent rebasing'));
  else
    rows.push({
      ...row('mergeable', 'Mergeable', 'no', 'alarm'),
      rebase: status.needs_rebase,
    });
  const decision = facts.review_decision;
  rows.push(
    row(
      'review',
      'Review',
      reviewWordOf(decision),
      decision === 'changes-requested' ? '' : 'quiet',
    ),
  );
  if (summaries.role === 'reviewer') {
    const yours = facts.my_review;
    rows.push(
      yours
        ? row('your-review', 'Your review', reviewWordOf(yours))
        : row('your-review', 'Your review', 'none yet', 'quiet'),
    );
  }
  rows.push(
    row('last-event', 'Last event', relativeOf(status.last_event_at, now)),
  );
  rows.push(
    row(
      'review-ready',
      'Review ready',
      relativeOf(status.review_ready_at, now),
      'quiet',
    ),
  );
  return rows;
}

function agentLine(system: DashboardSystem, now: number): string {
  const { agent, last_run: last } = system;
  if (!agent.enabled) return 'disabled in config.toml';
  if (agent.state === 'working') {
    const parts = [
      agent.event ? `working on ${runNameOf(agent.event)}` : 'working',
    ];
    if (agent.elapsed_seconds !== null)
      parts.push(`running ${lengthOf(agent.elapsed_seconds)}`);
    if (agent.silent_seconds !== null)
      parts.push(`${lengthOf(agent.silent_seconds)} since last output`);
    return parts.join(', ');
  }
  if (!last) return 'idle';
  const ago = lengthOf((now - Date.parse(last.ended_at)) / 1000);
  return `idle, last ${runNameOf(last.event)} ended ${ago} ago, ${exitWordOf(last.exit_code)}`;
}

function threadsLine(shown: ShownPr): string {
  const { queued, live, proposed } = shown.drawn.system.threads;
  return `${queued} queued, ${live} working, ${proposed} ready`;
}

function systemRows(shown: ShownPr, now: number): Row[] {
  const system = shown.drawn.system;
  const queued = system.queued_events;
  const rows = [
    row('agent', system.agent.name, agentLine(system, now)),
    row('queue', 'Queue', queued ? `${queued} pending` : 'empty'),
    row('threads', 'Threads', threadsLine(shown)),
  ];
  const ahead = system.unpushed_commits;
  if (ahead !== null) {
    rows.push(
      row(
        'unpushed',
        'Unpushed',
        ahead ? `${plural(ahead, 'commit')} ahead` : 'up to date',
      ),
    );
  }
  return rows;
}

export type BandState = 'normal' | 'on-hold' | 'frozen';

export interface Band {
  state: BandState;
  label: string;
  detail: string | null;
  computed: string | null;
}

function frozenComputed(frozen: FrozenWorktree): string {
  if (frozen.release_requested) {
    return 'Release asked for. The watcher hands this directory over on its next poll and builds a fresh worktree.';
  }
  const run = frozen.run_working
    ? 'An agent run is still going; the watcher waits while it produces output.'
    : 'No agent run is going.';
  return `Event dispatch is frozen. ${run} The watcher detaches it in ${graceOf(frozen.seconds_left)} and builds a fresh one. Nothing in the directory is removed.`;
}

function bandOf(
  shown: ShownPr,
  action: Action | null,
  move: string,
  why: string,
): Band {
  if (shown.drawn.frozen) {
    return {
      state: 'frozen',
      label: 'Next · frozen',
      detail: null,
      computed: frozenComputed(shown.drawn.frozen),
    };
  }
  if (shown.drawn.system.on_hold) {
    return {
      state: 'on-hold',
      label: 'Next · on hold',
      detail: action ? `Underneath: ${action.label}. ${action.detail}.` : null,
      computed: null,
    };
  }
  if (!action) {
    return {
      state: 'normal',
      label: 'Next',
      detail: 'Nothing known until the first poll',
      computed: null,
    };
  }
  const differs = action.label !== move;
  return {
    state: 'normal',
    label: 'Next',
    detail: why !== action.detail ? why : null,
    computed: differs
      ? `PR state: ${action.label} · ${action.detail}`
      : action.detail,
  };
}

function withoutLeadingTicket(title: string, ticket: string): string {
  const escaped = ticket.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const leading = new RegExp(`^\\[?${escaped}(?![\\w])\\]?[\\s:·-]*`, 'i');
  return title.replace(leading, '') || title;
}

function titleOf(shown: ShownPr): string {
  const { ticket } = shown;
  const title = shown.title ?? 'Title not known yet';
  return ticket ? `${ticket} · ${withoutLeadingTicket(title, ticket)}` : title;
}

export type Tone = 'alarm' | 'quiet' | 'plain' | 'strong';

export interface Cell {
  key: string;
  label: string;
  text: string;
  tone: Tone;
  live: boolean;
  count: boolean;
}

const CELL_LABELS: Record<string, string> = {
  ci: 'CI',
  merge: 'Conflicts',
  review: 'Review',
  agent: 'Agent',
  threads: 'Threads',
  ahead: 'Unpushed',
  queue: 'Queue',
};

const CELL_HINTS: Record<string, string> = {
  ci: 'GitHub’s checks on the head commit: passing, failing or pending',
  merge:
    'Whether the branch conflicts with its base on GitHub; a draft still has to be marked ready before it can merge',
  review: 'The review decision on GitHub',
  agent:
    'What this PR’s agent is doing, or how its last run ended. A run is named for what started it; carry on is the agent picking up its last conversation here',
  threads:
    'Review-board threads waiting on you: fixes ready to decide, local drafts, answers. A dot means none',
  ahead:
    'Commits in this PR’s worktree not yet pushed to origin. A dot means none',
  queue:
    'Events the watcher queued for this PR’s agent to pick up. A dot means none',
};

export interface Head {
  label: string;
  hint: string;
  right: boolean;
}

const COUNTED_KEYS = ['threads', 'ahead', 'queue'];

export const HEADS: Head[] = [
  {
    label: 'Your move, then the PR',
    hint: 'What you do next on each PR; clicking a row only opens it',
    right: false,
  },
  { label: 'Why', hint: 'What makes that your move', right: false },
  ...Object.keys(CELL_LABELS).map((key) => ({
    label: CELL_LABELS[key]!,
    hint: CELL_HINTS[key]!,
    right: COUNTED_KEYS.includes(key),
  })),
];

function cell(key: string, text: string, tone: Tone, live = false): Cell {
  return {
    key,
    label: CELL_LABELS[key] ?? key,
    text,
    tone,
    live,
    count: false,
  };
}

function counted(key: string, value: number | null): Cell {
  const shown = value
    ? cell(key, String(value), 'strong')
    : cell(key, '·', 'quiet');
  return { ...shown, count: true };
}

function ciCell(shown: ShownPr): Cell {
  const ci = polledOf(shown).ci_status;
  if (ci === 'failing') return cell('ci', ci, 'alarm');
  return cell('ci', ci, ci === 'passing' ? 'quiet' : 'plain');
}

function mergeCell(shown: ShownPr): Cell {
  if (shown.drawn.status.mergeable) return cell('merge', 'none', 'quiet');
  return cell('merge', 'yes', agentRebasing(shown) ? 'plain' : 'alarm');
}

function reviewCell(shown: ShownPr): Cell {
  const decision = polledOf(shown).review_decision;
  return cell(
    'review',
    reviewWordOf(decision),
    decision === 'changes-requested' ? 'plain' : 'quiet',
  );
}

function failedCell(failing: FinishedRun[], now: number): Cell {
  const newest = failing[0]!;
  const ago = lengthOf((now - Date.parse(newest.ended_at)) / 1000);
  const count =
    failing.length === 1 ? '1 failed run' : `${failing.length} failed runs`;
  return cell(
    'agent',
    `idle · ${count}, last ${runNameOf(newest.event)} ${ago} ago`,
    'alarm',
  );
}

function agentCell(shown: ShownPr, now: number, failing: FinishedRun[]): Cell {
  const { agent, last_run: last, on_hold } = shown.drawn.system;
  if (shown.drawn.frozen) return cell('agent', 'frozen', 'quiet');
  if (on_hold) return cell('agent', 'on hold', 'quiet');
  if (!agent.enabled) return cell('agent', 'disabled', 'quiet');
  if (agent.state === 'working') {
    const parts = [agent.event ? runNameOf(agent.event) : 'working'];
    if (agent.elapsed_seconds !== null)
      parts.push(lengthOf(agent.elapsed_seconds));
    if (agent.silent_seconds !== null)
      parts.push(`${lengthOf(agent.silent_seconds)} quiet`);
    return cell('agent', parts.join(' · '), 'plain', true);
  }
  if (failing.length) return failedCell(failing, now);
  if (!last) return cell('agent', 'idle', 'quiet');
  const ago = lengthOf((now - Date.parse(last.ended_at)) / 1000);
  return cell(
    'agent',
    `idle · last ${runNameOf(last.event)} ${exitWordOf(last.exit_code)} ${ago} ago`,
    'quiet',
  );
}

interface Waiting {
  ready: number;
  drafts: number;
  answered: number;
}

function waitingOf({ ready, drafts, answered }: Waiting): string | null {
  const parts = [
    ready ? `${ready} ready` : null,
    drafts ? plural(drafts, 'draft') : null,
    answered ? `${answered} answered` : null,
  ].filter((part) => part !== null);
  return parts.length ? parts.join(', ') : null;
}

function threadsCell(waiting: string | null): Cell {
  const shown = waiting
    ? cell('threads', waiting, 'strong')
    : cell('threads', '·', 'quiet');
  return { ...shown, count: true };
}

function whyOf(
  shown: ShownPr,
  action: Action | null,
  since: string[] | null,
): string {
  const frozen = shown.drawn.frozen;
  if (frozen?.release_requested) {
    return 'Release asked for; the watcher cuts a fresh worktree on its next cycle';
  }
  if (frozen) {
    return `Wrong branch checked out (${frozen.here}) · detaches in ${lengthOf(frozen.seconds_left)}`;
  }
  if (since) return `Since you acted: ${since.join(', ')}`;
  if (!action) return 'Nothing known until the first poll';
  if (shown.drawn.system.on_hold) return `${action.label}: ${action.detail}`;
  return action.detail;
}

export type Square = 'ready' | 'draft' | 'work' | 'wait' | 'alarm' | 'park';

const SQUARES: Record<WallGroup, Square> = {
  'needs-you': 'ready',
  draft: 'draft',
  'agent-working': 'work',
  'waiting-on-others': 'wait',
  'on-hold': 'park',
  mentioned: 'wait',
};

const EDGES: Record<Square, string> = {
  ready: 'ready',
  draft: 'draft',
  work: 'working',
  wait: 'waiting-on-others',
  alarm: 'failed',
  park: 'parked',
};

export interface Frozen {
  worktree: string;
  here: string;
  expected: string;
}

export interface Flag {
  text: string;
  hint: string;
}

const DETAILED_REVIEWER: Flag = {
  text: 'You are the detailed reviewer',
  hint: DETAILED_REVIEWER_HINT,
};

export interface MoveFlag {
  code: FlagCode;
  text: string;
  alarm: boolean;
}

const FLAG_WORDS: Record<FlagCode, (move: NextMove) => string> = {
  draft: () => 'Draft',
  'fix-ci': () => 'Fix CI',
  rebase: () => 'Rebase',
  'unresolved-threads': (move) => plural(move.unresolved, 'unresolved thread'),
};

export function threadsWaitingOf(summaries: Summaries): string | null {
  if (!summaries.role) return null;
  const decided = groupCountsOf(summaries.groups, summaries.role).find(
    (one) => one.key === READY_GROUP,
  );
  const parts = [
    decided ? `${decided.count} ${decided.label}` : null,
    summaries.drafts ? plural(summaries.drafts, 'draft') : null,
  ].filter((part) => part !== null);
  return parts.length ? parts.join(', ') : null;
}

export function countsOf(summaries: Summaries): string[] {
  const { human, bot, yours } = summaries;
  if (!summaries.role) return [];
  if (summaries.role === 'reviewer') {
    return [`Your threads ${yours.answered}/${yours.total} answered`];
  }
  return [
    `Human comments ${human.done}/${human.total} done`,
    `Bot comments ${bot.done}/${bot.total} done`,
  ];
}

function flagsOf(move: NextMove): MoveFlag[] {
  return move.flags.map((code) => ({
    code,
    text: FLAG_WORDS[code](move),
    alarm: code === 'fix-ci',
  }));
}

export interface Reading {
  number: number;
  code: Move;
  move: string;
  square: Square;
  edge: string;
  working: boolean;
  title: string;
  titleKnown: boolean;
  whose: string | null;
  branch: string | null;
  detailedReviewer: Flag | null;
  why: string;
  cells: Cell[];
  band: Band;
  frozen: Frozen | null;
  onHold: boolean;
  unpolled: string | null;
  notice: string | null;
  status: Row[];
  system: Row[];
  since: string[] | null;
  rebaseIsNext: boolean;
  flags: MoveFlag[];
  draft: boolean;
  muted: boolean;
  dismiss: DismissWording;
}

export function dashboardOf(
  shown: ShownPr,
  summaries: Summaries,
  now: number,
  failing: FinishedRun[] = [],
): Reading {
  const next = summaries.move;
  const square = shown.drawn.frozen
    ? 'alarm'
    : next.group
      ? SQUARES[next.group]
      : 'park';
  const action = actionOf(shown, next);
  const move = moveOf(shown, summaries);
  const since = sinceOf(shown);
  const why = whyOf(shown, action, since);
  const frozen = shown.drawn.frozen;
  return {
    number: shown.number,
    code: next.code,
    move,
    square,
    edge: EDGES[square],
    working: shown.drawn.system.agent.state === 'working',
    title: titleOf(shown),
    titleKnown: shown.title !== null,
    whose: whoseOf(shown, summaries),
    branch: shown.branch,
    detailedReviewer: shown.drawn.status.you_are_the_detailed_reviewer
      ? DETAILED_REVIEWER
      : null,
    why,
    cells: [
      ciCell(shown),
      mergeCell(shown),
      reviewCell(shown),
      agentCell(shown, now, failing),
      threadsCell(
        waitingOf({
          ready: summaries.ready,
          drafts: summaries.drafts,
          answered: summaries.yours.answered,
        }),
      ),
      counted('ahead', shown.drawn.system.unpushed_commits),
      counted('queue', shown.drawn.system.queued_events),
    ],
    band: bandOf(shown, action, move, why),
    frozen: frozen
      ? {
          worktree: tildeOf(frozen.worktree),
          here: frozen.here,
          expected: frozen.expected,
        }
      : null,
    onHold: shown.drawn.system.on_hold,
    unpolled: shown.drawn.polled ? null : FIRST_POLL,
    notice: shown.drawn.notice,
    status: shown.drawn.polled ? statusRows(shown, summaries, now) : [],
    system: systemRows(shown, now),
    since: frozen ? null : since,
    rebaseIsNext: rebaseIsNext(shown, next),
    flags: flagsOf(next),
    draft: next.flags.includes('draft'),
    muted: next.muted,
    dismiss: dismissOf(shown),
  };
}

export type Dismissal = 'until its next event' | 'forever';

export function dismissedSaying(number: number, how: Dismissal): string {
  return `Dismissed #${number} ${how}. Its manager has exited.`;
}

export interface Absence {
  number: number | null;
  dismissed: Dismissal | null;
  shown: boolean;
  missed: boolean;
  starting: boolean;
}

export function standingOf(absence: Absence): string | null {
  const { number, dismissed } = absence;
  if (dismissed && number !== null) {
    return `${dismissedSaying(number, dismissed)} This page has nothing more to show.`;
  }
  if (absence.shown && !absence.starting) return null;
  if (absence.missed) return 'Can’t reach the board server.';
  if (absence.starting) return 'The manager is starting…';
  return 'The manager is not running.';
}

export function notLiveOf(reading: Reading, live: boolean): string | null {
  if (live) return null;
  if (reading.frozen) {
    return 'Not live: the board is down while the worktree is frozen, so this is the watcher’s view from disk.';
  }
  return 'Not live: the manager’s board is not answering, so this is the watcher’s view from disk. Carry on, dismiss and git wait for the board.';
}
