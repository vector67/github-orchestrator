import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { waitForPromise } from '@ember/test-waiters';
import { pulses } from 'frontend/motion';
import { exitWordOf, lengthOf, relativeOf } from 'frontend/data/dashboard';
import { markdownOf } from 'frontend/data/markdown';
import drawn from 'frontend/modifiers/drawn';
import type HereService from 'frontend/services/here';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type { SummaryTab as Tab } from 'frontend/services/store';

function is(one: string, other: string): boolean {
  return one === other;
}

function commits(count: number | null): string {
  return count === 1 ? '1 commit' : `${count} commits`;
}

export default class SummaryTab extends Component {
  @service declare here: HereService;
  @service declare hub: HubService;
  @service declare store: StoreService;

  @tracked said: string | null = null;

  get tab(): Tab | null {
    const { repo, number } = this.here.at;
    return this.store.prSummary(repo, number);
  }

  get finished(): string {
    return relativeOf(this.tab?.finished ?? null, this.hub.now);
  }

  get started(): string {
    return relativeOf(this.tab?.since ?? null, this.hub.now);
  }

  get elapsed(): string {
    const since = Date.parse(this.tab?.since ?? '');
    return Number.isNaN(since) ? '' : lengthOf((this.hub.now - since) / 1000);
  }

  get githubApi(): string {
    const calls = this.tab?.calls;
    return calls
      ? `Use the GitHub API (about ${calls} calls)`
      : 'Use the GitHub API';
  }

  run = (): void => {
    this.said = null;
    void waitForPromise(this.ask(this.store.summarise(this.here.at)));
  };

  runWithGithubApi = (): void => {
    this.said = null;
    void waitForPromise(
      this.ask(this.store.summariseWithGithubApi(this.here.at)),
    );
  };

  private async ask(asking: Promise<string | null>): Promise<void> {
    this.said = await asking;
  }

  <template>
    {{#if this.tab}}
      <div id="summary-tab" data-test-summary-tab>
        <div
          class="summary-strip"
          data-state={{this.tab.state}}
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
              {{on "click" this.run}}
            >Summarise</button>
          {{else if (is this.tab.state "running")}}
            {{#if this.tab.markdown}}
              <span><code>{{this.tab.sha}}</code>
                · finished
                {{this.finished}}</span>
              <span class="rerun" data-test-summary-rerun>rerun started
                {{this.started}}, finished
                {{this.tab.witnessesDone}}/{{this.tab.witnessCount}}
                witnesses</span>
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
              {{on "click" this.runWithGithubApi}}
            >{{this.githubApi}}</button>
          {{else if (is this.tab.state "failed")}}
            <span>{{exitWordOf this.tab.exitStatus}}
              ·
              {{this.tab.reason}}</span>
            <button
              type="button"
              class="btn"
              data-test-summary-run
              {{on "click" this.run}}
            >Rerun</button>
          {{else if (is this.tab.state "stale")}}
            <span>Written for
              <code>{{this.tab.sha}}</code>, head is
              <code>{{this.tab.head}}</code>{{#if this.tab.behind}},
                {{commits this.tab.behind}}
                behind{{/if}}</span>
            <button
              type="button"
              class="btn"
              data-test-summary-run
              {{on "click" this.run}}
            >Rerun</button>
          {{else}}
            <span><code>{{this.tab.sha}}</code>
              · finished
              {{this.finished}}</span>
            <button
              type="button"
              class="btn"
              data-test-summary-run
              {{on "click" this.run}}
            >Rerun</button>
          {{/if}}
          {{#if this.said}}
            <span class="said" data-test-summary-said>{{this.said}}</span>
          {{/if}}
        </div>
        {{#if this.tab.markdown}}
          <div
            class="summary-body comment-body"
            data-test-summary-markdown
            {{drawn markdownOf this.tab.markdown}}
          ></div>
        {{/if}}
      </div>
    {{/if}}
  </template>
}
