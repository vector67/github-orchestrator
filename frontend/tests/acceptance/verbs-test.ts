import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  fillIn,
  triggerEvent,
  visit,
  waitFor,
} from '@ember/test-helpers';
import type { Conversation } from 'frontend/data/api';
import {
  operation,
  setupFakeBoard,
  summary,
  type FakeBoard,
  type Phase,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

const POSTING = '#panel-actions [data-test-posting]';

function offered(): readonly string[] {
  return [...document.querySelectorAll('[data-test-decision]')].map((button) =>
    [...button.childNodes]
      .filter((one) => one.nodeName !== 'KBD')
      .map((one) => one.textContent)
      .join('')
      .trim(),
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
      'Resolve',
      'Mark done',
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
      'Resolve',
      'Mark done',
    ]);
  });

  test('each dialog a proposal opens submits with its opener’s words', async function (assert) {
    await open(board(), 'proposed');

    for (const [decision, label] of [
      ['defer', 'Defer'],
      ['reject', 'Reject'],
      ['resolve', 'Resolve'],
    ] as const) {
      await click(`[data-test-decision="${decision}"]`);
      assert.dom('[data-test-dialog-submit]').hasText(label, decision);
      await click('[data-test-dialog-cancel]');
    }
  });

  test('a declined run is argued with in its own words', async function (assert) {
    await open(board(), 'declined');

    assert.deepEqual(offered(), ['Send back for rework', 'Resolve', 'Defer']);
    assert
      .dom('[data-test-decision="rework"]')
      .hasAttribute('data-weight', 'secondary');
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('data-weight', 'secondary');
  });

  test('a waiting thread stops waiting and a deferred one is brought back', async function (assert) {
    await each(
      board(),
      [
        ['waiting', ['Stop waiting', 'Mark done', 'Resolve', 'Defer']],
        ['deferred', ['Bring back', 'Resolve', 'Mark done']],
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

  test('s asks for an optional reply, then resolves the thread on GitHub after it', async function (assert) {
    await open(board(), 'proposed');

    await triggerEvent(document, 'keydown', { key: 's' });

    assert.deepEqual(board().posted, [], 'nothing has reached GitHub yet');
    await fillIn('[data-test-dialog-body]', 'Not needed after all.');
    assert.dom('[data-test-dialog-submit]').hasText('Resolve');

    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'Not needed after all.',
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
      resolve: true,
    });
  });

  test('a dialog offers no agent’s words where the agent said nothing', async function (assert) {
    await open(board(), 'proposed');

    await triggerEvent(document, 'keydown', { key: 's' });

    assert.dom('[data-test-agent-words]').doesNotExist();
  });

  test('h marks a waiting thread done on the board at once, sending GitHub nothing', async function (assert) {
    await open(board(), 'waiting');

    await triggerEvent(document, 'keydown', { key: 'h' });

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted[0]!.verb, 'mark-done');
    assert.deepEqual(board().posted[0]!.body, {});
  });

  test('x asks before it stops the agent, and stops it once confirmed', async function (assert) {
    await open(board(), 'working');

    await triggerEvent(document, 'keydown', { key: 'x' });

    assert.deepEqual(board().posted, [], 'nothing stopped yet');
    assert
      .dom('[data-test-are-you-sure-question]')
      .hasText('Stop the agent on this comment?');

    await click('[data-test-are-you-sure-submit]');

    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['stop'],
    );
  });

  test('a done review thread GitHub shows resolved is unresolved on GitHub', async function (assert) {
    board().conversations = [
      board().threadIn('resolved', { key: 'k1', github_resolved: true }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.deepEqual(offered(), ['Unresolve on GitHub']);
    assert
      .dom('[data-test-decision="unpark"]')
      .hasAttribute('title', /unresolves this thread on GitHub/);
    await click('[data-test-decision="unpark"]');
    assert.strictEqual(board().posted[0]!.verb, 'unpark');
    assert.deepEqual(board().posted[0]!.body, {});
  });

  test('a done thread GitHub does not show resolved, or that is no review thread, is brought back', async function (assert) {
    board().conversations = [
      board().threadIn('resolved', { key: 'k1', github_resolved: false }),
      board().threadIn('resolved', {
        key: 'k2',
        kind: 'issue',
        github_resolved: true,
      }),
    ];

    await visit('/pr/o/r/7/conversations/k1');
    assert.deepEqual(offered(), ['Bring back'], 'unresolved on GitHub');
    await visit('/pr/o/r/7/conversations/k2');
    assert.deepEqual(offered(), ['Bring back'], 'an issue comment');
  });
});

module('Acceptance | verbs | the reviewer board', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().actAs('reviewer');
  });

  test('an answered thread is resolved, argued with, moved or put off', async function (assert) {
    await open(board(), 'answered');

    assert.deepEqual(offered(), ['Resolve', 'Not fixed', 'Move', 'Defer']);
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('data-weight', 'primary');
    assert
      .dom('[data-test-decision="resolve"]')
      .hasAttribute('title', /resolves this thread on GitHub/);
  });

  test('each dialog an answered thread opens submits with its opener’s words', async function (assert) {
    await open(board(), 'answered');

    for (const [decision, label] of [
      ['not-fixed', 'Not fixed'],
      ['place', 'Move'],
      ['defer', 'Defer'],
    ] as const) {
      await click(`[data-test-decision="${decision}"]`);
      assert.dom('[data-test-dialog-submit]').hasText(label, decision);
      await click('[data-test-dialog-cancel]');
    }
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

  test('a parked thread is resolved, put off or moved, and a deferred one brought back', async function (assert) {
    await each(
      board(),
      [
        ['waiting', ['Resolve', 'Mark done', 'Defer', 'Move']],
        ['deferred', ['Bring back', 'Resolve', 'Mark done']],
      ] as const,
      ([phase]) => phase,
      ([phase, labels]) => {
        assert.deepEqual(offered(), labels, phase);
        assert
          .dom('[data-test-decision="resolve"]')
          .hasAttribute('data-weight', 'secondary', phase);
      },
    );
  });

  test('a resolved thread GitHub does not show resolved is brought back', async function (assert) {
    board().conversations = [
      board().threadIn('resolved', { key: 'k1', github_resolved: false }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.deepEqual(offered(), ['Bring back']);
  });

  test('a review thread GitHub shows resolved is unresolved on GitHub', async function (assert) {
    board().conversations = [
      board().threadIn('resolved', { key: 'k1', github_resolved: true }),
    ];

    await visit('/pr/o/r/7/conversations/k1');

    assert.deepEqual(offered(), ['Unresolve on GitHub']);
    assert
      .dom('[data-test-decision="unpark"]')
      .hasAttribute('title', /unresolves this thread on GitHub/);
  });

  test('an answered thread offers Reply to its author by the comment it answers', async function (assert) {
    await open(board(), 'answered');

    assert.dom('#panel-talk [data-test-reply-open]').hasText('Reply to Anna');
  });
});

module('Acceptance | verbs | a draft', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('Post now posts the draft at once, with no dialog', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'draft');

    assert
      .dom('[data-test-decision="post-now"]')
      .doesNotHaveAttribute('data-opens-dialog');
    await click('[data-test-decision="post-now"]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['post-now'],
    );
  });

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

  test('a draft being posted shows Posting to GitHub… in place of its buttons', async function (assert) {
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
    assert.dom(POSTING).hasText('Posting to GitHub…');
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
    await triggerEvent(document, 'keydown', { key: 'e' });
    await triggerEvent(document, 'keydown', { key: 'd' });
    await visit('/pr/o/r/7/conversations/k1');
    await triggerEvent(document, 'keydown', { key: 'l' });
    await visit('/pr/o/r/7/conversations/k0');
    await triggerEvent(document, 'keydown', { key: 'G' });

    assert.deepEqual(
      board().posted.map((one) => one.verb),
      ['enrol', 'discard', 'withdraw-from-review', 'post-now'],
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
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="withdraw-from-review"]');

    assert.deepEqual(
      board().posted.map((one) => [one.url, one.body]),
      [
        ['/pr/o/r/7/api/conversations/k0/operations:enrol', {}],
        ['/pr/o/r/7/api/conversations/k0/operations:discard', {}],
        ['/pr/o/r/7/api/conversations/k0/operations:post-now', {}],
        ['/pr/o/r/7/api/conversations/k1/operations:withdraw-from-review', {}],
      ],
    );
  });
});

module('Acceptance | verbs | posting to GitHub', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  test('Post now shows Posting to GitHub… in place of the buttons until GitHub has the comment, then the waiting card’s buttons', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'draft');
    const release = board().hold(/operations:post-now$/);

    const posting = click('[data-test-decision="post-now"]');
    await waitFor(POSTING);

    assert.dom(POSTING).hasText('Posting to GitHub…');
    assert.dom('#panel-actions').hasAttribute('data-pending');
    assert.deepEqual(offered(), []);

    release();
    await posting;

    assert
      .dom(POSTING)
      .hasText('Posting to GitHub…', 'the board has it, GitHub not yet');
    assert.deepEqual(offered(), []);

    board().conversations = [board().threadIn('waiting', { key: 'k1' })];
    await clock().tick(LIST);

    assert.dom(POSTING).doesNotExist();
    assert.deepEqual(offered(), ['Resolve', 'Mark done', 'Defer', 'Move']);
  });

  test('a reply posted with Not fixed shows Posting to GitHub… in place of the buttons', async function (assert) {
    board().actAs('reviewer');
    await open(board(), 'answered');
    await click('[data-test-decision="not-fixed"]');
    await fillIn('[data-test-dialog-body]', 'Not fixed — still in the loop.');
    const release = board().hold(/operations:reply$/);

    const posting = click('[data-test-dialog-submit]');
    await waitFor(POSTING);

    assert.dom(POSTING).hasText('Posting to GitHub…');
    assert.deepEqual(offered(), []);

    release();
    await posting;
  });

  test('Reply and mark done shows Posting to GitHub… in place of the buttons until GitHub has the reply', async function (assert) {
    const answered = board().threadIn('answered', { key: 'k1', kind: 'issue' });
    board().conversations = [answered];
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reply-and-mark-done"]');
    await fillIn('[data-test-dialog-body]', 'Thanks, done in the next commit.');
    const release = board().hold(/operations:mark-done$/);

    const posting = click('[data-test-dialog-submit]');
    await waitFor(POSTING);

    assert.dom(POSTING).hasText('Posting to GitHub…');
    assert.deepEqual(offered(), []);

    release();
    await posting;
    board().conversations = [
      {
        ...answered,
        operations: [
          ...answered.operations,
          summary({ id: 'op_1', kind: 'resolve', state: 'pending' }),
        ],
      },
    ];
    await clock().tick(LIST);

    assert
      .dom(POSTING)
      .hasText('Posting to GitHub…', 'the board has it, GitHub not yet');
  });
});
