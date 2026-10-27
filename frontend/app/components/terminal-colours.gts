import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import modal from 'frontend/modifiers/modal';
import { DARK_THEMES, LIGHT_THEMES } from 'frontend/data/terminal-themes';
import {
  TERMINAL_THEMES,
  type TerminalTheme,
} from 'frontend/services/terminal';
import type TerminalService from 'frontend/services/terminal';

interface TerminalColoursSignature {
  Args: { close: () => void };
}

const MODE_NAMES: Record<TerminalTheme, string> = {
  system: 'System',
  light: 'Light',
  dark: 'Dark',
};

const MODES = TERMINAL_THEMES.map((mode) => ({
  mode,
  name: MODE_NAMES[mode],
}));

const eq = (one: unknown, other: unknown): boolean => one === other;

export default class TerminalColours extends Component<TerminalColoursSignature> {
  @service declare terminal: TerminalService;

  readonly lightThemes = LIGHT_THEMES;
  readonly darkThemes = DARK_THEMES;

  mode = (mode: TerminalTheme) => this.terminal.chooseTheme(mode);

  light = (key: string) => this.terminal.chooseLightTheme(key);

  dark = (key: string) => this.terminal.chooseDarkTheme(key);

  <template>
    <div class="decide-dialog">
      <form
        class="terminal-colours"
        role="dialog"
        aria-modal="true"
        aria-labelledby="terminal-colours-title"
        tabindex="-1"
        data-test-terminal-colours
        {{modal @close}}
      >
        <header class="dialog-head">
          <p class="question" id="terminal-colours-title">Terminal colours</p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            {{on "click" @close}}
          >×</button>
        </header>
        <fieldset class="setting-choices">
          <legend>Mode</legend>
          {{#each MODES key="mode" as |choice|}}
            <label class="setting-choice">
              <input
                type="radio"
                name="terminal-theme"
                value={{choice.mode}}
                checked={{eq this.terminal.theme choice.mode}}
                data-test-terminal-theme={{choice.mode}}
                {{on "change" (fn this.mode choice.mode)}}
              />
              {{choice.name}}
            </label>
          {{/each}}
        </fieldset>
        <div class="terminal-schemes">
          <fieldset class="setting-choices">
            <legend>Light theme</legend>
            {{#each this.lightThemes key="key" as |theme|}}
              <label class="setting-choice">
                <input
                  type="radio"
                  name="terminal-light-theme"
                  value={{theme.key}}
                  checked={{eq this.terminal.lightTheme theme.key}}
                  data-test-light-theme={{theme.key}}
                  {{on "change" (fn this.light theme.key)}}
                />
                <span data-test-light-theme-name>{{theme.name}}</span>
              </label>
            {{/each}}
          </fieldset>
          <fieldset class="setting-choices">
            <legend>Dark theme</legend>
            {{#each this.darkThemes key="key" as |theme|}}
              <label class="setting-choice">
                <input
                  type="radio"
                  name="terminal-dark-theme"
                  value={{theme.key}}
                  checked={{eq this.terminal.darkTheme theme.key}}
                  data-test-dark-theme={{theme.key}}
                  {{on "change" (fn this.dark theme.key)}}
                />
                <span data-test-dark-theme-name>{{theme.name}}</span>
              </label>
            {{/each}}
          </fieldset>
        </div>
      </form>
    </div>
  </template>
}
