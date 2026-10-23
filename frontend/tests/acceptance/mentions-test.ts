import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, visit } from '@ember/test-helpers';
import {
  heldPr,
  outstandingMention,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

module('Acceptance | mentions', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('the counter in the top bar reads 0 when no mention is outstanding', async function (assert) {
    await visit('/');

    assert.dom('[data-test-mentions-count]').hasText('0');
  });

  test('the counter counts every outstanding mention and lists who wrote each one where', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
      outstandingMention({
        repo: 'acme/gadgets',
        number: 3,
        thread: 'k2',
        comment_id: 2,
        author: 'bob',
        on_board: false,
      }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mentions-count]').hasText('2');
    assert
      .dom('[data-test-mention]')
      .exists({ count: 2 }, 'one row for each mention');
    assert.dom('[data-test-mention="k1"]').includesText('anna');
    assert.dom('[data-test-mention="k1"]').includesText('o/r#7');
    assert.dom('[data-test-mention="k2"]').includesText('acme/gadgets#3');
  });

  test('a mention on the board opens its pull request at its thread', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [thread({ key: 'k1' })];
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];
    await visit('/');

    await click('[data-test-mentions-count]');
    await click('[data-test-mention="k1"] [data-test-mention-open]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('a mention not on the board says so and links to the comment on GitHub', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        on_board: false,
        url: 'https://github.com/o/r/pull/7#issuecomment-1',
      }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mention="k1"]').includesText('not on the board');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-github]')
      .hasAttribute('href', 'https://github.com/o/r/pull/7#issuecomment-1');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-open]')
      .doesNotExist();
  });

  test('the counter is in the top bar of a pull request’s page too', async function (assert) {
    board().held = [heldPr()];
    board().mentions.mentions = [outstandingMention()];

    await visit('/pr/o/r/7');

    assert.dom('[data-top-bar] [data-test-mentions-count]').hasText('1');
  });
});
