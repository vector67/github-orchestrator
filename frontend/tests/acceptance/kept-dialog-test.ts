import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  visit,
  click,
  fillIn,
  select,
  setupApplicationContext,
  setupContext,
  teardownContext,
  type TestContext,
} from '@ember/test-helpers';
import {
  comment,
  proposal,
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const DAY = 24 * 60 * 60 * 1000;

async function reloaded(context: TestContext) {
  await teardownContext(context);
  await setupContext(context);
  await setupApplicationContext(context);
}

async function closeWith(decision: string, words: string) {
  await click(`[data-test-decision="${decision}"]`);
  await fillIn('[data-test-dialog-body]', words);
  await click('[data-test-dialog-cancel]');
  await click('[data-test-close-confirm]');
}

module('Acceptance | kept dialog', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    const own = [
      { id: 1, author: 'octocat', created_at: null, review_state: null },
    ];
    board().conversations = [
      thread({ key: 'k1', comments: own, operations: [summary()] }),
      thread({ key: 'k2', comments: own, operations: [summary()] }),
    ];
    board().comments['k1'] = [comment({ author: 'octocat' })];
    board().comments['k2'] = [comment({ author: 'octocat' })];
  });

  test('a reply closed on one card is not on another', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    await visit('/pr/o/r/7/conversations/k2');
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('');
  });

  test('the draft belongs to its verb', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    await click('[data-test-decision="reject"]');

    assert.dom('[data-test-dialog-body]').hasValue('');
  });

  test('a restored draft still asks before it is closed', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');
    await click('[data-test-decision="approve"]');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-close-ask]').exists();
  });

  test('the delete tick comes back with the reply', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-delete]');
    await click('[data-test-dialog-cancel]');
    await click('[data-test-close-confirm]');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-delete]').isChecked();
  });

  test('the GitHub ticks sit under one heading, delete before resolve', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    const ticks = [
      ...document.querySelectorAll('[data-test-github-ticks] input'),
    ].map((tick) =>
      tick.hasAttribute('data-test-delete') ? 'delete' : 'resolve',
    );
    assert.deepEqual(ticks, ['delete', 'resolve']);
  });

  test('deleting the comment greys the resolve tick out', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-resolve]');

    await click('[data-test-delete]');

    assert.dom('[data-test-resolve]').isDisabled();
    await click('[data-test-dialog-submit]');
    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: true,
      resolve: false,
    });
  });

  test('no delete is offered on a thread somebody else has joined', async function (assert) {
    board().comments['k1'] = [
      comment({ author: 'octocat' }),
      comment({ id: 2, author: 'anna' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-delete]').doesNotExist();
    assert.dom('[data-test-resolve]').exists();
  });

  test('unticking delete gives the resolve tick back as it was', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-resolve]');
    await click('[data-test-delete]');

    await click('[data-test-delete]');

    assert.dom('[data-test-resolve]').isEnabled();
    assert.dom('[data-test-resolve]').isChecked();
  });

  test('an edited message comes back', async function (assert) {
    board().proposals['k1'] = [proposal()];
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-edit-message]');
    await fillIn('[data-test-message-body]', 'Rename it properly');
    await click('[data-test-dialog-cancel]');
    await click('[data-test-close-confirm]');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-message-body]').hasValue('Rename it properly');
  });

  test('an edited ticket comes back', async function (assert) {
    board().proposals['k1'] = [
      proposal({
        kind: 'ticket',
        reply: 'I have proposed a ticket.',
        ticket: { project: 'PROJ', title: 'Cache models', body: 'Read once.' },
        commits: null,
        commit_message: null,
      }),
    ];
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-ticket-project]', 'WEB');
    await click('[data-test-dialog-cancel]');
    await click('[data-test-close-confirm]');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-ticket-project]').hasValue('WEB');
    assert.dom('[data-test-ticket-title]').hasValue('Cache models');
  });

  test('the resolve tick comes back', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-resolve]');
    await click('[data-test-dialog-cancel]');
    await click('[data-test-close-confirm]');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-resolve]').isChecked();
  });

  test('the wake condition and its pr number come back', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="defer"]');
    await select('[data-test-wake]', 'pr');
    await fillIn('[data-test-wake-pr]', '99');
    await click('[data-test-dialog-cancel]');
    await click('[data-test-close-confirm]');

    await click('[data-test-decision="defer"]');

    assert.dom('[data-test-wake]').hasValue('pr');
    assert.dom('[data-test-wake-pr]').hasValue('99');
  });

  test('a verb you submit on the card clears every draft it holds', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'not this way');
    await click('[data-test-dialog-submit]');
    await click('[data-test-decision="approve"]');

    assert.strictEqual(board().posted[0]!.verb, 'reject');
    assert.dom('[data-test-dialog-body]').hasValue('');
  });

  test("a verb submitted on another card leaves this one's draft alone", async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');
    await visit('/pr/o/r/7/conversations/k2');
    await click('[data-test-decision="reject"]');
    await click('[data-test-dialog-submit]');

    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
  });

  test('a card that moves without you keeps its draft', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');
    board().conversations = board().conversations.map((one) =>
      one.key === 'k1' ? { ...one, etag: '"t2"', state: 'working' } : one,
    );
    await visit('/pr/o/r/7/conversations/k2');
    await visit('/pr/o/r/7/conversations/k1');
    board().conversations = board().conversations.map((one) =>
      one.key === 'k1' ? { ...one, etag: '"t3"', state: 'ready' } : one,
    );
    await visit('/pr/o/r/7/conversations/k2');

    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
  });

  test('a draft kept before a reload is there after it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    await reloaded(this);
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
  });

  test('a draft untouched for fourteen days is dropped', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    clock().now += 14 * DAY;
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('');
  });

  test('a draft touched thirteen days ago is still kept', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await closeWith('approve', 'thanks, pushed');

    clock().now += 13 * DAY;
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
  });
});
