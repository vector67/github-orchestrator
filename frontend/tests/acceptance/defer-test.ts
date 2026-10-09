import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, fillIn, select } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';

module('Acceptance | defer', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      thread({
        key: 'k1',
        comments: [
          { id: 1, author: 'octocat', created_at: null, review_state: null },
        ],
        operations: [summary()],
      }),
    ];
    board().comments['k1'] = [comment({ author: 'octocat' })];
  });

  test('defer asks when it should come back', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="defer"]');

    assert.dom('[data-test-wake]').exists();
    assert.dom('[data-test-dialog-body]').doesNotExist('defer posts nothing');
  });

  test('defer warns that a reply wakes the thread whatever is picked', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="defer"]');

    assert
      .dom('[data-test-wake-by-reply]')
      .hasText('A reply to this thread will wake it automatically.');
  });

  test('a pr wake condition carries the number it was given', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="defer"]');

    await select('[data-test-wake]', 'pr');
    await fillIn('[data-test-wake-pr]', '99');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'defer');
    assert.deepEqual(board().posted[0]!.body, { until: 'pr:99' });
  });

  test('a pr wake with no number cannot be confirmed', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="defer"]');

    await select('[data-test-wake]', 'pr');

    assert
      .dom('[data-test-dialog-submit]')
      .isDisabled('a pr condition with no number would park by hand instead');
  });

  test('reject offers to delete your own comment too', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');

    await click('[data-test-delete]');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'reject');
    assert.deepEqual(board().posted[0]!.body, { delete_comment: true });
  });

  test('someone else’s comment is not yours to delete', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().comments['k1'] = [comment()];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-delete]').doesNotExist();
  });
  test('a wake condition you picked is asked about before it is dropped', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="defer"]');
    await select('[data-test-wake]', 'ci');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-close-ask]').exists();
  });

  test('a delete tick is asked about before it is dropped', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-delete]');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-close-ask]').exists();
  });
});
