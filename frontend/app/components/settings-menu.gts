import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import type HarvestSwitchService from 'frontend/services/harvest-switch';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type ThemeService from 'frontend/services/theme';

const TOOTH_RADIUS = 5.75;
const TEETH = 8;
const TOOTH = (Math.PI * TOOTH_RADIUS) / TEETH;

export default class SettingsMenu extends Component {
  @service declare harvestSwitch: HarvestSwitchService;
  @service declare hub: HubService;
  @service declare keys: KeysService;
  @service declare theme: ThemeService;

  @tracked showing = false;

  readonly tooth = `${TOOTH} ${TOOTH}`;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key === 'Escape') this.close();
      return true;
    },
  };

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  open = () => {
    this.showing = true;
    this.keys.push('dialog', this.keymap);
  };

  close = () => {
    this.showing = false;
    this.keys.drop(this.keymap);
  };

  flip = () => this.theme.toggle();

  flipHarvest = () => this.harvestSwitch.toggle();

  get harvestLabel(): string {
    return `Harvest timer: ${this.harvestSwitch.on ? 'on' : 'off'}`;
  }

  <template>
    <span class="settings">
      <button
        type="button"
        class="settings-pick"
        aria-label="Settings"
        title="Settings"
        aria-haspopup="true"
        aria-expanded={{if this.showing "true" "false"}}
        data-test-settings-open
        {{on "click" this.open}}
      ><svg
          class="gear"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentcolor"
          stroke-width="2"
          aria-hidden="true"
          focusable="false"
        ><circle cx="8" cy="8" r="3.75" /><circle
            cx="8"
            cy="8"
            r={{TOOTH_RADIUS}}
            stroke-dasharray={{this.tooth}}
          /></svg></button>
      {{#if this.showing}}
        <button
          type="button"
          class="settings-scrim"
          tabindex="-1"
          aria-label="close the settings"
          {{on "click" this.close}}
        ></button>
        <div class="settings-menu" data-test-settings-menu>
          <button
            type="button"
            class="setting"
            data-test-setting
            data-test-theme-toggle
            {{on "click" this.flip}}
          >{{if this.theme.dark "Light theme" "Dark theme"}}</button>
          <button
            type="button"
            class="setting"
            data-test-setting
            data-test-harvest-toggle
            {{on "click" this.flipHarvest}}
          >{{this.harvestLabel}}</button>
          {{#if this.hub.pollStatus}}
            <span
              class="settings-health tone-{{this.hub.pollStatus.tone}}"
              title={{this.hub.poll.text}}
              data-test-pr-health
              data-test-health-tone={{this.hub.pollStatus.tone}}
              data-test-health-alarm={{this.hub.poll.alarm}}
            ><i class="status-dot"></i><span
                class="headline"
              >{{this.hub.pollStatus.headline}}</span>
              {{#if this.hub.pollStatus.when}}<span
                  class="when"
                >{{this.hub.pollStatus.when}}</span>{{/if}}</span>
          {{/if}}
        </div>
      {{/if}}
    </span>
  </template>
}
