import { Refusal } from 'frontend/data/refusal';
import { reportError } from 'frontend/data/report';
import { DOWN } from 'frontend/services/reachability';

export const MOVED = 'precondition-failed';

const SAID: Record<string, string> = {
  [MOVED]:
    'That thread moved before your click reached the board. It has been ' +
    'read again; look at it before you press.',
  'operation-outstanding':
    'Something is already on its way for this thread; wait for the board ' +
    'to take it.',
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
};

export type Tried<T> =
  { done: true; body: T } | { done: false; why: string; code: string | null };

export async function tried<T>(
  where: string,
  asking: Promise<T>,
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
      why: SAID[trouble.code] ?? trouble.detail,
      code: trouble.code,
    };
  }
}
