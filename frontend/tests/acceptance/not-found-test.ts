import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { visit } from '@ember/test-helpers';
import { setupFakeBoard } from 'frontend/tests/helpers/fake-board';

module('Acceptance | not found', function (hooks) {
  setupApplicationTest(hooks);
  setupFakeBoard(hooks);

  test('a path the board never had says so instead of throwing', async function (assert) {
    await visit('/panel/PRRT_aa');

    assert
      .dom('[data-test-not-found]')
      .exists(
        'the old board left urls behind, and the router owns them all now',
      );
  });

  test('a pull request path with no number in it says so', async function (assert) {
    await visit('/pr/acme/widgets/latest');

    assert.dom('[data-test-not-found]').exists();
    assert.dom('[data-test-old-link]').doesNotExist();
  });
});
