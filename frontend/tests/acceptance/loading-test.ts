import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, find, rerender, waitFor } from '@ember/test-helpers';
import {
  comment,
  heldPr,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

module('Acceptance | loading', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(): void {
    board().serves = 'hub';
    board().held = [heldPr()];
  }

  test('the board says it is loading until the server answers', async function (assert) {
    board().conversations = [thread({ key: 'k1' })];
    const release = board().hold(/\/api\/conversations$/);

    const visiting = visit('/pr/o/r/7/conversations');
    await waitFor('[data-test-loading="board"]');

    assert.dom('[data-test-loading="board"]').hasText('Loading the board…');

    release();
    await visiting;

    assert.dom('[data-test-loading="board"]').doesNotExist();
    assert.dom('#c-k1').exists();
  });

  test('the columns view says it is loading until the server answers', async function (assert) {
    const release = board().hold(/\/api\/conversations$/);

    const visiting = visit('/pr/o/r/7/board');
    await waitFor('[data-test-loading="board"]');

    assert.dom('[data-test-loading="board"]').exists();

    release();
    await visiting;

    assert.dom('[data-test-loading="board"]').doesNotExist();
  });

  test('the PR bar stays up while the board loads under it', async function (assert) {
    onTheHub();
    const release = board().hold(/\/api\/conversations$/);

    const visiting = visit('/pr/o/r/7/conversations');
    await waitFor('[data-test-loading="board"]');

    assert.dom('[data-test-pr-bar]').exists();

    release();
    await visiting;
  });

  test('the board is drawn without waiting for the hub’s list of pull requests', async function (assert) {
    onTheHub();
    const release = board().hold(/\/api\/pull-requests$/);

    const visiting = visit('/pr/o/r/7/board');
    await waitFor('[data-test-board-columns]');

    assert.dom('[data-test-pr-bar]').exists();

    release();
    await visiting;
  });

  test('the wall says it is loading the wall, under the hub bar', async function (assert) {
    onTheHub();
    const release = board().hold(/\/api\/pull-requests$/);

    const visiting = visit('/');
    await waitFor('[data-test-loading="wall"]');

    assert.dom('[data-test-loading="wall"]').hasText('Loading the wall…');
    assert.dom('[data-test-nav="wall"]').exists();

    release();
    await visiting;

    assert.dom('[data-test-loading="wall"]').doesNotExist();
  });

  test('after ten seconds the wall names each read it is still waiting on once', async function (assert) {
    onTheHub();
    const release = board().hold(/\/api\/pull-requests$/);

    const visiting = visit('/');
    await waitFor('[data-test-loading="wall"]');
    void clock().tick(5_000);
    void clock().tick(5_000);
    await waitFor('[data-test-waiting]');

    const said = find('[data-test-waiting]')?.textContent ?? '';
    assert.strictEqual(said.split('/api/pull-requests').length - 1, 1);

    release();
    await visiting;
  });

  test('the runs page says it is loading the runs, under the hub bar', async function (assert) {
    onTheHub();
    const release = board().hold(/\/api\/runs$/);

    const visiting = visit('/runs');
    await waitFor('[data-test-loading="runs"]');

    assert.dom('[data-test-loading="runs"]').hasText('Loading the runs…');
    assert.dom('[data-test-nav="runs"]').exists();

    release();
    await visiting;
  });

  test('after ten seconds the loading board says what it is still waiting on', async function (assert) {
    const release = board().hold(/\/api\/conversations$/);

    const visiting = visit('/pr/o/r/7/conversations');
    await waitFor('[data-test-loading="board"]');
    void clock().tick(9_000);
    await rerender();

    assert.dom('[data-test-waiting]').doesNotExist();

    void clock().tick(1_000);
    await waitFor('[data-test-waiting]');

    assert.dom('[data-test-waiting]').includesText('/api/conversations');

    release();
    await visiting;

    assert.dom('[data-test-waiting]').doesNotExist();
  });

  test('a thread says it is loading until its comments arrive', async function (assert) {
    board().conversations = [thread({ key: 'k1' })];
    board().comments['k1'] = [comment({ body: 'please rename' })];
    const release = board().hold(/\/comments$/);

    const visiting = visit('/pr/o/r/7/conversations/k1');
    await waitFor('[data-test-loading="thread"]');

    assert.dom('[data-test-loading="thread"]').hasText('Loading the thread…');
    assert.dom('[data-test-transcript]').doesNotExist();

    release();
    await visiting;

    assert.dom('[data-test-loading="thread"]').doesNotExist();
    assert.dom('[data-test-transcript]').includesText('please rename');
  });

  test('after ten seconds a thread says it is still waiting on its comments', async function (assert) {
    board().conversations = [thread({ key: 'k1' })];
    const release = board().hold(/\/comments$/);

    const visiting = visit('/pr/o/r/7/conversations/k1');
    await waitFor('[data-test-loading="thread"]');
    void clock().tick(10_000);
    await waitFor('#panel-talk [data-test-waiting]');

    assert
      .dom('#panel-talk [data-test-waiting]')
      .includesText('/api/conversations/k1/comments');

    release();
    await visiting;
  });

  test('after ten seconds the code says it is still waiting on its lines', async function (assert) {
    board().conversations = [thread({ key: 'k1' })];
    const release = board().hold(/\/api\/files\?/);

    const visiting = visit('/pr/o/r/7/conversations/k1');
    await waitFor('[data-test-loading="code"]');
    void clock().tick(10_000);
    await waitFor('[data-test-context] [data-test-waiting]');

    assert
      .dom('[data-test-context] [data-test-waiting]')
      .includesText('/api/files?');

    release();
    await visiting;
  });

  test('the buttons wait while a decision is on its way', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');
    const release = board().hold(/operations:unpark$/);

    const clicking = click('[data-test-decision="unpark"]');
    await waitFor('#panel-actions[aria-busy="true"]');

    assert.dom('[data-test-decision="unpark"]').isDisabled();

    release();
    await clicking;

    assert.dom('#panel-actions').doesNotHaveAttribute('aria-busy');
    assert.strictEqual(board().posted.length, 1);
  });

  test('code already read is drawn at once on coming back to its thread', async function (assert) {
    board().conversations = [
      thread({ key: 'k1' }),
      thread({
        key: 'k2',
        anchor: { ...thread().anchor, line: 10, original_line: 10 },
      }),
    ];
    board().files = {
      sha: 'c0ffee1',
      path: 'src/foo.py',
      from_line: 39,
      to_line: 45,
      truncated: false,
      lines: [{ number: 42, text: '    return helper()' }],
    };
    await visit('/pr/o/r/7/conversations/k1');
    await visit('/pr/o/r/7/conversations/k2');
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-context]').includesText('return helper()');
    assert.strictEqual(board().askedFor(/\/api\/files/).length, 2);
  });
});
