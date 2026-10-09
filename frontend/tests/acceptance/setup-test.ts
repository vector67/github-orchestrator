import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { click, currentURL, fillIn, findAll, visit } from '@ember/test-helpers';
import { heldPr, setupFakeBoard } from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import {
  choice,
  setupRead,
  type FakeSetup,
} from 'frontend/tests/helpers/fake-setup';

const RESTART = 500;

module('Acceptance | setup', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  function inSetup(): FakeSetup {
    board().serves = 'hub';
    board().state = 'setup';
    const setup = board().setup;
    setup.choices = [
      choice('acme/widgets', { has_my_prs: true }),
      choice('acme/gadgets'),
      choice('octocat/spoon-knife', { can_push: false }),
    ];
    return setup;
  }

  function watchingTwo(): FakeSetup {
    const setup = inSetup();
    board().state = 'watching';
    setup.read = setupRead({
      state: 'watching',
      problem: null,
      gh_account: 'octocat',
      repos: [
        {
          repo: 'acme/widgets',
          local_path: '~/repositories/widgets',
          new_worktree_command: 'cp .env .',
        },
        {
          repo: 'acme/gadgets',
          local_path: '~/repositories/gadgets',
          new_worktree_command: '',
        },
      ],
    });
    setup.cloned = {
      'acme/widgets': '~/repositories/widgets',
      'acme/gadgets': '~/repositories/gadgets',
    };
    return setup;
  }

  function listed(): string[] {
    return findAll('[data-test-setup-repo]').map(
      (row) => row.getAttribute('data-test-setup-repo') ?? '',
    );
  }

  function row(repo: string): string {
    return `[data-test-setup-repo="${repo}"]`;
  }

  async function pick(repo: string): Promise<void> {
    await click(`${row(repo)} input[type="checkbox"]`);
  }

  async function back(pid = 5001): Promise<void> {
    board().pid = pid;
    await clock().tick(RESTART);
    await clock().tick(RESTART);
  }

  test("a hub in setup opens on the setup page with gh's account filled in and its pushable repos listed at once", async function (assert) {
    inSetup();

    await visit('/');

    assert.strictEqual(currentURL(), '/setup');
    assert.dom('[data-test-setup-login]').hasValue('octocat');
    assert.deepEqual(listed(), ['acme/widgets', 'acme/gadgets']);
    assert.dom(`${row('acme/widgets')} [data-test-has-my-prs]`).exists();
    assert.dom(`${row('acme/gadgets')} [data-test-has-my-prs]`).doesNotExist();
  });

  test('show read-only adds the repos the account can only read', async function (assert) {
    inSetup();
    await visit('/setup');

    await click('[data-test-setup-read-only]');

    assert.deepEqual(listed(), [
      'acme/widgets',
      'acme/gadgets',
      'octocat/spoon-knife',
    ]);
    assert.dom(`${row('octocat/spoon-knife')} [data-test-read-only]`).exists();
  });

  test('the filter box narrows the list to the repos whose name holds it', async function (assert) {
    inSetup();
    await visit('/setup');

    await fillIn('[data-test-setup-filter]', 'gadg');

    assert.deepEqual(listed(), ['acme/gadgets']);
  });

  test('each picked repo gets a clone line saying whether its clone is found or will be cloned', async function (assert) {
    const setup = inSetup();
    setup.cloned = { 'acme/gadgets': '~/src/gadgets' };
    await visit('/setup');

    await pick('acme/widgets');
    await pick('acme/gadgets');

    assert
      .dom('[data-test-clone="acme/widgets"] [data-test-clone-said]')
      .hasText('Will clone into ~/repositories/widgets');
    assert
      .dom('[data-test-clone="acme/gadgets"] [data-test-clone-said]')
      .hasText('Found a clone at ~/src/gadgets');
    assert
      .dom('[data-test-clone="acme/widgets"] [data-test-clone-path]')
      .hasValue('~/repositories/widgets');
  });

  test('a repo typed by name joins the picks when the account can see it', async function (assert) {
    const setup = inSetup();
    setup.visible['octocat/hello-world'] = choice('octocat/hello-world', {
      can_push: false,
    });
    await visit('/setup');

    await fillIn('[data-test-setup-by-name-input]', 'octocat/hello-world');
    await click('[data-test-setup-add]');

    assert
      .dom(row('octocat/hello-world'))
      .hasAttribute('data-test-picked', 'true');
    assert.dom('[data-test-clone="octocat/hello-world"]').exists();
  });

  test('a repo typed by name that the account cannot see says so and is not picked', async function (assert) {
    inSetup();
    await visit('/setup');

    await fillIn('[data-test-setup-by-name-input]', 'acme/typo');
    await click('[data-test-setup-add]');

    assert
      .dom('[data-test-setup-by-name-trouble]')
      .hasText('octocat cannot see acme/typo');
    assert.dom('[data-test-clone="acme/typo"]').doesNotExist();
  });

  test('the model option is the instance agent’s, under its name', async function (assert) {
    const setup = inSetup();
    setup.read = setupRead({
      agent_name: 'Codex',
      options: {
        agent_model: 'gpt-6-luna',
        agents_enabled: true,
        max_thread_runs: 4,
      },
    });
    await visit('/setup');

    assert.dom('[data-test-setup-model-label]').hasText('Codex model');
    assert.dom('[data-test-setup-model]').hasValue('gpt-6-luna');
  });

  test('an account gh holds no token for says to log in, then checks again', async function (assert) {
    const setup = inSetup();
    setup.read = setupRead({ active_account: 'someone' });
    await visit('/setup');

    assert.dom('[data-test-setup-login-trouble]').includesText('gh auth login');
    assert.dom('[data-test-setup-repos]').doesNotExist();

    setup.tokens['someone'] = ['repo'];
    await click('[data-test-setup-check-again]');

    assert.dom('[data-test-setup-login-trouble]').doesNotExist();
    assert.deepEqual(listed(), ['acme/widgets', 'acme/gadgets']);
  });

  test('start watching writes the picks with the etag read, shows each clone, and opens the wall once the watcher is back', async function (assert) {
    const setup = inSetup();
    await visit('/setup');
    await pick('acme/widgets');
    await fillIn('[data-test-setup-command="acme/widgets"]', 'cp .env .');
    await click('[data-test-setup-enabled]');

    await click('[data-test-setup-start]');

    assert.deepEqual(setup.writes, [
      {
        ifMatch: '"setup-1"',
        body: {
          gh_account: 'octocat',
          repos: [
            {
              repo: 'acme/widgets',
              local_path: '~/repositories/widgets',
              new_worktree_command: 'cp .env .',
            },
          ],
          options: {
            agent_model: 'opus',
            agents_enabled: false,
            max_thread_runs: 4,
          },
        },
      },
    ]);
    assert
      .dom('[data-test-clone-progress="acme/widgets"]')
      .hasAttribute('data-test-clone-state', 'waiting');

    setup.progress = {
      ...setup.progress!,
      state: 'restarting',
      clones: [{ ...setup.progress!.clones[0]!, state: 'cloned' }],
    };
    await clock().tick(RESTART);

    assert.dom('[data-test-setup-restarting]').exists();
    assert
      .dom('[data-test-clone-progress="acme/widgets"]')
      .hasAttribute('data-test-clone-state', 'cloned');

    board().state = 'watching';
    board().held = [heldPr({ repo: 'acme/widgets', number: 7 })];
    board().watching = ['acme/widgets'];
    await back();

    assert.strictEqual(currentURL(), '/');
    assert.dom('[data-test-wall-row="acme/widgets#7"]').exists();
  });

  test('a write refused field by field shows each reason beside its field and writes nothing more', async function (assert) {
    const setup = inSetup();
    setup.refusals = [
      {
        status: 422,
        code: 'setup-refused',
        detail: 'octocat cannot see acme/widgets',
        field: 'repos[0].repo',
      },
      {
        status: 422,
        code: 'setup-refused',
        detail: '~/repositories/widgets holds something that is not a clone',
        field: 'repos[0].local_path',
      },
      {
        status: 422,
        code: 'setup-refused',
        detail: 'hub_port must be outside the boards’ 8730-8829',
        field: 'config',
      },
    ];
    await visit('/setup');
    await pick('acme/widgets');

    await click('[data-test-setup-start]');

    assert
      .dom('[data-test-clone="acme/widgets"] [data-test-refused="repo"]')
      .hasText('octocat cannot see acme/widgets');
    assert
      .dom('[data-test-clone="acme/widgets"] [data-test-refused="local_path"]')
      .includesText('not a clone');
    assert.dom('[data-test-setup-trouble]').includesText('8730-8829');
    assert.dom('[data-test-setup-progress]').doesNotExist();
  });

  test('a write against a config changed since the page read it asks to save again', async function (assert) {
    const setup = inSetup();
    await visit('/setup');
    setup.read = { ...setup.read, etag: '"setup-2"' };
    await pick('acme/widgets');

    await click('[data-test-setup-start]');

    assert.dom('[data-test-setup-trouble]').includesText('changed');
    await click('[data-test-setup-start]');
    assert.strictEqual(setup.writes[1]?.ifMatch, '"setup-2"');
  });

  test('a clone that fails says why and goes back to the choices kept', async function (assert) {
    const setup = inSetup();
    await visit('/setup');
    await pick('acme/widgets');
    await click('[data-test-setup-start]');

    setup.progress = {
      ...setup.progress!,
      state: 'failed',
      error: 'could not clone acme/widgets: permission denied',
      clones: [
        { ...setup.progress!.clones[0]!, state: 'failed', error: 'denied' },
      ],
    };
    await clock().tick(RESTART);

    assert.dom('[data-test-setup-failed]').includesText('permission denied');
    await click('[data-test-setup-back]');
    assert.dom(row('acme/widgets')).hasAttribute('data-test-picked', 'true');
  });

  test('a broken config shows its error and its path, and is moved aside into setup', async function (assert) {
    const setup = inSetup();
    board().state = 'broken';
    setup.read = setupRead({
      state: 'broken',
      problem: 'config.toml: Invalid value (at line 1, column 14)',
    });
    await visit('/');

    assert.strictEqual(currentURL(), '/setup');
    assert.dom('[data-test-setup-problem]').hasText(setup.read.problem!);
    assert.dom('[data-test-setup-broken]').includesText(setup.read.config_path);

    await click('[data-test-setup-move-aside]');
    assert.strictEqual(setup.movedAside, 1);
    assert.dom('[data-test-setup-moved]').includesText('broken-20261009');

    board().state = 'setup';
    setup.read = setupRead();
    await back();

    assert.dom('[data-test-setup-broken]').doesNotExist();
    assert.dom('[data-test-setup-login]').hasValue('octocat');
  });

  test('on a watching hub the top bar opens setup with the watched repos picked, and reading it writes nothing', async function (assert) {
    const setup = watchingTwo();
    await visit('/');

    await click('[data-test-nav="setup"]');

    assert.strictEqual(currentURL(), '/setup');
    assert.dom(row('acme/widgets')).hasAttribute('data-test-picked', 'true');
    assert.dom(row('acme/gadgets')).hasAttribute('data-test-picked', 'true');
    assert
      .dom('[data-test-setup-command="acme/widgets"]')
      .hasValue('cp .env .');
    assert.dom('[data-test-setup-start]').hasText('Save and restart');
    assert.deepEqual(
      setup.asked.filter((one) => !one.startsWith('GET ')),
      [],
    );
    assert.deepEqual(board().posted, []);
  });

  test('unpicking a watched repo says it stops being watched, and the write leaves it out', async function (assert) {
    const setup = watchingTwo();
    await visit('/setup');

    await pick('acme/gadgets');

    assert
      .dom('[data-test-setup-dropped="acme/gadgets"]')
      .includesText('worktrees and its clone stay');
    await click('[data-test-setup-start]');
    assert.deepEqual(
      setup.writes[0]?.body.repos.map((one) => one.repo),
      ['acme/widgets'],
    );
    assert.dom('[data-test-setup-progress]').exists();
  });
});
