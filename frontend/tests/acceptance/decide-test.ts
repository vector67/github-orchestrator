import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, fillIn, waitFor } from '@ember/test-helpers';
import {
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';

module('Acceptance | decide', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', etag: '"k1-v1"' }),
    ];
  });

  test('a verb with no dialog goes to its custom method under the thread tag', async function (assert) {
    board().conversations = [
      thread({ key: 'k1', etag: '"k1-v1"', state: 'waiting' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="unpark"]');

    assert.strictEqual(board().posted.length, 1);
    assert.strictEqual(
      board().posted[0]!.url,
      '/api/conversations/k1/operations:unpark',
    );
    assert.strictEqual(board().posted[0]!.ifMatch, '"k1-v1"');
    assert.deepEqual(board().posted[0]!.body, {});
  });

  test('a queued verb says so in a toast wearing the square it heads for', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="unpark"]');

    assert.dom('[data-test-toast]').hasText('Queued: bringing it back.');
    assert
      .dom('[data-test-toast] [data-test-square]')
      .hasAttribute('data-square', 'ready');
  });

  test('a queued verb reads the list again so the card shows it waiting', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');
    const before = board().askedFor(/\/api\/conversations$/).length;
    board().conversations = [
      thread({
        key: 'k1',
        etag: '"k1-v2"',
        state: 'waiting',
        operations: [summary({ id: 'op_1', kind: 'unpark', state: 'pending' })],
      }),
    ];

    await click('[data-test-decision="unpark"]');

    assert.strictEqual(
      board().askedFor(/\/api\/conversations$/).length,
      before + 1,
    );
    assert.dom('[data-test-decision]').doesNotExist('one operation at a time');
    assert.dom('#c-k1 [data-test-meta]').hasText('bringing it back…');
  });

  test('stop halts the work in flight', async function (assert) {
    board().conversations = [board().threadIn('working', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="stop"]');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'stop');
    assert
      .dom('[data-test-decision="reject"]')
      .doesNotExist(
        'reject turns down a finished proposal, and nothing has finished',
      );
  });

  test('a thread that moved is read again and the click is not repeated', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 412,
      code: 'precondition-failed',
      detail: 'thread k1 has moved',
    };
    board().conversations = [
      board().threadIn('waiting', { key: 'k1', etag: '"k1-v2"' }),
    ];

    await click('[data-test-decision="resolve"]');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted.length, 1, 'nothing is retried');
    assert.dom('[data-test-toast]').containsText('It has been read again');
    assert
      .dom('[data-test-decision="unpark"]')
      .exists('the buttons are drawn from the state the re-read gave');
  });

  test('a refusal says what the board said', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 409,
      code: 'operation-outstanding',
      detail: 'thread k1 already has an operation waiting',
    };

    await click('[data-test-decision="resolve"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-toast]').containsText('already on its way');
    assert
      .dom('[data-test-toast] [data-test-square]')
      .hasAttribute('data-square', 'failed');
  });

  test('a refusal the board has no words for is shown in its own', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 409,
      code: 'confirm-again',
      detail: 'the rebased fix reports tests failed; approve again to land it',
    };

    await click('[data-test-decision="approve"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-toast]').containsText('approve again to land it');
  });

  test('the pressed button says what it is doing until the board answers', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const release = board().hold(/operations:approve$/);
    await click('[data-test-decision="approve"]');

    const submitting = click('[data-test-dialog-submit]');
    await waitFor('[data-test-decision="approve"][disabled]');

    assert.dom('[data-test-decision="approve"]').includesText('Accepting…');
    assert.dom('[data-test-decision="reject"]').includesText('Reject');

    release();
    await submitting;
  });

  test('a reply is posted in the operator own words', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-reply-open]');
    await fillIn('[data-test-reply]', 'good point, done');
    await click('[data-test-reply-send]');

    assert.strictEqual(board().posted[0]!.verb, 'reply');
    assert.strictEqual(board().posted[0]!.ifMatch, '"k1-v1"');
    assert.deepEqual(board().posted[0]!.body, { body: 'good point, done' });
    assert.dom('[data-test-reply-open]').exists('the composer folds back up');
  });

  test('an empty reply cannot be posted at all', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-reply-open]');
    await fillIn('[data-test-reply]', '   ');

    assert.dom('[data-test-reply-send]').isDisabled();
    assert.strictEqual(board().posted.length, 0);
  });
});
