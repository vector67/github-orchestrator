import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn, uniqueId } from '@ember/helper';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import { pageTitle } from 'ember-page-title';
import DismissConfirm from 'frontend/components/dismiss-confirm';
import ReadyConfirm from 'frontend/components/ready-confirm';
import HubBar from 'frontend/components/hub-bar';
import StateChip from 'frontend/components/state-chip';
import { copyAddress, openOnGitHub } from 'frontend/data/address';
import { ageOf, dashboardOf, type Reading } from 'frontend/data/dashboard';
import { failingOf, keyOf, pageOf } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type {
  Outstanding,
  WallRow,
  WallSection,
} from 'frontend/services/store';
import type KeysService from 'frontend/services/keys';
import { stepped, type Keymap } from 'frontend/services/keys';
import type PrControlsService from 'frontend/services/pr-controls';
import {
  capOfControl,
  keyedControl,
  type Control,
} from 'frontend/services/pr-controls';
import type ToastsService from 'frontend/services/toasts';
import { moves, pulses, selects } from 'frontend/motion';

const same = (one: unknown, other: unknown): boolean => one === other;

const KEYED = ['hold', 'carry-on', 'mark-ready', 'dismiss', 'release'] as const;

const FOLDABLE = 'parked';
const PARKED_FOLDED = 'wall-parked-folded';

function foldedBefore(): boolean {
  try {
    return localStorage.getItem(PARKED_FOLDED) === 'true';
  } catch {
    return false;
  }
}

interface WallSignature {
  Args: { ready?: string | null };
}

export default class Wall extends Component<WallSignature> {
  @service declare hub: HubService;
  @service declare store: StoreService;
  @service declare router: RouterService;
  @service declare keys: KeysService;
  @service declare toasts: ToastsService;
  @service('pr-controls') declare controls: PrControlsService;

  @tracked confirming: Pick<WallRow, 'key' | 'arrived'> | null = null;
  @tracked parkedFolded = foldedBefore();

  private readonly keymap: Keymap = { take: (key) => this.takes(key) };
  private lastAt = -1;

  constructor(owner: Owner, args: WallSignature['Args']) {
    super(owner, args);
    this.keys.push('screen', this.keymap);
  }

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get order(): WallRow[] {
    return this.hub.sections.flatMap((section) => this.shownOf(section));
  }

  foldable = (section: WallSection): boolean => section.group === FOLDABLE;

  isFolded = (section: WallSection): boolean =>
    this.foldable(section) && this.parkedFolded;

  shownOf = (section: WallSection): WallRow[] =>
    this.isFolded(section) ? [] : section.prs;

  toggleParked = () => {
    this.parkedFolded = !this.parkedFolded;
    try {
      localStorage.setItem(PARKED_FOLDED, String(this.parkedFolded));
    } catch {
      return;
    }
  };

  get stale(): boolean {
    return this.hub.stale && this.order.length > 0;
  }

  get chosen(): WallRow | undefined {
    return this.order.find((pr) => keyOf(pr) === this.hub.selected);
  }

  readingOf = (pr: WallRow): Reading =>
    dashboardOf(
      pr,
      pr.summaries,
      this.hub.now,
      failingOf(pr, this.store.ledger?.runs ?? []),
    );

  get tabTitle(): string {
    const count = this.store.needYou;
    return count ? `(${count}) wall` : 'wall';
  }

  ageOf = (pr: WallRow): string => ageOf(pr.entered, this.hub.now);

  ageHintOf = (section: WallSection, pr: WallRow): string =>
    `In ${section.name} for ${this.ageOf(pr)}`;

  get filteredOut(): string {
    const hidden = this.store.hidden;
    return hidden === 1
      ? '1 pull request in other repos is filtered out'
      : `${hidden} pull requests in other repos are filtered out`;
  }

  showAll = () => {
    this.store.choose(null);
  };

  isSelected = (pr: WallRow): boolean => keyOf(pr) === this.hub.selected;

  isConfirming = (pr: WallRow): boolean =>
    pr.key === this.confirming?.key && pr.arrived === this.confirming.arrived;

  isReadying = (pr: WallRow): boolean => keyOf(pr) === this.args.ready;

  outstandingOf = (pr: WallRow): Outstanding | null =>
    this.store.outstanding(pr.repo, pr.number);

  private askReady(ready: string | null): void {
    void this.router.replaceWith({ queryParams: { ready } });
  }

  cancelReady = () => {
    this.askReady(null);
  };

  markReady = (pr: WallRow) => {
    this.cancelReady();
    void this.controls.markReady(this.controls.ofRow(pr));
  };

  open = (pr: WallRow) => {
    void this.router.transitionTo(pageOf(pr));
  };

  select = (pr: WallRow) => {
    this.hub.selected = keyOf(pr);
    this.lastAt = this.order.indexOf(pr);
  };

  releasable = (pr: WallRow): boolean =>
    this.controls.offer(this.controls.ofRow(pr), 'release').state === 'ready';

  titleOf = (pr: WallRow, control: Control): string | null => {
    const offer = this.controls.offer(this.controls.ofRow(pr), control);
    return 'title' in offer ? offer.title : null;
  };

  pressed = (pr: WallRow, control: Control) => {
    this.press(pr, control);
  };

  dismiss = (pr: WallRow, forever: boolean) => {
    this.confirming = null;
    void this.controls.dismiss(this.controls.ofRow(pr), forever);
  };

  private press(pr: WallRow, control: Control): boolean {
    const next = this.controls.press(this.controls.ofRow(pr), control);
    if (next === 'confirm-dismiss')
      this.confirming = { key: pr.key, arrived: pr.arrived };
    if (next === 'confirm-ready') this.askReady(keyOf(pr));
    return next !== 'nothing';
  }

  cancel = () => {
    this.confirming = null;
  };

  private move(by: number): void {
    const order = this.order;
    const chosen = this.chosen;
    const at = chosen ? order.indexOf(chosen) : this.lastAt - (by > 0 ? 1 : 0);
    const next = stepped(order, at, by);
    if (!next) return;
    this.leaveTheRow();
    this.select(next);
  }

  private leaveTheRow(): void {
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && focused.closest('.wall-row'))
      focused.blur();
  }

  private takes(key: string): boolean {
    const pr = this.chosen;
    if (key === 'Enter' && document.activeElement?.closest('.row-controls'))
      return false;
    if (key === 'j' || key === 'k') {
      this.move(key === 'j' ? 1 : -1);
      return true;
    }
    if (!pr) return false;
    const control = keyedControl(key, KEYED);
    if (control) return this.press(pr, control);
    if (key === 'Enter') this.open(pr);
    else if (key === 'o') openOnGitHub(pr.url);
    else if (key === 'y') void this.copy(pr);
    else return false;
    return true;
  }

  private async copy(pr: WallRow): Promise<void> {
    this.toasts.say(await copyAddress(pr.url), 'done');
  }

  <template>
    {{pageTitle this.tabTitle}}
    <main id="wall" data-test-wall>
      <HubBar @on="wall" />
      <h1 class="visually-hidden">Pull requests</h1>
      {{#if this.stale}}
        <p class="wall-stale-note" data-test-wall-stale-note>These rows may be
          out of date.</p>
      {{/if}}
      <div
        class="wall-body"
        data-test-wall-stale={{this.stale}}
        {{moves}}
        {{selects this.hub.selected}}
      >
        {{#each this.hub.sections key="group" as |section|}}
          <h2
            class="group-head wall-group lvl-{{section.level}}-h"
            data-flip-key="head:{{section.group}}"
            data-test-wall-group={{section.group}}
          ><span
              class="edge-key edge"
              aria-hidden="true"
              data-square={{section.edge}}
              data-test-edge-key
            ></span>{{#if (this.foldable section)}}<button
                type="button"
                class="group-fold"
                aria-expanded={{if (this.isFolded section) "false" "true"}}
                title={{if
                  (this.isFolded section)
                  "Show the parked pull requests"
                  "Fold the parked pull requests to their count"
                }}
                data-test-fold
                {{on "click" this.toggleParked}}
              ><span class="group-name">{{section.name}}</span>
                <span
                  class="group-count"
                  data-test-count
                >{{section.prs.length}}</span></button>{{else}}<span
                class="group-name"
              >{{section.name}}</span>
              <span
                class="group-count"
                data-test-count
              >{{section.prs.length}}</span>{{/if}}</h2>
          {{#each (this.shownOf section) key="key" as |pr|}}
            {{#let (this.readingOf pr) (uniqueId) as |reading says|}}
              <div
                class="wall-row edge lvl-{{section.level}}"
                aria-current={{if (this.isSelected pr) "true"}}
                data-square={{reading.edge}}
                data-flip-key={{keyOf pr}}
                data-flip-group={{section.group}}
                data-move={{reading.code}}
                data-test-wall-row={{keyOf pr}}
              >
                <button
                  type="button"
                  class="wall-lead"
                  title="Open #{{pr.number}} · nothing runs until you choose"
                  aria-label="{{reading.move}}: {{reading.title}}"
                  aria-describedby={{says}}
                  data-test-wall-lead
                  {{on "focus" (fn this.select pr)}}
                  {{on "click" (fn this.open pr)}}
                >
                  <span class="move-line"><span
                      class="verb"
                      data-test-verb
                    >{{#if reading.working}}<span
                          class="live-dot"
                          {{pulses reading.move}}
                        ></span>{{/if}}{{reading.move}}</span>{{#if
                      reading.reason
                    }}<span
                        class="reason"
                        data-test-reason
                      >{{reading.reason}}</span>{{/if}}<span
                      class="state-chips"
                    >{{#each reading.chips key="key" as |chip|}}<StateChip
                          @chip={{chip}}
                        />{{/each}}{{#if pr.moved}}<span
                          class="state-chip tone-accent moved"
                          data-test-moved
                        >moved here</span>{{/if}}</span><span
                      class="age"
                      title={{this.ageHintOf section pr}}
                      data-test-age
                    >{{this.ageOf pr}}</span></span>
                  <span
                    class="ttl"
                    data-test-wall-title
                  >{{reading.title}}</span>
                  <span class="meta" data-test-wall-meta>{{#if
                      this.store.severalReposShown
                    }}<span
                        data-test-row-repo
                      >{{pr.repo}}</span>{{/if}}#{{pr.number}}{{#if
                      reading.whose
                    }}
                      ·
                      {{reading.whose}}{{/if}}{{#if reading.branch}}
                      ·
                      <span class="mono">{{reading.branch}}</span>{{/if}}</span>
                  <span id={{says}} class="wall-says">{{#if
                      reading.reason
                    }}<span>{{reading.reason}}.</span>{{/if}}{{#each
                      reading.chips key="key"
                      as |chip|
                    }}<span>{{chip.text}}: {{chip.hint}}.</span>{{/each}}{{#if
                      pr.moved
                    }}<span>moved here.</span>{{/if}}<span>{{this.ageHintOf
                        section
                        pr
                      }}.</span><span>{{#if
                        this.store.severalReposShown
                      }}{{pr.repo}}{{/if}}#{{pr.number}}{{#if reading.whose}}
                        ·
                        {{reading.whose}}{{/if}}{{#if reading.branch}}
                        ·
                        {{reading.branch}}{{/if}}.</span></span>
                </button>
                <span class="row-controls">
                  {{#if (this.releasable pr)}}<button
                      type="button"
                      class="row-control release"
                      data-test-release
                      title="let go of the worktree on the wrong branch; the watcher keeps it aside and cuts a fresh one"
                      {{on "focus" (fn this.select pr)}}
                      {{on "click" (fn this.pressed pr "release")}}
                    >Release</button>{{/if}}
                  {{#unless reading.frozen}}<button
                      type="button"
                      class="row-control"
                      title={{this.titleOf pr "hold"}}
                      data-test-wall-control="hold"
                      {{on "focus" (fn this.select pr)}}
                      {{on "click" (fn this.pressed pr "hold")}}
                    >{{if reading.onHold "Resume" "Hold"}}</button><button
                      type="button"
                      class="row-control"
                      title={{this.titleOf pr "dismiss"}}
                      data-test-wall-control="dismiss"
                      {{on "focus" (fn this.select pr)}}
                      {{on "click" (fn this.pressed pr "dismiss")}}
                    >Dismiss</button>{{/unless}}
                </span>
              </div>
              {{#if (this.isConfirming pr)}}
                <DismissConfirm
                  @number={{pr.number}}
                  @wording={{reading.dismiss}}
                  @dismiss={{fn this.dismiss pr}}
                  @cancel={{this.cancel}}
                />
              {{/if}}
              {{#if (this.isReadying pr)}}
                <ReadyConfirm
                  @repo={{pr.repo}}
                  @number={{pr.number}}
                  @outstanding={{this.outstandingOf pr}}
                  @mark={{fn this.markReady pr}}
                  @cancel={{this.cancelReady}}
                />
              {{/if}}
            {{/let}}
          {{/each}}
        {{else}}
          {{#if this.store.hidden}}
            <div class="wall-empty" data-test-wall-filtered>
              <p>Nothing here in the repos this filter shows.
                {{this.filteredOut}}.</p>
              <button
                type="button"
                class="btn"
                data-test-repo-all
                {{on "click" this.showAll}}
              >Show all repos</button>
            </div>
          {{else if (same this.store.unheld "watcher-failing")}}
            <div class="wall-empty" data-test-wall-unheld="watcher-failing">
              <p>The watcher’s polls are failing.</p>
              {{#if this.store.watcher.fix}}
                <p data-test-wall-fix>{{this.store.watcher.fix}}</p>
              {{/if}}
              <p class="mono" data-test-wall-error>
                {{this.store.watcher.last_error}}
              </p>
            </div>
          {{else if (same this.store.unheld "not-watching")}}
            <div class="wall-empty" data-test-wall-unheld="not-watching">
              <p>This hub watches nothing until its config is complete.</p>
              <p class="mono">{{this.store.configProblem}}</p>
            </div>
          {{else if (same this.store.unheld "watcher-starting")}}
            <p class="wall-empty" data-test-wall-unheld="watcher-starting">
              Waiting for the watcher’s first poll. The wall fills in when it
              ends.
            </p>
          {{else if this.store.heldCount}}
            <p class="wall-empty" data-test-wall-empty>
              None of the pull requests the watcher holds belongs on the wall.
            </p>
          {{else}}
            <p class="wall-empty" data-test-wall-empty>
              The watcher holds no pull requests yet. They appear here after its
              next cycle.
            </p>
          {{/if}}
        {{/each}}
      </div>
      <footer class="wall-foot">
        <span class="grow"></span>
        <span><kbd>j</kbd>
          <kbd>k</kbd>
          move ·
          <kbd>Enter</kbd>
          open ·
          <kbd>{{capOfControl "hold"}}</kbd>
          hold ·
          <kbd>{{capOfControl "dismiss"}}</kbd>
          dismiss ·
          <kbd>{{capOfControl "release"}}</kbd>
          release ·
          <kbd>o</kbd>
          GitHub ·
          <kbd>y</kbd>
          copy link</span>
      </footer>
    </main>
  </template>
}
