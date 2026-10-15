import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  prSummary,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const MINUTE = 60_000;
const LIST = 5000;

module('Acceptance | summary tab', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function asReviewer(): void {
    board().held = [
      heldPr({
        dashboard: { facts: { is_author: false }, pr: { author: 'erin' } },
      }),
    ];
    board().actAs('reviewer');
  }

  function ago(minutes: number): string {
    return new Date(clock().now - minutes * MINUTE).toISOString();
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  test('a pull request you review opens on Summary, its strip naming the head it read and when it finished above the summary', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      started: ago(9),
      finished: ago(5),
      markdown: '# What it asks\n\nSplit the writer in two.',
    });

    await visit('/pr/o/r/7');

    assert.strictEqual(currentURL(), '/pr/o/r/7/summary');
    assert.deepEqual(texts('[data-test-tab]'), [
      'Summary 1',
      'Board 2',
      'Dashboard 3',
      'Terminal 4',
      'Diff 5',
    ]);
    assert
      .dom('[data-test-tab="summary"]')
      .hasAttribute('aria-current', 'page');
    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'ready');
    assert
      .dom('[data-test-summary-strip]')
      .hasText('c0ffee1 · finished 5m ago');
    assert.dom('[data-test-summary-markdown] h1').hasText('What it asks');
  });

  test('a push since the summary marks it stale, naming both heads and how far behind it is, with Rerun', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'abc1234',
      exit_status: 0,
      finished: ago(30),
      markdown: '# What it asks',
      behind: 2,
    });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'stale');
    assert
      .dom('[data-test-summary-strip]')
      .hasText('Written for abc1234, head is c0ffee1, 2 commits behind Rerun');
    assert.dom('[data-test-summary-markdown] h1').hasText('What it asks');
  });

  test('a pull request you review with no summary yet waits for its turn, with nothing below', async function (assert) {
    asReviewer();
    board().summary = prSummary({ wanted: ago(2) });

    await visit('/pr/o/r/7');

    assert.strictEqual(currentURL(), '/pr/o/r/7/summary');
    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'none-yet-reviewer');
    assert.dom('[data-test-summary-strip]').hasText('Waiting for its turn');
    assert.dom('[data-test-summary-markdown]').doesNotExist();
  });

  test('a pull request you review with no request waiting offers Summarise rather than a wait that never ends', async function (assert) {
    asReviewer();
    board().summary = prSummary({ etag: '"summary-5"' });

    await visit('/pr/o/r/7');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'none-yet-author');
    assert.dom('[data-test-summary-strip]').hasText('No summary Summarise');

    await click('[data-test-summary-run]');

    assert.deepEqual(
      board().posted.map(({ verb, ifMatch }) => ({ verb, ifMatch })),
      [{ verb: 'summarise', ifMatch: '"summary-5"' }],
    );
  });

  test('your own pull request opens on Board, and its Summary tab offers Summarise, which runs one against the summary it read', async function (assert) {
    board().summary = prSummary({ etag: '"summary-4"' });

    await visit('/pr/o/r/7');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    await click('[data-test-tab="summary"]');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'none-yet-author');
    assert.dom('[data-test-summary-strip]').hasText('No summary Summarise');

    await click('[data-test-summary-run]');

    assert.deepEqual(
      board().posted.map(({ verb, ifMatch }) => ({ verb, ifMatch })),
      [{ verb: 'summarise', ifMatch: '"summary-4"' }],
    );
    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'running');
  });

  test('while a run is in flight the strip shows it live on the head it reads, how long it has run and each witness, ticking them off as the polls come in, over the previous summary', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'abc1234',
      exit_status: 0,
      markdown: '# Before',
      running: true,
      since: ago(3),
      witnesses: [
        { witness: 'claimed', done: true },
        { witness: 'implementation', done: false },
      ],
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'running');
    assert.dom('[data-test-summary-strip] .live-dot').exists();
    assert.dom('[data-test-summary-strip]').containsText('c0ffee1 · 3m 0s');
    assert.deepEqual(texts('[data-test-witness]'), [
      'claimed',
      'implementation',
    ]);
    assert.dom('[data-test-witness="claimed"]').hasAttribute('data-done');
    assert
      .dom('[data-test-witness="implementation"]')
      .doesNotHaveAttribute('data-done');
    assert.dom('[data-test-summary-markdown] h1').hasText('Before');

    board().summary = {
      ...board().summary,
      witnesses: [
        { witness: 'claimed', done: true },
        { witness: 'implementation', done: true },
      ],
    };
    await clock().tick(LIST);

    assert
      .dom('[data-test-witness="implementation"]')
      .hasAttribute('data-done');
  });

  test('a run that needs the GitHub API shows the plugin’s reason and offers the API with its cost, over the previous summary', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'abc1234',
      exit_status: 3,
      markdown: '# Before',
      stderr:
        'Cannot read o/r locally: no clone.\n' +
        'Run this from a clone of o/r, or confirm reading its 6 changed files over the GitHub API (about 37 API calls) by adding --use-github-api.\n',
      etag: '"summary-7"',
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'needs-github-api');
    assert
      .dom('[data-test-summary-strip]')
      .hasText(
        'Cannot read o/r locally: no clone. Use the GitHub API (about 37 calls)',
      );
    assert.dom('[data-test-summary-markdown] h1').hasText('Before');

    await click('[data-test-summary-github-api]');

    assert.deepEqual(
      board().posted.map(({ verb, ifMatch }) => ({ verb, ifMatch })),
      [{ verb: 'summarise-with-github-api', ifMatch: '"summary-7"' }],
    );
    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'running');
  });

  test('a failed run shows its exit status and the end of what it printed, with Rerun, over the previous summary', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 2,
      markdown: '# Before',
      stderr: 'Traceback (most recent call last):\nValueError: no witnesses\n',
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'failed');
    assert
      .dom('[data-test-summary-strip]')
      .hasText('exit 2 · ValueError: no witnesses Rerun');
    assert.dom('[data-test-summary-markdown] h1').hasText('Before');

    await click('[data-test-summary-run]');

    assert.deepEqual(
      board().posted.map(({ verb }) => verb),
      ['summarise'],
    );
  });

  test('a run the plugin never started is a failure too, saying why', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      exit_status: null,
      stderr: 'uv: command not found',
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'failed');
    assert
      .dom('[data-test-summary-strip]')
      .hasText('exit unknown · uv: command not found Rerun');
  });

  test('a run the lane refuses leaves the strip as it was, saying why in the lane’s words', async function (assert) {
    board().summary = prSummary();
    await visit('/pr/o/r/7/summary');
    board().refusal = {
      status: 409,
      code: 'summary-refused',
      detail: 'another summary is running',
    };

    await click('[data-test-summary-run]');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'none-yet-author');
    assert
      .dom('[data-test-summary-said]')
      .hasText('another summary is running');
  });

  test('a summary that moved before the click is read again, and the strip says so', async function (assert) {
    board().summary = prSummary({ etag: '"summary-1"' });
    await visit('/pr/o/r/7/summary');
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      markdown: '# Meanwhile',
      etag: '"summary-2"',
    });

    await click('[data-test-summary-run]');

    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'ready');
    assert.dom('[data-test-summary-markdown] h1').hasText('Meanwhile');
    assert
      .dom('[data-test-summary-said]')
      .hasText(
        'The summary moved before your click reached the board. It has been read again; look at it before you press.',
      );
  });

  test('a run in flight is shown as running whatever the last run left', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      exit_status: 3,
      stderr: 'Cannot read o/r locally: no clone.',
      running: true,
      since: ago(1),
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'running');
  });

  test('until the facts say whose pull request it is, the tab draws no strip', async function (assert) {
    board().manager = dashboard({ facts: null, polled: false });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').doesNotExist();
  });

  test('each wall row counts the mismatches of its stored summary, one in the singular, and none at zero or with no count', async function (assert) {
    board().held = [
      heldPr({ number: 7, mismatches: 3 }),
      heldPr({ number: 8, mismatches: 1 }),
      heldPr({ number: 9, mismatches: 0 }),
      heldPr({ number: 10, mismatches: null }),
    ];

    await visit('/');

    const chipOf = (number: number): string =>
      `[data-test-wall-row="o/r#${number}"] [data-test-mismatches]`;
    assert.dom(chipOf(7)).hasText('3 mismatches');
    assert.dom(chipOf(8)).hasText('1 mismatch');
    assert.dom(chipOf(9)).doesNotExist();
    assert.dom(chipOf(10)).doesNotExist();
  });

  test('the header counts the mismatches the wall served, with the summary tab never opened', async function (assert) {
    board().held = [heldPr({ mismatches: 2 })];

    await visit('/pr/o/r/7');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    assert.dom('.prflags [data-test-mismatches]').hasText('2 mismatches');
  });

  test('a stale summary still counts its mismatches in the header, as the summary feed serves them', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'abc1234',
      exit_status: 0,
      finished: ago(30),
      markdown: '# What it asks',
      behind: 2,
      mismatches: 4,
    });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'stale');
    assert.dom('.prflags [data-test-mismatches]').hasText('4 mismatches');
  });

  test('1 opens Summary and 2 Board, in the order the tabs stand', async function (assert) {
    await visit('/pr/o/r/7/dashboard');

    await triggerEvent(document, 'keydown', { key: '1' });
    assert.strictEqual(currentURL(), '/pr/o/r/7/summary');

    await triggerEvent(document, 'keydown', { key: '2' });
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });
});
