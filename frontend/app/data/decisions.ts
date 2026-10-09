import type {
  Conversation,
  Proposal,
  ProposalKind,
  Ticket,
} from 'frontend/data/api';
import type { Role } from 'frontend/data/groups';
import {
  busy,
  newestOf,
  phaseOf,
  proposalWaiting,
  RUN_KINDS,
  type Phase,
} from 'frontend/data/thread';
import type { DraftRequest } from 'frontend/services/drafts';

export interface DialogSpec {
  question: string;
  note: string;
  reply: boolean;
  del?: boolean;
  wake?: boolean;
  prefill?: string;
  ticket?: Ticket;
  placeholder?: string;
  requiresReply?: boolean;
  accept?: boolean;
  resolves?: boolean;
  resolving?: boolean;
  thumbsUp?: boolean;
  outcomes?: Outcome[];
  submit: (
    typed: string,
    resolving: boolean,
    thumbing: boolean,
    outcome: string,
  ) => string;
}

export interface Outcome {
  to: string;
  label: string;
}

export const LATER = 'later';

function placing(outcomes: Outcome[]): DialogSpec {
  return {
    question: 'Where does this thread stand instead?',
    note: 'Nothing is posted to GitHub. Later… asks when it should come back.',
    reply: false,
    outcomes,
    submit: (_typed, _resolving, _thumbing, outcome) =>
      outcome === LATER ? 'Choose when…' : 'Move it',
  };
}

export interface Brief {
  note: string;
  pointed: { file: string; line: number; text: string }[];
  include: string[];
}

export interface Gathered {
  body?: string;
  modifier?: string;
  delete?: boolean;
  resolve?: boolean;
  thumbsUp?: boolean;
  message?: string;
  ticket?: Ticket;
  brief?: Brief;
  draft?: DraftRequest;
}

type Weight = 'primary' | 'secondary' | 'ghost' | 'destructive';

type Asks = DialogSpec | 'rework' | 'composer' | null;

interface Request {
  verb: string;
  body: Record<string, unknown>;
}

interface Carrying {
  request?: (gathered: Gathered) => Request;
  doing: string;
  square: string | null;
  toast?: (gathered: Gathered) => string;
  opensTerminal?: boolean;
}

interface Shade {
  label?: string;
  weight?: Weight;
}

interface Entry extends Carrying {
  key: string;
  label: string;
  weight: Weight;
  title: string;
  asks: Asks;
  savedFirst?: boolean;
  offeredWhen?: (conversation: Conversation) => boolean;
  forKind?: Partial<Record<ProposalKind, Partial<DialogSpec>>>;
  inPhase?: Partial<Record<Phase, Shade & { dialog?: Partial<DialogSpec> }>>;
  reviewer?: {
    title?: string;
    asks?: DialogSpec;
    inPhase?: Partial<Record<Phase, Shade>>;
  };
}

export interface Offer {
  decision: Decision;
  label: string;
  title: string;
  weight: Weight;
  key: string;
  cap: string;
  doing: string;
  asks: Asks;
  savedFirst: boolean;
}

export interface Carried {
  request: Request;
  toast: { text: string; square: string } | null;
  opensTerminal: boolean;
}

export const WAKE_CONDITIONS = [
  { value: 'manual', label: 'when I bring it back' },
  { value: 'ci', label: "when this PR's CI passes" },
  { value: 'pr', label: 'when another PR closes' },
  { value: 'push', label: 'when the next push lands' },
] as const;

function closing({
  body,
  delete: deleting,
}: Gathered): Record<string, unknown> {
  return {
    ...(body ? { reply: body } : {}),
    delete_comment: Boolean(deleting),
  };
}

function reworkToast(pointed: number): string {
  const counted =
    pointed === 0
      ? ''
      : ` with ${pointed} pointed line${pointed === 1 ? '' : 's'}`;
  return `Sent back for rework${counted}. Agent re-running.`;
}

const ENTRIES = {
  approve: {
    key: 'a',
    label: 'Accept',
    weight: 'primary',
    title:
      'lands this fix on the PR branch and replies to the comment, on its ' +
      'thread or on the PR itself — public, and the board has no way to undo it',
    asks: {
      question:
        'This action pushes this commit and replies to the comment. ' +
        'Are you sure?',
      note:
        'Anything you write here is posted as the reply, in your own words, ' +
        'with the landed commit under it. Leave it blank to reply with the ' +
        'commit link alone.',
      reply: true,
      del: true,
      accept: true,
      placeholder:
        'Optional. Posted to the thread with the commit linked. ' +
        'Leave empty to push silently.',
      submit: (typed) => (typed ? 'Push and post reply' : 'Push commit'),
    },
    offeredWhen: proposalWaiting,
    forKind: {
      reply: {
        question: 'This posts this reply to the comment. Are you sure?',
        note:
          'The reply is the agent’s, posted as it stands here once you ' +
          'accept. Nothing is pushed.',
        del: false,
        placeholder: '',
        submit: () => 'Post reply',
      },
      ticket: {
        question: 'This files this ticket and posts this reply. Are you sure?',
        note:
          'The ticket and the reply are the agent’s, filed and posted as ' +
          'they stand here once you accept, with the ticket’s link under ' +
          'the reply. Nothing is pushed.',
        del: false,
        placeholder: '',
        submit: () => 'File ticket and post reply',
      },
    },
    inPhase: {
      'push failed': {
        label: 'Push it',
        dialog: {
          submit: (typed) =>
            typed ? 'Push again and post reply' : 'Push again',
        },
      },
      'filing failed': { label: 'File it again' },
      'reply failed': {
        label: 'Retry the reply',
        dialog: {
          submit: (typed) =>
            typed ? 'Post the reply' : 'Post the commit link',
        },
      },
      removed: { dialog: { reply: false } },
    },
    request: (gathered) => ({
      verb: 'approve',
      body: {
        ...closing(gathered),
        resolve: Boolean(gathered.resolve),
        ...(gathered.message ? { message: gathered.message } : {}),
        ...(gathered.ticket ? { ticket: gathered.ticket } : {}),
      },
    }),
    doing: 'accepting',
    square: 'done',
  },
  rework: {
    key: 'w',
    label: 'Send back for rework',
    weight: 'secondary',
    title:
      'queues the agent again on this comment, carrying your note and the ' +
      'lines you pointed at, starting from the commit it already wrote — ' +
      'nothing reaches the PR branch',
    asks: 'rework',
    inPhase: { declined: { label: 'Disagree — try a fix anyway' } },
    request: ({ brief }) => ({ verb: 'rework', body: { ...brief } }),
    doing: 'sending it back',
    square: 'rework',
    toast: ({ brief }) => reworkToast(brief?.pointed.length ?? 0),
  },
  'start-session': {
    key: 'o',
    label: 'Steer it yourself',
    weight: 'ghost',
    title:
      'opens an agent session in the Terminal tab for you to steer, in a ' +
      'worktree of its own — nothing reaches the PR branch until you approve ' +
      'what it writes',
    asks: {
      question:
        'What should the agent do differently in the session you steer?',
      note:
        'Your notes go to the agent session in the thread’s own ' +
        'worktree, and reach nothing on GitHub. Leave it blank to start the ' +
        'session with no steer.',
      reply: true,
      submit: () => 'start the session',
    },
    request: ({ body, brief }) => ({
      verb: 'start-session',
      body: brief
        ? { steer: brief.note, pointed: brief.pointed, include: brief.include }
        : body
          ? { steer: body }
          : {},
    }),
    doing: 'opening a fix session',
    square: 'rework',
    opensTerminal: true,
  },
  fix: {
    key: 'i',
    label: 'Write a fix',
    weight: 'primary',
    title:
      'puts an agent on this comment to write a fix in its own worktree, ' +
      'for you to accept or turn down — nothing reaches the PR branch yet',
    asks: null,
    offeredWhen: (conversation) =>
      newestOf(conversation, RUN_KINDS) === undefined,
    doing: 'writing a fix',
    square: 'rework',
  },
  retry: {
    key: 't',
    label: 'Try again',
    weight: 'primary',
    title:
      'runs the agent on this comment again with a fresh attempt budget — ' +
      'nothing reaches the PR branch',
    asks: null,
    doing: 'retrying',
    square: 'rework',
  },
  resolve: {
    key: 's',
    label: 'Resolve on GitHub',
    weight: 'ghost',
    title:
      'closes this comment on the board, drops the agent’s worktree and ' +
      'posts any reply you write — tick the box in the dialog to mark the ' +
      'thread resolved on GitHub too',
    asks: {
      question: 'Resolve this comment on GitHub?',
      note:
        'Anything you write here is posted to GitHub as your reply, in your ' +
        'own words, and then the thread is marked resolved there if the box ' +
        'is ticked. The card moves to Done and the agent’s worktree is dropped.',
      reply: true,
      del: true,
      resolves: true,
      submit: (typed, resolving) =>
        resolving
          ? typed
            ? 'Post reply and resolve on the board and GitHub'
            : 'Resolve on GitHub'
          : typed
            ? 'Post reply and resolve on the board'
            : 'Resolve, posting nothing to GitHub',
    },
    inPhase: {
      declined: { label: 'Agreed, resolve the comment', weight: 'secondary' },
      removed: {
        dialog: {
          reply: false,
          resolves: false,
          submit: () => 'Resolve, posting nothing to GitHub',
        },
      },
    },
    reviewer: {
      title:
        'marks this thread resolved on GitHub and moves the card to Done; ' +
        'anything you write is posted as the reply first, and with nothing ' +
        'written the board puts a thumbs-up on the newest reply instead',
      asks: {
        question: 'Resolve this conversation on GitHub?',
        note:
          'Leave it empty and the board puts 👍 on the newest reply instead, ' +
          'unless you untick it. ' +
          'Either way the thread is marked resolved on GitHub and moves to ' +
          'Done. Reopen is one click from there.',
        reply: true,
        thumbsUp: true,
        submit: (typed, _resolving, thumbing) =>
          typed
            ? 'Reply and resolve'
            : thumbing
              ? 'Resolve and put 👍 on the newest reply'
              : 'Resolve',
      },
      inPhase: {
        answered: { label: 'Resolve', weight: 'primary' },
        waiting: { label: 'Resolve' },
        deferred: { label: 'Resolve' },
      },
    },
    request: (gathered) => ({
      verb: 'resolve',
      body: {
        ...closing(gathered),
        resolve: gathered.resolve !== false && !gathered.delete,
        ...(gathered.thumbsUp === false ? { thumbs_up: false } : {}),
      },
    }),
    doing: 'resolving',
    square: 'done',
  },
  'resolve-here': {
    key: 'v',
    label: 'Resolve',
    weight: 'secondary',
    title:
      'closes this comment on the board and drops the agent’s worktree — the ' +
      'thread itself stays open on GitHub',
    asks: {
      question: 'Resolve this comment?',
      note:
        'Anything you write here is posted to GitHub as your reply, in your ' +
        'own words. Leave it empty and nothing is posted: the card moves to ' +
        'Done and the agent’s worktree is dropped. The thread stays open on ' +
        'GitHub either way.',
      reply: true,
      del: true,
      submit: (typed) =>
        typed ? 'Post reply and resolve' : 'Resolve, posting nothing to GitHub',
    },
    reviewer: {
      title:
        'posts your reply to GitHub and closes this mention on the board — ' +
        'nothing is resolved on GitHub',
      asks: {
        question: 'Reply to this mention?',
        note:
          'Your words are posted to GitHub as your reply. The mention moves ' +
          'to Done on the board; nothing is resolved on GitHub.',
        reply: true,
        requiresReply: true,
        submit: () => 'Reply and resolve',
      },
      inPhase: {
        answered: { label: 'Reply and resolve', weight: 'primary' },
        waiting: { label: 'Reply and resolve' },
        'assumed-done': { label: 'Reply and resolve' },
        'not-mine': { label: 'Reply and resolve' },
        deferred: { label: 'Reply and resolve' },
      },
    },
    request: (gathered) => ({ verb: 'resolve', body: closing(gathered) }),
    doing: 'resolving',
    square: 'done',
  },
  'resolve-on-board': {
    key: 'h',
    label: 'Resolve on board',
    weight: 'secondary',
    title:
      'moves this mention to Done on the board with nothing posted to GitHub — ' +
      'no reply, no 👍, nothing resolved there',
    asks: null,
    request: () => ({
      verb: 'resolve',
      body: { delete_comment: false, thumbs_up: false },
    }),
    doing: 'resolving on the board',
    square: 'done',
  },
  reject: {
    key: 'R',
    label: 'Reject',
    weight: 'destructive',
    title:
      'turns this fix down and drops its worktree — the proposed diff goes with ' +
      'it, so bringing the conversation back re-runs the agent from scratch',
    asks: {
      question:
        'This action drops the fix and replies to the comment. ' +
        'Are you sure?',
      note: 'Anything you write here is posted as the reply, in your own words.',
      reply: true,
      del: true,
      submit: (typed) => (typed ? 'reply and reject' : 'reject'),
    },
    inPhase: {
      'reply failed': {
        dialog: {
          question:
            'The fix is already pushed and stays on the PR branch on GitHub. ' +
            'Reject closes this comment on the board and reverts nothing. ' +
            'Are you sure?',
        },
      },
      'push failed': {
        dialog: {
          question:
            'The fix stays committed on the PR branch on this machine. Reject ' +
            'closes this comment on the board and does not undo that commit. ' +
            'Are you sure?',
        },
      },
    },
    request: (gathered) => ({ verb: 'reject', body: closing(gathered) }),
    doing: 'rejecting',
    square: 'waiting',
  },
  defer: {
    key: 'f',
    label: 'Defer',
    weight: 'ghost',
    title:
      'parks this comment with nothing posted to GitHub until you bring it back ' +
      'or the condition you chose is met; a run still going is stopped',
    asks: {
      question: 'When should this come back to you?',
      note:
        'Nothing is posted on GitHub. The card waits on the ' +
        'board until the condition you pick is met.',
      reply: false,
      wake: true,
      submit: () => 'defer it',
    },
    reviewer: {
      title:
        'parks this card with nothing posted to GitHub until the condition you ' +
        'choose is met — the next push, this PR’s CI, another PR closing, or you',
      inPhase: {
        answered: { label: 'Defer until next push' },
        waiting: { label: 'Defer until next push' },
      },
    },
    request: ({ modifier }) => ({
      verb: 'defer',
      body: { until: modifier ?? 'manual' },
    }),
    doing: 'deferring',
    square: 'waiting',
  },
  confirm: {
    key: 'g',
    label: 'Confirm',
    weight: 'primary',
    title:
      'moves this card to Done on the board — nothing is resolved, posted or ' +
      'reacted to on GitHub, and a new comment brings it back',
    asks: null,
    doing: 'confirming',
    square: 'done',
  },
  place: {
    key: 'm',
    label: 'Not confirm',
    weight: 'secondary',
    title:
      'asks where this card stands instead, apart from Done — nothing is ' +
      'posted to GitHub',
    asks: placing([
      { to: 'queued', label: 'Needs a fix' },
      { to: 'ready', label: 'Needs a reply from me' },
      { to: 'waiting', label: 'Their move' },
      { to: LATER, label: 'Later…' },
    ]),
    reviewer: {
      asks: placing([
        { to: 'ready', label: 'My move' },
        { to: 'waiting', label: 'Their move' },
        { to: 'not-mine', label: 'Not my conversation' },
        { to: LATER, label: 'Later…' },
      ]),
      inPhase: { 'not-mine': { label: 'Move…', weight: 'primary' } },
    },
    request: ({ modifier }) => ({ verb: 'place', body: { to: modifier } }),
    doing: 'moving it',
    square: 'ready',
  },
  unpark: {
    key: 'u',
    label: 'Bring back to Ready',
    weight: 'secondary',
    title:
      'brings this conversation back; from rejected or landed it also re-runs ' +
      'the agent, because the worktree went with it',
    asks: null,
    inPhase: {
      deferred: { label: 'Undefer' },
      rejected: { label: 'Reconsider' },
      resolved: { label: 'Un-resolve' },
      confirmed: { label: 'Bring back' },
      landed: { label: 'Bring back' },
      discarded: { label: 'Bring back' },
    },
    reviewer: {
      title:
        'brings this card back to Answered; from Done it unresolves the thread on ' +
        'GitHub too, which is public',
      inPhase: {
        deferred: { label: 'Undefer' },
        resolved: { label: 'Reopen' },
        confirmed: { label: 'Reopen' },
        rejected: { label: 'Reopen' },
        discarded: { label: 'Bring back' },
      },
    },
    doing: 'bringing it back',
    square: 'ready',
  },
  stop: {
    key: 'x',
    label: 'Stop',
    weight: 'secondary',
    title:
      'halts whatever is in flight on this thread, queued or running — nothing ' +
      'is posted to GitHub, and the thread is yours to decide again',
    asks: {
      question: 'Stop the agent on this comment?',
      note:
        'Whatever is queued or running on this thread is halted. Nothing is ' +
        'posted to GitHub, and the thread is yours to decide again.',
      reply: false,
      submit: () => 'stop it',
    },
    doing: 'stopping',
    square: 'ready',
  },
  'not-fixed': {
    key: 'b',
    label: 'Not fixed',
    weight: 'secondary',
    title:
      'posts your own words to the thread, leaves it open on GitHub and parks ' +
      'the card on the author until they come back to it',
    asks: {
      question: 'Say why it is not fixed?',
      note:
        'Your words are posted to the thread as your reply. Nothing is ' +
        'resolved: the thread stays open and the card parks on the author.',
      reply: true,
      requiresReply: true,
      prefill: 'Not fixed — ',
      submit: () => 'post the reply',
    },
    request: ({ body }) => ({ verb: 'reply', body: { body: body ?? '' } }),
    doing: 'replying that it is not fixed',
    square: 'waiting',
  },
  reply: {
    key: 'c',
    label: 'Reply',
    weight: 'ghost',
    title:
      'opens the composer under the thread; your words post to GitHub and park ' +
      'the card on the author, with nothing resolved',
    asks: 'composer',
    request: ({ body }) => ({ verb: 'reply', body: { body } }),
    doing: 'replying',
    square: null,
  },
  enrol: {
    key: 'e',
    label: 'Add to review',
    weight: 'primary',
    title:
      'puts this draft into the review you send from the head — nothing is ' +
      'posted until you send it, and the line is checked against the diff now',
    asks: null,
    savedFirst: true,
    doing: 'adding it to your review',
    square: 'ready',
  },
  'post-now': {
    key: 'G',
    label: 'Post now',
    weight: 'secondary',
    title:
      'posts this draft to GitHub on its own, as a single review comment, ' +
      'without waiting for the review — public, and the board cannot take it back',
    asks: {
      question: 'Post this comment to GitHub now, on its own?',
      note:
        'It goes out as a single review comment on its line, and the author ' +
        'is told of it alone rather than with your review. The board cannot ' +
        'take it back.',
      reply: false,
      submit: () => 'post it',
    },
    savedFirst: true,
    doing: 'posting it',
    square: 'waiting',
  },
  discard: {
    key: 'd',
    label: 'Discard',
    weight: 'ghost',
    title:
      'throws this draft away with nothing posted; it moves to Done, and ' +
      'Bring back returns it as it was',
    asks: null,
    doing: 'discarding it',
    square: 'done',
  },
  'withdraw-from-review': {
    key: 'l',
    label: 'Leave out of review',
    weight: 'secondary',
    title:
      'takes this draft back out of the review you are about to send, so you ' +
      'can edit it or leave it for later',
    asks: null,
    doing: 'leaving it out of your review',
    square: 'ready',
  },
} satisfies Record<string, Entry>;

export type Decision = keyof typeof ENTRIES;

const CARRIED: Record<Decision | 'edit-draft', Carrying> = {
  ...ENTRIES,
  'edit-draft': {
    request: ({ draft }) => ({ verb: 'edit-draft', body: { ...draft } }),
    doing: 'saving the draft',
    square: 'ready',
  },
};

const LANDING_AGAIN: Decision[] = [
  'approve',
  'rework',
  'defer',
  'reject',
  'resolve',
  'start-session',
];
const TRY_AGAIN: Decision[] = [
  'fix',
  'retry',
  'rework',
  'start-session',
  'defer',
  'resolve',
];
const GAVE_UP: Decision[] = [
  'retry',
  'rework',
  'start-session',
  'defer',
  'reject',
  'resolve',
];
const AT_WORK: Decision[] = ['stop', 'defer'];
const DRAFTING: Decision[] = ['enrol', 'post-now', 'discard'];
const ENROLLED: Decision[] = ['withdraw-from-review'];

const AUTHOR_OFFERS: Record<Phase, Decision[]> = {
  proposed: LANDING_AGAIN,
  'push failed': LANDING_AGAIN,
  'reply failed': LANDING_AGAIN,
  'filing failed': LANDING_AGAIN,
  declined: ['rework', 'resolve', 'defer'],
  failed: GAVE_UP,
  stopped: GAVE_UP,
  answered: TRY_AGAIN,
  removed: ['approve', 'resolve'],
  queued: AT_WORK,
  working: AT_WORK,
  session: AT_WORK,
  rework: AT_WORK,
  landing: ['stop'],
  rebasing: [],
  filing: [],
  waiting: ['fix', 'unpark', 'resolve-here', 'resolve', 'defer'],
  'assumed-done': ['confirm', 'place', 'resolve'],
  'not-mine': ['resolve', 'defer'],
  deferred: ['unpark', 'resolve'],
  landed: ['unpark'],
  rejected: ['unpark'],
  resolved: ['unpark'],
  confirmed: ['unpark'],
  discarded: ['unpark'],
  draft: DRAFTING,
  enrolled: ENROLLED,
};

const REVIEWER_OFFERS: Partial<Record<Phase, Decision[]>> = {
  answered: ['resolve', 'not-fixed', 'reply', 'defer'],
  removed: ['resolve'],
  waiting: ['resolve', 'defer', 'reply'],
  'assumed-done': ['confirm', 'place', 'resolve', 'reply'],
  'not-mine': ['place', 'resolve', 'reply'],
  deferred: ['unpark', 'resolve'],
  resolved: ['unpark'],
  confirmed: ['unpark'],
  rejected: ['unpark'],
  discarded: ['unpark'],
  draft: DRAFTING,
  enrolled: ENROLLED,
};

const MENTION_OFFERS: Partial<Record<Phase, Decision[]>> = {
  answered: ['resolve-here', 'resolve-on-board', 'defer'],
  waiting: ['resolve-here', 'resolve-on-board', 'defer'],
  'assumed-done': ['confirm', 'place', 'resolve-here', 'resolve-on-board'],
  'not-mine': ['place', 'resolve-here', 'resolve-on-board'],
  deferred: ['unpark', 'resolve-here'],
};

export function keyOf(decision: Decision): string {
  return ENTRIES[decision].key;
}

export function capOf(key: string): string {
  return key === key.toLowerCase() ? key : `⇧${key}`;
}

function doingOf(doing: string): string {
  return `${doing.charAt(0).toUpperCase()}${doing.slice(1)}…`;
}

function besides(asks: Asks, phase: Phase): Asks {
  if (typeof asks !== 'object' || asks === null || !asks.outcomes) return asks;
  return {
    ...asks,
    outcomes: asks.outcomes.filter((one) => one.to !== phase),
  };
}

function offerOf(
  decision: Decision,
  shade: Shade,
  title: string,
  asks: Asks,
): Offer {
  const entry: Entry = ENTRIES[decision];
  return {
    decision,
    label: shade.label ?? entry.label,
    title,
    weight: shade.weight ?? entry.weight,
    key: entry.key,
    cap: capOf(entry.key),
    doing: doingOf(entry.doing),
    asks,
    savedFirst: Boolean(entry.savedFirst),
  };
}

function kindToAccept(
  proposal: Proposal | undefined,
  phase: Phase,
): ProposalKind | undefined {
  if (proposal?.kind === 'ticket' && phase === 'reply failed') return 'reply';
  return proposal?.kind;
}

function forProposal(
  entry: Entry,
  proposal: Proposal | undefined,
  phase: Phase,
): Partial<DialogSpec> {
  const kind = kindToAccept(proposal, phase);
  const dialog = kind ? entry.forKind?.[kind] : undefined;
  if (!dialog) return {};
  return {
    ...dialog,
    ...(proposal?.reply ? { prefill: proposal.reply } : {}),
    ...(proposal?.ticket && kind === 'ticket'
      ? { ticket: proposal.ticket }
      : {}),
  };
}

function authorOffer(
  decision: Decision,
  conversation: Conversation,
  proposal: Proposal | undefined,
): Offer {
  const entry: Entry = ENTRIES[decision];
  const phase = phaseOf(conversation);
  const { dialog, ...shade } = entry.inPhase?.[phase] ?? {};
  const asks =
    typeof entry.asks === 'object' && entry.asks !== null
      ? {
          ...entry.asks,
          ...forProposal(entry, proposal, phase),
          ...dialog,
          resolving: conversation.author_kind === 'bot',
        }
      : entry.asks;
  return offerOf(decision, shade, entry.title, besides(asks, phase));
}

function reviewerOffer(decision: Decision, phase: Phase): Offer {
  const entry: Entry = ENTRIES[decision];
  return offerOf(
    decision,
    entry.reviewer?.inPhase?.[phase] ?? {},
    entry.reviewer?.title ?? entry.title,
    besides(entry.reviewer?.asks ?? entry.asks, phase),
  );
}

function reviewerPhase(conversation: Conversation): Phase {
  const phase = phaseOf(conversation);
  if (conversation.state === 'ready' && phase !== 'removed') return 'answered';
  return phase;
}

export function offered(
  conversation: Conversation,
  role: Role,
  proposal?: Proposal,
): Offer[] {
  if (busy(conversation)) return [];
  if (role === 'reviewer') {
    const phase = reviewerPhase(conversation);
    const offers =
      (conversation.mention ? MENTION_OFFERS[phase] : undefined) ??
      REVIEWER_OFFERS[phase] ??
      [];
    return offers.map((decision) => reviewerOffer(decision, phase));
  }
  const phase = phaseOf(conversation);
  return AUTHOR_OFFERS[phase]
    .filter((decision) => {
      const entry: Entry = ENTRIES[decision];
      return entry.offeredWhen?.(conversation) ?? true;
    })
    .map((decision) => authorOffer(decision, conversation, proposal));
}

export function carriedOut(
  decision: Decision | 'edit-draft',
  gathered: Gathered,
): Carried {
  const carrying = CARRIED[decision];
  return {
    request: carrying.request?.(gathered) ?? { verb: decision, body: {} },
    toast:
      carrying.square === null
        ? null
        : {
            text: carrying.toast?.(gathered) ?? `Queued: ${carrying.doing}.`,
            square: carrying.square,
          },
    opensTerminal: Boolean(carrying.opensTerminal),
  };
}

export function laterAsks(): DialogSpec {
  return ENTRIES.defer.asks;
}

export function inFlight(kind: string): string {
  const carrying: Carrying | undefined = (
    CARRIED as Record<string, Carrying | undefined>
  )[kind];
  return `${carrying?.doing ?? kind}…`;
}
