import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  visit,
  currentURL,
  click,
  triggerEvent,
  waitFor,
} from '@ember/test-helpers';
import {
  added,
  removed,
  comment,
  diffOf,
  operation,
  proposal,
  setupFakeBoard,
  summary,
  thread,
  type FakeBoard,
  type Phase,
} from 'frontend/tests/helpers/fake-board';
import { setupFakeClock } from 'frontend/tests/helpers/fake-clock';
import type { Operation } from 'frontend/data/api';
import { stubGitHub } from 'frontend/tests/helpers/browser';

const KEY = 'PRRT_aa';

function seed(board: FakeBoard) {
  board.people = [
    { login: 'anna', name: 'Anna Example' },
    { login: 'ben', name: null },
  ];
  board.conversations = [
    board.threadIn('proposed', { key: 'PRRT_zz' }),
    board.threadIn('proposed', { key: KEY }),
  ];
  board.comments[KEY] = [
    comment({ body: 'please rename' }),
    comment({
      id: 2,
      author: 'ben',
      review_state: null,
      body: 'still unclear',
    }),
  ];
  board.operations[KEY] = [
    operation({
      id: `${KEY}.1`,
      conversation: KEY,
      plan: [{ text: 'rename it', file: 'src/foo.py', done: true }],
    }),
  ];
  board.proposals[KEY] = [
    proposal({
      id: `${KEY}.1.proposal`,
      summary: 'renamed it',
      confidence: 'high',
      confidence_note: 'the tests cover it',
      tests: 'pass',
      tests_note: '41 of them',
      agent_note: 'git said no',
    }),
  ];
  board.diffs[`${KEY}.1.proposal`] = diffOf(
    'src/foo.py',
    removed(42, '    return helper()'),
    added(42, '    return renamed()'),
    added(43, '    check()'),
    added(44, '    done()'),
  );
  board.files = {
    sha: 'c0ffee1',
    path: 'src/foo.py',
    from_line: 39,
    to_line: 45,
    truncated: false,
    lines: [{ number: 42, text: '    return helper()' }],
  };
}

function readingOrder(scope: string, texts: string[]): string[] {
  const text = document.querySelector(scope)?.textContent ?? '';
  return texts
    .filter((one) => text.includes(one))
    .sort((one, other) => text.indexOf(one) - text.indexOf(other));
}

function entries(): [string, string, boolean][] {
  return [...document.querySelectorAll('[data-test-entry]')].map((entry) => [
    entry.querySelector('[data-test-entry-who]')?.textContent?.trim() ?? '',
    entry.querySelector('[data-test-entry-meta]')?.textContent?.trim() ?? '',
    entry.hasAttribute('data-marked'),
  ]);
}

function lastFileRead(board: FakeBoard): string | undefined {
  return board.askedFor(/\/api\/files/).at(-1)?.url;
}

module('Acceptance | panel', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const github = stubGitHub(hooks);

  hooks.beforeEach(function () {
    seed(board());
  });

  test('a conversation is a url you can land on', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.strictEqual(currentURL(), `/pr/o/r/7/conversations/${KEY}`);
    assert.dom('[data-test-panel-author]').hasText('Anna Example');
  });

  test('the header says where the row sits and where it points', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-kicker]')
      .hasText('2 of 2 ready · src/foo.py line 42');
    assert
      .dom('[data-test-kicker] a')
      .hasAttribute('href', 'https://github.com/o/r/pull/7#discussion_r1');
  });

  test('the way out leaves the board rather than replacing it', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-kicker] a')
      .hasAttribute('target', '_blank')
      .hasAttribute('rel', 'noopener noreferrer');
    assert
      .dom('[data-test-kicker] a [data-test-anchor-out-icon]')
      .exists()
      .hasAttribute('aria-hidden', 'true');
  });

  test('the header leads with the reviewer and how they reviewed', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('#panel-talk [data-test-panel-author]').hasText('Anna Example');
    assert.dom('[data-test-role-line]').hasText('requested changes');
  });

  test('a reopened card leads with coming back', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: KEY, reopened: true }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-kicker]').includesText('Re-opened · top of queue');
    assert.dom('[data-test-role-line]').hasText('replied again');
  });

  test('the kicker’s state word says what it means', async function (assert) {
    board().conversations = [board().threadIn('landing', { key: KEY })];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-kicker]').includesText('Landing');
    assert
      .dom('[data-test-kicker] .kicker-place')
      .hasAttribute('title', /on its way to the PR branch/);
  });

  test('prev and next ready are buttons, not text shaped like one', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-prev]').hasTagName('button').hasText('← Prev');
    assert.dom('[data-test-next]').hasTagName('button').hasText('Next ready →');
  });

  test('clicking a row opens it and puts it in the url', async function (assert) {
    await visit('/pr/o/r/7/conversations');

    await click(`#c-${KEY}`);

    assert.strictEqual(currentURL(), `/pr/o/r/7/conversations/${KEY}`);
    assert.dom(`#c-${KEY}`).hasAttribute('aria-selected', 'true');
  });

  test('the panel reads the thread, its operations and its proposals', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    for (const read of ['comments', 'operations', 'proposals']) {
      assert.strictEqual(
        board().askedFor(new RegExp(`/api/conversations/${KEY}/${read}$`))
          .length,
        1,
        read,
      );
    }
  });

  test('a card drawn before its details arrive still stands', async function (assert) {
    const release = board().hold(new RegExp(`${KEY}/comments$`));

    const visiting = visit(`/pr/o/r/7/conversations/${KEY}`);
    await waitFor('[data-test-loading="thread"]');

    assert.dom('[data-test-kicker]').includesText('2 of 2 ready');
    assert.dom('[data-test-frame]').doesNotExist();

    release();
    await visiting;

    assert.dom('[data-test-frame]').exists();
  });

  test('the fix label copies the directory the fix was made in', async function (assert) {
    board().proposals[KEY] = [
      proposal({
        id: `${KEY}.1.proposal`,
        directory: '/data/thread-worktrees/o/r/7/prrt-aa',
      }),
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-fix-label] [data-test-copy-directory]')
      .hasText('copy directory');
    await click('[data-test-copy-directory]');

    assert.deepEqual(github().copied, ['/data/thread-worktrees/o/r/7/prrt-aa']);
  });

  test('a proposal with no directory offers nothing to copy', async function (assert) {
    board().proposals[KEY] = [
      proposal({ id: `${KEY}.1.proposal`, directory: null }),
    ];
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-fix-label]').exists();
    assert.dom('[data-test-copy-directory]').doesNotExist();
  });

  test('the panel draws the proposal: its summary, plan, confidence and notes', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-fix-label]')
      .hasText('Agent proposal · 1 of 1 changes');
    assert.dom('[data-test-panel-summary]').hasText('renamed it');
    assert.dom('[data-test-plan]').containsText('rename it');
    assert
      .dom('[data-test-plan-step] [data-test-step-file]')
      .hasText('src/foo.py');
    assert.dom('[data-test-plan-step]').hasAttribute('data-done', '1');
    assert
      .dom('[data-test-confidence]')
      .includesText('Confidence: high')
      .includesText('the tests cover it');
    assert.dom('[data-test-notes]').containsText('git said no');
  });

  test('a proposed reply is drawn as the reply, with no diff, files or tests', async function (assert) {
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY, plan: [] }),
    ];
    board().proposals[KEY] = [
      proposal({
        id: `${KEY}.1.proposal`,
        kind: 'reply',
        reply: 'It runs once per poll,\nso the cache is never stale.',
        commits: null,
        summary: null,
        commit_message: null,
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-fix-label]').hasText('Agent proposes a reply');
    assert
      .dom('[data-test-proposed-reply]')
      .hasText('It runs once per poll, so the cache is never stale.');
    assert.dom('[data-test-panel-summary]').doesNotExist();
    assert.dom('[data-test-fix-meta]').doesNotExist();
    assert.dom('[data-test-frame]').doesNotExist();
    assert.dom('[data-test-decision="approve"]').exists();
  });

  test('a proposed ticket is drawn with its project, title, body and reply, and no diff', async function (assert) {
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY, plan: [] }),
    ];
    board().proposals[KEY] = [
      proposal({
        id: `${KEY}.1.proposal`,
        kind: 'ticket',
        reply: 'That belongs outside this PR, so I have proposed a ticket.',
        ticket: {
          project: 'PROJ',
          title: 'Cache tax rates across exports',
          body: 'Each export reads its tax rate again.',
        },
        commits: null,
        summary: null,
        commit_message: null,
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-fix-label]').hasText('Agent proposes a ticket');
    assert.dom('[data-test-ticket-project-shown]').hasText('PROJ');
    assert
      .dom('[data-test-ticket-title-shown]')
      .hasText('Cache tax rates across exports');
    assert
      .dom('[data-test-ticket-body-shown]')
      .hasText('Each export reads its tax rate again.');
    assert
      .dom('[data-test-proposed-reply]')
      .hasText('That belongs outside this PR, so I have proposed a ticket.');
    assert.dom('[data-test-fix-meta]').doesNotExist();
    assert.dom('[data-test-frame]').doesNotExist();
    assert.dom('[data-test-decision="approve"]').exists();
  });

  test('a step naming one long unbroken identifier wraps inside its row', async function (assert) {
    const identifier = 'test_' + 'an_invoice_voided_then_reissued_'.repeat(6);
    board().operations[KEY] = [
      operation({
        id: `${KEY}.1`,
        conversation: KEY,
        plan: [
          {
            text: `Rename the test to ${identifier}`,
            file: 'src/foo.py',
            done: true,
          },
        ],
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const step = document.querySelector('[data-test-plan-step]')!;
    assert.dom(step).containsText(identifier);
    assert.ok(
      step.scrollWidth <= step.clientWidth,
      `the step is ${step.scrollWidth}px of content in a ${step.clientWidth}px row`,
    );
  });

  test('a fold brings its diff frame, drawn from the proposal', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-fold-title]').hasText('Proposed diff · 1 file');
    assert.dom('[data-test-frame]').includesText('return renamed()');
  });

  test('every row of a proposed diff spans the width of its longest line', async function (assert) {
    board().diffs[`${KEY}.1.proposal`] = diffOf(
      'src/foo.py',
      added(42, '    return ' + 'renamed_'.repeat(60) + '()'),
      added(43, '    pass'),
    );

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const diff = document.querySelector('[data-test-frame] .thread-diff')!;
    const short = document.querySelector<HTMLElement>(
      '[data-test-row="added"]:last-child',
    )!;
    assert.ok(diff.scrollWidth > diff.clientWidth, 'the long line overflows');
    assert.strictEqual(short.offsetWidth, diff.scrollWidth);
  });

  test('a proposal that committed nothing has no diff to fold', async function (assert) {
    board().proposals[KEY] = [
      proposal({ id: `${KEY}.1.proposal`, commits: null }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-frame]').doesNotExist();
    assert.dom('[data-test-panel-summary]').hasText('renamed it');
  });

  test('escape leaves the expanded diff before it leaves the panel', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    await click('[data-test-expand]');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-frame]').doesNotHaveAttribute('data-expanded');
    assert.strictEqual(currentURL(), `/pr/o/r/7/conversations/${KEY}`);

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations');
  });

  test('a run with no diff yet says so where the diff would be', async function (assert) {
    board().conversations = [board().threadIn('working', { key: KEY })];
    board().proposals[KEY] = [];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-frame]').doesNotExist();
    assert
      .dom('[data-test-fold-placeholder]')
      .hasText('The diff appears when the agent finishes.');
    assert
      .dom('[data-test-banner-fix]')
      .includesText('Running')
      .includesText('The proposal appears here when the agent finishes.');
  });

  test('the verdict and the file count are the meta line, each with its detail', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-verdict]')
      .includesText('Tests pass')
      .includesText('41 of them');
    assert
      .dom('[data-test-files]')
      .includesText('1 file')
      .includesText('src/foo.py')
      .includesText('+3')
      .includesText('−1');
  });

  test('a landing that failed reads the failure instead of a proposal', async function (assert) {
    board().conversations = [board().threadIn('push failed', { key: KEY })];
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY }),
      operation({
        id: 'op_000000000001',
        conversation: KEY,
        kind: 'approve',
        state: 'refused',
        reason_code: 'push-failed',
        reason: ' ! [rejected]  export-fixes -> export-fixes (fetch first)',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-failure]').containsText('The push failed');
    assert.dom('[data-test-failure]').containsText('fetch first');
    assert
      .dom('[data-test-failure]')
      .containsText('committed on the PR branch on this machine');
    assert.dom('#panel-fix [data-test-plan]').doesNotExist();
    assert.dom('[data-test-frame]').doesNotExist();
    assert.dom('[data-test-decision="approve"]').includesText('Push it');
  });

  module('a landing that failed', function () {
    function refused(phase: Phase, reason: string) {
      const landed = board().threadIn(phase, { key: KEY });
      const approve = landed.operations.at(-1)!;
      board().conversations = [landed];
      board().operations[KEY] = [
        operation({ id: `${KEY}.1`, conversation: KEY }),
        operation({
          id: approve.id,
          conversation: KEY,
          kind: 'approve',
          state: 'refused',
          reason_code: approve.reason_code,
          reason,
        }),
      ];
    }

    test('leads with what went wrong, and folds git output away', async function (assert) {
      refused(
        'push failed',
        'To /var/folders/xy/T/preview/worktree-origin.git\n' +
          ' ! [rejected]  export-fixes -> export-fixes (fetch first)',
      );

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-failure-summary]')
        .hasText(
          'GitHub has newer commits on the PR branch, so it refused the push.',
        );
      assert
        .dom(
          '[data-test-failure] details:not([open]) [data-test-failure-output]',
        )
        .containsText('/var/folders/xy/T/preview/worktree-origin.git');
      assert
        .dom('[data-test-failure-summary]')
        .doesNotContainText('/var/folders');
    });

    test('says a thread GitHub could not find in words', async function (assert) {
      refused(
        'reply failed',
        'gh graphql mutation failed: Could not resolve to a node with the ' +
          "global id of 'PRRT_reply_refused'",
      );

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-failure-summary]')
        .hasText(
          'GitHub could not find this thread to reply on; it may have been deleted.',
        );
      assert
        .dom('[data-test-failure] details [data-test-failure-output]')
        .containsText('PRRT_reply_refused');
    });

    test('says what it can when the output is one it does not know', async function (assert) {
      refused('push failed', 'fatal: the remote end hung up unexpectedly');

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-failure-summary]')
        .hasText('git could not push the fix.');
      assert
        .dom('[data-test-failure] details [data-test-failure-output]')
        .hasText('fatal: the remote end hung up unexpectedly');
    });
  });

  module('a ticket the viewer accepted', function () {
    const FILED = 'https://example.atlassian.net/browse/PROJ-12';

    const filed = {
      ticket_key: 'PROJ-12',
      ticket_url: FILED,
      steps: { filed: true, picked: false, pushed: false, answered: false },
    };

    function accepted(phase: Phase, approve: Partial<Operation>) {
      const reached = board().threadIn(phase, { key: KEY });
      board().conversations = [reached];
      board().proposals[KEY] = [
        proposal({
          id: `${KEY}.1.proposal`,
          kind: 'ticket',
          reply: 'That reaches past this PR, so I have filed a ticket.',
          ticket: {
            project: 'PROJ',
            title: 'Share one model cache',
            body: 'Every export builds its own cache.',
          },
          commits: null,
          summary: null,
          commit_message: null,
        }),
      ];
      board().operations[KEY] = [
        operation({ id: `${KEY}.1`, conversation: KEY }),
        operation({
          id: reached.operations.find((one) => one.kind === 'approve')!.id,
          conversation: KEY,
          kind: 'approve',
          ...approve,
        }),
      ];
    }

    test('says it is posting the reply once the ticket is filed', async function (assert) {
      accepted('landing', { ...filed, state: 'running' });

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-fix-label]')
        .hasText('Accepted · posting the reply');
    });

    test('names the ticket it filed once it has landed', async function (assert) {
      accepted('landed', {
        ...filed,
        steps: { ...filed.steps, answered: true },
      });

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert.dom('[data-test-fix-label]').hasText('Accepted · ticket filed');
      assert.dom('[data-test-banner-fix]').containsText('Filed PROJ-12');
    });

    test('a filing that failed posted nothing and offers to file again', async function (assert) {
      accepted('filing failed', {
        state: 'refused',
        reason_code: 'file-failed',
        reason: 'Jira refused the project key PROJ',
      });

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-fix-label]')
        .hasText('Accepted · the filing failed');
      assert.dom('[data-test-failure]').containsText('The filing failed');
      assert
        .dom('[data-test-failure]')
        .containsText('Nothing was posted to GitHub');
      assert
        .dom('[data-test-failure] [data-test-failure-output]')
        .containsText('Jira refused the project key PROJ');
      assert
        .dom('[data-test-decision="approve"]')
        .includesText('File it again');
    });

    test('a reply that failed after the filing says the ticket is filed', async function (assert) {
      accepted('reply failed', {
        ...filed,
        state: 'refused',
        reason_code: 'reply-failed',
        reason: 'gh api exploded',
      });

      await visit(`/pr/o/r/7/conversations/${KEY}`);

      assert
        .dom('[data-test-fix-label]')
        .hasText('Accepted · ticket filed, the reply failed');
      assert
        .dom('[data-test-failure]')
        .containsText('The ticket is filed as PROJ-12');
    });
  });

  test('an agent that gave up says which attempt it was on and why', async function (assert) {
    board().conversations = [board().threadIn('failed', { key: KEY })];
    board().operations[KEY] = [
      operation({
        id: `${KEY}.1`,
        conversation: KEY,
        state: 'refused',
        reason_code: 'max-attempts',
        reason: 'tests failed twice',
        attempts: 3,
        attempts_allowed: 3,
      }),
    ];
    board().proposals[KEY] = [];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-notes] .verdict')
      .hasText('attempt 3 of 3 failed: tests failed twice');
  });

  test('an assumed done thread on your PR says the agent skipped it, not that it failed', async function (assert) {
    board().conversations = [board().threadIn('assumed-done', { key: KEY })];
    board().operations[KEY] = [
      operation({
        id: `${KEY}.1`,
        conversation: KEY,
        state: 'refused',
        reason_code: 'agent-declined',
        reason: 'thanks the author, asks for nothing',
        classification: 'acknowledgement',
      }),
    ];
    board().proposals[KEY] = [];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-notes] .verdict')
      .hasText('skipped: thanks the author, asks for nothing');
  });

  test('a fix the agent is rebasing says it lands on its own, with the conflict folded away', async function (assert) {
    board().conversations = [board().threadIn('rebasing', { key: KEY })];
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY }),
      operation({
        id: `${KEY}.3`,
        conversation: KEY,
        kind: 'rebase',
        state: 'running',
        onto: 'eb2f8ff0b8f5aaaa',
        conflict: 'error: could not apply 7208d66... rename the helper',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-notes] .landing-failure')
      .hasText(
        'Rebasing onto eb2f8ff0b8f5: it lands on its own if its tests pass',
      );
    assert
      .dom('[data-test-notes] details:not([open]) [data-test-note-detail]')
      .hasText('error: could not apply 7208d66... rename the helper');
  });

  test('a deferred card says what wakes it', async function (assert) {
    board().conversations = [board().threadIn('deferred', { key: KEY })];
    board().operations[KEY] = [
      operation({ id: `${KEY}.1`, conversation: KEY }),
      operation({
        id: 'op_000000000001',
        conversation: KEY,
        kind: 'defer',
        until: 'pr:87',
        note: 'after the split',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      readingOrder('[data-test-notes]', [
        'after the split',
        'waiting until PR #87 closes',
      ]),
      ['waiting until PR #87 closes', 'after the split'],
    );
  });

  test('a comment body is drawn as markdown, and its html as the words it is', async function (assert) {
    board().comments[KEY] = [
      comment({ body: '<img src=x onerror=alert(1)> **bold**' }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert
      .dom('[data-test-entry-body]')
      .hasText('<img src=x onerror=alert(1)> bold');
    assert.dom('[data-test-entry-body] strong').hasText('bold');
    assert.dom('[data-test-entry-body] img').doesNotExist();
  });

  test('the comment a reopened thread came back with is marked', async function (assert) {
    board().conversations = [thread({ key: KEY, reopened: true })];
    board().comments[KEY] = [
      comment(),
      comment({ id: 2, author: 'octocat', review_state: null, body: 'done' }),
      comment({ id: 3, review_state: null, body: 'still unclear' }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    const marked = document.querySelectorAll('[data-test-entry][data-marked]');
    assert.strictEqual(marked.length, 1, 'only the newest one');
    assert.dom(marked[0]).containsText('still unclear');
  });

  test('a reply on a ready card parks it on the other party', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k0' }),
      board().threadIn('working', { key: 'k1' }),
      board().threadIn('landed', { key: 'k2' }),
    ];

    await visit('/pr/o/r/7/conversations/k0');
    await click('[data-test-reply-open]');
    assert
      .dom('[data-test-composer-note]')
      .hasText(
        'No code change; comment moves to "Waiting on reviewer" and the proposal is parked.',
      );
    await click('[data-test-reply-close]');

    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-reply-open]');
    assert
      .dom('[data-test-composer-note]')
      .hasText('Posted to the GitHub thread.');
    await click('[data-test-reply-close]');

    await visit('/pr/o/r/7/conversations/k2');
    assert.dom('[data-test-reply-open]').doesNotExist('a done card takes none');
  });

  test('an outdated thread is read where it was written', async function (assert) {
    board().conversations = [
      thread({
        key: KEY,
        anchor: {
          ...thread().anchor,
          line: null,
          is_outdated: true,
          original_line: 7,
        },
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.strictEqual(
      lastFileRead(board()),
      '/api/files?sha=a1b2c3d&path=src%2Ffoo.py&from_line=4&to_line=10',
    );
  });

  test('the thread and the composer come before the code the comment is about', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-transcript]').includesText('please rename');
    assert.dom('[data-test-reply-open]').hasText('Reply to ben');
    assert.dom('[data-test-context]').containsText('return helper()');
    assert.deepEqual(
      readingOrder('#panel', [
        'return helper()',
        'Reply to ben',
        'please rename',
      ]),
      ['please rename', 'Reply to ben', 'return helper()'],
    );
  });

  test('a comment on no line has no code beside it', async function (assert) {
    board().conversations = [
      thread({
        key: KEY,
        kind: 'issue',
        anchor: {
          ...thread().anchor,
          path: null,
          line: null,
          original_line: null,
        },
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.dom('[data-test-transcript]').includesText('please rename');
    assert.dom('[data-test-context]').doesNotExist();
    assert.strictEqual(lastFileRead(board()), undefined);
  });

  test('the panel reads as the thread, then the fix, then the decision', async function (assert) {
    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      readingOrder('#panel', ['Accept', 'renamed it', 'please rename']),
      ['please rename', 'renamed it', 'Accept'],
    );
  });

  test('the fix section reads top to bottom in the order you decide in', async function (assert) {
    board().conversations = [board().threadIn('working', { key: KEY })];
    board().operations[KEY] = [
      operation({
        id: `${KEY}.1`,
        conversation: KEY,
        state: 'running',
        plan: [{ text: 'rename it', file: 'src/foo.py', done: true }],
      }),
    ];
    const order = [
      'Agent working · 1 of 1 changes',
      'Running · 1 of 1 changes done',
      'renamed it',
      'rename it',
      'Confidence: high',
      'Tests pass',
      'git said no',
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(readingOrder('#panel', [...order].reverse()), order);
  });

  test('a thread the board does not have says so', async function (assert) {
    await visit('/pr/o/r/7/conversations/PRRT_nothing');

    assert.dom('[data-test-missing]').containsText('PRRT_nothing');
  });

  test('another thread opens scrolled to its top', async function (assert) {
    const many = Array.from({ length: 24 }, (_, i) =>
      comment({ id: i + 1, body: `comment number ${i}` }),
    );
    board().comments[KEY] = many;
    board().comments['PRRT_zz'] = many;
    board().diffs[`${KEY}.1.proposal`] = diffOf(
      'src/foo.py',
      ...Array.from({ length: 60 }, (_, i) => added(i + 1, `line ${i}`)),
    );

    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const panel = document.querySelector('#panel') as HTMLElement;
    const thread = document.querySelector('#panel-thread') as HTMLElement;
    panel.scrollTop = 80;
    thread.scrollTop = 80;
    assert.strictEqual(panel.scrollTop, 80);
    assert.strictEqual(thread.scrollTop, 80);

    await visit('/pr/o/r/7/conversations/PRRT_zz');

    assert.strictEqual(
      (document.querySelector('#panel') as HTMLElement).scrollTop,
      0,
    );
    assert.strictEqual(
      (document.querySelector('#panel-thread') as HTMLElement).scrollTop,
      0,
    );
  });
});

module('Acceptance | panel | the thread in time', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);
  const clock = setupFakeClock(hooks);

  hooks.beforeEach(function () {
    seed(board());
    clock().now = Date.parse('2026-09-12T12:00:00Z');
  });

  test('the thread is drawn with who said it and when', async function (assert) {
    board().conversations = [thread({ key: KEY, reopened: true })];
    board().comments[KEY] = [
      comment(),
      comment({
        id: 2,
        author: 'ben',
        review_state: null,
        created_at: '2026-09-12T11:56:00Z',
      }),
      comment({
        id: 3,
        author: 'anna',
        review_state: null,
        created_at: '2026-09-12T11:59:30Z',
      }),
    ];

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(entries(), [
      ['Anna Example', 'requested changes · 2h ago', false],
      ['ben', '4m ago', false],
      ['Anna Example', 'just now', true],
    ]);
  });

  test('it says how long ago in the largest unit that fits', async function (assert) {
    board().comments[KEY] = [
      '2026-09-12T11:59:40Z',
      '2026-09-12T11:30:00Z',
      '2026-09-12T09:00:00Z',
      '2026-09-10T12:00:00Z',
      null,
    ].map((created_at, at) =>
      comment({ id: at + 1, review_state: null, created_at }),
    );

    await visit(`/pr/o/r/7/conversations/${KEY}`);

    assert.deepEqual(
      entries().map(([, meta]) => meta),
      ['just now', '30m ago', '3h ago', '2d ago', ''],
    );
  });

  test('a poll leaves the thread where it was scrolled', async function (assert) {
    board().comments[KEY] = Array.from({ length: 24 }, (_, i) =>
      comment({ id: i + 1, body: `comment number ${i}` }),
    );
    board().diffs[`${KEY}.1.proposal`] = diffOf(
      'src/foo.py',
      ...Array.from({ length: 60 }, (_, i) => added(i + 1, `line ${i}`)),
    );
    await visit(`/pr/o/r/7/conversations/${KEY}`);
    const panel = document.querySelector('#panel') as HTMLElement;
    const pane = document.querySelector('#panel-thread') as HTMLElement;
    panel.scrollTop = 80;
    pane.scrollTop = 80;

    board().conversations = [
      board().threadIn('proposed', { key: 'PRRT_zz', etag: '"moved"' }),
      board().threadIn('proposed', { key: KEY }),
    ];
    await clock().tick(5000);

    assert.strictEqual(
      (document.querySelector('#panel') as HTMLElement).scrollTop,
      80,
    );
    assert.strictEqual(
      (document.querySelector('#panel-thread') as HTMLElement).scrollTop,
      80,
    );
  });
});

module('Acceptance | panel | a draft', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  const DRAFT = 'draft_00000000000000aa';

  hooks.beforeEach(function () {
    board().actAs('reviewer');
    board().comments[DRAFT] = [
      comment({
        id: null,
        author: 'octocat',
        review_state: null,
        body: 'this leaks',
        html_url: null,
      }),
    ];
  });

  test('a draft GitHub would not take says so in its words', async function (assert) {
    const drafted = board().threadIn('draft', { key: DRAFT });
    board().conversations = [
      {
        ...drafted,
        operations: [
          ...drafted.operations,
          summary({
            id: 'op_000000000002',
            kind: 'post-now',
            state: 'refused',
            reason_code: 'github-rejected',
            reason: 'line must be part of the diff',
          }),
        ],
      },
    ];

    await visit(`/pr/o/r/7/conversations/${DRAFT}`);

    assert
      .dom('[data-test-notes]')
      .hasText('GitHub refused the post: line must be part of the diff');
  });

  test('a draft whose details have not arrived is not composed yet', async function (assert) {
    board().conversations = [board().threadIn('draft', { key: DRAFT })];
    const release = board().hold(/\/comments$/);

    const visiting = visit(`/pr/o/r/7/conversations/${DRAFT}`);
    await waitFor('[data-test-loading="thread"]');

    assert.dom('[data-test-draft-body]').doesNotExist();

    release();
    await visiting;

    assert.dom('[data-test-draft-body]').hasValue('this leaks');
  });
});
