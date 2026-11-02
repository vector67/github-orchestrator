import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, findAll, visit } from '@ember/test-helpers';
import { heldPr, setupFakeBoard } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;
const FOLDER = '/data/thread-worktrees/o/r/7/PRRT_a';

module('Acceptance | thread names migration', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function waiting(): void {
    board().held = [heldPr()];
    board().unheld = {
      code: 'waiting-to-migrate',
      detail:
        'terminal sessions are in folders the thread names migration moves',
    };
    board().migration = {
      migrated: false,
      sessions: [{ repo: 'o/r', number: 7, thread: 'PRRT_a', folder: FOLDER }],
    };
  }

  test('a hub waiting to migrate names each session in its way', async function (assert) {
    waiting();

    await visit('/');
    await clock().tick(LIST);

    assert.dom('[data-test-wall-unheld="waiting-to-migrate"]').exists();
    assert.deepEqual(
      findAll('[data-test-migration-session]').map((one) =>
        one.textContent.trim().replace(/\s+/g, ' '),
      ),
      [`o/r#7 thread PRRT_a ${FOLDER}`],
    );
  });

  test('a wall that had rows before the hub began waiting still offers to close the sessions', async function (assert) {
    board().held = [heldPr()];
    await visit('/');
    assert.dom('[data-test-wall-row="o/r#7"]').exists();

    waiting();
    await clock().tick(LIST);

    assert.dom('[data-test-close-sessions-and-migrate]').exists();
    assert.strictEqual(findAll('[data-test-migration-session]').length, 1);
  });

  test('close sessions and migrate closes them and the wall fills in', async function (assert) {
    waiting();
    await visit('/');
    await clock().tick(LIST);

    await click('[data-test-close-sessions-and-migrate]');
    await clock().tick(LIST);

    assert.strictEqual(board().migrationsAsked, 1);
    assert.dom('[data-test-wall-unheld]').doesNotExist();
    assert.dom('[data-test-wall-row="o/r#7"]').exists();
  });
});
