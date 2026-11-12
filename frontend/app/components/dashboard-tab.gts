import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { pulses } from 'frontend/motion';
import { concat, fn } from '@ember/helper';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import DismissConfirm from 'frontend/components/dismiss-confirm';
import type { DismissUntil } from 'frontend/data/api';
import GitPalette from 'frontend/components/git-palette';
import GitPaletteState from 'frontend/components/git-palette-state';
import Glyphs from 'frontend/components/glyphs';
import PendingRing from 'frontend/components/pending-ring';
import RebaseButton from 'frontend/components/rebase-button';
import {
  clockOf,
  notLiveOf,
  standingOf,
  threadsWaitingOf,
  type Reading,
} from 'frontend/data/dashboard';
import { opensDialog, runsAgent, type Pressing } from 'frontend/data/decisions';
import { notesOf } from 'frontend/data/markdown';
import type { Numbered } from 'frontend/data/wall';
import drawn from 'frontend/modifiers/drawn';
import followsEnd from 'frontend/modifiers/follows-end';
import AgentOutput from 'frontend/components/agent-output';
import type DashboardService from 'frontend/services/dashboard';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type PrControlsService from 'frontend/services/pr-controls';
import {
  capOfControl,
  controlOf,
  keyedControl,
  type Control,
  type Controlled,
  type Offer,
} from 'frontend/services/pr-controls';
import type StoreService from 'frontend/services/store';
import type {
  Outstanding,
  ReviewerGroup,
  Summaries,
} from 'frontend/services/store';
import type TerminalService from 'frontend/services/terminal';
import type ToastsService from 'frontend/services/toasts';
import modal from 'frontend/modifiers/modal';
import navigates from 'frontend/modifiers/navigates';
import ReadyConfirm from 'frontend/components/ready-confirm';
import AssignReviewers from 'frontend/components/assign-reviewers';
import type { AssignReviewersRequest } from 'frontend/data/api';
import eq from 'frontend/helpers/eq';

type Pane = 'notes' | 'agent';

const KEYED = [
  'hold',
  'carry-on',
  'start-review',
  'mark-ready',
  'assign-reviewers',
  'take-over',
  'check-for-fixes',
  'dismiss',
  'close',
  'git',
  'release',
] as const;

const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'CapsLock']);

interface DashboardTabSignature {
  Args: { pane?: string | null; ready?: boolean };
}

export default class DashboardTab extends Component<DashboardTabSignature> {
  @service declare dashboard: DashboardService;
  @service declare here: HereService;
  @service declare hub: HubService;
  @service declare keys: KeysService;
  @service declare toasts: ToastsService;
  @service declare router: RouterService;
  @service declare terminal: TerminalService;
  @service declare store: StoreService;
  @service('pr-controls') declare controls: PrControlsService;

  @tracked pane: Pane = 'notes';
  @tracked asking: 'dismiss' | 'close' | 'assign' | null = null;

  readonly palette = new GitPaletteState({
    run: (keys) => this.controls.runGit(this.on!, keys),
    pressing: () => this.summaries?.pressing.git ?? null,
    openInTerminal: async (keys, line) => {
      if (await this.terminal.open(keys, line)) {
        void this.router.transitionTo('terminal');
        return;
      }
      const refused = this.summaries?.pressing.session.refused;
      if (refused)
        this.toasts.say(`${line} did not open: ${refused}`, 'failed');
    },
    say: (text, tone) => this.toasts.say(text, tone),
    opened: (keymap) => this.keys.push('dialog', keymap),
    closed: (keymap) => this.keys.drop(keymap),
  });

  private readonly keymap: Keymap = { take: (key) => this.takes(key) };

  constructor(owner: Owner, args: DashboardTabSignature['Args']) {
    super(owner, args);
    if (args.pane === 'agent') this.pane = 'agent';
    this.keys.push('tab', this.keymap);
  }

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
    this.keys.drop(this.palette.keymap);
  }

  get number(): number | null {
    return this.here.pr?.number ?? null;
  }

  get summaries(): Summaries | null {
    const pr = this.here.pr;
    if (!this.dashboard.shown || pr === null) return null;
    return this.store.summary(pr.repo, pr.number);
  }

  get reading(): Reading | null {
    const shown = this.dashboard.shown;
    return shown ? this.store.reading(shown, this.hub.now) : null;
  }

  get threadsWaiting(): string | null {
    const summaries = this.summaries;
    return summaries ? threadsWaitingOf(summaries) : null;
  }

  get standing(): string | null {
    return standingOf({
      number: this.number,
      dismissed: this.controls.dismissedOf(this.here.pr),
      shown: this.reading !== null,
      missed: this.dashboard.missed,
      starting: this.dashboard.standing === 'starting',
    });
  }

  get paneLive(): boolean {
    return this.pane === 'notes'
      ? this.dashboard.notesLive
      : this.dashboard.outputLive;
  }

  get notLive(): string | null {
    const reading = this.reading;
    return reading ? notLiveOf(reading, this.dashboard.isLive) : null;
  }

  get refreshed(): string {
    return `refreshed ${clockOf(this.dashboard.refreshedAt)}`;
  }

  get on(): Controlled | null {
    return this.controls.onPage;
  }

  offer = (control: Control): Offer => this.controls.offer(this.on, control);

  offered = (control: Control): boolean =>
    this.offer(control).state !== 'absent';

  get pressing(): Pressing | null {
    return this.summaries?.pressing.controls ?? null;
  }

  get pending(): boolean {
    return Boolean(this.pressing?.pressed);
  }

  pressed = (control: Control): boolean =>
    controlOf(this.pressing?.pressed ?? null) === control;

  ringed = (control: Control): boolean =>
    this.pressed(control) && Boolean(this.pressing?.ring);

  labelOf = (control: Control, label: string): string =>
    this.pressed(control) ? (this.pressing?.doing ?? label) : label;

  heldBack = (control: Control): boolean =>
    this.pending || this.offer(control).state === 'held';

  titleOf = (control: Control): string | null => {
    const offer = this.offer(control);
    return offer.state === 'ready' || offer.state === 'held'
      ? offer.title
      : null;
  };

  get releaseAsked(): boolean {
    return this.pending || this.offer('release').state === 'asked';
  }

  showPane = (pane: Pane) => {
    this.pane = pane;
  };

  flipPane = () => {
    this.pane = this.pane === 'notes' ? 'agent' : 'notes';
  };

  get boardHref(): string {
    return this.router.urlFor('conversations');
  }

  toBoard = () => {
    void this.router.transitionTo('conversations');
  };

  toTerminal = () => {
    void this.router.transitionTo('terminal');
  };

  press = (control: Control): boolean => {
    const next = this.controls.press(this.on, control);
    if (next === 'confirm-dismiss') this.asking = 'dismiss';
    else if (next === 'confirm-close') this.asking = 'close';
    else if (next === 'confirm-ready') this.askReady(true);
    else if (next === 'confirm-assign') this.asking = 'assign';
    else if (next === 'palette') this.palette.open();
    return next !== 'nothing';
  };

  cancelAsking = () => {
    this.asking = null;
  };

  dismiss = (until: DismissUntil) => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.dismiss(on, until);
  };

  close = () => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.close(on);
  };

  private askReady(ready: boolean): void {
    void this.router.replaceWith({ queryParams: { ready } });
  }

  cancelReady = () => {
    this.askReady(false);
  };

  markReady = () => {
    this.cancelReady();
    const on = this.on;
    if (on) void this.controls.markReady(on);
  };

  assignReviewers = (pick: AssignReviewersRequest) => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.assignReviewers(on, pick);
  };

  assignWhenReady = (pick: AssignReviewersRequest) => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.assignWhenReady(on, pick);
  };

  get draft(): boolean {
    return this.on?.shown.facts?.draft ?? false;
  }

  get savedPick(): AssignReviewersRequest | null {
    return this.on?.shown.drawn.system.assign_when_ready ?? null;
  }

  get groups(): ReviewerGroup[] | null {
    const pr = this.here.pr;
    return pr ? this.store.reviewable(pr) : null;
  }

  get readyAbout(): Numbered | null {
    return this.args.ready && this.offered('mark-ready') ? this.here.pr : null;
  }

  get outstanding(): Outstanding | null {
    const pr = this.here.pr;
    return pr ? this.store.outstanding(pr.repo, pr.number) : null;
  }

  closeSubmitted = (event: Event) => {
    event.preventDefault();
    this.close();
  };

  closeAnswer = (key: string): boolean => {
    if (MODIFIERS.has(key)) return true;
    if (key === 'y') this.close();
    else this.cancelAsking();
    return true;
  };

  private takes(key: string): boolean {
    const reading = this.reading;
    if (!reading || this.controls.dismissedOf(this.here.pr)) return false;
    const control = keyedControl(key, KEYED);
    if (control) return this.press(control);
    if (key === 'C') this.flipPane();
    else if (key === 't' && !reading.frozen) this.toTerminal();
    else return false;
    return true;
  }

  <template>
    <main id="dashboard" data-test-dashboard>
      {{#if this.standing}}
        <p class="dash-standing" role="status" data-test-standing>
          {{this.standing}}
        </p>
      {{else if this.reading}}
        <section
          class="actionband {{this.reading.band.state}}"
          data-pending={{if this.pending "true"}}
          data-refused={{if this.pressing.refused "true"}}
          data-test-action-band
          data-test-band={{this.reading.band.state}}
        >
          <div class="band-words">
            <div
              class="lab"
              data-test-band-label
            >{{this.reading.band.label}}</div>
            <div class="big" data-test-band-move>{{#if
                this.reading.working
              }}<span
                  class="live-dot"
                  {{pulses this.reading.move}}
                ></span>{{/if}}{{this.reading.move}}</div>
            {{#if this.reading.frozen}}
              <div class="detail" data-test-band-detail>The worktree at
                <span class="mono">{{this.reading.frozen.worktree}}</span>
                holds
                <b class="mono">{{this.reading.frozen.here}}</b>, not
                <b class="mono">{{this.reading.frozen.expected}}</b>.</div>
            {{else if this.reading.band.detail}}
              <div
                class="detail"
                data-test-band-detail
              >{{this.reading.band.detail}}</div>
            {{/if}}
            {{#if this.reading.band.computed}}
              <div
                class="computed"
                data-test-band-computed
              >{{this.reading.band.computed}}</div>
            {{/if}}
            {{#if this.reading.notice}}
              <div class="notice" role="status" data-test-notice>
                {{this.reading.notice}}
              </div>
            {{/if}}
            {{#if this.pressing.refused}}
              <p class="refusal" data-test-refusal>{{this.pressing.refused}}</p>
            {{/if}}
          </div>
          <div class="controls">
            {{#if this.reading.frozen}}
              <button
                type="button"
                class="btn fill"
                disabled={{this.releaseAsked}}
                data-opens-dialog={{if (opensDialog "release") "true"}}
                data-runs-agent={{if (runsAgent "release") "true"}}
                data-test-control="release"
                {{on "click" (fn this.press "release")}}
              >{{#if (this.ringed "release")}}<PendingRing
                  />{{/if}}{{this.labelOf "release" "Release now"}}<Glyphs
                  @opensDialog={{opensDialog "release"}}
                  @runsAgent={{runsAgent "release"}}
                />
                <kbd>{{capOfControl "release"}}</kbd></button>
            {{else}}
              {{#if this.threadsWaiting}}
                <a
                  href={{this.boardHref}}
                  class="btn"
                  data-test-control="board"
                  {{navigates this.toBoard}}
                >Open the Board <kbd>2</kbd></a>
              {{/if}}
              {{#if this.reading.onHold}}
                <button
                  type="button"
                  class="btn fill"
                  disabled={{this.pending}}
                  title={{this.titleOf "hold"}}
                  data-opens-dialog={{if (opensDialog "hold") "true"}}
                  data-runs-agent={{if (runsAgent "hold") "true"}}
                  data-test-control="resume"
                  {{on "click" (fn this.press "hold")}}
                >{{this.labelOf "hold" "Resume the agent"}}<Glyphs
                    @opensDialog={{opensDialog "hold"}}
                    @runsAgent={{runsAgent "hold"}}
                  />
                  <kbd>{{capOfControl "hold"}}</kbd></button>
              {{else}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.pending}}
                  title={{this.titleOf "hold"}}
                  data-opens-dialog={{if (opensDialog "hold") "true"}}
                  data-runs-agent={{if (runsAgent "hold") "true"}}
                  data-test-control="hold"
                  {{on "click" (fn this.press "hold")}}
                >{{this.labelOf "hold" "Put on hold"}}<Glyphs
                    @opensDialog={{opensDialog "hold"}}
                    @runsAgent={{runsAgent "hold"}}
                  />
                  <kbd>{{capOfControl "hold"}}</kbd></button>
              {{/if}}
              <button
                type="button"
                class="btn"
                disabled={{this.heldBack "carry-on"}}
                title={{this.titleOf "carry-on"}}
                data-opens-dialog={{if (opensDialog "carry-on") "true"}}
                data-runs-agent={{if (runsAgent "carry-on") "true"}}
                data-test-control="carry-on"
                {{on "click" (fn this.press "carry-on")}}
              >{{this.labelOf "carry-on" "Carry on"}}<Glyphs
                  @opensDialog={{opensDialog "carry-on"}}
                  @runsAgent={{runsAgent "carry-on"}}
                />
                <kbd>{{capOfControl "carry-on"}}</kbd></button>
              {{#if (this.offered "start-review")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "start-review"}}
                  title={{this.titleOf "start-review"}}
                  data-opens-dialog={{if (opensDialog "start-review") "true"}}
                  data-runs-agent={{if (runsAgent "start-review") "true"}}
                  data-test-control="start-review"
                  {{on "click" (fn this.press "start-review")}}
                >{{this.labelOf "start-review" "Start a review agent"}}<Glyphs
                    @opensDialog={{opensDialog "start-review"}}
                    @runsAgent={{runsAgent "start-review"}}
                  />
                  <kbd>{{capOfControl "start-review"}}</kbd></button>
              {{/if}}
              {{#if (this.offered "mark-ready")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "mark-ready"}}
                  title={{this.titleOf "mark-ready"}}
                  data-opens-dialog={{if (opensDialog "mark-ready") "true"}}
                  data-runs-agent={{if (runsAgent "mark-ready") "true"}}
                  data-test-control="mark-ready"
                  {{on "click" (fn this.press "mark-ready")}}
                >{{#if (this.ringed "mark-ready")}}<PendingRing
                    />{{/if}}{{this.labelOf
                    "mark-ready"
                    "Ready for review"
                  }}<Glyphs
                    @opensDialog={{opensDialog "mark-ready"}}
                    @runsAgent={{runsAgent "mark-ready"}}
                  />
                  <kbd>{{capOfControl "mark-ready"}}</kbd></button>
              {{/if}}
              {{#if (this.offered "assign-reviewers")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "assign-reviewers"}}
                  title={{this.titleOf "assign-reviewers"}}
                  data-opens-dialog={{if
                    (opensDialog "assign-reviewers")
                    "true"
                  }}
                  data-runs-agent={{if (runsAgent "assign-reviewers") "true"}}
                  data-test-control="assign-reviewers"
                  {{on "click" (fn this.press "assign-reviewers")}}
                >{{this.labelOf "assign-reviewers" "Assign reviewers"}}<Glyphs
                    @opensDialog={{opensDialog "assign-reviewers"}}
                    @runsAgent={{runsAgent "assign-reviewers"}}
                  />
                  <kbd>{{capOfControl "assign-reviewers"}}</kbd></button>
              {{/if}}
              {{#if (this.offered "take-over")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "take-over"}}
                  title={{this.titleOf "take-over"}}
                  data-opens-dialog={{if (opensDialog "take-over") "true"}}
                  data-runs-agent={{if (runsAgent "take-over") "true"}}
                  data-test-control="take-over"
                  {{on "click" (fn this.press "take-over")}}
                >{{this.labelOf "take-over" "Take over"}}<Glyphs
                    @opensDialog={{opensDialog "take-over"}}
                    @runsAgent={{runsAgent "take-over"}}
                  />
                  <kbd>{{capOfControl "take-over"}}</kbd></button>
              {{/if}}
              {{#if (this.offered "check-for-fixes")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "check-for-fixes"}}
                  title={{this.titleOf "check-for-fixes"}}
                  data-opens-dialog={{if
                    (opensDialog "check-for-fixes")
                    "true"
                  }}
                  data-runs-agent={{if (runsAgent "check-for-fixes") "true"}}
                  data-test-control="check-for-fixes"
                  {{on "click" (fn this.press "check-for-fixes")}}
                >{{this.labelOf "check-for-fixes" "Check for fixes"}}<Glyphs
                    @opensDialog={{opensDialog "check-for-fixes"}}
                    @runsAgent={{runsAgent "check-for-fixes"}}
                  />
                  <kbd>{{capOfControl "check-for-fixes"}}</kbd></button>
              {{/if}}
              <button
                type="button"
                class="btn"
                disabled={{this.heldBack "dismiss"}}
                title={{this.titleOf "dismiss"}}
                data-opens-dialog={{if (opensDialog "dismiss") "true"}}
                data-runs-agent={{if (runsAgent "dismiss") "true"}}
                data-test-control="dismiss"
                {{on "click" (fn this.press "dismiss")}}
              >{{this.labelOf
                  "dismiss"
                  (concat "Dismiss #" this.reading.number)
                }}<Glyphs
                  @opensDialog={{opensDialog "dismiss"}}
                  @runsAgent={{runsAgent "dismiss"}}
                />
                <kbd>{{capOfControl "dismiss"}}</kbd></button>
              {{#if (this.offered "close")}}
                <button
                  type="button"
                  class="btn danger"
                  disabled={{this.heldBack "close"}}
                  title={{this.titleOf "close"}}
                  data-opens-dialog={{if (opensDialog "close") "true"}}
                  data-runs-agent={{if (runsAgent "close") "true"}}
                  data-test-control="close"
                  {{on "click" (fn this.press "close")}}
                >{{#if (this.ringed "close")}}<PendingRing
                    />{{/if}}{{this.labelOf
                    "close"
                    (concat "Close PR #" this.reading.number)
                  }}<Glyphs
                    @opensDialog={{opensDialog "close"}}
                    @runsAgent={{runsAgent "close"}}
                  />
                  <kbd>{{capOfControl "close"}}</kbd></button>
              {{/if}}
            {{/if}}
          </div>
        </section>
        {{#if (eq this.asking "close")}}
          <div class="decide-dialog">
            <form
              role="dialog"
              aria-modal="true"
              aria-labelledby="close-confirm-question"
              tabindex="-1"
              data-test-close-confirm
              {{modal this.cancelAsking this.closeAnswer}}
              {{on "submit" this.closeSubmitted}}
            >
              <header class="dialog-head">
                <p class="question" id="close-confirm-question">Close #{{this.reading.number}}
                  on GitHub?</p>
                <button
                  type="button"
                  class="dialog-close"
                  aria-label="cancel"
                  {{on "click" this.cancelAsking}}
                >×</button>
              </header>
              <div class="dialog-actions">
                <button
                  type="submit"
                  class="primary danger"
                  data-test-close-option
                >Close it <kbd>y</kbd></button>
                <button
                  type="button"
                  class="ghost"
                  data-test-close-cancel
                  {{on "click" this.cancelAsking}}
                >Cancel <kbd>Esc</kbd></button>
              </div>
            </form>
          </div>
        {{/if}}
        {{#if this.readyAbout}}
          <ReadyConfirm
            @repo={{this.readyAbout.repo}}
            @number={{this.readyAbout.number}}
            @outstanding={{this.outstanding}}
            @groups={{this.groups}}
            @mark={{this.markReady}}
            @assign={{this.assignReviewers}}
            @assignWhenReady={{this.assignWhenReady}}
            @cancel={{this.cancelReady}}
          />
        {{/if}}
        {{#if (eq this.asking "assign")}}
          <AssignReviewers
            @number={{this.reading.number}}
            @groups={{this.groups}}
            @draft={{this.draft}}
            @pick={{this.savedPick}}
            @assign={{this.assignReviewers}}
            @assignWhenReady={{this.assignWhenReady}}
            @cancel={{this.cancelAsking}}
          />
        {{/if}}
        {{#if (eq this.asking "dismiss")}}
          <DismissConfirm
            @number={{this.reading.number}}
            @wording={{this.reading.dismiss}}
            @dismiss={{this.dismiss}}
            @cancel={{this.cancelAsking}}
          />
        {{/if}}
        {{#if this.notLive}}
          <p class="not-live" data-test-not-live>{{this.notLive}}</p>
        {{/if}}
        <div class="dgrid">
          <div class="dleft">
            <section class="blk status" data-test-block="status">
              <h2 class="bh"><span>Status</span></h2>
              {{#if this.reading.detailedReviewer}}
                <span
                  class="loud"
                  title={{this.reading.detailedReviewer.hint}}
                  data-test-flag
                >{{this.reading.detailedReviewer.text}}</span>
              {{/if}}
              {{#if this.reading.unpolled}}
                <p class="note">{{this.reading.unpolled}}</p>
              {{/if}}
              {{#each this.reading.status key="key" as |one|}}
                <div class="kv" data-test-status={{one.key}}>
                  <span
                    title={{if one.hint one.hint}}
                    data-test-label
                  >{{one.label}}</span>
                  <span
                    class="{{if one.quiet 'quiet'}} {{if one.alarm 'alarm-t'}}"
                  >{{#if one.alarm}}<i
                        class="sq alarm"
                        data-test-alarm
                      ></i>{{/if}}<span
                      data-test-value
                    >{{one.value}}</span>{{#if one.rebase}}
                      <RebaseButton />{{/if}}</span>
                </div>
              {{/each}}
            </section>
            {{#if this.reading.since}}
              <section class="blk" data-test-block="since">
                <h2 class="bh"><span>Since you last acted</span></h2>
                <div class="since" data-test-since>
                  {{#each this.reading.since key="@index" as |one|}}<span
                    >{{one}}</span>{{/each}}
                </div>
              </section>
            {{/if}}
            <section class="blk system" data-test-block="system">
              <h2 class="bh"><span>System</span><span
                  data-test-refreshed
                >{{this.refreshed}}</span></h2>
              {{#each this.reading.system key="key" as |one|}}
                <div class="kv" data-test-system={{one.key}}>
                  <span
                    title={{if one.hint one.hint}}
                    data-test-label
                  >{{one.label}}</span>
                  <span data-test-value>{{one.value}}</span>
                </div>
              {{/each}}
            </section>
          </div>
          <div class="dright">
            <div class="panehead">
              <span
                class="seg"
                role="group"
                aria-label="what the right pane shows"
              >
                <button
                  type="button"
                  aria-pressed={{if (eq this.pane "notes") "true" "false"}}
                  data-test-pane-toggle="notes"
                  {{on "click" (fn this.showPane "notes")}}
                >Notes</button>
                <button
                  type="button"
                  aria-pressed={{if (eq this.pane "agent") "true" "false"}}
                  data-test-pane-toggle="agent"
                  {{on "click" (fn this.showPane "agent")}}
                >Agent output <kbd>⇧C</kbd></button>
              </span>
              <span>{{if
                  (eq this.pane "notes")
                  "agent-changes.md"
                  "The agent's output, newest last"
                }}{{#unless this.paneLive}}
                  ·
                  <span class="pane-not-live" data-test-pane-live>not live: the
                    board is not answering</span>{{/unless}}</span>
            </div>
            {{#if (eq this.pane "notes")}}
              {{#if this.dashboard.notes}}
                <div
                  class="md comment-body"
                  data-test-notes
                  {{drawn notesOf this.dashboard.notes}}
                  {{followsEnd this.dashboard.notes}}
                ></div>
              {{else if this.dashboard.notesLive}}
                <p class="md note" data-test-notes-empty>
                  The agent has written no notes yet.
                </p>
              {{else}}
                <p class="md note" data-test-notes-empty>
                  The notes come from the manager’s board, which is not
                  answering.
                </p>
              {{/if}}
            {{else if this.dashboard.output.length}}
              <AgentOutput @lines={{this.dashboard.output}} />
            {{else if this.dashboard.outputLive}}
              <p class="tx note" data-test-output-empty>
                The agent has said nothing on this pull request yet.
              </p>
            {{else}}
              <p class="tx note" data-test-output-empty>
                The agent’s output comes from the manager’s board, which is not
                answering.
              </p>
            {{/if}}
          </div>
        </div>
      {{/if}}
      {{#if this.palette.isOpen}}
        <GitPalette @number={{this.number}} @palette={{this.palette}} />
      {{/if}}
    </main>
  </template>
}
