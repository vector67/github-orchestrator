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
      .hasText('c0ffee1 finished 5m ago Rerun');
    assert.dom('[data-test-summary-end]').hasText('finished 5m ago Rerun');
    assert.dom('[data-test-summary-markdown] h1').hasText('What it asks');
  });

  function squares(): (string | undefined)[] {
    return findAll('[data-test-diffstat-square]').map(
      (one) => (one as HTMLElement).dataset['testDiffstatSquare'],
    );
  }

  test('the tab heads with the full title, when it was opened, its commits and its lines changed as GitHub draws them', async function (assert) {
    const title =
      'Split the snapshot writer in two so each half can be tested alone';
    board().held = [heldPr({ dashboard: { pr: { title } } })];
    board().pullRequest = {
      ...board().pullRequest,
      created_at: ago(3 * 24 * 60),
      commits: 4,
      additions: 501,
      deletions: 214,
    };

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-title]').hasText(title);
    assert.dom('[data-test-summary-opened]').hasText('opened 3d ago');
    assert.dom('[data-test-summary-commits]').hasText('4 commits');
    assert.dom('[data-test-summary-additions]').hasText('+501');
    assert.dom('[data-test-summary-deletions]').hasText('-214');
    assert.deepEqual(squares(), [
      'added',
      'added',
      'added',
      'deleted',
      'neutral',
    ]);
  });

  test('a pull request of one commit says so in the singular, and one that changes no lines draws five grey squares', async function (assert) {
    board().pullRequest = {
      ...board().pullRequest,
      commits: 1,
      additions: 0,
      deletions: 0,
    };

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-commits]').hasText('1 commit');
    assert.dom('[data-test-summary-additions]').hasText('+0');
    assert.dom('[data-test-summary-deletions]').hasText('-0');
    assert.deepEqual(squares(), [
      'neutral',
      'neutral',
      'neutral',
      'neutral',
      'neutral',
    ]);
  });

  test('Rerun on a current summary starts a run against the summary it read, keeping the text and showing the run beside when the last one finished', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: ago(19),
      markdown: '# What it asks',
      etag: '"summary-9"',
    });
    await visit('/pr/o/r/7/summary');

    await click('[data-test-summary-run]');

    assert.deepEqual(
      board().posted.map(({ verb, ifMatch }) => ({ verb, ifMatch })),
      [{ verb: 'summarise', ifMatch: '"summary-9"' }],
    );
    assert
      .dom('[data-test-summary-strip]')
      .hasAttribute('data-state', 'running');
    assert
      .dom('[data-test-summary-strip]')
      .hasText(
        'c0ffee1 · finished 19m ago rerun started 0s ago, finished 0/6 witnesses',
      );
    assert.dom('[data-test-summary-markdown] h1').hasText('What it asks');
  });

  test('a rerun over a summary counts its witnesses as the polls come in', async function (assert) {
    asReviewer();
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: ago(19),
      markdown: '# What it asks',
      running: true,
      since: ago(5),
      witnesses: [
        { witness: 'requested', done: true },
        { witness: 'claimed', done: true },
        { witness: 'implementation', done: true },
        { witness: 'tests', done: true },
        { witness: 'why', done: false },
      ],
    });

    await visit('/pr/o/r/7/summary');

    assert
      .dom('[data-test-summary-rerun]')
      .hasText('rerun started 5m ago, finished 4/6 witnesses');

    board().summary = {
      ...board().summary,
      witnesses: [
        { witness: 'requested', done: true },
        { witness: 'claimed', done: true },
        { witness: 'implementation', done: true },
        { witness: 'tests', done: true },
        { witness: 'why', done: true },
        { witness: 'alignment', done: false },
      ],
    };
    await clock().tick(LIST);

    assert
      .dom('[data-test-summary-rerun]')
      .hasText('rerun started 5m ago, finished 5/6 witnesses');
  });

  test('a push since the summary marks it stale, naming both heads and how far behind it is, with when it finished and Rerun at its end', async function (assert) {
    asReviewer();
    const finished = ago(30);
    board().summary = prSummary({
      head_sha: 'abc1234',
      exit_status: 0,
      finished,
      markdown: '# What it asks',
      behind: 2,
    });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'stale');
    assert
      .dom('[data-test-summary-strip]')
      .hasText(
        'Written for abc1234, head is c0ffee1, 2 commits behind finished 30m ago Rerun',
      );
    assert.dom('[data-test-summary-end]').hasText('finished 30m ago Rerun');
    assert
      .dom('[data-test-summary-end] [data-test-summary-finished]')
      .hasAttribute('title', finished);
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

  test('a summary whose pull request has no facts yet still shows its strip and the summary', async function (assert) {
    board().held = [heldPr({ dashboard: { facts: null } })];
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: ago(5),
      markdown: '# What it asks',
    });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasAttribute('data-state', 'ready');
    assert.dom('[data-test-summary-markdown] h1').hasText('What it asks');
  });

  test('a request waiting on a pull request with no facts yet waits for its turn, since only a reviewer is asked', async function (assert) {
    board().held = [heldPr({ dashboard: { facts: null } })];
    board().summary = prSummary({ wanted: ago(2) });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasText('Waiting for its turn');
  });

  test('no request on a pull request with no facts yet offers Summarise', async function (assert) {
    board().held = [heldPr({ dashboard: { facts: null } })];
    board().summary = prSummary();

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-strip]').hasText('No summary Summarise');
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

  test('while a first run is in flight the strip shows it live on the head it reads, how long it has run and each witness, ticking them off as the polls come in', async function (assert) {
    asReviewer();
    board().summary = prSummary({
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
    assert.dom('[data-test-summary-end]').hasText('Rerun');
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

  test('each wall row counts the mismatches of its stored summary, one in the singular, and none at zero or with no count', async function (assert) {
    board().held = [
      heldPr({ number: 7, mismatches: 3 }),
      heldPr({ number: 8, mismatches: 1 }),
      heldPr({ number: 9, mismatches: 0 }),
      heldPr({ number: 10, mismatches: null }),
    ];

    await visit('/');

    const chipOf = (number: number): string =>
      `[data-test-wall-row="o/r#${number}"] [data-test-state="mismatches"]`;
    assert.dom(chipOf(7)).hasText('3 mismatches');
    assert.dom(chipOf(8)).hasText('1 mismatch');
    assert.dom(chipOf(9)).doesNotExist();
    assert.dom(chipOf(10)).doesNotExist();
  });

  test('a summary with mismatches carries no word of being about an older head or still running', async function (assert) {
    board().held = [heldPr({ mismatches: 3 })];

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-state="mismatches"]')
      .hasText('3 mismatches')
      .hasAttribute('title', /older head/);
  });

  test('the header counts the mismatches the wall served, with the summary tab never opened', async function (assert) {
    board().held = [heldPr({ mismatches: 2 })];

    await visit('/pr/o/r/7');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    assert
      .dom('.prflags [data-test-state="mismatches"]')
      .hasText('2 mismatches');
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
    assert
      .dom('.prflags [data-test-state="mismatches"]')
      .hasText('4 mismatches');
  });

  test('1 opens Summary and 2 Board, in the order the tabs stand', async function (assert) {
    await visit('/pr/o/r/7/dashboard');

    await triggerEvent(document, 'keydown', { key: '1' });
    assert.strictEqual(currentURL(), '/pr/o/r/7/summary');

    await triggerEvent(document, 'keydown', { key: '2' });
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });
});
