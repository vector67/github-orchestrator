import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  fillIn,
  find,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import type { Conversation, DiffLine, OperationKind } from 'frontend/data/api';
import {
  added,
  changed,
  comment,
  context,
  prDiff,
  removed,
  setupFakeBoard,
  summary,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const SLOW = 5000;

const KEY = 'draft_00000000000000aa';

function draft(over: Partial<Conversation> = {}): Conversation {
  return thread({
    key: KEY,
    github_node_id: null,
    kind: 'draft',
    state: 'draft',
    etag: '"d1"',
    gist: null,
    anchor: {
      ...thread().anchor,
      path: 'src/foo.py',
      line: 12,
      start_line: null,
      start_side: null,
      side: 'RIGHT',
      original_line: null,
      original_commit: null,
    },
    comments: [
      { id: null, author: 'octocat', created_at: null, review_state: null },
    ],
    ...over,
  });
}

function seed(board: FakeBoard, over: Partial<Conversation> = {}) {
  board.actAs('reviewer');
  board.conversations = [draft(over)];
  board.comments[KEY] = [
    comment({
      id: null,
      author: 'octocat',
      review_state: null,
      body: 'this leaks the handle',
      html_url: null,
    }),
  ];
  board.pullRequestDiff = prDiff(
    changed('src/foo.py', FOO),
    changed('src/bar.py', [added(1, 'import os')], { status: 'added' }),
  );
}

const FOO: DiffLine[] = [
  { kind: 'context', old_line: 30, new_line: 10, text: 'def read(path):' },
  removed(31, '    return open(path).read()'),
  added(11, '    handle = open(path)'),
  added(12, '    return handle.read()'),
];

const ANCHOR = '#panel-anchor';

function selected(): string[] {
  return findAll(`${ANCHOR} [data-selected]`).map(
    (one) => one.getAttribute('data-test-end') ?? '',
  );
}

function row(end: string): string {
  return `${ANCHOR} [data-test-end="${end}"]`;
}

function lastPost(board: FakeBoard) {
  return board.posted.at(-1);
}

module('Acceptance | drafts', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    seed(board());
  });

  test('a draft opens with its words on the left and its file’s diff on the right, its lines selected', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-draft-body]').hasValue('this leaks the handle');
    assert.dom('[data-test-draft-anchor]').hasText('foo.py +12');
    assert.dom('[data-test-reply-open]').doesNotExist();
    assert.dom(`${ANCHOR} [data-test-file="src/foo.py"]`).exists();
    assert
      .dom(`${ANCHOR} [data-test-file="src/bar.py"]`)
      .doesNotExist('only the draft’s file is drawn');
    assert.deepEqual(selected(), ['+12']);
  });

  test('a draft on a range across both sides opens with the range selected', async function (assert) {
    seed(board(), {
      anchor: {
        ...draft().anchor,
        start_line: 31,
        start_side: 'LEFT',
        line: 12,
      },
    });
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(selected(), ['−31', '+11', '+12']);
    assert.dom('[data-test-draft-anchor]').hasText('foo.py −31 to +12');
  });

  test('dragging across − and + lines anchors the draft there, and saving sends it under the thread tag', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await triggerEvent(`${row('−31')} [data-test-add]`, 'mousedown');
    await triggerEvent(row('+11'), 'mouseover');
    await triggerEvent(row('+11'), 'mouseup');

    assert.deepEqual(selected(), ['−31', '+11']);
    assert.dom('[data-test-draft-anchor]').hasText('foo.py −31 to +11');

    await fillIn('[data-test-draft-body]', 'this leaks the file handle');
    await click('[data-test-draft-save]');

    const sent = lastPost(board());
    assert.strictEqual(
      sent?.url,
      `/api/conversations/${KEY}/operations:edit-draft`,
    );
    assert.strictEqual(sent?.ifMatch, '"d1"');
    assert.deepEqual(sent?.body, {
      body: 'this leaks the file handle',
      path: 'src/foo.py',
      line: 11,
      start_line: 31,
      start_side: 'LEFT',
      side: 'RIGHT',
    });
  });

  test('the file button over the diff switches to another changed file, and selecting there moves the draft', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-anchor-file]').hasText('src/foo.py');

    await click('[data-test-anchor-file]');
    await click(
      `${ANCHOR} [data-test-tree-row="file"][data-path="src/bar.py"]`,
    );

    assert.dom(`${ANCHOR} [data-test-file="src/bar.py"]`).exists();
    assert.dom(`${ANCHOR} [data-test-file="src/foo.py"]`).doesNotExist();
    assert
      .dom('[data-test-draft-anchor]')
      .hasText('foo.py +12', 'looking elsewhere does not move the draft');

    await click(`${row('+1')} [data-test-new]`);

    assert.dom('[data-test-draft-anchor]').hasText('bar.py +1');
    assert.dom('[data-test-anchor-file]').hasText('src/bar.py');
  });

  test('a draft whose lines are no longer in the diff shows its file and says so', async function (assert) {
    seed(board(), { anchor: { ...draft().anchor, line: 400 } });
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-draft-gone]')
      .hasText('These lines are no longer in the diff. Select new ones.');
    assert.dom(`${ANCHOR} [data-test-file="src/foo.py"]`).exists();
    assert.deepEqual(selected(), []);

    await click(`${row('+11')} [data-test-new]`);

    assert.dom('[data-test-draft-gone]').doesNotExist();
    assert.dom('[data-test-draft-anchor]').hasText('foo.py +11');
  });

  test('the other conversations on the file are gutter markers linking to them, not cards', async function (assert) {
    board().conversations = [
      ...board().conversations,
      thread({
        key: 'k1',
        anchor: { ...draft().anchor, line: 11 },
      }),
    ];
    board().comments['k1'] = [comment({ body: 'please rename' })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom(`${row('+11')} [data-test-marker="k1"]`).exists();
    assert
      .dom(`${ANCHOR} [data-test-marker="${KEY}"]`)
      .doesNotExist('the draft itself is the selection');
    assert.dom(`${ANCHOR} [data-test-card]`).doesNotExist();

    await click(`${row('+11')} [data-test-marker="k1"]`);

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('the diff opens scrolled to the draft’s lines', async function (assert) {
    const lead = Array.from({ length: 120 }, (_, at) =>
      context(at + 1, 'pass'),
    );
    const tail = Array.from({ length: 40 }, (_, at) =>
      context(at + 122, 'pass'),
    );
    seed(board(), { anchor: { ...draft().anchor, line: 121 } });
    board().pullRequestDiff = prDiff(
      changed('src/foo.py', [
        ...lead,
        added(121, 'handle = open(path)'),
        ...tail,
      ]),
    );
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const pane = find(`${ANCHOR} [data-test-anchor-diff]`)!;
    const line = find(row('+121'))!.getBoundingClientRect();
    const shown = pane.getBoundingClientRect();
    assert.true(pane.scrollTop > 0, 'the diff scrolled');
    assert.true(line.top >= shown.top, 'the line starts inside the pane');
    assert.true(line.bottom <= shown.bottom, 'the line ends inside the pane');
  });

  test('nothing is saved while nothing has changed', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-draft-save]').isDisabled();
  });

  test('a draft with no words cannot be saved', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await fillIn('[data-test-draft-body]', '   ');
    assert.dom('[data-test-draft-save]').isDisabled();
  });

  test('a draft is added to the review under the thread tag', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="enrol"]');

    assert.strictEqual(
      lastPost(board())?.url,
      `/api/conversations/${KEY}/operations:enrol`,
    );
    assert.strictEqual(lastPost(board())?.ifMatch, '"d1"');
  });

  test('a draft with edits not saved is not added or posted', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await fillIn('[data-test-draft-body]', 'changed my mind');

    assert.dom('[data-test-decision="enrol"]').isDisabled();
    assert.dom('[data-test-decision="post-now"]').isDisabled();
    assert.dom('[data-test-decision="discard"]').isNotDisabled();
  });

  test('a line outside the diff is refused in words that say what to do', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    board().refusal = {
      status: 409,
      code: 'anchor-not-in-diff',
      detail: "src/foo.py:12 is not a line of the pull request's diff",
    };

    await click('[data-test-decision="enrol"]');

    assert
      .dom('[data-test-toast]')
      .containsText("That line is not in the pull request's diff");
  });

  test('a draft is discarded, and brought back from Done', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="discard"]');
    assert.strictEqual(
      lastPost(board())?.url,
      `/api/conversations/${KEY}/operations:discard`,
    );

    seed(board(), {
      state: 'done',
      etag: '"d2"',
      operations: [summary({ id: 'op_1', kind: 'discard' })],
    });
    await clock().tick(SLOW);
    await click('[data-test-decision="unpark"]');

    assert.strictEqual(
      lastPost(board())?.url,
      `/api/conversations/${KEY}/operations:unpark`,
    );
  });

  test('an enrolled draft is edited where it is and stays in the review', async function (assert) {
    seed(board(), { state: 'enrolled' });
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-draft-note]')
      .hasText('In your review. Changes go out when you send the review.');
    await fillIn('[data-test-draft-body]', 'this leaks the file handle');
    await click('[data-test-draft-save]');

    assert.strictEqual(
      lastPost(board())?.url,
      `/api/conversations/${KEY}/operations:edit-draft`,
    );
  });

  test('an enrolled draft moved off the diff keeps what was typed', async function (assert) {
    seed(board(), { state: 'enrolled' });
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    board().refusal = {
      status: 409,
      code: 'anchor-not-in-diff',
      detail: "src/foo.py:11 is not a line of the pull request's diff",
    };

    await click(`${row('+11')} [data-test-new]`);
    await click('[data-test-draft-save]');

    assert
      .dom('[data-test-toast]')
      .containsText("That line is not in the pull request's diff");
    assert.dom('[data-test-draft-anchor]').hasText('foo.py +11');
    assert.deepEqual(selected(), ['+11']);
  });

  test('an enrolled draft the board is still saving is not changed, and nothing is said to be going to GitHub', async function (assert) {
    seed(board(), {
      state: 'enrolled',
      operations: [
        summary({ id: 'op_1', kind: 'edit-draft', state: 'pending' }),
      ],
    });
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-draft-body]').isDisabled();
    assert.dom('[data-test-draft-save]').doesNotExist();
    assert.dom(`${ANCHOR} [data-test-add]`).doesNotExist();
    assert.dom('[data-test-anchor-file]').doesNotExist();
    await click(`${row('+11')} [data-test-new]`);
    assert.deepEqual(selected(), ['+12'], 'its lines cannot change');
    assert
      .dom('[data-test-draft-note]')
      .hasText('The board is saving this; nothing is posted to GitHub.');
  });

  test('a local draft being saved or added to the review is not said to be going to GitHub', async function (assert) {
    for (const kind of ['edit-draft', 'enrol'] satisfies OperationKind[]) {
      seed(board(), {
        operations: [summary({ id: 'op_1', kind, state: 'pending' })],
      });
      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-draft-note]')
        .hasText(
          'The board is saving this; nothing is posted to GitHub.',
          kind,
        );
      await visit('/pr/o/r/7/conversations');
    }
  });

  test('saving an edit keeps the new words in the box while the board saves it', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await fillIn('[data-test-draft-body]', 'this leaks the file handle');
    await click('[data-test-draft-save]');
    board().conversations = [
      draft({
        operations: [
          summary({ id: 'op_1', kind: 'edit-draft', state: 'pending' }),
        ],
      }),
    ];
    await clock().tick(SLOW);

    assert.dom('[data-test-draft-body]').hasValue('this leaks the file handle');
  });

  test('a draft on its way to GitHub is not changed, and says why', async function (assert) {
    seed(board(), {
      operations: [summary({ id: 'op_1', kind: 'post-now', state: 'pending' })],
    });
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-draft-body]').isDisabled();
    assert
      .dom('[data-test-draft-note]')
      .hasText(
        'On its way to GitHub; it cannot change until the board has it.',
      );
  });

  test('a new draft opens on the changed files, and is created on the lines selected in the one chosen', async function (assert) {
    board().created = 'draft_00000000000000bb';
    await visit('/pr/o/r/7/conversations');

    await click('[data-test-new-draft]');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/new-draft');
    assert.deepEqual(
      findAll(`${ANCHOR} [data-test-tree-row="file"]`).map((one) =>
        one.getAttribute('data-path'),
      ),
      ['src/bar.py', 'src/foo.py'],
    );
    assert.dom(`${ANCHOR} [data-test-pr-diff]`).doesNotExist();
    assert.dom('[data-test-draft-save]').hasText('Create draft');
    await fillIn('[data-test-draft-body]', 'why not a context manager?');
    assert
      .dom('[data-test-draft-save]')
      .isDisabled('no lines are selected yet');
    assert
      .dom('[data-test-draft-note]')
      .hasText(
        'Pick a line in the diff on the right to place this comment.',
        'the note says what the disabled button is waiting for',
      );

    await click(
      `${ANCHOR} [data-test-tree-row="file"][data-path="src/foo.py"]`,
    );

    assert.dom(`${ANCHOR} [data-test-file="src/foo.py"]`).exists();
    assert.deepEqual(selected(), []);

    await click(`${row('+12')} [data-test-add]`);

    assert.dom('[data-test-draft-anchor]').hasText('foo.py +12');
    board().conversations = [
      ...board().conversations,
      draft({ key: 'draft_00000000000000bb' }),
    ];
    await click('[data-test-draft-save]');

    const sent = lastPost(board());
    assert.strictEqual(sent?.url, '/api/operations:create-draft');
    assert.strictEqual(sent?.ifMatch, null);
    assert.deepEqual(sent?.body, {
      body: 'why not a context manager?',
      path: 'src/foo.py',
      line: 12,
      start_line: null,
      start_side: null,
      side: 'RIGHT',
    });
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/draft_00000000000000bb',
    );
  });
});
