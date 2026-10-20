import Service, { service } from '@ember/service';
import { tracked } from '@glimmer/tracking';
import { waitForPromise } from '@ember/test-waiters';
import type RouterService from '@ember/routing/router-service';
import type { DismissUntil, GitRun } from 'frontend/data/api';
import { dismissedSaying, type Dismissal } from 'frontend/data/dashboard';
import { capOf } from 'frontend/data/decisions';
import { tried, type Tried } from 'frontend/data/tried';
import { keyOf, type Numbered } from 'frontend/data/wall';
import type DashboardService from 'frontend/services/dashboard';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type PollService from 'frontend/services/poll';
import type StoreService from 'frontend/services/store';
import type { Move, ShownPr, WallRow } from 'frontend/services/store';
import type ToastsService from 'frontend/services/toasts';

export type Control =
  | 'hold'
  | 'carry-on'
  | 'start-review'
  | 'mark-ready'
  | 'dismiss'
  | 'close'
  | 'git'
  | 'release';

export type Pressed =
  | 'nothing'
  | 'done'
  | 'palette'
  | 'confirm-dismiss'
  | 'confirm-close'
  | 'confirm-ready';

export interface Controlled {
  number: number;
  shown: ShownPr;
  move: Move | null;
  yours: boolean;
  held: boolean;
  live: boolean;
  showing: 'board' | 'hub';
}

export type Offer =
  | { state: 'ready'; title: string | null }
  | { state: 'held'; title: string }
  | { state: 'asked' }
  | { state: 'absent' };

const ONLY_W = 'Only w works here: the worktree holds another branch.';

const HINTS = {
  close: 'Closes this pull request on GitHub, after you confirm',
  hold: 'Stops this PR’s agent: no event is dispatched and no board thread drained until you resume',
  resume:
    'Lets this PR’s agent dispatch its held events and drain the board again',
  'carry-on':
    'Starts the agent again, carrying on its last conversation in this worktree, with no new instructions',
  'start-review':
    'Starts a review agent as a review request does, for when the automatic one went wrong: a re-review when you have reviewed before',
  dismiss:
    'Takes this PR off the wall, until its next event or forever; you choose after the click',
  'mark-ready':
    'Marks this draft ready for review on GitHub, after you confirm with what is still outstanding in front of you',
};

const BOARD_DOWN = {
  'carry-on': 'Carry on waits for the manager’s board, which is not answering.',
  'start-review':
    'Start a review agent waits for the manager’s board, which is not answering.',
  dismiss: 'Dismiss goes through the manager’s board, which is not answering.',
  close: 'Close goes through the manager’s board, which is not answering.',
  'mark-ready':
    'Ready for review goes through the manager’s board, which is not answering.',
  git: 'Git runs through the manager’s board, which is not answering.',
};

const DISMISSALS: Record<DismissUntil, Dismissal> = {
  'next-event': 'until its next event',
  'ready-for-review': 'until it is ready for review',
  forever: 'forever',
};

const ABSENT: Offer = { state: 'absent' };

const held = (title: string): Offer => ({ state: 'held', title });

const REVIEW_MOVES: ReadonlySet<Move | null> = new Set(['review', 'rereview']);

function agentHeldBack(shown: ShownPr): string | null {
  const agent = shown.drawn.system.agent;
  if (!agent.enabled) return 'Agents are disabled for this pull request.';
  if (agent.state === 'working') return 'The agent is already working.';
  return null;
}

function carryOnHeldBack(shown: ShownPr): string | null {
  const agent = agentHeldBack(shown);
  if (agent) return agent;
  if (!shown.drawn.system.last_run)
    return 'The agent has no earlier run here to carry on from.';
  return null;
}

type HubVerb = 'hold' | 'resume' | 'release';

interface Sent {
  verb: HubVerb;
}

function onHoldOf(shown: ShownPr, sent: Sent | undefined): boolean {
  if (sent?.verb === 'hold') return true;
  if (sent?.verb === 'resume') return false;
  return shown.drawn.system.on_hold;
}

function releaseOffer(shown: ShownPr, sent: Sent | undefined): Offer {
  if (!shown.drawn.frozen) return ABSENT;
  if (shown.drawn.frozen.release_requested || sent?.verb === 'release')
    return { state: 'asked' };
  return { state: 'ready', title: null };
}

function heldBackOf(control: Control, shown: ShownPr): string | null {
  if (control === 'carry-on') return carryOnHeldBack(shown);
  if (control === 'start-review') return agentHeldBack(shown);
  return null;
}

function offerOf(
  on: Controlled,
  control: Control,
  sent: Sent | undefined,
): Offer {
  const shown = on.shown;
  if (control === 'release') return releaseOffer(shown, sent);
  if (shown.drawn.frozen) return held(ONLY_W);
  if (control === 'hold') {
    return {
      state: 'ready',
      title: onHoldOf(shown, sent) ? HINTS.resume : HINTS.hold,
    };
  }
  if (control === 'close' && !on.yours) return ABSENT;
  if (control === 'mark-ready' && !(on.yours && shown.facts?.draft))
    return ABSENT;
  if (control === 'start-review' && !REVIEW_MOVES.has(on.move)) return ABSENT;
  const why = heldBackOf(control, shown);
  if (why) return held(why);
  if (!on.live) return held(BOARD_DOWN[control]);
  return {
    state: 'ready',
    title: control === 'git' ? null : HINTS[control],
  };
}

const KEYS: Record<Control, string> = {
  hold: 'h',
  'carry-on': 'c',
  'start-review': 'a',
  'mark-ready': 'r',
  dismiss: 'd',
  close: 'Q',
  git: 'g',
  release: 'w',
};

export function keyedControl(
  key: string,
  among: readonly Control[],
): Control | undefined {
  return among.find((control) => KEYS[control] === key);
}

export function capOfControl(control: Control): string {
  return capOf(KEYS[control]);
}

type Command =
  'hold' | 'carry-on' | 'start-review' | 'mark-ready' | 'close' | 'release';

export default class PrControlsService extends Service {
  @service declare dashboard: DashboardService;
  @service declare here: HereService;
  @service declare hub: HubService;
  @service('poll') declare loader: PollService;
  @service declare router: RouterService;
  @service declare store: StoreService;
  @service declare toasts: ToastsService;

  @tracked private dismissals: ReadonlyMap<string, Dismissal> = new Map();
  @tracked private sent: ReadonlyMap<string, Sent> = new Map();

  get onPage(): Controlled | null {
    const shown = this.dashboard.shown;
    const number = this.here.pr?.number ?? null;
    if (!shown || number === null) return null;
    const live = this.dashboard.isLive;
    return {
      number,
      shown,
      move: this.moveOf(shown.repo, number),
      yours: this.yours(shown.repo, number),
      held: this.dashboard.onTheWall,
      live,
      showing: live ? 'board' : 'hub',
    };
  }

  ofRow(row: WallRow): Controlled {
    return {
      number: row.number,
      shown: row,
      move: row.summaries.move.code,
      yours: this.yours(row.repo, row.number),
      held: true,
      live: row.drawn.standing === 'answering',
      showing: 'hub',
    };
  }

  private moveOf(repo: string, number: number): Move | null {
    return this.store.summary(repo, number)?.move.code ?? null;
  }

  private yours(repo: string, number: number): boolean {
    return this.store.pr(repo, number)?.facts?.is_author === true;
  }

  offer(on: Controlled | null, control: Control): Offer {
    return on ? offerOf(on, control, this.sentTo(on)) : ABSENT;
  }

  press(on: Controlled | null, control: Control): Pressed {
    if (!on) return 'nothing';
    const offer = offerOf(on, control, this.sentTo(on));
    if (offer.state === 'absent') return 'nothing';
    if (offer.state === 'held') this.toasts.say(offer.title, 'failed');
    if (offer.state !== 'ready') return 'done';
    if (control === 'dismiss') return 'confirm-dismiss';
    if (control === 'close') return 'confirm-close';
    if (control === 'mark-ready') {
      void waitForPromise(this.readOutstanding(on));
      return 'confirm-ready';
    }
    if (control === 'git') return 'palette';
    void this.carryOut(on, control);
    return 'done';
  }

  close = (on: Controlled): Promise<void> => this.carryOut(on, 'close');

  markReady = (on: Controlled): Promise<void> =>
    this.carryOut(on, 'mark-ready');

  dismiss = (on: Controlled, until: DismissUntil): Promise<void> =>
    waitForPromise(this.dismissing(on, until));

  dismissedOf(pr: Numbered | null): Dismissal | null {
    if (pr === null) return null;
    const how = this.dismissals.get(keyOf(pr));
    if (!how) return null;
    return this.hub.find(pr)?.drawn?.standing === 'answering' ? null : how;
  }

  runGit = (on: Controlled, keys: string): Promise<Tried<GitRun>> =>
    waitForPromise(
      tried(
        'manager git',
        this.store.runGit(`${this.prefix(on)}/api/manager/git`, keys),
      ),
    );

  private carryOut(on: Controlled, control: Command): Promise<void> {
    return waitForPromise(this.carrying(on, control));
  }

  private sentTo(on: Controlled): Sent | undefined {
    return this.sent.get(keyOf(on.shown));
  }

  private prefix(on: Controlled): string {
    return this.here.prefixOf(on.shown);
  }

  private async carrying(on: Controlled, control: Command): Promise<void> {
    if (control === 'release') {
      if (on.held) await this.throughTheHub(on.shown, 'release');
      return;
    }
    if (control === 'hold') {
      const verb = onHoldOf(on.shown, this.sentTo(on)) ? 'resume' : 'hold';
      if (on.showing === 'hub' && on.held) {
        await this.throughTheHub(on.shown, verb);
      } else {
        await this.throughTheManager(on, verb);
      }
      return;
    }
    if (!(await this.throughTheManager(on, control))) return;
    if (control === 'close') {
      this.toasts.say(
        `Asked GitHub to close #${on.number}. The watcher tears it down on its next poll.`,
        'done',
      );
    }
    if (control === 'mark-ready') {
      this.toasts.say(
        `Asked GitHub to mark #${on.number} ready for review.`,
        'done',
      );
    }
  }

  private async readOutstanding(on: Controlled): Promise<void> {
    const pr = on.shown;
    if (on.showing === 'hub') {
      const asked = await this.store
        .ask({ kind: 'conversations', pr }, null)
        .catch(() => null);
      if (asked?.changed) asked.take();
    }
  }

  private async dismissing(on: Controlled, until: DismissUntil): Promise<void> {
    const how = DISMISSALS[until];
    if (!(await this.throughTheManager(on, 'dismiss', { until }))) return;
    this.dismissals = new Map(this.dismissals).set(keyOf(on.shown), how);
    this.toasts.say(dismissedSaying(on.number, how), 'done');
    await this.loader.refreshHub();
    const here = this.here.pr;
    if (here !== null && keyOf(here) === keyOf(on.shown))
      void this.router.transitionTo('index');
  }

  private async throughTheManager(
    on: Controlled,
    verb: string,
    body?: unknown,
  ): Promise<boolean> {
    const taken = await tried(
      `manager ${verb}`,
      this.store.hand(`${this.prefix(on)}/api/manager:${verb}`, body),
    );
    if (!taken.done) {
      this.toasts.say(
        `The manager did not take the ${verb.replace('-', ' ')}: ${taken.why}`,
        'failed',
      );
    }
    return taken.done;
  }

  private async throughTheHub(row: ShownPr, verb: HubVerb): Promise<void> {
    const key = keyOf(row);
    const sent = { verb };
    this.sent = new Map(this.sent).set(key, sent);
    try {
      await this.handToTheHub(row, verb);
    } finally {
      if (this.sent.get(key) === sent) {
        const left = new Map(this.sent);
        left.delete(key);
        this.sent = left;
      }
    }
  }

  private async handToTheHub(row: ShownPr, verb: HubVerb): Promise<void> {
    const taken = await tried(
      `hub ${verb}`,
      this.store.hand(`/api/pull-requests/${row.repo}/${row.number}:${verb}`),
    );
    if (!taken.done) {
      this.toasts.say(
        `${keyOf(row)} did not take the ${verb}: ${taken.why}`,
        'failed',
      );
    }
    await this.loader.refreshHub();
  }
}
