import Component from '@glimmer/component';
import { service } from '@ember/service';
import { hash } from '@ember/helper';
import { LinkTo } from '@ember/routing';
import HubBar from 'frontend/components/hub-bar';
import type { FinishedRun } from 'frontend/data/api';
import { factsOf, rowsOf, type Fact, type RunRow } from 'frontend/data/runs';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';

export default class RunsPage extends Component {
  @service declare hub: HubService;
  @service declare store: StoreService;

  get facts(): Fact[] {
    const { ledger, watcher, health } = this.store;
    return ledger && watcher
      ? factsOf(
          watcher,
          health?.state ?? null,
          ledger.today,
          ledger.runs,
          this.hub.now,
        )
      : [];
  }

  get rows(): RunRow[] {
    return rowsOf(this.store.ledger?.runs ?? [], this.hub.now);
  }

  <template>
    <main id="runs" data-test-runs>
      <HubBar @on="runs" />
      <dl class="runs-watcher">
        {{#each this.facts key="label" as |fact|}}
          <div
            class="runs-fact {{if fact.alarm 'failing'}}"
            data-test-watcher-fact
          ><dt>{{fact.label}}</dt>
            <dd>{{#if fact.alarm}}<i
                  class="sq alarm"
                ></i>{{/if}}{{fact.text}}</dd></div>
        {{/each}}
      </dl>
      <div class="runs-head" aria-hidden="true">
        <span></span><span>Ended</span><span>PR</span><span>Event</span><span
          class="r"
        >Took</span><span>Exit</span><span class="r">Cost</span>
      </div>
      <div class="runs-body">
        {{#each this.rows key="@index" as |row|}}
          <div
            class="runs-row {{if row.run.failed 'failing'}}"
            data-test-run
            data-test-failed={{row.run.failed}}
          >
            <i class="sq {{if row.run.failed 'alarm'}}"></i>
            {{#each row.cells key="key" as |cell|}}
              {{#if (isPr cell.key)}}
                <span class="cell" data-test-run-cell={{cell.key}}>{{#if
                    row.run.number
                  }}{{#if row.run.board_url}}<LinkTo
                        @route="dashboard"
                        @models={{modelsOf row.run}}
                        @query={{hash pane="agent"}}
                        title="open this pull request's dashboard on the agent's output"
                        data-test-run-open
                      >{{cell.text}}</LinkTo>{{else}}{{cell.text}}{{/if}}{{else}}{{cell.text}}{{/if}}</span>
              {{else}}
                <span
                  class="cell {{if (isCount cell.key) 'r'}}"
                  data-test-run-cell={{cell.key}}
                >{{cell.text}}</span>
              {{/if}}
            {{/each}}
          </div>
        {{else}}
          <p class="wall-empty" data-test-runs-empty>
            No agent run ended in the last seven days.
          </p>
        {{/each}}
      </div>
    </main>
  </template>
}

function modelsOf(run: FinishedRun): string[] {
  return [...(run.repo ?? '').split('/'), String(run.number)];
}

function isPr(key: string): boolean {
  return key === 'pr';
}

function isCount(key: string): boolean {
  return key === 'took' || key === 'cost';
}
