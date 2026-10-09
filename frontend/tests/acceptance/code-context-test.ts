import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, visit, waitFor } from '@ember/test-helpers';
import {
  setupFakeBoard,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';

const SOURCE = 'c0ffee1:src/foo.py';

function sourceWith(lines: Record<number, string>): string[] {
  return Array.from(
    { length: 60 },
    (_, at) => lines[at + 1] ?? `line ${at + 1}`,
  );
}

function codeAsks(board: FakeBoard) {
  return board.askedFor(/\/api\/files\?/).map((one) => one.url);
}

module('Acceptance | code context', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      thread({ key: 'k1' }),
      thread({
        key: 'k2',
        anchor: { ...thread().anchor, line: 8, original_line: 8 },
      }),
    ];
    board().sources[SOURCE] = sourceWith({
      41: 'def helper():',
      42: '    return rows',
      8: 'the next comment in its code',
    });
  });

  test('it reads the lines the comment sits in, at the commit it names', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-context]').containsText('return rows');
    assert.deepEqual(codeAsks(board()), [
      '/api/files?sha=c0ffee1&path=src%2Ffoo.py&from_line=39&to_line=45',
    ]);
  });

  test('See in diff opens the diff tab at the file and line the comment sits on', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-context] [data-test-see-in-diff]');

    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/diff?file=src%2Ffoo.py&line=42',
    );
  });

  test('an outdated thread reads its lines at the commit it was written on, though GitHub still names a line', async function (assert) {
    board().conversations = [
      thread({
        key: 'k1',
        anchor: {
          ...thread().anchor,
          line: 42,
          original_line: 42,
          is_outdated: true,
        },
      }),
    ];
    board().sources['a1b2c3d:src/foo.py'] = sourceWith({
      42: '    return old_rows',
    });

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-context]').containsText('return old_rows');
    assert.deepEqual(codeAsks(board()), [
      '/api/files?sha=a1b2c3d&path=src%2Ffoo.py&from_line=39&to_line=45',
    ]);
  });

  test('an outdated thread says so, and names the commit its code is from', async function (assert) {
    board().conversations = [
      thread({
        key: 'k1',
        anchor: { ...thread().anchor, is_outdated: true },
      }),
    ];
    board().sources['a1b2c3d:src/foo.py'] = sourceWith({});

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-code-outdated]').hasText('Outdated · at a1b2c3d');
  });

  test('a current thread says nothing of being outdated', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-code-outdated]').doesNotExist();
  });

  test('the code is drawn in the language of its file, its words intact', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    const code = document.querySelector(
      '[data-test-context] [data-ranged] [data-test-code]',
    );
    assert.dom(code).hasText('return rows');
    assert.strictEqual(
      code?.firstElementChild?.textContent,
      'return',
      'the keyword is a token of its own',
    );
  });

  test('the line the comment is on is the one marked', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    const marked = document.querySelectorAll(
      '[data-test-context] [data-ranged]',
    );
    assert.strictEqual(marked.length, 1);
    assert.dom(marked[0]).containsText('return rows');
  });

  test('another anchor asks for its own lines', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await visit('/pr/o/r/7/conversations/k2');

    assert.dom('[data-test-context]').containsText('the next comment');
    assert.strictEqual(codeAsks(board()).length, 2);
  });

  test('the last code goes the moment another anchor arrives', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    const release = board().hold(/\/api\/files\?.*from_line=5&/);

    const going = visit('/pr/o/r/7/conversations/k2');
    await waitFor('[data-test-loading="code"]');

    assert.dom('[data-test-context]').doesNotContainText('return rows');

    release();
    await going;
  });

  test('the code says it is loading until its lines arrive', async function (assert) {
    const release = board().hold(/\/api\/files\?/);

    const visiting = visit('/pr/o/r/7/conversations/k1');
    await waitFor('[data-test-loading="code"]');

    assert.dom('[data-test-loading="code"]').hasText('Loading the code…');

    release();
    await visiting;

    assert.dom('[data-test-loading="code"]').doesNotExist();
    assert.dom('[data-test-context]').containsText('return rows');
  });

  test('code the board could not read stops saying it is loading', async function (assert) {
    board().broken = /\/api\/files\?/;

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-loading="code"]').doesNotExist();
  });

  test('code the board cannot read draws nothing', async function (assert) {
    delete board().sources[SOURCE];

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-context]').hasNoText();
  });

  test('code the board could not read is asked for again on coming back', async function (assert) {
    const source = board().sources[SOURCE]!;
    delete board().sources[SOURCE];
    await visit('/pr/o/r/7/conversations/k1');
    board().sources[SOURCE] = source;

    await visit('/pr/o/r/7/conversations/k2');
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-context]').containsText('return rows');
    assert.strictEqual(codeAsks(board()).length, 3);
  });
});
