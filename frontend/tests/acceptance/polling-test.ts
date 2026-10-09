import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit } from '@ember/test-helpers';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import {
  added,
  comment,
  diffOf,
  operation,
  proposal,
  setupFakeBoard,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';

const FAST = 1000;
const SLOW = 5000;

function seed(board: FakeBoard, words: string, etag = '"t1"') {
  board.conversations = [board.threadIn('proposed', { key: 'k1', etag })];
  board.comments['k1'] = [comment({ body: 'rename it' })];
  board.operations['k1'] = [operation({ id: 'k1.1', conversation: 'k1' })];
  board.proposals['k1'] = [proposal({ id: 'k1.1.proposal', summary: words })];
  board.diffs['k1.1.proposal'] = diffOf('src/foo.py', added(42, 'return rows'));
}

module('Acceptance | polling', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    seed(board(), 'first');
  });

  async function moved(words: string) {
    seed(board(), words, '"t2"');
    await clock().tick(SLOW);
  }

  test('a thread that moved brings its new words without redrawing the panel', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-panel-summary]').hasText('first');
    const before = document.querySelector('#panel-body');
    const panel = before as HTMLElement;
    panel.style.height = '20px';
    panel.style.overflow = 'auto';
    panel.scrollTop = 0;
    const room = document.createElement('div');
    room.style.height = '500px';
    room.style.flexShrink = '0';
    panel.appendChild(room);
    panel.scrollTop = 120;

    await moved('second');

    assert.dom('[data-test-panel-summary]').hasText('second');
    assert.strictEqual(panel.scrollTop, 120, 'a scroller keeps its place');
    assert.strictEqual(
      document.querySelector('#panel-body'),
      before,
      'the panel element survives a refresh: nothing is swapped, so a ' +
        'scroller in it keeps its place and a selection in it lives',
    );
  });

  test('a comment and its words survive a refresh', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const body = document.querySelector('#panel-thread [data-test-entry-body]');
    const words = body?.firstChild;

    await moved('second');

    assert.strictEqual(
      document.querySelector('#panel-thread [data-test-entry-body]'),
      body,
      'a comment redrawn every poll loses the selection in it and flickers',
    );
    assert.strictEqual(
      document.querySelector('#panel-thread [data-test-entry-body]')
        ?.firstChild,
      words,
      'a body written again every poll is a selection lost every poll',
    );
  });

  test('the diff is not asked for again while the proposal is the same', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    assert.strictEqual(board().askedFor(/\/api\/diffs\//).length, 1);

    await moved('second');

    assert.strictEqual(
      board().askedFor(/\/api\/diffs\//).length,
      1,
      'a diff fetched every poll blanks the fold and draws it again',
    );
  });

  test('a rail row survives a refresh', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const before = document.querySelector('#rows li[role="option"]');

    await moved('second');

    assert.strictEqual(
      document.querySelector('#rows li[role="option"]'),
      before,
      'the rail is redrawn every poll',
    );
  });

  test('the board follows the list, and so does the queue a card opens from it', async function (assert) {
    await visit('/pr/o/r/7/board');
    board().conversations = [board().threadIn('landed', { key: 'k1' })];
    await clock().tick(SLOW);

    assert.dom('[data-test-column="done"] [data-test-card="k1"]').exists();

    await click('[data-test-card="k1"]');
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await clock().tick(SLOW);

    assert.dom('[data-test-heading="waiting"]').exists();
  });

  test('a thread that has not moved is not read again', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const read = board().askedFor(/\/comments$/).length;

    await clock().tick(SLOW);
    await clock().tick(SLOW);

    assert.strictEqual(
      board().askedFor(/\/comments$/).length,
      read,
      'the collection came back 304, and so the card has nothing new to read',
    );
  });

  test('work moving under an agent is the fast poll alone', async function (assert) {
    board().conversations = [board().threadIn('working', { key: 'k1' })];
    board().inFlight = [
      operation({
        id: 'k1.1',
        conversation: 'k1',
        state: 'running',
        plan: [
          { text: 'rename it', file: 'src/foo.py', done: false },
          { text: 'update callers', file: null, done: false },
        ],
      }),
    ];
    await visit('/pr/o/r/7/conversations/k1');
    const lists = board().askedFor(/\/api\/conversations$/).length;

    board().inFlight = [
      operation({
        id: 'k1.1',
        conversation: 'k1',
        state: 'running',
        last_action: 'editing src/foo.py',
        plan: [
          { text: 'rename it', file: 'src/foo.py', done: true },
          { text: 'update callers', file: null, done: false },
        ],
      }),
    ];
    await clock().tick(FAST);

    assert
      .dom('#c-k1 [data-test-meta]')
      .hasText('Anna Example · running · 1/2');
    assert.dom('[data-test-notes]').containsText('editing src/foo.py');
    assert.strictEqual(
      board().askedFor(/\/api\/conversations$/).length,
      lists,
      'a plan ticking over is not a reason to read forty threads',
    );
    assert.ok(
      board()
        .askedFor(/\/api\/operations$/)
        .at(-1)?.ifNoneMatch,
    );
  });

  test('work that settles has the list read at once', async function (assert) {
    board().conversations = [board().threadIn('working', { key: 'k1' })];
    board().inFlight = [
      operation({ id: 'k1.1', conversation: 'k1', state: 'running' }),
    ];
    await visit('/pr/o/r/7/conversations');

    board().inFlight = [];
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', etag: '"t2"' }),
    ];
    await clock().tick(FAST);

    assert
      .dom('[data-test-heading="ready"]')
      .exists('the run came back and the thread is yours again');
  });

  test('the queue polls on its own clocks, on the tags it last had, and never refreshes the route', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const lists = board().askedFor(/\/api\/conversations$/).length;
    const [first] = board().askedFor(/\/api\/conversations$/);

    await clock().tick(SLOW);

    assert.strictEqual(first?.ifNoneMatch, null);
    assert.ok(
      board()
        .askedFor(/\/api\/conversations$/)
        .at(-1)?.ifNoneMatch,
      'the second read of the list is conditional',
    );
    assert.strictEqual(
      board().askedFor(/\/api\/conversations$/).length,
      lists + 1,
      'the list is read again on its own clock',
    );
    assert.strictEqual(
      board().askedFor(/\/api\/viewer$/).length,
      1,
      'the viewer is read once, not on every tick of a route refresh',
    );
    assert.deepEqual(
      board()
        .askedFor(/\/api\/pull-request$/)
        .map((one) => one.ifNoneMatch !== null),
      [false, true],
      'the pull request is asked again on the list clock, with its tag',
    );
  });

  test('the bar stops reading the dashboard once its pull request is left', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    await visit('/nowhere');
    const read = board().askedFor(/\/api\/dashboard$/).length;

    await clock().tick(SLOW);
    await clock().tick(SLOW);

    assert.strictEqual(board().askedFor(/\/api\/dashboard$/).length, read);
  });
});
