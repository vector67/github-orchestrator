import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  fillIn,
  find,
  findAll,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import {
  ONE_PR_READ,
  heldPr,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

module('Acceptance | hub', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(...held: ReturnType<typeof heldPr>[]): void {
    board().serves = 'hub';
    board().held = held;
  }

  test('on the hub the page asks for none of one pull request’s reads', async function (assert) {
    onTheHub(heldPr());

    await visit('/');
    await clock().tick(LIST);

    assert.deepEqual(
      board()
        .askedFor(ONE_PR_READ)
        .map((one) => one.url),
      [],
    );
  });

  test('a board still opens on its queue', async function (assert) {
    await visit('/');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('on its own port a board asks for its reads with no prefix', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.ok(board().askedFor(/^\/api\/conversations$/).length);
    assert.deepEqual(board().askedFor(/^\/pr\//), []);
  });

  test('a pull request opens in the page, every one of its reads going through the hub under its number', async function (assert) {
    onTheHub(heldPr());
    board().conversations = [thread({ key: 'k1' })];
    await visit('/');

    await click('[data-test-wall-row="o/r#7"] [data-test-wall-lead]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
    assert.dom('#c-k1').exists();
    assert.deepEqual(
      board()
        .askedFor(ONE_PR_READ)
        .map((one) => one.url),
      [],
    );
    assert.ok(board().askedFor(/^\/pr\/o\/r\/7\/api\/conversations$/).length);
  });

  function sameNumberInTwoRepos(): void {
    onTheHub(
      heldPr({
        repo: 'acme/widgets',
        dashboard: { pr: { title: 'Sharpen the widget' } },
      }),
      heldPr({
        repo: 'acme/gadgets',
        dashboard: { pr: { title: 'Polish the gadget' } },
      }),
    );
  }

  test('two pull requests with one number in two repos each open their own page', async function (assert) {
    sameNumberInTwoRepos();

    await visit('/pr/acme/widgets/7/conversations');

    assert.dom('[data-test-pr-title]').includesText('Sharpen the widget');

    await visit('/pr/acme/gadgets/7/conversations');

    assert.dom('[data-test-pr-title]').includesText('Polish the gadget');
    assert.ok(
      board().askedFor(/^\/pr\/acme\/gadgets\/7\/api\/pull-request$/).length,
    );
  });

  test('a row on the wall opens its own repo’s pull request when another repo has one with its number', async function (assert) {
    sameNumberInTwoRepos();
    await visit('/');

    await click('[data-test-wall-row="acme/gadgets#7"] [data-test-wall-lead]');

    assert.strictEqual(currentURL(), '/pr/acme/gadgets/7/conversations');
    assert.dom('[data-test-pr-title]').includesText('Polish the gadget');
  });

  test('an old link by number alone opens the one pull request held with that number', async function (assert) {
    onTheHub(heldPr({ repo: 'acme/widgets' }), heldPr({ number: 8 }));

    await visit('/pr/7');

    assert.strictEqual(currentURL(), '/pr/acme/widgets/7/conversations');
  });

  test('an old link into a pull request’s tab or thread lands on the same place under its repo', async function (assert) {
    onTheHub(heldPr({ repo: 'acme/widgets' }));
    board().conversations = [thread({ key: 'k1' })];

    await visit('/pr/7/dashboard');

    assert.strictEqual(currentURL(), '/pr/acme/widgets/7/dashboard');

    await visit('/pr/7/conversations/k1');

    assert.strictEqual(currentURL(), '/pr/acme/widgets/7/conversations/k1');
    assert.dom('#c-k1').exists();
  });

  test('an old link to a number two repos hold names both and opens the one picked', async function (assert) {
    sameNumberInTwoRepos();

    await visit('/pr/7/dashboard');

    assert.strictEqual(currentURL(), '/pr/7/dashboard');
    assert
      .dom('[data-test-old-link]')
      .includesText('#7 is held in more than one repo');
    assert.deepEqual(
      findAll('[data-test-old-link-choice]').map((one) =>
        one.textContent?.replace(/\s+/g, ' ').trim(),
      ),
      ['acme/gadgets#7 Polish the gadget', 'acme/widgets#7 Sharpen the widget'],
    );

    await click('[data-test-old-link-choice="acme/gadgets#7"]');

    assert.strictEqual(currentURL(), '/pr/acme/gadgets/7/dashboard');
  });

  test('an old link to a number no repo holds says so', async function (assert) {
    onTheHub(heldPr({ number: 8 }));

    await visit('/pr/7');

    assert.strictEqual(currentURL(), '/pr/7');
    assert.dom('[data-test-old-link]').includesText('holds no #7');
    assert.dom('[data-test-old-link-choice]').doesNotExist();
  });

  test('an old link on a board’s own port opens its pull request', async function (assert) {
    await visit('/pr/7/diff');

    assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
  });

  test('a write under a pull request on the hub goes through the hub', async function (assert) {
    onTheHub(heldPr());

    await visit('/pr/o/r/7/dashboard');
    await click('[data-test-control="hold"]');

    assert.deepEqual(
      board().posted.map((one) => one.url),
      ['/pr/o/r/7/api/manager:hold'],
    );
    assert.dom('[data-test-control="resume"]').exists();
  });

  test('the wall is one click back from a pull request, and the next one opened reads its own board', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/pr/o/r/7/conversations');

    await click('[data-test-wall-link]');

    assert.strictEqual(currentURL(), '/');

    await click('[data-test-wall-row="o/r#8"] [data-test-wall-lead]');

    assert.strictEqual(currentURL(), '/pr/o/r/8/conversations');
    assert.strictEqual(
      board().askedFor(/^\/pr\/o\/r\/8\/api\/pull-request$/).length,
      1,
    );
  });

  test('a review left open on one pull request is not carried into the next', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/pr/o/r/7/conversations');
    await click('[data-test-send-review]');
    await fillIn('[data-test-review-body]', 'for seven only');

    await click('[data-test-wall-link]');
    await click('[data-test-wall-row="o/r#8"] [data-test-wall-lead]');

    assert.dom('[data-test-review]').doesNotExist();
    await click('[data-test-send-review]');
    assert.dom('[data-test-review-body]').hasValue('');
  });

  test('the diff source picked on one pull request is not carried into the next', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/pr/o/r/7/diff');
    await click('[data-test-source="local"]');

    await visit('/pr/o/r/8/diff');

    assert
      .dom('[data-test-source="origin"]')
      .hasAttribute('aria-pressed', 'true');
    assert.deepEqual(
      board().askedFor(/^\/pr\/o\/r\/8\/api\/pull-request\/diff\?source=local/),
      [],
    );
  });

  test('a branch fetch the last pull request left in flight reads no diff when it lands', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    const release = board().hold(/^\/pr\/o\/r\/7\/api\/pull-request:fetch$/);
    const leaving = visit('/pr/o/r/7/diff');
    await waitUntil(() => find('[data-test-fetching]'));
    const opening = visit('/pr/o/r/8/diff');
    await waitUntil(
      () =>
        currentURL() === '/pr/o/r/8/diff' &&
        find('[data-test-pr-diff]') &&
        !find('[data-test-fetching]'),
    );
    const before = board().askedFor(/\/api\/pull-request\/diff/).length;

    release();
    await Promise.all([leaving, opening]);

    assert.strictEqual(
      board().askedFor(/\/api\/pull-request\/diff/).length,
      before,
    );
  });

  test('the Dashboard tab of the next pull request reads its own board afresh', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-wall-link]');
    await visit('/pr/o/r/8/dashboard');

    assert.deepEqual(
      board()
        .openStreams.map((one) => [
          new URL(one.url, 'http://127.0.0.1').pathname,
          one.lastEventId,
        ])
        .sort(),
      [
        ['/pr/o/r/8/api/dashboard/stream', null],
        ['/pr/o/r/8/api/manager/agent-output/stream', null],
        ['/pr/o/r/8/api/manager/changes/stream', null],
      ],
    );
  });

  test('a read the last pull request left in flight does not land in the next one', async function (assert) {
    onTheHub(heldPr(), heldPr({ number: 8 }));
    board().conversations = [thread({ key: 'k7' })];
    await visit('/pr/o/r/7/conversations/k7');
    board().hold(/^\/pr\/o\/r\/7\/api\/conversations$/);
    void clock().tick(LIST);

    board().conversations = [thread({ key: 'k8' })];
    const opening = visit('/pr/o/r/8/conversations');
    await waitUntil(() => find('#c-k8'));
    board().conversations = [thread({ key: 'late-from-7' })];
    board().releaseAll();
    await opening;

    assert.dom('#c-k8').exists();
    assert.dom('#c-late-from-7').doesNotExist();
    assert.dom('[data-test-banner]').doesNotExist();
    assert.deepEqual(board().reported, [], 'leaving a read is not a fault');
  });

  test('a board whose page cannot load says why', async function (assert) {
    board().broken = /\/api\/pull-request$/;

    await visit('/pr/o/r/7/conversations');

    assert
      .dom('[data-test-load-trouble]')
      .hasText('The board could not load: connection refused');
  });

  test('a board that cannot load says why under the top bar, which still leads back to the wall', async function (assert) {
    onTheHub(heldPr());
    board().broken = /\/api\/pull-request$/;

    await visit('/pr/o/r/7/conversations');

    assert
      .dom('[data-test-pr-view] [data-test-load-trouble]')
      .hasText('The board could not load: connection refused');
    await click('[data-test-wall-link]');
    assert.strictEqual(currentURL(), '/');
  });

  test('a held pull request whose board is not answering says so', async function (assert) {
    onTheHub(heldPr({ board_url: null }));

    await visit('/pr/o/r/7/conversations');

    assert
      .dom('[data-test-unreachable]')
      .includesText(
        'PR #7’s board is not answering. It may still be starting, be frozen on the wrong branch, or its manager may be down.',
      );
  });
});
