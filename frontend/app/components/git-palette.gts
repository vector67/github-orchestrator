import type { TOC } from '@ember/component/template-only';
import { on } from '@ember/modifier';
import { fn, get } from '@ember/helper';
import type { GitRun } from 'frontend/data/api';
import {
  GIT_COMMANDS,
  WHERE_WORDS,
  keysLabel,
  reachable,
} from 'frontend/data/git';
import type GitPaletteState from 'frontend/components/git-palette-state';

interface GitPaletteSignature {
  Args: {
    number: number | null;
    palette: GitPaletteState;
  };
}

const secondsOf = (answer: GitRun): string => answer.seconds.toFixed(1);

const ok = (answer: GitRun): boolean => answer.exit_code === 0;

const GitPalette: TOC<GitPaletteSignature> = <template>
  <div class="palette-scrim" data-test-palette-scrim>
    <button
      type="button"
      class="palette-away"
      tabindex="-1"
      aria-label="close the git palette"
      {{on "click" @palette.close}}
    ></button>
    <div
      class="palette {{if @palette.ran 'ran'}}"
      role="dialog"
      aria-label="git palette"
      data-test-palette
    >
      <div class="ph"><span>Git · #{{@number}}</span><button
          type="button"
          class="linkish"
          {{on "click" @palette.close}}
        >Esc closes</button></div>
      {{#if @palette.ran}}
        <div class="git-output" data-test-git-output>
          <b data-test-git-output-command>{{@palette.ran.command}}</b>
          {{#if @palette.ran.answer}}
            <span
              class="git-status {{unless (ok @palette.ran.answer) 'failed'}}"
              data-test-git-output-status
            >{{#if (ok @palette.ran.answer)}}✓{{else}}<i
                  class="sq alarm"
                  data-test-alarm
                ></i>✗{{/if}}
              exit
              {{@palette.ran.answer.exit_code}}
              ({{secondsOf @palette.ran.answer}}s)</span>
            <ol class="git-lines">
              {{#each @palette.ran.answer.lines key="@index" as |line|}}
                <li data-test-git-output-line>{{line}}</li>
              {{/each}}
            </ol>
            {{#if @palette.ran.answer.truncated}}
              <p class="note" data-test-git-output-truncated>Only the first 2000
                lines are shown.</p>
            {{/if}}
          {{else}}
            <span class="git-status failed" data-test-git-output-status><i
                class="sq alarm"
                data-test-alarm
              ></i>{{@palette.ran.failed}}</span>
          {{/if}}
          <span class="note">Esc or any key closes</span>
        </div>
      {{else}}
        {{#each GIT_COMMANDS key="keys" as |one|}}
          <button
            type="button"
            class="p {{unless (reachable one @palette.typed) 'dim'}}"
            data-test-palette-row={{one.keys}}
            {{on "click" (fn @palette.choose one.keys)}}
          >
            <span>g {{keysLabel one}}</span>
            <span>{{one.display}}</span>
            <span class="where">{{get WHERE_WORDS one.where}}</span>
          </button>
        {{/each}}
        <div class="buf" data-test-palette-buffer>&gt; g
          {{@palette.typed}}</div>
        <div class="foot">
          <span class="note" data-test-palette-footer>{{@palette.footer}}</span>
          {{#if @palette.runLabel}}
            <button
              type="button"
              class="btn fill"
              disabled={{@palette.running}}
              data-test-palette-run
              {{on "click" @palette.run}}
            >{{@palette.runLabel}} <kbd>Enter</kbd></button>
          {{/if}}
        </div>
      {{/if}}
    </div>
  </div>
</template>;

export default GitPalette;
