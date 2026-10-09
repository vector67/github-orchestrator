import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  settled,
  triggerEvent,
  visit,
  waitFor,
} from '@ember/test-helpers';
import type { ThreadCounts } from 'frontend/data/api';
import {
  factsFor,
  finishedRun,
  heldPr,
  runLedger,
  setupFakeBoard,
  threadRow as row,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import { stubGitHub } from 'frontend/tests/helpers/browser';

const LIST = 5000;

module('Acceptance | wall', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);
  const github = stubGitHub(hooks);

  function onTheHub(...held: ReturnType<typeof heldPr>[]): void {
    board().serves = 'hub';
    board().held = held;
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  function rows(): string[] {
    return findAll('[data-test-wall-row]').map((one) =>
      one.getAttribute('data-test-wall-row')!,
    );
  }

  test('the hub opens on the wall, its groups in the feed’s order and each row led by its verb', async function (assert) {
    onTheHub(
      heldPr(),
      heldPr({
        number: 8,
        dashboard: {
          pr: { title: 'Tidy the importer', ticket: null, branch: 'tidy' },
          threads: [row('h1', 'ready', 'open', 'human')],
        },
      }),
      heldPr({
        number: 9,
        dashboard: {
          manager: { on_hold: true },
          system: { queued_events: 2, on_hold: true },
        },
      }),
      heldPr({
        number: 10,
        dashboard: { facts: factsFor('fix-ci', { draft: true }) },
      }),
    );

    await visit('/');

    assert.strictEqual(currentURL(), '/');
    assert.deepEqual(texts('[data-test-wall-group]'), [
      'Needs you 1',
      'Draft 1',
      'Waiting on others 1',
      'On hold 1',
    ]);
    assert
      .dom('[data-test-wall-group="needs-you"]')
      .hasClass('group-head', 'the wall’s headers are the rail’s');
    assert
      .dom('[data-test-wall-group="needs-you"] .group-name + [data-test-count]')
      .hasText('1', 'the count sits right after the name');
    assert.deepEqual(rows(), ['o/r#8', 'o/r#10', 'o/r#7', 'o/r#9']);
    const lead = '[data-test-wall-row="o/r#8"] [data-test-wall-lead] > *';
    assert.deepEqual(texts(lead), [
      'Human comments · 0/1 done · 1 to decide',
      'Tidy the importer',
      '#8 · your PR · tidy',
    ]);
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-wall-title]')
      .hasText('PROJ-7 · Fix the widget');
  });

  test('a pull request off the wall gets no row and no count', async function (assert) {
    onTheHub(
      heldPr(),
      heldPr({
        number: 8,
        dashboard: { facts: factsFor('closed') },
      }),
    );

    await visit('/');

    assert.deepEqual(rows(), ['o/r#7']);
    assert.deepEqual(texts('[data-test-wall-group]'), ['Waiting on others 1']);
  });

  test('a mention you have not answered needs you and names who, and answered ones sit in Mentioned below On hold', async function (assert) {
    onTheHub(
      heldPr({
        number: 8,
        dashboard: {
          pr: { author: 'alice' },
          facts: factsFor('mention', {
            mentions: [
              { author: 'anna', at: null, answered: false },
              { author: 'bob', at: null, answered: false },
            ],
          }),
        },
      }),
      heldPr({
        number: 9,
        dashboard: { pr: { author: 'alice' }, facts: factsFor('mentioned') },
      }),
      heldPr({
        number: 10,
        dashboard: { manager: { on_hold: true }, system: { on_hold: true } },
      }),
    );

    await visit('/');

    assert.deepEqual(texts('[data-test-wall-group]'), [
      'Needs you 1',
      'On hold 1',
      'Mentioned 1',
    ]);
    assert.deepEqual(texts('[data-test-wall-row] [data-test-verb]'), [
      'anna, bob mentioned you',
      'On hold',
      'Every mention answered',
    ]);
  });

  function threads(over: Partial<ThreadCounts>): ThreadCounts {
    return { queued: 0, live: 0, proposed: 0, drafts: 0, ...over };
  }

  function needing(number: number, dashboard: DashboardOver) {
    return heldPr({ number, dashboard });
  }

  function verbsOf(numbers: number[]): string[] {
    return numbers.map((number) => {
      const verb = find(
        `[data-test-wall-row="o/r#${number}"] [data-test-verb]`,
      );
      const own = [...(verb?.childNodes ?? [])].filter(
        (one) => one.nodeType === Node.TEXT_NODE,
      );
      return own
        .map((one) => one.textContent ?? '')
        .join('')
        .trim();
    });
  }

  test('each row words its move from the move the board names and the counts and people beside it', async function (assert) {
    const since = {
      commits: 0,
      force_pushed: true,
      reviews: 0,
      comments: 0,
      threads_resolved: 0,
    };
    onTheHub(
      needing(1, { manager: { frozen_on: 'another-pr' } }),
      needing(2, {
        manager: { on_hold: true },
        system: { on_hold: true, queued_events: 2 },
      }),
      needing(3, { manager: { on_hold: true }, system: { on_hold: true } }),
      needing(4, {
        threads: [
          row('a', 'done', 'resolved', 'human'),
          row('b', 'ready', 'open', 'human'),
          row('c', 'ready', 'open', 'human'),
          row('d', 'working', 'open', 'human'),
        ],
      }),
      needing(5, {
        facts: factsFor('rereview'),
        threads: [row('d', 'draft', 'draft', 'mine')],
      }),
      needing(6, {
        facts: factsFor('rereview'),
        threads: [
          row('a', 'ready', 'open', 'mine'),
          row('b', 'waiting', 'open', 'mine'),
        ],
      }),
      needing(7, {
        manager: { working_on: 'manual-continue' },
        system: {
          agent: {
            name: 'Claude',
            enabled: true,
            state: 'working',
            event: 'manual-continue',
            elapsed_seconds: 1,
            silent_seconds: null,
          },
        },
      }),
      needing(8, {
        facts: factsFor('review'),
        manager: { threads_live: 1 },
        system: { threads: threads({ live: 1 }) },
      }),
      needing(9, { facts: null, polled: false }),
      needing(10, { facts: factsFor('ready-to-merge') }),
      needing(11, { facts: factsFor('await-ci') }),
      needing(12, {
        facts: factsFor('await-reviewers', {
          pending_reviewers: ['dave', 'erin'],
        }),
      }),
      needing(13, {
        pr: { author: 'alice' },
        facts: factsFor('await-rerequest'),
      }),
      needing(14, {
        facts: factsFor('await-author', {
          review_decision: null,
          pending_reviewers: ['erin'],
        }),
        status: { since_you_last_acted: since },
      }),
      needing(15, { facts: factsFor('rereview') }),
      needing(16, { facts: factsFor('fix-ci') }),
      needing(17, {
        facts: factsFor('await-reviewers', { pending_reviewers: [] }),
      }),
      needing(18, {
        pr: { author: null },
        facts: factsFor('await-author'),
      }),
      needing(19, {
        threads: [
          row('a', 'done', 'resolved', 'human'),
          row('b', 'waiting', 'waiting_on_reviewer', 'human'),
          row('c', 'working', 'open', 'human'),
          row('d', 'queued', 'open', 'human'),
          row('e', 'landing', 'open', 'human'),
        ],
      }),
      needing(20, {
        threads: [
          row('a', 'ready', 'open', 'bot'),
          row('b', 'ready', 'open', 'bot'),
        ],
      }),
      needing(21, {
        threads: [
          row('a', 'done', 'resolved', 'bot'),
          row('b', 'working', 'open', 'bot'),
        ],
      }),
      needing(22, {
        facts: factsFor('address-feedback', {
          changes_requested_by: ['bob', 'carol'],
        }),
      }),
      needing(23, { facts: factsFor('await-rereview') }),
      needing(24, {
        facts: factsFor('await-review', {
          pending_reviewers: ['dave', 'erin'],
        }),
      }),
    );

    await visit('/');

    assert.deepEqual(verbsOf([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]), [
      'Release the worktree',
      'On hold, 2 events held',
      'On hold',
      'Human comments · 1/4 done · 2 to decide',
      'Send your review · 1 draft',
      'Re-review · 1/2 of your threads answered',
      'Agent is carrying on',
      'Agent is working on 1 thread',
      'Waiting for the first poll',
      'Ready to merge',
      'Waiting on CI',
      'Waiting on reviewers dave, erin',
    ]);
    assert.deepEqual(
      verbsOf([13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]),
      [
        'Waiting on the author to ask you again',
        'Waiting on the author · erin still requested',
        'Re-review · 0/0 of your threads answered',
        'Fix CI',
        'Waiting on reviewers',
        'Waiting on the author',
        'Human comments · 2/5 done · agent on 3',
        'Bot comments · 0/2 done · 2 to decide',
        'Bot comments · 1/2 done · agent on 1',
        'Address changes requested from bob, carol',
        'Waiting on carol to re-review',
        'Waiting on reviewers dave, erin',
      ],
    );
    assert
      .dom('[data-test-wall-row="o/r#13"] .meta')
      .hasText("#13 · alice's PR · PROJ-7-fix-the-widget");
    assert
      .dom('[data-test-wall-row="o/r#18"] .meta')
      .hasText('#18 · reviewing · PROJ-7-fix-the-widget');
  });

  test('each row’s why words what change detection says from the facts the board sends', async function (assert) {
    onTheHub(
      needing(1, {
        facts: factsFor('fix-ci'),
        status: { failed_checks: ['lint', 'unit'] },
      }),
      needing(2, { facts: factsFor('fix-ci') }),
      needing(3, { facts: factsFor('rebase') }),
      needing(4, {
        facts: factsFor('address-feedback', {
          changes_requested_by: ['erin'],
          unresolved_threads: 3,
        }),
      }),
      needing(5, { facts: factsFor('await-rereview') }),
      needing(6, {
        facts: factsFor('ready-to-merge'),
        status: { approved_by: ['erin'] },
      }),
      needing(7, {
        facts: factsFor('await-review'),
        status: { approved_by: ['erin'] },
      }),
      needing(8, {
        facts: factsFor('request-reviewers'),
      }),
      needing(9, {
        facts: factsFor('await-ci'),
        status: { checks_done: 2, checks_total: 5 },
      }),
      needing(10, {
        facts: factsFor('review', { ci_status: 'failing' }),
        status: { changed_files: 3 },
      }),
      needing(11, { facts: factsFor('rereview') }),
      needing(12, {
        facts: factsFor('await-rerequest', { unresolved_threads: null }),
      }),
      needing(13, { facts: factsFor('await-reviewers') }),
      needing(14, {
        facts: factsFor('await-author', {
          review_decision: null,
          pending_reviewers: ['dave'],
          unresolved_threads: 1,
        }),
      }),
      needing(15, { facts: factsFor('await-author') }),
      needing(17, {
        status: {
          since_you_last_acted: {
            commits: 3,
            force_pushed: true,
            reviews: 0,
            comments: 1,
            threads_resolved: 2,
          },
        },
      }),
      needing(18, {
        facts: factsFor('review'),
        status: { changed_files: null },
      }),
      needing(19, {
        facts: factsFor('await-reviewers', { pending_reviewers: [] }),
        status: { failed_checks: ['lint'] },
      }),
    );

    await visit('/');

    assert.deepEqual(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19].map(
        (number) =>
          texts(
            `[data-test-wall-row="o/r#${number}"] [data-test-cell="why"]`,
          ).join(''),
      ),
      [
        'Failed: lint, unit',
        'Fix CI failures',
        'Merge conflicts detected',
        'erin requested changes | 3 unresolved comments',
        'Waiting on carol to re-review',
        'Approved by erin | CI passing',
        'erin approved | Waiting on: carol',
        'No reviewers assigned',
        '2/5 checks complete',
        'CI failing | 3 files changed | no reviews yet',
        'Re-review requested | CI passing',
        'Waiting for the author to ask you to review again',
        'You approved | Waiting on review from: carol',
        'You approved | dave still requested',
        'You approved',
        'Since you acted: force-pushed, 1 comment, 2 threads resolved',
        'CI passing | ? files changed | no reviews yet',
        'You approved',
      ],
    );
  });

  function cells(key: string): Record<string, string> {
    return Object.fromEntries(
      findAll(`[data-test-wall-row="${key}"] [data-test-cell]`).map((one) => [
        one.getAttribute('data-test-cell') ?? '',
        one.textContent.trim().replace(/\s+/g, ' '),
      ]),
    );
  }

  test('each row carries the wall’s fields from its dashboard, a zero as a dot and an alarm marked', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          status: {
            mergeable: false,
            failed_checks: ['unit-tests'],
          },
          facts: factsFor('fix-ci', { review_decision: 'changes-requested' }),
          manager: { working_on: 'ci-failed' },
          threads: [row('h1', 'ready', 'open', 'human')],
          system: {
            agent: {
              name: 'Claude',
              enabled: true,
              state: 'working',
              event: 'ci-failed',
              elapsed_seconds: 134,
              silent_seconds: 6,
            },
            queued_events: 1,
            unpushed_commits: 2,
          },
        },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/');

    assert.deepEqual(cells('o/r#7'), {
      why: 'Failed: unit-tests',
      ci: 'failing',
      merge: 'yes',
      review: 'changes requested',
      agent: 'CI fix · 2m 14s · 6s quiet',
      threads: '1 ready',
      ahead: '2',
      queue: '1',
    });
    assert
      .dom(
        '[data-test-wall-row="o/r#7"] [data-test-cell="ci"] [data-test-alarm]',
      )
      .exists();
    assert
      .dom(
        '[data-test-wall-row="o/r#7"] [data-test-cell="merge"] [data-test-alarm]',
      )
      .exists();
    assert.deepEqual(cells('o/r#8'), {
      why: 'Waiting on: carol',
      ci: 'passing',
      merge: 'none',
      review: 'pending',
      agent: 'idle',
      threads: '·',
      ahead: '·',
      queue: '·',
    });
    assert.dom('[data-test-wall-row="o/r#8"] [data-test-alarm]').doesNotExist();
  });

  test('the Threads cell on someone else’s pull request counts your threads answered, not other people’s threads', async function (assert) {
    onTheHub(
      heldPr({
        number: 8,
        dashboard: {
          facts: factsFor('review'),
          threads: [
            row('a', 'ready', 'open', 'human'),
            row('m', 'ready', 'open', 'mine'),
          ],
        },
      }),
    );

    await visit('/');

    assert.strictEqual(cells('o/r#8')['threads'], '1 answered');
  });

  test('each status cell names its column, for the narrow wall that folds the header away', async function (assert) {
    onTheHub(heldPr());

    await visit('/');

    assert.deepEqual(
      findAll(
        '[data-test-wall-row="o/r#7"] [data-test-cell]:not([data-test-cell="why"])',
      ).map((one) => [
        one.getAttribute('data-test-cell'),
        one.getAttribute('data-label'),
      ]),
      [
        ['ci', 'CI'],
        ['merge', 'Conflicts'],
        ['review', 'Review'],
        ['agent', 'Agent'],
        ['threads', 'Threads'],
        ['ahead', 'Unpushed'],
        ['queue', 'Queue'],
      ],
    );
  });

  test('a row’s edge says who holds the ball, and a frozen pull request’s says failed, as the rail’s does', async function (assert) {
    onTheHub(
      heldPr({ dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({
        number: 12,
        dashboard: { facts: factsFor('fix-ci', { draft: true }) },
      }),
      heldPr({
        number: 8,
        dashboard: { manager: { working_on: 'ci-failed' } },
      }),
      heldPr({ number: 9 }),
      heldPr({
        number: 10,
        dashboard: { manager: { on_hold: true }, system: { on_hold: true } },
      }),
      heldPr({
        number: 11,
        dashboard: {
          manager: { frozen_on: 'main' },
          frozen: {
            worktree: '/wt',
            here: 'main',
            expected: 'tidy',
            seconds_left: 2280,
            run_working: false,
            release_requested: false,
          },
        },
      }),
    );

    await visit('/');

    const edges = findAll('[data-test-wall-row]').map((one) =>
      one.getAttribute('data-square'),
    );
    assert.deepEqual(edges, [
      'ready',
      'failed',
      'draft',
      'working',
      'waiting-on-others',
      'parked',
    ]);
    assert.dom('[data-test-wall-row] [data-test-square]').doesNotExist();
    assert.true(
      findAll('[data-test-wall-row]').every((one) =>
        one.classList.contains('edge'),
      ),
      'the wall’s rows take the edge the rail’s rows draw',
    );
    assert
      .dom('[data-test-wall-row="o/r#11"] [data-test-cell="why"]')
      .hasText('Wrong branch checked out (main) · detaches in 38m 0s');
  });

  test('the detailed reviewer is flagged beside the verb', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: { status: { you_are_the_detailed_reviewer: true } },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-verb] [data-test-flag]')
      .hasText('You are the detailed reviewer');
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-flag]')
      .hasAttribute('title', /Detailed reviewer: @/);
    assert.dom('[data-test-wall-row="o/r#8"] [data-test-flag]').doesNotExist();
  });

  test('the move’s flags sit beside the verb, and a row without any has none', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: {
            draft: true,
            ci_status: 'failing',
            merge_state: 'conflicts',
            unresolved_threads: 1,
          },
        },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/');

    assert.deepEqual(
      texts(
        '[data-test-wall-row="o/r#7"] [data-test-verb] [data-test-move-flag]',
      ),
      ['Draft', 'Fix CI', 'Rebase', '1 unresolved thread'],
    );
    assert
      .dom('[data-test-wall-row="o/r#8"] [data-test-move-flag]')
      .doesNotExist();
  });

  test('each column header says what its word means, and what a dot means', async function (assert) {
    onTheHub(heldPr());

    await visit('/');

    const heads = findAll('[data-test-wall-head]');
    assert.deepEqual(
      heads.map((one) => one.textContent.trim()),
      [
        'Your move, then the PR',
        'Why',
        'CI',
        'Conflicts',
        'Review',
        'Agent',
        'Threads',
        'Unpushed',
        'Queue',
      ],
    );
    assert.true(
      heads.every((one) => (one.getAttribute('title') ?? '').length > 0),
      'every header carries a definition',
    );
    const title = (label: string) =>
      heads
        .find((one) => one.textContent.trim() === label)!
        .getAttribute('title') ?? '';
    assert.true(title('Unpushed').includes('not yet pushed'));
    for (const counted of ['Threads', 'Unpushed', 'Queue']) {
      assert.true(title(counted).includes('A dot means none'), counted);
    }
    assert.true(title('Conflicts').includes('marked ready'));
    assert.true(title('Agent').includes('carry on'));
  });

  test('a row says it only opens the pull request', async function (assert) {
    onTheHub(heldPr());

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-wall-lead]')
      .hasAttribute('title', 'Open #7 · nothing runs until you choose');
  });

  test('a row that moved group says moved here until you open it', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    assert.dom('[data-test-moved]').doesNotExist('nothing has moved yet');

    board().held = [
      heldPr({ dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 8 }),
    ];
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-moved]')
      .hasText('moved here');
    assert.dom('[data-test-wall-row="o/r#8"] [data-test-moved]').doesNotExist();

    await clock().tick(LIST * 4);

    assert
      .dom('[data-test-moved]')
      .exists('still there however long you leave it');

    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');
    await visit('/');

    assert
      .dom('[data-test-moved]')
      .doesNotExist('gone once you have opened the pull request');
  });

  test('a pull request that leaves the wall and comes back starts fresh: it joins at the end and is not marked moved', async function (assert) {
    const ciFailing = { dashboard: { facts: factsFor('fix-ci') } };
    onTheHub(heldPr(ciFailing), heldPr({ ...ciFailing, number: 8 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8']);

    board().held = [heldPr({ ...ciFailing, number: 8 })];
    await clock().tick(LIST);
    assert.deepEqual(rows(), ['o/r#8']);

    board().held = [heldPr(ciFailing), heldPr({ ...ciFailing, number: 8 })];
    await clock().tick(LIST);

    assert.deepEqual(
      rows(),
      ['o/r#8', 'o/r#7'],
      'it joins behind the rows that stayed',
    );
    assert.dom('[data-test-moved]').doesNotExist();
  });

  test('a pull request that left in one group and comes back in another is not marked moved', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');

    board().held = [heldPr({ number: 8 })];
    await clock().tick(LIST);
    board().held = [
      heldPr({ dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 8 }),
    ];
    await clock().tick(LIST);

    assert.dom('[data-test-wall-row="o/r#7"]').exists();
    assert.dom('[data-test-moved]').doesNotExist();
  });

  test('a move from before you looked is not marked', async function (assert) {
    onTheHub(heldPr({ dashboard: { facts: factsFor('fix-ci') } }));

    await visit('/');

    assert.dom('[data-test-wall-row="o/r#7"]').exists();
    assert.dom('[data-test-moved]').doesNotExist();
  });

  async function press(key: string): Promise<void> {
    await triggerEvent(document, 'keydown', { key });
  }

  function selected(): string[] {
    return findAll('[data-test-wall-row][aria-current="true"]').map((one) =>
      one.getAttribute('data-test-wall-row')!,
    );
  }

  function verbs(): string[] {
    return board().posted.map(
      (one) => `${one.url} ${JSON.stringify(one.body)}`,
    );
  }

  test('j and k walk the rows and Enter opens the one you are on, on its Board', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');

    await press('j');
    assert.deepEqual(selected(), ['o/r#7']);
    await press('j');
    assert.deepEqual(selected(), ['o/r#8']);
    await press('k');
    assert.deepEqual(selected(), ['o/r#7']);

    await press('Enter');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    assert
      .dom('[data-test-wall]')
      .doesNotExist('the wall gives way to the pull request');
  });

  test('the selection stays on its pull request when the feed moves rows around it', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');

    board().held = [
      heldPr({ number: 8, dashboard: { facts: factsFor('fix-ci') } }),
      heldPr(),
    ];
    await clock().tick(LIST);

    assert.deepEqual(selected(), ['o/r#7']);
  });

  test('p holds the selected pull request and p again resumes it', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    await press('j');

    await press('p');
    await press('p');

    assert.deepEqual(
      board().posted.map((one) => `${one.key} ${one.verb}`),
      ['o/r#8 hold', 'o/r#8 resume'],
    );
  });

  test('the dashboard’s r, Q and g do nothing on the wall', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');

    await press('r');
    await press('Q');
    await press('g');

    assert.deepEqual(board().posted, []);
    assert.dom('[data-test-palette]').doesNotExist();
    assert.dom('[data-test-close-confirm]').doesNotExist();
    assert.dom('[data-test-toast]').doesNotExist();
  });

  test('the dismiss question takes the focus and holds j and k', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');

    await press('x');

    assert.ok(
      document
        .querySelector('[data-test-dismiss-confirm]')!
        .contains(document.activeElement),
      'the focus is in the question',
    );
    await press('j');
    assert.deepEqual(selected(), ['o/r#7']);

    await press('p');
    assert.dom('[data-test-dismiss-confirm]').exists();
    assert.deepEqual(verbs(), []);
  });

  test('x asks how long to dismiss for, u and f answer, Esc cancels', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');

    await press('x');

    assert.dom('[data-test-dismiss-confirm]').includesText('Dismiss #7?');
    assert
      .dom('[data-test-dismiss-confirm] [data-test-dismiss-option="u"]')
      .hasText('until next event u');
    assert
      .dom('[data-test-dismiss-confirm] [data-test-dismiss-option="f"]')
      .includesText('forever — removes the worktree');

    await press('Escape');
    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.deepEqual(verbs(), []);

    await press('x');
    await press('u');
    await press('j');
    await press('x');
    await press('f');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.deepEqual(verbs(), [
      '/pr/o/r/7/api/manager:dismiss {"forever":false}',
      '/pr/o/r/8/api/manager:dismiss {"forever":true}',
    ]);
  });

  test('x on a row whose board is not answering says dismiss waits for it and asks nothing', async function (assert) {
    onTheHub(
      heldPr({ dashboard: { standing: 'gone' } }),
      heldPr({ number: 8, board_url: null, dashboard: { standing: 'gone' } }),
    );
    await visit('/');

    for (const step of ['j', 'x', 'j', 'x']) await press(step);

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.deepEqual(
      texts('[data-test-toast]'),
      Array(2).fill(
        'Dismiss goes through the manager’s board, which is not answering.',
      ),
    );
    assert.deepEqual(verbs(), []);
  });

  test('a dismissal the manager does not take says so', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');
    board().broken = /\/api\/manager:dismiss$/;

    await press('x');
    await press('u');

    assert
      .dom('[data-test-toast]')
      .hasText(
        'The manager did not take the dismiss: the board server is not answering',
      );
  });

  test('a frozen row takes only w: p and x say so and send nothing, and w releases it', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          frozen: {
            worktree: '/wt',
            here: 'main',
            expected: 'tidy',
            seconds_left: 60,
            run_working: false,
            release_requested: false,
          },
        },
      }),
    );
    await visit('/');
    await press('j');

    await press('p');
    await press('x');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.deepEqual(
      texts('[data-test-toast]'),
      Array(2).fill('Only w works here: the worktree holds another branch.'),
    );
    assert.deepEqual(verbs(), []);

    await press('w');
    await press('w');

    assert.deepEqual(
      board().posted.map((one) => `${one.key} ${one.verb}`),
      ['o/r#7 release'],
    );
  });

  test('the dismiss confirmation is a modal dialog whose until-next-event button dismisses', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');

    await press('x');

    assert
      .dom('[data-test-dismiss-confirm]')
      .hasAttribute('role', 'dialog')
      .hasAttribute('aria-modal', 'true');

    await click('[data-test-dismiss-option="u"]');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.deepEqual(verbs(), [
      '/pr/o/r/7/api/manager:dismiss {"forever":false}',
    ]);
    assert
      .dom('[data-test-toast]')
      .hasText('Dismissed #7 until its next event. Its manager has exited.');
  });

  test('a pull request dismissed from the wall opens on its dismissal while its manager is gone', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');
    await press('x');
    await press('f');
    board().held = [
      heldPr({ board_url: null, dashboard: { standing: 'gone' } }),
    ];
    await clock().tick(LIST);

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-standing]')
      .hasText(
        'Dismissed #7 forever. Its manager has exited. This page has nothing more to show.',
      );
    await press('p');
    assert.deepEqual(verbs(), [
      '/pr/o/r/7/api/manager:dismiss {"forever":true}',
    ]);
  });

  test('a dismissal stops standing once the pull request’s manager answers again', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');
    await press('x');
    await press('u');

    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-standing]').doesNotExist();
    assert.dom('[data-test-action-band]').exists();
  });

  test('a frozen pull request offers Release on its row, and stops once it has been asked for', async function (assert) {
    onTheHub(
      heldPr(),
      heldPr({
        number: 8,
        dashboard: {
          manager: { frozen_on: 'main' },
          frozen: {
            worktree: '/wt',
            here: 'main',
            expected: 'tidy',
            seconds_left: 60,
            run_working: false,
            release_requested: false,
          },
        },
      }),
    );
    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-release]')
      .doesNotExist();

    await click('[data-test-wall-row="o/r#8"] [data-test-release]');

    assert.deepEqual(
      board().posted.map((one) => `${one.key} ${one.verb}`),
      ['o/r#8 release'],
    );
    assert.strictEqual(
      currentURL(),
      '/',
      'releasing does not open the pull request',
    );
    assert
      .dom('[data-test-wall-row="o/r#8"] [data-test-release]')
      .doesNotExist();
    assert
      .dom('[data-test-wall-row="o/r#8"] [data-test-cell="why"]')
      .includesText('Release asked for');
  });

  test('o opens the selected pull request on GitHub and y copies its address', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');

    await press('o');
    await press('y');

    assert.deepEqual(github().opened, ['https://github.com/o/r/pull/7']);
    assert.deepEqual(github().copied, ['https://github.com/o/r/pull/7']);
    assert.dom('[data-test-toast]').includesText('Copied');
  });

  test('a command the hub refuses says why in a toast', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    await press('j');
    board().refusal = {
      status: 404,
      code: 'not-found',
      detail: 'the watcher holds no pull request o/r#7',
    };

    await press('p');

    assert
      .dom('[data-test-toast]')
      .includesText('the watcher holds no pull request o/r#7');
  });

  test('the wall follows the watcher, asking with the tag it was last given', async function (assert) {
    onTheHub(heldPr());
    await visit('/');

    board().held = [heldPr(), heldPr({ number: 9 })];
    await clock().tick(LIST);

    assert.deepEqual(rows(), ['o/r#7', 'o/r#9']);
    const asked = board().askedFor(/^\/api\/pull-requests$/);
    assert.notStrictEqual(asked[asked.length - 1]!.ifNoneMatch, null);
  });

  test('a wall before the watcher’s first poll says it waits for it', async function (assert) {
    onTheHub();
    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };

    await visit('/');

    assert
      .dom('[data-test-wall-unheld="watcher-starting"]')
      .includesText('Waiting for the watcher’s first poll');
    assert.dom('[data-test-wall-empty]').doesNotExist();
  });

  test('a wall whose polls fail shows the error and its fix in place of waiting', async function (assert) {
    onTheHub();
    board().unheld = {
      code: 'watcher-failing',
      detail: 'gh auth token --user octocat failed (exit 1)',
    };
    board().ledger = runLedger({
      watcher: {
        last_error: 'gh auth token --user octocat failed (exit 1)',
        fix: 'Log in with `gh auth login`, then this page retries.',
      },
    });

    await visit('/');
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-fix]')
      .hasText('Log in with `gh auth login`, then this page retries.');
    assert
      .dom('[data-test-wall-error]')
      .hasText('gh auth token --user octocat failed (exit 1)');
    assert.dom('[data-test-wall-unheld="watcher-starting"]').doesNotExist();
    assert.dom('[data-test-banner]').doesNotExist();
    assert.dom('[data-test-wall-stale]').doesNotExist();
  });

  test('a wall whose hub went back to setup shows what its config lacks', async function (assert) {
    onTheHub();
    await visit('/');

    board().state = 'setup';
    board().unheld = {
      code: 'not-watching',
      detail:
        '~/.config/github-orchestrator/config.toml: the config file does not exist',
    };
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-unheld="not-watching"]')
      .includesText(
        '~/.config/github-orchestrator/config.toml: the config file does not exist',
      );
  });

  test('the wall fills in once a cycle succeeds after failing', async function (assert) {
    onTheHub(heldPr());
    board().unheld = { code: 'watcher-failing', detail: 'gh: HTTP 502' };
    await visit('/');

    board().unheld = null;
    await clock().tick(LIST);

    assert.deepEqual(rows(), ['o/r#7']);
    assert.dom('[data-test-wall-unheld]').doesNotExist();
  });

  test('an empty wall says the watcher holds nothing yet', async function (assert) {
    onTheHub();

    await visit('/');

    assert.dom('[data-test-wall-empty]').exists();
  });

  test('what no poll has said yet reads as not known, never blank', async function (assert) {
    onTheHub(
      heldPr({
        manager: 'no-window',
        board_url: null,
        dashboard: {
          standing: 'gone',
          pr: {
            title: null,
            url: null,
            author: null,
            ticket: null,
            branch: null,
          },
          polled: false,
          facts: null,
        },
      }),
    );

    await visit('/');

    assert.deepEqual(
      texts('[data-test-wall-row="o/r#7"] [data-test-wall-lead] > *'),
      ['Waiting for the first poll', 'Title not known yet', '#7'],
    );
    assert
      .dom('[data-test-cell="why"]')
      .hasText('Nothing known until the first poll');
  });

  test('a title that already leads with its ticket shows the ticket once', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          pr: {
            title: '[PROJ-31] Share one summary shape',
            ticket: 'PROJ-31',
          },
        },
      }),
      heldPr({
        number: 8,
        dashboard: {
          pr: { title: 'proj-32: Split the mapper', ticket: 'PROJ-32' },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(texts('[data-test-wall-title]'), [
      'PROJ-31 · Share one summary shape',
      'PROJ-32 · Split the mapper',
    ]);

    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');

    assert
      .dom('[data-test-pr-title]')
      .hasText('#7 PROJ-31 · Share one summary shape');
  });

  test('Claude’s column names the last run in words, not its event id, with how it ended', async function (assert) {
    const ago = (seconds: number) =>
      new Date(clock().now - seconds * 1000).toISOString();
    onTheHub(
      heldPr({
        dashboard: {
          system: {
            last_run: {
              event: 'became-unmergeable',
              exit_code: 0,
              ended_at: ago((17 * 24 + 15) * 3600),
            },
          },
        },
      }),
      heldPr({
        number: 8,
        dashboard: {
          system: {
            last_run: {
              event: 'thread-fix-PRRT_kwDOABCDEF5abc',
              exit_code: -9,
              ended_at: ago(120),
            },
          },
        },
      }),
      heldPr({
        number: 9,
        dashboard: {
          system: {
            last_run: {
              event: 'review-requested',
              exit_code: 1,
              ended_at: ago(3 * 3600),
            },
          },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(texts('[data-test-cell="agent"]'), [
      'idle · last rebase on main ok 17d 15h ago',
      'idle · last thread fix killed (SIGKILL) 2m 0s ago',
      'idle · last review exit 1 3h 0m ago',
    ]);
  });

  test('a pull request whose newest runs failed is marked failed in Claude’s column, counting them', async function (assert) {
    const ago = (seconds: number) =>
      new Date(clock().now - seconds * 1000).toISOString();
    onTheHub(heldPr(), heldPr({ number: 8 }));
    board().ledger = runLedger({
      runs: [
        finishedRun({
          event: 'thread-fix-PRRT_b',
          exit_code: 1,
          failed: true,
          ended_at: ago(120),
        }),
        finishedRun({ number: 8, ended_at: ago(150) }),
        finishedRun({
          event: 'thread-fix-PRRT_a',
          exit_code: 1,
          failed: true,
          ended_at: ago(180),
        }),
        finishedRun({
          number: 8,
          exit_code: 1,
          failed: true,
          ended_at: ago(200),
        }),
        finishedRun({ ended_at: ago(240) }),
      ],
    });

    await visit('/');

    assert.deepEqual(texts('[data-test-cell="agent"]'), [
      'idle · 2 failed runs, last thread fix 2m 0s ago',
      'idle',
    ]);
    assert
      .dom(
        '[data-test-wall-row="o/r#7"] [data-test-cell="agent"] [data-test-alarm]',
      )
      .exists();
    assert
      .dom(
        '[data-test-wall-row="o/r#8"] [data-test-cell="agent"] [data-test-alarm]',
      )
      .doesNotExist();
  });

  test('a live dot pulses for five seconds when work starts or its move changes, then holds steady', async function (assert) {
    const working = (event: string) =>
      heldPr({
        dashboard: {
          manager: { working_on: event },
          system: {
            agent: {
              name: 'Claude',
              enabled: true,
              state: 'working',
              event,
              elapsed_seconds: 1,
              silent_seconds: null,
            },
          },
        },
      });
    onTheHub(working('ci-failed'));
    await visit('/');
    const dots = '[data-test-wall-row="o/r#7"] .live-dot';
    const pulsing = () =>
      findAll(dots).map((dot) => dot.hasAttribute('data-pulsing'));

    assert.deepEqual(pulsing(), [true, true], 'work starting pulses');
    await clock().tick(4000);
    assert.deepEqual(pulsing(), [true, true]);
    await clock().tick(1000);
    assert.deepEqual(pulsing(), [false, false], 'then it holds steady');

    board().held = [working('became-unmergeable')];
    await clock().tick(LIST);
    assert.deepEqual(pulsing(), [true, true], 'a new move pulses again');
    await clock().tick(LIST);
    assert.deepEqual(pulsing(), [false, false]);
  });

  test('a wall whose hub stops answering says so and marks its rows stale', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    assert.dom('[data-test-banner]').doesNotExist();
    assert.dom('[data-test-wall-stale]').doesNotExist();

    board().down = true;
    await clock().tick(LIST);
    assert.dom('[data-test-banner]').doesNotExist('one miss is a blip');
    assert.dom('[data-test-wall-stale]').doesNotExist();
    await clock().tick(LIST);

    assert
      .dom('[data-test-banner]')
      .hasText('the board server is not answering');
    assert.dom('[data-test-wall-stale]').exists();
    assert.deepEqual(rows(), ['o/r#7'], 'the rows it had are still drawn');
  });

  test('a hub whose health answers while its reads do not says the system is under heavy load', async function (assert) {
    onTheHub(heldPr());
    await visit('/');

    board().broken = /\/api\/(pull-requests|runs)$/;
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert.dom('[data-test-banner]').hasText('the system is under heavy load');
    assert
      .dom('[data-test-health="poll"]')
      .hasText('the system is under heavy load');
  });

  test('a hub that answers again clears the banner and the stale mark', async function (assert) {
    onTheHub(heldPr());
    await visit('/');
    board().down = true;
    await clock().tick(LIST);
    await clock().tick(LIST);

    board().down = false;
    await clock().tick(LIST);

    assert.dom('[data-test-banner]').doesNotExist();
    assert.dom('[data-test-wall-stale]').doesNotExist();
  });

  test('a hub that leaves its refreshes unanswered for two refreshes is not answering', async function (assert) {
    onTheHub(heldPr());
    await visit('/');

    const release = board().hold(/\/api\/runs/);
    void clock().tick(LIST);
    void clock().tick(LIST);
    assert.dom('[data-test-banner]').doesNotExist();
    void clock().tick(LIST);
    await waitFor('[data-test-banner]');

    assert.dom('[data-test-wall-stale]').exists();
    release();
    await settled();
  });

  test('the rows of a wall whose watcher is overdue are marked stale', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({
      watcher: {
        polled_at: new Date(clock().now - 600_000).toISOString(),
        overdue: true,
      },
    });

    await visit('/');

    assert.dom('[data-test-wall-stale]').exists();
    assert.dom('[data-test-banner]').doesNotExist();
  });

  test('the rows of a wall whose watcher polls on time are not marked stale', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({
      watcher: { polled_at: new Date(clock().now - 20_000).toISOString() },
    });

    await visit('/');

    assert.dom('[data-test-wall-stale]').doesNotExist();
  });

  test('a row keeps its own element when another repo’s pull request with its number leaves the wall', async function (assert) {
    const widgets = heldPr({ repo: 'acme/widgets' });
    const gadgets = heldPr({ repo: 'acme/gadgets' });
    onTheHub(widgets, gadgets);
    await visit('/');
    assert.deepEqual(rows(), ['acme/gadgets#7', 'acme/widgets#7']);
    const before = find('[data-test-wall-row="acme/widgets#7"]');

    board().held = [widgets];
    await clock().tick(LIST);

    assert.deepEqual(rows(), ['acme/widgets#7']);
    assert.strictEqual(find('[data-test-wall-row="acme/widgets#7"]'), before);
  });
});
