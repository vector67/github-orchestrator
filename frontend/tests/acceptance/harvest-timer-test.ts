import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, find, visit } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';

const HARVEST_TIMER = 'harvest-timer';

module('Acceptance | harvest timer', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.afterEach(function () {
    localStorage.removeItem(HARVEST_TIMER);
    document.getElementById('harvest-messaging')?.remove();
  });

  function extensionRunning(): void {
    const messaging = document.createElement('div');
    messaging.id = 'harvest-messaging';
    messaging.hidden = true;
    document.body.appendChild(messaging);
  }

  async function switchedOn(): Promise<void> {
    await visit('/pr/o/r/7/dashboard');
    await click('[data-test-settings-open]');
    await click('[data-test-harvest-toggle]');
  }

  function json(name: string): unknown {
    return JSON.parse(find('.harvest-timer')!.getAttribute(name)!);
  }

  test('the extension finds no timer button until the settings menu turns it on', async function (assert) {
    extensionRunning();
    await visit('/pr/o/r/7/dashboard');

    assert.dom('.harvest-timer').doesNotExist();

    await switchedOn();

    assert.dom('[data-test-harvest-toggle]').hasText('Harvest timer: on');
    assert.strictEqual(localStorage.getItem(HARVEST_TIMER), 'on');
    assert.dom('[data-test-harvest-setup]').doesNotExist();
  });

  test('the timer button names the pull request as the extension does on github', async function (assert) {
    extensionRunning();
    await switchedOn();

    assert.strictEqual(
      JSON.stringify(json('data-item')),
      JSON.stringify({ id: '7', name: '#7: Fix the widget' }),
    );
    assert.strictEqual(
      JSON.stringify(json('data-group')),
      JSON.stringify({ id: 'r', name: 'r' }),
    );
    assert.strictEqual(
      JSON.stringify(json('data-account')),
      JSON.stringify({ id: 'o' }),
    );
    assert
      .dom('.harvest-timer')
      .hasAttribute('data-permalink', 'https://github.com/o/r/pull/7')
      .hasAttribute('data-skip-styling', 'true');
  });

  test('turning it on without the extension on the board offers to set it up', async function (assert) {
    await switchedOn();

    assert.dom('[data-test-harvest-setup]').exists();

    await click('[data-test-harvest-prepare]');

    assert.deepEqual(
      board()
        .posted.filter((one) =>
          one.url.endsWith('/api/harvest-extension:prepare'),
        )
        .map((one) => one.url),
      ['/api/harvest-extension:prepare'],
    );
    assert
      .dom('[data-test-harvest-folder]')
      .hasText(board().harvestExtensionFolder);
    assert.dom('[data-test-harvest-steps] li').exists({ count: 3 });
  });

  test('a setup the server refuses says why', async function (assert) {
    await switchedOn();
    board().refusal = {
      status: 409,
      code: 'harvest-extension-missing',
      detail: 'Chrome has no Harvest Time Tracker installed',
    };

    await click('[data-test-harvest-prepare]');

    assert
      .dom('[data-test-harvest-setup]')
      .includesText('Chrome has no Harvest Time Tracker installed');
  });

  test('closing the setup leaves the switch on', async function (assert) {
    await switchedOn();

    await click('[data-test-harvest-setup-close]');

    assert.dom('[data-test-harvest-setup]').doesNotExist();
    assert.strictEqual(localStorage.getItem(HARVEST_TIMER), 'on');
  });
});
