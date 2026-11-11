import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  fillIn,
  find,
  findAll,
  select,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  heldPr,
  outstandingMention,
  setupFakeBoard,
  thread,
  threadRow,
  WALL_GROUPS,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

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

  test('each mention’s arrow opens its four actions in order', async function (assert) {
    board().mentions.mentions = [outstandingMention({ thread: 'k1' })];

    await opened();

    assert.deepEqual(
      findAll('[data-test-mention-action]').map((one) =>
        one.textContent.replace(/\s+/g, ' ').trim(),
      ),
      ['See in context', 'See on GitHub', 'Defer…', 'Dismiss'],
    );
    assert.dom('[data-test-mention-action="defer"]').isNotDisabled();
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

  test('a pull request’s page opened on a wall kept from an earlier visit counts the mentions at once, as the hub does', async function (assert) {
    board().held = [heldPr()];
    board().conversations = [thread({ key: 'k1' })];
    board().mentions.mentions = [
      outstandingMention({ thread: 'k2', comment_id: 2 }),
    ];
    localStorage.setItem(
      'hub-pull-requests',
      JSON.stringify({
        watching: ['o/r'],
        groups: WALL_GROUPS,
        pull_requests: [heldPr()],
      }),
    );

    try {
      await visit('/pr/o/r/7/conversations/k1');

      assert.dom('[data-top-bar] [data-test-mentions-count]').hasText('1');
    } finally {
      localStorage.removeItem('hub-pull-requests');
    }
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

module('Acceptance | mentions | defer', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  const WEDNESDAY_TEN = new Date(2026, 10, 11, 10, 0).getTime();

  function local(day: number, hour: number, minute = 0): string {
    return new Date(2026, 10, day, hour, minute).toISOString();
  }

  function texts(selector: string): string[] {
    return findAll(selector).map((one) =>
      one.textContent.replace(/\s+/g, ' ').trim(),
    );
  }

  async function deferring(key = 'k1'): Promise<void> {
    await visit('/');
    await click('[data-test-mentions-count]');
    await click(`[data-test-mention="${key}"] [data-test-mention-more]`);
    await click('[data-test-mention-action="defer"]');
  }

  hooks.beforeEach(function () {
    clock().now = WEDNESDAY_TEN;
    board().mentions.mentions = [
      outstandingMention({ thread: 'k1', comment_id: 1 }),
      outstandingMention({ thread: 'k2', comment_id: 2 }),
    ];
  });

  test('Defer… opens a dialog on its For a time tab, with four presets in your local time', async function (assert) {
    await deferring();

    assert.dom('[data-test-defer-dialog]').exists();
    assert.deepEqual(texts('[data-test-defer-tab]'), [
      'For a time',
      'Until a PR…',
    ]);
    assert
      .dom('[data-test-defer-tab="time"]')
      .hasAttribute('aria-selected', 'true');
    assert.deepEqual(texts('[data-test-defer-preset]'), [
      '1 hour 11:00',
      'Later today 13:00',
      'Tomorrow 9:00 Thu',
      'Monday 9:00 Mon',
    ]);
    assert.dom('[data-test-mention-actions]').doesNotExist();
  });

  for (const [preset, until] of [
    ['1 hour', local(11, 11)],
    ['Later today', local(11, 13)],
    ['Tomorrow 9:00', local(12, 9)],
    ['Monday 9:00', local(16, 9)],
  ] as const) {
    test(`the ${preset} preset defers the mention until then`, async function (assert) {
      await deferring();

      await click(`[data-test-defer-preset="${preset}"]`);

      assert.deepEqual(board().deferredMentions, [
        {
          repo: 'o/r',
          number: 7,
          comment_id: 1,
          until_at: until,
          until_pr: null,
        },
      ]);
      assert.dom('[data-test-defer-dialog]').doesNotExist();
    });
  }

  for (const [typed, until] of [
    ['3d', local(14, 10)],
    ['4h', local(11, 14)],
    ['90m', local(11, 11, 30)],
    ['fri 14:00', local(13, 14)],
    ['tomorrow 9:00', local(12, 9)],
    ['Wed 9:00', local(18, 9)],
    ['17:30', local(11, 17, 30)],
  ] as const) {
    test(`a typed ${typed} defers the mention until then`, async function (assert) {
      await deferring();

      await fillIn('[data-test-defer-typed]', typed);
      await click('[data-test-defer-send]');

      assert.deepEqual(
        board().deferredMentions.map((one) => one.until_at),
        [until],
      );
    });
  }

  test('a typed time names when it lands before you send it', async function (assert) {
    await deferring();

    await fillIn('[data-test-defer-typed]', 'fri 14:00');

    assert.dom('[data-test-defer-lands]').hasText('Fri 13 Nov 14:00');
  });

  test('a typed time that does not parse says so and keeps the text', async function (assert) {
    await deferring();

    await fillIn('[data-test-defer-typed]', 'next blue moon');
    await click('[data-test-defer-send]');

    assert
      .dom('[data-test-defer-problem]')
      .hasText(
        '“next blue moon” is not a time to come. Try 3d, 4h, fri 14:00 or tomorrow 9:00.',
      );
    assert.dom('[data-test-defer-typed]').hasValue('next blue moon');
    assert.deepEqual(board().deferredMentions, []);
    assert.dom('[data-test-defer-dialog]').exists();
  });

  test('Until a PR… defers the mention until the PR you pick reaches the state you pick', async function (assert) {
    board().held = [
      heldPr(),
      heldPr({ number: 8, dashboard: { pr: { title: 'Tidy the importer' } } }),
    ];
    await deferring();
    await click('[data-test-defer-tab="pr"]');

    assert.deepEqual(texts('[data-test-defer-state]'), [
      'lands in Needs you',
      'is approved',
      'gets a new commit',
      'is merged',
      'is closed',
      'has any new activity',
    ]);
    await select('[data-test-defer-pr]', 'o/r#8');
    await click('[data-test-defer-state="approved"]');

    assert.deepEqual(board().deferredMentions, [
      {
        repo: 'o/r',
        number: 7,
        comment_id: 1,
        until_at: null,
        until_pr: { repo: 'o/r', number: 8, state: 'approved' },
      },
    ]);
    assert.dom('[data-test-defer-dialog]').doesNotExist();
  });

  test('Until a PR… lists every PR on the board and starts on the mentioned one', async function (assert) {
    board().held = [
      heldPr({ number: 8, dashboard: { pr: { title: 'Tidy the importer' } } }),
      heldPr({ dashboard: { pr: { title: 'Add widgets' } } }),
    ];
    await deferring();
    await click('[data-test-defer-tab="pr"]');

    assert.deepEqual(texts('[data-test-defer-pr] option'), [
      'o/r#7 Add widgets',
      'o/r#8 Tidy the importer',
    ]);
    assert.dom('[data-test-defer-pr]').hasValue('o/r#7');
  });

  test('a deferred mention stays in the list, greyed with until when, and leaves the count', async function (assert) {
    await deferring();

    await click('[data-test-defer-preset="Tomorrow 9:00"]');

    assert.dom('[data-test-mentions-count]').hasText('1');
    assert.dom('[data-test-mention="k1"]').hasClass('deferred');
    assert
      .dom('[data-test-mention="k1"] [data-test-mention-deferred]')
      .hasText('deferred until Thu 12 Nov 9:00');
    assert.dom('[data-test-mention="k2"]').doesNotHaveClass('deferred');
  });

  test('a mention deferred until a PR says which PR and what it waits for', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        deferred: {
          deferred_at: local(11, 9),
          until_at: null,
          until_pr: { repo: 'o/r', number: 8, state: 'new-commit' },
        },
      }),
    ];
    await visit('/');
    await click('[data-test-mentions-count]');

    assert
      .dom('[data-test-mention="k1"] [data-test-mention-deferred]')
      .hasText('deferred until o/r#8 gets a new commit');
    assert.dom('[data-test-mentions-count]').hasText('0');
    assert.dom('[data-test-mentions-count]').doesNotHaveClass('outstanding');
  });

  test('a deferred mention’s menu offers Stop deferring, which counts it again', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        deferred: {
          deferred_at: local(11, 9),
          until_at: local(12, 9),
          until_pr: null,
        },
      }),
    ];
    await visit('/');
    await click('[data-test-mentions-count]');
    await click('[data-test-mention="k1"] [data-test-mention-more]');

    assert.deepEqual(texts('[data-test-mention-action]'), [
      'See in context',
      'See on GitHub',
      'Stop deferring',
      'Dismiss',
    ]);
    await click('[data-test-mention-action="stop-deferring"]');

    assert.deepEqual(board().undeferredMentions, [
      { repo: 'o/r', number: 7, comment_id: 1 },
    ]);
    assert.dom('[data-test-mentions-count]').hasText('1');
    assert.dom('[data-test-mention="k1"]').doesNotHaveClass('deferred');
  });

  test('a refused defer says why in the dialog and keeps what you typed', async function (assert) {
    await deferring();
    board().refusal = {
      status: 400,
      code: 'malformed-request',
      detail: 'until_at: Input should have timezone info',
    };

    await fillIn('[data-test-defer-typed]', '3d');
    await click('[data-test-defer-send]');

    assert.dom('[data-test-defer-refused]').includesText('Not deferred');
    assert
      .dom('[data-test-defer-refused]')
      .includesText('until_at: Input should have timezone info');
    assert.dom('[data-test-defer-typed]').hasValue('3d');
    assert.dom('[data-test-mentions-count]').hasText('2');
  });

  test('a refused Stop deferring says why and keeps the mention deferred', async function (assert) {
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        deferred: {
          deferred_at: local(11, 9),
          until_at: local(12, 9),
          until_pr: null,
        },
      }),
    ];
    await visit('/');
    await click('[data-test-mentions-count]');
    await click('[data-test-mention="k1"] [data-test-mention-more]');
    board().refusal = {
      status: 400,
      code: 'malformed-request',
      detail: 'repo: String should match pattern',
    };

    await click('[data-test-mention-action="stop-deferring"]');

    assert.dom('[data-test-toast]').includesText('Mention still deferred');
    assert.dom('[data-test-mention="k1"]').hasClass('deferred');
  });

  test('a mention deferred until its PR lands in Needs you counts again once it does, and stops the deferral', async function (assert) {
    board().held = [
      heldPr({
        number: 8,
        dashboard: { threads: [threadRow('h1', 'ready', 'open', 'human')] },
      }),
    ];
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        deferred: {
          deferred_at: local(11, 9),
          until_at: null,
          until_pr: { repo: 'o/r', number: 8, state: 'needs-you' },
        },
      }),
    ];

    await visit('/');

    assert.dom('[data-test-mentions-count]').hasText('1');
    assert.deepEqual(board().undeferredMentions, [
      { repo: 'o/r', number: 7, comment_id: 1 },
    ]);
  });

  test('a mention deferred until a PR that is not in Needs you stays deferred', async function (assert) {
    board().held = [heldPr({ number: 8 })];
    board().mentions.mentions = [
      outstandingMention({
        thread: 'k1',
        deferred: {
          deferred_at: local(11, 9),
          until_at: null,
          until_pr: { repo: 'o/r', number: 8, state: 'needs-you' },
        },
      }),
    ];

    await visit('/');

    assert.dom('[data-test-mentions-count]').hasText('0');
    assert.deepEqual(board().undeferredMentions, []);
  });
});
