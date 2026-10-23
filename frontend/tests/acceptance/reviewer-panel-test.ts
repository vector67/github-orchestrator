import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit, click, fillIn, select } from '@ember/test-helpers';
import {
  added,
  comment,
  diffOf,
  operation,
  proposal,
  setupFakeBoard,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import type { CommitVerdict } from 'frontend/data/api';

const KEY = 'PRRT_aa';

function reviewing(board: FakeBoard) {
  board.actAs('reviewer');
  board.viewer = { login: 'vector67', name: null };
  board.people = [{ login: 'mei', name: 'Mei Placeholder' }];
  board.conversations = [
    thread({
      key: KEY,
      comments: [
        {
          id: 1,
          author: 'vector67',
          created_at: null,
          review_state: 'CHANGES_REQUESTED',
        },
        { id: 2, author: 'mei', created_at: null, review_state: null },
      ],
    }),
  ];
  board.comments[KEY] = [
    comment({
      author: 'vector67',
      created_at: null,
      body: 'this skips the missing tax rate',
    }),
    comment({
      id: 2,
      author: 'mei',
      created_at: null,
      review_state: null,
      body: 'moved the guard into _collect()',
    }),
  ];
}

module('Acceptance | reviewer panel', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    reviewing(board());
  });

  test('on your own thread the reply link names who answered you, not yourself', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-reply-open]').hasText('Reply to Mei');
  });

  test('a thread only you have written on offers a plain reply', async function (assert) {
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = [
      comment({
        author: 'vector67',
        created_at: null,
        review_state: null,
        body: 'this skips the missing tax rate',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-reply-open]').hasText('Reply');
  });

  test('a reviewer card draws the thread and no fix', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('#panel-thread').containsText('moved the guard into _collect()');
    assert.dom('#panel-fix [data-test-work-placeholder]').exists();
    assert.dom('[data-test-fix-label]').doesNotExist();
    assert.dom('[data-test-plan]').doesNotExist();
    assert.dom('[data-test-frame]').doesNotExist();
    assert
      .dom('[data-test-draft-body]')
      .doesNotExist('a thread that is not a draft has nothing to compose');
    assert
      .dom('#panel-talk [data-test-reply-open]')
      .exists('the composer is the one thing a reviewer card always offers');
    assert.dom('[data-test-role-line]').hasText('Mei Placeholder replied');
  });

  test('the header says how long ago the thread started, and when on hover', async function (assert) {
    const started = new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString();
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = [
      comment({
        author: 'mei',
        created_at: started,
        review_state: null,
        body: 'this skips the missing tax rate',
      }),
      comment({
        id: 2,
        author: 'vector67',
        created_at: null,
        review_state: null,
        body: 'moved the guard',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-role-line]').hasText('started 3d ago · you replied');
    assert
      .dom('[data-test-role-line] [data-test-started]')
      .hasAttribute('title', new Date(started).toLocaleString());
  });

  test('the header of a thread no verdict has placed says it is not yet read', async function (assert) {
    board().conversations = [
      board().threadIn('answered', { key: KEY, unread: true }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-role-line]').includesText('not yet read');
  });

  test('a parked reviewer card says what it waits for, under the placeholder', async function (assert) {
    const deferred = board().threadIn('deferred', { key: KEY });
    board().conversations = [deferred];
    board().operations[KEY] = [
      operation({
        id: deferred.operations.findLast((one) => one.kind === 'defer')!.id,
        conversation: KEY,
        kind: 'defer',
        until: 'push',
        note: 'Look again once the guard is in.',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const order = [
      'What the author did lands here',
      'waiting until the next push',
      'Look again once the guard is in.',
    ];
    const text = document.querySelector('#panel')?.textContent ?? '';
    assert.deepEqual(
      [...order]
        .reverse()
        .filter((one) => text.includes(one))
        .sort((one, other) => text.indexOf(one) - text.indexOf(other)),
      order,
    );
  });

  test('the reviewer walks the answered rows', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-next]').hasText('Next answered →');
    assert.dom('[data-test-kicker]').includesText('1 of 1 answered');
  });

  test('resolve asks before it writes and offers an empty reply', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="resolve"]');

    assert.strictEqual(
      board().posted.length,
      0,
      'nothing has reached GitHub yet',
    );
    assert.dom('[data-test-dialog-body]').hasValue('');
    assert
      .dom('[data-test-dialog]')
      .includesText("👍 on the author's message")
      .includesText('moves to Done');

    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
      thumbs_up: false,
    });
  });

  test('not fixed opens with the opener in the box and posts a reply', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="not-fixed"]');

    assert.dom('[data-test-dialog-body]').hasValue('Not fixed — ');

    await fillIn('[data-test-dialog-body]', 'Not fixed — still in the loop.');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'reply');
    assert.deepEqual(board().posted[0]!.body, {
      body: 'Not fixed — still in the loop.',
    });
  });

  test('the opener alone will not post: the template is not a reason', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="not-fixed"]');

    assert.dom('[data-test-dialog-submit]').isDisabled();
  });

  test('the opener alone is nothing to lose: cancel closes without asking', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="not-fixed"]');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-close-ask]').doesNotExist();
    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });

  test('defer offers the next push', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="defer"]');

    assert.dom('[data-test-wake] option[value="push"]').exists();
  });

  test('defer is a button that says you choose when', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-decision="defer"]').includesText('Defer until …');
    assert
      .dom('[data-test-decision="defer"]')
      .hasAttribute('data-weight', 'secondary');
  });

  test('defer can wait for a reply on the thread', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="defer"]');

    await select('[data-test-wake]', 'reply');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, { until: 'reply' });
  });

  test('a card parked for a reply says so', async function (assert) {
    const deferred = board().threadIn('deferred', { key: KEY });
    board().conversations = [deferred];
    board().operations[KEY] = [
      operation({
        id: deferred.operations.findLast((one) => one.kind === 'defer')!.id,
        conversation: KEY,
        kind: 'defer',
        until: 'reply',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('#panel')
      .includesText('waiting until someone replies on the thread');
  });

  test('reply on the bar opens the composer rather than deciding', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="reply"]');

    assert.dom('[data-test-reply]').exists('the composer is open');
    assert.strictEqual(board().posted.length, 0);
  });

  test('the composer says where a reply leaves the thread', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-reply-open]');

    assert
      .dom('[data-test-composer-note]')
      .hasText(
        'Posts to GitHub now, on its own, not with your review. No verdict, no resolve; the thread moves to Waiting on author.',
      );
  });

  test('resolve opens with resolving on GitHub and the 👍 unticked and resolves on the board alone', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-resolve]').isNotChecked();
    assert.dom('[data-test-thumbs-up]').isNotChecked();
    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve, posting nothing to GitHub');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
      thumbs_up: false,
    });
  });

  test('the 👍 alone resolves on the board and reacts on GitHub', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="resolve"]');

    await click('[data-test-thumbs-up]');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve on the board and put 👍 on the newest reply');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
    });
  });

  test('a reply with resolving on GitHub unticked says it resolves on the board', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="resolve"]');

    await fillIn('[data-test-dialog-body]', 'Not for me to answer.');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Post reply and resolve on the board');
  });

  test('an empty resolve on GitHub says on its button that it puts 👍 on the newest reply', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="resolve"]');
    await click('[data-test-resolve]');
    await click('[data-test-thumbs-up]');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve on GitHub and put 👍 on the newest reply');

    await fillIn('[data-test-dialog-body]', 'Thanks, that covers it.');

    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Reply and resolve on GitHub');
  });

  test('ticking resolve alone resolves on GitHub with no reaction', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="resolve"]');
    await click('[data-test-resolve]');

    assert.dom('[data-test-thumbs-up]').isNotChecked();
    assert.dom('[data-test-dialog-submit]').hasText('Resolve on GitHub');

    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: true,
      thumbs_up: false,
    });
  });

  test('a written reply is the thanks, so the 👍 tick goes away', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="resolve"]');
    await click('[data-test-resolve]');

    await fillIn('[data-test-dialog-body]', 'Thanks, that covers it.');

    assert.dom('[data-test-thumbs-up]').doesNotExist();
  });

  test('an author card is drawn with its fix', async function (assert) {
    board().actAs('author');
    board().conversations = [board().threadIn('proposed', { key: KEY })];
    board().operations[KEY] = [
      operation({
        id: `${KEY}.1`,
        conversation: KEY,
        plan: [{ text: 'rename it', file: 'src/foo.py', done: true }],
      }),
    ];
    board().proposals[KEY] = [proposal({ id: `${KEY}.1.proposal` })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-work-placeholder]').doesNotExist();
    assert
      .dom('#panel-fix [data-test-fix-label]')
      .hasText('Agent proposal · 1 of 1 changes');
    assert.dom('#panel-fix [data-test-plan]').containsText('rename it');
    assert.dom('#panel-diff [data-test-fold-title]').hasText('Proposed diff');
    assert.dom('[data-test-next]').hasText('Next ready →');
  });

  test("an author card's resolve asks its own question, with no 👍", async function (assert) {
    board().actAs('author');
    board().conversations = [board().threadIn('waiting', { key: KEY })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="resolve"]');

    assert
      .dom('[data-test-dialog-question]')
      .hasText('Resolve this comment on GitHub?');
    assert.dom('[data-test-dialog]').doesNotIncludeText('👍');
    await click('[data-test-dialog-submit]');
    assert.strictEqual(board().posted[0]!.verb, 'resolve');
  });
});

const MENTION = 'IC_mention';

function mentioned(board: FakeBoard, kind: 'issue' | 'pr-body' = 'issue') {
  board.actAs('reviewer');
  board.viewer = { login: 'vector67', name: null };
  board.people = [{ login: 'mei', name: 'Mei Placeholder' }];
  board.conversations = [
    thread({
      key: MENTION,
      github_node_id: MENTION,
      kind,
      mention: true,
      anchor: {
        path: null,
        line: null,
        start_line: null,
        start_side: null,
        side: null,
        original_line: null,
        original_start_line: null,
        original_commit: null,
        is_outdated: false,
      },
      comments: [
        { id: 9, author: 'mei', created_at: null, review_state: null },
      ],
    }),
  ];
  board.comments[MENTION] = [
    comment({
      id: 9,
      author: 'mei',
      review_state: null,
      body: '@vector67 does the export still need the guard?',
    }),
  ];
}

module('Acceptance | mention card', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    mentioned(board());
  });

  test('a mention offers Reply and resolve, Resolve on board, and Defer', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-decision]')].map((one) =>
        one.getAttribute('data-test-decision'),
      ),
      ['resolve-here', 'resolve-on-board', 'defer'],
    );
    assert
      .dom('[data-test-decision="resolve-here"]')
      .includesText('Reply and resolve');
    assert
      .dom('[data-test-decision="resolve-on-board"]')
      .includesText('Resolve on board');
    assert
      .dom('#panel-thread')
      .containsText('does the export still need the guard?');
  });

  test('a mention a verdict put in Waiting keeps Reply and resolve', async function (assert) {
    board().conversations = board().conversations.map((one) => ({
      ...one,
      state: 'waiting' as const,
    }));

    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    assert
      .dom('[data-test-decision="resolve-here"]')
      .includesText('Reply and resolve');
  });

  test('a mention has no reply link under the comment and no line for a proposal', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    assert.dom('[data-test-reply-open]').doesNotExist();
    assert.dom('[data-test-work-placeholder]').doesNotExist();
  });

  test('Reply and resolve opens the decide dialog and will not post without a reply', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    await click('[data-test-decision="resolve-here"]');

    assert.dom('[data-test-dialog]').exists();
    assert.dom('[data-test-dialog-submit]').isDisabled();
    assert.dom('[data-test-delete]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });

  test('Reply and resolve posts the reply and resolves on the board only', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${MENTION}`);
    await click('[data-test-decision="resolve-here"]');

    await fillIn('[data-test-dialog-body]', 'It does, the guard stays.');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'It does, the guard stays.',
      delete_comment: false,
    });
  });

  test('Resolve on board closes the mention with nothing posted to GitHub', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    await click('[data-test-decision="resolve-on-board"]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      thumbs_up: false,
    });
  });

  test('a deferred mention comes back or is answered, never resolved on GitHub', async function (assert) {
    board().conversations = [
      board().threadIn('deferred', { key: MENTION, mention: true }),
    ];

    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-decision]')].map((one) =>
        one.getAttribute('data-test-decision'),
      ),
      ['unpark', 'resolve-here'],
    );
  });

  test('a mention in the PR description is placed as the PR description', async function (assert) {
    mentioned(board(), 'pr-body');

    await visit(`/pr/o/r/7/conversations/${MENTION}`);

    assert.dom('[data-test-kicker]').includesText('PR description');
  });
});

module('Acceptance | a commit a reply names', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function checked(verdict: CommitVerdict, reasoning: string) {
    const diff = diffOf('src/tax.py', added(12, '    if rate is None: raise'));
    board().diffs['named commit'] = diff;
    board().conversations = [
      {
        ...board().conversations[0]!,
        commit_check: {
          sha: diff.head,
          parent: diff.base,
          verdict,
          reasoning,
        },
      },
    ];
    return diff;
  }

  hooks.beforeEach(function () {
    reviewing(board());
  });

  test('the panel says what the check made of the commit, where the placeholder was', async function (assert) {
    checked('not-addressed', 'it moves the guard but still skips the rate');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-work-placeholder]').doesNotExist();
    assert
      .dom('#panel-fix [data-test-commit-verdict]')
      .hasText('Not addressed');
    assert
      .dom('#panel-fix [data-test-commit-reasoning]')
      .hasText('it moves the guard but still skips the rate');
  });

  test('the panel draws the commit the reply names', async function (assert) {
    const diff = checked('addressed', 'the guard now raises');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('#panel-diff [data-test-fold-title]')
      .hasText(`Commit ${diff.head.slice(0, 7)}`);
    assert
      .dom('#panel-diff [data-test-frame]')
      .containsText('if rate is None: raise');
  });

  test('a partly addressed commit says so', async function (assert) {
    checked('partly', 'one caller still skips it');

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('#panel-fix [data-test-commit-verdict]')
      .hasText('Partly addressed');
  });
});

module('Acceptance | placing a thread an agent placed', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function outcomes(): string[] {
    return [...document.querySelectorAll('[data-test-outcome]')].map(
      (node) => node.closest('label')?.textContent?.trim() ?? '',
    );
  }

  function offers(): string[] {
    return [...document.querySelectorAll('[data-test-decision]')].map(
      (node) => node.getAttribute('data-test-decision') ?? '',
    );
  }

  hooks.beforeEach(function () {
    board().actAs('reviewer');
  });

  test('an assumed done card offers Confirm, which asks only whether to resolve on GitHub and put 👍 there, both ticked', async function (assert) {
    board().conversations = [board().threadIn('assumed-done', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(offers().slice(0, 2), ['confirm-resolve', 'place']);
    assert.dom('[data-test-decision="place"]').includesText('Not confirm');
    await click('[data-test-decision="confirm-resolve"]');

    assert.dom('[data-test-dialog-body]').doesNotExist();
    assert.dom('[data-test-resolve]').isChecked();
    assert.dom('[data-test-thumbs-up]').isChecked();
    assert.dom('[data-test-dialog-submit]').hasText('Confirm');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'resolve');
    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: true,
    });
  });

  test('confirm with resolving unticked keeps the thread open on GitHub and still puts 👍 there', async function (assert) {
    board().conversations = [board().threadIn('assumed-done', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="confirm-resolve"]');

    await click('[data-test-resolve]');

    assert.dom('[data-test-thumbs-up]').isChecked();
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
    });
  });

  test('a mention in a review thread offers Confirm and Not confirm first, with its replies on the right', async function (assert) {
    board().conversations = [
      board().threadIn('assumed-done', { key: KEY, mention: true }),
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      [...document.querySelectorAll('[data-test-decision]')].map((node) => [
        node.getAttribute('data-test-decision'),
        node.getAttribute('data-weight'),
      ]),
      [
        ['confirm-resolve', 'primary'],
        ['place', 'secondary'],
        ['resolve-here', 'ghost'],
        ['resolve-on-board', 'ghost'],
      ],
    );
  });

  test('confirm on a mention outside a review thread still only moves it to Done on the board', async function (assert) {
    board().conversations = [
      board().threadIn('assumed-done', {
        key: KEY,
        mention: true,
        kind: 'issue',
      }),
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="confirm"]');

    assert.strictEqual(board().posted[0]!.verb, 'confirm');
    assert.deepEqual(board().posted[0]!.body, {});
  });

  test('not confirm lists the outcomes the thread could be in apart from Done', async function (assert) {
    board().conversations = [board().threadIn('assumed-done', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-decision="place"]');

    assert.deepEqual(outcomes(), [
      'My move',
      'Their move',
      'Not my conversation',
      'Later…',
    ]);
    await click('[data-test-outcome="waiting"]');
    await click('[data-test-dialog-submit]');
    assert.strictEqual(board().posted[0]!.verb, 'place');
    assert.deepEqual(board().posted[0]!.body, { to: 'waiting' });
  });

  test('a not my conversation card offers Move… and Resolve, and Move… leaves out where it is', async function (assert) {
    board().conversations = [board().threadIn('not-mine', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(offers(), ['place', 'resolve', 'reply']);
    assert.dom('[data-test-decision="place"]').includesText('Move…');
    await click('[data-test-decision="place"]');

    assert.deepEqual(outcomes(), ['My move', 'Their move', 'Later…']);
  });

  test('an answered card offers Move…, which leaves out My move', async function (assert) {
    board().conversations = [board().threadIn('answered', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(offers(), [
      'resolve',
      'not-fixed',
      'place',
      'reply',
      'defer',
    ]);
    assert.dom('[data-test-decision="place"]').includesText('Move…');
    await click('[data-test-decision="place"]');

    assert.deepEqual(outcomes(), [
      'Their move',
      'Not my conversation',
      'Later…',
    ]);
    await click('[data-test-outcome="waiting"]');
    await click('[data-test-dialog-submit]');
    assert.deepEqual(board().posted[0]!.body, { to: 'waiting' });
  });

  test('a waiting card offers Move…, which leaves out Their move', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(offers(), ['resolve', 'defer', 'place', 'reply']);
    await click('[data-test-decision="place"]');

    assert.deepEqual(outcomes(), ['My move', 'Not my conversation', 'Later…']);
  });

  test('later… opens the defer dialog, which defers the thread', async function (assert) {
    board().conversations = [board().threadIn('not-mine', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-decision="place"]');

    await click('[data-test-outcome="later"]');
    await click('[data-test-dialog-submit]');

    assert.dom('[data-test-outcome]').doesNotExist();
    assert.dom('[data-test-wake]').exists();
    await click('[data-test-dialog-submit]');
    assert.strictEqual(board().posted[0]!.verb, 'defer');
  });

  test('on my own pull request not confirm offers a fix, a reply of mine or their move', async function (assert) {
    board().actAs('author');
    board().conversations = [
      board().threadIn('declined', {
        key: KEY,
        state: 'assumed-done',
        record_state: 'assumed_done',
      }),
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(offers().slice(0, 2), ['confirm', 'place']);
    await click('[data-test-decision="place"]');

    assert.deepEqual(outcomes(), [
      'Needs a fix',
      'Needs a reply from me',
      'Their move',
      'Later…',
    ]);
    await click('[data-test-outcome="queued"]');
    await click('[data-test-dialog-submit]');
    assert.deepEqual(board().posted[0]!.body, { to: 'queued' });
  });

  test('a confirmed card offers Reopen', async function (assert) {
    board().conversations = [board().threadIn('confirmed', { key: KEY })];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-decision="unpark"]').includesText('Reopen');
  });
});
