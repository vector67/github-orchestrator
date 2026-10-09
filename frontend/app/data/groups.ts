import type { Conversation, ConversationState } from 'frontend/data/api';
import { closedBy, phaseOf, type Phase } from 'frontend/data/thread';

export type Role = 'author' | 'reviewer';

export interface Group {
  key: string;
  label: string;
  hint: string;
}

export interface Count {
  key: string;
  label: string;
  count: number;
}

export interface Grouped {
  group: Group;
  threads: Conversation[];
}

export interface Column {
  column: Group;
  threads: Conversation[];
}

export const READY_GROUP = 'ready';

const ATTENTION_GROUP = 'attention';

const DECIDED_PHASE: Record<Role, Phase> = {
  author: 'proposed',
  reviewer: 'answered',
};

const GROUP_ORDER: Record<Role, string[]> = {
  author: [
    'ready',
    'attention',
    'review',
    'drafts',
    'working',
    'queued',
    'rework',
    'landing',
    'waiting',
    'assumed-done',
    'deferred',
    'done',
  ],
  reviewer: [
    'ready',
    'attention',
    'review',
    'drafts',
    'waiting',
    'assumed-done',
    'not-mine',
    'deferred',
    'done',
  ],
};

const AUTHOR_LABELS: Record<string, string> = {
  ready: 'Ready for you',
  attention: 'Needs a look',
  review: 'Your review',
  drafts: 'Local drafts',
  working: 'Agent working',
  queued: 'Queued for agent',
  rework: 'Sent back for rework',
  landing: 'Landing',
  waiting: 'Waiting on reviewer',
  'assumed-done': 'Assumed done',
  'not-mine': 'Not my conversation',
  deferred: 'Deferred',
  done: 'Done',
};

const REVIEWER_LABELS: Record<string, string> = {
  ...AUTHOR_LABELS,
  ready: 'Answered',
  waiting: 'Waiting on author',
};

const AUTHOR_HINTS: Record<string, string> = {
  ready: 'The agent proposed a fix; accept it, send it back or turn it down',
  attention:
    'Yours, with no fix to accept: the agent skipped or failed, a push, reply or filing failed, or someone answered',
  review:
    'Drafts in the review you send from the strip; nothing posts until you send it',
  drafts: 'Comments you wrote here that are not on GitHub yet',
  working: 'An agent is writing a fix right now',
  queued: 'Waiting for a free agent',
  rework: 'Back with the agent carrying your note, or in a session you steer',
  landing: 'Accepted: the fix is on its way to the PR branch, then the reply',
  waiting: 'You replied; parked until the reviewer answers',
  'assumed-done':
    'An agent read these as settled; only you can move them to Done',
  deferred: 'Parked until the condition you chose is met',
  done: 'Finished: pushed, resolved, confirmed, rejected or discarded',
};

const REVIEWER_HINTS: Record<string, string> = {
  ...AUTHOR_HINTS,
  ready:
    'The author answered your thread; resolve it, reply or say it is not fixed',
  attention:
    'Yours to look at: the comment was removed on GitHub, or a step failed',
  waiting: 'Their move; parked until the author or someone else answers',
  'not-mine':
    'An agent read these as asking nothing of you: someone else’s thread, the description or a summary',
};

const GROUP_OF_STATE: Record<ConversationState, string> = {
  draft: 'drafts',
  enrolled: 'review',
  ready: 'ready',
  working: 'working',
  queued: 'queued',
  rework: 'rework',
  'in-session': 'rework',
  landing: 'landing',
  waiting: 'waiting',
  'assumed-done': 'assumed-done',
  'not-mine': 'not-mine',
  deferred: 'deferred',
  done: 'done',
};

const SQUARE_OF_GROUP: Record<string, string> = {
  ready: 'ready',
  review: 'ready',
  drafts: 'ready',
  working: 'working',
  queued: 'queued',
  rework: 'rework',
  landing: 'working',
  waiting: 'waiting',
  deferred: 'waiting',
  'assumed-done': 'done',
  'not-mine': 'done',
  done: 'done',
};

const ALERTS: Partial<Record<Phase, string>> = {
  failed: 'Agent gave up',
  stopped: 'You stopped the agent',
  declined: 'Agent declined',
  'push failed': 'Push failed',
  'reply failed': 'Reply failed',
  'filing failed': 'Filing failed',
  removed: 'Comment removed',
};

const SQUARE_TITLES: Record<string, string> = {
  ready: 'Your decision',
  failed: 'Needs a look',
  working: 'Agent working',
  queued: 'Queued for agent',
  rework: 'Sent back for rework',
  waiting: 'Parked',
  reopened: 'Reviewer replied',
  done: 'Done',
};

const AUTHOR_COLUMNS: Group[] = [
  {
    key: 'working',
    label: 'Agent working',
    hint: 'An agent is writing a fix, or these wait for a free one',
  },
  {
    key: 'ready',
    label: 'Ready for you',
    hint: 'Yours to decide: proposed fixes, and drafts not posted yet',
  },
  { key: 'attention', label: 'Needs a look', hint: AUTHOR_HINTS['attention']! },
  {
    key: 'waiting',
    label: 'Waiting',
    hint: 'Parked on someone else: being reworked, landing, waiting on a reply or deferred',
  },
  { key: 'done', label: 'Done', hint: AUTHOR_HINTS['done']! },
];

const REVIEWER_COLUMNS: Group[] = AUTHOR_COLUMNS.map((column) =>
  column.key === 'ready'
    ? {
        key: 'ready',
        label: 'Answered',
        hint: 'The author answered your thread, and your drafts not posted yet',
      }
    : column.key === 'attention'
      ? { ...column, hint: REVIEWER_HINTS['attention']! }
      : column,
);

const COLUMN_OF_GROUP: Record<string, string> = {
  ready: 'ready',
  attention: 'attention',
  review: 'ready',
  drafts: 'ready',
  working: 'working',
  queued: 'working',
  rework: 'waiting',
  landing: 'waiting',
  waiting: 'waiting',
  deferred: 'waiting',
  'assumed-done': 'done',
  'not-mine': 'done',
  done: 'done',
};

const COUNTED: { key: string; label: string }[] = [
  { key: 'ready', label: 'ready' },
  { key: 'attention', label: 'to look at' },
  { key: 'review', label: 'in your review' },
  { key: 'drafts', label: 'local drafts' },
  { key: 'working', label: 'agent working' },
  { key: 'queued', label: 'queued' },
  { key: 'rework', label: 'sent back for rework' },
  { key: 'landing', label: 'landing' },
  { key: 'waiting', label: 'waiting on reviewer' },
  { key: 'assumed-done', label: 'assumed done' },
  { key: 'not-mine', label: 'not mine' },
  { key: 'deferred', label: 'deferred' },
  { key: 'done', label: 'done' },
];

const REVIEWER_COUNT_LABELS: Record<string, string> = {
  ready: 'answered',
  waiting: 'waiting on author',
};

export function groupOf(conversation: Conversation, role: Role): string {
  if (conversation.state !== 'ready') return GROUP_OF_STATE[conversation.state];
  return phaseOf(conversation) === DECIDED_PHASE[role]
    ? READY_GROUP
    : ATTENTION_GROUP;
}

export function groupsFor(role: Role): Group[] {
  const labels = role === 'reviewer' ? REVIEWER_LABELS : AUTHOR_LABELS;
  const hints = role === 'reviewer' ? REVIEWER_HINTS : AUTHOR_HINTS;
  return GROUP_ORDER[role].map((key) => ({
    key,
    label: labels[key] ?? key,
    hint: hints[key] ?? '',
  }));
}

export function grouped(threads: Conversation[], role: Role): Grouped[] {
  return groupsFor(role)
    .map((group) => ({
      group,
      threads: threads.filter((one) => groupOf(one, role) === group.key),
    }))
    .filter((one) => one.threads.length > 0);
}

export function columnOf(conversation: Conversation, role: Role): string {
  return COLUMN_OF_GROUP[groupOf(conversation, role)] ?? READY_GROUP;
}

export function columnCards(threads: Conversation[], role: Role): Column[] {
  const columns = role === 'reviewer' ? REVIEWER_COLUMNS : AUTHOR_COLUMNS;
  return columns.map((column) => ({
    column,
    threads: threads.filter((one) => columnOf(one, role) === column.key),
  }));
}

export function countsOf(counted: Record<string, number>, role: Role): Count[] {
  const words = role === 'reviewer' ? REVIEWER_COUNT_LABELS : {};
  return COUNTED.map(({ key, label }) => ({
    key,
    label: words[key] ?? label,
    count: counted[key] ?? 0,
  })).filter((one) => one.count > 0);
}

export function squareTitleOf(square: string): string {
  return SQUARE_TITLES[square] ?? '';
}

export function alertOf(conversation: Conversation): string {
  if (conversation.state !== 'ready') return '';
  return ALERTS[phaseOf(conversation)] ?? '';
}

export function squareOf(conversation: Conversation): string {
  const group = GROUP_OF_STATE[conversation.state];
  if (conversation.reopened) return 'reopened';
  if (alertOf(conversation)) return 'failed';
  if (group === 'done' && closedBy(conversation) === 'reject') return 'waiting';
  return SQUARE_OF_GROUP[group] ?? READY_GROUP;
}
