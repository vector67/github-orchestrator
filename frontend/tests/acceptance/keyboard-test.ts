import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  visit,
  currentURL,
  triggerEvent,
  click,
  findAll,
} from '@ember/test-helpers';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';

module('Acceptance | keyboard', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [
      board().threadIn('working', { key: 'a' }),
      board().threadIn('proposed', { key: 'b' }),
      board().threadIn('proposed', { key: 'c' }),
    ];
  });

  test('j walks down the rail in the order it is drawn', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');
    await triggerEvent(document, 'keydown', { key: 'Escape' });

    await triggerEvent(document, 'keydown', { key: 'j' });
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/b',
      'the first row',
    );

    await triggerEvent(document, 'keydown', { key: 'j' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/c');
  });

  test('k walks back up it', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');

    await triggerEvent(document, 'keydown', { key: 'k' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
  });

  test('from the new draft, where no row is open, k lands on the first row as j does', async function (assert) {
    await visit('/pr/o/r/7/conversations/new-draft');

    await triggerEvent(document, 'keydown', { key: 'k' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
  });

  test('n on the columns opens the first row that is ready for you', async function (assert) {
    await visit('/pr/o/r/7/board');

    await triggerEvent(document, 'keydown', { key: 'n' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
  });

  test('j steps over the group headings', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');

    await triggerEvent(document, 'keydown', { key: 'j' });

    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/a',
      'the working heading sits between c and a and is not a stop',
    );
  });

  test('escape closes the panel back to the board', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test("a keystroke typed into a field is the field's", async function (assert) {
    await visit('/pr/o/r/7/conversations/b');
    const box = document.createElement('textarea');
    document.querySelector('#panel')?.appendChild(box);

    await triggerEvent(box, 'keydown', { key: 'j' });

    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/b',
      'no navigation',
    );
  });

  test('n opens the first row that is ready for you', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');
    await triggerEvent(document, 'keydown', { key: 'Escape' });

    await triggerEvent(document, 'keydown', { key: 'n' });

    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/b',
      'b is the first row in the ready group, a is in working',
    );
  });

  test('n walks on through the rows that are ready for you', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');

    await triggerEvent(document, 'keydown', { key: 'n' });
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/c',
      'the next ready row',
    );

    await triggerEvent(document, 'keydown', { key: 'n' });
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/c',
      'the last ready row holds; a is in working and n never reaches it',
    );
  });

  test('p walks back up them', async function (assert) {
    await visit('/pr/o/r/7/conversations/c');

    await triggerEvent(document, 'keydown', { key: 'p' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/b');
  });

  test('the panel buttons walk the list the keys walk', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');

    await click('[data-test-next]');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/c');

    await click('[data-test-prev]');
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/b',
      'one ordering, pressed two ways',
    );
  });

  test('question mark shows the key help and any key hides it', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerEvent(document, 'keydown', { key: '?' });
    assert.dom('[data-test-key-help]').exists();

    await triggerEvent(document, 'keydown', { key: 'x' });
    assert.dom('[data-test-key-help]').doesNotExist();
  });

  test('the key help takes the focus, keeps it on tab and hands it back', async function (assert) {
    await visit('/pr/o/r/7/conversations/b');
    const trigger = document.querySelector<HTMLElement>(
      '[data-test-decision]',
    )!;
    trigger.focus();

    await triggerEvent(document, 'keydown', { key: '?' });
    assert.dom('[data-test-key-help]').isFocused();

    await triggerEvent('[data-test-key-help]', 'keydown', { key: 'Shift' });
    await triggerEvent('[data-test-key-help]', 'keydown', { key: 'Tab' });
    assert.dom('[data-test-key-help]').exists('tab moves within it');
    assert.dom('[data-test-key-help] .key-help-close').isFocused();

    await triggerEvent(document, 'keydown', { key: 'Escape' });
    assert.dom('[data-test-key-help]').doesNotExist();
    assert.strictEqual(document.activeElement, trigger);
  });

  test("the key help is a dialog listing every screen's shortcuts", async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerEvent(document, 'keydown', { key: '?' });

    assert.dom('[data-test-key-help]').hasAttribute('role', 'dialog');
    assert.deepEqual(
      findAll('[data-test-key-help] h3').map((one) => one.textContent.trim()),
      ['Everywhere', 'Board', 'Dashboard', 'Terminal', 'Wall', 'Diff'],
    );

    const keys = findAll('[data-test-key-group="Board"] dt').map((one) =>
      one.textContent.trim(),
    );
    const does = findAll('[data-test-key-group="Board"] dd').map((one) =>
      one.textContent.trim(),
    );
    assert.deepEqual(keys.map((key, at) => `${key} ${does[at]}`).slice(4), [
      'a Accept',
      'w Send back for rework',
      'c Reply',
      's Resolve on GitHub',
      'v Resolve on the board',
      '⇧R Reject',
      'f Defer',
      'u Bring back to Ready',
      'g Confirm an assumed done card',
      'm Not confirm, or Move…',
      'b Not fixed',
      'i Write a fix',
      't Try again',
      'x Stop',
      'o Steer it yourself where the panel offers it, GitHub otherwise',
      'e Add to review',
      '⇧G Post now',
      'd Discard',
      'l Withdraw from review',
      'z Full screen the fix, or close it',
    ]);
  });

  test('the key help writes a capital key with the shift sign', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerEvent(document, 'keydown', { key: '?' });

    const caps = findAll('[data-test-key-help] kbd').map((one) =>
      one.textContent.trim(),
    );
    assert.true(caps.includes('⇧S'), 'Send your review');
    assert.false(caps.includes('S'), 'no bare capital');
  });

  test('c opens the reply box on an author row the help promises it on', async function (assert) {
    board().conversations = [board().threadIn('proposed', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');

    await triggerEvent(document, 'keydown', { key: 'c' });

    assert.dom('[data-test-reply]').isFocused();
    assert.deepEqual(board().posted, []);
  });

  test('question mark shows the key help on the dashboard', async function (assert) {
    board().serves = 'hub';
    board().manager = dashboard();
    board().held = [heldPr({ board_url: '/pr/o/r/7' })];
    await visit('/pr/o/r/7/dashboard');

    await triggerEvent(document, 'keydown', { key: '?' });
    assert.dom('[data-test-key-help]').exists();

    await triggerEvent(document, 'keydown', { key: 'x' });
    assert.dom('[data-test-key-help]').doesNotExist();
    assert.dom('[data-test-dashboard]').exists('the x went to the help');
  });

  test('question mark shows the key help on the wall', async function (assert) {
    board().serves = 'hub';
    board().held = [heldPr()];
    await visit('/');

    await triggerEvent(document, 'keydown', { key: '?' });

    assert.dom('[data-test-key-help]').exists();
  });

  test('the shortcut hints show only while slash is held', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    assert.dom('[data-test-github] kbd').isNotVisible('hidden at rest');

    await triggerEvent(document, 'keydown', { key: '/' });
    assert.dom('[data-test-github] kbd').isVisible('shown while held');

    await triggerEvent(document, 'keyup', { key: '/' });
    assert.dom('[data-test-github] kbd').isNotVisible('hidden on release');
  });

  test("the panel's buttons show their keys while slash is held", async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');
    assert.dom('[data-test-decision="unpark"] kbd').isNotVisible();

    await triggerEvent(document, 'keydown', { key: '/' });

    assert.dom('[data-test-decision="unpark"] kbd').isVisible().hasText('u');
  });

  test("a panel button's capital key carries the shift sign", async function (assert) {
    await visit('/pr/o/r/7/conversations/b');

    await triggerEvent(document, 'keydown', { key: '/' });

    assert.dom('[data-test-decision="reject"] kbd').hasText('⇧R');
  });

  test('slash typed into a field shows no hints', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    const box = document.createElement('textarea');
    document.querySelector('#rows')?.appendChild(box);

    await triggerEvent(box, 'keydown', { key: '/' });

    assert.dom('[data-test-github] kbd').isNotVisible();
  });

  test('the hints go when the window loses focus mid-hold', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await triggerEvent(document, 'keydown', { key: '/' });
    await triggerEvent(window, 'blur');

    assert.dom('[data-test-github] kbd').isNotVisible();
  });

  test('a decide key presses the button the panel offers', async function (assert) {
    board().conversations = [board().threadIn('waiting', { key: 'b' })];
    await visit('/pr/o/r/7/conversations/b');

    await triggerEvent(document, 'keydown', { key: 'u' });

    assert.strictEqual(
      board().posted[0]?.verb,
      'unpark',
      'the panel owns which key is which decision, not the key service',
    );
  });
});
