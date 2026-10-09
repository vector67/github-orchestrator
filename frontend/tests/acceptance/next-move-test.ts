import { module, test } from 'qunit';
import { setupApplicationTest } from 'frontend/tests/helpers';
import { find, findAll, visit } from '@ember/test-helpers';
import type { MentionFact, PrFacts } from 'frontend/data/api';
import {
  dashboard,
  heldPr,
  setupFakeBoard,
  threadRow as row,
  type DashboardOver,
} from 'frontend/tests/helpers/fake-board';

interface OnTheWall {
  wallMove: string | null;
  group: string | null;
  flags: string[];
}

interface OnTheDashboard {
  move: string | null;
  muted: boolean;
  verb: string;
  computed: string;
}

const REVIEWED_AT = '2026-06-09T12:00:00Z';
const BEFORE_YOUR_REVIEW = '2026-06-09T11:00:00Z';
const AFTER_YOUR_REVIEW = '2026-06-09T13:00:00Z';

const PASSING: Partial<PrFacts> = {
  ci_status: 'passing',
  merge_state: 'blocked',
  unresolved_threads: 0,
};

const NOBODY_ASKED_FOR_CHANGES: Partial<PrFacts> = {
  review_decision: 'review-required',
  pending_reviewers: [],
  changes_requested_by: [],
};

const CI_FAILING: Partial<PrFacts> = {
  ...NOBODY_ASKED_FOR_CHANGES,
  ci_status: 'failing',
  merge_state: 'blocked',
  unresolved_threads: 3,
};

const READY_TO_MERGE: Partial<PrFacts> = {
  ...NOBODY_ASKED_FOR_CHANGES,
  review_decision: 'approved',
  merge_state: 'clean',
};

const WAITING_ON_REVIEW: Partial<PrFacts> = {
  ...PASSING,
  pending_reviewers: ['grace'],
  review_decision: 'review-required',
};

const SOMEONE_ELSES: Partial<PrFacts> = {
  is_author: false,
  pending_reviewers: [],
  merge_state: 'clean',
  review_decision: 'review-required',
};

const ASKED_AGAIN: Partial<PrFacts> = {
  ...SOMEONE_ELSES,
  viewer_requested: true,
  my_review: 'commented',
  my_review_at: REVIEWED_AT,
};

const REVIEWED: Partial<PrFacts> = {
  ...SOMEONE_ELSES,
  review_decision: 'approved',
  my_review: 'approved',
  my_review_at: REVIEWED_AT,
};

const WAITING_ON_THE_AUTHOR: Partial<PrFacts> = {
  ...SOMEONE_ELSES,
  my_review: 'changes-requested',
  my_review_at: REVIEWED_AT,
  unresolved_threads: 3,
};

function reviewing(over: Partial<PrFacts>): Partial<PrFacts> {
  return { ...SOMEONE_ELSES, ...over };
}

function reviewed(
  verdict: string,
  over: Partial<PrFacts> = {},
): Partial<PrFacts> {
  return reviewing({
    my_review: verdict,
    my_review_at: REVIEWED_AT,
    pending_reviewers: ['erin'],
    ...over,
  });
}

function mention(
  author: string,
  at: string | null = AFTER_YOUR_REVIEW,
  answered = false,
): MentionFact {
  return { author, at, answered };
}

function text(selector: string): string {
  return find(selector)?.textContent?.trim().replace(/\s+/g, ' ') ?? '';
}

module('Acceptance | next move', function (hooks) {
  setupApplicationTest(hooks);
  const board = setupFakeBoard(hooks);

  function serve(over: DashboardOver): void {
    board().serves = 'hub';
    board().held = [heldPr({ dashboard: over })];
    board().manager = dashboard(over);
  }

  async function wallRead(): Promise<OnTheWall> {
    await visit('/');
    const wallRow = find('[data-test-wall-row="o/r#7"]');
    return {
      wallMove: wallRow?.getAttribute('data-move') ?? null,
      group: wallRow?.getAttribute('data-flip-group') ?? null,
      flags: findAll('[data-test-wall-row="o/r#7"] [data-test-move-flag]').map(
        (one) => one.textContent.trim(),
      ),
    };
  }

  async function dashboardRead(): Promise<OnTheDashboard> {
    await visit('/pr/o/r/7/dashboard');
    const next = find('[data-test-your-move]');
    return {
      move: next?.getAttribute('data-move') ?? null,
      muted: next?.getAttribute('data-muted') === 'true',
      verb: find('[data-test-your-move] .vb')?.getAttribute('title') ?? '',
      computed: text('[data-test-band-computed]'),
    };
  }

  async function seen(
    over: DashboardOver,
  ): Promise<OnTheWall & OnTheDashboard> {
    serve(over);
    return { ...(await wallRead()), ...(await dashboardRead()) };
  }

  async function onTheWall(over: DashboardOver): Promise<OnTheWall> {
    serve(over);
    return wallRead();
  }

  async function onTheDashboard(over: DashboardOver): Promise<OnTheDashboard> {
    serve(over);
    return dashboardRead();
  }

  async function moveAndGroup(over: DashboardOver): Promise<string[]> {
    const { move, group } = await seen(over);
    return [move ?? 'none', group ?? 'off the wall'];
  }

  const NOTHING_ELSE: [string, DashboardOver, string[]][] = [
    ['fix ci', { facts: CI_FAILING }, ['fix-ci', 'needs-you']],
    [
      'ready to merge',
      { facts: READY_TO_MERGE },
      ['ready-to-merge', 'needs-you'],
    ],
    [
      'ci running',
      { facts: { ...WAITING_ON_REVIEW, ci_status: 'pending' } },
      ['await-ci', 'waiting-on-others'],
    ],
    [
      'awaiting review',
      { facts: WAITING_ON_REVIEW },
      ['await-review', 'waiting-on-others'],
    ],
    [
      'review',
      { facts: reviewing({ viewer_requested: true, ci_status: 'pending' }) },
      ['review', 'needs-you'],
    ],
    ['re-review', { facts: ASKED_AGAIN }, ['rereview', 'needs-you']],
    [
      'awaiting other reviewers',
      { facts: REVIEWED },
      ['await-author', 'waiting-on-others'],
    ],
    [
      'awaiting the author',
      { facts: WAITING_ON_THE_AUTHOR },
      ['await-rerequest', 'waiting-on-others'],
    ],
  ];

  for (const [name, over, wanted] of NOTHING_ELSE) {
    test(`with nothing else going on the move is what the pull request wants and its group who has the ball: ${name}`, async function (assert) {
      const shown = await seen(over);
      assert.deepEqual([shown.move, shown.group], wanted);
      assert.strictEqual(
        shown.wallMove,
        wanted[0],
        'the wall row carries the move the NEXT box shows',
      );
    });
  }

  const YOU_OWE: [string, Partial<PrFacts>, string, string][] = [
    [
      'ci failing beats a conflict',
      { ...CI_FAILING, merge_state: 'conflicts' },
      'fix-ci',
      'Fix CI',
    ],
    [
      'changes owed beat failing ci',
      { ...CI_FAILING, changes_requested_by: ['bob'] },
      'address-feedback',
      'Address changes requested from bob',
    ],
    [
      'a requester not asked again',
      {
        ...PASSING,
        review_decision: 'changes-requested',
        changes_requested_by: ['carol', 'bob'],
        pending_reviewers: ['carol'],
      },
      'address-feedback',
      'Address changes requested from bob',
    ],
    [
      'every requester asked again',
      {
        ...PASSING,
        review_decision: 'changes-requested',
        changes_requested_by: ['carol'],
        pending_reviewers: ['carol'],
      },
      'await-rereview',
      'Waiting on carol to re-review',
    ],
    [
      'conflicts',
      { ...PASSING, ...NOBODY_ASKED_FOR_CHANGES, merge_state: 'conflicts' },
      'rebase',
      '',
    ],
    [
      'behind main',
      { ...PASSING, ...NOBODY_ASKED_FOR_CHANGES, merge_state: 'behind' },
      'rebase',
      '',
    ],
    [
      'nobody asked for changes',
      WAITING_ON_REVIEW,
      'await-review',
      'Waiting on reviewers grace',
    ],
  ];

  for (const [name, facts, move, verb] of YOU_OWE) {
    test(`on your own pull request changes you owe come first, then CI, then main: ${name}`, async function (assert) {
      const shown = await onTheDashboard({ facts });

      assert.deepEqual([shown.move, shown.verb], [move, verb]);
    });
  }

  const NOBODY_PENDING: Partial<PrFacts> = {
    ...PASSING,
    review_decision: null,
    pending_reviewers: [],
    changes_requested_by: [],
  };

  test('with nobody pending review your own pull request waits on you, not on reviewers: ready for review', async function (assert) {
    const shown = await seen({ facts: { ...NOBODY_PENDING, draft: false } });

    assert.deepEqual(
      [shown.move, shown.group, shown.muted],
      ['request-reviewers', 'needs-you', false],
    );
  });

  test('with nobody pending review your own pull request waits on you, not on reviewers: draft', async function (assert) {
    const shown = await seen({ facts: { ...NOBODY_PENDING, draft: true } });

    assert.deepEqual(
      [shown.move, shown.group, shown.muted],
      ['mark-ready-for-review', 'draft', true],
    );
  });

  for (const [name, facts] of [
    ['fix ci', CI_FAILING],
    ['ready to merge', READY_TO_MERGE],
  ] as const) {
    test(`a draft is in the Draft group with the rest of the list muted: ${name}`, async function (assert) {
      const undrafted = await onTheDashboard({ facts });
      const drafted = await seen({ facts: { ...facts, draft: true } });

      assert.deepEqual(
        [drafted.move, drafted.group, drafted.muted],
        [undrafted.move, 'draft', true],
      );
      assert.false(undrafted.muted);
    });
  }

  const FLAGS: [string, Partial<PrFacts>, string[]][] = [
    ['your pr failing ci', CI_FAILING, ['Fix CI', '3 unresolved threads']],
    [
      'your draft behind main',
      {
        ...PASSING,
        ...NOBODY_ASKED_FOR_CHANGES,
        merge_state: 'conflicts',
        draft: true,
      },
      ['Draft', 'Rebase'],
    ],
    ['nothing to flag', READY_TO_MERGE, []],
    [
      'someone else’s pr with threads open',
      WAITING_ON_THE_AUTHOR,
      ['3 unresolved threads'],
    ],
    [
      'someone else’s pr failing ci and behind',
      reviewing({
        ci_status: 'failing',
        merge_state: 'behind',
        unresolved_threads: 1,
        my_review: 'commented',
        my_review_at: REVIEWED_AT,
      }),
      ['Fix CI', 'Rebase', '1 unresolved thread'],
    ],
  ];

  for (const [name, facts, flags] of FLAGS) {
    test(`flags name what holds on the pull request whatever the move: ${name}`, async function (assert) {
      assert.deepEqual((await onTheWall({ facts })).flags, flags);
    });
  }

  test('the people a waiting move names travel with it', async function (assert) {
    board().serves = 'hub';
    board().held = [
      heldPr({
        dashboard: {
          facts: WAITING_ON_THE_AUTHOR,
          pr: { author: 'alice' },
        },
      }),
    ];

    await visit('/');

    assert
      .dom('[data-test-wall-row="o/r#7"] [data-test-wall-lead]')
      .includesText('Waiting on the author to ask you again')
      .includesText("alice's PR");
  });

  test('a pull request dismissed until its next event is off the wall whatever it wants', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({ facts: CI_FAILING, manager: { hidden: true } }),
      ['fix-ci', 'off the wall'],
    );
  });

  for (const [name, queued, verb] of [
    ['nothing held', 0, 'On hold'],
    ['two held', 2, 'On hold, 2 events held'],
  ] as const) {
    test(`a pull request on hold says so and how many events wait: ${name}`, async function (assert) {
      const shown = await seen({
        facts: { changes_requested_by: ['bob'], pending_reviewers: [] },
        manager: { on_hold: true },
        system: { on_hold: true, queued_events: queued },
      });

      assert.deepEqual(
        [shown.move, shown.group, shown.verb],
        ['on-hold', 'on-hold', verb],
      );
    });
  }

  test('a frozen pull request asks for the worktree back even when on hold', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        manager: { frozen_on: 'another-pr', on_hold: true },
      }),
      ['release-worktree', 'needs-you'],
    );
  });

  test('a run fixing CI says the agent has the ball', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: CI_FAILING,
        manager: { working_on: 'ci-failed' },
      }),
      ['agent-running', 'agent-working'],
    );
  });

  test('a carried-on run says the agent is carrying on', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: WAITING_ON_REVIEW,
        manager: { working_on: 'manual-continue' },
      }),
      ['agent-running', 'agent-working'],
    );
  });

  test('threads an agent is fixing say how many', async function (assert) {
    const shown = await seen({
      facts: WAITING_ON_REVIEW,
      threads: [row('PRRT_1', 'working', 'open', 'human')],
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      [
        'agent-on-human-comments',
        'agent-working',
        'Human comments · 0/1 done · agent on 1',
      ],
    );
  });

  for (const [name, kind, move, verb] of [
    [
      'human',
      'human',
      'human-comments',
      'Human comments · 0/2 done · 2 to decide',
    ],
    ['bot', 'bot', 'bot-comments', 'Bot comments · 0/2 done · 2 to decide'],
  ] as const) {
    test(`comments waiting on you come before failing CI: ${name}`, async function (assert) {
      const shown = await seen({
        facts: CI_FAILING,
        threads: [
          row('PRRT_1', 'ready', 'open', kind),
          row('PRRT_2', 'ready', 'open', kind),
        ],
      });

      assert.deepEqual(
        [shown.move, shown.group, shown.verb],
        [move, 'needs-you', verb],
      );
      assert.true(
        shown.computed.startsWith('PR state: Fix CI'),
        'what the pull request wants sits beneath',
      );
    });
  }

  test('human comments waiting on you come before bot comments', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: CI_FAILING,
        threads: [
          row('PRRT_1', 'ready', 'open', 'bot'),
          row('PRRT_2', 'ready', 'open', 'human'),
        ],
      }),
      ['human-comments', 'needs-you'],
    );
  });

  test('changes you owe come before human comments', async function (assert) {
    const shown = await onTheDashboard({
      facts: {
        ...PASSING,
        review_decision: 'changes-requested',
        changes_requested_by: ['carol'],
        pending_reviewers: [],
      },
      threads: [row('PRRT_1', 'ready', 'open', 'human')],
    });

    assert.deepEqual(
      [shown.move, shown.verb],
      ['address-feedback', 'Address changes requested from carol'],
    );
  });

  test('an agent on human comments comes before bot comments waiting on you', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: CI_FAILING,
        threads: [
          row('PRRT_1', 'ready', 'open', 'bot'),
          row('PRRT_2', 'queued', 'open', 'human'),
        ],
      }),
      ['agent-on-human-comments', 'agent-working'],
    );
  });

  test('an agent on bot comments comes before failing CI', async function (assert) {
    const shown = await seen({
      facts: CI_FAILING,
      threads: [row('PRRT_1', 'working', 'open', 'bot')],
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      [
        'agent-on-bot-comments',
        'agent-working',
        'Bot comments · 0/1 done · agent on 1',
      ],
    );
  });

  test('unsent drafts ask you to send your review', async function (assert) {
    const shown = await seen({
      facts: ASKED_AGAIN,
      threads: [row('draft_1', 'draft', 'draft', 'mine')],
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      ['send-review', 'needs-you', 'Send your review · 1 draft'],
    );
  });

  test('an approved pull request GitHub calls approved waits on the author, whoever is still requested', async function (assert) {
    const shown = await seen({
      facts: reviewed('approved', {
        review_decision: 'approved',
        pending_reviewers: ['heidi'],
      }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      ['await-author', 'waiting-on-others', 'Waiting on the author'],
    );
  });

  test('threads another reviewer opened leave a pull request you approved waiting on its reviewers', async function (assert) {
    const shown = await seen({
      facts: reviewed('approved', { pending_reviewers: ['grace', 'frank'] }),
      threads: [row('PRRT_1', 'ready', 'open', 'human')],
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      [
        'await-reviewers',
        'waiting-on-others',
        'Waiting on reviewers grace, frank',
      ],
    );
  });

  test('an approved pull request with no review decision names who is still requested', async function (assert) {
    const shown = await seen({
      facts: reviewed('approved', {
        review_decision: null,
        pending_reviewers: ['dave', 'erin'],
      }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      [
        'await-author',
        'waiting-on-others',
        'Waiting on the author · dave, erin still requested',
      ],
    );
  });

  test('changes requested by someone else keep the pull request waiting on reviewers', async function (assert) {
    const shown = await seen({
      facts: reviewed('approved', {
        review_decision: 'changes-requested',
        changes_requested_by: ['bob'],
      }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      [
        'await-reviewers',
        'waiting-on-others',
        'Waiting on reviewers erin, bob',
      ],
    );
  });

  for (const verdict of ['commented', 'changes-requested', 'dismissed']) {
    test(`after a review that is not an approval you wait to be asked again: ${verdict}`, async function (assert) {
      assert.deepEqual(await moveAndGroup({ facts: reviewed(verdict) }), [
        'await-rerequest',
        'waiting-on-others',
      ]);
    });
  }

  test('a pull request you were never asked to review and never reviewed is off the wall', async function (assert) {
    const shown = await seen({
      facts: reviewing({ pending_reviewers: ['erin'] }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.computed],
      ['not-reviewing', null, 'You are not a reviewer on this PR'],
    );
  });

  for (const [name, mine, move] of [
    ['first review', null, 'review'],
    ['re-review', 'commented', 'rereview'],
  ] as const) {
    test(`being requested is your turn to review: ${name}`, async function (assert) {
      assert.deepEqual(
        await moveAndGroup({
          facts: reviewing({
            viewer_requested: true,
            pending_reviewers: ['octocat'],
            my_review: mine,
            my_review_at: mine ? REVIEWED_AT : null,
          }),
        }),
        [move, 'needs-you'],
      );
    });
  }

  test('a request to your team is your turn to review', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: reviewing({
          viewer_requested: true,
          pending_reviewers: ['@platform'],
        }),
      }),
      ['review', 'needs-you'],
    );
  });

  test('a re-review counts the threads you opened that the author answered', async function (assert) {
    const shown = await onTheDashboard({
      facts: ASKED_AGAIN,
      threads: [
        row('PRRT_1', 'ready', 'open', 'mine'),
        row('PRRT_2', 'waiting', 'open', 'mine'),
        row('PRRT_3', 'ready', 'open', 'human'),
      ],
    });

    assert.deepEqual(
      [shown.move, shown.verb],
      ['rereview', 'Re-review · 1/2 of your threads answered'],
    );
  });

  test('drafts wait until it is your turn to review', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: REVIEWED,
        threads: [row('draft_1', 'draft', 'draft', 'mine')],
      }),
      ['await-author', 'waiting-on-others'],
    );
  });

  test('a pull request that mentioned you once and was answered sits in Mentioned', async function (assert) {
    const shown = await seen({
      facts: reviewing({
        pending_reviewers: ['erin'],
        mentioned: true,
        mentions: [mention('anna', AFTER_YOUR_REVIEW, true)],
      }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      ['mentioned', 'mentioned', 'Every mention answered'],
    );
  });

  test('a mention you have not answered needs you and names who', async function (assert) {
    const shown = await seen({
      facts: reviewing({
        pending_reviewers: ['erin'],
        mentioned: true,
        mentions: [
          mention('anna'),
          mention('bob', AFTER_YOUR_REVIEW, true),
          mention('carol'),
          mention('anna', null),
        ],
      }),
    });

    assert.deepEqual(
      [shown.move, shown.group, shown.verb],
      ['mention', 'needs-you', 'anna, carol mentioned you'],
    );
  });

  for (const verdict of [
    'approved',
    'commented',
    'changes-requested',
    'dismissed',
  ]) {
    test(`a mention since your review that you have not answered needs you: ${verdict}`, async function (assert) {
      const shown = await seen({
        facts: reviewed(verdict, {
          mentioned: true,
          mentions: [mention('anna')],
        }),
      });

      assert.deepEqual(
        [shown.move, shown.group, shown.verb],
        ['mention', 'needs-you', 'anna mentioned you'],
      );
    });
  }

  for (const [verdict, move, verb] of [
    ['approved', 'await-reviewers', 'Waiting on reviewers erin'],
    ['commented', 'await-rerequest', 'Waiting on the author to ask you again'],
  ] as const) {
    test(`a mention from before your review, or answered, leaves the pull request waiting: ${verdict}`, async function (assert) {
      const shown = await seen({
        facts: reviewed(verdict, {
          mentioned: true,
          mentions: [
            mention('anna', BEFORE_YOUR_REVIEW),
            mention('anna', null),
            mention('bob', AFTER_YOUR_REVIEW, true),
          ],
        }),
      });

      assert.deepEqual(
        [shown.move, shown.group, shown.verb],
        [move, 'waiting-on-others', verb],
      );
    });
  }

  test('your turn to review comes before a mention', async function (assert) {
    assert.deepEqual(
      await moveAndGroup({
        facts: reviewing({
          viewer_requested: true,
          pending_reviewers: ['octocat'],
          mentioned: true,
          mentions: [mention('anna')],
        }),
      }),
      ['review', 'needs-you'],
    );
  });

  test('a merged or closed pull request is off the wall', async function (assert) {
    assert.deepEqual(await moveAndGroup({ facts: { ended: true } }), [
      'closed',
      'off the wall',
    ]);
  });
});
