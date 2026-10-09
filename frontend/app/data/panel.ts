import type {
  Comment,
  Conversation,
  Commits,
  DiffSide,
  Operation,
  OperationKind,
  Proposal,
  ProposalKind,
  Ticket,
} from 'frontend/data/api';
import { causeOf } from 'frontend/data/failure';
import {
  groupOf,
  groupsFor,
  squareOf,
  READY_GROUP,
} from 'frontend/data/groups';
import { KIND_LABELS, nameOf, sentence, type Seen } from 'frontend/data/rows';
import {
  atWork,
  busy,
  newestOf,
  outstanding,
  PHASE_HINTS,
  phaseOf,
  REOPENED_HINT,
  RUN_KINDS,
  type Phase,
} from 'frontend/data/thread';
import { inFlight, offered, type Offer } from 'frontend/data/decisions';
import type { PrEntity } from 'frontend/services/store';

export interface TranscriptEntry {
  author: string;
  author_name: string;
  body: string;
  meta: string;
  highlighted: boolean;
}

export interface PlanStep {
  text: string;
  file: string;
  done: boolean;
}

export interface LandingFailure {
  headline: string;
  summary: string;
  output_label: string;
  machine: string;
  standing: string;
}

export interface Fold {
  commits: Commits;
  title: string;
  pointing_title: string;
}

export interface ReplyBox {
  threaded: boolean;
  parks: boolean;
  note: string;
}

export interface FileStat {
  path: string;
  added: number;
  removed: number;
}

export interface AcceptView {
  title: string | null;
  lead: string | null;
  files: FileStat[];
  reply_kicker: string;
  resolvable: boolean;
  message: string | null;
}

export interface Reviewer {
  author: string;
  label: string;
}

export interface ReworkView {
  kicker: string;
  placeholder: string;
  send_label: string;
  note: string;
  reviewers: Reviewer[];
}

export interface Affordance {
  kind: string;
  label: string;
  weight: string;
}

export interface FixBanner {
  title: string;
  body: string;
  tone: string;
}

export interface Note {
  kind: string;
  text: string;
  detail?: string;
}

export interface Code {
  sha: string;
  path: string;
  first: number;
  last: number;
  from_line: number;
  to_line: number;
  outdated: string | null;
}

export interface DraftView {
  body: string;
  path: string;
  line: number | null;
  start_line: number | null;
  start_side: DiffSide | null;
  side: DiffSide;
  editable: boolean;
  enrolled: boolean;
  posting: boolean;
}

export interface Panel {
  id: string;
  role: string;
  mention: boolean;
  phase: Phase;
  square: string;
  reviewer_name: string;
  reply_to: string;
  role_line: string;
  started: string;
  started_at: string;
  kicker: string;
  kicker_hint: string;
  location: string;
  url: string;
  anchor: string;
  code: Code | null;
  loading: boolean;
  draft: DraftView | null;
  transcript: TranscriptEntry[];
  reply: ReplyBox | null;
  reply_action: Affordance | null;
  actions: Offer[];
  can_delete: boolean;
  accept: AcceptView | null;
  rework: ReworkView | null;
  agent_words: string | null;
  fix_label: string;
  fix_directory: string | null;
  in_session: boolean;
  banner: FixBanner | null;
  proposed_reply: string | null;
  proposed_ticket: Ticket | null;
  summary: string;
  failure: LandingFailure | null;
  plan: PlanStep[];
  confidence: string | null;
  confidence_note: string;
  tests: string | null;
  tests_note: string;
  files: FileStat[];
  files_label: string;
  notes: Note[];
  fold: Fold | null;
  fold_placeholder: string;
}

export interface Details {
  version: string;
  comments: Comment[];
  operations: Operation[];
}

export interface Fix {
  proposal: Proposal | undefined;
  files: FileStat[];
}

export interface Context extends Seen {
  pullRequest: PrEntity | null;
  ready: string[];
  now: number;
}

const POINTING_TITLE = 'Click lines to point the agent at them';
const CONTEXT_LINES = 3;
const SHORT_SHA = 12;
const DELETABLE = ['review', 'issue'];
const MINUTE = 60_000;

const REVIEW_STATE_WORDS: Record<string, string> = {
  CHANGES_REQUESTED: 'requested changes',
  COMMENTED: 'commented',
  APPROVED: 'approved',
  DISMISSED: 'dismissed',
  PENDING: 'pending',
};

const KICKER_PHASES: Partial<Record<Phase, string>> = {
  rejected: 'Rejected',
  resolved: 'Resolved on GitHub',
  confirmed: 'Confirmed',
};

const KICKER_GROUPS: Record<string, string> = {
  working: 'Agent working',
  queued: 'Queued · agent not started',
  rework: 'Sent back for rework',
  landing: 'Landing',
  deferred: 'Deferred',
  done: 'Done',
};

const FIX_PHRASES: Partial<Record<Phase, string>> = {
  proposed: 'Agent proposal',
  working: 'Agent working',
  queued: 'Queued for agent',
  rework: 'Agent reworking · your note',
  session: 'Session open',
  rebasing: 'Rebasing onto the PR head',
  filing: 'Accepted · filing the ticket',
  landing: 'Accepted · landing',
  landed: 'Accepted · pushed',
  'push failed': 'Accepted · the push failed',
  'reply failed': 'Accepted · pushed, the reply failed',
  'filing failed': 'Accepted · the filing failed',
  declined: 'Agent declined',
  failed: 'Agent gave up',
  stopped: 'You stopped the agent',
  removed: 'Comment removed',
  waiting: 'Parked · you replied',
  deferred: 'Parked · deferred',
  rejected: 'Rejected · the fix was dropped',
  resolved: 'Resolved on GitHub',
};

const REPLY_PHRASES: Partial<Record<Phase, string>> = {
  proposed: 'Agent proposes a reply',
  landing: 'Accepted · posting the reply',
  landed: 'Accepted · reply posted',
  'reply failed': 'Accepted · the reply failed',
};

const KIND_PHRASES: Record<ProposalKind, Partial<Record<Phase, string>>> = {
  commit: {},
  reply: REPLY_PHRASES,
  ticket: {
    proposed: 'Agent proposes a ticket',
    landing: 'Accepted · posting the reply',
    landed: 'Accepted · ticket filed',
    'reply failed': 'Accepted · ticket filed, the reply failed',
  },
};

function withoutCode(proposal: Proposal | undefined): boolean {
  return proposal !== undefined && proposal.kind !== 'commit';
}

const FAILURES: Partial<
  Record<Phase, { headline: string; output_label: string; standing: string }>
> = {
  'push failed': {
    headline: 'The push failed',
    output_label: 'What git said',
    standing:
      'The fix is committed on the PR branch on this machine. Nothing ' +
      'reached GitHub, and the comment is unanswered.',
  },
  'reply failed': {
    headline: 'The reply failed',
    output_label: 'What GitHub said',
    standing:
      'The fix is pushed and on the PR branch. The comment has no reply.',
  },
  'filing failed': {
    headline: 'The filing failed',
    output_label: 'What the agent said',
    standing: 'Nothing was posted to GitHub. The comment has no reply.',
  },
};

const VERDICTS: Partial<Record<Phase, string>> = {
  declined: 'skipped: ',
  failed: 'failed: ',
  stopped: '',
};

const FOLD_PLACEHOLDERS: Partial<Record<Phase, string>> = {
  queued: 'Nothing yet. The agent has not started on this comment.',
  working: 'The diff appears when the agent finishes.',
};

const REWORK: Omit<ReworkView, 'reviewers'> = {
  kicker: 'Send back for rework',
  placeholder: 'Tell the agent what to change and why…',
  send_label: 'Send to agent for rework',
  note:
    'Comment moves to "Sent back for rework"; the agent re-runs with your ' +
    'note and the pointed lines.',
};

const REVIEWER_REPLY_NOTE =
  'Posts to GitHub now, on its own, not with your review. ' +
  'No verdict, no resolve; the thread moves to Waiting on author.';

const UNREPLIED = ['draft', 'enrolled', 'done'];

const COMPOSED = ['draft', 'enrolled'];

function composing(conversation: Conversation): boolean {
  return conversation.kind === 'draft' && COMPOSED.includes(conversation.state);
}

export function draftOf(
  conversation: Conversation,
  details: Details | null,
): DraftView | null {
  if (!composing(conversation) || !details) return null;
  const { path, line, start_line, start_side, side } = conversation.anchor;
  return {
    body: details.comments[0]?.body ?? '',
    path: path ?? '',
    line,
    start_line,
    start_side,
    side: side ?? 'RIGHT',
    editable: !busy(conversation),
    enrolled: conversation.state === 'enrolled',
    posting: outstanding(conversation)?.kind === 'post-now',
  };
}

export function draftLocked(
  draft: Pick<DraftView, 'editable' | 'enrolled'>,
  reviewSending: boolean,
): boolean {
  return !draft.editable || (draft.enrolled && reviewSending);
}

function draftNotes(conversation: Conversation): Note[] {
  if (!composing(conversation)) return [];
  const posted = conversation.operations.findLast(
    (one) => one.kind === 'post-now',
  );
  if (posted?.state !== 'refused') return [];
  return [
    {
      kind: 'verdict',
      text: `GitHub refused the post: ${posted.reason ?? posted.reason_code ?? ''}`,
    },
  ];
}

function relative(stamp: string | null, now: number): string {
  if (!stamp) return '';
  const minutes = Math.floor((now - Date.parse(stamp)) / MINUTE);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function counted(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function firstName(name: string): string {
  return name.split(' ')[0] ?? '';
}

function short(sha: string | null | undefined): string {
  return (sha ?? '').slice(0, SHORT_SHA);
}

type OperationOf<K extends OperationKind> = Operation & { kind: K };

function newest<K extends OperationKind>(
  operations: Operation[],
  kinds: K[],
): OperationOf<K> | undefined {
  return operations.findLast((one): one is OperationOf<K> =>
    kinds.some((kind) => kind === one.kind),
  );
}

function runningOf(operation: Operation | undefined) {
  return operation && 'plan' in operation ? operation : undefined;
}

function kickerOf(conversation: Conversation, context: Context): string {
  if (conversation.reopened) return 'Re-opened · top of queue';
  const phase = phaseOf(conversation);
  const byPhase = KICKER_PHASES[phase];
  if (byPhase) return byPhase;
  const group = groupOf(conversation, context.role);
  const labels = groupsFor(context.role);
  const at = context.ready.indexOf(conversation.key);
  if (group === READY_GROUP && at >= 0) {
    const word = (labels[0]?.label ?? '').split(' ')[0]?.toLowerCase() ?? '';
    return `${at + 1} of ${context.ready.length} ${word}`;
  }
  return (
    KICKER_GROUPS[group] ?? labels.find((one) => one.key === group)?.label ?? ''
  );
}

function replyToOf(conversation: Conversation, context: Context): string {
  const other = conversation.comments.findLast(
    (one) => one.author !== context.viewer,
  );
  return other ? nameOf(other.author, context.names) : '';
}

function locationOf(conversation: Conversation): string {
  const { path, line, original_line } = conversation.anchor;
  const at = line ?? original_line;
  if (path && at !== null) return `${path} line ${at}`;
  return path ?? KIND_LABELS[conversation.kind] ?? '';
}

function anchorOf(conversation: Conversation): string {
  const { path, line } = conversation.anchor;
  if (path && line !== null) return `${path}:${line}`;
  return path ?? `comment #${conversation.comments[0]?.id ?? 0}`;
}

function codeOf(conversation: Conversation, context: Context): Code | null {
  const anchor = conversation.anchor;
  if (!anchor.path || conversation.kind === 'issue') return null;
  const head = context.pullRequest?.head_sha;
  const current = !anchor.is_outdated && anchor.line !== null && head;
  const sha =
    anchor.side === 'LEFT'
      ? context.pullRequest?.diffs.origin?.base
      : current
        ? head
        : anchor.original_commit;
  const last = current ? anchor.line : anchor.original_line;
  if (!sha || last === null) return null;
  const first =
    (current ? anchor.start_line : anchor.original_start_line) ?? last;
  return {
    sha,
    path: anchor.path,
    first,
    last,
    from_line: Math.max(1, first - CONTEXT_LINES),
    to_line: last + CONTEXT_LINES,
    outdated: anchor.is_outdated ? `Outdated · at ${short(sha)}` : null,
  };
}

function roleLineOf(conversation: Conversation, context: Context): string {
  const opener = conversation.comments[0];
  if (context.role === 'reviewer') {
    const unread = conversation.unread ? 'not yet read' : '';
    const replier = conversation.comments.at(-1);
    if (conversation.comments.length < 2 || !replier) return unread;
    const who =
      replier.author === context.viewer
        ? 'you'
        : nameOf(replier.author, context.names);
    return sentence(`${who} replied`, unread);
  }
  if (conversation.reopened) return 'replied again';
  return REVIEW_STATE_WORDS[opener?.review_state ?? ''] ?? '';
}

function startedOf(
  conversation: Conversation,
  context: Context,
): { started: string; started_at: string } {
  const stamp = conversation.comments[0]?.created_at ?? null;
  if (context.role !== 'reviewer' || !stamp)
    return { started: '', started_at: '' };
  return {
    started: `started ${relative(stamp, context.now)}`,
    started_at: new Date(stamp).toLocaleString(),
  };
}

export function transcriptOf(
  conversation: Conversation,
  comments: Comment[],
  context: Context,
): TranscriptEntry[] {
  const opener = comments[0]?.author;
  const cameBack = conversation.reopened
    ? comments.findLastIndex((one) => one.author === opener)
    : -1;
  return comments.map((one, at) => ({
    author: one.author || 'ghost',
    author_name: context.names[one.author] ?? '',
    body: one.body,
    meta: sentence(
      REVIEW_STATE_WORDS[one.review_state ?? ''] ?? '',
      relative(one.created_at, context.now),
    ),
    highlighted: at === cameBack && at > 0,
  }));
}

function replyOf(
  conversation: Conversation,
  comments: Comment[],
  context: Context,
): ReplyBox | null {
  if (
    UNREPLIED.includes(conversation.state) ||
    comments[0]?.deleted ||
    conversation.mention
  ) {
    return null;
  }
  return {
    threaded: conversation.kind === 'review',
    parks: conversation.state === 'ready',
    note: context.role === 'reviewer' ? REVIEWER_REPLY_NOTE : '',
  };
}

function canDelete(
  conversation: Conversation,
  comments: Comment[],
  viewer: string,
): boolean {
  const root = comments[0];
  return (
    root !== undefined &&
    root.author === viewer &&
    DELETABLE.includes(conversation.kind) &&
    root.id !== null &&
    !root.deleted &&
    comments.every((one) => one.author === viewer)
  );
}

function planOf(
  conversation: Conversation,
  operations: Operation[],
  context: Context,
): PlanStep[] {
  const live = atWork(conversation)
    ? runningOf(context.inFlight)?.plan
    : undefined;
  const plan = live ?? newest(operations, RUN_KINDS)?.plan ?? [];
  return plan.map((step) => ({
    text: step.text,
    file: step.file ?? '',
    done: step.done,
  }));
}

function changesClause(plan: PlanStep[]): string {
  if (!plan.length) return '';
  return ` · ${plan.filter((step) => step.done).length} of ${plan.length} changes`;
}

function fixLabelOf(
  conversation: Conversation,
  plan: PlanStep[],
  proposal: Proposal | undefined,
): string {
  const phase = phaseOf(conversation);
  const reopenedRun =
    conversation.reopened && (phase === 'queued' || phase === 'working');
  const phrases = proposal ? KIND_PHRASES[proposal.kind] : {};
  const phrase = reopenedRun
    ? 'Agent re-running with the reply'
    : (phrases[phase] ?? FIX_PHRASES[phase]);
  return phrase ? phrase + changesClause(plan) : '';
}

function bannerOf(
  conversation: Conversation,
  plan: PlanStep[],
  operations: Operation[],
  files: FileStat[],
  replying: boolean,
): FixBanner | null {
  const phase = phaseOf(conversation);
  if (phase === 'landed' && replying) {
    const filed = newest(operations, ['approve'])?.ticket_key;
    return filed
      ? { title: `Filed ${filed}`, body: 'The reply links it.', tone: 'landed' }
      : { title: 'Reply posted', body: '', tone: 'landed' };
  }
  if (phase === 'working') {
    const done = plan.filter((step) => step.done).length;
    return {
      title: plan.length
        ? `Running · ${done} of ${plan.length} changes done`
        : 'Running',
      body: 'The proposal appears here when the agent finishes.',
      tone: 'working',
    };
  }
  if (phase === 'queued') {
    return {
      title: 'Waiting for a free agent',
      body: 'The agent has not started.',
      tone: 'queued',
    };
  }
  if (phase === 'rework') {
    const note = newest(operations, ['rework'])?.brief?.note.trim();
    return {
      title: 'Re-running with your note',
      body: note
        ? `"${note}"`
        : 'Pointed lines and your instructions are in its context.',
      tone: 'rework',
    };
  }
  if (phase === 'landed') {
    const landed = newest(operations, ['approve'])?.landed_sha;
    const carried = [
      plan.length ? counted(plan.length, 'change') : '',
      files.length ? counted(files.length, 'file') : '',
    ].filter(Boolean);
    return {
      title: `Pushed ${short(landed)}`.trim(),
      body: carried.join(', '),
      tone: 'landed',
    };
  }
  return null;
}

function wakeText(until: string | undefined): string {
  if (until === 'ci') return "waiting until this PR's CI passes";
  if (until?.startsWith('push')) return 'waiting until the next push';
  const pr = /^pr:(\d+)$/.exec(until ?? '');
  if (pr) return `waiting until PR #${pr[1]} closes`;
  return 'waiting until you bring it back';
}

function deferralNotes(
  conversation: Conversation,
  operations: Operation[],
): Note[] {
  if (conversation.state !== 'deferred') return [];
  const deferred = newest(operations, ['defer']);
  const notes = [{ kind: 'deferral', text: wakeText(deferred?.until) }];
  if (deferred?.note) notes.push({ kind: 'defer-note', text: deferred.note });
  return notes;
}

function queuedNote(conversation: Conversation): Note[] {
  if (!busy(conversation)) return [];
  const kind = outstanding(conversation)?.kind ?? '';
  return [{ kind: 'queued', text: inFlight(kind) }];
}

function workNotes(
  conversation: Conversation,
  operations: Operation[],
  proposal: Proposal | undefined,
  context: Context,
): Note[] {
  const phase = phaseOf(conversation);
  const notes: Note[] = [];
  const live = runningOf(context.inFlight);
  if (phase === 'queued') {
    const attempts = newestOf(conversation, RUN_KINDS);
    const again =
      attempts?.attempts && attempts.attempts_allowed
        ? ` (attempt ${attempts.attempts + 1} of ${attempts.attempts_allowed})`
        : '';
    notes.push({ kind: 'agent', text: `waiting for an agent…${again}` });
  }
  if (atWork(conversation) && live?.last_action) {
    notes.push({ kind: 'action', text: live.last_action });
  }
  if (atWork(conversation) && live?.progress) {
    notes.push({ kind: 'progress', text: live.progress });
  }
  const run = newest(operations, RUN_KINDS);
  const fix = run?.kind === 'start-session' ? undefined : run;
  if (run?.state === 'refused' && run.reason) {
    const attempt =
      phase === 'failed' && fix?.attempts && fix.attempts_allowed
        ? `attempt ${fix.attempts} of ${fix.attempts_allowed} failed: `
        : null;
    const verdict =
      attempt ??
      VERDICTS[phase] ??
      (run.reason_code === 'agent-declined'
        ? VERDICTS.declined
        : 'previous attempt failed: ');
    notes.push({ kind: 'verdict', text: `${verdict}${run.reason}` });
  }
  if (fix?.conflict) {
    notes.push({
      kind: 'landing-failure',
      text:
        phase === 'rebasing'
          ? `Rebasing onto ${short(fix.onto)}: it lands on its own if its tests pass`
          : `could not land on ${short(fix.onto)}`,
      detail: fix.conflict,
    });
  }
  const note = proposal?.agent_note;
  if (note && note !== proposal?.summary) {
    notes.push({ kind: 'agent-note', text: note });
  }
  return notes;
}

function foldOf(
  conversation: Conversation,
  proposal: Proposal | undefined,
  operations: Operation[],
  files: FileStat[],
): Fold | null {
  const phase = phaseOf(conversation);
  const commits = proposal?.kind === 'commit' ? proposal.commits : null;
  if (!commits || FAILURES[phase]) return null;
  const landed = phase === 'landed';
  let title = `Proposed diff${files.length ? ` · ${counted(files.length, 'file')}` : ''}`;
  if (landed) {
    title = `Pushed as ${short(newest(operations, ['approve'])?.landed_sha)}`;
  } else if (conversation.reopened) {
    title = 'Previous proposal';
  } else if (phase === 'rework') {
    title = 'Previous proposal (being reworked)';
  }
  return {
    commits,
    title,
    pointing_title: POINTING_TITLE,
  };
}

function repliersOf(comments: Comment[], context: Context): Reviewer[] {
  const seen = new Map<string, string>();
  for (const one of comments.slice(1)) {
    if (!one.author || one.author === context.viewer || seen.has(one.author)) {
      continue;
    }
    seen.set(one.author, firstName(nameOf(one.author, context.names)));
  }
  return [...seen].map(([author, first]) => ({
    author,
    label: `Include ${first}'s replies`,
  }));
}

function acceptOf(
  conversation: Conversation,
  proposal: Proposal | undefined,
  plan: PlanStep[],
  files: FileStat[],
  reviewer: string,
  context: Context,
): AcceptView {
  const first = firstName(reviewer);
  const changes = plan.length ? counted(plan.length, 'change') : 'the fix';
  const branch = context.pullRequest?.branch ?? 'the PR branch';
  const accept = {
    title: `Accept: push ${changes} to ${branch}`,
    lead:
      'One commit on the PR branch. Decide here how ' +
      `${first || 'the reviewer'} hears about it.`,
    files,
    reply_kicker: first ? `Reply to ${first} on GitHub` : 'Reply on GitHub',
    resolvable: conversation.kind === 'review' && !conversation.github_removed,
    message: proposal?.commit_message ?? null,
  };
  const phase = phaseOf(conversation);
  const replying = withoutCode(proposal);
  if (phase === 'reply failed') {
    return {
      ...accept,
      title: first ? `Retry the reply to ${first}` : 'Retry the reply',
      lead: replying
        ? proposal?.kind === 'ticket'
          ? 'The ticket is already filed, so nothing is filed again: this ' +
            'posts the reply only.'
          : 'Nothing is pushed: this posts the reply only.'
        : `The fix is already pushed to ${branch}, so nothing is pushed ` +
          'again: this posts the reply only.',
      files: [],
      message: null,
    };
  }
  if (replying) {
    return { ...accept, title: null, lead: null, files: [], message: null };
  }
  if (phase === 'push failed') {
    return {
      ...accept,
      title: `Push the fix again to ${branch}`,
      lead:
        'The fix is already committed on the PR branch on this machine, so ' +
        'nothing new is committed: this pushes that commit. If GitHub has ' +
        'newer commits on the branch, it refuses the push again.',
      message: null,
    };
  }
  return accept;
}

function failureOf(
  phase: Phase,
  failure: Omit<LandingFailure, 'summary' | 'machine'>,
  operations: Operation[],
  replying: boolean,
): LandingFailure {
  const approve = newest(operations, ['approve']);
  const machine = approve?.reason?.trim() ?? '';
  const standing = approve?.ticket_key
    ? `The ticket is filed as ${approve.ticket_key}. The comment has no reply.`
    : replying && phase === 'reply failed'
      ? 'Nothing was pushed. The comment has no reply.'
      : failure.standing;
  return {
    ...failure,
    standing,
    summary: causeOf(phase, machine)?.sentence ?? '',
    machine,
  };
}

const NO_FIX = {
  fix_label: '',
  fix_directory: null,
  in_session: false,
  banner: null,
  proposed_reply: null,
  proposed_ticket: null,
  summary: '',
  failure: null,
  plan: [],
  confidence: null,
  confidence_note: '',
  tests: null,
  tests_note: '',
  files: [],
  files_label: '',
  fold: null,
  fold_placeholder: '',
  accept: null,
  rework: null,
  agent_words: null,
};

export function panelOf(
  conversation: Conversation,
  details: Details | null,
  context: Context,
  fix: Fix,
): Panel {
  const comments = details?.comments ?? [];
  const operations = details?.operations ?? [];
  const reviewer = nameOf(
    conversation.comments[0]?.author ?? '',
    context.names,
  );
  const { proposal } = fix;
  const actions = offered(conversation, context.role, proposal);
  const reply = replyOf(conversation, comments, context);
  const replyTo = replyToOf(conversation, context);
  const top = {
    id: conversation.key,
    role: context.role,
    mention: conversation.mention,
    phase: phaseOf(conversation),
    square: squareOf(conversation),
    reviewer_name: reviewer,
    reply_to: replyTo,
    role_line: roleLineOf(conversation, context),
    ...startedOf(conversation, context),
    kicker: kickerOf(conversation, context),
    kicker_hint: conversation.reopened
      ? REOPENED_HINT
      : PHASE_HINTS[phaseOf(conversation)],
    location: locationOf(conversation),
    url: comments[0]?.html_url ?? context.pullRequest?.url ?? '',
    anchor: anchorOf(conversation),
    code: codeOf(conversation, context),
    loading: details === null,
    draft: draftOf(conversation, details),
    transcript: composing(conversation)
      ? []
      : transcriptOf(conversation, comments, context),
    reply,
    reply_action:
      reply &&
      context.role !== 'reviewer' &&
      actions.every((one) => one.weight === 'ghost')
        ? {
            kind: 'reply',
            label: `Reply to ${firstName(replyTo)}`,
            weight: 'secondary',
          }
        : null,
    actions,
    can_delete: canDelete(conversation, comments, context.viewer),
  };
  if (context.role === 'reviewer') {
    return {
      ...top,
      ...NO_FIX,
      notes: [
        ...deferralNotes(conversation, operations),
        ...draftNotes(conversation),
        ...queuedNote(conversation),
      ],
    };
  }
  const replying = withoutCode(proposal);
  const plan = planOf(conversation, operations, context);
  const files = fix.files;
  const phase = phaseOf(conversation);
  const failure = FAILURES[phase];
  const decides = (decision: string) =>
    actions.some((one) => one.decision === decision);
  return {
    ...top,
    fix_label: fixLabelOf(conversation, plan, proposal),
    fix_directory: proposal?.directory ?? null,
    in_session: phase === 'session',
    banner: bannerOf(conversation, plan, operations, files, replying),
    proposed_reply: replying ? (proposal?.reply ?? null) : null,
    proposed_ticket: proposal?.ticket ?? null,
    summary: proposal?.summary || proposal?.agent_note || '',
    failure: failure ? failureOf(phase, failure, operations, replying) : null,
    plan,
    confidence: proposal?.confidence ?? null,
    confidence_note: proposal?.confidence_note ?? '',
    tests: replying ? null : (proposal?.tests ?? null),
    tests_note: proposal?.tests_note ?? '',
    files,
    files_label: files.length ? counted(files.length, 'file') : '',
    notes: [
      ...deferralNotes(conversation, operations),
      ...workNotes(conversation, operations, proposal, context),
      ...draftNotes(conversation),
      ...queuedNote(conversation),
    ],
    fold: foldOf(conversation, proposal, operations, files),
    fold_placeholder: FOLD_PLACEHOLDERS[phase] ?? '',
    accept: decides('approve')
      ? acceptOf(conversation, proposal, plan, files, reviewer, context)
      : null,
    rework: decides('rework')
      ? { ...REWORK, reviewers: repliersOf(comments, context) }
      : null,
    agent_words:
      phase === 'declined'
        ? (newest(operations, RUN_KINDS)?.reason ?? null)
        : null,
  };
}
