import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { currentURL, findAll, triggerEvent, visit } from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

module('Acceptance | git palette', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  setupFakeClock(hooks);

  function onTheHub(boardUp = true): void {
    board().serves = 'hub';
    board().manager = dashboard();
    board().held = [heldPr({ board_url: boardUp ? '/pr/o/r/7' : null })];
  }

  async function press(...keys: string[]): Promise<void> {
    for (const key of keys) await triggerEvent(document, 'keydown', { key });
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  function ran(): unknown[] {
    return board()
      .posted.filter((one) => one.verb === 'git')
      .map((one) => one.body);
  }

  test('g alone opens the palette with every command and where it runs, with no Git button or git block', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="git"]').doesNotExist();
    assert.dom('[data-test-block="git"]').doesNotExist();
    await press('g');

    assert.dom('[data-test-palette]').exists();
    assert.deepEqual(texts('[data-test-palette-row]'), [
      'g f git push --force-with-lease runs here',
      'g p git push runs here',
      'g pra git pull --rebase --autostash runs here',
      'g s git status runs here',
      'g l git log shown',
      'g d git diff HEAD shown',
      'g a git add -p Terminal tab',
      'g c git commit Terminal tab',
      'g i<N> git rebase -i HEAD~<N> Terminal tab',
      'g r rebase-on-main in an agent session Terminal tab',
    ]);
    assert.dom('[data-test-palette-buffer]').hasText('> g');
  });

  test('g p Enter pushes in the worktree and shows what git printed', async function (assert) {
    onTheHub();
    board().gitRuns = {
      p: {
        exit_code: 0,
        lines: ['To github.com:o/r.git', '   a1b2c3d..e4f5a6b  HEAD -> fix'],
        seconds: 1.24,
        truncated: false,
      },
    };
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'p');
    assert
      .dom('[data-test-palette-footer]')
      .hasText('will run: git push · Enter run · Esc cancel');
    await press('Enter');

    assert.deepEqual(ran(), [{ keys: 'p' }]);
    assert.dom('[data-test-git-output-command]').hasText('git push');
    assert.dom('[data-test-git-output-status]').hasText('✓ exit 0 (1.2s)');
    assert.deepEqual(texts('[data-test-git-output-line]'), [
      'To github.com:o/r.git',
      'a1b2c3d..e4f5a6b HEAD -> fix',
    ]);
  });

  test('a command that fails shows its exit code as a failure', async function (assert) {
    onTheHub();
    board().gitRuns = {
      p: {
        exit_code: 1,
        lines: [' ! [rejected] fix -> fix (fetch first)'],
        seconds: 0.8,
        truncated: false,
      },
    };
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'p', 'Enter');

    assert.dom('[data-test-git-output-status]').hasText('✗ exit 1 (0.8s)');
    assert.dom('[data-test-git-output-status] [data-test-alarm]').exists();
  });

  test('force-push asks once more before it runs, and Esc then runs nothing', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'f', 'Enter');

    assert.deepEqual(ran(), []);
    assert
      .dom('[data-test-palette-footer]')
      .hasText(
        'Force-push with lease replaces the branch on GitHub with this worktree’s. Enter again to force-push · Esc cancel',
      );

    await press('Escape');

    assert.dom('[data-test-palette]').doesNotExist();
    assert.deepEqual(ran(), []);
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');

    await press('g', 'f', 'Enter', 'Enter');

    assert.deepEqual(ran(), [{ keys: 'f' }]);
  });

  test('a held Enter cannot confirm a force-push: only a fresh press does', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'f', 'Enter');
    await triggerEvent(document, 'keydown', { key: 'Enter', repeat: true });

    assert.deepEqual(ran(), []);

    await press('Enter');

    assert.deepEqual(ran(), [{ keys: 'f' }]);
  });

  test('p is a command and the start of pra, so typing on reaches the pull', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'p');
    assert.dom('[data-test-palette-buffer]').hasText('> g p');
    assert.deepEqual(board().posted, []);
    await press('r');
    assert.dom('[data-test-palette-footer]').hasText('Esc cancel');
    await press('a');
    assert
      .dom('[data-test-palette-footer]')
      .hasText(
        'will run: git pull --rebase --autostash · Enter run · Esc cancel',
      );
    await press('Backspace', 'Backspace');
    assert.dom('[data-test-palette-buffer]').hasText('> g p');
    await press('r', 'a', 'Enter');

    assert.deepEqual(ran(), [{ keys: 'pra' }]);
  });

  test('log and diff are shown read-only in the page', async function (assert) {
    onTheHub();
    board().gitRuns = {
      l: {
        exit_code: 0,
        lines: ['commit e4f5a6b', 'Author: me', '', '    Fix the widget'],
        seconds: 0.1,
        truncated: true,
      },
    };
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'l', 'Enter');

    assert.deepEqual(ran(), [{ keys: 'l' }]);
    assert.dom('[data-test-git-output-command]').hasText('git log');
    assert.strictEqual(findAll('[data-test-git-output-line]').length, 4);
    assert
      .dom('[data-test-git-output-truncated]')
      .hasText('Only the first 2000 lines are shown.');
  });

  test('a key that names no command closes the palette', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 'z');

    assert.dom('[data-test-palette]').doesNotExist();

    await press('g', '1');

    assert.dom('[data-test-palette]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
  });

  test('Esc closes the palette and its output without leaving for the wall', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');

    await press('g', 's', 'Enter');
    await press('Escape');

    assert.dom('[data-test-palette]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/dashboard');
  });

  test('a run the board cannot be reached for says so in the palette and is reported', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');
    board().broken = /\/api\/manager\/git$/;

    await press('g', 's', 'Enter');

    assert
      .dom('[data-test-git-output-status]')
      .hasText('git status did not run: the board server is not answering');
    assert.deepEqual(
      board().reported.map(({ where }) => where),
      ['manager git'],
    );
  });

  test('a run the board refuses says the refusal in the palette and is not reported', async function (assert) {
    onTheHub();
    await visit('/pr/o/r/7/dashboard');
    board().refusal = {
      status: 503,
      code: 'board-unreachable',
      detail: 'acme/widgets#7’s board is not answering',
    };

    await press('g', 's', 'Enter');

    assert
      .dom('[data-test-git-output-status]')
      .hasText(
        'git status did not run: acme/widgets#7’s board is not answering',
      );
    assert.deepEqual(board().reported, []);
  });

  test('with the board down git waits for it and the palette does not open', async function (assert) {
    onTheHub(false);
    await visit('/pr/o/r/7/dashboard');

    await press('g');

    assert.dom('[data-test-palette]').doesNotExist();
    assert
      .dom('[data-test-toast]')
      .hasText('Git runs through the manager’s board, which is not answering.');
  });
});
