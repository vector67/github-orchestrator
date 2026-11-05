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

  test('the picker opens over the page just under the smiley and moves nothing in the thread', async function (assert) {
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = Array.from({ length: 8 }, (_, at) =>
      comment({ id: at + 1, review_state: null, body: `point ${at + 1}` }),
    );
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const smileys = [...document.querySelectorAll('[data-test-react]')];
    const smiley = smileys.at(-1)!;
    const thread_ = document.querySelector('#panel-thread')!;
    const entries = () =>
      [...document.querySelectorAll('[data-test-entry]')].map(
        (entry) => entry.getBoundingClientRect().top,
      );
    smiley.scrollIntoView({ block: 'nearest' });
    const before = JSON.stringify({
      scrolled: thread_.scrollTop,
      entries: entries(),
    });

    await click(smiley);

    const picker = document.querySelector('[data-test-reaction-picker]')!;
    const under = smiley.getBoundingClientRect().bottom;
    const top = picker.getBoundingClientRect().top;
    assert.strictEqual(
      JSON.stringify({ scrolled: thread_.scrollTop, entries: entries() }),
      before,
      'nothing in the thread moved',
    );
    assert.true(picker.matches(':popover-open'), 'it is drawn over the page');
    assert.true(
      top >= under && top <= under + 12,
      `it opens just under the smiley (${top} under ${under})`,
    );
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
