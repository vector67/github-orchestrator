import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  findAll,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  heldPr,
  outstandingMention,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';

function actions(): Element {
  return find('[data-test-mention-actions]')!;
}

function insideTheWindow(box: DOMRect): boolean {
  return (
    box.left >= 0 &&
    box.top >= 0 &&
    box.right <= window.innerWidth &&
    box.bottom <= window.innerHeight
  );
}

function justUnder(box: DOMRect, by: DOMRect): boolean {
  return box.top >= by.bottom && box.top <= by.bottom + 12;
}

function clearOf(box: DOMRect, by: DOMRect): boolean {
  return box.bottom <= by.top || box.top >= by.bottom;
}

function many(count: number) {
  return Array.from({ length: count }, (_, at) =>
    outstandingMention({ thread: `k${at + 1}`, comment_id: at + 1 }),
  );
}

module('Acceptance | mentions', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  async function listed(): Promise<void> {
    await visit('/');
    await click('[data-test-mentions-count]');
  }

  async function opened(key = 'k1'): Promise<void> {
    await listed();
    await click(`[data-test-mention="${key}"] [data-test-mention-more]`);
  }

  test('clicking anywhere on a mention on the board opens its thread', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [thread({ key: 'k1' })];
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];
    await listed();

    await click('[data-test-mention="k1"] [data-test-mention-body]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('each mention’s arrow opens its four actions in order, with Defer still to come', async function (assert) {
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];

    await opened();

    assert.deepEqual(
      findAll('[data-test-mention-action]').map((one) =>
        one.textContent.replace(/\s+/g, ' ').trim(),
      ),
      ['See in context', 'See on GitHub', 'Defer… coming', 'Dismiss'],
    );
    assert.dom('[data-test-mention-action="defer"]').isDisabled();
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-more]')
      .hasAttribute('aria-expanded', 'true');
  });

  test('the actions open over the list by their arrow and move nothing', async function (assert) {
    board().mentions.mentions = many(3);
    await listed();
    const tops = () =>
      findAll('[data-test-mention]').map(
        (row) => row.getBoundingClientRect().top,
      );
    const before = JSON.stringify(tops());
    const arrow = find('[data-test-mention="k2"] [data-test-mention-more]')!;

    await click(arrow);

    const box = actions().getBoundingClientRect();
    const by = arrow.getBoundingClientRect();
    assert.true(actions().matches(':popover-open'), 'it is in the top layer');
    assert.strictEqual(JSON.stringify(tops()), before, 'no row moved');
    assert.true(
      justUnder(box, by),
      `it opens just under its arrow (${box.top} under ${by.bottom})`,
    );
    assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
  });

  test('the actions of the last mention in a long list stay inside the window', async function (assert) {
    board().mentions.mentions = many(30);
    await listed();
    const list = find('[data-test-mentions-menu]')!;
    list.scrollTop = list.scrollHeight;
    const arrow = find('[data-test-mention="k30"] [data-test-mention-more]')!;

    await click(arrow);

    const box = actions().getBoundingClientRect();
    assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
    assert.true(
      clearOf(box, arrow.getBoundingClientRect()),
      'it covers not its own arrow',
    );
  });

  for (const corner of [
    { right: '2px', bottom: '2px' },
    { left: '2px', bottom: '2px' },
    { left: '2px', top: '2px' },
  ]) {
    test(`the actions of an arrow in the window’s corner at ${JSON.stringify(corner)} stay inside the window`, async function (assert) {
      board().mentions.mentions = many(1);
      await listed();
      const arrow = find(
        '[data-test-mention="k1"] [data-test-mention-more]',
      ) as HTMLElement;
      Object.assign(arrow.style, { position: 'fixed', ...corner });

      await click(arrow);

      const box = actions().getBoundingClientRect();
      const by = arrow.getBoundingClientRect();
      assert.true(insideTheWindow(box), `it fits (${JSON.stringify(box)})`);
      assert.true(clearOf(box, by), 'it covers not its own arrow');
    });
  }

  test('Escape closes the actions and leaves the list open', async function (assert) {
    board().mentions.mentions = many(1);
    await opened();

    await triggerEvent(document.activeElement!, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-mention-actions]').doesNotExist();
    assert.dom('[data-test-mentions-menu]').exists();
  });

  test('a click outside the actions closes them', async function (assert) {
    board().mentions.mentions = many(2);
    await opened();

    await triggerEvent('[data-test-mentions-menu]', 'mousedown');

    assert.dom('[data-test-mention-actions]').doesNotExist();
  });

  test('scrolling the list closes the actions', async function (assert) {
    board().mentions.mentions = many(30);
    await opened();
    const list = find('[data-test-mentions-menu]')!;

    list.scrollTop = 40;
    await triggerEvent(list, 'scroll');

    assert.dom('[data-test-mention-actions]').doesNotExist();
  });

  test('resizing the window closes the actions', async function (assert) {
    board().mentions.mentions = many(1);
    await opened();

    await triggerEvent(window, 'resize');

    assert.dom('[data-test-mention-actions]').doesNotExist();
  });

  test('See in context opens the mention’s thread', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [thread({ key: 'k1' })];
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];
    await opened();

    await click('[data-test-mention-action="context"]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('See in context is off for a mention the board has no card for', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', on_board: false }),
    ];

    await opened();

    assert.dom('[data-test-mention-action="context"]').isDisabled();
  });

  test('See on GitHub opens the comment in a new tab', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        url: 'https://github.com/o/r/pull/7#issuecomment-1',
      }),
    ];

    await opened();

    assert
      .dom('[data-test-mention-action="github"]')
      .hasAttribute('href', 'https://github.com/o/r/pull/7#issuecomment-1')
      .hasAttribute('target', '_blank');
  });

  test('Dismiss clears the mention for good', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
      outstandingMention({ thread: 'k2', comment_id: 2 }),
    ];
    await opened();

    await click('[data-test-mention-action="dismiss"]');

    assert.deepEqual(board().dismissedMentions, [
      { repo: 'o/r', number: 7, comment_id: 1 },
    ]);
    assert.dom('[data-test-mention-actions]').doesNotExist();
    assert.dom('[data-test-mention="k1"]').doesNotExist();
    assert.dom('[data-test-mentions-count]').hasText('1');
  });

  test('a refused Dismiss says why and keeps the mention', async function (assert) {
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];
    await opened();
    board().refusal = {
      status: 400,
      code: 'malformed-request',
      detail: 'repo: String should match pattern',
    };

    await click('[data-test-mention-action="dismiss"]');

    assert.dom('[data-test-toast]').includesText('Mention not dismissed');
    assert.dom('[data-test-mention="k1"]').exists();
    assert.dom('[data-test-mentions-count]').hasText('1');
  });

  test('the counter in the top bar reads 0 when no mention is outstanding', async function (assert) {
    await visit('/');

    assert.dom('[data-test-mentions-count]').hasText('0');
  });

  test('the counter counts every outstanding mention and lists who wrote each one where', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
      outstandingMention({
        repo: 'acme/gadgets',
        number: 3,
        thread: 'k2',
        comment_id: 2,
        author: 'bob',
        on_board: false,
      }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mentions-count]').hasText('2');
    assert
      .dom('[data-test-mention]')
      .exists({ count: 2 }, 'one row for each mention');
    assert.dom('[data-test-mention="k1"]').includesText('anna');
    assert.dom('[data-test-mention="k1"]').includesText('o/r#7');
    assert.dom('[data-test-mention="k2"]').includesText('acme/gadgets#3');
  });

  test('a mention on the board opens its pull request at its thread', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [thread({ key: 'k1' })];
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];
    await visit('/');

    await click('[data-test-mentions-count]');
    await click('[data-test-mention="k1"] [data-test-mention-open]');

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('a mention not on the board says so and links to the comment on GitHub', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        on_board: false,
        url: 'https://github.com/o/r/pull/7#issuecomment-1',
      }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mention="k1"]').includesText('not on the board');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-github]')
      .hasAttribute('href', 'https://github.com/o/r/pull/7#issuecomment-1');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-open]')
      .doesNotExist();
  });

  test('a mention whose card is being built says so and links to the comment on GitHub meanwhile', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        on_board: false,
        building: true,
        url: 'https://github.com/o/r/pull/7#issuecomment-1',
      }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mentions-count]').hasText('1');
    assert.dom('[data-test-mention="k1"]').includesText('card being built');
    assert
      .dom('[data-test-mention="k1"]')
      .doesNotIncludeText('not on the board');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-github]')
      .hasAttribute('href', 'https://github.com/o/r/pull/7#issuecomment-1');
  });

  test('a mention on the board without a thread links to GitHub instead', async function (assert) {
    board().held = [heldPr()];
    board().mentions.mentions = [
      outstandingMention({ thread: null, comment_id: 1 }),
    ];
    await visit('/');

    await click('[data-test-mentions-count]');

    assert.dom('[data-test-mentions-menu] [data-test-mention-github]').exists();
    assert
      .dom('[data-test-mentions-menu] [data-test-mention-open]')
      .doesNotExist();
  });

  test('the counter is in the top bar of a pull request’s page too', async function (assert) {
    board().held = [heldPr()];
    board().mentions.mentions = [outstandingMention()];

    await visit('/pr/o/r/7');

    assert.dom('[data-top-bar] [data-test-mentions-count]').hasText('1');
  });

  test('a mention leaves the counter once the board holds your reply after it, before the next search', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [
      thread({
        key: 'k1',
        comments: [
          {
            id: 1,
            author: 'anna',
            created_at: '2026-06-10T10:00:00Z',
            review_state: null,
          },
          {
            id: 2,
            author: 'octocat',
            created_at: '2026-06-10T10:05:00Z',
            review_state: null,
          },
        ],
      }),
    ];
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
      outstandingMention({ thread: 'k2', comment_id: 3 }),
    ];

    await visit('/pr/o/r/7');

    assert.dom('[data-top-bar] [data-test-mentions-count]').hasText('1');
    await click('[data-test-mentions-count]');
    assert.dom('[data-test-mention="k1"]').doesNotExist();
    assert.dom('[data-test-mention="k2"]').exists();
  });

  test('a mention made after your last reply stays in the counter', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [
      thread({
        key: 'k1',
        comments: [
          {
            id: 2,
            author: 'octocat',
            created_at: '2026-06-10T09:55:00Z',
            review_state: null,
          },
          {
            id: 1,
            author: 'anna',
            created_at: '2026-06-10T10:00:00Z',
            review_state: null,
          },
        ],
      }),
    ];
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
    ];

    await visit('/pr/o/r/7');

    assert.dom('[data-top-bar] [data-test-mentions-count]').hasText('1');
  });
});
