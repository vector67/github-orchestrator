import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, currentURL, triggerEvent } from '@ember/test-helpers';
import type { Conversation } from 'frontend/data/api';
import {
  operation,
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';

function columnCounts(): [string | null, string][] {
  return [...document.querySelectorAll('[data-test-column]')].map((node) => [
    node.getAttribute('data-test-column'),
    node.querySelector('[data-test-column-count]')?.textContent?.trim() ?? '',
  ]);
}

function steps(card: string): (string | null)[] {
  return [...document.querySelectorAll(`${card} [data-test-step]`)].map(
    (node) => node.getAttribute('data-done'),
  );
}

function readingOrder(card: string): string[] {
  return [
    ...document.querySelectorAll(
      [
        '[data-test-card-path]',
        '[data-test-card-title]',
        '[data-test-card-steps]',
        '[data-test-card-meta]',
      ]
        .map((hook) => `${card} ${hook}`)
        .join(', '),
    ),
  ].map((node) => node.textContent?.trim() ?? '');
}

module('Acceptance | board', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      board().threadIn('working', { key: 'PRRT_w' }),
      board().threadIn('proposed', { key: 'PRRT_r' }),
      thread({ key: 'PRRT_o', reopened: true }),
      board().threadIn('waiting', { key: 'PRRT_x' }),
      board().threadIn('landed', { key: 'PRRT_d' }),
      board().threadIn('queued', { key: 'PRRT_q' }),
    ];
  });

  test('the board heads its five columns in its own order', async function (assert) {
    await visit('/pr/o/r/7/board');

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-column-name]')].map((node) =>
        node.textContent?.trim(),
      ),
      ['Agent working', 'Ready for you', 'Needs a look', 'Waiting', 'Done'],
    );
  });

  test('Esc on the columns goes back to the rail', async function (assert) {
    await visit('/pr/o/r/7/board');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('#rows').exists();
    assert.true(currentURL().startsWith('/pr/o/r/7/conversations'));
  });

  test('a reviewer’s columns use the queue’s words for the author’s answer', async function (assert) {
    board().actAs('reviewer');

    await visit('/pr/o/r/7/board');

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-column-name]')].map((node) =>
        node.textContent?.trim(),
      ),
      ['Agent working', 'Answered', 'Needs a look', 'Waiting', 'Done'],
    );
  });

  test('a reviewer’s assumed done and not my conversation cards stand in the Done column', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('assumed-done', { key: 'PRRT_a' }),
      board().threadIn('not-mine', { key: 'PRRT_n' }),
    ];

    await visit('/pr/o/r/7/board');

    assert.dom('[data-test-column="done"] [data-test-card="PRRT_a"]').exists();
    assert.dom('[data-test-column="done"] [data-test-card="PRRT_n"]').exists();
  });

  test('every column head and queue heading says what stands under it', async function (assert) {
    await visit('/pr/o/r/7/board');

    const columns = [...document.querySelectorAll('[data-test-column-name]')];
    assert.true(
      columns.every((node) => (node.getAttribute('title') ?? '').length > 0),
    );

    await visit('/pr/o/r/7/conversations');

    const headings = [...document.querySelectorAll('[data-test-heading]')];
    assert.true(headings.length > 0);
    assert.true(
      headings.every((node) => (node.getAttribute('title') ?? '').length > 0),
    );
  });

  test('it heads every column, empty or not', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'a' })];

    await visit('/pr/o/r/7/board');

    assert.deepEqual(
      columnCounts(),
      [
        ['working', '0'],
        ['ready', '1'],
        ['attention', '0'],
        ['waiting', '0'],
        ['done', '0'],
      ],
      'the design stands five columns whatever the PR is doing',
    );
  });

  test('a column counts the cards standing in it', async function (assert) {
    await visit('/pr/o/r/7/board');

    assert
      .dom('[data-test-column="working"] [data-test-column-count]')
      .hasText('2', 'a queued run stands with the working ones');
    assert
      .dom('[data-test-column="working"] [data-test-card="PRRT_q"]')
      .exists();
    assert
      .dom('[data-test-column="done"] [data-test-column-count]')
      .hasText('1');
  });

  test('a card stands in its own column and nowhere else', async function (assert) {
    await visit('/pr/o/r/7/board');

    assert
      .dom('[data-test-column="attention"] [data-test-card="PRRT_o"]')
      .exists('a reply that came back with nothing to decide needs a look');
    assert.dom('[data-test-card="PRRT_o"]').exists({ count: 1 });
  });

  test('clicking a card opens it in the queue', async function (assert) {
    await visit('/pr/o/r/7/board');

    await click('[data-test-card="PRRT_r"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/PRRT_r');
    assert.dom('#panel').exists('the board hands the decision to the queue');
  });

  test('a card carries the state of its thread', async function (assert) {
    await visit('/pr/o/r/7/board');

    assert
      .dom('[data-test-card="PRRT_r"]')
      .hasAttribute('data-square', 'ready')
      .hasAttribute('data-group', 'ready');
    assert
      .dom('[data-test-card="PRRT_o"]')
      .hasAttribute('data-square', 'reopened');
  });
});

module('Acceptance | board | what a card says', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  async function cardFor(one: Conversation): Promise<string> {
    board().conversations = [one];
    await visit('/pr/o/r/7/board');
    return `[data-test-card="${one.key}"]`;
  }

  test('a running card reads location, title, steps, then meta', async function (assert) {
    board().inFlight = [
      operation({
        state: 'running',
        plan: [
          { text: 'a', file: null, done: true },
          { text: 'b', file: null, done: false },
          { text: 'c', file: null, done: false },
        ],
      }),
    ];

    const card = await cardFor(
      thread({
        state: 'working',
        operations: [
          summary({ state: 'running', steps_done: 0, steps_total: 3 }),
        ],
      }),
    );

    assert.deepEqual(readingOrder(card), [
      'src/foo.py:42',
      'rename the helper',
      '1 / 3 changes',
      'Anna Example · running · 1/3',
    ]);
    assert.deepEqual(
      steps(card),
      ['1', null, null],
      'a filled square is a change the agent has finished, off the fast poll',
    );
  });

  test('a proposal draws a square per change and fills the finished ones', async function (assert) {
    const card = await cardFor(
      thread({ operations: [summary({ steps_done: 2, steps_total: 3 })] }),
    );

    assert.deepEqual(steps(card), ['1', '1', null]);
    assert.dom(`${card} [data-test-card-steps]`).hasText('2 / 3 changes');
    assert
      .dom(`${card} [data-test-card-meta]`)
      .hasText('Anna Example · 2 of 3 changes');
  });

  test('a settled card counts no changes and says how it ended', async function (assert) {
    const card = await cardFor(board().threadIn('landed'));

    assert.dom(`${card} [data-test-step]`).doesNotExist();
    assert.dom(`${card} [data-test-card-steps]`).hasText('landed');
    assert
      .dom(`${card} [data-test-card-steps]`)
      .hasAttribute('title', 'landed: on the PR branch');
    assert.dom(`${card} [data-test-card-meta]`).hasText('Pushed');
    assert.dom(card).hasAttribute('data-group', 'done');
  });

  test('a card with nothing to say draws no meta line', async function (assert) {
    const card = await cardFor(thread({ comments: [] }));

    assert.dom(`${card} [data-test-card-title]`).hasText('rename the helper');
    assert.dom(`${card} [data-test-card-meta]`).doesNotExist();
  });
});
