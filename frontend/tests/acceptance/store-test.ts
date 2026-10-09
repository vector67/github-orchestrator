import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  findAll,
  settled,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
  threadRow as row,
  type HeldOver,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

const LAGGING: HeldOver = {
  dashboard: {
    system: { threads: { queued: 0, live: 0, proposed: 3, drafts: 4 } },
  },
};

module('Acceptance | one store', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function onTheHub(...held: HeldOver[]): void {
    board().serves = 'hub';
    board().held = held.map((one) => heldPr({ ...LAGGING, ...one }));
  }

  function chips(): string[] {
    return findAll('[data-test-pr-bar] [data-test-pr-count]').map((one) =>
      one.textContent.trim().replace(/\s+/g, ' '),
    );
  }

  function badge(): string | null {
    return (
      document
        .querySelector('[data-test-tab="board"] [data-test-tab-count]')
        ?.textContent?.trim() ?? null
    );
  }

  test('the bar counts the threads on your pull request, leaving out your own and the unsent, whatever the hub’s copy says', async function (assert) {
    onTheHub({});
    board().conversations = [
      board().threadIn('landed', { key: 'h1' }),
      board().threadIn('waiting', { key: 'h2' }),
      board().threadIn('proposed', { key: 'h3' }),
      board().threadIn('working', { key: 'b1', author_kind: 'bot' }),
      board().threadIn('resolved', { key: 'b2', author_kind: 'bot' }),
      board().threadIn('waiting', { key: 'm1', author_kind: 'mine' }),
      board().threadIn('draft', { key: 'd1' }),
    ];

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), [
      'Human comments 2/3 done',
      'Bot comments 1/2 done',
    ]);
    assert.strictEqual(badge(), '1 ready, 1 draft');
  });

  test('on someone else’s pull request the bar counts your threads answered from the threads', async function (assert) {
    onTheHub({
      dashboard: { facts: { is_author: false }, pr: { author: 'erin' } },
    });
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('resolved', { key: 'r' }),
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('deferred', { key: 'f' }),
      board().threadIn('draft', { key: 'd' }),
    ];

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), ['Your threads 2/4 answered']);
    assert.strictEqual(badge(), '1 answered, 1 draft');
  });

  test('on someone else’s pull request the Board tab and the strip count the same answered threads', async function (assert) {
    onTheHub({
      dashboard: { facts: { is_author: false }, pr: { author: 'erin' } },
    });
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('answered', { key: 'o', author_kind: 'human' }),
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('draft', { key: 'd' }),
    ];

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), ['Your threads 1/2 answered']);
    assert.strictEqual(badge(), '2 answered, 1 draft');
    await visit('/pr/o/r/7/conversations');
    assert
      .dom('#board-strip [data-test-count="ready"]')
      .hasText('2 answered', 'the strip counts the same two');
  });

  test('whose pull request it is comes from its facts alone, so the rail, the bar and NEXT read the same role', async function (assert) {
    onTheHub({
      dashboard: { facts: { is_author: false }, pr: { author: 'erin' } },
    });
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('waiting', { key: 'w' }),
    ];

    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-heading="ready"]').includesText('Answered');
    assert.deepEqual(chips(), ['Your threads 1/2 answered']);
    assert
      .dom('[data-test-your-move]')
      .hasAttribute('data-move', 'not-reviewing');
  });

  test('until the facts say whose pull request it is, nothing that depends on it is drawn', async function (assert) {
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('answered', { key: 'a' }),
      board().threadIn('waiting', { key: 'w' }),
    ];
    board().manager = dashboard({ facts: null, polled: false });

    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-heading]').doesNotExist();
    assert.dom('[data-test-board-waiting]').exists();
    assert.deepEqual(chips(), []);
    assert.dom('[data-test-your-move]').hasAttribute('data-move', 'first-poll');

    board().manager = dashboard({ facts: { is_author: false } });
    await clock().tick(LIST);

    assert.dom('[data-test-heading="ready"]').includesText('Answered');
    assert.deepEqual(chips(), ['Your threads 1/2 answered']);
  });

  test('an assumed done thread counts as done and one that is not mine is left out', async function (assert) {
    onTheHub({});
    board().conversations = [
      board().threadIn('landed', { key: 'h1' }),
      board().threadIn('proposed', { key: 'h2' }),
      board().threadIn('waiting', {
        key: 'h3',
        state: 'assumed-done',
        record_state: 'assumed_done',
      }),
      board().threadIn('waiting', {
        key: 'h4',
        state: 'not-mine',
        record_state: 'not_mine',
      }),
    ];

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), [
      'Human comments 2/3 done',
      'Bot comments 0/0 done',
    ]);
  });

  test('on someone else’s pull request your assumed done thread is answered and your not mine one is left out', async function (assert) {
    onTheHub({
      dashboard: { facts: { is_author: false }, pr: { author: 'erin' } },
    });
    board().actAs('reviewer');
    board().conversations = [
      board().threadIn('waiting', { key: 'w' }),
      board().threadIn('assumed-done', { key: 'a' }),
      board().threadIn('not-mine', { key: 'n', author_kind: 'mine' }),
    ];

    await visit('/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), ['Your threads 1/2 answered']);
  });

  test('after an accept the bar, the Board tab and the strip agree with the list at once', async function (assert) {
    onTheHub({
      dashboard: {
        system: { threads: { queued: 0, live: 0, proposed: 1, drafts: 0 } },
      },
    });
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), '1 ready');

    board().conversations = [board().threadIn('landed', { key: 'k1' })];
    await click('[data-test-decision="approve"]');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(chips(), [
      'Human comments 1/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), null);
    assert
      .dom('#board-strip [data-test-count="done"]')
      .containsText('1', 'the strip counts it done');
  });

  test('a hub row fills the record of a pull request whose page is not open, so its bar counts before its threads are read', async function (assert) {
    const threads = [
      row('h1', 'done', 'resolved', 'human'),
      row('h2', 'ready', 'open', 'human'),
      row('b1', 'working', 'open', 'bot'),
      row('d1', 'draft', 'draft', 'human'),
    ];
    onTheHub({}, { number: 8, dashboard: { threads } });
    await visit('/pr/o/r/7/dashboard');

    const release = board().hold(
      /^\/pr\/o\/r\/8\/api\/(conversations$|dashboard)/,
    );
    void visit('/pr/o/r/8/dashboard');
    await waitUntil(() => currentURL() === '/pr/o/r/8/dashboard');

    assert.deepEqual(chips(), [
      'Human comments 1/2 done',
      'Bot comments 0/1 done',
    ]);
    release();
    await settled();
  });

  test('a hub row newer than the thread the page read merges into that one thread, so the chips, the strip and NEXT agree', async function (assert) {
    const read = row('k1', 'ready', 'open', 'human', '2026-10-08T09:00:00Z');
    onTheHub({ dashboard: { threads: [read] } });
    board().conversations = [
      board().threadIn('proposed', {
        key: 'k1',
        updated_at: '2026-10-08T09:00:00Z',
      }),
    ];
    await visit('/pr/o/r/7/conversations');
    assert.dom('#board-strip [data-test-count="ready"]').hasText('1 ready');

    board().held = [
      heldPr({
        ...LAGGING,
        dashboard: {
          ...LAGGING.dashboard,
          threads: [
            row('k1', 'done', 'resolved', 'human', '2026-10-08T10:00:00Z'),
          ],
        },
      }),
    ];
    await clock().tick(LIST);

    assert.deepEqual(chips(), [
      'Human comments 1/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.dom('#board-strip [data-test-count="ready"]').doesNotExist();
    assert.dom('#board-strip [data-test-count="done"]').containsText('1');
    assert
      .dom('[data-test-your-move]')
      .hasAttribute('data-move', 'await-review');
  });

  test('a pull request you come back to shows its counts before its threads are read again', async function (assert) {
    onTheHub({}, { number: 8 });
    const proposed = board().threadIn('proposed', { key: 'k1' });
    board().held = [
      heldPr({
        ...LAGGING,
        dashboard: {
          ...LAGGING.dashboard,
          threads: [
            row('k1', 'ready', 'open', 'human', proposed.updated_at ?? ''),
          ],
        },
      }),
      heldPr({ ...LAGGING, number: 8 }),
    ];
    board().conversations = [proposed];
    await visit('/pr/o/r/7/dashboard');
    await visit('/pr/o/r/8/dashboard');
    board().conversations = [];

    const release = board().hold(/^\/pr\/o\/r\/7\/api\/conversations$/);
    void visit('/pr/o/r/7/dashboard');
    await waitUntil(() => currentURL() === '/pr/o/r/7/dashboard');

    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), '1 ready');
    release();
    await settled();
  });

  test('a thread the next list no longer names leaves the page, whichever read listed it', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1' }),
      board().threadIn('proposed', { key: 'k2' }),
    ];
    await visit('/pr/o/r/7/conversations');
    assert.deepEqual(chips(), [
      'Human comments 0/2 done',
      'Bot comments 0/0 done',
    ]);

    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await clock().tick(LIST);

    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), '1 ready');
    assert.dom('#c-k2').doesNotExist();
  });

  test('a hub row read before a thread was saved does not drop that thread', async function (assert) {
    onTheHub({
      dashboard: {
        threads: [row('k1', 'ready', 'open', 'human', '2026-09-12T11:00:00Z')],
        listed_at: '2026-10-08T09:00:00Z',
      },
    });
    board().conversations = [
      board().threadIn('proposed', { key: 'k1' }),
      board().threadIn('proposed', {
        key: 'k2',
        updated_at: '2026-10-08T10:00:00Z',
      }),
    ];
    const release = board().hold(/^\/api\/pull-requests$/);
    void visit('/pr/o/r/7/conversations');
    await waitUntil(() => board().askedFor(/\/api\/operations$/).length > 0);
    await new Promise((done) => setTimeout(done, 50));

    release();
    await settled();

    assert.deepEqual(chips(), [
      'Human comments 0/2 done',
      'Bot comments 0/0 done',
    ]);
  });

  const READ = '2026-09-12T11:00:00Z';
  const ASKED = '2026-09-12T11:00:05Z';
  const SETTLED = '2026-09-12T11:00:09Z';
  const POLLS = /\/api\/(conversations|dashboard|operations|pull-requests)$/;

  async function decided(): Promise<void> {
    const before = board().posted.length;
    await click('[data-test-decision="resolve"]');
    void click('[data-test-dialog-submit]');
    await waitUntil(
      () =>
        board().posted.length > before &&
        document.querySelector('#c-k1[data-provisional]') !== null,
    );
  }

  function asItStoodWithTheVerbWaiting(): void {
    board().conversations = [
      board().threadIn('proposed', {
        key: 'k1',
        updated_at: READ,
        etag: '"k1-resolve-waiting"',
      }),
    ];
  }

  function railRow(): Element | null {
    return document.querySelector('#c-k1');
  }

  test('a click moves the chips, the Board tab badge, NEXT and the row before any poll answers', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().projections = {
      k1: board().threadIn('resolved', { key: 'k1', updated_at: ASKED }),
    };
    await visit('/pr/o/r/7/conversations/k1');
    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), '1 ready');
    assert
      .dom('[data-test-your-move]')
      .hasAttribute('data-move', 'human-comments');
    assert.strictEqual(railRow()?.getAttribute('data-group'), 'ready');

    const release = board().hold(POLLS);
    await decided();

    assert.deepEqual(chips(), [
      'Human comments 1/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), null);
    assert
      .dom('[data-test-your-move]')
      .hasAttribute('data-move', 'await-review');
    assert.strictEqual(railRow()?.getAttribute('data-group'), 'done');
    release();
    await settled();
  });

  test('a poll answering the thread as it was before the click leaves the projection, and the settled copy replaces it whatever it says', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', updated_at: READ }),
    ];
    board().projections = {
      k1: board().threadIn('resolved', { key: 'k1', updated_at: ASKED }),
    };
    await visit('/pr/o/r/7/conversations/k1');
    await decided();
    await settled();
    asItStoodWithTheVerbWaiting();
    await clock().tick(LIST);

    assert.strictEqual(railRow()?.getAttribute('data-group'), 'done');
    assert.dom('#c-k1').hasAttribute('data-provisional');
    assert.deepEqual(chips(), [
      'Human comments 1/1 done',
      'Bot comments 0/0 done',
    ]);

    board().conversations = [
      board().threadIn('proposed', { key: 'k1', updated_at: SETTLED }),
    ];
    await clock().tick(LIST);

    assert.strictEqual(railRow()?.getAttribute('data-group'), 'ready');
    assert.dom('#c-k1').doesNotHaveAttribute('data-provisional');
    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
  });

  test('a settled copy stamped in the second the verb was asked replaces the projection', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', updated_at: READ }),
    ];
    board().projections = {
      k1: board().threadIn('landing', { key: 'k1', updated_at: ASKED }),
    };
    await visit('/pr/o/r/7/conversations/k1');
    await decided();
    await settled();

    board().conversations = [
      board().threadIn('resolved', { key: 'k1', updated_at: ASKED }),
    ];
    await clock().tick(LIST);

    assert.strictEqual(railRow()?.getAttribute('data-group'), 'done');
    assert.dom('#c-k1').doesNotHaveAttribute('data-provisional');
  });

  test('on hold the projection stays through every poll until the server’s copy says otherwise', async function (assert) {
    board().manager = dashboard({
      manager: { on_hold: true },
      system: { on_hold: true },
    });
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', updated_at: READ }),
    ];
    board().projections = {
      k1: board().threadIn('resolved', { key: 'k1', updated_at: ASKED }),
    };
    await visit('/pr/o/r/7/conversations/k1');
    await decided();
    await settled();

    asItStoodWithTheVerbWaiting();
    await clock().tick(LIST);
    await clock().tick(LIST);
    await clock().tick(LIST);

    assert.strictEqual(railRow()?.getAttribute('data-group'), 'done');
    assert.strictEqual(badge(), null);

    board().conversations = [
      board().threadIn('proposed', { key: 'k1', updated_at: SETTLED }),
    ];
    await clock().tick(LIST);

    assert.strictEqual(railRow()?.getAttribute('data-group'), 'ready');
    assert.strictEqual(badge(), '1 ready');
  });

  test('a refused write leaves the chips, the badge, NEXT and the row as they were', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().projections = {
      k1: board().threadIn('resolved', { key: 'k1', updated_at: ASKED }),
    };
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 409,
      code: 'operation-outstanding',
      detail: 'thread k1 already has an operation waiting',
    };

    await click('[data-test-decision="resolve"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-toast]').containsText('already on its way');
    assert.deepEqual(chips(), [
      'Human comments 0/1 done',
      'Bot comments 0/0 done',
    ]);
    assert.strictEqual(badge(), '1 ready');
    assert
      .dom('[data-test-your-move]')
      .hasAttribute('data-move', 'human-comments');
    assert.strictEqual(railRow()?.getAttribute('data-group'), 'ready');
    assert.dom('#c-k1').doesNotHaveAttribute('data-provisional');
  });

  test('a full read older than the hub row already held fills in what the row lacks, so the badge counts it', async function (assert) {
    onTheHub(
      {
        dashboard: {
          threads: [
            row('k1', 'ready', 'open', 'human', '2026-10-08T10:00:00Z'),
          ],
        },
      },
      { number: 8 },
    );
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    await visit('/pr/o/r/8/dashboard');

    await visit('/pr/o/r/7/conversations');

    assert.strictEqual(badge(), '1 ready');
    assert.dom('#board-strip [data-test-count="ready"]').hasText('1 ready');
  });
});
