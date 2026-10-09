import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, visit } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

const OPEN = '[data-test-reply-open]';

const CLOSE = '[data-test-reply-close]';

const BOX = '[data-test-reply]';

module('Acceptance | reply', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [thread({ key: 'k1' }), thread({ key: 'k2' })];
    board().comments['k1'] = [comment()];
    board().comments['k2'] = [comment()];
  });

  test('the composer is a link until it is asked for', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom(OPEN).hasText('Reply to Anna');
    assert.dom(BOX).doesNotExist();
    assert.dom('[data-test-reply-send]').doesNotExist();
    assert.dom('[data-test-composer-note]').doesNotExist();
  });

  test('asking for it opens the composer with the cursor in it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click(OPEN);

    assert.dom(BOX).isFocused();
    assert.dom(OPEN).doesNotExist();
  });

  test('an open composer folds back to the link when it is closed, dropping the words nobody posted', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'half a thought');

    await click(CLOSE);

    assert.dom(BOX).doesNotExist();
    assert.dom(OPEN).hasText('Reply to Anna');
    assert.strictEqual(board().posted.length, 0);

    await click(OPEN);

    assert.dom(BOX).hasValue('');
  });

  test('the box says who it answers and where the words go', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click(OPEN);

    assert
      .dom(BOX)
      .hasAttribute('placeholder', 'Reply to Anna… posts to the GitHub thread');
  });

  test('a reviewer github has no name for is not named at all', async function (assert) {
    board().conversations = [thread({ key: 'k1', comments: [] })];
    board().comments['k1'] = [];
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom(OPEN).hasText('Reply');
    await click(OPEN);

    assert
      .dom(BOX)
      .hasAttribute('placeholder', 'Reply… posts to the GitHub thread');
  });

  test('a comment with no thread of its own says it posts to the pr', async function (assert) {
    board().conversations = [
      thread({ key: 'k1', kind: 'issue', state: 'waiting' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click(OPEN);

    assert
      .dom(BOX)
      .hasAttribute('placeholder', 'Reply to Anna… posts to the PR');
    assert.dom('[data-test-composer-note]').hasText('Posted to the PR.');
  });

  test('everywhere else it only says where it posts', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click(OPEN);

    assert
      .dom('[data-test-composer-note]')
      .hasText('Posted to the GitHub thread.');
  });

  test('post reply waits until there are words to post', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    assert.dom('[data-test-reply-send]').hasText('Post reply');
    assert.dom('[data-test-reply-send]').isDisabled();

    await fillIn(BOX, 'good catch');

    assert.dom('[data-test-reply-send]').isNotDisabled();
  });

  test('a composer is open on one conversation at a time, and waits there', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'half a thought');

    await visit('/pr/o/r/7/conversations/k2');

    assert.dom(BOX).doesNotExist();
    assert.dom(OPEN).exists();

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom(BOX).hasValue('half a thought');
  });

  test('another conversation is answered in its own words', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'good catch');

    await visit('/pr/o/r/7/conversations/k2');
    await click(OPEN);

    assert.dom(BOX).hasValue('');

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom(BOX).doesNotExist();
  });

  test('asking again for the composer already open keeps the words', async function (assert) {
    board().actAs('reviewer');
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reply"]');
    await fillIn(BOX, 'half a thought');

    await click('[data-test-decision="reply"]');

    assert.dom(BOX).hasValue('half a thought');
  });
});
