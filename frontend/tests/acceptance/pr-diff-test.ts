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
  waitFor,
} from '@ember/test-helpers';
import type { Anchor } from 'frontend/data/api';
import {
  added,
  changed,
  comment,
  context,
  heldPr,
  prDiff,
  removed,
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { stubGitHub } from 'frontend/tests/helpers/browser';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

const CHANGES = [
  context(18, '    rows = []'),
  removed(19, '    return None'),
  added(19, '    return rows'),
  added(20, '    # done'),
];

const LONG = Array.from({ length: 80 }, (_, at) => context(21 + at, 'pass'));

function texts(selector: string): string[] {
  return findAll(selector).map((one) =>
    one.textContent.trim().replace(/\s+/g, ' '),
  );
}

function scrolledTo(path: string): boolean {
  const pane = find('[data-test-diff-files]');
  const file = find(`[data-test-file="${path}"]`);
  if (!pane || !file) return false;
  const offset =
    file.getBoundingClientRect().top - pane.getBoundingClientRect().top;
  return pane.scrollTop > 0 && Math.abs(offset) < 2;
}

module('Acceptance | pr diff', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const github = stubGitHub(hooks);
  const clock = setupFakeClock(hooks);

  function diffReads(): number {
    return board().askedFor(/\/api\/pull-request\/diff(\?|$)/).length;
  }

  hooks.beforeEach(function () {
    board().pullRequestDiff = prDiff(
      changed('src/widgets/changes.py', CHANGES),
      changed('README.md', [added(3, 'the widget')], { status: 'added' }),
    );
  });

  test('the Diff tab is the fourth, on 4, and stacks every changed file', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerEvent(document, 'keydown', { key: '4' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
    assert.deepEqual(texts('[data-test-tab]'), [
      'Board 1',
      'Dashboard 2',
      'Terminal 3',
      'Diff 4',
    ]);
    assert.dom('[data-test-tab="diff"]').hasAttribute('aria-current', 'page');
    assert.deepEqual(texts('[data-test-file-path]'), [
      'src/widgets/changes.py',
      'README.md',
    ]);
    assert
      .dom('[data-test-file="src/widgets/changes.py"] [data-test-row="added"]')
      .exists({ count: 2 });

    await click('[data-test-tab="board"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('the diff is read again when the poll brings a new head, and not before', async function (assert) {
    await visit('/pr/o/r/7/diff');
    const opened = diffReads();
    await clock().tick(LIST);

    assert.strictEqual(diffReads(), opened, 'the same head is not read again');

    board().pullRequest = { ...board().pullRequest, head_sha: 'deadbee' };
    board().pullRequestDiff = prDiff(
      changed('src/widgets/changes.py', [added(19, '    return everything')]),
    );
    await clock().tick(LIST);

    assert.strictEqual(diffReads(), opened + 1);
    assert.dom('[data-test-pr-diff]').containsText('return everything');
  });

  module('origin or local', function () {
    test('opening the tab fetches the branch and draws what was pushed since', async function (assert) {
      board().pushedSinceFetch = prDiff(
        changed('src/widgets/changes.py', [added(19, '    return pushed')]),
      );

      await visit('/pr/o/r/7/diff');

      assert.strictEqual(board().fetches, 1);
      assert.dom('[data-test-pr-diff]').containsText('return pushed');
    });

    test('the last fetched diff is drawn at once, marked fetching… until the fetch comes back', async function (assert) {
      board().pushedSinceFetch = prDiff(
        changed('src/widgets/changes.py', [added(19, '    return pushed')]),
      );
      const release = board().hold(/\/api\/pull-request:fetch$/);

      const visiting = visit('/pr/o/r/7/diff');
      await waitFor('[data-test-pr-diff]');

      assert.dom('[data-test-fetching]').hasText('fetching…');
      assert.dom('[data-test-pr-diff]').containsText('return rows');

      release();
      await visiting;

      assert.dom('[data-test-fetching]').doesNotExist();
      assert.dom('[data-test-pr-diff]').containsText('return pushed');
    });

    test('the branch is fetched only once the last fetched diff is in', async function (assert) {
      const release = board().hold(/\/api\/pull-request\/diff/);

      const visiting = visit('/pr/o/r/7/diff');
      await waitFor('[data-test-loading="diff"]');

      assert.strictEqual(board().fetches, 0);

      release();
      await visiting;

      assert.strictEqual(board().fetches, 1);
    });

    test('after ten seconds the diff says it is still waiting on the diff', async function (assert) {
      const release = board().hold(/\/api\/pull-request\/diff/);

      const visiting = visit('/pr/o/r/7/diff');
      await waitFor('[data-test-loading="diff"]');
      void clock().tick(10_000);
      await waitFor('[data-test-diff-files] [data-test-waiting]');

      assert
        .dom('[data-test-diff-files] [data-test-waiting]')
        .includesText('/api/pull-request/diff?source=origin');

      release();
      await visiting;
    });

    test('the toggle above the filter starts on origin and draws the local commit on local', async function (assert) {
      board().localDiff = {
        ...prDiff(
          changed('src/widgets/changes.py', [added(19, '    return local')]),
        ),
        head: '10ca1e0',
      };
      await visit('/pr/o/r/7/diff');

      assert
        .dom('[data-test-tree] [data-test-source="origin"]')
        .hasAttribute('aria-pressed', 'true');
      assert.dom('[data-test-pr-diff]').doesNotContainText('return local');

      await click('[data-test-source="local"]');

      assert
        .dom('[data-test-source="local"]')
        .hasAttribute('aria-pressed', 'true');
      assert.dom('[data-test-pr-diff]').containsText('return local');

      await click('[data-test-source="origin"]');

      assert.dom('[data-test-pr-diff]').containsText('return rows');
    });

    test('origin and local each say which head they draw', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert
        .dom('[data-test-source="origin"]')
        .hasAttribute('title', /on GitHub, as last fetched/);
      assert
        .dom('[data-test-source="local"]')
        .hasAttribute('title', /not pushed yet/);
    });

    test('a fetch git refuses leaves the diff it already drew', async function (assert) {
      board().refusal = {
        status: 500,
        code: 'git-failed',
        detail: 'git fetch origin feature failed',
      };

      await visit('/pr/o/r/7/diff');

      assert.dom('[data-test-pr-diff]').containsText('return rows');
      assert.dom('[data-test-diff-failed]').doesNotExist();
    });
  });

  module('a file', function () {
    test('a docstring over several lines is drawn as one string, with no keyword inside it', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('docs.py', [
          added(1, '"""Shared translation into SQL.'),
          added(2, ''),
          added(3, 'not one function with two callers, and is'),
          added(4, '"""'),
          added(5, 'import os'),
        ]),
      );

      await visit('/pr/o/r/7/diff');

      const rows = '[data-test-file="docs.py"] [data-test-row="added"]';
      assert.dom(`${rows} [data-test-code] .hljs-keyword`).exists({ count: 1 });
      assert.dom(`${rows}[data-line="5"] .hljs-keyword`).hasText('import');
      assert.deepEqual(
        [1, 3, 4].map(
          (line) =>
            find(`${rows}[data-line="${line}"] [data-test-code] .hljs-string`)
              ?.textContent,
        ),
        [
          '"""Shared translation into SQL.',
          'not one function with two callers, and is',
          '"""',
        ],
      );
    });

    test('its header counts what it adds and removes, copies its path, and folds it on the chevron', async function (assert) {
      await visit('/pr/o/r/7/diff');
      const file = '[data-test-file="src/widgets/changes.py"]';

      assert.deepEqual(texts('[data-test-file-counts]'), ['+2 −1', '+1 −0']);

      await click(`${file} [data-test-copy-path]`);

      assert.deepEqual(github().copied, ['src/widgets/changes.py']);

      await click(`${file} [data-test-fold]`);

      assert.dom(`${file} [data-test-row]`).doesNotExist();
      assert
        .dom(`${file} [data-test-fold]`)
        .hasAttribute('aria-expanded', 'false');

      await click(`${file} [data-test-fold]`);

      assert.dom(`${file} [data-test-row="added"]`).exists({ count: 2 });
    });

    test('a binary file starts open on a note that it is not rendered, with nothing to load', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('logo.png', [], { is_binary: true, hunks: [] }),
      );
      await visit('/pr/o/r/7/diff');

      const file = '[data-test-file="logo.png"]';
      assert
        .dom(`${file} [data-test-fold]`)
        .hasAttribute('aria-expanded', 'true');
      assert
        .dom(`${file} [data-test-held]`)
        .hasText('Binary files are not rendered by default.');
      assert.dom(`${file} [data-test-load-diff]`).doesNotExist();
    });

    test('a deleted file starts open on a note that it is not shown, and a button that loads its diff', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('gone.py', [removed(1, 'import re')], { status: 'removed' }),
        changed('emptied.py', [removed(1, 'import os')]),
      );
      await visit('/pr/o/r/7/diff');

      const gone = '[data-test-file="gone.py"]';
      assert
        .dom(`${gone} [data-test-fold]`)
        .hasAttribute('aria-expanded', 'true');
      assert.dom(`${gone} [data-test-row]`).doesNotExist();
      assert
        .dom(`${gone} [data-test-held]`)
        .containsText('Deleted files are not shown by default.');
      assert
        .dom('[data-test-file="emptied.py"] [data-test-row="removed"]')
        .exists({ count: 1 });

      await click(`${gone} [data-test-load-diff]`);

      assert.dom(`${gone} [data-test-row="removed"]`).exists({ count: 1 });
    });

    test('hovering a file name cut short by the header shows the whole path, and a name that fits shows none', async function (assert) {
      const long = `src/${'deeply/'.repeat(60)}integrity_error_converter.py`;
      board().pullRequestDiff = prDiff(
        changed(long, CHANGES),
        changed('README.md', [added(3, 'the widget')]),
      );
      await visit('/pr/o/r/7/diff');

      const cut = `[data-test-file="${long}"] [data-test-file-path]`;
      const fits = '[data-test-file="README.md"] [data-test-file-path]';
      await triggerEvent(cut, 'mouseenter');
      await triggerEvent(fits, 'mouseenter');

      assert.dom(cut).hasAttribute('title', long);
      assert.dom(fits).doesNotHaveAttribute('title');
    });

    test('a file name is cut short only when the header runs out of room', async function (assert) {
      const path =
        'src/widgets/adapters/driven/repositories/integrity_error_converter.py';
      board().pullRequestDiff = prDiff(changed(path, CHANGES));
      await visit('/pr/o/r/7/diff');

      const head = find(`[data-test-file="${path}"] .file-head`)!;
      const name = find(`[data-test-file="${path}"] [data-test-file-path]`)!;
      const others = [...head.children]
        .filter((one) => one !== name)
        .reduce((sum, one) => sum + one.getBoundingClientRect().width, 0);
      assert.ok(
        name.scrollWidth + others + 100 < head.clientWidth,
        `the header has room: ${head.clientWidth}px for a ${name.scrollWidth}px name`,
      );
      assert.ok(
        name.scrollWidth <= name.clientWidth,
        `the name is ${name.scrollWidth}px of text in ${name.clientWidth}px`,
      );
    });

    test('a file with more than 400 lines added and removed starts open on a button that loads its diff', async function (assert) {
      const many = Array.from({ length: 401 }, (_, at) => added(at + 1, 'x'));
      board().pullRequestDiff = prDiff(changed('big.py', many));
      await visit('/pr/o/r/7/diff');

      const file = '[data-test-file="big.py"]';
      assert
        .dom(`${file} [data-test-fold]`)
        .hasAttribute('aria-expanded', 'true');
      assert.dom(`${file} [data-test-row]`).doesNotExist();
      assert.dom(`${file} [data-test-load-diff]`).hasText('Load diff');

      await click(`${file} [data-test-load-diff]`);

      assert.dom(`${file} [data-test-row="added"]`).exists({ count: 401 });
      assert.dom(`${file} [data-test-load-diff]`).doesNotExist();
    });

    test('opening lines leaves the diff where it was scrolled', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('src/widgets/changes.py', CHANGES),
        changed('README.md', LONG, {
          line_count: 120,
          hunks: [
            {
              old_start: 21,
              old_lines: 80,
              new_start: 21,
              new_lines: 80,
              section: null,
              lines: LONG,
            },
          ],
        }),
      );
      board().sources['c0ffee1:README.md'] = Array.from(
        { length: 120 },
        (_, at) => `line ${at + 1}`,
      );
      await visit('/pr/o/r/7/diff?file=README.md');
      const pane = find('[data-test-diff-files]')!;
      pane.scrollTop = pane.scrollHeight;
      const scrolled = pane.scrollTop;

      await click('[data-test-file="README.md"] [data-test-expand="down"]');

      assert.dom('[data-test-pr-diff]').containsText('line 101');
      assert.true(scrolled > 0, 'the pane was scrolled');
      assert.strictEqual(pane.scrollTop, scrolled);
    });
  });

  module('selecting', function () {
    const FILE = '[data-test-file="src/widgets/changes.py"]';

    function row(end: string): string {
      return `${FILE} [data-test-end="${end}"]`;
    }

    function selected(): string[] {
      return findAll(`${FILE} [data-selected]`).map(
        (one) => one.getAttribute('data-test-end') ?? '',
      );
    }

    test('on the hub Esc drops the selection before it leaves for the wall', async function (assert) {
      board().serves = 'hub';
      board().held = [heldPr()];
      await visit('/pr/o/r/7/diff');
      await click(`${row('+20')} [data-test-new]`);

      await triggerEvent(document, 'keydown', { key: 'Escape' });

      assert.deepEqual(selected(), []);
      assert.strictEqual(currentURL(), '/pr/o/r/7/diff');

      await triggerEvent(document, 'keydown', { key: 'Escape' });

      assert.strictEqual(currentURL(), '/');
    });

    test('clicking a line number selects the line, and its + opens the comment box under it', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click(`${row('+20')} [data-test-new]`);

      assert.deepEqual(selected(), ['+20']);
      assert
        .dom('[data-test-comment-box]')
        .doesNotExist('the rows stay put until the box is asked for');

      await click(`${row('+20')} [data-test-add]`);

      assert
        .dom(`${row('+20')} + [data-test-inline] [data-test-commenting]`)
        .hasText('Commenting on line +20');
      assert.dom('[data-test-comment-box] textarea').exists();
    });

    test('the + in the gutter selects its line', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click(`${row('−19')} [data-test-add]`);

      assert.deepEqual(selected(), ['−19']);
      assert.dom('[data-test-commenting]').hasText('Commenting on line −19');
    });

    test('shift-click extends the selection across removed and added lines', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click(`${row('−19')} [data-test-old]`);
      await click(`${row('+20')} [data-test-new]`, { shiftKey: true });

      assert.deepEqual(selected(), ['−19', '+19', '+20']);

      await click(`${row('+19')} [data-test-add]`);

      assert.deepEqual(
        selected(),
        ['−19', '+19', '+20'],
        'a + inside keeps it',
      );
      assert
        .dom(`${row('+20')} + [data-test-inline] [data-test-commenting]`)
        .hasText('Commenting on lines −19 to +20');
    });

    test('dragging selects from where it began, and never out of its hunk', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('src/widgets/changes.py', CHANGES, {
          hunks: [
            {
              old_start: 18,
              old_lines: 2,
              new_start: 18,
              new_lines: 3,
              section: null,
              lines: CHANGES,
            },
            {
              old_start: 40,
              old_lines: 1,
              new_start: 41,
              new_lines: 2,
              section: null,
              lines: [context(41, 'x'), added(42, 'y')],
            },
          ],
        }),
      );
      await visit('/pr/o/r/7/diff');

      await triggerEvent(`${row('+20')} [data-test-add]`, 'mousedown');
      await triggerEvent(row('+19'), 'mouseover');
      await triggerEvent(row('+18'), 'mouseover');
      await triggerEvent(row('+42'), 'mouseover');
      await triggerEvent(row('+18'), 'mouseup');

      assert.deepEqual(selected(), ['+18', '−19', '+19', '+20']);
      assert
        .dom('[data-test-commenting]')
        .hasText('Commenting on lines +18 to +20');
    });

    test('lines opened by expanding context are drawn but cannot be selected', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('src/widgets/changes.py', CHANGES, { line_count: 24 }),
      );
      board().sources['c0ffee1:src/widgets/changes.py'] = Array.from(
        { length: 24 },
        (_, at) => `line ${at + 1}`,
      );
      await visit('/pr/o/r/7/diff');
      await click('[data-test-expand="down"]');

      const revealed = findAll(`${FILE} [data-test-row="context"]`).at(-1)!;
      assert.dom(revealed).containsText('line 24');
      assert.dom(revealed.querySelector('[data-test-add]')).doesNotExist();

      await click(revealed.querySelector('[data-test-new]')!);

      assert.deepEqual(selected(), []);
      assert.dom('[data-test-comment-box]').doesNotExist();
    });

    test('Save draft creates a draft on the selected lines and the tab stays where it is', async function (assert) {
      await visit('/pr/o/r/7/diff?file=src%2Fwidgets%2Fchanges.py');
      await click(`${row('−19')} [data-test-old]`);
      await click(`${row('+20')} [data-test-new]`, { shiftKey: true });
      await click(`${row('+20')} [data-test-add]`);

      assert.dom('[data-test-box-save]').isDisabled('nothing typed yet');

      await fillIn('[data-test-comment-box] textarea', 'return the rows');
      await click('[data-test-box-save]');

      assert.deepEqual(
        board().posted.map((one) => [one.verb, one.body]),
        [
          [
            'create-draft',
            {
              body: 'return the rows',
              path: 'src/widgets/changes.py',
              line: 20,
              side: 'RIGHT',
              start_line: 19,
              start_side: 'LEFT',
            },
          ],
        ],
      );
      assert.strictEqual(
        currentURL(),
        '/pr/o/r/7/diff?file=src%2Fwidgets%2Fchanges.py',
      );
      assert.dom('[data-test-comment-box]').doesNotExist();
    });

    test('Add to review creates the draft on the selected lines and adds it to the review, as the board’s Add to review does', async function (assert) {
      board().created = 'draft_00000000000000bb';
      await visit('/pr/o/r/7/diff?file=src%2Fwidgets%2Fchanges.py');
      await click(`${row('+20')} [data-test-add]`);

      assert.dom('[data-test-box-add]').isDisabled('nothing typed yet');

      await fillIn('[data-test-comment-box] textarea', 'return the rows');
      board().conversations = [
        ...board().conversations,
        thread({
          key: 'draft_00000000000000bb',
          kind: 'draft',
          state: 'draft',
          etag: '"bb-v1"',
          comments: [],
        }),
      ];
      await click('[data-test-box-add]');

      assert.deepEqual(
        board().posted.map((one) => [one.verb, one.key, one.ifMatch]),
        [
          ['create-draft', '', null],
          ['enrol', 'draft_00000000000000bb', '"bb-v1"'],
        ],
      );
      assert.strictEqual(
        currentURL(),
        '/pr/o/r/7/diff?file=src%2Fwidgets%2Fchanges.py',
      );
      assert.dom('[data-test-comment-box]').doesNotExist();
    });

    test('a draft being edited has no Add to review in its box', async function (assert) {
      board().conversations = [
        thread({
          key: 'd1',
          kind: 'draft',
          state: 'draft',
          anchor: {
            ...thread().anchor,
            path: 'src/widgets/changes.py',
            line: 20,
          },
          comments: [],
        }),
      ];
      board().comments = {
        d1: [comment({ id: null, author: 'octocat', body: 'return the rows' })],
      };
      await visit('/pr/o/r/7/diff');

      await click('[data-test-card="d1"] [data-test-card-edit]');

      assert.dom('[data-test-box-save]').exists();
      assert.dom('[data-test-box-add]').doesNotExist();
    });

    test('selecting lines without opening the box leaves the board’s new draft where it was', async function (assert) {
      await visit('/pr/o/r/7/conversations/new-draft');
      await click(
        '#panel-anchor [data-test-tree-row="file"][data-path="README.md"]',
      );
      await click('#panel-anchor [data-test-end="+3"] [data-test-new]');
      await click('[data-test-tab="diff"]');

      await click(`${row('+20')} [data-test-new]`);
      await visit('/pr/o/r/7/conversations/new-draft');

      assert.dom('[data-test-draft-anchor]').hasText('README.md +3');
    });

    test('Cancel and Esc close the box, and what was typed is there when it opens again', async function (assert) {
      await visit('/pr/o/r/7/diff');
      await click(`${row('+20')} [data-test-add]`);
      await fillIn('[data-test-comment-box] textarea', 'half a thought');

      await click('[data-test-box-cancel]');

      assert.dom('[data-test-comment-box]').doesNotExist();
      assert.deepEqual(selected(), []);

      await click(`${row('+19')} [data-test-add]`);

      assert.dom('[data-test-comment-box] textarea').hasValue('half a thought');

      await triggerEvent('[data-test-comment-box] textarea', 'keydown', {
        key: 'Escape',
      });

      assert.dom('[data-test-comment-box]').doesNotExist();
      assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
    });
  });

  module('conversations', function (hooks) {
    const FILE = '[data-test-file="src/widgets/changes.py"]';

    function under(end: string): string {
      return `${FILE} [data-test-end="${end}"] + [data-test-inline]`;
    }

    function anchored(line: number | null, over: Partial<Anchor> = {}): Anchor {
      return {
        path: 'src/widgets/changes.py',
        line,
        start_line: null,
        start_side: null,
        side: 'RIGHT',
        original_line: 20,
        original_start_line: null,
        original_commit: 'ba5e000',
        is_outdated: false,
        ...over,
      };
    }

    hooks.beforeEach(function () {
      board().conversations = [
        thread({ key: 'k1', anchor: anchored(20) }),
        thread({
          key: 'k2',
          anchor: anchored(19, { start_line: 17, start_side: 'RIGHT' }),
          github_resolved: true,
        }),
        thread({
          key: 'k3',
          anchor: anchored(null, { is_outdated: true }),
        }),
        thread({
          key: 'k4',
          anchor: anchored(null, { is_outdated: true }),
        }),
        thread({
          key: 'd1',
          kind: 'draft',
          state: 'draft',
          anchor: anchored(20, { start_line: 19, start_side: 'LEFT' }),
          comments: [],
        }),
        thread({
          key: 'd2',
          kind: 'draft',
          state: 'enrolled',
          anchor: anchored(3, { path: 'README.md' }),
          comments: [],
        }),
      ];
      board().comments = {
        k1: [
          comment({ body: 'please rename' }),
          comment({
            id: 2,
            author: 'octocat',
            body: 'on it',
            review_state: null,
          }),
        ],
        k2: [comment({ body: 'fixed already' })],
        d1: [comment({ id: null, author: 'octocat', body: 'return the rows' })],
        d2: [comment({ id: null, author: 'octocat', body: 'say more' })],
      };
    });

    test('a posted thread shows under its last line with its comments, a resolved one folds to the lines it is on', async function (assert) {
      board().conversations.push(
        thread({ key: 'k5', anchor: anchored(20), github_resolved: true }),
      );
      board().comments['k5'] = [comment({ body: 'done' })];
      await visit('/pr/o/r/7/diff');

      assert.deepEqual(
        texts(`${under('+20')} [data-test-card="k1"] [data-test-entry-body]`),
        ['please rename', 'on it'],
      );
      const folded = `${under('+19')} [data-test-card="k2"]`;
      assert
        .dom(`${folded} [data-test-entry-body]`)
        .doesNotExist('the resolved thread is folded');
      assert
        .dom(`${folded} [data-test-standing]`)
        .doesNotExist('a folded thread says only where it is');
      assert
        .dom(`${folded} [data-test-show-resolved]`)
        .hasText('Comment on lines R17 to R19 Resolved');
      assert
        .dom(`[data-test-card="k5"] [data-test-show-resolved]`)
        .hasText('Comment on line R20 Resolved');

      await click(`${folded} [data-test-show-resolved]`);

      assert.dom(`${folded} [data-test-entry-body]`).hasText('fixed already');

      await click(`${folded} [data-test-hide-resolved]`);

      assert.dom(`${folded} [data-test-entry-body]`).doesNotExist();
      assert
        .dom(`${folded} [data-test-show-resolved]`)
        .hasText('Comment on lines R17 to R19 Resolved');
    });

    test('a thread deleted on GitHub folds to the lines it is on with a Deleted badge, and opens to its comments', async function (assert) {
      board().conversations.push(
        thread({ key: 'k5', anchor: anchored(20), github_removed: true }),
      );
      board().comments['k5'] = [comment({ body: 'never mind' })];
      await visit('/pr/o/r/7/diff');

      const folded = `${under('+20')} [data-test-card="k5"]`;
      assert.dom(`${folded} [data-test-entry-body]`).doesNotExist();
      assert
        .dom(`${folded} [data-test-show-resolved]`)
        .hasText('Comment on line R20 Deleted');

      await click(`${folded} [data-test-show-resolved]`);

      assert.dom(`${folded} [data-test-entry-body]`).hasText('never mind');
      assert
        .dom(`${folded} [data-test-resolved-chip]`)
        .hasText('Deleted on GitHub');
    });

    test('a thread waiting on the other side folds behind a badge naming who it waits on', async function (assert) {
      board().actAs('reviewer');
      board().conversations.push(
        thread({ key: 'k5', anchor: anchored(20), state: 'waiting' }),
      );
      board().comments['k5'] = [comment({ body: 'over to you' })];
      await visit('/pr/o/r/7/diff');

      const folded = `${under('+20')} [data-test-card="k5"]`;
      assert.dom(`${folded} [data-test-entry-body]`).doesNotExist();
      assert
        .dom(`${folded} [data-test-show-resolved]`)
        .hasText('Comment on line R20 Waiting on author');

      await click(`${folded} [data-test-show-resolved]`);

      assert.dom(`${folded} [data-test-entry-body]`).hasText('over to you');
      assert
        .dom(`${folded} [data-test-resolved-chip]`)
        .hasText('Waiting on author');
    });

    test('a done thread folds behind a Done badge', async function (assert) {
      board().conversations.push(
        thread({ key: 'k5', anchor: anchored(20), state: 'done' }),
      );
      board().comments['k5'] = [comment({ body: 'renamed it' })];
      await visit('/pr/o/r/7/diff');

      const folded = `${under('+20')} [data-test-card="k5"]`;
      assert.dom(`${folded} [data-test-entry-body]`).doesNotExist();
      assert
        .dom(`${folded} [data-test-show-resolved]`)
        .hasText('Comment on line R20 Done');

      await click(`${folded} [data-test-show-resolved]`);

      assert.dom(`${folded} [data-test-entry-body]`).hasText('renamed it');
      assert.dom(`${folded} [data-test-resolved-chip]`).hasText('Done');
    });

    test('outdated threads are not drawn and are the file header’s count, linking to the board', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert.dom('[data-test-card="k3"]').doesNotExist();
      assert.dom(`${FILE} [data-test-outdated]`).hasText('2 outdated');

      await click(`${FILE} [data-test-outdated]`);

      assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k3');
    });

    test('drafts show as cards, open or in the review, each linking to its conversation on the board', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert
        .dom(`${under('+20')} [data-test-card="d1"] [data-test-entry-body]`)
        .hasText('return the rows');
      assert
        .dom('[data-test-card="d1"] [data-test-standing]')
        .hasText('Local draft');
      assert
        .dom('[data-test-card="d1"]')
        .hasAttribute('data-standing', 'local');
      assert
        .dom(
          '[data-test-file="README.md"] [data-test-card="d2"] [data-test-standing]',
        )
        .hasText('In your pending review');
      assert
        .dom('[data-test-card="d2"]')
        .hasAttribute('data-standing', 'pending');
      assert
        .dom('[data-test-card="k1"] [data-test-standing]')
        .hasText('Posted');
      assert
        .dom('[data-test-card="k1"]')
        .hasAttribute('data-standing', 'posted');

      await click(
        `${under('+20')} [data-test-card="d1"] [data-test-card-link]`,
      );

      assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/d1');
    });

    test('the tree counts the conversations drawn on each file', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert.deepEqual(
        findAll('[data-test-tree-row="file"]').map((one) => [
          one.getAttribute('data-path'),
          one.querySelector('[data-test-tree-count]')?.textContent.trim() ?? '',
        ]),
        [
          ['src/widgets/changes.py', '3'],
          ['README.md', '1'],
        ],
      );
    });

    test('Edit on a draft turns its card into the comment box on its lines, and Save draft edits it', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click('[data-test-card="d1"] [data-test-card-edit]');

      assert.dom('[data-test-card="d1"]').doesNotExist();
      assert
        .dom(`${under('+20')} [data-test-commenting]`)
        .hasText('Commenting on lines −19 to +20');
      assert
        .dom('[data-test-comment-box] textarea')
        .hasValue('return the rows');

      await click(`${FILE} [data-test-end="+19"] [data-test-new]`);
      await fillIn('[data-test-comment-box] textarea', 'return them');
      await click('[data-test-box-save]');

      assert.deepEqual(
        board().posted.map((one) => [one.verb, one.key, one.body]),
        [
          [
            'edit-draft',
            'd1',
            {
              body: 'return them',
              path: 'src/widgets/changes.py',
              line: 19,
              side: 'RIGHT',
              start_line: null,
              start_side: null,
            },
          ],
        ],
      );
      assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
    });

    test('Edit on a draft whose lines left the diff opens the box saying so, and selecting lines anchors it again', async function (assert) {
      board().conversations = board().conversations.map((one) =>
        one.key === 'd1'
          ? {
              ...one,
              anchor: anchored(20, { start_line: 3, start_side: 'RIGHT' }),
            }
          : one,
      );
      await visit('/pr/o/r/7/diff');

      await click('[data-test-card="d1"] [data-test-card-edit]');

      assert
        .dom(`${under('+20')} [data-test-commenting]`)
        .hasText('These lines are no longer in the diff. Select new ones.');
      assert
        .dom('[data-test-comment-box] textarea')
        .hasValue('return the rows');

      await click(`${FILE} [data-test-end="+19"] [data-test-new]`);

      assert
        .dom(`${under('+19')} [data-test-commenting]`)
        .hasText('Commenting on line +19');
    });

    test('a draft on its way to GitHub has no Edit', async function (assert) {
      board().conversations = board().conversations.map((one) =>
        one.key === 'd1'
          ? {
              ...one,
              operations: [
                summary({ id: 'd1.1', kind: 'post-now', state: 'pending' }),
              ],
            }
          : one,
      );
      await visit('/pr/o/r/7/diff');

      assert.dom('[data-test-card="d1"]').exists();
      assert.dom('[data-test-card="d1"] [data-test-card-edit]').doesNotExist();
      assert.dom('[data-test-card="d2"] [data-test-card-edit]').exists();
    });

    test('a local draft’s card adds it to the review or discards it; one in the review offers neither', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert
        .dom('[data-test-card="d2"] [data-test-card-decide]')
        .doesNotExist();
      assert
        .dom('[data-test-card="k1"] [data-test-card-decide]')
        .doesNotExist();

      await click('[data-test-card="d1"] [data-test-card-decide="enrol"]');
      await click('[data-test-card="d1"] [data-test-card-decide="discard"]');

      assert.deepEqual(
        board().posted.map((one) => [one.verb, one.key]),
        [
          ['enrol', 'd1'],
          ['discard', 'd1'],
        ],
      );
    });

    test('once the board answers a discard, the draft’s card is gone and nothing is left in flight', async function (assert) {
      await visit('/pr/o/r/7/diff');
      board().projections = {
        d1: board().threadIn('discarded', { key: 'd1' }),
      };
      board().conversations = board().conversations.filter(
        (one) => one.key !== 'd1',
      );

      await click('[data-test-card="d1"] [data-test-card-decide="discard"]');

      assert.dom('[data-test-card="d1"]').doesNotExist();
      assert.dom(`${under('+20')} [data-test-card="k1"]`).exists();
      assert.deepEqual(document.getAnimations(), []);
    });

    function resolvedOnGitHub(key: string): void {
      board().conversations = board().conversations.map((one) =>
        one.key === key ? { ...one, github_resolved: true, etag: '"t2"' } : one,
      );
    }

    test('a thread you are reading stays open when a poll brings its resolution, with a chip saying so, and its chevron folds it', async function (assert) {
      await visit('/pr/o/r/7/diff');
      const reading = `${under('+20')} [data-test-card="k1"]`;
      resolvedOnGitHub('k1');

      await clock().tick(LIST);

      assert.deepEqual(texts(`${reading} [data-test-entry-body]`), [
        'please rename',
        'on it',
      ]);
      assert
        .dom(`${reading} [data-test-resolved-chip]`)
        .hasText('Resolved on GitHub');
      assert
        .dom(`${reading} [data-test-resolved-chip]`)
        .hasAttribute('data-arrived');

      await click(`${reading} [data-test-hide-resolved]`);

      assert.dom(`${reading} [data-test-entry-body]`).doesNotExist();
      assert
        .dom(`${reading} [data-test-show-resolved]`)
        .hasText('Comment on line R20 Resolved');
    });

    test('a thread resolved while you were away starts folded when the diff is drawn again, and opens without the arrival mark', async function (assert) {
      await visit('/pr/o/r/7/diff');
      resolvedOnGitHub('k1');
      await clock().tick(LIST);

      await visit('/pr/o/r/7/conversations');
      await visit('/pr/o/r/7/diff');

      const folded = `${under('+20')} [data-test-card="k1"]`;
      assert.dom(`${folded} [data-test-entry-body]`).doesNotExist();
      assert.dom(`${folded} [data-test-show-resolved]`).exists();

      await click(`${folded} [data-test-show-resolved]`);

      assert
        .dom(`${folded} [data-test-resolved-chip]`)
        .hasText('Resolved on GitHub');
      assert
        .dom(`${folded} [data-test-resolved-chip]`)
        .doesNotHaveAttribute('data-arrived');
    });
  });

  module('the file tree', function (hooks) {
    hooks.beforeEach(function () {
      board().pullRequestDiff = prDiff(
        changed('src/widgets/changes.py', CHANGES),
        changed('src/widgets/old.py', [removed(1, 'gone')], {
          status: 'removed',
        }),
        changed('docs/guides/intro/start.md', [added(1, 'hello')], {
          status: 'renamed',
          old_path: 'docs/start.md',
        }),
        changed('README.md', [added(3, 'the widget'), ...LONG], {
          status: 'added',
        }),
      );
    });

    test('folds a folder with one folder in it into one row, folders before files, each file with its status', async function (assert) {
      await visit('/pr/o/r/7/diff');

      assert.deepEqual(texts('[data-test-tree-row]'), [
        'docs/guides/intro',
        'start.md',
        'src/widgets',
        'changes.py',
        'old.py',
        'README.md',
      ]);
      assert.deepEqual(
        findAll('[data-test-tree-row="file"]').map((one) =>
          one.getAttribute('data-status'),
        ),
        ['renamed', 'modified', 'removed', 'added'],
      );
    });

    test('nests each folder under its parent and each file under its folder, as GitHub does', async function (assert) {
      board().pullRequestDiff = prDiff(
        changed('src/widgets/changes.py', CHANGES),
        changed('src/main.py', [added(1, 'run()')]),
        changed('README.md', [added(3, 'the widget')]),
      );
      await visit('/pr/o/r/7/diff');

      assert.deepEqual(texts('[data-test-tree-row]'), [
        'src',
        'widgets',
        'changes.py',
        'main.py',
        'README.md',
      ]);
      assert
        .dom(
          '[data-test-tree-folder="src"] [data-test-tree-folder="src/widgets"] [data-path="src/widgets/changes.py"]',
        )
        .exists();
      assert
        .dom('[data-test-tree-folder="src"] [data-path="src/main.py"]')
        .exists();
      assert
        .dom('[data-test-tree-folder] [data-path="README.md"]')
        .doesNotExist('a file at the root sits under no folder');
    });

    test('a folder’s chevron folds what is under it and opens it again', async function (assert) {
      await visit('/pr/o/r/7/diff');
      const folder = '[data-test-tree-folder="src/widgets"]';

      await click(`${folder} [data-test-tree-row="folder"]`);

      assert
        .dom(`${folder} [data-test-tree-row="folder"]`)
        .hasAttribute('aria-expanded', 'false');
      assert.dom(`${folder} [data-test-tree-row="file"]`).doesNotExist();
      assert
        .dom('[data-test-tree-row="file"][data-path="README.md"]')
        .exists('other folders and files stay');

      await click(`${folder} [data-test-tree-row="folder"]`);

      assert.dom(`${folder} [data-test-tree-row="file"]`).exists({ count: 2 });
    });

    test('the filter keeps the files whose path has the words in it, and their folders', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await fillIn('[data-test-tree-filter]', 'WIDGETS/ch');

      assert.deepEqual(texts('[data-test-tree-row]'), [
        'src/widgets',
        'changes.py',
      ]);
    });

    test('clicking a file names it in the address and scrolls to it', async function (assert) {
      await visit('/pr/o/r/7/diff');

      await click(
        '[data-test-tree-row="file"][data-path="src/widgets/old.py"]',
      );

      assert.strictEqual(
        currentURL(),
        '/pr/o/r/7/diff?file=src%2Fwidgets%2Fold.py',
      );
      assert
        .dom('[data-test-tree-row="file"][data-path="src/widgets/old.py"]')
        .hasAttribute('aria-current', 'true');
      assert.true(scrolledTo('src/widgets/old.py'), 'old.py is at the top');
    });

    test('an address naming a file opens scrolled to it', async function (assert) {
      await visit('/pr/o/r/7/diff?file=src%2Fwidgets%2Fold.py');

      assert.true(scrolledTo('src/widgets/old.py'), 'old.py is at the top');
    });

    test('an address naming a line opens with that line in the middle of the pane', async function (assert) {
      await visit('/pr/o/r/7/diff?file=README.md&line=80');

      const pane = find('[data-test-diff-files]')!.getBoundingClientRect();
      const row = find(
        '[data-test-file="README.md"] [data-line="80"]',
      )!.getBoundingClientRect();
      const middle = pane.top + pane.height / 2;
      assert.true(
        Math.abs(row.top + row.height / 2 - middle) < row.height,
        'line 80 sits in the middle',
      );
    });

    test('an address naming a line the diff does not show opens scrolled to its file', async function (assert) {
      await visit('/pr/o/r/7/diff?file=src%2Fwidgets%2Fold.py&line=500');

      assert.true(scrolledTo('src/widgets/old.py'), 'old.py is at the top');
    });

    test('clicking a file drops the line from the address', async function (assert) {
      await visit('/pr/o/r/7/diff?file=README.md&line=80');

      await click(
        '[data-test-tree-row="file"][data-path="src/widgets/old.py"]',
      );

      assert.strictEqual(
        currentURL(),
        '/pr/o/r/7/diff?file=src%2Fwidgets%2Fold.py',
      );
    });
  });
});
