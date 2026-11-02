import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, find, findAll, visit } from '@ember/test-helpers';
import {
  added,
  comment,
  diffOf,
  operation,
  prCommit,
  prHistory,
  proposal,
  setupFakeBoard,
  summary,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { stubGitHub } from 'frontend/tests/helpers/browser';

const KEY = 'PRRT_ask';

function seed(board: FakeBoard) {
  const asking = board.threadIn('asking', { key: KEY });
  board.conversations = [asking];
  board.comments[KEY] = [comment({ body: 'use one helper for both bounds' })];
  board.operations[KEY] = [
    operation({
      id: asking.operations.at(-1)!.id,
      conversation: KEY,
      kind: 'rework',
      state: 'applied',
      plan: [
        { text: 'add the helper', file: 'tests/test_edit.py', done: true },
        { text: 'run the tests and commit', file: null, done: false },
      ],
    }),
  ];
  const last = asking.question!.last_proposal!;
  board.diffs['last'] = {
    ...diffOf('tests/test_edit.py', added(12, 'def helper():')),
    base: last.base,
    head: last.head,
  };
  board.worktreeDiffs[KEY] = {
    ...diffOf('tests/test_edit.py', added(13, '    return clock_timestamp()')),
    base: last.head,
    head: last.head,
  };
  return asking;
}

function texts(selector: string): string[] {
  return findAll(selector).map((one) =>
    (one.textContent ?? '').replace(/\s+/g, ' ').trim(),
  );
}

module('Acceptance | agent question', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('the queue row says an agent is asking', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-meta]').hasText('Agent question');
  });

  test('a question waits under Ready for you', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      findAll('[data-test-heading]').map((one) =>
        one.getAttribute('data-test-heading'),
      ),
      ['ready'],
    );
  });

  test('the next move is the agent question', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.strictEqual(
      find('.vb')?.getAttribute('title'),
      'Your move: an agent is asking you a question',
    );
  });

  test('the card puts the question, its ways out, why it stopped and the plan where the proposal goes', async function (assert) {
    const asking = seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-question-heading]')
      .hasText('Agent question · stopped after 1 of 2 steps');
    assert.dom('[data-test-question-text]').hasText(asking.question!.text);
    assert.deepEqual(
      texts('[data-test-question-option]'),
      asking.question!.options,
    );
    assert
      .dom('[data-test-question-context]')
      .includesText(asking.question!.context);
    assert.dom('[data-test-plan-step]').exists({ count: 2 });
    assert.dom('[data-test-confidence]').doesNotExist();
  });

  test('a question offers an answer in a session and a drop, and nothing to approve', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('[data-test-decision]'), [
      'Answer in a session o',
      'Drop… ⇧D',
    ]);
  });

  test('answering opens a session on the thread', async function (assert) {
    seed(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="answer"]');

    assert.strictEqual(board().posted.at(-1)?.verb, 'start-session');
  });

  test('dropping back to the last proposal drops the question', async function (assert) {
    seed(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="drop"]');
    assert.deepEqual(texts('[data-test-outcome-label]'), [
      'Back to the last proposal',
      'Defer',
      'Reject the thread',
    ]);
    assert
      .dom('[data-test-outcome-steps="proposal"]')
      .hasText('asking → proposed');
    await click('[data-test-outcome="proposal"]');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted.at(-1)?.verb, 'drop-question');
  });

  test('dropping into a deferral asks when it comes back', async function (assert) {
    seed(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="drop"]');
    await click('[data-test-outcome="later"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-wake]').exists();
    assert.strictEqual(board().posted.length, 0);
  });

  test('dropping by rejecting the thread asks for the reply first', async function (assert) {
    seed(board());
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="drop"]');
    await click('[data-test-outcome="reject"]');
    await click('[data-test-dialog-submit]');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted.at(-1)?.verb, 'reject');
  });

  test('a first run that asked has no proposal to go back to', async function (assert) {
    const asking = seed(board());
    board().conversations = [
      { ...asking, question: { ...asking.question!, last_proposal: null } },
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="drop"]');

    assert
      .dom('[data-test-outcome-steps="proposal"]')
      .hasText('asking → failed');
    assert.dom('[data-test-fold-title]').hasText('Changes so far');
  });

  test('the diff holds the last proposal folded and everything since open', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('[data-test-fold-title]'), [
      'Since the last proposal',
    ]);
    assert.dom('[data-test-last-proposal]').doesNotHaveAttribute('open');
    assert
      .dom('[data-test-frame] [data-test-diff]')
      .includesText('return clock_timestamp()');
  });

  test('a worktree with nothing past the last proposal says so', async function (assert) {
    seed(board());
    board().worktreeDiffs[KEY] = { ...board().worktreeDiffs[KEY]!, files: [] };

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-frame] [data-test-diff]').hasText('No changes');
  });

  test('a branch that moved since the question says so', async function (assert) {
    const asking = seed(board());
    const head = asking.question!.head!;
    board().pullRequest = { ...board().pullRequest, head_sha: 'feed123' };
    board().commits = prHistory('ba5e000', [
      prCommit(head, 'ba5e000', 'what the agent saw'),
      prCommit('abc1234', head, 'pushed since'),
      prCommit('feed123', 'abc1234', 'pushed since too'),
    ]);

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-question-moved]')
      .hasText('PR moved since the question · 2 new commits');
  });

  module('while you answer in a session', function (inner) {
    const github = stubGitHub(inner);

    inner.beforeEach(function () {
      localStorage.removeItem('answer-replies-seen');
    });

    function answering(board: FakeBoard) {
      const asking = seed(board);
      board.conversations = [
        {
          ...asking,
          state: 'in-session',
          operations: [
            ...asking.operations,
            summary({
              id: `${KEY}.9`,
              kind: 'start-session',
              state: 'running',
              requested_at: '2026-09-12T12:00:00Z',
            }),
          ],
          comments: [
            ...asking.comments,
            {
              id: 3,
              author: 'anna',
              created_at: '2026-09-12T12:05:00Z',
              review_state: null,
            },
          ],
        },
      ];
      board.comments[KEY] = [
        comment({ body: 'use one helper for both bounds' }),
        comment({
          id: 3,
          author: 'anna',
          created_at: '2026-09-12T12:05:00Z',
          body: 'Stamping in the entity would sidestep it.',
          review_state: null,
        }),
      ];
    }

    test('a reply on the thread you are answering says so until you open it', async function (assert) {
      answering(board());

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-answer-reply]')
        .includesText("anna replied to the thread you're answering");
      await click('[data-test-see-reply]');
      assert
        .dom('[data-test-reply-dialog] [data-test-entry]')
        .exists({ count: 2 });
      assert
        .dom('[data-test-reply-dialog] [data-test-entry][data-marked]')
        .includesText('Stamping in the entity would sidestep it.');
      await click('[data-test-copy-reply]');
      assert.deepEqual(github().copied, [
        'Stamping in the entity would sidestep it.',
      ]);
      await click('[data-test-close-reply]');
      assert.dom('[data-test-answer-reply]').doesNotExist();
    });

    test('a dismissed reply toast stays dismissed', async function (assert) {
      answering(board());
      await visit(`/pr/o/r/7/conversations/${KEY}`);

      await click('[data-test-dismiss-reply]');

      assert.dom('[data-test-answer-reply]').doesNotExist();
    });

    test('a reply from before the session opened says nothing', async function (assert) {
      answering(board());
      const [shown] = board().conversations;
      board().conversations = [
        {
          ...shown!,
          comments: shown!.comments.map((one) => ({
            ...one,
            created_at: '2026-09-12T11:00:00Z',
          })),
        },
      ];
      board().comments[KEY] = board().comments[KEY]!.map((one) => ({
        ...one,
        created_at: '2026-09-12T11:00:00Z',
      }));

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert.dom('[data-test-answer-reply]').doesNotExist();
    });
  });

  test('a run that stopped without reporting shows its last words, not a question', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: KEY })];
    board().proposals[KEY] = [
      proposal({
        id: `${KEY}.1.proposal`,
        last_words: 'Shall I change production, or widen the bound?',
        tests: 'unverified',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-stopped]').includesText('Stopped without reporting');
    assert
      .dom('[data-test-stopped]')
      .includesText('Shall I change production, or widen the bound?');
    assert.dom('[data-test-question]').doesNotExist();
  });
});
