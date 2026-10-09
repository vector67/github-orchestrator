import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import { LinkTo } from '@ember/routing';
import { todayOf, type Said } from 'frontend/data/runs';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';

interface HubBarSignature {
  Args: { on: 'wall' | 'runs' | 'setup' };
}

const eq = (one: string, other: string): boolean => one === other;

export default class HubBar extends Component<HubBarSignature> {
  @service declare hub: HubService;
  @service declare store: StoreService;
  @service declare theme: ThemeService;
  @service declare keys: KeysService;

  @tracked picking = false;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key === 'Escape') this.closePicker();
      return true;
    },
  };

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get chosenLabel(): string {
    const { chosen, watching } = this.store;
    if (!chosen) return watching.length === 1 ? watching[0]! : 'All repos';
    return chosen.length === 1 ? chosen[0]! : `${chosen.length} repos`;
  }

  isChosen = (repo: string): boolean =>
    (this.store.chosen ?? this.store.watching).includes(repo);

  openPicker = () => {
    this.picking = true;
    this.keys.push('dialog', this.keymap);
  };

  closePicker = () => {
    this.picking = false;
    this.keys.drop(this.keymap);
  };

  only = (repo: string) => {
    this.closePicker();
    this.store.choose([repo]);
  };

  all = () => {
    this.closePicker();
    this.store.choose(null);
  };

  toggle = (repo: string) => {
    const was = this.store.chosen ?? this.store.watching;
    this.store.choose(
      was.includes(repo) ? was.filter((one) => one !== repo) : [...was, repo],
    );
  };

  get poll(): Said | null {
    return this.hub.poll;
  }

  get today(): string | null {
    const ledger = this.store.ledger;
    return ledger ? todayOf(ledger.today) : null;
  }

  flip = () => this.theme.toggle();

  <template>
    <header class="wall-bar">
      <span class="wall-name">Orchestrator</span>
      <nav class="hub-nav">
        <LinkTo
          @route="index"
          data-test-nav="wall"
          aria-current={{if (eq @on "wall") "page"}}
        >Wall</LinkTo>
        <LinkTo
          @route="runs"
          data-test-nav="runs"
          aria-current={{if (eq @on "runs") "page"}}
        >Runs</LinkTo>
        <LinkTo
          @route="setup"
          data-test-nav="setup"
          aria-current={{if (eq @on "setup") "page"}}
        >Setup</LinkTo>
      </nav>
      <span class="repo-filter">
        <button
          type="button"
          class="repo-pick"
          aria-haspopup="true"
          aria-expanded={{if this.picking "true" "false"}}
          title="show the pull requests of some repos only"
          data-test-repo-filter
          {{on "click" this.openPicker}}
        >{{this.chosenLabel}}</button>
        {{#if this.picking}}
          <button
            type="button"
            class="repo-scrim"
            tabindex="-1"
            aria-label="close the repo filter"
            {{on "click" this.closePicker}}
          ></button>
          <div class="repo-menu" data-test-repo-menu>
            <button
              type="button"
              class="repo-all"
              aria-pressed={{if this.store.chosen "false" "true"}}
              data-test-repo-all
              {{on "click" this.all}}
            >All repos</button>
            {{#each this.store.watching key="@identity" as |repo|}}
              <span class="repo-choice" data-test-repo-choice={{repo}}>
                <input
                  type="checkbox"
                  class="checkbox"
                  checked={{this.isChosen repo}}
                  aria-label="show {{repo}}"
                  {{on "change" (fn this.toggle repo)}}
                />
                <button
                  type="button"
                  class="repo-only"
                  title="show {{repo}} only"
                  data-test-repo-only
                  data-test-watching
                  {{on "click" (fn this.only repo)}}
                >{{repo}}</button>
              </span>
            {{/each}}
          </div>
        {{/if}}
      </span>
      <span class="grow"></span>
      <span class="health">
        {{#if this.poll}}
          <span
            class="health-poll {{if this.poll.alarm 'alarm-t'}}"
            title={{this.poll.text}}
            data-test-health="poll"
            data-test-health-alarm={{this.poll.alarm}}
          >{{#if this.poll.alarm}}<i
                class="sq alarm"
              ></i>{{/if}}{{this.poll.text}}</span>
        {{/if}}
        {{#if this.today}}
          <span data-test-health="today">{{this.today}}</span>
        {{/if}}
      </span>
      {{#if this.hub.fontProblem}}
        <span
          class="font-problem"
          title={{this.hub.fontProblem}}
          data-test-font-problem
        >Board font missing</span>
      {{/if}}
      {{#if this.hub.update}}
        <span
          class="update-available"
          title="github-orchestrator {{this.hub.update.version}} is out. Run github-orchestrator update to install it."
          data-test-update-available
        >Update available</span>
      {{/if}}
      <button
        type="button"
        class="theme-toggle btn"
        data-test-theme-toggle
        aria-pressed={{if this.theme.dark "true" "false"}}
        {{on "click" this.flip}}
      >Dark theme</button>
    </header>
  </template>
}
