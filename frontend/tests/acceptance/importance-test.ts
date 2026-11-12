import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, findAll, visit } from '@ember/test-helpers';
import type { Importance, PrFacts } from 'frontend/data/api';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';

const ROW = '[data-test-wall-row="o/r#7"]';

const WAITING_ON_REVIEW: Partial<PrFacts> = {
  ci_status: 'passing',
  merge_state: 'blocked',
  pending_reviewers: ['grace'],
  review_decision: 'review-required',
  unresolved_threads: 0,
};

module('Acceptance | importance', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function serve(over: DashboardOver): void {
    board().held = [heldPr({ dashboard: over })];
    board().manager = dashboard(over);
  }

  function ranked(importance: Importance | null): DashboardOver {
    return { facts: WAITING_ON_REVIEW, manager: { importance } };
  }

  function posts(): unknown[][] {
    return board().posted.map((one) => [one.verb, one.body]);
  }

  test('a row with no importance offers Set importance with a red dot', async function (assert) {
    serve(ranked(null));
    await visit('/');

    assert.dom(`${ROW} [data-test-set-importance]`).hasText('Set importance');
    assert.dom(`${ROW} [data-test-importance-unset]`).exists();
  });

  test('a row whose importance is set still offers Set importance, without the dot', async function (assert) {
    serve(ranked('normal'));
    await visit('/');

    assert.dom(`${ROW} [data-test-set-importance]`).hasText('Set importance');
    assert.dom(`${ROW} [data-test-importance-unset]`).doesNotExist();
  });

  test('Set importance on a row asks which, marks the current one and saves the pick', async function (assert) {
    serve(ranked('someday'));
    await visit('/');

    await click(`${ROW} [data-test-set-importance]`);

    assert.dom('[data-test-importance-confirm]').exists();
    assert.deepEqual(
      findAll('[data-test-importance-option]').map((one) =>
        one.getAttribute('data-test-importance-option'),
      ),
      ['important', 'normal', 'someday'],
    );
    assert
      .dom('[data-test-importance-option="someday"]')
      .hasAttribute('aria-current', 'true');

    await click('[data-test-importance-option="important"]');

    assert.deepEqual(posts(), [['set', { importance: 'important' }]]);
    assert.dom('[data-test-importance-confirm]').doesNotExist();
    assert.dom(`${ROW} [data-test-state="importance"]`).hasText('important');
  });

  test('a row due a nudge offers I nudged them, and saying so sends it back to waiting', async function (assert) {
    serve({
      facts: WAITING_ON_REVIEW,
      manager: { importance: 'important', nudge_due: true },
    });
    await visit('/');

    assert.dom(ROW).hasAttribute('data-move', 'nudge');

    await click(`${ROW} [data-test-nudged]`);

    assert.deepEqual(posts(), [['nudged', null]]);
    assert.dom(ROW).hasAttribute('data-move', 'await-review');
    assert.dom(`${ROW} [data-test-nudged]`).doesNotExist();
  });

  test('a row with no nudge due offers no I nudged them', async function (assert) {
    serve(ranked('important'));
    await visit('/');

    assert.dom(`${ROW} [data-test-nudged]`).doesNotExist();
  });

  test('the dashboard offers Set importance beside Put on hold, with the red dot until it is set', async function (assert) {
    serve(ranked(null));
    await visit('/pr/o/r/7/dashboard');

    const controls = findAll('[data-test-control]').map((one) =>
      one.getAttribute('data-test-control'),
    );
    assert.strictEqual(
      controls[controls.indexOf('hold') + 1],
      'set-importance',
    );
    assert
      .dom('[data-test-control="set-importance"] [data-test-importance-unset]')
      .exists();

    await click('[data-test-control="set-importance"]');
    await click('[data-test-importance-option="normal"]');

    assert.deepEqual(posts(), [['set', { importance: 'normal' }]]);
    assert
      .dom('[data-test-control="set-importance"] [data-test-importance-unset]')
      .doesNotExist();
  });

  test('the dashboard offers I nudged them while a nudge is due', async function (assert) {
    serve({
      facts: WAITING_ON_REVIEW,
      manager: { importance: 'important', nudge_due: true },
    });
    await visit('/pr/o/r/7/dashboard');

    await click('[data-test-control="nudged"]');

    assert.deepEqual(posts(), [['nudged', null]]);
    assert.dom('[data-test-control="nudged"]').doesNotExist();
  });

  test('an importance the server refuses says so on the dashboard', async function (assert) {
    serve(ranked(null));
    await visit('/pr/o/r/7/dashboard');
    board().refusal = {
      status: 400,
      code: 'malformed-request',
      detail: 'importance: not one of important, normal, someday',
    };

    await click('[data-test-control="set-importance"]');
    await click('[data-test-importance-option="important"]');

    assert
      .dom('[data-test-importance-refused]')
      .includesText('Importance not set');
    assert
      .dom('[data-test-control="set-importance"] [data-test-importance-unset]')
      .exists();
  });

  const BADGES: [string, DashboardOver, string | null][] = [
    ['importance set and nothing wrong', ranked('normal'), null],
    ['importance not set', ranked(null), '1'],
    [
      'importance not set, CI failing and behind main',
      {
        facts: {
          ...WAITING_ON_REVIEW,
          ci_status: 'failing',
          merge_state: 'behind',
        },
        manager: { importance: null },
      },
      '3',
    ],
    [
      'importance set, CI failing',
      {
        facts: { ...WAITING_ON_REVIEW, ci_status: 'failing' },
        manager: { importance: 'someday' },
      },
      '1',
    ],
  ];

  for (const [name, over, badge] of BADGES) {
    test(`the Dashboard tab counts what is wrong on the pull request: ${name}`, async function (assert) {
      serve(over);
      await visit('/pr/o/r/7/board');

      if (badge === null) {
        assert
          .dom('[data-test-tab="dashboard"] [data-test-tab-badge]')
          .doesNotExist();
      } else {
        assert
          .dom('[data-test-tab="dashboard"] [data-test-tab-badge]')
          .hasText(badge);
      }
    });
  }

  test('the wall row carries only the red dot, never the tab’s count', async function (assert) {
    serve({
      facts: { ...WAITING_ON_REVIEW, ci_status: 'failing' },
      manager: { importance: null },
    });
    await visit('/');

    assert.dom(`${ROW} [data-test-tab-badge]`).doesNotExist();
    assert.dom(`${ROW} [data-test-importance-unset]`).exists();
  });
});
