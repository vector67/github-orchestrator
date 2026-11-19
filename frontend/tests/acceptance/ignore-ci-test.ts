import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, visit } from '@ember/test-helpers';
import type { CiCheck } from 'frontend/data/api';
import {
  check,
  dashboard,
  heldPr,
  setupFakeBoard,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';

const VERCEL_FAILING: DashboardOver = {
  facts: {
    is_author: true,
    ci_status: 'failing',
    checks: [check('Vercel', 'failed'), check('tests')],
  },
};

function ignored(one: CiCheck): CiCheck {
  return { ...one, ignored: true };
}

const VERCEL_IGNORED: DashboardOver = {
  facts: {
    is_author: true,
    ci_status: 'passing',
    checks: [ignored(check('Vercel', 'failed')), check('tests')],
  },
};

const CI_ROW = '[data-test-status="ci"]';

module('Acceptance | ignore CI', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  async function onTheDashboard(over: DashboardOver): Promise<void> {
    board().held = [heldPr({ dashboard: over })];
    board().manager = dashboard(over);
    await visit('/pr/o/r/7/dashboard');
  }

  function verbs(): string[] {
    return board().posted.map((one) => one.verb);
  }

  function ticked(name: string): HTMLInputElement {
    return document.querySelector(
      `[data-test-ignore-check="${name}"] input`,
    ) as HTMLInputElement;
  }

  test('a failing CI row offers "Ignore CI" beside the red failing', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    assert.dom(`${CI_ROW} [data-test-value]`).hasText('failing');
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('Ignore CI');
    assert.dom('[data-test-band-move]').hasText('Fix CI');
  });

  test('a passing CI row offers no "Ignore CI"', async function (assert) {
    await onTheDashboard({
      facts: { is_author: true, checks: [check('tests')] },
    });

    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).doesNotExist();
  });

  test('"Ignore CI" opens the dialog with the failing check ticked until the next push, and posts nothing', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    await click('[data-test-ignore-ci]');

    assert
      .dom('[data-test-ignore-ci-dialog] .question')
      .hasText('Ignore CI on #7');
    assert.false(ticked('*').checked);
    assert.true(ticked('Vercel').checked);
    assert.false(ticked('tests').checked);
    assert.dom('[data-test-ignore-for="this-push"] input').isChecked();
    assert.dom('[data-test-ignore-ci-submit]').hasText('Ignore');
    assert.deepEqual(verbs(), []);
  });

  const SOMEONE_ELSES_FAILING: DashboardOver = {
    facts: { ...VERCEL_FAILING.facts, is_author: false },
  };

  test('on someone else’s pull request a failing CI reads yellow, not red, and "Ignore CI" is drawn as danger', async function (assert) {
    await onTheDashboard(SOMEONE_ELSES_FAILING);

    assert.dom(`${CI_ROW} [data-test-alarm]`).doesNotExist();
    assert.dom(`${CI_ROW} [data-test-warn]`).exists();
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasClass('danger');
  });

  test('on your own pull request a failing CI reads red, and "Ignore CI" is not drawn as danger', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    assert.dom(`${CI_ROW} [data-test-alarm]`).exists();
    assert.dom(`${CI_ROW} [data-test-warn]`).doesNotExist();
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).doesNotHaveClass('danger');
  });

  test('"Ignore CI" on someone else’s pull request asks first, and the dialog opens only after yes', async function (assert) {
    await onTheDashboard(SOMEONE_ELSES_FAILING);

    await click('[data-test-ignore-ci]');

    assert
      .dom('[data-test-are-you-sure-question]')
      .hasText('#7 is not your pull request. Ignore its CI anyway?');
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();

    await click('[data-test-are-you-sure-submit]');

    assert.dom('[data-test-are-you-sure]').doesNotExist();
    assert.dom('[data-test-ignore-ci-dialog]').exists();
    assert.deepEqual(verbs(), []);
  });

  test('saying no to "Ignore CI" on someone else’s pull request opens nothing', async function (assert) {
    await onTheDashboard(SOMEONE_ELSES_FAILING);

    await click('[data-test-ignore-ci]');
    await click('[data-test-are-you-sure-cancel]');

    assert.dom('[data-test-are-you-sure]').doesNotExist();
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();
  });

  test('each check in the dialog carries the square for how it stands: done when passed, alarm when failed', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    await click('[data-test-ignore-ci]');

    assert.dom('[data-test-ignore-check="Vercel"] .sq').hasClass('alarm');
    assert.dom('[data-test-ignore-check="tests"] .sq').hasClass('done');
  });

  test('Ignore posts the ticked checks and how long, and CI then counts only the rest', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);
    await click('[data-test-ignore-ci]');

    await click('[data-test-ignore-for="this-pr"] input');
    await click('[data-test-ignore-ci-submit]');

    assert.deepEqual(verbs(), ['ignore-ci']);
    assert.strictEqual(
      board().posted[0]!.url,
      '/pr/o/r/7/api/manager:ignore-ci',
    );
    assert.deepEqual(board().posted[0]!.body, {
      checks: ['Vercel'],
      every: false,
      for: 'this-pr',
      count_again: [],
    });
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();
    assert.dom(`${CI_ROW} [data-test-value]`).hasText('passing');
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('1 ignored');
    assert.dom('[data-test-band-move]').doesNotHaveTextContaining('Fix CI');
  });

  test('All checks ticks every check and posts every', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);
    await click('[data-test-ignore-ci]');

    await click('[data-test-ignore-check="*"] input');

    assert.true(ticked('tests').checked);
    await click('[data-test-ignore-ci-submit]');
    assert.deepEqual(board().posted[0]!.body, {
      checks: [],
      every: true,
      for: 'this-push',
      count_again: [],
    });
  });

  test('with nothing ticked, Ignore cannot be pressed', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);
    await click('[data-test-ignore-ci]');

    await click('[data-test-ignore-check="Vercel"] input');

    assert.dom('[data-test-ignore-ci-submit]').isDisabled();
  });

  test('Cancel and × close the dialog and post nothing', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    await click('[data-test-ignore-ci]');
    await click('[data-test-ignore-ci-cancel]');
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();

    await click('[data-test-ignore-ci]');
    await click('[data-test-ignore-ci-dialog] .dialog-close');
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();
    assert.deepEqual(verbs(), []);
  });

  test('ignored checks are counted on one button in the CI row and left out of what failed', async function (assert) {
    await onTheDashboard(VERCEL_IGNORED);

    assert.dom(`${CI_ROW} [data-test-value]`).hasText('passing');
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('1 ignored');
    assert
      .dom(`${CI_ROW} [data-test-ignore-ci]`)
      .hasAttribute('data-opens-dialog', 'true');
    assert.dom(`${CI_ROW} [data-test-stop-ignoring-ci]`).doesNotExist();
    assert.dom('[data-test-band-move]').doesNotHaveTextContaining('Fix CI');
  });

  test('the ignored count opens the dialog with each ignored check ticked, and Save waits for a change', async function (assert) {
    await onTheDashboard(VERCEL_IGNORED);

    await click(`${CI_ROW} [data-test-ignore-ci]`);

    assert.true(ticked('Vercel').checked);
    assert.false(ticked('Vercel').disabled);
    assert.false(ticked('tests').checked);
    assert.dom('[data-test-ignore-ci-submit]').hasText('Save');
    assert.dom('[data-test-ignore-ci-submit]').isDisabled();
    assert.dom('[data-test-stop-ignoring-ci]').hasText('Stop ignoring');
    assert.deepEqual(verbs(), []);
  });

  test('unticking an ignored check and saving counts it again', async function (assert) {
    await onTheDashboard(VERCEL_IGNORED);
    await click(`${CI_ROW} [data-test-ignore-ci]`);

    await click('[data-test-ignore-check="Vercel"] input');
    await click('[data-test-ignore-ci-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      checks: [],
      every: false,
      for: 'this-push',
      count_again: ['Vercel'],
    });
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();
    assert.dom(`${CI_ROW} [data-test-value]`).hasText('failing');
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('Ignore CI');
  });

  test('ticking another check beside an ignored one ignores it too and keeps the first', async function (assert) {
    await onTheDashboard(VERCEL_IGNORED);
    await click(`${CI_ROW} [data-test-ignore-ci]`);

    await click('[data-test-ignore-check="tests"] input');
    await click('[data-test-ignore-ci-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      checks: ['tests'],
      every: false,
      for: 'this-push',
      count_again: [],
    });
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('2 ignored');
  });

  test('a dialog opened on a failing CI with nothing ignored offers no "Stop ignoring"', async function (assert) {
    await onTheDashboard(VERCEL_FAILING);

    await click('[data-test-ignore-ci]');

    assert.dom('[data-test-stop-ignoring-ci]').doesNotExist();
  });

  test('"Stop ignoring" in the dialog counts every check again', async function (assert) {
    await onTheDashboard(VERCEL_IGNORED);
    await click(`${CI_ROW} [data-test-ignore-ci]`);

    await click('[data-test-stop-ignoring-ci]');

    assert.deepEqual(verbs(), ['stop-ignoring-ci']);
    assert.strictEqual(
      board().posted[0]!.url,
      '/pr/o/r/7/api/manager:stop-ignoring-ci',
    );
    assert.dom('[data-test-ignore-ci-dialog]').doesNotExist();
    assert.dom(`${CI_ROW} [data-test-value]`).hasText('failing');
    assert.dom(`${CI_ROW} [data-test-ignore-ci]`).hasText('Ignore CI');
    assert.dom('[data-test-band-move]').hasText('Fix CI');
  });
});
