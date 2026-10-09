import type {
  Conversation,
  Operation,
  OperationSummary,
} from 'frontend/data/api';
import { causeOf } from 'frontend/data/failure';
import {
  alertOf,
  columnOf,
  groupOf,
  squareOf,
  type Role,
} from 'frontend/data/groups';
import {
  busy,
  newestOf,
  outstanding,
  PHASE_HINTS,
  phaseOf,
  RUN_KINDS,
  STANDING_LABELS,
  standingOf,
  type Phase,
  type Standing,
} from 'frontend/data/thread';
import { inFlight } from 'frontend/data/decisions';

export interface Row {
  id: string;
  group: string;
  column: string;
  square: string;
  gist: string;
  reference: string | null;
  meta: string;
  steps: boolean[];
  steps_text: string;
  steps_hint: string;
  standing: Standing | null;
  standing_label: string;
  alert: string;
  provisional: boolean;
}

export interface Seen {
  role: Role;
  viewer: string;
  names: Record<string, string | null>;
  inFlight?: Operation | undefined;
}

export const KIND_LABELS: Record<string, string> = {
  issue: 'conversation',
  'review-summary': 'review summary',
  'pr-body': 'PR description',
};

const COMPOSING = ['draft', 'enrolled'];

const SETTLED: Phase[] = [
  'landed',
  'rejected',
  'resolved',
  'confirmed',
  'discarded',
];

const SAID: Partial<Record<Phase, string>> = {
  rework: 'Your note · agent re-running',
  session: 'Session open',
  landing: 'Landing',
  rebasing: 'Rebasing onto the PR head',
  filing: 'Filing the ticket',
  deferred: 'Deferred',
  rejected: 'Rejected',
  resolved: 'Resolved on GitHub',
  confirmed: 'Confirmed',
  discarded: 'Discarded',
  removed: 'comment removed from GitHub',
};

const VERDICTS: Partial<Record<Phase, string>> = {
  declined: 'skipped',
  failed: 'failed',
  stopped: 'stopped',
  'push failed': 'push failed',
  'reply failed': 'reply failed',
  'filing failed': 'filing failed',
};

export function nameOf(
  login: string,
  names: Record<string, string | null>,
): string {
  return names[login] ?? login;
}

export function sentence(...parts: string[]): string {
  return parts.filter(Boolean).join(' · ');
}

export function referenceOf(conversation: Conversation): string | null {
  const label = KIND_LABELS[conversation.kind];
  if (label) return label;
  const { path, line, original_line } = conversation.anchor;
  if (!path) return null;
  const at = line ?? original_line;
  return at === null ? path : `${path}:${at}`;
}

function currentRun(conversation: Conversation): OperationSummary | undefined {
  return newestOf(conversation, RUN_KINDS);
}

export function stepsOf(conversation: Conversation, seen: Seen): boolean[] {
  if (SETTLED.includes(phaseOf(conversation))) return [];
  const live = seen.inFlight;
  const plan = live && 'plan' in live ? live.plan : undefined;
  if (plan?.length) return plan.map((step) => step.done);
  const run = currentRun(conversation);
  const total = run?.steps_total ?? 0;
  const done = run?.steps_done ?? 0;
  return Array.from({ length: total }, (_, at) => at < done);
}

function counted(steps: boolean[]): { done: number; total: number } {
  return { done: steps.filter(Boolean).length, total: steps.length };
}

function verdict(conversation: Conversation, word: string): string {
  const reason =
    conversation.operations.findLast((one) => one.state === 'refused')
      ?.reason ?? '';
  const cause = causeOf(phaseOf(conversation), reason);
  if (cause) return `${word}: ${cause.short}`;
  return reason ? `${word}: ${reason.trim().split('\n').at(-1)}` : word;
}

function authorMeta(
  conversation: Conversation,
  seen: Seen,
  steps: boolean[],
): string {
  const phase = phaseOf(conversation);
  const opener = conversation.comments[0]?.author ?? '';
  const who = nameOf(opener, seen.names);
  const { done, total } = counted(steps);
  if (conversation.reopened && (phase === 'queued' || phase === 'working')) {
    return sentence(`${who} replied`, 'agent re-running');
  }
  const word = VERDICTS[phase];
  if (word) return verdict(conversation, word);
  switch (phase) {
    case 'proposed':
      return sentence(
        who,
        total ? `${done} of ${total} changes` : '',
        conversation.reopened ? 'revised' : '',
      );
    case 'queued':
      return sentence(who, 'waiting for a free agent');
    case 'working':
      return sentence(who, 'running', total ? `${done}/${total}` : '');
    case 'answered':
    case 'assumed-done':
    case 'not-mine':
      return answeredMeta(conversation, seen);
    case 'waiting':
      return conversation.comments.at(-1)?.author === seen.viewer
        ? 'You replied'
        : answeredMeta(conversation, seen);
    case 'landed':
      return landedMeta(conversation);
    default:
      return SAID[phase] ?? '';
  }
}

function landedMeta(conversation: Conversation): string {
  const approve = newestOf(conversation, ['approve']);
  if (approve?.lands === 'reply') return 'Replied';
  if (approve?.lands === 'ticket') {
    return `Filed ${approve.ticket_key ?? 'the ticket'}`;
  }
  return 'Pushed';
}

function answeredMeta(conversation: Conversation, seen: Seen): string {
  const opener = conversation.comments[0]?.author ?? '';
  const newest = conversation.comments.at(-1)?.author ?? opener;
  const replied =
    conversation.comments.length > 1
      ? `${nameOf(newest, seen.names)} replied`
      : nameOf(opener, seen.names);
  const whose =
    seen.role === 'reviewer' && opener !== seen.viewer
      ? `${nameOf(opener, seen.names)}'s thread`
      : '';
  return sentence(whose, replied);
}

function metaOf(
  conversation: Conversation,
  seen: Seen,
  steps: boolean[],
): string {
  if (busy(conversation)) {
    const kind = outstanding(conversation)?.kind ?? '';
    return inFlight(kind);
  }
  if (seen.role === 'reviewer' && conversation.state === 'ready') {
    return sentence(
      answeredMeta(conversation, seen),
      conversation.unread ? 'not yet read' : '',
    );
  }
  return authorMeta(conversation, seen, steps);
}

export function gistOf(conversation: Conversation, seen: Seen): string {
  if (conversation.gist) return conversation.gist;
  const opener = conversation.comments[0]?.author;
  return opener ? `${nameOf(opener, seen.names)} commented` : 'a comment';
}

function draftStanding(conversation: Conversation): Standing | null {
  const standing = standingOf(conversation);
  return standing !== 'posted' && COMPOSING.includes(conversation.state)
    ? standing
    : null;
}

export function rowOf(
  conversation: Conversation & { provisional?: boolean },
  seen: Seen,
): Row {
  const steps = stepsOf(conversation, seen);
  const standing = draftStanding(conversation);
  const { done, total } = counted(steps);
  const phase = phaseOf(conversation);
  return {
    id: conversation.key,
    group: groupOf(conversation, seen.role),
    column: columnOf(conversation, seen.role),
    square: squareOf(conversation),
    gist: gistOf(conversation, seen),
    reference: referenceOf(conversation),
    meta: metaOf(conversation, seen, steps),
    steps,
    steps_text: total ? `${done} / ${total} changes` : phase,
    steps_hint: total ? '' : `${phase}: ${PHASE_HINTS[phase]}`,
    standing,
    standing_label: standing ? STANDING_LABELS[standing] : '',
    alert: alertOf(conversation),
    provisional: conversation.provisional === true,
  };
}
