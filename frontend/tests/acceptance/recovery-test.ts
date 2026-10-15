import { module, test } from 'qunit';
import { waitUntil } from '@ember/test-helpers';

const DRAFTS = 'decide-dialog-drafts';
const SHELF = 'hub-pull-requests';
const SECTIONS_ENTERED = 'hub-sections-entered';
const KEEP_DRAFTS =
  'Delete everything except saved drafts and reload (might work)';
const DELETE_ALL = 'Delete all local storage and reload';

interface Framed {
  frame: HTMLIFrameElement;
  page: () => Document;
  loads: () => number;
}

const SPED_UP = 20;
const SETTLED = 100;

const FAST_TIMERS = `<script>
  const realSetTimeout = window.setTimeout;
  window.setTimeout = (run, ms = 0, ...rest) =>
    realSetTimeout(run, ms / ${SPED_UP}, ...rest);
</script>`;

async function framed(body: string, patience = 60000): Promise<Framed> {
  const frame = document.createElement('iframe');
  let loads = 0;
  frame.addEventListener('load', () => (loads += 1));
  frame.srcdoc = `<!DOCTYPE html><html><head>${FAST_TIMERS}<script src="/recovery.js" data-patience="${patience}"></script></head><body>${body}</body></html>`;
  document.querySelector('#qunit-fixture')!.append(frame);
  await waitUntil(() => loads > 0, { timeout: 5000 });
  return { frame, page: () => frame.contentDocument!, loads: () => loads };
}

function panelOf(page: Document): HTMLElement | null {
  const panel = page.getElementById('board-recovery');
  return panel && !panel.hidden ? panel : null;
}

async function panelIn(page: () => Document): Promise<HTMLElement> {
  await waitUntil(() => panelOf(page()), { timeout: 5000 });
  return panelOf(page())!;
}

function offered(panel: HTMLElement): string[] {
  return [...panel.querySelectorAll('button')].map((one) =>
    one.textContent.trim(),
  );
}

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module('Acceptance | recovery', function (hooks) {
  hooks.beforeEach(function () {
    localStorage.removeItem(DRAFTS);
    localStorage.removeItem(SHELF);
    localStorage.removeItem(SECTIONS_ENTERED);
  });

  hooks.afterEach(function () {
    localStorage.removeItem(DRAFTS);
    localStorage.removeItem(SHELF);
  });

  test('a page that throws before anything appears says why and offers both ways out', async function (assert) {
    localStorage.setItem(SHELF, '{}');
    localStorage.setItem(DRAFTS, '{}');

    const { page } = await framed(
      "<script>throw new Error('the bundle broke')</script>",
    );

    const panel = await panelIn(page);
    assert.true(panel.textContent.includes('the bundle broke'));
    assert.deepEqual(offered(panel), [KEEP_DRAFTS, DELETE_ALL]);
  });

  test('a script that cannot load is named', async function (assert) {
    const { page } = await framed('<script src="/no-such-bundle.js"></script>');

    const panel = await panelIn(page);

    assert.true(panel.textContent.includes('/no-such-bundle.js'));
  });

  test('with only drafts saved, deleting all is the one offer', async function (assert) {
    localStorage.setItem(DRAFTS, '{}');

    const { page } = await framed("<script>throw new Error('broke')</script>");

    assert.deepEqual(offered(await panelIn(page)), [DELETE_ALL]);
  });

  test('deleting everything except drafts keeps the drafts and reloads', async function (assert) {
    localStorage.setItem(SHELF, '{}');
    localStorage.setItem(DRAFTS, '{"kept":{}}');
    const { page, loads } = await framed(
      "<script>throw new Error('broke')</script>",
    );

    [...(await panelIn(page)).querySelectorAll('button')][0]!.click();

    await waitUntil(() => loads() === 2, { timeout: 5000 });
    assert.strictEqual(localStorage.getItem(SHELF), null);
    assert.strictEqual(localStorage.getItem(DRAFTS), '{"kept":{}}');
  });

  test('deleting all local storage leaves nothing and reloads', async function (assert) {
    localStorage.setItem(SHELF, '{}');
    localStorage.setItem(DRAFTS, '{}');
    const { page, loads } = await framed(
      "<script>throw new Error('broke')</script>",
    );

    [...(await panelIn(page)).querySelectorAll('button')][1]!.click();

    await waitUntil(() => loads() === 2, { timeout: 5000 });
    assert.strictEqual(localStorage.getItem(SHELF), null);
    assert.strictEqual(localStorage.getItem(DRAFTS), null);
  });

  test('a page that is showing something is left alone when an error comes later', async function (assert) {
    const { page } = await framed(
      "<main>The wall</main><script>throw new Error('late')</script>",
    );

    await pause(SETTLED);

    assert.strictEqual(panelOf(page()), null);
  });

  test('a page still blank past its patience says nothing appeared, and steps aside once something does', async function (assert) {
    const { page } = await framed('', 100);

    const panel = await panelIn(page);
    assert.true(
      panel.textContent.includes('Nothing appeared after 0.1 seconds'),
    );

    page().body.insertAdjacentHTML('beforeend', '<main>The wall</main>');

    await waitUntil(() => panelOf(page()) === null, { timeout: 5000 });
    assert.dom('main', page().body).hasText('The wall');
  });

  const TROUBLE =
    '<section data-board-trouble><p>The board could not load: connection refused</p></section>';

  test('an error under a top bar keeps its own line, without the panel', async function (assert) {
    const { page } = await framed(
      `<header data-top-bar>The bar</header>${TROUBLE}`,
    );

    await pause(SETTLED);

    assert.strictEqual(panelOf(page()), null);
  });

  test('a panel the page’s own rendering removes comes back while the page is still in trouble', async function (assert) {
    const { page } = await framed(TROUBLE);
    (await panelIn(page)).remove();

    page().body.insertAdjacentHTML('beforeend', '<p>re-rendered</p>');

    assert.true((await panelIn(page)).isConnected);
  });

  test('a page that could not start shows the board’s reason until the board’s error goes', async function (assert) {
    const { page } = await framed(`${TROUBLE}<main>The rest</main>`);

    const panel = await panelIn(page);
    assert.true(
      panel.textContent.includes(
        'The board could not load: connection refused',
      ),
    );
    page().querySelector('[data-board-trouble]')!.remove();
    await waitUntil(() => panelOf(page()) === null, { timeout: 5000 });
  });
});
