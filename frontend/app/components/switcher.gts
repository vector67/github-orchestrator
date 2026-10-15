import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { pulses } from 'frontend/motion';
import { fn } from '@ember/helper';
import StateChip from 'frontend/components/state-chip';
import { dashboardOf, type Reading } from 'frontend/data/dashboard';
import { failingOf, keyOf, type Numbered } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
import type StoreService from 'frontend/services/store';
import type { WallRow } from 'frontend/services/store';

export interface SwitcherSignature {
  Args: {
    open: boolean;
    current: Numbered;
    pick: (pr: WallRow) => void;
    close: () => void;
  };
}

export default class Switcher extends Component<SwitcherSignature> {
  @service declare hub: HubService;
  @service declare store: StoreService;

  isCurrent = (pr: WallRow): boolean => keyOf(pr) === keyOf(this.args.current);

  readingOf = (pr: WallRow): Reading =>
    dashboardOf(
      pr,
      pr.summaries,
      this.hub.now,
      failingOf(pr, this.store.ledger?.runs ?? []),
    );

  <template>
    <button
      type="button"
      class="switcher-scrim {{if @open 'on'}}"
      tabindex="-1"
      aria-label="close the switcher"
      {{on "click" @close}}
    ></button>
    <aside
      class="switcher {{if @open 'on'}}"
      aria-hidden={{if @open "false" "true"}}
      inert={{if @open false true}}
      aria-label="switch pull request"
      data-test-switcher
    >
      <div class="switcher-head"><b>Switch PR</b>
        <button type="button" class="linkish" {{on "click" @close}}>Close
          <kbd>Esc</kbd></button></div>
      <div class="switcher-list">
        {{#each this.hub.sections key="group" as |section|}}
          <div
            class="group-head switcher-group lvl-{{section.level}}-h"
            data-test-switcher-group
          ><span class="group-name">{{section.name}}</span>
            <span class="group-count">{{section.prs.length}}</span></div>
          {{#each section.prs key="key" as |pr|}}
            {{#let (this.readingOf pr) as |reading|}}
              <button
                type="button"
                class="switcher-row edge lvl-{{section.level}}"
                aria-current={{if (this.isCurrent pr) "true"}}
                data-square={{reading.edge}}
                data-test-switcher-row={{keyOf pr}}
                {{on "click" (fn @pick pr)}}
              ><span class="switcher-text"><span
                    class="verb"
                    data-test-verb
                  >{{#if reading.working}}<span
                        class="live-dot"
                        {{pulses reading.move}}
                      ></span>{{/if}}{{reading.move}}</span>{{#if
                    reading.chips.length
                  }}<span class="state-chips">{{#each
                        reading.chips key="key"
                        as |chip|
                      }}<StateChip @chip={{chip}} />{{/each}}</span>{{/if}}<span
                    class="ttl"
                  >{{#if this.store.severalReposShown}}<span
                        data-test-row-repo
                      >{{pr.repo}}</span>{{/if}}#{{pr.number}}
                    {{reading.title}}</span></span></button>
            {{/let}}
          {{/each}}
        {{/each}}
      </div>
    </aside>
  </template>
}
