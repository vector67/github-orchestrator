import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  click,
  currentURL,
  findAll,
  triggerKeyEvent,
  visit,
} from '@ember/test-helpers';
import {
  heldPr,
  setupFakeBoard,
  threadRow,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';

module('Acceptance | repo filter', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  const needsYou = { threads: [threadRow('h1', 'ready', 'open', 'human')] };

  function twoRepos(): void {
    board().serves = 'hub';
    board().watching = ['acme/gadgets', 'acme/widgets'];
    board().held = [
      heldPr({ repo: 'acme/widgets', number: 1, dashboard: needsYou }),
      heldPr({ repo: 'acme/gadgets', number: 2, dashboard: needsYou }),
      heldPr({ repo: 'acme/gadgets', number: 3 }),
    ];
  }

  function attribute(selector: string, name: string): string[] {
    return findAll(selector).map((one) => one.getAttribute(name) ?? '');
  }

  function rows(): string[] {
    return attribute('[data-test-wall-row]', 'data-test-wall-row');
  }

  function switcherRows(): string[] {
    return attribute('[data-test-switcher-row]', 'data-test-switcher-row');
  }

  test('with no selection the wall shows every watched repo’s pull requests', async function (assert) {
    twoRepos();

    await visit('/');

    assert.deepEqual(rows(), [
      'acme/gadgets#2',
      'acme/widgets#1',
      'acme/gadgets#3',
    ]);
  });

  test('a repo selected in the address hides the other repo’s rows and the groups they leave empty', async function (assert) {
    twoRepos();

    await visit('/?repos=acme/widgets');

    assert.deepEqual(rows(), ['acme/widgets#1']);
    assert.deepEqual(
      attribute('[data-test-wall-group]', 'data-test-wall-group'),
      ['needs-you'],
    );
  });

  test('a pull request’s page counts and lists only the selected repos’ pull requests', async function (assert) {
    twoRepos();

    await visit('/pr/acme/widgets/1?repos=acme/widgets');

    assert.dom('[data-test-switcher-open]').includesText('1 needs you');

    await click('[data-test-switcher-open]');

    assert.deepEqual(switcherRows(), ['acme/widgets#1']);
  });

  test('without a selection a pull request’s page counts and lists every repo', async function (assert) {
    twoRepos();

    await visit('/pr/acme/widgets/1');

    assert.dom('[data-test-switcher-open]').includesText('2 need you');

    await click('[data-test-switcher-open]');

    assert.deepEqual(switcherRows(), [
      'acme/gadgets#2',
      'acme/widgets#1',
      'acme/gadgets#3',
    ]);
  });

  function choices(): string[] {
    return attribute('[data-test-repo-choice]', 'data-test-repo-choice');
  }

  function checked(): string[] {
    return findAll('[data-test-repo-choice]')
      .filter((one) => one.querySelector<HTMLInputElement>('input')?.checked)
      .map((one) => one.getAttribute('data-test-repo-choice') ?? '');
  }

  function chosenInAddress(): string | null {
    return new URL(currentURL(), 'http://hub').searchParams.get('repos');
  }

  test('the top bar’s filter says All repos and opens on All repos then each watched repo, every one checked', async function (assert) {
    twoRepos();
    await visit('/');

    assert.dom('[data-test-repo-filter]').hasText('All repos');
    assert.dom('[data-test-repo-menu]').doesNotExist();

    await click('[data-test-repo-filter]');

    assert
      .dom('[data-test-repo-menu] [data-test-repo-all]')
      .hasText('All repos');
    assert.deepEqual(choices(), ['acme/gadgets', 'acme/widgets']);
    assert.deepEqual(checked(), ['acme/gadgets', 'acme/widgets']);
  });

  test('one click on a repo’s name selects only it, in the address, the wall and the filter', async function (assert) {
    twoRepos();
    await visit('/');
    await click('[data-test-repo-filter]');

    await click('[data-test-repo-choice="acme/widgets"] [data-test-repo-only]');

    assert.strictEqual(chosenInAddress(), 'acme/widgets');
    assert.deepEqual(rows(), ['acme/widgets#1']);
    assert.dom('[data-test-repo-filter]').hasText('acme/widgets');
    assert.dom('[data-test-repo-menu]').doesNotExist();
  });

  test('the checkboxes build a selection, and All repos clears it', async function (assert) {
    board().serves = 'hub';
    board().watching = ['acme/gadgets', 'acme/sprockets', 'acme/widgets'];
    board().held = [
      heldPr({ repo: 'acme/widgets', number: 1 }),
      heldPr({ repo: 'acme/gadgets', number: 2 }),
      heldPr({ repo: 'acme/sprockets', number: 3 }),
    ];
    await visit('/?repos=acme/widgets');
    await click('[data-test-repo-filter]');

    await click('[data-test-repo-choice="acme/gadgets"] input');

    assert.strictEqual(chosenInAddress(), 'acme/widgets,acme/gadgets');
    assert.deepEqual(checked(), ['acme/gadgets', 'acme/widgets']);
    assert.deepEqual(rows().sort(), ['acme/gadgets#2', 'acme/widgets#1']);
    assert.dom('[data-test-repo-filter]').hasText('2 repos');

    await click('[data-test-repo-all]');

    assert.strictEqual(chosenInAddress(), null);
    assert.strictEqual(rows().length, 3);
    assert.dom('[data-test-repo-filter]').hasText('All repos');
  });

  test('unchecking a repo from All repos selects every other one', async function (assert) {
    twoRepos();
    await visit('/');
    await click('[data-test-repo-filter]');

    await click('[data-test-repo-choice="acme/gadgets"] input');

    assert.strictEqual(chosenInAddress(), 'acme/widgets');
    assert.deepEqual(rows(), ['acme/widgets#1']);
  });

  test('Esc closes the filter without changing the selection', async function (assert) {
    twoRepos();
    await visit('/?repos=acme/widgets');
    await click('[data-test-repo-filter]');

    await triggerKeyEvent(document, 'keydown', 'Escape');

    assert.dom('[data-test-repo-menu]').doesNotExist();
    assert.strictEqual(chosenInAddress(), 'acme/widgets');
  });

  test('the last selection comes back on a visit with no selection in the address', async function (assert) {
    twoRepos();
    await visit('/');
    await click('[data-test-repo-filter]');
    await click('[data-test-repo-choice="acme/gadgets"] [data-test-repo-only]');

    await visit('/');

    assert.deepEqual(rows(), ['acme/gadgets#2', 'acme/gadgets#3']);
    assert.dom('[data-test-repo-filter]').hasText('acme/gadgets');
  });

  test('a selection opened from an address is the one remembered', async function (assert) {
    twoRepos();
    await visit('/?repos=acme/gadgets');

    await visit('/runs');
    await visit('/');

    assert.deepEqual(rows(), ['acme/gadgets#2', 'acme/gadgets#3']);
  });

  test('a repo in the address the hub does not watch is passed over', async function (assert) {
    twoRepos();

    await visit('/?repos=acme/sprockets');

    assert.strictEqual(rows().length, 3);
    assert.dom('[data-test-repo-filter]').hasText('All repos');
  });

  test('a selection that leaves the wall empty says how many the other repos hold', async function (assert) {
    board().serves = 'hub';
    board().watching = ['acme/gadgets', 'acme/widgets'];
    board().held = [
      heldPr({ repo: 'acme/gadgets', number: 2 }),
      heldPr({ repo: 'acme/gadgets', number: 3 }),
    ];

    await visit('/?repos=acme/widgets');

    assert
      .dom('[data-test-wall-filtered]')
      .includesText('2 pull requests in other repos are filtered out');
    assert.dom('[data-test-wall-empty]').doesNotExist();

    await click('[data-test-wall-filtered] [data-test-repo-all]');

    assert.strictEqual(rows().length, 2);
  });

  test('with one repo watched the filter names it and holds that one name', async function (assert) {
    board().serves = 'hub';
    board().watching = ['acme/widgets'];
    board().held = [heldPr({ repo: 'acme/widgets', number: 1 })];
    await visit('/');

    assert.dom('[data-test-repo-filter]').hasText('acme/widgets');

    await click('[data-test-repo-filter]');

    assert.deepEqual(choices(), ['acme/widgets']);
  });

  test('choosing repos asks the server for nothing new and sends it nothing', async function (assert) {
    twoRepos();
    await visit('/');
    const before = board().asked.length;

    await click('[data-test-repo-filter]');
    await click('[data-test-repo-choice="acme/widgets"] [data-test-repo-only]');
    await click('[data-test-repo-filter]');
    await click('[data-test-repo-choice="acme/gadgets"] input');

    assert.deepEqual(board().asked.slice(before), []);
    assert.deepEqual(board().posted, []);

    await clock().tick(5000);

    assert.deepEqual(
      board().asked.filter((one) => one.url.includes('repos')),
      [],
    );
  });
});
