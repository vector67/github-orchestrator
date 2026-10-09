import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { pulses } from 'frontend/motion';
import { fn } from '@ember/helper';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import DismissConfirm from 'frontend/components/dismiss-confirm';
import GitPalette from 'frontend/components/git-palette';
import GitPaletteState from 'frontend/components/git-palette-state';
import RebaseButton from 'frontend/components/rebase-button';
import {
  clockOf,
  dashboardOf,
  notLiveOf,
  standingOf,
  threadsWaitingOf,
  type Reading,
} from 'frontend/data/dashboard';
import { notesOf } from 'frontend/data/markdown';
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
  keyedControl,
  type Control,
  type Controlled,
  type Offer,
} from 'frontend/services/pr-controls';
import type StoreService from 'frontend/services/store';
import type { Summaries } from 'frontend/services/store';
import type TerminalService from 'frontend/services/terminal';
import type ToastsService from 'frontend/services/toasts';
import modal from 'frontend/modifiers/modal';

type Pane = 'notes' | 'agent';

const KEYED = [
  'hold',
  'carry-on',
  'start-review',
  'dismiss',
  'close',
  'git',
  'release',
] as const;

const eq = (one: unknown, other: unknown): boolean => one === other;

interface DashboardTabSignature {
  Args: { pane?: string | null };
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
  @tracked asking: 'dismiss' | 'close' | null = null;

  readonly palette = new GitPaletteState({
    run: (keys) => this.controls.runGit(this.on!, keys),
    openInTerminal: async (keys, line) => {
      if (await this.terminal.open(keys, line)) {
        void this.router.transitionTo('terminal');
      }
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

  get now(): number {
    return Math.max(this.dashboard.now, this.hub.now);
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
    const summaries = this.summaries;
    return shown && summaries ? dashboardOf(shown, summaries, this.now) : null;
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

  heldBack = (control: Control): boolean =>
    this.offer(control).state === 'held';

  titleOf = (control: Control): string | null => {
    const offer = this.offer(control);
    return offer.state === 'ready' || offer.state === 'held'
      ? offer.title
      : null;
  };

  get releaseAsked(): boolean {
    return this.offer('release').state === 'asked';
  }

  showPane = (pane: Pane) => {
    this.pane = pane;
  };

  flipPane = () => {
    this.pane = this.pane === 'notes' ? 'agent' : 'notes';
  };

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
    else if (next === 'palette') this.palette.open();
    return next !== 'nothing';
  };

  cancelAsking = () => {
    this.asking = null;
  };

  dismiss = (forever: boolean) => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.dismiss(on, forever);
  };

  close = () => {
    this.cancelAsking();
    const on = this.on;
    if (on) void this.controls.close(on);
  };

  closeSubmitted = (event: Event) => {
    event.preventDefault();
    this.close();
  };

  closeAnswer = (key: string): boolean => {
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
          </div>
          <div class="controls">
            {{#if this.reading.frozen}}
              <button
                type="button"
                class="btn fill"
                disabled={{this.releaseAsked}}
                data-test-control="release"
                {{on "click" (fn this.press "release")}}
              >Release now <kbd>{{capOfControl "release"}}</kbd></button>
            {{else}}
              {{#if this.threadsWaiting}}
                <button
                  type="button"
                  class="btn"
                  data-test-control="board"
                  {{on "click" this.toBoard}}
                >Open the Board <kbd>1</kbd></button>
              {{/if}}
              {{#if (this.offered "close")}}
                <button
                  type="button"
                  class="btn danger"
                  disabled={{this.heldBack "close"}}
                  title={{this.titleOf "close"}}
                  data-test-control="close"
                  {{on "click" (fn this.press "close")}}
                >Close PR #{{this.reading.number}}
                  <kbd>{{capOfControl "close"}}</kbd></button>
              {{/if}}
              {{#if this.reading.onHold}}
                <button
                  type="button"
                  class="btn fill"
                  title={{this.titleOf "hold"}}
                  data-test-control="resume"
                  {{on "click" (fn this.press "hold")}}
                >Resume the agent <kbd>{{capOfControl "hold"}}</kbd></button>
              {{else}}
                <button
                  type="button"
                  class="btn"
                  title={{this.titleOf "hold"}}
                  data-test-control="hold"
                  {{on "click" (fn this.press "hold")}}
                >Put on hold <kbd>{{capOfControl "hold"}}</kbd></button>
              {{/if}}
              <button
                type="button"
                class="btn"
                disabled={{this.heldBack "carry-on"}}
                title={{this.titleOf "carry-on"}}
                data-test-control="carry-on"
                {{on "click" (fn this.press "carry-on")}}
              >Carry on <kbd>{{capOfControl "carry-on"}}</kbd></button>
              {{#if (this.offered "start-review")}}
                <button
                  type="button"
                  class="btn"
                  disabled={{this.heldBack "start-review"}}
                  title={{this.titleOf "start-review"}}
                  data-test-control="start-review"
                  {{on "click" (fn this.press "start-review")}}
                >Start a review agent
                  <kbd>{{capOfControl "start-review"}}</kbd></button>
              {{/if}}
              <button
                type="button"
                class="btn"
                disabled={{this.heldBack "dismiss"}}
                title={{this.titleOf "dismiss"}}
                data-test-control="dismiss"
                {{on "click" (fn this.press "dismiss")}}
              >Dismiss #{{this.reading.number}}
                <kbd>{{capOfControl "dismiss"}}</kbd></button>
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
