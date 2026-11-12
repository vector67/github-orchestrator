import type {
  Conversation,
  DashboardSystem,
  PrFacts,
  Proposal,
  ProposalKind,
  SplitPart,
  SplitPartName,
  Ticket,
} from 'frontend/data/api';
import type { Role } from 'frontend/data/groups';
import {
  busy,
  confirmed,
  local,
  newestOf,
  outstanding,
  phaseOf,
  proposalWaiting,
  RUN_KINDS,
  sent,
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
  legend?: string;
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
  steps?: string[];
  worktree?: string;
}

export const LATER = 'later';

export const REJECTED = 'reject';

function droppedOutcomes(proposed: boolean): Outcome[] {
  return [
    {
      to: 'proposal',
      label: 'Back to the last proposal',
      steps: ['asking', proposed ? 'proposed' : 'failed'],
      worktree: proposed
        ? 'worktree: everything since that proposal discarded'
        : 'worktree: no proposal to go back to, so the edits are discarded',
    },
    {
      to: LATER,
      label: 'Defer',
      steps: ['asking', 'deferred', 'asking'],
      worktree: 'edits kept',
    },
    {
      to: REJECTED,
      label: 'Reject the thread',
      steps: ['asking', 'rejected'],
      worktree: 'edits discarded · reply step follows',
    },
  ];
}

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
  part?: SplitPartName;
}

export interface Gathered {
  part?: SplitPartName;
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
  ring?: boolean;
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
  dialogFor?: (conversation: Conversation) => Partial<DialogSpec>;
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
  { value: 'reply', label: 'when someone replies on the thread' },
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

function resolveRequest(gathered: Gathered): Request {
  return {
    verb: 'resolve',
    body: {
      ...closing(gathered),
      resolve: gathered.resolve !== false && !gathered.delete,
      ...(gathered.thumbsUp === false ? { thumbs_up: false } : {}),
    },
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
        ...(gathered.part ? { part: gathered.part } : {}),
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
    ring: true,
  },
  'answer-in-session': {
    key: 'o',
    label: 'Answer in a session',
    weight: 'primary',
    title:
      'opens a session in the Terminal tab that carries on the agent’s own ' +
      'conversation, so you answer it where it stopped — nothing reaches the ' +
      'PR branch until you accept what it proposes',
    asks: null,
    request: () => ({ verb: 'start-session', body: {} }),
    doing: 'opening the session',
    square: 'rework',
    opensTerminal: true,
    ring: true,
  },
  drop: {
    key: 'D',
    label: 'Drop…',
    weight: 'secondary',
    title:
      'gives up the agent’s question: back to the last proposal, deferred ' +
      'with its edits kept, or the thread rejected',
    asks: {
      question: 'Drop this question',
      note:
        'Choose where the thread goes and what happens to its worktree. ' +
        'Nothing is posted to GitHub unless you reject it with a reply.',
      reply: false,
      legend: 'Instead:',
      outcomes: droppedOutcomes(true),
      submit: () => 'Drop it',
    },
    dialogFor: (conversation) => ({
      outcomes: droppedOutcomes(Boolean(conversation.question?.last_proposal)),
    }),
    request: () => ({ verb: 'drop-question', body: {} }),
    doing: 'dropping the question',
    square: 'ready',
  },
  'open-shell': {
    key: 'q',
    label: 'Open a shell',
    weight: 'ghost',
    title:
      'opens a login shell in the Terminal tab, in a worktree of its own for ' +
      'this comment, made first if it has none — no agent runs, and nothing ' +
      'reaches the PR branch',
    asks: null,
    request: () => ({ verb: 'open-shell', body: {} }),
    doing: 'opening a shell',
    square: 'ready',
    opensTerminal: true,
    ring: true,
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
        'moves the card to Done and posts any reply you write — tick the box ' +
        'in the dialog to mark the thread resolved on GitHub too',
      asks: {
        question: 'Resolve this conversation?',
        note:
          'Anything you write is posted to GitHub as your reply. Tick the ' +
          'boxes to mark the thread resolved there too, or, with nothing ' +
          'written, to put 👍 on the newest reply. Either way the card moves ' +
          'to Done. Reopen is one click from there.',
        reply: true,
        resolves: true,
        thumbsUp: true,
        submit: (typed, resolving, thumbing) =>
          resolving
            ? typed
              ? 'Reply and resolve on GitHub'
              : thumbing
                ? 'Resolve on GitHub and put 👍 on the newest reply'
                : 'Resolve on GitHub'
            : typed
              ? 'Post reply and resolve on the board'
              : thumbing
                ? 'Resolve on the board and put 👍 on the newest reply'
                : 'Resolve, posting nothing to GitHub',
      },
      inPhase: {
        answered: { label: 'Resolve', weight: 'primary' },
        waiting: { label: 'Resolve', weight: 'secondary' },
        deferred: { label: 'Resolve', weight: 'secondary' },
      },
    },
    request: resolveRequest,
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
        'assumed-done': { label: 'Reply and resolve', weight: 'ghost' },
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
    reviewer: { inPhase: { 'assumed-done': { weight: 'ghost' } } },
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
        'choose is met — a reply, the next push, this PR’s CI, another PR ' +
        'closing, or you',
      inPhase: {
        answered: { label: 'Defer until …', weight: 'secondary' },
        waiting: { label: 'Defer until …', weight: 'secondary' },
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
  'confirm-resolve': {
    key: 'g',
    label: 'Confirm',
    weight: 'primary',
    title:
      'moves this card to Done and asks whether to resolve the thread on ' +
      "GitHub and put 👍 on the author's message there",
    asks: {
      question: 'Confirm this conversation?',
      note:
        'The card moves to Done. Untick what should not happen on GitHub. ' +
        'Reopen is one click from there.',
      reply: false,
      resolves: true,
      resolving: true,
      thumbsUp: true,
      submit: () => 'Confirm',
    },
    request: resolveRequest,
    doing: 'resolving',
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
      inPhase: {
        'not-mine': { label: 'Move…', weight: 'primary' },
        answered: { label: 'Move…' },
        waiting: { label: 'Move…' },
      },
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
        'brings this card back to Ready for you; from Done it unresolves the thread on ' +
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

export type Slot =
  | 'controls'
  | 'fetch'
  | 'reset'
  | 'read'
  | 'git'
  | 'session'
  | 'ask'
  | 'summary'
  | 'reviewers';

interface PrWrite extends Carrying {
  slot: Slot;
  until?: (facts: PrFacts, system: DashboardSystem | null) => boolean;
  leaves?: boolean;
  unsent?: string;
  ringsOn?: string[];
}

const PR_WRITES = {
  hold: { doing: 'putting it on hold', square: null, slot: 'controls' },
  resume: { doing: 'resuming the agent', square: null, slot: 'controls' },
  'carry-on': { doing: 'carrying on', square: null, slot: 'controls' },
  'start-review': {
    doing: 'starting a review agent',
    square: null,
    slot: 'controls',
  },
  'mark-ready': {
    doing: 'marking it ready for review',
    square: null,
    slot: 'controls',
    ring: true,
    until: (facts) => !facts.draft,
  },
  'take-over': { doing: 'taking it over', square: null, slot: 'controls' },
  'assign-reviewers': {
    doing: 'asking the reviewers',
    square: null,
    slot: 'reviewers',
    until: (facts) => facts.pending_reviewers.length > 0,
  },
  'assign-when-ready': {
    doing: 'keeping the reviewers for when it is ready',
    square: null,
    slot: 'reviewers',
    until: (_facts, system) => Boolean(system?.assign_when_ready),
  },
  'check-for-fixes': {
    doing: 'asking for the checks',
    square: null,
    slot: 'controls',
  },
  dismiss: {
    doing: 'dismissing it',
    square: null,
    slot: 'controls',
    leaves: true,
  },
  close: {
    doing: 'closing it',
    square: null,
    slot: 'controls',
    ring: true,
    until: (facts) => facts.ended,
    leaves: true,
  },
  release: { doing: 'asking for the release', square: null, slot: 'controls' },
  fetch: {
    doing: 'fetching the branch',
    square: null,
    slot: 'fetch',
    ring: true,
    unsent: 'Not fetched',
  },
  'reset-to-origin': {
    doing: 'resetting to origin',
    square: null,
    slot: 'reset',
    ring: true,
    unsent: 'Not reset',
  },
  'queue-reset-to-origin': {
    doing: 'queueing the reset',
    square: null,
    slot: 'reset',
    unsent: 'Not queued',
  },
  'cancel-reset-to-origin': {
    doing: 'taking the reset off',
    square: null,
    slot: 'reset',
    unsent: 'Not taken off',
  },
  'mark-read': {
    doing: 'marking it read',
    square: null,
    slot: 'read',
    unsent: 'Not marked read',
  },
  'mark-unread': {
    doing: 'marking it unread',
    square: null,
    slot: 'read',
    unsent: 'Not marked unread',
  },
  git: {
    doing: 'running git',
    square: null,
    slot: 'git',
    ringsOn: ['f', 'p', 'pra'],
  },
  'open-session': {
    doing: 'opening the session',
    square: null,
    slot: 'session',
    ring: true,
  },
  'ask-the-agent': {
    doing: 'asking the agent',
    square: null,
    slot: 'ask',
    ring: true,
  },
  summarise: { doing: 'summarising', square: null, slot: 'summary' },
  'summarise-with-github-api': {
    doing: 'summarising over the GitHub API',
    square: null,
    slot: 'summary',
  },
} satisfies Record<string, PrWrite>;

export type PrVerb = keyof typeof PR_WRITES;

export type SetupWrite = 'check-account' | 'write-setup' | 'move-aside';

const SLOTS: Slot[] = [
  'controls',
  'fetch',
  'reset',
  'read',
  'git',
  'session',
  'ask',
  'summary',
  'reviewers',
];

function prWriteOf(kind: string): PrWrite | undefined {
  return (PR_WRITES as Record<string, PrWrite | undefined>)[kind];
}

export function slotOf(kind: string): Slot | undefined {
  return prWriteOf(kind)?.slot;
}

export function leavesThePage(verb: PrVerb): boolean {
  return Boolean(prWriteOf(verb)?.leaves);
}

export function settledBy(
  kind: string,
  facts: PrFacts | null,
  system: DashboardSystem | null,
  answered: boolean,
): boolean {
  const until = prWriteOf(kind)?.until;
  if (!until) return answered;
  return facts !== null && until(facts, system);
}

export interface Pressed {
  pressed: string | null;
  doing: string | null;
  pending: string | null;
  ring: boolean;
  refused: string | null;
  code: string | null;
}

export interface Pressing extends Pressed {
  pressed: PrVerb | null;
  on: string | null;
}

export type Pressings = Record<Slot, Pressing>;

interface Written {
  kind?: string;
  state?: string;
  reason?: string | null;
  reason_code?: string | null;
  body?: string | null;
}

function refusalOf(kind: string, reason: string | null): string | null {
  const unsent = prWriteOf(kind)?.unsent;
  return unsent ? `${unsent}: ${reason}` : reason;
}

function ringsFor(kind: string, on: string | null): boolean {
  if (carryingOf(kind)?.ring) return true;
  return on !== null && Boolean(prWriteOf(kind)?.ringsOn?.includes(on));
}

export function pressedBy(write: Written | null | undefined): Pressed {
  const kind = write?.kind ?? '';
  const pressed = write?.state === 'sent' ? kind : null;
  const refused = write?.state === 'refused' && !prWriteOf(kind)?.leaves;
  return {
    pressed,
    doing: pressed && doingOf(carryingOf(pressed)?.doing ?? pressed),
    pending: pressed && inFlight(pressed),
    ring: pressed !== null && ringsFor(pressed, write?.body ?? null),
    refused: refused ? refusalOf(kind, write.reason ?? null) : null,
    code: refused ? (write.reason_code ?? null) : null,
  };
}

function pressingIn(writes: Written[], slot: Slot): Pressing {
  const write = writes.findLast(
    (one) => local(one) && slotOf(one.kind ?? '') === slot,
  );
  const shown = pressedBy(write);
  return {
    ...shown,
    pressed: shown.pressed as PrVerb | null,
    on: write?.body ?? null,
  };
}

export function pressingOf(writes: Written[]): Pressings {
  return Object.fromEntries(
    SLOTS.map((slot) => [slot, pressingIn(writes, slot)]),
  ) as Pressings;
}

const CARRIED: Record<
  | Decision
  | PrVerb
  | 'edit-draft'
  | 'edit-part'
  | 'create-draft'
  | 'request-change'
  | 'check-session'
  | AnswerKind
  | 'send-review'
  | 'prepare-harvest-extension'
  | SetupWrite,
  Carrying
> = {
  ...ENTRIES,
  ...PR_WRITES,
  'create-draft': {
    doing: 'saving the draft',
    square: null,
  },
  'request-change': {
    doing: 'requesting the change',
    square: null,
  },
  'check-session': {
    doing: 'checking the session',
    square: null,
  },
  answer: {
    request: ({ body }) => ({
      verb: 'answer',
      body: { text: body ?? '', visible: false },
    }),
    doing: 'answering the agent',
    square: 'rework',
  },
  'answer-watched': {
    request: ({ body }) => ({
      verb: 'answer',
      body: { text: body ?? '', visible: true },
    }),
    doing: 'opening the session with your answer',
    square: null,
    opensTerminal: true,
    ring: true,
  },
  'edit-draft': {
    request: ({ draft }) => ({ verb: 'edit-draft', body: { ...draft } }),
    doing: 'saving',
    square: null,
  },
  'edit-part': {
    request: ({ part, body, ticket }) => ({
      verb: 'edit-part',
      body: part === 'ticket' ? { part, ticket } : { part, reply: body ?? '' },
    }),
    doing: 'saving',
    square: null,
  },
  'send-review': {
    doing: 'sending the review',
    square: null,
    ring: true,
  },
  'prepare-harvest-extension': {
    doing: 'setting up the extension',
    square: null,
    ring: true,
  },
  'check-account': {
    doing: 'checking the account',
    square: null,
    ring: true,
  },
  'write-setup': {
    doing: 'checking each repo and clone with GitHub',
    square: null,
    ring: true,
  },
  'move-aside': {
    doing: 'moving it aside',
    square: null,
    ring: true,
  },
};

interface Answered extends Written {
  answer?: string;
}

export function opensTerminal(kind: string): boolean {
  return Boolean(carryingOf(kind)?.opensTerminal);
}

export function openingOf(writes: Answered[]): Pressed {
  return pressedBy(
    writes.findLast((one) => local(one) && one.answer !== undefined),
  );
}

export interface Writing {
  outgoing: boolean;
  sending: string | null;
  pending: string | null;
  ring: boolean;
  refused: string | null;
  retype: boolean;
}

const SENDING_REVIEW: Written = { kind: 'send-review', state: 'sent' };

function carryingOf(kind: string): Carrying | undefined {
  return (CARRIED as Record<string, Carrying | undefined>)[kind];
}

export function writtenOn(
  conversation: Conversation,
  reviewSending: boolean,
): Writing {
  const going = outstanding(conversation);
  const write = conversation.operations.findLast(local);
  const outgoing = conversation.state === 'enrolled' && reviewSending;
  const shown = pressedBy(
    going && sent(going) ? going : outgoing ? SENDING_REVIEW : null,
  );
  return {
    outgoing,
    sending: shown.pressed,
    pending: shown.pending,
    ring: shown.ring,
    refused: pressedBy(write).refused,
    retype: write?.kind === 'edit-draft',
  };
}

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
  'open-shell',
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
  asking: ['answer-in-session', 'drop'],
  'push failed': LANDING_AGAIN,
  'landing failed': LANDING_AGAIN,
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
  answered: ['resolve', 'not-fixed', 'place', 'reply', 'defer'],
  removed: ['resolve'],
  waiting: ['resolve', 'defer', 'place', 'reply'],
  'assumed-done': ['confirm-resolve', 'place', 'resolve', 'reply'],
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

const REVIEW_MENTION_OFFERS: Partial<Record<Phase, Decision[]>> = {
  ...MENTION_OFFERS,
  'assumed-done': [
    'confirm-resolve',
    'place',
    'resolve-here',
    'resolve-on-board',
  ],
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

const OUTCOME_OF_PHASE: Partial<Record<Phase, string>> = { answered: 'ready' };

function besides(asks: Asks, phase: Phase): Asks {
  if (typeof asks !== 'object' || asks === null || !asks.outcomes) return asks;
  const here = OUTCOME_OF_PHASE[phase] ?? phase;
  return {
    ...asks,
    outcomes: asks.outcomes.filter((one) => one.to !== here),
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

const ON_THE_BOARD_ALONE: Partial<DialogSpec> = {
  note: 'The change was requested on the board alone, so nothing is posted to GitHub.',
  reply: false,
  del: false,
  resolves: false,
  thumbsUp: false,
};

function authorOffer(
  decision: Decision,
  conversation: Conversation,
  proposal: Proposal | undefined,
  unsent: string | null,
): Offer {
  const entry: Entry = ENTRIES[decision];
  const phase = phaseOf(conversation);
  const { dialog, ...shade } = entry.inPhase?.[phase] ?? {};
  const asks =
    typeof entry.asks === 'object' && entry.asks !== null
      ? {
          ...entry.asks,
          ...forProposal(entry, proposal, phase),
          ...(unsent && entry.asks.accept ? { prefill: unsent } : {}),
          ...entry.dialogFor?.(conversation),
          ...dialog,
          ...(conversation.kind === 'request' ? ON_THE_BOARD_ALONE : {}),
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

const NEED_A_LIVE_PR: Decision[] = [
  'fix',
  'retry',
  'rework',
  'start-session',
  'answer-in-session',
  'open-shell',
];

export function offered(
  conversation: Conversation,
  role: Role,
  proposal: Proposal | undefined,
  unsent: string | null,
  ended: boolean,
): Offer[] {
  const offers = offeredOn(confirmed(conversation), role, proposal, unsent);
  return ended
    ? offers.filter((one) => !NEED_A_LIVE_PR.includes(one.decision))
    : offers;
}

function offeredOn(
  conversation: Conversation,
  role: Role,
  proposal: Proposal | undefined,
  unsent: string | null,
): Offer[] {
  if (busy(conversation)) return [];
  if (role === 'reviewer') {
    const phase = reviewerPhase(conversation);
    const mentionOffers =
      conversation.kind === 'review' ? REVIEW_MENTION_OFFERS : MENTION_OFFERS;
    const offers =
      (conversation.mention ? mentionOffers[phase] : undefined) ??
      REVIEWER_OFFERS[phase] ??
      [];
    return offers.map((decision) => reviewerOffer(decision, phase));
  }
  const phase = phaseOf(conversation);
  const split = proposal?.split;
  if (split) return splitOffers(conversation, proposal, split.parts, phase);
  return AUTHOR_OFFERS[phase]
    .filter((decision) => {
      const entry: Entry = ENTRIES[decision];
      return entry.offeredWhen?.(conversation) ?? true;
    })
    .map((decision) => authorOffer(decision, conversation, proposal, unsent));
}

const GONE_ONCE_A_PART_RAN: Decision[] = ['reject', 'rework'];

const ACCEPT_ALL_TITLE =
  'accepts every part not yet accepted; they run one at a time, in order — ' +
  'public, and the board has no way to undo a part once it has run';

const PART_ORDER: SplitPartName[] = ['ticket', 'changes', 'new-pr', 'reply'];

function runsWhenAccepted(part: SplitPartName, opening: boolean): string {
  return {
    ticket: 'the ticket is filed',
    changes: 'the changes are pushed to this PR',
    'new-pr': 'the new PR is opened',
    reply: `the reply is posted naming ${opening ? 'it' : 'the new PR'}`,
  }[part];
}

function acceptAllNote(parts: SplitPart[]): string {
  const proposed = PART_ORDER.filter((name) =>
    parts.some((one) => one.part === name && one.state === 'proposed'),
  );
  const steps = proposed.map((name) =>
    runsWhenAccepted(name, proposed.includes('new-pr')),
  );
  const last = steps.at(-1) ?? '';
  const sentence =
    steps.length > 1
      ? `Each runs in turn: ${steps.slice(0, -1).join(', ')}, and ${last}.`
      : `${last.charAt(0).toUpperCase()}${last.slice(1)}.`;
  return `${sentence} A part that has run cannot be undone.`;
}

function acceptAllAsks(
  conversation: Conversation,
  parts: SplitPart[],
): DialogSpec {
  return {
    question: 'Accept every part not yet accepted?',
    note: acceptAllNote(parts),
    reply: false,
    resolves: conversation.kind === 'review' && !conversation.github_removed,
    resolving: conversation.author_kind === 'bot',
    submit: () => 'Accept all',
  };
}

function splitOffers(
  conversation: Conversation,
  proposal: Proposal,
  parts: SplitPart[],
  phase: Phase,
): Offer[] {
  const ran = parts.some((one) => one.state === 'run');
  const unaccepted =
    DECIDING_PARTS.includes(phase) &&
    parts.some((one) => one.state === 'proposed');
  const acceptAll = unaccepted
    ? [
        offerOf(
          'approve',
          { label: 'Accept all' },
          ACCEPT_ALL_TITLE,
          acceptAllAsks(conversation, parts),
        ),
      ]
    : [];
  return [
    ...acceptAll,
    ...AUTHOR_OFFERS[phase]
      .filter((decision) => decision !== 'approve')
      .filter((decision) => !(ran && GONE_ONCE_A_PART_RAN.includes(decision)))
      .map((decision) => authorOffer(decision, conversation, proposal, null)),
  ];
}

export type AnswerKind = 'answer' | 'answer-watched';

export function carriedOut(
  decision: Decision | AnswerKind | 'edit-draft' | 'edit-part',
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
    opensTerminal: opensTerminal(decision),
  };
}

export type PartAct = 'accept' | 'edit' | 'rework';

export interface PartOffer {
  act: PartAct;
  label: string;
  title: string;
  weight: Weight;
}

const ACCEPT_TITLES: Record<SplitPartName, string> = {
  ticket: 'files this ticket now, through an agent',
  changes:
    'pushes the commit that takes this code out of the PR — public, and ' +
    'the board has no way to undo it',
  'new-pr': 'opens the new PR now, through an agent, once its ticket is filed',
  reply: 'posts this reply once the new PR is open, naming it',
};

const WORDED: SplitPartName[] = ['ticket', 'reply'];

const DECIDING_PARTS: Phase[] = ['proposed', 'landing'];

export function partOffers(
  part: SplitPart,
  running: boolean,
  phase: Phase,
): PartOffer[] {
  if (!DECIDING_PARTS.includes(phase)) return [];
  if (part.state === 'run' || part.state === 'running') return [];
  const offers: PartOffer[] = [];
  if (part.state === 'proposed') {
    offers.push({
      act: 'accept',
      label: 'Accept',
      title: ACCEPT_TITLES[part.part],
      weight: 'primary',
    });
  }
  if (WORDED.includes(part.part)) {
    offers.push({
      act: 'edit',
      label: 'Edit',
      title: 'changes its words and saves them; nothing is accepted',
      weight: 'secondary',
    });
  }
  if (!running) {
    offers.push({
      act: 'rework',
      label: 'Rework',
      title:
        'sends this part back to the agent with your note; the other parts ' +
        'keep what they have',
      weight: 'secondary',
    });
  }
  return offers;
}

export function editAsks(
  part: SplitPartName,
  words: { reply: string | null; ticket: Ticket | null },
): DialogSpec {
  if (part === 'ticket' && words.ticket) {
    return {
      question: 'Edit the ticket',
      note:
        'Saved for when you accept the ticket. Nothing is accepted or ' +
        'filed now.',
      reply: false,
      ticket: words.ticket,
      submit: () => 'Save',
    };
  }
  return {
    question: 'Edit the reply',
    note:
      'Saved for when the reply is posted, with the new PR linked under it. ' +
      'Nothing is accepted or posted now.',
    reply: true,
    prefill: words.reply ?? '',
    placeholder: '',
    submit: () => 'Save',
  };
}

export function laterAsks(): DialogSpec {
  return ENTRIES.defer.asks;
}

export function rejectAsks(): DialogSpec {
  return ENTRIES.reject.asks;
}

export function inFlight(kind: string): string {
  return `${carryingOf(kind)?.doing ?? kind}…`;
}
