import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, currentURL, waitFor, waitUntil } from '@ember/test-helpers';
import { setupFakeBoard, thread } from 'frontend/tests/helpers/fake-board';

function commentsAskedFor(asked: { url: string }[]): string[] {
  return asked
    .map((one) => /\/api\/conversations\/([^/]+)\/comments$/.exec(one.url))
    .filter((match) => match !== null)
    .map((match) => decodeURIComponent(match[1]!));
}

module('Acceptance | preload', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('the board lands with the first row of the rail open', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      thread({ key: 'b' }),
      thread({ key: 'c' }),
    ];

    await visit('/');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
    assert.dom('#c-b').hasAttribute('aria-selected', 'true');
  });

  test('the queue lands with the first row open too', async function (assert) {
    board().conversations = [thread({ key: 'a' }), thread({ key: 'b' })];

    await visit('/pr/o/r/7/conversations');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/a');
  });

  test('an empty board opens nothing', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('the other threads wait until the open one has loaded', async function (assert) {
    board().conversations = [
      thread({ key: 'a' }),
      thread({ key: 'b' }),
      thread({ key: 'c' }),
    ];
    const release = board().hold(/\/conversations\/a\/comments$/);

    const visiting = visit('/pr/o/r/7/conversations');
    await waitFor('[data-test-loading="thread"]');

    assert.deepEqual(commentsAskedFor(board().asked), []);

    release();
    await visiting;

    assert.deepEqual(commentsAskedFor(board().asked), ['a', 'b', 'c']);
  });

  test('the rest load top to bottom, five at a time', async function (assert) {
    board().conversations = [
      thread({ key: 't0' }),
      thread({ key: 't1' }),
      thread({ key: 't2' }),
      thread({ key: 't3' }),
      thread({ key: 't4' }),
      thread({ key: 't5' }),
      board().threadIn('working', { key: 't6' }),
      board().threadIn('landed', { key: 't7' }),
    ];
    const release = board().hold(/\/conversations\/t2\/comments$/);

    const visiting = visit('/pr/o/r/7/conversations');
    await waitUntil(() => commentsAskedFor(board().asked).length === 5);

    assert.deepEqual(commentsAskedFor(board().asked), [
      't0',
      't1',
      't3',
      't4',
      't5',
    ]);

    release();
    await visiting;

    assert.deepEqual(commentsAskedFor(board().asked), [
      't0',
      't1',
      't3',
      't4',
      't5',
      't2',
      't6',
      't7',
    ]);
  });

  test('a thread opened by its link is loaded before the rest', async function (assert) {
    board().conversations = [
      thread({ key: 'a' }),
      thread({ key: 'b' }),
      thread({ key: 'c' }),
    ];

    await visit('/pr/o/r/7/conversations/c');

    assert.deepEqual(commentsAskedFor(board().asked), ['c', 'a', 'b']);
  });
});
