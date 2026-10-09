import type {
  Conversation,
  ConversationState,
  OperationKind,
  OperationSummary,
} from 'frontend/data/api';

export const RUN_KINDS = [
  'first',
  'rebase',
  'rework',
  'retry',
  'start-session',
] satisfies OperationKind[];

const CLOSES = ['approve', 'reject', 'resolve', 'discard'];

const AT_WORK: ConversationState[] = [
  'queued',
  'working',
  'in-session',
  'rework',
  'landing',
];

const LANDING_FAILURES: Record<string, Phase> = {
  'push-failed': 'push failed',
  'reply-failed': 'reply failed',
  'file-failed': 'filing failed',
};

const REFUSALS: Record<string, Phase> = {
  'agent-declined': 'declined',
  withdrawn: 'stopped',
};

const CLOSED_PHASES: Record<string, Phase> = {
  approve: 'landed',
  reject: 'rejected',
  resolve: 'resolved',
  discard: 'discarded',
};

export type Phase =
  | 'draft'
  | 'enrolled'
  | 'queued'
  | 'working'
  | 'session'
  | 'rework'
  | 'landing'
  | 'filing'
  | 'rebasing'
  | 'proposed'
  | 'declined'
  | 'failed'
  | 'stopped'
  | 'answered'
  | 'removed'
  | 'push failed'
  | 'reply failed'
  | 'filing failed'
  | 'waiting'
  | 'assumed-done'
  | 'not-mine'
  | 'deferred'
  | 'landed'
  | 'rejected'
  | 'resolved'
  | 'confirmed'
  | 'discarded';

export const PHASE_HINTS: Record<Phase, string> = {
  draft: 'a comment you wrote here, not on GitHub yet',
  enrolled: 'a draft in your review; it posts when you send the review',
  queued: 'waiting for an agent',
  working: 'an agent is running',
  session: 'a session you steer is open in the Terminal tab or a tmux pane',
  rework: 'an agent is working from your rework note',
  landing: 'accepted: the fix is on its way to the PR branch, then the reply',
  rebasing:
    'the fix conflicted on accept; an agent is rebasing it onto the PR head',
  filing:
    'accepted: an agent is filing the ticket, and the reply follows once it is filed',
  proposed: 'there is a fix to decide on',
  declined: 'the agent declined to write a fix, and said why',
  failed: 'three attempts failed',
  stopped: 'you stopped the agent before it finished',
  answered: 'someone answered; yours to reply to or resolve',
  removed: 'the comment was deleted on GitHub before this row was finished',
  'push failed': 'accepted, but pushing the fix to the PR branch failed',
  'reply failed': 'pushed, but posting the reply on GitHub failed',
  'filing failed':
    'accepted, but filing the ticket failed; nothing was posted to GitHub',
  waiting: 'their move; parked until the other side answers',
  'assumed-done': 'an agent read it as settled; only you can move it to Done',
  'not-mine': 'an agent read it as asking nothing of you',
  deferred: 'parked until something wakes it',
  landed: 'on the PR branch',
  rejected: 'you turned it down',
  resolved: 'closed, worktree and branch gone',
  confirmed: 'you confirmed it was settled; nothing was posted to GitHub',
  discarded: 'a draft thrown away with nothing posted',
};

export const REOPENED_HINT =
  'you replied, and it is yours again whatever the agent is doing';

export type Standing = 'local' | 'pending' | 'posted';

export const STANDING_LABELS: Record<Standing, string> = {
  local: 'Local draft',
  pending: 'In your pending review',
  posted: 'Posted',
};

export function standingOf(conversation: Conversation): Standing {
  if (conversation.kind !== 'draft') return 'posted';
  return conversation.state === 'enrolled' ? 'pending' : 'local';
}

function inFlight(operation: OperationSummary): boolean {
  return operation.state === 'pending' || operation.state === 'running';
}

export function newestOf(
  conversation: Conversation,
  kinds: string[],
): OperationSummary | undefined {
  return conversation.operations.findLast((one) => kinds.includes(one.kind));
}

export function outstanding(
  conversation: Conversation,
): OperationSummary | undefined {
  return conversation.operations.findLast(inFlight);
}

export function atWork(thread: { state: ConversationState }): boolean {
  return AT_WORK.includes(thread.state);
}

export function busy(conversation: Conversation): boolean {
  return !atWork(conversation) && outstanding(conversation) !== undefined;
}

export function proposalWaiting(conversation: Conversation): boolean {
  if (outstanding(conversation)) return false;
  return newestOf(conversation, RUN_KINDS)?.state === 'applied';
}

export function closedBy(conversation: Conversation): string | null {
  const closes = conversation.operations.filter(
    (one) => CLOSES.includes(one.kind) && one.state === 'applied',
  );
  return closes.at(-1)?.kind ?? null;
}

function readyPhase(conversation: Conversation): Phase {
  if (conversation.github_removed) return 'removed';
  const landing = newestOf(conversation, [...RUN_KINDS, 'approve']);
  if (landing?.kind === 'approve' && landing.state === 'refused') {
    const failure = LANDING_FAILURES[landing.reason_code ?? ''];
    if (failure) return failure;
  }
  if (proposalWaiting(conversation)) return 'proposed';
  const run = newestOf(conversation, RUN_KINDS);
  if (run?.state === 'refused') {
    return REFUSALS[run.reason_code ?? ''] ?? 'failed';
  }
  return 'answered';
}

export function phaseOf(conversation: Conversation): Phase {
  switch (conversation.state) {
    case 'ready':
      return readyPhase(conversation);
    case 'done':
      if (conversation.record_state === 'confirmed') return 'confirmed';
      return CLOSED_PHASES[closedBy(conversation) ?? ''] ?? 'resolved';
    case 'in-session':
      return 'session';
    case 'landing': {
      const running = outstanding(conversation)?.kind;
      if (running === 'file') return 'filing';
      return newestOf(conversation, RUN_KINDS)?.kind === 'rebase' &&
        running === 'rebase'
        ? 'rebasing'
        : 'landing';
    }
    default:
      return conversation.state;
  }
}
