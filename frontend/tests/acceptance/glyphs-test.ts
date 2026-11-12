import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { findAll, visit } from '@ember/test-helpers';
import {
  operation,
  proposal,
  setupFakeBoard,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';

const KEY = 'PRRT_glyphs';

function marks(selector: string): string[] {
  return findAll(selector).map((one) =>
    [
      one.getAttribute('data-test-decision'),
      one.hasAttribute('data-runs-agent') ? '✦' : '',
      one.hasAttribute('data-opens-dialog') ? '⧉' : '',
    ].join(''),
  );
}

async function footerIn(
  board: FakeBoard,
  phase: Parameters<FakeBoard['threadIn']>[0],
): Promise<string[]> {
  board.conversations = [board.threadIn(phase, { key: KEY })];
  await visit(`/pr/o/r/7/conversations/${KEY}`);
  return marks('#panel-actions [data-test-decision]');
}

module('Acceptance | glyphs', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('a proposed fix marks each button that opens a dialog, and Send back for rework as an agent run too', async function (assert) {
    assert.deepEqual(await footerIn(board(), 'proposed'), [
      'approve⧉',
      'rework✦⧉',
      'defer⧉',
      'reject⧉',
      'resolve⧉',
      'start-session✦⧉',
    ]);
  });

  test('the glyphs follow the label, the star before the window', async function (assert) {
    await footerIn(board(), 'proposed');

    const drawn = findAll('[data-test-decision="rework"] [data-glyph]').map(
      (one) => one.getAttribute('data-glyph'),
    );
    assert.deepEqual(drawn, ['agent', 'dialog']);
    assert
      .dom('[data-test-decision="approve"] [data-glyph="agent"]')
      .doesNotExist();
  });

  test('Stop carries no window icon, because it becomes the red are-you-sure', async function (assert) {
    assert.deepEqual(await footerIn(board(), 'working'), ['stop', 'defer⧉']);
  });

  test('starting the agent again carries the star and no window', async function (assert) {
    assert.deepEqual((await footerIn(board(), 'failed')).slice(0, 1), [
      'retry✦',
    ]);
  });

  test('Bring back after a reject re-runs the agent, so it carries the star', async function (assert) {
    assert.deepEqual(await footerIn(board(), 'rejected'), ['unpark✦']);
  });

  test('Bring back after a resolve runs no agent', async function (assert) {
    assert.deepEqual(await footerIn(board(), 'resolved'), ['unpark']);
  });

  test('an agent asking a question offers a session with the star, and Drop without the window icon', async function (assert) {
    assert.deepEqual(await footerIn(board(), 'asking'), [
      'answer-in-session✦',
      'drop',
    ]);
    assert.dom('[data-test-question-option]').hasAttribute('data-runs-agent');
    assert
      .dom('[data-test-question-other]')
      .doesNotHaveAttribute('data-runs-agent');
  });

  test('accepting a proposed ticket starts the agent that files it', async function (assert) {
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY, plan: [] }),
    ];
    board().proposals[KEY] = [
      proposal({
        id: `${KEY}.1.proposal`,
        kind: 'ticket',
        reply: 'That belongs outside this PR, so I have proposed a ticket.',
        ticket: {
          project: 'PROJ',
          title: 'Cache tax rates across exports',
          body: 'Each export reads its tax rate again.',
        },
        commits: null,
        summary: null,
        commit_message: null,
      }),
    ];

    const offered = await footerIn(board(), 'proposed');

    assert.strictEqual(offered[0], 'approve✦⧉');
  });

  test('the reviewer’s Reply opens the composer in place, not a dialog', async function (assert) {
    board().actAs('reviewer');

    assert.deepEqual(await footerIn(board(), 'answered'), [
      'resolve⧉',
      'not-fixed⧉',
      'place⧉',
      'reply',
      'defer⧉',
    ]);
  });
});
