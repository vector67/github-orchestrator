import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import { setupFakeBoard, thread } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

const SLOW = 5000;

module('Acceptance | failure', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    board().conversations = [thread({ key: 'k1' })];
  });

  test('one refresh that cannot reach the board raises no banner, and the second does', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    board().down = true;
    await clock().tick(SLOW);

    assert.dom('[data-test-banner]').doesNotExist('one miss is a blip');

    await clock().tick(SLOW);

    assert
      .dom('[data-test-banner]')
      .hasText(
        'the board server is not answering',
        'two in a row are an outage, and the banner names the trouble',
      );
  });

  test('one good refresh after two failed ones takes the banner down', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    board().down = true;
    await clock().tick(SLOW);
    await clock().tick(SLOW);

    board().down = false;
    await clock().tick(SLOW);

    assert.dom('[data-test-banner]').doesNotExist();
  });

  test('a board whose health answers while its reads do not says the system is under heavy load', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    board().broken = /\/api\/(?!health$)/;
    await clock().tick(SLOW);
    await clock().tick(SLOW);

    assert.dom('[data-test-banner]').hasText('the system is under heavy load');
  });

  test('a read that fails each time it is asked raises the banner even while the reads beside it answer', async function (assert) {
    await visit('/pr/o/r/7/conversations');
    board().broken = /\/api\/people$/;

    board().conversations = [thread({ key: 'k1' }), thread({ key: 'k2' })];
    await clock().tick(SLOW);
    await clock().tick(SLOW);
    board().conversations = [thread({ key: 'k1' })];
    await clock().tick(SLOW);

    assert.dom('[data-test-banner]').hasText('the system is under heavy load');
  });

  test('a refresh that fails does not empty the board', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    board().down = true;
    await clock().tick(SLOW);

    assert.dom('#c-k1').exists('the rows it already had are still drawn');
  });

  test('a panel that cannot load reports why to the board log', async function (assert) {
    board().broken = /\/api\/conversations\/k1\/comments/;

    await visit('/pr/o/r/7/conversations/k1');

    const [report] = board().reported;
    assert.strictEqual(report?.where, 'panel');
    assert.strictEqual(report?.message, 'connection refused');
  });

  test('a board that answers leaves the page nothing to report', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    assert.deepEqual(board().reported, []);
  });

  test('a panel the board will not answer keeps the banner standing', async function (assert) {
    board().broken = /\/api\/conversations\/k1\//;

    await visit('/pr/o/r/7/conversations/k1');

    const raised = document.querySelector('[data-test-banner]');
    assert.ok(raised, 'the card it cannot read says the board is not there');

    await clock().tick(SLOW);

    assert.strictEqual(
      document.querySelector('[data-test-banner]'),
      raised,
      'the rail clearing a banner the panel still wants blinks it every poll',
    );
  });
});
