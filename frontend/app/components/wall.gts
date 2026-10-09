import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import DismissConfirm from 'frontend/components/dismiss-confirm';
import HubBar from 'frontend/components/hub-bar';
import MoveFlagTag from 'frontend/components/move-flag';
import { copyAddress, openOnGitHub } from 'frontend/data/address';
import {
  dashboardOf,
  HEADS,
  type Reading,
  type Tone,
} from 'frontend/data/dashboard';
import { failingOf, keyOf, pageOf } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type { WallRow } from 'frontend/services/store';
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

const eq = (tone: Tone, wanted: Tone): boolean => tone === wanted;
const same = (one: unknown, other: unknown): boolean => one === other;

const KEYED = ['hold', 'dismiss', 'release'] as const;

export default class Wall extends Component {
  @service declare hub: HubService;
  @service declare store: StoreService;
  @service declare router: RouterService;
  @service declare keys: KeysService;
  @service declare toasts: ToastsService;
  @service('pr-controls') declare controls: PrControlsService;

  @tracked confirming: string | null = null;

  private readonly keymap: Keymap = { take: (key) => this.takes(key) };

  constructor(owner: Owner, args: object) {
    super(owner, args);
    this.keys.push('screen', this.keymap);
  }

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get order(): WallRow[] {
    return this.hub.sections.flatMap((section) => section.prs);
  }

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

  isConfirming = (pr: WallRow): boolean => keyOf(pr) === this.confirming;

  open = (pr: WallRow) => {
    void this.router.transitionTo(pageOf(pr));
  };

  releasable = (pr: WallRow): boolean =>
    this.controls.offer(this.controls.ofRow(pr), 'release').state === 'ready';

  release = (pr: WallRow) => {
    this.press(pr, 'release');
  };

  dismiss = (pr: WallRow, forever: boolean) => {
    this.confirming = null;
    void this.controls.dismiss(this.controls.ofRow(pr), forever);
  };

  private press(pr: WallRow, control: Control): boolean {
    const next = this.controls.press(this.controls.ofRow(pr), control);
    if (next === 'confirm-dismiss') this.confirming = keyOf(pr);
    return next !== 'nothing';
  }

  cancel = () => {
    this.confirming = null;
  };

  private move(by: number): void {
    const order = this.order;
    const chosen = this.chosen;
    const next = stepped(order, chosen ? order.indexOf(chosen) : -1, by);
    if (next) this.hub.selected = keyOf(next);
  }

  private takes(key: string): boolean {
    const pr = this.chosen;
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
    <main id="wall" data-test-wall>
      <HubBar @on="wall" />
      <div class="wall-head" aria-hidden="true">
        {{#each HEADS key="label" as |head|}}<span
            class={{if head.right "r"}}
            title={{head.hint}}
            data-test-wall-head
          >{{head.label}}</span>{{/each}}
      </div>
      <div
        class="wall-body {{if this.stale 'stale'}}"
        data-test-wall-stale={{this.stale}}
        {{moves}}
        {{selects this.hub.selected}}
      >
        {{#each this.hub.sections key="group" as |section|}}
          <h2
            class="group-head wall-group lvl-{{section.level}}-h"
            data-flip-key="head:{{section.group}}"
            data-test-wall-group={{section.group}}
          ><span class="group-name">{{section.name}}</span>
            <span
              class="group-count"
              data-test-count
            >{{section.prs.length}}</span></h2>
          {{#each section.prs key="key" as |pr|}}
            {{#let (this.readingOf pr) as |reading|}}
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
                  data-test-wall-lead
                  {{on "click" (fn this.open pr)}}
                >
                  <span class="verb" data-test-verb>{{#if reading.working}}<span
                        class="live-dot"
                        {{pulses reading.move}}
                      ></span>{{/if}}{{reading.move}}{{#each
                      reading.flags key="code"
                      as |flag|
                    }}<MoveFlagTag @flag={{flag}} />{{/each}}{{#if
                      reading.detailedReviewer
                    }}<span
                        class="flag"
                        title={{reading.detailedReviewer.hint}}
                        data-test-flag
                      >{{reading.detailedReviewer.text}}</span>{{/if}}{{#if
                      pr.moved
                    }}<span class="moved" data-test-moved>moved here</span>{{/if}}</span>
                  <span
                    class="ttl"
                    data-test-wall-title
                  >{{reading.title}}</span>
                  <span class="meta">#{{pr.number}}{{#if reading.whose}}
                      ·
                      {{reading.whose}}{{/if}}{{#if reading.branch}}
                      ·
                      <span class="mono">{{reading.branch}}</span>{{/if}}</span>
                </button>
                <span class="why"><span
                    data-test-cell="why"
                  >{{reading.why}}</span>{{#if (this.releasable pr)}}<button
                      type="button"
                      class="release"
                      data-test-release
                      title="let go of the worktree on the wrong branch; the watcher keeps it aside and cuts a fresh one"
                      {{on "click" (fn this.release pr)}}
                    >Release</button>{{/if}}</span>
                <span class="cells">
                  {{#each reading.cells key="key" as |one|}}
                    <span
                      class="cell tone-{{one.tone}} {{if one.count 'r'}}"
                      data-test-cell={{one.key}}
                      data-label={{one.label}}
                    >{{#if one.live}}<span
                          class="live-dot"
                          {{pulses reading.move}}
                        ></span>{{/if}}{{#if (eq one.tone "alarm")}}<i
                          class="sq alarm"
                          data-test-alarm
                        ></i>{{/if}}{{one.text}}</span>
                  {{/each}}
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
