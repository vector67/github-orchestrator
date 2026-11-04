import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import type { Reaction } from 'frontend/data/api';

const KEY = 'PRRT_aa';

function pills(): [string, string, boolean][] {
  return [...document.querySelectorAll('[data-test-reaction]')].map((pill) => [
    pill.getAttribute('data-test-reaction') ?? '',
    pill.textContent?.replace(/\s+/g, ' ').trim() ?? '',
    pill.getAttribute('aria-pressed') === 'true',
  ]);
}

module('Acceptance | reactions', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function seed(reactions: Reaction[]) {
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = [comment({ id: 1, reactions })];
  }

  test('a comment shows each reaction with its count, mine pressed', async function (assert) {
    seed([
      { content: 'thumbs-up', count: 2, mine: true },
      { content: 'eyes', count: 1, mine: false },
    ]);

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(pills(), [
      ['thumbs-up', '👍 2', true],
      ['eyes', '👀 1', false],
    ]);
  });

  test('the smiley offers GitHub’s eight reactions and a pick is sent and shown', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-react]');
    const offered = [
      ...document.querySelectorAll('[data-test-reaction-option]'),
    ].map((one) => one.textContent?.trim());
    await click('[data-test-reaction-option="heart"]');

    assert.deepEqual(offered, ['👍', '👎', '😄', '🎉', '😕', '❤️', '🚀', '👀']);
    assert.deepEqual(board().reacted, [
      { key: KEY, comment: 1, content: 'heart', mine: true },
    ]);
    assert.deepEqual(pills(), [['heart', '❤️ 1', true]]);
    assert.dom('[data-test-reaction-option]').doesNotExist('the picker closes');
  });

  test('pressing my own reaction takes it back', async function (assert) {
    seed([{ content: 'rocket', count: 2, mine: true }]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-reaction="rocket"]');

    assert.deepEqual(board().reacted, [
      { key: KEY, comment: 1, content: 'rocket', mine: false },
    ]);
    assert.deepEqual(pills(), [['rocket', '🚀 1', false]]);
  });

  test('pressing someone else’s reaction adds mine to it', async function (assert) {
    seed([{ content: 'laugh', count: 1, mine: false }]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-reaction="laugh"]');

    assert.deepEqual(pills(), [['laugh', '😄 2', true]]);
  });

  test('a reaction GitHub refuses says so and leaves the comment as it was', async function (assert) {
    seed([]);
    board().reactionRefused = 'GitHub said no';
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-react]');
    await click('[data-test-reaction-option="eyes"]');

    assert.deepEqual(pills(), []);
    assert.dom('[data-test-toast]').containsText('GitHub said no');
  });
});
