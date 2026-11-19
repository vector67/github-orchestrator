import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  triggerEvent,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import { stubGitHub } from 'frontend/tests/helpers/browser';
import type { WatchedSession } from 'frontend/data/api';

const NOW = new Date(2026, 10, 19, 14, 0, 0).getTime();

function groundAt(x: number, y: number): string {
  const under = [...document.querySelectorAll('[data-test-terminals] *')]
    .filter((one) => {
      const box = one.getBoundingClientRect();
      return box.left <= x && x < box.right && box.top <= y && y < box.bottom;
    })
    .at(-1);
  let at: Element | null = under ?? null;
  while (at) {
    const ground = getComputedStyle(at).backgroundColor;
    if (ground !== 'rgba(0, 0, 0, 0)') return ground;
    at = at.parentElement;
  }
  return 'none';
}

function actions(): Element {
  return find('[data-test-watched-actions]')!;
}

function insideTheWindow(box: DOMRect): boolean {
  return (
    box.left >= 0 &&
    box.top >= 0 &&
    box.right <= window.innerWidth &&
    box.bottom <= window.innerHeight
  );
}

function justUnder(box: DOMRect, by: DOMRect): boolean {
  return box.top >= by.bottom && box.top <= by.bottom + 12;
}

function clearOf(box: DOMRect, by: DOMRect): boolean {
  return box.bottom <= by.top || box.top >= by.bottom;
}

function scrolledToTheEnd(box: Element): Promise<void> {
  const landed = new Promise<void>((resolve) =>
    box.addEventListener('scroll', () => resolve(), { once: true }),
  );
  box.scrollTop = box.scrollHeight;
  return landed;
}

function minutesAgo(minutes: number): string {
  return new Date(NOW - minutes * 60_000).toISOString();
}

function watched(over: Partial<WatchedSession> = {}): WatchedSession {
  return {
    repo: 'o/r',
    number: 7,
    board_url: '/pr/o/r/7',
    id: 'shell-1',
    argv: ['/bin/zsh', '-l'],
    worktree: '/Users/me/repositories/o/r',
    branch: 'feature-7',
    thread: null,
    started_at: minutesAgo(5),
    activity: 'idle',
    waiting_since: null,
    ...over,
  };
}

const WAITING = watched({
  number: 8,
  board_url: '/pr/o/r/8',
  id: 'claude-1',
  argv: ['claude', '--', 'why?'],
  started_at: minutesAgo(42),
  activity: 'waiting',
  waiting_since: minutesAgo(3),
});
const WORKING = watched({
  id: 'git-1',
  argv: ['git', 'rebase', '-i', 'HEAD~3'],
  started_at: minutesAgo(1),
  activity: 'working',
});
const IDLE = watched();

module('Acceptance | terminals', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);
  const github = stubGitHub(hooks);

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      (one as HTMLElement).innerText.trim().replace(/\s+/g, ' '),
    );
  }

  function onTheHub(...sessions: WatchedSession[]): void {
    clock().now = NOW;
    board().manager = dashboard();
    board().held = [heldPr(), heldPr({ number: 8 })];
    board().watchedSessions = sessions;
  }

  test('the hub bar leads to the Terminals page between Runs and Setup', async function (assert) {
    onTheHub();
    await visit('/');

    assert.deepEqual(texts('[data-test-nav]'), [
      'Wall',
      'Runs',
      'Terminals',
      'Setup',
    ]);
    await click('[data-test-nav="terminals"]');

    assert.strictEqual(currentURL(), '/terminals');
    assert
      .dom('[data-test-nav="terminals"]')
      .hasAttribute('aria-current', 'page');
  });

  test('each session says what it is doing, its pull request, its program and how long it has been open, in the hub’s order', async function (assert) {
    onTheHub(WAITING, WORKING, IDLE);

    await visit('/terminals');

    assert.deepEqual(
      findAll('[data-test-watched]').map((one) =>
        one.getAttribute('data-test-activity'),
      ),
      ['waiting', 'working', 'idle'],
    );
    assert.deepEqual(texts('[data-test-watched-pr]'), [
      'o/r#8',
      'o/r#7',
      'o/r#7',
    ]);
    assert.deepEqual(texts('[data-test-watched-command]'), [
      'claude -- why?',
      'git rebase -i HEAD~3',
      '/bin/zsh -l',
    ]);
    assert.deepEqual(texts('[data-test-watched-open]'), [
      'open 42m 0s',
      'open 1m 0s',
      'open 5m 0s',
    ]);
    assert.deepEqual(texts('[data-test-watched-activity]'), [
      'waiting for you',
      'working',
      'idle',
    ]);
  });

  test('each session names the branch it started on, and one on no branch names none', async function (assert) {
    onTheHub(
      { ...WAITING, branch: 'fix/the-cache' },
      { ...IDLE, branch: null },
    );

    await visit('/terminals');

    assert
      .dom('[data-test-watched="claude-1"] [data-test-watched-branch]')
      .hasText('fix/the-cache');
    assert
      .dom('[data-test-watched="shell-1"] [data-test-watched-branch]')
      .doesNotExist();
  });

  test('the list follows the sessions as the hub sees them', async function (assert) {
    onTheHub(WORKING);
    await visit('/terminals');

    board().watchedSessions = [{ ...WORKING, activity: 'waiting' }];
    await clock().tick(5000);

    assert
      .dom('[data-test-watched="git-1"]')
      .hasAttribute('data-test-activity', 'waiting');
  });

  test('no session open says so', async function (assert) {
    onTheHub();

    await visit('/terminals');

    assert
      .dom('[data-test-terminals-empty]')
      .hasText('No terminal session is open.');
  });

  test('clicking a session opens its screen beside the list, on its own pull request', async function (assert) {
    onTheHub(WAITING, IDLE);
    board().terminalSessions = [
      { id: WAITING.id, argv: WAITING.argv, worktree: WAITING.worktree },
    ];
    await visit('/terminals');

    await click('[data-test-watched="claude-1"] .sess');
    board().print('claude-1', 'What next?');
    await waitUntil(() =>
      (find('[data-test-screen] .xterm-rows')?.textContent ?? '').includes(
        'What next?',
      ),
    );

    assert
      .dom('[data-test-watched="claude-1"] .sess')
      .hasAttribute('aria-current', 'true');
    assert.true(
      board()
        .socketsOf('claude-1')[0]!
        .url.endsWith('/pr/o/r/8/api/terminal/sessions/claude-1'),
    );
  });

  test('a chosen session’s highlight spans its whole row, out to the far edge past its buttons', async function (assert) {
    onTheHub(WAITING, IDLE);
    document.documentElement.style.setProperty('--selected', 'rgb(1, 2, 3)');
    await visit('/terminals');

    await click('[data-test-watched="claude-1"] .sess');

    const chosen = find(
      '[data-test-watched="claude-1"]',
    )!.getBoundingClientRect();
    const other = find(
      '[data-test-watched="shell-1"]',
    )!.getBoundingClientRect();
    const nearEdge = chosen.right - 3;
    const highlight = groundAt(chosen.left + 20, chosen.top + 3);
    assert.notStrictEqual(
      highlight,
      groundAt(other.left + 20, other.top + 3),
      'the chosen row stands out from the others',
    );
    assert.strictEqual(
      groundAt(nearEdge, chosen.top + 3),
      highlight,
      'at its far edge',
    );
    assert.strictEqual(
      groundAt(nearEdge, chosen.bottom - 2),
      highlight,
      'at its far bottom corner',
    );
    document.documentElement.style.removeProperty('--selected');
  });

  async function act(id: string, action: string): Promise<void> {
    await click(`[data-test-watched="${id}"] [data-test-watched-more]`);
    await click(`[data-test-watched-action="${action}"]`);
  }

  test('Close, from the row’s menu, asks once, then ends the session and takes it off the list', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('shell-1', 'close');
    assert
      .dom('[data-test-are-you-sure-question]')
      .hasText('Close this terminal session?');
    await click('[data-test-are-you-sure-submit]');

    assert.deepEqual(
      board()
        .posted.filter((one) => one.verb === 'close-terminal')
        .map((one) => new URL(one.url, location.origin).pathname),
      ['/pr/o/r/7/api/terminal/sessions/shell-1:close'],
    );
    assert.dom('[data-test-are-you-sure]').doesNotExist();
    assert.deepEqual(
      findAll('[data-test-watched]').map((one) =>
        one.getAttribute('data-test-watched'),
      ),
      ['claude-1'],
    );
  });

  test('cancelling Close leaves the session running', async function (assert) {
    onTheHub(IDLE);
    await visit('/terminals');

    await act('shell-1', 'close');
    await click('[data-test-are-you-sure-cancel]');

    assert.deepEqual(
      board().posted.filter((one) => one.verb === 'close-terminal'),
      [],
    );
    assert.dom('[data-test-watched="shell-1"]').exists();
  });

  test('each row’s arrow opens its actions in order, Close last, in place of a Close button', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await click('[data-test-watched="claude-1"] [data-test-watched-more]');

    assert.deepEqual(texts('[data-test-watched-action]'), [
      'Open pull request',
      'Open diff',
      'Open in Terminal tab',
      'Fullscreen',
      'New shell here',
      'Copy worktree path',
      'Copy branch name',
      'Open conversation',
      'Close',
    ]);
    assert
      .dom('[data-test-watched="claude-1"] [data-test-watched-more]')
      .hasAttribute('aria-expanded', 'true');
    assert.dom('[data-test-watched-close]').doesNotExist();
  });

  test('the actions open over the list by their arrow and move nothing', async function (assert) {
    onTheHub(WAITING, WORKING, IDLE);
    await visit('/terminals');
    const tops = () =>
      JSON.stringify(
        findAll('[data-test-watched]').map(
          (row) => row.getBoundingClientRect().top,
        ),
      );
    const before = tops();
    const arrow = find('[data-test-watched="git-1"] [data-test-watched-more]')!;

    await click(arrow);

    const box = actions().getBoundingClientRect();
    const by = arrow.getBoundingClientRect();
    assert.true(actions().matches(':popover-open'), 'it is in the top layer');
    assert.strictEqual(tops(), before, 'no row moved');
    assert.true(
      justUnder(box, by),
      `it opens just under its arrow (${box.top} under ${by.bottom})`,
    );
    assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
  });

  test('the actions of the last session in a long list stay inside the window', async function (assert) {
    onTheHub(
      ...Array.from({ length: 30 }, (_, at) => watched({ id: `shell-${at}` })),
    );
    await visit('/terminals');
    await scrolledToTheEnd(find('.term-side')!);
    const arrow = find(
      '[data-test-watched="shell-29"] [data-test-watched-more]',
    )!;

    await click(arrow);

    const box = actions().getBoundingClientRect();
    assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
    assert.true(
      clearOf(box, arrow.getBoundingClientRect()),
      'it covers not its own arrow',
    );
  });

  for (const corner of [
    { right: '2px', bottom: '2px' },
    { left: '2px', bottom: '2px' },
    { left: '2px', top: '2px' },
  ]) {
    test(`the actions of an arrow in the window’s corner at ${JSON.stringify(corner)} stay inside the window`, async function (assert) {
      onTheHub(IDLE);
      await visit('/terminals');
      const arrow = find(
        '[data-test-watched="shell-1"] [data-test-watched-more]',
      ) as HTMLElement;
      Object.assign(arrow.style, { position: 'fixed', ...corner });

      await click(arrow);

      const box = actions().getBoundingClientRect();
      assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
      assert.true(
        clearOf(box, arrow.getBoundingClientRect()),
        'it covers not its own arrow',
      );
    });
  }

  test('Escape, a click outside, scrolling the list or resizing the window closes the actions', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');
    const more = '[data-test-watched="shell-1"] [data-test-watched-more]';

    await click(more);
    await triggerEvent(document.activeElement!, 'keydown', { key: 'Escape' });
    assert.dom('[data-test-watched-actions]').doesNotExist('Escape');

    await click(more);
    await triggerEvent('[data-test-terminals-empty], .term-side', 'mousedown');
    assert.dom('[data-test-watched-actions]').doesNotExist('a click outside');

    await click(more);
    await triggerEvent('.term-side', 'scroll');
    assert.dom('[data-test-watched-actions]').doesNotExist('scrolling');

    await click(more);
    await triggerEvent(window, 'resize');
    assert.dom('[data-test-watched-actions]').doesNotExist('resizing');
  });

  test('Open pull request goes to the session’s pull request', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('claude-1', 'open-pr');

    assert.strictEqual(currentURL(), '/pr/o/r/8/conversations');
  });

  test('Open diff goes to the pull request’s Diff tab', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('claude-1', 'open-diff');

    assert.true(
      currentURL().startsWith('/pr/o/r/8/diff'),
      `it is on the diff (${currentURL()})`,
    );
  });

  test('Open in Terminal tab arrives with that session chosen', async function (assert) {
    onTheHub(IDLE, watched({ id: 'git-2', argv: ['git', 'commit'] }));
    board().terminalSessions = [
      { id: 'shell-1', argv: IDLE.argv, worktree: IDLE.worktree },
      { id: 'git-2', argv: ['git', 'commit'], worktree: IDLE.worktree },
    ];
    await visit('/terminals');

    await act('shell-1', 'open-tab');

    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal?session=shell-1');
    assert
      .dom('[data-test-session="shell-1"]')
      .hasAttribute('aria-current', 'true');
  });

  test('Fullscreen shows the session over the whole page until its × closes it', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('shell-1', 'fullscreen');

    assert
      .dom('[data-test-watched="shell-1"] .sess')
      .hasAttribute('aria-current', 'true');
    assert.dom('[data-test-screen]').hasAttribute('data-fullscreen', 'true');
    await click('[data-test-terminal-leave-fullscreen]');
    assert.dom('[data-test-screen]').doesNotHaveAttribute('data-fullscreen');
  });

  test('New shell here opens a shell in the pull request’s worktree for a session no thread opened', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('shell-1', 'new-shell');

    assert.deepEqual(
      board()
        .posted.filter((one) => one.verb === 'open-terminal')
        .map((one) => [new URL(one.url, location.origin).pathname, one.body]),
      [['/pr/o/r/7/api/terminal/sessions', { keys: 'new' }]],
    );
    assert
      .dom('[data-test-toast]')
      .includesText('Opened a shell beside /bin/zsh -l');
  });

  test('New shell here opens a shell in the thread’s own worktree for a session a thread opened', async function (assert) {
    onTheHub({ ...WAITING, thread: 'PRRT_8' }, IDLE);
    board().conversations = [thread({ key: 'PRRT_8', etag: '"PRRT_8-v3"' })];
    await visit('/terminals');

    await act('claude-1', 'new-shell');

    const [asked] = board().posted.filter((one) => one.verb === 'open-shell');
    assert.strictEqual(
      new URL(asked!.url, location.origin).pathname,
      '/pr/o/r/8/api/conversations/PRRT_8/operations:open-shell',
    );
    assert.strictEqual(asked!.ifMatch, '"PRRT_8-v3"');
  });

  test('a refused New shell here says why', async function (assert) {
    onTheHub(IDLE);
    board().refusal = {
      status: 409,
      code: 'manager-down',
      detail: 'the manager is down',
    };
    await visit('/terminals');

    await act('shell-1', 'new-shell');

    assert
      .dom('[data-test-toast]')
      .includesText('No shell opened: The manager is down');
  });

  test('Copy worktree path and Copy branch name put them on the clipboard', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await act('shell-1', 'copy-path');
    await act('shell-1', 'copy-branch');

    assert.deepEqual(github().copied, [
      '/Users/me/repositories/o/r',
      'feature-7',
    ]);
  });

  test('a session on no branch or opened by no thread offers neither', async function (assert) {
    onTheHub(watched({ branch: null, thread: null }));
    await visit('/terminals');

    await click('[data-test-watched="shell-1"] [data-test-watched-more]');

    assert.dom('[data-test-watched-action="copy-branch"]').isDisabled();
    assert.dom('[data-test-watched-action="open-thread"]').isDisabled();
  });

  test('Open conversation goes to the thread that opened the session', async function (assert) {
    onTheHub({ ...WAITING, thread: 'PRRT_8' }, IDLE);
    board().conversations = [thread({ key: 'PRRT_8' })];
    await visit('/terminals');

    await act('claude-1', 'open-thread');

    assert.strictEqual(currentURL(), '/pr/o/r/8/conversations/PRRT_8');
  });
});

module('Acceptance | terminals on the wall', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function chips(number: number): string[] {
    return findAll(
      `[data-test-wall-row="o/r#${number}"] [data-test-state]`,
    ).map((one) => (one as HTMLElement).innerText.trim());
  }

  test('a row whose pull request has terminals waiting says how many', async function (assert) {
    board().held = [
      heldPr({ number: 7, terminals_waiting: 1 }),
      heldPr({ number: 8, terminals_waiting: 2 }),
      heldPr({ number: 9 }),
    ];

    await visit('/');

    assert.true(chips(7).includes('1 terminal waiting'));
    assert.true(chips(8).includes('2 terminals waiting'));
    assert.false(chips(9).some((one) => one.includes('terminal')));
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-state="terminals-waiting"]')
      .hasClass('tone-strong');
  });
});
