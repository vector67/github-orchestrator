import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, fillIn, focus, triggerEvent, visit } from '@ember/test-helpers';
import {
  DESCRIPTION_SAVED_AT,
  dashboard,
  heldPr,
  prSummary,
  setupFakeBoard,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';

const WRITTEN = '🤖 Renames **the** helper.';

module('Acceptance | pull request description', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function described(body = WRITTEN): void {
    board().pullRequest = { ...board().pullRequest, body };
  }

  function onTheHub(over: DashboardOver = {}): void {
    board().manager = dashboard(over);
    board().held = [heldPr({ dashboard: over })];
  }

  async function press(key: string): Promise<void> {
    await triggerEvent(document, 'keydown', { key });
  }

  function sent(): { verb: string; body: unknown }[] {
    return board().posted.map(({ verb, body }) => ({ verb, body }));
  }

  function saves(): { verb: string; body: unknown }[] {
    return sent().filter(({ verb }) => verb === 'save-description');
  }

  test('the summary tab shows the description drawn from its markdown under the title, with Edit', async function (assert) {
    described();

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-title]').hasText('Fix the widget');
    assert
      .dom('[data-test-description] strong')
      .hasText('the', 'the description is drawn from its markdown');
    assert.dom('[data-test-description]').hasText('🤖 Renames the helper.');
    assert.dom('[data-test-description-edit]').hasText('Edit');
  });

  function longSummary(): void {
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: '2026-09-12T10:00:00Z',
      markdown: Array.from({ length: 200 }, (_, n) => `Paragraph ${n}.`).join(
        '\n\n',
      ),
    });
  }

  async function scrollSummaryDown(): Promise<void> {
    const body = document.querySelector<HTMLElement>(
      '[data-test-summary-markdown]',
    )!;
    body.scrollTop += 200;
    await triggerEvent(body, 'scroll');
  }

  test('scrolling the summary down folds the description to Show description beside the title, which opens it again with Edit and Hide', async function (assert) {
    described();
    longSummary();
    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-description-show]').doesNotExist();
    assert.dom('[data-test-description-hide]').hasText('Hide');

    await scrollSummaryDown();

    assert.dom('[data-test-description]').doesNotExist();
    assert.dom('[data-test-description-edit]').doesNotExist();
    assert.dom('[data-test-description-hide]').doesNotExist();
    assert
      .dom('[data-test-summary-title-row] [data-test-description-show]')
      .hasText('Show description');

    await click('[data-test-description-show]');

    assert.dom('[data-test-description]').hasText('🤖 Renames the helper.');
    assert.dom('[data-test-description-edit]').hasText('Edit');
    assert.dom('[data-test-description-hide]').hasText('Hide');
    assert.dom('[data-test-description-show]').doesNotExist();
  });

  test('scrolling the summary back to the top brings the description back', async function (assert) {
    described();
    longSummary();
    await visit('/pr/o/r/7/summary');
    await scrollSummaryDown();
    const body = document.querySelector<HTMLElement>(
      '[data-test-summary-markdown]',
    )!;

    body.scrollTop = 0;
    await triggerEvent(body, 'scroll');

    assert.dom('[data-test-description]').hasText('🤖 Renames the helper.');
    assert.dom('[data-test-description-show]').doesNotExist();
  });

  test('Hide folds the description to Show description', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');

    await click('[data-test-description-hide]');

    assert.dom('[data-test-description]').doesNotExist();
    assert.dom('[data-test-description-show]').hasText('Show description');
  });

  test('scrolling the summary while editing the description keeps the editor open', async function (assert) {
    described();
    longSummary();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', '🤖 Your words.');

    await scrollSummaryDown();

    assert.dom('[data-test-description-text]').hasValue('🤖 Your words.');
  });

  test('Edit opens the title and the markdown in a box with Write and Preview, and Save writes both and shows them', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');

    await click('[data-test-description-edit]');

    assert.dom('[data-test-description-title]').hasValue('Fix the widget');
    assert.dom('[data-test-description-text]').hasValue(WRITTEN);
    assert
      .dom('[data-test-description-tab="write"]')
      .hasAttribute('aria-selected', 'true');

    await fillIn('[data-test-description-title]', 'Rename the helper');
    await fillIn('[data-test-description-text]', '🤖 Renames it _for good_.');
    await click('[data-test-description-tab="preview"]');

    assert.dom('[data-test-description-preview] em').hasText('for good');
    assert.dom('[data-test-description-text]').doesNotExist();

    await click('[data-test-description-save]');

    assert.deepEqual(saves(), [
      {
        verb: 'save-description',
        body: {
          title: 'Rename the helper',
          body: '🤖 Renames it _for good_.',
          started_from: WRITTEN,
        },
      },
    ]);
    assert.dom('[data-test-description-title]').doesNotExist();
    assert.dom('[data-test-summary-title]').hasText('Rename the helper');
    assert.dom('[data-test-description] em').hasText('for good');
  });

  test('Cancel throws the edit away and saves nothing', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', 'Something else.');

    await click('[data-test-description-cancel]');

    assert.deepEqual(saves(), []);
    assert.dom('[data-test-description]').hasText('🤖 Renames the helper.');

    await click('[data-test-description-edit]');

    assert.dom('[data-test-description-text]').hasValue(WRITTEN);
  });

  test('a description changed on GitHub since Edit keeps your text and shows GitHub’s beside it, to save over or start again from', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', '🤖 Your words.');
    board().onGithub = 'A **teammate’s** words.';

    await click('[data-test-description-save]');

    assert.dom('[data-test-description-text]').hasValue('🤖 Your words.');
    assert
      .dom('[data-test-description-moved]')
      .containsText('The description changed on GitHub since you opened it.');
    assert
      .dom('[data-test-description-on-github] strong')
      .hasText('teammate’s');

    await click('[data-test-description-save-over]');

    assert.deepEqual(
      saves().map(({ body }) => body),
      [
        {
          title: 'Fix the widget',
          body: '🤖 Your words.',
          started_from: WRITTEN,
        },
        {
          title: 'Fix the widget',
          body: '🤖 Your words.',
          started_from: 'A **teammate’s** words.',
        },
      ],
    );
    assert.dom('[data-test-description]').hasText('🤖 Your words.');
  });

  test('starting again from GitHub’s description puts its text in the box', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', '🤖 Your words.');
    board().onGithub = 'A teammate’s words.';
    await click('[data-test-description-save]');

    await click('[data-test-description-start-again]');

    assert.dom('[data-test-description-text]').hasValue('A teammate’s words.');
    assert.dom('[data-test-description-moved]').doesNotExist();

    await click('[data-test-description-save]');

    assert.deepEqual(saves().at(-1)?.body, {
      title: 'Fix the widget',
      body: 'A teammate’s words.',
      started_from: 'A teammate’s words.',
    });
  });

  test('a summary finished before the description was saved says so above its report, and never reruns', async function (assert) {
    described();
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: '2026-09-12T09:00:00Z',
      markdown: '# What it asks',
    });
    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-before-description]').doesNotExist();

    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', '🤖 Your words.');
    await click('[data-test-description-save]');

    assert
      .dom('[data-test-summary-before-description]')
      .hasText('Written before the description changed');
    assert.deepEqual(
      sent().map(({ verb }) => verb),
      ['check-description', 'save-description'],
    );
  });

  test('a summary finished after the last save, or none at all, says nothing about the description', async function (assert) {
    board().pullRequest = {
      ...board().pullRequest,
      body: WRITTEN,
      description_saved_at: DESCRIPTION_SAVED_AT,
    };
    board().summary = prSummary({
      head_sha: 'c0ffee1',
      exit_status: 0,
      finished: '2026-09-12T10:00:00Z',
      markdown: '# What it asks',
    });

    await visit('/pr/o/r/7/summary');

    assert.dom('[data-test-summary-markdown]').exists();
    assert.dom('[data-test-summary-before-description]').doesNotExist();
  });

  test('Mark ready lists a description Claude wrote first, and showing it checks it without touching the 🤖', async function (assert) {
    described();
    onTheHub({ facts: { draft: true } });
    await visit('/pr/o/r/7/dashboard');

    await press('r');

    assert
      .dom('[data-test-ready-confirm] [data-test-outstanding]')
      .hasAttribute('data-test-outstanding', 'description')
      .containsText('Description written by Claude');
    assert.dom('[data-test-ready-description]').doesNotExist();

    await click('[data-test-ready-show-description]');

    assert
      .dom('[data-test-ready-description] strong')
      .hasText('the', 'the description is drawn from its markdown');
    assert.deepEqual(sent(), [
      { verb: 'check-description', body: { body: WRITTEN } },
    ]);
    assert.dom('[data-test-outstanding="description"]').doesNotExist();
    assert.dom('[data-test-ready-description]').exists();
  });

  test('Mark ready on the wall reads the description, so a description Claude wrote is listed there too', async function (assert) {
    described();
    board().held = [heldPr({ dashboard: { facts: { draft: true } } })];
    await visit('/');
    await press('j');

    await press('r');

    assert
      .dom('[data-test-ready-confirm] [data-test-outstanding]')
      .hasAttribute('data-test-outstanding', 'description');
  });

  test('a description that does not start with 🤖, or one already checked, is not outstanding', async function (assert) {
    described('Renames the helper. 🤖');
    onTheHub({ facts: { draft: true } });
    await visit('/pr/o/r/7/dashboard');

    await press('r');

    assert.dom('[data-test-outstanding="description"]').doesNotExist();

    await press('Escape');
    board().pullRequest = {
      ...board().pullRequest,
      body: WRITTEN,
      description_checked: true,
    };
    await visit('/pr/o/r/7/summary');
    await visit('/pr/o/r/7/dashboard');
    await press('r');

    assert.dom('[data-test-ready-confirm]').exists();
    assert.dom('[data-test-outstanding="description"]').doesNotExist();
  });

  test('clicking into the description field checks a description Claude wrote, and leaves the text as it was', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');

    await focus('[data-test-description-text]');

    assert.deepEqual(sent(), [
      { verb: 'check-description', body: { body: WRITTEN } },
    ]);
    assert.dom('[data-test-description-text]').hasValue(WRITTEN);
  });

  test('a save GitHub refuses says why and keeps your text', async function (assert) {
    described();
    await visit('/pr/o/r/7/summary');
    await click('[data-test-description-edit]');
    await fillIn('[data-test-description-text]', '🤖 Your words.');
    board().refusal = {
      status: 502,
      code: 'github-rejected',
      detail: 'gh: Not Found (HTTP 404)',
    };

    await click('[data-test-description-save]');

    assert
      .dom('[data-test-description-refused]')
      .containsText('gh: Not Found (HTTP 404)');
    assert.dom('[data-test-description-text]').hasValue('🤖 Your words.');
  });
});
