import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { waitForPromise } from '@ember/test-waiters';
import { pulses } from 'frontend/motion';
import { elapsedOf, exitWordOf, relativeOf } from 'frontend/data/dashboard';
import type { Pressing } from 'frontend/data/decisions';
import { summaryOf } from 'frontend/data/markdown';
import diagrams from 'frontend/modifiers/diagrams';
import drawn from 'frontend/modifiers/drawn';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type ThemeService from 'frontend/services/theme';
import type { PrHeader, SummaryTab as Tab } from 'frontend/services/store';

function is(one: string, other: string): boolean {
  return one === other;
}

export default class SummaryTab extends Component {
  @service declare here: HereService;
  @service declare hub: HubService;
  @service declare store: StoreService;
  @service declare theme: ThemeService;

  get tab(): Tab | null {
    const { repo, number } = this.here.at;
    return this.store.prSummary(repo, number);
  }

  get header(): PrHeader | null {
    const { repo, number } = this.here.at;
    return this.store.prHeader(repo, number);
  }

  get opened(): string {
    return relativeOf(this.header?.createdAt ?? null, this.hub.now);
  }

  get finished(): string {
    return relativeOf(this.tab?.finished ?? null, this.hub.now);
  }

  get started(): string {
    return relativeOf(this.tab?.since ?? null, this.hub.now);
  }

  get elapsed(): string {
    return elapsedOf(this.tab?.since ?? null, this.hub.now);
  }

  get pressing(): Pressing | null {
    const { repo, number } = this.here.at;
    return this.store.summary(repo, number)?.pressing.summary ?? null;
  }

  get githubApi(): string {
    const calls = this.tab?.calls;
    return calls
      ? `Use the GitHub API (about ${calls} calls)`
      : 'Use the GitHub API';
  }

  run = (): void => {
    void waitForPromise(this.store.summarise(this.here.at, 'summarise'));
  };

  runWithGithubApi = (): void => {
    void waitForPromise(
      this.store.summarise(this.here.at, 'summarise-with-github-api'),
    );
  };

  <template>
    <div id="summary-tab" data-test-summary-tab>
      {{#if this.header}}
        <header class="summary-pr" data-test-summary-pr>
          <h2 class="summary-pr-title" data-test-summary-title>
            {{this.header.title}}
          </h2>
          <div class="summary-pr-facts">
            {{#if this.header.createdAt}}
              <span
                title={{this.header.createdAt}}
                data-test-summary-opened
              >opened {{this.opened}}</span>
            {{/if}}
            {{#if this.header.commits}}
              <span data-test-summary-commits>{{this.header.commits}}</span>
            {{/if}}
            <span class="diffstat">
              <span
                class="diffstat-added"
                data-test-summary-additions
              >+{{this.header.additions}}</span>
              <span
                class="diffstat-deleted"
                data-test-summary-deletions
              >-{{this.header.deletions}}</span>
              <span class="diffstat-squares" aria-hidden="true">
                {{#each this.header.squares key="@index" as |square|}}
                  <span
                    class="diffstat-square"
                    data-kind={{square}}
                    data-test-diffstat-square={{square}}
                  ></span>
                {{/each}}
              </span>
            </span>
          </div>
        </header>
      {{/if}}
      {{#if this.tab}}
        <div
          class="summary-strip"
          data-state={{this.tab.state}}
          data-pending={{if this.pressing.pressed "true"}}
          data-test-summary-strip
        >
          {{#if (is this.tab.state "none-yet-reviewer")}}
            <span>Waiting for its turn</span>
          {{else if (is this.tab.state "none-yet-author")}}
            <span>No summary</span>
            <button
              type="button"
              class="btn"
              data-test-summary-run
              disabled={{if this.pressing.pressed true}}
              {{on "click" this.run}}
            >{{if
                this.pressing.pressed
                this.pressing.doing
                "Summarise"
              }}</button>
          {{else if (is this.tab.state "running")}}
            {{#if this.tab.markdown}}
              <span><code>{{this.tab.sha}}</code>
                · finished
                {{this.finished}}</span>
              <span class="rerun" data-test-summary-rerun>rerun started
                {{this.started}}, finished
                {{this.tab.witnessesDone}}/{{this.tab.witnessCount}}
                agents</span>
            {{else}}
              <span class="live-dot" {{pulses this.tab.since}}></span>
              <span><code>{{this.tab.head}}</code> · {{this.elapsed}}</span>
              <ol class="witnesses">
                {{#each this.tab.witnesses key="witness" as |one|}}
                  <li
                    data-done={{if one.done "true"}}
                    data-test-witness={{one.witness}}
                  >{{one.witness}}</li>
                {{/each}}
              </ol>
            {{/if}}
          {{else if (is this.tab.state "needs-github-api")}}
            <span>{{this.tab.reason}}</span>
            <button
              type="button"
              class="btn"
              data-test-summary-github-api
              disabled={{if this.pressing.pressed true}}
              {{on "click" this.runWithGithubApi}}
            >{{if
                this.pressing.pressed
                this.pressing.doing
                this.githubApi
              }}</button>
          {{else if (is this.tab.state "failed")}}
            <span>{{exitWordOf this.tab.exitStatus}}
              ·
              {{this.tab.reason}}</span>
            <span class="strip-end" data-test-summary-end>
              <button
                type="button"
                class="btn"
                data-test-summary-run
                disabled={{if this.pressing.pressed true}}
                {{on "click" this.run}}
              >{{if this.pressing.pressed this.pressing.doing "Rerun"}}</button>
            </span>
          {{else if (is this.tab.state "stale")}}
            <span>Written for
              <code>{{this.tab.sha}}</code>, head is
              <code>{{this.tab.head}}</code>{{#if this.tab.behind}},
                {{this.tab.behind}}{{/if}}</span>
            <span class="strip-end" data-test-summary-end>
              <span
                title={{this.tab.finished}}
                data-test-summary-finished
              >finished {{this.finished}}</span>
              <button
                type="button"
                class="btn"
                data-test-summary-run
                disabled={{if this.pressing.pressed true}}
                {{on "click" this.run}}
              >{{if this.pressing.pressed this.pressing.doing "Rerun"}}</button>
            </span>
          {{else}}
            <span><code>{{this.tab.sha}}</code></span>
            <span class="strip-end" data-test-summary-end>
              <span
                title={{this.tab.finished}}
                data-test-summary-finished
              >finished {{this.finished}}</span>
              <button
                type="button"
                class="btn"
                data-test-summary-run
                disabled={{if this.pressing.pressed true}}
                {{on "click" this.run}}
              >{{if this.pressing.pressed this.pressing.doing "Rerun"}}</button>
            </span>
          {{/if}}
          {{#if this.pressing.refused}}
            <span
              class="said"
              data-refused="true"
              data-test-summary-said
            >{{this.pressing.refused}}</span>
          {{/if}}
        </div>
        {{#if this.tab.markdown}}
          <div
            class="summary-body comment-body"
            data-test-summary-markdown
            {{drawn summaryOf this.tab.markdown}}
            {{diagrams this.tab.markdown this.theme.dark}}
          ></div>
        {{/if}}
      {{/if}}
    </div>
  </template>
}
