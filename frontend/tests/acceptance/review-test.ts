import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  fillIn,
  triggerKeyEvent,
  visit,
} from '@ember/test-helpers';
import type { Conversation } from 'frontend/data/api';
import {
  comment,
  operation,
  setupFakeBoard,
  thread,
  type FakeBoard,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const SLOW = 5000;

function draft(key: string, over: Partial<Conversation> = {}): Conversation {
  return thread({
    key,
    github_node_id: null,
    kind: 'draft',
    state: 'enrolled',
    etag: `"${key}-v1"`,
    gist: null,
    comments: [
      { id: null, author: 'octocat', created_at: null, review_state: null },
    ],
    ...over,
  });
}

function seed(board: FakeBoard) {
  board.actAs('reviewer');
  board.conversations = [
    draft('draft_a'),
    draft('draft_b', {
      anchor: { ...thread().anchor, path: 'src/bar.py', line: 7 },
    }),
    draft('draft_c', { state: 'draft' }),
    thread({
      key: 'PRRT_w',
      state: 'waiting',
      comments: [
        { id: 5, author: 'octocat', created_at: null, review_state: null },
      ],
    }),
  ];
  board.comments['draft_a'] = [
    comment({ id: null, author: 'octocat', body: 'this leaks' }),
  ];
  board.comments['draft_b'] = [
    comment({ id: null, author: 'octocat', body: 'why a list?' }),
  ];
}

module('Acceptance | send review', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    seed(board());
  });

  async function opened() {
    await visit('/pr/o/r/7/conversations');
    await click('[data-test-send-review]');
  }

  function sent() {
    return board().posted.filter((one) => one.verb === 'send-review');
  }

  test('the head says how many drafts the review carries', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.dom('[data-test-send-review]').hasText('Send review · 2');
  });

  test('the modal asks for a verdict, Comment first', async function (assert) {
    await opened();

    assert.dom('[data-test-review]').exists();
    assert.dom('[data-test-verdict="COMMENT"]').isChecked();
    assert.dom('[data-test-verdict="REQUEST_CHANGES"]').isNotChecked();
    assert.dom('[data-test-verdict="APPROVE"]').isNotChecked();
  });

  test('the modal takes the focus and hands it back on escape', async function (assert) {
    await opened();

    assert
      .dom('[data-test-review] [role="dialog"]')
      .hasAttribute('aria-modal', 'true');
    assert.dom('[data-test-verdict="COMMENT"]').isFocused();

    await triggerKeyEvent(document, 'keydown', 'Escape');

    assert.dom('[data-test-review]').doesNotExist();
    assert.dom('[data-test-send-review]').isFocused();
  });

  test('the drafts going out are listed with where they sit and what they say', async function (assert) {
    await opened();

    const rows = document.querySelectorAll('[data-test-review-draft]');
    assert.strictEqual(rows.length, 2);
    assert.dom(rows[0]).containsText('src/foo.py:42');
    assert.dom(rows[0]).containsText('this leaks');
    assert.dom(rows[1]).containsText('src/bar.py:7');
    assert.dom(rows[1]).containsText('why a list?');
  });

  module('with a review left pending on GitHub', function (hooks) {
    hooks.beforeEach(function () {
      board().conversations.push(
        thread({
          key: 'PRRT_p',
          state: 'waiting',
          anchor: { ...thread().anchor, path: 'src/baz.py', line: 3 },
          comments: [
            {
              id: 9,
              author: 'octocat',
              created_at: null,
              review_state: 'PENDING',
            },
          ],
        }),
      );
      board().comments['PRRT_p'] = [
        comment({
          id: 9,
          author: 'octocat',
          body: 'drafted on github',
          review_state: 'PENDING',
        }),
      ];
    });

    test('its drafts go out with the review, marked as from GitHub', async function (assert) {
      await opened();

      assert
        .dom('[data-test-review-github-draft="PRRT_p"]')
        .containsText('src/baz.py:3')
        .containsText('drafted on github')
        .containsText('from GitHub');
      assert
        .dom('[data-test-review-github-draft="PRRT_p"] [data-test-leave-out]')
        .doesNotExist();
    });

    test('its drafts are not threads the author has left unanswered', async function (assert) {
      await opened();

      assert
        .dom('[data-test-left-open]')
        .hasText(
          'Left open: 1 thread of yours the author has not answered, and ' +
            '1 draft you have not added.',
        );
    });
  });

  test('a comment or a change request is not sent without a summary', async function (assert) {
    await opened();

    assert.dom('[data-test-review-send]').isDisabled();
    await click('[data-test-verdict="REQUEST_CHANGES"]');
    await fillIn('[data-test-review-body]', '   ');
    assert.dom('[data-test-review-send]').isDisabled();
    await fillIn('[data-test-review-body]', 'two leaks');
    assert.dom('[data-test-review-send]').isNotDisabled();
  });

  test('an approval goes without a summary', async function (assert) {
    await opened();

    await click('[data-test-verdict="APPROVE"]');
    await click('[data-test-review-send]');

    assert.strictEqual(sent().length, 1);
    assert.strictEqual(sent()[0]?.url, '/api/operations:send-review');
    assert.strictEqual(sent()[0]?.ifMatch, null);
    assert.deepEqual(sent()[0]?.body, { verdict: 'APPROVE', body: null });
  });

  test('a review is sent with its verdict and summary', async function (assert) {
    await opened();

    await click('[data-test-verdict="REQUEST_CHANGES"]');
    await fillIn('[data-test-review-body]', 'two leaks');
    await click('[data-test-review-send]');

    assert.deepEqual(sent()[0]?.body, {
      verdict: 'REQUEST_CHANGES',
      body: 'two leaks',
    });
    assert.dom('[data-test-review-state]').hasText('Sending your review…');
    assert.dom('[data-test-review-send]').isDisabled();
  });

  test('the review is followed at its location until GitHub has it', async function (assert) {
    await opened();
    await fillIn('[data-test-review-body]', 'two leaks');
    await click('[data-test-review-send]');
    const id = Object.keys(board().reviews)[0]!;

    await clock().tick(SLOW);
    assert.ok(board().askedFor(new RegExp(`/api/operations/${id}$`)).length);
    assert.dom('[data-test-review]').exists('still going out');

    board().reviews[id] = operation({
      id,
      conversation: null,
      kind: 'send-review',
      state: 'applied',
    });
    await clock().tick(SLOW);

    assert.dom('[data-test-review]').doesNotExist();
    assert.dom('[data-test-toast]').hasText('Sent: your review is on GitHub.');
  });

  test('a review GitHub turns down says so in its words, and can be sent again', async function (assert) {
    await opened();
    await fillIn('[data-test-review-body]', 'two leaks');
    await click('[data-test-review-send]');
    const id = Object.keys(board().reviews)[0]!;
    board().reviews[id] = operation({
      id,
      conversation: null,
      kind: 'send-review',
      state: 'refused',
      reason_code: 'github-rejected',
      reason: 'Validation Failed: pull_request_review_thread.line is invalid',
    });

    await clock().tick(SLOW);

    assert
      .dom('[data-test-review-trouble]')
      .hasText(
        'GitHub refused the review: Validation Failed: ' +
          'pull_request_review_thread.line is invalid. Every draft is ' +
          'still in it.',
      );
    assert.dom('[data-test-review-send]').isNotDisabled();
  });

  test('a refusal is not reported: the board logged it as it answered', async function (assert) {
    await opened();
    await fillIn('[data-test-review-body]', 'two leaks');
    board().refusal = {
      status: 409,
      code: 'review-in-flight',
      detail: 'a review is already going out',
    };

    await click('[data-test-review-send]');

    assert.deepEqual(board().reported, []);
  });

  test('a review already going out is said in the modal', async function (assert) {
    await opened();
    await fillIn('[data-test-review-body]', 'two leaks');
    board().refusal = {
      status: 409,
      code: 'review-in-flight',
      detail: 'a review is already going out',
    };

    await click('[data-test-review-send]');

    assert
      .dom('[data-test-review-trouble]')
      .hasText(
        'A review is already on its way to GitHub; wait for it to land.',
      );
  });

  test('leaving a draft out takes it back out of the review', async function (assert) {
    await opened();

    await click('[data-test-review-draft="draft_b"] [data-test-leave-out]');

    const asked = board().posted.at(-1);
    assert.strictEqual(
      asked?.url,
      '/api/conversations/draft_b/operations:withdraw-from-review',
    );
    assert.strictEqual(asked?.ifMatch, '"draft_b-v1"');
  });

  test('the drafts not added are listed apart, where they sit and what they say, and each can be added', async function (assert) {
    board().comments['draft_c'] = [
      comment({ id: null, author: 'octocat', body: 'a half thought' }),
    ];
    await opened();

    const left = document.querySelectorAll('[data-test-review-unadded]');
    assert.strictEqual(left.length, 1);
    assert.dom(left[0]).containsText('src/foo.py:42');
    assert.dom(left[0]).containsText('a half thought');
    assert
      .dom('[data-test-review-draft="draft_c"]')
      .doesNotExist('it is not among those going out');

    await click('[data-test-review-unadded="draft_c"] [data-test-add]');

    const asked = board().posted.at(-1);
    assert.strictEqual(
      asked?.url,
      '/api/conversations/draft_c/operations:enrol',
    );
    assert.strictEqual(asked?.ifMatch, '"draft_c-v1"');
    assert.strictEqual(sent().length, 0, 'nothing is sent by adding');
  });

  test('it says the review is public and cannot be taken back', async function (assert) {
    await opened();

    assert
      .dom('[data-test-review-public]')
      .hasText(
        'Sending posts the review to GitHub now; the board cannot take it back.',
      );
  });

  test('editing a draft opens it and leaves it in the review', async function (assert) {
    await opened();
    const asked = board().posted.length;

    await click('[data-test-review-draft="draft_a"] [data-test-edit]');

    assert.strictEqual(board().posted.length, asked);
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/draft_a');
    assert.dom('[data-test-review]').doesNotExist();
  });

  test('a draft in a review on its way to GitHub opens locked', async function (assert) {
    await opened();
    await fillIn('[data-test-review-body]', 'two leaks');
    await click('[data-test-review-send]');

    await click('[data-test-review-draft="draft_a"] [data-test-edit]');

    assert.dom('[data-test-draft-body]').isDisabled();
    assert
      .dom('[data-test-draft-note]')
      .hasText(
        'On its way to GitHub; it cannot change until the board has it.',
      );
  });

  test('S opens the review from anywhere on the board', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerKeyEvent(document, 'keydown', 'S');

    assert.dom('[data-test-review]').exists();
  });

  test('the modal closes without sending anything', async function (assert) {
    await opened();

    await click('[data-test-review-close]');

    assert.dom('[data-test-review]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });
});

module(
  'Acceptance | send review | what it carries and leaves',
  function (hooks) {
    setupApplicationTest(hooks);
    const board = setupFakeBoard(hooks);

    hooks.beforeEach(function () {
      board().actAs('reviewer');
    });

    test('the enrolled drafts go out, in the order the list has them', async function (assert) {
      board().conversations = [
        draft('d2'),
        draft('d1', { state: 'draft' }),
        draft('d3', { anchor: { ...thread().anchor, path: 'b.py', line: 3 } }),
      ];
      board().comments['d3'] = [
        comment({ id: null, author: 'octocat', body: 'why a list?' }),
      ];

      await visit('/pr/o/r/7/conversations');
      await click('[data-test-send-review]');

      const rows = [...document.querySelectorAll('[data-test-review-draft]')];
      assert.deepEqual(
        rows.map((one) => one.getAttribute('data-test-review-draft')),
        ['d2', 'd3'],
        'a draft not added stays out, and the list order holds',
      );
      assert
        .dom(rows[0])
        .hasText('src/foo.py:42 Edit Leave out', 'a draft with no words yet');
      assert.dom(rows[1]).containsText('b.py:3');
      assert.dom(rows[1]).containsText('why a list?');
    });

    test('it counts the drafts not added and your threads the author has not answered', async function (assert) {
      board().conversations = [
        draft('d1', { state: 'draft' }),
        draft('d2', { state: 'draft' }),
        board().threadIn('waiting', { key: 'w1' }),
        thread({ key: 'w2', state: 'waiting' }),
        board().threadIn('answered', { key: 'r1' }),
      ];

      await visit('/pr/o/r/7/conversations');
      await click('[data-test-send-review]');

      assert
        .dom('[data-test-left-open]')
        .hasText(
          'Left open: 1 thread of yours the author has not answered, and ' +
            '2 drafts you have not added.',
          "another's waiting thread and your answered one are not left open",
        );
    });
  },
);
