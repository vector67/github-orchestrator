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
  waitUntil,
} from '@ember/test-helpers';
import {
  dashboard,
  factsFor,
  heldPr,
  runLedger,
  setupFakeBoard,
  thread,
  threadRow,
  WALL_GROUPS,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import { stubGitHub } from 'frontend/tests/helpers/browser';

const LIST = 5000;
const KEPT_PULL_REQUESTS = 'hub-pull-requests';

module('Acceptance | pr view', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);
  const github = stubGitHub(hooks);

  function onTheHub(...held: ReturnType<typeof heldPr>[]): void {
    board().serves = 'hub';
    board().held = held;
  }

  function three(): void {
    onTheHub(
      heldPr({
        number: 8,
        dashboard: {
          pr: { title: 'Tidy the importer' },
          threads: [threadRow('h1', 'ready', 'open', 'human')],
        },
      }),
      heldPr(),
      heldPr({
        number: 9,
        dashboard: {
          manager: { on_hold: true },
          system: { queued_events: 2, on_hold: true },
        },
      }),
    );
  }

  async function press(key: string): Promise<void> {
    await triggerEvent(document, 'keydown', { key });
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  function switcherOpen(): boolean {
    return (
      find('[data-test-switcher]')?.getAttribute('aria-hidden') === 'false'
    );
  }

  test('opening a pull request replaces the wall with it, on its Board, your move beside the title', async function (assert) {
    three();
    board().conversations = [thread({ key: 'k1' })];
    await visit('/');

    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-wall]').doesNotExist();
    assert.dom('[data-test-pr-title]').hasText('#7 PROJ-7 · Fix the widget');
    assert
      .dom('[data-test-pr-heading] + [data-test-your-move]')
      .hasText(
        'Next Human comments · 0/1 done · 1 to decide',
        'the move counts the thread the page read',
      );
    assert.deepEqual(texts('[data-test-tab]'), [
      'Board 1',
      'Dashboard 2',
      'Terminal 3',
      'Diff 4',
    ]);
    assert.dom('[data-test-tab="board"]').hasAttribute('aria-current', 'page');
    assert.dom('#c-k1').exists('the board is in the Board tab');
  });

  test('on the hub the bar beside PRs carries the watcher’s health', async function (assert) {
    onTheHub(heldPr());

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-switcher-open] + [data-test-pr-health]')
      .hasAttribute('title', 'no poll yet');
    assert
      .dom('[data-test-pr-health]')
      .doesNotHaveAttribute('data-test-health-alarm');
  });

  test('on the hub a watcher whose cycles fail is an alarm beside PRs', async function (assert) {
    onTheHub(heldPr());
    board().ledger = runLedger({ watcher: { last_error: 'gh: HTTP 502' } });

    await visit('/pr/o/r/7/dashboard');

    assert
      .dom('[data-test-pr-health][data-test-health-alarm]')
      .hasAttribute('title', 'polls failing: gh: HTTP 502');
  });

  test('on the hub a hub that stops answering is an alarm beside PRs', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7/dashboard');

    board().down = true;
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert
      .dom('[data-test-pr-health][data-test-health-alarm]')
      .hasAttribute('title', 'the board server is not answering');
  });

  test('the bar stays exactly as it was while a restarted hub waits for the watcher’s first cycle', async function (assert) {
    three();
    await visit('/pr/o/r/7/terminal');
    const before = find('[data-test-pr-bar]')?.outerHTML;

    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert.strictEqual(find('[data-test-pr-bar]')?.outerHTML, before);
    assert.dom('[data-test-banner]').doesNotExist();
  });

  test('the pull request’s keys work once it has been opened from the wall, and after a pick in the switcher', async function (assert) {
    three();
    await visit('/');
    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');

    await press('2');
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');

    await press('\\');
    await click('[data-test-switcher-row="o/r#8"]');
    await press('2');
    assert.strictEqual(currentURL(), '/pr/o/r/8/dashboard');

    await press('Escape');
    assert.strictEqual(currentURL(), '/');
    await press('j');
    assert.dom('[aria-current="true"][data-test-wall-row]').exists();
  });

  test('the Board tab keeps the board’s counts, New draft and Send review in its strip, and its two views', async function (assert) {
    onTheHub(heldPr());
    board().conversations = [
      board().threadIn('proposed', { key: 'k1' }),
      board().threadIn('proposed', { key: 'k2' }),
    ];
    await visit('/pr/o/r/7/conversations');

    assert
      .dom('[data-test-board-strip] [data-test-count="ready"]')
      .containsText('2');
    assert.dom('[data-test-board-strip] [data-test-new-draft]').exists();
    assert.dom('[data-test-board-strip] [data-test-send-review]').exists();

    await click('[data-test-view="board"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/board');
    assert.dom('[data-test-tab="board"]').hasAttribute('aria-current', 'page');
    assert.dom('[data-test-view="board"]').hasClass('active');
  });

  test('the bar and the Board tab show what needs you: the tab’s count, the move’s flags and the detailed reviewer', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: {
            ci_status: 'failing',
            merge_state: 'behind',
            unresolved_threads: 2,
          },
          status: { you_are_the_detailed_reviewer: true },
        },
      }),
    );
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];

    await visit('/pr/o/r/7');

    assert
      .dom('[data-test-tab="board"] [data-test-tab-count]')
      .hasText('1 ready');
    assert.deepEqual(texts('[data-test-pr-bar] [data-test-move-flag]'), [
      'Fix CI',
      'Rebase',
      '2 unresolved threads',
    ]);
    assert
      .dom('[data-test-move-flag="fix-ci"] .sq')
      .hasClass('alarm', 'Fix CI keeps the alarm CI failing had');
    assert
      .dom('[data-test-pr-bar] [data-test-flag]')
      .hasText('You are the detailed reviewer');
    assert
      .dom('[data-test-pr-bar] [data-test-flag]')
      .hasAttribute('title', /Detailed reviewer: @/);
    assert
      .dom('[data-test-github]')
      .hasAttribute('href', 'https://github.com/o/r/pull/7');
  });

  test('the bar shows only the flags the move names, whatever the status says', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          status: { needs_rebase: true },
        },
      }),
    );

    await visit('/pr/o/r/7');

    assert.dom('[data-test-pr-bar] [data-test-move-flag]').doesNotExist();
    assert.dom('[data-test-pr-bar]').doesNotIncludeText('CI failing');
  });

  test('a draft shows a Draft pill before its title and its next move muted', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: factsFor('fix-ci', { draft: true }),
        },
      }),
      heldPr({ number: 8 }),
    );

    await visit('/pr/o/r/7');

    assert
      .dom(
        '[data-test-pr-heading] [data-test-draft-pill] + [data-test-pr-title]',
      )
      .hasText('#7 PROJ-7 · Fix the widget');
    assert.dom('[data-test-draft-pill]').hasText('Draft');
    assert.dom('[data-test-your-move]').hasAttribute('data-muted');
    assert
      .dom('[data-test-your-move] [data-test-move-label]')
      .hasText('Next, when it’s ready');
    assert.deepEqual(texts('[data-test-pr-bar] [data-test-move-flag]'), [
      'Fix CI',
    ]);

    await visit('/pr/o/r/8');

    assert.dom('[data-test-draft-pill]').doesNotExist();
    assert.dom('[data-test-your-move]').doesNotHaveAttribute('data-muted');
    assert.dom('[data-test-your-move] [data-test-move-label]').hasText('Next');
  });

  test('the bar counts the comments on your pull request, and your threads on someone else’s', async function (assert) {
    onTheHub(
      heldPr(),
      heldPr({
        number: 8,
        dashboard: {
          pr: { author: 'erin' },
          facts: factsFor('await-author'),
        },
      }),
    );
    board().conversations = [
      board().threadIn('landed', { key: 'h1' }),
      board().threadIn('proposed', { key: 'h2' }),
      board().threadIn('queued', { key: 'h3' }),
      board().threadIn('resolved', { key: 'b1', author_kind: 'bot' }),
      board().threadIn('waiting', { key: 'b2', author_kind: 'bot' }),
    ];

    await visit('/pr/o/r/7');
    assert.deepEqual(texts('[data-test-pr-bar] [data-test-pr-count]'), [
      'Human comments 1/3 done',
      'Bot comments 2/2 done',
    ]);

    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('waiting', { key: 'w1' }),
      board().threadIn('waiting', { key: 'w2' }),
      board().threadIn('deferred', { key: 'd' }),
    ];
    await visit('/pr/o/r/8');
    assert.deepEqual(texts('[data-test-pr-bar] [data-test-pr-count]'), [
      'Your threads 1/4 answered',
    ]);
  });

  test('the bar counts the hub’s thread rows until the pull request’s threads have been read, then the threads', async function (assert) {
    const threads = [threadRow('k1', 'ready', 'open', 'human')];
    onTheHub(heldPr({ dashboard: { threads } }));
    board().manager = dashboard({ threads });
    board().conversations = [
      board().threadIn('landed', {
        key: 'k1',
        updated_at: '2026-10-08T09:00:00Z',
      }),
    ];
    const release = board().hold(/^\/pr\/o\/r\/7\/api\/conversations$/);

    void visit('/pr/o/r/7/dashboard');
    await waitUntil(() => find('[data-test-pr-heading]'));

    assert.deepEqual(texts('[data-test-pr-bar] [data-test-pr-count]'), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    release();
    await settled();
    assert.deepEqual(texts('[data-test-pr-bar] [data-test-pr-count]'), [
      'Human comments 1/1 done',
      'Bot comments 0/0 done',
    ]);
  });

  test('every link out to GitHub opens in a new tab', async function (assert) {
    onTheHub(heldPr());
    board().conversations = [thread({ key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    const outward = findAll('a[href^="https://github.com"]');

    assert.true(outward.length > 1);
    assert.deepEqual(
      outward.map((link) => [
        link.getAttribute('href'),
        link.getAttribute('target'),
      ]),
      outward.map((link) => [link.getAttribute('href'), '_blank']),
    );
  });

  test('1 and 2 walk the tabs, and the Dashboard tab holds the dashboard', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7');

    await press('2');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-tab="dashboard"]')
      .hasAttribute('aria-current', 'page');
    assert.dom('[data-test-dashboard]').exists();

    await press('1');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('Esc goes back to the wall, closing the switcher first', async function (assert) {
    three();
    await visit('/pr/o/r/7/dashboard');

    await press('\\');
    assert.true(switcherOpen());

    await press('x');
    assert.true(switcherOpen());
    assert.dom('[data-test-dismiss-confirm]').doesNotExist();

    await press('Escape');
    assert.false(switcherOpen());
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');

    await press('Escape');
    assert.strictEqual(currentURL(), '/');
    assert.dom('[data-test-wall]').exists();
  });

  test('a pull request off the wall is left out of the switcher', async function (assert) {
    onTheHub(
      heldPr(),
      heldPr({
        number: 8,
        dashboard: {
          facts: factsFor('not-reviewing'),
        },
      }),
    );
    await visit('/pr/o/r/7');

    await click('[data-test-switcher-open]');

    assert.deepEqual(
      findAll('[data-test-switcher-row]').map((one) =>
        one.getAttribute('data-test-switcher-row'),
      ),
      ['o/r#7'],
    );
  });

  test('a switcher row keeps its own element when another repo’s pull request with its number leaves', async function (assert) {
    const widgets = heldPr({ repo: 'acme/widgets' });
    onTheHub(heldPr({ repo: 'acme/gadgets' }), widgets);
    await visit('/pr/acme/widgets/7');
    await click('[data-test-switcher-open]');
    assert.deepEqual(
      findAll('[data-test-switcher-row]').map((one) =>
        one.getAttribute('data-test-switcher-row'),
      ),
      ['acme/gadgets#7', 'acme/widgets#7'],
    );
    const before = find('[data-test-switcher-row="acme/widgets#7"]');

    board().held = [widgets];
    await clock().tick(LIST);

    assert.strictEqual(
      find('[data-test-switcher-row="acme/widgets#7"]'),
      before,
    );
  });

  test('the switcher is closed until asked for and lists each pull request’s verb by group', async function (assert) {
    three();
    await visit('/pr/o/r/7');

    assert.false(switcherOpen());
    assert.dom('[data-test-switcher-open]').includesText('1 needs you');

    await click('[data-test-switcher-open]');

    assert.true(switcherOpen());
    assert.deepEqual(texts('[data-test-switcher] [data-test-switcher-group]'), [
      'Needs you 1',
      'Waiting on others 1',
      'On hold 1',
    ]);
    assert
      .dom('[data-test-switcher-group]')
      .hasClass('group-head', 'the switcher’s headers are the rail’s');
    assert.deepEqual(
      findAll('[data-test-switcher-row]').map((one) =>
        one.getAttribute('data-square'),
      ),
      ['ready', 'waiting-on-others', 'parked'],
    );
    assert.dom('[data-test-switcher-row] .sq').doesNotExist();
    assert.true(
      findAll('[data-test-switcher-row]').every((one) =>
        one.classList.contains('edge'),
      ),
      'the switcher’s rows take the edge the rail’s rows draw',
    );
    assert.deepEqual(texts('[data-test-switcher-row] [data-test-verb]'), [
      'Human comments · 0/1 done · 1 to decide',
      'Waiting on reviewers carol',
      'On hold, 2 events held',
    ]);
    assert
      .dom('[data-test-switcher-row="o/r#7"]')
      .hasAttribute('aria-current', 'true');
  });

  test('the switcher carries each pull request’s flags beside its verb', async function (assert) {
    onTheHub(
      heldPr({
        dashboard: {
          facts: { draft: true, unresolved_threads: 4 },
        },
      }),
      heldPr({ number: 8 }),
    );
    await visit('/pr/o/r/8');

    await click('[data-test-switcher-open]');

    assert.deepEqual(
      texts(
        '[data-test-switcher-row="o/r#7"] [data-test-verb] [data-test-move-flag]',
      ),
      ['Draft', '4 unresolved threads'],
    );
    assert
      .dom('[data-test-switcher-row="o/r#8"] [data-test-move-flag]')
      .doesNotExist();
  });

  test('the switcher keeps the last list it heard from the hub', async function (assert) {
    three();
    await visit('/pr/o/r/7');

    const kept = JSON.parse(
      localStorage.getItem(KEPT_PULL_REQUESTS) ?? 'null',
    ) as { pull_requests: { number: number }[] } | null;
    assert.deepEqual(
      kept?.pull_requests.map((pr) => pr.number),
      [8, 7, 9],
    );
  });

  test('the switcher lists the kept pull requests when the hub’s list is not answering', async function (assert) {
    three();
    localStorage.setItem(
      KEPT_PULL_REQUESTS,
      JSON.stringify({
        watching: 'o/r',
        groups: WALL_GROUPS,
        pull_requests: board().held,
      }),
    );
    board().broken = /\/api\/pull-requests$/;
    await visit('/pr/o/r/7');

    await click('[data-test-switcher-open]');

    assert.deepEqual(texts('[data-test-switcher-row] [data-test-verb]'), [
      'Human comments · 0/1 done · 1 to decide',
      'Waiting on reviewers carol',
      'On hold, 2 events held',
    ]);
  });

  test('picking a pull request in the switcher opens it on its Board and the switcher goes away', async function (assert) {
    three();
    await visit('/pr/o/r/7/dashboard');
    await press('\\');

    await click('[data-test-switcher-row="o/r#8"]');

    assert.strictEqual(currentURL(), '/pr/o/r/8/conversations/h1');
    assert.false(switcherOpen());
    assert.dom('[data-test-pr-title]').hasText('#8 PROJ-7 · Tidy the importer');
  });

  test('[ and ] step to the previous and next pull request in wall order', async function (assert) {
    three();
    await visit('/pr/o/r/7');

    await press(']');
    assert.strictEqual(currentURL(), '/pr/o/r/9/conversations');

    await press('[');
    await press('[');
    assert.strictEqual(currentURL(), '/pr/o/r/8/conversations/h1');

    await press('[');
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/8/conversations/h1',
      'the first stays put',
    );
  });

  test('o opens the pull request on GitHub and y copies its address', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7/dashboard');

    await press('o');
    await press('y');

    assert.deepEqual(github().opened, ['https://github.com/o/r/pull/7']);
    assert.deepEqual(github().copied, ['https://github.com/o/r/pull/7']);
  });

  test('on the Board a key the board is offering stays the board’s: s asks to resolve, and the switcher stays shut', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await press('s');

    assert.false(switcherOpen());
    assert.dom('[data-test-dialog-question]').includesText('Resolve');
    assert.deepEqual(board().posted, []);
  });

  test('a held o opens the pull request on GitHub once', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7/dashboard');

    await press('o');
    await triggerEvent(document, 'keydown', { key: 'o', repeat: true });
    await triggerEvent(document, 'keydown', { key: 'o', repeat: true });

    assert.deepEqual(github().opened, ['https://github.com/o/r/pull/7']);
  });

  test('s never opens the switcher, even where no thread offers Resolve, so a press meant for it cannot resolve a thread on GitHub', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/pr/o/r/7/dashboard');

    await press('s');

    assert.false(switcherOpen());
    assert.deepEqual(board().posted, []);
  });

  test('on the Board Esc closes the open thread first, then goes to the wall', async function (assert) {
    onTheHub(heldPr());
    board().conversations = [thread({ key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await press('Escape');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');

    await press('Escape');
    assert.strictEqual(currentURL(), '/');
  });

  test('on the Board a decision key beats the pull request’s own: o steers the thread and opens nothing on GitHub', async function (assert) {
    onTheHub(heldPr());
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await press('o');

    assert.deepEqual(github().opened, []);
    assert.dom('[data-test-dialog-question]').includesText('steer');
  });

  test('the open switcher holds the board’s keys: j walks nothing and s asks nothing', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    board().conversations = [
      board().threadIn('waiting', { key: 'k1' }),
      board().threadIn('waiting', { key: 'k2' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await press('\\');
    await press('j');
    await press('s');

    assert.true(switcherOpen());
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-dialog-question]').doesNotExist();
  });

  test('a key under an open dialog reaches neither the pull request nor the key help', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7/dashboard');
    await click('[data-test-control="dismiss"]');

    await press('1');
    await press('?');
    await press('o');
    await press('p');

    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
    assert.dom('[data-test-dismiss-confirm]').exists();
    assert.dom('[data-test-key-help]').doesNotExist();
    assert.deepEqual(github().opened, []);
    assert.deepEqual(board().posted, []);
  });

  test('Esc closes an open dialog before it leaves for the wall', async function (assert) {
    onTheHub(heldPr());
    await visit('/pr/o/r/7/dashboard');
    await click('[data-test-control="dismiss"]');

    await press('Escape');

    assert.dom('[data-test-dismiss-confirm]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');

    await visit('/pr/o/r/7/conversations');
    await click('[data-test-send-review]');

    await press('Escape');

    assert.dom('[data-test-review]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('a pull request whose board is down opens with its bar and says the board is unreachable', async function (assert) {
    onTheHub(heldPr({ board_url: null }));
    await visit('/');

    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    assert.dom('[data-test-pr-title]').hasText('#7 PROJ-7 · Fix the widget');
    assert
      .dom('[data-test-unreachable]')
      .includesText('PR #7’s board is not answering.');

    await clock().tick(LIST);

    assert
      .dom('[data-test-banner]')
      .doesNotExist(
        'the body already says it, and a banner would cover the bar',
      );
  });

  test('leaving a pull request mid-read for one whose board is down raises no banner', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8, board_url: null }));
    board().conversations = [thread({ key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');
    board().hold(/^\/pr\/o\/r\/7\/api\//);
    void clock().tick(LIST);

    await visit('/pr/o/r/8');

    assert.dom('[data-test-unreachable]').exists();
    assert.dom('[data-test-banner]').doesNotExist();
  });

  test('a board that comes back fills the Board tab on the next poll', async function (assert) {
    onTheHub(heldPr({ board_url: null }));
    board().conversations = [thread({ key: 'k1' })];
    await visit('/pr/o/r/7');

    board().held = [heldPr()];
    await clock().tick(LIST);

    assert.dom('[data-test-unreachable]').doesNotExist();
    assert.dom('#c-k1').exists();
  });

  test('on its own port a board shows its bar from its own dashboard, a way to the wall, and no switcher', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-pr-title]').hasText('#7 PROJ-7 · Fix the widget');
    assert
      .dom('[data-test-your-move]')
      .hasText('Next Waiting on reviewers carol');
    assert
      .dom('[data-test-wall-link]')
      .hasAttribute('href', 'http://127.0.0.1:8720');
    assert.dom('[data-test-switcher-open]').doesNotExist();

    await press('Escape');
    await press('Escape');
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations',
      'Esc never leaves the board’s page',
    );
  });
});
