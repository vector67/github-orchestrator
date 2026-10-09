import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, currentURL } from '@ember/test-helpers';
import { heldPr, setupFakeBoard } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const SLOW = 5000;

module('Acceptance | shell', function (hooks) {
  setupApplicationTest(hooks);

  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    localStorage.removeItem('board-theme');
    document.documentElement.removeAttribute('data-theme');
    board().conversations = [
      board().threadIn('proposed', { key: 'k1' }),
      board().threadIn('proposed', { key: 'k2' }),
    ];
  });

  hooks.afterEach(function () {
    localStorage.removeItem('board-theme');
    document.documentElement.removeAttribute('data-theme');
  });

  test('the bar names the pr and the strip its counts', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-pr-title]').hasText('#7 PROJ-7 · Fix the widget');
    assert
      .dom('[data-test-repo]')
      .hasText('o/r#7')
      .hasAttribute('href', 'https://github.com/o/r/pull/7');
    assert.dom('[data-test-count="ready"]').containsText('2');
    assert.dom('[data-test-count="ready"]').containsText('ready');
  });

  test('the view toggle walks between queue and board', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-view="queue"]').hasClass('active');
    assert.dom('[data-test-view="board"]').doesNotHaveClass('active');
    assert.dom('[data-test-view="queue"]').hasAttribute('aria-current', 'page');
    assert.dom('[data-test-view="board"]').doesNotHaveAttribute('aria-current');

    await click('[data-test-view="board"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/board');
    assert.dom('[data-test-view="board"]').hasAttribute('aria-current', 'page');
    assert.dom('[data-test-view="queue"]').doesNotHaveAttribute('aria-current');
    assert
      .dom('[data-test-view="board"]')
      .hasClass('active', 'the bar says which view you are in');
    assert
      .dom('[data-test-pr-title]')
      .hasText(
        '#7 PROJ-7 · Fix the widget',
        'and the board view keeps the same bar',
      );

    await click('[data-test-view="queue"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('the threads are read again on every tab of the pull request, and not once you have left it', async function (assert) {
    board().serves = 'hub';
    board().held = [heldPr()];
    await visit('/pr/o/r/7/conversations');
    const lists = () => board().askedFor(/\/api\/conversations$/).length;
    const before = lists();
    await clock().tick(SLOW);
    assert.strictEqual(lists(), before + 1, 'the queue refreshes itself');

    await click('[data-test-tab="dashboard"]');
    const onTheDashboard = lists();
    await clock().tick(SLOW);
    assert.strictEqual(
      lists(),
      onTheDashboard + 1,
      'the bar’s counts come from the threads on every tab',
    );

    await visit('/');
    const left = lists();
    await clock().tick(SLOW);

    assert.strictEqual(
      lists(),
      left,
      'refreshing a pull request you have left rejects, and the banner would ' +
        'call that a dead server every second',
    );
  });

  test('the theme toggle stamps the root and is remembered', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    const wasDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const flipped = wasDark ? 'light' : 'dark';

    await click('[data-test-theme-toggle]');

    assert
      .dom(document.documentElement)
      .hasAttribute(
        'data-theme',
        flipped,
        'the toggle flips whatever the viewer was actually seeing',
      );
    assert.strictEqual(localStorage.getItem('board-theme'), flipped);

    await click('[data-test-theme-toggle]');

    assert
      .dom(document.documentElement)
      .hasAttribute('data-theme', wasDark ? 'dark' : 'light', 'and flips back');
  });

  test('the theme toggle names the dark theme and says whether it is on', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    const wasDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    assert
      .dom('[data-test-theme-toggle]')
      .hasText('Dark theme')
      .hasAttribute('aria-pressed', String(wasDark));

    await click('[data-test-theme-toggle]');

    assert
      .dom('[data-test-theme-toggle]')
      .hasText('Dark theme', 'the name stays put and the state flips')
      .hasAttribute('aria-pressed', String(!wasDark));
  });

  test('sending the review is the primary action of the strip', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-send-review]').hasClass('btn').hasClass('fill');
    assert
      .dom('[data-test-new-draft]')
      .hasClass('btn')
      .doesNotHaveClass('fill', 'opening the composer is secondary');
  });

  test('a face the board cannot serve is said in the bar', async function (assert) {
    const problem =
      'board_font_dir /nowhere cannot be listed, so the board is set in ' +
      'Helvetica Neue instead of its own face';
    board().fontProblem = problem;

    await visit('/pr/o/r/7/conversations');

    assert
      .dom('[data-test-font-problem]')
      .hasText('Board font missing')
      .hasAttribute('title', problem);
  });

  test('the wall says so too', async function (assert) {
    board().serves = 'hub';
    board().fontProblem =
      'board_font_dir /nowhere holds no <Family>-<Style>.otf face';

    await visit('/');

    assert.dom('[data-test-font-problem]').exists();
  });

  test('a newer release the hub has seen shows a quiet badge naming it and the command', async function (assert) {
    board().serves = 'hub';
    board().newestRelease = {
      version: '0.6.0',
      checked_at: '2026-10-09T08:00:00+00:00',
      newer: true,
    };

    await visit('/');

    assert
      .dom('[data-test-update-available]')
      .hasText('Update available')
      .hasAttribute(
        'title',
        'github-orchestrator 0.6.0 is out. Run github-orchestrator update to install it.',
      );
  });

  test('a release no newer than the running one shows no badge', async function (assert) {
    board().serves = 'hub';
    board().newestRelease = {
      version: '0.1.0',
      checked_at: '2026-10-09T08:00:00+00:00',
      newer: false,
    };

    await visit('/');

    assert.dom('[data-test-update-available]').doesNotExist();
  });

  test('a board serving its own face says nothing of it', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-font-problem]').doesNotExist();
  });
});
