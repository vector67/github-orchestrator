import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, triggerKeyEvent, visit } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

const OPEN = '[data-test-reply-open]';

const CLOSE = '[data-test-reply-close]';

const BOX = '[data-test-reply]';

const SUGGESTIONS = '[data-test-suggestions]';

const OPTION = '[data-test-suggestion]';

const PICTURES = 'https://github.githubassets.com/images/icons/emoji';

const SHIPIT = `${PICTURES}/shipit.png?v8`;

const EMOJIS = {
  '+1': `${PICTURES}/unicode/1f44d.png?v8`,
  lithuania: `${PICTURES}/unicode/1f1f1-1f1f9.png?v8`,
  shipit: SHIPIT,
  tada: `${PICTURES}/unicode/1f389.png?v8`,
  thumbsdown: `${PICTURES}/unicode/1f44e.png?v8`,
  thumbsup: `${PICTURES}/unicode/1f44d.png?v8`,
};

module('Acceptance | reply', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [thread({ key: 'k1' }), thread({ key: 'k2' })];
    board().comments['k1'] = [comment()];
    board().comments['k2'] = [comment()];
    board().emojis = EMOJIS;
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

  test('a colon and a few letters offer the emoji github names that way', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    await fillIn(BOX, 'nice :thu');

    assert
      .dom(OPTION)
      .hasText('👎 :thumbsdown:')
      .hasAttribute('aria-selected', 'true');
    assert.dom(`${OPTION}:nth-child(2)`).hasText('👍 :thumbsup:');
    assert.dom(`${OPTION}:nth-child(3)`).hasText('🇱🇹 :lithuania:');
  });

  test('tab puts the offered emoji in place of the colon and its letters', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'nice :thu');

    await triggerKeyEvent(BOX, 'keydown', 'Tab');

    assert.dom(BOX).hasValue('nice 👎').isFocused();
    assert.dom(SUGGESTIONS).doesNotExist();
    await visit('/pr/o/r/7/conversations/k2');
    await visit('/pr/o/r/7/conversations/k1');
    assert.dom(BOX).hasValue('nice 👎');
  });

  test('the arrow keys pick another emoji and enter puts it in', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, ':thu');

    await triggerKeyEvent(BOX, 'keydown', 'ArrowDown');
    await triggerKeyEvent(BOX, 'keydown', 'Enter');

    assert.dom(BOX).hasValue('👍');
  });

  test('clicking an emoji puts it in', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'shipped :tad');

    await click(OPTION);

    assert.dom(BOX).hasValue('shipped 🎉').isFocused();
  });

  test('an emoji only github draws is offered as its picture and put in by name', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'lgtm :ship');

    assert.dom(OPTION).hasText(':shipit:');
    assert.dom(`${OPTION} img`).hasAttribute('src', SHIPIT);

    await triggerKeyEvent(BOX, 'keydown', 'Tab');

    assert.dom(BOX).hasValue('lgtm :shipit:');
  });

  test('escape puts the offer away and leaves the words', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, ':thu');

    await triggerKeyEvent(BOX, 'keydown', 'Escape');

    assert.dom(SUGGESTIONS).doesNotExist();
    assert.dom(BOX).hasValue(':thu');
  });

  test('a colon inside a word offers nothing', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    await fillIn(BOX, 'see https:thu');

    assert.dom(SUGGESTIONS).doesNotExist();
  });

  test('an at sign offers the pull request people first, then the rest of the repository', async function (assert) {
    board().mentionable = ['erin', 'anna', 'bob'];
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    await fillIn(BOX, 'cc @');

    assert.deepEqual(
      [...document.querySelectorAll(OPTION)].map((one) => one.textContent),
      ['@dave', '@carol', '@anna Anna Example', '@erin', '@bob'],
    );
    assert.dom(OPTION).hasAttribute('aria-selected', 'true');
  });

  test('letters after the at narrow the people by login or name', async function (assert) {
    board().mentionable = ['erin', 'bob'];
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    await fillIn(BOX, 'cc @exa');

    assert.dom(OPTION).exists({ count: 1 }).hasText('@anna Anna Example');
  });

  test('tab puts the login in place of the at and its letters, with a space after', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);
    await fillIn(BOX, 'cc @car');

    await triggerKeyEvent(BOX, 'keydown', 'Tab');

    assert.dom(BOX).hasValue('cc @carol ').isFocused();
    assert.dom(SUGGESTIONS).doesNotExist();
  });

  test('an at inside a word offers nobody', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click(OPEN);

    await fillIn(BOX, 'mail me@car');

    assert.dom(SUGGESTIONS).doesNotExist();
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
