import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, triggerEvent, visit } from '@ember/test-helpers';
import type { Conversation } from 'frontend/data/api';
import {
  operation,
  setupFakeBoard,
  summary,
  type FakeBoard,
  type Phase,
} from 'frontend/tests/helpers/fake-board';

function offered(): readonly string[] {
  return [...document.querySelectorAll('[data-test-decision]')].map(
    (button) => button.firstChild?.textContent?.trim() ?? '',
  );
}

async function open(
  board: FakeBoard,
  phase: Phase,
  asked?: Conversation['operations'][number],
): Promise<void> {
  const conversation = board.threadIn(phase, { key: 'k1' });
  board.conversations = [
    asked
      ? { ...conversation, operations: [...conversation.operations, asked] }
      : conversation,
  ];
  await visit('/pr/o/r/7/conversations/k1');
}

async function each<T>(
  board: FakeBoard,
  cases: readonly T[],
  phaseOf: (one: T) => Phase,
  check: (one: T) => void,
): Promise<void> {
  const keys = cases.map(() => `case${(drawn += 1)}`);
  board.conversations = cases.map((one, at) =>
    board.threadIn(phaseOf(one), { key: keys[at] }),
  );
  for (const [at, one] of cases.entries()) {
    await visit(`/pr/o/r/7/conversations/${keys[at]}`);
    check(one);
  }
}

let drawn = 0;

module('Acceptance | verbs | the author board', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('a proposal waiting is the whole decision', async function (assert) {
    await open(board(), 'proposed');

    assert.deepEqual(offered(), [
      'Accept',
      'Send back for rework',
      'Defer',
      'Reject',
      'Resolve on GitHub',
      'Steer it yourself',
    ]);
  });

  test('reject is offered only where an agent came back with something', async function (assert) {
    const phases = [
      'queued',
      'working',
      'session',
      'rework',
      'landing',
      'rebasing',
      'declined',
      'waiting',
      'deferred',
      'landed',
    ] as const;

    await each(
      board(),
      phases,
      (phase) => phase,
      (phase) =>
        assert.dom('[data-test-decision="reject"]').doesNotExist(phase),
    );
  });

  test('stop is offered on every thread with work in flight and nowhere else', async function (assert) {
    await each(
      board(),
      [
        ['queued', ['Stop', 'Defer']],
        ['working', ['Stop', 'Defer']],
        ['session', ['Stop', 'Defer']],
        ['rework', ['Stop', 'Defer']],
        ['landing', ['Stop']],
      ] as const,
      ([phase]) => phase,
      ([phase, labels]) => assert.deepEqual(offered(), labels, phase),
    );
    await each(
      board(),
      ['proposed', 'waiting', 'deferred', 'landed'] as const,
      (phase) => phase,
      (phase) => assert.dom('[data-test-decision="stop"]').doesNotExist(phase),
    );
  });

  test('a run that came back with nothing can be tried again', async function (assert) {
    await open(board(), 'failed');

    assert.deepEqual(offered(), [
      'Try again',
      'Send back for rework',
      'Steer it yourself',
      'Defer',
      'Reject',
      'Resolve on GitHub',
    ]);
  });

  test('a declined run is argued with in its own words', async function (assert) {
    await open(board(), 'declined');

    assert.deepEqual(offered(), [
      'Disagree — try a fix anyway',
      'Agreed, resolve the comment',
      'Defer',
    ]);
    assert
      .dom('[data-test-decision="rework"]')
      .hasAttribute('data-weight', 'secondary');
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('data-weight', 'secondary');
  });

  test('a parked thread is brought back', async function (assert) {
    await each(
      board(),
      [
        [
          'waiting',
          ['Bring back to Ready', 'Resolve', 'Resolve on GitHub', 'Defer'],
        ],
        ['deferred', ['Undefer', 'Resolve on GitHub']],
      ] as const,
      ([phase]) => phase,
      ([phase, labels]) => assert.deepEqual(offered(), labels, phase),
    );
  });

  test('a comment you posted with no fix yet has one written on asking', async function (assert) {
    const posted = board().threadIn('waiting', { key: 'k1' });
    for (const state of ['waiting', 'ready'] as const) {
      board().conversations = [{ ...posted, state, operations: [] }];
      await visit('/pr/o/r/7/conversations/k1');

      assert.strictEqual(offered()[0], 'Write a fix', state);
    }

    await click('[data-test-decision="fix"]');

    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['fix'],
    );
  });

  test('a thread with a verb waiting for the board offers nothing more', async function (assert) {
    await open(
      board(),
      'proposed',
      summary({
        id: 'op_000000000001',
        kind: 'resolve',
        state: 'pending',
        attempts: null,
        attempts_allowed: null,
      }),
    );

    assert.deepEqual(offered(), []);
    assert.dom('[data-test-notes]').hasText('resolving…');
  });

  test('every verb says what it does', async function (assert) {
    await open(board(), 'proposed');

    for (const button of document.querySelectorAll('[data-test-decision]')) {
      assert.dom(button).hasAttribute('title', /\w/);
    }
  });

  test('every verb answers to a key of its own', async function (assert) {
    await open(board(), 'proposed');
    const dialogs: [string, string][] = [
      ['a', 'Accept: push'],
      ['f', 'When should this come back to you?'],
      ['R', 'drops the fix'],
      ['o', 'the session you steer'],
      ['s', 'Resolve this comment'],
    ];

    for (const [key, question] of dialogs) {
      await triggerEvent(document, 'keydown', { key });
      assert.dom('[data-test-dialog-question]').includesText(question, key);
      await triggerEvent(document, 'keydown', { key: 'Escape' });
    }
    await triggerEvent(document, 'keydown', { key: 'w' });
    assert.dom('[data-test-rework-dialog]').exists('w');
    await click('[data-test-cancel-rework]');

    assert.deepEqual(board().posted, [], 'every verb asked first');
  });

  test('r, which is Carry on on the Dashboard, rejects nothing on the Board', async function (assert) {
    await open(board(), 'proposed');

    await triggerEvent(document, 'keydown', { key: 'r' });

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.deepEqual(board().posted, []);
  });

  test('resolve on GitHub, ticked, asks for the thread to be resolved there, after the reply typed', async function (assert) {
    await open(board(), 'proposed');

    await triggerEvent(document, 'keydown', { key: 's' });
    await click('[data-test-resolve]');

    assert.deepEqual(board().posted, [], 'nothing has reached GitHub yet');
    assert.dom('[data-test-dialog-submit]').hasText('Resolve on GitHub');

    await fillIn('[data-test-dialog-body]', 'Not needed after all.');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Post reply and resolve on the board and GitHub');

    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'Not needed after all.',
      delete_comment: false,
      resolve: true,
    });
  });

  test('resolve on GitHub opens unticked and resolves the comment on the board alone', async function (assert) {
    await open(board(), 'declined');

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-resolve]').isNotChecked();
    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve, posting nothing to GitHub');

    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
    });
  });

  test('resolve on GitHub opens ticked on a thread a bot opened', async function (assert) {
    board().conversations = [
      board().threadIn('declined', { key: 'k1', author_kind: 'bot' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-dialog-submit]').hasText('Resolve on GitHub');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: true,
    });
  });

  test('agreeing with a declined run can reply in the agent’s words', async function (assert) {
    board().operations['k1'] = [
      operation({
        id: 'k1.1',
        conversation: 'k1',
        state: 'refused',
        reason_code: 'agent-declined',
        reason: 'a question, not an instruction',
      }),
    ];
    await open(board(), 'declined');

    await click('[data-test-decision="resolve"]');
    await click('[data-test-agent-words]');

    assert
      .dom('[data-test-dialog-body]')
      .hasValue('a question, not an instruction');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      reply: 'a question, not an instruction',
      delete_comment: false,
      resolve: false,
    });
  });

  test('a dialog offers no agent’s words where the agent said nothing', async function (assert) {
    await open(board(), 'proposed');

    await triggerEvent(document, 'keydown', { key: 's' });

    assert.dom('[data-test-agent-words]').doesNotExist();
  });

  test('a reply with resolve on GitHub unticked says it resolves on the board', async function (assert) {
    await open(board(), 'declined');

    await click('[data-test-decision="resolve"]');
    await fillIn('[data-test-dialog-body]', 'Not needed after all.');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Post reply and resolve on the board');
  });

  test('a parked thread resolves on the board alone, posting nothing when the box is empty', async function (assert) {
    await open(board(), 'waiting');

    await triggerEvent(document, 'keydown', { key: 'v' });

    assert.dom('[data-test-dialog-question]').hasText('Resolve this comment?');
    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve, posting nothing to GitHub');

    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, { delete_comment: false });
  });

  test('x asks before it stops the agent, and stops it once confirmed', async function (assert) {
    await open(board(), 'working');

    await triggerEvent(document, 'keydown', { key: 'x' });

    assert.deepEqual(board().posted, [], 'nothing stopped yet');
    assert
      .dom('[data-test-dialog-question]')
      .hasText('Stop the agent on this comment?');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['stop'],
    );
  });
});

module('Acceptance | verbs | the reviewer board', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().actAs('reviewer');
  });

  test('an answered thread is resolved, argued with, answered or put off', async function (assert) {
    await open(board(), 'answered');

    assert.deepEqual(offered(), [
      'Resolve',
      'Not fixed',
      'Reply',
      'Defer until next push',
    ]);
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('data-weight', 'primary');
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('title', /thumbs-up on the newest reply/);
  });

  test('no agent verb reaches a reviewer', async function (assert) {
    const agents = [
      'approve',
      'rework',
      'retry',
      'fix',
      'reject',
      'stop',
      'start-session',
    ];

    await each(
      board(),
      ['answered', 'waiting', 'deferred', 'resolved'] as const,
      (phase) => phase,
      (phase) => {
        for (const verb of agents) {
          assert
            .dom(`[data-test-decision="${verb}"]`)
            .doesNotExist(`${verb} on ${phase}`);
        }
      },
    );
  });

  test('a parked thread is resolved, put off or answered, and a deferred one brought back', async function (assert) {
    await each(
      board(),
      [
        ['waiting', ['Resolve', 'Defer until next push', 'Reply']],
        ['deferred', ['Undefer', 'Resolve']],
      ] as const,
      ([phase]) => phase,
      ([phase, labels]) => {
        assert.deepEqual(offered(), labels, phase);
        assert
          .dom('[data-test-decision="resolve"]')
          .hasAttribute('data-weight', 'ghost', phase);
      },
    );
  });

  test('a resolved thread is reopened', async function (assert) {
    await open(board(), 'resolved');

    assert.deepEqual(offered(), ['Reopen']);
  });
});

module('Acceptance | verbs | a draft', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  for (const role of ['author', 'reviewer'] as const) {
    test(`a draft on the ${role}'s board is added, posted on its own, thrown away or brought back`, async function (assert) {
      board().actAs(role);

      await each(
        board(),
        [
          ['draft', ['Add to review', 'Post now', 'Discard']],
          ['enrolled', ['Leave out of review']],
          ['discarded', ['Bring back']],
        ] as const,
        ([phase]) => phase,
        ([phase, labels]) => assert.deepEqual(offered(), labels, phase),
      );
    });
  }

  test('a draft being posted offers nothing more', async function (assert) {
    board().actAs('reviewer');

    await open(
      board(),
      'draft',
      summary({
        id: 'op_000000000002',
        kind: 'post-now',
        state: 'pending',
        attempts: null,
        attempts_allowed: null,
      }),
    );

    assert.deepEqual(offered(), []);
  });

  test('every draft verb says what it does and answers to a key of its own', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('draft', { key: 'k0' }),
      board().threadIn('enrolled', { key: 'k1' }),
    ];
    for (const key of ['k1', 'k0']) {
      await visit(`/pr/o/r/7/conversations/${key}`);
      for (const button of document.querySelectorAll('[data-test-decision]')) {
        assert.dom(button).hasAttribute('title', /\w/);
      }
    }

    await triggerEvent(document, 'keydown', { key: 'g' });
    assert
      .dom('[data-test-dialog]')
      .doesNotExist('g is the Git palette on the Dashboard, not Post now');
    await triggerEvent(document, 'keydown', { key: 'G' });
    assert
      .dom('[data-test-dialog-question]')
      .hasText('Post this comment to GitHub now, on its own?');
    await triggerEvent(document, 'keydown', { key: 'Escape' });
    await triggerEvent(document, 'keydown', { key: 'e' });
    await triggerEvent(document, 'keydown', { key: 'd' });
    await visit('/pr/o/r/7/conversations/k1');
    await triggerEvent(document, 'keydown', { key: 'l' });

    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['enrol', 'discard', 'withdraw-from-review'],
    );
  });

  test('each draft verb is its own custom method with nothing in the body', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('draft', { key: 'k0' }),
      board().threadIn('enrolled', { key: 'k1' }),
    ];

    await visit('/pr/o/r/7/conversations/k0');
    await click('[data-test-decision="enrol"]');
    await click('[data-test-decision="discard"]');
    await click('[data-test-decision="post-now"]');
    await click('[data-test-dialog-submit]');
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="withdraw-from-review"]');

    assert.deepEqual(
      board().posted.map((one) => [one.url, one.body]),
      [
        ['/api/conversations/k0/operations:enrol', {}],
        ['/api/conversations/k0/operations:discard', {}],
        ['/api/conversations/k0/operations:post-now', {}],
        ['/api/conversations/k1/operations:withdraw-from-review', {}],
      ],
    );
  });
});
