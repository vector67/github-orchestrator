import type { ReasonCode, ResetRefusalCode } from 'frontend/data/api';
import { Refusal, type Refused } from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { local } from 'frontend/data/thread';
import { DOWN } from 'frontend/services/reachability';

export const MOVED = 'precondition-failed';

export type ThreadNamed = (key: string) => string;

const unnamed: ThreadNamed = (key) => `thread ${key}`;

type Code = Refused['code'] | ResetRefusalCode;

type Said = string | ((detail: string | null, named: ThreadNamed) => string);

function beside(said: string): Said {
  return (detail) => (detail ? `${said}: ${detail}` : said);
}

const SAID: Record<Code, Said> = {
  'not-found':
    'The board no longer holds that; it may have closed. Reload the page ' +
    'to see what it holds.',
  'operation-outstanding':
    'Something is already on its way for this thread; wait for the board ' +
    'to take it.',
  'landing-stalled':
    'This fix was accepted, but its landing stopped part way; approve it ' +
    'again to finish landing it.',
  'nothing-in-flight': 'Nothing is under way on this thread to stop.',
  'work-in-flight': 'A fix is still under way on this thread; stop it first.',
  'no-proposal': 'This thread holds no proposal to act on.',
  'proposal-exists':
    'This thread holds a proposal already; accept it, send it back or ' +
    'reject it.',
  'nothing-committed':
    'The agent committed nothing, so there is nothing to land.',
  'already-closed': 'This thread is closed already.',
  parked: 'This thread is set aside; bring it back before you act on it.',
  'not-parked':
    'This thread is not set aside, so there is nothing to bring back.',
  'still-a-draft':
    'This thread is a draft that is not on GitHub yet; post it first.',
  'not-a-draft': 'This thread is on GitHub already, so it is no draft to edit.',
  'already-enrolled':
    'That draft is in your review already. Leave it out of the review ' +
    'first.',
  'confirm-again':
    'Something changed on this fix since you looked. Read it again, then ' +
    'press once more to go ahead.',
  'anchor-not-in-diff':
    "That line is not in the pull request's diff, and GitHub takes no " +
    'comment outside it. Select lines inside one hunk of the diff and save ' +
    'the draft.',
  'empty-brief': 'Say what to change first: write a note or point at a line.',
  'malformed-request': beside('The board could not take that request'),
  'empty-body': 'GitHub takes no comment or change request without a summary.',
  'body-too-long':
    'That is longer than the board takes; shorten it and send it again.',
  'comment-gone':
    'The comment was deleted from GitHub, so no reply was posted.',
  'not-deletable':
    'That comment is not yours to delete from here; leave it on GitHub and ' +
    'press again.',
  'bad-wake-condition': 'Nothing wakes a thread on that; pick another time.',
  [MOVED]:
    'That thread moved before your click reached the board. It has been ' +
    'read again; look at it before you press.',
  'unreadable-record':
    "This thread's record will not read; the server's log says why.",
  'range-inverted': 'Those lines end before they start.',
  'range-too-wide':
    'That is more lines than the board reads at once; ask for fewer.',
  'not-text': 'That file is not text, so it cannot be shown as lines.',
  'no-such-commit':
    'The worktree holds no such commit; it may not have fetched it yet.',
  'no-such-path': 'That commit holds no file at that path.',
  'review-in-flight':
    'A review is already on its way to GitHub; wait for it to land.',
  'nothing-enrolled': 'That draft is not in your review.',
  'git-failed': beside('git failed'),
  'github-rejected': beside('GitHub refused it'),
  'agents-disabled':
    'Agents are switched off on this board, so there is no agent to send ' +
    'this to.',
  'internal-refusal':
    "The board refused that for a reason of its own; the server's log says why.",
  'foreign-origin':
    "The board takes writes only from its own page; open it from the board's " +
    'address.',
  'watcher-starting':
    'The watcher has not finished its first look yet; try again in a moment.',
  'watcher-failing': beside('The watcher is failing'),
  'not-watching': beside('The board watches nothing until its config is fixed'),
  'waiting-to-migrate':
    'Terminal sessions are open in folders the board needs to move; close ' +
    'them so it can carry on.',
  'not-frozen':
    "That pull request's manager is not held on the wrong branch, so there " +
    'is nothing to let go of.',
  'terminal-refused': beside('the system would not start it'),
  'manager-down': "The manager is down, so your action can't be recorded.",
  'no-worktree':
    'This pull request has no worktree yet, since its manager has not started.',
  'worktree-frozen': "The worktree holds another pull request's branch.",
  'agent-running': 'An agent is already running for this pull request.',
  'no-gh-token':
    'gh holds no token for that login; run gh auth login in a terminal, ' +
    'then try again.',
  'repo-not-visible':
    'That login cannot see that repository, or it does not exist.',
  'setup-refused': 'The setup was not saved; fix what each field says.',
  'not-broken': 'The config reads, so it stays where it is.',
  'summary-running': 'Another summary is running; wait for it to finish.',
  'repo-not-watched':
    'This repository is not watched, so the board has no clone to summarise it in.',
  'harvest-extension-missing':
    'Chrome has no Harvest Time Tracker to copy. Add it to Chrome, then try ' +
    'again.',
  'agent-working':
    'an agent is working in the worktree, so it was left as it is',
  'no-agent-working':
    'no agent is working in the worktree, so there is no run to wait for; ' +
    'reset it now instead',
  'uncommitted-changes':
    'the worktree has uncommitted changes, so it was left as it is',
  'not-diverged':
    "origin's branch has nothing the worktree lacks, so its own commits " +
    'are only unpushed and it was left as it is',
  'fix-awaits-push': (thread, named) =>
    `the fix for ${named(thread ?? '')} is picked onto the branch and not ` +
    'pushed yet; stop its landing or send it back for rework, then reset',
  'branch-unknown':
    "GitHub has not named the pull request's branch, so the worktree was " +
    'left as it is',
  'fetch-failed': (detail) => `git could not fetch origin: ${detail ?? ''}`,
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
  'head-unreadable':
    "the worktree's HEAD will not read, so it was left as it is",
  'worktree-moved': (head) =>
    `the worktree moved to ${(head ?? '').slice(0, 12)} since the page ` +
    'showed it, so it was left as it is',
  'origin-adds-unknown':
    "git could not say what origin's branch adds, so the worktree was left " +
    'as it is',
  'untracked-in-the-way': (paths) =>
    `origin's branch adds ${paths ?? ''}, which the worktree holds ` +
    'untracked or ignored, so it was left as it is',
  'reset-refused': (detail) =>
    `git would not reset the worktree: ${detail ?? ''}`,
  'server-error':
    "The board failed in a way it did not expect; the server's log has the " +
    'traceback.',
  unexpected:
    "The board answered in a way the page does not understand; the server's " +
    'log may say why.',
};

const REASONS: Record<ReasonCode, Said> = {
  withdrawn: 'it was stopped before it finished',
  'agent-declined': beside('the agent made no change'),
  'max-attempts': beside('the agent gave up'),
  'agent-unavailable': beside('no agent could start'),
  conflict: beside('the fix would not apply cleanly'),
  'nothing-committed': 'the agent committed nothing',
  'push-failed': beside('git could not push the fix'),
  'reply-failed': beside('GitHub refused the reply'),
  'file-failed': beside('the ticket was not filed'),
  'open-failed': beside('the new pull request was not opened'),
  'comment-gone': 'the comment was deleted from GitHub',
  'github-rejected': beside('GitHub refused it'),
  'git-failed': beside('git failed'),
  'anchor-not-in-diff': "that line is not in the pull request's diff",
  superseded: 'a newer request took its place',
  'worktree-missing': "no worktree holds the pull request's branch",
  'not-taken': 'the board did not take it, so it never ran',
};

export function reasonOf(one: {
  reason?: string | null;
  reason_code?: string | null;
}): string {
  const reason = one.reason ?? '';
  if (local(one) || !one.reason_code) return reason;
  const said = REASONS[one.reason_code as ReasonCode];
  return typeof said === 'function' ? said(reason, unnamed) : said;
}

export function saidOf(
  code: Code,
  detail: string | null,
  named: ThreadNamed = unnamed,
): string {
  const said = SAID[code];
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
      why: saidOf(trouble.code, trouble.detail, named),
      code: trouble.code,
    };
  }
}
