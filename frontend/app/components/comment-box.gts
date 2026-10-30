import Component from '@glimmer/component';
import { tracked } from '@glimmer/tracking';
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

  @tracked private sending = false;

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
    if (await this.drafts.save(this.args.draft, this.args.saved)) {
      this.args.close();
    }
  };

  add = async () => {
    const made = await this.drafts.save(this.args.draft, this.args.saved);
    if (!made) return;
    this.args.close();
    await this.board.decide(made, 'enrol');
  };

  get unaskable(): boolean {
    return (
      this.sending ||
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
    this.sending = true;
    try {
      if (await this.terminal.ask(prompt)) {
        void this.router.transitionTo('terminal');
      }
    } finally {
      this.sending = false;
    }
  };

  <template>
    <form class="comment-box" data-test-comment-box {{on "submit" this.save}}>
      <span class="commenting" data-test-commenting>{{this.commenting}}</span>
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
