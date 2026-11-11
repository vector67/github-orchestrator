import type { Phase } from 'frontend/data/thread';

export interface Cause {
  short: string;
  sentence: string;
}

interface Known {
  seen: RegExp;
  short: string;
  more: string;
}

const KNOWN: Partial<Record<Phase, { known: Known[]; otherwise: string }>> = {
  'push failed': {
    known: [
      {
        seen: /PR branch was rewritten/,
        short:
          'GitHub’s PR branch was rewritten elsewhere and lacks commits this machine holds',
        more: ', so nothing was pushed',
      },
      {
        seen: /fetch first|non-fast-forward|\[rejected\]/,
        short: 'GitHub has newer commits on the PR branch',
        more: ', so it refused the push',
      },
    ],
    otherwise: 'git could not push the fix',
  },
  'landing failed': {
    known: [
      {
        seen: /reconciling the PR worktree with origin/,
        short:
          'The PR worktree could not be reconciled with GitHub’s rewritten branch',
        more: ', so nothing landed',
      },
    ],
    otherwise: 'the accept stopped before anything was pushed',
  },
  'reply failed': {
    known: [
      {
        seen: /Could not resolve to a node/,
        short: 'GitHub could not find this thread',
        more: ' to reply on; it may have been deleted',
      },
    ],
    otherwise: 'GitHub refused the reply',
  },
  'filing failed': {
    known: [],
    otherwise: 'the agent did not file the ticket',
  },
};

export function causeOf(phase: Phase, reason: string): Cause | null {
  const words = KNOWN[phase];
  if (!words) return null;
  const known = words.known.find((one) => one.seen.test(reason));
  if (known) {
    return { short: known.short, sentence: `${known.short}${known.more}.` };
  }
  return { short: words.otherwise, sentence: `${words.otherwise}.` };
}
