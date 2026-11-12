import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, find, findAll, visit } from '@ember/test-helpers';
import {
  comment,
  setupFakeBoard,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import type { Conversation } from 'frontend/data/api';

const KEY = 'PRRT_resolve';

function footer(): string[] {
  return findAll('#panel-actions [data-test-decision]').map((one) =>
    [
      one.getAttribute('data-test-decision'),
      one.hasAttribute('data-runs-agent') ? '✦' : '',
      one.hasAttribute('data-opens-dialog') ? '⧉' : '',
    ].join(''),
  );
}

function labelOf(decision: string): string {
  const button = find(`#panel-actions [data-test-decision="${decision}"]`);
  return [...(button?.childNodes ?? [])]
    .filter((one) => one.nodeType === Node.TEXT_NODE)
    .map((one) => one.textContent)
    .join('')
    .trim();
}

async function authorIn(
  board: FakeBoard,
  phase: Parameters<FakeBoard['threadIn']>[0],
  over: Partial<Conversation> = {},
): Promise<string[]> {
  board.conversations = [board.threadIn(phase, { key: KEY, ...over })];
  await visit(`/pr/o/r/7/conversations/${KEY}`);
  return footer();
}

function reviewing(board: FakeBoard, over: Partial<Conversation> = {}) {
  board.actAs('reviewer');
  board.viewer = { login: 'vector67', name: null };
  board.people = [{ login: 'mei', name: 'Mei Placeholder' }];
  board.conversations = [
    thread({
      key: KEY,
      comments: [
        {
          id: 1,
          author: 'vector67',
          created_at: null,
          review_state: 'CHANGES_REQUESTED',
        },
        { id: 2, author: 'mei', created_at: null, review_state: null },
      ],
      ...over,
    }),
  ];
  board.comments[KEY] = [
    comment({ author: 'vector67', created_at: null, body: 'skips the tax' }),
    comment({
      id: 2,
      author: 'mei',
      created_at: null,
      review_state: null,
      body: 'moved the guard',
    }),
  ];
}

module('Acceptance | Resolve and Mark done', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('a proposed fix offers Resolve beside Mark done, which opens no dialog', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'proposed'), [
      'approve⧉',
      'rework✦⧉',
      'defer⧉',
      'reject⧉',
      'resolve⧉',
      'mark-done',
    ]);
    assert.strictEqual(labelOf('resolve'), 'Resolve');
    assert.strictEqual(labelOf('mark-done'), 'Mark done');
  });

  test('a waiting card offers Stop waiting, Mark done, Resolve and Defer', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'waiting'), [
      'unpark',
      'mark-done',
      'resolve⧉',
      'defer⧉',
    ]);
  });

  test('an assumed-done card offers Confirm, Move and Resolve', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'assumed-done'), [
      'confirm',
      'place⧉',
      'resolve⧉',
    ]);
  });

  test('a declined card offers Resolve by that name', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'declined'), [
      'rework✦⧉',
      'resolve⧉',
      'defer⧉',
    ]);
    assert.strictEqual(labelOf('resolve'), 'Resolve');
  });

  test("a declined card's Resolve offers the agent's words", async function (assert) {
    await authorIn(board(), 'declined');

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-agent-words]').exists();
  });

  test('Resolve asks for an optional reply with no resolve tick box, and resolves on GitHub', async function (assert) {
    await authorIn(board(), 'waiting');

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-resolve]').doesNotExist();
    assert.dom('[data-test-dialog-submit]').hasText('Resolve');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.propContains(board().posted[0]!.body, { resolve: true });
  });

  test('Resolve posts what you wrote before it resolves', async function (assert) {
    await authorIn(board(), 'waiting');
    await click('[data-test-decision="resolve"]');

    await fillIn('[data-test-dialog-body]', 'Renamed it.');

    assert.dom('[data-test-dialog-submit]').hasText('Resolve');
    await click('[data-test-dialog-submit]');
    assert.propContains(board().posted[0]!.body, {
      reply: 'Renamed it.',
      resolve: true,
    });
  });

  test('Mark done finishes the card on the board at once, sending GitHub nothing', async function (assert) {
    await authorIn(board(), 'waiting');

    await click('[data-test-decision="mark-done"]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted[0]!.verb, 'mark-done');
    assert.deepEqual(board().posted[0]!.body, {});
  });

  test('an issue comment, which GitHub cannot resolve, offers Reply and mark done where a review thread offers Resolve', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'waiting', { kind: 'issue' }), [
      'unpark',
      'mark-done',
      'reply-and-mark-done⧉',
      'defer⧉',
    ]);
    assert.strictEqual(labelOf('reply-and-mark-done'), 'Reply and mark done');
  });

  test('Reply and mark done needs a reply and sends it with nothing else', async function (assert) {
    await authorIn(board(), 'waiting', { kind: 'issue' });
    await click('[data-test-decision="reply-and-mark-done"]');

    assert.dom('[data-test-dialog-submit]').isDisabled();
    await fillIn('[data-test-dialog-body]', 'Done in the next push.');
    assert.dom('[data-test-dialog-submit]').hasText('Reply and mark done');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'mark-done');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'Done in the next push.',
    });
  });

  test('a change asked for on the board alone offers Mark done and no Resolve', async function (assert) {
    assert.deepEqual(await authorIn(board(), 'proposed', { kind: 'request' }), [
      'approve⧉',
      'rework✦⧉',
      'defer⧉',
      'reject⧉',
      'mark-done',
    ]);
  });

  test("the reviewer's Resolve keeps a ticked 👍 on the newest reply and no resolve tick box", async function (assert) {
    reviewing(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-resolve]').doesNotExist();
    assert.dom('[data-test-thumbs-up]').isChecked();
    assert
      .dom(find('[data-test-thumbs-up]')?.closest('label') ?? null)
      .hasText('Put 👍 on the newest reply');
    assert.dom('[data-test-dialog-submit]').hasText('Resolve');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.propContains(board().posted[0]!.body, { resolve: true });
  });

  test("the reviewer's Resolve with the 👍 unticked resolves with no reaction", async function (assert) {
    reviewing(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="resolve"]');

    await click('[data-test-thumbs-up]');
    await click('[data-test-dialog-submit]');

    assert.propContains(board().posted[0]!.body, {
      resolve: true,
      thumbs_up: false,
    });
  });
});
