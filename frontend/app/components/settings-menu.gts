import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import HarvestSetup from 'frontend/components/harvest-setup';
import {
  COMMIT_SIZINGS,
  type CommitSizing,
} from 'frontend/services/commit-box';
import type CommitBoxService from 'frontend/services/commit-box';
import type HarvestSwitchService from 'frontend/services/harvest-switch';
import type HubService from 'frontend/services/hub';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';
import type ThemeService from 'frontend/services/theme';
import {
  TERMINAL_THEMES,
  type TerminalTheme,
} from 'frontend/services/terminal';
import type TerminalService from 'frontend/services/terminal';

const TOOTH_RADIUS = 5.75;
const TEETH = 8;
const TOOTH = (Math.PI * TOOTH_RADIUS) / TEETH;

const SIZING_NAMES: Record<CommitSizing, string> = {
  full: 'Full',
  minimal: 'Minimal',
  hidden: 'Hidden',
};

const SIZINGS = COMMIT_SIZINGS.map((size) => ({
  size,
  name: SIZING_NAMES[size],
}));

const TERMINAL_THEME_NAMES: Record<TerminalTheme, string> = {
  system: 'System',
  light: 'Light',
  dark: 'Dark',
};

const TERMINAL_CHOICES = TERMINAL_THEMES.map((theme) => ({
  theme,
  name: TERMINAL_THEME_NAMES[theme],
}));

const eq = (one: unknown, other: unknown): boolean => one === other;

export default class SettingsMenu extends Component {
  @service declare harvestSwitch: HarvestSwitchService;
  @service declare hub: HubService;
  @service declare keys: KeysService;
  @service declare theme: ThemeService;
  @service declare commitBox: CommitBoxService;
  @service declare terminal: TerminalService;

  @tracked showing = false;
  @tracked sizing = false;
  @tracked terminalTheming = false;

  readonly tooth = `${TOOTH} ${TOOTH}`;

  private readonly keymap: Keymap = {
    take: (key) => {
      if (key !== 'Escape') return false;
      this.close();
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
    this.sizing = false;
    this.terminalTheming = false;
    this.keys.drop(this.keymap);
  };

  flip = () => this.theme.toggle();

  flipHarvest = () => this.harvestSwitch.toggle();

  openSizing = () => {
    this.sizing = !this.sizing;
  };

  size = (sizing: CommitSizing) => this.commitBox.choose(sizing);

  openTerminalTheming = () => {
    this.terminalTheming = !this.terminalTheming;
  };

  themeTerminal = (theme: TerminalTheme) => this.terminal.chooseTheme(theme);

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
          <button
            type="button"
            class="setting"
            aria-expanded={{if this.sizing "true" "false"}}
            data-test-setting
            data-test-commit-sizing-open
            {{on "click" this.openSizing}}
          >Commit box sizing</button>
          {{#if this.sizing}}
            <fieldset class="setting-choices" data-test-commit-sizings>
              <legend class="visually-hidden">Commit box sizing</legend>
              {{#each SIZINGS key="size" as |choice|}}
                <label class="setting-choice">
                  <input
                    type="radio"
                    name="commit-box-sizing"
                    value={{choice.size}}
                    checked={{eq this.commitBox.sizing choice.size}}
                    data-test-commit-sizing={{choice.size}}
                    {{on "change" (fn this.size choice.size)}}
                  />
                  {{choice.name}}
                </label>
              {{/each}}
            </fieldset>
          {{/if}}
          <button
            type="button"
            class="setting"
            aria-expanded={{if this.terminalTheming "true" "false"}}
            data-test-setting
            data-test-terminal-theme-open
            {{on "click" this.openTerminalTheming}}
          >Terminal colours</button>
          {{#if this.terminalTheming}}
            <fieldset class="setting-choices" data-test-terminal-themes>
              <legend class="visually-hidden">Terminal colours</legend>
              {{#each TERMINAL_CHOICES key="theme" as |choice|}}
                <label class="setting-choice">
                  <input
                    type="radio"
                    name="terminal-theme"
                    value={{choice.theme}}
                    checked={{eq this.terminal.theme choice.theme}}
                    data-test-terminal-theme={{choice.theme}}
                    {{on "change" (fn this.themeTerminal choice.theme)}}
                  />
                  {{choice.name}}
                </label>
              {{/each}}
            </fieldset>
          {{/if}}
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
      {{#if this.harvestSwitch.settingUp}}
        <HarvestSetup />
      {{/if}}
    </span>
  </template>
}
