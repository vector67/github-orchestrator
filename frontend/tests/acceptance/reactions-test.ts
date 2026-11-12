import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  find,
  triggerEvent,
  visit,
} from '@ember/test-helpers';
import {
  added,
  changed,
  comment,
  context,
  prDiff,
  setupFakeBoard,
  thread,
} from 'frontend/tests/helpers/fake-board';
import type { Anchor, Reaction } from 'frontend/data/api';

const KEY = 'PRRT_aa';

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

function picker(): Element {
  return find('[data-test-reaction-picker]')!;
}

function insideTheWindow(box: DOMRect): boolean {
  return (
    box.left >= 0 &&
    box.top >= 0 &&
    box.right <= window.innerWidth &&
    box.bottom <= window.innerHeight
  );
}

function pills(): [string, string, boolean][] {
  return [...document.querySelectorAll('[data-test-reaction]')].map((pill) => [
    pill.getAttribute('data-test-reaction') ?? '',
    pill.textContent?.replace(/\s+/g, ' ').trim() ?? '',
    pill.getAttribute('aria-pressed') === 'true',
  ]);
}

module('Acceptance | reactions', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function seed(reactions: Reaction[]) {
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = [comment({ id: 1, reactions })];
  }

  test('a comment shows each reaction with its count, mine pressed', async function (assert) {
    seed([
      { content: 'thumbs-up', count: 2, mine: true },
      { content: 'eyes', count: 1, mine: false },
    ]);

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(pills(), [
      ['thumbs-up', '👍 2', true],
      ['eyes', '👀 1', false],
    ]);
  });

  test('the smiley offers GitHub’s eight reactions and a pick is sent and shown', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-react]');
    const offered = [
      ...document.querySelectorAll('[data-test-reaction-option]'),
    ].map((one) => one.textContent?.trim());
    await click('[data-test-reaction-option="heart"]');

    assert.deepEqual(offered, ['👍', '👎', '😄', '🎉', '😕', '❤️', '🚀', '👀']);
    assert.deepEqual(board().reacted, [
      { key: KEY, comment: 1, content: 'heart', mine: true },
    ]);
    assert.deepEqual(pills(), [['heart', '❤️ 1', true]]);
    assert.dom('[data-test-reaction-option]').doesNotExist('the picker closes');
  });

  test('the picker opens over the page just under the smiley and moves nothing in the thread', async function (assert) {
    board().conversations = [thread({ key: KEY })];
    board().comments[KEY] = Array.from({ length: 40 }, (_, at) =>
      comment({ id: at + 1, review_state: null, body: `point ${at + 1}` }),
    );
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const smileys = [...document.querySelectorAll('[data-test-react]')];
    const smiley = smileys.at(-1)!;
    const thread_ = document.querySelector('#panel-thread')!;
    const entries = () =>
      [...document.querySelectorAll('[data-test-entry]')].map(
        (entry) => entry.getBoundingClientRect().top,
      );
    smiley.scrollIntoView({ block: 'nearest' });
    const before = JSON.stringify({
      scrolled: thread_.scrollTop,
      entries: entries(),
    });

    await click(smiley);

    const picker = document.querySelector('[data-test-reaction-picker]')!;
    const under = smiley.getBoundingClientRect().bottom;
    const top = picker.getBoundingClientRect().top;
    assert.strictEqual(
      JSON.stringify({ scrolled: thread_.scrollTop, entries: entries() }),
      before,
      'nothing in the thread moved',
    );
    assert.true(picker.matches(':popover-open'), 'it is drawn over the page');
    assert.true(
      top >= under,
      `it opens below the smiley (${top} under ${under})`,
    );
    assert.true(
      top <= under + 12,
      `it opens right by it (${top} under ${under})`,
    );
  });

  test('Escape closes the picker and leaves the thread open', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-react]');

    await triggerEvent(document.activeElement!, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-reaction-picker]').doesNotExist();
    assert.strictEqual(currentURL(), `/pr/o/r/7/conversations/${KEY}`);
    assert.deepEqual(board().reacted, []);
  });

  test('a click outside the picker closes it and sends nothing', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-react]');

    await click('[data-test-entry-body]');

    assert.dom('[data-test-reaction-picker]').doesNotExist();
    assert.deepEqual(board().reacted, []);
  });

  test('a picker opened at the window’s right edge stays inside the window', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const smiley = find('[data-test-react]') as HTMLElement;
    const drawn = smiley.getBoundingClientRect();
    const scale = drawn.width / smiley.offsetWidth;
    const shift = (window.innerWidth - 2 - drawn.right) / scale;
    smiley.style.transform = `translateX(${shift}px)`;
    const placed = smiley.getBoundingClientRect();

    await triggerEvent(smiley, 'click');

    const box = picker().getBoundingClientRect();
    assert.true(
      placed.right > window.innerWidth - 40,
      `the smiley sits at the edge (${placed.right} of ${window.innerWidth})`,
    );
    assert.true(
      insideTheWindow(box),
      `the picker fits (${JSON.stringify(box)})`,
    );
    assert.true(box.top >= placed.bottom, 'it still opens below the smiley');
  });

  test('a picker with no room under the smiley opens above it, inside the window', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const smiley = find('[data-test-react]') as HTMLElement;
    const drawn = smiley.getBoundingClientRect();
    const scale = drawn.height / smiley.offsetHeight;
    const shift = (window.innerHeight - 2 - drawn.bottom) / scale;
    smiley.style.transform = `translateY(${shift}px)`;
    const placed = smiley.getBoundingClientRect();

    await triggerEvent(smiley, 'click');

    const box = picker().getBoundingClientRect();
    assert.true(
      placed.bottom > window.innerHeight - 40,
      `the smiley sits at the foot (${placed.bottom} of ${window.innerHeight})`,
    );
    assert.true(
      insideTheWindow(box),
      `the picker fits (${JSON.stringify(box)})`,
    );
    assert.true(
      box.bottom <= placed.top,
      `it opens above the smiley (${box.bottom} over ${placed.top})`,
    );
    assert.true(
      box.bottom >= placed.top - 12,
      `it opens right by it (${box.bottom} over ${placed.top})`,
    );
  });

  test('resizing the window closes the picker and sends nothing', async function (assert) {
    seed([]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-react]');

    await triggerEvent(window, 'resize');

    assert.dom('[data-test-reaction-picker]').doesNotExist();
    assert.deepEqual(board().reacted, []);
  });

  test('the smiley on a diff card opens its picker over the page, under it, and Escape closes it', async function (assert) {
    board().pullRequestDiff = prDiff(
      changed('src/widgets/changes.py', [
        context(18, '    rows = []'),
        added(19, '    return rows'),
        added(20, '    # done'),
      ]),
    );
    board().conversations = [thread({ key: 'k1', anchor: ON_LINE_20 })];
    board().comments = { k1: [comment({ body: 'please rename' })] };
    await visit('/pr/o/r/7/diff');
    const smiley = find('[data-test-card="k1"] [data-test-react]')!;

    await click(smiley);

    const under = smiley.getBoundingClientRect().bottom;
    const box = picker().getBoundingClientRect();
    assert.true(picker().matches(':popover-open'), 'it is drawn over the page');
    assert.true(box.top >= under, `it opens below the smiley (${box.top})`);
    assert.true(box.top <= under + 12, `it opens right by it (${under})`);
    assert.true(
      insideTheWindow(box),
      `the picker fits (${JSON.stringify(box)})`,
    );

    await triggerEvent(document.activeElement!, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-reaction-picker]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/diff');
  });

  test('pressing my own reaction takes it back', async function (assert) {
    seed([{ content: 'rocket', count: 2, mine: true }]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-reaction="rocket"]');

    assert.deepEqual(board().reacted, [
      { key: KEY, comment: 1, content: 'rocket', mine: false },
    ]);
    assert.deepEqual(pills(), [['rocket', '🚀 1', false]]);
  });

  test('pressing someone else’s reaction adds mine to it', async function (assert) {
    seed([{ content: 'laugh', count: 1, mine: false }]);
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-reaction="laugh"]');

    assert.deepEqual(pills(), [['laugh', '😄 2', true]]);
  });

  test('a reaction GitHub refuses says so and leaves the comment as it was', async function (assert) {
    seed([]);
    board().reactionRefused = 'GitHub said no';
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    await click('[data-test-react]');
    await click('[data-test-reaction-option="eyes"]');

    assert.deepEqual(pills(), []);
    assert.dom('[data-test-toast]').containsText('GitHub said no');
  });
});
