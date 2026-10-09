import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, triggerEvent } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';

module('Acceptance | seen', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('proposed', { key: 'b' }),
      board().threadIn('proposed', { key: 'c' }),
    ];
  });

  test('landing on the board or a conversation says nothing was seen', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    await visit('/pr/o/r/7/conversations/c');

    assert.deepEqual(board().seen, []);
  });

  test('clicking a row in the rail says that conversation was seen', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');

    await click('#c-b');

    assert.deepEqual(board().seen, ['b']);
  });

  test('clicking a card on the board says that conversation was seen', async function (assert) {
    await visit('/pr/o/r/7/board');

    await click('[data-test-card="c"]');

    assert.deepEqual(board().seen, ['c']);
  });

  test('stepping to the next ready one says where it landed', async function (assert) {
    await visit('/pr/o/r/7/conversations/a');

    await click('[data-test-next]');
    await triggerEvent(document, 'keydown', { key: 'n' });

    assert.deepEqual(board().seen, ['b', 'c']);
  });

  test('walking the rail with j says each one it lands on', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');
    await triggerEvent(document, 'keydown', { key: 'Escape' });

    await triggerEvent(document, 'keydown', { key: 'j' });

    assert.strictEqual(board().seen.length, 1);
  });
});
