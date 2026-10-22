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
  dashboard,
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
const COMMIT_SIZING = 'commit-box-sizing';

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

  async function sized(size: string) {
    await click('[data-test-settings-open]');
    await click('[data-test-commit-sizing-open]');
    await click(`[data-test-commit-sizing="${size}"]`);
  }

  test('commit box sizing is a choice in the settings menu, Full until you pick another, kept in this browser', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await click('[data-test-settings-open]');
    await click('[data-test-commit-sizing-open]');

    assert.dom('[data-test-commit-sizing="full"]').isChecked();
    assert.dom('[data-test-commit-sizing="minimal"]').isNotChecked();
    assert.dom('[data-test-commit-sizing="hidden"]').isNotChecked();

    await click('[data-test-commit-sizing="minimal"]');

    assert.dom('[data-test-commit-sizing="minimal"]').isChecked();
    assert.strictEqual(localStorage.getItem(COMMIT_SIZING), 'minimal');
  });

  test('Minimal is the pips alone: hovering one names its commit and clicking it goes there', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await sized('minimal');

    assert.dom('[data-test-commit-bar]').doesNotExist();
    assert.deepEqual(pips(), ['current', 'unread', 'unread']);
    assert
      .dom(findAll('[data-test-pip]')[1])
      .hasAttribute('title', `2 of 3 · ${SECOND} Name the widget`);

    await click(findAll('[data-test-pip]')[2]!);

    assert.deepEqual(pips(), ['unread', 'unread', 'current']);
    assert.dom('[data-test-pr-diff]').containsText('third change');
  });

  test('[ and ] still step in Minimal', async function (assert) {
    localStorage.setItem(COMMIT_SIZING, 'minimal');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-bar]').doesNotExist();

    await press(']');

    assert.deepEqual(pips(), ['unread', 'current', 'unread']);
    assert.dom('[data-test-pr-diff]').containsText('second change');

    await press('[');

    assert.deepEqual(pips(), ['current', 'unread', 'unread']);
  });

  test('Hidden has no bar and no stepping: the diff is the whole pull request', async function (assert) {
    localStorage.setItem(COMMIT_SIZING, 'hidden');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-stepper]').doesNotExist();
    assert.dom('[data-test-pip]').doesNotExist();
    assert.dom('[data-test-pr-diff]').containsText('every commit');
    assert.dom('[data-test-tree]').containsText('all.py');
    assert.strictEqual(board().askedFor(/\/api\/diffs\//).length, 0);
  });

  test('picking Full again brings the bar back on the commit you were on', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press(']');
    await sized('hidden');

    assert.dom('[data-test-pr-diff]').containsText('every commit');

    await click('[data-test-commit-sizing="full"]');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
    assert.strictEqual(localStorage.getItem(COMMIT_SIZING), 'full');
  });

  function reviewedOn(sha: string) {
    board().manager = dashboard({
      facts: {
        is_author: false,
        my_review: 'commented',
        my_review_at: '2026-10-20T12:00:00Z',
        my_review_sha: sha,
      },
    });
  }

  test('after your review, a note under the bar counts the commits pushed since', async function (assert) {
    reviewedOn(FIRST);
    board().readMarks = [{ sha: FIRST, subject: 'Add the widget' }];

    await visit('/pr/o/r/7/diff');

    assert
      .dom('[data-test-commit-note]')
      .hasText(
        'Picked up at the first new commit: 2 commits pushed since your review on Tue 20 Oct. ×',
      );
  });

  test('there is no note before you review, nor when nothing was pushed after your review', async function (assert) {
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-bar]').exists();
    assert.dom('[data-test-commit-note]').doesNotExist();

    reviewedOn(THIRD);
    await visit('/pr/o/r/7/dashboard');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-note]').doesNotExist();
  });

  test('× hides the note until the pull request has a new head', async function (assert) {
    reviewedOn(FIRST);
    await visit('/pr/o/r/7/diff');

    await click('[data-test-commit-note-close]');

    assert.dom('[data-test-commit-note]').doesNotExist();

    await visit('/pr/o/r/7/dashboard');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-note]').doesNotExist();

    board().commits = {
      ...board().commits,
      commits: [
        ...board().commits.commits,
        prCommit('d4d4d4d', THIRD, 'Document the widget'),
      ],
    };
    await visit('/pr/o/r/7/dashboard');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-commit-note]').includesText('3 commits pushed');
  });

  test('Minimal has no note', async function (assert) {
    reviewedOn(FIRST);
    localStorage.setItem(COMMIT_SIZING, 'minimal');

    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-pip]').exists({ count: 3 });
    assert.dom('[data-test-commit-note]').doesNotExist();
  });
});
