import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';
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

  test('a pull request the watcher holds keeps its tabs and shows no not-found page', async function (assert) {
    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-tab]').exists({ count: 5 });
    assert.dom('[data-test-pr-not-found]').doesNotExist();
  });
});
