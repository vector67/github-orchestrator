import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  fillIn,
  find,
  findAll,
  triggerEvent,
  visit,
  waitFor,
  waitUntil,
} from '@ember/test-helpers';
import {
  dashboard,
  factsFor,
  heldPr,
  proposal,
  setupFakeBoard,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const SHELL = {
  id: 'shell-1',
  argv: ['/bin/zsh', '-l'],
  worktree: '/Users/me/repositories/o/r',
};

module('Acceptance | terminal', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(): void {
    board().serves = 'hub';
    board().manager = dashboard();
    board().held = [heldPr()];
  }

  async function press(...keys: string[]): Promise<void> {
    for (const key of keys) await triggerEvent(document, 'keydown', { key });
  }

  function screen(): string {
    return find('[data-test-screen] .xterm-rows')?.textContent ?? '';
  }

  async function shows(text: string): Promise<void> {
    await waitUntil(() => screen().includes(text), { timeout: 3000 });
  }

  function opened(): unknown[] {
    return board()
      .posted.filter((one) => one.verb === 'open-terminal')
      .map((one) => one.body);
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      (one as HTMLElement).innerText.trim().replace(/\s+/g, ' '),
    );
  }

  async function typeInTheTerminal(key: string, keyCode: number) {
    await triggerEvent('[data-test-screen] textarea', 'keydown', {
      key,
      keyCode,
    });
  }

  test('the Terminal tab lists the sessions and shows the chosen one on its screen', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];

    await visit('/pr/o/r/7/terminal');
    board().print('shell-1', 'PROJ-7-fix-the-widget $ ');

    assert
      .dom('[data-test-tab="terminal"]')
      .hasAttribute('aria-current', 'page');
    assert.deepEqual(texts('[data-test-session]'), [
      '/bin/zsh -l ~/repositories/o/r',
    ]);
    assert
      .dom('[data-test-session="shell-1"]')
      .hasAttribute('aria-current', 'true');
    await shows('PROJ-7-fix-the-widget $');
    assert.ok(true, 'the screen shows what the session printed');
  });

  test('the page tells the session its size and sends what you type in the terminal', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    const [socket] = board().socketsOf('shell-1');

    await typeInTheTerminal('l', 76);
    await typeInTheTerminal('s', 83);
    await typeInTheTerminal('Enter', 13);

    assert.strictEqual(socket!.typed, 'ls\r');
    const [size] = socket!.sizes as { columns: number; rows: number }[];
    assert.ok(size!.columns > 0, 'it sent its columns');
    assert.ok(size!.rows > 0, 'it sent its rows');
  });

  test('Esc inside the terminal goes to the shell and leaves you on the tab', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');

    await typeInTheTerminal('Escape', 27);

    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
    assert.strictEqual(board().socketsOf('shell-1')[0]!.typed, '\x1b');
  });

  test('3 opens the Terminal tab and 1 and 2 leave it', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('3');
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
    await press('2');
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
  });

  test('with no session yet the tab says how to start one', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/terminal');

    assert
      .dom('[data-test-terminal-standing]')
      .hasText('No session yet. Start one from the list on the left.');
    assert.deepEqual(texts('[data-test-launch]'), [
      'Shell in the worktree',
      'git add -p',
      'git commit',
      'git rebase -i HEAD~N',
      'rebase-on-main in an agent session, steered by you',
    ]);
  });

  test('Ctrl+Shift+ArrowLeft leaves the terminal for its session list, and the tab and the key help say so', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');

    await triggerEvent('[data-test-screen] textarea', 'keydown', {
      key: 'ArrowLeft',
      keyCode: 37,
      ctrlKey: true,
      shiftKey: true,
    });

    assert.dom('[data-test-session="shell-1"]').isFocused();
    assert.strictEqual(board().socketsOf('shell-1')[0]!.typed, '');
    assert.deepEqual(texts('[data-test-terminal-leave]'), [
      'Ctrl+Shift+← leaves the terminal for this list.',
    ]);

    await press('?');
    const group = '[data-test-key-help] [data-test-key-group="Terminal"]';
    assert.deepEqual(
      findAll(`${group} kbd`).map((one) => one.textContent),
      ['Ctrl', 'Shift', '←'],
    );
    assert
      .dom(`${group} dd`)
      .hasText('Leave the terminal for its session list');
    await press('x');

    await press('1');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('what the terminal shows reaches a screen reader', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');

    const now = performance.now.bind(performance);
    const pastXtermsRenderThrottle = () => now() + 1000;
    performance.now = pastXtermsRenderThrottle;
    try {
      board().print('shell-1', 'read me aloud');

      await waitUntil(
        () =>
          find(
            '[data-test-screen] .xterm-accessibility-tree',
          )?.textContent?.includes('read me aloud'),
        { timeout: 3000 },
      );
    } finally {
      performance.now = now;
    }
    assert.ok(true, 'the accessibility tree carries the output');
  });

  test('a Session open conversation leads to its own session on the Terminal tab', async function (assert) {
    board().conversations = [board().threadIn('session', { key: 'k1' })];
    board().proposals['k1'] = [proposal({ directory: '/wt/thread-k1' })];
    board().terminalSessions = [
      { id: 'claude-k1', argv: ['claude'], worktree: '/wt/thread-k1' },
      SHELL,
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-go-to-session]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
    assert
      .dom('[data-test-session="claude-k1"]')
      .hasAttribute('aria-current', 'true');
  });

  test('on a board’s own port a Terminal tab whose board stops answering says so', async function (assert) {
    await visit('/pr/o/r/7/terminal');

    board().down = true;
    await clock().tick(5000);
    await clock().tick(5000);

    assert
      .dom('[data-test-banner]')
      .hasText('the board server is not answering');
  });

  test('on the hub a Terminal tab whose hub stops answering says so', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/terminal');

    board().down = true;
    await clock().tick(5000);
    await clock().tick(5000);

    assert
      .dom('[data-test-banner]')
      .hasText('the board server is not answering');
  });

  test('a launcher starts its command and the tab shows it at once', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/terminal');

    await click('[data-test-launch="new"]');

    assert.deepEqual(opened(), [{ keys: 'new' }]);
    assert
      .dom('[data-test-session="made-1"]')
      .hasAttribute('aria-current', 'true');
    assert.strictEqual(board().socketsOf('made-1').length, 1);
  });

  test('rebase -i asks how many commits before it starts', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/terminal');

    await click('[data-test-launch="i"]');
    await fillIn('[data-test-rebase-count]', '4');
    await click('[data-test-rebase-open]');

    assert.deepEqual(opened(), [{ keys: 'i4' }]);
  });

  test('a terminal command from the git palette opens in the Terminal tab', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'i', '3');
    assert
      .dom('[data-test-palette-footer]')
      .hasText(
        'will open: git rebase -i HEAD~3 in the Terminal tab · Enter open · Esc cancel',
      );
    await press('Enter');

    assert.deepEqual(opened(), [{ keys: 'i3' }]);
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
    assert
      .dom('[data-test-session="made-1"]')
      .hasAttribute('aria-current', 'true');
  });

  test('g r opens the steered rebase in the Terminal tab', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'r', 'Enter');

    assert.deepEqual(opened(), [{ keys: 'r' }]);
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  function needingARebase(over: DashboardOver): void {
    board().serves = 'hub';
    board().manager = dashboard(over);
    board().held = [heldPr({ dashboard: over })];
  }

  const REBASE_NEXT: DashboardOver = {
    facts: factsFor('rebase'),
    status: { mergeable: false, needs_rebase: true },
  };

  test('when the next move is a rebase, the bar offers it and it opens the steered rebase in the Terminal tab', async function (assert) {
    needingARebase(REBASE_NEXT);
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-your-move] [data-test-rebase]');

    assert.deepEqual(opened(), [{ keys: 'r' }]);
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  test('when the next move is a rebase, the bar names it once, on the button', async function (assert) {
    needingARebase(REBASE_NEXT);
    await visit('/pr/o/r/7/dashboard');

    const move = find('[data-test-your-move]')?.textContent ?? '';
    assert.strictEqual(move.split('Rebase on main').length - 1, 1);
  });

  test('in a crowded bar, the rebase button stays inside its box and the draft pill clear of it', async function (assert) {
    needingARebase({
      ...REBASE_NEXT,
      facts: factsFor('rebase', { draft: true }),
    });
    await visit('/pr/o/r/7/dashboard');

    const bar = find('[data-test-pr-bar]') as HTMLElement;
    bar.style.width = '900px';

    const box = find('[data-test-your-move]')!.getBoundingClientRect();
    const button = find(
      '[data-test-your-move] [data-test-rebase]',
    )!.getBoundingClientRect();
    const pill = find('[data-test-draft-pill]')!.getBoundingClientRect();
    assert.true(button.right <= box.right, `${button.right} <= ${box.right}`);
    assert.true(pill.right <= box.left, `${pill.right} <= ${box.left}`);
  });

  test('a mergeable no that a rebase would fix offers the rebase beside it, whatever the next move', async function (assert) {
    needingARebase({
      facts: factsFor('fix-ci', { merge_state: 'conflicts' }),
      status: { mergeable: false, needs_rebase: true },
    });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-your-move] [data-test-rebase]').doesNotExist();
    await click('[data-test-status="mergeable"] [data-test-rebase]');

    assert.deepEqual(opened(), [{ keys: 'r' }]);
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  test('a pull request that needs no rebase is offered none', async function (assert) {
    needingARebase({ status: { mergeable: false, needs_rebase: false } });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-rebase]').doesNotExist();
  });

  test('while the agent is already rebasing, neither place offers another', async function (assert) {
    needingARebase({
      ...REBASE_NEXT,
      system: {
        agent: {
          name: 'Claude',
          enabled: true,
          state: 'working',
          event: 'became-unmergeable',
          elapsed_seconds: 10,
          silent_seconds: 1,
        },
      },
    });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-rebase]').doesNotExist();
  });

  test('a command the manager refuses says why and leaves you where you were', async function (assert) {
    onTheHub();
    board().refusal = {
      status: 409,
      code: 'terminal-refused',
      detail: "refused: the worktree holds another PR's branch",
    };
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'c', 'Enter');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-toast]')
      .includesText(
        "git commit did not open: refused: the worktree holds another PR's branch",
      );
  });

  test('a command whose board cannot be reached says so, is reported and leaves you where you were', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');
    board().broken = /\/api\/terminal\/sessions$/;

    await press('g', 'c', 'Enter');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-toast]')
      .includesText(
        'git commit did not open: the board server is not answering',
      );
    assert.true(
      board().reported.some(({ where }) => where === 'terminal'),
      'the fault is reported',
    );
  });

  test('a command that opened outside the page says so and leaves you where you were', async function (assert) {
    onTheHub();
    board().opensOutside = true;
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'a', 'Enter');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-toast]')
      .includesText('git add -p opened outside this page');
  });

  test('the Dashboard reaches the Terminal tab by t, with no button for it', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="terminal"]').doesNotExist();
    await press('t');
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  test("the Board's Steer it yourself takes you to the Terminal tab with the session", async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="start-session"]');
    await click('[data-test-dialog-submit]');
    await clock().tick(500);

    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
    assert.deepEqual(texts('[data-test-session]'), [
      'claude --resume k1 /wt/thread-k1',
    ]);
    assert
      .dom('[data-test-session="made-1"]')
      .hasAttribute('aria-current', 'true');
  });

  test('a session whose command exits keeps its screen and its place in the list, with a bar that says its exit code', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().print('shell-1', 'bye');
    await shows('bye');

    board().exit('shell-1', 3);
    await waitFor('[data-test-terminal-exit]');

    assert.dom('[data-test-terminal-exit]').includesText('Exited with code 3');
    assert.dom('[data-test-terminal-close]').hasText('Close');
    assert.ok(screen().includes('bye'), 'the last screen stays');
    assert.dom('[data-test-screen] .tty-screen').hasAttribute('data-exited');
    assert
      .dom('[data-test-session="shell-1"]')
      .hasAttribute('aria-current', 'true');
    assert
      .dom('[data-test-session="shell-1"] [data-test-session-standing]')
      .hasText('exited 3');
  });

  test('closing an exited session takes its screen and its list entry away', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().exit('shell-1', 0);
    await waitFor('[data-test-terminal-exit]');

    await click('[data-test-terminal-close]');

    assert.dom('[data-test-session]').doesNotExist();
    assert.dom('[data-test-screen] .xterm').doesNotExist();
    assert.dom('[data-test-terminal-exit]').doesNotExist();
    assert
      .dom('[data-test-terminal-standing]')
      .hasText('No session yet. Start one from the list on the left.');
  });

  test('closing the shown exited session gives the screen to the one before it', async function (assert) {
    onTheHub();
    board().terminalSessions = [
      SHELL,
      { ...SHELL, id: 'shell-2', argv: ['git', 'commit'] },
    ];
    await visit('/pr/o/r/7/terminal');
    await click('[data-test-session="shell-2"]');
    board().exit('shell-2', 0);
    await waitFor('[data-test-terminal-exit]');

    await click('[data-test-terminal-close]');

    assert.dom('[data-test-session="shell-2"]').doesNotExist();
    assert
      .dom('[data-test-session="shell-1"]')
      .hasAttribute('aria-current', 'true');
    assert.strictEqual(findAll('[data-test-screen] .xterm').length, 1);
    assert.dom('[data-test-terminal-exit]').doesNotExist();
  });

  test('leaving the tab and coming back keeps the session and its connection', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().print('shell-1', 'still here');
    await shows('still here');

    await press('1');
    await press('3');

    assert.strictEqual(board().socketsOf('shell-1').length, 1);
    assert.strictEqual(board().socketsOf('shell-1')[0]!.closedWith, null);
    await shows('still here');
    assert.ok(true, 'the screen came back as it was');
  });

  test('a session whose connection was lost reattaches when the board lists it again', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().socketsOf('shell-1')[0]!.close(1006);
    await waitUntil(() =>
      find('[data-test-session-standing]')?.textContent?.includes('lost'),
    );

    await press('1');
    await press('3');
    await waitUntil(() => board().socketsOf('shell-1').length === 2);
    board().print('shell-1', 'carried on');

    await shows('carried on');
    assert.dom('[data-test-session-standing]').doesNotExist();
    assert.deepEqual(texts('[data-test-session]'), [
      '/bin/zsh -l ~/repositories/o/r',
    ]);
  });

  test('a lost connection says the session is not lost and reattaches by itself once the board lists it again', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().socketsOf('shell-1')[0]!.close(1006);
    await waitUntil(() => find('[data-test-terminal-lost]'));

    assert
      .dom('[data-test-terminal-lost]')
      .hasText(
        'Lost connection with the board, please wait. Your terminal session is not lost.',
      );

    await clock().tick(1000);
    await waitUntil(() => board().socketsOf('shell-1').length === 2);
    board().print('shell-1', 'carried on');

    await shows('carried on');
    assert.dom('[data-test-terminal-lost]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  test('a lost connection resumes on the same screen after the last byte it showed', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().print('shell-1', 'halfway ');
    await shows('halfway');
    board().socketsOf('shell-1')[0]!.close(1006);
    await waitUntil(() => find('[data-test-terminal-lost]'));

    await clock().tick(1000);
    await waitUntil(() => board().socketsOf('shell-1').length === 2);
    board().print('shell-1', 'through');

    await shows('halfway through');
    assert.strictEqual(
      new URL(board().socketsOf('shell-1')[1]!.url).searchParams.get('after'),
      '8',
    );
    assert.strictEqual(
      screen().split('halfway').length - 1,
      1,
      'what was shown before is not shown again',
    );
    assert.strictEqual(findAll('[data-test-screen] .xterm').length, 1);
  });

  test('a lost session the board no longer lists says it ended', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];
    await visit('/pr/o/r/7/terminal');
    board().socketsOf('shell-1')[0]!.close(1006);
    await waitUntil(() => find('[data-test-terminal-lost]'));
    board().terminalSessions = [];

    await clock().tick(1000);
    await waitUntil(() =>
      find('[data-test-session-standing]')?.textContent?.includes('ended'),
    );

    assert.dom('[data-test-session-standing]').hasText('ended');
    assert.dom('[data-test-terminal-lost]').doesNotExist();
  });

  test('a session through the hub connects under the pull request', async function (assert) {
    onTheHub();
    board().terminalSessions = [SHELL];

    await visit('/pr/o/r/7/terminal');

    assert.strictEqual(
      new URL(board().socketsOf('shell-1')[0]!.url).pathname,
      '/pr/o/r/7/api/terminal/sessions/shell-1',
    );
  });

  test('a board that does not answer says the terminal waits for it', async function (assert) {
    onTheHub();
    board().held = [heldPr({ board_url: null })];

    await visit('/pr/o/r/7/terminal');

    assert
      .dom('[data-test-terminal-standing]')
      .hasText(
        'The terminal runs in the manager’s board, which is not answering.',
      );
  });
});
