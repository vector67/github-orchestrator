import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, find, findAll, visit } from '@ember/test-helpers';
import {
  finishedRun,
  heldPr,
  runLedger,
  setupFakeBoard,
  WALL_GROUPS,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import type { WatcherHealth } from 'frontend/data/api';

const LIST = 5000;
const POLLED = new Date(2026, 8, 28, 14, 32, 5).getTime();

module('Acceptance | runs', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(): void {
    board().serves = 'hub';
    board().held = [heldPr()];
  }

  function text(selector: string): string {
    return (find(selector)?.textContent ?? '').trim().replace(/\s+/g, ' ');
  }

  function polledAt(): { watcher: Partial<WatcherHealth> } {
    return {
      watcher: {
        polled_at: new Date(POLLED).toISOString(),
        next_poll_at: new Date(POLLED + 60_000).toISOString(),
      },
    };
  }

  test('the wall’s top bar says when the watcher polled and how long ago', async function (assert) {
    onTheHub();
    board().ledger = runLedger(polledAt());
    clock().now = POLLED + 19_000;

    await visit('/');

    assert.strictEqual(
      text('[data-test-health="poll"]'),
      'polled 14:32:05, 19s ago',
    );
  });

  test('the age moves on with the wall’s refresh', async function (assert) {
    onTheHub();
    board().ledger = runLedger(polledAt());
    clock().now = POLLED + 19_000;
    await visit('/');

    await clock().tick(LIST);

    assert.strictEqual(
      text('[data-test-health="poll"]'),
      'polled 14:32:05, 24s ago',
    );
  });

  test('a poll that is due and has not ended yet is no alarm', async function (assert) {
    onTheHub();
    board().ledger = runLedger(polledAt());
    clock().now = POLLED + 70_000;

    await visit('/');

    assert.strictEqual(
      text('[data-test-health="poll"]'),
      'polled 14:32:05, 1m ago',
    );
    assert.dom('[data-test-health-alarm]').doesNotExist();
  });

  test('a watcher that has not polled for too long is an alarm', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      watcher: { ...polledAt().watcher, overdue: true },
    });
    clock().now = POLLED + 300_000;

    await visit('/');

    assert.strictEqual(
      text('[data-test-health="poll"]'),
      'no poll since 14:32:05, 5m ago',
    );
    assert.dom('[data-test-health="poll"][data-test-health-alarm]').exists();
  });

  test('a watcher whose cycles fail says why, as an alarm', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      watcher: { ...polledAt().watcher, last_error: 'gh: HTTP 502' },
    });
    clock().now = POLLED + 19_000;

    await visit('/');

    assert.strictEqual(
      text('[data-test-health="poll"]'),
      'polls failing: gh: HTTP 502',
    );
    assert.dom('[data-test-health="poll"][data-test-health-alarm]').exists();
  });

  test('a long failure stays on the bar’s one row and gives its whole text on hover', async function (assert) {
    const failure = `watcher cannot search acme/gadgets-api as vector67 — ${'check [[repos]] and gh_account '.repeat(12)}`;
    onTheHub();
    board().watching = ['acme/gadgets-api'];
    board().ledger = runLedger({
      watcher: { ...polledAt().watcher, last_error: failure },
    });
    clock().now = POLLED + 19_000;

    await visit('/');

    const bar = find('.wall-bar')!.getBoundingClientRect();
    const toggle = find('[data-test-theme-toggle]')!.getBoundingClientRect();
    assert.true(
      bar.height < 2 * toggle.height,
      `bar ${bar.height}px against a ${toggle.height}px button`,
    );
    assert
      .dom('[data-test-health="poll"]')
      .hasAttribute('title', `polls failing: ${failure}`);
  });

  test('a watcher that has never polled says so', async function (assert) {
    onTheHub();

    await visit('/');

    assert.strictEqual(text('[data-test-health="poll"]'), 'no poll yet');
  });

  test('the top bar counts today’s runs and what they would have cost', async function (assert) {
    onTheHub();
    board().ledger = runLedger({ today: { runs: 12, cost_usd: 8.14 } });

    await visit('/');

    assert.strictEqual(
      text('[data-test-health="today"]'),
      '12 runs today · ~$8.14',
    );
  });

  test('a day of one run that reported no cost names no cost', async function (assert) {
    onTheHub();
    board().ledger = runLedger({ today: { runs: 1, unpriced: 1 } });

    await visit('/');

    assert.strictEqual(text('[data-test-health="today"]'), '1 run today');
  });

  function watched(): string[] {
    return findAll('[data-test-watching]').map(
      (element) => element.textContent?.trim() ?? '',
    );
  }

  test('the top bar’s repo filter names every repository this instance watches, on the wall and the runs', async function (assert) {
    onTheHub();
    board().watching = ['acme/gadgets', 'acme/widgets'];

    await visit('/');
    await click('[data-test-repo-filter]');

    assert.deepEqual(watched(), ['acme/gadgets', 'acme/widgets']);

    await click('[data-test-nav="runs"]');
    await click('[data-test-repo-filter]');

    assert.deepEqual(watched(), ['acme/gadgets', 'acme/widgets']);
  });

  test('a wall an older page kept, naming its one repository, still names it', async function (assert) {
    onTheHub();
    localStorage.setItem(
      'hub-pull-requests',
      JSON.stringify({
        watching: 'acme/gadgets',
        groups: WALL_GROUPS,
        pull_requests: [],
      }),
    );
    board().broken = /\/api\/pull-requests$/;

    await visit('/');

    assert.dom('[data-test-repo-filter]').hasText('acme/gadgets');
  });

  test('the top bar leads from the wall to the runs and back', async function (assert) {
    onTheHub();
    await visit('/');

    await click('[data-test-nav="runs"]');

    assert.strictEqual(currentURL(), '/runs');
    assert.dom('[data-test-nav="runs"]').hasAttribute('aria-current', 'page');
    assert.dom('[data-test-health="today"]').exists();

    await click('[data-test-nav="wall"]');

    assert.strictEqual(currentURL(), '/');
    assert.dom('[data-test-wall]').exists();
  });

  test('each run shows when it ended, its pull request, what it was for, how long it took, how it ended and what it cost', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      runs: [
        finishedRun({
          ended_at: new Date(POLLED).toISOString(),
          event: 'ci-failed',
          elapsed_seconds: 95,
          exit_code: 0,
          cost_usd: 0.42,
        }),
      ],
    });
    clock().now = POLLED + 60_000;

    await visit('/runs');

    assert.deepEqual(
      findAll('[data-test-run] [data-test-run-cell]').map((one) =>
        one.textContent.trim().replace(/\s+/g, ' '),
      ),
      ['14:32:05', '#7', 'CI fix', '1m 35s', 'ok', '$0.42'],
    );
  });

  test('a run from an earlier day says which day', async function (assert) {
    onTheHub();
    const saturday = new Date(2026, 8, 26, 9, 5, 0).getTime();
    board().ledger = runLedger({
      runs: [finishedRun({ ended_at: new Date(saturday).toISOString() })],
    });
    clock().now = POLLED;

    await visit('/runs');

    assert.strictEqual(
      text('[data-test-run] [data-test-run-cell="ended"]'),
      'Sat 09:05',
    );
  });

  test('a failed run is marked failed and a run that went fine is not', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      runs: [
        finishedRun({ exit_code: 1, failed: true, cost_usd: null }),
        finishedRun({ event: 'review-requested' }),
      ],
    });

    await visit('/runs');

    assert.deepEqual(
      findAll('[data-test-run]').map((one) =>
        one.hasAttribute('data-test-failed'),
      ),
      [true, false],
    );
    assert.strictEqual(
      text('[data-test-run] [data-test-run-cell="exit"]'),
      'exit 1',
    );
    assert.strictEqual(
      text('[data-test-run] [data-test-run-cell="cost"]'),
      '—',
    );
  });

  test('a stretch of failures is one row per pull request and kind, counting them', async function (assert) {
    onTheHub();
    const at = (minutes: number) =>
      new Date(POLLED + minutes * 60_000).toISOString();
    const failure = (ended_at: string, event: string, number = 48) =>
      finishedRun({
        ended_at,
        number,
        event,
        elapsed_seconds: 8,
        exit_code: 1,
        cost_usd: 0,
        failed: true,
      });
    board().ledger = runLedger({
      runs: [
        failure(at(2), 'thread-fix-PRRT_b'),
        failure(at(1.5), 'thread-fix-PRRT_c', 49),
        failure(at(1), 'thread-fix-PRRT_a'),
        failure(at(0), 'thread-fix-PRRT_a'),
        finishedRun({ ended_at: at(-5), number: 48 }),
      ],
    });
    clock().now = POLLED + 10 * 60_000;

    await visit('/runs');

    assert.deepEqual(
      findAll('[data-test-run] [data-test-run-cell="pr"]').map((one) =>
        one.textContent.trim(),
      ),
      ['#48', '#49', '#48'],
    );
    assert.deepEqual(
      findAll('[data-test-run]:first-child [data-test-run-cell]').map((one) =>
        one.textContent.trim().replace(/\s+/g, ' '),
      ),
      [
        '14:32:05–14:34:05',
        '#48',
        'thread fix · 3 failed',
        '24s',
        'exit 1',
        '$0.00',
      ],
    );
  });

  test('the facts count the week’s failed runs, as an alarm', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      runs: [
        finishedRun({ exit_code: 1, failed: true }),
        finishedRun({ exit_code: 1, failed: true, number: 8 }),
        finishedRun(),
      ],
    });

    await visit('/runs');

    const failed = findAll('[data-test-watcher-fact]').find((one) =>
      one.textContent.includes('Failed'),
    );
    assert.strictEqual(
      failed?.textContent.trim().replace(/\s+/g, ' '),
      'Failed 2 of 3 this week',
    );
    assert.dom(failed).hasClass('failing');
  });

  test('a run claude reported as an error though it exited cleanly says it errored', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      runs: [finishedRun({ exit_code: 0, failed: true })],
    });

    await visit('/runs');

    assert.strictEqual(
      text('[data-test-run] [data-test-run-cell="exit"]'),
      'errored',
    );
  });

  test('a run opens its pull request’s dashboard on claude’s output', async function (assert) {
    onTheHub();
    board().ledger = runLedger({ runs: [finishedRun()] });
    await visit('/runs');

    await click('[data-test-run] [data-test-run-open]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard?pane=agent');
    assert
      .dom('[data-test-pane-toggle="agent"]')
      .hasAttribute('aria-pressed', 'true');
  });

  test('a run on a pull request the watcher no longer holds opens nothing', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      runs: [finishedRun({ number: 82, board_url: null })],
    });

    await visit('/runs');

    assert.dom('[data-test-run] [data-test-run-open]').doesNotExist();
    assert.strictEqual(
      text('[data-test-run] [data-test-run-cell="pr"]'),
      '#82',
    );
  });

  test('the dashboard still opens on the agent’s notes when nothing asks for claude’s output', async function (assert) {
    onTheHub();

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-pane-toggle="agent"]')
      .hasAttribute('aria-pressed', 'false');
  });

  test('a week with no runs says so', async function (assert) {
    onTheHub();

    await visit('/runs');

    assert.dom('[data-test-runs-empty]').exists();
    assert.dom('[data-test-run]').doesNotExist();
  });

  test('a hub without a complete config sends the runs page to setup', async function (assert) {
    onTheHub();
    board().state = 'broken';

    await visit('/runs');

    assert.strictEqual(currentURL(), '/setup');
  });

  test('the runs page shows the watcher’s health in full', async function (assert) {
    onTheHub();
    board().ledger = runLedger({
      ...polledAt(),
      today: { runs: 3, cost_usd: 0.75, unpriced: 1 },
    });
    clock().now = POLLED + 19_000;

    await visit('/runs');

    assert.deepEqual(
      findAll('[data-test-watcher-fact]').map((one) =>
        one.textContent.trim().replace(/\s+/g, ' '),
      ),
      [
        'Watcher watching',
        'Last poll 14:32:05, 19s ago',
        'Next poll in 41s',
        'Today 3 runs · ~$0.75, 1 without a cost',
      ],
    );
  });
});
