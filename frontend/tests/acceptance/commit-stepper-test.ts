import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  added,
  changed,
  heldPr,
  prCommit,
  prDiff,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

const FORK = 'ba5e000';
const FIRST = 'a1a1a1a';
const SECOND = 'b2b2b2b';
const THIRD = 'c3c3c3c';

function pips(): (string | undefined)[] {
  return findAll('[data-test-pip]').map(
    (one) => (one as HTMLElement).dataset['state'],
  );
}

module('Acceptance | commit stepper', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function press(key: string) {
    return triggerEvent(document, 'keydown', { key });
  }

  hooks.beforeEach(function () {
    board().pullRequestDiff = {
      ...prDiff(changed('src/widgets/all.py', [added(19, 'every commit')])),
      base: FORK,
      head: THIRD,
    };
    board().commits = {
      fork: FORK,
      commits: [
        prCommit(FIRST, FORK, 'Add the widget'),
        prCommit(SECOND, FIRST, 'Name the widget'),
        prCommit(THIRD, SECOND, 'Test the widget'),
      ],
    };
    board().diffs = {
      first: {
        base: FORK,
        head: FIRST,
        files: [changed('src/widgets/first.py', [added(19, 'first change')])],
      },
      second: {
        base: FIRST,
        head: SECOND,
        files: [changed('src/widgets/second.py', [added(19, 'second change')])],
      },
      third: {
        base: SECOND,
        head: THIRD,
        files: [changed('src/widgets/third.py', [added(19, 'third change')])],
      },
    };
  });

  test('it opens on the first commit you have not read, and draws only that commit', async function (assert) {
    board().readMarks = [{ sha: FIRST, subject: 'Add the widget' }];

    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
    assert.dom('[data-test-commit-bar]').containsText(SECOND);
    assert.dom('[data-test-commit-bar]').containsText('Name the widget');
    assert.dom('[data-test-commit-bar]').containsText('Anna Example');
    assert.deepEqual(pips(), ['read', 'current', 'unread']);
    assert.dom('[data-test-read]').isNotChecked();
    assert.dom('[data-test-pr-diff]').containsText('second change');
    assert.dom('[data-test-pr-diff]').doesNotContainText('every commit');
    assert.dom('[data-test-tree]').containsText('second.py');
    assert.dom('[data-test-tree]').doesNotContainText('all.py');
    assert.strictEqual(
      board().askedFor(new RegExp(`/api/diffs/${FIRST}\\.\\.${SECOND}$`))
        .length,
      1,
      "the diff asked for is the commit's own range",
    );
  });

  test('it opens on the last commit when every commit is read', async function (assert) {
    board().readMarks = [
      { sha: FIRST, subject: 'Add the widget' },
      { sha: SECOND, subject: 'Name the widget' },
      { sha: THIRD, subject: 'Test the widget' },
    ];

    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
    assert.deepEqual(pips(), ['read', 'read', 'current']);
    assert.dom('[data-test-read]').isChecked();
    assert.dom('[data-test-pr-diff]').containsText('third change');
  });

  test('] and Next step on, [ and Prev step back', async function (assert) {
    await visit('/pr/o/r/7/diff');

    await press(']');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
    assert.dom('[data-test-pr-diff]').containsText('second change');

    await click('[data-test-step="next"]');

    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');

    await press('[');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');

    await click('[data-test-step="previous"]');

    assert.dom('[data-test-commit-place]').hasText('Commit 1 of 3');
    assert.dom('[data-test-pr-diff]').containsText('first change');
  });

  test('[ at the first commit and ] at the last do nothing, not even switch pull request', async function (assert) {
    board().held = [heldPr({ number: 6 }), heldPr(), heldPr({ number: 8 })];
    await visit('/pr/o/r/7/diff');

    await press('[');

    assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
    assert.dom('[data-test-commit-place]').hasText('Commit 1 of 3');
    assert.dom('[data-test-step="previous"]').isDisabled();

    await press(']');
    await press(']');
    await press(']');

    assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
    assert.dom('[data-test-step="next"]').isDisabled();
  });

  test('ticking Read keeps the mark on the server and leaves you on the commit', async function (assert) {
    await visit('/pr/o/r/7/diff');

    await click('[data-test-read]');

    assert.deepEqual(board().readMarks, [
      { sha: FIRST, subject: 'Add the widget' },
    ]);
    assert.dom('[data-test-read]').isChecked();
    assert.dom('[data-test-commit-place]').hasText('Commit 1 of 3');
    assert.deepEqual(pips(), ['current', 'unread', 'unread']);

    await press(']');

    assert.deepEqual(pips(), ['read', 'current', 'unread']);

    await press('[');
    await click('[data-test-read]');

    assert.deepEqual(board().readMarks, []);
    assert.dom('[data-test-read]').isNotChecked();
  });

  test('[ and ] still step once the Read box has the focus', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await click('[data-test-read]');

    await triggerEvent('[data-test-read]', 'keydown', { key: ']' });

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
  });

  test('a pull request with no commits of its own shows its whole diff and no bar', async function (assert) {
    board().commits = { fork: FORK, commits: [] };

    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-bar]').doesNotExist();
    assert.dom('[data-test-pr-diff]').containsText('every commit');
  });

  test('threads and commenting are on the last commit, whose lines are the head, and not on earlier ones', async function (assert) {
    board().conversations = [
      thread({
        anchor: {
          ...thread().anchor,
          path: 'src/widgets/third.py',
          line: 19,
        },
      }),
    ];
    board().readMarks = [
      { sha: FIRST, subject: 'Add the widget' },
      { sha: SECOND, subject: 'Name the widget' },
    ];
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-pr-diff] [data-test-inline]').exists();
    assert.dom('[data-test-pr-diff] [data-test-add]').exists();

    await press('[');

    assert.dom('[data-test-pr-diff]').containsText('second change');
    assert.dom('[data-test-pr-diff] [data-test-inline]').doesNotExist();
    assert.dom('[data-test-pr-diff] [data-test-add]').doesNotExist();
  });
});
