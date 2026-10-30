import Component from '@glimmer/component';
import { on } from '@ember/modifier';
import type RouterService from '@ember/routing/router-service';
import { service } from '@ember/service';
import {
  LINES_GONE,
  commentingOn,
  linesOf,
  questionAbout,
  type Lines,
  type Selection,
} from 'frontend/data/selection';
import { inLatestOf } from 'frontend/data/anchors';
import didChange from 'frontend/modifiers/did-change';
import { NEW_DRAFT, type Copy, type Saved } from 'frontend/services/drafts';
import PendingRing from 'frontend/components/pending-ring';
import type { Pressing } from 'frontend/data/decisions';
import type BoardService from 'frontend/services/board';
import type DraftsService from 'frontend/services/drafts';
import type TerminalService from 'frontend/services/terminal';
import autocomplete from 'frontend/modifiers/autocomplete';

export interface CommentBoxSignature {
  Args: {
    selection: Selection | null;
    posted?: Lines | null;
    from?: string | null;
    draft: string;
    saved: Saved;
    close: () => void;
  };
}

export default class CommentBox extends Component<CommentBoxSignature> {
  @service declare drafts: DraftsService;
  @service declare board: BoardService;
  @service declare terminal: TerminalService;
  @service declare router: RouterService;

  get copy(): Copy {
    return this.drafts.copyOf(this.args.draft, this.args.saved);
  }

  get commenting(): string {
    const selection = this.args.selection;
    if (!selection) return LINES_GONE;
    const posted = this.args.posted ?? null;
    return commentingOn(selection) + inLatestOf(linesOf(selection), posted);
  }

  get creating(): boolean {
    return this.args.draft === NEW_DRAFT;
  }

  get unsaveable(): boolean {
    return !this.drafts.saveable(this.args.draft, this.args.saved);
  }

  get asking(): Pressing | null {
    return this.creating ? (this.terminal.pressing?.ask ?? null) : null;
  }

  get pending(): string | null {
    if (!this.creating) return null;
    return this.asking?.pending ?? this.drafts.making.pending;
  }

  get refused(): string | null {
    if (!this.creating) return null;
    return this.asking?.refused ?? this.drafts.making.refused;
  }

  focus = (element: HTMLElement) => {
    element.focus();
  };

  type = (event: Event) => {
    const value = (event.target as HTMLTextAreaElement).value;
    this.drafts.change(this.args.draft, this.args.saved, 'body', value);
  };

  press = (event: KeyboardEvent) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    this.args.close();
  };

  save = async (event: Event) => {
    event.preventDefault();
    const went = this.creating
      ? await this.drafts.create()
      : this.drafts.edit(this.args.draft, this.args.saved);
    if (went) this.args.close();
  };

  add = async () => {
    const made = await this.drafts.create();
    if (!made) return;
    this.args.close();
    await this.board.decide(made, 'enrol');
  };

  get unaskable(): boolean {
    return (
      Boolean(this.asking?.pressed) ||
      this.args.selection === null ||
      this.copy.body.trim() === ''
    );
  }

  ask = async () => {
    const selection = this.args.selection;
    if (selection === null) return;
    const prompt = questionAbout(
      this.args.posted ?? linesOf(selection),
      this.copy.body,
      null,
      this.args.from ?? null,
    );
    if (await this.terminal.ask(prompt, null)) {
      void this.router.transitionTo('terminal');
    }
  };

  <template>
    <form
      class="comment-box"
      data-pending={{if this.pending "true"}}
      data-refused={{if this.refused "true"}}
      data-test-comment-box
      {{on "submit" this.save}}
    >
      <span class="commenting" data-test-commenting>{{#if
          this.asking.ring
        }}<PendingRing />{{/if}}{{if
          this.pending
          this.pending
          this.commenting
        }}</span>
      {{#if this.refused}}
        <p class="refusal" data-test-refusal>{{this.refused}}</p>
      {{/if}}
      <textarea
        aria-label="the comment"
        rows="4"
        placeholder="Leave a comment"
        value={{this.copy.body}}
        {{didChange this.focus}}
        {{on "input" this.type}}
        {{on "keydown" this.press}}
        {{autocomplete}}
      ></textarea>
      <div class="box-foot">
        <button
          type="button"
          class="box-cancel"
          data-test-box-cancel
          {{on "click" @close}}
        >Cancel</button>
        {{#if this.creating}}
          <button
            type="button"
            class="box-draft"
            data-test-box-ask
            disabled={{this.unaskable}}
            {{on "click" this.ask}}
          >Ask the agent</button>
          <button
            type="submit"
            class="box-draft"
            data-test-box-save
            disabled={{this.unsaveable}}
          >Save as local draft</button>
          <button
            type="button"
            class="reply-send"
            data-test-box-add
            disabled={{this.unsaveable}}
            {{on "click" this.add}}
          >Add to review</button>
        {{else}}
          <button
            type="submit"
            class="reply-send"
            data-test-box-save
            disabled={{this.unsaveable}}
          >Save draft</button>
        {{/if}}
      </div>
    </form>
  </template>
}
