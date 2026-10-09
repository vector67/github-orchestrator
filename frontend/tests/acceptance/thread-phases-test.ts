import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import type { Conversation } from 'frontend/data/api';
import {
  setupFakeBoard,
  summary,
  thread,
  type FakeBoard,
  type Phase,
} from 'frontend/tests/helpers/fake-board';

function offered(): string[] {
  return [...document.querySelectorAll('[data-test-decision]')].map(
    (button) => button.firstChild?.textContent?.trim() ?? '',
  );
}

function fixLabel(): string | null {
  return (
    document.querySelector('[data-test-fix-label]')?.textContent?.trim() ?? null
  );
}

async function each<Name extends string>(
  board: FakeBoard,
  cases: [Name, Conversation][],
  check: (name: Name) => void,
): Promise<void> {
  board.conversations = cases.map(([, one], at) => ({ ...one, key: `k${at}` }));
  for (const [at, [name]] of cases.entries()) {
    await visit(`/pr/o/r/7/conversations/k${at}`);
    check(name);
  }
}

async function phases(
  board: FakeBoard,
  names: Phase[],
  check: (name: Phase) => void,
): Promise<void> {
  await each(
    board,
    names.map((name) => [name, board.threadIn(name)]),
    check,
  );
}

module('Acceptance | thread phases', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  for (const role of ['author', 'reviewer'] as const) {
    test(`every thread the machine reached for the ${role} names its phase on its card`, async function (assert) {
      board().actAs(role);
      const phases = board().phasesRecorded();
      board().conversations = phases.map((phase, at) =>
        board().threadIn(phase, { key: `k${at}` }),
      );

      await visit('/pr/o/r/7/board');

      assert.deepEqual(
        phases.map(
          (_, at) =>
            document
              .querySelector(`[data-test-card="k${at}"] [data-test-card-steps]`)
              ?.getAttribute('title')
              ?.split(':')[0],
        ),
        phases,
      );
    });
  }

  test('a run that settled refused left nothing to accept, whatever it said', async function (assert) {
    const stopped = thread({
      operations: [
        summary({
          state: 'refused',
          reason_code: 'withdrawn',
          attempts: 1,
          attempts_allowed: 3,
        }),
        summary({ id: 'op_000000000001', kind: 'stop' }),
      ],
    });

    await each(
      board(),
      [
        ['declined', board().threadIn('declined')],
        ['failed', board().threadIn('failed')],
        ['stopped', stopped],
      ],
      (name) => assert.dom('[data-test-decision="approve"]').doesNotExist(name),
    );
  });

  test('the newest run is the one that answers', async function (assert) {
    board().conversations = [
      thread({
        key: 'k1',
        operations: [
          summary(),
          summary({ id: 'PRRT_a.2', kind: 'rework', state: 'refused' }),
        ],
      }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-fix-label]').hasText('Agent gave up');
    assert.dom('[data-test-decision="approve"]').doesNotExist();
  });

  test('a ready thread says what its newest run left', async function (assert) {
    const labels: Record<string, string> = {
      proposed: 'Agent proposal',
      declined: 'Agent declined',
      failed: 'Agent gave up',
      stopped: 'You stopped the agent',
    };

    await phases(
      board(),
      ['proposed', 'declined', 'failed', 'stopped'],
      (name) => assert.strictEqual(fixLabel(), labels[name], name),
    );
  });

  test('a run you stopped says so, not that its attempts ran out', async function (assert) {
    board().conversations = [board().threadIn('stopped')];

    await visit('/pr/o/r/7/board');

    const title = document
      .querySelector('[data-test-card="PRRT_a"] [data-test-card-steps]')
      ?.getAttribute('title');
    assert.strictEqual(
      title,
      'stopped: you stopped the agent before it finished',
    );
  });

  test('a thread answered with no run behind it says nothing about a fix', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [board().threadIn('answered')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.dom('[data-test-fix-label]').doesNotExist();
  });

  test('a landing that failed is ready again and says where it stopped', async function (assert) {
    const said: Record<string, [string, string]> = {
      'push failed': ['Accepted · the push failed', 'Push it'],
      'reply failed': [
        'Accepted · pushed, the reply failed',
        'Retry the reply',
      ],
      'filing failed': ['Accepted · the filing failed', 'File it again'],
    };

    await phases(
      board(),
      ['push failed', 'reply failed', 'filing failed'],
      (phase) => {
        const [label, verb] = said[phase]!;
        assert.dom('[data-test-fix-label]').hasText(label, phase);
        assert.dom('[data-test-decision="approve"]').includesText(verb, phase);
      },
    );
  });

  test('a rework after a failed landing is the newer fact', async function (assert) {
    const pushFailed = board().threadIn('push failed', { key: 'k1' });
    board().conversations = [
      {
        ...pushFailed,
        operations: [
          ...pushFailed.operations,
          summary({
            id: 'op_000000000002',
            kind: 'rework',
            attempts: 1,
            attempts_allowed: 3,
          }),
        ],
      },
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-fix-label]').hasText('Agent proposal');
    assert.dom('[data-test-decision="approve"]').includesText('Accept');
  });

  test('a thread GitHub lost is removed whatever its runs did', async function (assert) {
    board().conversations = [board().threadIn('removed')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.dom('[data-test-fix-label]').hasText('Comment removed');
  });

  test('a landing tells a rebase from a pick by its newest run', async function (assert) {
    const labels: Record<string, string> = {
      rebasing: 'Rebasing onto the PR head',
      landing: 'Accepted · landing',
    };

    await phases(board(), ['rebasing', 'landing'], (phase) =>
      assert.dom('[data-test-fix-label]').hasText(labels[phase]!),
    );
  });

  test('a rebase an approve is waiting on offers no Stop the board would refuse', async function (assert) {
    board().conversations = [board().threadIn('rebasing')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.dom('[data-test-fix-label]').hasText('Rebasing onto the PR head');
    assert.dom('[data-test-decision="stop"]').doesNotExist();
  });

  test('a ticket being filed says so and offers no Stop the board would refuse', async function (assert) {
    board().conversations = [board().threadIn('filing')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.dom('[data-test-fix-label]').hasText('Accepted · filing the ticket');
    assert.deepEqual(offered(), []);
  });

  test('a done thread says how it closed', async function (assert) {
    const said: Record<string, [string, string]> = {
      landed: ['Accepted · pushed', 'Bring back'],
      rejected: ['Rejected · the fix was dropped', 'Reconsider'],
      resolved: ['Resolved on GitHub', 'Un-resolve'],
    };

    await phases(board(), ['landed', 'rejected', 'resolved'], (phase) => {
      const [label, verb] = said[phase]!;
      assert.strictEqual(fixLabel(), label, phase);
      assert.deepEqual(offered(), [verb], phase);
    });
  });

  test('a discarded draft says nothing about a fix and offers it back', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [board().threadIn('discarded')];

    await visit('/pr/o/r/7/conversations/draft_0000000000000001');

    assert.dom('[data-test-fix-label]').doesNotExist();
    assert.deepEqual(offered(), ['Bring back']);
  });

  test('the newest applied close names how the thread got to done', async function (assert) {
    board().conversations = [
      thread({
        key: 'k1',
        state: 'done',
        operations: [
          summary(),
          summary({ id: 'op_1', kind: 'resolve' }),
          summary({ id: 'op_2', kind: 'unpark' }),
          summary({ id: 'op_3', kind: 'reject' }),
        ],
      }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert
      .dom('[data-test-fix-label]')
      .hasText('Rejected · the fix was dropped');
    assert.deepEqual(offered(), ['Reconsider']);
  });

  test('a close that was refused did not close anything', async function (assert) {
    board().conversations = [
      thread({
        key: 'k1',
        state: 'done',
        operations: [
          summary({ id: 'op_1', kind: 'approve' }),
          summary({ id: 'op_2', kind: 'resolve', state: 'refused' }),
        ],
      }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-fix-label]').hasText('Accepted · pushed');
    assert.deepEqual(offered(), ['Bring back']);
  });

  test('a session is its own phase', async function (assert) {
    board().conversations = [board().threadIn('session')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.dom('[data-test-fix-label]').hasText('Session open');
  });

  test('a verb waiting for the board holds a thread nobody is working on', async function (assert) {
    const asked = summary({ id: 'op_1', kind: 'reply', state: 'pending' });

    await each(
      board(),
      [
        ['ready', thread({ operations: [asked] })],
        ['waiting', thread({ state: 'waiting', operations: [asked] })],
      ],
      (state) => {
        assert.deepEqual(offered(), [], state);
        assert.dom('[data-test-notes]').hasText('replying…', state);
      },
    );
  });

  test('a run in flight is the state itself, not something in the way', async function (assert) {
    board().conversations = [board().threadIn('working')];

    await visit('/pr/o/r/7/conversations/PRRT_a');

    assert.deepEqual(offered(), ['Stop', 'Defer']);
  });
});
