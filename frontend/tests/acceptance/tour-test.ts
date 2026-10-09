import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  findAll,
  triggerKeyEvent,
  visit,
} from '@ember/test-helpers';
import { heldPr, setupFakeBoard } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

module('Acceptance | tour', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  setupFakeClock(hooks);

  function onTheHub(due: boolean, held = [heldPr({ repo: 'acme/widgets' })]) {
    board().serves = 'hub';
    board().watching = ['acme/widgets'];
    board().tourDue = due;
    board().held = held;
  }

  function steps(): string[] {
    return findAll('[data-test-tour-step]').map(
      (one) => one.getAttribute('data-test-tour-step') ?? '',
    );
  }

  test('the first time the wall has pull requests the tour starts on the wall', async function (assert) {
    onTheHub(true);

    await visit('/');

    assert.deepEqual(steps(), ['wall']);
    assert.dom('[data-test-tour]').includesText('Needs you');
  });

  test('the tour waits while the wall has no pull requests yet', async function (assert) {
    onTheHub(true, []);

    await visit('/');

    assert.dom('[data-test-tour]').doesNotExist();
    assert.strictEqual(board().toursSeen, 0);
  });

  test('a tour already seen is not shown again', async function (assert) {
    onTheHub(false);

    await visit('/');

    assert.dom('[data-test-tour]').doesNotExist();
  });

  test('the tour walks the wall, your move, the repo filter, a pull request’s page and where setup and doctor live', async function (assert) {
    onTheHub(true);
    await visit('/');
    const seen = [...steps()];

    for (let step = 1; step < 5; step++) {
      await click('[data-test-tour-next]');
      seen.push(...steps());
    }

    assert.deepEqual(seen, ['wall', 'move', 'filter', 'pr', 'help']);
    assert.dom('[data-test-tour]').includesText('github-orchestrator doctor');
    assert.dom('[data-test-tour-next]').hasText('Done');
    assert.strictEqual(board().toursSeen, 0);
  });

  test('Back returns to the step before', async function (assert) {
    onTheHub(true);
    await visit('/');

    await click('[data-test-tour-next]');
    await click('[data-test-tour-back]');

    assert.deepEqual(steps(), ['wall']);
  });

  test('finishing the tour says it was seen and closes it for good', async function (assert) {
    onTheHub(true);
    await visit('/');

    for (let step = 1; step < 5; step++) await click('[data-test-tour-next]');
    await click('[data-test-tour-next]');

    assert.dom('[data-test-tour]').doesNotExist();
    assert.strictEqual(board().toursSeen, 1);

    await visit('/runs');
    await visit('/');

    assert.dom('[data-test-tour]').doesNotExist();
  });

  test('skipping the tour says it was seen too', async function (assert) {
    onTheHub(true);
    await visit('/');

    await click('[data-test-tour-skip]');

    assert.dom('[data-test-tour]').doesNotExist();
    assert.strictEqual(board().toursSeen, 1);
  });

  test('Escape skips the tour', async function (assert) {
    onTheHub(true);
    await visit('/');

    await triggerKeyEvent(document, 'keydown', 'Escape');

    assert.dom('[data-test-tour]').doesNotExist();
    assert.strictEqual(board().toursSeen, 1);
  });

  test('the tutorial command’s address shows the tour again, and closing it leaves the address', async function (assert) {
    onTheHub(false);

    await visit('/?tour=1');

    assert.deepEqual(steps(), ['wall']);

    await click('[data-test-tour-skip]');

    assert.dom('[data-test-tour]').doesNotExist();
    assert.strictEqual(currentURL(), '/');
  });
});
