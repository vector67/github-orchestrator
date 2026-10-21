import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import modal from 'frontend/modifiers/modal';
import type HarvestSwitchService from 'frontend/services/harvest-switch';
import type StoreService from 'frontend/services/store';

export default class HarvestSetup extends Component {
  @service declare harvestSwitch: HarvestSwitchService;
  @service declare store: StoreService;

  @tracked folder: string | null = null;
  @tracked refused: string | null = null;

  prepare = async () => {
    const prepared = await this.store.prepareHarvestExtension();
    if (typeof prepared === 'string') {
      this.refused = prepared;
      return;
    }
    this.refused = null;
    this.folder = prepared.folder;
  };

  close = () => this.harvestSwitch.doneSettingUp();

  <template>
    <div class="decide-dialog">
      <form
        class="harvest-setup"
        role="dialog"
        aria-modal="true"
        aria-labelledby="harvest-setup-question"
        tabindex="-1"
        data-test-harvest-setup
        {{modal this.close}}
      >
        <header class="dialog-head">
          <p class="question" id="harvest-setup-question">Set up Harvest on the
            board</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            data-test-harvest-setup-close
            {{on "click" this.close}}
          >×</button>
        </header>
        {{#if this.folder}}
          <p class="note">The board's copy of the Harvest extension is in
            <code data-test-harvest-folder>{{this.folder}}</code>, and its path
            is on your clipboard.</p>
          <ol class="harvest-steps" data-test-harvest-steps>
            <li>In the chrome://extensions tab that just opened, turn on
              Developer mode.</li>
            <li>Click Load unpacked, press ⌘⇧G, paste the path and choose the
              folder. Or drag the folder from Finder onto the page.</li>
            <li>Turn off the Chrome Web Store's Harvest Time Tracker, then
              reload this page.</li>
          </ol>
        {{else}}
          <p class="note">The Harvest extension puts its timer beside the gear
            once Chrome loads a copy of it that knows this board.</p>
          {{#if this.refused}}
            <p class="note refused">{{this.refused}}</p>
          {{/if}}
          <div class="dialog-actions">
            <button
              type="button"
              class="primary"
              data-test-harvest-prepare
              {{on "click" this.prepare}}
            >Set up the extension</button>
            <button type="button" class="ghost" {{on "click" this.close}}>Not
              now
              <kbd>Esc</kbd></button>
          </div>
        {{/if}}
      </form>
    </div>
  </template>
}
