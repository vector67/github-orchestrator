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
  if (Number.isNaN(seconds)) return '?';
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

const BIDI_CONTROLS = /[\u202A-\u202E\u2066-\u2069]/g;

function withoutBidiControls(name: string): string {
  return name.replace(BIDI_CONTROLS, '');
}

function listed(people: string[]): string {
  return people.map(withoutBidiControls).join(', ');
}

const WAITING_FOR_AUTHOR = 'Waiting for author';

const STATE_LABELS: Partial<Record<Move, string>> = {
  closed: 'Merged or closed',
  'fix-ci': 'Fix CI',
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

function baseOf(shown: ShownPr): string {
  return shown.base_branch ?? 'the base branch';
}

function labelOf(state: Move, shown: ShownPr): string {
  if (state === 'rebase') return `Rebase on ${baseOf(shown)}`;
  return STATE_LABELS[state] ?? state;
}

const CI_WORDS: Record<string, string> = {
  passing: 'CI passing',
  failing: 'CI failing',
  pending: 'CI pending',
  none: 'no CI',
};

type Polled = Pick<
  PrFacts,
  | 'ci_status'
  | 'merge_state'
  | 'review_decision'
  | 'my_review'
  | 'changes_requested_by'
  | 'pending_reviewers'
  | 'unresolved_threads'
>;

const UNPOLLED: Polled = {
  ci_status: 'pending',
  merge_state: null,
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
  const approved = status.approved_by.filter(
    (login) => !facts.pending_reviewers.includes(login),
  );
  const parts = approved.map((login) => `${login} approved`);
  if (facts.pending_reviewers.length) {
    parts.push(`Waiting on: ${listed(facts.pending_reviewers)}`);
  } else if (!approved.length) {
    parts.push('No reviewers assigned');
  }
  return parts.join(' | ');
}

function afterApprovingWithOthersOf(move: NextMove, facts: Polled): string {
  const requesters = move.reviewers.filter(
    (login) =>
      facts.changes_requested_by.includes(login) &&
      !facts.pending_reviewers.includes(login),
  );
  const awaited = move.reviewers.filter((login) => !requesters.includes(login));
  const parts = ['You approved'];
  if (requesters.length) parts.push(`${listed(requesters)} requested changes`);
  if (awaited.length) parts.push(`Waiting on review from: ${listed(awaited)}`);
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
      return facts.merge_state === 'conflicts'
        ? 'Merge conflicts detected'
        : `Behind ${baseOf(shown)}`;
    case 'address-feedback':
      return `${listed(facts.changes_requested_by) || 'Reviewer'} requested changes | ${unresolvedOf(facts)}`;
    case 'ready-to-merge':
      return `${status.approved_by.length ? `Approved by ${listed(status.approved_by)}` : 'No approval needed'} | ${ci}`;
    case 'await-review':
    case 'request-reviewers':
    case 'mark-ready-for-review':
      return awaitingReviewOf(status, facts);
    case 'await-rereview':
      return `Waiting on ${listed(move.reviewers)} to re-review`;
    case 'await-ci':
      return `${status.checks_done}/${status.checks_total} checks complete`;
    case 'review':
      return `${ci} | ${status.changed_files ?? '?'} files changed | ${reviewsSoFarOf(status, facts).replace(', ', ' | ')}`;
    case 'rereview':
      return `Re-review requested | ${ci}`;
    case 'await-reviewers':
      return afterApprovingWithOthersOf(move, facts);
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
    label: labelOf(state, shown),
    detail: detailOf(state, shown, move),
  };
}

const FIRST_POLL = 'Waiting for the first poll';

const AGENT_DOING: Record<string, string> = {
  'ci-failed': 'fixing CI',
  'became-unmergeable': 'rebasing on main',
  'review-requested': 'reviewing',
  'manual-continue': 'carrying on',
};

function fixes(count: number): string {
  return count === 1 ? '1 fix' : `${count} fixes`;
}

function moveOf(shown: ShownPr, summaries: Summaries): string {
  const { threads, agent } = shown.drawn.system;
  const { move, human, bot } = summaries;
  const code = move.code;
  switch (code) {
    case 'release-worktree':
      return 'Release the worktree';
    case 'on-hold':
      return 'On hold';
    case 'address-feedback':
      return `Address changes from ${listed(move.reviewers)}`;
    case 'human-comments':
      return `Decide ${fixes(human.toDecide)}`;
    case 'agent-on-human-comments':
      return `Agent is fixing ${plural(human.agentOn, 'human thread')}`;
    case 'bot-comments':
      return `Decide ${fixes(bot.toDecide).replace(' ', ' bot ')}`;
    case 'agent-on-bot-comments':
      return `Agent is fixing ${plural(bot.agentOn, 'bot thread')}`;
    case 'send-review':
      return 'Send your review';
    case 'agent-running':
      return `Agent is ${doingOf(agent.event)}`;
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
      return 'Waiting on the author';
    case 'await-rerequest':
      return 'Waiting on the author to ask you again';
    case 'rereview':
      return 'Re-review';
    case 'mention':
      return 'Answer the mention';
    case 'mentioned':
      return 'Waiting on others';
    default:
      return labelOf(code, shown);
  }
}

function doingOf(event: string | null): string {
  if (event === null) return 'working';
  return AGENT_DOING[event] ?? `working on ${runNameOf(event)}`;
}

function frozenReasonOf(frozen: FrozenWorktree): string {
  if (frozen.release_requested) {
    return 'release asked for; the watcher cuts a fresh worktree on its next cycle';
  }
  return `wrong branch checked out (${withoutBidiControls(frozen.here)}) · detaches in ${lengthOf(frozen.seconds_left)}`;
}

function heldOf(queued: number): string {
  if (queued <= 0) return 'resume it to let events through';
  return queued === 1
    ? '1 event waits until you resume it'
    : `${queued} events wait until you resume it`;
}

function runningOf(system: DashboardSystem): string {
  const { elapsed_seconds: elapsed, silent_seconds: silent } = system.agent;
  const parts = [
    elapsed !== null ? `running ${lengthOf(elapsed)}` : null,
    silent !== null ? `${lengthOf(silent)} since its last output` : null,
  ].filter((part) => part !== null);
  return parts.length ? parts.join(' · ') : 'just started';
}

function doneOf(tally: Tally): string {
  return `${tally.done} of ${tally.total} done`;
}

function approvalsOf(status: DashboardStatus, facts: Polled): string[] {
  const approved = status.approved_by.filter(
    (login) => !facts.pending_reviewers.includes(login),
  );
  return approved.length ? [`${listed(approved)} approved`] : [];
}

function reviewsSoFarOf(status: DashboardStatus, facts: Polled): string {
  const parts: string[] = [];
  if (status.approved_by.length) {
    parts.push(`${listed(status.approved_by)} approved`);
  }
  if (facts.changes_requested_by.length) {
    parts.push(`${listed(facts.changes_requested_by)} requested changes`);
  }
  return parts.length ? parts.join(', ') : 'no reviews yet';
}

const YOUR_REVIEW_WORDS: Record<string, string> = {
  commented: 'you commented',
  'changes-requested': 'you requested changes',
  dismissed: 'your review was dismissed',
};

function filesOf(changed: number | null): string | null {
  if (changed === null) return null;
  return changed === 1 ? '1 file changed' : `${changed} files changed`;
}

function reviewerReasonOf(
  shown: ShownPr,
  summaries: Summaries,
): (string | null)[] | null {
  const status = shown.drawn.status;
  const facts = polledOf(shown);
  const { move, yours } = summaries;
  switch (move.code) {
    case 'review':
      return [
        'requested from you',
        filesOf(status.changed_files),
        reviewsSoFarOf(status, facts),
      ];
    case 'rereview':
      return [
        'asked again',
        yours.total
          ? `${yours.answered} of ${yours.total} of your threads answered`
          : null,
      ];
    case 'await-reviewers':
      return ['you approved'];
    case 'await-author':
      return [
        'you approved',
        move.stillRequested.length
          ? `${listed(move.stillRequested)} still requested`
          : null,
      ];
    case 'await-rerequest':
      return [YOUR_REVIEW_WORDS[facts.my_review ?? ''] ?? 'you reviewed'];
    default:
      return null;
  }
}

function authorReasonOf(shown: ShownPr, summaries: Summaries): string {
  const status = shown.drawn.status;
  const facts = polledOf(shown);
  const { move, human, bot } = summaries;
  const ci = CI_WORDS[facts.ci_status] ?? `CI ${facts.ci_status}`;
  switch (move.code) {
    case 'on-hold':
      return heldOf(shown.drawn.system.queued_events);
    case 'first-poll':
      return 'nothing known yet';
    case 'human-comments':
      return `human threads, ${doneOf(human)}`;
    case 'bot-comments':
      return `bot threads, ${doneOf(bot)}`;
    case 'agent-on-human-comments':
      return doneOf(human);
    case 'agent-on-bot-comments':
      return doneOf(bot);
    case 'agent-running':
      return runningOf(shown.drawn.system);
    case 'agent-on-threads': {
      const queued = shown.drawn.system.threads.queued;
      return queued
        ? `${queued} more queued`
        : 'its fixes come to the board for you to decide';
    }
    case 'send-review':
      return plural(summaries.drafts, 'unsent comment');
    case 'address-feedback':
      return move.reviewers.length === 1
        ? 'requested changes and is not asked to review again'
        : 'requested changes and are not asked to review again';
    case 'fix-ci':
      return status.failed_checks.length
        ? `${listed(status.failed_checks)} failing`
        : 'a check is failing';
    case 'rebase':
      return facts.merge_state === 'conflicts'
        ? `conflicts with ${baseOf(shown)}`
        : `behind ${baseOf(shown)}`;
    case 'ready-to-merge':
      return `${status.approved_by.length ? `approved by ${listed(status.approved_by)}` : 'no approval needed'}, ${ci}`;
    case 'await-ci':
      return `${status.checks_done} of ${status.checks_total} checks done`;
    case 'await-rereview':
      return 'asked again after requesting changes';
    case 'await-review':
      return [...approvalsOf(status, facts), 'review requested'].join(' · ');
    case 'request-reviewers':
      return [...approvalsOf(status, facts), 'nobody is asked to review'].join(
        ' · ',
      );
    case 'mark-ready-for-review':
      return 'still a draft';
    case 'mention':
      return `${listed(move.mentionedBy)} mentioned you`;
    case 'mentioned':
      return 'you are not a reviewer and every mention is answered';
    default:
      return '';
  }
}

function reasonOf(shown: ShownPr, summaries: Summaries): string {
  const frozen = shown.drawn.frozen;
  if (frozen) return frozenReasonOf(frozen);
  const parts = reviewerReasonOf(shown, summaries);
  if (!parts) return authorReasonOf(shown, summaries);
  const since = sinceOf(shown);
  if (since) parts.push(`since then: ${since.join(', ')}`);
  return parts.filter((part) => part !== null).join(' · ');
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

const NOT_REVIEWING: Move[] = ['not-reviewing', 'mention', 'mentioned'];

function whoseOf(shown: ShownPr, summaries: Summaries): string | null {
  if (!shown.drawn.polled) return null;
  if (summaries.role === 'author') return 'your PR';
  if (shown.author) return `${shown.author}'s PR`;
  const state = summaries.move.state;
  return state && NOT_REVIEWING.includes(state) ? null : 'reviewing';
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

function decisionWordOf(shown: ShownPr): string {
  const decision = polledOf(shown).review_decision;
  if (decision === null && shown.drawn.status.approved_by.length) {
    return reviewWordOf('approved');
  }
  return reviewWordOf(decision);
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
  if (status.mergeable === null)
    rows.push(row('mergeable', 'Mergeable', 'not known yet', 'quiet'));
  else if (status.mergeable)
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
      decisionWordOf(shown),
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

export type ChipTone = 'alarm' | 'warn' | 'plain' | 'quiet' | 'accent';

export interface Chip {
  key: string;
  text: string;
  hint: string;
  tone: ChipTone;
}

const FIXED_BY_RUN: Record<string, string> = {
  'ci-failed': 'ci',
  'became-unmergeable': 'merge',
};

function fixingNow(shown: ShownPr, key: string): boolean {
  const agent = shown.drawn.system.agent;
  return agent.state === 'working' && FIXED_BY_RUN[agent.event ?? ''] === key;
}

const BLOCKERS: Partial<Record<Move, string>> = {
  'fix-ci': 'ci',
  rebase: 'merge',
  'address-feedback': 'review',
};

const REVIEW_NAMED: Move[] = ['address-feedback', 'await-rereview', 'review'];

const APPROVAL_NAMED: Move[] = [
  'ready-to-merge',
  'review',
  'await-review',
  'request-reviewers',
  'await-author',
  'await-reviewers',
];

const DECISIONS: Move[] = ['human-comments', 'bot-comments'];

const MENTION_NAMED: Move[] = ['mention', 'mentioned'];

const DRAFT_HINT =
  'A draft: it has to be marked ready for review before it can merge';

const MISMATCHES_HINT =
  'Mismatches the last finished PR summary found between what was asked for, what the author says and what the code does. It may be about an older head, and a summary running now is not counted until it ends; the Summary tab says which head it read';

function chip(key: string, text: string, hint: string, tone: ChipTone): Chip {
  return { key, text, hint, tone };
}

function ciChip(shown: ShownPr, code: Move): Chip | null {
  if (shown.facts?.ci_status !== 'failing' || code === 'fix-ci') return null;
  if (fixingNow(shown, 'ci')) return null;
  const failed = shown.drawn.status.failed_checks;
  return chip(
    'ci',
    'CI failing',
    failed.length
      ? `Failing on the head commit: ${listed(failed)}`
      : 'A check on the head commit is failing',
    'warn',
  );
}

function mergeChip(shown: ShownPr, code: Move): Chip | null {
  const state = shown.facts?.merge_state;
  if (code === 'rebase' || fixingNow(shown, 'merge')) return null;
  if (state === 'conflicts') {
    return chip(
      'merge',
      `conflicts with ${baseOf(shown)}`,
      'The branch conflicts with the branch it merges into',
      'warn',
    );
  }
  if (state === 'behind') {
    return chip(
      'merge',
      `behind ${baseOf(shown)}`,
      'The branch is behind the branch it merges into and has to be brought up to date',
      'warn',
    );
  }
  return null;
}

function reviewChip(shown: ShownPr, code: Move): Chip | null {
  const facts = shown.facts;
  if (!facts || REVIEW_NAMED.includes(code)) return null;
  const hint = 'A reviewer asked for changes on GitHub';
  if (facts.changes_requested_by.length) {
    return chip(
      'review',
      `${listed(facts.changes_requested_by)} requested changes`,
      hint,
      'warn',
    );
  }
  return facts.review_decision === 'changes-requested'
    ? chip('review', 'changes requested', hint, 'warn')
    : null;
}

function approvedChip(shown: ShownPr, code: Move): Chip | null {
  const facts = shown.facts;
  if (!facts || APPROVAL_NAMED.includes(code)) return null;
  if (facts.changes_requested_by.length) return null;
  if (facts.review_decision === 'changes-requested') return null;
  const approvers = shown.drawn.status.approved_by;
  const hint = 'The pull request is approved on GitHub';
  if (approvers.length) {
    return chip('approved', `approved by ${listed(approvers)}`, hint, 'accent');
  }
  return facts.review_decision === 'approved'
    ? chip('approved', 'approved', hint, 'accent')
    : null;
}

function agoOf(iso: string, now: number): string {
  return lengthOf((now - Date.parse(iso)) / 1000);
}

function runsChip(
  shown: ShownPr,
  failing: FinishedRun[],
  now: number,
): Chip | null {
  const { agent, last_run: last } = shown.drawn.system;
  if (agent.state === 'working') return null;
  const newest = failing[0];
  if (newest) {
    const name = runNameOf(newest.event);
    const ago = agoOf(newest.ended_at, now);
    return failing.length === 1
      ? chip(
          'runs',
          '1 failed run',
          `The last run, a ${name}, failed ${ago} ago`,
          'warn',
        )
      : chip(
          'runs',
          `${failing.length} failed runs`,
          `${failing.length} runs failed in a row; the last, a ${name}, ended ${ago} ago`,
          'warn',
        );
  }
  if (!last || last.exit_code === 0 || last.exit_code === null) return null;
  const name = runNameOf(last.event);
  return chip(
    'runs',
    `last ${name} failed`,
    `The last run, a ${name}, ended ${agoOf(last.ended_at, now)} ago: ${exitWordOf(last.exit_code)}`,
    'warn',
  );
}

function agentChip(shown: ShownPr, code: Move): Chip | null {
  const system = shown.drawn.system;
  if (system.agent.state !== 'working' || code === 'agent-running') return null;
  return chip(
    'agent',
    `agent ${doingOf(system.agent.event)}`,
    `${system.agent.name} is ${runningOf(system)}`,
    'plain',
  );
}

function countChip(
  key: string,
  count: number | null,
  text: (count: number) => string,
  hint: string,
  tone: ChipTone = 'plain',
): Chip | null {
  return count !== null && count > 0
    ? chip(key, text(count), hint, tone)
    : null;
}

function mentionedChip(shown: ShownPr, code: Move): Chip | null {
  const facts = shown.facts;
  if (!facts?.mentioned || MENTION_NAMED.includes(code)) return null;
  const who = [...new Set(facts.mentions.map((one) => one.author))];
  return chip(
    'mentioned',
    'mentioned',
    who.length
      ? `${listed(who)} mentioned you here`
      : 'You were mentioned here',
    'quiet',
  );
}

function chipsOf(
  shown: ShownPr,
  summaries: Summaries,
  failing: FinishedRun[],
  now: number,
): Chip[] {
  const { move, role } = summaries;
  const code = move.code;
  const system = shown.drawn.system;
  const facts = shown.facts;
  const found = [
    ciChip(shown, code),
    mergeChip(shown, code),
    reviewChip(shown, code),
    runsChip(shown, failing, now),
    agentChip(shown, code),
    role === 'author' && !DECISIONS.includes(code)
      ? countChip(
          'decide',
          summaries.ready,
          (count) => `${fixes(count)} to decide`,
          'Fixes the agent proposed on the board, waiting for your decision',
        )
      : null,
    code === 'send-review'
      ? null
      : countChip(
          'unsent',
          summaries.drafts,
          (count) => `${count} unsent`,
          'Comments you drafted on the board and have not sent',
        ),
    countChip(
      'unresolved',
      facts?.unresolved_threads ?? null,
      (count) => `${count} unresolved`,
      'Review threads on GitHub not resolved yet',
    ),
    role === 'reviewer' && code !== 'rereview'
      ? countChip(
          'answered',
          summaries.yours.answered,
          (count) => `${count} answered`,
          'Threads you opened that the author has answered',
        )
      : null,
    countChip(
      'unpushed',
      system.unpushed_commits,
      (count) => `${count} unpushed`,
      ROW_HINTS['unpushed']!,
    ),
    code === 'on-hold'
      ? null
      : countChip(
          'queue',
          system.queued_events,
          (count) => `${count} queued`,
          ROW_HINTS['queue']!,
          'quiet',
        ),
    approvedChip(shown, code),
    mentionedChip(shown, code),
    shown.drawn.status.you_are_the_detailed_reviewer
      ? chip('reviewer', 'detailed reviewer', DETAILED_REVIEWER_HINT, 'accent')
      : null,
    summaries.mismatches
      ? chip('mismatches', summaries.mismatches, MISMATCHES_HINT, 'quiet')
      : null,
    facts?.draft && code !== 'mark-ready-for-review'
      ? chip('draft', 'draft', DRAFT_HINT, 'quiet')
      : null,
  ].filter((one) => one !== null);
  const blocker =
    role === 'author' && move.state && move.state !== code
      ? BLOCKERS[move.state]
      : undefined;
  const marked = found.map((one) =>
    one.key === blocker ? { ...one, tone: 'alarm' as const } : one,
  );
  return [
    ...marked.filter((one) => one.tone === 'alarm'),
    ...marked.filter((one) => one.tone !== 'alarm'),
  ];
}

const MINUTE_MS = 60_000;

export function ageOf(entered: number, now: number): string {
  const minutes = Math.floor(Math.max(0, now - entered) / MINUTE_MS);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
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
    return `Wrong branch checked out (${withoutBidiControls(frozen.here)}) · detaches in ${lengthOf(frozen.seconds_left)}`;
  }
  if (since) return `Since you acted: ${since.join(', ')}`;
  if (!action) return 'Nothing known until the first poll';
  if (shown.drawn.system.on_hold) return `${action.label}: ${action.detail}`;
  return action.detail;
}

export type Square = 'ready' | 'draft' | 'work' | 'wait' | 'alarm' | 'park';

const SQUARES: Record<WallGroup, Square> = {
  'needs-you': 'ready',
  'agent-working': 'work',
  'waiting-on-others': 'wait',
  parked: 'park',
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
  reason: string;
  chips: Chip[];
  band: Band;
  frozen: Frozen | null;
  onHold: boolean;
  unpolled: string | null;
  notice: string | null;
  status: Row[];
  system: Row[];
  since: string[] | null;
  rebaseIsNext: boolean;
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
    : next.group === 'parked' && next.muted
      ? 'draft'
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
    reason: reasonOf(shown, summaries),
    chips: chipsOf(shown, summaries, failing, now),
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
