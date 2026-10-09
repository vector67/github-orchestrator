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
  added,
  comment,
  context,
  diffOf,
  proposal,
  setupFakeBoard,
} from 'frontend/tests/helpers/fake-board';

module('Acceptance | rework', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  hooks.beforeEach(function () {
    board().conversations = [board().threadIn('proposed', { key: 'k1' })];
    board().comments['k1'] = [
      comment(),
      comment({ id: 2, author: 'octocat', review_state: null }),
      comment({ id: 3, review_state: null }),
    ];
    board().proposals['k1'] = [proposal({ id: 'k1.1.proposal' })];
    board().diffs['k1.1.proposal'] = diffOf(
      'billing/invoice_writer.py',
      added(142, '    return sorted(line_items)'),
      context(143, '    done'),
    );
  });

  test('pointing at a line and sending posts the whole brief', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'use the enum instead');
    await click('[data-test-rework-dialog] [data-test-row="added"]');
    await click('[data-test-include="anna"] input');
    await click('[data-test-send-rework]');

    assert.strictEqual(board().posted.length, 1);
    assert.strictEqual(board().posted[0]!.verb, 'rework');
    assert.deepEqual(board().posted[0]!.body, {
      note: 'use the enum instead',
      pointed: [
        {
          file: 'billing/invoice_writer.py',
          line: 142,
          text: '    return sorted(line_items)',
        },
      ],
      include: ['anna'],
    });
  });

  test('ticking the visible terminal sends the brief to a session in the Terminal tab', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');
    assert
      .dom('[data-test-rework-visible]')
      .hasText('Do rework in visible terminal session');
    await fillIn('[data-test-rework-body]', 'use the enum instead');
    await click('[data-test-rework-dialog] [data-test-row="added"]');
    await click('[data-test-include="anna"] input');
    await click('[data-test-rework-visible] input');
    await click('[data-test-send-rework]');

    assert.strictEqual(board().posted.length, 1);
    assert.strictEqual(board().posted[0]!.verb, 'start-session');
    assert.deepEqual(board().posted[0]!.body, {
      steer: 'use the enum instead',
      pointed: [
        {
          file: 'billing/invoice_writer.py',
          line: 142,
          text: '    return sorted(line_items)',
        },
      ],
      include: ['anna'],
    });
    assert.strictEqual(currentURL(), '/pr/o/r/7/terminal');
  });

  test('the send says what it did and closes the dialog', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');
    await click('[data-test-rework-dialog] [data-test-row="added"]');
    await click('[data-test-send-rework]');

    assert
      .dom('[data-test-toast]')
      .hasText('Sent back for rework with 1 pointed line. Agent re-running.');
    assert.dom('[data-test-rework-dialog]').doesNotExist();
  });

  test('the dialog brings the diff with it and says to click its lines', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    assert.dom('[data-test-fold-title]').hasText('Proposed diff · 1 file');
    assert.dom('[data-test-rework-dialog]').doesNotExist();

    await click('[data-test-decision="rework"]');

    assert
      .dom('[data-test-pointing-title]')
      .hasText('Click lines to point the agent at them');
    assert.dom('[data-test-rework-dialog] [data-test-row="added"]').exists();
    assert
      .dom('[data-test-include]')
      .exists({ count: 1 }, 'the viewer is never offered their own replies');
  });

  test('cancelling the dialog posts nothing at all', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');
    await click('[data-test-rework-dialog] [data-test-row="added"]');
    await click('[data-test-cancel-rework]');

    assert.strictEqual(board().posted.length, 0);
    assert.dom('[data-test-rework-dialog]').doesNotExist();
  });

  test('Claude switched off says so rather than failing quietly', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    board().refusal = {
      status: 409,
      code: 'agents-disabled',
      detail: 'Agents are disabled (agents_enabled=false)',
    };

    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'try again');
    await click('[data-test-send-rework]');

    assert.dom('[data-test-toast]').containsText('Agents are switched off');
  });

  test('it names itself and says what to write in the box', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-rework-kicker]').hasText('Send back for rework');
    assert
      .dom('[data-test-rework-body]')
      .hasAttribute('placeholder', 'Tell the agent what to change and why…');
    assert
      .dom('[data-test-rework-note]')
      .hasText(
        'Comment moves to "Sent back for rework"; the agent re-runs with your note and the pointed lines.',
      );
  });

  test('a conversation with no diff to show still takes a note', async function (assert) {
    board().conversations = [board().threadIn('declined', { key: 'k1' })];
    board().proposals['k1'] = [];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'try it anyway');
    await click('[data-test-send-rework]');

    assert.dom('[data-test-diff]').doesNotExist();
    assert.deepEqual(board().posted[0]!.body, {
      note: 'try it anyway',
      pointed: [],
      include: [],
    });
  });

  test('nothing pointed yet is still counted', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-pointed-count]').hasText('0 lines pointed');
    assert.dom('[data-test-chip]').doesNotExist();
  });

  test('clicking a line points it and clicking it again unpoints it', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    await click(rows()[0]!);

    assert.dom(rows()[0]).hasAttribute('data-pointed');
    assert.dom('[data-test-pointed-count]').hasText('1 line pointed');
    assert
      .dom('[data-test-chip] [data-test-chip-code]')
      .hasText('return sorted(line_items)');

    await click(rows()[0]!);

    assert.dom(rows()[0]).doesNotHaveAttribute('data-pointed');
    assert.dom('[data-test-pointed-count]').hasText('0 lines pointed');
    assert.dom('[data-test-chip]').doesNotExist();
  });

  test('it counts the pointed lines and wears one chip each, in the order pointed', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    await click(rows()[1]!);
    await click(rows()[0]!);

    assert.dom('[data-test-pointed-count]').hasText('2 lines pointed');
    assert.deepEqual(chips(), ['done ×', 'return sorted(line_items) ×']);
  });

  test('a chip unpoints the one line it names', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await click(rows()[0]!);
    await click(rows()[1]!);

    await click('[data-test-chip]');

    assert.deepEqual(chips(), ['done ×']);
    assert.dom(rows()[0]).doesNotHaveAttribute('data-pointed');
    await click('[data-test-send-rework]');
    assert.deepEqual(board().posted[0]!.body, {
      note: '',
      pointed: [
        { file: 'billing/invoice_writer.py', line: 143, text: '    done' },
      ],
      include: [],
    });
  });

  test('past three chips the rest fold into a count', async function (assert) {
    board().diffs['k1.1.proposal'] = diffOf(
      'a.py',
      ...[1, 2, 3, 4, 5, 6, 7, 8].map((line) => added(line, `row ${line}`)),
    );
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    for (const row of rows()) await click(row);

    assert.dom('[data-test-pointed-count]').hasText('8 lines pointed');
    assert.deepEqual(chips(), ['row 1 ×', 'row 2 ×', 'row 3 ×']);
    assert.dom('[data-test-chip-overflow]').hasText('+5 more');
  });

  test('three chips or fewer fold nothing', async function (assert) {
    board().diffs['k1.1.proposal'] = diffOf(
      'a.py',
      ...[1, 2, 3].map((line) => added(line, `row ${line}`)),
    );
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    for (const row of rows()) await click(row);

    assert.dom('[data-test-chip]').exists({ count: 3 });
    assert.dom('[data-test-chip-overflow]').doesNotExist();
  });

  test('a removed line and an added line on one number are two points', async function (assert) {
    board().diffs['k1.1.proposal'] = diffOf(
      'a.py',
      { kind: 'removed', old_line: 13, new_line: null, text: '  return rows' },
      added(13, '  return sorted(rows)'),
    );
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    await click(rows()[0]!);
    await click(rows()[1]!);

    assert.dom('[data-test-pointed-count]').hasText('2 lines pointed');

    await click(rows()[0]!);
    await click('[data-test-send-rework]');

    assert.deepEqual(board().posted[0]!.body, {
      note: '',
      pointed: [{ file: 'a.py', line: 13, text: '  return sorted(rows)' }],
      include: [],
    });
  });

  test('the send waits until there is a note or a pointed line', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-send-rework]').isDisabled();
    assert.dom('[data-test-send-rework]').hasText('Send to agent for rework');

    await fillIn('[data-test-rework-body]', '   ');
    assert
      .dom('[data-test-send-rework]')
      .isDisabled('whitespace is not a note');

    await fillIn('[data-test-rework-body]', 'use the enum instead');
    assert.dom('[data-test-send-rework]').isNotDisabled();

    await fillIn('[data-test-rework-body]', '');
    await click(rows()[0]!);
    assert
      .dom('[data-test-send-rework]')
      .isNotDisabled('a pointed line is enough');
  });

  test('it offers a tick per reviewer who replied', async function (assert) {
    board().people = [
      { login: 'anna', name: 'Anna Example' },
      { login: 'mira', name: 'Mira Sample' },
    ];
    board().comments['k1'] = [
      comment(),
      comment({ id: 2, author: 'anna', review_state: null }),
      comment({ id: 3, author: 'mira', review_state: null }),
    ];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-include]').exists({ count: 2 });
    assert.dom('[data-test-include="anna"]').hasText("Include Anna's replies");
    assert.dom('[data-test-include="mira"]').hasText("Include Mira's replies");
  });

  test('a conversation nobody replied to offers no tick at all', async function (assert) {
    board().comments['k1'] = [comment()];
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-include]').doesNotExist();
  });

  test('a reviewer is ticked and unticked', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'use the enum');

    await click('[data-test-include="anna"] input');
    assert.dom('[data-test-include="anna"] input').isChecked();
    await click('[data-test-include="anna"] input');
    assert.dom('[data-test-include="anna"] input').isNotChecked();
    await click('[data-test-send-rework]');

    assert.deepEqual(board().posted[0]!.body, {
      note: 'use the enum',
      pointed: [],
      include: [],
    });
  });

  test('the close cross backs out and posts nothing', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'use the enum');

    await click('[data-test-rework-close]');

    assert.dom('[data-test-rework-dialog]').doesNotExist();
    assert.strictEqual(board().posted.length, 0);
  });

  test('cancelling throws the note, the pointed lines and the ticks away', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'use the enum');
    await click(rows()[0]!);
    await click('[data-test-include="anna"] input');

    await click('[data-test-cancel-rework]');
    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-rework-body]').hasValue('');
    assert.dom('[data-test-pointed-count]').hasText('0 lines pointed');
    assert.dom(rows()[0]).doesNotHaveAttribute('data-pointed');
    assert.dom('[data-test-include="anna"] input').isNotChecked();
  });

  test('a brief is open on one conversation at a time, and waits there', async function (assert) {
    seedSecond();
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'kept across a visit');

    await visit('/pr/o/r/7/conversations/k2');
    assert.dom('[data-test-rework-dialog]').doesNotExist();

    await visit('/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-rework-body]').hasValue('kept across a visit');
  });

  test('opening a brief on another conversation starts it blank', async function (assert) {
    seedSecond();
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await fillIn('[data-test-rework-body]', 'kept');
    await click(rows()[0]!);
    await click('[data-test-include="anna"] input');

    await visit('/pr/o/r/7/conversations/k2');
    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-rework-body]').hasValue('');
    assert.dom('[data-test-pointed-count]').hasText('0 lines pointed');
    assert.dom('[data-test-include="anna"] input').isNotChecked();

    await visit('/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-rework-dialog]').doesNotExist();
  });

  test('the dialog opens with the cursor in the note', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');

    await click('[data-test-decision="rework"]');

    assert.dom('[data-test-rework-body]').isFocused();
    assert
      .dom('[data-test-rework-dialog] [role="dialog"]')
      .hasAttribute('aria-modal', 'true');
  });

  test('escape closes the dialog and leaves the thread open', async function (assert) {
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await click('[data-test-include="anna"] input');

    await triggerEvent(document, 'keydown', { key: 'Escape' });

    assert.dom('[data-test-rework-dialog]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-decision="rework"]').isFocused();
  });

  test('board keys under the dialog neither move nor stack another', async function (assert) {
    seedSecond();
    await visit('/pr/o/r/7/conversations/k1');
    await click('[data-test-decision="rework"]');
    await click('[data-test-rework-kicker]');

    await triggerEvent(document, 'keydown', { key: 'a' });
    await triggerEvent(document, 'keydown', { key: 'j' });

    assert.dom('[data-test-dialog]').doesNotExist();
    assert.strictEqual(currentURL(), '/pr/o/r/7/conversations/k1');
    assert.dom('[data-test-rework-dialog]').exists();
  });

  function seedSecond() {
    board().conversations = [
      ...board().conversations,
      board().threadIn('proposed', { key: 'k2' }),
    ];
    board().comments['k2'] = board().comments['k1']!;
    board().proposals['k2'] = [
      proposal({ id: 'k2.1.proposal', operation: 'k2.1' }),
    ];
    board().diffs['k2.1.proposal'] = board().diffs['k1.1.proposal']!;
  }
});

function rows(): Element[] {
  return [
    ...document.querySelectorAll(
      '[data-test-rework-dialog] [role="button"][data-line]',
    ),
  ];
}

function chips(): string[] {
  return [...document.querySelectorAll('[data-test-chip]')].map((one) =>
    (one.textContent ?? '').replace(/\s+/g, ' ').trim(),
  );
}
