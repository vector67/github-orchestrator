import { Refusal } from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { DOWN } from 'frontend/services/reachability';

export const MOVED = 'precondition-failed';

export type ThreadNamed = (key: string) => string;

const unnamed: ThreadNamed = (key) => `thread ${key}`;

const SAID: Record<
  string,
  string | ((detail: string | null, named: ThreadNamed) => string)
> = {
  [MOVED]:
    'That thread moved before your click reached the board. It has been ' +
    'read again; look at it before you press.',
  'operation-outstanding':
    'Something is already on its way for this thread; wait for the board ' +
    'to take it.',
  'landing-stalled':
    'This fix was accepted, but its landing stopped part way; approve it ' +
    'again to finish landing it.',
  'agents-disabled':
    'Agents are switched off on this board, so there is no agent to send ' +
    'this to.',
  'anchor-not-in-diff':
    "That line is not in the pull request's diff, and GitHub takes no " +
    'comment outside it. Select lines inside one hunk of the diff and save ' +
    'the draft.',
  'already-enrolled':
    'That draft is in your review already. Leave it out of the review ' +
    'first.',
  'review-in-flight':
    'A review is already on its way to GitHub; wait for it to land.',
  'empty-body': 'GitHub takes no comment or change request without a summary.',
  'manager-down': "The manager is down, so your action can't be recorded.",
  'no-worktree':
    'This pull request has no worktree yet, since its manager has not started.',
  'worktree-frozen': "The worktree holds another pull request's branch.",
  'agent-running': 'An agent is already running for this pull request.',
  'summary-running': 'Another summary is running; wait for it to finish.',
  'repo-not-watched':
    'This repository is not watched, so the board has no clone to summarise it in.',
  'fix-awaits-push': (thread, named) =>
    `the fix for ${named(thread ?? '')} is picked onto the branch and not ` +
    'pushed yet; stop its landing or send it back for rework, then reset',
  'branch-unknown':
    "GitHub has not named the pull request's branch, so the worktree was " +
    'left as it is',
  'fetch-failed': (detail) => `git could not fetch origin: ${detail ?? ''}`,
  'head-unreadable':
    "the worktree's HEAD will not read, so it was left as it is",
  'reset-interrupted':
    'the reset was under way when the manager stopped, so how it ended is ' +
    'not known',
  'worktree-missing':
    "no worktree holds the pull request's branch, so there was nothing to " +
    'reset',
  'no-origin-branch': 'origin holds no branch for the worktree to reset to',
  'on-another-branch': (branch) =>
    `the worktree holds ${branch || 'no branch'}, not the pull request's ` +
    'branch, so it was left as it is',
  'uncommitted-changes':
    'the worktree has uncommitted changes, so it was left as it is',
  'worktree-moved': (head) =>
    `the worktree moved to ${(head ?? '').slice(0, 12)} since the page ` +
    'showed it, so it was left as it is',
  'not-diverged':
    "origin's branch has nothing the worktree lacks, so its own commits " +
    'are only unpushed and it was left as it is',
  'origin-adds-unknown':
    "git could not say what origin's branch adds, so the worktree was left " +
    'as it is',
  'untracked-in-the-way': (paths) =>
    `origin's branch adds ${paths ?? ''}, which the worktree holds ` +
    'untracked or ignored, so it was left as it is',
  'reset-refused': (detail) =>
    `git would not reset the worktree: ${detail ?? ''}`,
};

export function saidOf(
  code: string,
  detail: string | null,
  named: ThreadNamed = unnamed,
): string | null {
  const said = SAID[code];
  if (said === undefined) return detail;
  return typeof said === 'function' ? said(detail, named) : said;
}

export type Tried<T> =
  { done: true; body: T } | { done: false; why: string; code: string | null };

export async function tried<T>(
  where: string,
  asking: Promise<T>,
  named: ThreadNamed = unnamed,
): Promise<Tried<T>> {
  try {
    return { done: true, body: await asking };
  } catch (trouble) {
    void reportError(where, trouble);
    if (!(trouble instanceof Refusal)) {
      return { done: false, why: DOWN, code: null };
    }
    return {
      done: false,
      why: saidOf(trouble.code, trouble.detail, named) ?? trouble.detail,
      code: trouble.code,
    };
  }
}
