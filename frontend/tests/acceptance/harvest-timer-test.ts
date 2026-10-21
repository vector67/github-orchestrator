import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';

const HARVEST_TIMER = 'harvest-timer';

module('Acceptance | harvest timer', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().harvestTimer = { tracked: true, running: false };
  });

  hooks.afterEach(function () {
    localStorage.removeItem(HARVEST_TIMER);
  });

  async function switchedOn(): Promise<void> {
    await visit('/pr/o/r/7/dashboard');
    await click('[data-test-settings-open]');
    await click('[data-test-harvest-toggle]');
  }

  function timerVerbs(): string[] {
    return board()
      .posted.filter((one) => one.url.includes('/api/harvest-timer:'))
      .map((one) => one.verb);
  }

  test('the timer is off until the settings menu turns it on', async function (assert) {
    await visit('/pr/o/r/7/dashboard');

    assert.dom('[data-test-harvest-timer]').doesNotExist();

    await click('[data-test-settings-open]');

    assert.dom('[data-test-harvest-toggle]').hasText('Harvest timer: off');

    await click('[data-test-harvest-toggle]');

    assert.dom('[data-test-harvest-toggle]').hasText('Harvest timer: on');
    assert.dom('[data-test-harvest-timer]').exists();
    assert.strictEqual(localStorage.getItem(HARVEST_TIMER), 'on');
  });

  test('a pr whose repo tracks no harvest project shows no timer', async function (assert) {
    board().harvestTimer = { tracked: false, running: false };

    await switchedOn();

    assert.dom('[data-test-harvest-timer]').doesNotExist();
  });

  test('clicking the timer starts it on the pr', async function (assert) {
    await switchedOn();

    assert
      .dom('[data-test-harvest-timer]')
      .hasAttribute('aria-pressed', 'false');

    await click('[data-test-harvest-timer]');

    assert.deepEqual(timerVerbs(), ['start']);
    assert
      .dom('[data-test-harvest-timer]')
      .hasAttribute('aria-pressed', 'true');
  });

  test('clicking a running timer asks before it stops it', async function (assert) {
    board().harvestTimer = { tracked: true, running: true };
    await switchedOn();

    await click('[data-test-harvest-timer]');

    assert
      .dom('[data-test-harvest-stop-confirm]')
      .includesText('Stop the timer?');
    assert.deepEqual(timerVerbs(), []);

    await click('[data-test-harvest-stop]');

    assert.deepEqual(timerVerbs(), ['stop']);
    assert.dom('[data-test-harvest-stop-confirm]').doesNotExist();
    assert
      .dom('[data-test-harvest-timer]')
      .hasAttribute('aria-pressed', 'false');
  });

  test('cancelling the question leaves the timer running', async function (assert) {
    board().harvestTimer = { tracked: true, running: true };
    await switchedOn();

    await click('[data-test-harvest-timer]');
    await click('[data-test-harvest-stop-cancel]');

    assert.deepEqual(timerVerbs(), []);
    assert.dom('[data-test-harvest-stop-confirm]').doesNotExist();
    assert
      .dom('[data-test-harvest-timer]')
      .hasAttribute('aria-pressed', 'true');
  });

  test('harvest refusing to start says why and leaves the timer stopped', async function (assert) {
    await switchedOn();
    board().refusal = {
      status: 502,
      code: 'harvest-refused',
      detail: 'Harvest refused POST /time_entries: HTTP Error 401',
    };

    await click('[data-test-harvest-timer]');

    assert
      .dom('[data-test-toast]')
      .includesText('Harvest refused POST /time_entries: HTTP Error 401');
    assert
      .dom('[data-test-harvest-timer]')
      .hasAttribute('aria-pressed', 'false');
  });
});
