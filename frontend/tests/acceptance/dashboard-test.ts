import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  dashboard,
  factsFor,
  heldPr,
  setupFakeBoard,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const POLL = 1000;
const LIST = 5000;

const WORKING = {
  name: 'Claude',
  enabled: true,
  state: 'working' as const,
  event: 'ci-failed',
  elapsed_seconds: 134,
  silent_seconds: 6,
};

const DISABLED = {
  name: 'Claude',
  enabled: false,
  state: 'idle' as const,
  event: null,
  elapsed_seconds: null,
  silent_seconds: null,
};

const EARLIER_RUN = {
  event: 'ci-failed',
  exit_code: 0,
  ended_at: '2026-06-09T08:00:00Z',
};

const FROZEN = {
  worktree: '/Users/me/repositories/PROJ-7-fix-the-widget',
  here: 'PROJ-7-split-2',
  expected: 'PROJ-7-fix-the-widget',
  seconds_left: 2280,
  run_working: false,
  release_requested: false,
};

module('Acceptance | dashboard', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(over: DashboardOver = {}, boardUp = true): void {
    board().serves = 'hub';
    board().manager = dashboard(over);
    board().held = [
      heldPr({ dashboard: over, board_url: boardUp ? '/pr/o/r/7' : null }),
    ];
  }

  async function press(key: string): Promise<void> {
    await triggerEvent(document, 'keydown', { key });
  }

  function text(selector: string): string {
    return (document.querySelector(selector)?.textContent ?? '')
      .trim()
      .replace(/\s+/g, ' ');
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  function verbs(): string[] {
    return board().posted.map((one) => one.verb);
  }

  async function streamed(): Promise<void> {
    board().streamed();
    await clock().tick(POLL);
  }

  function ago(seconds: number): string {
    return new Date(clock().now - seconds * 1000).toISOString();
  }

  test('your pull request with nobody pending review asks you to request reviewers', async function (assert) {
    onTheHub({ facts: factsFor('request-reviewers') });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-band-move]').hasText('Request reviewers');
    assert.dom('[data-test-band-computed]').hasText('No reviewers assigned');
  });

  test('your draft with nobody pending review asks you to mark it ready for review', async function (assert) {
    onTheHub({ facts: factsFor('mark-ready-for-review') });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-band-move]').hasText('Mark ready for review');
    assert.dom('[data-test-band-computed]').hasText('No reviewers assigned');
  });

  test('the tab leads with the action band, then status and since you last acted, then system', async function (assert) {
    onTheHub({
      pr: { author: 'anna' },
      status: {
        since_you_last_acted: {
          commits: 4,
          force_pushed: false,
          reviews: 1,
          comments: 0,
          threads_resolved: 0,
        },
      },
    });

    await visit('/pr/o/r/7/dashboard');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-tab="dashboard"]')
      .hasAttribute('aria-current', 'page');
    const order = findAll(
      '[data-test-dashboard] [data-test-action-band], [data-test-dashboard] [data-test-block]',
    ).map((one) =>
      one.hasAttribute('data-test-action-band')
        ? 'action'
        : one.getAttribute('data-test-block'),
    );
    assert.deepEqual(order, ['action', 'status', 'since', 'system']);
    assert.dom('[data-test-band-label]').hasText('Next');
    assert.dom('[data-test-band-move]').hasText('Waiting on reviewers carol');
    assert
      .dom('[data-test-band-computed]')
      .hasText('PR state: Waiting for review · Waiting on: carol');
    assert.deepEqual(texts('[data-test-since] > span'), [
      '4 commits',
      '1 review',
    ]);
  });

  test('when your move and the PR state agree, the band gives the state’s detail alone', async function (assert) {
    onTheHub({
      facts: factsFor('fix-ci'),
      status: { failed_checks: ['unit-tests'] },
    });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-band-move]').hasText('Fix CI');
    assert.dom('[data-test-band-computed]').hasText('Failed: unit-tests');
  });

  test('the status block marks what is wrong and words the rest', async function (assert) {
    onTheHub({
      facts: { ci_status: 'failing', review_decision: 'changes-requested' },
      status: {
        mergeable: false,
        last_event_at: ago(3 * 3600),
        review_ready_at: ago(2 * 86400),
      },
    });

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(
      Object.fromEntries(
        findAll('[data-test-status]').map((one) => [
          one.getAttribute('data-test-status'),
          one.querySelector('[data-test-value]')?.textContent.trim(),
        ]),
      ),
      {
        reviewer: '@carol',
        ci: 'failing',
        mergeable: 'no',
        review: 'changes requested',
        'last-event': '3h ago',
        'review-ready': '2d ago',
      },
    );
    assert.dom('[data-test-status="ci"] [data-test-alarm]').exists();
    assert.dom('[data-test-status="mergeable"] [data-test-alarm]').exists();
    assert.dom('[data-test-status="review"] [data-test-alarm]').doesNotExist();
  });

  test('a conflict the agent is rebasing away reads as handled, and no reviewer reads as not assigned', async function (assert) {
    onTheHub({
      status: { mergeable: false, detailed_reviewer: null },
      system: { agent: { ...WORKING, event: 'became-unmergeable' } },
    });

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-status="mergeable"] [data-test-value]')
      .hasText('no, agent rebasing');
    assert
      .dom('[data-test-status="mergeable"] [data-test-alarm]')
      .doesNotExist();
    assert
      .dom('[data-test-status="reviewer"] [data-test-value]')
      .hasText('not assigned');
  });

  test('you as the detailed reviewer is the flag in place of the reviewer row', async function (assert) {
    onTheHub({ status: { you_are_the_detailed_reviewer: true } });

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-block="status"] [data-test-flag]')
      .hasText('You are the detailed reviewer');
    assert.dom('[data-test-status="reviewer"]').doesNotExist();
  });

  test('your review shows on a pull request you review and not on your own, nor does since you last acted', async function (assert) {
    onTheHub({
      facts: { is_author: false, my_review: 'changes-requested' },
      status: {
        since_you_last_acted: {
          commits: 0,
          force_pushed: false,
          reviews: 0,
          comments: 0,
          threads_resolved: 0,
        },
      },
    });
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-status="your-review"] [data-test-value]')
      .hasText('changes requested');
    assert.dom('[data-test-since]').hasText('nothing new');

    onTheHub();
    await streamed();

    assert.dom('[data-test-status="your-review"]').doesNotExist();
    assert.dom('[data-test-block="since"]').doesNotExist();
  });

  test('the system block says what Claude is doing, the queue, the threads and what is unpushed', async function (assert) {
    onTheHub({
      system: {
        agent: WORKING,
        queued_events: 10,
        unpushed_commits: 2,
        threads: { queued: 1, live: 2, proposed: 3, drafts: 0 },
      },
    });

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(
      Object.fromEntries(
        findAll('[data-test-system]').map((one) => [
          one.getAttribute('data-test-system'),
          one.querySelector('[data-test-value]')?.textContent.trim(),
        ]),
      ),
      {
        agent: 'working on CI fix, running 2m 14s, 6s since last output',
        queue: '10 pending',
        threads: '1 queued, 2 working, 3 ready',
        unpushed: '2 commits ahead',
      },
    );
  });

  test('an idle Claude gives its last run, how it ended and how long ago, and keeps counting', async function (assert) {
    onTheHub({
      system: {
        last_run: {
          event: 'became-unmergeable',
          exit_code: -9,
          ended_at: ago(50),
        },
        unpushed_commits: 0,
      },
    });
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-system="agent"] [data-test-value]')
      .hasText('idle, last rebase on main ended 50s ago, killed (SIGKILL)');
    assert.dom('[data-test-system="queue"] [data-test-value]').hasText('empty');
    assert
      .dom('[data-test-system="unpushed"] [data-test-value]')
      .hasText('up to date');

    await clock().tick(20 * POLL);

    assert
      .dom('[data-test-system="agent"] [data-test-value]')
      .hasText('idle, last rebase on main ended 1m 10s ago, killed (SIGKILL)');
  });

  test('a disabled Claude and an unknown unpushed count say so, and a run never seen says idle', async function (assert) {
    onTheHub({ system: { agent: DISABLED, unpushed_commits: null } });

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-system="agent"] [data-test-value]')
      .hasText('disabled in config.toml');
    assert.dom('[data-test-system="unpushed"]').doesNotExist();

    onTheHub();
    await streamed();

    assert.dom('[data-test-system="agent"] [data-test-value]').hasText('idle');
  });

  test('the system block names the agent this instance runs', async function (assert) {
    onTheHub({ system: { agent: { ...WORKING, name: 'Codex' } } });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-system="agent"] [data-test-label]').hasText('Codex');
  });

  test('a dashboard before the first poll says nothing is known yet', async function (assert) {
    onTheHub({
      polled: false,
      facts: null,
    });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-band-move]').hasText('Waiting for the first poll');
    assert
      .dom('[data-test-band-detail]')
      .hasText('Nothing known until the first poll');
    assert
      .dom('[data-test-block="status"]')
      .hasText('Status Waiting for the first poll');
    assert.dom('[data-test-status]').doesNotExist();
  });

  test('the manager’s notice is shown with the band', async function (assert) {
    onTheHub({ notice: 'an agent is already running' });

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-notice]').hasText('an agent is already running');
  });

  test("the agent's notes are drawn as markdown beside the blocks, and C turns to Claude's output and back", async function (assert) {
    onTheHub();
    board().changes = '# What changed\n\n- Renamed `write_iso`.\n';
    board().output = [
      { text: 'Reading src/writer.py', run_boundary: false },
      { text: '', run_boundary: true },
      { text: 'All 212 tests pass.', run_boundary: false },
    ];
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-notes] h1').hasText('What changed');
    assert.dom('[data-test-notes] li code').hasText('write_iso');
    assert.dom('[data-test-output]').doesNotExist();
    assert
      .dom('[data-test-pane-toggle="notes"]')
      .hasAttribute('aria-pressed', 'true');

    await press('C');

    assert.dom('[data-test-notes]').doesNotExist();
    const drawn = findAll('[data-test-output] li').map((one) =>
      one.hasAttribute('data-test-run-boundary')
        ? '--'
        : one.textContent.trim(),
    );
    assert.deepEqual(drawn, [
      'Reading src/writer.py',
      '--',
      'All 212 tests pass.',
    ]);
    assert
      .dom('[data-test-pane-toggle="agent"]')
      .hasAttribute('aria-pressed', 'true');

    await click('[data-test-pane-toggle="notes"]');

    assert.dom('[data-test-notes]').exists();
  });

  function saying(from: number, to: number) {
    return Array.from({ length: to - from }, (_, at) => ({
      text: `line ${from + at}`,
      run_boundary: false,
    }));
  }

  async function outputPane(): Promise<HTMLElement> {
    await press('C');
    const pane = find('[data-test-output]') as HTMLElement;
    pane.style.flex = 'none';
    pane.style.height = '200px';
    pane.scrollTop = pane.scrollHeight;
    await triggerEvent(pane, 'scroll');
    return pane;
  }

  function lineOnTop(pane: HTMLElement): { text: string; offset: number } {
    const top = pane.getBoundingClientRect().top;
    const line = findAll('[data-test-output] li').find(
      (one) => one.getBoundingClientRect().bottom > top,
    )!;
    return {
      text: line.textContent.trim(),
      offset: Math.round(line.getBoundingClientRect().top - top),
    };
  }

  function atTheEnd(pane: HTMLElement): boolean {
    return pane.scrollHeight - pane.scrollTop - pane.clientHeight < 1;
  }

  test('scrolled up, Claude’s output keeps the lines on screen where they are and counts the new ones below', async function (assert) {
    onTheHub();
    board().output = saying(0, 200);
    await visit('/pr/o/r/7/dashboard');
    const pane = await outputPane();
    pane.scrollTop = Math.round(pane.scrollHeight / 2);
    await triggerEvent(pane, 'scroll');
    const before = lineOnTop(pane);

    board().output = saying(30, 230);
    await streamed();

    assert.deepEqual(lineOnTop(pane), before, 'the line on top has not moved');
    assert.dom('[data-test-output-new]').hasText('30 new lines ↓');

    board().output = saying(35, 235);
    await streamed();

    assert.deepEqual(lineOnTop(pane), before);
    assert.dom('[data-test-output-new]').hasText('35 new lines ↓');

    await click('[data-test-output-new]');

    assert.true(atTheEnd(pane), 'the pill jumps to the end');
    assert.dom('[data-test-output-new]').doesNotExist();
  });

  test('at the end, Claude’s output follows the stream', async function (assert) {
    onTheHub();
    board().output = saying(0, 200);
    await visit('/pr/o/r/7/dashboard');
    const pane = await outputPane();

    board().output = saying(30, 230);
    await streamed();

    assert.true(atTheEnd(pane));
    assert.dom('[data-test-output-new]').doesNotExist();
    assert.dom('[data-test-output] li:last-child').hasText('line 229');
  });

  test('no notes and no output yet each say so', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-notes-empty]')
      .hasText('The agent has written no notes yet.');

    await press('C');

    assert
      .dom('[data-test-output-empty]')
      .hasText('The agent has said nothing on this pull request yet.');
  });

  function streamPaths(): string[] {
    return board()
      .openStreams.map((one) => new URL(one.url, 'http://127.0.0.1').pathname)
      .sort();
  }

  function notesStream() {
    return board().openStreams.find((one) =>
      one.url.includes('/manager/changes/stream'),
    );
  }

  test('the dashboard, the notes and Claude’s output arrive on streams as they change, and the tab polls for none of them', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(streamPaths(), [
      '/pr/o/r/7/api/dashboard/stream',
      '/pr/o/r/7/api/manager/agent-output/stream',
      '/pr/o/r/7/api/manager/changes/stream',
    ]);

    board().changes = 'Split the writer.';
    board().output = [{ text: 'Running the tests', run_boundary: false }];
    board().manager = dashboard({
      facts: {
        pending_reviewers: ['dave'],
        polled_at: '2026-09-12T08:31:00Z',
      },
    });
    board().streamed();
    await clock().tick(5 * POLL);

    assert.dom('[data-test-notes]').hasText('Split the writer.');
    assert.dom('[data-test-band-move]').hasText('Waiting on reviewers dave');
    await press('C');
    assert.dom('[data-test-output] li').hasText('Running the tests');
    assert.strictEqual(
      board().askedFor(
        /\/api\/(dashboard|manager\/changes|manager\/agent-output)(\?|$)/,
      ).length,
      0,
    );
  });

  test('leaving the tab or the pull request closes its streams', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');
    assert.strictEqual(board().openStreams.length, 3);

    await press('1');
    assert.deepEqual(board().openStreams, []);

    await visit('/pr/o/r/7/dashboard');
    assert.strictEqual(board().openStreams.length, 3);

    await visit('/');
    assert.deepEqual(board().openStreams, []);
  });

  test('a dropped stream keeps the last notes on show marked not live, and picks up from the last event it saw', async function (assert) {
    onTheHub();
    board().changes = 'Split the writer.';
    await visit('/pr/o/r/7/dashboard');
    const seen = notesStream()?.sent;

    board().down = true;
    board().dropStreams();
    await clock().tick(POLL);

    assert.dom('[data-test-notes]').hasText('Split the writer.');
    assert
      .dom('[data-test-pane-live]')
      .hasText('not live: the board is not answering');
    assert.dom('[data-test-not-live]').exists();

    board().down = false;
    await clock().tick(POLL);

    assert.strictEqual(notesStream()?.lastEventId, seen);
    assert.dom('[data-test-pane-live]').doesNotExist();
    assert.dom('[data-test-not-live]').doesNotExist();
    assert.dom('[data-test-notes]').hasText('Split the writer.');
  });

  test('hard-wrapped notes read as paragraphs, keeping headers, lists and code as they are', async function (assert) {
    onTheHub();
    board().changes = [
      '## Rebase on main',
      '',
      'main added CachedPricing beside the factory',
      'this PR removes.',
      '',
      '- Kept CachedPricing,',
      '  pointed at FlatPricing.',
      '- Dropped the factory.',
      '',
      '```',
      'uv run pytest',
      'git push',
      '```',
    ].join('\n');
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-notes] h2').hasText('Rebase on main');
    assert.dom('[data-test-notes] br').doesNotExist();
    assert
      .dom('[data-test-notes] p')
      .hasText('main added CachedPricing beside the factory this PR removes.');
    assert.dom('[data-test-notes] li').exists({ count: 2 });
    assert.strictEqual(
      find('[data-test-notes] pre')?.textContent,
      'uv run pytest\ngit push\n',
    );
  });

  test('p puts it on hold through the board and the band becomes the on-hold band with Resume; p again resumes', async function (assert) {
    onTheHub({
      facts: factsFor('fix-ci'),
      status: { failed_checks: ['unit-tests'] },
    });
    await visit('/pr/o/r/7/dashboard');

    await press('p');

    assert.deepEqual(verbs(), ['hold']);
    assert
      .dom('[data-test-action-band]')
      .hasAttribute('data-test-band', 'on-hold');
    assert.dom('[data-test-band-label]').hasText('Next · on hold');
    assert
      .dom('[data-test-band-detail]')
      .hasText('Underneath: Fix CI. Failed: unit-tests.');
    assert.dom('[data-test-control="resume"]').exists();

    await click('[data-test-control="resume"]');

    assert.deepEqual(verbs(), ['hold', 'resume']);
    assert.dom('[data-test-control="hold"]').exists();
  });

  test('r carries on, and Open the Board is offered where threads wait on you', async function (assert) {
    onTheHub({ system: { last_run: EARLIER_RUN } });
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/7/dashboard');

    await press('r');

    assert.deepEqual(verbs(), ['carry-on']);

    await click('[data-test-control="board"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('Open the Board only navigates, so it is secondary, and closing the pull request is destructive', async function (assert) {
    onTheHub({ system: { last_run: EARLIER_RUN } });
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-control="board"]')
      .hasClass('btn')
      .doesNotHaveClass('fill');
    assert.dom('[data-test-control="close"]').hasClass('danger');

    await click('[data-test-control="close"]');

    assert.dom('[data-test-close-option]').hasClass('danger');
  });

  test('carry on is held back with the reason on hover while Claude works or is disabled, and r says why', async function (assert) {
    onTheHub({ system: { agent: WORKING } });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="carry-on"]').isDisabled();
    assert
      .dom('[data-test-control="carry-on"]')
      .hasAttribute('title', 'The agent is already working.');
    assert.dom('.controls').doesNotIncludeText('The agent is already working.');

    await press('r');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-toast]').hasText('The agent is already working.');

    onTheHub({ system: { agent: DISABLED } });
    await streamed();

    assert
      .dom('[data-test-control="carry-on"]')
      .hasAttribute('title', 'Agents are disabled for this pull request.');
  });

  test('carry on is held back while there is no earlier run to carry on from, and says why instead of what it does', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="carry-on"]').isDisabled();
    assert
      .dom('[data-test-control="carry-on"]')
      .hasAttribute(
        'title',
        'The agent has no earlier run here to carry on from.',
      );
    assert
      .dom('.controls')
      .doesNotIncludeText(
        'The agent has no earlier run here to carry on from.',
      );

    await press('r');

    assert.deepEqual(verbs(), []);
  });

  test('a pull request waiting on your review offers to start a review agent, and a starts one', async function (assert) {
    for (const code of ['review', 'rereview'] as const) {
      onTheHub({ facts: factsFor(code) });
      await visit('/pr/o/r/7/dashboard');

      assert
        .dom('[data-test-control="start-review"]')
        .isNotDisabled()
        .hasAttribute('title', /\w/);
      assert
        .dom('[data-test-control="start-review"]')
        .includesText('Start a review agent');
    }

    await press('a');

    assert.deepEqual(verbs(), ['start-review']);
  });

  test('start a review agent is offered only when the next move is a review', async function (assert) {
    onTheHub({ system: { last_run: EARLIER_RUN } });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="start-review"]').doesNotExist();

    await press('a');

    assert.deepEqual(verbs(), []);
  });

  test('start a review agent is held back with the reason while Claude works or is disabled', async function (assert) {
    onTheHub({
      facts: factsFor('review'),
      system: { agent: WORKING },
    });
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-control="start-review"]')
      .isDisabled()
      .hasAttribute('title', 'The agent is already working.');

    await press('a');

    assert.deepEqual(verbs(), []);

    onTheHub({
      facts: factsFor('rereview'),
      system: { agent: DISABLED },
    });
    await streamed();

    assert
      .dom('[data-test-control="start-review"]')
      .hasAttribute('title', 'Agents are disabled for this pull request.');
  });

  test('each band button names what it acts on and says what it does', async function (assert) {
    onTheHub({ system: { last_run: EARLIER_RUN } });
    await visit('/pr/o/r/7/dashboard');

    const labelOf = (control: string) =>
      text(`[data-test-control="${control}"]`).replace(/ \S+$/, '');
    assert.strictEqual(labelOf('close'), 'Close PR #7');
    assert.strictEqual(labelOf('hold'), 'Put on hold');
    assert.strictEqual(labelOf('dismiss'), 'Dismiss #7');
    for (const control of ['close', 'hold', 'carry-on', 'dismiss']) {
      assert
        .dom(`[data-test-control="${control}"]`)
        .hasAttribute('title', /\w/, `${control} says what it does`);
    }
    assert
      .dom('[data-test-control="carry-on"]')
      .hasAttribute('title', /carrying on its last conversation/);

    await press('p');

    assert.strictEqual(labelOf('resume'), 'Resume the agent');
    assert.dom('[data-test-control="resume"]').hasAttribute('title', /\w/);
  });

  test('the detailed reviewer, the queue and what is unpushed each say what they mean', async function (assert) {
    onTheHub({ system: { unpushed_commits: 2 } });
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-status="reviewer"] [data-test-label]')
      .hasAttribute('title', /Detailed reviewer: @/);
    assert
      .dom('[data-test-system="queue"] [data-test-label]')
      .hasAttribute('title', /\w/);
    assert
      .dom('[data-test-system="unpushed"] [data-test-label]')
      .hasAttribute('title', /not yet pushed/);
    onTheHub({ status: { you_are_the_detailed_reviewer: true } });
    await streamed();

    assert
      .dom('[data-test-block="status"] [data-test-flag]')
      .hasAttribute('title', /Detailed reviewer: @/);
  });

  test('x asks first with the dashboard’s own wording, and Esc cancels without leaving the tab', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('x');

    assert.ok(
      document
        .querySelector('[data-test-dismiss-confirm]')!
        .contains(document.activeElement),
      'the question takes the focus',
    );
    assert.dom('[data-test-dismiss-confirm]').containsText('Dismiss #7?');
    assert.dom('[data-test-dismiss-option="u"]').hasText('until next event u');
    assert
      .dom('[data-test-dismiss-option="f"]')
      .hasText('forever — removes the worktree f');
    assert
      .dom('[data-test-dismiss-confirm] .dialog-actions button')
      .exists({ count: 2 });
    assert
      .dom('[data-test-dismiss-option="f"]')
      .hasAttribute(
        'title',
        'Stops the watcher tracking this PR. Reverse it with: github-orchestrator undismiss 7',
      );

    await press('Escape');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert.deepEqual(verbs(), []);
  });

  test('x then u dismisses until the next event and, the manager gone, the page goes back to the wall', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('x');
    await press('u');

    assert.deepEqual(board().posted.at(-1)?.verb, 'dismiss');
    assert.deepEqual(board().posted.at(-1)?.body, { forever: false });
    assert.strictEqual(currentURL(), '/');
    assert
      .dom('[data-test-toast]')
      .hasText('Dismissed #7 until its next event. Its manager has exited.');
  });

  test('the dismiss confirmation is a modal dialog whose forever button dismisses forever', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-control="dismiss"]');

    assert
      .dom('[data-test-dismiss-confirm]')
      .hasAttribute('role', 'dialog')
      .hasAttribute('aria-modal', 'true');

    await click('[data-test-dismiss-option="f"]');

    assert.deepEqual(board().posted.at(-1)?.verb, 'dismiss');
    assert.deepEqual(board().posted.at(-1)?.body, { forever: true });
  });

  test('on a board’s own port a dismissal says the manager has exited instead of calling it broken', async function (assert) {
    await visit('/pr/o/r/7/dashboard');

    await press('x');
    await press('f');
    board().down = true;
    await clock().tick(POLL);

    assert
      .dom('[data-test-standing]')
      .hasText(
        'Dismissed #7 forever. Its manager has exited. This page has nothing more to show.',
      );
  });

  test('c, which is Reply on the Board, closes nothing here', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('c');

    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert.deepEqual(verbs(), []);

    await press('w');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-control="release"]').doesNotExist();
  });

  test('Q asks before closing, and Esc cancels without closing', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('Q');

    assert.dom('[data-test-close-confirm]').containsText('Close #7 on GitHub?');

    await press('Escape');

    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert.deepEqual(verbs(), []);

    await press('Q');
    await press('p');

    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert.deepEqual(verbs(), []);
  });

  test('only a pull request you authored offers Close, by button or by Q', async function (assert) {
    for (const is_author of [false, null]) {
      onTheHub({ facts: { is_author } });
      await visit('/pr/o/r/7/dashboard');

      assert.dom('[data-test-control="close"]').doesNotExist();

      await press('Q');

      assert.dom('[data-test-close-confirm]').doesNotExist();
      assert.deepEqual(verbs(), []);
    }
  });

  test('the close confirmation is a modal dialog whose Close button closes the pull request', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-control="close"]');

    assert
      .dom('[data-test-close-confirm]')
      .hasAttribute('role', 'dialog')
      .hasAttribute('aria-modal', 'true');

    await click('[data-test-close-option]');

    assert.deepEqual(verbs(), ['close']);
    assert.dom('[data-test-close-confirm]').doesNotExist();
  });

  test('the Close button then y closes the pull request and says so', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-control="close"]');
    await press('y');

    assert.deepEqual(verbs(), ['close']);
    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert
      .dom('[data-test-toast]')
      .hasText(
        'Asked GitHub to close #7. The watcher tears it down on its next poll.',
      );
  });

  test('close waits for the board while it is down', async function (assert) {
    onTheHub({}, false);
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="close"]').isDisabled();

    await press('Q');

    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert
      .dom('[data-test-toast]')
      .hasText(
        'Close goes through the manager’s board, which is not answering.',
      );
  });

  test('a command the manager does not take says so', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');
    board().broken = /\/api\/manager:hold$/;

    await press('p');

    assert
      .dom('[data-test-toast]')
      .hasText(
        'The manager did not take the hold: the board server is not answering',
      );
  });

  test('a frozen pull request’s band asks for the release, with where the worktree is and both branches', async function (assert) {
    onTheHub({ frozen: FROZEN, manager: { frozen_on: FROZEN.here } }, false);

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-action-band]')
      .hasAttribute('data-test-band', 'frozen');
    assert.dom('[data-test-band-label]').hasText('Next · frozen');
    assert.dom('[data-test-band-move]').hasText('Release the worktree');
    assert
      .dom('[data-test-band-detail]')
      .hasText(
        'The worktree at ~/repositories/PROJ-7-fix-the-widget holds PROJ-7-split-2, not PROJ-7-fix-the-widget.',
      );
    assert
      .dom('[data-test-band-computed]')
      .hasText(
        'Event dispatch is frozen. No agent run is going. The watcher detaches it in 38m and builds a fresh one. Nothing in the directory is removed.',
      );
    assert.deepEqual(
      texts('[data-test-control]').map((one) => one.split(' ')[0]),
      ['Release'],
    );
    assert.deepEqual(
      findAll('[data-test-block]').map((one) =>
        one.getAttribute('data-test-block'),
      ),
      ['status', 'system'],
    );
  });

  test('w releases a frozen worktree through the hub, and the band then says it was asked for', async function (assert) {
    onTheHub({ frozen: FROZEN, manager: { frozen_on: FROZEN.here } }, false);
    await visit('/pr/o/r/7/dashboard');

    await press('w');

    assert.deepEqual(board().posted.at(-1)?.verb, 'release');
    assert.deepEqual(board().posted.at(-1)?.key, 'o/r#7');
    assert.dom('[data-test-control="release"]').isDisabled();
    assert
      .dom('[data-test-band-computed]')
      .hasText(
        'Release asked for. The watcher hands this directory over on its next poll and builds a fresh worktree.',
      );

    await press('w');

    assert.deepEqual(verbs(), ['release']);
  });

  test('while frozen only w acts: the other keys say so and send nothing', async function (assert) {
    onTheHub({ frozen: FROZEN, manager: { frozen_on: FROZEN.here } }, false);
    await visit('/pr/o/r/7/dashboard');

    await press('p');

    assert.deepEqual(verbs(), []);
    assert
      .dom('[data-test-toast]')
      .hasText('Only w works here: the worktree holds another branch.');
  });

  test('a board that is down shows the watcher’s dashboard, marked as not live, and holds through the hub', async function (assert) {
    onTheHub({}, false);

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-standing]').doesNotExist();
    assert.dom('[data-test-band-move]').hasText('Waiting on reviewers carol');
    assert
      .dom('[data-test-not-live]')
      .hasText(
        'Not live: the manager’s board is not answering, so this is the watcher’s view from disk. Carry on, dismiss and git wait for the board.',
      );
    assert.dom('[data-test-control="carry-on"]').isDisabled();
    assert.dom('[data-test-control="dismiss"]').isDisabled();
    assert
      .dom('[data-test-notes-empty]')
      .hasText(
        'The notes come from the manager’s board, which is not answering.',
      );

    await press('x');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert
      .dom('[data-test-toast]')
      .hasText(
        'Dismiss goes through the manager’s board, which is not answering.',
      );
    assert.deepEqual(verbs(), []);

    await press('p');

    assert.deepEqual(board().posted.at(-1)?.verb, 'hold');
    assert.deepEqual(board().posted.at(-1)?.key, 'o/r#7');
  });

  test('a board that comes back makes the tab live again', async function (assert) {
    const earlier = { system: { last_run: EARLIER_RUN } };
    onTheHub(earlier, false);
    await visit('/pr/o/r/7/dashboard');

    board().held = [heldPr({ dashboard: earlier })];
    await clock().tick(LIST);

    assert.dom('[data-test-not-live]').doesNotExist();
    assert.dom('[data-test-control="carry-on"]').isNotDisabled();
  });

  test('on a board’s own port a manager starting or a board gone says so', async function (assert) {
    board().manager = dashboard({ standing: 'starting' });
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-standing]').hasText('The manager is starting…');

    board().manager = dashboard();
    await streamed();
    assert.dom('[data-test-standing]').doesNotExist();
    assert.dom('[data-test-band-move]').hasText('Waiting on reviewers carol');

    board().down = true;
    board().dropStreams();
    await clock().tick(LIST);
    assert.dom('[data-test-standing]').hasText('Can’t reach the board server.');
    assert.dom('[data-test-control]').doesNotExist();
  });

  test('the system block says when it was last read', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-refreshed]').includesText('refreshed');
    assert.ok(/\d\d:\d\d:\d\d/.test(text('[data-test-refreshed]')));
  });

  test('on a board’s own port a board that never answers still opens the tab, and one that comes back is shown again', async function (assert) {
    board().down = true;
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-standing]').hasText('Can’t reach the board server.');

    board().down = false;
    await clock().tick(POLL);

    assert.dom('[data-test-standing]').doesNotExist();
    assert.dom('[data-test-band-move]').hasText('Waiting on reviewers carol');
  });

  test('a Claude working on no named event just says it is working, and a run with no exit code says so', async function (assert) {
    onTheHub({
      system: {
        agent: { ...WORKING, event: null, silent_seconds: null },
      },
    });
    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-system="agent"] [data-test-value]')
      .hasText('working, running 2m 14s');

    onTheHub({
      system: {
        last_run: {
          event: 'manual-continue',
          exit_code: null,
          ended_at: ago(5 - POLL / 1000),
        },
      },
    });
    await streamed();

    assert
      .dom('[data-test-system="agent"] [data-test-value]')
      .hasText('idle, last carry on ended 5s ago, exit unknown');
  });
});
