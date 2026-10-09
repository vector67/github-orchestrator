import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import {
  visit,
  click,
  currentURL,
  fillIn,
  triggerEvent,
} from '@ember/test-helpers';
import {
  dashboard,
  operation,
  proposal,
  setupFakeBoard,
  type Phase,
} from 'frontend/tests/helpers/fake-board';

function file(path: string, added: number, removed: number) {
  return {
    path,
    old_path: null,
    status: 'modified' as const,
    added,
    removed,
    is_binary: false,
    line_count: null,
    hunks: [],
  };
}

module('Acceptance | dialog', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().pullRequest.base_branch = 'main';
    board().manager = dashboard({
      pr: { branch: 'PROJ-45-split-invoice-writer' },
    });
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().operations['k1'] = [
      operation({
        id: 'k1.1',
        conversation: 'k1',
        plan: [
          { text: 'a', file: null, done: true },
          { text: 'b', file: null, done: true },
          { text: 'c', file: null, done: true },
        ],
      }),
    ];
    board().proposals['k1'] = [proposal()];
    board().diffs['PRRT_a.1.proposal'] = {
      base: 'aaaaaaa',
      head: 'bbbbbbb',
      files: [
        file('billing/invoice_writer.py', 3, 2),
        file('billing/reader.py', 1, 0),
      ],
    };
  });

  test('approve asks before it pushes', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog]').exists('nothing is posted yet');
    assert.strictEqual(board().posted.length, 0);
  });

  test('confirming an approve posts the reply typed into it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await fillIn('[data-test-dialog-body]', 'thanks, pushed');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted.length, 1);
    assert.strictEqual(board().posted[0]!.verb, 'approve');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'thanks, pushed',
      delete_comment: false,
      resolve: false,
    });
  });

  test('the accept dialog offers to resolve the thread, unticked', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert
      .dom('[data-test-resolve]')
      .isNotChecked('resolving is something you ask for');
  });

  test('the accept dialog opens ticked on a thread a bot opened', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', author_kind: 'bot' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: true,
    });
  });

  test('a ticked accept asks for the thread to be resolved', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-resolve]');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: true,
    });
  });

  test('a comment with no thread offers nothing to resolve', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1', kind: 'issue' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-resolve]').doesNotExist();
  });

  test('reject offers nothing to resolve', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="reject"]');

    assert.dom('[data-test-resolve]').doesNotExist();
  });

  test('cancelling posts nothing at all', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });

  test('the accept dialog shows the message the commit lands with', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-commit-message]').hasText('Rename the helper');
    assert.dom('[data-test-message-body]').doesNotExist();
  });

  test('editing the message lands the commit with the words you gave it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-edit-message]');

    assert.dom('[data-test-message-body]').hasValue('Rename the helper');
    await fillIn('[data-test-message-body]', 'Rename the helper\n\nAs asked.');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
      message: 'Rename the helper\n\nAs asked.',
    });
  });

  test('a message opened and left as it was lands the agent’s', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-edit-message]');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
    });
  });

  test('a message emptied out lands the agent’s rather than none', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-edit-message]');
    await fillIn('[data-test-message-body]', '  ');
    await click('[data-test-dialog-submit]');

    assert.deepEqual(board().posted[0]!.body, {
      delete_comment: false,
      resolve: false,
    });
  });

  test('a commit git could not read the message of shows no message', async function (assert) {
    board().proposals['k1'] = [proposal({ commit_message: null })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-commit-message]').doesNotExist();
    assert.dom('[data-test-edit-message]').doesNotExist();
  });

  test('the accept dialog names every file the commit touches', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-commit-file]').exists({ count: 2 });
    assert
      .dom('[data-test-commit-file]')
      .hasText('billing/invoice_writer.py +3 −2');
  });

  test('the accept dialog addresses its reply box to the reviewer', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-reply-kicker]').hasText('Reply to Anna on GitHub');
  });

  test('the accept button says whether it will post the reply too', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-submit]').hasText('Push commit');

    await fillIn('[data-test-dialog-body]', 'thanks, pushed');

    assert.dom('[data-test-dialog-submit]').hasText('Push and post reply');
  });

  test('closing the accept dialog with the cross posts nothing', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await click('[data-test-dialog-close]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });

  test('reject keeps its own question, shows no commit and posts reject', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="reject"]');

    assert.dom('[data-test-dialog-question]').includesText('drops the fix');
    assert.dom('[data-test-commit-file]').doesNotExist();
    assert.dom('[data-test-dialog-body]').hasValue('');

    await fillIn('[data-test-dialog-body]', 'not this way');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'reject');
    assert.deepEqual(board().posted[0]!.body, {
      reply: 'not this way',
      delete_comment: false,
    });
  });

  test('a session is opened with the steer typed for it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="start-session"]');
    await fillIn('[data-test-dialog-body]', 'go slow');
    await click('[data-test-dialog-submit]');

    assert.strictEqual(board().posted[0]!.verb, 'start-session');
    assert.deepEqual(board().posted[0]!.body, { steer: 'go slow' });
  });
  test('escape in the box asks before it drops what you typed', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'thanks, pushed');

    await triggerEvent('[data-test-dialog-body]', 'keydown', { key: 'Escape' });

    assert
      .dom('[data-test-close-ask]')
      .hasText('Are you sure you want to close?');
    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('escape outside the box asks the same, and keeps the panel open', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'thanks, pushed');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-close-ask]').exists();
    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('cancel asks before it drops what you typed', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'not this way');

    await click('[data-test-dialog-cancel]');

    assert.dom('[data-test-close-ask]').exists();
    assert.dom('[data-test-dialog]').exists();
  });

  test('confirming the ask closes the dialog and posts nothing', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'thanks, pushed');
    await click('[data-test-dialog-close]');

    await click('[data-test-close-confirm]');

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
  });

  test('keeping on goes back to the dialog as you left it, with the cursor in the box', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'thanks, pushed');
    await triggerEvent(document, 'keydown', { key: 'Escape' });

    await click('[data-test-close-keep]');

    assert.dom('[data-test-close-ask]').doesNotExist();
    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
    assert.dom('[data-test-dialog-body]').isFocused();
  });

  test('escape on the ask goes back to the dialog rather than closing it, with the cursor in the box', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'thanks, pushed');
    await triggerEvent(document, 'keydown', { key: 'Escape' });

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-close-ask]').doesNotExist();
    assert.dom('[data-test-dialog-body]').hasValue('thanks, pushed');
    assert.dom('[data-test-dialog-body]').isFocused();
  });

  test('an untouched dialog closes on escape without asking, and gives the focus back to the button that opened it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(
      currentURL(),
      '/pr/o/r/7/conversations/k1',
      'escape closes the dialog, not the panel under it',
    );
    assert.dom('[data-test-decision="approve"]').isFocused();
  });

  test('the ask puts the cursor on Close, so Enter closes', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'not this way');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-close-confirm]').isFocused();
  });

  test('a dialog is a modal named by its question', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="reject"]');

    assert
      .dom('[data-test-dialog] [role="dialog"]')
      .hasAttribute('aria-modal', 'true');
    const named = document
      .querySelector('[data-test-dialog] [role="dialog"]')!
      .getAttribute('aria-labelledby')!;
    assert.dom(`#${named}`).includesText('drops the fix');
  });

  test('a dialog opens with the cursor in its first field', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').isFocused();
  });

  test('tab from the last control comes round to the first, and back', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    const dialog = document.querySelector<HTMLElement>(
      '[data-test-dialog] [role="dialog"]',
    )!;
    const controls = [
      ...dialog.querySelectorAll<HTMLElement>('button, textarea, input'),
    ];
    const first = controls[0]!;
    const last = controls[controls.length - 1]!;

    last.focus();
    await triggerEvent(last, 'keydown', { key: 'Tab' });
    assert.strictEqual(document.activeElement, first, 'forward wraps');

    await triggerEvent(first, 'keydown', { key: 'Tab', shiftKey: true });
    assert.strictEqual(document.activeElement, last, 'backward wraps');
  });

  test('a decision key under an open dialog leaves it as it is', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="approve"]');
    await fillIn('[data-test-dialog-body]', 'Thanks, pushed.');
    await click('[data-test-dialog-question]');

    await triggerEvent(document, 'keydown', { key: 'R' });
    await triggerEvent(document, 'keydown', { key: 'w' });

    assert
      .dom('[data-test-dialog-question]')
      .hasText('Accept: push 3 changes to PROJ-45-split-invoice-writer');
    assert.dom('[data-test-rework-dialog]').doesNotExist();
    assert.dom('[data-test-dialog-body]').hasValue('Thanks, pushed.');
  });

  test('S under an open dialog opens no review behind it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    await click('[data-test-dialog-question]');

    await triggerEvent(document, 'keydown', { key: 'S' });

    assert.dom('[data-test-review]').doesNotExist();
  });

  test('j under an open dialog stays on the thread', async function (assert) {
    board().conversations = [
      board().threadIn('proposed', { key: 'k1' }),
      board().threadIn('proposed', { key: 'k2' }),
    ];
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    await click('[data-test-dialog-question]');

    await triggerEvent(document, 'keydown', { key: 'j' });
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1', 'j');
    await triggerEvent(document, 'keydown', { key: 'k' });

    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1', 'k');
    assert.dom('[data-test-dialog]').exists();
  });

  test('a reason the board refused is there when the dialog opens again', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 409,
      code: 'operation-outstanding',
      detail: 'thread k1 already has an operation waiting',
    };
    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'reject from tab A');

    await click('[data-test-dialog-submit]');
    await click('[data-test-decision="reject"]');

    assert.dom('[data-test-dialog-body]').hasValue('reject from tab A');
  });

  test('a reason the board took is not offered again', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="reject"]');
    await fillIn('[data-test-dialog-body]', 'not this way');

    await click('[data-test-dialog-submit]');
    await click('[data-test-decision="reject"]');

    assert.dom('[data-test-dialog-body]').hasValue('');
  });

  module('after a landing failed', function (hooks) {
    function landedWith(phase: Phase) {
      board().conversations = [board().threadIn(phase, { key: 'k1' })];
    }

    hooks.beforeEach(function () {
      board().comments['k1'] = [];
    });

    test('retrying the reply asks only for the reply, and pushes nothing', async function (assert) {
      landedWith('reply failed');
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="approve"]');

      assert.dom('[data-test-dialog-question]').containsText('Retry the reply');
      assert.dom('[data-test-dialog]').containsText('nothing is pushed again');
      assert.dom('[data-test-commit-message]').doesNotExist();
      assert.dom('[data-test-edit-message]').doesNotExist();
      assert.dom('[data-test-commit-file]').doesNotExist();
      assert.dom('[data-test-dialog-submit]').hasText('Post the commit link');
      await fillIn('[data-test-dialog-body]', 'pushed, thanks');
      assert.dom('[data-test-dialog-submit]').hasText('Post the reply');
    });

    test('pushing again says nothing new is committed and why it may be refused', async function (assert) {
      landedWith('push failed');
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="approve"]');

      assert
        .dom('[data-test-dialog-question]')
        .containsText('Push the fix again');
      assert.dom('[data-test-dialog]').containsText('nothing new is committed');
      assert.dom('[data-test-dialog]').containsText('newer commits');
      assert.dom('[data-test-edit-message]').doesNotExist();
      assert.dom('[data-test-commit-file]').exists({ count: 2 });
      assert.dom('[data-test-dialog-submit]').hasText('Push again');
    });

    test('reject once the fix is pushed says the commit stays on GitHub', async function (assert) {
      landedWith('reply failed');
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="reject"]');

      assert.dom('[data-test-dialog-question]').doesNotContainText('drops');
      assert
        .dom('[data-test-dialog-question]')
        .containsText('stays on the PR branch on GitHub');
    });

    test('reject once the push failed says the local commit stays', async function (assert) {
      landedWith('push failed');
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="reject"]');

      assert.dom('[data-test-dialog-question]').doesNotContainText('drops');
      assert
        .dom('[data-test-dialog-question]')
        .containsText('stays committed on the PR branch on this machine');
    });
  });

  test('accepting a fix for a removed comment has no reply to write and no thread to resolve', async function (assert) {
    board().conversations = [board().threadIn('removed', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="approve"]');

    assert.dom('[data-test-dialog-body]').doesNotExist();
    assert.dom('[data-test-reply-kicker]').doesNotExist();
    assert.dom('[data-test-resolve]').doesNotExist();
    assert.dom('[data-test-dialog-submit]').hasText('Push commit');
  });

  test('resolving a removed comment asks first, with no reply to write', async function (assert) {
    board().conversations = [board().threadIn('removed', { key: 'k1' })];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="resolve"]');

    assert.dom('[data-test-dialog-body]').doesNotExist();
    assert
      .dom('[data-test-dialog-submit]')
      .hasText('Resolve, posting nothing to GitHub');
  });

  module('accepting a proposed reply', function (hooks) {
    hooks.beforeEach(function () {
      board().proposals['k1'] = [
        proposal({
          kind: 'reply',
          reply: 'It runs once per poll, so the cache is never stale.',
          commits: null,
          summary: null,
          commit_message: null,
        }),
      ];
    });

    test('asks before it posts the reply, with the reply filled in', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="approve"]');

      assert
        .dom('[data-test-dialog-question]')
        .hasText('This posts this reply to the comment. Are you sure?');
      assert
        .dom('[data-test-dialog-body]')
        .hasValue('It runs once per poll, so the cache is never stale.');
      assert.dom('[data-test-commit-message]').doesNotExist();
      assert.dom('[data-test-commit-file]').doesNotExist();
      assert.dom('[data-test-delete]').doesNotExist();
      assert.dom('[data-test-dialog-submit]').hasText('Post reply');
    });

    test('posts the reply as you left it, and resolves only when ticked', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');
      await click('[data-test-decision="approve"]');

      await fillIn('[data-test-dialog-body]', 'It runs once per poll.');
      await click('[data-test-resolve]');
      await click('[data-test-dialog-submit]');

      assert.strictEqual(board().posted[0]!.verb, 'approve');
      assert.deepEqual(board().posted[0]!.body, {
        reply: 'It runs once per poll.',
        delete_comment: false,
        resolve: true,
      });
    });

    test('an untouched reply posts what the agent wrote', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');
      await click('[data-test-decision="approve"]');

      await click('[data-test-dialog-submit]');

      assert.deepEqual(board().posted[0]!.body, {
        reply: 'It runs once per poll, so the cache is never stale.',
        delete_comment: false,
        resolve: false,
      });
    });
  });

  module('accepting a proposed ticket', function (hooks) {
    hooks.beforeEach(function () {
      board().proposals['k1'] = [
        proposal({
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
    });

    test('asks before it files, with the ticket and the reply filled in', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="approve"]');

      assert
        .dom('[data-test-dialog-question]')
        .hasText('This files this ticket and posts this reply. Are you sure?');
      assert.dom('[data-test-ticket-project]').hasValue('PROJ');
      assert
        .dom('[data-test-ticket-title]')
        .hasValue('Cache tax rates across exports');
      assert
        .dom('[data-test-ticket-body]')
        .hasValue('Each export reads its tax rate again.');
      assert
        .dom('[data-test-dialog-body]')
        .hasValue('That belongs outside this PR, so I have proposed a ticket.');
      assert.dom('[data-test-commit-message]').doesNotExist();
      assert.dom('[data-test-commit-file]').doesNotExist();
      assert.dom('[data-test-delete]').doesNotExist();
      assert
        .dom('[data-test-dialog-submit]')
        .hasText('File ticket and post reply');
    });

    test('retrying the reply once the ticket is filed asks only for the reply', async function (assert) {
      board().conversations = [board().threadIn('reply failed', { key: 'k1' })];
      board().comments['k1'] = [];
      await visit('/pr/o/r/7/conversations/k1');

      await click('[data-test-decision="approve"]');

      assert.dom('[data-test-dialog]').containsText('nothing is filed again');
      assert.dom('[data-test-ticket-project]').doesNotExist();
      assert.dom('[data-test-ticket-title]').doesNotExist();
      assert
        .dom('[data-test-dialog-body]')
        .hasValue('That belongs outside this PR, so I have proposed a ticket.');
      assert.dom('[data-test-dialog-submit]').hasText('Post the reply');
    });

    test('asks to file the ticket and post the reply as you left them', async function (assert) {
      await visit('/pr/o/r/7/conversations/k1');
      await click('[data-test-decision="approve"]');

      await fillIn('[data-test-ticket-project]', 'WEB');
      await fillIn('[data-test-ticket-title]', 'Cache models');
      await fillIn('[data-test-ticket-body]', 'Read each model once.');
      await fillIn('[data-test-dialog-body]', 'I have proposed a ticket.');
      await click('[data-test-dialog-submit]');

      assert.strictEqual(board().posted[0]!.verb, 'approve');
      assert.deepEqual(board().posted[0]!.body, {
        reply: 'I have proposed a ticket.',
        delete_comment: false,
        resolve: false,
        ticket: {
          project: 'WEB',
          title: 'Cache models',
          body: 'Read each model once.',
        },
      });
    });
  });
});
