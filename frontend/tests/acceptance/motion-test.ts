import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  find,
  findAll,
  settled,
  triggerEvent,
  visit,
  waitUntil,
} from '@ember/test-helpers';
import type { Anchor, ErrorCode } from 'frontend/data/api';
import {
  added,
  changed,
  comment,
  context,
  factsFor,
  heldPr,
  prDiff,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const LIST = 5000;

const ON_LINE_20: Anchor = {
  path: 'src/widgets/changes.py',
  line: 20,
  start_line: null,
  start_side: null,
  side: 'RIGHT',
  original_line: 20,
  original_start_line: null,
  original_commit: 'ba5e000',
  is_outdated: false,
};

module('Acceptance | motion', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.afterEach(function () {
    document.documentElement.setAttribute('data-still', '');
    Reflect.deleteProperty(document, 'hidden');
  });

  function tabHidden(): void {
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => true,
    });
  }

  function marked(selector: string, attribute: string): string[] {
    return findAll(`${selector}[data-moved]`).map((one) =>
      one.getAttribute(attribute)!,
    );
  }

  function inMotion(): void {
    document.documentElement.removeAttribute('data-still');
  }

  function slides(): Animation[] {
    return document
      .getAnimations()
      .filter((one) => !(one instanceof CSSAnimation));
  }

  async function press(key: string, times = 1): Promise<void> {
    for (let at = 0; at < times; at++) {
      await triggerEvent(document, 'keydown', { key });
    }
  }

  function insideOf(scroller: Element, selector: string): boolean {
    const box = scroller.getBoundingClientRect();
    const row = find(selector)!.getBoundingClientRect();
    const pixel = 1;
    return row.top > box.top - pixel && row.bottom < box.bottom + pixel;
  }

  async function refused(code: ErrorCode): Promise<void> {
    board().refusal = { status: 409, code, detail: code };
    await click('[data-test-decision="unpark"]');
  }

  async function diffWithADraft(): Promise<void> {
    board().pullRequestDiff = prDiff(
      changed('src/widgets/changes.py', [
        context(18, '    rows = []'),
        added(19, '    return rows'),
        added(20, '    # done'),
      ]),
    );
    board().conversations = [
      thread({ key: 'k1', anchor: ON_LINE_20 }),
      thread({
        key: 'd1',
        kind: 'draft',
        state: 'draft',
        anchor: ON_LINE_20,
        comments: [],
      }),
    ];
    board().comments = {
      k1: [comment({ body: 'please rename' })],
      d1: [comment({ id: null, author: 'octocat', body: 'return the rows' })],
    };
    await visit('/pr/o/r/7/diff');
  }

  test('a discarded draft collapses in the diff once the board answers, and goes when it has', async function (assert) {
    await diffWithADraft();
    inMotion();
    board().projections = {
      d1: board().threadIn('discarded', { key: 'd1' }),
    };
    board().conversations = board().conversations.filter(
      (one) => one.key !== 'd1',
    );

    const pressing = click(
      '[data-test-card="d1"] [data-test-card-decide="discard"]',
    );
    await waitUntil(() => slides().length > 0);

    assert.dom('[data-test-card="d1"]').exists('it stays while it collapses');

    slides().forEach((one) => one.finish());
    await pressing;

    assert.dom('[data-test-card="d1"]').doesNotExist();
    assert.dom('[data-test-card="k1"]').exists();
    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });

  test('the chevron folds a resolved thread by collapsing its comments, then drawing the folded row', async function (assert) {
    await diffWithADraft();
    board().conversations = board().conversations.map((one) =>
      one.key === 'k1' ? { ...one, github_resolved: true, etag: '"t2"' } : one,
    );
    await clock().tick(LIST);
    inMotion();

    const folding = click('[data-test-card="k1"] [data-test-hide-resolved]');
    await waitUntil(() => slides().length > 0);

    assert
      .dom('[data-test-card="k1"] [data-test-entry-body]')
      .exists('its comments stay while they collapse');

    slides().forEach((one) => one.finish());
    await folding;

    assert.dom('[data-test-card="k1"] [data-test-entry-body]').doesNotExist();
    assert.dom('[data-test-card="k1"] [data-test-show-resolved]').exists();
    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });

  test('a refused discard leaves the draft where it is', async function (assert) {
    await diffWithADraft();
    inMotion();
    board().refusal = {
      status: 409,
      code: 'operation-outstanding',
      detail: 'operation-outstanding',
    };

    await click('[data-test-card="d1"] [data-test-card-decide="discard"]');

    assert.dom('[data-test-card="d1"]').isVisible();
    assert.deepEqual(slides(), [], 'nothing collapsed');
  });

  test('a toast clicked away is gone, and the others stay', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');
    await refused('operation-outstanding');
    await refused('agents-disabled');

    await click('[data-test-toast]');

    assert.dom('[data-test-toast]').exists({ count: 1 });
    assert.dom('[data-test-toast]').containsText('switched off');
  });

  test('a toast leaves when its time is up, and one raised after it stays', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');
    await refused('operation-outstanding');
    await clock().tick(2000);
    await refused('agents-disabled');

    await clock().tick(1000);

    assert.dom('[data-test-toast]').exists({ count: 1 });
    assert.dom('[data-test-toast]').containsText('switched off');
  });

  test('a toast that goes leaves the mark on a row whose flash is still playing', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
    ];
    await visit('/pr/o/r/7/conversations/b');
    inMotion();
    board().conversations = [
      board().threadIn('landed', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
    ];
    const polling = clock().tick(LIST);
    await waitUntil(() => slides().length > 0);
    slides().forEach((one) => one.finish());
    await polling;
    document
      .getAnimations()
      .filter((one) => one instanceof CSSAnimation)
      .forEach((one) => one.pause());
    await refused('operation-outstanding');

    await click('[data-test-toast]');
    await clock().tick(1000);
    slides().forEach((one) => one.finish());
    await settled();

    assert.dom('[data-test-toast]').doesNotExist();
    assert.deepEqual(marked('#rows [id]', 'id'), ['c-a']);
  });

  test('a toast clicked away is marked leaving while it fades, then goes', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');
    await refused('operation-outstanding');
    await refused('agents-disabled');
    inMotion();

    await click('[data-test-toast]');

    assert.deepEqual(
      findAll('[data-test-toast]').map((one) =>
        one.hasAttribute('data-leaving'),
      ),
      [true, false],
    );

    await clock().tick(1000);
    slides().forEach((one) => one.finish());
    await settled();

    assert.dom('[data-test-toast]').exists({ count: 1 });
    assert.dom('[data-test-toast]').containsText('switched off');
  });

  test('a decision marks the decided card, and its toast waits for the card to land and a rest after', async function (assert) {
    board().conversations = [
      thread({ key: 'a', state: 'ready' }),
      board().threadIn('waiting', { key: 'b' }),
    ];
    await visit('/pr/o/r/7/conversations/b');
    inMotion();
    board().conversations = [
      thread({ key: 'a', state: 'ready' }),
      thread({ key: 'b', state: 'ready', etag: '"t2"' }),
    ];

    const pressing = click('[data-test-decision="unpark"]');
    await waitUntil(() => slides().length > 0);

    assert.dom('#c-b').hasAttribute('data-decided');
    assert.dom('[data-test-toast]').doesNotExist('not while the card slides');

    slides().forEach((one) => one.finish());
    await pressing;

    assert.dom('[data-test-heading="waiting"]').doesNotExist();
    assert.dom('[data-test-toast]').doesNotExist('not as the card lands');

    await clock().tick(1000);

    assert.dom('[data-test-toast]').hasText('Queued: bringing it back.');
  });

  test('a refused decision toasts at once, before the re-read lands', async function (assert) {
    board().conversations = [
      thread({ key: 'a', state: 'ready' }),
      board().threadIn('waiting', { key: 'b' }),
    ];
    await visit('/pr/o/r/7/conversations/b');
    inMotion();
    board().refusal = {
      status: 412,
      code: 'precondition-failed',
      detail: 'thread b has moved',
    };
    board().conversations = [
      thread({ key: 'a', state: 'ready' }),
      thread({ key: 'b', state: 'ready', etag: '"t2"' }),
    ];

    const pressing = click('[data-test-decision="unpark"]');
    await waitUntil(() => slides().length > 0);

    assert.dom('[data-test-toast]').containsText('It has been read again');
    assert.dom('#c-b').doesNotHaveAttribute('data-decided');

    slides().forEach((one) => one.finish());
    await pressing;
  });

  test('a hidden tab takes a move at once: the row is marked and nothing slides', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await visit('/pr/o/r/7/conversations');
    inMotion();
    tabHidden();
    const slides = new Set<number>();
    let watching = true;
    const watch = () => {
      slides.add(
        document.getAnimations().filter((one) => !(one instanceof CSSAnimation))
          .length,
      );
      if (watching) requestAnimationFrame(watch);
    };
    watch();

    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('landed', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await clock().tick(LIST);
    watching = false;

    assert.deepEqual(marked('#rows [id]', 'id'), ['c-b']);
    assert.deepEqual([...slides], [0], 'no frame held a slide');
  });

  test('a board column scrolled down keeps its place while a poll carries a card into it', async function (assert) {
    const done = Array.from({ length: 12 }, (_, at) =>
      board().threadIn('landed', { key: `d${at}` }),
    );
    board().conversations = [
      ...done,
      board().threadIn('waiting', { key: 'b' }),
    ];
    await visit('/pr/o/r/7/board');
    const column = find('[data-test-card="d0"]')!.parentElement!;
    column.style.maxHeight = '200px';
    column.scrollTop = 150;
    assert.strictEqual(column.scrollTop, 150, 'the column scrolls');

    inMotion();
    const seen = new Set<number>();
    let watching = true;
    const watch = () => {
      seen.add(column.scrollTop);
      if (watching) requestAnimationFrame(watch);
    };
    watch();
    board().conversations = [...done, board().threadIn('landed', { key: 'b' })];
    const polling = clock().tick(LIST);
    await waitUntil(() => slides().length > 0);
    for (const part of [0, 0.5]) {
      slides().forEach((one) => {
        one.currentTime = Number(one.effect!.getTiming().duration) * part;
      });
      seen.add(column.scrollTop);
    }
    slides().forEach((one) => one.finish());
    await polling;
    seen.add(column.scrollTop);
    watching = false;

    assert.dom('[data-test-column="done"] [data-test-card="b"]').exists();
    assert.dom('[data-test-card="b"]').exists({ count: 1 });
    assert.deepEqual([...seen], [150], 'every frame of the flight');
  });

  test('the switcher is all the way in once the page settles, with a live dot beside a working pull request', async function (assert) {
    board().serves = 'hub';
    board().held = [
      heldPr({
        dashboard: {
          system: {
            agent: {
              name: 'Claude',
              enabled: true,
              state: 'working',
              event: 'ci-failed',
              elapsed_seconds: 134,
              silent_seconds: 6,
            },
          },
        },
      }),
    ];
    await visit('/pr/o/r/7');

    await click('[data-test-switcher-open]');

    assert.dom('[data-test-switcher] .live-dot').exists();
    assert.strictEqual(
      find('[data-test-switcher]')?.getAttribute('aria-hidden'),
      'false',
    );
    assert.deepEqual(document.getAnimations(), [], 'nothing is still moving');
  });

  test('a rail row that changes group after a poll is the one row marked as moved, and the group it left loses its heading', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(
      marked('#rows [id]', 'id'),
      [],
      'a first draw marks nothing',
    );

    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('landed', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await clock().tick(LIST);

    assert.deepEqual(marked('#rows [id]', 'id'), ['c-b']);
    assert.dom('[data-test-heading="waiting"]').doesNotExist();
    assert.deepEqual(document.getAnimations(), [], 'nothing is still moving');
  });

  test('a poll that moves no row between groups marks nothing, and clears the last move', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
    ];
    await visit('/pr/o/r/7/conversations');
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('landed', { key: 'b' }),
    ];
    await clock().tick(LIST);

    board().conversations = [
      board().threadIn('landed', { key: 'b' }),
      thread({ key: 'a', state: 'working', etag: '"t2"' }),
    ];
    await clock().tick(LIST);

    assert.deepEqual(marked('#rows [id]', 'id'), []);
  });

  test('a wall row that changes section after a poll is the one row marked as moved, and the section it left loses its heading', async function (assert) {
    board().serves = 'hub';
    board().held = [
      heldPr({ number: 7, dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({
        number: 8,
        dashboard: { manager: { on_hold: true }, system: { on_hold: true } },
      }),
      heldPr({ number: 9 }),
    ];
    await visit('/');

    assert.deepEqual(
      marked('[data-test-wall-row]', 'data-test-wall-row'),
      [],
      'a first draw marks nothing',
    );

    board().held = [
      heldPr({ number: 7, dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 8, dashboard: { facts: factsFor('fix-ci') } }),
      heldPr({ number: 9 }),
    ];
    await clock().tick(LIST);

    assert.deepEqual(marked('[data-test-wall-row]', 'data-test-wall-row'), [
      'o/r#8',
    ]);
    assert.dom('[data-test-wall-group="on-hold"]').doesNotExist();
    assert.deepEqual(document.getAnimations(), [], 'nothing is still moving');
  });

  test('a board card that changes column after a poll is the one card marked as moved, in its new column', async function (assert) {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('waiting', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await visit('/pr/o/r/7/board');

    assert.deepEqual(
      marked('[data-test-card]', 'data-test-card'),
      [],
      'a first draw marks nothing',
    );

    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('landed', { key: 'b' }),
      board().threadIn('landed', { key: 'c' }),
    ];
    await clock().tick(LIST);

    assert.deepEqual(marked('[data-test-card]', 'data-test-card'), ['b']);
    assert.dom('[data-test-column="done"] [data-test-card="b"]').exists();
    assert.deepEqual(document.getAnimations(), [], 'nothing is still moving');
  });

  function sliding(): (string | null)[] {
    return slides().map((one) => {
      const target = (one.effect as KeyframeEffect).target;
      return target?.id || target?.getAttribute('data-test-wall-row') || null;
    });
  }

  test('a click on a rail row slides the highlight over to it from the row it leaves', async function (assert) {
    board().conversations = Array.from({ length: 3 }, (_, at) =>
      board().threadIn('landed', { key: `t${at}` }),
    );
    await visit('/pr/o/r/7/conversations/t0');
    inMotion();

    await click('#c-t2');

    assert.dom('#rows [aria-selected="true"]').hasAttribute('id', 'c-t2');
    assert.deepEqual(sliding(), ['c-t2'], 'the highlight slides onto the row');

    slides().forEach((one) => one.finish());
    await settled();

    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });

  test('j on the wall slides the highlight from the row it leaves to the next one', async function (assert) {
    board().serves = 'hub';
    board().held = [heldPr({ number: 1 }), heldPr({ number: 2 })];
    await visit('/');
    await press('j');
    inMotion();

    await press('j');

    assert
      .dom('[data-test-wall-row][aria-current="true"]')
      .hasAttribute('data-test-wall-row', 'o/r#2');
    assert.deepEqual(sliding(), ['o/r#2'], 'the highlight slides onto the row');

    slides().forEach((one) => one.finish());
    await settled();

    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });

  test('the first selection on the wall draws its highlight in place', async function (assert) {
    board().serves = 'hub';
    board().held = [heldPr({ number: 1 }), heldPr({ number: 2 })];
    await visit('/');
    inMotion();

    await press('j');

    assert.deepEqual(sliding(), [], 'there is no row to slide from');
  });

  test('j past the bottom of a short rail scrolls the selected row into view, and k past the top scrolls it back', async function (assert) {
    board().conversations = Array.from({ length: 12 }, (_, at) =>
      board().threadIn('landed', { key: `t${at}` }),
    );
    await visit('/pr/o/r/7/conversations/t0');
    const rail = find('#rows') as HTMLElement;
    rail.style.maxHeight = '200px';

    await press('j', 11);

    assert.dom('#rows [aria-selected="true"]').hasAttribute('id', 'c-t11');
    assert.true(rail.scrollTop > 0, 'the rail scrolled down');
    assert.true(insideOf(rail, '#c-t11'), 'the selected row is in view');

    await press('k', 11);

    assert.dom('#rows [aria-selected="true"]').hasAttribute('id', 'c-t0');
    assert.true(insideOf(rail, '#c-t0'), 'the selected row is in view');
    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });

  test('j past the bottom of a short wall scrolls the selected row into view, and k past the top scrolls it back', async function (assert) {
    board().serves = 'hub';
    board().held = Array.from({ length: 12 }, (_, at) =>
      heldPr({ number: at + 1 }),
    );
    await visit('/');
    const wall = find('.wall-body') as HTMLElement;
    wall.style.maxHeight = '200px';

    await press('j', 12);

    assert
      .dom('[data-test-wall-row][aria-current="true"]')
      .hasAttribute('data-test-wall-row', 'o/r#12');
    assert.true(wall.scrollTop > 0, 'the wall scrolled down');
    assert.true(
      insideOf(wall, '[data-test-wall-row="o/r#12"]'),
      'the selected row is in view',
    );

    await press('k', 11);

    assert
      .dom('[data-test-wall-row][aria-current="true"]')
      .hasAttribute('data-test-wall-row', 'o/r#1');
    assert.true(
      insideOf(wall, '[data-test-wall-row="o/r#1"]'),
      'the selected row is in view',
    );
    assert.deepEqual(slides(), [], 'nothing is left in flight');
  });
});
