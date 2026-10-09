import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { pulses } from 'frontend/motion';
import { fn } from '@ember/helper';
import MoveFlagTag from 'frontend/components/move-flag';
import { dashboardOf, type Reading } from 'frontend/data/dashboard';
import { keyOf, type Numbered } from 'frontend/data/wall';
import type HubService from 'frontend/services/hub';
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

  isCurrent = (pr: WallRow): boolean => keyOf(pr) === keyOf(this.args.current);

  readingOf = (pr: WallRow): Reading =>
    dashboardOf(pr, pr.summaries, this.hub.now);

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
                      ></span>{{/if}}{{reading.move}}{{#each
                      reading.flags key="code"
                      as |flag|
                    }}<MoveFlagTag @flag={{flag}} />{{/each}}</span><span
                    class="ttl"
                  >#{{pr.number}} {{reading.title}}</span></span></button>
            {{/let}}
          {{/each}}
        {{/each}}
      </div>
    </aside>
  </template>
}
