import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';

function counts(): string[] {
  return [...document.querySelectorAll('#board-strip [data-test-count]')].map(
    (node) => node.textContent?.replace(/\s+/g, ' ').trim() ?? '',
  );
}

function stripCount(key: string): string {
  return (
    document
      .querySelector(`#board-strip [data-test-count="${key}"]`)
      ?.textContent?.replace(/\D+/g, '') ?? ''
  );
}

module('Acceptance | header counts', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('ready counts the proposals you can decide, and what else needs you has its own count', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'a' }),
      board().threadIn('declined', { key: 'b' }),
      board().threadIn('failed', { key: 'c' }),
      board().threadIn('queued', { key: 'e', reopened: true }),
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('deferred', { key: 'd' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(
      counts(),
      [
        '1 ready',
        '2 to look at',
        '1 queued',
        '1 waiting on reviewer',
        '1 deferred',
      ],
      'a decline and a failure are not decisions, a reopened run is where its agent is, and deferred is not waiting',
    );
  });

  test('the strip, the queue heading and the ready column give the same number', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'r' }),
      board().threadIn('proposed', { key: 'o', reopened: true }),
      board().threadIn('declined', { key: 'x' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.strictEqual(stripCount('ready'), '2');
    assert
      .dom('[data-test-heading="ready"] [data-test-count]')
      .hasText('2', 'the queue heading');

    await click('[data-test-view="board"]');

    assert
      .dom('[data-test-column="ready"] [data-test-column-count]')
      .hasText('2', 'the ready column');
    assert
      .dom('[data-test-column="ready"] [data-test-card="o"]')
      .exists('a reopened proposal stands where it is counted');
    assert
      .dom('[data-test-column="attention"] [data-test-card="x"]')
      .exists('a decline stands under its own column');
  });

  test('a reviewer counts deferred threads apart from those waiting on the author', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('waiting', { key: 'v' }),
      board().threadIn('deferred', { key: 'd' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(counts(), [
      '1 answered',
      '2 waiting on author',
      '1 deferred',
    ]);
    assert
      .dom('[data-test-heading="waiting"] [data-test-count]')
      .hasText('2', 'the heading and the strip agree');
  });

  test('a reviewer’s strip counts the assumed done and the not mine', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('assumed-done', { key: 'a' }),
      board().threadIn('assumed-done', { key: 'b' }),
      board().threadIn('not-mine', { key: 'n' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(counts(), [
      '1 waiting on author',
      '2 assumed done',
      '1 not mine',
    ]);
  });

  test('a reviewer’s drafts not added are not counted in the review', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('draft', { key: 'd1' }),
      board().threadIn('draft', { key: 'd2' }),
      board().threadIn('enrolled', { key: 'e' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(counts(), ['1 in your review', '2 local drafts']);
  });
});
