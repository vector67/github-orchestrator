import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, waitUntil } from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import { setupOtherTab } from 'frontend/tests/helpers/other-tab';

const SEVEN_NOTES = '/pr/o/r/7/api/manager/changes/stream';
const EIGHT_NOTES = '/pr/o/r/8/api/manager/changes/stream';

function relayed(path: string): unknown {
  if (path.includes('/manager/changes/')) {
    return { markdown: 'Split the writer.' };
  }
  if (path.includes('/manager/agent-output/')) return { lines: [] };
  return dashboard();
}

module('Acceptance | streams shared across tabs', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  setupFakeClock(hooks);
  const other = setupOtherTab(hooks);

  hooks.beforeEach(function () {
    board().manager = dashboard();
    board().held = [heldPr(), heldPr({ number: 8 })];
  });

  function followed(): string[] {
    return board()
      .openStreams.map((one) => new URL(one.url, 'http://127.0.0.1').pathname)
      .sort();
  }

  test('a tab whose streams another tab holds opens no connection and shows what that tab relays', async function (assert) {
    await other().lead(relayed);

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(board().connections, []);
    assert.dom('[data-test-notes]').hasText('Split the writer.');
    assert.dom('[data-test-not-live]').doesNotExist();
  });

  test('when the tab holding the streams goes away, this tab takes them over on its own connection', async function (assert) {
    await other().lead(relayed);
    await visit('/pr/o/r/7/dashboard');

    other().stepDown();
    await waitUntil(() => board().connections.length === 1);
    await waitUntil(() => other().said.some((one) => one.kind === 'ask'));

    assert.deepEqual(followed(), [
      '/pr/o/r/7/api/dashboard/stream',
      '/pr/o/r/7/api/manager/agent-output/stream',
      '/pr/o/r/7/api/manager/changes/stream',
    ]);
  });

  test('a tab on another pull request is followed on the same connection and sent what it hears', async function (assert) {
    board().changes = 'Split the writer.';
    await visit('/pr/o/r/7/dashboard');

    other().tell({ kind: 'want', tab: 'other', paths: [EIGHT_NOTES] });
    await waitUntil(() => other().heard(EIGHT_NOTES).length > 0);

    assert.strictEqual(board().connections.length, 1);
    assert.ok(followed().includes(EIGHT_NOTES));
    assert.deepEqual(other().heard(EIGHT_NOTES), [
      { markdown: 'Split the writer.' },
    ]);
  });

  test('a tab on the same pull request is sent what the connection already heard', async function (assert) {
    board().changes = 'Split the writer.';
    await visit('/pr/o/r/7/dashboard');
    await waitUntil(() => other().heard(SEVEN_NOTES).length > 0);
    other().forget();

    other().tell({ kind: 'want', tab: 'other', paths: [SEVEN_NOTES] });
    await waitUntil(() => other().heard(SEVEN_NOTES).length > 0);

    assert.deepEqual(other().heard(SEVEN_NOTES), [
      { markdown: 'Split the writer.' },
    ]);
  });

  test('a tab that closes is no longer followed', async function (assert) {
    await visit('/pr/o/r/7/dashboard');
    other().tell({ kind: 'want', tab: 'other', paths: [EIGHT_NOTES] });
    await waitUntil(() => followed().includes(EIGHT_NOTES));

    other().tell({ kind: 'gone', tab: 'other' });
    await waitUntil(() => !followed().includes(EIGHT_NOTES));

    assert.strictEqual(board().connections.length, 1);
    assert.strictEqual(followed().length, 3);
  });
});
