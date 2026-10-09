import { capOf, keyOf, type Decision } from 'frontend/data/decisions';
import { capOfControl } from 'frontend/services/pr-controls';

export interface Shortcut {
  keys: string[];
  does: string;
}

export interface ShortcutGroup {
  screen: string;
  shortcuts: Shortcut[];
}

function decides(decision: Decision, does: string): Shortcut {
  return { keys: [capOf(keyOf(decision))], does };
}

export const SHORTCUTS: ShortcutGroup[] = [
  {
    screen: 'Everywhere',
    shortcuts: [
      { keys: ['?'], does: 'Show these shortcuts' },
      { keys: ['/'], does: 'Hold to show the key on each button' },
      { keys: ['1'], does: 'Board tab' },
      { keys: ['2'], does: 'Dashboard tab' },
      { keys: ['3'], does: 'Terminal tab' },
      { keys: ['4'], does: 'Diff tab' },
      { keys: ['o'], does: 'Open the pull request on GitHub' },
      { keys: ['y'], does: "Copy the pull request's address" },
      { keys: ['\\'], does: 'Switch pull request' },
      { keys: ['[', ']'], does: 'Previous or next pull request' },
      { keys: ['Esc'], does: 'Back to the wall' },
    ],
  },
  {
    screen: 'Board',
    shortcuts: [
      { keys: ['j', 'k'], does: 'Walk the rail' },
      { keys: ['n', 'p'], does: 'Next or previous row ready for you' },
      { keys: ['⇧S'], does: 'Send your review' },
      { keys: ['Esc'], does: 'Close the panel' },
      decides('approve', 'Accept'),
      decides('rework', 'Send back for rework'),
      decides('reply', 'Reply'),
      decides('resolve', 'Resolve on GitHub'),
      decides('resolve-here', 'Resolve on the board'),
      decides('reject', 'Reject'),
      decides('defer', 'Defer'),
      decides('unpark', 'Bring back to Ready'),
      decides('confirm', 'Confirm an assumed done card'),
      decides('place', 'Not confirm, or Move…'),
      decides('not-fixed', 'Not fixed'),
      decides('fix', 'Write a fix'),
      decides('retry', 'Try again'),
      decides('stop', 'Stop'),
      decides(
        'start-session',
        'Steer it yourself where the panel offers it, GitHub otherwise',
      ),
      decides('enrol', 'Add to review'),
      decides('post-now', 'Post now'),
      decides('discard', 'Discard'),
      decides('withdraw-from-review', 'Withdraw from review'),
      { keys: ['z'], does: 'Full screen the fix, or close it' },
    ],
  },
  {
    screen: 'Dashboard',
    shortcuts: [
      { keys: [capOfControl('hold')], does: 'Put on hold or resume' },
      { keys: [capOfControl('carry-on')], does: 'Carry on' },
      {
        keys: [capOfControl('start-review')],
        does: 'Start a review agent, where the next move is a review',
      },
      { keys: [capOfControl('close')], does: 'Close the pull request' },
      { keys: [capOfControl('dismiss')], does: 'Dismiss' },
      { keys: [capOfControl('git')], does: 'Git palette' },
      { keys: ['t'], does: 'Terminal' },
      { keys: ['⇧C'], does: 'Agent output' },
      { keys: [capOfControl('release')], does: 'Release a frozen worktree' },
    ],
  },
  {
    screen: 'Terminal',
    shortcuts: [
      {
        keys: ['Ctrl', 'Shift', '←'],
        does: 'Leave the terminal for its session list',
      },
    ],
  },
  {
    screen: 'Wall',
    shortcuts: [
      { keys: ['j', 'k'], does: 'Walk the pull requests' },
      { keys: ['Enter'], does: 'Open the chosen one' },
      { keys: [capOfControl('hold')], does: 'Put on hold or resume' },
      { keys: [capOfControl('dismiss')], does: 'Dismiss' },
      { keys: [capOfControl('release')], does: 'Release a frozen worktree' },
      { keys: ['o'], does: 'Open on GitHub' },
      { keys: ['y'], does: 'Copy its address' },
    ],
  },
  {
    screen: 'Diff',
    shortcuts: [{ keys: ['Esc'], does: 'Drop the selection' }],
  },
];
