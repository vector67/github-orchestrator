import Component from '@glimmer/component';
import { service } from '@ember/service';
import { on } from '@ember/modifier';
import { fn } from '@ember/helper';
import DiffSlot from 'frontend/components/diff-slot';
import modal from 'frontend/modifiers/modal';
import type { Fold, ReworkView } from 'frontend/data/panel';
import type ReworkService from 'frontend/services/rework';

export interface ReworkDialogSignature {
  Element: HTMLDivElement;
  Args: {
    conversationId: string;
    rework: ReworkView;
    fold?: Fold | null;
    send: () => void;
    cancel: () => void;
  };
}

const CHIPS_SHOWN = 3;

export default class ReworkDialog extends Component<ReworkDialogSignature> {
  @service declare rework: ReworkService;

  get counted(): string {
    const count = this.rework.count;
    return `${count} ${count === 1 ? 'line' : 'lines'} pointed`;
  }

  get chips() {
    return this.rework.pointed.slice(0, CHIPS_SHOWN).map((one) => ({
      id: this.rework.idOf(one),
      text: one.text.trim(),
    }));
  }

  get folded(): number {
    return Math.max(0, this.rework.count - CHIPS_SHOWN);
  }

  type = (event: Event) => {
    this.rework.note = (event.target as HTMLTextAreaElement).value;
  };

  ticked = (author: string): boolean => this.rework.isIncluded(author);

  tick = (author: string) => this.rework.toggleReviewer(author);

  unpoint = (id: string) => this.rework.remove(id);

  showIt = (event: Event) => {
    this.rework.visible = (event.target as HTMLInputElement).checked;
  };

  send = (event: Event) => {
    event.preventDefault();
    if (this.rework.empty) return;
    this.args.send();
  };

  <template>
    <div class="rework-dialog" data-test-rework-dialog ...attributes>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="rework-dialog-kicker"
        tabindex="-1"
        {{modal @cancel}}
        {{on "submit" this.send}}
      >
        <header class="dialog-head">
          <p class="question" id="rework-dialog-kicker" data-test-rework-kicker>
            {{@rework.kicker}}
          </p>
          <button
            type="button"
            class="dialog-close"
            aria-label="close"
            data-test-rework-close
            {{on "click" @cancel}}
          >×</button>
        </header>
        <textarea
          aria-label="what to change"
          data-test-rework-body
          rows="3"
          placeholder={{@rework.placeholder}}
          value={{this.rework.note}}
          {{on "input" this.type}}
        ></textarea>
        <div class="composer-brief">
          <span class="pointed-count" data-test-pointed-count>
            {{this.counted}}
          </span>
          {{#each this.chips key="id" as |chip|}}
            <button
              type="button"
              class="chip"
              data-test-chip
              {{on "click" (fn this.unpoint chip.id)}}
            ><span class="chip-code" data-test-chip-code>{{chip.text}}</span>
              <span class="chip-cross">&times;</span></button>
          {{/each}}
          {{#if this.folded}}
            <span class="chip-overflow" data-test-chip-overflow>
              +{{this.folded}}
              more
            </span>
          {{/if}}
          {{#each @rework.reviewers key="author" as |reviewer|}}
            <label class="composer-tick" data-test-include={{reviewer.author}}>
              <input
                type="checkbox"
                class="checkbox"
                checked={{this.ticked reviewer.author}}
                {{on "change" (fn this.tick reviewer.author)}}
              />
              {{reviewer.label}}
            </label>
          {{/each}}
        </div>
        <label class="composer-tick" data-test-rework-visible>
          <input
            type="checkbox"
            class="checkbox"
            checked={{this.rework.visible}}
            {{on "change" this.showIt}}
          />
          Do rework in visible terminal session
        </label>
        {{#if @fold}}
          <section class="rework-diff">
            <p class="dialog-kicker" data-test-pointing-title>
              {{@fold.pointing_title}}
            </p>
            <DiffSlot
              @conversationId={{@conversationId}}
              @commits={{@fold.commits}}
              @pointable={{true}}
            />
          </section>
        {{/if}}
        <div class="dialog-actions">
          <button
            type="submit"
            class="primary"
            data-test-send-rework
            disabled={{this.rework.empty}}
          >{{@rework.send_label}}</button>
          <button
            type="button"
            class="ghost"
            data-test-cancel-rework
            {{on "click" @cancel}}
          >Cancel</button>
          <span
            class="actions-note"
            data-test-rework-note
          >{{@rework.note}}</span>
        </div>
      </form>
    </div>
  </template>
}
