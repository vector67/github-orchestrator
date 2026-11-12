import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  fillIn,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  added,
  comment,
  diffOf,
  operation,
  proposal,
  removed,
  setupFakeBoard,
  summary,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import type {
  Proposal,
  SplitPart,
  SplitPartName,
  Ticket,
  TicketLink,
} from 'frontend/data/api';

const KEY = 'PRRT_split';
const PROPOSAL = `${KEY}.1.proposal`;
const REPLY = 'Agreed; the rounding change moved to its own PR.';
const TICKET: Ticket = {
  project: 'PROJ',
  title: 'Round invoice totals once',
  body: 'Round once, at the end.',
};

function part(name: SplitPartName, over: Partial<SplitPart> = {}): SplitPart {
  return {
    part: name,
    state: 'proposed',
    waits_for: null,
    result: null,
    ...over,
  };
}

function parts(ticket: boolean): SplitPart[] {
  return [
    ...(ticket ? [part('ticket')] : []),
    part('changes'),
    part('new-pr', { waits_for: ticket ? 'ticket' : null }),
    part('reply', { waits_for: 'new-pr' }),
  ];
}

interface SplitOver {
  ticket?: Ticket | null;
  existing?: TicketLink | null;
  parts?: SplitPart[];
}

function splitProposal(over: SplitOver = {}): Proposal {
  const ticket = over.ticket ?? null;
  return proposal({
    id: PROPOSAL,
    conversation: KEY,
    kind: 'split',
    reply: REPLY,
    summary: null,
    commit_message: 'Take the rounding change out',
    split: {
      branch: 'split/rounding',
      base: 'main',
      base_reason: 'the rounding change stands alone',
      ticket,
      existing_ticket: over.existing ?? null,
      parts: over.parts ?? parts(ticket !== null),
    },
  });
}

function seed(board: FakeBoard, over: SplitOver = {}) {
  board.conversations = [board.threadIn('proposed', { key: KEY })];
  board.comments[KEY] = [comment({ body: 'this belongs in its own PR' })];
  board.operations[KEY] = [
    operation({ id: `${KEY}.1`, conversation: KEY, plan: [] }),
  ];
  board.proposals[KEY] = [splitProposal(over)];
  board.diffs[PROPOSAL] = diffOf(
    'billing/round.py',
    removed(12, '    return round(total, 2)'),
    added(12, '    return total'),
  );
}

function texts(selector: string): string[] {
  return findAll(selector).map((one) =>
    (one.textContent ?? '').replace(/\s+/g, ' ').trim(),
  );
}

module('Acceptance | split', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('each part is a card, top to bottom changes, new PR, reply, when the new PR keeps this ticket', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('[data-test-split-card] [data-test-part-kicker]'), [
      'Changes to this PR',
      'New PR',
      'Reply',
    ]);
  });

  test('a drafted ticket is the first card, drawn as the ticket box', async function (assert) {
    seed(board(), { ticket: TICKET });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('[data-test-split-card] [data-test-part-kicker]'), [
      'Ticket',
      'Changes to this PR',
      'New PR',
      'Reply',
    ]);
    assert
      .dom('[data-test-split-card="ticket"] [data-test-ticket-title-shown]')
      .hasText(TICKET.title);
    assert
      .dom('[data-test-split-card="ticket"] [data-test-ticket-project-shown]')
      .hasText(TICKET.project);
  });

  test('the changes card lists the files the removal touches', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-split-card="changes"] [data-test-part-file]')
      .includesText('billing/round.py');
  });

  test('the new PR card names its branch, its base and why that base', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-branch]')
      .hasText('split/rounding');
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-base]')
      .hasText('main');
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-base-reason]')
      .hasText('the rounding change stands alone');
  });

  test('a new PR under an existing ticket names it on the new PR card, with no ticket card', async function (assert) {
    seed(board(), {
      existing: {
        key: 'PROJ-34',
        url: 'https://example.atlassian.net/browse/PROJ-34',
      },
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('[data-test-split-card] [data-test-part-kicker]'), [
      'Changes to this PR',
      'New PR',
      'Reply',
    ]);
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-existing-ticket]')
      .hasText('Existing ticket PROJ-34');
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-existing-ticket] a')
      .hasAttribute('href', 'https://example.atlassian.net/browse/PROJ-34');
  });

  test("a new PR under this PR's ticket names no existing ticket", async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-part-existing-ticket]').doesNotExist();
  });

  test('each proposed part offers its own buttons, Edit only where it has words', async function (assert) {
    seed(board(), { ticket: TICKET });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const offered = (name: string) =>
      texts(`[data-test-split-card="${name}"] [data-test-part-act]`);
    assert.deepEqual(offered('ticket'), ['Accept', 'Edit', 'Rework']);
    assert.deepEqual(offered('changes'), ['Accept', 'Rework']);
    assert.deepEqual(offered('new-pr'), ['Accept', 'Rework']);
    assert.deepEqual(offered('reply'), ['Accept', 'Edit', 'Rework']);
  });

  test('a part’s buttons mark the dialogs they open and the agent runs they start', async function (assert) {
    seed(board(), { ticket: TICKET });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const marked = (name: string) =>
      findAll(`[data-test-split-card="${name}"] [data-test-part-act]`).map(
        (one) =>
          [
            one.getAttribute('data-test-part-act'),
            one.hasAttribute('data-runs-agent') ? '✦' : '',
            one.hasAttribute('data-opens-dialog') ? '⧉' : '',
          ].join(''),
      );
    assert.deepEqual(marked('ticket'), ['accept✦', 'edit⧉', 'rework✦⧉']);
    assert.deepEqual(marked('changes'), ['accept', 'rework✦⧉']);
    assert.deepEqual(marked('new-pr'), ['accept✦', 'rework✦⧉']);
    assert.deepEqual(marked('reply'), ['accept', 'edit⧉', 'rework✦⧉']);
    assert
      .dom('[data-test-decision="approve"]')
      .hasAttribute('data-runs-agent')
      .hasAttribute('data-opens-dialog');
  });

  test('accepting a part accepts that part alone, at once', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click(
      '[data-test-split-card="changes"] [data-test-part-act="accept"]',
    );

    assert.dom('[data-test-dialog]').doesNotExist();
    const posted = board().posted.at(-1)!;
    assert.strictEqual(posted.verb, 'approve');
    assert.propContains(posted.body, { part: 'changes' });
  });

  test('a part accepted and waiting its turn offers no Accept, and keeps its Edit', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr'),
        part('reply', { state: 'queued', waits_for: 'new-pr' }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      texts('[data-test-split-card="reply"] [data-test-part-act]'),
      ['Edit', 'Rework'],
    );
  });

  test('Edit on the reply opens the dialog on the reply and saves it without accepting', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-split-card="reply"] [data-test-part-act="edit"]');

    assert.dom('[data-test-dialog-body]').hasValue(REPLY);
    assert.dom('[data-test-dialog-submit]').hasText('Edit');
    await fillIn('[data-test-dialog-body]', 'Moved to its own PR.');
    await click('[data-test-dialog-submit]');

    const posted = board().posted.at(-1)!;
    assert.strictEqual(posted.verb, 'edit-part');
    assert.deepEqual(posted.body, {
      part: 'reply',
      reply: 'Moved to its own PR.',
    });
  });

  test('Edit on the ticket opens the ticket fields and saves the ticket without filing it', async function (assert) {
    seed(board(), { ticket: TICKET });

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-split-card="ticket"] [data-test-part-act="edit"]');

    assert.dom('[data-test-dialog-body]').doesNotExist();
    assert.dom('[data-test-ticket-title]').hasValue(TICKET.title);
    await fillIn('[data-test-ticket-title]', 'Round totals once');
    await click('[data-test-dialog-submit]');

    const posted = board().posted.at(-1)!;
    assert.strictEqual(posted.verb, 'edit-part');
    assert.deepEqual(posted.body, {
      part: 'ticket',
      ticket: { ...TICKET, title: 'Round totals once' },
    });
  });

  test('Rework on a part sends back that part alone, with your note', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click(
      '[data-test-split-card="new-pr"] [data-test-part-act="rework"]',
    );

    assert.dom('[data-test-rework-kicker]').includesText('New PR');
    assert.dom('[data-test-rework-visible]').doesNotExist();
    await fillIn('[data-test-rework-body]', 'Name the branch after the ticket');
    await click('[data-test-send-rework]');

    const posted = board().posted.at(-1)!;
    assert.strictEqual(posted.verb, 'rework');
    assert.propContains(posted.body, {
      part: 'new-pr',
      note: 'Name the branch after the ticket',
    });
  });

  test('once a part has run, the footer offers no rework of the whole split, and a part still can be', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr'),
        part('reply', { waits_for: 'new-pr' }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('#panel-actions [data-test-decision="rework"]').doesNotExist();
    await click('[data-test-split-card="reply"] [data-test-part-act="rework"]');
    assert.dom('[data-test-rework-dialog]').exists();
  });

  test('Accept all sits in the footer and accepts every part, asking only whether to resolve the thread', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('#panel-actions [data-test-decision="approve"]');

    assert
      .dom('#panel-actions [data-test-decision="approve"]')
      .includesText('Accept all');
    assert.dom('[data-test-dialog-question]').doesNotIncludeText('push');
    assert.dom('[data-test-dialog-body]').doesNotExist();
    assert.dom('[data-test-resolve]').exists();
    await click('[data-test-resolve]');
    await click('[data-test-dialog-submit]');

    const posted = board().posted.at(-1)!;
    assert.strictEqual(posted.verb, 'approve');
    assert.propContains(posted.body, { resolve: true });
    assert.notOk('part' in (posted.body as object));
  });

  test('Accept all names every part in turn when the split files a ticket', async function (assert) {
    seed(board(), { ticket: TICKET });

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('#panel-actions [data-test-decision="approve"]');

    assert
      .dom('[data-test-dialog-note]')
      .hasText(
        'Each runs in turn: the ticket is filed, the changes are pushed to ' +
          'this PR, the new PR is opened, and the reply is posted naming it. ' +
          'A part that has run cannot be undone.',
      );
  });

  test('Accept all files no ticket when the new PR keeps this ticket', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('#panel-actions [data-test-decision="approve"]');

    assert
      .dom('[data-test-dialog-note]')
      .hasText(
        'Each runs in turn: the changes are pushed to this PR, the new PR is ' +
          'opened, and the reply is posted naming it. A part that has run ' +
          'cannot be undone.',
      );
  });

  test('Accept all names only the parts not yet accepted or run', async function (assert) {
    seed(board(), {
      ticket: TICKET,
      parts: [
        part('ticket', { state: 'run', result: { text: 'PROJ-1', url: null } }),
        part('changes', { state: 'queued' }),
        part('new-pr', { state: 'running', waits_for: 'ticket' }),
        part('reply', { waits_for: 'new-pr' }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('#panel-actions [data-test-decision="approve"]');

    assert
      .dom('[data-test-dialog-note]')
      .hasText(
        'The reply is posted naming the new PR. A part that has run cannot ' +
          'be undone.',
      );
  });

  test('Reject is offered while no part has run', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('#panel-actions [data-test-decision="reject"]').exists();
  });

  test('once a part has run, Reject is gone and Accept all stays', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr'),
        part('reply', { waits_for: 'new-pr' }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('#panel-actions [data-test-decision="reject"]').doesNotExist();
    assert.dom('#panel-actions [data-test-decision="approve"]').exists();
  });

  test('a queued part shows the queued banner saying what it waits for', async function (assert) {
    seed(board(), {
      ticket: TICKET,
      parts: [
        part('ticket', { state: 'running' }),
        part('changes'),
        part('new-pr', { state: 'queued', waits_for: 'ticket' }),
        part('reply', { state: 'queued', waits_for: 'new-pr' }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-banner]')
      .includesText('waiting for ticket');
    assert
      .dom('[data-test-split-card="reply"] [data-test-part-banner]')
      .includesText('waiting for new PR');
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-banner]')
      .hasAttribute('data-tone', 'queued');
  });

  test('while a part runs it shows the working banner and offers nothing, no part offers Rework, and Accept all stays', async function (assert) {
    seed(board(), {
      ticket: TICKET,
      parts: [
        part('ticket', { state: 'running' }),
        part('changes'),
        part('new-pr', { state: 'queued', waits_for: 'ticket' }),
        part('reply', { state: 'queued', waits_for: 'new-pr' }),
      ],
    });

    board().conversations = [board().threadIn('landing', { key: KEY })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('#panel-actions [data-test-decision="approve"]')
      .includesText('Accept all');
    assert
      .dom('[data-test-split-card="ticket"] [data-test-part-banner]')
      .hasAttribute('data-tone', 'working');
    assert
      .dom('[data-test-split-card="ticket"] [data-test-part-banner]')
      .includesText('Filing the ticket');
    assert
      .dom('[data-test-split-card="ticket"] [data-test-part-act]')
      .doesNotExist();
    assert.dom('[data-test-part-act="rework"]').doesNotExist();
    assert.deepEqual(
      texts('[data-test-split-card="changes"] [data-test-part-act]'),
      ['Accept'],
    );
  });

  test('a part that has run collapses to its one-line result, with no buttons', async function (assert) {
    seed(board(), {
      ticket: TICKET,
      parts: [
        part('ticket', {
          state: 'run',
          result: {
            text: 'PROJ-12',
            url: 'https://example.atlassian.net/browse/PROJ-12',
          },
        }),
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1234567890', url: null },
        }),
        part('new-pr', {
          state: 'run',
          waits_for: 'ticket',
          result: {
            text: 'https://github.com/o/r/pull/8',
            url: 'https://github.com/o/r/pull/8',
          },
        }),
        part('reply', {
          state: 'run',
          waits_for: 'new-pr',
          result: { text: 'Moved to #8.', url: null },
        }),
      ],
    });

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-part-act]').doesNotExist();
    assert
      .dom('[data-test-split-card] [data-test-proposed-ticket]')
      .doesNotExist();
    assert
      .dom('[data-test-split-card] [data-test-proposed-reply]')
      .doesNotExist();
    assert
      .dom('[data-test-split-card="ticket"] [data-test-part-result] a')
      .hasAttribute('href', 'https://example.atlassian.net/browse/PROJ-12')
      .hasText('PROJ-12');
    assert
      .dom('[data-test-split-card="changes"] [data-test-part-result]')
      .includesText('c0ffee1');
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-result] a')
      .hasAttribute('href', 'https://github.com/o/r/pull/8');
    assert
      .dom('[data-test-split-card="reply"] [data-test-part-result]')
      .includesText('Moved to #8.');
  });

  test('a part whose work failed says why on its own card and can be accepted again, the rest of the split as it was', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr'),
        part('reply', { waits_for: 'new-pr' }),
      ],
    });
    const reason = 'the agent ended without reporting the new PR';
    const refused = {
      id: `${KEY}.2`,
      kind: 'approve' as const,
      state: 'refused' as const,
      reason,
      reason_code: 'open-failed' as const,
    };
    const [proposed] = board().conversations;
    board().conversations = [
      {
        ...proposed!,
        operations: [
          ...proposed!.operations,
          summary({ ...refused, lands: 'split' }),
        ],
      },
    ];
    board().operations[KEY] = [
      ...board().operations[KEY]!,
      operation({ ...refused, conversation: KEY }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-failure]').doesNotExist();
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-failure]')
      .includesText(reason);
    assert
      .dom('[data-test-split-card="new-pr"] [data-test-part-act="accept"]')
      .exists();
    assert
      .dom('[data-test-split-card="changes"] [data-test-part-failure]')
      .doesNotExist();
  });

  test('the diff pane holds two accordions, Changes to this PR and New PR, both collapsed, each a diff with its full-screen button', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(texts('#panel-diff [data-test-split-diff] > summary'), [
      'Changes to this PR',
      'New PR',
    ]);
    assert.dom('#panel-diff [data-test-split-diff][open]').doesNotExist();
    assert
      .dom('#panel-diff [data-test-split-diff] [data-test-full-screen]')
      .exists({ count: 2 });
  });

  test('the changes accordion shows the removal, and the new PR accordion its branch against its base', async function (assert) {
    seed(board());
    board().splitDiffs[KEY] = diffOf(
      'billing/rounding.py',
      added(1, 'def round_once(total):'),
    );

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-split-diff="changes"] > summary');
    await click('[data-test-split-diff="new-pr"] > summary');

    assert
      .dom('[data-test-split-diff="changes"] [data-test-diff-file]')
      .includesText('billing/round.py');
    assert
      .dom('[data-test-split-diff="new-pr"] [data-test-diff-file]')
      .includesText('billing/rounding.py');
  });

  test('z opens full screen on the accordion that is open, not on a collapsed one', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-split-diff="changes"] > summary');
    await triggerEvent(document, 'keydown', { key: 'z' });

    assert
      .dom('[data-test-split-diff="changes"] [data-test-frame]')
      .hasAttribute('data-expanded');
    assert
      .dom('[data-test-split-diff="new-pr"] [data-test-frame]')
      .doesNotHaveAttribute('data-expanded');
  });

  test('the label says the agent proposes moving this into a new PR', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-fix-label]')
      .hasText('Agent proposes moving this into a new PR');
  });

  test('once every part has run, the label says so and the cards alone show what each did', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr', {
          state: 'run',
          result: {
            text: 'https://github.com/o/r/pull/8',
            url: 'https://github.com/o/r/pull/8',
          },
        }),
        part('reply', {
          state: 'run',
          waits_for: 'new-pr',
          result: { text: 'Moved to #8.', url: null },
        }),
      ],
    });
    board().conversations = [board().threadIn('landed', { key: KEY })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-fix-label]')
      .hasText('Accepted · every part has run');
    assert.dom('[data-test-banner-fix]').doesNotExist();
    assert.dom('[data-test-split-card] [data-test-part-result]').exists({
      count: 3,
    });
    assert
      .dom('[data-test-split-diff="new-pr"] [data-test-frame]')
      .doesNotExist();
    assert
      .dom('[data-test-split-diff="new-pr"] [data-test-fold-placeholder] a')
      .hasAttribute('href', 'https://github.com/o/r/pull/8');
  });

  test('while the agent reworks a part, the cards stay drawn and nothing offers to accept, edit or rework', async function (assert) {
    seed(board(), {
      parts: [
        part('changes', {
          state: 'run',
          result: { text: 'c0ffee1', url: null },
        }),
        part('new-pr'),
        part('reply', { waits_for: 'new-pr' }),
      ],
    });
    board().conversations = [board().threadIn('rework', { key: KEY })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-split-card]').exists({ count: 3 });
    assert.dom('[data-test-part-act]').doesNotExist();
    assert.dom('#panel-actions [data-test-decision="approve"]').doesNotExist();
  });

  test('a split that has landed says on its rail row that it moved to a new PR', async function (assert) {
    seed(board());
    const landed = board().threadIn('landed', { key: KEY });
    board().conversations = [
      {
        ...landed,
        operations: landed.operations.map((one) =>
          one.kind === 'approve' ? { ...one, lands: 'split' as const } : one,
        ),
      },
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-meta]').hasText('Moved to a new PR');
  });

  test('the reply card quotes the reply', async function (assert) {
    seed(board());

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-split-card="reply"] [data-test-proposed-reply]')
      .hasText(REPLY);
  });
});
