import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { pulses } from 'frontend/motion';
import { LinkTo } from '@ember/routing';
import type Owner from '@ember/owner';
import type RouterService from '@ember/routing/router-service';
import RebaseButton from 'frontend/components/rebase-button';
import Switcher from 'frontend/components/switcher';
import {
  countsOf,
  dashboardOf,
  threadsWaitingOf,
  type Chip,
  type Reading,
} from 'frontend/data/dashboard';
import StateChip from 'frontend/components/state-chip';
import { copyAddress, openOnGitHub } from 'frontend/data/address';
import { failingOf, keyOf, pageOf, type Numbered } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import { stepped, type Keymap } from 'frontend/services/keys';
import type DashboardService from 'frontend/services/dashboard';
import type StoreService from 'frontend/services/store';
import type { ShownPr, Summaries, WallRow } from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';
import type ThreadsService from 'frontend/services/threads';
import type ToastsService from 'frontend/services/toasts';

const BOARD_TAB = /^(conversations|board)(\.|$)/;

export interface PrViewSignature {
  Args: { pr: Numbered };
  Blocks: { default: [] };
}

const SWITCHER_KEY = '\\';

export default class PrView extends Component<PrViewSignature> {
  @service declare hub: HubService;
  @service declare dashboard: DashboardService;
  @service declare threads: ThreadsService;
  @service declare store: StoreService;
  @service declare router: RouterService;
  @service declare keys: KeysService;
  @service declare theme: ThemeService;
  @service declare toasts: ToastsService;

  @tracked switching = false;

  private readonly keymap: Keymap = {
    take: (key) => this.switcherTakes(key),
    otherwise: (key) => this.takes(key),
  };

  constructor(owner: Owner, args: PrViewSignature['Args']) {
    super(owner, args);
    this.keys.push('screen', this.keymap);
  }

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  get shown(): ShownPr | null {
    return this.dashboard.shown;
  }

  get reading(): Reading | null {
    const { shown, summaries } = this;
    return shown && summaries
      ? dashboardOf(
          shown,
          summaries,
          this.hub.now,
          failingOf(shown, this.store.ledger?.runs ?? []),
        )
      : null;
  }

  get title(): string {
    const reading = this.reading;
    const title = reading?.titleKnown
      ? reading.title
      : (this.threads.pullRequest?.title ?? '');
    return `#${this.args.pr.number} ${title}`.trim();
  }

  get url(): string | null {
    return this.threads.pullRequest?.url ?? null;
  }

  get repo(): string {
    return this.args.pr.repo;
  }

  get summaries(): Summaries | null {
    return this.store.summary(this.repo, this.args.pr.number);
  }

  get counts(): string[] {
    const summaries = this.summaries;
    return summaries ? countsOf(summaries) : [];
  }

  get threadsWaiting(): string | null {
    const summaries = this.summaries;
    return summaries ? threadsWaitingOf(summaries) : null;
  }

  get moveTone(): string {
    return this.reading?.square ?? 'wait';
  }

  get barChips(): Chip[] {
    return (this.reading?.chips ?? []).filter((chip) => chip.key !== 'draft');
  }

  get needs(): string {
    const count = this.store.needYou;
    return `${count} ${count === 1 ? 'needs' : 'need'} you`;
  }

  get onSummaryTab(): boolean {
    return this.router.currentRouteName === 'summary';
  }

  get onBoardTab(): boolean {
    return BOARD_TAB.test(this.router.currentRouteName ?? '');
  }

  get onDashboardTab(): boolean {
    return this.router.currentRouteName === 'dashboard';
  }

  get onTerminalTab(): boolean {
    return this.router.currentRouteName === 'terminal';
  }

  get onDiffTab(): boolean {
    return this.router.currentRouteName === 'pr.diff';
  }

  get order(): WallRow[] {
    return this.hub.sections.flatMap((section) => section.prs);
  }

  openSwitcher = () => {
    this.switching = true;
  };

  closeSwitcher = () => {
    this.switching = false;
  };

  pick = (pr: WallRow) => {
    this.switching = false;
    void this.router.transitionTo(pageOf(pr));
  };

  flip = () => this.theme.toggle();

  private step(by: number): void {
    const order = this.order;
    const here = keyOf(this.args.pr);
    const at = order.findIndex((pr) => keyOf(pr) === here);
    const next = stepped(order, at, by);
    if (next && keyOf(next) !== here) this.pick(next);
  }

  private switcherTakes(key: string): boolean {
    if (!this.switching) return false;
    if (key === 'Escape' || key === SWITCHER_KEY) this.closeSwitcher();
    else if (key === '[' || key === ']') this.step(key === ']' ? 1 : -1);
    return true;
  }

  private takes(key: string): boolean {
    if (key === '1') {
      if (!this.onSummaryTab) void this.router.transitionTo('summary');
    } else if (key === '2') {
      if (!this.onBoardTab) void this.router.transitionTo('conversations');
    } else if (key === '3') {
      if (!this.onDashboardTab) void this.router.transitionTo('dashboard');
    } else if (key === '4') {
      if (!this.onTerminalTab) void this.router.transitionTo('terminal');
    } else if (key === '5') {
      if (!this.onDiffTab) void this.router.transitionTo('pr.diff');
    } else if (key === 'o') {
      openOnGitHub(this.url);
    } else if (key === 'y') {
      void this.copy();
    } else if (key === 'Escape') {
      void this.router.transitionTo('index');
    } else if (key === SWITCHER_KEY) {
      this.openSwitcher();
    } else if (key === '[' || key === ']') {
      this.step(key === ']' ? 1 : -1);
    } else {
      return false;
    }
    return true;
  }

  get notHeld(): boolean {
    return this.store.notHeld(this.repo, this.args.pr.number);
  }

  private async copy(): Promise<void> {
    this.toasts.say(await copyAddress(this.url), 'done');
  }

  <template>
    <div id="pr-view" data-test-pr-view>
      <header class="titlebar" data-top-bar data-test-title-bar>
        <button
          type="button"
          class="switch-btn"
          data-test-switcher-open
          {{on "click" this.openSwitcher}}
        ><span class="burger"></span>PRs
          <span class="n">{{this.needs}}</span>
          <kbd>\</kbd></button>
        {{#if this.hub.poll}}
          <span
            class="pr-health"
            title={{this.hub.poll.text}}
            aria-label={{this.hub.poll.text}}
            data-test-pr-health
            data-test-health-alarm={{this.hub.poll.alarm}}
          ><i class="sq {{if this.hub.poll.alarm 'alarm'}}"></i></span>
        {{/if}}
        <LinkTo @route="index" class="linkish" data-test-wall-link>Wall
          <kbd>Esc</kbd></LinkTo>
        <div class="prtitle" data-test-pr-heading>
          <span class="tline">{{#if this.reading.draft}}<span
                class="draft-pill"
                data-test-draft-pill
              >Draft</span>{{/if}}<span
              class="t"
              data-test-pr-title
            >{{this.title}}</span></span>
          <span class="m">{{#if this.reading.whose}}{{this.reading.whose}}
              ·
            {{/if}}{{#if this.reading.branch}}{{this.reading.branch}}
              ·
            {{/if}}<a
              data-test-repo
              href={{this.url}}
              target="_blank"
              rel="noopener noreferrer"
            >{{this.repo}}#{{@pr.number}}</a></span>
        </div>
        {{#if this.reading}}
          <div
            class="move tone-{{this.moveTone}}"
            data-muted={{if this.reading.muted "true"}}
            data-move={{this.reading.code}}
            data-test-your-move
          >
            <span class="lab" data-test-move-label>{{if
                this.reading.muted
                "Next, when it’s ready"
                "Next"
              }}</span>
            {{#if this.reading.rebaseIsNext}}
              <RebaseButton />
            {{else}}
              <span class="vb" title={{this.reading.move}}>{{#if
                  this.reading.working
                }}<span
                    class="live-dot"
                    {{pulses this.reading.move}}
                  ></span>{{/if}}{{this.reading.move}}</span>
            {{/if}}
          </div>
        {{/if}}
        <span class="grow"></span>
        <span class="prflags">
          {{#if this.counts.length}}
            <span class="prcounts">
              {{#each this.counts key="@index" as |count|}}
                <span data-test-pr-count>{{count}}</span>
              {{/each}}
            </span>
          {{/if}}
          {{#if this.barChips.length}}
            <span class="state-chips">
              {{#each this.barChips key="key" as |chip|}}
                <StateChip @chip={{chip}} />
              {{/each}}
            </span>
          {{/if}}
        </span>
        {{#if this.url}}
          <a
            class="linkish"
            href={{this.url}}
            target="_blank"
            rel="noopener noreferrer"
            data-test-github
          >GitHub <kbd>o</kbd></a>
        {{/if}}
        {{#if this.hub.fontProblem}}
          <span
            class="font-problem"
            title={{this.hub.fontProblem}}
            data-test-font-problem
          >Board font missing</span>
        {{/if}}
        <button
          type="button"
          class="theme-toggle btn"
          data-test-theme-toggle
          {{on "click" this.flip}}
        >{{if this.theme.dark "Light theme" "Dark theme"}}</button>
      </header>
      {{#if this.notHeld}}
        <section id="not-found" data-test-pr-not-found>
          <h1>Pull request not found</h1>
          <p>The watcher holds no pull request
            {{this.repo}}#{{@pr.number}}. It only watches pull requests you
            wrote or were asked to review.
            <a class="not-found-link" href="/">Back to the board</a>.</p>
        </section>
      {{else}}
        <nav class="prtabs" aria-label="this pull request">
          <LinkTo
            @route="summary"
            class="tab"
            aria-current={{if this.onSummaryTab "page"}}
            data-test-tab="summary"
          >Summary
            <kbd>1</kbd></LinkTo>
          <LinkTo
            @route="conversations"
            class="tab"
            aria-current={{if this.onBoardTab "page"}}
            data-test-tab="board"
          >Board
            {{#if this.threadsWaiting}}<span
                class="count"
                data-test-tab-count
              >{{this.threadsWaiting}}</span>{{/if}}
            <kbd>2</kbd></LinkTo>
          <LinkTo
            @route="dashboard"
            class="tab"
            aria-current={{if this.onDashboardTab "page"}}
            data-test-tab="dashboard"
          >Dashboard
            {{#if this.reading.working}}<span
                class="live-dot"
                {{pulses this.reading.move}}
              ></span>{{/if}}
            <kbd>3</kbd></LinkTo>
          <LinkTo
            @route="terminal"
            class="tab"
            aria-current={{if this.onTerminalTab "page"}}
            data-test-tab="terminal"
          >Terminal
            <kbd>4</kbd></LinkTo>
          <LinkTo
            @route="pr.diff"
            class="tab"
            aria-current={{if this.onDiffTab "page"}}
            data-test-tab="diff"
          >Diff
            <kbd>5</kbd></LinkTo>
        </nav>
        <div class="pane">
          {{yield}}
        </div>
      {{/if}}
      <Switcher
        @open={{this.switching}}
        @current={{@pr}}
        @pick={{this.pick}}
        @close={{this.closeSwitcher}}
      />
    </div>
  </template>
}
