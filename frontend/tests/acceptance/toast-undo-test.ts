import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit, waitUntil } from '@ember/test-helpers';
import {
  setupFakeBoard,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import type { Conversation } from 'frontend/data/api';

const KEY = 'PRRT_undo';

const CARD = `/pr/o/r/7/conversations/${KEY}`;

async function open(
  board: FakeBoard,
  phase: Parameters<FakeBoard['threadIn']>[0],
  over: Partial<Conversation> = {},
): Promise<void> {
  board.conversations = [board.threadIn(phase, { key: KEY, ...over })];
  await visit(CARD);
}

function settledIn(
  board: FakeBoard,
  phase: Parameters<FakeBoard['threadIn']>[0],
  over: Partial<Conversation> = {},
): void {
  board.conversations = [board.threadIn(phase, { key: KEY, ...over })];
}

function verbs(board: FakeBoard): string[] {
  return board.posted.map((one) => one.verb);
}

async function undone(board: FakeBoard, verb: string): Promise<string> {
  await click('[data-test-toast-undo]');
  await waitUntil(() => verbs(board).includes(verb), { timeout: 5000 });
  return board.posted.at(-1)!.url;
}

module('Acceptance | toast undo', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('Mark done says so with Bring back, which sends what the card’s Bring back sends', async function (assert) {
    await open(board(), 'waiting');

    await click('[data-test-decision="mark-done"]');

    assert.dom('[data-test-toast-undo]').hasText('Bring back');
    settledIn(board(), 'marked done');
    assert.strictEqual(
      await undone(board(), 'unpark'),
      `/pr/o/r/7/api/conversations/${KEY}/operations:unpark`,
    );
    assert.deepEqual(board().posted.at(-1)!.body, {});
  });

  test('the author’s Confirm acts at once and offers Bring back', async function (assert) {
    await open(board(), 'assumed-done');

    await click('[data-test-decision="confirm"]');

    assert.strictEqual(verbs(board())[0], 'confirm');
    assert.dom('[data-test-toast-undo]').hasText('Bring back');
    settledIn(board(), 'resolved');
    assert.strictEqual(
      await undone(board(), 'unpark'),
      `/pr/o/r/7/api/conversations/${KEY}/operations:unpark`,
    );
  });

  test('the reviewer’s Resolve offers Unresolve on GitHub, sent only once GitHub has resolved it', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'answered');
    await click('[data-test-decision="resolve"]');
    await click('[data-test-dialog-submit]');
    assert.dom('[data-test-toast-undo]').hasText('Unresolve on GitHub');

    await click('[data-test-toast-undo]');

    assert.deepEqual(
      verbs(board()),
      ['resolve'],
      'nothing is sent while the resolve is still on its way to GitHub',
    );
    settledIn(board(), 'resolved', { github_resolved: true });
    await waitUntil(() => verbs(board()).includes('unpark'), {
      timeout: 5000,
    });
    assert.deepEqual(verbs(board()), ['resolve', 'unpark']);
  });

  test('the author’s Resolve offers Unresolve on GitHub, sent only once GitHub has resolved it', async function (assert) {
    await open(board(), 'waiting');
    await click('[data-test-decision="resolve"]');
    await click('[data-test-dialog-submit]');
    assert.dom('[data-test-toast-undo]').hasText('Unresolve on GitHub');

    await click('[data-test-toast-undo]');

    assert.deepEqual(verbs(board()), ['resolve']);
    settledIn(board(), 'resolved', { github_resolved: true });
    await waitUntil(() => verbs(board()).includes('unpark'), {
      timeout: 5000,
    });
    assert.deepEqual(verbs(board()), ['resolve', 'unpark']);
  });

  test('Discard offers Bring back to the local draft', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'draft');

    await click('[data-test-decision="discard"]');

    assert.dom('[data-test-toast-undo]').hasText('Bring back');
    settledIn(board(), 'discarded');
    assert.strictEqual(
      await undone(board(), 'unpark'),
      `/pr/o/r/7/api/conversations/${KEY}/operations:unpark`,
    );
  });

  test('Add to review offers Leave out of review', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'draft');

    await click('[data-test-decision="enrol"]');

    assert.dom('[data-test-toast-undo]').hasText('Leave out of review');
    settledIn(board(), 'enrolled');
    assert.strictEqual(
      await undone(board(), 'withdraw-from-review'),
      `/pr/o/r/7/api/conversations/${KEY}/operations:withdraw-from-review`,
    );
  });

  test('a move with no way back by the toast carries no undo', async function (assert) {
    await open(board(), 'proposed');

    await click('[data-test-decision="reject"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-toast]').exists();
    assert.dom('[data-test-toast-undo]').doesNotExist();
  });
});
