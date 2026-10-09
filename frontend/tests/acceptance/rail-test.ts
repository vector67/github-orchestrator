import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, triggerEvent, visit } from '@ember/test-helpers';
import type { Conversation, OperationSummary } from 'frontend/data/api';
import {
  operation,
  setupFakeBoard,
  summary,
  thread,
} from 'frontend/tests/helpers/fake-board';

function headings(): (string | null)[] {
  return [...document.querySelectorAll('[data-test-heading]')].map((node) =>
    node.getAttribute('data-test-heading'),
  );
}

function rowIds(): string[] {
  return [...document.querySelectorAll('#rows li[role="option"]')].map(
    (node) => node.id,
  );
}

function readingOrder(row: string): string[] {
  return [
    ...document.querySelectorAll(
      `${row} [data-test-gist], ${row} [data-test-path], ${row} [data-test-meta]`,
    ),
  ].map((node) => node.textContent?.trim() ?? '');
}

module('Acceptance | rail', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      thread({
        key: 'PRRT_aa',
        operations: [summary({ steps_done: 3, steps_total: 3 })],
      }),
    ];
  });

  test('a row reads its title, then where it points, then what it is doing', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(
      readingOrder('#c-PRRT_aa'),
      ['rename the helper', 'src/foo.py:42', 'Anna Example · 3 of 3 changes'],
      'the design leads with the title and ends with what the row is doing',
    );
  });

  test('the rail asks the board api for them', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.strictEqual(board().askedFor(/\/api\/conversations$/).length, 1);
  });

  test('the rail groups by state and keeps the order the list came in', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('proposed', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
      board().threadIn('proposed', { key: 'd' }),
      board().threadIn('queued', { key: 'e', reopened: true }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(
      headings(),
      ['ready', 'working', 'queued', 'done'],
      'the groups stand in the board order and an empty group is not drawn',
    );
    assert.deepEqual(
      rowIds(),
      ['c-b', 'c-d', 'c-a', 'c-e', 'c-c'],
      'a reopened run stands with its agent, in the place the server gave it',
    );
  });

  test('inside a group the order is the order the list came in', async function (assert) {
    board().conversations = [
      thread({ key: 'mid', state_changed_at: '2026-05-05T00:00:00Z' }),
      thread({ key: 'old', state_changed_at: '2026-01-01T00:00:00Z' }),
      thread({ key: 'new', state_changed_at: '2026-09-09T00:00:00Z' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(
      rowIds(),
      ['c-mid', 'c-old', 'c-new'],
      'the server orders; the front end only groups',
    );
  });

  test('a reopened thread is ready for you only while it holds a proposal to decide', async function (assert) {
    board().conversations = [
      board().threadIn('queued', { key: 'q', reopened: true }),
      thread({ key: 'n', reopened: true }),
      board().threadIn('proposed', { key: 'p', reopened: true }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(headings(), ['ready', 'attention', 'queued']);
    assert.deepEqual(rowIds(), ['c-p', 'c-n', 'c-q']);
  });

  test('a rework and a session stand under one heading', async function (assert) {
    board().conversations = [
      board().threadIn('rework', { key: 'r' }),
      board().threadIn('session', { key: 's' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(headings(), ['rework']);
    assert
      .dom('[data-test-heading="rework"]')
      .includesText('Sent back for rework');
    assert.deepEqual(rowIds(), ['c-r', 'c-s']);
  });

  test('only enrolled drafts are your review; a draft not added stands under its own heading, and each row says which it is', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('draft', { key: 'd' }),
      board().threadIn('enrolled', { key: 'e' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(headings(), ['review', 'drafts']);
    assert.dom('[data-test-heading="review"]').includesText('Your review');
    assert.dom('[data-test-heading="drafts"]').includesText('Local drafts');
    assert.deepEqual(rowIds(), ['c-e', 'c-d']);
    assert.dom('#c-e [data-test-standing]').hasText('In your pending review');
    assert.dom('#c-d [data-test-standing]').hasText('Local draft');
  });

  test('an author reads the states in their own words', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-heading="ready"]').includesText('Ready for you');
    assert
      .dom('[data-test-heading="waiting"]')
      .includesText('Waiting on reviewer');
  });

  test('a reviewer reads the same states under their own headings', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-heading="ready"]').includesText('Answered');
    assert
      .dom('[data-test-heading="waiting"]')
      .includesText('Waiting on author');
  });

  test('a reviewer reads assumed done and not my conversation after waiting on the author', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('not-mine', { key: 'n' }),
      board().threadIn('resolved', { key: 'z' }),
      board().threadIn('deferred', { key: 'd' }),
      board().threadIn('assumed-done', { key: 'a' }),
      board().threadIn('enrolled', { key: 'e' }),
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('draft', { key: 'x' }),
      board().threadIn('answered', { key: 'r' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(headings(), [
      'ready',
      'review',
      'drafts',
      'waiting',
      'assumed-done',
      'not-mine',
      'deferred',
      'done',
    ]);
    assert
      .dom('[data-test-heading="assumed-done"]')
      .includesText('Assumed done');
    assert
      .dom('[data-test-heading="not-mine"]')
      .includesText('Not my conversation');
  });

  test('a thread the reviewer confirmed sits in Done and its card says Confirmed', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [board().threadIn('confirmed', { key: 'c' })];

    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(headings(), ['done']);
    assert.dom('#c-c [data-test-meta]').hasText('Confirmed');
  });

  test('a landed row says what its accept landed: a push, a reply or a filed ticket', async function (assert) {
    const landed = (key: string, approve: Partial<OperationSummary>) =>
      thread({
        key,
        state: 'done',
        operations: [
          summary(),
          summary({ id: `${key}.2`, kind: 'approve', ...approve }),
        ],
      });
    board().conversations = [
      landed('pushed', { lands: 'commit' }),
      landed('replied', { lands: 'reply' }),
      landed('filed', { lands: 'ticket', ticket_key: 'PROJ-12' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('#c-pushed [data-test-meta]').hasText('Pushed');
    assert.dom('#c-replied [data-test-meta]').hasText('Replied');
    assert.dom('#c-filed [data-test-meta]').hasText('Filed PROJ-12');
  });

  test('the open row says it is selected and the others say they are not', async function (assert) {
    board().conversations = [thread({ key: 'a' }), thread({ key: 'b' })];

    await visit('/pr/o/r/7/conversations/b');

    assert.dom('#c-b').hasAttribute('aria-selected', 'true');
    assert.dom('#c-a').hasAttribute('aria-selected', 'false');
  });

  test('a record the board cannot read is still a row', async function (assert) {
    board().unreadable = ['PRRT_shredded'];

    await visit('/pr/o/r/7/conversations');

    assert
      .dom('#c-PRRT_shredded [data-test-gist]')
      .hasText("this card's record could not be read");
    assert
      .dom('#c-PRRT_shredded [data-test-path]')
      .doesNotExist('a row with nowhere to point draws no location');
    assert
      .dom('#c-PRRT_shredded [data-test-meta]')
      .doesNotExist('a row with nothing to say draws no meta line');
  });

  test('the panel counts a card the board cannot read among the ready ones, as its heading does', async function (assert) {
    board().unreadable = ['PRRT_shredded'];

    await visit('/pr/o/r/7/conversations/PRRT_aa');

    assert.dom('[data-test-heading="ready"] [data-test-count]').hasText('2');
    assert.dom('[data-test-kicker]').includesText('1 of 2 ready');

    await triggerEvent(document, 'keydown', { key: 'n' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/PRRT_shredded');
  });

  test('a conversation with nothing to say draws no meta line', async function (assert) {
    board().conversations = [thread({ key: 'quiet', comments: [] })];

    await visit('/pr/o/r/7/conversations');

    assert.dom('#c-quiet [data-test-gist]').hasText('rename the helper');
    assert.dom('#c-quiet [data-test-meta]').doesNotExist();
  });

  test('nothing reads the old json:api board', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(board().askedFor(/\/api\/board/), []);
    assert.true(
      board().asked.every((one) => !one.url.includes('/v2/')),
      'the api is at /api now',
    );
  });
});

module('Acceptance | rail | what a row says', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  async function rowFor(one: Conversation): Promise<string> {
    board().conversations = [one];
    await visit('/pr/o/r/7/conversations');
    return `#c-${one.key}`;
  }

  test('a thread no agent has summed up yet is named by who wrote it', async function (assert) {
    const row = await rowFor(thread({ gist: null }));

    assert.dom(`${row} [data-test-gist]`).hasText('Anna Example commented');
  });

  test('a comment on the pull request at large says what kind it is', async function (assert) {
    const row = await rowFor(
      thread({
        kind: 'issue',
        anchor: {
          ...thread().anchor,
          path: null,
          line: null,
          original_line: null,
        },
      }),
    );

    assert.dom(`${row} [data-test-path]`).hasText('conversation');
  });

  test('a proposal counts the changes it made', async function (assert) {
    const row = await rowFor(
      thread({ operations: [summary({ steps_done: 2, steps_total: 3 })] }),
    );

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('Anna Example · 2 of 3 changes');
  });

  test('a running agent is counted off the fast poll', async function (assert) {
    board().inFlight = [
      operation({
        state: 'running',
        plan: [
          { text: 'a', file: null, done: true },
          { text: 'b', file: null, done: false },
        ],
      }),
    ];

    const row = await rowFor(
      thread({
        state: 'working',
        operations: [
          summary({ state: 'running', steps_done: 0, steps_total: 2 }),
        ],
      }),
    );

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('Anna Example · running · 1/2');
  });

  test('a reply that came back while the agent runs again says both', async function (assert) {
    const row = await rowFor(board().threadIn('queued', { reopened: true }));

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('Anna Example replied · agent re-running');
  });

  test('a verb waiting for the board says what it is doing', async function (assert) {
    const row = await rowFor(
      thread({
        operations: [
          summary(),
          summary({ id: 'op_1', kind: 'resolve', state: 'pending' }),
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).hasText('resolving…');
  });

  test('a declined run says why', async function (assert) {
    const row = await rowFor(board().threadIn('declined'));

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('skipped: only the author can choose between the two');
  });

  test('a refused push says why in words, not in git output', async function (assert) {
    const row = await rowFor(board().threadIn('push failed'));

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('push failed: GitHub has newer commits on the PR branch');
  });

  test('a refused reply says why in words, not by node id', async function (assert) {
    const row = await rowFor(board().threadIn('reply failed'));

    assert
      .dom(`${row} [data-test-meta]`)
      .hasText('reply failed: GitHub could not find this thread');
  });

  test('a landed thread says how it ended', async function (assert) {
    const row = await rowFor(board().threadIn('landed'));

    assert.dom(`${row} [data-test-meta]`).hasText('Pushed');
  });

  test('a reviewer reads who answered, by login when the board has no name', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(
      thread({
        comments: [
          { id: 1, author: 'octocat', created_at: null, review_state: null },
          { id: 2, author: 'ben', created_at: null, review_state: null },
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).hasText('ben replied');
  });

  test('a waiting thread nobody but a colleague spoke on never reads "You replied"', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(
      thread({
        state: 'waiting',
        comments: [
          { id: 1, author: 'ben', created_at: null, review_state: null },
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).hasText("ben's thread · ben");
  });

  test('a thread no verdict has placed yet says it is not yet read', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(board().threadIn('answered', { unread: true }));

    assert.dom(`${row} [data-test-meta]`).includesText('not yet read');
  });

  test('a thread a verdict put in my move is read', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(board().threadIn('answered'));

    assert.dom(`${row} [data-test-meta]`).doesNotIncludeText('not yet read');
  });

  test('a waiting PR description never reads "You replied"', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(
      thread({
        kind: 'pr-body',
        state: 'waiting',
        comments: [
          { id: null, author: 'mei', created_at: null, review_state: null },
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).doesNotIncludeText('You replied');
  });

  test('a waiting bot summary never reads "You replied"', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(
      thread({
        kind: 'issue',
        state: 'waiting',
        author_kind: 'bot',
        comments: [
          { id: 3, author: 'claude', created_at: null, review_state: null },
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).doesNotIncludeText('You replied');
  });

  test('a waiting thread whose newest comment is the viewer\'s reads "You replied"', async function (assert) {
    board().actAs('reviewer');

    const row = await rowFor(
      thread({
        state: 'waiting',
        comments: [
          { id: 1, author: 'ben', created_at: null, review_state: null },
          { id: 2, author: 'octocat', created_at: null, review_state: null },
        ],
      }),
    );

    assert.dom(`${row} [data-test-meta]`).hasText('You replied');
  });
});

module('Acceptance | rail | the state a row carries', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  test('each row carries the state of its heading, and a reopened one its own', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'ready' }),
      thread({ key: 'reopened', reopened: true }),
      board().threadIn('landing', { key: 'landing' }),
      board().threadIn('deferred', { key: 'deferred' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('#c-ready').hasAttribute('data-square', 'ready');
    assert.dom('#c-reopened').hasAttribute('data-square', 'reopened');
    assert.dom('#c-landing').hasAttribute('data-square', 'working');
    assert.dom('#c-deferred').hasAttribute('data-square', 'waiting');
    assert
      .dom('#c-ready')
      .hasClass('edge', 'the rail and the wall draw one edge');
  });

  test('what needs a look carries the failed state and says which it is, a proposal only its decision', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'proposed' }),
      board().threadIn('failed', { key: 'failed' }),
      board().threadIn('declined', { key: 'declined' }),
      board().threadIn('push failed', { key: 'push' }),
      board().threadIn('reply failed', { key: 'reply' }),
      board().threadIn('removed', { key: 'removed' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('#c-proposed').hasAttribute('data-square', 'ready');
    assert.dom('#c-proposed [data-test-alert]').doesNotExist();
    const chips = {
      failed: 'Agent gave up',
      declined: 'Agent declined',
      push: 'Push failed',
      reply: 'Reply failed',
      removed: 'Comment removed',
    };
    for (const [key, chip] of Object.entries(chips)) {
      assert.dom(`#c-${key}`).hasAttribute('data-square', 'failed');
      assert.dom(`#c-${key} [data-test-alert]`).hasText(chip);
    }
  });

  test('a card that needs a look carries the failed state and its chip', async function (assert) {
    board().conversations = [board().threadIn('push failed', { key: 'push' })];

    await visit('/pr/o/r/7/conversations');
    await click('[data-test-view="board"]');

    assert.dom('[data-test-card="push"]').hasAttribute('data-square', 'failed');
    assert
      .dom('[data-test-card="push"] [data-test-alert]')
      .hasText('Push failed');
  });

  test('the open thread’s square says in words what its colour means', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'proposed' }),
      board().threadIn('failed', { key: 'failed' }),
    ];

    await visit('/pr/o/r/7/conversations/proposed');

    assert
      .dom('.panel-head [data-test-square]')
      .hasAttribute('title', 'Your decision')
      .hasAttribute('aria-label', 'Your decision');

    await visit('/pr/o/r/7/conversations/failed');

    assert
      .dom('.panel-head [data-test-square]')
      .hasAttribute('title', 'Needs a look')
      .hasAttribute('aria-label', 'Needs a look');
  });

  test('a rejected thread is done but carries the state of a park', async function (assert) {
    board().conversations = [board().threadIn('rejected', { key: 'rejected' })];

    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-heading="done"]').exists();
    assert.dom('#c-rejected').hasAttribute('data-square', 'waiting');
  });
});
