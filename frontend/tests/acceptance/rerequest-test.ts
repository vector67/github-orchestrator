import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, find, triggerEvent, visit } from '@ember/test-helpers';
import type { Conversation, PrFacts } from 'frontend/data/api';
import {
  comment,
  dashboard,
  heldPr,
  operation,
  proposal,
  setupFakeBoard,
  summary,
  thread,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';
import type { Phase } from 'frontend/tests/helpers/fake-board';

const OPENED_AT = '2026-09-12T10:00:00Z';

const CAROL_COMMENTED: Partial<PrFacts> = {
  is_author: true,
  review_decision: 'review-required',
  commented_by: ['carol'],
  changes_requested_by: [],
  pending_reviewers: [],
};

module('Acceptance | re-request review', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function serve(over: DashboardOver = { facts: CAROL_COMMENTED }): void {
    board().held = [heldPr({ dashboard: over })];
    board().manager = dashboard(over);
  }

  function carols(
    phase: Phase,
    over: Partial<Conversation> = {},
  ): Conversation {
    return board().threadIn(phase, {
      key: 'PRRT_c1',
      opened_by: 'carol',
      opened_at: OPENED_AT,
      author_kind: 'human',
      comments: [
        {
          id: 1,
          author: 'carol',
          created_at: OPENED_AT,
          review_state: 'COMMENTED',
        },
      ],
      ...over,
    });
  }

  function verbs(): string[] {
    return board().posted.map((one) => one.verb);
  }

  hooks.beforeEach(function () {
    serve();
  });

  test("Mark done on carol's last open thread opens the prompt and posts nothing", async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    await click('[data-test-decision="mark-done"]');

    assert
      .dom('[data-test-rerequest-prompt]')
      .hasAttribute('role', 'alertdialog');
    assert
      .dom('[data-test-rerequest-kicker]')
      .hasText('Last comment from carol');
    assert
      .dom('[data-test-rerequest-question]')
      .hasText("Re-request carol's review of #7?");
    assert.deepEqual(verbs(), []);
  });

  test('"Mark done and re-request" posts mark-done, then queues the re-request for carol', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');

    assert
      .dom('[data-test-rerequest-and]')
      .hasText('Mark done and re-request r');
    await click('[data-test-rerequest-and]');

    assert.deepEqual(verbs(), ['mark-done', 'rerequest-review']);
    assert.strictEqual(
      board().posted[1]!.url,
      '/pr/o/r/7/api/manager:rerequest-review',
    );
    assert.deepEqual(board().posted[1]!.body, { reviewer: 'carol' });
    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
  });

  test('"Mark done only" posts mark-done alone, and the next move asks to re-request carol', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');
    board().conversations = [
      carols('proposed', { state: 'done', record_state: 'resolved' }),
    ];

    assert.dom('[data-test-rerequest-only]').hasText('Mark done only o');
    await click('[data-test-rerequest-only]');

    assert.deepEqual(verbs(), ['mark-done']);
    await visit('/pr/o/r/7/dashboard');
    assert
      .dom('[data-test-your-move] .vb')
      .hasAttribute('title', 'Re-request review from carol');
  });

  test('× posts nothing and leaves the thread open', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');

    await click('[data-test-rerequest-cancel]');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.dom('[data-test-decision="mark-done"]').isEnabled();
  });

  test('Escape posts nothing, and r and o pick the buttons', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-prompt]').doesNotExist();

    await click('[data-test-decision="mark-done"]');
    await triggerEvent(document, 'keydown', { key: 'o' });

    assert.deepEqual(verbs(), ['mark-done']);
  });

  const DIALOG_FIRST: [string, Partial<Conversation>, string, unknown][] = [
    [
      'approve',
      {},
      'Accept and re-request',
      { reply: 'Fixed.', delete_comment: false, resolve: false },
    ],
    [
      'resolve',
      {},
      'Resolve and re-request',
      { reply: 'Fixed.', delete_comment: false, resolve: true },
    ],
    [
      'reject',
      {},
      'Reject and re-request',
      { reply: 'Fixed.', delete_comment: false },
    ],
    ['defer', {}, 'Defer and re-request', { until: 'manual' }],
    [
      'reply-and-mark-done',
      { kind: 'issue' },
      'Reply and mark done and re-request',
      { reply: 'Fixed.' },
    ],
  ];

  for (const [decision, over, label, body] of DIALOG_FIRST) {
    test(`${decision} shows its own dialog, then the prompt, and posts what was gathered`, async function (assert) {
      board().conversations = [carols('proposed', over)];
      await visit('/pr/o/r/7/conversations/PRRT_c1');
      await click(`[data-test-decision="${decision}"]`);
      if (find('[data-test-dialog-body]')) {
        await fillIn('[data-test-dialog-body]', 'Fixed.');
      }

      await click('[data-test-dialog-submit]');

      assert.dom('[data-test-dialog]').doesNotExist();
      assert.dom('[data-test-rerequest-prompt]').exists();
      assert.deepEqual(verbs(), []);

      assert.dom('[data-test-rerequest-and]').hasText(`${label} r`);
      await click('[data-test-rerequest-and]');

      assert.deepEqual(verbs(), [
        decision === 'reply-and-mark-done' ? 'mark-done' : decision,
        'rerequest-review',
      ]);
      assert.deepEqual(board().posted[0]!.body, body);
    });
  }

  test('× on the prompt after a dialog posts nothing and keeps the words typed into it', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="resolve"]');
    await fillIn('[data-test-dialog-body]', 'Fixed.');
    await click('[data-test-dialog-submit]');

    await click('[data-test-rerequest-cancel]');

    assert.deepEqual(verbs(), []);
    await click('[data-test-decision="resolve"]');
    assert.dom('[data-test-dialog-body]').hasValue('Fixed.');
  });

  test('Confirm on an assumed-done thread opens the prompt and posts confirm', async function (assert) {
    board().conversations = [carols('assumed-done')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    await click('[data-test-decision="confirm"]');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-and]').hasText('Confirm and re-request r');
    await click('[data-test-rerequest-and]');
    assert.deepEqual(verbs(), ['confirm', 'rerequest-review']);
  });

  async function moveTo(to: string): Promise<void> {
    board().conversations = [carols('assumed-done')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="place"]');
    await click(`[data-test-outcome="${to}"]`);
    await click('[data-test-dialog-submit]');
  }

  test('Move to Their move opens the prompt, then posts place', async function (assert) {
    await moveTo('waiting');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-and]').hasText('Move and re-request r');
    await click('[data-test-rerequest-only]');

    assert.deepEqual(verbs(), ['place']);
    assert.deepEqual(board().posted[0]!.body, { to: 'waiting' });
  });

  for (const to of ['queued', 'ready']) {
    test(`Move to ${to} posts at once with no prompt`, async function (assert) {
      await moveTo(to);

      assert.dom('[data-test-rerequest-prompt]').doesNotExist();
      assert.deepEqual(verbs(), ['place']);
      assert.deepEqual(board().posted[0]!.body, { to });
    });
  }

  test('a refused decision queues nothing', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');
    board().refusal = {
      status: 412,
      code: 'precondition-failed',
      detail: 'thread PRRT_c1 has moved',
    };

    await click('[data-test-rerequest-and]');

    assert.deepEqual(verbs(), ['mark-done']);
  });

  const NO_PROMPT: [string, DashboardOver, () => Conversation[]][] = [
    [
      'not the last open thread from carol',
      { facts: CAROL_COMMENTED },
      () => [
        carols('proposed'),
        carols('proposed', { key: 'PRRT_c2', github_node_id: 'PRRT_c2' }),
      ],
    ],
    [
      'GitHub lists carol as pending',
      { facts: { ...CAROL_COMMENTED, pending_reviewers: ['carol'] } },
      () => [carols('proposed')],
    ],
    [
      'carol approved',
      {
        facts: {
          ...CAROL_COMMENTED,
          commented_by: [],
          review_decision: 'approved',
        },
      },
      () => [carols('proposed')],
    ],
    [
      'a bot',
      { facts: CAROL_COMMENTED },
      () => [carols('proposed', { author_kind: 'bot' })],
    ],
    [
      'someone else’s pull request',
      { facts: { ...CAROL_COMMENTED, is_author: false } },
      () => [carols('waiting')],
    ],
  ];

  for (const [name, over, conversations] of NO_PROMPT) {
    test(`Mark done posts at once with no prompt: ${name}`, async function (assert) {
      serve(over);
      board().conversations = conversations();
      await visit('/pr/o/r/7/conversations/PRRT_c1');

      await click('[data-test-decision="mark-done"]');

      assert.dom('[data-test-rerequest-prompt]').doesNotExist();
      assert.deepEqual(verbs(), ['mark-done']);
    });
  }

  test('Mark done carries the window glyph where it opens the prompt', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    assert
      .dom('[data-test-decision="mark-done"]')
      .hasAttribute('data-opens-dialog');
  });

  test('Mark done carries no window glyph where another thread from carol is open', async function (assert) {
    board().conversations = NO_PROMPT[0]![2]();
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    assert
      .dom('[data-test-decision="mark-done"]')
      .doesNotHaveAttribute('data-opens-dialog');
  });

  test('the r key posts the decision and queues the re-request', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');

    await triggerEvent(document, 'keydown', { key: 'r' });

    assert.deepEqual(verbs(), ['mark-done', 'rerequest-review']);
  });

  async function replied(words: string): Promise<void> {
    await click('[data-test-reply-open]');
    await fillIn('[data-test-reply]', words);
    await click('[data-test-reply-send]');
  }

  test('a plain Reply on a thread waiting on you opens the prompt and sends nothing yet', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    await replied('Fixed in the next push.');

    assert.dom('[data-test-rerequest-prompt]').exists();
    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-and]').hasText('Reply and re-request r');
  });

  test('"Reply and re-request" posts the reply, then queues the re-request', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await replied('Fixed in the next push.');

    await click('[data-test-rerequest-and]');

    assert.deepEqual(verbs(), ['reply', 'rerequest-review']);
    assert.deepEqual(board().posted[0]!.body, {
      body: 'Fixed in the next push.',
    });
    assert.deepEqual(board().posted[1]!.body, { reviewer: 'carol' });
  });

  test('"Reply only" posts the reply alone', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await replied('Fixed in the next push.');

    await click('[data-test-rerequest-only]');

    assert.deepEqual(verbs(), ['reply']);
  });

  test('× on a Reply sends nothing and leaves the words in the box', async function (assert) {
    board().conversations = [carols('proposed')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await replied('Fixed in the next push.');

    await click('[data-test-rerequest-cancel]');

    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.dom('[data-test-reply]').hasValue('Fixed in the next push.');
  });

  test('a Reply on a thread already Their move posts at once', async function (assert) {
    board().conversations = [carols('waiting')];
    await visit('/pr/o/r/7/conversations/PRRT_c1');

    await replied('One more thing.');

    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.deepEqual(verbs(), ['reply']);
  });

  const LATER = '2026-09-13T10:00:00Z';

  function closed(key: string, over: Partial<Conversation>): Conversation {
    return thread({
      key,
      github_node_id: key,
      state: 'done',
      record_state: 'resolved',
      opened_by: 'carol',
      opened_at: OPENED_AT,
      comments: [
        {
          id: 1,
          author: 'carol',
          created_at: OPENED_AT,
          review_state: 'COMMENTED',
        },
      ],
      ...over,
    });
  }

  const PUSHED = closed('PRRT_c2', {
    operations: [
      summary({
        id: 'PRRT_c2.1',
        kind: 'approve',
        state: 'applied',
        lands: 'commit',
      }),
    ],
  });

  const REPLIED = closed('PRRT_c3', {
    github_resolved: true,
    comments: [
      { id: 1, author: 'carol', created_at: OPENED_AT, review_state: null },
      { id: 2, author: 'dave', created_at: LATER, review_state: null },
    ],
  });

  const RESOLVED = closed('PRRT_c4', { github_resolved: true });

  const REJECTED = closed('PRRT_c5', { record_state: 'rejected' });

  const DEFERRED = closed('PRRT_c6', {
    state: 'deferred',
    record_state: 'deferred',
  });

  async function markedDone(others: Conversation[]): Promise<void> {
    board().conversations = [carols('proposed'), ...others];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');
  }

  test('the badge reads Commented for a commented review', async function (assert) {
    await markedDone([]);

    assert.dom('[data-test-rerequest-badge]').hasText('Commented');
  });

  test('the badge reads Changes requested for a change request', async function (assert) {
    serve({
      facts: {
        ...CAROL_COMMENTED,
        commented_by: [],
        changes_requested_by: ['carol'],
      },
    });
    await markedDone([]);

    assert.dom('[data-test-rerequest-badge]').hasText('Changes requested');
  });

  test('the summary line counts the closing comment with the rest of the round, each once', async function (assert) {
    await markedDone([PUSHED, REPLIED, RESOLVED, REJECTED, DEFERRED]);

    assert
      .dom('[data-test-rerequest-summary]')
      .hasText(
        'This is the last one open: 1 pushed, 1 replied, 1 resolved, 1 marked done, 1 rejected, 1 deferred',
      );
  });

  test('the summary line leaves out zero counts', async function (assert) {
    await markedDone([PUSHED, closed('PRRT_c7', {})]);

    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('This is the last one open: 1 pushed, 2 marked done');
  });

  test('the flag line names rejected comments and those with no reply and no push', async function (assert) {
    await markedDone([PUSHED, REPLIED, RESOLVED, REJECTED, DEFERRED]);

    assert
      .dom('[data-test-rerequest-flag]')
      .hasText(
        'You rejected 1 comment, and 3 have no reply and no push. Open the list to see them before carol does.',
      );
  });

  test('the flag line stands on rejections alone', async function (assert) {
    board().conversations = [
      carols('proposed'),
      REJECTED,
      closed('PRRT_c7', { record_state: 'rejected' }),
    ];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'Not this time.');
    await click('[data-test-dialog-submit]');

    assert
      .dom('[data-test-rerequest-flag]')
      .hasText(
        'You rejected 3 comments. Open the list to see them before carol does.',
      );
  });

  test('the flag line stands on comments with no reply and no push alone', async function (assert) {
    await markedDone([PUSHED]);

    assert
      .dom('[data-test-rerequest-flag]')
      .hasText(
        '1 comment has no reply and no push. Open the list to see them before carol does.',
      );
  });

  test('no flag line when every comment was replied to or pushed', async function (assert) {
    board().conversations = [carols('proposed'), PUSHED, REPLIED];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="resolve"]');
    await fillIn('[data-test-dialog-body]', 'Done, thanks.');
    await click('[data-test-dialog-submit]');

    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('This is the last one open: 1 pushed, 2 replied');
    assert.dom('[data-test-rerequest-flag]').doesNotExist();
  });

  test('Accept of a commit counts the closing comment as pushed', async function (assert) {
    board().conversations = [carols('proposed')];
    board().proposals['PRRT_c1'] = [
      proposal({ conversation: 'PRRT_c1', kind: 'commit' }),
    ];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-dialog-submit]');

    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('This is the last one open: 1 pushed');
  });

  test('Accept of a reply counts the closing comment as replied', async function (assert) {
    board().conversations = [carols('proposed')];
    board().proposals['PRRT_c1'] = [
      proposal({ conversation: 'PRRT_c1', kind: 'reply', reply: 'Agreed.' }),
    ];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="approve"]');
    await click('[data-test-dialog-submit]');

    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('This is the last one open: 1 replied');
  });

  test('the list of carol’s comments is one closed row counting the round', async function (assert) {
    await markedDone([PUSHED, REPLIED]);

    assert
      .dom('[data-test-rerequest-comments]')
      .includesText('3 comments from carol');
    assert
      .dom('[data-test-rerequest-comments]')
      .hasAttribute('aria-expanded', 'false');
    assert.dom('[data-test-rerequest-comment]').doesNotExist();

    await click('[data-test-rerequest-comments]');

    assert.dom('[data-test-rerequest-comment]').exists({ count: 3 });
  });

  function said(key: string): string {
    return `[data-test-rerequest-comment="${key}"]`;
  }

  test('each comment says where it was left: a line, the review body or the PR at large', async function (assert) {
    await markedDone([
      closed('PRRT_c8', { kind: 'review-summary' }),
      closed('PRRT_c9', { kind: 'issue' }),
    ]);
    await click('[data-test-rerequest-comments]');

    assert
      .dom(`${said('PRRT_c8')} [data-test-rerequest-where]`)
      .hasText('review body');
    assert
      .dom(`${said('PRRT_c9')} [data-test-rerequest-where]`)
      .hasText('PR comment');
    assert
      .dom(`${said('PRRT_c1')} [data-test-rerequest-where]`)
      .hasText('src/foo.py:42');
  });

  test('each comment says what it said: the gist, else the first line carol wrote', async function (assert) {
    board().conversations = [
      carols('proposed', { gist: null }),
      closed('PRRT_c2', { gist: 'rename the helper' }),
      closed('PRRT_c3', { gist: null }),
    ];
    board().comments['PRRT_c1'] = [
      comment({
        author: 'carol',
        created_at: OPENED_AT,
        body: 'Split this function.\nIt does two things.',
      }),
    ];
    await visit('/pr/o/r/7/conversations/PRRT_c1');
    await click('[data-test-decision="mark-done"]');
    await click('[data-test-rerequest-comments]');

    assert
      .dom(`${said('PRRT_c1')} [data-test-rerequest-what]`)
      .hasText('Split this function.');
    assert
      .dom(`${said('PRRT_c2')} [data-test-rerequest-what]`)
      .hasText('rename the helper');
    assert.dom(`${said('PRRT_c3')} [data-test-rerequest-what]`).doesNotExist();
  });

  function chipsOf(key: string): string[] {
    return [
      ...document.querySelectorAll(`${said(key)} [data-test-rerequest-chip]`),
    ].map((one) => one.textContent?.trim() ?? '');
  }

  test('each comment carries a chip for every outcome that applies', async function (assert) {
    const filed = closed('PRRT_c7', {
      operations: [
        summary({
          id: 'PRRT_c7.1',
          kind: 'approve',
          state: 'applied',
          lands: 'ticket',
          ticket_key: 'PROJ-12',
        }),
      ],
    });
    await markedDone([PUSHED, REPLIED, RESOLVED, REJECTED, DEFERRED, filed]);
    await click('[data-test-rerequest-comments]');

    assert.deepEqual(chipsOf('PRRT_c1'), ['marked done']);
    assert.deepEqual(chipsOf('PRRT_c2'), ['pushed']);
    assert.deepEqual(chipsOf('PRRT_c3'), ['replied', 'resolved']);
    assert.deepEqual(chipsOf('PRRT_c4'), ['resolved']);
    assert.deepEqual(chipsOf('PRRT_c5'), ['rejected']);
    assert.deepEqual(chipsOf('PRRT_c6'), ['deferred']);
    assert.deepEqual(chipsOf('PRRT_c7'), ['ticket filed']);
  });

  const AT = (hour: number): string =>
    `2026-09-12T${String(hour).padStart(2, '0')}:00:00Z`;

  function historyOf(key: string): { at: string; what: string }[] {
    return [
      ...document.querySelectorAll(`${said(key)} [data-test-history-entry]`),
    ].map((one) => ({
      at: one.querySelector('time')?.getAttribute('datetime') ?? '',
      what:
        one.querySelector('[data-test-history-what]')?.textContent?.trim() ??
        '',
    }));
  }

  async function historyOpened(key: string): Promise<void> {
    await click('[data-test-rerequest-comments]');
    await click(`${said(key)} [data-test-history]`);
  }

  test('History stays closed until opened', async function (assert) {
    await markedDone([PUSHED]);
    await click('[data-test-rerequest-comments]');

    assert
      .dom(`${said('PRRT_c2')} [data-test-history]`)
      .hasAttribute('aria-expanded', 'false');
    assert.dom(`${said('PRRT_c2')} [data-test-history-entry]`).doesNotExist();
  });

  test('History reads the thread and tells its story oldest first, each step with its time', async function (assert) {
    const told = closed('PRRT_c2', {
      comments: [
        { id: 1, author: 'carol', created_at: AT(10), review_state: null },
        { id: 2, author: 'dave', created_at: AT(15), review_state: null },
      ],
      operations: [
        summary({ id: 'PRRT_c2.1', kind: 'first', settled_at: AT(11) }),
        summary({
          id: 'PRRT_c2.2',
          kind: 'rework',
          requested_at: AT(12),
          settled_at: AT(13),
        }),
        summary({
          id: 'PRRT_c2.3',
          kind: 'approve',
          lands: 'commit',
          settled_at: AT(14),
        }),
        summary({ id: 'PRRT_c2.4', kind: 'resolve', settled_at: AT(16) }),
      ],
    });
    board().operations['PRRT_c2'] = [
      operation({
        id: 'PRRT_c2.1',
        conversation: 'PRRT_c2',
        kind: 'first',
        settled_at: AT(11),
        proposal: 'PRRT_c2.1.proposal',
      }),
      operation({
        id: 'PRRT_c2.2',
        conversation: 'PRRT_c2',
        kind: 'rework',
        requested_at: AT(12),
        settled_at: AT(13),
        proposal: 'PRRT_c2.2.proposal',
        brief: {
          note: 'Keep the old name as an alias.',
          pointed: [],
          include: [],
          part: null,
        },
      }),
      operation({
        id: 'PRRT_c2.3',
        conversation: 'PRRT_c2',
        kind: 'approve',
        settled_at: AT(14),
        landed_sha: 'abcdef1234567890',
      }),
    ];
    await markedDone([told]);

    await historyOpened('PRRT_c2');

    assert.deepEqual(historyOf('PRRT_c2'), [
      { at: AT(10), what: 'carol commented' },
      { at: AT(11), what: 'Agent proposed a fix' },
      {
        at: AT(12),
        what: 'Sent back for rework: “Keep the old name as an alias.”',
      },
      { at: AT(13), what: 'Agent proposed a fix' },
      { at: AT(14), what: 'Accepted and pushed abcdef1' },
      { at: AT(15), what: 'dave replied' },
      { at: AT(16), what: 'Marked done' },
    ]);
  });

  test('History says a comment was rejected, resolved, or deferred and what wakes it', async function (assert) {
    const deferred = closed('PRRT_c6', {
      state: 'deferred',
      record_state: 'deferred',
      operations: [
        summary({ id: 'PRRT_c6.1', kind: 'defer', settled_at: AT(11) }),
      ],
    });
    board().operations['PRRT_c6'] = [
      operation({
        id: 'PRRT_c6.1',
        conversation: 'PRRT_c6',
        kind: 'defer',
        settled_at: AT(11),
        until: 'push',
      }),
    ];
    const rejected = closed('PRRT_c5', {
      record_state: 'rejected',
      operations: [
        summary({ id: 'PRRT_c5.1', kind: 'reject', settled_at: AT(11) }),
      ],
    });
    const resolved = closed('PRRT_c4', {
      github_resolved: true,
      operations: [
        summary({ id: 'PRRT_c4.1', kind: 'resolve', settled_at: AT(11) }),
      ],
    });
    await markedDone([deferred, rejected, resolved]);

    await historyOpened('PRRT_c6');
    await click(`${said('PRRT_c5')} [data-test-history]`);
    await click(`${said('PRRT_c4')} [data-test-history]`);

    assert.deepEqual(
      historyOf('PRRT_c6').map((one) => one.what),
      ['carol commented', 'Deferred, waiting until the next push'],
    );
    assert.deepEqual(
      historyOf('PRRT_c5').map((one) => one.what),
      ['carol commented', 'Rejected'],
    );
    assert.deepEqual(
      historyOf('PRRT_c4').map((one) => one.what),
      ['carol commented', 'Resolved'],
    );
  });

  async function onTheDashboard(over: DashboardOver): Promise<void> {
    serve(over);
    board().conversations = [closed('PRRT_c1', {})];
    await visit('/pr/o/r/7/dashboard');
  }

  test('the Dashboard offers "Re-request review" only for its move', async function (assert) {
    await onTheDashboard({ facts: CAROL_COMMENTED });

    assert.dom('[data-test-band-move]').hasText('Re-request review from carol');
    assert
      .dom('[data-test-control="rerequest-review"]')
      .hasText('Re-request review e');
  });

  test('the Dashboard offers no "Re-request review" once GitHub lists carol as pending', async function (assert) {
    await onTheDashboard({
      facts: { ...CAROL_COMMENTED, pending_reviewers: ['carol'] },
    });

    assert.dom('[data-test-control="rerequest-review"]').doesNotExist();
  });

  test('"Re-request review" opens the prompt without a decision and posts nothing', async function (assert) {
    await onTheDashboard({ facts: CAROL_COMMENTED });

    await click('[data-test-control="rerequest-review"]');

    assert
      .dom('[data-test-rerequest-kicker]')
      .hasText('Last comment from carol');
    assert
      .dom('[data-test-rerequest-question]')
      .hasText("Re-request carol's review of #7?");
    assert.dom('[data-test-rerequest-badge]').hasText('Commented');
    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('Every comment is closed: 1 marked done');
    assert
      .dom('[data-test-rerequest-comments]')
      .includesText('1 comment from carol');
    assert.dom('[data-test-rerequest-and]').hasText('Re-request review r');
    assert.dom('[data-test-rerequest-only]').hasText('Not yet n');
    assert.deepEqual(verbs(), []);
  });

  test('"Re-request review" in the prompt queues carol, and the move says so', async function (assert) {
    await onTheDashboard({ facts: CAROL_COMMENTED });
    await click('[data-test-control="rerequest-review"]');

    await click('[data-test-rerequest-and]');

    assert.deepEqual(verbs(), ['rerequest-review']);
    assert.deepEqual(board().posted[0]!.body, { reviewer: 'carol' });
    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.dom('[data-test-band-move]').hasText('Re-request queued for carol');
  });

  test('"Not yet" closes the prompt and posts nothing', async function (assert) {
    await onTheDashboard({ facts: CAROL_COMMENTED });
    await click('[data-test-control="rerequest-review"]');

    await click('[data-test-rerequest-only]');

    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.deepEqual(verbs(), []);
    assert.dom('[data-test-band-move]').hasText('Re-request review from carol');
  });

  test('on the Dashboard, e opens the prompt and r and n pick its buttons', async function (assert) {
    await onTheDashboard({ facts: CAROL_COMMENTED });

    await triggerEvent(document, 'keydown', { key: 'e' });
    await triggerEvent(document, 'keydown', { key: 'n' });

    assert.dom('[data-test-rerequest-prompt]').doesNotExist();
    assert.deepEqual(verbs(), []);

    await triggerEvent(document, 'keydown', { key: 'e' });
    await triggerEvent(document, 'keydown', { key: 'r' });

    assert.deepEqual(verbs(), ['rerequest-review']);
  });

  test('a change request with no comments opens the prompt with no list', async function (assert) {
    serve({
      facts: {
        ...CAROL_COMMENTED,
        commented_by: [],
        changes_requested_by: ['carol'],
      },
    });
    board().conversations = [];
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-control="rerequest-review"]');

    assert.dom('[data-test-rerequest-badge]').hasText('Changes requested');
    assert
      .dom('[data-test-rerequest-summary]')
      .hasText('carol left no comments to close.');
    assert.dom('[data-test-rerequest-comments]').doesNotExist();
  });

  test('with two reviewers owed, each "Re-request review" names its login', async function (assert) {
    serve({ facts: { ...CAROL_COMMENTED, commented_by: ['carol', 'erin'] } });
    board().conversations = [
      closed('PRRT_c1', {}),
      closed('PRRT_e1', { opened_by: 'erin' }),
    ];
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-control="rerequest-review"]').exists({ count: 2 });
    assert
      .dom('[data-test-control="rerequest-review"][data-test-reviewer="erin"]')
      .hasText('Re-request review from erin');

    await click(
      '[data-test-control="rerequest-review"][data-test-reviewer="erin"]',
    );

    assert
      .dom('[data-test-rerequest-question]')
      .hasText("Re-request erin's review of #7?");
  });

  const QUEUED: DashboardOver = {
    facts: CAROL_COMMENTED,
    system: { rerequest_queued: ['carol'] },
  };

  test('a queued re-request offers "Cancel" and "Send now", and nothing to re-request', async function (assert) {
    await onTheDashboard(QUEUED);

    assert.dom('[data-test-band-move]').hasText('Re-request queued for carol');
    assert.dom('[data-test-control="cancel-rerequest"]').hasText('Cancel x');
    assert.dom('[data-test-control="send-rerequest"]').hasText('Send now s');
    assert.dom('[data-test-control="rerequest-review"]').doesNotExist();
  });

  test('"Cancel" takes carol off the queue, and the move asks to re-request carol again', async function (assert) {
    await onTheDashboard(QUEUED);

    await click('[data-test-control="cancel-rerequest"]');

    assert.deepEqual(verbs(), ['cancel-rerequest']);
    assert.strictEqual(
      board().posted[0]!.url,
      '/pr/o/r/7/api/manager:cancel-rerequest',
    );
    assert.deepEqual(board().posted[0]!.body, { reviewer: 'carol' });
    assert.dom('[data-test-band-move]').hasText('Re-request review from carol');
  });

  test('"Send now" asks the manager to send carol\'s re-request at once', async function (assert) {
    await onTheDashboard(QUEUED);

    await click('[data-test-control="send-rerequest"]');

    assert.deepEqual(verbs(), ['send-rerequest']);
    assert.strictEqual(
      board().posted[0]!.url,
      '/pr/o/r/7/api/manager:send-rerequest',
    );
    assert.deepEqual(board().posted[0]!.body, { reviewer: 'carol' });
  });

  test('s sends the first queued re-request now', async function (assert) {
    await onTheDashboard(QUEUED);

    await triggerEvent(document, 'keydown', { key: 's' });

    assert.deepEqual(verbs(), ['send-rerequest']);
  });

  test('x cancels the first queued re-request', async function (assert) {
    await onTheDashboard(QUEUED);

    await triggerEvent(document, 'keydown', { key: 'x' });

    assert.deepEqual(verbs(), ['cancel-rerequest']);
  });

  test('with two reviewers queued, each Cancel and Send now names its login', async function (assert) {
    serve({
      facts: { ...CAROL_COMMENTED, commented_by: ['carol', 'erin'] },
      system: { rerequest_queued: ['carol', 'erin'] },
    });
    board().conversations = [
      closed('PRRT_c1', {}),
      closed('PRRT_e1', { opened_by: 'erin' }),
    ];
    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-control$="-rerequest"]')].map(
        (one) => one.textContent?.replace(/\s+/g, ' ').trim(),
      ),
      [
        'Cancel carol x',
        'Send now to carol s',
        'Cancel erin',
        'Send now to erin',
      ],
    );

    await click(
      '[data-test-control="send-rerequest"][data-test-reviewer="erin"]',
    );

    assert.deepEqual(board().posted[0]!.body, { reviewer: 'erin' });
  });
});
