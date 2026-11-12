import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, findAll, visit } from '@ember/test-helpers';
import { heldPr, setupFakeBoard } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;
const FOLDER = '/data/thread-worktrees/o/r/7/PRRT_a';
const CLONE = '/data/clones/o/r';
const OLD_BRANCH = 'orchestrator/thread/7/PRRT_b';
const NEW_BRANCH = 'orchestrator/thread/7/PRRT_b-2';
const GIT_SAID =
  "error: Unable to create '/data/clones/o/r/.git/refs/heads/orchestrator/thread/7/PRRT_b-2.lock': File exists.";

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
      branches: [],
    };
  }

  function stuck(): void {
    board().held = [heldPr()];
    board().unheld = {
      code: 'waiting-to-migrate',
      detail: 'a thread branch would not take its new name',
    };
    board().migration = {
      migrated: false,
      sessions: [],
      branches: [
        {
          repo: 'o/r',
          number: 7,
          thread: 'PRRT_b',
          branch: OLD_BRANCH,
          new_branch: NEW_BRANCH,
          clone: CLONE,
          error: GIT_SAID,
        },
      ],
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

  test('a branch that would not take its new name is named with what git said and what to do', async function (assert) {
    stuck();

    await visit('/');
    await clock().tick(LIST);

    assert.dom('[data-test-wall-unheld="waiting-to-migrate"]').exists();
    assert.dom('[data-test-migration-sessions-note]').doesNotExist();
    assert.strictEqual(findAll('[data-test-migration-session]').length, 0);
    assert.deepEqual(
      findAll('[data-test-migration-branch]').map((one) =>
        one.textContent.trim().replace(/\s+/g, ' '),
      ),
      [
        `o/r#7 thread PRRT_b ${OLD_BRANCH} would not become ${NEW_BRANCH} ${GIT_SAID} git -C ${CLONE} branch -m ${OLD_BRANCH} ${NEW_BRANCH}`,
      ],
    );
    assert
      .dom('[data-test-migration-branches-note]')
      .includesText('Close sessions and migrate');
  });

  test('a hub held only by sessions says nothing about branches', async function (assert) {
    waiting();

    await visit('/');
    await clock().tick(LIST);

    assert.dom('[data-test-migration-sessions-note]').exists();
    assert.dom('[data-test-migration-branches-note]').doesNotExist();
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
