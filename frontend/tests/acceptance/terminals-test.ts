import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
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

  test('Close asks once, then ends the session and takes it off the list', async function (assert) {
    onTheHub(WAITING, IDLE);
    await visit('/terminals');

    await click('[data-test-watched-close="shell-1"]');
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

    await click('[data-test-watched-close="shell-1"]');
    await click('[data-test-are-you-sure-cancel]');

    assert.deepEqual(
      board().posted.filter((one) => one.verb === 'close-terminal'),
      [],
    );
    assert.dom('[data-test-watched="shell-1"]').exists();
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
