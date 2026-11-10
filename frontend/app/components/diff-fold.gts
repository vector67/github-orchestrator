import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
import { on } from '@ember/modifier';
import { service } from '@ember/service';
import DiffSlot from 'frontend/components/diff-slot';
import { modifier } from 'ember-modifier';
import type { Fold } from 'frontend/data/panel';
import type KeysService from 'frontend/services/keys';
import type { Keymap } from 'frontend/services/keys';

export interface DiffFoldSignature {
  Element: HTMLDivElement;
  Args: {
    conversationId: string;
    fold: Fold;
    anchor?: string;
  };
}

export default class DiffFold extends Component<DiffFoldSignature> {
  @service declare keys: KeysService;

  @tracked expanded = false;

  private readonly keymap: Keymap = { take: (key) => this.takes(key) };

  private frame: Element | null = null;

  load = (frame: Element) => {
    this.frame = frame;
    this.keys.push('board', this.keymap);
  };

  inserted = modifier((frame: Element) => {
    this.load(frame);
  });

  willDestroy(): void {
    super.willDestroy();
    this.keys.drop(this.keymap);
  }

  private get folded(): boolean {
    return Boolean(this.frame?.closest('details:not([open])'));
  }

  private takes(key: string): boolean {
    if (this.folded) return false;
    if (key === 'Escape') return this.close();
    if (key !== 'z') return false;
    this.toggle();
    return true;
  }

  toggle = () => {
    this.expanded = !this.expanded;
  };

  close = (): boolean => {
    if (!this.expanded) return false;
    this.expanded = false;
    return true;
  };

  <template>
    <div
      class="diff-frame"
      data-test-frame
      data-expanded={{if this.expanded "1"}}
      {{this.inserted}}
      ...attributes
    >
      <div class="diff-frame-head">
        <span class="diff-frame-title">
          {{#if this.expanded}}
            <span class="diff-frame-file" data-test-fold-file>
              {{@anchor}}
            </span>
          {{/if}}
          <span data-test-fold-title>{{@fold.title}}</span>
        </span>
        <span class="diff-frame-tools">
          {{#if this.expanded}}
            <span class="esc-hint" data-test-esc-hint>Esc to close</span>
          {{/if}}
          <button
            type="button"
            class="expand-diff"
            data-test-expand
            data-test-full-screen
            {{on "click" this.toggle}}
          >{{if this.expanded "Close" "Full screen"}} <kbd>z</kbd></button>
        </span>
      </div>
      <DiffSlot
        @conversationId={{@conversationId}}
        @commits={{@fold.commits}}
      />
    </div>
  </template>
}
