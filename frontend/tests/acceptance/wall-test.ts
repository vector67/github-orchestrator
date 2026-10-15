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
  waitUntil,
} from '@ember/test-helpers';
import type { HeldPullRequest, ThreadCounts } from 'frontend/data/api';
import {
  factsFor,
  finishedRun,
  heldPr,
  runLedger,
  setupFakeBoard,
  threadRow as row,
  WALL_GROUPS,
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

  function wallOf(held: unknown[], over: Record<string, unknown> = {}): string {
    return JSON.stringify({
      watching: ['o/r'],
      groups: WALL_GROUPS,
      pull_requests: held,
      ...over,
    });
  }

  function withoutDashboard(number: number): Partial<HeldPullRequest> {
    const held: Partial<HeldPullRequest> = { ...heldPr({ number }) };
    delete held.dashboard;
    return held;
  }

  function wallAnswers(body: string): void {
    const served = globalThis.fetch;
    globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      return new URL(url, 'http://127.0.0.1').pathname === '/api/pull-requests'
        ? Promise.resolve(
            new Response(body, {
              headers: { 'Content-Type': 'application/json' },
            }),
          )
        : served(input, init);
    };
  }

  function answerTheNextWallReadLate(): () => void {
    const served = globalThis.fetch;
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let used = false;
    globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const path = new URL(url, 'http://127.0.0.1').pathname;
      if (!used && path === '/api/pull-requests') {
        used = true;
        const answered = served(input, init);
        return gate.then(() => answered);
      }
      return served(input, init);
    };
    return release;
  }

  function tap(key: string): void {
    document.dispatchEvent(
      new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }),
    );
  }

  test('a wall shelved before dashboards carried threads does not stop the hub opening', async function (assert) {
    const { pr, polled, status, system, frozen, undismiss_command, notice } =
      heldPr().dashboard;
    localStorage.setItem(
      'hub-pull-requests',
      JSON.stringify({
        watching: ['o/r'],
        groups: [],
        pull_requests: [
          {
            ...heldPr(),
            dashboard: {
              pr,
              polled,
              status,
              system,
              frozen,
              undismiss_command,
              notice,
            },
          },
        ],
      }),
    );
    onTheHub(heldPr({ number: 8 }));

    await visit('/');

    assert.deepEqual(rows(), ['o/r#8']);
  });

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
      'Waiting on others 1',
      'Parked 2',
    ]);
    assert
      .dom('[data-test-wall-group="needs-you"]')
      .hasClass('group-head', 'the wall’s headers are the rail’s');
    assert
      .dom('[data-test-wall-group="needs-you"] .group-name + [data-test-count]')
      .hasText('1', 'the count sits right after the name');
    assert.deepEqual(rows(), ['o/r#8', 'o/r#7', 'o/r#9', 'o/r#10']);
    const lead = '[data-test-wall-row="o/r#8"] [data-test-wall-lead]';
    assert.deepEqual(
      texts(
        `${lead} [data-test-verb], ${lead} [data-test-reason], ${lead} [data-test-wall-title], ${lead} .meta`,
      ),
      [
        'Decide 1 fix',
        'human threads, 0 of 1 done',
        'Tidy the importer',
        '#8 · your PR · tidy',
      ],
    );
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

  test('a mention you have not answered needs you and names who, and answered ones wait on others', async function (assert) {
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
      'Waiting on others 1',
      'Parked 1',
    ]);
    assert.deepEqual(texts('[data-test-wall-row] [data-test-verb]'), [
      'Answer the mention',
      'Waiting on others',
      'On hold',
    ]);
    assert.deepEqual(texts('[data-test-wall-row] [data-test-reason]'), [
      'anna, bob mentioned you',
      'you are not a reviewer and every mention is answered',
      'resume it to let events through',
    ]);
  });

  test('a mention on a pull request that waits on others shows as a chip', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-author', {
            mentioned: true,
            mentions: [{ author: 'anna', at: null, answered: true }],
          }),
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), ['mentioned']);
  });

  function chips(key: string): string[] {
    return texts(`[data-test-wall-row="${key}"] [data-test-state]`);
  }

  function reasonOf(number: number): string {
    return texts(
      `[data-test-wall-row="o/r#${number}"] [data-test-reason]`,
    ).join('');
  }

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
      'On hold',
      'On hold',
      'Decide 2 fixes',
      'Send your review',
      'Re-review',
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
        'Waiting on the author',
        'Re-review',
        'Fix CI',
        'Waiting on the author',
        'Waiting on the author',
        'Agent is fixing 3 human threads',
        'Decide 2 bot fixes',
        'Agent is fixing 1 bot thread',
        'Address changes from bob, carol',
        'Waiting on carol to re-review',
        'Waiting on reviewers dave, erin',
      ],
    );
    assert.deepEqual([2, 3, 4, 5, 6, 7, 19, 20, 21].map(reasonOf), [
      '2 events wait until you resume it',
      'resume it to let events through',
      'human threads, 1 of 4 done',
      '1 unsent comment',
      'asked again · 1 of 2 of your threads answered',
      'running 1s',
      '2 of 5 done',
      'bot threads, 0 of 2 done',
      '1 of 2 done',
    ]);
    assert
      .dom('[data-test-wall-row="o/r#13"] .meta')
      .hasText("#13 · alice's PR · PROJ-7-fix-the-widget");
    assert
      .dom('[data-test-wall-row="o/r#18"] .meta')
      .hasText('#18 · reviewing · PROJ-7-fix-the-widget');
  });

  test('each row’s reason explains its move, from the facts the board sends', async function (assert) {
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
        facts: factsFor('await-author'),
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
        facts: factsFor('mark-ready-for-review'),
      }),
    );

    await visit('/');

    assert.deepEqual(
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19].map(
        reasonOf,
      ),
      [
        'lint, unit failing',
        'a check is failing',
        'conflicts with main',
        'requested changes and is not asked to review again',
        'asked again after requesting changes',
        'approved by erin, CI passing',
        'erin approved · review requested',
        'nobody is asked to review',
        '2 of 5 checks done',
        'requested from you · 3 files changed · no reviews yet',
        'asked again',
        'you commented',
        'you approved',
        'you approved · dave still requested',
        'you approved',
        'you approved · since then: force-pushed, 1 comment, 2 threads resolved',
        'requested from you · no reviews yet',
        'still a draft',
      ],
    );
  });

  test('a repo with no CI and no review rules is not said to be approved with CI passing', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('ready-to-merge', {
            ci_status: 'pending',
            review_decision: null,
          }),
          status: { approved_by: [], checks_done: 0, checks_total: 0 },
        },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'ready-to-merge');
    assert.deepEqual(
      [reasonOf(7), chips('o/r#7')],
      ['no approval needed, CI pending', []],
    );
  });

  test('a head with no checks reads as no CI', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('ready-to-merge', { ci_status: 'none' }),
          status: { approved_by: ['erin'] },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(
      [reasonOf(7), chips('o/r#7')],
      ['approved by erin, no CI', []],
    );
  });

  test('a branch only behind its base is not described as conflicting', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('rebase', { merge_state: 'behind' }),
          status: { mergeable: true, needs_rebase: true },
        },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'rebase');
    assert.deepEqual([chips('o/r#7'), reasonOf(7)], [[], 'behind main']);
  });

  test('the rebase move names the branch the pull request merges into', async function (assert) {
    onTheHub(
      needing(7, {
        pr: { base_branch: 'develop' },
        facts: factsFor('rebase'),
      }),
      needing(8, { pr: { base_branch: null }, facts: factsFor('rebase') }),
    );

    await visit('/');

    assert.deepEqual(verbsOf([7, 8]), [
      'Rebase on develop',
      'Rebase on the base branch',
    ]);
  });

  test('an approval on a repo without review rules shows as a chip', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-ci', { review_decision: null }),
          status: { approved_by: ['alice'] },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), ['approved by alice']);
  });

  test('a review request after others reviewed does not say "no reviews yet"', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('review', { review_decision: 'approved' }),
          status: { approved_by: ['alice'] },
        },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'review');
    assert.strictEqual(
      reasonOf(7),
      'requested from you · 3 files changed · alice approved',
    );
  });

  test('a reviewer who approved and was asked again is not both approved and awaited', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-review', {
            pending_reviewers: ['alice'],
            review_decision: 'review-required',
          }),
          status: { approved_by: ['alice'] },
        },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'await-review');
    assert.strictEqual(reasonOf(7), 'review requested');
  });

  test('after you approve, a reviewer who requested changes is not someone you wait on to review', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-reviewers', {
            review_decision: 'changes-requested',
            changes_requested_by: ['bob'],
            pending_reviewers: [],
          }),
        },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'await-author');
    assert.deepEqual(
      [reasonOf(7), chips('o/r#7')],
      ['you approved', ['bob requested changes']],
    );
  });

  test('a pull request whose author account was deleted is not called one you are reviewing', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: { pr: { author: null }, facts: factsFor('mention') },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'mention');
    assert
      .dom('[data-test-wall-row="o/r#7"] .meta')
      .hasText('#7 · PROJ-7-fix-the-widget');
  });

  const RLO = '\u202E';

  function boxOfCharacter(text: Node, at: number): DOMRect {
    const range = document.createRange();
    range.setStart(text, at);
    range.setEnd(text, at + 1);
    return range.getBoundingClientRect();
  }

  function readsAfter(later: DOMRect, earlier: DOMRect): boolean {
    if (later.top >= earlier.bottom) return true;
    return later.bottom > earlier.top && later.left > earlier.left;
  }

  test('a right-to-left override in a branch does not reverse the why text after it', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          manager: { frozen_on: 'x' },
          frozen: {
            worktree: '/wt',
            here: `${RLO}niam`,
            expected: 'tidy',
            seconds_left: 60,
            run_working: false,
            release_requested: false,
          },
        },
      }),
    );

    await visit('/');

    const text = find(
      '[data-test-wall-row="o/r#7"] [data-test-reason]',
    )!.firstChild!;
    const said = text.textContent!;
    const after = [...said]
      .map((character, at) => ({ character, at }))
      .filter(
        ({ character, at }) => at >= said.indexOf(')') && /\S/.test(character),
      );
    const backwards = after
      .slice(1)
      .filter(
        ({ at }, before) =>
          !readsAfter(
            boxOfCharacter(text, at),
            boxOfCharacter(text, after[before]!.at),
          ),
      )
      .map(({ character }) => character);
    assert.deepEqual(
      backwards,
      [],
      `the characters of "${said.slice(said.indexOf(')'))}" drawn before the one ahead of them`,
    );
  });

  test('a right-to-left override in a failing check name does not reverse the names after it', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('fix-ci'),
          status: { failed_checks: [`${RLO}tnil`, 'build', 'deploy'] },
        },
      }),
    );

    await visit('/');

    const text = find(
      '[data-test-wall-row="o/r#7"] [data-test-reason]',
    )!.firstChild!;
    const said = text.textContent!;
    const build = boxOfCharacter(text, said.indexOf('build'));
    const deploy = boxOfCharacter(text, said.indexOf('deploy'));
    assert.true(
      readsAfter(deploy, build),
      `"build" at (${Math.round(build.left)}, ${Math.round(build.top)}), "deploy" at (${Math.round(deploy.left)}, ${Math.round(deploy.top)})`,
    );
  });

  test('a row shows a chip only for a fact away from its quiet default, by severity, with only the one in the move’s way red', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          status: {
            mergeable: false,
            failed_checks: ['unit-tests'],
          },
          facts: factsFor('fix-ci', {
            review_decision: 'changes-requested',
            merge_state: 'conflicts',
          }),
          manager: { working_on: 'manual-continue' },
          threads: [row('h1', 'ready', 'open', 'human')],
          system: {
            agent: {
              name: 'Claude',
              enabled: true,
              state: 'working',
              event: 'manual-continue',
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

    assert.deepEqual(verbsOf([7]), ['Decide 1 fix']);
    assert.deepEqual(chips('o/r#7'), [
      'CI failing',
      'conflicts with main',
      'changes requested',
      'agent carrying on',
      '2 unpushed',
      '1 queued',
    ]);
    assert.deepEqual(
      texts('[data-test-wall-row="o/r#7"] [data-test-blocking]'),
      ['CI failing'],
    );
    assert.deepEqual(chips('o/r#8'), []);
    assert
      .dom('[data-test-wall-row="o/r#8"] [data-test-blocking]')
      .doesNotExist();
  });

  test('an agent run fixing the fact in the way leaves that fact’s chip out', async function (assert) {
    const running = (event: string) => ({
      name: 'Claude',
      enabled: true,
      state: 'working' as const,
      event,
      elapsed_seconds: 30,
      silent_seconds: null,
    });
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('fix-ci', { merge_state: 'behind' }),
          manager: { working_on: 'ci-failed' },
          system: { agent: running('ci-failed') },
        },
      }),
      heldPr({
        number: 8,
        dashboard: {
          facts: factsFor('rebase'),
          manager: { working_on: 'became-unmergeable' },
          system: { agent: running('became-unmergeable') },
        },
      }),
    );

    await visit('/');

    assert.deepEqual([chips('o/r#7'), chips('o/r#8')], [['behind main'], []]);
  });

  test('a fact on a pull request you only review is never red', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-rerequest', {
            ci_status: 'failing',
            merge_state: 'conflicts',
          }),
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), ['CI failing', 'conflicts with main']);
    assert.dom('[data-test-blocking]').doesNotExist();
  });

  test('the wall has no status columns and no column header', async function (assert) {
    onTheHub(heldPr());

    await visit('/');

    assert.dom('.wall-head').doesNotExist();
    assert.dom('[data-test-wall-head]').doesNotExist();
    assert.dom('[data-test-cell]').doesNotExist();
  });

  test('the move, its reason, its chips and its age share one line', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-review', { unresolved_threads: 2 }),
          system: { unpushed_commits: 3 },
        },
      }),
    );

    await visit('/');

    const middleOf = (selector: string) => {
      const box = find(
        `[data-test-wall-row="o/r#7"] ${selector}`,
      )!.getBoundingClientRect();
      return Math.round(box.top + box.height / 2);
    };
    const verb = middleOf('[data-test-verb]');
    assert.deepEqual(
      ['[data-test-reason]', '[data-test-state]', '[data-test-age]'].map(
        (selector) => Math.abs(middleOf(selector) - verb) <= 3,
      ),
      [true, true, true],
    );
  });

  test('negative counts read as none, not as a minus number', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          system: { unpushed_commits: -3, queued_events: -1 },
          facts: { unresolved_threads: -2 },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), []);
  });

  test('on someone else’s pull request the answered chip counts your threads answered, not other people’s threads', async function (assert) {
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

    assert.deepEqual(chips('o/r#8'), ['1 answered']);
  });

  test('unsent comments show as a chip until sending them is the move', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-author'),
          threads: [row('d', 'draft', 'draft', 'mine')],
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), ['1 unsent']);
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
      'working',
      'waiting-on-others',
      'parked',
      'draft',
    ]);
    assert.dom('[data-test-wall-row] [data-test-square]').doesNotExist();
    assert.true(
      findAll('[data-test-wall-row]').every((one) =>
        one.classList.contains('edge'),
      ),
      'the wall’s rows take the edge the rail’s rows draw',
    );
    assert.strictEqual(
      reasonOf(11),
      'wrong branch checked out (main) · detaches in 38m 0s',
    );
  });

  test('the detailed reviewer is a chip beside the move', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: { status: { you_are_the_detailed_reviewer: true } },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), ['detailed reviewer']);
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-state="reviewer"]')
      .hasAttribute('title', /Detailed reviewer: @/);
    assert.deepEqual(chips('o/r#8'), []);
  });

  test('facts the move does not name sit beside it as states, and a row without any has none', async function (assert) {
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

    assert.deepEqual(verbsOf([7]), ['Fix CI']);
    assert.deepEqual(chips('o/r#7'), [
      'conflicts with main',
      '1 unresolved',
      'draft',
    ]);
    assert.deepEqual(chips('o/r#8'), []);
  });

  test('every chip says what it means on hover', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('await-author', {
            draft: true,
            ci_status: 'failing',
            merge_state: 'conflicts',
            unresolved_threads: 1,
            changes_requested_by: ['bob'],
            mentioned: true,
          }),
          status: { you_are_the_detailed_reviewer: true },
          system: { unpushed_commits: 1, queued_events: 1 },
          threads: [
            row('d', 'draft', 'draft', 'mine'),
            row('m', 'ready', 'open', 'mine'),
          ],
        },
        mismatches: 2,
      }),
    );

    await visit('/');

    const untitled = findAll('[data-test-wall-row="o/r#7"] [data-test-state]')
      .filter((one) => !one.getAttribute('title'))
      .map((one) => one.textContent.trim());
    assert.true(chips('o/r#7').length >= 9, chips('o/r#7').join(', '));
    assert.deepEqual(untitled, []);
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

  const MINUTE = 60_000;
  const DAY = 24 * 60 * MINUTE;

  function minutesAgo(minutes: number): string {
    return new Date(clock().now - minutes * MINUTE).toISOString();
  }

  function ageOf(key: string): string {
    return texts(`[data-test-wall-row="${key}"] [data-test-age]`).join('');
  }

  test('each row ends its move line with how long it has been in its section, and starts again when it moves', async function (assert) {
    const lastEvent = { status: { last_event_at: minutesAgo(47) } };
    onTheHub(heldPr({ dashboard: lastEvent }));
    await visit('/');

    assert.strictEqual(ageOf('o/r#7'), '47m');
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-age]')
      .hasAttribute('title', 'In Waiting on others for 47m');

    board().held = [
      heldPr({ dashboard: { ...lastEvent, facts: factsFor('fix-ci') } }),
    ];
    await clock().tick(LIST);
    assert.strictEqual(ageOf('o/r#7'), 'now');

    await clock().tick(LIST * 24);
    assert.strictEqual(ageOf('o/r#7'), '2m');
  });

  test('a row remembers when it entered its section from an earlier visit', async function (assert) {
    localStorage.setItem(
      'hub-sections-entered',
      JSON.stringify({
        'o/r#7': { group: 'waiting-on-others', at: clock().now - 3 * DAY },
        'o/r#8': { group: 'needs-you', at: clock().now - 3 * DAY },
      }),
    );
    onTheHub(
      heldPr({ dashboard: { status: { last_event_at: minutesAgo(5) } } }),
      heldPr({
        number: 8,
        dashboard: { status: { last_event_at: minutesAgo(5) } },
      }),
    );

    await visit('/');

    assert.deepEqual(
      [ageOf('o/r#7'), ageOf('o/r#8')],
      ['3d', '5m'],
      'a section it has left since is not remembered',
    );
  });

  test('the tab title counts the pull requests that need you', async function (assert) {
    onTheHub(
      heldPr({ dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 8, dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 9 }),
    );
    await visit('/');

    assert.true(document.title.startsWith('(2) '), document.title);

    board().held = [heldPr({ number: 9 })];
    await clock().tick(LIST);

    assert.false(document.title.startsWith('('), document.title);
  });

  test('a section’s heading stays in view while its rows scroll under it', async function (assert) {
    onTheHub(
      ...Array.from({ length: 30 }, (_, at) =>
        heldPr({ number: at + 1, dashboard: { facts: factsFor('fix-ci') } }),
      ),
    );
    await visit('/');
    const body = find('.wall-body')!;
    const heading = find('[data-test-wall-group="needs-you"]')!;

    body.scrollTop = body.scrollHeight;
    await settled();

    const top = body.getBoundingClientRect().top;
    assert.true(
      Math.abs(heading.getBoundingClientRect().top - top) <= 1,
      `heading at ${Math.round(heading.getBoundingClientRect().top)}px, the wall’s body at ${Math.round(top)}px`,
    );
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

  test('k after the selected row leaves the wall lands next to where it was, not on the first row', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }), heldPr({ number: 9 }));
    await visit('/');
    await press('j');
    await press('j');
    await press('j');
    assert.deepEqual(selected(), ['o/r#9']);

    board().held = [heldPr(), heldPr({ number: 8 })];
    await clock().tick(LIST);
    assert.deepEqual(selected(), [], 'nothing is highlighted');

    await press('k');

    assert.deepEqual(selected(), ['o/r#8']);
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

  test('p pressed twice before the hub answers the first hold resumes, rather than holding twice', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    const release = board().hold(/\/api\/pull-requests\/o\/r\/7:/);

    tap('p');
    tap('p');
    release();
    await settled();

    assert.deepEqual(
      board().posted.map((one) => `${one.key} ${one.verb}`),
      ['o/r#7 hold', 'o/r#7 resume'],
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

  test('a dismiss question whose row leaves the wall does not come back by itself when the row returns', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    await press('x');
    assert.dom('[data-test-dismiss-confirm]').exists();

    board().held = [heldPr({ number: 8 })];
    await clock().tick(LIST);
    assert.dom('[data-test-dismiss-confirm]').doesNotExist();

    await press('j');
    assert.deepEqual(
      selected(),
      ['o/r#8'],
      'j moves again once the question went',
    );

    board().held = [heldPr(), heldPr({ number: 8 })];
    await clock().tick(LIST);

    assert
      .dom('[data-test-dismiss-confirm]')
      .doesNotExist('no question pops up that the user did not ask for now');
  });

  test('a dismiss question whose row changes section keeps the focus and still dismisses that row', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    await press('x');

    board().held = [
      heldPr({
        dashboard: { manager: { on_hold: true }, system: { on_hold: true } },
      }),
      heldPr({ number: 8 }),
    ];
    await clock().tick(LIST);

    assert.dom('[data-test-dismiss-confirm]').includesText('Dismiss #7?');
    assert.ok(
      find('[data-test-dismiss-confirm]')!.contains(document.activeElement),
      'the focus is still in the question',
    );
    await press('u');
    assert.deepEqual(verbs(), [
      '/pr/o/r/7/api/manager:dismiss {"forever":false}',
    ]);
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
      heldPr({ number: 8, dashboard: { standing: 'gone' } }),
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

  test('a wall read sent before a dismissal and answered after it does not bring the dismissed row back', async function (assert) {
    const listed = (at: string, ...numbers: number[]) =>
      numbers.map((number) => heldPr({ number, dashboard: { listed_at: at } }));
    onTheHub(...listed('2026-10-08T09:30:00Z', 7, 8));
    await visit('/');
    await press('j');
    await press('x');

    onTheHub(...listed('2026-10-08T09:30:30Z', 7, 8));
    const reads = board().askedFor(/\/api\/pull-requests$/).length;
    const release = answerTheNextWallReadLate();
    const ticking = clock().tick(LIST);
    try {
      await waitUntil(
        () => board().askedFor(/\/api\/pull-requests$/).length === reads + 1,
      );
      const served = globalThis.fetch;
      globalThis.fetch = async (input, init) => {
        const answer = await served(input, init);
        const url = input instanceof Request ? input.url : String(input);
        if (init?.method === 'POST' && url.endsWith('/api/manager:dismiss')) {
          onTheHub(...listed('2026-10-08T09:31:00Z', 8));
        }
        return answer;
      };
      tap('u');
      await waitUntil(() => !rows().includes('o/r#7'));
    } finally {
      release();
    }
    await ticking;
    await settled();

    assert.deepEqual(rows(), ['o/r#8'], 'the dismissed row stays gone');
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

  test('w pressed twice before the hub answers the first release sends one release', async function (assert) {
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
    const release = board().hold(/:release$/);

    tap('w');
    tap('w');
    release();
    await settled();

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
    board().held = [heldPr({ dashboard: { standing: 'gone' } })];
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

  test('a pull request opened while a dismissal from the wall is in flight stays open when the dismissal lands', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    await press('x');
    const release = board().hold(/\/api\/manager:dismiss$/);

    tap('u');
    await waitUntil(() => !find('[data-test-dismiss-confirm]'));
    tap('j');
    await waitUntil(() => selected()[0] === 'o/r#8');
    tap('Enter');
    await waitUntil(() => currentURL() === '/pr/o/r/8/conversations');

    release();
    await settled();

    assert.strictEqual(
      currentURL(),
      '/pr/o/r/8/conversations',
      'the dismissal did not pull the user back to the wall',
    );
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
    assert.true(reasonOf(8).startsWith('release asked for'), reasonOf(8));
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

  test('a pull-request address with a script scheme is not opened from the wall', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: { pr: { url: 'javascript:window.__wallPwned="url"' } },
      }),
    );
    await visit('/');
    await press('j');

    await press('o');

    assert.deepEqual(github().opened, []);
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

  test('an answer to an older wall poll that lands late does not bring back a row that left', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }), heldPr({ number: 9 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8', 'o/r#9']);

    onTheHub(heldPr(), heldPr({ number: 8 }));
    const reads = board().askedFor(/\/api\/pull-requests$/).length;
    const late = answerTheNextWallReadLate();
    void clock().tick(LIST);
    await waitUntil(
      () => board().askedFor(/\/api\/pull-requests$/).length === reads + 1,
    );

    onTheHub(heldPr());
    void clock().tick(LIST);
    await waitUntil(() => rows().length === 1, { timeout: 2000 });
    assert.deepEqual(rows(), ['o/r#7'], 'the newer poll took #8 and #9 away');

    late();
    await settled();

    assert.deepEqual(
      rows(),
      ['o/r#7'],
      'the older answer, landing last, put #8 back on the wall',
    );
  });

  test('two wall actions while one wall read is slow do not raise the outage banner or dim the wall', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    await press('j');
    const runs = board().askedFor(/\/api\/runs$/).length;
    const release = board().hold(/\/api\/pull-requests$/);
    const ticking = clock().tick(LIST);

    tap('p');
    await waitUntil(() => board().posted.length === 1);
    tap('j');
    tap('p');
    await waitUntil(() => board().posted.length === 2);
    await waitUntil(() => board().askedFor(/\/api\/runs$/).length === runs + 3);

    const banner = find('[data-test-banner]')?.textContent.trim() ?? null;
    const stale = find('[data-test-wall-stale]') !== null;
    release();
    await ticking;
    await settled();

    assert.strictEqual(banner, null, 'no outage banner while the hub answers');
    assert.false(stale, 'the wall is not dimmed as stale');
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

  test('a hub that restarted and has not finished its first cycle does not pass off the old rows as current', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');

    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    const told =
      find('[data-test-wall-unheld="watcher-starting"]') !== null ||
      find('[data-test-wall-stale]') !== null;
    assert.true(
      told,
      `three polls refused as watcher-starting, the page still shows ${rows().join(', ')} unmarked`,
    );
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

  test('a hub that stops watching after a good wall says so instead of showing the old rows as fresh', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8']);

    board().unheld = {
      code: 'not-watching',
      detail: 'config.toml names no repos',
    };
    board().state = 'setup';
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    const told =
      find('[data-test-wall-unheld="not-watching"]') !== null ||
      find('[data-test-wall-stale]') !== null;
    assert.true(
      told,
      `the hub refuses the wall as not-watching, yet the page shows ${rows().join(', ')} unmarked and never says why`,
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

  test('a hub holding only pull requests off the wall does not say it holds none', async function (assert) {
    onTheHub(heldPr({ dashboard: { facts: factsFor('not-reviewing') } }));

    await visit('/');

    assert
      .dom('[data-test-wall-row]')
      .doesNotExist('not-reviewing is off the wall');
    assert
      .dom('[data-test-wall-empty]')
      .doesNotIncludeText(
        'holds no pull requests',
        'the watcher holds one; it is just not shown',
      );
  });

  test('a wall body without its groups does not say the watcher holds nothing', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8']);

    wallAnswers(
      JSON.stringify({ watching: ['o/r'], pull_requests: [heldPr()] }),
    );
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-empty]')
      .doesNotExist(
        'a body missing `groups` wipes every row and claims the watcher holds no pull requests',
      );
  });

  test('what no poll has said yet reads as not known, never blank', async function (assert) {
    onTheHub(
      heldPr({
        manager: 'no-window',
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

    const lead = '[data-test-wall-row="o/r#7"] [data-test-wall-lead]';
    assert.deepEqual(
      texts(
        `${lead} [data-test-verb], ${lead} [data-test-reason], ${lead} [data-test-wall-title], ${lead} .meta`,
      ),
      [
        'Waiting for the first poll',
        'nothing known yet',
        'Title not known yet',
        '#7',
      ],
    );
  });

  test('a pull request not polled yet does not raise a conflicts alarm', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: { polled: false, facts: null, status: { mergeable: false } },
      }),
    );

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .hasAttribute('data-move', 'first-poll');
    assert.deepEqual(chips('o/r#7'), []);
  });

  test('a pull request GitHub is still checking for conflicts reads as not known, not as conflicting', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: { merge_state: 'unknown' },
          status: { mergeable: null },
        },
      }),
    );

    await visit('/');

    assert.deepEqual(chips('o/r#7'), []);
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

  test('a 2,000-character title does not take over the screen', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          pr: {
            title: 'lorem ipsum dolor sit amet '.repeat(80).slice(0, 2000),
          },
        },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/');

    const heightOf = (key: string) =>
      find(`[data-test-wall-row="${key}"]`)!.getBoundingClientRect().height;
    assert.true(
      heightOf('o/r#7') <= heightOf('o/r#8') * 3,
      `the long-titled row is ${Math.round(heightOf('o/r#7'))}px against ${Math.round(heightOf('o/r#8'))}px for a plain one`,
    );
  });

  test('an idle agent shows no chip unless its last run failed, which it names in words with how it ended', async function (assert) {
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

    assert.deepEqual(
      ['o/r#7', 'o/r#8', 'o/r#9'].map((key) => chips(key)),
      [[], ['last thread fix failed'], ['last review failed']],
    );
    assert.deepEqual(
      findAll('[data-test-state="runs"]').map((one) =>
        one.getAttribute('title'),
      ),
      [
        'The last run, a thread fix, ended 2m 0s ago: killed (SIGKILL)',
        'The last run, a review, ended 3h 0m ago: exit 1',
      ],
    );
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

    assert.deepEqual(
      ['o/r#7', 'o/r#8'].map((key) => chips(key)),
      [['2 failed runs'], []],
    );
    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-state="runs"]')
      .hasAttribute(
        'title',
        '2 runs failed in a row; the last, a thread fix, ended 2m 0s ago',
      );
  });

  test('a failed run with an unreadable end time does not print NaN', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({
      runs: [finishedRun({ failed: true, ended_at: 'not a time' })],
    });

    await visit('/');

    const said = find('[data-test-state="runs"]')!.getAttribute('title') ?? '';
    assert.false(said.includes('NaN'), `the runs chip says "${said}"`);
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

    assert.deepEqual(pulsing(), [true], 'work starting pulses');
    await clock().tick(4000);
    assert.deepEqual(pulsing(), [true]);
    await clock().tick(1000);
    assert.deepEqual(pulsing(), [false], 'then it holds steady');

    board().held = [working('became-unmergeable')];
    await clock().tick(LIST);
    assert.deepEqual(pulsing(), [true], 'a new move pulses again');
    await clock().tick(LIST);
    assert.deepEqual(pulsing(), [false]);
  });

  test('an agent run the manager reported does not outlive the manager going away', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('fix-ci'),
          manager: {
            working_on: 'ci-failed',
            changed_at: '2026-09-12T09:00:00.000000Z',
          },
          system: {
            agent: {
              name: 'Claude',
              enabled: true,
              state: 'working',
              event: 'ci-failed',
              elapsed_seconds: 30,
              silent_seconds: 1,
            },
          },
        },
      }),
    );
    await visit('/');
    assert.deepEqual(verbsOf([7]), ['Agent is fixing CI']);

    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('fix-ci'),
          standing: 'gone',
          manager: {
            working_on: null,
            changed_at: '2026-09-12T08:00:00.000000Z',
          },
        },
      }),
    );
    await clock().tick(LIST);

    assert.deepEqual(
      chips('o/r#7'),
      [],
      'no agent chip outlives the new dashboard',
    );
    assert.false(
      verbsOf([7])[0]!.startsWith('Agent is'),
      `the verb reads "${verbsOf([7])[0]}": it still says the agent works, from flags the hub stamped earlier than the dead manager did`,
    );
    assert
      .dom('[data-test-wall-group="agent-working"]')
      .doesNotExist('the row still sits under Agent working');
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

  test('a wall poll whose body will not take marks the wall stale after it keeps failing', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8']);

    wallAnswers(wallOf([heldPr(), withoutDashboard(8)]));
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-stale]')
      .exists(
        'three polls in a row brought a wall the page could not take, yet the wall does not say its rows are stale',
      );
  });

  test('a wall poll whose body breaks part-way is taken whole or not at all', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }), heldPr({ number: 9 }));
    await visit('/');
    assert.deepEqual(rows(), ['o/r#7', 'o/r#8', 'o/r#9']);

    wallAnswers(
      wallOf([
        heldPr({ dashboard: { pr: { title: 'Renamed on GitHub' } } }),
        withoutDashboard(8),
      ]),
    );
    await clock().tick(LIST);

    const title = texts(
      '[data-test-wall-row="o/r#7"] [data-test-wall-title]',
    ).join('');
    const halfTaken =
      title.includes('Renamed on GitHub') && rows().includes('o/r#9');
    assert.false(
      halfTaken,
      `half a poll was taken: #7 shows the new title (${title}) while #9, which that same poll dropped, is still on the wall (${rows().join(', ')})`,
    );
  });

  test('a half-taken wall body is not left on the shelf for the next visit', async function (assert) {
    onTheHub(heldPr());
    await visit('/');

    wallAnswers(wallOf([heldPr(), withoutDashboard(8)]));
    await clock().tick(LIST);

    const shelved = JSON.parse(
      localStorage.getItem('hub-pull-requests') ?? '',
    ) as { pull_requests: { dashboard?: unknown }[] };
    assert.true(
      shelved.pull_requests.every((one) => one.dashboard !== undefined),
      'the body the store could not take was shelved before it was read',
    );
  });

  test('a null list in one pull request’s facts does not take the whole wall down', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/');

    const eight = heldPr({ number: 8 });
    wallAnswers(
      wallOf([
        heldPr(),
        {
          ...eight,
          dashboard: {
            ...eight.dashboard,
            facts: { ...eight.dashboard.facts, pending_reviewers: null },
          },
        },
      ]),
    );
    await clock().tick(LIST);

    assert
      .dom('[data-test-wall-row="o/r#7"]')
      .exists('the healthy row still shows');
    assert.dom('[data-test-wall]').exists();
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

  test('a stale wall says in words that its rows may be out of date', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({
      watcher: {
        polled_at: new Date(clock().now - 600_000).toISOString(),
        overdue: true,
      },
    });

    await visit('/');

    assert
      .dom('[data-test-wall-stale-note]')
      .hasText('These rows may be out of date.');
  });

  test('the rows of a wall whose watcher polls on time are not marked stale', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({
      watcher: { polled_at: new Date(clock().now - 20_000).toISOString() },
    });

    await visit('/');

    assert.dom('[data-test-wall-stale]').doesNotExist();
    assert.dom('[data-test-wall-stale-note]').doesNotExist();
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
