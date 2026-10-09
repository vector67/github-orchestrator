import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  visit,
  click,
  currentURL,
  triggerEvent,
  waitFor,
} from '@ember/test-helpers';
import type { Diff, DiffHunk, FileChange } from 'frontend/data/api';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import {
  added,
  changed,
  comment,
  context,
  diffOf,
  operation,
  proposal,
  removed,
  setupFakeBoard,
  summary,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';

const ROWS = diffOf(
  'a.py',
  added(4, '    return rows'),
  context(5, '    done'),
);

function seed(board: FakeBoard, key: string, diff: Diff) {
  if (!board.conversations.some((one) => one.key === key)) {
    board.conversations = [
      ...board.conversations,
      board.threadIn('proposed', { key }),
    ];
  }
  board.comments[key] = [
    comment(),
    comment({ id: 2, author: 'octocat', review_state: null }),
  ];
  board.operations[key] = [operation({ id: `${key}.1`, conversation: key })];
  board.proposals[key] = [
    proposal({ id: `${key}.1.proposal`, operation: `${key}.1` }),
  ];
  board.diffs[`${key}.1.proposal`] = diff;
}

function diffPath(board: FakeBoard, key: string): string {
  const diff = board.diffs[`${key}.1.proposal`]!;
  return `/api/diffs/${diff.base}..${diff.head}`;
}

function diffAsks(board: FakeBoard, key: string) {
  return board.askedFor(new RegExp(`${diffPath(board, key)}$`));
}

const ANY_DIFF = /\/api\/diffs\//;

module('Acceptance | diff', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    seed(board(), 'k1', ROWS);
  });

  module('in the fold', function () {
    test('the fold draws the diff of its proposal, asked for once', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('#panel-diff [data-test-diff]').containsText('return rows');
      assert.deepEqual(
        diffAsks(board(), 'k1').map((one) => one.url),
        [diffPath(board(), 'k1')],
      );
    });

    test('another conversation brings its own diff', async function (assert) {
      seed(board(), 'k2', diffOf('a.py', added(4, '    return columns')));
      await visit('/pr/o/r/7/conversations/k1');

      await visit('/pr/o/r/7/conversations/k2');

      assert
        .dom('#panel-diff [data-test-diff]')
        .containsText('return columns')
        .doesNotContainText('return rows');
      assert.strictEqual(diffAsks(board(), 'k2').length, 1);
    });

    test('the last diff goes the moment another conversation arrives', async function (assert) {
      seed(board(), 'k2', diffOf('a.py', added(4, '    return columns')));
      await visit('/pr/o/r/7/conversations/k1');
      const release = board().hold(new RegExp(`${diffPath(board(), 'k2')}$`));

      const going = visit('/pr/o/r/7/conversations/k2');
      await waitFor('#panel-diff [data-test-loading="diff"]');

      assert
        .dom('#panel-diff [data-test-diff]')
        .doesNotContainText('return rows');

      release();
      await going;
    });

    test('the diff says it is loading until it arrives', async function (assert) {
      const release = board().hold(ANY_DIFF);

      const visiting = visit('/pr/o/r/7/conversations/k1');
      await waitFor('[data-test-loading="diff"]');

      assert.dom('[data-test-loading="diff"]').hasText('Loading the diff…');

      release();
      await visiting;

      assert.dom('[data-test-loading="diff"]').doesNotExist();
      assert.dom('#panel-diff [data-test-diff]').containsText('return rows');
    });

    test('a diff the server will not render says so and stops loading', async function (assert) {
      board().broken = ANY_DIFF;

      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('[data-test-loading="diff"]').doesNotExist();
      assert
        .dom('#panel-diff [data-test-diff]')
        .hasText('that diff will not render');
    });

    test('a line is drawn in the language of its file, its words intact', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      const code = document.querySelector(
        '#panel-diff [data-test-row="added"] [data-test-code]',
      );
      assert.dom(code).hasText('return rows');
      assert.strictEqual(
        code?.firstElementChild?.textContent,
        'return',
        'the keyword is a token of its own',
      );
    });

    test('a row carries its line numbers and its text as it is', async function (assert) {
      seed(board(), 'k1', diffOf('a.py', added(4, '<b>return</b> rows')));

      await visit('/pr/o/r/7/conversations/k1');

      assert
        .dom('#panel-diff [data-test-row="added"] [data-test-code]')
        .hasText('<b>return</b> rows');
      assert
        .dom('#panel-diff [data-test-row="added"] b')
        .doesNotExist('text from git is never markup');
      assert
        .dom('#panel-diff [data-test-row="added"] [data-test-new]')
        .hasText('4');
      assert.dom('#panel-diff [data-test-diff-file]').hasText('a.py');
    });

    test('an added and a removed line say which they are in a sign, not only a colour', async function (assert) {
      seed(
        board(),
        'k1',
        diffOf(
          'a.py',
          removed(4, '    return rows'),
          added(4, '    return columns'),
          context(5, '    done'),
        ),
      );

      await visit('/pr/o/r/7/conversations/k1');

      assert
        .dom('#panel-diff [data-test-row="removed"] [data-test-sign]')
        .hasText('-');
      assert
        .dom('#panel-diff [data-test-row="added"] [data-test-sign]')
        .hasText('+');
      assert
        .dom('#panel-diff [data-test-row="context"] [data-test-sign]')
        .hasText('');
      assert
        .dom('#panel-diff [data-test-row="added"] [data-test-code]')
        .hasText('return columns', 'the sign stays out of the code');
    });

    test('full screen is a state on the frame, not a new fetch', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-full-screen]');

      assert.dom('[data-test-frame]').hasAttribute('data-expanded');
      assert.strictEqual(
        diffAsks(board(), 'k1').length,
        1,
        'the diff it already has is the diff',
      );
    });

    test('full screen names the file and says how to get out', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('[data-test-esc-hint]').doesNotExist();
      assert.dom('[data-test-fold-file]').doesNotExist();
      assert.dom('[data-test-full-screen]').includesText('Full screen');

      await click('[data-test-full-screen]');

      assert.dom('[data-test-fold-file]').hasText('src/foo.py:42');
      assert.dom('[data-test-esc-hint]').hasText('Esc to close');
      assert.dom('[data-test-full-screen]').includesText('Close');
    });

    test('z opens the fold full screen and z closes it', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      await triggerEvent(document, 'keydown', { key: 'z' });
      assert.dom('[data-test-frame]').hasAttribute('data-expanded');

      await triggerEvent(document, 'keydown', { key: 'z' });
      assert.dom('[data-test-frame]').doesNotHaveAttribute('data-expanded');

      await triggerEvent(document, 'keydown', { key: 'z' });
      await triggerEvent(document, 'keydown', { key: 'Escape' });

      assert.dom('[data-test-frame]').doesNotHaveAttribute('data-expanded');
      assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');

      await triggerEvent(document, 'keydown', { key: 'Escape' });

      assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
    });

    test('the full screen button shows its key while slash is held', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      await triggerEvent(document, 'keydown', { key: '/' });

      assert.dom('[data-test-full-screen] kbd').isVisible().hasText('z');
    });
  });

  module('while a diff is slow', function (hooks) {
    const clock = setupFakeClock(hooks);

    test('after ten seconds a proposal’s diff says it is still waiting on it', async function (assert) {
      const release = board().hold(ANY_DIFF);

      const visiting = visit('/pr/o/r/7/conversations/k1');
      await waitFor('#panel-diff [data-test-loading="diff"]');
      void clock().tick(10_000);
      await waitFor('#panel-diff [data-test-waiting]');

      assert
        .dom('#panel-diff [data-test-waiting]')
        .includesText(diffPath(board(), 'k1'));

      release();
      await visiting;
    });
  });

  module('once a diff has been drawn', function (hooks) {
    hooks.beforeEach(async function () {
      seed(board(), 'k2', diffOf('a.py', added(4, '    return columns')));
      await visit('/pr/o/r/7/conversations/k1');
      await visit('/pr/o/r/7/conversations/k2');
    });

    test('coming back draws it at once and does not ask for it again, since a diff of two commits never changes', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('[data-test-loading="diff"]').doesNotExist();
      assert.strictEqual(diffAsks(board(), 'k1').length, 1);
      assert.dom('#panel-diff [data-test-diff]').containsText('return rows');
      assert
        .dom('#panel-diff [data-test-diff]')
        .doesNotHaveAttribute('data-updated');
    });

    test('a diff that cannot be asked after again stays drawn', async function (assert) {
      board().broken = new RegExp(`${diffPath(board(), 'k1')}$`);

      await visit('/pr/o/r/7/conversations/k1');

      assert
        .dom('#panel-diff [data-test-diff]')
        .containsText('return rows')
        .doesNotContainText('that diff will not render');
    });
  });

  module('when the fix lands', function (hooks) {
    const clock = setupFakeClock(hooks);

    test('landing the fix titles the fold with its commit and asks for its diff afresh', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      board().conversations = [
        thread({
          key: 'k1',
          etag: '"t2"',
          state: 'done',
          operations: [
            summary({ id: 'k1.1' }),
            summary({ id: 'k1.2', kind: 'approve' }),
          ],
        }),
      ];
      board().operations['k1'] = [
        operation({ id: 'k1.1', conversation: 'k1' }),
        operation({
          id: 'k1.2',
          conversation: 'k1',
          kind: 'approve',
          landed_sha: 'abc123def4567890',
        }),
      ];
      board().diffs['k1.1.proposal'] = diffOf(
        'a.py',
        added(4, '    return landed'),
      );
      await clock().tick(5000);

      assert.dom('[data-test-fold-title]').hasText('Pushed as abc123def456');
      assert.dom('#panel-diff [data-test-diff]').containsText('return landed');
      assert.strictEqual(diffAsks(board(), 'k1').at(-1)?.ifNoneMatch, null);
    });
  });

  module('when the base moves', function (hooks) {
    const clock = setupFakeClock(hooks);

    function files(): string[] {
      return [
        ...document.querySelectorAll('#panel-diff [data-test-diff-file]'),
      ].map((one) => one.textContent?.trim() ?? '');
    }

    test('the fold counts the files of the diff it draws, and a moved base changes both together', async function (assert) {
      seed(board(), 'k1', {
        base: 'aaaaaaa',
        head: 'ccccccc',
        files: [
          changed('a.py', [added(1, 'one')]),
          changed('b.py', [added(1, 'two')]),
          changed('c.py', [added(1, 'three')]),
        ],
      });
      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('[data-test-fold-title]').hasText('Proposed diff · 3 files');
      assert.deepEqual(files(), ['a.py', 'b.py', 'c.py']);

      board().diffs['k1.1.proposal'] = {
        base: 'ddddddd',
        head: 'ccccccc',
        files: [changed('a.py', [added(1, 'one')])],
      };
      board().conversations = board().conversations.map((one) => ({
        ...one,
        updated_at: '2026-10-08T10:00:00Z',
      }));
      await clock().tick(5000);

      assert.dom('[data-test-fold-title]').hasText('Proposed diff · 1 file');
      assert.deepEqual(files(), ['a.py']);
      assert.dom('#panel-diff [data-test-diff]').hasAttribute('data-updated');
      assert.deepEqual(document.getAnimations(), []);
    });
  });

  module('in the rework dialog', function () {
    function pointedCount() {
      return document
        .querySelector('[data-test-pointed-count]')
        ?.textContent?.trim();
    }

    test('a row that is no line of any file points at nothing', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');
      await click('[data-test-decision="rework"]');

      await click('[data-test-rework-dialog] [data-test-row="hunk"]');

      assert.dom('[data-test-chip]').doesNotExist();
      assert.strictEqual(pointedCount(), '0 lines pointed');
    });

    test('the panel fold points at nothing, even with the dialog open', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');
      await click('[data-test-decision="rework"]');

      await click('#panel-diff [data-test-row="added"]');

      assert.dom('[data-test-chip]').doesNotExist();
      assert.strictEqual(pointedCount(), '0 lines pointed');
      assert
        .dom('#panel-diff [data-test-row="added"]')
        .doesNotHaveAttribute('role')
        .doesNotHaveAttribute('data-pointed');
      assert.dom('[data-test-frame]').doesNotHaveAttribute('data-pointing');
    });

    test('two views of one diff ask for it once', async function (assert) {
      const release = board().hold(ANY_DIFF);
      const visiting = visit('/pr/o/r/7/conversations/k1');
      await waitFor('[data-test-decision="rework"]');

      const opening = click('[data-test-decision="rework"]');
      await waitFor('[data-test-rework-dialog] [data-test-diff]');
      release();
      await visiting;
      await opening;

      assert.strictEqual(diffAsks(board(), 'k1').length, 1);
      assert.dom('[data-test-diff]').exists({ count: 2 });
    });
  });

  module('lines the diff leaves out', function (hooks) {
    function hunkAt(
      oldStart: number,
      newStart: number,
      count: number,
    ): DiffHunk {
      return {
        old_start: oldStart,
        old_lines: count,
        new_start: newStart,
        new_lines: count,
        section: null,
        lines: Array.from({ length: count }, (_, at) => ({
          kind: 'context' as const,
          old_line: oldStart + at,
          new_line: newStart + at,
          text: `line ${newStart + at}`,
        })),
      };
    }

    function fileOf(
      path: string,
      lineCount: number | null,
      ...hunks: DiffHunk[]
    ): FileChange {
      return {
        path,
        old_path: null,
        status: 'modified',
        added: 0,
        removed: 0,
        is_binary: false,
        line_count: lineCount,
        hunks,
      };
    }

    let lineCount: number | null = 100;

    async function draw(...hunks: DiffHunk[]): Promise<void> {
      seed(board(), 'k1', {
        base: 'aaaaaaa',
        head: 'bbbbbbb',
        files: [fileOf('a.py', lineCount, ...hunks)],
      });
      await visit('/pr/o/r/7/conversations/k1');
    }

    function linesAsked(): string[] {
      return board()
        .askedFor(/\/api\/files\?/)
        .map((one) => new URL(one.url, 'http://board').searchParams)
        .filter((query) => query.get('sha') === 'bbbbbbb')
        .map(
          (query) =>
            `${query.get('path')}@${query.get('sha')}:${query.get('from_line')}-${query.get('to_line')}`,
        );
    }

    function shownNumbers(): string[] {
      return [
        ...document.querySelectorAll('#panel-diff [data-test-row="context"]'),
      ].map(
        (row) =>
          `${row.querySelector('[data-test-old]')?.textContent}/${row.querySelector('[data-test-new]')?.textContent}`,
      );
    }

    function expanders(): string[] {
      return [
        ...document.querySelectorAll(
          '#panel-diff [data-test-diff] [data-test-expand]',
        ),
      ].map((row) => row.getAttribute('data-test-expand') ?? '');
    }

    function headers(): { arrows: string[]; text: string }[] {
      return [
        ...document.querySelectorAll('#panel-diff [data-test-row="hunk"]'),
      ].map((row) => ({
        arrows: [...row.querySelectorAll('[data-test-expand]')].map(
          (arrow) => arrow.getAttribute('data-test-expand') ?? '',
        ),
        text: row.querySelector('[data-test-code]')?.textContent ?? '',
      }));
    }

    function rowTexts(): string[] {
      return [...document.querySelectorAll('#panel-diff [data-test-row]')].map(
        (row) => row.querySelector('[data-test-code]')?.textContent ?? '',
      );
    }

    hooks.beforeEach(function () {
      lineCount = 100;
      board().sources['bbbbbbb:a.py'] = Array.from(
        { length: 100 },
        (_, at) => `line ${at + 1}`,
      );
    });

    test('lines above the first change put an arrow in the gutter of its header', async function (assert) {
      lineCount = 42;
      await draw(hunkAt(38, 40, 3));

      assert.deepEqual(headers(), [
        { arrows: ['up'], text: '@@ -38,3 +40,3 @@' },
      ]);
    });

    test('an arrow says how many lines it shows instead of a row of its own', async function (assert) {
      lineCount = 42;
      await draw(hunkAt(38, 40, 3));

      assert
        .dom('#panel-diff [data-test-expand="up"]')
        .hasAttribute('aria-label', 'Show 16 more lines')
        .hasNoText();
    });

    test('both arrows between two changes stack in the gutter of the later header', async function (assert) {
      lineCount = 62;
      await draw(hunkAt(1, 1, 3), hunkAt(60, 60, 3));

      assert.deepEqual(headers(), [
        { arrows: [], text: '@@ -1,3 +1,3 @@' },
        { arrows: ['down', 'up'], text: '@@ -60,3 +60,3 @@' },
      ]);
    });

    test('lines below the last change get a header row of their own with no text', async function (assert) {
      await draw(hunkAt(1, 1, 3));

      assert.deepEqual(headers(), [
        { arrows: [], text: '@@ -1,3 +1,3 @@' },
        { arrows: ['down'], text: '' },
      ]);
    });

    test('a header reads above the lines opened up from its change', async function (assert) {
      lineCount = 42;
      await draw(hunkAt(38, 40, 3));

      await click('#panel-diff [data-test-expand="up"]');

      assert.deepEqual(headers(), [
        { arrows: ['up'], text: '@@ -38,3 +40,3 @@' },
      ]);
      assert.deepEqual(rowTexts().slice(0, 2), [
        '@@ -38,3 +40,3 @@',
        'line 24',
      ]);
    });

    test('a header whose gap is all open keeps its text and loses its arrows', async function (assert) {
      lineCount = 12;
      await draw(hunkAt(10, 10, 3));

      await click('#panel-diff [data-test-expand="up"]');

      assert.deepEqual(headers(), [{ arrows: [], text: '@@ -10,3 +10,3 @@' }]);
    });

    test('the row above shows the sixteen lines over the change, numbered on both sides', async function (assert) {
      lineCount = 42;
      await draw(hunkAt(38, 40, 3));

      await click('#panel-diff [data-test-expand="up"]');

      assert.deepEqual(linesAsked(), ['a.py@bbbbbbb:24-39']);
      assert.strictEqual(shownNumbers()[0], '22/24');
      assert.strictEqual(shownNumbers()[15], '37/39');
      assert.strictEqual(shownNumbers().length, 19);
      assert.deepEqual(expanders(), ['up']);
    });

    test('the last lines above the change take the row with them', async function (assert) {
      lineCount = 12;
      await draw(hunkAt(10, 10, 3));

      await click('#panel-diff [data-test-expand="up"]');

      assert.deepEqual(linesAsked(), ['a.py@bbbbbbb:1-9']);
      assert.deepEqual(expanders(), []);
      assert.strictEqual(shownNumbers()[0], '1/1');
    });

    test('lines below the last change get one row, below the change', async function (assert) {
      await draw(hunkAt(1, 1, 3));

      assert.deepEqual(expanders(), ['down']);

      await click('#panel-diff [data-test-expand="down"]');

      assert.deepEqual(linesAsked(), ['a.py@bbbbbbb:4-19']);
      assert.strictEqual(shownNumbers()[3], '4/4');
      assert.deepEqual(expanders(), ['down']);
    });

    test('a file that ends at its last change has no row below it', async function (assert) {
      lineCount = 3;
      await draw(hunkAt(1, 1, 3));

      assert.deepEqual(expanders(), []);
    });

    test('a file whose length is unknown has no row below it', async function (assert) {
      lineCount = null;
      await draw(hunkAt(1, 1, 3));

      assert.deepEqual(expanders(), []);
    });

    test('more than sixteen lines between two changes get a row from each side', async function (assert) {
      lineCount = 62;
      await draw(hunkAt(1, 1, 3), hunkAt(60, 60, 3));

      assert.deepEqual(expanders(), ['down', 'up']);

      await click('#panel-diff [data-test-expand="down"]');
      await click('#panel-diff [data-test-expand="up"]');

      assert.deepEqual(linesAsked(), [
        'a.py@bbbbbbb:4-19',
        'a.py@bbbbbbb:44-59',
      ]);
      assert.deepEqual(shownNumbers().slice(3, 5), ['4/4', '5/5']);
      assert.deepEqual(shownNumbers().slice(19, 21), ['44/44', '45/45']);
      assert.deepEqual(expanders(), ['down', 'up']);
    });

    test('sixteen lines or fewer between two changes get one row that shows them all', async function (assert) {
      lineCount = 22;
      await draw(hunkAt(1, 1, 3), hunkAt(20, 20, 3));

      assert.deepEqual(expanders(), ['all']);

      await click('#panel-diff [data-test-expand="all"]');

      assert.deepEqual(linesAsked(), ['a.py@bbbbbbb:4-19']);
      assert.deepEqual(expanders(), []);
      assert.strictEqual(shownNumbers().length, 22);
    });

    test('two changes whose gap is all open join with no header between them', async function (assert) {
      lineCount = 22;
      await draw(hunkAt(1, 1, 3), hunkAt(20, 20, 3));

      await click('#panel-diff [data-test-expand="all"]');

      assert.deepEqual(headers(), [{ arrows: [], text: '@@ -1,3 +1,3 @@' }]);
    });

    test('a gap opened down to sixteen lines or fewer becomes one row', async function (assert) {
      lineCount = 32;
      await draw(hunkAt(1, 1, 3), hunkAt(30, 30, 3));

      await click('#panel-diff [data-test-expand="down"]');

      assert.deepEqual(expanders(), ['all']);
      assert
        .dom('#panel-diff [data-test-expand="all"]')
        .hasAttribute('aria-label', 'Show 10 hidden lines');
    });

    test('a pointed line stays pointed as lines open up above it', async function (assert) {
      lineCount = 42;
      await draw(hunkAt(38, 40, 3));
      await click('[data-test-decision="rework"]');
      await click('[data-test-rework-dialog] [data-test-row="context"]');

      await click('[data-test-rework-dialog] [data-test-expand="up"]');

      const pointed = [
        ...document.querySelectorAll(
          '[data-test-rework-dialog] [data-test-row][data-pointed]',
        ),
      ].map((row) => row.querySelector('[data-test-code]')?.textContent);
      assert.deepEqual(pointed, ['line 40']);
    });
  });
});
