import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit } from '@ember/test-helpers';
import {
  added,
  diffOf,
  proposal,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

function bar(): string[] {
  return [...document.querySelectorAll('#panel-actions button')].map(
    (button) => button.firstChild?.textContent?.trim() ?? '',
  );
}

module('Acceptance | action bar', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().proposals['k1'] = [proposal({ id: 'k1.1.proposal' })];
    board().diffs['k1.1.proposal'] = diffOf(
      'src/foo.py',
      added(142, '    return sorted(line_items)'),
    );
  });

  test('each verb wears the weight of the decision it is', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert
      .dom('[data-test-decision="approve"]')
      .hasAttribute('data-weight', 'primary');
    assert
      .dom('[data-test-decision="rework"]')
      .hasAttribute('data-weight', 'secondary');
    assert
      .dom('[data-test-decision="defer"]')
      .hasAttribute('data-weight', 'ghost');
  });

  test('turning a fix down wears the destructive weight, not a link’s', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert
      .dom('[data-test-decision="reject"]')
      .hasAttribute('data-weight', 'destructive');
  });

  test('a verb says what it will do', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert
      .dom('[data-test-decision="approve"]')
      .includesText('Accept')
      .hasAttribute('title', /^lands this fix on the PR branch/);
  });

  test('a bar with nothing to decide leads with the reply', async function (assert) {
    board().conversations = [thread({ key: 'k1', github_removed: true })];

    await visit('/pr/o/r/7/conversations/k1');

    assert.deepEqual(bar(), ['Reply to Anna', 'Resolve on GitHub']);
    assert.dom('[data-test-reply-to]').hasAttribute('data-weight', 'secondary');
  });

  test('the reply opens the composer and puts the cursor in it', async function (assert) {
    board().conversations = [thread({ key: 'k1', github_removed: true })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-reply-to]');

    assert.dom('[data-test-reply]').isFocused();
  });

  test('a bar with something to decide offers no reply of its own', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-reply-to]').doesNotExist();
  });

  test('send back for rework opens the rework dialog, not the decide one', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.dom('[data-test-rework-dialog]').exists();
  });

  test('the open dialog carries the send and leaves the bar alone', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert
      .dom('[data-test-rework-dialog] [data-test-send-rework]')
      .hasText('Send to agent for rework');
    assert.dom('[data-test-rework-dialog] [data-test-cancel-rework]').exists();
    assert
      .dom('[data-test-rework-note]')
      .hasText(
        'Comment moves to "Sent back for rework"; the agent re-runs with your note and the pointed lines.',
      );
    assert.dom('[data-test-decision="approve"]').exists('the bar stays put');
  });
});
