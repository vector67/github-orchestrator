import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, find, findAll, triggerEvent, visit } from '@ember/test-helpers';
import {
  added,
  changed,
  dashboard,
  prHistory,
  prCommit,
  prDiff,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';

const FORK = 'ba5e000';
const FIRST = 'a1a1a1a';
const SECOND = 'b2b2b2b';
const THIRD = 'c3c3c3c';

interface Dot {
  sha: string;
  lane: string;
  style: string;
  x: number;
  y: number;
}

function dots(lane: string): Dot[] {
  return findAll(`[data-test-dot][data-lane="${lane}"]`).map((one) => ({
    sha: one.getAttribute('data-sha') ?? '',
    lane,
    style: one.getAttribute('data-style') ?? '',
    x: Number(one.getAttribute('data-x')),
    y: Number(one.getAttribute('data-y')),
  }));
}

const MAIN_ONE = 'd4d4d4d';
const MAIN_TWO = 'e5e5e5e';
const COMMIT_SIZING = 'commit-box-sizing';

function pips(): (string | undefined)[] {
  return findAll('[data-test-pip]').map(
    (one) => (one as HTMLElement).dataset['state'],
  );
}

function dot(sha: string): Element {
  return find(`[data-test-dot][data-sha="${sha}"]`)!;
}

function inRange(): string[] {
  return findAll('[data-test-dot][data-in-range="true"]').map(
    (one) => one.getAttribute('data-sha') ?? '',
  );
}

function increasing(values: number[]): boolean {
  return values.every((one, index) => index === 0 || one > values[index - 1]!);
}

module('Acceptance | commit timeline', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function press(key: string) {
    return triggerEvent(document, 'keydown', { key });
  }

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

  async function dragTo(end: string, sha: string) {
    const target = dot(sha).getBoundingClientRect();
    await triggerEvent(`[data-test-handle="${end}"]`, 'pointerdown');
    await triggerEvent('[data-test-timeline-graph]', 'pointermove', {
      clientX: target.left + target.width / 2,
      clientY: target.top + target.height / 2,
    });
    await triggerEvent('[data-test-timeline-graph]', 'pointerup');
  }

  hooks.beforeEach(function () {
    board().pullRequestDiff = {
      ...prDiff(changed('src/widgets/all.py', [added(19, 'every commit')])),
      base: FORK,
      head: THIRD,
    };
    board().commits = prHistory(FORK, [
      prCommit(FIRST, FORK, 'Add the widget'),
      prCommit(SECOND, FIRST, 'Name the widget'),
      prCommit(THIRD, SECOND, 'Test the widget'),
    ]);
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
      secondToThird: {
        base: FIRST,
        head: THIRD,
        files: [
          changed('src/widgets/second.py', [added(19, 'second change')]),
          changed('src/widgets/third.py', [added(19, 'third change')]),
        ],
      },
    };
  });

  test('with main where the branch left it, the branch forks off main at its tip', async function (assert) {
    board().readMarks = [{ sha: FIRST, subject: 'Add the widget' }];
    await visit('/pr/o/r/7/diff');

    await click('[data-test-timeline-toggle]');

    assert
      .dom('[data-test-timeline-header]')
      .hasText(
        `3 commits on PROJ-7-fix-the-widget · forked from main at ${FORK}, main's tip`,
      );
    assert.dom('[data-test-behind]').doesNotExist();
    assert.dom('[data-test-since-fork]').doesNotExist();
    const main = dots('base');
    const branch = dots('pr');
    assert.deepEqual(
      main.map((one) => one.sha),
      [FORK],
    );
    assert.deepEqual(
      branch.map((one) => [one.sha, one.style]),
      [
        [FIRST, 'read'],
        [SECOND, 'unread'],
        [THIRD, 'unread'],
      ],
    );
    assert.true(
      branch.every((one) => one.y > main[0]!.y),
      'the branch runs on a lane under main',
    );
    assert.true(
      increasing([main[0]!.x, ...branch.map((one) => one.x)]),
      'the branch runs on from the fork',
    );
    assert.dom('[data-test-lane-label="main"]').hasAttribute('data-at', FORK);
    assert.dom('[data-test-lane-label="head"]').hasAttribute('data-at', THIRD);
    assert.dom('[data-test-current]').hasAttribute('data-at', SECOND);
    assert.dom('[data-test-fork-curve]').exists({ count: 1 });
  });

  test('with main moved on, main runs past the fork to its tip and the header says how far behind the branch is', async function (assert) {
    board().commits = {
      ...board().commits,
      base_tip: MAIN_TWO,
      behind: 2,
      base_commits: [
        prCommit(MAIN_ONE, FORK, 'Bump the parser'),
        prCommit(MAIN_TWO, MAIN_ONE, 'Speed up the build'),
      ],
    };
    await visit('/pr/o/r/7/diff');

    await press('t');

    assert
      .dom('[data-test-timeline-header]')
      .hasText(
        `3 commits on PROJ-7-fix-the-widget · forked from main at ${FORK} 2 behind main main's new commits aren't in this diff`,
      );
    assert.dom('[data-test-behind]').hasText('2 behind main');
    assert
      .dom('[data-test-since-fork]')
      .hasText('2 commits on main since the fork');
    const main = dots('base');
    assert.deepEqual(
      main.map((one) => one.sha),
      [FORK, MAIN_ONE, MAIN_TWO],
    );
    assert.true(
      increasing(main.map((one) => one.x)),
      'main runs on past the fork',
    );
    assert.strictEqual(
      new Set(main.map((one) => one.y)).size,
      1,
      'on one lane',
    );
    assert.true(
      dots('pr').every((one) => one.y > main[0]!.y && one.x > main[0]!.x),
      'the branch still leaves main at the fork',
    );
    assert
      .dom('[data-test-lane-label="main"]')
      .hasAttribute('data-at', MAIN_TWO);
    assert
      .dom(`[data-test-dot][data-sha="${MAIN_ONE}"] title`)
      .hasText(`${MAIN_ONE} Bump the parser`);

    await click(dot(MAIN_ONE));

    assert.dom('[data-test-commit-place]').hasText('Commit 1 of 3');
    assert.dom('[data-test-pr-diff]').containsText('first change');
  });

  test("main's commits each take their own place on its lane, even ones merged into main from elsewhere", async function (assert) {
    board().commits = {
      ...board().commits,
      base_tip: MAIN_TWO,
      behind: 2,
      base_commits: [
        prCommit(MAIN_ONE, '0ddba11', 'Fix the parser on its own branch'),
        {
          ...prCommit(MAIN_TWO, FORK, 'Merge the parser fix'),
          parents: [FORK, MAIN_ONE],
        },
      ],
    };
    await visit('/pr/o/r/7/diff');

    await press('t');

    const main = dots('base');
    assert.deepEqual(
      main.map((one) => one.sha),
      [FORK, MAIN_ONE, MAIN_TWO],
    );
    assert.true(
      increasing(main.map((one) => one.x)),
      'no two of them share a place',
    );
  });

  test('t and the Timeline button open the graph under the stepper and close it again', async function (assert) {
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-timeline]').doesNotExist();
    assert
      .dom('[data-test-timeline-toggle]')
      .hasAttribute('aria-pressed', 'false');

    await press('t');

    assert.dom('[data-test-timeline]').exists();
    assert
      .dom('[data-test-timeline-toggle]')
      .hasAttribute('aria-pressed', 'true');

    await press('t');

    assert.dom('[data-test-timeline]').doesNotExist();

    await click('[data-test-timeline-toggle]');

    assert.dom('[data-test-timeline]').exists();

    await click('[data-test-timeline-toggle]');

    assert.dom('[data-test-timeline]').doesNotExist();
  });

  test('clicking a dot shows that one commit', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press('t');

    await click(dot(THIRD));

    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
    assert.dom('[data-test-pr-diff]').containsText('third change');
    assert.dom('[data-test-current]').hasAttribute('data-at', THIRD);
    assert.deepEqual(inRange(), [THIRD]);
  });

  test('shift-click picks a range: the bar says so, its pips turn yellow and the diff is the range as one change', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press(']');
    await press('t');

    await click(dot(THIRD), { shiftKey: true });

    assert.dom('[data-test-range-pill]').hasText('range');
    assert
      .dom('[data-test-range]')
      .hasText(`${SECOND} → ${THIRD} · 2 commits · 2 files`);
    assert.dom('[data-test-back-to-stepping]').exists();
    assert.dom('[data-test-commit-bar] [data-test-timeline-toggle]').exists();
    assert.dom('[data-test-read]').doesNotExist();
    assert.deepEqual(pips(), ['unread', 'range', 'range']);
    assert.deepEqual(inRange(), [SECOND, THIRD]);
    assert.dom('[data-test-pr-diff]').containsText('second change');
    assert.dom('[data-test-pr-diff]').containsText('third change');
    assert.strictEqual(
      board().askedFor(new RegExp(`/api/diffs/${FIRST}\\.\\.${THIRD}$`)).length,
      1,
      "the diff asked for runs from the first commit's parent to the last",
    );
  });

  test('Escape and Back to stepping return to the commit you were on', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press(']');
    await press('t');
    await click(dot(THIRD), { shiftKey: true });

    assert.dom('[data-test-range]').includesText(`${SECOND} → ${THIRD}`);

    await press('Escape');

    assert.dom('[data-test-range]').doesNotExist();
    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
    assert.deepEqual(pips(), ['unread', 'current', 'unread']);
    assert.dom('[data-test-pr-diff]').containsText('second change');

    await click(dot(FIRST), { shiftKey: true });
    await click('[data-test-back-to-stepping]');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
  });

  test('dragging a handle stretches the band into a range', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press('t');

    assert.deepEqual(inRange(), [FIRST]);

    await dragTo('to', THIRD);

    assert.deepEqual(inRange(), [FIRST, SECOND, THIRD]);
    assert.dom('[data-test-range]').includesText(`${FIRST} → ${THIRD}`);

    await dragTo('from', SECOND);

    assert.deepEqual(inRange(), [SECOND, THIRD]);
    assert.dom('[data-test-range]').includesText(`${SECOND} → ${THIRD}`);
  });

  test('All picks every commit, Since my review the ones after it, This commit goes back to stepping', async function (assert) {
    reviewedOn(FIRST);
    await visit('/pr/o/r/7/diff');
    await press('t');

    assert
      .dom('[data-test-preset="this-commit"]')
      .hasAttribute('aria-pressed', 'true');

    await click('[data-test-preset="all"]');

    assert.deepEqual(inRange(), [FIRST, SECOND, THIRD]);
    assert.dom('[data-test-preset="all"]').hasAttribute('aria-pressed', 'true');
    assert
      .dom('[data-test-preset="this-commit"]')
      .hasAttribute('aria-pressed', 'false');

    await click('[data-test-preset="since-review"]');

    assert.deepEqual(inRange(), [SECOND, THIRD]);
    assert
      .dom('[data-test-range]')
      .includesText(`${SECOND} → ${THIRD} · 2 commits`);
    assert
      .dom('[data-test-preset="since-review"]')
      .hasAttribute('aria-pressed', 'true');

    await click('[data-test-preset="this-commit"]');

    assert.dom('[data-test-range]').doesNotExist();
    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 3');
    assert.deepEqual(inRange(), [SECOND]);
  });

  test('without a review Since my review cannot be picked, and with one a flag marks where it was given', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press('t');

    assert.dom('[data-test-preset="since-review"]').isDisabled();
    assert.dom('[data-test-review-flag]').doesNotExist();

    reviewedOn(FIRST);
    await visit('/pr/o/r/7/dashboard');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-preset="since-review"]').isNotDisabled();
    assert.dom('[data-test-review-flag]').hasText('you reviewed Tue 20 Oct');
    const flag = Number(
      find('[data-test-review-flag] line')!.getAttribute('x1'),
    );
    const [first, second] = dots('pr');
    assert.true(
      flag > first!.x,
      'the flag stands after the commit your review saw',
    );
    assert.true(flag < second!.x, 'and before the next');
  });

  test('in Minimal t opens the timeline under the line, with no button', async function (assert) {
    localStorage.setItem(COMMIT_SIZING, 'minimal');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-timeline-toggle]').doesNotExist();

    await press('t');

    assert.dom('[data-test-timeline]').exists();
    assert.dom('[data-test-current]').hasAttribute('data-at', FIRST);

    await click(dot(THIRD), { shiftKey: true });

    assert.deepEqual(pips(), ['range', 'range', 'range']);
    assert.dom('[data-test-range]').doesNotExist();
  });

  test('in Hidden the Timeline button sits by the origin/local switch, and the diff is the whole pull request until you pick', async function (assert) {
    localStorage.setItem(COMMIT_SIZING, 'hidden');
    await visit('/pr/o/r/7/diff');

    assert.dom('[data-test-diff-sources] [data-test-timeline-toggle]').exists();

    await click('[data-test-timeline-toggle]');

    assert.dom('[data-test-timeline]').exists();
    assert.dom('[data-test-current]').doesNotExist();
    assert.deepEqual(inRange(), [FIRST, SECOND, THIRD]);
    assert.dom('[data-test-preset="all"]').hasAttribute('aria-pressed', 'true');
    assert.dom('[data-test-pr-diff]').containsText('every commit');

    await click(dot(SECOND));

    assert.deepEqual(inRange(), [SECOND]);
    assert.dom('[data-test-pr-diff]').containsText('second change');

    await press('Escape');

    assert.deepEqual(inRange(), [FIRST, SECOND, THIRD]);
    assert.dom('[data-test-pr-diff]').containsText('every commit');
  });
});

const MERGE = 'f6f6f6f';
const SKIP_MERGES = 'commit-skip-merges';

module('Acceptance | commit timeline with main merged in', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function press(key: string) {
    return triggerEvent(document, 'keydown', { key });
  }

  hooks.beforeEach(function () {
    board().pullRequestDiff = {
      ...prDiff(changed('src/widgets/all.py', [added(19, 'every commit')])),
      base: MAIN_ONE,
      head: THIRD,
    };
    board().commits = prHistory(MAIN_ONE, [
      prCommit(FIRST, FORK, 'Add the widget'),
      prCommit(SECOND, FIRST, 'Name the widget'),
      {
        ...prCommit(MERGE, SECOND, "Merge branch 'main'"),
        parents: [SECOND, MAIN_ONE],
      },
      prCommit(THIRD, MERGE, 'Test the widget'),
    ]);
    board().diffs = {
      second: {
        base: FIRST,
        head: SECOND,
        files: [changed('src/widgets/second.py', [added(19, 'second change')])],
      },
      merge: {
        base: SECOND,
        head: MERGE,
        files: [
          changed('src/parser.py', [added(19, 'from main')]),
          changed('src/widgets/mended.py', [added(19, 'came from main')]),
        ],
      },
      mergeOwn: {
        base: SECOND,
        head: MERGE,
        merged: MAIN_ONE,
        files: [changed('src/widgets/mended.py', [added(19, 'the fix')])],
      },
      third: {
        base: MERGE,
        head: THIRD,
        files: [changed('src/widgets/third.py', [added(19, 'third change')])],
      },
      firstToThird: {
        base: FORK,
        head: THIRD,
        merged: MAIN_ONE,
        files: [changed('src/widgets/third.py', [added(19, 'all but main')])],
      },
    };
    board().readMarks = [{ sha: FIRST, subject: 'Add the widget' }];
  });

  test('a merge is a diamond on the branch with a curve down from the main commit it pulled in', async function (assert) {
    await visit('/pr/o/r/7/diff');

    await press('t');

    assert
      .dom('[data-test-timeline-header]')
      .hasText(
        `3 commits and 1 merge on PROJ-7-fix-the-widget · last synced with main at ${MAIN_ONE}, main's tip`,
      );
    assert.deepEqual(
      dots('base').map((one) => one.sha),
      [FORK, MAIN_ONE],
    );
    assert.deepEqual(
      dots('pr').map((one) => one.sha),
      [FIRST, SECOND, MERGE, THIRD],
    );
    assert.dom(dot(MERGE)).hasAttribute('data-shape', 'diamond');
    assert.dom(dot(SECOND)).hasAttribute('data-shape', 'dot');
    assert.dom('[data-test-merge-curve]').exists({ count: 1 });
    assert.dom('[data-test-fork-curve]').exists({ count: 1 });
    assert.true(
      Number(dot(MAIN_ONE).getAttribute('data-x')) <
        Number(dot(MERGE).getAttribute('data-x')),
      'the main commit it pulled in comes before the merge',
    );
  });

  test('stepping skips merges while the box is ticked, and its pip is striped', async function (assert) {
    await visit('/pr/o/r/7/diff');

    assert.deepEqual(
      findAll('[data-test-pip]').map((one) => one.hasAttribute('data-merge')),
      [false, false, true, false],
    );
    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 4');

    await press(']');

    assert.dom('[data-test-commit-place]').hasText('Commit 4 of 4');
    assert.dom('[data-test-pr-diff]').containsText('third change');

    await press('[');

    assert.dom('[data-test-commit-place]').hasText('Commit 2 of 4');
  });

  test('unticked, stepping stops on a merge and shows only what it changed on its own', async function (assert) {
    localStorage.setItem(SKIP_MERGES, 'false');
    await visit('/pr/o/r/7/diff');

    await press(']');

    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 4');
    assert.dom('[data-test-merge-pill]').hasText('merge');
    assert.dom('[data-test-pr-diff]').containsText('the fix');
    assert.dom('[data-test-pr-diff]').doesNotContainText('from main');
    assert.strictEqual(
      board().askedFor(
        new RegExp(`/api/diffs/${SECOND}\\.\\.${MERGE}\\?merged=${MAIN_ONE}$`),
      ).length,
      1,
      "the diff asked for is the merge's own",
    );
    assert
      .dom('[data-test-merge-note]')
      .hasText(
        '1 file came in from main and is hidden. This merge changed 1 file on its own: src/widgets/mended.py Skip merges when stepping',
      );
    assert.dom('[data-test-skip-merges]').isNotChecked();

    await click('[data-test-skip-merges]');

    assert.strictEqual(localStorage.getItem(SKIP_MERGES), 'true');
    await press('[');
    await press(']');
    assert.dom('[data-test-commit-place]').hasText('Commit 4 of 4');
  });

  test('picked in the timeline a merge is shown even while merges are skipped', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press('t');

    await click(dot(MERGE));

    assert.dom('[data-test-commit-place]').hasText('Commit 3 of 4');
    assert.dom('[data-test-merge-pill]').exists();
    assert.dom('[data-test-skip-merges]').isChecked();
    assert.dom('[data-test-pr-diff]').containsText('the fix');
  });

  test('a range across a merge leaves out what came in from main', async function (assert) {
    await visit('/pr/o/r/7/diff');
    await press('t');

    await click(dot(FIRST));
    await click(dot(THIRD), { shiftKey: true });

    assert.dom('[data-test-pr-diff]').containsText('all but main');
    assert.strictEqual(
      board().askedFor(
        new RegExp(`/api/diffs/${FORK}\\.\\.${THIRD}\\?merged=${MAIN_ONE}$`),
      ).length,
      1,
    );
  });
});
