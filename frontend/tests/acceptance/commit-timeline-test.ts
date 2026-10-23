import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  triggerEvent,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import {
  added,
  changed,
  dashboard,
  heldPr,
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

function inside(inner: DOMRect, outer: DOMRect): boolean {
  return (
    outer.left <= inner.left &&
    inner.right <= outer.right &&
    outer.top <= inner.top &&
    inner.bottom <= outer.bottom
  );
}

function keyed(): string[] {
  return findAll('[data-test-key]').map(
    (one) => one.getAttribute('data-test-key') ?? '',
  );
}

const PLAIN_KEY = ['unread', 'read', 'current', 'base', 'band'];

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
    assert.deepEqual(keyed(), PLAIN_KEY, 'the key names only what is drawn');
    assert.true(
      Number(find('[data-test-timeline-graph]')!.getAttribute('width')) <
        (find('.timeline-scroll') as HTMLElement).clientWidth,
      'a short branch is not stretched across the whole pane',
    );
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
    assert.deepEqual(keyed(), [...PLAIN_KEY, 'merge', 'merge-pip']);
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

const STACK_ONE = '5a5a5a5';
const STACK_TWO = '6b6b6b6';
const BASE_BRANCH = 'PROJ-6-the-base';

module(
  'Acceptance | commit timeline stacked on another pull request',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    hooks.beforeEach(function () {
      board().pullRequest = {
        ...board().pullRequest,
        base_branch: BASE_BRANCH,
      };
      board().held = [
        heldPr({ number: 6, dashboard: { pr: { branch: BASE_BRANCH } } }),
        heldPr({ dashboard: { pr: { base_branch: BASE_BRANCH } } }),
      ];
      board().pullRequestDiff = {
        ...prDiff(changed('src/widgets/all.py', [added(19, 'every commit')])),
        base: STACK_TWO,
        head: SECOND,
      };
      board().commits = {
        ...prHistory(STACK_TWO, [
          prCommit(FIRST, STACK_TWO, 'Add the widget'),
          prCommit(SECOND, FIRST, 'Name the widget'),
        ]),
        stack: {
          branch: 'main',
          fork: FORK,
          commits: [
            prCommit(STACK_ONE, FORK, 'Lay the base'),
            prCommit(STACK_TWO, STACK_ONE, 'Finish the base'),
          ],
        },
      };
    });

    test("three lanes: main, the base pull request's commits, and this one's off it", async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert
        .dom('[data-test-timeline-header]')
        .hasText(
          `2 commits on PROJ-7-fix-the-widget · base is #6 ${BASE_BRANCH}, which is based on main`,
        );
      assert.deepEqual(
        dots('base').map((one) => one.sha),
        [FORK],
      );
      const stacked = dots('stack');
      assert.deepEqual(
        stacked.map((one) => [one.sha, one.style]),
        [
          [STACK_ONE, 'stack'],
          [STACK_TWO, 'stack'],
        ],
      );
      const branch = dots('pr');
      assert.deepEqual(
        branch.map((one) => one.sha),
        [FIRST, SECOND],
      );
      assert.true(
        dots('base')[0]!.y < stacked[0]!.y,
        'main above the base pull request',
      );
      assert.true(stacked[0]!.y < branch[0]!.y, 'and this one under it');
      assert.true(
        branch[0]!.x > stacked[1]!.x,
        'this branch forks off the base pull request',
      );
      assert.dom('[data-test-lane-label="main"]').hasText('main');
      assert.dom('[data-test-lane-label="stack"]').hasText(`#6 ${BASE_BRANCH}`);
      assert.dom('[data-test-commit-place]').hasText('Commit 1 of 2');
      assert.dom(dot(STACK_ONE)).doesNotHaveAttribute('data-pickable');
      assert
        .dom('[data-test-timeline-key]')
        .includesText(`main ${BASE_BRANCH}`);

      await click('[data-test-lane-label="stack"]');

      assert.strictEqual(currentURL(), '/pr/o/r/6/diff');
    });
  },
);

function mainRun(count: number): string[] {
  return Array.from(
    { length: count },
    (_, index) => `${(index + 1).toString(16).padStart(2, '0')}e0000`,
  );
}

module('Acceptance | commit timeline far behind main', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function behind(count: number, sent: number[]) {
    const run = mainRun(count);
    board().commits = {
      ...prHistory(FORK, [
        prCommit(FIRST, FORK, 'Add the widget'),
        prCommit(SECOND, FIRST, 'Name the widget'),
      ]),
      fork_at: '2026-10-01T09:00:00Z',
      behind: count,
      base_tip: run.at(-1)!,
      base_commits: sent.map((index) =>
        prCommit(run[index]!, run[index - 1] ?? FORK, `main ${index}`),
      ),
    };
    return run;
  }

  function range(from: number, to: number): number[] {
    return Array.from({ length: to - from }, (_, index) => from + index);
  }

  test("past twenty commits behind, main's run up to its last two folds into a pill that lists them", async function (assert) {
    const run = behind(25, [...range(0, 10), ...range(15, 25)]);
    await visit('/pr/o/r/7/diff');

    await click('[data-test-timeline-toggle]');

    assert.deepEqual(
      dots('base').map((one) => one.sha),
      [FORK, run[23], run[24]],
    );
    assert.dom('[data-test-collapsed]').hasText('⋯ 23 more');
    const box = (selector: string) => find(selector)!.getBoundingClientRect();
    const apart = (one: DOMRect, other: DOMRect) =>
      one.bottom <= other.top ||
      other.bottom <= one.top ||
      one.right <= other.left ||
      other.right <= one.left;
    const caption = box('[data-test-since-fork] text');
    const pillBox = box('[data-test-collapsed] rect');
    const since = box('[data-test-since-fork] rect');
    assert.true(apart(caption, pillBox), 'the caption stays clear of the pill');
    assert.true(
      findAll('[data-test-date]').every((one) =>
        apart(caption, one.getBoundingClientRect()),
      ),
      'and of the dates',
    );
    assert.true(
      inside(pillBox, since),
      "the pill sits inside the box of main's commits since the fork",
    );
    const pill = Number(find('[data-test-collapsed]')!.getAttribute('data-x'));
    const [fork, beforeTip] = dots('base');
    assert.true(pill > fork!.x, 'after the fork');
    assert.true(pill < beforeTip!.x, "and before main's last two");
    assert.deepEqual(
      findAll('[data-test-date]').map((one) => one.textContent?.trim()),
      ['Thu 1 Oct', 'Tue 20 Oct'],
    );
    assert
      .dom('[data-test-since-fork]')
      .hasText('25 commits on main since the fork');
    assert.dom('[data-test-behind]').hasText('25 behind main');
    assert.dom('[data-test-collapsed-list]').doesNotExist();

    await click('[data-test-collapsed]');

    const listed = findAll('[data-test-collapsed-list] li').map((one) =>
      one.textContent?.replace(/\s+/g, ' ').trim(),
    );
    assert.strictEqual(listed.length, 19);
    assert.strictEqual(listed[0], `${run[0]} main 0`);
    assert.strictEqual(listed[10], '⋯ 5 more');
    assert.strictEqual(listed.at(-1), `${run[22]} main 22`);
    assert.dom('[data-test-collapsed-list] [data-pickable]').doesNotExist();

    await click('[data-test-collapsed]');

    assert.dom('[data-test-collapsed-list]').doesNotExist();
  });

  test('twenty behind, every one of them is a dot of its own', async function (assert) {
    behind(20, range(0, 20));
    await visit('/pr/o/r/7/diff');

    await click('[data-test-timeline-toggle]');

    assert.dom('[data-test-collapsed]').doesNotExist();
    assert.strictEqual(dots('base').length, 21);
  });
});

module(
  'Acceptance | commit timeline for a long pull request',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    const DAYS = ['2026-10-19', '2026-10-20', '2026-10-21'];

    function long(count: number): string[] {
      const shas = Array.from(
        { length: count },
        (_, index) => `${(index + 1).toString(16).padStart(2, '0')}c0000`,
      );
      board().commits = prHistory(
        FORK,
        shas.map((sha, index) => ({
          ...prCommit(sha, shas[index - 1] ?? FORK, `step ${index}`),
          authored_at: `${DAYS[Math.floor((index * DAYS.length) / count)]}T09:${String(index).padStart(2, '0')}:00Z`,
        })),
      );
      return shas;
    }

    function shasShown(): string[] {
      return findAll('[data-test-sha]').map((one) => one.textContent.trim());
    }

    test('past twenty commits the dots turn to ticks, shas show only where you are, and a day row marks each day', async function (assert) {
      const shas = long(24);
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert.true(
        dots('pr').every(
          (one) => dot(one.sha).getAttribute('data-shape') === 'tick',
        ),
      );
      assert.deepEqual(shasShown(), [shas[0]]);
      assert.deepEqual(keyed(), [...PLAIN_KEY, 'tick']);
      const days = findAll('[data-test-day]');
      assert.deepEqual(
        days.map((one) => one.textContent.trim()),
        ['Mon 19 Oct', 'Tue 20 Oct', 'Wed 21 Oct'],
      );
      assert.deepEqual(
        days.map((one) => Number(one.getAttribute('data-x'))),
        [shas[0], shas[8], shas[16]].map((sha) =>
          Number(dot(sha!).getAttribute('data-x')),
        ),
        'each day starts at its first commit',
      );
      assert
        .dom('[data-test-commit-stepper] .commit-pips')
        .hasAttribute('data-thin');
      assert.strictEqual(findAll('[data-test-pip]').length, 24);

      await click(dot(shas[3]!));
      await click(dot(shas[10]!), { shiftKey: true });

      assert.deepEqual(shasShown(), [shas[3], shas[10]]);
    });

    test('the graph spreads its columns across the pane, and again when the pane changes width', async function (assert) {
      long(24);
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      const pane = find('.timeline-scroll') as HTMLElement;
      const drawn = () =>
        Number(find('[data-test-timeline-graph]')!.getAttribute('width'));
      await waitUntil(() => drawn() === pane.clientWidth);

      assert.strictEqual(drawn(), pane.clientWidth, 'it fills the pane');

      const before = pane.clientWidth;
      pane.style.width = `${before - 80}px`;
      await waitUntil(() => drawn() === pane.clientWidth);

      assert.strictEqual(
        drawn(),
        before - 80,
        'and fills it again once narrower',
      );
    });

    test('twenty commits keep their dots, their shas and their pips', async function (assert) {
      long(20);
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert.dom('[data-test-dot][data-shape="tick"]').doesNotExist();
      assert.strictEqual(shasShown().length, 20);
      assert.dom('[data-test-day]').doesNotExist();
      assert
        .dom('[data-test-commit-stepper] .commit-pips')
        .doesNotHaveAttribute('data-thin');
    });
  },
);

const FOURTH = 'd4e4f4a';

module(
  'Acceptance | commit timeline with commits not pushed',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    hooks.beforeEach(function () {
      const pushed = [
        prCommit(FIRST, FORK, 'Add the widget'),
        prCommit(SECOND, FIRST, 'Name the widget'),
      ];
      board().commits = prHistory(FORK, pushed);
      board().localCommits = prHistory(FORK, [
        ...pushed,
        prCommit(THIRD, SECOND, 'Test the widget'),
        prCommit(FOURTH, THIRD, 'Document the widget'),
      ]);
      board().readMarks = [
        { sha: FIRST, subject: 'Add the widget' },
        { sha: SECOND, subject: 'Name the widget' },
      ];
    });

    test('on local the commits not pushed run on past an origin flag, dashed, to a local label', async function (assert) {
      await visit('/pr/o/r/7/diff');
      await click('[data-test-source="local"]');

      await click('[data-test-timeline-toggle]');

      assert.deepEqual(
        dots('pr').map((one) => [
          one.sha,
          dot(one.sha).getAttribute('data-pushed'),
        ]),
        [
          [FIRST, 'true'],
          [SECOND, 'true'],
          [THIRD, 'false'],
          [FOURTH, 'false'],
        ],
      );
      assert
        .dom('[data-test-lane-label="origin"]')
        .hasAttribute('data-at', SECOND);
      assert
        .dom('[data-test-lane-label="local"]')
        .hasAttribute('data-at', FOURTH);
      assert.dom('[data-test-lane-label="head"]').doesNotExist();
      const word = find(
        '[data-test-lane-label="local"]',
      )!.getBoundingClientRect();
      const frame = find(
        '[data-test-label-box="local"]',
      )!.getBoundingClientRect();
      assert.true(
        inside(word, frame),
        'the local label sits in a box of its own',
      );
      assert.dom('[data-test-label-box]').exists({ count: 1 });
      assert.deepEqual(keyed(), [...PLAIN_KEY, 'not-pushed']);
      assert.dom('[data-test-unpushed-lane]').exists({ count: 1 });
      assert.dom('[data-test-commit-place]').hasText('Commit 3 of 4');
      assert.dom('[data-test-not-pushed]').hasText('not pushed');

      await press('[');

      assert.dom('[data-test-not-pushed]').doesNotExist();
    });

    test('on origin they are not drawn', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert.deepEqual(
        dots('pr').map((one) => one.sha),
        [FIRST, SECOND],
      );
      assert.dom('[data-pushed="false"]').doesNotExist();
      assert.dom('[data-test-lane-label="origin"]').doesNotExist();
      assert
        .dom('[data-test-lane-label="head"]')
        .hasAttribute('data-at', SECOND);
      assert.dom('[data-test-not-pushed]').doesNotExist();
    });

    function press(key: string) {
      return triggerEvent(document, 'keydown', { key });
    }
  },
);

const STALE_ONE = '5a5a5a5';
const STALE_TWO = '6b6b6b6';
const STALE_FORK = '01d0000';

module(
  'Acceptance | commit timeline with a worktree diverged from origin',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    hooks.beforeEach(function () {
      board().manager = dashboard({
        facts: {
          is_author: false,
          my_review: 'commented',
          my_review_at: '2026-10-20T12:00:00Z',
          my_review_sha: STALE_TWO,
        },
      });
      board().commits = prHistory(FORK, [
        prCommit(FIRST, FORK, 'Add the widget'),
        prCommit(SECOND, FIRST, 'Name the widget'),
        prCommit(THIRD, SECOND, 'Test the widget'),
      ]);
      board().localCommits = {
        ...prHistory(STALE_FORK, [
          prCommit(STALE_ONE, STALE_FORK, 'Add the widget'),
          prCommit(STALE_TWO, STALE_ONE, 'Name the widget'),
        ]),
        base_tip: FORK,
        base_commits: [prCommit(FORK, STALE_FORK, 'Bump the parser')],
        behind: 1,
      };
    });

    test("on local origin's commits get a grey lane of their own between main and the worktree's", async function (assert) {
      await visit('/pr/o/r/7/diff');
      await click('[data-test-source="local"]');

      await click('[data-test-timeline-toggle]');

      const [onOrigin, here, [fork]] = [
        dots('origin'),
        dots('pr'),
        dots('base').filter((one) => one.sha === FORK),
      ];
      assert.deepEqual(
        onOrigin.map((one) => [one.sha, one.style]),
        [
          [FIRST, 'origin'],
          [SECOND, 'origin'],
          [THIRD, 'origin'],
        ],
      );
      assert.deepEqual(
        here.map((one) => one.sha),
        [STALE_ONE, STALE_TWO],
      );
      assert.true(fork!.y < onOrigin[0]!.y, 'origin under main');
      assert.true(onOrigin[0]!.y < here[0]!.y, 'the worktree under origin');
      assert.true(
        onOrigin[0]!.x > fork!.x,
        "origin's lane forks from origin's fork",
      );
      assert
        .dom('[data-test-dot][data-lane="origin"][data-pickable]')
        .doesNotExist();
      assert.dom('[data-pushed="false"]').doesNotExist();
      assert.dom('[data-test-unpushed-lane]').doesNotExist();
      assert
        .dom('[data-test-lane-label="origin"]')
        .hasAttribute('data-at', THIRD);
      assert
        .dom('[data-test-lane-label="local"]')
        .hasAttribute('data-at', STALE_TWO);
      assert.dom('[data-test-label-box]').exists({ count: 2 });
      assert.dom('[data-test-lane-label="head"]').doesNotExist();
      assert.dom('[data-test-review-flag]').doesNotExist();
      assert.deepEqual(keyed(), [...PLAIN_KEY, 'origin']);
    });

    test('on local the header counts the worktree and origin apart, and the stepper says its commit is not on origin', async function (assert) {
      await visit('/pr/o/r/7/diff');
      await click('[data-test-source="local"]');

      await click('[data-test-timeline-toggle]');

      assert
        .dom('[data-test-timeline-header]')
        .hasText(
          `2 commits in the worktree · forked from main at ${STALE_FORK} · origin has 3 other commits from ${FORK} diverged from origin · 2 here, 3 on origin Reset to origin`,
        );
      assert
        .dom('[data-test-diverged]')
        .hasText('diverged from origin · 2 here, 3 on origin');
      assert.dom('[data-test-not-pushed]').hasText('not on origin');
    });

    test("clicking one of origin's commits picks nothing", async function (assert) {
      await visit('/pr/o/r/7/diff');
      await click('[data-test-source="local"]');
      await click('[data-test-timeline-toggle]');
      assert.dom('[data-test-commit-place]').hasText('Commit 1 of 2');

      await click(dot(FIRST));

      assert.dom('[data-test-commit-place]').hasText('Commit 1 of 2');
      assert.dom(dot(FIRST)).hasAttribute('data-in-range', 'false');
    });

    async function openLocal() {
      await visit('/pr/o/r/7/diff');
      await click('[data-test-source="local"]');
      await click('[data-test-timeline-toggle]');
    }

    function resets(): number {
      return board().posted.filter((one) => one.verb === 'reset-to-origin')
        .length;
    }

    test('Reset to origin asks on the page first, then puts the worktree on origin', async function (assert) {
      await openLocal();

      await click('[data-test-reset-to-origin]');

      assert
        .dom('[data-test-reset-confirm]')
        .hasText(
          "Reset the worktree to origin? Its 2 commits that aren't on origin will be dropped. Reset Cancel",
        );
      assert.strictEqual(resets(), 0, 'nothing is sent before Reset');

      await click('[data-test-reset-yes]');

      assert.strictEqual(resets(), 1);
      assert.dom('[data-test-reset-confirm]').doesNotExist();
      assert.deepEqual(
        dots('pr').map((one) => one.sha),
        [FIRST, SECOND, THIRD],
      );
      assert.dom('[data-test-dot][data-lane="origin"]').doesNotExist();
      assert.dom('[data-test-diverged]').doesNotExist();
    });

    test('Cancel leaves the worktree as it is', async function (assert) {
      await openLocal();
      await click('[data-test-reset-to-origin]');

      await click('[data-test-reset-no]');

      assert.dom('[data-test-reset-confirm]').doesNotExist();
      assert.strictEqual(resets(), 0);
      assert.dom('[data-test-diverged]').exists();
    });

    test('a refused reset says why and leaves the drawing as it was', async function (assert) {
      await openLocal();
      await click('[data-test-reset-to-origin]');
      board().refusal = {
        status: 409,
        code: 'uncommitted-changes',
        detail: 'the worktree has uncommitted changes, so it was left as it is',
      };

      await click('[data-test-reset-yes]');

      assert
        .dom('[data-test-reset-refused]')
        .hasText(
          'Not reset: the worktree has uncommitted changes, so it was left as it is',
        );
      assert.deepEqual(
        dots('pr').map((one) => one.sha),
        [STALE_ONE, STALE_TWO],
      );
      assert.dom('[data-test-diverged]').exists();
    });

    test('on origin there is no second lane and nothing about the worktree', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert.dom('[data-test-dot][data-lane="origin"]').doesNotExist();
      assert.dom('[data-test-diverged]').doesNotExist();
      assert.dom('[data-test-not-pushed]').doesNotExist();
      assert.dom('[data-test-review-flag]').doesNotExist();
      assert.deepEqual(keyed(), PLAIN_KEY);
    });
  },
);

const OLD_FORK = '0f0f0f0';
const OLD_ONE = '1e1e1e1';
const OLD_TWO = '2d2d2d2';
const NEW_FORK = 'e5e5e5e';

module(
  'Acceptance | commit timeline rebased since your review',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    function rebasedOnto(...subjects: string[]) {
      const shas = [FIRST, SECOND, THIRD];
      board().commits = {
        ...prHistory(
          NEW_FORK,
          subjects.map((subject, index) =>
            prCommit(shas[index]!, shas[index - 1] ?? NEW_FORK, subject),
          ),
        ),
        reviewed: {
          sha: OLD_TWO,
          fork: OLD_FORK,
          commits: [
            prCommit(OLD_ONE, OLD_FORK, 'Add the widget'),
            prCommit(OLD_TWO, OLD_ONE, 'Name the widget'),
          ],
        },
      };
    }

    hooks.beforeEach(function () {
      board().manager = dashboard({
        facts: {
          is_author: false,
          my_review: 'commented',
          my_review_at: '2026-10-20T12:00:00Z',
          my_review_sha: OLD_TWO,
          force_pushed_at: '2026-10-21T08:00:00Z',
        },
      });
      board().readMarks = [
        { sha: OLD_ONE, subject: 'Add the widget' },
        { sha: OLD_TWO, subject: 'Name the widget' },
      ];
      board().diffs = {
        first: {
          base: NEW_FORK,
          head: FIRST,
          files: [changed('src/widgets/first.py', [added(19, 'first change')])],
        },
        third: {
          base: SECOND,
          head: THIRD,
          files: [changed('src/widgets/third.py', [added(19, 'third change')])],
        },
      };
    });

    test('what your review saw hangs off the old fork as a ghost lane under the branch, and cannot be picked', async function (assert) {
      rebasedOnto('Add the widget', 'Name the widget', 'Test the widget');
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      const ghosts = dots('ghost');
      const branch = dots('pr');
      assert.deepEqual(
        ghosts.map((one) => [one.sha, one.style]),
        [
          [OLD_ONE, 'ghost'],
          [OLD_TWO, 'ghost'],
        ],
      );
      assert.true(
        ghosts.every((one) => one.y > branch[0]!.y),
        'the ghost lane runs under the branch',
      );
      assert.true(
        dots('base').find((one) => one.sha === OLD_FORK)!.x <
          dots('base').find((one) => one.sha === NEW_FORK)!.x,
        'the old fork comes before the new one on main',
      );
      assert.dom('[data-test-ghost-lane]').exists({ count: 1 });
      assert
        .dom('[data-test-lane-label="old-fork"]')
        .hasAttribute('data-at', OLD_FORK);
      assert
        .dom('[data-test-lane-label="fork"]')
        .hasAttribute('data-at', NEW_FORK);
      assert
        .dom('[data-test-timeline-header]')
        .hasText(
          `3 commits on PROJ-7-fix-the-widget · now forked from main at ${NEW_FORK}, was ${OLD_FORK}`,
        );
      assert
        .dom('[data-test-ghost-shas]')
        .hasText(`your review saw ${OLD_ONE} ${OLD_TWO}, rewritten since`);
      assert.dom('[data-test-review-flag]').hasText('you reviewed Tue 20 Oct');
      const flag = Number(
        find('[data-test-review-flag] line')!.getAttribute('x1'),
      );
      assert.true(
        flag > ghosts[1]!.x,
        'the flag stands after the reviewed ghost',
      );
      assert
        .dom(`[data-test-dot][data-sha="${OLD_ONE}"]`)
        .doesNotHaveAttribute('data-pickable');

      await click(`[data-test-dot][data-sha="${OLD_ONE}"]`);

      assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
      assert.dom('[data-test-range]').doesNotExist();
    });

    test('new commits matching a read one by subject count as read, and Since my review picks only the rest', async function (assert) {
      rebasedOnto('Add the widget', 'Name the widget', 'Test the widget');
      await visit('/pr/o/r/7/diff');

      assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
      assert.deepEqual(pips(), ['read', 'read', 'current']);
      assert
        .dom('[data-test-commit-note]')
        .hasText(
          'Rebased since your review (force-pushed Wed 21 Oct). 2 of your read commits were rewritten onto newer main and matched by message; 1 is new. ×',
        );

      await click('[data-test-timeline-toggle]');

      assert.deepEqual(
        dots('pr').map((one) => [one.sha, one.style]),
        [
          [FIRST, 'read'],
          [SECOND, 'read'],
          [THIRD, 'unread'],
        ],
      );
      assert.deepEqual(
        findAll('[data-test-matched]').map((one) =>
          one.getAttribute('data-at'),
        ),
        [FIRST, SECOND],
      );
      assert.dom('[data-test-matched]').hasText('≈ read');

      await click('[data-test-preset="since-review"]');

      assert.dom('[data-test-commit-place]').hasText('Commit 3 of 3');
      assert.deepEqual(inRange(), [THIRD]);
    });

    test('when nothing matches, every commit is new and it opens on the first', async function (assert) {
      rebasedOnto('Build the widget', 'Rename the widget', 'Test the widget');
      await visit('/pr/o/r/7/diff');

      assert.dom('[data-test-commit-place]').hasText('Commit 1 of 3');
      assert
        .dom('[data-test-commit-note]')
        .hasText(
          'Rebased since your review (force-pushed Wed 21 Oct). 0 of your read commits were rewritten onto newer main and matched by message; 3 are new. ×',
        );

      await click('[data-test-timeline-toggle]');

      assert.dom('[data-test-matched]').doesNotExist();
      assert.strictEqual(dots('ghost').length, 2);
      assert.dom('[data-test-preset="since-review"]').isNotDisabled();

      await click('[data-test-preset="since-review"]');

      assert.deepEqual(inRange(), [FIRST, SECOND, THIRD]);
    });

    test("the note's counts are the graph's: matched dots, unmatched dots and the ones still read as they were", async function (assert) {
      board().commits = {
        ...prHistory(NEW_FORK, [
          prCommit(FIRST, NEW_FORK, 'Add the widget'),
          prCommit(SECOND, FIRST, 'Name the widget'),
          prCommit(THIRD, SECOND, 'Test the widget'),
        ]),
        reviewed: {
          sha: OLD_TWO,
          fork: OLD_FORK,
          commits: [
            prCommit(FIRST, NEW_FORK, 'Add the widget'),
            prCommit(OLD_TWO, FIRST, 'Name the widget'),
          ],
        },
      };
      board().readMarks = [
        { sha: FIRST, subject: 'Add the widget' },
        { sha: OLD_TWO, subject: 'Name the widget' },
        { sha: OLD_ONE, subject: 'Polish the widget' },
      ];
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      const matched = findAll('[data-test-matched]').map((one) =>
        one.getAttribute('data-at'),
      );
      const unmatched = dots('pr')
        .filter((one) => one.style === 'unread')
        .map((one) => one.sha);
      assert.deepEqual([matched, unmatched], [[SECOND], [THIRD]]);
      assert
        .dom('[data-test-commit-note]')
        .hasText(
          'Rebased since your review (force-pushed Wed 21 Oct). 1 of your read commits was rewritten onto newer main and matched by message; 1 is new; 1 is read as it was. ×',
        );
    });

    test('without a force-push GitHub reported, the note names no day', async function (assert) {
      board().manager = dashboard({
        facts: {
          is_author: false,
          my_review: 'commented',
          my_review_at: '2026-10-20T12:00:00Z',
          my_review_sha: OLD_TWO,
          force_pushed_at: null,
        },
      });
      rebasedOnto('Add the widget', 'Name the widget', 'Test the widget');

      await visit('/pr/o/r/7/diff');

      assert
        .dom('[data-test-commit-note]')
        .includesText('Rebased since your review (force-pushed). 2 of');
    });

    test('a plain push since your review draws no ghost lane', async function (assert) {
      board().manager = dashboard({
        facts: {
          is_author: false,
          my_review: 'commented',
          my_review_at: '2026-10-20T12:00:00Z',
          my_review_sha: FIRST,
        },
      });
      board().readMarks = [{ sha: FIRST, subject: 'Add the widget' }];
      board().commits = prHistory(NEW_FORK, [
        prCommit(FIRST, NEW_FORK, 'Add the widget'),
        prCommit(SECOND, FIRST, 'Name the widget'),
      ]);
      board().diffs = {
        second: {
          base: FIRST,
          head: SECOND,
          files: [
            changed('src/widgets/second.py', [added(19, 'second change')]),
          ],
        },
      };
      await visit('/pr/o/r/7/diff');

      await click('[data-test-timeline-toggle]');

      assert.strictEqual(dots('ghost').length, 0);
      assert.dom('[data-test-ghost-lane]').doesNotExist();
      assert.dom('[data-test-ghost-shas]').doesNotExist();
      assert.dom('[data-test-lane-label="old-fork"]').doesNotExist();
      assert.dom('[data-test-matched]').doesNotExist();
      assert
        .dom('[data-test-timeline-header]')
        .hasText(
          `2 commits on PROJ-7-fix-the-widget · forked from main at ${NEW_FORK}, main's tip`,
        );
      assert.dom('[data-test-commit-note]').includesText('Picked up');
    });
  },
);
