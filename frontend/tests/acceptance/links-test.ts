import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, visit } from '@ember/test-helpers';
import {
  heldPr,
  outstandingMention,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { leftToTheBrowser } from 'frontend/tests/helpers/browser';

module('Acceptance | links open in a new tab', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().held = [heldPr(), heldPr({ number: 8 })];
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('proposed', { key: 'b' }),
      board().threadIn('proposed', { key: 'c' }),
    ];
  });

  test('a wall card links to its pull request', async function (assert) {
    await visit('/');
    const lead = '[data-test-wall-row="o/r#8"] [data-test-wall-lead]';

    assert.dom(lead).hasAttribute('href', '/pr/o/r/8');
    assert.true(await leftToTheBrowser(lead));
    assert.strictEqual(currentURL(), '/');
  });

  test('a switcher row links to its pull request', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');
    await click('[data-test-switcher-open]');
    const row = '[data-test-switcher-row="o/r#8"]';

    assert.dom(row).hasAttribute('href', '/pr/o/r/8');
    assert.true(await leftToTheBrowser(row));
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
  });

  test('a rail row links to its conversation', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');

    assert.dom('#c-c a').hasAttribute('href', '/pr/o/r/7/conversations/c');
    assert.true(await leftToTheBrowser('#c-c a'));
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
    assert.deepEqual(board().seen, [], 'only a click in this tab reads it');
  });

  test('a card on the board links to its conversation', async function (assert) {
    await visit('/pr/o/r/7/board');

    assert
      .dom('[data-test-card="c"]')
      .hasAttribute('href', '/pr/o/r/7/conversations/c');
    assert.true(await leftToTheBrowser('[data-test-card="c"]'));
    assert.strictEqual(currentURL(), '/pr/o/r/7/board');
  });

  test('the panel’s Prev and Next link to the conversations they walk to', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');

    assert
      .dom('[data-test-prev]')
      .hasAttribute('href', '/pr/o/r/7/conversations/b');
    assert
      .dom('[data-test-next]')
      .hasAttribute('href', '/pr/o/r/7/conversations/c');
    assert.true(await leftToTheBrowser('[data-test-prev]'));
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/c');
  });

  test('a mention on the board links to its thread', async function (assert) {
    board().mentions.mentions = [outstandingMention({ thread: 'b' })];
    await visit('/');
    await click('[data-test-mentions-count]');
    const open = '[data-test-mention="b"] [data-test-mention-open]';

    assert.dom(open).hasAttribute('href', '/pr/o/r/7/conversations/b');
    assert.true(await leftToTheBrowser(open));
    assert.strictEqual(currentURL(), '/');
  });

  test('the dashboard’s Open the Board links to the Board tab', async function (assert) {
    await visit('/pr/o/r/7/dashboard');
    const open = '[data-test-control="board"]';

    assert.dom(open).hasAttribute('href', '/pr/o/r/7/conversations');
    assert.true(await leftToTheBrowser(open));
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
  });
});
