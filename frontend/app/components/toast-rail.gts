import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import type KeysService from 'frontend/services/keys';
import type ReachabilityService from 'frontend/services/reachability';
import type ToastsService from 'frontend/services/toasts';
import modal from 'frontend/modifiers/modal';
import { SHORTCUTS } from 'frontend/data/shortcuts';
import { moves } from 'frontend/motion';

export default class ToastRail extends Component {
  @service declare toasts: ToastsService;
  @service declare keys: KeysService;
  @service declare reachability: ReachabilityService;

  closeHelp = () => {
    this.keys.helping = false;
  };

  <template>
    {{#if this.reachability.banner}}
      <div id="error-banner" role="alert" data-test-banner>
        <span>{{this.reachability.banner}}</span>
      </div>
    {{/if}}
    {{#if this.keys.helping}}
      <div id="key-help">
        <section
          role="dialog"
          aria-modal="true"
          aria-labelledby="key-help-title"
          tabindex="-1"
          data-test-key-help
          {{modal this.closeHelp}}
        >
          <header class="key-help-head">
            <h2 class="key-help-title" id="key-help-title">Keyboard shortcuts</h2>
            <button
              type="button"
              class="key-help-close"
              aria-label="close"
              {{on "click" this.closeHelp}}
            >×</button>
          </header>
          <div class="key-groups">
            {{#each SHORTCUTS key="screen" as |group|}}
              <div class="key-group" data-test-key-group={{group.screen}}>
                <h3 class="key-group-title">{{group.screen}}</h3>
                <dl class="key-list">
                  {{#each group.shortcuts key="does" as |shortcut|}}
                    <dt class="key-keys">{{#each
                        shortcut.keys key="@index"
                        as |key|
                      }}<kbd>{{key}}</kbd>{{/each}}</dt>
                    <dd class="key-does">{{shortcut.does}}</dd>
                  {{/each}}
                </dl>
              </div>
            {{/each}}
          </div>
        </section>
      </div>
    {{/if}}
    <div id="toasts" aria-live="polite" {{moves}}>
      {{#each this.toasts.bars key="id" as |bar|}}
        <button
          type="button"
          class="toast"
          data-flip-key="toast:{{bar.id}}"
          data-leaving={{if bar.leaving "true"}}
          data-test-toast
          {{on "click" (fn this.toasts.drop bar.id)}}
        ><span
            class="square"
            data-test-square
            data-square={{bar.square}}
          ></span>{{bar.text}}</button>
      {{/each}}
    </div>
  </template>
}
