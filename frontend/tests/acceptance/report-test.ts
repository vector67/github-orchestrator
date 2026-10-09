import QUnit, { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import { setupFakeBoard, thread } from 'frontend/tests/helpers/fake-board';

function nextTask(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

module('Acceptance | report', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [thread({ key: 'k1' })];
  });

  test('what failed is posted with its stack', async function (assert) {
    board().broken = /\/api\/conversations\/k1\/comments/;

    await visit('/pr/o/r/7/conversations/k1');

    const [report] = board().reported;
    assert.strictEqual(typeof report?.stack, 'string');
  });

  test('an error nothing caught is reported from the window', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    const qunits = window.onerror;
    window.onerror = null;
    try {
      window.dispatchEvent(
        new ErrorEvent('error', { error: new Error('boom'), message: 'boom' }),
      );
      await nextTask();
    } finally {
      window.onerror = qunits;
    }

    assert.deepEqual(
      board().reported.map(({ where, message }) => [where, message]),
      [['window', 'boom']],
    );
  });

  test('a rejection nothing handled is reported from the window', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    const rejected = new Event('unhandledrejection') as Event & {
      reason: unknown;
    };
    rejected.reason = new Error('never awaited');
    const qunits = QUnit.onUncaughtException;
    QUnit.onUncaughtException = () => {};
    try {
      window.dispatchEvent(rejected);
      await nextTask();
    } finally {
      QUnit.onUncaughtException = qunits;
    }

    assert.deepEqual(
      board().reported.map(({ where, message }) => [where, message]),
      [['window', 'never awaited']],
    );
  });
});
