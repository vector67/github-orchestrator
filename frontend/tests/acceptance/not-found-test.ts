import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import { setupFakeBoard, thread } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

const UNHELD_TABS = [
  '/pr/o/r/9',
  '/pr/o/r/9/summary',
  '/pr/o/r/9/conversations',
  '/pr/o/r/9/dashboard',
  '/pr/o/r/9/terminal',
  '/pr/o/r/9/diff',
];

module('Acceptance | not found', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  test('a path the board never had says so instead of throwing', async function (assert) {
    await visit('/panel/PRRT_aa');

    assert
      .dom('[data-test-not-found]')
      .exists(
        'the old board left urls behind, and the router owns them all now',
      );
  });

  test('a pull request path with no number in it says so', async function (assert) {
    await visit('/pr/acme/widgets/latest');

    assert.dom('[data-test-not-found]').exists();
    assert.dom('[data-test-old-link]').doesNotExist();
  });

  for (const url of UNHELD_TABS) {
    test(`${url}, a pull request the watcher does not hold, keeps the top bar and says it is not watched in place of its tabs`, async function (assert) {
      await visit(url);

      assert.dom('[data-test-title-bar]').exists();
      assert.dom('[data-test-title-bar] [data-test-repo]').hasText('o/r#9');
      assert.dom('[data-test-pr-not-found]').exists();
      assert
        .dom('[data-test-pr-not-found] h1')
        .hasText('Pull request not found');
      assert
        .dom('[data-test-pr-not-found]')
        .includesText('o/r#9')
        .includesText(
          'only watches pull requests you wrote or were asked to review',
        );
      assert.dom('[data-test-pr-not-found] a[href="/"]').exists();
      assert.dom('[data-test-tab]').doesNotExist();
      assert.dom('[data-test-load-trouble]').doesNotExist();
    });
  }

  test('a pull request the watcher does not hold is never called an outage, however long it stays open', async function (assert) {
    await visit('/pr/o/r/9/conversations');
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert.dom('[data-test-pr-not-found]').exists();
    assert.dom('[data-test-banner]').doesNotExist();
    assert.dom(document.body).doesNotIncludeText('not answering');
    assert.dom(document.body).doesNotIncludeText('heavy load');
  });

  test('a board that stops answering is still an outage, not a pull request it lost', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    board().down = true;
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert
      .dom('[data-test-banner]')
      .hasText('the board server is not answering');
    assert.dom('[data-test-pr-not-found]').doesNotExist();
    assert.dom('[data-test-tab]').exists({ count: 5 });
  });

  test('a pull request opened before the restarted watcher’s first cycle says the server is starting, not that it is lost', async function (assert) {
    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-title-bar]').exists();
    assert
      .dom('[data-test-pr-starting]')
      .includesText('The server is starting up');
    assert.dom('[data-test-pr-not-found]').doesNotExist();
    assert.dom('[data-test-banner]').doesNotExist();
  });

  test('a pull request page waiting on the watcher’s first cycle opens its tabs once the cycle ends', async function (assert) {
    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };
    await visit('/pr/o/r/7/summary');

    board().unheld = null;
    await clock().tick(LIST);

    assert.dom('[data-test-pr-starting]').doesNotExist();
    assert.dom('[data-test-tab]').exists({ count: 5 });
  });

  test('a board opened during the watcher’s first cycle loads once the cycle ends instead of saying it could not load', async function (assert) {
    board().conversations = [thread({ key: 'k1' })];
    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };
    await visit('/pr/o/r/7/conversations');

    board().unheld = null;
    await clock().tick(LIST);

    assert.dom('[data-test-pr-starting]').doesNotExist();
    assert.dom('[data-test-load-trouble]').doesNotExist();
    assert.dom('#c-k1').exists();
  });

  test('the columns view opened during the watcher’s first cycle loads once the cycle ends instead of saying it could not load', async function (assert) {
    board().unheld = {
      code: 'watcher-starting',
      detail: 'the watcher has not finished its first cycle yet',
    };
    await visit('/pr/o/r/7/board');

    board().unheld = null;
    await clock().tick(LIST);

    assert.dom('[data-test-pr-starting]').doesNotExist();
    assert.dom('[data-test-load-trouble]').doesNotExist();
    assert.dom('[data-test-board-columns]').exists();
  });

  test('a pull request the watcher holds keeps its tabs and shows no not-found page', async function (assert) {
    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-tab]').exists({ count: 5 });
    assert.dom('[data-test-pr-not-found]').doesNotExist();
  });
});
